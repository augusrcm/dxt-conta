# ============================================================
# DXT CONTA - Seguridad y validaciones transversales Planillas
# ============================================================

from __future__ import annotations

import secrets
from typing import Any

from flask import jsonify, request, session


_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
_CSRF_SESSION_KEY = '_dxt_csrf_token'


def get_csrf_token() -> str:
    """Devuelve el token CSRF de la sesión actual, generándolo si no existe."""
    token = session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_SESSION_KEY] = token
    return str(token)


def validate_csrf_request():
    """Valida CSRF para operaciones mutantes del módulo de planillas."""
    if request.method not in _MUTATING_METHODS:
        return None
    if 'user_id' not in session:
        return None

    expected = session.get(_CSRF_SESSION_KEY)
    provided = (
        request.headers.get('X-CSRFToken')
        or request.headers.get('X-CSRF-Token')
        or request.form.get('csrf_token')
    )

    if not expected or not provided or not secrets.compare_digest(str(expected), str(provided)):
        return jsonify({
            'success': False,
            'message': 'La solicitud no pudo ser validada. Actualice la pantalla e intente nuevamente.'
        }), 400
    return None


def assert_gestion_abierta(db: Any, gestion: int, accion: str = 'operar') -> None:
    """Bloquea movimientos de planillas sobre gestiones cerradas o inexistentes."""
    rows = db.execute_query(
        """
        SELECT estado
        FROM contabilidad.gestion_control
        WHERE gestion = %s
        LIMIT 1
        """,
        (int(gestion),)
    )
    if not rows:
        raise ValueError(f'No existe una gestión contable configurada para {gestion}.')
    estado = str(rows[0].get('estado') or '').upper()
    if estado != 'ABIERTA':
        raise ValueError(f'No se puede {accion} porque la gestión {gestion} no está abierta.')


def mensaje_error_operacion(accion: str) -> str:
    return f'No se pudo {accion}. Revise los datos ingresados y la configuración operativa del módulo.'
