# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Operaciones en borrador
# ============================================================

from __future__ import annotations

from datetime import date, timedelta

from modules.reportes_rapidos.core.config import MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.utils import clean as _clean
from modules.reportes_rapidos.core.utils import parse_date as _parse_date
from modules.reportes_rapidos.core.utils import parse_optional_int as _parse_optional_int
from modules.reportes_rapidos.reports.control_operativo_common import (
    build_payload_common,
    descripcion_periodo,
    execute_rows,
    excel_summary_text_control,
    map_control_row,
    pdf_header_note_control,
)


REPORT_ID = 'operaciones_en_borrador'
TITLE = 'Operaciones en borrador'
DESCRIPTION = 'Control de borradores financieros y contables por area, origen y moneda.'
WORKSHEET_TITLE = 'Operaciones borrador'
FILE_SLUG = 'operaciones_en_borrador'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-pen-to-square'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha de operacion'
FILTER_GROUP_LABEL = 'Area'
DEFAULT_ALCANCE = 'todos'
DEFAULT_GRUPO = ''
MONEY_FIELDS = {'monto'}

HELP_TITLE = 'Operaciones en borrador'
HELP_INTRO = 'Permite revisar operaciones que aun no tienen efecto operativo definitivo.'
HELP_ITEMS = [
    'Muestra borradores reales de contabilidad, tesoreria, facturacion y cartera.',
    'Los asientos automaticos asociados a cobros, pagos, movimientos, facturas o documentos no se duplican como operaciones independientes.',
    'Los importes se totalizan por moneda para evitar saldos mezclados.',
]

ALCANCES = {
    'todos': 'Todos',
    'hoy': 'Hoy',
    'ayer': 'Ayer',
    'ultimos_7': 'Ultimos 7 dias',
    'este_mes': 'Este mes',
    'rango': 'Rango personalizado',
}

GRUPOS = {
    '': 'Todas',
    'CONTABILIDAD': 'Contabilidad',
    'TESORERIA': 'Tesoreria',
    'FACTURACION': 'Facturacion',
    'CARTERA': 'Cartera',
}


def validate_filters(args):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El periodo seleccionado no es valido.')

    grupo = _clean(args.get('grupo'))
    if grupo == '' and DEFAULT_GRUPO is not None:
        grupo = DEFAULT_GRUPO
    if grupo not in GRUPOS:
        raise ValueError('El area seleccionada no es valida.')

    fecha_base = _parse_date(args.get('fecha_base'), FILTER_DATE_LABEL, default=hoy)
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if alcance == 'todos':
        fecha_desde = date(1900, 1, 1)
        fecha_hasta = date(9999, 12, 31)
    elif alcance == 'hoy':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
    elif alcance == 'ayer':
        fecha_desde = fecha_base - timedelta(days=1)
        fecha_hasta = fecha_desde
    elif alcance == 'ultimos_7':
        fecha_desde = fecha_base - timedelta(days=6)
        fecha_hasta = fecha_base
    elif alcance == 'este_mes':
        fecha_desde = fecha_base.replace(day=1)
        fecha_hasta = fecha_base
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


def _descripcion(filtros):
    if filtros['alcance'] == 'todos':
        return 'Todos los borradores'
    return descripcion_periodo(filtros)


