# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Cartera por cliente
# ============================================================

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from modules.reportes_rapidos.core.catalogos import unidad_label as _unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN, MONEDA_BASE
from modules.reportes_rapidos.core.formatos import dias_label as _dias_label
from modules.reportes_rapidos.core.formatos import format_money as _format_money
from modules.reportes_rapidos.core.monedas import aplicar_contexto_monetario
from modules.reportes_rapidos.core.utils import date_label as _date_label
from modules.reportes_rapidos.core.utils import decimal_value as _decimal
from modules.reportes_rapidos.reports import cuentas_por_cobrar_pendientes as cartera_base


REPORT_ID = 'cuentas_por_cobrar_por_cliente'
TITLE = 'Cartera por cliente'
DESCRIPTION = 'Pendientes de cobro agrupados por cliente.'
WORKSHEET_TITLE = 'Cartera por cliente'
FILE_SLUG = 'cartera_por_cliente'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-users'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha base'
FILTER_GROUP_LABEL = 'Origen'
DEFAULT_ALCANCE = cartera_base.DEFAULT_ALCANCE
DEFAULT_GRUPO = cartera_base.DEFAULT_GRUPO
MONEY_FIELDS = {'monto_total', 'monto_aplicado', 'monto_pendiente'}

ALCANCES = cartera_base.ALCANCES
GRUPOS = cartera_base.GRUPOS

HELP_TITLE = 'Cartera por cliente'
HELP_INTRO = 'Agrupa la cartera pendiente por cliente.'
HELP_ITEMS = [
    'Incluye compromisos por cobrar, documentos por cobrar y facturas electrónicas contabilizadas con saldo.',
    'Un cliente puede aparecer en más de una línea si tiene saldos en distintas monedas.',
    'Los pendientes sin vencimiento no se consideran vencidos.',
    'Los totales se separan por moneda; no se mezclan importes de monedas distintas.',
]


validate_filters = cartera_base.validate_filters


def _descripcion_periodo(filtros):
    return cartera_base._descripcion_periodo(filtros)


def _priority_from_group(first_due, fecha_base, vencidas, hoy_count, sin_vencimiento):
    if int(vencidas or 0) > 0:
        return 'CRITICA', 'Vencida', None, 0
    if int(hoy_count or 0) > 0:
        return 'ALTA', 'Hoy', 0, 1
    if isinstance(first_due, date):
        dias = (first_due - fecha_base).days
        if dias <= 7:
            return 'MEDIA', _dias_label(dias), dias, 2
        return 'BAJA', _dias_label(dias), dias, 4
    if int(sin_vencimiento or 0) > 0:
        return 'BAJA', 'Sin vencimiento', None, 3
    return 'BAJA', 'Sin pendientes', None, 5


def _totales_label(valores):
    if not valores:
        return '0.00'
    partes = []
    for moneda in sorted(valores):
        partes.append(f'{moneda} {_format_money(valores[moneda], moneda)}')
    return ' · '.join(partes)


