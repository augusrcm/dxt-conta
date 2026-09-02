# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Cartera por proveedor
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


REPORT_ID = 'cuentas_por_pagar_por_proveedor'
TITLE = 'Cartera por proveedor'
DESCRIPTION = 'Pendientes de pago agrupados por proveedor.'
WORKSHEET_TITLE = 'Cartera proveedor'
FILE_SLUG = 'cartera_por_proveedor'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-user-tie'

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
    'manana': 'Manana',
    'proximos_7': 'Proximos 7 dias',
    'proximos_30': 'Proximos 30 dias',
    'rango': 'Rango personalizado',
}

GRUPOS = {
    '': 'Todos',
    'PENDIENTE': 'Sin pagos',
    'PARCIAL': 'Parcial',
    'VENCIDO': 'Vencido',
}

HELP_TITLE = 'Cartera por proveedor'
HELP_INTRO = 'Agrupa compromisos pendientes de pago por proveedor y moneda.'
HELP_ITEMS = [
    'Incluye compromisos por pagar activos con saldo pendiente.',
    'Agrupa por proveedor y moneda para no mezclar importes.',
    'El estado se calcula por importes y fecha base, no solo por el estado guardado.',
    'Los pagos directos no aparecen como cartera porque no tienen obligacion previa pendiente.',
]

FECHA_MINIMA = date(1900, 1, 1)
FECHA_MAXIMA = date(9999, 12, 31)


def validate_filters(args):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El periodo seleccionado no es valido.')

    grupo = _clean(args.get('grupo')) or DEFAULT_GRUPO
    if grupo == 'INCUMPLIDO':
        grupo = 'VENCIDO'
    if grupo not in GRUPOS:
        raise ValueError('El estado seleccionado no es valido.')

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