def _map_row(row, idx):
    item = map_control_row(row, idx)
    item['bloque'] = row.get('bloque') or ''
    item['bloque_label'] = row.get('bloque_label') or GRUPOS.get(row.get('bloque') or '', row.get('bloque') or '')
    return item


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    sql = """
        WITH asiento_totales AS (
            SELECT
                asiento_id,
                SUM(COALESCE(debe, 0))::numeric(18,2) AS monto
            FROM contabilidad.asiento_detalle
            GROUP BY asiento_id
        ), operaciones AS (
            SELECT
                'CONTABILIDAD'::text AS bloque,
                'Contabilidad'::text AS bloque_label,
                a.fecha::date AS fecha,
                'Asiento contable'::text AS origen,
                COALESCE(NULLIF(a.referencia::text, ''), 'Asiento #' || a.id::text)::text AS referencia,
                COALESCE(NULLIF(a.cliente_nombre_ref::text, ''), 'Sin auxiliar')::text AS cliente_proveedor,
                COALESCE(NULLIF(a.glosa::text, ''), 'Asiento en borrador')::text AS detalle,
                a.estado::text AS estado,
                a.estado::text AS estado_codigo,
                a.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(a.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(at.monto, 0)::numeric(18,2) AS monto,
                'ALTA'::text AS prioridad_codigo,
                'Alta'::text AS prioridad,
                'Confirmar o anular'::text AS accion
            FROM contabilidad.asiento a
            LEFT JOIN asiento_totales at ON at.asiento_id = a.id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
            WHERE a.estado::text = 'BORRADOR'
              AND COALESCE(a.tabla_origen::text, '') NOT IN (
                  'contabilidad.cobro',
                  'contabilidad.pago',
                  'contabilidad.movimiento_tesoreria',
                  'contabilidad.factura_electronica',
                  'contabilidad.documento_por_cobrar'
              )

            UNION ALL

            SELECT
                'TESORERIA'::text AS bloque,
                'Tesoreria'::text AS bloque_label,
                p.fecha::date AS fecha,
                'Pago'::text AS origen,
                COALESCE(NULLIF(p.referencia::text, ''), 'Pago #' || p.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(p.cliente_nombre_ref::text, ''), 'Sin proveedor')::text AS cliente_proveedor,
                COALESCE(NULLIF(p.glosa::text, ''), 'Pago en borrador')::text AS detalle,
                p.estado::text AS estado,
                p.estado::text AS estado_codigo,
                p.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(p.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(p.monto_total, 0)::numeric(18,2) AS monto,
                'ALTA'::text AS prioridad_codigo,
                'Alta'::text AS prioridad,
                'Confirmar o anular'::text AS accion
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = p.proveedor_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE p.estado::text = 'BORRADOR'

            UNION ALL

            SELECT
                'TESORERIA'::text AS bloque,
                'Tesoreria'::text AS bloque_label,
                c.fecha::date AS fecha,
                'Cobro'::text AS origen,
                COALESCE(NULLIF(c.referencia::text, ''), 'Cobro #' || c.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(c.cliente_nombre_ref::text, ''), 'Sin cliente')::text AS cliente_proveedor,
                COALESCE(NULLIF(c.glosa::text, ''), 'Cobro en borrador')::text AS detalle,
                c.estado::text AS estado,
                c.estado::text AS estado_codigo,
                c.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(c.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(c.monto_total, 0)::numeric(18,2) AS monto,
                'ALTA'::text AS prioridad_codigo,
                'Alta'::text AS prioridad,
                'Confirmar o anular'::text AS accion
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = c.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE c.estado::text = 'BORRADOR'

            UNION ALL

            SELECT
                'TESORERIA'::text AS bloque,
                'Tesoreria'::text AS bloque_label,
                m.fecha::date AS fecha,
                'Movimiento tesoreria'::text AS origen,
                COALESCE(NULLIF(m.referencia::text, ''), 'Movimiento #' || m.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), 'Sin auxiliar')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ', NULLIF(m.tipo_movimiento::text, ''), NULLIF(m.glosa::text, '')))::text AS detalle,
                m.estado::text AS estado,
                m.estado::text AS estado_codigo,
                m.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(m.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(m.monto, 0)::numeric(18,2) AS monto,
                'MEDIA'::text AS prioridad_codigo,
                'Media'::text AS prioridad,
                'Confirmar o anular'::text AS accion
            FROM contabilidad.movimiento_tesoreria m
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = m.auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
            WHERE m.estado::text = 'BORRADOR'

            UNION ALL

            SELECT
                'FACTURACION'::text AS bloque,
                'Facturacion'::text AS bloque_label,
                f.fecha_emision::date AS fecha,
                'Factura electronica'::text AS origen,
                COALESCE(NULLIF(f.numero_factura::text, ''), 'Factura #' || f.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(f.nombre_cliente::text, ''), 'Sin cliente')::text AS cliente_proveedor,
                COALESCE(NULLIF(f.cuf::text, ''), 'Factura en borrador')::text AS detalle,
                f.estado::text AS estado,
                f.estado::text AS estado_codigo,
                f.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(f.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(f.importe_total, 0)::numeric(18,2) AS monto,
                'ALTA'::text AS prioridad_codigo,
                'Alta'::text AS prioridad,
                'Completar o anular'::text AS accion
            FROM contabilidad.factura_electronica f
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = f.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = f.unidad_negocio_id
            WHERE UPPER(f.estado::text) = 'BORRADOR'

            UNION ALL

            SELECT
                'CARTERA'::text AS bloque,
                'Cartera'::text AS bloque_label,
                d.fecha_documento::date AS fecha,
                'Documento por cobrar'::text AS origen,
                COALESCE(NULLIF(d.numero_documento::text, ''), 'Documento #' || d.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(d.cliente_nombre::text, ''), 'Sin cliente')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ', NULLIF(d.tipo_documento::text, ''), NULLIF(d.descripcion::text, '')))::text AS detalle,
                d.estado::text AS estado,
                d.estado::text AS estado_codigo,
                d.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(d.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(d.importe_total, 0)::numeric(18,2) AS monto,
                'ALTA'::text AS prioridad_codigo,
                'Alta'::text AS prioridad,
                'Completar o anular'::text AS accion
            FROM contabilidad.documento_por_cobrar d
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = d.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
            WHERE d.estado::text = 'BORRADOR'
        )
        SELECT *
        FROM operaciones
        WHERE fecha BETWEEN %s AND %s
          AND (%s = '' OR bloque = %s)
          AND (%s IS NULL OR unidad_negocio_id = %s)
        ORDER BY fecha DESC, bloque ASC, origen ASC, referencia ASC
        LIMIT %s
    """
    params = (
        filtros['fecha_desde'], filtros['fecha_hasta'],
        filtros['grupo'], filtros['grupo'],
        filtros['unidad_negocio_id'], filtros['unidad_negocio_id'],
        int(limit_rows),
    )
    rows = execute_rows(sql, params)
    return [_map_row(row, idx) for idx, row in enumerate(rows, start=1)]


