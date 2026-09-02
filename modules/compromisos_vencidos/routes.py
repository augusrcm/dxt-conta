# ============================================================
# DXT CONTA - Herramientas - Compromisos Vencidos
# Seguimiento de obligaciones por pagar y cobrar pendientes
# ============================================================

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Response, jsonify, render_template, request

from database.db_manager import DatabaseManager
from modules.compromisos_vencidos import compromisos_vencidos_bp
from modules.reportes_rapidos.core.catalogos import obtener_unidades_negocio, unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import dias_label, format_money
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]

TIPOS = [
    {'value': '', 'label': 'Todos'},
    {'value': 'PAGAR', 'label': 'Por pagar'},
    {'value': 'COBRAR', 'label': 'Por cobrar'},
]

RANGOS = [
    {'value': 'VENCIDOS', 'label': 'Vencidos'},
    {'value': 'HOY', 'label': 'Vence hoy'},
    {'value': 'PROXIMOS', 'label': 'Próximos'},
    {'value': 'TODOS', 'label': 'Todos pendientes'},
]

HORIZONTES = [7, 15, 30, 60]

PRIORIDAD_LABEL = {
    'CRITICA': 'Crítica',
    'ALTA': 'Alta',
    'MEDIA': 'Media',
    'BAJA': 'Baja',
}

PRIORIDAD_ORDEN = {
    'CRITICA': 1,
    'ALTA': 2,
    'MEDIA': 3,
    'BAJA': 4,
}

SITUACION_LABEL = {
    'VENCIDO': 'Vencido',
    'HOY': 'Vence hoy',
    'POR_VENCER': 'Por vencer',
    'PENDIENTE': 'Pendiente',
}

TIPO_LABEL = {
    'PAGAR': 'Por pagar',
    'COBRAR': 'Por cobrar',
}


# ============================================================
# Helpers generales
# ============================================================


def _json_ok(**kwargs):
    payload = {'ok': True}
    payload.update(kwargs)
    return jsonify(_json_ready(payload))


def _json_error(message: str, status: int = 400, **kwargs):
    payload = {'ok': False, 'msg': message}
    payload.update(kwargs)
    return jsonify(_json_ready(payload)), status


def _clean(value: Any) -> str:
    return (value or '').strip()


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _parse_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es válido.') from exc
    return parsed


def _parse_optional_int(value: Any, field_name: str) -> int | None:
    raw = _clean(value)
    if not raw:
        return None
    parsed = _parse_int(raw, field_name)
    return parsed if parsed > 0 else None


