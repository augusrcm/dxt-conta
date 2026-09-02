# ============================================================
# DXT CONTA - Reportes Rapidos
# Reporte: Cartera por unidad/origen
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
from modules.reportes_rapidos.reports.cuentas_por_cobrar_pendientes import (
    ALCANCES as CARTERA_ALCANCES,
    GRUPOS as CARTERA_GRUPOS,
    _descripcion_periodo as _descripcion_cartera_periodo,
    fetch_cartera_rows,
    validate_filters as _validate_cartera_filters,
)


REPORT_ID = 'cuentas_por_cobrar_por_unidad_rubro'
TITLE = 'Cartera por unidad/origen'
DESCRIPTION = 'Cartera cobrable consolidada por unidad, origen y cuenta.'
WORKSHEET_TITLE = 'Cartera unidad origen'
FILE_SLUG = 'cartera_por_unidad_origen'
PDF_ORIENTATION = 'landscape'
ICON = 'fas fa-layer-group'

FILTER_ALCANCE_LABEL = 'Periodo'
FILTER_DATE_LABEL = 'Fecha base'
FILTER_GROUP_LABEL = 'Origen'
DEFAULT_ALCANCE = 'todas'
DEFAULT_GRUPO = ''
MONEY_FIELDS = {'monto_total', 'monto_aplicado', 'monto_pendiente'}

ALCANCES = dict(CARTERA_ALCANCES)
GRUPOS = dict(CARTERA_GRUPOS)

HELP_TITLE = 'Cartera por unidad/origen'
HELP_INTRO = 'Agrupa la cartera pendiente por unidad, origen y cuenta.'
HELP_ITEMS = [
    'Incluye compromisos por cobrar, documentos por cobrar y facturas electrónicas pendientes.',
    'Agrupa por moneda para evitar totales mezclados.',
    'Los pendientes sin vencimiento se muestran solo en Toda la cartera o Sin vencimiento.',
]


def validate_filters(args):
    return _validate_cartera_filters(args)


def _descripcion_periodo(filtros):
    return _descripcion_cartera_periodo(filtros)


def _origen_grupo(row):
    fuente = str(row.get('fuente_codigo') or '').upper()
    origen = str(row.get('origen') or '').strip()

    if fuente == 'COMPROMISO':
        return 'COMPROMISO', 'Compromisos'
    if fuente == 'FACTURA':
        return 'FACTURA', 'Facturas electrónicas'
    if fuente == 'DOCUMENTO':
        origen_lower = origen.lower()
        if 'histórico' in origen_lower or 'historico' in origen_lower:
            return 'DOCUMENTO_HISTORICO', 'Documentos históricos'
        if 'vigente' in origen_lower:
            return 'DOCUMENTO_VIGENTE', 'Documentos vigentes'
        return 'DOCUMENTO', 'Documentos'
    return fuente or 'OTRO', origen or 'Otro'


def _prioridad_agregada(row):
    vencidas = int(row.get('vencidas') or 0)
    hoy = int(row.get('hoy') or 0)
    proximas_7 = int(row.get('proximas_7') or 0)
    proximo = row.get('proximo_vencimiento')
    fecha_base = row.get('_fecha_base')

    if vencidas > 0:
        return 'CRITICA', 'Vencida', 0
    if hoy > 0:
        return 'ALTA', 'Hoy', 1
    if proximas_7 > 0:
        return 'MEDIA', 'Próx. 7 días', 2
    if isinstance(proximo, date) and isinstance(fecha_base, date):
        dias = (proximo - fecha_base).days
        return 'BAJA', _dias_label(dias), 3
    return 'BAJA', 'Sin vencimiento', 4


def _fecha_sort(fecha_ref):
    if isinstance(fecha_ref, date):
        return fecha_ref.isoformat()
    return '9999-12-31'


def _cuenta_codigo(cuenta_label):
    cuenta = str(cuenta_label or '').strip()
    if ' · ' in cuenta:
        return cuenta.split(' · ', 1)[0].strip()
    return cuenta


