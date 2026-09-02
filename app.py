#!/usr/bin/env python3
from __future__ import annotations

import base64
import mimetypes
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from database.db import close_db
from utils.planillas_security import get_csrf_token, validate_csrf_request


def _normalize_base_path(value: str | None) -> str:
    raw = (value or '').strip()
    if not raw or raw == '/':
        return ''
    if not raw.startswith('/'):
        raw = f'/{raw}'
    return raw.rstrip('/')


def _configure_template_loader(app: Flask) -> None:
    base_dir = Path(__file__).resolve().parent
    loaders = [app.jinja_loader, FileSystemLoader(str(base_dir / 'templates'))]
    for template_dir in sorted((base_dir / 'modules').glob('*/templates')):
        loaders.append(FileSystemLoader(str(template_dir)))
    app.jinja_loader = ChoiceLoader(loaders)


def _register_blueprints(app: Flask) -> None:
    from modules.auth import auth_bp
    from modules.dashboard import dashboard_bp
    from modules.plandecuentas.routes import plandecuentas_bp
    from modules.tipo_cambio import tipo_cambio_bp
    from modules.compromisos import compromisos_bp
    from modules.agenda_financiera import agenda_financiera_bp
    from modules.tesoreria_pagos import tesoreria_pagos_bp
    from modules.tesoreria_cobros import tesoreria_cobros_bp
    from modules.monedas import monedas_bp
    from modules.centro_costo import centro_costo_bp
    from modules.auxiliar import auxiliar_bp
    from modules.caja import caja_bp
    from modules.cuenta_bancaria import cuenta_bancaria_bp
    from modules.auxiliar_cuenta import auxiliar_cuenta_bp
    from modules.unidad_negocio import unidad_negocio_bp
    from modules.rubro import rubro_bp
    from modules.tesoreria_caja_bancos import tesoreria_caja_bancos_bp
    from modules.tesoreria_arqueo_caja import tesoreria_arqueo_caja_bp
    from modules.tesoreria_bancarizacion import tesoreria_bancarizacion_bp
    from modules.facturas_electronicas import facturas_electronicas_bp
    from modules.facturas_mantenimiento import facturas_mantenimiento_bp
    from modules.comprobantes import comprobantes_bp
    from modules.libro_diario import libro_diario_bp
    from modules.libro_mayor import libro_mayor_bp
    from modules.balance_comprobacion import balance_comprobacion_bp
    from modules.balance_general import balance_general_bp
    from modules.estado_resultados import estado_resultados_bp
    from modules.cierre_gestion import cierre_gestion_bp
    from modules.saldos_iniciales import saldos_iniciales_bp
    from modules.configuracion_inicial import configuracion_inicial_bp
    from modules.backups_gestion import backups_gestion_bp
    from modules.reportes_rapidos import reportes_rapidos_bp
    from modules.facturas_auxiliar import facturas_auxiliar_bp
    from modules.estado_resultados_mes import estado_resultados_mes_bp
    from modules.caja_bancos_estado import caja_bancos_estado_bp
    from modules.auxiliar_estado import auxiliar_estado_bp
    from modules.revision_contable import revision_contable_bp
    from modules.checklist_precierre import checklist_precierre_bp
    from modules.compromisos_vencidos import compromisos_vencidos_bp
    from modules.conciliacion_caja_banco import conciliacion_caja_banco_bp
    from modules.movimientos_observados import movimientos_observados_bp
    from modules.asistente_ajustes import asistente_ajustes_bp
    from modules.bitacora_procesos import bitacora_procesos_bp
    from modules.estado_cuenta_auxiliar import estado_cuenta_auxiliar_bp
    from modules.antiguedad_saldos_cobrar import antiguedad_saldos_cobrar_bp
    from modules.estado_cuentas_cobrar import estado_cuentas_cobrar_bp
    from modules.documentos_cobrar import documentos_cobrar_bp
    from modules.saldos_iniciales_cobrar import saldos_iniciales_cobrar_bp
    from modules.resumen_ejecutivo_mensual import resumen_ejecutivo_mensual_bp
    from modules.movimiento_unidad_negocio import movimiento_unidad_negocio_bp
    from modules.estado_cuentas_pagar import estado_cuentas_pagar_bp
    from modules.planilla_personas import planilla_personas_bp
    from modules.planilla_parametros import planilla_parametros_bp
    from modules.planilla_conceptos import planilla_conceptos_bp
    from modules.planilla_prestamos import planilla_prestamos_bp
    from modules.planilla_sueldos_planta import planilla_sueldos_planta_bp
    from modules.planilla_honorarios_colaboradores import planilla_honorarios_colaboradores_bp
    from modules.planilla_pagos import planilla_pagos_bp
    
    blueprints = (
        auth_bp,
        dashboard_bp,
        plandecuentas_bp,
        tipo_cambio_bp,
        compromisos_bp,
        agenda_financiera_bp,
        tesoreria_pagos_bp,
        tesoreria_cobros_bp,
        monedas_bp,
        centro_costo_bp,
        auxiliar_bp,
        caja_bp,
        cuenta_bancaria_bp,
        auxiliar_cuenta_bp,
        unidad_negocio_bp,
        rubro_bp,
        tesoreria_caja_bancos_bp,
        tesoreria_arqueo_caja_bp,
        tesoreria_bancarizacion_bp,
        facturas_electronicas_bp,
        facturas_mantenimiento_bp,
        comprobantes_bp,
        libro_diario_bp,
        libro_mayor_bp,
        balance_comprobacion_bp,
        balance_general_bp,
        estado_resultados_bp,
        cierre_gestion_bp,
        saldos_iniciales_bp,
        configuracion_inicial_bp,
        backups_gestion_bp,
        reportes_rapidos_bp,
        facturas_auxiliar_bp,
        estado_resultados_mes_bp,
        auxiliar_estado_bp,
        caja_bancos_estado_bp,
        revision_contable_bp,
        checklist_precierre_bp,
        compromisos_vencidos_bp,
        conciliacion_caja_banco_bp,
        movimientos_observados_bp,
        asistente_ajustes_bp,
        bitacora_procesos_bp,
        estado_cuenta_auxiliar_bp,
        antiguedad_saldos_cobrar_bp,
        estado_cuentas_cobrar_bp,
        documentos_cobrar_bp,
        saldos_iniciales_cobrar_bp,
        resumen_ejecutivo_mensual_bp,
        movimiento_unidad_negocio_bp,
        estado_cuentas_pagar_bp,
        planilla_personas_bp,
        planilla_parametros_bp,
        planilla_conceptos_bp,
        planilla_prestamos_bp,
        planilla_sueldos_planta_bp,
        planilla_honorarios_colaboradores_bp,
        planilla_pagos_bp,
    )

    base_path = app.config.get('BASE_PATH', '')
    for bp in blueprints:
        prefix = getattr(bp, 'url_prefix', '') or ''
        if base_path and prefix:
            app.register_blueprint(bp, url_prefix=f'{base_path}{prefix}')
        elif base_path:
            app.register_blueprint(bp, url_prefix=base_path)
        else:
            app.register_blueprint(bp)