def _date_label(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    raw = _clean(value)
    if not raw:
        return ''
    try:
        parsed = datetime.strptime(raw[:10], '%Y-%m-%d').date()
        return parsed.strftime('%d/%m/%Y')
    except ValueError:
        return raw


def _db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    return [dict(row) for row in rows]


def _gestion_actual() -> int:
    return date.today().year


def _obtener_gestiones() -> list[int]:
    sql = """
        SELECT gestion
        FROM (
            SELECT gestion::int AS gestion FROM contabilidad.gestion_control
            UNION
            SELECT gestion::int AS gestion FROM contabilidad.compromiso
            UNION
            SELECT EXTRACT(YEAR FROM CURRENT_DATE)::int AS gestion
        ) q
        WHERE gestion IS NOT NULL
        ORDER BY gestion DESC
    """
    rows = _db_rows(sql)
    return [int(row['gestion']) for row in rows] or [_gestion_actual()]


def _gestion_preferida() -> int:
    rows = _db_rows(
        """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
        """
    )
    if rows:
        return int(rows[0]['gestion'])
    return _gestion_actual()


def _tipo_label(value: str) -> str:
    return TIPO_LABEL.get(value, value or 'Todos')


def _rango_label(value: str, dias: int) -> str:
    if value == 'VENCIDOS':
        return 'Compromisos vencidos'
    if value == 'HOY':
        return 'Compromisos que vencen hoy'
    if value == 'PROXIMOS':
        return f'Compromisos próximos a vencer en {dias} día(s)'
    return 'Todos los compromisos pendientes'


def _parse_filters(args) -> dict[str, Any]:
    gestion = _parse_int(args.get('gestion') or _gestion_preferida(), 'Gestión')
    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestión indicada no es válida.')

    tipo = _clean(args.get('tipo')).upper()
    if tipo not in {'', 'PAGAR', 'COBRAR'}:
        raise ValueError('El tipo de compromiso seleccionado no es válido.')

    rango = _clean(args.get('rango') or 'VENCIDOS').upper()
    if rango not in {'VENCIDOS', 'HOY', 'PROXIMOS', 'TODOS'}:
        raise ValueError('El rango seleccionado no es válido.')

    dias = _parse_int(args.get('dias') or 7, 'Días')
    if dias not in set(HORIZONTES):
        raise ValueError('El horizonte de días no es válido.')

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')
    fecha_corte = date.today()
    fecha_hasta = fecha_corte + timedelta(days=dias)

    return {
        'gestion': gestion,
        'tipo': tipo,
        'rango': rango,
        'dias': dias,
        'unidad_negocio_id': unidad_negocio_id,
        'fecha_corte': fecha_corte,
        'fecha_hasta': fecha_hasta,
        'periodo_label': f'Gestión {gestion} · corte {fecha_corte.strftime("%d/%m/%Y")}',
        'unidad_label': unidad_label(unidad_negocio_id),
        'tipo_label': _tipo_label(tipo),
        'rango_label': _rango_label(rango, dias),
    }


def _where_rango(filtros: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    rango = filtros['rango']
    if rango == 'VENCIDOS':
        return 'AND d.fecha_vencimiento < %s', (filtros['fecha_corte'],)
    if rango == 'HOY':
        return 'AND d.fecha_vencimiento = %s', (filtros['fecha_corte'],)
    if rango == 'PROXIMOS':
        return 'AND d.fecha_vencimiento > %s AND d.fecha_vencimiento <= %s', (
            filtros['fecha_corte'],
            filtros['fecha_hasta'],
        )
    return '', ()


def _prioridad(dias_plazo: int) -> str:
    if dias_plazo < -30:
        return 'CRITICA'
    if dias_plazo < 0:
        return 'ALTA'
    if dias_plazo == 0:
        return 'MEDIA'
    return 'BAJA'


def _situacion(dias_plazo: int) -> str:
    if dias_plazo < 0:
        return 'VENCIDO'
    if dias_plazo == 0:
        return 'HOY'
    if dias_plazo > 0:
        return 'POR_VENCER'
    return 'PENDIENTE'


def _accion(tipo: str, situacion_codigo: str) -> str:
    verbo = 'pago' if tipo == 'PAGAR' else 'cobro'
    if situacion_codigo == 'VENCIDO':
        return f'Priorizar seguimiento y registrar {verbo} si corresponde.'
    if situacion_codigo == 'HOY':
        return f'Gestionar hoy y registrar {verbo} al confirmar la operación.'
    return f'Programar seguimiento y registrar {verbo} cuando se concrete.'


# ============================================================
# Consulta principal
# ============================================================


def _consultar_compromisos(filtros: dict[str, Any], limit_rows: int) -> list[dict[str, Any]]:
    rango_sql, rango_params = _where_rango(filtros)
    params: list[Any] = [
        filtros['fecha_corte'],
        filtros['fecha_corte'],
        filtros['fecha_corte'],
        filtros['tipo'],
        filtros['tipo'],
        filtros['unidad_negocio_id'],
        filtros['unidad_negocio_id'],
    ]
    params.extend(rango_params)
    params.append(limit_rows)

    sql = f"""
        SELECT
            c.id AS compromiso_id,
            c.codigo AS compromiso_codigo,
            c.tipo,
            c.nombre AS compromiso_nombre,
            COALESCE(c.descripcion, '') AS compromiso_descripcion,
            c.gestion,
            c.cuenta_contable,
            COALESCE(cu.nombre, '') AS cuenta_nombre,
            c.auxiliar_id,
            COALESCE(NULLIF(a.razon_social, ''), a.nombre, 'Sin auxiliar') AS auxiliar_nombre,
            c.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, 'Sin unidad') AS unidad_nombre,
            d.id AS detalle_id,
            d.fecha_vencimiento,
            d.monto_programado,
            d.monto_registrado,
            GREATEST(d.monto_programado - COALESCE(d.monto_registrado, 0), 0) AS saldo_pendiente,
            d.estado,
            COALESCE(d.observacion, '') AS observacion,
            (d.fecha_vencimiento - %s)::int AS dias_plazo,
            CASE
                WHEN d.fecha_vencimiento < %s THEN 'VENCIDO'
                WHEN d.fecha_vencimiento = %s THEN 'HOY'
                WHEN d.fecha_vencimiento > CURRENT_DATE THEN 'POR_VENCER'
                ELSE 'PENDIENTE'
            END AS situacion_codigo
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        LEFT JOIN contabilidad.cuenta cu ON cu.codigo = c.cuenta_contable
        WHERE c.activo = TRUE
          AND (%s = '' OR c.tipo = %s)
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
          AND d.estado = 'PENDIENTE'
          AND GREATEST(d.monto_programado - COALESCE(d.monto_registrado, 0), 0) > 0
          {rango_sql}
        ORDER BY d.fecha_vencimiento ASC, c.tipo DESC, c.codigo ASC, d.id ASC
        LIMIT %s
    """
    rows = _db_rows(sql, tuple(params))

    parsed: list[dict[str, Any]] = []
    for idx, item in enumerate(rows, start=1):
        dias_plazo = int(item.get('dias_plazo') or 0)
        situacion_codigo = item.get('situacion_codigo') or _situacion(dias_plazo)
        prioridad_codigo = _prioridad(dias_plazo)
        saldo = _decimal(item.get('saldo_pendiente'))
        programado = _decimal(item.get('monto_programado'))
        registrado = _decimal(item.get('monto_registrado'))
        tipo = item.get('tipo') or ''
        unidad = item.get('unidad_nombre') or 'Sin unidad'
        if item.get('unidad_codigo'):
            unidad = f"{item.get('unidad_codigo')} · {unidad}"
        cuenta_label = _clean(item.get('cuenta_contable'))
        if item.get('cuenta_nombre'):
            cuenta_label = f"{cuenta_label} · {item.get('cuenta_nombre')}" if cuenta_label else item.get('cuenta_nombre')

        parsed.append({
            'nro': idx,
            'prioridad_codigo': prioridad_codigo,
            'prioridad': PRIORIDAD_LABEL.get(prioridad_codigo, prioridad_codigo.title()),
            'prioridad_orden': PRIORIDAD_ORDEN.get(prioridad_codigo, 9),
            'situacion_codigo': situacion_codigo,
            'situacion': SITUACION_LABEL.get(situacion_codigo, situacion_codigo.title()),
            'tipo': tipo,
            'tipo_label': TIPO_LABEL.get(tipo, tipo),
            'compromiso_id': item.get('compromiso_id'),
            'detalle_id': item.get('detalle_id'),
            'compromiso_codigo': item.get('compromiso_codigo') or '',
            'compromiso_nombre': item.get('compromiso_nombre') or '',
            'referencia': f"{item.get('compromiso_codigo') or ''} · Cuota {item.get('detalle_id')}",
            'fecha_vencimiento': item.get('fecha_vencimiento'),
            'fecha_label': _date_label(item.get('fecha_vencimiento')),
            'dias_plazo': dias_plazo,
            'dias_label': dias_label(dias_plazo),
            'unidad': unidad,
            'auxiliar': item.get('auxiliar_nombre') or 'Sin auxiliar',
            'cuenta': cuenta_label or 'Sin cuenta',
            'estado': item.get('estado') or 'PENDIENTE',
            'observacion': item.get('observacion') or '',
            'monto_programado': float(programado),
            'monto_programado_label': format_money(programado, 'BOB'),
            'monto_registrado': float(registrado),
            'monto_registrado_label': format_money(registrado, 'BOB'),
            'saldo_pendiente': float(saldo),
            'saldo_pendiente_label': format_money(saldo, 'BOB'),
            'monto': float(saldo),
            'monto_label': format_money(saldo, 'BOB'),
            'moneda_codigo': 'BOB',
            'accion': _accion(tipo, situacion_codigo),
        })
    return parsed


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = Decimal('0.00')
    pagar = Decimal('0.00')
    cobrar = Decimal('0.00')
    vencidos = 0
    hoy = 0
    proximos = 0
    max_dias_vencido = 0

    for row in rows:
        saldo = _decimal(row.get('saldo_pendiente'))
        total += saldo
        if row.get('tipo') == 'PAGAR':
            pagar += saldo
        elif row.get('tipo') == 'COBRAR':
            cobrar += saldo
        situacion = row.get('situacion_codigo')
        if situacion == 'VENCIDO':
            vencidos += 1
            max_dias_vencido = max(max_dias_vencido, abs(int(row.get('dias_plazo') or 0)))
        elif situacion == 'HOY':
            hoy += 1
        elif situacion == 'POR_VENCER':
            proximos += 1

    moneda_note = 'Expresado en Bs.' if rows else 'Sin importes monetarios'
    return {
        'cantidad': len(rows),
        'vencidos': vencidos,
        'hoy': hoy,
        'proximos': proximos,
        'total_pendiente': float(total),
        'total_pendiente_label': format_money(total, 'BOB'),
        'total_pagar': float(pagar),
        'total_pagar_label': format_money(pagar, 'BOB'),
        'total_cobrar': float(cobrar),
        'total_cobrar_label': format_money(cobrar, 'BOB'),
        'max_dias_vencido': max_dias_vencido,
        'moneda_unica': 'BOB',
        'moneda_unica_simbolo': 'Bs',
        'moneda_display_note': moneda_note,
    }


def _summary_cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'kind': 'group',
            'label': 'Pendientes',
            'value': summary.get('cantidad', 0),
            'note': 'cuotas por revisar',
        },
        {
            'kind': 'critical',
            'label': 'Vencidos',
            'value': summary.get('vencidos', 0),
            'note': f"máx. {summary.get('max_dias_vencido', 0)} día(s)",
        },
        {
            'kind': 'medium',
            'label': 'Vence hoy',
            'value': summary.get('hoy', 0),
            'note': 'atención inmediata',
        },
        {
            'kind': 'low',
            'label': 'Por vencer',
            'value': summary.get('proximos', 0),
            'note': 'dentro del horizonte',
        },
        {
            'kind': 'high',
            'label': 'Saldo pendiente',
            'value': summary.get('total_pendiente_label', '0.00'),
            'note': 'expresado en Bs',
        },
    ]


