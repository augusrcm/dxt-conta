# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Pagos por proveedor
# ============================================================

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from database.db_manager import DatabaseManager
from modules.reportes_rapidos.core.catalogos import unidad_label as _unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.formatos import format_money as _format_money
from modules.reportes_rapidos.core.monedas import aplicar_contexto_monetario
from modules.reportes_rapidos.core.utils import clean as _clean
from modules.reportes_rapidos.core.utils import date_label as _date_label
from modules.reportes_rapidos.core.utils import decimal_value as _decimal
from modules.reportes_rapidos.core.utils import parse_date as _parse_date
from modules.reportes_rapidos.core.utils import parse_optional_int as _parse_optional_int


REPORT_ID = 'pagos_por_proveedor'
TITLE = 'Pagos por proveedor'
DESCRIPTION = 'Pagos agrupados por proveedor, moneda, estado, origen, medio y unidad.'
WORKSHEET_TITLE = 'Pagos por proveedor'
FILE_SLUG = 'pagos_por_proveedor'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-hand-holding-dollar'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha de pago'
FILTER_GROUP_LABEL = 'Estado'
DEFAULT_ALCANCE = 'gestion'
DEFAULT_GRUPO = 'CONFIRMADO'
MONEY_FIELDS = {'monto_total'}

HELP_TITLE = 'Pagos por proveedor'
HELP_INTRO = 'Agrupa pagos por proveedor y moneda con origen operativo y control contable.'
HELP_ITEMS = [
    'Por defecto muestra pagos confirmados de la gestion abierta.',
    'El total operativo considera solo pagos confirmados.',
    'Use Estado para revisar borradores, anulados o todos.',
    'Si existen varias monedas, los totales se muestran separados por moneda.',
]

ALCANCES = {
    'gestion': 'Gestion abierta',
    'hoy': 'Hoy',
    'ayer': 'Ayer',
    'ultimos_7': 'Ultimos 7 dias',
    'este_mes': 'Este mes',
    'rango': 'Rango personalizado',
}

GRUPOS = {
    '': 'Todos',
    'CONFIRMADO': 'Confirmados',
    'BORRADOR': 'Borrador',
    'ANULADO': 'Anulados',
}

ORIGEN_LABELS = {
    'DIRECTO': 'Directo',
    'COMPROMISO': 'Compromiso',
    'MIXTO': 'Mixto',
}


