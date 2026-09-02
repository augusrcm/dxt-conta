# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Cartera por pagar
# ============================================================

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from database.db_manager import DatabaseManager
from modules.reportes_rapidos.core.catalogos import unidad_label as _unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_PDF, MAX_ROWS_SCREEN, MONEDA_BASE
from modules.reportes_rapidos.core.formatos import dias_label as _dias_label
from modules.reportes_rapidos.core.formatos import format_money as _format_money
from modules.reportes_rapidos.core.monedas import aplicar_contexto_monetario
from modules.reportes_rapidos.core.utils import clean as _clean
from modules.reportes_rapidos.core.utils import date_label as _date_label
from modules.reportes_rapidos.core.utils import decimal_value as _decimal
from modules.reportes_rapidos.core.utils import parse_date as _parse_date
from modules.reportes_rapidos.core.utils import parse_optional_int as _parse_optional_int


REPORT_ID = 'cuentas_por_pagar_pendientes'
TITLE = 'Cartera por pagar'
DESCRIPTION = 'Pendientes de pago consolidados.'
WORKSHEET_TITLE = 'Cartera por pagar'
FILE_SLUG = 'cartera_por_pagar'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-money-bill-transfer'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha base'
FILTER_GROUP_LABEL = 'Estado'
DEFAULT_ALCANCE = 'todas'
DEFAULT_GRUPO = ''
MONEY_FIELDS = {'monto_total', 'monto_aplicado', 'monto_pendiente'}

ALCANCES = {
    'todas': 'Toda la cartera',
    'vencidas': 'Vencidas',
    'hoy': 'Hoy',
    'manana': 'Mañana',
    'proximos_7': 'Próximos 7 días',
    'proximos_30': 'Próximos 30 días',
    'rango': 'Rango personalizado',
}

GRUPOS = {
    '': 'Todos',
    'PENDIENTE': 'Sin pagos',
    'PARCIAL': 'Parcial',
    'VENCIDO': 'Vencido',
}

HELP_TITLE = 'Cartera por pagar'
HELP_INTRO = 'Muestra los compromisos pendientes de pago con saldo real pendiente.'
HELP_ITEMS = [
    'Incluye compromisos por pagar activos con saldo pendiente.',
    'El estado de pago se calcula por importe pagado: sin pagos o parcial.',
    'Los vencidos se determinan por la fecha de vencimiento y la fecha base.',
    'Los pagos directos no aparecen como pendientes porque no tienen obligación previa.',
]

FECHA_MINIMA = date(1900, 1, 1)
FECHA_MAXIMA = date(9999, 12, 31)


def validate_filters(args):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El periodo seleccionado no es válido.')

    grupo = _clean(args.get('grupo')) or DEFAULT_GRUPO
    if grupo == 'INCUMPLIDO':
        grupo = 'VENCIDO'
    if grupo not in GRUPOS:
        raise ValueError('El estado seleccionado no es válido.')

    fecha_base = _parse_date(args.get('fecha_base'), FILTER_DATE_LABEL, default=hoy)
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if alcance == 'todas':
        fecha_desde = FECHA_MINIMA
        fecha_hasta = FECHA_MAXIMA
    elif alcance == 'vencidas':
        fecha_desde = FECHA_MINIMA
        fecha_hasta = fecha_base - timedelta(days=1)
    elif alcance == 'hoy':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
    elif alcance == 'manana':
        fecha_desde = fecha_base + timedelta(days=1)
        fecha_hasta = fecha_desde
    elif alcance == 'proximos_7':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=7)
    elif alcance == 'proximos_30':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=30)
    else:
        fecha_desde = _parse_date(args.get('fecha_desde'), 'Fecha desde')
        fecha_hasta = _parse_date(args.get('fecha_hasta'), 'Fecha hasta')
        if fecha_desde > fecha_hasta:
            raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')

    return {
        'alcance': alcance,
        'alcance_label': ALCANCES[alcance],
        'grupo': grupo,
        'grupo_label': GRUPOS[grupo],
        'fecha_base': fecha_base,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
    }