def _prioridad(fecha_ref, fecha_base, vencidas, hoy_count):
    if int(vencidas or 0) > 0:
        dias = (fecha_ref - fecha_base).days if isinstance(fecha_ref, date) else None
        return 'CRITICA', 'Vencida', dias, 0
    if int(hoy_count or 0) > 0:
        dias = (fecha_ref - fecha_base).days if isinstance(fecha_ref, date) else 0
        return 'ALTA', 'Hoy', dias, 1
    if isinstance(fecha_ref, date):
        dias = (fecha_ref - fecha_base).days
        if dias <= 7:
            return 'MEDIA', _dias_label(dias), dias, 2
        return 'BAJA', _dias_label(dias), dias, 4
    return 'BAJA', 'Sin fecha', None, 5


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    fecha_desde = filtros['fecha_desde']
    fecha_hasta = filtros['fecha_hasta']
    fecha_base = filtros['fecha_base']
    unidad_id = filtros['unidad_negocio_id']
    grupo = filtros['grupo']

    estado_sql = ''
    estado_params = []
    if grupo == 'PENDIENTE':
        estado_sql = 'AND monto_aplicado = 0'
    elif grupo == 'PARCIAL':
        estado_sql = 'AND monto_aplicado > 0 AND monto_pendiente > 0'
    elif grupo == 'VENCIDO':
        estado_sql = 'AND fecha_vencimiento < %s'
        estado_params.append(fecha_base)

    sql = f"""
        WITH base AS (
            SELECT
                COALESCE(a.id, 0) AS proveedor_id,
                COALESCE(a.nombre, a.razon_social, c.nombre, 'Sin proveedor')::text AS proveedor,
                COALESCE(a.nit_ci, '')::text AS proveedor_doc,
                COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad')::text AS unidad,
                c.codigo::text AS compromiso_codigo,
                d.fecha_vencimiento::date AS fecha_vencimiento,
                COALESCE(d.monto_programado, 0)::numeric(18,2) AS monto_total,
                COALESCE(d.monto_registrado, 0)::numeric(18,2) AS monto_aplicado,
                GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)::numeric(18,2) AS monto_pendiente,
                d.estado::text AS estado_sistema,
                %s::text AS moneda_codigo
            FROM contabilidad.compromiso c
            INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
            LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE c.activo = TRUE
              AND c.tipo = 'PAGAR'
              AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
              AND d.fecha_vencimiento BETWEEN %s AND %s
              AND (%s IS NULL OR c.unidad_negocio_id = %s)
        ), filtrada AS (
            SELECT *
            FROM base
            WHERE 1 = 1
              {estado_sql}
        )
        SELECT
            proveedor_id,
            proveedor,
            proveedor_doc,
            moneda_codigo,
            COUNT(*)::integer AS registros,
            COUNT(*) FILTER (WHERE monto_aplicado = 0)::integer AS sin_pago,
            COUNT(*) FILTER (WHERE monto_aplicado > 0 AND monto_pendiente > 0)::integer AS parciales,
            COUNT(*) FILTER (WHERE fecha_vencimiento < %s)::integer AS vencidas,
            COUNT(*) FILTER (WHERE fecha_vencimiento = %s)::integer AS hoy,
            COUNT(*) FILTER (WHERE fecha_vencimiento > %s)::integer AS proximas,
            MIN(fecha_vencimiento)::date AS proximo_vencimiento,
            MAX(fecha_vencimiento)::date AS ultimo_vencimiento,
            SUM(monto_total)::numeric(18,2) AS monto_total,
            SUM(monto_aplicado)::numeric(18,2) AS monto_aplicado,
            SUM(monto_pendiente)::numeric(18,2) AS monto_pendiente,
            string_agg(DISTINCT unidad, ', ' ORDER BY unidad)::text AS unidades,
            string_agg(DISTINCT compromiso_codigo, ', ' ORDER BY compromiso_codigo)::text AS compromisos
        FROM filtrada
        GROUP BY proveedor_id, proveedor, proveedor_doc, moneda_codigo
        ORDER BY
            MIN(fecha_vencimiento) ASC,
            SUM(monto_pendiente) DESC,
            proveedor ASC
        LIMIT %s
    """
    params = [
        MONEDA_BASE,
        fecha_desde,
        fecha_hasta,
        unidad_id,
        unidad_id,
        *estado_params,
        fecha_base,
        fecha_base,
        fecha_base,
        int(limit_rows),
    ]

    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))

    mapped = []
    for idx, row in enumerate(rows, start=1):
        fecha_ref = row.get('proximo_vencimiento')
        prioridad_codigo, prioridad_label, dias, orden_prioridad = _prioridad(
            fecha_ref,
            fecha_base,
            row.get('vencidas'),
            row.get('hoy'),
        )
        total = _decimal(row.get('monto_total'))
        aplicado = _decimal(row.get('monto_aplicado'))
        pendiente = _decimal(row.get('monto_pendiente'))
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        registros = int(row.get('registros') or 0)
        sin_pago = int(row.get('sin_pago') or 0)
        parciales = int(row.get('parciales') or 0)
        vencidas = int(row.get('vencidas') or 0)
        hoy_count = int(row.get('hoy') or 0)
        proximas = int(row.get('proximas') or 0)

        if vencidas > 0:
            estado_label = 'Vencido'
            estado_codigo = 'VENCIDO'
        elif parciales > 0:
            estado_label = 'Parcial'
            estado_codigo = 'PARCIAL'
        else:
            estado_label = 'Sin pagos'
            estado_codigo = 'PENDIENTE'

        mapped.append({
            'nro': idx,
            'prioridad_codigo': prioridad_codigo,
            'prioridad_orden': orden_prioridad,
            'prioridad': prioridad_label,
            'proveedor': row.get('proveedor') or 'Sin proveedor',
            'proveedor_doc': row.get('proveedor_doc') or '',
            'moneda_codigo': moneda,
            'estado_codigo': estado_codigo,
            'estado': estado_label,
            'registros': registros,
            'sin_pago': sin_pago,
            'parciales': parciales,
            'vencidas': vencidas,
            'hoy': hoy_count,
            'proximas': proximas,
            'proximo_vencimiento': fecha_ref.isoformat() if isinstance(fecha_ref, date) else str(fecha_ref or ''),
            'proximo_vencimiento_label': _date_label(fecha_ref),
            'ultimo_vencimiento_label': _date_label(row.get('ultimo_vencimiento')),
            'dias': dias,
            'dias_label': _dias_label(dias),
            'unidades': row.get('unidades') or '',
            'compromisos': row.get('compromisos') or '',
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
        {'key': 'proveedor', 'label': 'Proveedor', 'sub_key': 'proveedor_doc', 'align': 'left', 'strong': True},
        {'key': 'proximo_vencimiento_label', 'label': 'Prox. vencimiento', 'sub_key': 'dias_label', 'align': 'center'},
        {'key': 'estado', 'label': 'Estado', 'align': 'center'},
        {'key': 'moneda_codigo', 'label': 'Moneda', 'align': 'center'},
        {'key': 'registros', 'label': 'Registros', 'align': 'center'},
        {'key': 'vencidas', 'label': 'Vencidas', 'align': 'center'},
        {'key': 'parciales', 'label': 'Parciales', 'align': 'center'},
        {'key': 'unidades', 'label': 'Unidades', 'align': 'left'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
        {'key': 'monto_aplicado', 'label': 'Pagado', 'type': 'money', 'align': 'right'},
        {'key': 'monto_pendiente', 'label': 'Pendiente', 'type': 'money', 'align': 'right'},
    ]


def _build_summary(rows):
    totales = defaultdict(lambda: {'total': Decimal('0.00'), 'aplicado': Decimal('0.00'), 'pendiente': Decimal('0.00')})
    proveedores_criticos = 0
    proveedores_hoy = 0
    proveedores_proximos = 0
    registros = 0
    registros_vencidos = 0
    registros_parciales = 0
    proveedores_set = set()

    for row in rows:
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        totales[moneda]['total'] += _decimal(row.get('monto_total'))
        totales[moneda]['aplicado'] += _decimal(row.get('monto_aplicado'))
        totales[moneda]['pendiente'] += _decimal(row.get('monto_pendiente'))
        registros += int(row.get('registros') or 0)
        registros_vencidos += int(row.get('vencidas') or 0)
        registros_parciales += int(row.get('parciales') or 0)
        proveedores_set.add((row.get('proveedor') or '', row.get('proveedor_doc') or ''))

        prioridad = row.get('prioridad_codigo')
        if prioridad == 'CRITICA':
            proveedores_criticos += 1
        elif prioridad == 'ALTA':
            proveedores_hoy += 1
        else:
            proveedores_proximos += 1

    totales_por_moneda = []
    for moneda, total in sorted(totales.items()):
        totales_por_moneda.append({
            'moneda_codigo': moneda,
            'total': float(total['total']),
            'total_label': _format_money(total['total'], moneda),
            'total_aplicado': float(total['aplicado']),
            'total_aplicado_label': _format_money(total['aplicado'], moneda),
            'total_pendiente': float(total['pendiente']),
            'total_pendiente_label': _format_money(total['pendiente'], moneda),
        })

    moneda_unica = totales_por_moneda[0]['moneda_codigo'] if len(totales_por_moneda) == 1 else None
    total_label = totales_por_moneda[0]['total_pendiente_label'] if len(totales_por_moneda) == 1 else 'Por moneda'

    return {
        'cantidad': len(rows),
        'proveedores': len(proveedores_set),
        'registros': registros,
        'registros_vencidos': registros_vencidos,
        'registros_parciales': registros_parciales,
        'proveedores_criticos': proveedores_criticos,
        'proveedores_hoy': proveedores_hoy,
        'proveedores_proximos': proveedores_proximos,
        'moneda_unica': moneda_unica,
        'total_pendiente': float(totales_por_moneda[0]['total_pendiente']) if len(totales_por_moneda) == 1 else None,
        'total_pendiente_label': total_label,
        'totales_por_moneda': totales_por_moneda,
        'monedas': len(totales_por_moneda),
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Total pendiente', 'value': summary.get('total_pendiente_label'), 'note': 'Saldo por pagar', 'kind': 'total'},
        {'label': 'Proveedores', 'value': summary.get('proveedores', 0), 'note': 'Con saldo pendiente', 'kind': 'group'},
        {'label': 'Criticos', 'value': summary.get('proveedores_criticos', 0), 'note': 'Con vencidas', 'kind': 'critical'},
        {'label': 'Hoy', 'value': summary.get('proveedores_hoy', 0), 'note': 'Vencen en fecha base', 'kind': 'high'},
        {'label': 'Registros', 'value': summary.get('registros', 0), 'note': 'Obligaciones', 'kind': 'group'},
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
        'empty_title': 'No hay proveedores con cartera por pagar para los filtros seleccionados',
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
        ('proveedor', 'Proveedor', 36),
        ('proveedor_doc', 'NIT/CI', 16),
        ('proximo_vencimiento_label', 'Prox. vencimiento', 16),
        ('ultimo_vencimiento_label', 'Ultimo vencimiento', 16),
        ('dias_label', 'Situacion', 18),
        ('estado', 'Estado', 14),
        ('moneda_codigo', 'Moneda', 10),
        ('registros', 'Registros', 12),
        ('sin_pago', 'Sin pagos', 12),
        ('parciales', 'Parciales', 12),
        ('vencidas', 'Vencidas', 12),
        ('hoy', 'Hoy', 10),
        ('proximas', 'Proximas', 12),
        ('unidades', 'Unidades', 36),
        ('compromisos', 'Compromisos', 42),
        ('monto_total', 'Total', 16),
        ('monto_aplicado', 'Pagado', 16),
        ('monto_pendiente', 'Pendiente', 16),
    ]


def excel_summary_text(summary):
    totales = summary.get('totales_por_moneda') or []
    if totales:
        total_txt = ' · '.join(item.get('total_pendiente_label') or '' for item in totales)
    else:
        total_txt = summary.get('total_pendiente_label', '')
    return (
        f"Total pendiente: {total_txt} · "
        f"Proveedores: {summary.get('proveedores', 0)} · "
        f"Criticos: {summary.get('proveedores_criticos', 0)} · "
        f"Registros: {summary.get('registros', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 20, 'align': 'center'},
        {'label': 'Proveedor', 'width': 52, 'align': 'left'},
        {'label': 'Prox. venc.', 'width': 22, 'align': 'center'},
        {'label': 'Estado', 'width': 18, 'align': 'center'},
        {'label': 'Moneda', 'width': 16, 'align': 'center'},
        {'label': 'Reg.', 'width': 13, 'align': 'center'},
        {'label': 'Venc.', 'width': 14, 'align': 'center'},
        {'label': 'Parc.', 'width': 14, 'align': 'center'},
        {'label': 'Unidades', 'width': 48, 'align': 'left'},
        {'label': 'Total', 'width': 25, 'align': 'right'},
        {'label': 'Pagado', 'width': 25, 'align': 'right'},
        {'label': 'Pendiente', 'width': 27, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['prioridad'],
            item['proveedor'],
            item['proximo_vencimiento_label'],
            item['estado'],
            item['moneda_codigo'],
            item['registros'],
            item['vencidas'],
            item['parciales'],
            item['unidades'],
            item['monto_total_label'],
            item['monto_aplicado_label'],
            item['monto_pendiente_label'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} proveedores. Use Excel para el detalle completo.', '', '', '', '', '', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    totales = summary.get('totales_por_moneda') or []
    total_txt = ' · '.join(item.get('total_pendiente_label') or '' for item in totales) if totales else summary.get('total_pendiente_label', '')
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Total pendiente: {total_txt}. "
        f"Proveedores: {summary.get('proveedores', 0)}. "
        f"Criticos: {summary.get('proveedores_criticos', 0)}. "
        f"Registros: {summary.get('registros', 0)}."
    )