def _display_columns() -> list[dict[str, str]]:
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'tipo_label', 'label': 'Tipo', 'type': 'badge', 'code_key': 'tipo', 'align': 'center'},
        {'key': 'situacion', 'label': 'Situación', 'type': 'badge', 'code_key': 'situacion_codigo', 'align': 'center'},
        {'key': 'compromiso_nombre', 'label': 'Compromiso', 'strong': True},
        {'key': 'referencia', 'label': 'Referencia'},
        {'key': 'fecha_label', 'label': 'Vencimiento', 'align': 'center'},
        {'key': 'dias_label', 'label': 'Plazo', 'align': 'center'},
        {'key': 'unidad', 'label': 'Unidad'},
        {'key': 'auxiliar', 'label': 'Auxiliar'},
        {'key': 'saldo_pendiente', 'label': 'Saldo', 'type': 'money', 'align': 'right'},
        {'key': 'accion', 'label': 'Acción sugerida'},
    ]


def _build_payload(filtros: dict[str, Any], limit_rows: int) -> dict[str, Any]:
    rows = _consultar_compromisos(filtros, limit_rows)
    summary = _summary(rows)
    return {
        'titulo': 'Compromisos Vencidos',
        'descripcion': 'Seguimiento operativo de compromisos pendientes por pagar y por cobrar.',
        'descripcion_periodo': filtros['periodo_label'],
        'unidad_label': filtros['unidad_label'],
        'criterio_reporte': 'Incluye cuotas activas con estado PENDIENTE y saldo mayor a cero, filtradas por vencimiento, tipo y unidad de negocio.',
        'fuente_datos': 'contabilidad.compromiso y contabilidad.compromiso_detalle.',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'filtros': {
            'gestion': filtros['gestion'],
            'tipo': filtros['tipo'],
            'rango': filtros['rango'],
            'dias': filtros['dias'],
            'unidad_negocio_id': filtros.get('unidad_negocio_id') or '',
        },
        'columns': _display_columns(),
        'summary': summary,
        'summary_cards': _summary_cards(summary),
        'rows': rows,
        'empty_title': 'No hay compromisos pendientes para los filtros seleccionados',
        'empty_icon': 'fas fa-circle-check',
        'rango_label': filtros['rango_label'],
        'tipo_label': filtros['tipo_label'],
    }