def display_columns():
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'fecha_label', 'label': 'Fecha', 'align': 'center'},
        {'key': 'bloque_label', 'label': 'Area', 'align': 'left'},
        {'key': 'origen', 'label': 'Origen', 'align': 'left'},
        {'key': 'referencia', 'label': 'Referencia', 'align': 'left'},
        {'key': 'cliente_proveedor', 'label': 'Cliente / Proveedor', 'align': 'left', 'strong': True},
        {'key': 'estado', 'label': 'Estado', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
        {'key': 'unidad', 'label': 'Unidad', 'align': 'left'},
        {'key': 'monto', 'label': 'Monto', 'type': 'money', 'align': 'right'},
        {'key': 'accion', 'label': 'Control', 'align': 'left'},
    ]


def build_payload(filtros, limit_rows=MAX_ROWS_SCREEN):
    rows = _fetch_rows(filtros, limit_rows=limit_rows)
    filtros = dict(filtros)
    filtros['descripcion'] = _descripcion(filtros)
    return build_payload_common(
        REPORT_ID,
        TITLE,
        DESCRIPTION,
        filtros,
        rows,
        display_columns(),
        'No hay operaciones en borrador para los filtros seleccionados',
        include_money=True,
    )


def excel_columns():
    return [
        ('prioridad', 'Prioridad', 14),
        ('fecha_label', 'Fecha', 13),
        ('bloque_label', 'Area', 18),
        ('origen', 'Origen', 28),
        ('referencia', 'Referencia', 24),
        ('cliente_proveedor', 'Cliente / Proveedor', 36),
        ('detalle', 'Detalle', 52),
        ('estado', 'Estado', 16),
        ('unidad', 'Unidad', 28),
        ('moneda_codigo', 'Moneda', 10),
        ('monto', 'Monto', 16),
        ('accion', 'Control', 24),
    ]


def excel_summary_text(summary):
    return excel_summary_text_control(summary)


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 21, 'align': 'center'},
        {'label': 'Fecha', 'width': 22, 'align': 'center'},
        {'label': 'Area', 'width': 25, 'align': 'left'},
        {'label': 'Origen', 'width': 36, 'align': 'left'},
        {'label': 'Referencia', 'width': 34, 'align': 'left'},
        {'label': 'Cliente / Proveedor', 'width': 52, 'align': 'left'},
        {'label': 'Estado', 'width': 25, 'align': 'center'},
        {'label': 'Monto', 'width': 28, 'align': 'right'},
        {'label': 'Control', 'width': 30, 'align': 'left'},
    ]


def pdf_rows(payload):
    rows = []
    max_rows = 45
    for item in payload['rows'][:max_rows]:
        rows.append([
            item.get('prioridad', ''),
            item.get('fecha_label', ''),
            item.get('bloque_label', ''),
            item.get('origen', ''),
            item.get('referencia', ''),
            item.get('cliente_proveedor', ''),
            item.get('estado', ''),
            item.get('monto_label', ''),
            item.get('accion', ''),
        ])
    if len(payload['rows']) > max_rows:
        filler = [''] * 9
        filler[3] = f'Se muestran {max_rows} de {len(payload["rows"])} registros. Use Excel para el detalle completo.'
        rows.append(filler)
    return rows


def pdf_header_note(payload):
    return pdf_header_note_control(payload)
