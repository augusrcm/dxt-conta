# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Cartera por cobrar
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


REPORT_ID = 'cuentas_por_cobrar_pendientes'
TITLE = 'Cartera por cobrar'
DESCRIPTION = 'Pendientes cobrables consolidados.'
WORKSHEET_TITLE = 'Cartera por cobrar'
FILE_SLUG = 'cartera_por_cobrar'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-money-bill-trend-up'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha base'
FILTER_GROUP_LABEL = 'Origen'
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
    'sin_vencimiento': 'Sin vencimiento',
    'rango': 'Rango personalizado',
}

GRUPOS = {
    '': 'Todos',
    'COMPROMISO': 'Compromisos',
    'DOCUMENTO': 'Documentos',
    'FACTURA': 'Facturas electrónicas',
}

HELP_TITLE = 'Cartera por cobrar'
HELP_INTRO = 'Consolida todo lo pendiente de cobro.'
HELP_ITEMS = [
    'Incluye compromisos por cobrar, documentos por cobrar y facturas electrónicas contabilizadas con saldo.',
    'Los documentos y facturas sin vencimiento aparecen en Toda la cartera o en Sin vencimiento.',
    'Los totales se separan por moneda; no se mezclan importes de monedas distintas.',
    'No representa dinero en caja o banco hasta que el cobro sea confirmado en Tesorería.',
]


FECHA_MINIMA = date(1900, 1, 1)
FECHA_MAXIMA = date(9999, 12, 31)
ESTADOS_COBRABLES = ('PENDIENTE', 'PARCIAL', 'INCUMPLIDO')


def validate_filters(args):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El periodo seleccionado no es válido.')

    grupo = _clean(args.get('grupo')) or DEFAULT_GRUPO
    if grupo not in GRUPOS:
        raise ValueError('El origen seleccionado no es válido.')

    fecha_base = _parse_date(args.get('fecha_base'), FILTER_DATE_LABEL, default=hoy)
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if alcance == 'todas':
        fecha_desde = FECHA_MINIMA
        fecha_hasta = FECHA_MAXIMA
        modo_fecha = 'todas'
    elif alcance == 'sin_vencimiento':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
        modo_fecha = 'sin_vencimiento'
    elif alcance == 'vencidas':
        fecha_desde = FECHA_MINIMA
        fecha_hasta = fecha_base - timedelta(days=1)
        modo_fecha = 'fechadas'
    elif alcance == 'hoy':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
        modo_fecha = 'fechadas'
    elif alcance == 'manana':
        fecha_desde = fecha_base + timedelta(days=1)
        fecha_hasta = fecha_desde
        modo_fecha = 'fechadas'
    elif alcance == 'proximos_7':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=7)
        modo_fecha = 'fechadas'
    elif alcance == 'proximos_30':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=30)
        modo_fecha = 'fechadas'
    else:
        fecha_desde = _parse_date(args.get('fecha_desde'), 'Fecha desde')
        fecha_hasta = _parse_date(args.get('fecha_hasta'), 'Fecha hasta')
        if fecha_desde > fecha_hasta:
            raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')
        modo_fecha = 'fechadas'

    return {
        'alcance': alcance,
        'alcance_label': ALCANCES[alcance],
        'grupo': grupo,
        'grupo_label': GRUPOS[grupo],
        'fecha_base': fecha_base,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
        'modo_fecha': modo_fecha,
    }


def _descripcion_periodo(filtros):
    if filtros['alcance'] == 'todas':
        return 'Toda la cartera pendiente'
    if filtros['alcance'] == 'sin_vencimiento':
        return 'Pendientes sin vencimiento definido'
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
        'HISTORICO': 'Documento histórico',
        'VIGENTE_MANUAL': 'Documento vigente',
        'FACTURA_ELECTRONICA': 'Factura electrónica',
    }
    return valores.get(str(origen or '').upper(), 'Documento por cobrar')


def _prioridad(fecha_ref, fecha_base):
    if not isinstance(fecha_ref, date):
        return 'BAJA', 'Sin vencimiento', None, 3
    dias = (fecha_ref - fecha_base).days
    if dias < 0:
        return 'CRITICA', 'Vencida', dias, 0
    if dias == 0:
        return 'ALTA', 'Hoy', dias, 1
    if dias <= 7:
        return 'MEDIA', _dias_label(dias), dias, 2
    return 'BAJA', _dias_label(dias), dias, 4


