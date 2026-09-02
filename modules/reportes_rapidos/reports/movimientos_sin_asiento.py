# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Movimientos sin asiento
# ============================================================

from __future__ import annotations

from datetime import date, timedelta

from modules.reportes_rapidos.core.config import MAX_ROWS_PDF, MAX_ROWS_SCREEN
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


REPORT_ID = 'movimientos_sin_asiento'
TITLE = 'Movimientos sin asiento'
DESCRIPTION = 'Control de operaciones financieras y documentos que requieren asiento confirmado.'
WORKSHEET_TITLE = 'Movimientos sin asiento'
FILE_SLUG = 'movimientos_sin_asiento'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-link-slash'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha de operacion'
FILTER_GROUP_LABEL = 'Situacion'
DEFAULT_ALCANCE = 'todos'
DEFAULT_GRUPO = ''
MONEY_FIELDS = {'monto'}

HELP_TITLE = 'Movimientos sin asiento'
HELP_INTRO = 'Controla operaciones confirmadas y documentos contabilizables sin asiento confirmado.'
HELP_ITEMS = [
    'Incluye pagos, cobros, movimientos de tesoreria, facturas electronicas y documentos por cobrar vigentes.',
    'Los documentos historicos por cobrar no se observan por no tener asiento inicial; solo se revisan al cobrarse.',
    'Los importes se totalizan por moneda.',
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
    '': 'Todos',
    'SIN_ASIENTO': 'Sin asiento',
    'ASIENTO_BORRADOR': 'Asiento en borrador',
    'DOCUMENTO_SIN_ASIENTO': 'Documento sin asiento',
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
        raise ValueError('La situacion seleccionada no es valida.')

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
        return 'Todos los movimientos pendientes de asiento'
    return descripcion_periodo(filtros)


def _map_row(row, idx):
    item = map_control_row(row, idx)
    item['bloque'] = row.get('bloque') or ''
    item['bloque_label'] = row.get('bloque_label') or row.get('bloque') or ''
    item['situacion'] = row.get('situacion') or ''
    return item


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    sql = """
        WITH operaciones AS (
            SELECT
                'TESORERIA'::text AS bloque,
                'Tesoreria'::text AS bloque_label,
                CASE WHEN a.id IS NULL THEN 'SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS situacion,
                p.fecha::date AS fecha,
                'Pago'::text AS origen,
                COALESCE(NULLIF(p.referencia::text, ''), 'Pago #' || p.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(p.cliente_nombre_ref::text, ''), 'Sin proveedor')::text AS cliente_proveedor,
                COALESCE(NULLIF(p.glosa::text, ''), 'Pago confirmado')::text AS detalle,
                CASE WHEN a.id IS NULL THEN 'Sin asiento' ELSE 'Asiento borrador' END::text AS estado,
                CASE WHEN a.id IS NULL THEN 'SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS estado_codigo,
                p.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(p.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(p.monto_total, 0)::numeric(18,2) AS monto,
                CASE WHEN a.id IS NULL THEN 'CRITICA' ELSE 'ALTA' END::text AS prioridad_codigo,
                CASE WHEN a.id IS NULL THEN 'Critica' ELSE 'Alta' END::text AS prioridad,
                CASE WHEN a.id IS NULL THEN 'Generar asiento' ELSE 'Confirmar asiento' END::text AS accion
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.documento_asiento da
                   ON da.tabla_origen IN ('pago', 'contabilidad.pago')
                  AND da.origen_id = p.id
            LEFT JOIN contabilidad.asiento a ON a.id = COALESCE(da.asiento_id, p.asiento_id)
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = p.proveedor_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE p.estado::text = 'CONFIRMADO'
              AND (a.id IS NULL OR a.estado::text = 'BORRADOR')

            UNION ALL

            SELECT
                'TESORERIA'::text AS bloque,
                'Tesoreria'::text AS bloque_label,
                CASE WHEN a.id IS NULL THEN 'SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS situacion,
                c.fecha::date AS fecha,
                'Cobro'::text AS origen,
                COALESCE(NULLIF(c.referencia::text, ''), 'Cobro #' || c.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(c.cliente_nombre_ref::text, ''), 'Sin cliente')::text AS cliente_proveedor,
                COALESCE(NULLIF(c.glosa::text, ''), 'Cobro confirmado')::text AS detalle,
                CASE WHEN a.id IS NULL THEN 'Sin asiento' ELSE 'Asiento borrador' END::text AS estado,
                CASE WHEN a.id IS NULL THEN 'SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS estado_codigo,
                c.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(c.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(c.monto_total, 0)::numeric(18,2) AS monto,
                CASE WHEN a.id IS NULL THEN 'CRITICA' ELSE 'ALTA' END::text AS prioridad_codigo,
                CASE WHEN a.id IS NULL THEN 'Critica' ELSE 'Alta' END::text AS prioridad,
                CASE WHEN a.id IS NULL THEN 'Generar asiento' ELSE 'Confirmar asiento' END::text AS accion
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.documento_asiento da
                   ON da.tabla_origen IN ('cobro', 'contabilidad.cobro')
                  AND da.origen_id = c.id
            LEFT JOIN contabilidad.asiento a ON a.id = COALESCE(da.asiento_id, c.asiento_id)
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = c.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE c.estado::text = 'CONFIRMADO'
              AND (a.id IS NULL OR a.estado::text = 'BORRADOR')

            UNION ALL

            SELECT
                'TESORERIA'::text AS bloque,
                'Tesoreria'::text AS bloque_label,
                CASE WHEN a.id IS NULL THEN 'SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS situacion,
                m.fecha::date AS fecha,
                'Movimiento tesoreria'::text AS origen,
                COALESCE(NULLIF(m.referencia::text, ''), 'Movimiento #' || m.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), 'Sin auxiliar')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ', NULLIF(m.tipo_movimiento::text, ''), NULLIF(m.glosa::text, '')))::text AS detalle,
                CASE WHEN a.id IS NULL THEN 'Sin asiento' ELSE 'Asiento borrador' END::text AS estado,
                CASE WHEN a.id IS NULL THEN 'SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS estado_codigo,
                m.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(m.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(m.monto, 0)::numeric(18,2) AS monto,
                CASE WHEN a.id IS NULL THEN 'CRITICA' ELSE 'ALTA' END::text AS prioridad_codigo,
                CASE WHEN a.id IS NULL THEN 'Critica' ELSE 'Alta' END::text AS prioridad,
                CASE WHEN a.id IS NULL THEN 'Generar asiento' ELSE 'Confirmar asiento' END::text AS accion
            FROM contabilidad.movimiento_tesoreria m
            LEFT JOIN contabilidad.documento_asiento da
                   ON da.tabla_origen IN ('movimiento_tesoreria', 'contabilidad.movimiento_tesoreria')
                  AND da.origen_id = m.id
            LEFT JOIN contabilidad.asiento a ON a.id = COALESCE(da.asiento_id, m.asiento_id)
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = m.auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
            WHERE m.estado::text = 'CONFIRMADO'
              AND (a.id IS NULL OR a.estado::text = 'BORRADOR')

            UNION ALL

            SELECT
                'FACTURACION'::text AS bloque,
                'Facturacion'::text AS bloque_label,
                CASE WHEN a.id IS NULL THEN 'DOCUMENTO_SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS situacion,
                f.fecha_emision::date AS fecha,
                'Factura electronica'::text AS origen,
                COALESCE(NULLIF(f.numero_factura::text, ''), 'Factura #' || f.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(f.nombre_cliente::text, ''), 'Sin cliente')::text AS cliente_proveedor,
                COALESCE(NULLIF(f.cuf::text, ''), 'Factura con cuenta por cobrar')::text AS detalle,
                CASE WHEN a.id IS NULL THEN 'Sin asiento' ELSE 'Asiento borrador' END::text AS estado,
                CASE WHEN a.id IS NULL THEN 'DOCUMENTO_SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS estado_codigo,
                f.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(f.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(f.importe_total, 0)::numeric(18,2) AS monto,
                CASE WHEN a.id IS NULL THEN 'CRITICA' ELSE 'ALTA' END::text AS prioridad_codigo,
                CASE WHEN a.id IS NULL THEN 'Critica' ELSE 'Alta' END::text AS prioridad,
                CASE WHEN a.id IS NULL THEN 'Contabilizar factura' ELSE 'Confirmar asiento' END::text AS accion
            FROM contabilidad.factura_electronica f
            LEFT JOIN contabilidad.documento_asiento da
                   ON da.tabla_origen = 'contabilidad.factura_electronica'
                  AND da.origen_id = f.id
            LEFT JOIN contabilidad.asiento a ON a.id = da.asiento_id
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = f.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = f.unidad_negocio_id
            WHERE UPPER(f.estado::text) NOT IN ('ANULADA', 'ANULADO')
              AND COALESCE(f.cuenta_cobrar_codigo::text, '') <> ''
              AND (a.id IS NULL OR a.estado::text = 'BORRADOR')

            UNION ALL

            SELECT
                'CARTERA'::text AS bloque,
                'Cartera'::text AS bloque_label,
                CASE WHEN a.id IS NULL THEN 'DOCUMENTO_SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS situacion,
                d.fecha_documento::date AS fecha,
                'Documento por cobrar'::text AS origen,
                COALESCE(NULLIF(d.numero_documento::text, ''), 'Documento #' || d.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(d.cliente_nombre::text, ''), 'Sin cliente')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ', NULLIF(d.tipo_documento::text, ''), NULLIF(d.descripcion::text, '')))::text AS detalle,
                CASE WHEN a.id IS NULL THEN 'Sin asiento' ELSE 'Asiento borrador' END::text AS estado,
                CASE WHEN a.id IS NULL THEN 'DOCUMENTO_SIN_ASIENTO' ELSE 'ASIENTO_BORRADOR' END::text AS estado_codigo,
                d.unidad_negocio_id,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(d.moneda_codigo::text, '') AS moneda_codigo,
                COALESCE(d.importe_total, 0)::numeric(18,2) AS monto,
                CASE WHEN a.id IS NULL THEN 'CRITICA' ELSE 'ALTA' END::text AS prioridad_codigo,
                CASE WHEN a.id IS NULL THEN 'Critica' ELSE 'Alta' END::text AS prioridad,
                CASE WHEN a.id IS NULL THEN 'Generar asiento inicial' ELSE 'Confirmar asiento' END::text AS accion
            FROM contabilidad.documento_por_cobrar d
            LEFT JOIN contabilidad.asiento a ON a.id = d.asiento_registro_id
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = d.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
            WHERE d.activo = TRUE
              AND d.estado::text <> 'ANULADO'
              AND d.origen_documento::text = 'VIGENTE_MANUAL'
              AND (a.id IS NULL OR a.estado::text = 'BORRADOR')
        )
        SELECT *
        FROM operaciones
        WHERE fecha BETWEEN %s AND %s
          AND (%s = '' OR situacion = %s)
          AND (%s IS NULL OR unidad_negocio_id = %s)
        ORDER BY
            CASE prioridad_codigo WHEN 'CRITICA' THEN 1 WHEN 'ALTA' THEN 2 WHEN 'MEDIA' THEN 3 ELSE 4 END,
            fecha DESC,
            bloque ASC,
            origen ASC,
            referencia ASC
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
        {'key': 'estado', 'label': 'Situacion', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
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
        'No hay movimientos sin asiento para los filtros seleccionados',
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
        ('detalle', 'Detalle', 46),
        ('estado', 'Situacion', 20),
        ('unidad', 'Unidad', 28),
        ('moneda_codigo', 'Moneda', 10),
        ('monto', 'Monto', 16),
        ('accion', 'Control', 30),
    ]


def excel_summary_text(summary):
    return excel_summary_text_control(summary)


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 22, 'align': 'center'},
        {'label': 'Fecha', 'width': 22, 'align': 'center'},
        {'label': 'Area', 'width': 28, 'align': 'left'},
        {'label': 'Origen', 'width': 38, 'align': 'left'},
        {'label': 'Referencia', 'width': 34, 'align': 'left'},
        {'label': 'Cliente / Proveedor', 'width': 54, 'align': 'left'},
        {'label': 'Situacion', 'width': 30, 'align': 'center'},
        {'label': 'Monto', 'width': 28, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item.get('prioridad', ''),
            item.get('fecha_label', ''),
            item.get('bloque_label', ''),
            item.get('origen', ''),
            item.get('referencia', ''),
            item.get('cliente_proveedor', ''),
            item.get('estado', ''),
            item.get('monto_label', ''),
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', '', '', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} registros. Use Excel para el detalle completo.', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    return pdf_header_note_control(payload)
