# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Datos incompletos
# ============================================================

from __future__ import annotations

from datetime import date
from decimal import Decimal

from modules.reportes_rapidos.core.config import MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.formatos import format_money as _format_money
from modules.reportes_rapidos.core.monedas import aplicar_contexto_monetario
from modules.reportes_rapidos.core.utils import clean as _clean
from modules.reportes_rapidos.core.utils import date_label as _date_label
from modules.reportes_rapidos.core.utils import decimal_value as _decimal
from modules.reportes_rapidos.core.utils import parse_optional_int as _parse_optional_int
from modules.reportes_rapidos.reports.control_operativo_common import (
    build_summary_control,
    execute_rows,
    excel_summary_text_control,
    map_control_row,
    pdf_header_note_control,
)


REPORT_ID = 'datos_incompletos'
TITLE = 'Datos incompletos'
DESCRIPTION = 'Control de registros financieros y contables con datos requeridos pendientes.'
WORKSHEET_TITLE = 'Datos incompletos'
FILE_SLUG = 'datos_incompletos'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-triangle-exclamation'

FILTER_ALCANCE_LABEL = 'Area'
FILTER_DATE_LABEL = 'Fecha de referencia'
FILTER_GROUP_LABEL = 'Tipo de dato'
DEFAULT_ALCANCE = 'todos'
DEFAULT_GRUPO = ''
FILTER_UNIDAD_VISIBLE = True
HIDE_FECHA_BASE_FILTER = True
HIDE_HOY_BUTTON = True
MONEY_FIELDS = {'monto'}

HELP_TITLE = 'Datos incompletos'
HELP_INTRO = 'Controla datos requeridos para evitar saldos, reportes o asientos incompletos.'
HELP_ITEMS = [
    'Incluye maestros contables, cartera por cobrar, facturas, tesoreria y comprobantes.',
    'No incluye controles de publicidad ni documentos comerciales externos al nucleo financiero.',
    'Los documentos historicos por cobrar no se observan por no tener asiento inicial; si se observan cuando tienen datos operativos incompletos.',
    'Los importes se totalizan por moneda solo como referencia del registro observado.',
]

ALCANCES = {
    'todos': 'Todas',
    'maestros': 'Maestros',
    'cartera': 'Cartera',
    'facturacion': 'Facturacion',
    'tesoreria': 'Tesoreria',
    'contabilidad': 'Contabilidad',
}

GRUPOS = {
    '': 'Todos',
    'BASICO': 'Datos basicos',
    'RELACION': 'Relacion',
    'CONTABLE': 'Contable',
    'MONTO': 'Importe',
    'FECHA': 'Fecha',
    'TESORERIA': 'Caja/Banco',
}

PRIORIDAD_ORDEN = {
    'CRITICA': 1,
    'ALTA': 2,
    'MEDIA': 3,
    'BAJA': 4,
}

AREA_LABELS = {
    'maestros': 'Maestros',
    'cartera': 'Cartera',
    'facturacion': 'Facturacion',
    'tesoreria': 'Tesoreria',
    'contabilidad': 'Contabilidad',
}


# ============================================================
# Filtros
# ============================================================

def validate_filters(args):
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El area seleccionada no es valida.')

    grupo = _clean(args.get('grupo'))
    if grupo == '' and DEFAULT_GRUPO is not None:
        grupo = DEFAULT_GRUPO
    if grupo not in GRUPOS:
        raise ValueError('El tipo de dato seleccionado no es valido.')

    hoy = date.today()
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')
    return {
        'alcance': alcance,
        'alcance_label': ALCANCES[alcance],
        'grupo': grupo,
        'grupo_label': GRUPOS[grupo],
        'fecha_base': hoy,
        'fecha_desde': hoy,
        'fecha_hasta': hoy,
        'unidad_negocio_id': unidad_negocio_id,
    }


def _descripcion(filtros):
    return f"Area: {filtros['alcance_label']} · Tipo: {filtros['grupo_label']}"


# ============================================================
# Datos
# ============================================================