def _descripcion_periodo(filtros):
    if filtros['alcance'] == 'todas':
        return 'Toda la cartera pendiente'
    if filtros['alcance'] == 'vencidas':
        return f"Vencidas hasta el {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    if filtros['alcance'] == 'rango':
        return f"Del {filtros['fecha_desde'].strftime('%d/%m/%Y')} al {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    if filtros['fecha_desde'] == filtros['fecha_hasta']:
        return f"{filtros['alcance_label']} · {filtros['fecha_desde'].strftime('%d/%m/%Y')}"
    return (
        f"{filtros['alcance_label']} · "
        f"{filtros['fecha_desde'].strftime('%d/%m/%Y')} al {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    )


def _prioridad(fecha_ref, fecha_base):
    if not isinstance(fecha_ref, date):
        return 'BAJA', 'Sin fecha', None, 3
    dias = (fecha_ref - fecha_base).days
    if dias < 0:
        return 'CRITICA', 'Vencida', dias, 0
    if dias == 0:
        return 'ALTA', 'Hoy', dias, 1
    if dias <= 7:
        return 'MEDIA', _dias_label(dias), dias, 2
    return 'BAJA', _dias_label(dias), dias, 4


def _estado_pago(programado: Decimal, aplicado: Decimal, fecha_ref, fecha_base):
    pendiente = max(programado - aplicado, Decimal('0.00'))
    if pendiente <= Decimal('0.00'):
        return 'PAGADO', 'Pagado'
    if aplicado > Decimal('0.00'):
        return 'PARCIAL', 'Parcial'
    if isinstance(fecha_ref, date) and fecha_ref < fecha_base:
        return 'VENCIDO', 'Vencido'
    return 'PENDIENTE', 'Sin pagos'


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    fecha_desde = filtros['fecha_desde']
    fecha_hasta = filtros['fecha_hasta']
    fecha_base = filtros['fecha_base']
    unidad_id = filtros['unidad_negocio_id']
    grupo = filtros['grupo']

    estado_sql = ''
    estado_params = []
    if grupo == 'PENDIENTE':
        estado_sql = 'AND COALESCE(d.monto_registrado, 0) = 0'
    elif grupo == 'PARCIAL':
        estado_sql = 'AND COALESCE(d.monto_registrado, 0) > 0 AND COALESCE(d.monto_registrado, 0) < COALESCE(d.monto_programado, 0)'
    elif grupo == 'VENCIDO':
        estado_sql = 'AND d.fecha_vencimiento < %s'
        estado_params.append(fecha_base)

    sql = f"""
        SELECT
            d.id AS detalle_id,
            c.codigo::text AS compromiso_codigo,
            c.nombre::text AS compromiso_nombre,
            COALESCE(NULLIF(c.descripcion, ''), c.nombre, 'Cuenta por pagar')::text AS detalle,
            c.cuenta_contable::text AS cuenta_contable,
            COALESCE(cta.nombre, '')::text AS cuenta_nombre,
            d.fecha_vencimiento::date AS fecha_vencimiento,
            COALESCE(d.monto_programado, 0)::numeric(18,2) AS monto_total,
            COALESCE(d.monto_registrado, 0)::numeric(18,2) AS monto_aplicado,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)::numeric(18,2) AS monto_pendiente,
            d.estado::text AS estado_sistema,
            COALESCE(d.observacion, '')::text AS observacion,
            COALESCE(a.nombre, a.razon_social, c.nombre, 'Sin proveedor')::text AS proveedor,
            COALESCE(a.nit_ci, '')::text AS proveedor_doc,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad')::text AS unidad,
            %s::text AS moneda_codigo
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = c.cuenta_contable
        WHERE c.activo = TRUE
          AND c.tipo = 'PAGAR'
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
          AND d.fecha_vencimiento BETWEEN %s AND %s
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
          {estado_sql}
        ORDER BY
            d.fecha_vencimiento ASC,
            proveedor ASC,
            c.codigo ASC,
            d.id ASC
        LIMIT %s
    """
    params = [MONEDA_BASE, fecha_desde, fecha_hasta, unidad_id, unidad_id, *estado_params, int(limit_rows)]

    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))

    mapped = []
    for idx, row in enumerate(rows, start=1):
        fecha_ref = row.get('fecha_vencimiento')
        prioridad_codigo, prioridad_label, dias, orden_prioridad = _prioridad(fecha_ref, fecha_base)
        total = _decimal(row.get('monto_total'))
        aplicado = _decimal(row.get('monto_aplicado'))
        pendiente = _decimal(row.get('monto_pendiente'))
        estado_codigo, estado_label = _estado_pago(total, aplicado, fecha_ref, fecha_base)
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        cuenta = row.get('cuenta_contable') or ''
        cuenta_nombre = row.get('cuenta_nombre') or ''
        cuenta_label = f"{cuenta} · {cuenta_nombre}" if cuenta and cuenta_nombre else cuenta
        proveedor = row.get('proveedor') or 'Sin proveedor'
        proveedor_doc = row.get('proveedor_doc') or ''
        observacion = row.get('observacion') or ''

        mapped.append({
            'nro': idx,
            'prioridad_codigo': prioridad_codigo,
            'prioridad_orden': orden_prioridad,
            'prioridad': prioridad_label,
            'fecha': fecha_ref.isoformat() if isinstance(fecha_ref, date) else str(fecha_ref or ''),
            'fecha_label': _date_label(fecha_ref),
            'dias': dias,
            'dias_label': _dias_label(dias),
            'compromiso': row.get('compromiso_codigo') or '',
            'proveedor': proveedor,
            'proveedor_doc': proveedor_doc,
            'detalle': row.get('detalle') or '',
            'unidad': row.get('unidad') or '',
            'cuenta': cuenta_label,
            'estado_codigo': estado_codigo,
            'estado': estado_label,
            'estado_sistema': row.get('estado_sistema') or '',
            'observacion': observacion,
            'moneda_codigo': moneda,
            'monto_total': float(total),
            'monto_total_label': _format_money(total, moneda),
            'monto_aplicado': float(aplicado),
            'monto_aplicado_label': _format_money(aplicado, moneda),
            'monto_pendiente': float(pendiente),
            'monto_pendiente_label': _format_money(pendiente, moneda),
        })
    return mapped


