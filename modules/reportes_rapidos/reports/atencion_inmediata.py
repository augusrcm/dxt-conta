# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Atencion inmediata
# ============================================================

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from database.db_manager import DatabaseManager
from modules.reportes_rapidos.core.catalogos import unidad_label as _unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_PDF, MAX_ROWS_SCREEN, MONEDA_BASE, PRIORIDAD_LABEL, PRIORIDAD_ORDEN
from modules.reportes_rapidos.core.formatos import dias_label as _dias_label
from modules.reportes_rapidos.core.formatos import format_money as _format_money
from modules.reportes_rapidos.core.monedas import aplicar_contexto_monetario
from modules.reportes_rapidos.core.utils import clean as _clean
from modules.reportes_rapidos.core.utils import date_label as _date_label
from modules.reportes_rapidos.core.utils import decimal_value as _decimal
from modules.reportes_rapidos.core.utils import parse_date as _parse_date
from modules.reportes_rapidos.core.utils import parse_optional_int as _parse_optional_int


REPORT_ID = 'atencion_inmediata'
TITLE = 'Atención inmediata'
DESCRIPTION = 'Alertas operativas de cobros, pagos y control.'
ICON = 'fas fa-triangle-exclamation'
FILTER_ALCANCE_LABEL = 'Alcance'
FILTER_DATE_LABEL = 'Fecha base'
FILTER_GROUP_LABEL = 'Grupo'
DEFAULT_ALCANCE = 'hoy'
DEFAULT_GRUPO = ''
MONEY_FIELDS = {'monto'}
WORKSHEET_TITLE = 'Atención inmediata'
FILE_SLUG = 'atencion_inmediata'
PDF_ORIENTATION = 'landscape'

ALCANCES = {
    'hoy': 'Hoy + vencidos',
    'vencidos': 'Solo vencidos',
    'proximos_7': 'Próximos 7 días + vencidos',
    'proximos_30': 'Próximos 30 días + vencidos',
    'sin_vencimiento': 'Sin vencimiento',
    'rango': 'Rango personalizado',
}

GRUPOS = {
    '': 'Todos',
    'COBRAR': 'Cobros',
    'PAGAR': 'Pagos',
    'CONTROL': 'Control',
}

HELP_TITLE = 'Atención inmediata'
HELP_INTRO = 'Radar operativo de situaciones que requieren revision.'
HELP_ITEMS = [
    'Incluye cobros y pagos vencidos o próximos según el alcance seleccionado.',
    'Incluye documentos por cobrar, facturas electrónicas y compromisos dentro de un mismo criterio de cartera.',
    'Los documentos sin vencimiento se muestran solo cuando se elige el alcance Sin vencimiento.',
    'Los documentos históricos no se marcan como error por no tener asiento inicial.',
]


def validate_filters(args):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El alcance seleccionado no es válido.')

    grupo = _clean(args.get('grupo'))
    if grupo not in GRUPOS:
        raise ValueError('El grupo seleccionado no es válido.')

    fecha_base = _parse_date(args.get('fecha_base'), FILTER_DATE_LABEL, default=hoy)
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if alcance == 'hoy':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
        incluir_vencidos = True
        sin_vencimiento = False
    elif alcance == 'vencidos':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base - timedelta(days=1)
        incluir_vencidos = True
        sin_vencimiento = False
    elif alcance == 'proximos_7':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=7)
        incluir_vencidos = True
        sin_vencimiento = False
    elif alcance == 'proximos_30':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=30)
        incluir_vencidos = True
        sin_vencimiento = False
    elif alcance == 'sin_vencimiento':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
        incluir_vencidos = False
        sin_vencimiento = True
    else:
        fecha_desde = _parse_date(args.get('fecha_desde'), 'Fecha desde')
        fecha_hasta = _parse_date(args.get('fecha_hasta'), 'Fecha hasta')
        if fecha_desde > fecha_hasta:
            raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')
        incluir_vencidos = False
        sin_vencimiento = False

    return {
        'alcance': alcance,
        'alcance_label': ALCANCES[alcance],
        'grupo': grupo,
        'grupo_label': GRUPOS[grupo],
        'fecha_base': fecha_base,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'incluir_vencidos': incluir_vencidos,
        'sin_vencimiento': sin_vencimiento,
        'unidad_negocio_id': unidad_negocio_id,
    }


