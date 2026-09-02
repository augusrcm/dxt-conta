# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Cobros realizados
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


REPORT_ID = 'cobros_realizados'
TITLE = 'Cobros realizados'
DESCRIPTION = 'Cobros por fecha, origen, cliente, medio y estado.'
WORKSHEET_TITLE = 'Cobros realizados'
FILE_SLUG = 'cobros_realizados'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-cash-register'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha de cobro'
FILTER_GROUP_LABEL = 'Estado'
DEFAULT_ALCANCE = 'gestion'
DEFAULT_GRUPO = 'CONFIRMADO'
MONEY_FIELDS = {'monto_total'}

HELP_TITLE = 'Cobros realizados'
HELP_INTRO = 'Muestra cobros registrados y su origen operativo.'
HELP_ITEMS = [
    'Por defecto muestra cobros confirmados de la gestion abierta.',
    'El total operativo suma solo cobros confirmados.',
    'Los cobros anulados y en borrador se muestran solo si se cambia el filtro de estado.',
    'El origen identifica cobros directos, compromisos, documentos por cobrar y facturas electronicas.',
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


def _to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _origen_operativo(row):
    factura_count = _to_int(row.get('factura_count'))
    documento_count = _to_int(row.get('documento_count'))
    compromiso_count = _to_int(row.get('compromiso_count'))
    origen = str(row.get('origen_operacion') or '').upper()

    if factura_count and documento_count:
        return 'MIXTO'
    if factura_count:
        return 'FACTURA_ELECTRONICA'
    if documento_count:
        return 'DOCUMENTO_COBRAR'
    if compromiso_count or origen == 'COMPROMISO':
        return 'COMPROMISO'
    if origen == 'DOCUMENTO_COBRAR':
        return 'DOCUMENTO_COBRAR'
    return 'DIRECTO'


def _detalle_origen(row, origen_codigo):
    partes = []
    factura_count = _to_int(row.get('factura_count'))
    documento_count = _to_int(row.get('documento_count'))
    compromiso_count = _to_int(row.get('compromiso_count'))
    linea_count = _to_int(row.get('linea_count'))

    factura_refs = str(row.get('factura_refs') or '').strip()
    documento_refs = str(row.get('documento_refs') or '').strip()
    compromiso_refs = str(row.get('compromiso_refs') or '').strip()

    if factura_count:
        partes.append(f"Facturas: {factura_refs}" if factura_refs else f"Facturas: {factura_count}")
    if documento_count:
        partes.append(f"Documentos: {documento_refs}" if documento_refs else f"Documentos: {documento_count}")
    if compromiso_count:
        partes.append(f"Compromisos: {compromiso_refs}" if compromiso_refs else f"Compromisos: {compromiso_count}")
    if not partes and linea_count:
        partes.append(f"Lineas: {linea_count}")
    if not partes:
        referencia = str(row.get('referencia') or '').strip()
        if referencia:
            partes.append(referencia)
    if not partes:
        partes.append(ORIGEN_LABELS.get(origen_codigo, origen_codigo))
    return ' · '.join(partes)


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
                COALESCE(SUM(fa.monto_aplicado), 0)::numeric(18,2) AS factura_monto,
                STRING_AGG(DISTINCT ('Fac. ' || COALESCE(fe.numero_factura::text, fe.id::text)), ', ') AS factura_refs
            FROM contabilidad.factura_aplicacion fa
            INNER JOIN contabilidad.factura_electronica fe ON fe.id = fa.factura_electronica_id
            WHERE fa.cobro_id IS NOT NULL
            GROUP BY fa.cobro_id
        ), documento_apps AS (
            SELECT
                da.cobro_id,
                COUNT(DISTINCT da.documento_por_cobrar_id) AS documento_count,
                COALESCE(SUM(da.monto_aplicado), 0)::numeric(18,2) AS documento_monto,
                STRING_AGG(DISTINCT (COALESCE(d.tipo_documento::text, 'DOC') || ' ' || COALESCE(d.numero_documento::text, d.id::text)), ', ') AS documento_refs,
                STRING_AGG(DISTINCT COALESCE(d.origen_documento::text, ''), ', ') AS documento_origenes
            FROM contabilidad.documento_por_cobrar_aplicacion da
            INNER JOIN contabilidad.documento_por_cobrar d ON d.id = da.documento_por_cobrar_id
            WHERE da.cobro_id IS NOT NULL
            GROUP BY da.cobro_id
        ), detalle AS (
            SELECT
                cd.cobro_id,
                COUNT(*) AS linea_count,
                COUNT(DISTINCT cd.compromiso_detalle_id) FILTER (WHERE cd.compromiso_detalle_id IS NOT NULL) AS compromiso_count,
                STRING_AGG(DISTINCT COALESCE(co.codigo::text, cd.compromiso_detalle_id::text), ', ') FILTER (WHERE cd.compromiso_detalle_id IS NOT NULL) AS compromiso_refs
            FROM contabilidad.cobro_detalle cd
            LEFT JOIN contabilidad.compromiso_detalle cod ON cod.id = cd.compromiso_detalle_id
            LEFT JOIN contabilidad.compromiso co ON co.id = cod.compromiso_id
            GROUP BY cd.cobro_id
        )
        SELECT
            c.id AS cobro_id,
            c.fecha::date AS fecha,
            c.estado::text AS estado,
            c.medio_pago::text AS medio_pago,
            c.origen_operacion::text AS origen_operacion,
            c.moneda_codigo::text AS moneda_codigo,
            COALESCE(c.tipo_cambio, 1)::numeric(18,6) AS tipo_cambio,
            COALESCE(c.monto_total, 0)::numeric(18,2) AS monto_total,
            COALESCE(c.referencia, '')::text AS referencia,
            COALESCE(c.glosa, '')::text AS glosa,
            COALESCE(a.nombre, a.razon_social, c.cliente_nombre_ref, 'Sin cliente')::text AS cliente,
            COALESCE(a.nit_ci, c.cliente_nit_ci_ref, '')::text AS cliente_doc,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad')::text AS unidad,
            COALESCE(cj.codigo || ' · ' || cj.nombre, cj.nombre, '')::text AS caja,
            COALESCE(cb.nombre_banco || ' · ' || cb.numero_cuenta, cb.nombre_banco, '')::text AS cuenta_bancaria,
            COALESCE(da.asiento_id, c.asiento_id) AS asiento_id,
            COALESCE(fa.factura_count, 0) AS factura_count,
            COALESCE(fa.factura_monto, 0)::numeric(18,2) AS factura_monto,
            COALESCE(fa.factura_refs, '')::text AS factura_refs,
            COALESCE(doc.documento_count, 0) AS documento_count,
            COALESCE(doc.documento_monto, 0)::numeric(18,2) AS documento_monto,
            COALESCE(doc.documento_refs, '')::text AS documento_refs,
            COALESCE(doc.documento_origenes, '')::text AS documento_origenes,
            COALESCE(det.linea_count, 0) AS linea_count,
            COALESCE(det.compromiso_count, 0) AS compromiso_count,
            COALESCE(det.compromiso_refs, '')::text AS compromiso_refs
        FROM contabilidad.cobro c
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        LEFT JOIN contabilidad.caja cj ON cj.id = c.caja_id
        LEFT JOIN contabilidad.cuenta_bancaria cb ON cb.id = c.cuenta_bancaria_id
        LEFT JOIN contabilidad.documento_asiento da
               ON da.tabla_origen = 'cobro'
              AND da.origen_id = c.id
        LEFT JOIN factura_apps fa ON fa.cobro_id = c.id
        LEFT JOIN documento_apps doc ON doc.cobro_id = c.id
        LEFT JOIN detalle det ON det.cobro_id = c.id
        WHERE c.fecha BETWEEN %s AND %s
          AND (%s = '' OR c.estado::text = %s)
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
        ORDER BY c.fecha DESC, c.id DESC
        LIMIT %s
    """
    params = (fecha_desde, fecha_hasta, estado, estado, unidad_id, unidad_id, int(limit_rows))
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)

    mapped = []
    for idx, row in enumerate(rows, start=1):
        monto = _decimal(row.get('monto_total'))
        moneda = row.get('moneda_codigo') or ''
        caja = row.get('caja') or ''
        cuenta_bancaria = row.get('cuenta_bancaria') or ''
        destino = caja or cuenta_bancaria or row.get('medio_pago') or ''
        origen_codigo = _origen_operativo(row)
        origen_label = ORIGEN_LABELS.get(origen_codigo, origen_codigo)
        detalle_origen = _detalle_origen(row, origen_codigo)
        asiento_id = row.get('asiento_id') or ''
        estado_codigo = row.get('estado') or ''
        control = 'OK'
        if estado_codigo == 'CONFIRMADO' and not asiento_id:
            control = 'Sin asiento'
        elif estado_codigo == 'ANULADO':
            control = 'Anulado'
        elif estado_codigo == 'BORRADOR':
            control = 'Borrador'

        mapped.append({
            'nro': idx,
            'cobro_id': row.get('cobro_id'),
            'fecha_label': _date_label(row.get('fecha')),
            'fecha_iso': row.get('fecha').isoformat() if row.get('fecha') else '',
            'estado_codigo': estado_codigo,
            'estado': estado_codigo,
            'medio_pago': row.get('medio_pago') or '',
            'origen_codigo': origen_codigo,
            'origen': origen_label,
            'origen_operacion': row.get('origen_operacion') or '',
            'detalle_origen': detalle_origen,
            'cliente': row.get('cliente') or 'Sin cliente',
            'cliente_doc': row.get('cliente_doc') or '',
            'destino': destino,
            'caja': caja,
            'cuenta_bancaria': cuenta_bancaria,
            'unidad': row.get('unidad') or '',
            'referencia': row.get('referencia') or '',
            'glosa': row.get('glosa') or '',
            'asiento_id': asiento_id,
            'control': control,
            'moneda_codigo': moneda,
            'tipo_cambio': float(_decimal(row.get('tipo_cambio'))),
            'tipo_cambio_label': f"{_decimal(row.get('tipo_cambio')):,.6f}",
            'factura_count': _to_int(row.get('factura_count')),
            'documento_count': _to_int(row.get('documento_count')),
            'compromiso_count': _to_int(row.get('compromiso_count')),
            'linea_count': _to_int(row.get('linea_count')),
            'factura_monto': float(_decimal(row.get('factura_monto'))),
            'documento_monto': float(_decimal(row.get('documento_monto'))),
            'monto_total': float(monto),
            'monto_total_label': _format_money(monto, moneda),
        })
    return mapped


def display_columns():
    return [
        {'key': 'fecha_label', 'label': 'Fecha', 'align': 'center'},
        {'key': 'estado', 'label': 'Estado', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
        {'key': 'origen', 'label': 'Origen', 'sub_key': 'detalle_origen', 'align': 'left', 'strong': True},
        {'key': 'cliente', 'label': 'Cliente', 'sub_key': 'cliente_doc', 'align': 'left', 'strong': True},
        {'key': 'medio_pago', 'label': 'Medio', 'sub_key': 'destino', 'align': 'left'},
        {'key': 'unidad', 'label': 'Unidad', 'align': 'left'},
        {'key': 'referencia', 'label': 'Referencia', 'sub_key': 'control', 'align': 'left'},
        {'key': 'monto_total', 'label': 'Monto', 'type': 'money', 'align': 'right'},
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
        monto = _decimal(row.get('monto_total'))
        estado = row.get('estado_codigo')
        origen = row.get('origen_codigo')

        _sumar_total(totales_registrados, moneda, monto)
        if estado == 'CONFIRMADO':
            confirmados += 1
            _sumar_total(totales_confirmados, moneda, monto)
            if row.get('control') == 'Sin asiento':
                sin_asiento += 1
        elif estado == 'ANULADO':
            anulados += 1
        else:
            borradores += 1

        if origen == 'COMPROMISO':
            compromisos += 1
        elif origen == 'DOCUMENTO_COBRAR':
            documentos += 1
        elif origen == 'FACTURA_ELECTRONICA':
            facturas += 1
        elif origen == 'MIXTO':
            mixtos += 1
        else:
            directos += 1

    totales_por_moneda = _totales_payload(totales_confirmados)
    moneda_unica = totales_por_moneda[0]['moneda_codigo'] if len(totales_por_moneda) == 1 else ''
    total_unico = Decimal(str(totales_por_moneda[0]['total'])) if len(totales_por_moneda) == 1 else Decimal('0.00')

    return {
        'cantidad': len(rows),
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
        {'label': 'Registros', 'value': summary.get('cantidad', 0), 'note': 'Cobros encontrados', 'kind': 'group'},
        {'label': 'Documentos', 'value': summary.get('documentos', 0) + summary.get('facturas', 0) + summary.get('mixtos', 0), 'note': 'Docs. y facturas', 'kind': 'group'},
        {'label': 'Compromisos', 'value': summary.get('compromisos', 0), 'note': 'Cobros programados', 'kind': 'group'},
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
        'empty_title': 'No hay cobros para los filtros seleccionados',
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
        ('fecha_label', 'Fecha', 13),
        ('estado', 'Estado', 14),
        ('origen', 'Origen operativo', 22),
        ('detalle_origen', 'Detalle origen', 55),
        ('cliente', 'Cliente', 36),
        ('cliente_doc', 'NIT/CI', 16),
        ('medio_pago', 'Medio', 13),
        ('destino', 'Caja/Banco', 34),
        ('unidad', 'Unidad', 30),
        ('referencia', 'Referencia', 24),
        ('glosa', 'Glosa', 45),
        ('control', 'Control', 16),
        ('asiento_id', 'Asiento ID', 12),
        ('factura_count', 'Facturas', 10),
        ('documento_count', 'Documentos', 12),
        ('compromiso_count', 'Compromisos', 12),
        ('moneda_codigo', 'Moneda', 10),
        ('tipo_cambio', 'Tipo cambio', 14),
        ('monto_total', 'Monto', 16),
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
        f"Confirmados: {summary.get('confirmados', 0)} · "
        f"Borrador: {summary.get('borradores', 0)} · "
        f"Anulados: {summary.get('anulados', 0)} · "
        f"Documentos/facturas: {summary.get('documentos', 0) + summary.get('facturas', 0) + summary.get('mixtos', 0)} · "
        f"Registros: {summary.get('cantidad', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Fecha', 'width': 21, 'align': 'center'},
        {'label': 'Estado', 'width': 23, 'align': 'center'},
        {'label': 'Origen', 'width': 36, 'align': 'left'},
        {'label': 'Cliente', 'width': 52, 'align': 'left'},
        {'label': 'Medio', 'width': 24, 'align': 'left'},
        {'label': 'Unidad', 'width': 42, 'align': 'left'},
        {'label': 'Referencia', 'width': 42, 'align': 'left'},
        {'label': 'Monto', 'width': 28, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['fecha_label'],
            item['estado'],
            item['origen'],
            item['cliente'],
            item['medio_pago'],
            item['unidad'],
            item['referencia'],
            item['monto_total_label'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', '', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} cobros. Use Excel para el detalle completo.', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Estado: {payload.get('filtros', {}).get('grupo_label', '')}. "
        f"{_totales_text(summary)}. "
        f"Confirmados: {summary.get('confirmados', 0)}. "
        f"Registros: {summary.get('cantidad', 0)}."
    )