def _agregar_rows(cartera_rows, filtros, limit_rows):
    grupos = {}
    fecha_base = filtros['fecha_base']

    for item in cartera_rows:
        moneda = item.get('moneda_codigo') or MONEDA_BASE
        unidad = item.get('unidad') or 'Sin unidad'
        origen_codigo, origen_label = _origen_grupo(item)
        cuenta = item.get('cuenta') or 'Sin cuenta cartera'
        cuenta_codigo = _cuenta_codigo(cuenta)
        key = (unidad, origen_codigo, origen_label, cuenta, moneda)

        if key not in grupos:
            grupos[key] = {
                'unidad': unidad,
                'origen_codigo': origen_codigo,
                'origen': origen_label,
                'cuenta': cuenta,
                'cuenta_codigo': cuenta_codigo,
                'moneda_codigo': moneda,
                'registros': 0,
                'clientes_set': set(),
                'clientes_lista_set': set(),
                'vencidas': 0,
                'hoy': 0,
                'proximas_7': 0,
                'sin_vencimiento': 0,
                'parciales': 0,
                'monto_total': Decimal('0.00'),
                'monto_aplicado': Decimal('0.00'),
                'monto_pendiente': Decimal('0.00'),
                'proximo_vencimiento': None,
                'ultimo_vencimiento': None,
                '_fecha_base': fecha_base,
            }

        grupo = grupos[key]
        total = _decimal(item.get('monto_total'))
        aplicado = _decimal(item.get('monto_aplicado'))
        pendiente = _decimal(item.get('monto_pendiente'))
        fecha_texto = item.get('fecha') or ''
        fecha_ref = None
        if fecha_texto:
            try:
                fecha_ref = date.fromisoformat(fecha_texto[:10])
            except ValueError:
                fecha_ref = None

        grupo['registros'] += 1
        grupo['monto_total'] += total
        grupo['monto_aplicado'] += aplicado
        grupo['monto_pendiente'] += pendiente

        cliente = item.get('cliente') or 'Sin cliente'
        cliente_doc = item.get('cliente_doc') or ''
        cliente_key = f'{cliente}|{cliente_doc}'
        grupo['clientes_set'].add(cliente_key)
        grupo['clientes_lista_set'].add(cliente)

        prioridad = item.get('prioridad_codigo')
        if not fecha_ref:
            grupo['sin_vencimiento'] += 1
        elif prioridad == 'CRITICA':
            grupo['vencidas'] += 1
        elif prioridad == 'ALTA':
            grupo['hoy'] += 1
        elif isinstance(fecha_ref, date) and (fecha_ref - fecha_base).days <= 7:
            grupo['proximas_7'] += 1

        if str(item.get('estado_codigo') or item.get('estado') or '').upper() == 'PARCIAL':
            grupo['parciales'] += 1

        if fecha_ref:
            actual_min = grupo['proximo_vencimiento']
            actual_max = grupo['ultimo_vencimiento']
            if actual_min is None or fecha_ref < actual_min:
                grupo['proximo_vencimiento'] = fecha_ref
            if actual_max is None or fecha_ref > actual_max:
                grupo['ultimo_vencimiento'] = fecha_ref

    rows = []
    for idx, grupo in enumerate(grupos.values(), start=1):
        prioridad_codigo, prioridad_label, prioridad_orden = _prioridad_agregada(grupo)
        clientes_lista = ', '.join(sorted(grupo['clientes_lista_set']))
        if len(clientes_lista) > 130:
            clientes_lista = f'{clientes_lista[:127]}...'

        total = grupo['monto_total']
        aplicado = grupo['monto_aplicado']
        pendiente = grupo['monto_pendiente']
        moneda = grupo['moneda_codigo']
        proximo = grupo['proximo_vencimiento']
        ultimo = grupo['ultimo_vencimiento']

        rows.append({
            'nro': idx,
            'prioridad_codigo': prioridad_codigo,
            'prioridad': prioridad_label,
            'orden_prioridad': prioridad_orden,
            'unidad': grupo['unidad'],
            'origen_codigo': grupo['origen_codigo'],
            'origen': grupo['origen'],
            'cuenta': grupo['cuenta'],
            'cuenta_codigo': grupo['cuenta_codigo'],
            'moneda_codigo': moneda,
            'registros': grupo['registros'],
            'clientes': len(grupo['clientes_set']),
            'clientes_lista': clientes_lista,
            'vencidas': grupo['vencidas'],
            'hoy': grupo['hoy'],
            'proximas_7': grupo['proximas_7'],
            'sin_vencimiento': grupo['sin_vencimiento'],
            'parciales': grupo['parciales'],
            'proximo_vencimiento': proximo.isoformat() if isinstance(proximo, date) else '',
            'proximo_vencimiento_label': _date_label(proximo) if isinstance(proximo, date) else 'Sin vencimiento',
            'ultimo_vencimiento_label': _date_label(ultimo) if isinstance(ultimo, date) else 'Sin vencimiento',
            'monto_total': float(total),
            'monto_total_label': _format_money(total, moneda),
            'monto_aplicado': float(aplicado),
            'monto_aplicado_label': _format_money(aplicado, moneda),
            'monto_pendiente': float(pendiente),
            'monto_pendiente_label': _format_money(pendiente, moneda),
        })

    rows.sort(key=lambda row: (
        row.get('orden_prioridad', 9),
        _fecha_sort(date.fromisoformat(row['proximo_vencimiento']) if row.get('proximo_vencimiento') else None),
        row.get('unidad') or '',
        row.get('origen') or '',
        row.get('cuenta') or '',
        row.get('moneda_codigo') or '',
    ))

    for idx, row in enumerate(rows[:limit_rows], start=1):
        row['nro'] = idx
    return rows[:limit_rows]