def _descripcion_periodo(filtros):
    if filtros['alcance'] == 'sin_vencimiento':
        return 'Pendientes sin vencimiento definido'
    if filtros['alcance'] == 'vencidos':
        return f"Vencidos al {filtros['fecha_base'].strftime('%d/%m/%Y')}"
    if filtros['alcance'] == 'rango':
        return f"Del {filtros['fecha_desde'].strftime('%d/%m/%Y')} al {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    return f"{filtros['alcance_label']} · Corte {filtros['fecha_base'].strftime('%d/%m/%Y')}"


def _period_condition(alias: str, column: str, filtros: dict, params: list) -> str:
    if filtros['sin_vencimiento']:
        return f'{alias}.{column} IS NULL'
    if filtros['alcance'] == 'vencidos':
        params.append(filtros['fecha_base'])
        return f'{alias}.{column} < %s'
    if filtros['incluir_vencidos']:
        params.append(filtros['fecha_hasta'])
        return f'{alias}.{column} <= %s'
    params.extend([filtros['fecha_desde'], filtros['fecha_hasta']])
    return f'{alias}.{column} BETWEEN %s AND %s'


def _priority_from_date(fecha_ref, fecha_base: date, sin_vencimiento: bool = False):
    if sin_vencimiento or fecha_ref is None:
        return 'MEDIA', 3
    if fecha_ref < fecha_base:
        return 'CRITICA', 1
    if fecha_ref == fecha_base:
        return 'ALTA', 2
    return 'MEDIA', 3


def _tipo_documento_label(tipo):
    valores = {
        'FACTURA': 'Factura',
        'DOCUMENTO': 'Documento',
        'CONTRATO': 'Contrato',
        'NOTA_COBRO': 'Nota de cobro',
        'OTRO': 'Otro',
    }
    return valores.get(str(tipo or '').upper(), tipo or 'Documento')


def _origen_documento_label(origen):
    valores = {
        'HISTORICO': 'Documento historico',
        'VIGENTE_MANUAL': 'Documento vigente',
        'FACTURA_ELECTRONICA': 'Factura electronica',
    }
    return valores.get(str(origen or '').upper(), 'Documento por cobrar')


def _date_or_sin_vencimiento(value):
    return _date_label(value) if value else 'Sin vencimiento'