def _to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rango_gestion_abierta(fecha_base):
    sql = """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql)

    if rows:
        gestion = int(rows[0].get('gestion'))
        return date(gestion, 1, 1), date(gestion, 12, 31), f'Gestion abierta {gestion}'

    gestion = fecha_base.year
    return date(gestion, 1, 1), date(gestion, 12, 31), f'Gestion {gestion}'


def validate_filters(args):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El periodo seleccionado no es valido.')

    grupo = _clean(args.get('grupo')) or DEFAULT_GRUPO
    if grupo not in GRUPOS:
        raise ValueError('El estado seleccionado no es valido.')

    fecha_base = _parse_date(args.get('fecha_base'), FILTER_DATE_LABEL, default=hoy)
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if alcance == 'gestion':
        fecha_desde, fecha_hasta, alcance_label = _rango_gestion_abierta(fecha_base)
    elif alcance == 'hoy':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
        alcance_label = ALCANCES[alcance]
    elif alcance == 'ayer':
        fecha_desde = fecha_base - timedelta(days=1)
        fecha_hasta = fecha_desde
        alcance_label = ALCANCES[alcance]
    elif alcance == 'ultimos_7':
        fecha_desde = fecha_base - timedelta(days=6)
        fecha_hasta = fecha_base
        alcance_label = ALCANCES[alcance]
    elif alcance == 'este_mes':
        fecha_desde = fecha_base.replace(day=1)
        fecha_hasta = fecha_base
        alcance_label = ALCANCES[alcance]
    else:
        fecha_desde = _parse_date(args.get('fecha_desde'), 'Fecha desde')
        fecha_hasta = _parse_date(args.get('fecha_hasta'), 'Fecha hasta')
        if fecha_desde > fecha_hasta:
            raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')
        alcance_label = ALCANCES[alcance]

    return {
        'alcance': alcance,
        'alcance_label': alcance_label,
        'grupo': grupo,
        'grupo_label': GRUPOS[grupo],
        'fecha_base': fecha_base,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
    }


def _descripcion_periodo(filtros):
    if filtros['alcance'] == 'rango':
        return f"Del {filtros['fecha_desde'].strftime('%d/%m/%Y')} al {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    if filtros['fecha_desde'] == filtros['fecha_hasta']:
        return f"{filtros['alcance_label']} · {filtros['fecha_desde'].strftime('%d/%m/%Y')}"
    return (
        f"{filtros['alcance_label']} · "
        f"{filtros['fecha_desde'].strftime('%d/%m/%Y')} al {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    )


def _origenes_label(directos, compromisos, mixtos):
    partes = []
    if directos:
        partes.append(f"Directos: {directos}")
    if compromisos:
        partes.append(f"Compromisos: {compromisos}")
    if mixtos:
        partes.append(f"Mixtos: {mixtos}")
    return ' · '.join(partes) if partes else 'Sin origen'


def _estado_label(estado_codigo):
    if estado_codigo == 'CONFIRMADO':
        return 'Confirmado'
    if estado_codigo == 'BORRADOR':
        return 'Borrador'
    if estado_codigo == 'ANULADO':
        return 'Anulado'
    return estado_codigo or 'Todos'


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    fecha_desde = filtros['fecha_desde']
    fecha_hasta = filtros['fecha_hasta']
    unidad_id = filtros['unidad_negocio_id']
    estado = filtros['grupo']

    sql = """
        WITH detalle AS (
            SELECT
                pd.pago_id,
                COUNT(*) AS linea_count,
                COUNT(*) FILTER (WHERE pd.tipo_linea::text = 'COMPROMISO') AS compromiso_count,
                COUNT(*) FILTER (WHERE pd.tipo_linea::text = 'DIRECTO') AS directo_count,
                COALESCE(SUM(pd.subtotal) FILTER (WHERE pd.tipo_linea::text = 'COMPROMISO'), 0)::numeric(18,2) AS compromiso_monto,
                COALESCE(SUM(pd.subtotal) FILTER (WHERE pd.tipo_linea::text = 'DIRECTO'), 0)::numeric(18,2) AS directo_monto
            FROM contabilidad.pago_detalle pd
            GROUP BY pd.pago_id
        ),
        base AS (
            SELECT
                p.id AS pago_id,
                p.fecha::date AS fecha,
                p.estado::text AS estado,
                p.medio_pago::text AS medio_pago,
                p.origen_operacion::text AS origen_operacion,
                p.moneda_codigo::text AS moneda_codigo,
                COALESCE(p.tipo_cambio, 1)::numeric(18,6) AS tipo_cambio,
                COALESCE(p.monto_total, 0)::numeric(18,2) AS monto_total,
                COALESCE(a.id, 0) AS proveedor_id,
                COALESCE(a.nombre, a.razon_social, p.cliente_nombre_ref, 'Sin proveedor')::text AS proveedor,
                COALESCE(a.nit_ci, '')::text AS proveedor_doc,
                COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(da.asiento_id, p.asiento_id) AS asiento_id,
                COALESCE(det.linea_count, 0)::integer AS linea_count,
                COALESCE(det.compromiso_count, 0)::integer AS compromiso_count,
                COALESCE(det.directo_count, 0)::integer AS directo_count,
                COALESCE(det.compromiso_monto, 0)::numeric(18,2) AS compromiso_monto,
                COALESCE(det.directo_monto, 0)::numeric(18,2) AS directo_monto,
                CASE
                    WHEN COALESCE(det.compromiso_count, 0) > 0 AND COALESCE(det.directo_count, 0) > 0 THEN 'MIXTO'
                    WHEN COALESCE(det.compromiso_count, 0) > 0 OR p.origen_operacion::text = 'COMPROMISO' THEN 'COMPROMISO'
                    ELSE 'DIRECTO'
                END::text AS origen_operativo
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.auxiliar a ON a.id = p.proveedor_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            LEFT JOIN contabilidad.documento_asiento da
                   ON da.tabla_origen = 'pago'
                  AND da.origen_id = p.id
            LEFT JOIN detalle det ON det.pago_id = p.id
            WHERE p.fecha BETWEEN %s AND %s
              AND (%s = '' OR p.estado::text = %s)
              AND (%s IS NULL OR p.unidad_negocio_id = %s)
        )
        SELECT
            proveedor_id,
            proveedor,
            proveedor_doc,
            estado,
            moneda_codigo,
            COUNT(*)::integer AS registros,
            COUNT(*) FILTER (WHERE origen_operativo = 'DIRECTO')::integer AS pagos_directos,
            COUNT(*) FILTER (WHERE origen_operativo = 'COMPROMISO')::integer AS pagos_compromiso,
            COUNT(*) FILTER (WHERE origen_operativo = 'MIXTO')::integer AS pagos_mixtos,
            COUNT(*) FILTER (WHERE estado = 'CONFIRMADO' AND asiento_id IS NULL)::integer AS sin_asiento,
            MIN(fecha)::date AS primera_fecha,
            MAX(fecha)::date AS ultima_fecha,
            COALESCE(SUM(monto_total), 0)::numeric(18,2) AS monto_total,
            COALESCE(SUM(compromiso_monto), 0)::numeric(18,2) AS compromiso_monto,
            COALESCE(SUM(directo_monto), 0)::numeric(18,2) AS directo_monto,
            AVG(COALESCE(NULLIF(tipo_cambio, 0), 1))::numeric(18,6) AS tipo_cambio_promedio,
            string_agg(DISTINCT COALESCE(medio_pago, ''), ', ' ORDER BY COALESCE(medio_pago, ''))::text AS medios,
            string_agg(DISTINCT COALESCE(unidad, 'Sin unidad'), ', ' ORDER BY COALESCE(unidad, 'Sin unidad'))::text AS unidades
        FROM base
        GROUP BY proveedor_id, proveedor, proveedor_doc, estado, moneda_codigo
        ORDER BY
            SUM(CASE WHEN estado = 'CONFIRMADO' THEN monto_total ELSE 0 END) DESC,
            SUM(monto_total) DESC,
            MAX(fecha) DESC,
            proveedor ASC
        LIMIT %s
    """
    params = (fecha_desde, fecha_hasta, estado, estado, unidad_id, unidad_id, int(limit_rows))
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)

    mapped = []
    for idx, row in enumerate(rows, start=1):
        estado_codigo = row.get('estado') or ''
        moneda = row.get('moneda_codigo') or ''
        monto = _decimal(row.get('monto_total'))
        directos = _to_int(row.get('pagos_directos'))
        compromisos = _to_int(row.get('pagos_compromiso'))
        mixtos = _to_int(row.get('pagos_mixtos'))
        sin_asiento = _to_int(row.get('sin_asiento'))
        primera_fecha = row.get('primera_fecha')
        ultima_fecha = row.get('ultima_fecha')
        rango_fechas = _date_label(ultima_fecha)
        if primera_fecha and ultima_fecha and primera_fecha != ultima_fecha:
            rango_fechas = f"{_date_label(primera_fecha)} al {_date_label(ultima_fecha)}"
        control = 'OK'
        if sin_asiento:
            control = f'Sin asiento: {sin_asiento}'
        elif estado_codigo == 'ANULADO':
            control = 'Anulado'
        elif estado_codigo == 'BORRADOR':
            control = 'Borrador'

        mapped.append({
            'nro': idx,
            'proveedor_id': row.get('proveedor_id'),
            'proveedor': row.get('proveedor') or 'Sin proveedor',
            'proveedor_doc': row.get('proveedor_doc') or '',
            'estado_codigo': estado_codigo,
            'estado': _estado_label(estado_codigo),
            'moneda_codigo': moneda,
            'registros': _to_int(row.get('registros')),
            'pagos_directos': directos,
            'pagos_compromiso': compromisos,
            'pagos_mixtos': mixtos,
            'sin_asiento': sin_asiento,
            'primera_fecha_label': _date_label(primera_fecha),
            'ultima_fecha_label': _date_label(ultima_fecha),
            'rango_fechas': rango_fechas,
            'origenes': _origenes_label(directos, compromisos, mixtos),
            'medios': row.get('medios') or '',
            'unidades': row.get('unidades') or '',
            'control': control,
            'tipo_cambio_promedio': float(_decimal(row.get('tipo_cambio_promedio'))),
            'compromiso_monto': float(_decimal(row.get('compromiso_monto'))),
            'directo_monto': float(_decimal(row.get('directo_monto'))),
            'monto_total': float(monto),
            'monto_total_label': _format_money(monto, moneda),
        })
    return mapped


def display_columns():
    return [
        {'key': 'estado', 'label': 'Estado', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
        {'key': 'proveedor', 'label': 'Proveedor', 'sub_key': 'proveedor_doc', 'align': 'left', 'strong': True},
        {'key': 'rango_fechas', 'label': 'Fechas', 'align': 'center'},
        {'key': 'origenes', 'label': 'Origenes', 'sub_key': 'control', 'align': 'left'},
        {'key': 'registros', 'label': 'Pagos', 'align': 'center'},
        {'key': 'medios', 'label': 'Medios', 'align': 'left'},
        {'key': 'unidades', 'label': 'Unidades', 'align': 'left'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
    ]


def _build_summary(rows):
    totales_confirmados = {}
    proveedores = set()
    registros = 0
    confirmados = 0
    borradores = 0
    anulados = 0
    directos = 0
    compromisos = 0
    mixtos = 0
    sin_asiento = 0

    for row in rows:
        proveedores.add((row.get('proveedor') or '').strip().upper())
        registros += _to_int(row.get('registros'))
        directos += _to_int(row.get('pagos_directos'))
        compromisos += _to_int(row.get('pagos_compromiso'))
        mixtos += _to_int(row.get('pagos_mixtos'))
        estado = row.get('estado_codigo')
        if estado == 'CONFIRMADO':
            confirmados += _to_int(row.get('registros'))
            sin_asiento += _to_int(row.get('sin_asiento'))
            moneda = str(row.get('moneda_codigo') or '').upper() or 'SIN_MONEDA'
            totales_confirmados[moneda] = totales_confirmados.get(moneda, Decimal('0.00')) + _decimal(row.get('monto_total'))
        elif estado == 'ANULADO':
            anulados += _to_int(row.get('registros'))
        else:
            borradores += _to_int(row.get('registros'))

    totales_por_moneda = [
        {
            'moneda_codigo': moneda,
            'total': float(total),
            'total_label': _format_money(total, moneda),
        }
        for moneda, total in sorted(totales_confirmados.items())
    ]
    moneda_unica = totales_por_moneda[0]['moneda_codigo'] if len(totales_por_moneda) == 1 else ''
    total_unico = Decimal(str(totales_por_moneda[0]['total'])) if len(totales_por_moneda) == 1 else Decimal('0.00')

    return {
        'cantidad': len(rows),
        'proveedores': len([item for item in proveedores if item]),
        'registros': registros,
        'confirmados': confirmados,
        'borradores': borradores,
        'anulados': anulados,
        'directos': directos,
        'compromisos': compromisos,
        'mixtos': mixtos,
        'sin_asiento': sin_asiento,
        'moneda_unica': moneda_unica,
        'totales_por_moneda': totales_por_moneda,
        'total_general': float(total_unico),
        'total_general_label': _format_money(total_unico, moneda_unica) if moneda_unica else 'Por moneda',
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Total pagado', 'value': summary.get('total_general_label'), 'note': 'Confirmados', 'kind': 'total'},
        {'label': 'Proveedores', 'value': summary.get('proveedores', 0), 'note': 'Segun filtros', 'kind': 'group'},
        {'label': 'Pagos', 'value': summary.get('registros', 0), 'note': 'Agrupados', 'kind': 'group'},
        {'label': 'Confirmados', 'value': summary.get('confirmados', 0), 'note': 'Con efecto contable', 'kind': 'group'},
        {'label': 'Sin asiento', 'value': summary.get('sin_asiento', 0), 'note': 'Confirmados', 'kind': 'critical'},
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
        'empty_title': 'No hay pagos por proveedor para los filtros seleccionados',
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
        ('proveedor', 'Proveedor', 36),
        ('proveedor_doc', 'NIT/CI', 16),
        ('estado', 'Estado', 14),
        ('rango_fechas', 'Fechas', 24),
        ('origenes', 'Origenes', 34),
        ('registros', 'Pagos', 12),
        ('pagos_directos', 'Pagos directos', 16),
        ('pagos_compromiso', 'Pagos compromiso', 18),
        ('pagos_mixtos', 'Pagos mixtos', 14),
        ('medios', 'Medios', 28),
        ('unidades', 'Unidades', 36),
        ('sin_asiento', 'Sin asiento', 14),
        ('control', 'Control', 16),
        ('moneda_codigo', 'Moneda', 10),
        ('tipo_cambio_promedio', 'T/C promedio', 14),
        ('directo_monto', 'Monto directo', 16),
        ('compromiso_monto', 'Monto compromiso', 18),
        ('monto_total', 'Total pagado', 16),
    ]


def _totales_text(summary):
    totales = summary.get('totales_por_moneda') or []
    if not totales:
        return 'Total confirmado: 0.00'
    if len(totales) == 1:
        return f"Total confirmado: {totales[0].get('total_label', '0.00')}"
    partes = [
        f"{item.get('total_label', '0.00')} ({item.get('moneda_simbolo') or item.get('moneda_codigo')})"
        for item in totales
    ]
    return 'Totales confirmados por moneda: ' + '; '.join(partes)


def excel_summary_text(summary):
    return (
        f"{_totales_text(summary)} · "
        f"Proveedores: {summary.get('proveedores', 0)} · "
        f"Pagos: {summary.get('registros', 0)} · "
        f"Confirmados: {summary.get('confirmados', 0)} · "
        f"Borrador: {summary.get('borradores', 0)} · "
        f"Sin asiento: {summary.get('sin_asiento', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Estado', 'width': 24, 'align': 'center'},
        {'label': 'Proveedor', 'width': 58, 'align': 'left'},
        {'label': 'Fechas', 'width': 34, 'align': 'center'},
        {'label': 'Origenes', 'width': 44, 'align': 'left'},
        {'label': 'Pagos', 'width': 18, 'align': 'center'},
        {'label': 'Medios', 'width': 32, 'align': 'left'},
        {'label': 'Unidades', 'width': 42, 'align': 'left'},
        {'label': 'Total', 'width': 28, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['estado'],
            item['proveedor'],
            item['rango_fechas'],
            item['origenes'],
            item['registros'],
            item['medios'],
            item['unidades'],
            item['monto_total_label'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} proveedores. Use Excel para el detalle completo.', '', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Estado: {payload.get('filtros', {}).get('grupo_label', '')}. "
        f"{_totales_text(summary)}. "
        f"Proveedores: {summary.get('proveedores', 0)}. "
        f"Pagos: {summary.get('registros', 0)}."
    )