def _register_core_routes(app: Flask) -> None:
    base_path = app.config.get('BASE_PATH', '')

    @app.get('/')
    def root():
        return redirect(url_for('auth.login'))

    if base_path:
        @app.get(base_path)
        @app.get(f'{base_path}/')
        def root_alias():
            return redirect(url_for('auth.login'))

    @app.get('/healthz')
    def healthz():
        return jsonify({'ok': True, 'app': app.config['APP_NAME'], 'version': app.config['APP_VERSION']})

    if base_path:
        @app.get(f'{base_path}/healthz')
        def healthz_alias():
            return jsonify({'ok': True, 'app': app.config['APP_NAME'], 'version': app.config['APP_VERSION']})


def _file_to_data_uri(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ''
    mime_type, _ = mimetypes.guess_type(str(path))
    mime_type = mime_type or 'application/octet-stream'
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{mime_type};base64,{encoded}'


def _logo_data_uri(app: Flask, primary_filename: str, fallback_filename: str = '') -> str:
    logo_dir = Path(app.config['LOGO_FOLDER'])
    primary = (logo_dir / primary_filename).resolve()
    if primary.exists():
        return _file_to_data_uri(primary)
    if fallback_filename:
        fallback = (logo_dir / fallback_filename).resolve()
        if fallback.exists():
            return _file_to_data_uri(fallback)
    for candidate in sorted(logo_dir.glob('*')):
        if candidate.is_file():
            return _file_to_data_uri(candidate)
    return ''


def create_app(config_class=None) -> Flask:
    selected_config = config_class or get_config()
    base_path = _normalize_base_path(getattr(selected_config, 'BASE_PATH', ''))
    static_url_path = f'{base_path}/static' if base_path else '/static'
    static_folder = str(Path(getattr(selected_config, 'STATIC_FOLDER', Path(__file__).resolve().parent / 'static')))

    app = Flask(__name__, static_folder=static_folder, static_url_path=static_url_path)
    app.config.from_object(selected_config)
    app.config['BASE_PATH'] = base_path
    app.config['APPLICATION_ROOT'] = '/'
    app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']

    if app.config.get('TRUST_PROXY'):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)  # type: ignore[assignment]

    _configure_template_loader(app)
    _register_blueprints(app)
    _register_core_routes(app)

    from modules.configuracion_inicial import (
        obtener_estado_inicializacion,
        obtener_gestion_operativa_actual,
    )
    from database.db import get_db

    @app.before_request
    def check_session_timeout():
        public_prefixes = ('static', 'auth.')
        if not request.endpoint or request.endpoint.startswith(public_prefixes):
            return None

        if 'user_id' not in session:
            return None

        last_activity = session.get('last_activity')
        if last_activity:
            try:
                last_dt = datetime.fromisoformat(str(last_activity))
            except Exception:
                last_dt = datetime.utcnow()
            idle_seconds = (datetime.utcnow() - last_dt).total_seconds()
            if idle_seconds > app.config['SESSION_TIMEOUT_SECONDS']:
                session.clear()
                is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = 'application/json' in (request.headers.get('Accept') or '')
                is_api_body = request.is_json
                if is_ajax or accepts_json or is_api_body:
                    return jsonify({'ok': False, 'session_expired': True, 'msg': 'Tu sesión expiró por inactividad.'}), 401
                return redirect(url_for('auth.login'))

        session['last_activity'] = datetime.utcnow().isoformat()
        return None

    @app.before_request
    def enforce_global_relogin():
        if not request.endpoint or request.endpoint.startswith(('static', 'auth.')):
            return None

        if 'user_id' not in session:
            return None

        if not session.get('login_at'):
            session['login_at'] = datetime.utcnow().isoformat()
            return None

        try:
            db = get_db()
            cur = db.cursor()
            cur.execute(
                """
                SELECT forzar_relogin_desde
                FROM contabilidad.sistema_control_sesion
                WHERE id = 1
                """
            )
            row = cur.fetchone()
            cur.close()
            forced_at = row['forzar_relogin_desde'] if row and row.get('forzar_relogin_desde') is not None else None
            if forced_at is None:
                return None

            forced_at = forced_at.replace(tzinfo=None) if getattr(forced_at, 'tzinfo', None) else forced_at
            login_dt = datetime.fromisoformat(str(session['login_at'])).replace(tzinfo=None)
            if login_dt < forced_at:
                session.clear()
                is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = 'application/json' in (request.headers.get('Accept') or '')
                is_api_body = request.is_json
                if is_ajax or accepts_json or is_api_body:
                    return jsonify({
                        'ok': False,
                        'session_expired': True,
                        'force_relogin': True,
                        'msg': 'La sesión fue cerrada por una restauración del sistema.',
                    }), 401
                return redirect(url_for('auth.login'))
        except Exception:
            return None
        return None

    @app.before_request
    def protect_planillas_csrf():
        if not request.endpoint or not request.endpoint.startswith('planilla_'):
            return None
        return validate_csrf_request()

    @app.before_request
    def enforce_configuracion_inicial():
        if not request.endpoint:
            return None
        if request.endpoint.startswith(('static', 'auth.')):
            return None
        if 'user_id' not in session:
            return None
        if request.endpoint.startswith('backups_gestion.'):
            return None

        allowed_endpoints = {
            'configuracion_inicial.index',
            'configuracion_inicial.guardar',
            'configuracion_inicial.help',
            'configuracion_inicial.api_cuentas_patrimoniales',
            'tipo_cambio.verificar_hoy',
            'tipo_cambio.registrar',
            'tipo_cambio.gestion',
            'tipo_cambio.api_verificar_dia',
            'tipo_cambio.api_guardar',
        }
        if request.endpoint in allowed_endpoints:
            return None

        try:
            estado = obtener_estado_inicializacion()
        except Exception:
            return None
        if not estado.get('initialized', False):
            return redirect(url_for('configuracion_inicial.index'))
        return None

    @app.after_request
    def apply_security_headers(response):
        for name, value in app.config.get('SECURITY_HEADERS', {}).items():
            response.headers.setdefault(name, value)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if app.config.get('ENABLE_HSTS') and app.config.get('PREFERRED_URL_SCHEME') == 'https':
            response.headers.setdefault('Strict-Transport-Security', f"max-age={app.config.get('HSTS_MAX_AGE', 31536000)}")
        return response

    @app.teardown_appcontext
    def teardown_db(exception):
        close_db(exception)

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        close_db(error)
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    def _build_layout_context():
        current_gestion_label = 'Sin gestión abierta'
        tipo_cambio_hoy_completo = False
        tipo_cambio_hoy_label = 'TC hoy pendiente'

        def _valor_fila(row, key, index=0):
            if row is None:
                return None
            if hasattr(row, 'get'):
                return row.get(key)
            try:
                return row[index]
            except (IndexError, TypeError):
                return None

        def _formato_decimal(valor, decimales):
            if valor is None:
                return None
            try:
                return f"{valor:.{decimales}f}"
            except (TypeError, ValueError):
                return str(valor)

        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT gestion
                FROM contabilidad.gestion_control
                WHERE estado = 'ABIERTA'::contabilidad.estado_gestion_enum
                ORDER BY gestion DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            gestion_abierta = _valor_fila(row, 'gestion', 0)
            if gestion_abierta is not None:
                current_gestion_label = f'Gestión {gestion_abierta} abierta'

            cursor.execute(
                """
                SELECT usd_paralelo, ufv
                FROM contabilidad.tipo_cambio
                WHERE fecha = CURRENT_DATE
                  AND usd_paralelo > 0
                  AND ufv > 0
                LIMIT 1
                """
            )
            tc_row = cursor.fetchone()
            usd_paralelo = _valor_fila(tc_row, 'usd_paralelo', 0)
            ufv = _valor_fila(tc_row, 'ufv', 1)
            tipo_cambio_hoy_completo = usd_paralelo is not None and ufv is not None

            if tipo_cambio_hoy_completo:
                usd_display = _formato_decimal(usd_paralelo, 4)
                ufv_display = _formato_decimal(ufv, 6)
                tipo_cambio_hoy_label = f'TC hoy: $us {usd_display} | UFV {ufv_display}'
        except Exception:
            pass
        finally:
            if cursor is not None:
                cursor.close()

        return {
            'current_gestion_label': current_gestion_label,
            'tipo_cambio_hoy_completo': tipo_cambio_hoy_completo,
            'tipo_cambio_hoy_label': tipo_cambio_hoy_label,
        }

    @app.context_processor
    def inject_globals():
        gestion_actual = None
        configuracion_inicial_pendiente = False

        if session.get('user_id'):
            try:
                estado_inicializacion = obtener_estado_inicializacion()
                configuracion_inicial_pendiente = not estado_inicializacion.get('initialized', False)
                gestion_actual = obtener_gestion_operativa_actual()
            except Exception:
                gestion_actual = None
                configuracion_inicial_pendiente = False

        context = {
            'app_name': app.config['APP_NAME'],
            'app_description': app.config['APP_DESCRIPTION'],
            'app_version': app.config['APP_VERSION'],
            'base_path': app.config.get('BASE_PATH', ''),
            'db_engine': 'PostgreSQL',
            'gestion_actual': gestion_actual,
            'configuracion_inicial_pendiente': configuracion_inicial_pendiente,
            'login_logo_data_uri': _logo_data_uri(app, app.config['LOGIN_LOGO_FILENAME'], app.config['SIDEBAR_LOGO_FILENAME']),
            'sidebar_logo_data_uri': _logo_data_uri(app, app.config['SIDEBAR_LOGO_FILENAME'], app.config['LOGIN_LOGO_FILENAME']),
            'dxt_csrf_token': get_csrf_token,
        }
        context.update(_build_layout_context())
        return context

    return app


if __name__ == '__main__':
    application = create_app()
    application.run(
        host=application.config['HOST'],
        port=application.config['PORT'],
        debug=application.config['DEBUG'],
        use_reloader=application.config['DEBUG'],
    )