def _fuente_label(codigo):
    valores = {
        'COMPROMISO': 'Compromisos',
        'DOCUMENTO': 'Documentos',
        'FACTURA': 'Facturas',
    }
    return valores.get(str(codigo or '').upper(), codigo or 'Otro')


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    # Para agrupar por cliente no se puede cortar la fuente antes de sumar, porque se perderian
    # saldos de clientes con muchos documentos. Se toma el limite exportable y luego se limita la salida.
    detalle = cartera_base.fetch_cartera_rows(filtros, limit_rows=MAX_ROWS_EXPORT)
    grupos = {}
    fecha_base = filtros['fecha_base']

    for item in detalle:
        cliente = item.get('cliente') or 'Sin cliente'
        cliente_doc = item.get('cliente_doc') or ''
        moneda = item.get('moneda_codigo') or MONEDA_BASE
        key = (cliente.strip().upper(), cliente_doc.strip().upper(), moneda)

        if key not in grupos:
            grupos[key] = {
                'cliente': cliente,
                'cliente_doc': cliente_doc,
                'moneda_codigo': moneda,
                'monto_total': Decimal('0.00'),
                'monto_aplicado': Decimal('0.00'),
                'monto_pendiente': Decimal('0.00'),
                'registros': 0,
                'vencidas': 0,
                'hoy': 0,
                'proximas': 0,
                'sin_vencimiento': 0,
                'parciales': 0,
                'compromisos': 0,
                'documentos': 0,
                'facturas': 0,
                'fuentes': set(),
                'unidades': set(),
                'primer_vencimiento': None,
                'ultimo_vencimiento': None,
            }

        grupo = grupos[key]
        grupo['monto_total'] += _decimal(item.get('monto_total'))
        grupo['monto_aplicado'] += _decimal(item.get('monto_aplicado'))
        grupo['monto_pendiente'] += _decimal(item.get('monto_pendiente'))
        grupo['registros'] += 1

        fuente = str(item.get('fuente_codigo') or '').upper()
        if fuente:
            grupo['fuentes'].add(_fuente_label(fuente))
        if fuente == 'COMPROMISO':
            grupo['compromisos'] += 1
        elif fuente == 'DOCUMENTO':
            grupo['documentos'] += 1
        elif fuente == 'FACTURA':
            grupo['facturas'] += 1

        unidad = item.get('unidad') or ''
        if unidad:
            grupo['unidades'].add(unidad)

        estado = str(item.get('estado_codigo') or item.get('estado') or '').upper()
        if estado == 'PARCIAL':
            grupo['parciales'] += 1

        prioridad = str(item.get('prioridad_codigo') or '').upper()
        fecha_txt = item.get('fecha') or ''
        fecha_ref = None
        if fecha_txt:
            try:
                fecha_ref = date.fromisoformat(fecha_txt)
            except ValueError:
                fecha_ref = None

        if not fecha_ref:
            grupo['sin_vencimiento'] += 1
        elif prioridad == 'CRITICA':
            grupo['vencidas'] += 1
        elif prioridad == 'ALTA':
            grupo['hoy'] += 1
        else:
            grupo['proximas'] += 1

        if fecha_ref:
            if grupo['primer_vencimiento'] is None or fecha_ref < grupo['primer_vencimiento']:
                grupo['primer_vencimiento'] = fecha_ref
            if grupo['ultimo_vencimiento'] is None or fecha_ref > grupo['ultimo_vencimiento']:
                grupo['ultimo_vencimiento'] = fecha_ref

    rows = []
    for grupo in grupos.values():
        prioridad_codigo, prioridad, dias, orden_prioridad = _priority_from_group(
            grupo['primer_vencimiento'],
            fecha_base,
            grupo['vencidas'],
            grupo['hoy'],
            grupo['sin_vencimiento'],
        )
        total = grupo['monto_total']
        aplicado = grupo['monto_aplicado']
        pendiente = grupo['monto_pendiente']
        moneda = grupo['moneda_codigo']
        fuentes = ', '.join(sorted(grupo['fuentes']))
        unidades = ', '.join(sorted(grupo['unidades']))
        primer = grupo['primer_vencimiento']
        ultimo = grupo['ultimo_vencimiento']

        rows.append({
            'prioridad_codigo': prioridad_codigo,
            'prioridad': prioridad,
            'orden_prioridad': orden_prioridad,
            'cliente': grupo['cliente'],
            'cliente_doc': grupo['cliente_doc'],
            'moneda_codigo': moneda,
            'primer_vencimiento': primer.isoformat() if isinstance(primer, date) else '',
            'primer_vencimiento_label': _date_label(primer) if isinstance(primer, date) else 'Sin vencimiento',
            'ultimo_vencimiento': ultimo.isoformat() if isinstance(ultimo, date) else '',
            'ultimo_vencimiento_label': _date_label(ultimo) if isinstance(ultimo, date) else 'Sin vencimiento',
            'dias': dias,
            'dias_label': _dias_label(dias) if dias is not None else 'Sin fecha',
            'origenes': fuentes or 'Sin origen',
            'unidades': unidades,
            'registros': grupo['registros'],
            'compromisos': grupo['compromisos'],
            'documentos': grupo['documentos'],
            'facturas': grupo['facturas'],
            'vencidas': grupo['vencidas'],
            'hoy': grupo['hoy'],
            'proximas': grupo['proximas'],
            'sin_vencimiento': grupo['sin_vencimiento'],
            'parciales': grupo['parciales'],
            'monto_total': float(total),
            'monto_total_label': _format_money(total, moneda),
            'monto_aplicado': float(aplicado),
            'monto_aplicado_label': _format_money(aplicado, moneda),
            'monto_pendiente': float(pendiente),
            'monto_pendiente_label': _format_money(pendiente, moneda),
        })

    rows.sort(key=lambda row: (
        row.get('orden_prioridad', 9),
        row.get('primer_vencimiento') or '9999-12-31',
        -_decimal(row.get('monto_pendiente')),
        row.get('cliente') or '',
        row.get('moneda_codigo') or '',
    ))

    for idx, row in enumerate(rows[:limit_rows], start=1):
        row['nro'] = idx
    return rows[:limit_rows]