def _fetch_rows(filtros, limit_rows=MAX_ROWS_SCREEN):
    cartera_limit = max(MAX_ROWS_EXPORT, int(limit_rows))
    cartera_rows = fetch_cartera_rows(filtros, limit_rows=cartera_limit)
    return _agregar_rows(cartera_rows, filtros, limit_rows)


def display_columns():
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'unidad', 'label': 'Unidad', 'align': 'left', 'strong': True},
        {'key': 'origen', 'label': 'Origen', 'align': 'left', 'strong': True},
        {'key': 'cuenta', 'label': 'Cuenta cartera', 'sub_key': 'cuenta_codigo', 'align': 'left'},
        {'key': 'moneda_codigo', 'label': 'Moneda', 'align': 'center'},
        {'key': 'proximo_vencimiento_label', 'label': 'Próx. vencimiento', 'align': 'center'},
        {'key': 'registros', 'label': 'Registros', 'align': 'center'},
        {'key': 'clientes', 'label': 'Clientes', 'align': 'center'},
        {'key': 'vencidas', 'label': 'Vencidas', 'align': 'center'},
        {'key': 'sin_vencimiento', 'label': 'Sin venc.', 'align': 'center'},
        {'key': 'parciales', 'label': 'Parciales', 'align': 'center'},
        {'key': 'monto_total', 'label': 'Total', 'type': 'money', 'align': 'right'},
        {'key': 'monto_aplicado', 'label': 'Cobrado', 'type': 'money', 'align': 'right'},
        {'key': 'monto_pendiente', 'label': 'Pendiente', 'type': 'money', 'align': 'right'},
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
    total_original = defaultdict(lambda: Decimal('0.00'))
    total_aplicado = defaultdict(lambda: Decimal('0.00'))
    origenes = set()
    unidades = set()
    cuentas = set()
    registros = 0
    clientes = 0
    criticos = 0
    hoy = 0
    sin_vencimiento = 0
    parciales = 0

    for row in rows:
        moneda = row.get('moneda_codigo') or MONEDA_BASE
        total[moneda] += _decimal(row.get('monto_pendiente'))
        total_original[moneda] += _decimal(row.get('monto_total'))
        total_aplicado[moneda] += _decimal(row.get('monto_aplicado'))
        registros += int(row.get('registros') or 0)
        clientes += int(row.get('clientes') or 0)
        sin_vencimiento += int(row.get('sin_vencimiento') or 0)
        parciales += int(row.get('parciales') or 0)

        if row.get('origen'):
            origenes.add(row['origen'])
        if row.get('unidad'):
            unidades.add(row['unidad'])
        if row.get('cuenta'):
            cuentas.add(row['cuenta'])

        if row.get('prioridad_codigo') == 'CRITICA':
            criticos += 1
        elif row.get('prioridad_codigo') == 'ALTA':
            hoy += 1

    monedas = sorted(total.keys())
    totales_por_moneda = []
    for moneda in monedas:
        totales_por_moneda.append({
            'moneda_codigo': moneda,
            'total': float(total[moneda]),
            'total_label': _format_money(total[moneda], moneda),
            'original': float(total_original[moneda]),
            'original_label': _format_money(total_original[moneda], moneda),
            'aplicado': float(total_aplicado[moneda]),
            'aplicado_label': _format_money(total_aplicado[moneda], moneda),
        })

    return {
        'cantidad': len(rows),
        'registros': registros,
        'clientes': clientes,
        'unidades': len(unidades),
        'origenes': len(origenes),
        'cuentas': len(cuentas),
        'grupos_criticos': criticos,
        'grupos_hoy': hoy,
        'sin_vencimiento': sin_vencimiento,
        'parciales': parciales,
        'moneda_unica': monedas[0] if len(monedas) == 1 else '',
        'total_pendiente_label': _label_totales_por_moneda(total),
        'total_original_label': _label_totales_por_moneda(total_original),
        'total_aplicado_label': _label_totales_por_moneda(total_aplicado),
        'totales_por_moneda': totales_por_moneda,
        'hay_limite': len(rows) >= MAX_ROWS_SCREEN,
    }