def display_columns():
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'fecha_label', 'label': 'Vencimiento', 'sub_key': 'dias_label', 'align': 'center'},
        {'key': 'compromiso', 'label': 'Compromiso', 'align': 'left', 'strong': True},
        {'key': 'proveedor', 'label': 'Proveedor', 'sub_key': 'proveedor_doc', 'align': 'left'},
        {'key': 'detalle', 'label': 'Detalle', 'sub_key': 'unidad', 'align': 'left'},
        {'key': 'estado', 'label': 'Estado', 'align': 'center'},
        {'key': 'moneda_codigo', 'label': 'Moneda', 'align': 'center'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
        {'key': 'monto_aplicado', 'label': 'Pagado', 'type': 'money', 'align': 'right'},
        {'key': 'monto_pendiente', 'label': 'Pendiente', 'type': 'money', 'align': 'right'},
    ]


def _build_summary(rows):
    totales = defaultdict(lambda: Decimal('0.00'))
    vencidas = 0
    hoy = 0
    proximas = 0
    sin_pago = 0
    parcial = 0

    for row in rows:
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        pendiente = _decimal(row.get('monto_pendiente'))
        totales[moneda] += pendiente

        prioridad = row.get('prioridad_codigo')
        estado = row.get('estado_codigo')
        if prioridad == 'CRITICA':
            vencidas += 1
        elif prioridad == 'ALTA':
            hoy += 1
        else:
            proximas += 1

        if estado == 'PARCIAL':
            parcial += 1
        else:
            sin_pago += 1

    totales_por_moneda = [
        {
            'moneda_codigo': moneda,
            'total': float(total),
            'total_pendiente': float(total),
            'total_pendiente_label': _format_money(total, moneda),
        }
        for moneda, total in sorted(totales.items())
    ]
    moneda_unica = totales_por_moneda[0]['moneda_codigo'] if len(totales_por_moneda) == 1 else None
    total_label = totales_por_moneda[0]['total_pendiente_label'] if len(totales_por_moneda) == 1 else 'Por moneda'

    return {
        'cantidad': len(rows),
        'vencidas': vencidas,
        'hoy': hoy,
        'proximas': proximas,
        'sin_pago': sin_pago,
        'parcial': parcial,
        'moneda_unica': moneda_unica,
        'total_pendiente': float(totales_por_moneda[0]['total']) if len(totales_por_moneda) == 1 else None,
        'total_pendiente_label': total_label,
        'totales_por_moneda': totales_por_moneda,
        'monedas': len(totales_por_moneda),
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Total pendiente', 'value': summary.get('total_pendiente_label'), 'note': 'Saldo por pagar', 'kind': 'total'},
        {'label': 'Vencidas', 'value': summary.get('vencidas', 0), 'note': 'Prioridad crítica', 'kind': 'critical'},
        {'label': 'Hoy', 'value': summary.get('hoy', 0), 'note': 'Vencen en fecha base', 'kind': 'high'},
        {'label': 'Parciales', 'value': summary.get('parcial', 0), 'note': 'Con pago parcial', 'kind': 'group'},
        {'label': 'Registros', 'value': summary.get('cantidad', 0), 'note': 'Pendientes por pagar', 'kind': 'group'},
    ]