def display_columns():
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'cliente', 'label': 'Cliente', 'sub_key': 'cliente_doc', 'align': 'left', 'strong': True},
        {'key': 'moneda_codigo', 'label': 'Moneda', 'align': 'center'},
        {'key': 'primer_vencimiento_label', 'label': 'Próx. venc.', 'sub_key': 'dias_label', 'align': 'center'},
        {'key': 'origenes', 'label': 'Orígenes', 'align': 'left'},
        {'key': 'registros', 'label': 'Registros', 'align': 'center'},
        {'key': 'vencidas', 'label': 'Vencidas', 'align': 'center'},
        {'key': 'sin_vencimiento', 'label': 'Sin venc.', 'align': 'center'},
        {'key': 'parciales', 'label': 'Parciales', 'align': 'center'},
        {'key': 'unidades', 'label': 'Unidades', 'align': 'left'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
        {'key': 'monto_aplicado', 'label': 'Cobrado', 'type': 'money', 'align': 'right'},
        {'key': 'monto_pendiente', 'label': 'Pendiente', 'type': 'money', 'align': 'right'},
    ]


def _build_summary(rows):
    total = defaultdict(lambda: Decimal('0.00'))
    aplicado = defaultdict(lambda: Decimal('0.00'))
    clientes_unicos = set()
    vencidas = 0
    sin_vencimiento = 0
    parciales = 0
    registros = 0
    compromisos = 0
    documentos = 0
    facturas = 0

    for row in rows:
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        total[moneda] += _decimal(row.get('monto_pendiente'))
        aplicado[moneda] += _decimal(row.get('monto_aplicado'))
        clientes_unicos.add((row.get('cliente') or '', row.get('cliente_doc') or ''))
        vencidas += int(row.get('vencidas') or 0)
        sin_vencimiento += int(row.get('sin_vencimiento') or 0)
        parciales += int(row.get('parciales') or 0)
        registros += int(row.get('registros') or 0)
        compromisos += int(row.get('compromisos') or 0)
        documentos += int(row.get('documentos') or 0)
        facturas += int(row.get('facturas') or 0)

    monedas = sorted(total.keys())
    return {
        'cantidad': len(rows),
        'clientes': len(clientes_unicos),
        'registros': registros,
        'vencidas': vencidas,
        'sin_vencimiento': sin_vencimiento,
        'parciales': parciales,
        'compromisos': compromisos,
        'documentos': documentos,
        'facturas': facturas,
        'moneda_unica': monedas[0] if len(monedas) == 1 else '',
        'total_pendiente_label': _totales_label(total),
        'total_aplicado_label': _totales_label(aplicado),
        'totales_por_moneda': [
            {
                'moneda_codigo': moneda,
                'total_pendiente': float(total[moneda]),
                'total_pendiente_label': _format_money(total[moneda], moneda),
                'total_aplicado': float(aplicado[moneda]),
                'total_aplicado_label': _format_money(aplicado[moneda], moneda),
            }
            for moneda in monedas
        ],
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Total pendiente', 'value': summary.get('total_pendiente_label'), 'note': 'Por moneda', 'kind': 'total'},
        {'label': 'Clientes', 'value': summary.get('clientes', 0), 'note': 'Con cartera', 'kind': 'group'},
        {'label': 'Vencidas', 'value': summary.get('vencidas', 0), 'note': 'Registros críticos', 'kind': 'critical'},
        {'label': 'Sin vencimiento', 'value': summary.get('sin_vencimiento', 0), 'note': 'Sin fecha definida', 'kind': 'high'},
        {'label': 'Registros', 'value': summary.get('registros', 0), 'note': 'Pendientes agrupados', 'kind': 'group'},
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
        'empty_title': 'No hay cartera por cliente para los filtros seleccionados',
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
        ('cliente', 'Cliente', 36),
        ('cliente_doc', 'NIT/CI', 16),
        ('moneda_codigo', 'Moneda', 10),
        ('primer_vencimiento_label', 'Prox. vencimiento', 16),
        ('ultimo_vencimiento_label', 'Ultimo vencimiento', 16),
        ('dias_label', 'Situacion', 18),
        ('origenes', 'Origenes', 28),
        ('unidades', 'Unidades', 36),
        ('registros', 'Registros', 12),
        ('compromisos', 'Compromisos', 12),
        ('documentos', 'Documentos', 12),
        ('facturas', 'Facturas', 12),
        ('vencidas', 'Vencidas', 12),
        ('hoy', 'Hoy', 10),
        ('proximas', 'Proximas', 12),
        ('sin_vencimiento', 'Sin vencimiento', 16),
        ('parciales', 'Parciales', 12),
        ('monto_total', 'Total', 16),
        ('monto_aplicado', 'Cobrado', 16),
        ('monto_pendiente', 'Pendiente', 16),
    ]


