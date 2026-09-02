# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Agenda financiera
# ============================================================

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from database.db_manager import DatabaseManager
from modules.reportes_rapidos.core.catalogos import unidad_label as _unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_PDF, MAX_ROWS_SCREEN, MONEDA_BASE
from modules.reportes_rapidos.core.formatos import format_money as _format_money
from modules.reportes_rapidos.core.monedas import aplicar_contexto_monetario
from modules.reportes_rapidos.core.utils import clean as _clean
from modules.reportes_rapidos.core.utils import date_label as _date_label
from modules.reportes_rapidos.core.utils import decimal_value as _decimal
from modules.reportes_rapidos.core.utils import parse_date as _parse_date
from modules.reportes_rapidos.core.utils import parse_optional_int as _parse_optional_int


REPORT_ID = 'agenda_financiera_hoy'
TITLE = 'Agenda financiera'
DESCRIPTION = 'Pendientes por fecha, vencimiento o sin vencimiento.'
WORKSHEET_TITLE = 'Agenda financiera'
FILE_SLUG = 'agenda_financiera'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-calendar-day'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha base'
FILTER_GROUP_LABEL = 'Tipo'
DEFAULT_ALCANCE = 'hoy'
DEFAULT_GRUPO = ''
MONEY_FIELDS = {'monto_total', 'monto_registrado', 'monto_pendiente'}

ALCANCES = {
    'hoy': 'Hoy',
    'manana': 'Mañana',
    'proximos_7': 'Próximos 7 días',
    'proximos_30': 'Próximos 30 días',
    'sin_vencimiento': 'Sin vencimiento',
    'rango': 'Rango personalizado',
}

GRUPOS = {
    '': 'Pagar y cobrar',
    'PAGAR': 'Solo pagos',
    'COBRAR': 'Solo cobros',
}


HELP_TITLE = 'Agenda financiera'
HELP_INTRO = 'Consolida pendientes financieros por fecha de atención.'
HELP_ITEMS = [
    'Incluye compromisos por pagar y por cobrar con vencimiento en el periodo filtrado.',
    'Incluye documentos por cobrar con vencimiento en el periodo filtrado.',
    'La opción Sin vencimiento muestra facturas electrónicas por cobrar y documentos sin fecha de vencimiento.',
    'No suma documentos pendientes como dinero real; solo muestra lo gestionable.',
]


def validate_filters(args):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or DEFAULT_ALCANCE
    if alcance not in ALCANCES:
        raise ValueError('El periodo seleccionado no es válido.')

    grupo = _clean(args.get('grupo'))
    if grupo not in GRUPOS:
        raise ValueError('El tipo seleccionado no es válido.')

    fecha_base = _parse_date(args.get('fecha_base'), FILTER_DATE_LABEL, default=hoy)
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if alcance == 'hoy':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
        incluir_sin_vencimiento = False
    elif alcance == 'manana':
        fecha_desde = fecha_base + timedelta(days=1)
        fecha_hasta = fecha_desde
        incluir_sin_vencimiento = False
    elif alcance == 'proximos_7':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=7)
        incluir_sin_vencimiento = False
    elif alcance == 'proximos_30':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base + timedelta(days=30)
        incluir_sin_vencimiento = False
    elif alcance == 'sin_vencimiento':
        fecha_desde = fecha_base
        fecha_hasta = fecha_base
        incluir_sin_vencimiento = True
    else:
        fecha_desde = _parse_date(args.get('fecha_desde'), 'Fecha desde')
        fecha_hasta = _parse_date(args.get('fecha_hasta'), 'Fecha hasta')
        if fecha_desde > fecha_hasta:
            raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')
        incluir_sin_vencimiento = False

    return {
        'alcance': alcance,
        'alcance_label': ALCANCES[alcance],
        'grupo': grupo,
        'grupo_label': GRUPOS[grupo],
        'fecha_base': fecha_base,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
        'incluir_sin_vencimiento': incluir_sin_vencimiento,
    }


def _descripcion_periodo(filtros):
    if filtros['alcance'] == 'sin_vencimiento':
        return 'Pendientes sin vencimiento definido'
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


def _date_or_sin_vencimiento(value):
    return _date_label(value) if value else 'Sin vencimiento'


def _period_condition(alias, filtros, params):
    if filtros['incluir_sin_vencimiento']:
        return f'{alias}.fecha_vencimiento IS NULL'
    params.extend([filtros['fecha_desde'], filtros['fecha_hasta']])
    return f'{alias}.fecha_vencimiento BETWEEN %s AND %s'