class CompromisosVencidosExport:
    TITLE = 'Compromisos Vencidos'
    WORKSHEET_TITLE = 'Compromisos Vencidos'
    FILE_SLUG = 'compromisos_vencidos'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'monto_programado', 'monto_registrado', 'saldo_pendiente', 'monto'}

    @staticmethod
    def excel_columns():
        return [
            ('prioridad', 'Prioridad', 14),
            ('tipo_label', 'Tipo', 14),
            ('situacion', 'Situacion', 16),
            ('compromiso_codigo', 'Codigo', 12),
            ('compromiso_nombre', 'Compromiso', 34),
            ('detalle_id', 'Cuota ID', 12),
            ('fecha_label', 'Vencimiento', 14),
            ('dias_label', 'Plazo', 18),
            ('unidad', 'Unidad', 30),
            ('auxiliar', 'Auxiliar', 32),
            ('cuenta', 'Cuenta', 34),
            ('monto_programado', 'Programado', 16),
            ('monto_registrado', 'Registrado', 16),
            ('saldo_pendiente', 'Saldo pendiente', 18),
            ('accion', 'Accion sugerida', 42),
            ('observacion', 'Observacion', 40),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Pendientes: {summary.get('cantidad', 0)} · "
            f"Vencidos: {summary.get('vencidos', 0)} · "
            f"Vence hoy: {summary.get('hoy', 0)} · "
            f"Por vencer: {summary.get('proximos', 0)} · "
            f"Saldo pendiente: {summary.get('total_pendiente_label', '0.00')}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Prioridad', 'width': 18, 'align': 'center'},
            {'label': 'Tipo', 'width': 20, 'align': 'center'},
            {'label': 'Situación', 'width': 22, 'align': 'center'},
            {'label': 'Compromiso', 'width': 42, 'align': 'left'},
            {'label': 'Vencimiento', 'width': 20, 'align': 'center'},
            {'label': 'Plazo', 'width': 24, 'align': 'center'},
            {'label': 'Unidad', 'width': 34, 'align': 'left'},
            {'label': 'Auxiliar', 'width': 34, 'align': 'left'},
            {'label': 'Saldo', 'width': 22, 'align': 'right'},
            {'label': 'Acción sugerida', 'width': 46, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('prioridad', ''),
                item.get('tipo_label', ''),
                item.get('situacion', ''),
                item.get('compromiso_nombre', ''),
                item.get('fecha_label', ''),
                item.get('dias_label', ''),
                item.get('unidad', ''),
                item.get('auxiliar', ''),
                item.get('saldo_pendiente_label', ''),
                item.get('accion', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['', '', '', 'Límite PDF', '', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} registros. Use Excel para el detalle completo.'])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"{payload.get('descripcion_periodo', '')}. "
            f"Unidad: {payload.get('unidad_label', '')}. "
            f"Tipo: {payload.get('tipo_label', '')}. "
            f"Rango: {payload.get('rango_label', '')}. "
            f"Pendientes: {summary.get('cantidad', 0)}. "
            f"Vencidos: {summary.get('vencidos', 0)}. "
            f"Saldo pendiente: {summary.get('total_pendiente_label', '0.00')}."
        )


# ============================================================
# Rutas
# ============================================================


@compromisos_vencidos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return render_template(
        'compromisos_vencidos_index.html',
        gestiones=_obtener_gestiones(),
        gestion_preferida=_gestion_preferida(),
        tipos=TIPOS,
        rangos=RANGOS,
        horizontes=HORIZONTES,
        unidades_negocio=obtener_unidades_negocio(),
    )


@compromisos_vencidos_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_compromisos_vencidos():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el seguimiento de compromisos vencidos. {exc}', 500)


@compromisos_vencidos_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_compromisos_vencidos():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        excel_bytes = build_excel(CompromisosVencidosExport, payload)
        nombre = f"compromisos_vencidos_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el Excel de compromisos vencidos. {exc}', 500)


@compromisos_vencidos_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_compromisos_vencidos():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(CompromisosVencidosExport, payload)
        nombre = f"compromisos_vencidos_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF de compromisos vencidos. {exc}', 500)


@compromisos_vencidos_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('compromisos_vencidos_help.html')