def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    sql = """
        WITH pendientes AS (
            SELECT
                'maestros'::text AS area,
                'Maestros'::text AS area_label,
                'BASICO'::text AS grupo,
                NULL::bigint AS unidad_negocio_id,
                CURRENT_DATE::date AS fecha,
                CASE WHEN a.tipo::text = 'CLIENTE' THEN 'Cliente contable' ELSE 'Proveedor contable' END::text AS origen,
                COALESCE(a.codigo_externo, a.id::text)::text AS referencia,
                COALESCE(NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), 'Sin nombre')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                    CASE WHEN COALESCE(NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), '') = '' THEN 'Sin nombre' END,
                    CASE WHEN COALESCE(NULLIF(a.nit_ci, ''), '') = '' THEN 'Sin NIT/CI' END,
                    CASE WHEN COALESCE(NULLIF(a.telefono, ''), '') = '' THEN 'Sin telefono' END,
                    CASE WHEN COALESCE(NULLIF(a.email, ''), '') = '' THEN 'Sin email' END,
                    CASE WHEN COALESCE(NULLIF(a.direccion, ''), '') = '' THEN 'Sin direccion' END
                ))::text AS detalle,
                CASE WHEN a.activo THEN 'ACTIVO' ELSE 'INACTIVO' END::text AS estado,
                CASE WHEN a.activo THEN 'ACTIVO' ELSE 'INACTIVO' END::text AS estado_codigo,
                ''::text AS unidad,
                ''::text AS moneda_codigo,
                0::numeric(18,2) AS monto,
                CASE
                    WHEN COALESCE(NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), '') = '' THEN 'CRITICA'
                    WHEN COALESCE(NULLIF(a.nit_ci, ''), '') = '' THEN 'ALTA'
                    ELSE 'MEDIA'
                END::text AS prioridad_codigo,
                CASE
                    WHEN COALESCE(NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), '') = '' THEN 'Critica'
                    WHEN COALESCE(NULLIF(a.nit_ci, ''), '') = '' THEN 'Alta'
                    ELSE 'Media'
                END::text AS prioridad,
                'Completar auxiliar'::text AS accion
            FROM contabilidad.auxiliar a
            WHERE a.activo = TRUE
              AND a.tipo::text IN ('CLIENTE', 'PROVEEDOR')
              AND (
                    COALESCE(NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), '') = ''
                 OR COALESCE(NULLIF(a.nit_ci, ''), '') = ''
                 OR COALESCE(NULLIF(a.telefono, ''), '') = ''
                 OR COALESCE(NULLIF(a.email, ''), '') = ''
                 OR COALESCE(NULLIF(a.direccion, ''), '') = ''
              )

            UNION ALL

            SELECT
                'cartera'::text AS area,
                'Cartera'::text AS area_label,
                CASE
                    WHEN d.unidad_negocio_id IS NULL
                      OR (d.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(d.cliente_nombre, ''), '') = '')
                      THEN 'RELACION'
                    WHEN COALESCE(d.cuenta_cartera_codigo, '') = ''
                      OR (d.origen_documento::text = 'VIGENTE_MANUAL' AND COALESCE(d.cuenta_contrapartida_codigo, '') = '')
                      THEN 'CONTABLE'
                    WHEN COALESCE(d.importe_total, 0) <= 0
                      OR COALESCE(d.saldo_pendiente, 0) < 0
                      OR COALESCE(d.importe_cobrado, 0) > COALESCE(d.importe_total, 0)
                      THEN 'MONTO'
                    WHEN d.fecha_documento IS NULL THEN 'FECHA'
                    ELSE 'BASICO'
                END::text AS grupo,
                d.unidad_negocio_id,
                COALESCE(d.fecha_documento, d.creado_en::date, CURRENT_DATE)::date AS fecha,
                CASE
                    WHEN d.origen_documento::text = 'HISTORICO' THEN 'Documento historico por cobrar'
                    WHEN d.origen_documento::text = 'VIGENTE_MANUAL' THEN 'Documento vigente por cobrar'
                    ELSE 'Documento por cobrar'
                END::text AS origen,
                (COALESCE(d.tipo_documento::text, 'DOCUMENTO') || ' ' || COALESCE(NULLIF(d.numero_documento::text, ''), d.id::text))::text AS referencia,
                COALESCE(NULLIF(d.cliente_nombre, ''), NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), 'Sin cliente')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                    CASE WHEN d.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                    CASE WHEN d.fecha_documento IS NULL THEN 'Sin fecha de documento' END,
                    CASE WHEN COALESCE(NULLIF(d.tipo_documento::text, ''), '') = '' THEN 'Sin tipo' END,
                    CASE WHEN COALESCE(NULLIF(d.numero_documento::text, ''), '') = '' THEN 'Sin numero' END,
                    CASE WHEN d.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(d.cliente_nombre, ''), '') = '' THEN 'Sin cliente' END,
                    CASE WHEN COALESCE(NULLIF(d.moneda_codigo::text, ''), '') = '' THEN 'Sin moneda' END,
                    CASE WHEN COALESCE(d.importe_total, 0) <= 0 THEN 'Importe no valido' END,
                    CASE WHEN COALESCE(d.saldo_pendiente, 0) < 0 THEN 'Saldo negativo' END,
                    CASE WHEN COALESCE(d.importe_cobrado, 0) > COALESCE(d.importe_total, 0) THEN 'Cobrado excede total' END,
                    CASE WHEN COALESCE(d.cuenta_cartera_codigo, '') = '' THEN 'Sin cuenta cartera' END,
                    CASE WHEN d.origen_documento::text = 'VIGENTE_MANUAL' AND COALESCE(d.cuenta_contrapartida_codigo, '') = '' THEN 'Sin contrapartida' END
                ))::text AS detalle,
                d.estado::text AS estado,
                d.estado::text AS estado_codigo,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(d.moneda_codigo::text, '') AS moneda_codigo,
                GREATEST(COALESCE(d.saldo_pendiente, 0), COALESCE(d.importe_total, 0), 0)::numeric(18,2) AS monto,
                CASE
                    WHEN d.unidad_negocio_id IS NULL
                      OR (d.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(d.cliente_nombre, ''), '') = '')
                      OR COALESCE(d.importe_total, 0) <= 0
                      OR COALESCE(d.saldo_pendiente, 0) < 0
                      OR COALESCE(d.importe_cobrado, 0) > COALESCE(d.importe_total, 0)
                      THEN 'CRITICA'
                    WHEN COALESCE(d.cuenta_cartera_codigo, '') = ''
                      OR (d.origen_documento::text = 'VIGENTE_MANUAL' AND COALESCE(d.cuenta_contrapartida_codigo, '') = '')
                      OR COALESCE(NULLIF(d.moneda_codigo::text, ''), '') = ''
                      THEN 'ALTA'
                    ELSE 'MEDIA'
                END::text AS prioridad_codigo,
                CASE
                    WHEN d.unidad_negocio_id IS NULL
                      OR (d.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(d.cliente_nombre, ''), '') = '')
                      OR COALESCE(d.importe_total, 0) <= 0
                      OR COALESCE(d.saldo_pendiente, 0) < 0
                      OR COALESCE(d.importe_cobrado, 0) > COALESCE(d.importe_total, 0)
                      THEN 'Critica'
                    WHEN COALESCE(d.cuenta_cartera_codigo, '') = ''
                      OR (d.origen_documento::text = 'VIGENTE_MANUAL' AND COALESCE(d.cuenta_contrapartida_codigo, '') = '')
                      OR COALESCE(NULLIF(d.moneda_codigo::text, ''), '') = ''
                      THEN 'Alta'
                    ELSE 'Media'
                END::text AS prioridad,
                'Corregir documento'::text AS accion
            FROM contabilidad.documento_por_cobrar d
            LEFT JOIN contabilidad.auxiliar a ON a.id = d.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
            WHERE d.activo = TRUE
              AND COALESCE(d.estado::text, '') <> 'ANULADO'
              AND (
                    d.unidad_negocio_id IS NULL
                 OR d.fecha_documento IS NULL
                 OR COALESCE(NULLIF(d.tipo_documento::text, ''), '') = ''
                 OR COALESCE(NULLIF(d.numero_documento::text, ''), '') = ''
                 OR (d.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(d.cliente_nombre, ''), '') = '')
                 OR COALESCE(NULLIF(d.moneda_codigo::text, ''), '') = ''
                 OR COALESCE(d.importe_total, 0) <= 0
                 OR COALESCE(d.saldo_pendiente, 0) < 0
                 OR COALESCE(d.importe_cobrado, 0) > COALESCE(d.importe_total, 0)
                 OR COALESCE(d.cuenta_cartera_codigo, '') = ''
                 OR (d.origen_documento::text = 'VIGENTE_MANUAL' AND COALESCE(d.cuenta_contrapartida_codigo, '') = '')
              )

            UNION ALL

            SELECT
                'facturacion'::text AS area,
                'Facturacion'::text AS area_label,
                CASE
                    WHEN fe.unidad_negocio_id IS NULL
                      OR (fe.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(fe.nombre_cliente, ''), '') = '')
                      THEN 'RELACION'
                    WHEN COALESCE(fe.cuenta_cobrar_codigo, '') = '' THEN 'CONTABLE'
                    WHEN COALESCE(fe.importe_total, 0) <= 0 THEN 'MONTO'
                    WHEN fe.fecha_emision IS NULL THEN 'FECHA'
                    ELSE 'BASICO'
                END::text AS grupo,
                fe.unidad_negocio_id,
                COALESCE(fe.fecha_emision, fe.creado_en::date, CURRENT_DATE)::date AS fecha,
                'Factura electronica'::text AS origen,
                ('FACTURA ' || COALESCE(NULLIF(fe.numero_factura::text, ''), fe.id::text))::text AS referencia,
                COALESCE(NULLIF(fe.nombre_cliente, ''), NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), 'Sin cliente')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                    CASE WHEN fe.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                    CASE WHEN fe.fecha_emision IS NULL THEN 'Sin fecha de emision' END,
                    CASE WHEN COALESCE(NULLIF(fe.numero_factura::text, ''), '') = '' THEN 'Sin numero' END,
                    CASE WHEN fe.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(fe.nombre_cliente, ''), '') = '' THEN 'Sin cliente' END,
                    CASE WHEN COALESCE(NULLIF(fe.moneda_codigo::text, ''), '') = '' THEN 'Sin moneda' END,
                    CASE WHEN COALESCE(fe.importe_total, 0) <= 0 THEN 'Importe no valido' END,
                    CASE WHEN COALESCE(fe.cuenta_cobrar_codigo, '') = '' THEN 'Sin cuenta por cobrar' END
                ))::text AS detalle,
                fe.estado::text AS estado,
                fe.estado::text AS estado_codigo,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(fe.moneda_codigo::text, '') AS moneda_codigo,
                GREATEST(COALESCE(fe.importe_total, 0), 0)::numeric(18,2) AS monto,
                CASE
                    WHEN fe.unidad_negocio_id IS NULL
                      OR (fe.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(fe.nombre_cliente, ''), '') = '')
                      OR COALESCE(fe.importe_total, 0) <= 0
                      THEN 'CRITICA'
                    WHEN COALESCE(fe.cuenta_cobrar_codigo, '') = ''
                      OR COALESCE(NULLIF(fe.moneda_codigo::text, ''), '') = ''
                      THEN 'ALTA'
                    ELSE 'MEDIA'
                END::text AS prioridad_codigo,
                CASE
                    WHEN fe.unidad_negocio_id IS NULL
                      OR (fe.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(fe.nombre_cliente, ''), '') = '')
                      OR COALESCE(fe.importe_total, 0) <= 0
                      THEN 'Critica'
                    WHEN COALESCE(fe.cuenta_cobrar_codigo, '') = ''
                      OR COALESCE(NULLIF(fe.moneda_codigo::text, ''), '') = ''
                      THEN 'Alta'
                    ELSE 'Media'
                END::text AS prioridad,
                'Corregir factura'::text AS accion
            FROM contabilidad.factura_electronica fe
            LEFT JOIN contabilidad.auxiliar a ON a.id = fe.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
            WHERE COALESCE(fe.estado::text, '') <> 'ANULADA'
              AND (
                    fe.unidad_negocio_id IS NULL
                 OR fe.fecha_emision IS NULL
                 OR COALESCE(NULLIF(fe.numero_factura::text, ''), '') = ''
                 OR (fe.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(fe.nombre_cliente, ''), '') = '')
                 OR COALESCE(NULLIF(fe.moneda_codigo::text, ''), '') = ''
                 OR COALESCE(fe.importe_total, 0) <= 0
                 OR COALESCE(fe.cuenta_cobrar_codigo, '') = ''
              )

            UNION ALL

            SELECT
                'tesoreria'::text AS area,
                'Tesoreria'::text AS area_label,
                CASE
                    WHEN c.unidad_negocio_id IS NULL
                      OR (c.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(c.cliente_nombre_ref, ''), '') = '')
                      THEN 'RELACION'
                    WHEN COALESCE(NULLIF(c.medio_pago::text, ''), '') = ''
                      OR (c.medio_pago::text = 'CAJA' AND c.caja_id IS NULL)
                      OR (c.medio_pago::text = 'BANCO' AND c.cuenta_bancaria_id IS NULL)
                      THEN 'TESORERIA'
                    WHEN COALESCE(c.monto_total, 0) <= 0 THEN 'MONTO'
                    WHEN c.fecha IS NULL THEN 'FECHA'
                    ELSE 'BASICO'
                END::text AS grupo,
                c.unidad_negocio_id,
                COALESCE(c.fecha, c.creado_en::date, CURRENT_DATE)::date AS fecha,
                'Cobro'::text AS origen,
                COALESCE(NULLIF(c.referencia::text, ''), 'Cobro #' || c.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(c.cliente_nombre_ref::text, ''), 'Sin cliente')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                    CASE WHEN c.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                    CASE WHEN c.fecha IS NULL THEN 'Sin fecha' END,
                    CASE WHEN c.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(c.cliente_nombre_ref, ''), '') = '' THEN 'Sin cliente' END,
                    CASE WHEN COALESCE(NULLIF(c.moneda_codigo::text, ''), '') = '' THEN 'Sin moneda' END,
                    CASE WHEN COALESCE(c.monto_total, 0) <= 0 THEN 'Monto no valido' END,
                    CASE WHEN COALESCE(NULLIF(c.medio_pago::text, ''), '') = '' THEN 'Sin medio de pago' END,
                    CASE WHEN c.medio_pago::text = 'CAJA' AND c.caja_id IS NULL THEN 'Sin caja' END,
                    CASE WHEN c.medio_pago::text = 'BANCO' AND c.cuenta_bancaria_id IS NULL THEN 'Sin cuenta bancaria' END
                ))::text AS detalle,
                c.estado::text AS estado,
                c.estado::text AS estado_codigo,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(c.moneda_codigo::text, '') AS moneda_codigo,
                GREATEST(COALESCE(c.monto_total, 0), 0)::numeric(18,2) AS monto,
                CASE
                    WHEN c.unidad_negocio_id IS NULL
                      OR COALESCE(c.monto_total, 0) <= 0
                      OR COALESCE(NULLIF(c.medio_pago::text, ''), '') = ''
                      OR (c.medio_pago::text = 'CAJA' AND c.caja_id IS NULL)
                      OR (c.medio_pago::text = 'BANCO' AND c.cuenta_bancaria_id IS NULL)
                      THEN 'CRITICA'
                    ELSE 'ALTA'
                END::text AS prioridad_codigo,
                CASE
                    WHEN c.unidad_negocio_id IS NULL
                      OR COALESCE(c.monto_total, 0) <= 0
                      OR COALESCE(NULLIF(c.medio_pago::text, ''), '') = ''
                      OR (c.medio_pago::text = 'CAJA' AND c.caja_id IS NULL)
                      OR (c.medio_pago::text = 'BANCO' AND c.cuenta_bancaria_id IS NULL)
                      THEN 'Critica'
                    ELSE 'Alta'
                END::text AS prioridad,
                'Corregir cobro'::text AS accion
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = c.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE COALESCE(c.estado::text, '') <> 'ANULADO'
              AND (
                    c.unidad_negocio_id IS NULL
                 OR c.fecha IS NULL
                 OR (c.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(c.cliente_nombre_ref, ''), '') = '')
                 OR COALESCE(NULLIF(c.moneda_codigo::text, ''), '') = ''
                 OR COALESCE(c.monto_total, 0) <= 0
                 OR COALESCE(NULLIF(c.medio_pago::text, ''), '') = ''
                 OR (c.medio_pago::text = 'CAJA' AND c.caja_id IS NULL)
                 OR (c.medio_pago::text = 'BANCO' AND c.cuenta_bancaria_id IS NULL)
              )

            UNION ALL

            SELECT
                'tesoreria'::text AS area,
                'Tesoreria'::text AS area_label,
                CASE
                    WHEN p.unidad_negocio_id IS NULL
                      OR (p.proveedor_auxiliar_id IS NULL AND COALESCE(NULLIF(p.cliente_nombre_ref, ''), '') = '')
                      THEN 'RELACION'
                    WHEN COALESCE(NULLIF(p.medio_pago::text, ''), '') = ''
                      OR (p.medio_pago::text = 'CAJA' AND p.caja_id IS NULL)
                      OR (p.medio_pago::text = 'BANCO' AND p.cuenta_bancaria_id IS NULL)
                      THEN 'TESORERIA'
                    WHEN COALESCE(p.monto_total, 0) <= 0 THEN 'MONTO'
                    WHEN p.fecha IS NULL THEN 'FECHA'
                    ELSE 'BASICO'
                END::text AS grupo,
                p.unidad_negocio_id,
                COALESCE(p.fecha, p.creado_en::date, CURRENT_DATE)::date AS fecha,
                'Pago'::text AS origen,
                COALESCE(NULLIF(p.referencia::text, ''), 'Pago #' || p.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), NULLIF(p.cliente_nombre_ref::text, ''), 'Sin proveedor')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                    CASE WHEN p.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                    CASE WHEN p.fecha IS NULL THEN 'Sin fecha' END,
                    CASE WHEN p.proveedor_auxiliar_id IS NULL AND COALESCE(NULLIF(p.cliente_nombre_ref, ''), '') = '' THEN 'Sin proveedor' END,
                    CASE WHEN COALESCE(NULLIF(p.moneda_codigo::text, ''), '') = '' THEN 'Sin moneda' END,
                    CASE WHEN COALESCE(p.monto_total, 0) <= 0 THEN 'Monto no valido' END,
                    CASE WHEN COALESCE(NULLIF(p.medio_pago::text, ''), '') = '' THEN 'Sin medio de pago' END,
                    CASE WHEN p.medio_pago::text = 'CAJA' AND p.caja_id IS NULL THEN 'Sin caja' END,
                    CASE WHEN p.medio_pago::text = 'BANCO' AND p.cuenta_bancaria_id IS NULL THEN 'Sin cuenta bancaria' END
                ))::text AS detalle,
                p.estado::text AS estado,
                p.estado::text AS estado_codigo,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(p.moneda_codigo::text, '') AS moneda_codigo,
                GREATEST(COALESCE(p.monto_total, 0), 0)::numeric(18,2) AS monto,
                CASE
                    WHEN p.unidad_negocio_id IS NULL
                      OR COALESCE(p.monto_total, 0) <= 0
                      OR COALESCE(NULLIF(p.medio_pago::text, ''), '') = ''
                      OR (p.medio_pago::text = 'CAJA' AND p.caja_id IS NULL)
                      OR (p.medio_pago::text = 'BANCO' AND p.cuenta_bancaria_id IS NULL)
                      THEN 'CRITICA'
                    ELSE 'ALTA'
                END::text AS prioridad_codigo,
                CASE
                    WHEN p.unidad_negocio_id IS NULL
                      OR COALESCE(p.monto_total, 0) <= 0
                      OR COALESCE(NULLIF(p.medio_pago::text, ''), '') = ''
                      OR (p.medio_pago::text = 'CAJA' AND p.caja_id IS NULL)
                      OR (p.medio_pago::text = 'BANCO' AND p.cuenta_bancaria_id IS NULL)
                      THEN 'Critica'
                    ELSE 'Alta'
                END::text AS prioridad,
                'Corregir pago'::text AS accion
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = p.proveedor_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE COALESCE(p.estado::text, '') <> 'ANULADO'
              AND (
                    p.unidad_negocio_id IS NULL
                 OR p.fecha IS NULL
                 OR (p.proveedor_auxiliar_id IS NULL AND COALESCE(NULLIF(p.cliente_nombre_ref, ''), '') = '')
                 OR COALESCE(NULLIF(p.moneda_codigo::text, ''), '') = ''
                 OR COALESCE(p.monto_total, 0) <= 0
                 OR COALESCE(NULLIF(p.medio_pago::text, ''), '') = ''
                 OR (p.medio_pago::text = 'CAJA' AND p.caja_id IS NULL)
                 OR (p.medio_pago::text = 'BANCO' AND p.cuenta_bancaria_id IS NULL)
              )

            UNION ALL

            SELECT
                'tesoreria'::text AS area,
                'Tesoreria'::text AS area_label,
                CASE
                    WHEN m.unidad_negocio_id IS NULL THEN 'RELACION'
                    WHEN COALESCE(NULLIF(m.medio_origen::text, ''), '') = '' AND COALESCE(NULLIF(m.medio_destino::text, ''), '') = '' THEN 'TESORERIA'
                    WHEN COALESCE(m.monto, 0) <= 0 THEN 'MONTO'
                    WHEN m.fecha IS NULL THEN 'FECHA'
                    WHEN COALESCE(m.contra_cuenta_codigo, '') = '' AND m.tipo_movimiento::text IN ('INGRESO', 'EGRESO') THEN 'CONTABLE'
                    ELSE 'BASICO'
                END::text AS grupo,
                m.unidad_negocio_id,
                COALESCE(m.fecha, m.creado_en::date, CURRENT_DATE)::date AS fecha,
                'Movimiento tesoreria'::text AS origen,
                COALESCE(NULLIF(m.referencia::text, ''), 'Movimiento #' || m.id::text)::text AS referencia,
                COALESCE(NULLIF(ax.nombre::text, ''), NULLIF(ax.razon_social::text, ''), 'Sin auxiliar')::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                    CASE WHEN m.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                    CASE WHEN m.fecha IS NULL THEN 'Sin fecha' END,
                    CASE WHEN COALESCE(NULLIF(m.tipo_movimiento::text, ''), '') = '' THEN 'Sin tipo' END,
                    CASE WHEN COALESCE(NULLIF(m.moneda_codigo::text, ''), '') = '' THEN 'Sin moneda' END,
                    CASE WHEN COALESCE(m.monto, 0) <= 0 THEN 'Monto no valido' END,
                    CASE WHEN m.tipo_movimiento::text IN ('EGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_origen::text, ''), '') = '' THEN 'Sin medio origen' END,
                    CASE WHEN m.tipo_movimiento::text IN ('INGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_destino::text, ''), '') = '' THEN 'Sin medio destino' END,
                    CASE WHEN m.medio_origen::text = 'CAJA' AND m.caja_origen_id IS NULL THEN 'Sin caja origen' END,
                    CASE WHEN m.medio_origen::text = 'BANCO' AND m.banco_origen_id IS NULL THEN 'Sin banco origen' END,
                    CASE WHEN m.medio_destino::text = 'CAJA' AND m.caja_destino_id IS NULL THEN 'Sin caja destino' END,
                    CASE WHEN m.medio_destino::text = 'BANCO' AND m.banco_destino_id IS NULL THEN 'Sin banco destino' END,
                    CASE WHEN m.tipo_movimiento::text IN ('INGRESO', 'EGRESO') AND COALESCE(m.contra_cuenta_codigo, '') = '' THEN 'Sin contra cuenta' END,
                    CASE WHEN COALESCE(NULLIF(m.glosa::text, ''), '') = '' THEN 'Sin glosa' END
                ))::text AS detalle,
                m.estado::text AS estado,
                m.estado::text AS estado_codigo,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(m.moneda_codigo::text, '') AS moneda_codigo,
                GREATEST(COALESCE(m.monto, 0), 0)::numeric(18,2) AS monto,
                CASE
                    WHEN m.unidad_negocio_id IS NULL
                      OR COALESCE(m.monto, 0) <= 0
                      OR (m.tipo_movimiento::text IN ('EGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_origen::text, ''), '') = '')
                      OR (m.tipo_movimiento::text IN ('INGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_destino::text, ''), '') = '')
                      THEN 'CRITICA'
                    ELSE 'ALTA'
                END::text AS prioridad_codigo,
                CASE
                    WHEN m.unidad_negocio_id IS NULL
                      OR COALESCE(m.monto, 0) <= 0
                      OR (m.tipo_movimiento::text IN ('EGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_origen::text, ''), '') = '')
                      OR (m.tipo_movimiento::text IN ('INGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_destino::text, ''), '') = '')
                      THEN 'Critica'
                    ELSE 'Alta'
                END::text AS prioridad,
                'Corregir movimiento'::text AS accion
            FROM contabilidad.movimiento_tesoreria m
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = m.auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
            WHERE COALESCE(m.estado::text, '') <> 'ANULADO'
              AND (
                    m.unidad_negocio_id IS NULL
                 OR m.fecha IS NULL
                 OR COALESCE(NULLIF(m.tipo_movimiento::text, ''), '') = ''
                 OR COALESCE(NULLIF(m.moneda_codigo::text, ''), '') = ''
                 OR COALESCE(m.monto, 0) <= 0
                 OR (m.tipo_movimiento::text IN ('EGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_origen::text, ''), '') = '')
                 OR (m.tipo_movimiento::text IN ('INGRESO', 'TRANSFERENCIA') AND COALESCE(NULLIF(m.medio_destino::text, ''), '') = '')
                 OR (m.medio_origen::text = 'CAJA' AND m.caja_origen_id IS NULL)
                 OR (m.medio_origen::text = 'BANCO' AND m.banco_origen_id IS NULL)
                 OR (m.medio_destino::text = 'CAJA' AND m.caja_destino_id IS NULL)
                 OR (m.medio_destino::text = 'BANCO' AND m.banco_destino_id IS NULL)
                 OR (m.tipo_movimiento::text IN ('INGRESO', 'EGRESO') AND COALESCE(m.contra_cuenta_codigo, '') = '')
                 OR COALESCE(NULLIF(m.glosa::text, ''), '') = ''
              )

            UNION ALL

            SELECT
                'contabilidad'::text AS area,
                'Contabilidad'::text AS area_label,
                CASE
                    WHEN a.unidad_negocio_id IS NULL THEN 'RELACION'
                    WHEN COALESCE(NULLIF(a.moneda_codigo::text, ''), '') = '' THEN 'BASICO'
                    WHEN a.fecha IS NULL THEN 'FECHA'
                    WHEN COALESCE(res.lineas, 0) = 0 THEN 'CONTABLE'
                    WHEN COALESCE(res.total_debe, 0) <= 0 OR COALESCE(res.total_haber, 0) <= 0 THEN 'MONTO'
                    WHEN ABS(COALESCE(res.total_debe, 0) - COALESCE(res.total_haber, 0)) > 0.01 THEN 'CONTABLE'
                    ELSE 'BASICO'
                END::text AS grupo,
                a.unidad_negocio_id,
                COALESCE(a.fecha, a.creado_en::date, CURRENT_DATE)::date AS fecha,
                'Comprobante contable'::text AS origen,
                COALESCE(NULLIF(a.referencia::text, ''), 'Asiento #' || a.id::text)::text AS referencia,
                'Contabilidad'::text AS cliente_proveedor,
                TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                    CASE WHEN a.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                    CASE WHEN a.fecha IS NULL THEN 'Sin fecha' END,
                    CASE WHEN COALESCE(NULLIF(a.moneda_codigo::text, ''), '') = '' THEN 'Sin moneda' END,
                    CASE WHEN COALESCE(NULLIF(a.glosa::text, ''), '') = '' THEN 'Sin glosa' END,
                    CASE WHEN COALESCE(res.lineas, 0) = 0 THEN 'Sin detalle' END,
                    CASE WHEN COALESCE(res.total_debe, 0) <= 0 THEN 'Debe en cero' END,
                    CASE WHEN COALESCE(res.total_haber, 0) <= 0 THEN 'Haber en cero' END,
                    CASE WHEN ABS(COALESCE(res.total_debe, 0) - COALESCE(res.total_haber, 0)) > 0.01 THEN 'No cuadra' END
                ))::text AS detalle,
                a.estado::text AS estado,
                a.estado::text AS estado_codigo,
                COALESCE(NULLIF(un.codigo || ' · ' || un.nombre, ' · '), un.nombre, 'Sin unidad')::text AS unidad,
                COALESCE(a.moneda_codigo::text, '') AS moneda_codigo,
                GREATEST(COALESCE(res.total_debe, 0), COALESCE(res.total_haber, 0), 0)::numeric(18,2) AS monto,
                CASE
                    WHEN a.unidad_negocio_id IS NULL
                      OR COALESCE(res.lineas, 0) = 0
                      OR COALESCE(res.total_debe, 0) <= 0
                      OR COALESCE(res.total_haber, 0) <= 0
                      OR ABS(COALESCE(res.total_debe, 0) - COALESCE(res.total_haber, 0)) > 0.01
                      THEN 'CRITICA'
                    ELSE 'ALTA'
                END::text AS prioridad_codigo,
                CASE
                    WHEN a.unidad_negocio_id IS NULL
                      OR COALESCE(res.lineas, 0) = 0
                      OR COALESCE(res.total_debe, 0) <= 0
                      OR COALESCE(res.total_haber, 0) <= 0
                      OR ABS(COALESCE(res.total_debe, 0) - COALESCE(res.total_haber, 0)) > 0.01
                      THEN 'Critica'
                    ELSE 'Alta'
                END::text AS prioridad,
                'Corregir comprobante'::text AS accion
            FROM contabilidad.asiento a
            LEFT JOIN (
                SELECT asiento_id,
                       COUNT(*) AS lineas,
                       COALESCE(SUM(debe), 0)::numeric(18,2) AS total_debe,
                       COALESCE(SUM(haber), 0)::numeric(18,2) AS total_haber
                FROM contabilidad.asiento_detalle
                GROUP BY asiento_id
            ) res ON res.asiento_id = a.id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
            WHERE COALESCE(a.estado::text, '') <> 'ANULADO'
              AND (
                    a.unidad_negocio_id IS NULL
                 OR a.fecha IS NULL
                 OR COALESCE(NULLIF(a.moneda_codigo::text, ''), '') = ''
                 OR COALESCE(NULLIF(a.glosa::text, ''), '') = ''
                 OR COALESCE(res.lineas, 0) = 0
                 OR COALESCE(res.total_debe, 0) <= 0
                 OR COALESCE(res.total_haber, 0) <= 0
                 OR ABS(COALESCE(res.total_debe, 0) - COALESCE(res.total_haber, 0)) > 0.01
              )
        )
        SELECT *
        FROM pendientes
        WHERE (%s = 'todos' OR area = %s)
          AND (%s = '' OR grupo = %s)
          AND (%s IS NULL OR unidad_negocio_id = %s)
        ORDER BY
            CASE prioridad_codigo WHEN 'CRITICA' THEN 1 WHEN 'ALTA' THEN 2 WHEN 'MEDIA' THEN 3 ELSE 4 END,
            area ASC,
            origen ASC,
            fecha ASC,
            referencia ASC
        LIMIT %s
    """
    params = (
        filtros['alcance'], filtros['alcance'],
        filtros['grupo'], filtros['grupo'],
        filtros['unidad_negocio_id'], filtros['unidad_negocio_id'],
        int(limit_rows),
    )
    rows = execute_rows(sql, params)
    return [_map_row(row, idx) for idx, row in enumerate(rows, start=1)]


