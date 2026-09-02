# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Cobros por cliente
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


REPORT_ID = 'cobros_por_cliente'
TITLE = 'Cobros por cliente'
DESCRIPTION = 'Cobros agrupados por cliente, origen, moneda y estado.'
WORKSHEET_TITLE = 'Cobros por cliente'
FILE_SLUG = 'cobros_por_cliente'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-user-check'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha de cobro'
FILTER_GROUP_LABEL = 'Estado'
DEFAULT_ALCANCE = 'gestion'
DEFAULT_GRUPO = 'CONFIRMADO'
MONEY_FIELDS = {'monto_total'}

HELP_TITLE = 'Cobros por cliente'
HELP_INTRO = 'Agrupa cobros reales por cliente, moneda y origen operativo.'
HELP_ITEMS = [
    'Por defecto muestra cobros confirmados de la gestion abierta.',
    'El origen distingue directos, compromisos, documentos por cobrar, facturas electronicas y mixtos.',
    'El total operativo suma solo cobros confirmados.',
    'Los totales se separan por moneda.',
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
    'DOCUMENTO_COBRAR': 'Documento por cobrar',
    'FACTURA_ELECTRONICA': 'Factura electronica',
    'MIXTO': 'Mixto',
}


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


def _estado_label(estado):
    etiquetas = {
        'CONFIRMADO': 'Confirmado',
        'BORRADOR': 'Borrador',
        'ANULADO': 'Anulado',
    }
    return etiquetas.get(estado or '', estado or '')