def _summary_cards(summary):
    return [
        {'label': 'Total pendiente', 'value': summary.get('total_pendiente_label'), 'note': 'Por moneda', 'kind': 'total'},
        {'label': 'Grupos', 'value': summary.get('cantidad', 0), 'note': 'Unidad/origen/cuenta', 'kind': 'group'},
        {'label': 'Unidades', 'value': summary.get('unidades', 0), 'note': 'Con cartera', 'kind': 'group'},
        {'label': 'Críticos', 'value': summary.get('grupos_criticos', 0), 'note': 'Con vencidos', 'kind': 'critical'},
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
        'empty_title': 'No hay cartera por unidad/origen para los filtros seleccionados',
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
        ('unidad', 'Unidad', 34),
        ('origen', 'Origen', 24),
        ('cuenta', 'Cuenta cartera', 38),
        ('cuenta_codigo', 'Código cuenta', 16),
        ('moneda_codigo', 'Moneda', 10),
        ('proximo_vencimiento_label', 'Próx. vencimiento', 18),
        ('ultimo_vencimiento_label', 'Último vencimiento', 18),
        ('registros', 'Registros', 12),
        ('clientes', 'Clientes', 12),
        ('clientes_lista', 'Clientes relacionados', 48),
        ('vencidas', 'Vencidas', 12),
        ('hoy', 'Hoy', 10),
        ('proximas_7', 'Próx. 7 días', 14),
        ('sin_vencimiento', 'Sin vencimiento', 16),
        ('parciales', 'Parciales', 12),
        ('monto_total', 'Total', 16),
        ('monto_aplicado', 'Cobrado', 16),
        ('monto_pendiente', 'Pendiente', 16),
    ]


def excel_summary_text(summary):
    return (
        f"Total pendiente: {summary.get('total_pendiente_label', '')} · "
        f"Grupos: {summary.get('cantidad', 0)} · "
        f"Unidades: {summary.get('unidades', 0)} · "
        f"Críticos: {summary.get('grupos_criticos', 0)} · "
        f"Registros: {summary.get('registros', 0)}"
    )


def pdf_columns():
    return [
        {'label': 'Prioridad', 'width': 20, 'align': 'center'},
        {'label': 'Unidad', 'width': 42, 'align': 'left'},
        {'label': 'Origen', 'width': 32, 'align': 'left'},
        {'label': 'Cuenta', 'width': 46, 'align': 'left'},
        {'label': 'Mon.', 'width': 12, 'align': 'center'},
        {'label': 'Venc.', 'width': 20, 'align': 'center'},
        {'label': 'Reg.', 'width': 14, 'align': 'center'},
        {'label': 'Cli.', 'width': 14, 'align': 'center'},
        {'label': 'Sin venc.', 'width': 18, 'align': 'center'},
        {'label': 'Total', 'width': 27, 'align': 'right'},
        {'label': 'Cobrado', 'width': 27, 'align': 'right'},
        {'label': 'Pendiente', 'width': 27, 'align': 'right'},
    ]


def pdf_rows(payload):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        rows.append([
            item['prioridad'],
            item['unidad'],
            item['origen'],
            item['cuenta'],
            item['moneda_codigo'],
            item['proximo_vencimiento_label'],
            item['registros'],
            item['clientes'],
            item['sin_vencimiento'],
            item['monto_total_label'],
            item['monto_aplicado_label'],
            item['monto_pendiente_label'],
        ])
    if len(payload['rows']) > MAX_ROWS_PDF:
        rows.append(['', f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} grupos. Use Excel para el detalle completo.', '', '', '', '', '', '', '', '', '', ''])
    return rows


def pdf_header_note(payload):
    summary = payload.get('summary', {})
    return (
        f"Periodo: {payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Total pendiente: {summary.get('total_pendiente_label', '')}. "
        f"Grupos: {summary.get('cantidad', 0)}. "
        f"Unidades: {summary.get('unidades', 0)}. "
        f"Críticos: {summary.get('grupos_criticos', 0)}."
    )