def _map_row(row, idx):
    item = map_control_row(row, idx)
    item['area'] = row.get('area') or ''
    item['area_label'] = row.get('area_label') or AREA_LABELS.get(item['area'], item['area'])
    item['grupo'] = row.get('grupo') or ''
    item['grupo_label'] = GRUPOS.get(item['grupo'], item['grupo'])
    item['prioridad_orden'] = PRIORIDAD_ORDEN.get(item.get('prioridad_codigo'), 9)
    return item


# ============================================================
# Payload y columnas
# ============================================================

def display_columns():
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'area_label', 'label': 'Area', 'align': 'left'},
        {'key': 'origen', 'label': 'Origen', 'align': 'left'},
        {'key': 'referencia', 'label': 'Referencia', 'align': 'left'},
        {'key': 'cliente_proveedor', 'label': 'Cliente / Proveedor', 'align': 'left', 'strong': True},
        {'key': 'detalle', 'label': 'Detalle', 'align': 'left'},
        {'key': 'unidad', 'label': 'Unidad', 'align': 'left'},
        {'key': 'monto', 'label': 'Monto', 'type': 'money', 'align': 'right'},
        {'key': 'accion', 'label': 'Accion', 'align': 'left'},
    ]


def _summary_cards(summary):
    return [
        {'label': 'Registros', 'value': summary.get('cantidad', 0), 'note': 'Observaciones', 'kind': 'group'},
        {'label': 'Criticas', 'value': summary.get('criticas', 0), 'note': 'Corregir primero', 'kind': 'critical'},
        {'label': 'Altas', 'value': summary.get('altas', 0), 'note': 'Prioritarias', 'kind': 'high'},
        {'label': 'Medias', 'value': summary.get('medias', 0), 'note': 'Revision', 'kind': 'group'},
        {'label': 'Importe', 'value': summary.get('total_general_label'), 'note': 'Referencia por moneda', 'kind': 'total'},
    ]