def _fetch_compromisos(db, filtros, limit_rows):
    if filtros['incluir_sin_vencimiento']:
        return []
    if filtros['grupo'] not in ('', 'PAGAR', 'COBRAR'):
        return []

    params = [filtros['fecha_desde'], filtros['fecha_hasta'], filtros['grupo'], filtros['grupo']]
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND c.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)

    return db.execute_query(
        f"""
        SELECT
            c.tipo::text AS tipo_codigo,
            d.fecha_vencimiento::date AS fecha_ref,
            c.codigo::text AS referencia,
            COALESCE(a.nombre, c.nombre, 'Sin contraparte')::text AS contraparte,
            COALESCE(NULLIF(c.descripcion, ''), c.nombre, 'Compromiso financiero')::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            %s::text AS moneda_codigo,
            COALESCE(d.monto_programado, 0)::numeric(18,2) AS monto_total,
            COALESCE(d.monto_registrado, 0)::numeric(18,2) AS monto_registrado,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)::numeric(18,2) AS monto_pendiente,
            d.estado::text AS estado,
            'Compromiso'::text AS origen,
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
          AND d.fecha_vencimiento BETWEEN %s AND %s
          AND (%s = '' OR c.tipo = %s)
          {unidad_sql}
        ORDER BY d.fecha_vencimiento ASC, c.tipo ASC, contraparte ASC, c.codigo ASC, d.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_documentos_cobrar(db, filtros, limit_rows):
    if filtros['grupo'] == 'PAGAR':
        return []

    params = []
    fecha_condition = _period_condition('d', filtros, params)
    unidad_sql = ''
    if filtros['unidad_negocio_id']:
        unidad_sql = 'AND d.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])
    params.append(limit_rows)

    return db.execute_query(
        f"""
        SELECT
            'COBRAR'::text AS tipo_codigo,
            d.fecha_vencimiento::date AS fecha_ref,
            (d.tipo_documento::text || ' ' || d.numero_documento::text) AS referencia,
            COALESCE(NULLIF(d.cliente_nombre, ''), a.nombre, 'Sin cliente')::text AS contraparte,
            COALESCE(NULLIF(d.descripcion, ''), d.referencia_externa, d.numero_documento, 'Documento por cobrar')::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(d.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(d.importe_total, 0)::numeric(18,2) AS monto_total,
            COALESCE(d.importe_cobrado, 0)::numeric(18,2) AS monto_registrado,
            GREATEST(COALESCE(d.saldo_pendiente, 0), 0)::numeric(18,2) AS monto_pendiente,
            d.estado::text AS estado,
            d.origen_documento::text AS origen_codigo,
            d.tipo_documento::text AS tipo_documento,
            'Cobrar'::text AS accion,
            2::int AS orden_fuente
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.auxiliar a ON a.id = d.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        WHERE d.activo = TRUE
          AND d.estado IN ('PENDIENTE', 'PARCIAL')
          AND GREATEST(COALESCE(d.saldo_pendiente, 0), 0) > 0
          AND {fecha_condition}
          {unidad_sql}
        ORDER BY COALESCE(d.fecha_vencimiento, d.fecha_documento) ASC, d.numero_documento ASC, d.id ASC
        LIMIT %s
        """,
        tuple([MONEDA_BASE, *params]),
    )


def _fetch_facturas_sin_vencimiento(db, filtros, limit_rows):
    if not filtros['incluir_sin_vencimiento'] or filtros['grupo'] == 'PAGAR':
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
            'COBRAR'::text AS tipo_codigo,
            NULL::date AS fecha_ref,
            ('FACTURA ' || fe.numero_factura::text) AS referencia,
            COALESCE(NULLIF(fe.nombre_cliente, ''), a.nombre, 'Sin cliente')::text AS contraparte,
            ('Emitida ' || TO_CHAR(fe.fecha_emision, 'DD/MM/YYYY'))::text AS detalle,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '')::text AS unidad,
            COALESCE(fe.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(fe.importe_total, 0)::numeric(18,2) AS monto_total,
            (COALESCE(apps.total_aplicado, 0) + COALESCE(reg.total_regularizado, 0))::numeric(18,2) AS monto_registrado,
            GREATEST(
                COALESCE(fe.importe_total, 0)
                - COALESCE(apps.total_aplicado, 0)
                - COALESCE(reg.total_regularizado, 0),
                0
            )::numeric(18,2) AS monto_pendiente,
            fe.estado::text AS estado,
            'Factura electrónica'::text AS origen,
            'Cobrar'::text AS accion,
            3::int AS orden_fuente
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.auxiliar a ON a.id = fe.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
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


def _map_row(row, idx):
    tipo_codigo = row.get('tipo_codigo') or ''
    tipo_label = 'Pagar' if tipo_codigo == 'PAGAR' else 'Cobrar'
    fecha_ref = row.get('fecha_ref')
    total = _decimal(row.get('monto_total'))
    registrado = _decimal(row.get('monto_registrado'))
    pendiente = _decimal(row.get('monto_pendiente'))
    moneda = row.get('moneda_codigo') or MONEDA_BASE

    origen = row.get('origen') or _origen_documento_label(row.get('origen_codigo'))
    if row.get('tipo_documento'):
        origen = f"{origen} · {_tipo_documento_label(row.get('tipo_documento'))}"

    return {
        'nro': idx,
        'tipo_codigo': tipo_codigo,
        'tipo': tipo_label,
        'fecha': fecha_ref.isoformat() if isinstance(fecha_ref, date) else '',
        'fecha_label': _date_or_sin_vencimiento(fecha_ref),
        'origen': origen,
        'referencia': row.get('referencia') or '',
        'contraparte': row.get('contraparte') or '',
        'detalle': row.get('detalle') or '',
        'unidad': row.get('unidad') or '',
        'moneda_codigo': moneda,
        'monto_total': float(total),
        'monto_total_label': _format_money(total, moneda),
        'monto_registrado': float(registrado),
        'monto_registrado_label': _format_money(registrado, moneda),
        'monto_pendiente': float(pendiente),
        'monto_pendiente_label': _format_money(pendiente, moneda),
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

    mapped = [_map_row(row, idx) for idx, row in enumerate(rows_raw, start=1)]
    mapped.sort(key=lambda row: (
        row.get('fecha') or '9999-12-31',
        0 if row.get('tipo_codigo') == 'PAGAR' else 1,
        row.get('orden_fuente') or 9,
        row.get('contraparte') or '',
        row.get('referencia') or '',
    ))
    for idx, row in enumerate(mapped[:limit_rows], start=1):
        row['nro'] = idx
    return mapped[:limit_rows]


def display_columns():
    return [
        {'key': 'tipo', 'label': 'Tipo', 'type': 'badge', 'code_key': 'tipo_codigo', 'align': 'center'},
        {'key': 'fecha_label', 'label': 'Vencimiento', 'align': 'center'},
        {'key': 'origen', 'label': 'Origen', 'align': 'left'},
        {'key': 'referencia', 'label': 'Referencia', 'align': 'left'},
        {'key': 'contraparte', 'label': 'Cliente / proveedor', 'align': 'left'},
        {'key': 'detalle', 'label': 'Detalle', 'sub_key': 'unidad', 'align': 'left'},
        {'key': 'moneda_codigo', 'label': 'Moneda', 'align': 'center'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
        {'key': 'monto_registrado', 'label': 'Aplicado', 'type': 'money', 'align': 'right'},
        {'key': 'monto_pendiente', 'label': 'Pendiente', 'type': 'money', 'align': 'right'},
        {'key': 'estado', 'label': 'Estado', 'align': 'center'},
        {'key': 'accion', 'label': 'Acción', 'align': 'center'},
    ]


def _label_totales_por_moneda(valores):
    if not valores:
        return '0.00'
    partes = []
    for moneda in sorted(valores):
        partes.append(f"{moneda} {_format_money(valores[moneda], moneda)}")
    return ' · '.join(partes)


def _build_summary(rows):
    total_pagar = defaultdict(lambda: Decimal('0.00'))
    total_cobrar = defaultdict(lambda: Decimal('0.00'))
    cant_pagar = 0
    cant_cobrar = 0
    sin_vencimiento = 0

    for row in rows:
        pendiente = _decimal(row.get('monto_pendiente'))
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        if not row.get('fecha'):
            sin_vencimiento += 1
        if row.get('tipo_codigo') == 'PAGAR':
            total_pagar[moneda] += pendiente
            cant_pagar += 1
        elif row.get('tipo_codigo') == 'COBRAR':
            total_cobrar[moneda] += pendiente
            cant_cobrar += 1

    monedas = sorted(set(total_pagar.keys()) | set(total_cobrar.keys()))
    totales_por_moneda = []
    for moneda in monedas:
        cobrar = total_cobrar[moneda]
        pagar = total_pagar[moneda]
        neto = cobrar - pagar
        totales_por_moneda.append({
            'moneda_codigo': moneda,
            'total_cobrar': float(cobrar),
            'total_pagar': float(pagar),
            'total': float(neto),
            'total_cobrar_label': _format_money(cobrar, moneda),
            'total_pagar_label': _format_money(pagar, moneda),
            'saldo_neto_label': _format_money(neto, moneda),
        })

    moneda_unica = monedas[0] if len(monedas) == 1 else ''
    total_cobrar_label = _label_totales_por_moneda(total_cobrar)
    total_pagar_label = _label_totales_por_moneda(total_pagar)
    saldo_neto_label = _label_totales_por_moneda({item['moneda_codigo']: _decimal(item['total']) for item in totales_por_moneda})

    return {
        'cantidad': len(rows),
        'cant_pagar': cant_pagar,
        'cant_cobrar': cant_cobrar,
        'sin_vencimiento': sin_vencimiento,
        'moneda_unica': moneda_unica,
        'total_pagar_label': total_pagar_label,
        'total_cobrar_label': total_cobrar_label,
        'saldo_neto_label': saldo_neto_label,
        'totales_por_moneda': totales_por_moneda,
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Por cobrar', 'value': summary.get('total_cobrar_label'), 'note': f"{summary.get('cant_cobrar', 0)} pendiente(s)", 'kind': 'total'},
        {'label': 'Por pagar', 'value': summary.get('total_pagar_label'), 'note': f"{summary.get('cant_pagar', 0)} pendiente(s)", 'kind': 'high'},
        {'label': 'Neto', 'value': summary.get('saldo_neto_label'), 'note': 'Cobrar - pagar', 'kind': 'group'},
        {'label': 'Sin vencimiento', 'value': summary.get('sin_vencimiento', 0), 'note': 'Pendientes sin fecha', 'kind': 'group'},
        {'label': 'Registros', 'value': summary.get('cantidad', 0), 'note': 'Resultado filtrado', 'kind': 'group'},
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
        'empty_title': 'No hay pendientes financieros para los filtros seleccionados',
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
        ('tipo', 'Tipo', 13),
        ('fecha_label', 'Vencimiento', 16),
        ('origen', 'Origen', 28),
        ('referencia', 'Referencia', 22),
        ('contraparte', 'Cliente / proveedor', 34),
        ('detalle', 'Detalle', 45),
        ('unidad', 'Unidad', 28),
        ('estado', 'Estado', 14),
        ('moneda_codigo', 'Moneda', 10),
        ('monto_total', 'Total', 16),
        ('monto_registrado', 'Aplicado', 16),
        ('monto_pendiente', 'Pendiente', 16),
        ('accion', 'Acción', 14),
    ]


def excel_summary_text(summary):
    return (
        f"Por cobrar: {summary.get('total_cobrar_label', '')} · "
        f"Por pagar: {summary.get('total_pagar_label', '')} · "
        f"Neto: {summary.get('saldo_neto_label', '')} · "
        f"Registros: {summary.get('cantidad', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Tipo', 'width': 16, 'align': 'center'},
        {'label': 'Venc.', 'width': 20, 'align': 'center'},
        {'label': 'Origen', 'width': 34, 'align': 'left'},
        {'label': 'Referencia', 'width': 28, 'align': 'left'},
        {'label': 'Cliente / Proveedor', 'width': 44, 'align': 'left'},
        {'label': 'Mon.', 'width': 12, 'align': 'center'},
        {'label': 'Pendiente', 'width': 28, 'align': 'right'},
        {'label': 'Estado', 'width': 18, 'align': 'center'},
        {'label': 'Acción', 'width': 18, 'align': 'center'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['tipo'],
            item['fecha_label'],
            item['origen'],
            item['referencia'],
            item['contraparte'],
            item['moneda_codigo'],
            item['monto_pendiente_label'],
            item['estado'],
            item['accion'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', '', '', '', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} registros. Use Excel para el detalle completo.', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Por cobrar: {summary.get('total_cobrar_label', '')}. "
        f"Por pagar: {summary.get('total_pagar_label', '')}. "
        f"Neto: {summary.get('saldo_neto_label', '')}."
    )