def _origenes_label(row):
    partes = []
    valores = [
        ('DIRECTO', int(row.get('directos') or 0)),
        ('COMPROMISO', int(row.get('compromisos') or 0)),
        ('DOCUMENTO_COBRAR', int(row.get('documentos') or 0)),
        ('FACTURA_ELECTRONICA', int(row.get('facturas') or 0)),
        ('MIXTO', int(row.get('mixtos') or 0)),
    ]
    for codigo, cantidad in valores:
        if cantidad:
            partes.append(f"{ORIGEN_LABELS[codigo]}: {cantidad}")
    return ' · '.join(partes) if partes else 'Sin origen'


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    fecha_desde = filtros['fecha_desde']
    fecha_hasta = filtros['fecha_hasta']
    unidad_id = filtros['unidad_negocio_id']
    estado = filtros['grupo']

    sql = """
        WITH factura_apps AS (
            SELECT
                fa.cobro_id,
                COUNT(DISTINCT fa.factura_electronica_id) AS factura_count,
                COALESCE(SUM(fa.monto_aplicado), 0)::numeric(18,2) AS factura_monto
            FROM contabilidad.factura_aplicacion fa
            WHERE fa.cobro_id IS NOT NULL
            GROUP BY fa.cobro_id
        ), documento_apps AS (
            SELECT
                da.cobro_id,
                COUNT(DISTINCT da.documento_por_cobrar_id) AS documento_count,
                COALESCE(SUM(da.monto_aplicado), 0)::numeric(18,2) AS documento_monto
            FROM contabilidad.documento_por_cobrar_aplicacion da
            WHERE da.cobro_id IS NOT NULL
            GROUP BY da.cobro_id
        ), detalle AS (
            SELECT
                cd.cobro_id,
                COUNT(*) AS linea_count,
                COUNT(DISTINCT cd.compromiso_detalle_id) FILTER (WHERE cd.compromiso_detalle_id IS NOT NULL) AS compromiso_count
            FROM contabilidad.cobro_detalle cd
            GROUP BY cd.cobro_id
        ), base AS (
            SELECT
                c.id AS cobro_id,
                c.fecha::date AS fecha,
                c.estado::text AS estado,
                c.medio_pago::text AS medio_pago,
                c.origen_operacion::text AS origen_operacion,
                c.moneda_codigo::text AS moneda_codigo,
                COALESCE(c.tipo_cambio, 1)::numeric(18,6) AS tipo_cambio,
                COALESCE(c.monto_total, 0)::numeric(18,2) AS monto_total,
                COALESCE(a.id, 0) AS cliente_id,
                COALESCE(a.nombre, a.razon_social, c.cliente_nombre_ref, 'Sin cliente')::text AS cliente,
                COALESCE(a.nit_ci, c.cliente_nit_ci_ref, '')::text AS cliente_doc,
                COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(fa.factura_count, 0) AS factura_count,
                COALESCE(doc.documento_count, 0) AS documento_count,
                COALESCE(det.compromiso_count, 0) AS compromiso_count,
                COALESCE(da.asiento_id, c.asiento_id) AS asiento_id,
                CASE
                    WHEN COALESCE(fa.factura_count, 0) > 0 AND COALESCE(doc.documento_count, 0) > 0 THEN 'MIXTO'
                    WHEN COALESCE(fa.factura_count, 0) > 0 THEN 'FACTURA_ELECTRONICA'
                    WHEN COALESCE(doc.documento_count, 0) > 0 THEN 'DOCUMENTO_COBRAR'
                    WHEN COALESCE(det.compromiso_count, 0) > 0 OR c.origen_operacion::text = 'COMPROMISO' THEN 'COMPROMISO'
                    WHEN c.origen_operacion::text = 'DOCUMENTO_COBRAR' THEN 'DOCUMENTO_COBRAR'
                    ELSE 'DIRECTO'
                END AS origen_operativo
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.auxiliar a ON a.id = c.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            LEFT JOIN contabilidad.documento_asiento da
                   ON da.tabla_origen = 'cobro'
                  AND da.origen_id = c.id
            LEFT JOIN factura_apps fa ON fa.cobro_id = c.id
            LEFT JOIN documento_apps doc ON doc.cobro_id = c.id
            LEFT JOIN detalle det ON det.cobro_id = c.id
            WHERE c.fecha BETWEEN %s AND %s
              AND (%s = '' OR c.estado::text = %s)
              AND (%s IS NULL OR c.unidad_negocio_id = %s)
        )
        SELECT
            cliente_id,
            cliente,
            cliente_doc,
            estado,
            moneda_codigo,
            COUNT(*)::integer AS registros,
            COUNT(*) FILTER (WHERE origen_operativo = 'DIRECTO')::integer AS directos,
            COUNT(*) FILTER (WHERE origen_operativo = 'COMPROMISO')::integer AS compromisos,
            COUNT(*) FILTER (WHERE origen_operativo = 'DOCUMENTO_COBRAR')::integer AS documentos,
            COUNT(*) FILTER (WHERE origen_operativo = 'FACTURA_ELECTRONICA')::integer AS facturas,
            COUNT(*) FILTER (WHERE origen_operativo = 'MIXTO')::integer AS mixtos,
            COUNT(*) FILTER (WHERE estado = 'CONFIRMADO' AND asiento_id IS NULL)::integer AS sin_asiento,
            MIN(fecha)::date AS primera_fecha,
            MAX(fecha)::date AS ultima_fecha,
            MAX(fecha)::date AS ultimo_cobro,
            SUM(COALESCE(monto_total, 0))::numeric(18,2) AS monto_total,
            SUM(COALESCE(monto_total, 0)) FILTER (WHERE estado = 'CONFIRMADO')::numeric(18,2) AS monto_confirmado,
            AVG(COALESCE(NULLIF(tipo_cambio, 0), 1))::numeric(18,6) AS tipo_cambio_promedio,
            STRING_AGG(DISTINCT COALESCE(medio_pago, ''), ', ')::text AS medios,
            STRING_AGG(DISTINCT COALESCE(unidad, 'Sin unidad'), ', ')::text AS unidades
        FROM base
        GROUP BY cliente_id, cliente, cliente_doc, estado, moneda_codigo
        ORDER BY
            COALESCE(SUM(COALESCE(monto_total, 0)) FILTER (WHERE estado = 'CONFIRMADO'), 0) DESC,
            SUM(COALESCE(monto_total, 0)) DESC,
            MAX(fecha) DESC,
            cliente ASC
        LIMIT %s
    """
    params = (fecha_desde, fecha_hasta, estado, estado, unidad_id, unidad_id, int(limit_rows))
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)

    mapped = []
    for idx, row in enumerate(rows, start=1):
        estado_codigo = row.get('estado') or ''
        monto_total = _decimal(row.get('monto_total'))
        monto_confirmado = _decimal(row.get('monto_confirmado'))
        moneda = row.get('moneda_codigo') or ''
        primera_fecha = row.get('primera_fecha')
        ultima_fecha = row.get('ultima_fecha')
        rango_fechas = _date_label(ultima_fecha)
        if primera_fecha and ultima_fecha and primera_fecha != ultima_fecha:
            rango_fechas = f"{_date_label(primera_fecha)} al {_date_label(ultima_fecha)}"

        item = {
            'nro': idx,
            'cliente_id': row.get('cliente_id') or 0,
            'cliente': row.get('cliente') or 'Sin cliente',
            'cliente_doc': row.get('cliente_doc') or '',
            'estado_codigo': estado_codigo,
            'estado': _estado_label(estado_codigo),
            'registros': int(row.get('registros') or 0),
            'directos': int(row.get('directos') or 0),
            'compromisos': int(row.get('compromisos') or 0),
            'documentos': int(row.get('documentos') or 0),
            'facturas': int(row.get('facturas') or 0),
            'mixtos': int(row.get('mixtos') or 0),
            'sin_asiento': int(row.get('sin_asiento') or 0),
            'primera_fecha_label': _date_label(primera_fecha),
            'ultima_fecha_label': _date_label(ultima_fecha),
            'ultimo_cobro_label': _date_label(row.get('ultimo_cobro')),
            'rango_fechas': rango_fechas,
            'medios': row.get('medios') or '',
            'unidades': row.get('unidades') or '',
            'origenes': '',
            'moneda_codigo': moneda,
            'tipo_cambio_promedio': float(_decimal(row.get('tipo_cambio_promedio'))),
            'monto_total': float(monto_total),
            'monto_total_label': _format_money(monto_total, moneda),
            'monto_confirmado': float(monto_confirmado),
            'monto_confirmado_label': _format_money(monto_confirmado, moneda),
            'control': 'Sin asiento' if int(row.get('sin_asiento') or 0) else 'OK',
        }
        item['origenes'] = _origenes_label(item)
        mapped.append(item)
    return mapped