def build_payload(filtros, limit_rows=MAX_ROWS_SCREEN):
    rows = _fetch_rows(filtros, limit_rows=limit_rows)
    summary = build_summary_control(rows)
    payload = {
        'reporte': REPORT_ID,
        'titulo': TITLE,
        'descripcion': DESCRIPTION,
        'descripcion_periodo': _descripcion(filtros),
        'unidad_label': _unidad_label_safe(filtros.get('unidad_negocio_id')),
        'columns': display_columns(),
        'summary_cards': _summary_cards(summary),
        'empty_title': 'No hay datos incompletos para los filtros seleccionados',
        'empty_icon': 'fas fa-circle-check',
        'filtros': {
            'alcance': filtros['alcance'],
            'alcance_label': filtros['alcance_label'],
            'grupo': filtros.get('grupo', ''),
            'grupo_label': filtros.get('grupo_label', ''),
            'fecha_base': filtros['fecha_base'].isoformat(),
            'fecha_desde': filtros['fecha_desde'].isoformat(),
            'fecha_hasta': filtros['fecha_hasta'].isoformat(),
            'unidad_negocio_id': filtros.get('unidad_negocio_id') or '',
        },
        'rows': rows,
        'summary': summary,
    }
    return aplicar_contexto_monetario(payload)