def _fecha_condition(alias, filtros, params):
    modo = filtros['modo_fecha']
    if modo == 'todas':
        return 'TRUE'
    if modo == 'sin_vencimiento':
        return f'{alias}.fecha_vencimiento IS NULL'
    params.extend([filtros['fecha_desde'], filtros['fecha_hasta']])
    return f'{alias}.fecha_vencimiento BETWEEN %s AND %s'


def _fetch_compromisos(db, filtros, limit_rows):
    if filtros['grupo'] not in ('', 'COMPROMISO'):
        return []
    if filtros['modo_fecha'] == 'sin_vencimiento':
        return []

    params = []
    fecha_condition = _fecha_condition('d', filtros, params)
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND c.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)

    return db.execute_query(
        f"""
        SELECT
            'COMPROMISO'::text AS fuente_codigo,
            'Compromiso'::text AS origen,
            'COBRAR'::text AS tipo_cartera,
            d.fecha_vencimiento::date AS fecha_ref,
            c.codigo::text AS referencia,
            COALESCE(a.nombre, a.razon_social, c.nombre, 'Sin cliente')::text AS cliente,
            COALESCE(a.nit_ci, '')::text AS cliente_doc,
            COALESCE(NULLIF(c.descripcion, ''), c.nombre, 'Compromiso por cobrar')::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            %s::text AS moneda_codigo,
            COALESCE(d.monto_programado, 0)::numeric(18,2) AS monto_total,
            COALESCE(d.monto_registrado, 0)::numeric(18,2) AS monto_aplicado,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)::numeric(18,2) AS monto_pendiente,
            d.estado::text AS estado,
            COALESCE(d.observacion, '')::text AS observacion,
            c.cuenta_contable::text AS cuenta_codigo,
            COALESCE(cta.nombre, '')::text AS cuenta_nombre,
            1::int AS orden_fuente
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = c.cuenta_contable
        WHERE c.activo = TRUE
          AND c.tipo = 'COBRAR'
          AND d.estado IN ('PENDIENTE', 'PARCIAL', 'INCUMPLIDO')
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
          AND {fecha_condition}
          {unidad_sql}
        ORDER BY d.fecha_vencimiento ASC, cliente ASC, c.codigo ASC, d.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_documentos(db, filtros, limit_rows):
    if filtros['grupo'] not in ('', 'DOCUMENTO'):
        return []

    params = []
    fecha_condition = _fecha_condition('d', filtros, params)
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND d.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)

    return db.execute_query(
        f"""
        SELECT
            'DOCUMENTO'::text AS fuente_codigo,
            d.origen_documento::text AS origen_codigo,
            d.tipo_documento::text AS tipo_documento,
            'COBRAR'::text AS tipo_cartera,
            d.fecha_vencimiento::date AS fecha_ref,
            (d.tipo_documento::text || ' ' || d.numero_documento::text) AS referencia,
            COALESCE(NULLIF(d.cliente_nombre, ''), a.nombre, a.razon_social, 'Sin cliente')::text AS cliente,
            COALESCE(NULLIF(d.cliente_nit, ''), a.nit_ci, '')::text AS cliente_doc,
            COALESCE(NULLIF(d.descripcion, ''), d.referencia_externa, d.numero_documento, 'Documento por cobrar')::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(d.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(d.importe_total, 0)::numeric(18,2) AS monto_total,
            COALESCE(d.importe_cobrado, 0)::numeric(18,2) AS monto_aplicado,
            GREATEST(COALESCE(d.saldo_pendiente, 0), 0)::numeric(18,2) AS monto_pendiente,
            d.estado::text AS estado,
            COALESCE(d.observacion, '')::text AS observacion,
            d.cuenta_cartera_codigo::text AS cuenta_codigo,
            COALESCE(cta.nombre, '')::text AS cuenta_nombre,
            2::int AS orden_fuente
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.auxiliar a ON a.id = d.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = d.cuenta_cartera_codigo
        WHERE d.activo = TRUE
          AND d.estado IN ('PENDIENTE', 'PARCIAL')
          AND COALESCE(d.factura_electronica_id, 0) = 0
          AND COALESCE(d.origen_documento, '') <> 'FACTURA_ELECTRONICA'
          AND GREATEST(COALESCE(d.saldo_pendiente, 0), 0) > 0
          AND {fecha_condition}
          {unidad_sql}
        ORDER BY COALESCE(d.fecha_vencimiento, d.fecha_documento) ASC, cliente ASC, d.numero_documento ASC, d.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_facturas(db, filtros, limit_rows):
    if filtros['grupo'] not in ('', 'FACTURA'):
        return []
    if filtros['modo_fecha'] == 'fechadas':
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
            SELECT
                factura_electronica_id,
                COALESCE(SUM(monto), 0) AS total_regularizado
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
            WHERE (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
            GROUP BY fa.factura_electronica_id
        )
        SELECT
            'FACTURA'::text AS fuente_codigo,
            'Factura electrónica'::text AS origen,
            'COBRAR'::text AS tipo_cartera,
            NULL::date AS fecha_ref,
            ('FACTURA ' || fe.numero_factura::text) AS referencia,
            COALESCE(NULLIF(fe.nombre_cliente, ''), a.nombre, a.razon_social, 'Sin cliente')::text AS cliente,
            COALESCE(NULLIF(fe.nit_cliente, ''), a.nit_ci, '')::text AS cliente_doc,
            ('Emitida ' || TO_CHAR(fe.fecha_emision, 'DD/MM/YYYY'))::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(fe.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(fe.importe_total, 0)::numeric(18,2) AS monto_total,
            (COALESCE(apps.total_aplicado, 0) + COALESCE(reg.total_regularizado, 0))::numeric(18,2) AS monto_aplicado,
            GREATEST(
                COALESCE(fe.importe_total, 0)
                - COALESCE(apps.total_aplicado, 0)
                - COALESCE(reg.total_regularizado, 0),
                0
            )::numeric(18,2) AS monto_pendiente,
            fe.estado::text AS estado,
            ''::text AS observacion,
            fe.cuenta_cobrar_codigo::text AS cuenta_codigo,
            COALESCE(cta.nombre, '')::text AS cuenta_nombre,
            3::int AS orden_fuente
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.auxiliar a ON a.id = fe.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = fe.cuenta_cobrar_codigo
        LEFT JOIN reg ON reg.factura_electronica_id = fe.id
        LEFT JOIN apps ON apps.factura_electronica_id = fe.id
        WHERE fe.estado <> 'ANULADA'
          AND COALESCE(fe.cuenta_cobrar_codigo, '') <> ''
          AND GREATEST(
                COALESCE(fe.importe_total, 0)
                - COALESCE(apps.total_aplicado, 0)
                - COALESCE(reg.total_regularizado, 0),
                0
              ) > 0
          {unidad_sql}
        ORDER BY fe.fecha_emision ASC, fe.numero_factura ASC, fe.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _origen_label(row):
    if row.get('fuente_codigo') == 'DOCUMENTO':
        origen = _origen_documento_label(row.get('origen_codigo'))
        return f"{origen} · {_tipo_documento_label(row.get('tipo_documento'))}"
    return row.get('origen') or row.get('fuente_codigo') or ''


def _map_row(row, idx, fecha_base):
    fecha_ref = row.get('fecha_ref')
    prioridad_codigo, prioridad_label, dias, orden_prioridad = _prioridad(fecha_ref, fecha_base)
    total = _decimal(row.get('monto_total'))
    aplicado = _decimal(row.get('monto_aplicado'))
    pendiente = _decimal(row.get('monto_pendiente'))
    moneda = row.get('moneda_codigo') or MONEDA_BASE
    cuenta = row.get('cuenta_codigo') or ''
    cuenta_nombre = row.get('cuenta_nombre') or ''
    cuenta_label = f'{cuenta} · {cuenta_nombre}' if cuenta and cuenta_nombre else cuenta

    return {
        'nro': idx,
        'prioridad_codigo': prioridad_codigo,
        'prioridad': prioridad_label,
        'orden_prioridad': orden_prioridad,
        'fecha': fecha_ref.isoformat() if isinstance(fecha_ref, date) else '',
        'fecha_label': _date_label(fecha_ref) if isinstance(fecha_ref, date) else 'Sin vencimiento',
        'dias': dias,
        'dias_label': _dias_label(dias) if dias is not None else 'Sin fecha',
        'fuente_codigo': row.get('fuente_codigo') or '',
        'origen': _origen_label(row),
        'referencia': row.get('referencia') or '',
        'cliente': row.get('cliente') or 'Sin cliente',
        'cliente_doc': row.get('cliente_doc') or '',
        'detalle': row.get('detalle') or '',
        'unidad': row.get('unidad') or '',
        'cuenta': cuenta_label,
        'estado_codigo': row.get('estado') or '',
        'estado': row.get('estado') or '',
        'observacion': row.get('observacion') or '',
        'moneda_codigo': moneda,
        'monto_total': float(total),
        'monto_total_label': _format_money(total, moneda),
        'monto_aplicado': float(aplicado),
        'monto_aplicado_label': _format_money(aplicado, moneda),
        'monto_pendiente': float(pendiente),
        'monto_pendiente_label': _format_money(pendiente, moneda),
        'orden_fuente': int(row.get('orden_fuente') or 9),
    }


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    per_source_limit = max(int(limit_rows), 50)
    with DatabaseManager() as db:
        rows_raw = []
        rows_raw.extend(_fetch_compromisos(db, filtros, per_source_limit))
        rows_raw.extend(_fetch_documentos(db, filtros, per_source_limit))
        rows_raw.extend(_fetch_facturas(db, filtros, per_source_limit))

    mapped = [_map_row(row, idx, filtros['fecha_base']) for idx, row in enumerate(rows_raw, start=1)]
    mapped.sort(key=lambda row: (
        row.get('orden_prioridad', 9),
        row.get('fecha') or '9999-12-31',
        row.get('orden_fuente') or 9,
        row.get('cliente') or '',
        row.get('referencia') or '',
    ))
    for idx, row in enumerate(mapped[:limit_rows], start=1):
        row['nro'] = idx
    return mapped[:limit_rows]




def fetch_cartera_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    return _fetch_rows(filtros, limit_rows=limit_rows)

def display_columns():
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'fecha_label', 'label': 'Vencimiento', 'sub_key': 'dias_label', 'align': 'center'},
        {'key': 'origen', 'label': 'Origen', 'align': 'left'},
        {'key': 'referencia', 'label': 'Referencia', 'align': 'left', 'strong': True},
        {'key': 'cliente', 'label': 'Cliente', 'sub_key': 'cliente_doc', 'align': 'left'},
        {'key': 'detalle', 'label': 'Detalle', 'sub_key': 'unidad', 'align': 'left'},
        {'key': 'moneda_codigo', 'label': 'Moneda', 'align': 'center'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
        {'key': 'monto_aplicado', 'label': 'Cobrado', 'type': 'money', 'align': 'right'},
        {'key': 'monto_pendiente', 'label': 'Pendiente', 'type': 'money', 'align': 'right'},
        {'key': 'estado', 'label': 'Estado', 'align': 'center'},
    ]


def _label_totales_por_moneda(valores):
    if not valores:
        return '0.00'
    partes = []
    for moneda in sorted(valores):
        partes.append(f'{moneda} {_format_money(valores[moneda], moneda)}')
    return ' · '.join(partes)


def _build_summary(rows):
    total = defaultdict(lambda: Decimal('0.00'))
    total_por_origen = defaultdict(lambda: Decimal('0.00'))
    cantidad_por_origen = defaultdict(int)
    vencidas = 0
    hoy = 0
    proximas = 0
    sin_vencimiento = 0
    parciales = 0

    for row in rows:
        pendiente = _decimal(row.get('monto_pendiente'))
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        fuente = row.get('fuente_codigo') or 'OTRO'
        prioridad = row.get('prioridad_codigo')
        estado = str(row.get('estado_codigo') or '').upper()

        total[moneda] += pendiente
        total_por_origen[fuente] += pendiente
        cantidad_por_origen[fuente] += 1

        if not row.get('fecha'):
            sin_vencimiento += 1
        elif prioridad == 'CRITICA':
            vencidas += 1
        elif prioridad == 'ALTA':
            hoy += 1
        else:
            proximas += 1

        if estado == 'PARCIAL':
            parciales += 1

    monedas = sorted(total.keys())
    totales_por_moneda = []
    for moneda in monedas:
        monto = total[moneda]
        totales_por_moneda.append({
            'moneda_codigo': moneda,
            'total': float(monto),
            'total_label': _format_money(monto, moneda),
        })

    return {
        'cantidad': len(rows),
        'vencidas': vencidas,
        'hoy': hoy,
        'proximas': proximas,
        'sin_vencimiento': sin_vencimiento,
        'parciales': parciales,
        'moneda_unica': monedas[0] if len(monedas) == 1 else '',
        'total_pendiente_label': _label_totales_por_moneda(total),
        'totales_por_moneda': totales_por_moneda,
        'cantidad_compromisos': cantidad_por_origen.get('COMPROMISO', 0),
        'cantidad_documentos': cantidad_por_origen.get('DOCUMENTO', 0),
        'cantidad_facturas': cantidad_por_origen.get('FACTURA', 0),
        'total_compromisos_label': _format_money(total_por_origen.get('COMPROMISO', Decimal('0.00')), MONEDA_BASE),
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Total pendiente', 'value': summary.get('total_pendiente_label'), 'note': 'Por moneda', 'kind': 'total'},
        {'label': 'Vencidas', 'value': summary.get('vencidas', 0), 'note': 'Atención crítica', 'kind': 'critical'},
        {'label': 'Sin vencimiento', 'value': summary.get('sin_vencimiento', 0), 'note': 'Sin fecha definida', 'kind': 'high'},
        {'label': 'Parciales', 'value': summary.get('parciales', 0), 'note': 'Con cobros aplicados', 'kind': 'group'},
        {'label': 'Registros', 'value': summary.get('cantidad', 0), 'note': 'Pendientes', 'kind': 'group'},
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
        'empty_title': 'No hay cartera por cobrar para los filtros seleccionados',
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
        ('prioridad', 'Prioridad', 15),
        ('fecha_label', 'Vencimiento', 16),
        ('dias_label', 'Situación', 18),
        ('origen', 'Origen', 30),
        ('referencia', 'Referencia', 24),
        ('cliente', 'Cliente', 34),
        ('cliente_doc', 'NIT/CI', 16),
        ('detalle', 'Detalle', 45),
        ('unidad', 'Unidad', 28),
        ('cuenta', 'Cuenta cartera', 34),
        ('estado', 'Estado', 14),
        ('moneda_codigo', 'Moneda', 10),
        ('monto_total', 'Total', 16),
        ('monto_aplicado', 'Cobrado', 16),
        ('monto_pendiente', 'Pendiente', 16),
        ('observacion', 'Observación', 34),
    ]


def excel_summary_text(summary):
    return (
        f"Total pendiente: {summary.get('total_pendiente_label', '')} · "
        f"Vencidas: {summary.get('vencidas', 0)} · "
        f"Sin vencimiento: {summary.get('sin_vencimiento', 0)} · "
        f"Registros: {summary.get('cantidad', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 20, 'align': 'center'},
        {'label': 'Venc.', 'width': 20, 'align': 'center'},
        {'label': 'Origen', 'width': 34, 'align': 'left'},
        {'label': 'Referencia', 'width': 28, 'align': 'left'},
        {'label': 'Cliente', 'width': 48, 'align': 'left'},
        {'label': 'Mon.', 'width': 12, 'align': 'center'},
        {'label': 'Total', 'width': 28, 'align': 'right'},
        {'label': 'Cobrado', 'width': 28, 'align': 'right'},
        {'label': 'Pendiente', 'width': 28, 'align': 'right'},
        {'label': 'Estado', 'width': 18, 'align': 'center'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['prioridad'],
            item['fecha_label'],
            item['origen'],
            item['referencia'],
            item['cliente'],
            item['moneda_codigo'],
            item['monto_total_label'],
            item['monto_aplicado_label'],
            item['monto_pendiente_label'],
            item['estado'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', '', '', '', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} registros. Use Excel para el detalle completo.', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Total pendiente: {summary.get('total_pendiente_label', '')}. "
        f"Vencidas: {summary.get('vencidas', 0)}. "
        f"Sin vencimiento: {summary.get('sin_vencimiento', 0)}. "
        f"Registros: {summary.get('cantidad', 0)}."
    )
