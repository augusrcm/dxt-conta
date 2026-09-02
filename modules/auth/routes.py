from __future__ import annotations

import base64
import json
import mimetypes
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import bcrypt
import psycopg2.extras
from flask import current_app, flash, redirect, render_template, request, session, url_for

from database.db import get_db
from modules.auth import auth_bp

_login_attempts: dict[str, deque[datetime]] = defaultdict(deque)


def _client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def _is_locked(identifier: str) -> bool:
    window = timedelta(seconds=current_app.config['LOGIN_ATTEMPT_WINDOW_SECONDS'])
    lock_seconds = current_app.config['LOGIN_LOCKOUT_SECONDS']
    now = datetime.utcnow()
    attempts = _login_attempts[identifier]
    while attempts and now - attempts[0] > window:
        attempts.popleft()
    if len(attempts) >= current_app.config['LOGIN_MAX_ATTEMPTS']:
        return (now - attempts[-1]).total_seconds() < lock_seconds
    return False


def _register_attempt(identifier: str) -> None:
    _login_attempts[identifier].append(datetime.utcnow())


def _clear_attempts(identifier: str) -> None:
    _login_attempts.pop(identifier, None)


def _file_to_data_uri(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ''
    mime_type, _ = mimetypes.guess_type(str(path))
    mime_type = mime_type or 'application/octet-stream'
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{mime_type};base64,{encoded}'


def _resolve_logo_data_uri() -> str:
    logo_dir = Path(current_app.config['LOGO_FOLDER'])
    preferred = (logo_dir / current_app.config['LOGIN_LOGO_FILENAME']).resolve()
    if preferred.exists():
        return _file_to_data_uri(preferred)
    fallback = (logo_dir / current_app.config['SIDEBAR_LOGO_FILENAME']).resolve()
    if fallback.exists():
        return _file_to_data_uri(fallback)
    for candidate in sorted(logo_dir.glob('*')):
        if candidate.is_file():
            return _file_to_data_uri(candidate)
    return ''


def _login_context(**extra):
    payload = {
        'captcha_checked': False,
        'identifier': '',
        'error_message': '',
        'turnstile_enabled': current_app.config['TURNSTILE_ENABLED'],
        'turnstile_mode': current_app.config['TURNSTILE_MODE'],
        'turnstile_site_key': current_app.config['TURNSTILE_SITE_KEY'],
        'turnstile_placeholder_label': current_app.config['TURNSTILE_PLACEHOLDER_LABEL'],
        'login_logo_data_uri': _resolve_logo_data_uri(),
    }
    payload.update(extra)
    return payload


def _error_reference() -> str:
    return uuid.uuid4().hex[:8].upper()


def _login_temporarily_unavailable_message(reference: str) -> str:
    return (
        'No pudimos completar el ingreso en este momento. '
        'Intenta nuevamente en unos minutos. '
        'Si el problema continúa, contacta al administrador. '
        f'Código de seguimiento: {reference}.'
    )


def _security_validation_unavailable_message(reference: str) -> str:
    return (
        'La verificación de seguridad no está disponible en este momento. '
        'Intenta nuevamente en unos minutos. '
        'Si el problema continúa, contacta al administrador. '
        f'Código de seguimiento: {reference}.'
    )


def _verify_turnstile_token(token: str) -> tuple[bool, str | None]:
    secret = (current_app.config.get('TURNSTILE_SECRET_KEY') or '').strip()
    if not secret:
        ref = _error_reference()
        current_app.logger.error('[AUTH:%s] Configuración incompleta de Turnstile: falta TURNSTILE_SECRET_KEY.', ref)
        return False, _security_validation_unavailable_message(ref)

    payload = {'secret': secret, 'response': token}
    remote_ip = _client_ip()
    if remote_ip:
        payload['remoteip'] = remote_ip

    data = urlencode(payload).encode('utf-8')
    req = Request(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )

    timeout = int(current_app.config.get('TURNSTILE_VERIFY_TIMEOUT_SECONDS', 5) or 5)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', 'replace')
    except Exception:
        current_app.logger.exception('No se pudo validar Turnstile con Cloudflare.')
        return False, 'No se pudo validar la verificación de humanidad. Intenta nuevamente.'

    try:
        result = json.loads(raw)
    except Exception:
        current_app.logger.error('Respuesta inválida de Turnstile: %s', raw[:500])
        return False, 'No se pudo validar la verificación de humanidad. Intenta nuevamente.'

    if result.get('success') is True:
        return True, None

    current_app.logger.warning(
        'Turnstile rechazado. error_codes=%s hostname=%s action=%s',
        result.get('error-codes'),
        result.get('hostname'),
        result.get('action'),
    )
    codes = set(result.get('error-codes') or [])
    if 'timeout-or-duplicate' in codes:
        return False, 'La verificación de humanidad expiró o ya fue usada. Intenta nuevamente.'
    return False, 'No se pudo validar la verificación de humanidad.'


def _validate_turnstile() -> tuple[bool, str | None]:
    if not current_app.config['TURNSTILE_ENABLED']:
        return True, None

    if current_app.config['TURNSTILE_MODE'] == 'placeholder':
        checkbox_value = (request.form.get('cf_turnstile_ok') or '').strip().lower()
        if checkbox_value not in {'1', 'true', 'on', 'yes'}:
            return False, 'Debes completar la verificación de humanidad.'
        return True, None

    token = (request.form.get('cf-turnstile-response') or '').strip()
    if not token:
        return False, 'Debes completar la verificación de humanidad.'
    return _verify_turnstile_token(token)


def _normalize_hash(stored_hash: str | None) -> bytes:
    encoded = (stored_hash or '').encode('utf-8')
    if encoded.startswith(b'$2y$'):
        encoded = b'$2b$' + encoded[4:]
    return encoded


def _verify_password(raw_password: str, stored_hash: str | None) -> bool:
    normalized = _normalize_hash(stored_hash)
    if not normalized:
        return False
    try:
        return bcrypt.checkpw(raw_password.encode('utf-8'), normalized)
    except Exception:
        return False


def _find_user(identifier: str):
    allowed_roles = tuple(current_app.config.get('CONTA_ALLOWED_ROLE_IDS', (9, 10, 11)))
    placeholders = ','.join(['%s'] * len(allowed_roles))
    sql = f"""
        SELECT
            id,
            ci_nit,
            nombre,
            correo,
            password,
            activo,
            rol_id
        FROM usuarios.usuarios
        WHERE (ci_nit = %s OR LOWER(correo) = LOWER(%s))
          AND activo = TRUE
          AND rol_id IN ({placeholders})
        ORDER BY
            CASE rol_id
                WHEN 9 THEN 1
                WHEN 10 THEN 2
                WHEN 11 THEN 3
                ELSE 99
            END,
            id DESC
        LIMIT 1
    """
    params = (identifier, identifier, *allowed_roles)
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', **_login_context(captcha_checked=False))

    identifier = (request.form.get('identifier') or request.form.get('identificador') or '').strip()
    password = (request.form.get('password') or '').strip()
    captcha_checked = (request.form.get('cf_turnstile_ok') or '').strip().lower() in {'1', 'true', 'on', 'yes'}

    if not identifier or not password:
        flash('Ingresa tu correo o CI/NIT y tu contraseña para continuar.', 'warning')
        return render_template('login.html', **_login_context(identifier=identifier, captcha_checked=captcha_checked))

    locked_key = f'{_client_ip()}::{identifier.lower()}'
    if _is_locked(locked_key):
        flash('Por seguridad, pausamos temporalmente el ingreso por varios intentos consecutivos. Intenta nuevamente en unos minutos.', 'error')
        return render_template('login.html', **_login_context(identifier=identifier, captcha_checked=captcha_checked))

    turnstile_ok, turnstile_msg = _validate_turnstile()
    if not turnstile_ok:
        flash(turnstile_msg or 'No se pudo validar la verificación de humanidad.', 'error')
        return render_template('login.html', **_login_context(identifier=identifier, captcha_checked=captcha_checked))

    try:
        user = _find_user(identifier)
    except Exception:
        ref = _error_reference()
        current_app.logger.exception('[AUTH:%s] Error consultando usuario durante el login.', ref)
        flash(_login_temporarily_unavailable_message(ref), 'error')
        return render_template('login.html', **_login_context(identifier=identifier, captcha_checked=captcha_checked))

    if not user or not _verify_password(password, user.get('password')):
        _register_attempt(locked_key)
        flash('No pudimos validar esas credenciales o tu cuenta no tiene acceso a Contabilidad.', 'error')
        return render_template('login.html', **_login_context(identifier=identifier, captcha_checked=captcha_checked))

    if not user.get('activo'):
        flash('Tu cuenta no está activa. Solicita apoyo al administrador.', 'error')
        return render_template('login.html', **_login_context(identifier=identifier, captcha_checked=captcha_checked))

    _clear_attempts(locked_key)
    session.clear()
    session['user_id'] = int(user['id'])
    session['ci_nit'] = user.get('ci_nit') or ''
    session['nombre'] = user.get('nombre') or ''
    session['usuario_nombre'] = user.get('nombre') or ''
    session['correo'] = user.get('correo') or ''
    session['rol_id'] = int(user['rol_id']) if user.get('rol_id') is not None else None
    session['user_name'] = user.get('nombre') or ''
    session['user_email'] = user.get('correo') or ''
    session['user_ci_nit'] = user.get('ci_nit') or ''
    session['user_role_id'] = session['rol_id']
    session['login_at'] = datetime.utcnow().isoformat()
    session['last_activity'] = datetime.utcnow().isoformat()

    return redirect(url_for('dashboard.index'))


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