def _fetch_compromisos(db, filtros, limit_rows):
    if filtros['sin_vencimiento']:
        return []
    if filtros['grupo'] not in ('', 'PAGAR', 'COBRAR'):
        return []

    params = []
    fecha_sql = _period_condition('d', 'fecha_vencimiento', filtros, params)
    params.extend([filtros['grupo'], filtros['grupo']])
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND c.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)

    return db.execute_query(
        f"""
        SELECT
            CASE WHEN c.tipo = 'PAGAR' THEN 'PAGAR' ELSE 'COBRAR' END::text AS grupo_codigo,
            CASE WHEN c.tipo = 'PAGAR' THEN 'Compromiso por pagar' ELSE 'Compromiso por cobrar' END::text AS origen,
            d.fecha_vencimiento::date AS fecha_ref,
            c.codigo::text AS referencia,
            COALESCE(a.nombre, c.nombre, CASE WHEN c.tipo = 'PAGAR' THEN 'Sin proveedor' ELSE 'Sin cliente' END)::text AS contraparte,
            COALESCE(NULLIF(c.descripcion, ''), c.nombre, 'Compromiso financiero')::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            %s::text AS moneda_codigo,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)::numeric(18,2) AS monto,
            d.estado::text AS estado,
            CASE WHEN c.tipo = 'PAGAR' THEN 'Pagar' ELSE 'Cobrar' END::text AS accion,
            1::int AS orden_fuente
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        WHERE c.activo = TRUE
          AND c.tipo IN ('PAGAR', 'COBRAR')
          AND d.estado = 'PENDIENTE'
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
          AND {fecha_sql}
          AND (%s = '' OR c.tipo = %s)
          {unidad_sql}
        ORDER BY d.fecha_vencimiento ASC, c.tipo ASC, contraparte ASC, c.codigo ASC, d.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_documentos_cobrar(db, filtros, limit_rows):
    if filtros['grupo'] not in ('', 'COBRAR'):
        return []

    params = []
    fecha_sql = _period_condition('d', 'fecha_vencimiento', filtros, params)
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND d.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)

    return db.execute_query(
        f"""
        SELECT
            'COBRAR'::text AS grupo_codigo,
            (COALESCE(d.origen_documento::text, 'DOCUMENTO') || ' · ' || COALESCE(d.tipo_documento::text, 'DOCUMENTO'))::text AS origen_codigo,
            d.fecha_vencimiento::date AS fecha_ref,
            (COALESCE(d.tipo_documento::text, 'DOCUMENTO') || ' ' || COALESCE(d.numero_documento::text, d.id::text))::text AS referencia,
            COALESCE(NULLIF(d.cliente_nombre, ''), a.nombre, 'Sin cliente')::text AS contraparte,
            COALESCE(NULLIF(d.descripcion, ''), d.referencia_externa, d.numero_documento, 'Documento por cobrar')::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(d.moneda_codigo, %s)::text AS moneda_codigo,
            GREATEST(COALESCE(d.saldo_pendiente, 0), 0)::numeric(18,2) AS monto,
            d.estado::text AS estado,
            'Cobrar'::text AS accion,
            2::int AS orden_fuente,
            d.origen_documento::text AS origen_documento,
            d.tipo_documento::text AS tipo_documento
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.auxiliar a ON a.id = d.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        WHERE d.activo = TRUE
          AND d.estado IN ('PENDIENTE', 'PARCIAL')
          AND GREATEST(COALESCE(d.saldo_pendiente, 0), 0) > 0
          AND {fecha_sql}
          {unidad_sql}
        ORDER BY COALESCE(d.fecha_vencimiento, d.fecha_documento) ASC NULLS LAST, d.numero_documento ASC, d.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_facturas_sin_vencimiento(db, filtros, limit_rows):
    if not filtros['sin_vencimiento'] or filtros['grupo'] not in ('', 'COBRAR'):
        return []

    params = []
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND fe.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)

    return db.execute_query(
        f"""
        WITH reg AS (
            SELECT factura_electronica_id, COALESCE(SUM(monto), 0) AS total_regularizado
            FROM contabilidad.factura_regularizacion
            WHERE activo = TRUE
            GROUP BY factura_electronica_id
        ), apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR c.estado::text <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado::text <> 'ANULADO')
            GROUP BY fa.factura_electronica_id
        )
        SELECT
            'COBRAR'::text AS grupo_codigo,
            'Factura electronica'::text AS origen,
            NULL::date AS fecha_ref,
            ('FACTURA ' || fe.numero_factura::text) AS referencia,
            COALESCE(NULLIF(fe.nombre_cliente, ''), a.nombre, 'Sin cliente')::text AS contraparte,
            ('Emitida ' || TO_CHAR(fe.fecha_emision, 'DD/MM/YYYY'))::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(fe.moneda_codigo, %s)::text AS moneda_codigo,
            GREATEST(COALESCE(fe.importe_total, 0) - COALESCE(apps.total_aplicado, 0) - COALESCE(reg.total_regularizado, 0), 0)::numeric(18,2) AS monto,
            fe.estado::text AS estado,
            'Cobrar'::text AS accion,
            3::int AS orden_fuente
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.auxiliar a ON a.id = fe.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
        LEFT JOIN reg ON reg.factura_electronica_id = fe.id
        LEFT JOIN apps ON apps.factura_electronica_id = fe.id
        WHERE fe.estado::text <> 'ANULADA'
          AND COALESCE(fe.cuenta_cobrar_codigo, '') <> ''
          AND GREATEST(COALESCE(fe.importe_total, 0) - COALESCE(apps.total_aplicado, 0) - COALESCE(reg.total_regularizado, 0), 0) > 0
          {unidad_sql}
        ORDER BY fe.fecha_emision ASC, fe.numero_factura ASC, fe.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_borradores(db, filtros, limit_rows):
    if filtros['sin_vencimiento']:
        return []
    if filtros['grupo'] not in ('', 'PAGAR', 'COBRAR'):
        return []

    params_pago = []
    fecha_pago = _period_condition('p', 'fecha', filtros, params_pago)
    unidad_pago = ''
    if filtros['unidad_negocio_id']:
        unidad_pago = 'AND p.unidad_negocio_id = %s'
        params_pago.append(filtros['unidad_negocio_id'])

    params_cobro = []
    fecha_cobro = _period_condition('co', 'fecha', filtros, params_cobro)
    unidad_cobro = ''
    if filtros['unidad_negocio_id']:
        unidad_cobro = 'AND co.unidad_negocio_id = %s'
        params_cobro.append(filtros['unidad_negocio_id'])

    rows = []
    if filtros['grupo'] in ('', 'PAGAR'):
        rows.extend(db.execute_query(
            f"""
            SELECT
                'PAGAR'::text AS grupo_codigo,
                'Pago en borrador'::text AS origen,
                p.fecha::date AS fecha_ref,
                COALESCE(p.referencia, 'Pago #' || p.id::text)::text AS referencia,
                COALESCE(a.nombre, 'Sin proveedor')::text AS contraparte,
                COALESCE(NULLIF(p.glosa, ''), 'Pago pendiente')::text AS detalle,
                COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
                COALESCE(p.moneda_codigo, %s)::text AS moneda_codigo,
                COALESCE(p.monto_total, 0)::numeric(18,2) AS monto,
                p.estado::text AS estado,
                'Confirmar'::text AS accion,
                4::int AS orden_fuente
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.auxiliar a ON a.id = p.proveedor_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE p.estado::text = 'BORRADOR'
              AND {fecha_pago}
              {unidad_pago}
            ORDER BY p.fecha ASC, p.id ASC
            LIMIT %s
            """,
            tuple([MONEDA_BASE, *params_pago, limit_rows]),
        ))
    if filtros['grupo'] in ('', 'COBRAR'):
        rows.extend(db.execute_query(
            f"""
            SELECT
                'COBRAR'::text AS grupo_codigo,
                'Cobro en borrador'::text AS origen,
                co.fecha::date AS fecha_ref,
                COALESCE(co.referencia, 'Cobro #' || co.id::text)::text AS referencia,
                COALESCE(a.nombre, co.cliente_nombre_ref, 'Sin cliente')::text AS contraparte,
                COALESCE(NULLIF(co.glosa, ''), 'Cobro pendiente')::text AS detalle,
                COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
                COALESCE(co.moneda_codigo, %s)::text AS moneda_codigo,
                COALESCE(co.monto_total, 0)::numeric(18,2) AS monto,
                co.estado::text AS estado,
                'Confirmar'::text AS accion,
                5::int AS orden_fuente
            FROM contabilidad.cobro co
            LEFT JOIN contabilidad.auxiliar a ON a.id = co.cliente_auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = co.unidad_negocio_id
            WHERE co.estado::text = 'BORRADOR'
              AND {fecha_cobro}
              {unidad_cobro}
            ORDER BY co.fecha ASC, co.id ASC
            LIMIT %s
            """,
            tuple([MONEDA_BASE, *params_cobro, limit_rows]),
        ))
    return rows


def _fetch_control(db, filtros, limit_rows):
    if filtros['grupo'] not in ('', 'CONTROL'):
        return []

    rows = []
    if not filtros['sin_vencimiento']:
        params_arq = []
        fecha_arq = _period_condition('arq', 'fecha_arqueo', filtros, params_arq)
        rows.extend(db.execute_query(
            f"""
            SELECT
                'CONTROL'::text AS grupo_codigo,
                'Arqueo con diferencia'::text AS origen,
                arq.fecha_arqueo::date AS fecha_ref,
                ('Arqueo #' || arq.id::text)::text AS referencia,
                COALESCE(cx.nombre, 'Caja')::text AS contraparte,
                COALESCE(NULLIF(arq.observacion, ''), 'Diferencia de arqueo')::text AS detalle,
                ''::text AS unidad,
                %s::text AS moneda_codigo,
                ABS(COALESCE(arq.diferencia, 0))::numeric(18,2) AS monto,
                arq.estado::text AS estado,
                'Revisar'::text AS accion,
                6::int AS orden_fuente,
                'CRITICA'::text AS prioridad_fija
            FROM contabilidad.arqueo_caja arq
            LEFT JOIN contabilidad.caja cx ON cx.id = arq.caja_id
            WHERE COALESCE(arq.diferencia, 0) <> 0
              AND arq.estado::text <> 'ANULADO'
              AND {fecha_arq}
            ORDER BY arq.fecha_arqueo ASC, arq.id ASC
            LIMIT %s
            """,
            tuple([MONEDA_BASE, *params_arq, limit_rows]),
        ))

    rows.extend(db.execute_query(
        """
        SELECT
            'CONTROL'::text AS grupo_codigo,
            'Proceso critico activo'::text AS origen,
            b.fecha_hora_inicio::date AS fecha_ref,
            COALESCE(b.token_proceso::text, 'Bloqueo #' || b.id::text)::text AS referencia,
            COALESCE(b.usuario_nombre, 'Usuario no identificado')::text AS contraparte,
            ('Proceso ' || b.tipo_proceso::text || ' · gestion ' || b.gestion_origen::text)::text AS detalle,
            ''::text AS unidad,
            ''::text AS moneda_codigo,
            0::numeric(18,2) AS monto,
            b.estado::text AS estado,
            'Revisar'::text AS accion,
            7::int AS orden_fuente,
            'CRITICA'::text AS prioridad_fija
        FROM contabilidad.gestion_bloqueo_critico b
        WHERE b.estado::text = 'EN_PROCESO'
        ORDER BY b.fecha_hora_inicio ASC, b.id ASC
        LIMIT %s
        """,
        (limit_rows,),
    ))

    if filtros['grupo'] in ('', 'CONTROL'):
        rows.extend(_fetch_inconsistencias_documentos(db, filtros, limit_rows))
        rows.extend(_fetch_inconsistencias_facturas(db, filtros, limit_rows))
    return rows


def _fetch_inconsistencias_documentos(db, filtros, limit_rows):
    params = []
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND d.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)
    return db.execute_query(
        f"""
        SELECT
            'CONTROL'::text AS grupo_codigo,
            'Documento por cobrar'::text AS origen,
            COALESCE(d.fecha_vencimiento, d.fecha_documento)::date AS fecha_ref,
            (COALESCE(d.tipo_documento::text, 'DOCUMENTO') || ' ' || COALESCE(d.numero_documento::text, d.id::text))::text AS referencia,
            COALESCE(NULLIF(d.cliente_nombre, ''), a.nombre, 'Sin cliente')::text AS contraparte,
            TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                CASE WHEN d.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                CASE WHEN d.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(d.cliente_nombre, ''), '') = '' THEN 'Sin cliente' END,
                CASE WHEN COALESCE(d.cuenta_cartera_codigo, '') = '' THEN 'Sin cuenta cartera' END,
                CASE WHEN d.origen_documento::text = 'VIGENTE_MANUAL' AND COALESCE(d.cuenta_contrapartida_codigo, '') = '' THEN 'Sin contrapartida' END,
                CASE WHEN COALESCE(d.saldo_pendiente, 0) < 0 THEN 'Saldo negativo' END,
                CASE WHEN COALESCE(d.importe_cobrado, 0) > COALESCE(d.importe_total, 0) THEN 'Cobrado excede total' END
            ))::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(d.moneda_codigo, %s)::text AS moneda_codigo,
            GREATEST(COALESCE(d.saldo_pendiente, 0), 0)::numeric(18,2) AS monto,
            d.estado::text AS estado,
            'Corregir'::text AS accion,
            8::int AS orden_fuente,
            'ALTA'::text AS prioridad_fija
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.auxiliar a ON a.id = d.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        WHERE d.activo = TRUE
          AND d.estado IN ('PENDIENTE', 'PARCIAL')
          AND (
                d.unidad_negocio_id IS NULL
             OR (d.cliente_auxiliar_id IS NULL AND COALESCE(NULLIF(d.cliente_nombre, ''), '') = '')
             OR COALESCE(d.cuenta_cartera_codigo, '') = ''
             OR (d.origen_documento::text = 'VIGENTE_MANUAL' AND COALESCE(d.cuenta_contrapartida_codigo, '') = '')
             OR COALESCE(d.saldo_pendiente, 0) < 0
             OR COALESCE(d.importe_cobrado, 0) > COALESCE(d.importe_total, 0)
          )
          {unidad_sql}
        ORDER BY COALESCE(d.fecha_vencimiento, d.fecha_documento) ASC NULLS LAST, d.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_inconsistencias_facturas(db, filtros, limit_rows):
    params = []
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND fe.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)
    return db.execute_query(
        f"""
        SELECT
            'CONTROL'::text AS grupo_codigo,
            'Factura electronica'::text AS origen,
            fe.fecha_emision::date AS fecha_ref,
            ('FACTURA ' || COALESCE(fe.numero_factura::text, fe.id::text)) AS referencia,
            COALESCE(NULLIF(fe.nombre_cliente, ''), a.nombre, 'Sin cliente')::text AS contraparte,
            TRIM(BOTH ' · ' FROM CONCAT_WS(' · ',
                CASE WHEN fe.unidad_negocio_id IS NULL THEN 'Sin unidad' END,
                CASE WHEN COALESCE(fe.cuenta_cobrar_codigo, '') = '' THEN 'Sin cuenta por cobrar' END,
                CASE WHEN COALESCE(fe.importe_total, 0) <= 0 THEN 'Importe no valido' END
            ))::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(fe.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(fe.importe_total, 0)::numeric(18,2) AS monto,
            fe.estado::text AS estado,
            'Corregir'::text AS accion,
            9::int AS orden_fuente,
            'ALTA'::text AS prioridad_fija
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.auxiliar a ON a.id = fe.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
        WHERE fe.estado::text <> 'ANULADA'
          AND (
                fe.unidad_negocio_id IS NULL
             OR COALESCE(fe.cuenta_cobrar_codigo, '') = ''
             OR COALESCE(fe.importe_total, 0) <= 0
          )
          {unidad_sql}
        ORDER BY fe.fecha_emision ASC NULLS LAST, fe.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _map_row(row, idx, fecha_base):
    fecha_ref = row.get('fecha_ref')
    prioridad = row.get('prioridad_fija') or _priority_from_date(fecha_ref, fecha_base, fecha_ref is None)[0]
    prioridad_orden = PRIORIDAD_ORDEN.get(prioridad, 9)
    if row.get('prioridad_fija') == 'ALTA':
        prioridad_orden = 2
    elif row.get('prioridad_fija') == 'CRITICA':
        prioridad_orden = 1

    monto = _decimal(row.get('monto'))
    moneda = row.get('moneda_codigo') or ''
    grupo_codigo = row.get('grupo_codigo') or ''

    origen = row.get('origen') or ''
    if row.get('origen_documento') or row.get('tipo_documento'):
        origen = f"{_origen_documento_label(row.get('origen_documento'))} · {_tipo_documento_label(row.get('tipo_documento'))}"

    dias = None
    if isinstance(fecha_ref, date):
        dias = (fecha_ref - fecha_base).days

    return {
        'nro': idx,
        'grupo_codigo': grupo_codigo,
        'grupo': GRUPOS.get(grupo_codigo, grupo_codigo or 'Control'),
        'prioridad_codigo': prioridad,
        'prioridad': PRIORIDAD_LABEL.get(prioridad, prioridad),
        'prioridad_orden': int(prioridad_orden),
        'fecha': fecha_ref.isoformat() if isinstance(fecha_ref, date) else '',
        'fecha_label': _date_or_sin_vencimiento(fecha_ref),
        'dias': dias,
        'dias_label': _dias_label(dias) if dias is not None else 'Sin vencimiento',
        'origen': origen,
        'referencia': row.get('referencia') or '',
        'contraparte': row.get('contraparte') or '',
        'detalle': row.get('detalle') or '',
        'unidad': row.get('unidad') or '',
        'moneda_codigo': moneda,
        'monto': float(monto),
        'monto_label': _format_money(monto, moneda) if moneda else '',
        'estado': row.get('estado') or '',
        'accion': row.get('accion') or '',
        'orden_fuente': int(row.get('orden_fuente') or 9),
    }


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    per_source_limit = max(int(limit_rows), 50)
    with DatabaseManager() as db:
        rows_raw = []
        rows_raw.extend(_fetch_compromisos(db, filtros, per_source_limit))
        rows_raw.extend(_fetch_documentos_cobrar(db, filtros, per_source_limit))
        rows_raw.extend(_fetch_facturas_sin_vencimiento(db, filtros, per_source_limit))
        rows_raw.extend(_fetch_borradores(db, filtros, per_source_limit))
        rows_raw.extend(_fetch_control(db, filtros, per_source_limit))

    mapped = [_map_row(row, idx, filtros['fecha_base']) for idx, row in enumerate(rows_raw, start=1)]
    mapped.sort(key=lambda row: (
        row.get('prioridad_orden') or 9,
        row.get('fecha') or '9999-12-31',
        row.get('grupo_codigo') or '',
        row.get('orden_fuente') or 9,
        row.get('contraparte') or '',
        row.get('referencia') or '',
    ))
    for idx, row in enumerate(mapped[:limit_rows], start=1):
        row['nro'] = idx
    return mapped[:limit_rows]


def display_columns():
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'fecha_label', 'label': 'Fecha', 'sub_key': 'dias_label', 'align': 'center'},
        {'key': 'grupo', 'label': 'Grupo', 'type': 'badge', 'code_key': 'grupo_codigo', 'align': 'center'},
        {'key': 'origen', 'label': 'Origen', 'align': 'left', 'strong': True},
        {'key': 'referencia', 'label': 'Referencia', 'align': 'left'},
        {'key': 'contraparte', 'label': 'Cliente / proveedor', 'align': 'left'},
        {'key': 'detalle', 'label': 'Detalle', 'sub_key': 'unidad', 'align': 'left'},
        {'key': 'moneda_codigo', 'label': 'Moneda', 'align': 'center'},
        {'key': 'monto', 'label': 'Monto', 'type': 'money', 'align': 'right'},
        {'key': 'estado', 'label': 'Estado', 'align': 'center'},
        {'key': 'accion', 'label': 'Acción', 'align': 'center'},
    ]


def _label_totales_por_moneda(valores):
    if not valores:
        return '0.00'
    return ' · '.join(f"{moneda} {_format_money(valores[moneda], moneda)}" for moneda in sorted(valores))


def _build_summary(rows):
    total_cobrar = defaultdict(lambda: Decimal('0.00'))
    total_pagar = defaultdict(lambda: Decimal('0.00'))
    criticas = altas = medias = control = 0
    sin_vencimiento = 0

    for row in rows:
        prioridad = row.get('prioridad_codigo')
        if prioridad == 'CRITICA':
            criticas += 1
        elif prioridad == 'ALTA':
            altas += 1
        elif prioridad == 'MEDIA':
            medias += 1

        if not row.get('fecha'):
            sin_vencimiento += 1

        grupo = row.get('grupo_codigo') or ''
        moneda = row.get('moneda_codigo') or ''
        monto = _decimal(row.get('monto'))
        if grupo == 'COBRAR' and moneda:
            total_cobrar[moneda] += monto
        elif grupo == 'PAGAR' and moneda:
            total_pagar[moneda] += monto
        elif grupo == 'CONTROL':
            control += 1

    monedas = sorted(set(total_cobrar.keys()) | set(total_pagar.keys()))
    totales_por_moneda = []
    for moneda in monedas:
        cobrar = total_cobrar[moneda]
        pagar = total_pagar[moneda]
        totales_por_moneda.append({
            'moneda_codigo': moneda,
            'total_cobrar': float(cobrar),
            'total_pagar': float(pagar),
            'total_cobrar_label': _format_money(cobrar, moneda),
            'total_pagar_label': _format_money(pagar, moneda),
        })

    return {
        'cantidad': len(rows),
        'criticas': criticas,
        'altas': altas,
        'medias': medias,
        'control': control,
        'sin_vencimiento': sin_vencimiento,
        'total_cobrar_label': _label_totales_por_moneda(total_cobrar),
        'total_pagar_label': _label_totales_por_moneda(total_pagar),
        'totales_por_moneda': totales_por_moneda,
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Críticas', 'value': summary.get('criticas', 0), 'note': 'Bloqueantes o vencidas', 'kind': 'critical'},
        {'label': 'Altas', 'value': summary.get('altas', 0), 'note': 'Atención del día', 'kind': 'high'},
        {'label': 'Por cobrar', 'value': summary.get('total_cobrar_label'), 'note': 'Cartera en alerta', 'kind': 'total'},
        {'label': 'Por pagar', 'value': summary.get('total_pagar_label'), 'note': 'Pagos en alerta', 'kind': 'high'},
        {'label': 'Control', 'value': summary.get('control', 0), 'note': 'Inconsistencias', 'kind': 'group'},
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
        'empty_title': 'No hay alertas para los filtros seleccionados',
        'empty_icon': 'fas fa-circle-check',
        'filtros': {
            'alcance': filtros['alcance'],
            'alcance_label': filtros['alcance_label'],
            'grupo': filtros['grupo'],
            'grupo_label': filtros['grupo_label'],
            'fecha_base': filtros['fecha_base'].isoformat(),
            'fecha_desde': filtros['fecha_desde'].isoformat(),
            'fecha_hasta': filtros['fecha_hasta'].isoformat(),
            'incluir_vencidos': filtros['incluir_vencidos'],
            'sin_vencimiento': filtros['sin_vencimiento'],
            'unidad_negocio_id': filtros['unidad_negocio_id'] or '',
        },
        'rows': rows,
        'summary': summary,
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
    return aplicar_contexto_monetario(payload)


def excel_columns():
    return [
        ('prioridad', 'Prioridad', 13),
        ('fecha_label', 'Fecha', 16),
        ('dias_label', 'Situación', 18),
        ('grupo', 'Grupo', 13),
        ('origen', 'Origen', 28),
        ('referencia', 'Referencia', 22),
        ('contraparte', 'Cliente / proveedor', 34),
        ('detalle', 'Detalle', 42),
        ('unidad', 'Unidad', 28),
        ('estado', 'Estado', 14),
        ('moneda_codigo', 'Moneda', 10),
        ('monto', 'Monto', 16),
        ('accion', 'Acción', 14),
    ]


def excel_summary_text(summary):
    return (
        f"Alertas: {summary.get('cantidad', 0)} · "
        f"Críticas: {summary.get('criticas', 0)} · "
        f"Altas: {summary.get('altas', 0)} · "
        f"Por cobrar: {summary.get('total_cobrar_label', '')} · "
        f"Por pagar: {summary.get('total_pagar_label', '')}"
    )


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 18, 'align': 'center'},
        {'label': 'Fecha', 'width': 20, 'align': 'center'},
        {'label': 'Grupo', 'width': 18, 'align': 'center'},
        {'label': 'Origen', 'width': 34, 'align': 'left'},
        {'label': 'Referencia', 'width': 28, 'align': 'left'},
        {'label': 'Cliente / Proveedor', 'width': 42, 'align': 'left'},
        {'label': 'Mon.', 'width': 12, 'align': 'center'},
        {'label': 'Monto', 'width': 25, 'align': 'right'},
        {'label': 'Estado', 'width': 20, 'align': 'center'},
        {'label': 'Acción', 'width': 18, 'align': 'center'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['prioridad'],
            item['fecha_label'],
            item['grupo'],
            item['origen'],
            item['referencia'],
            item['contraparte'],
            item['moneda_codigo'],
            item['monto_label'],
            item['estado'],
            item['accion'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} registros. Use Excel para el detalle completo.', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Críticas: {summary.get('criticas', 0)}. "
        f"Altas: {summary.get('altas', 0)}. "
        f"Por cobrar: {summary.get('total_cobrar_label', '')}. "
        f"Por pagar: {summary.get('total_pagar_label', '')}."
    )