def _unidad_label_safe(unidad_negocio_id):
    if not unidad_negocio_id:
        return 'Todas'
    try:
        from modules.reportes_rapidos.core.catalogos import unidad_label
        return unidad_label(unidad_negocio_id)
    except Exception:
        return str(unidad_negocio_id)


# ============================================================
# Exportaciones
# ============================================================

def excel_columns():
    return [
        ('prioridad', 'Prioridad', 14),
        ('area_label', 'Area', 16),
        ('grupo_label', 'Tipo de dato', 18),
        ('fecha_label', 'Fecha', 13),
        ('origen', 'Origen', 28),
        ('referencia', 'Referencia', 24),
        ('cliente_proveedor', 'Cliente / Proveedor', 34),
        ('detalle', 'Detalle', 54),
        ('estado', 'Estado', 16),
        ('unidad', 'Unidad', 28),
        ('moneda_codigo', 'Moneda', 10),
        ('monto', 'Monto', 16),
        ('accion', 'Accion', 26),
    ]


def excel_summary_text(summary):
    return excel_summary_text_control(summary)


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 22, 'align': 'center'},
        {'label': 'Area', 'width': 28, 'align': 'left'},
        {'label': 'Origen', 'width': 40, 'align': 'left'},
        {'label': 'Referencia', 'width': 32, 'align': 'left'},
        {'label': 'Cliente / Proveedor', 'width': 48, 'align': 'left'},
        {'label': 'Detalle', 'width': 72, 'align': 'left'},
        {'label': 'Monto', 'width': 28, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item.get('prioridad', ''),
            item.get('area_label', ''),
            item.get('origen', ''),
            item.get('referencia', ''),
            item.get('cliente_proveedor', ''),
            item.get('detalle', ''),
            item.get('monto_label', ''),
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', '', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} registros. Use Excel para el detalle completo.', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    return pdf_header_note_control(payload)