def display_columns():
    return [
        {'key': 'estado', 'label': 'Estado', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
        {'key': 'cliente', 'label': 'Cliente', 'sub_key': 'cliente_doc', 'align': 'left', 'strong': True},
        {'key': 'ultimo_cobro_label', 'label': 'Ultimo cobro', 'sub_key': 'rango_fechas', 'align': 'center'},
        {'key': 'origenes', 'label': 'Origenes', 'align': 'left'},
        {'key': 'registros', 'label': 'Cobros', 'sub_key': 'control', 'align': 'center'},
        {'key': 'medios', 'label': 'Medios', 'align': 'left'},
        {'key': 'unidades', 'label': 'Unidades', 'align': 'left'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
    ]


def _sumar_total(totales, moneda, monto):
    codigo = str(moneda or '').upper() or 'SIN_MONEDA'
    totales[codigo] = totales.get(codigo, Decimal('0.00')) + _decimal(monto)


def _totales_payload(totales):
    return [
        {'moneda_codigo': moneda, 'total': float(total), 'total_label': _format_money(total, moneda)}
        for moneda, total in sorted(totales.items())
    ]


def _build_summary(rows):
    totales_confirmados = {}
    totales_registrados = {}
    clientes = set()
    registros = 0
    confirmados = 0
    borradores = 0
    anulados = 0
    directos = 0
    compromisos = 0
    documentos = 0
    facturas = 0
    mixtos = 0
    sin_asiento = 0

    for row in rows:
        moneda = row.get('moneda_codigo') or ''
        estado = row.get('estado_codigo')
        registros_row = int(row.get('registros') or 0)
        clientes.add((row.get('cliente') or '').strip().upper())
        registros += registros_row
        directos += int(row.get('directos') or 0)
        compromisos += int(row.get('compromisos') or 0)
        documentos += int(row.get('documentos') or 0)
        facturas += int(row.get('facturas') or 0)
        mixtos += int(row.get('mixtos') or 0)
        sin_asiento += int(row.get('sin_asiento') or 0)

        _sumar_total(totales_registrados, moneda, row.get('monto_total'))
        if estado == 'CONFIRMADO':
            confirmados += registros_row
            _sumar_total(totales_confirmados, moneda, row.get('monto_confirmado'))
        elif estado == 'ANULADO':
            anulados += registros_row
        else:
            borradores += registros_row

    totales_por_moneda = _totales_payload(totales_confirmados)
    moneda_unica = totales_por_moneda[0]['moneda_codigo'] if len(totales_por_moneda) == 1 else ''
    total_unico = Decimal(str(totales_por_moneda[0]['total'])) if len(totales_por_moneda) == 1 else Decimal('0.00')

    return {
        'cantidad': len(rows),
        'clientes': len([item for item in clientes if item]),
        'registros': registros,
        'confirmados': confirmados,
        'borradores': borradores,
        'anulados': anulados,
        'directos': directos,
        'compromisos': compromisos,
        'documentos': documentos,
        'facturas': facturas,
        'mixtos': mixtos,
        'sin_asiento': sin_asiento,
        'moneda_unica': moneda_unica,
        'totales_por_moneda': totales_por_moneda,
        'totales_registrados_por_moneda': _totales_payload(totales_registrados),
        'total_general': float(total_unico),
        'total_general_label': _format_money(total_unico, moneda_unica) if moneda_unica else 'Por moneda',
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Total confirmado', 'value': summary.get('total_general_label'), 'note': 'Solo cobros confirmados', 'kind': 'total'},
        {'label': 'Clientes', 'value': summary.get('clientes', 0), 'note': 'Con cobros', 'kind': 'group'},
        {'label': 'Cobros', 'value': summary.get('registros', 0), 'note': 'Registros agrupados', 'kind': 'group'},
        {'label': 'Docs./facturas', 'value': summary.get('documentos', 0) + summary.get('facturas', 0) + summary.get('mixtos', 0), 'note': 'Cartera cobrada', 'kind': 'group'},
        {'label': 'Control', 'value': summary.get('sin_asiento', 0), 'note': 'Confirmados sin asiento', 'kind': 'critical' if summary.get('sin_asiento') else 'group'},
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
        'empty_title': 'No hay cobros por cliente para los filtros seleccionados',
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
        ('cliente', 'Cliente', 36),
        ('cliente_doc', 'NIT/CI', 16),
        ('estado', 'Estado', 14),
        ('ultimo_cobro_label', 'Ultimo cobro', 14),
        ('rango_fechas', 'Rango fechas', 24),
        ('origenes', 'Origenes', 55),
        ('registros', 'Cobros', 12),
        ('directos', 'Directos', 10),
        ('compromisos', 'Compromisos', 13),
        ('documentos', 'Documentos', 13),
        ('facturas', 'Facturas electronicas', 18),
        ('mixtos', 'Mixtos', 10),
        ('medios', 'Medios', 28),
        ('unidades', 'Unidades', 36),
        ('control', 'Control', 16),
        ('moneda_codigo', 'Moneda', 10),
        ('tipo_cambio_promedio', 'T/C promedio', 14),
        ('monto_total', 'Total registrado', 16),
        ('monto_confirmado', 'Total confirmado', 18),
    ]


def _totales_text(summary):
    totales = summary.get('totales_por_moneda') or []
    if not totales:
        return 'Total confirmado: 0.00'
    if len(totales) == 1:
        return f"Total confirmado: {totales[0].get('total_label', '0.00')}"
    partes = [f"{item.get('total_label', '0.00')} ({item.get('moneda_simbolo') or item.get('moneda_codigo')})" for item in totales]
    return 'Totales confirmados por moneda: ' + '; '.join(partes)


def excel_summary_text(summary):
    return (
        f"{_totales_text(summary)} · "
        f"Clientes: {summary.get('clientes', 0)} · "
        f"Cobros: {summary.get('registros', 0)} · "
        f"Confirmados: {summary.get('confirmados', 0)} · "
        f"Documentos/facturas: {summary.get('documentos', 0) + summary.get('facturas', 0) + summary.get('mixtos', 0)} · "
        f"Control: {summary.get('sin_asiento', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Cliente', 'width': 58, 'align': 'left'},
        {'label': 'Estado', 'width': 22, 'align': 'center'},
        {'label': 'Ultimo cobro', 'width': 24, 'align': 'center'},
        {'label': 'Origenes', 'width': 68, 'align': 'left'},
        {'label': 'Cobros', 'width': 16, 'align': 'center'},
        {'label': 'Medios', 'width': 36, 'align': 'left'},
        {'label': 'Unidades', 'width': 48, 'align': 'left'},
        {'label': 'Total', 'width': 28, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['cliente'],
            item['estado'],
            item['ultimo_cobro_label'],
            item['origenes'],
            item['registros'],
            item['medios'],
            item['unidades'],
            item['monto_total_label'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append([f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} clientes. Use Excel para el detalle completo.', '', '', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Estado: {payload.get('filtros', {}).get('grupo_label', '')}. "
        f"{_totales_text(summary)}. "
        f"Clientes: {summary.get('clientes', 0)}. "
        f"Cobros: {summary.get('registros', 0)}."
    )
