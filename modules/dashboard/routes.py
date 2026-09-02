# ============================================================
# DXT CONTA - Dashboard Ejecutivo - Rutas
# ============================================================

from __future__ import annotations

from datetime import date, datetime

from flask import Response, jsonify, render_template, request, session, url_for

from modules.dashboard import dashboard_bp
from modules.dashboard.services.catalogos import obtener_unidades_negocio
from modules.dashboard.services.config import RANGOS, RANGO_DEFAULT, ROLES_LECTURA
from modules.dashboard.services.utils import build_filters, fetch_one, parse_date
from modules.dashboard.services.dashboard import build_dashboard_payload
from modules.dashboard.services.export_pdf import build_pdf
from utils.decorators import login_required, roles_required


def _json_ok(**payload):
    return jsonify({'ok': True, **payload})


def _json_error(message: str, status: int = 400):
    return jsonify({'ok': False, 'message': message}), status


def _quick_report_url(report_id: str, alcance: str = 'hoy', grupo: str = '') -> str:
    try:
        return url_for('reportes_rapidos.index', reporte=report_id, alcance=alcance, grupo=grupo)
    except Exception:
        return '#'




def _safe_url(endpoint: str, **values) -> str:
    try:
        return url_for(endpoint, **values)
    except Exception:
        return '#'


def _usuario_actual() -> str:
    return (
        session.get('nombre')
        or session.get('correo')
        or session.get('ci_nit')
        or session.get('usuario')
        or session.get('username')
        or 'Sistema'
    )


def _puede_editar_tipo_cambio() -> bool:
    return session.get('rol_id') in [9, 10]


def _tipo_cambio_payload(fecha_ref):
    row = fetch_one(
        """
        SELECT
            fecha,
            usd_paralelo,
            ufv,
            registrado_por,
            registrado_en,
            actualizado_por,
            actualizado_en
        FROM contabilidad.tipo_cambio
        WHERE fecha = %s
        LIMIT 1
        """,
        (fecha_ref,),
    )
    existe = bool(row)
    usd = row.get('usd_paralelo') if existe else None
    ufv = row.get('ufv') if existe else None
    return {
        'fecha': fecha_ref.isoformat(),
        'existe': existe,
        'requiere_carga': not existe,
        'puede_editar': _puede_editar_tipo_cambio(),
        'usd_paralelo': float(usd) if usd is not None else None,
        'ufv': float(ufv) if ufv is not None else None,
        'usd_label': f"Bs {float(usd):.4f}" if usd is not None else 'Sin registro',
        'ufv_label': f"{float(ufv):.6f}" if ufv is not None else 'Sin registro',
        'registrado_por': row.get('registrado_por') if existe else None,
        'registrado_en': str(row.get('registrado_en') or '') if existe else None,
        'actualizado_por': row.get('actualizado_por') if existe else None,
        'actualizado_en': str(row.get('actualizado_en') or '') if existe else None,
        'gestion_url': _safe_url('tipo_cambio.gestion'),
    }

def _quick_links():
    return [
        {
            'label': 'Cuentas por cobrar',
            'icono': 'fas fa-hand-holding-dollar',
            'url': _quick_report_url('cuentas_por_cobrar_pendientes', alcance='hoy'),
        },
        {
            'label': 'Cuentas por pagar',
            'icono': 'fas fa-file-invoice-dollar',
            'url': _quick_report_url('cuentas_por_pagar_pendientes', alcance='hoy'),
        },
        {
            'label': 'Pagos realizados',
            'icono': 'fas fa-money-bill-transfer',
            'url': _quick_report_url('pagos_realizados', alcance='hoy'),
        },
        {
            'label': 'Cobros realizados',
            'icono': 'fas fa-cash-register',
            'url': _quick_report_url('cobros_realizados', alcance='hoy'),
        },
        {
            'label': 'Licencias',
            'icono': 'fas fa-id-card',
            'url': _quick_report_url('publicidad_licencias_por_vencer', alcance='proximos_30', grupo='todos'),
        },
        {
            'label': 'Contratos',
            'icono': 'fas fa-file-signature',
            'url': _quick_report_url('publicidad_contratos_por_vencer', alcance='proximos_30', grupo='pendientes'),
        },
    ]


@dashboard_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    hoy = date.today()
    return render_template(
        'dashboard_index.html',
        fecha_hoy=hoy.isoformat(),
        rangos=[{'id': key, 'label': value} for key, value in RANGOS.items()],
        rango_default=RANGO_DEFAULT,
        unidades_negocio=obtener_unidades_negocio(),
        quick_links=_quick_links(),
        urls={
            'data': url_for('dashboard.data'),
            'pdf': url_for('dashboard.pdf'),
            'help': url_for('dashboard.help'),
            'tipo_cambio': url_for('dashboard.tipo_cambio_estado'),
            'tipo_cambio_gestion': _safe_url('tipo_cambio.gestion'),
        },
    )


@dashboard_bp.route('/api/resumen')
@login_required
@roles_required(ROLES_LECTURA)
def data():
    try:
        filters = build_filters(request.args)
        payload = build_dashboard_payload(filters)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:  # pragma: no cover - defensa operativa
        return _json_error(f'No se pudo generar el dashboard. {exc}', 500)


@dashboard_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filters = build_filters(request.args)
        payload = build_dashboard_payload(filters)
        pdf_bytes = build_pdf(payload)
        nombre = f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:  # pragma: no cover - defensa operativa
        return _json_error(f'No se pudo generar el PDF ejecutivo. {exc}', 500)


@dashboard_bp.route('/api/tipo-cambio')
@login_required
@roles_required(ROLES_LECTURA)
def tipo_cambio_estado():
    try:
        fecha_ref = parse_date(request.args.get('fecha'), 'Fecha', default=date.today())
        return _json_ok(tipo_cambio=_tipo_cambio_payload(fecha_ref))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:  # pragma: no cover
        return _json_error(f'No se pudo consultar el tipo de cambio. {exc}', 500)


@dashboard_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('dashboard_help.html')