def excel_summary_text(summary):
    return (
        f"Total pendiente: {summary.get('total_pendiente_label', '')} · "
        f"Clientes: {summary.get('clientes', 0)} · "
        f"Vencidas: {summary.get('vencidas', 0)} · "
        f"Registros: {summary.get('registros', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 20, 'align': 'center'},
        {'label': 'Cliente', 'width': 54, 'align': 'left'},
        {'label': 'Mon.', 'width': 12, 'align': 'center'},
        {'label': 'Prox. venc.', 'width': 22, 'align': 'center'},
        {'label': 'Origenes', 'width': 36, 'align': 'left'},
        {'label': 'Reg.', 'width': 13, 'align': 'center'},
        {'label': 'Venc.', 'width': 14, 'align': 'center'},
        {'label': 'Sin venc.', 'width': 17, 'align': 'center'},
        {'label': 'Total', 'width': 26, 'align': 'right'},
        {'label': 'Cobrado', 'width': 26, 'align': 'right'},
        {'label': 'Pendiente', 'width': 28, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['prioridad'],
            item['cliente'],
            item['moneda_codigo'],
            item['primer_vencimiento_label'],
            item['origenes'],
            item['registros'],
            item['vencidas'],
            item['sin_vencimiento'],
            item['monto_total_label'],
            item['monto_aplicado_label'],
            item['monto_pendiente_label'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} clientes. Use Excel para el detalle completo.', '', '', '', '', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Total pendiente: {summary.get('total_pendiente_label', '')}. "
        f"Clientes: {summary.get('clientes', 0)}. "
        f"Vencidas: {summary.get('vencidas', 0)}. "
        f"Registros: {summary.get('registros', 0)}."
    )