def build_payload(filtros, limit_rows=MAX_ROWS_SCREEN):
    rows = _fetch_rows(filtros, limit_rows=limit_rows)
    summary = _build_summary(rows)
    payload = {
        'reporte': REPORT_ID,
        'titulo': TITLE,
        'descripcion': DESCRIPTION,
        'descripcion_periodo': _descripcion_periodo(filtros),
        'unidad_label': _unidad_label(filtros['unidad_negocio_id']),
        'columns': display_columns(),
        'summary_cards': _summary_cards(summary),
        'empty_title': 'No hay pendientes por pagar para los filtros seleccionados',
        'empty_icon': 'fas fa-circle-check',
        'filtros': {
            'alcance': filtros['alcance'],
            'alcance_label': filtros['alcance_label'],
            'grupo': filtros['grupo'],
            'grupo_label': filtros['grupo_label'],
            'fecha_base': filtros['fecha_base'].isoformat(),
            'fecha_desde': filtros['fecha_desde'].isoformat(),
            'fecha_hasta': filtros['fecha_hasta'].isoformat(),
            'unidad_negocio_id': filtros['unidad_negocio_id'] or '',
        },
        'rows': rows,
        'summary': summary,
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
    return aplicar_contexto_monetario(payload)


def excel_columns():
    return [
        ('prioridad', 'Prioridad', 14),
        ('fecha_label', 'Vencimiento', 13),
        ('dias_label', 'Situación', 18),
        ('compromiso', 'Compromiso', 18),
        ('proveedor', 'Proveedor', 34),
        ('proveedor_doc', 'NIT/CI', 16),
        ('detalle', 'Detalle', 45),
        ('unidad', 'Unidad', 28),
        ('cuenta', 'Cuenta contable', 34),
        ('estado', 'Estado', 14),
        ('estado_sistema', 'Estado sistema', 16),
        ('moneda_codigo', 'Moneda', 10),
        ('monto_total', 'Total', 16),
        ('monto_aplicado', 'Pagado', 16),
        ('monto_pendiente', 'Pendiente', 16),
        ('observacion', 'Observación', 34),
    ]


def excel_summary_text(summary):
    totales = summary.get('totales_por_moneda') or []
    if totales:
        total_txt = ' · '.join(item.get('total_pendiente_label') or '' for item in totales)
    else:
        total_txt = summary.get('total_pendiente_label', '')
    return (
        f"Total pendiente: {total_txt} · "
        f"Vencidas: {summary.get('vencidas', 0)} · "
        f"Hoy: {summary.get('hoy', 0)} · "
        f"Parciales: {summary.get('parcial', 0)} · "
        f"Registros: {summary.get('cantidad', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 20, 'align': 'center'},
        {'label': 'Vencimiento', 'width': 22, 'align': 'center'},
        {'label': 'Compromiso', 'width': 24, 'align': 'left'},
        {'label': 'Proveedor', 'width': 48, 'align': 'left'},
        {'label': 'Detalle', 'width': 52, 'align': 'left'},
        {'label': 'Estado', 'width': 20, 'align': 'center'},
        {'label': 'Moneda', 'width': 18, 'align': 'center'},
        {'label': 'Total', 'width': 24, 'align': 'right'},
        {'label': 'Pagado', 'width': 24, 'align': 'right'},
        {'label': 'Pendiente', 'width': 26, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['prioridad'],
            item['fecha_label'],
            item['compromiso'],
            item['proveedor'],
            item['detalle'],
            item['estado'],
            item['moneda_codigo'],
            item['monto_total_label'],
            item['monto_aplicado_label'],
            item['monto_pendiente_label'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', '', '', '', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} registros. Use Excel para el detalle completo.', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    totales = summary.get('totales_por_moneda') or []
    total_txt = ' · '.join(item.get('total_pendiente_label') or '' for item in totales) if totales else summary.get('total_pendiente_label', '')
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Total pendiente: {total_txt}. "
        f"Vencidas: {summary.get('vencidas', 0)}. "
        f"Hoy: {summary.get('hoy', 0)}. "
        f"Registros: {summary.get('cantidad', 0)}."
    )
