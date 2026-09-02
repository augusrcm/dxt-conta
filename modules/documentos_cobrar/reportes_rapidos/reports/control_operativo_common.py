# ============================================================
# DXT CONTA - Reportes Rapidos
# Utilidades comunes: control operativo y calidad de datos
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


ALCANCES_PERIODO = {
    'hoy': 'Hoy',
    'ayer': 'Ayer',
    'ultimos_7': 'Ultimos 7 dias',
    'este_mes': 'Este mes',
    'rango': 'Rango personalizado',
}

ALCANCES_CALIDAD = {
    'todos': 'Todos',
    'clientes': 'Clientes',
    'proveedores': 'Proveedores',
    'publicidad': 'Publicidad',
    'documentos': 'Documentos',
}

GRUPOS_TODOS = {'': 'Todos'}


def validate_period_filters(args, default_grupo='', grupos=None, fecha_label='Fecha'):
    hoy = date.today()
    alcance = _clean(args.get('alcance')) or 'hoy'
    if alcance not in ALCANCES_PERIODO:
        raise ValueError('El periodo seleccionado no es valido.')

    grupos = grupos or GRUPOS_TODOS
    grupo = _clean(args.get('grupo'))
    if grupo == '' and default_grupo is not None:
        grupo = default_grupo
    if grupo not in grupos:
        raise ValueError('El grupo seleccionado no es valido.')

    fecha_base = _parse_date(args.get('fecha_base'), fecha_label, default=hoy)
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if alcance == 'hoy':
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
        'alcance_label': ALCANCES_PERIODO[alcance],
        'grupo': grupo,
        'grupo_label': grupos[grupo],
        'fecha_base': fecha_base,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
    }


def validate_quality_filters(args, grupos=None, default_grupo=''):
    alcance = _clean(args.get('alcance')) or 'todos'
    if alcance not in ALCANCES_CALIDAD:
        raise ValueError('El alcance seleccionado no es valido.')

    grupos = grupos or GRUPOS_TODOS
    grupo = _clean(args.get('grupo'))
    if grupo == '' and default_grupo is not None:
        grupo = default_grupo
    if grupo not in grupos:
        raise ValueError('El grupo seleccionado no es valido.')

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')
    hoy = date.today()
    return {
        'alcance': alcance,
        'alcance_label': ALCANCES_CALIDAD[alcance],
        'grupo': grupo,
        'grupo_label': grupos[grupo],
        'fecha_base': hoy,
        'fecha_desde': hoy,
        'fecha_hasta': hoy,
        'unidad_negocio_id': unidad_negocio_id,
    }


def descripcion_periodo(filtros):
    if filtros['alcance'] == 'rango':
        return f"Del {filtros['fecha_desde'].strftime('%d/%m/%Y')} al {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    if filtros['fecha_desde'] == filtros['fecha_hasta']:
        return f"{filtros['alcance_label']} · {filtros['fecha_desde'].strftime('%d/%m/%Y')}"
    return (
        f"{filtros['alcance_label']} · "
        f"{filtros['fecha_desde'].strftime('%d/%m/%Y')} al {filtros['fecha_hasta'].strftime('%d/%m/%Y')}"
    )


def descripcion_calidad(filtros):
    return f"Alcance: {filtros['alcance_label']}"


def execute_rows(sql, params):
    with DatabaseManager() as db:
        return db.execute_query(sql, params)


def map_control_row(row, idx):
    monto = _decimal(row.get('monto'))
    moneda = row.get('moneda_codigo') or ''
    fecha = row.get('fecha')
    return {
        'nro': idx,
        'fecha': fecha.isoformat() if isinstance(fecha, date) else str(fecha or ''),
        'fecha_label': _date_label(fecha),
        'origen': row.get('origen') or '',
        'referencia': row.get('referencia') or '',
        'cliente_proveedor': row.get('cliente_proveedor') or '',
        'detalle': row.get('detalle') or '',
        'estado': row.get('estado') or '',
        'estado_codigo': row.get('estado_codigo') or row.get('estado') or '',
        'unidad': row.get('unidad') or '',
        'prioridad': row.get('prioridad') or '',
        'prioridad_codigo': row.get('prioridad_codigo') or '',
        'accion': row.get('accion') or '',
        'moneda_codigo': moneda,
        'monto': float(monto),
        'monto_label': _format_money(monto, moneda),
    }


def build_summary_control(rows):
    total_registros = len(rows)
    criticas = 0
    altas = 0
    medias = 0
    bajas = 0
    totales = {}
    por_origen = {}

    for row in rows:
        prioridad = row.get('prioridad_codigo') or ''
        if prioridad == 'CRITICA':
            criticas += 1
        elif prioridad == 'ALTA':
            altas += 1
        elif prioridad == 'MEDIA':
            medias += 1
        else:
            bajas += 1

        origen = row.get('origen') or 'Sin origen'
        por_origen[origen] = por_origen.get(origen, 0) + 1

        moneda = str(row.get('moneda_codigo') or '').upper()
        if moneda:
            totales[moneda] = totales.get(moneda, Decimal('0.00')) + _decimal(row.get('monto'))

    totales_por_moneda = [
        {'moneda_codigo': moneda, 'total': float(total), 'total_label': _format_money(total, moneda)}
        for moneda, total in sorted(totales.items())
    ]
    moneda_unica = totales_por_moneda[0]['moneda_codigo'] if len(totales_por_moneda) == 1 else ''
    total_unico = Decimal(str(totales_por_moneda[0]['total'])) if len(totales_por_moneda) == 1 else Decimal('0.00')

    return {
        'cantidad': total_registros,
        'criticas': criticas,
        'altas': altas,
        'medias': medias,
        'bajas': bajas,
        'por_origen': por_origen,
        'moneda_unica': moneda_unica,
        'totales_por_moneda': totales_por_moneda,
        'total_general': float(total_unico),
        'total_general_label': _format_money(total_unico, moneda_unica) if moneda_unica else 'Por moneda',
        'hay_limite': total_registros >= MAX_ROWS_SCREEN,
    }


def summary_cards_control(summary, total_label='Total', total_note='Importe asociado'):
    return [
        {'label': 'Registros', 'value': summary.get('cantidad', 0), 'note': 'Resultados encontrados', 'kind': 'group'},
        {'label': 'Criticas', 'value': summary.get('criticas', 0), 'note': 'Requieren atencion inmediata', 'kind': 'critical'},
        {'label': 'Altas', 'value': summary.get('altas', 0), 'note': 'Atencion prioritaria', 'kind': 'high'},
        {'label': 'Medias', 'value': summary.get('medias', 0), 'note': 'Revision operativa', 'kind': 'group'},
        {'label': total_label, 'value': summary.get('total_general_label'), 'note': total_note, 'kind': 'total'},
    ]


def display_columns_control(include_money=True):
    columns = [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'fecha_label', 'label': 'Fecha', 'align': 'center'},
        {'key': 'origen', 'label': 'Origen', 'align': 'left'},
        {'key': 'referencia', 'label': 'Referencia', 'align': 'left'},
        {'key': 'cliente_proveedor', 'label': 'Cliente / Proveedor', 'align': 'left', 'strong': True},
        {'key': 'detalle', 'label': 'Detalle', 'align': 'left'},
        {'key': 'estado', 'label': 'Estado', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
        {'key': 'unidad', 'label': 'Unidad', 'align': 'left'},
    ]
    if include_money:
        columns.append({'key': 'monto', 'label': 'Monto', 'type': 'money', 'align': 'right'})
    columns.append({'key': 'accion', 'label': 'Accion sugerida', 'align': 'left'})
    return columns


def excel_columns_control(include_money=True):
    columns = [
        ('prioridad', 'Prioridad', 16),
        ('fecha_label', 'Fecha', 13),
        ('origen', 'Origen', 26),
        ('referencia', 'Referencia', 22),
        ('cliente_proveedor', 'Cliente / Proveedor', 36),
        ('detalle', 'Detalle', 48),
        ('estado', 'Estado', 16),
        ('unidad', 'Unidad', 28),
    ]
    if include_money:
        columns.extend([
            ('moneda_codigo', 'Moneda', 10),
            ('monto', 'Monto', 16),
        ])
    columns.append(('accion', 'Accion sugerida', 42))
    return columns


def pdf_columns_control(include_money=True):
    columns = [
        {'label': 'Prioridad', 'width': 22, 'align': 'center'},
        {'label': 'Fecha', 'width': 22, 'align': 'center'},
        {'label': 'Origen', 'width': 38, 'align': 'left'},
        {'label': 'Referencia', 'width': 32, 'align': 'left'},
        {'label': 'Cliente / Proveedor', 'width': 54, 'align': 'left'},
        {'label': 'Detalle', 'width': 70, 'align': 'left'},
        {'label': 'Estado', 'width': 28, 'align': 'center'},
    ]
    if include_money:
        columns.append({'label': 'Monto', 'width': 26, 'align': 'right'})
    return columns


def pdf_rows_control(payload, include_money=True):
    rows = []
    for item in payload['rows'][:MAX_ROWS_PDF]:
        row = [
            item.get('prioridad', ''),
            item.get('fecha_label', ''),
            item.get('origen', ''),
            item.get('referencia', ''),
            item.get('cliente_proveedor', ''),
            item.get('detalle', ''),
            item.get('estado', ''),
        ]
        if include_money:
            row.append(item.get('monto_label', ''))
        rows.append(row)
    if len(payload['rows']) > MAX_ROWS_PDF:
        filler = [''] * (8 if include_money else 7)
        filler[2] = f'Se muestran {MAX_ROWS_PDF} de {len(payload["rows"])} registros. Use Excel para el detalle completo.'
        rows.append(filler)
    return rows


def totales_text(summary):
    totales = summary.get('totales_por_moneda') or []
    if not totales:
        return 'Sin importes monetarios'
    if len(totales) == 1:
        return f"Total: {totales[0].get('total_label', '0.00')}"
    partes = [
        f"{item.get('total_label', '0.00')} ({item.get('moneda_simbolo') or item.get('moneda_codigo')})"
        for item in totales
    ]
    return 'Totales por moneda: ' + '; '.join(partes)


def excel_summary_text_control(summary):
    return (
        f"Registros: {summary.get('cantidad', 0)} · "
        f"Criticas: {summary.get('criticas', 0)} · "
        f"Altas: {summary.get('altas', 0)} · "
        f"Medias: {summary.get('medias', 0)} · "
        f"{totales_text(summary)}"
    )


def pdf_header_note_control(payload):
    summary = payload.get('summary', {})
    return (
        f"{payload.get('descripcion_periodo', '')}. "
        f"Unidad: {payload.get('unidad_label', '')}. "
        f"Grupo: {payload.get('filtros', {}).get('grupo_label', '')}. "
        f"Registros: {summary.get('cantidad', 0)}. "
        f"Criticas: {summary.get('criticas', 0)}. Altas: {summary.get('altas', 0)}. "
        f"{totales_text(summary)}."
    )


def build_payload_common(report_id, title, description, filtros, rows, columns, empty_title, include_money=True):
    summary = build_summary_control(rows)
    if not include_money:
        summary['totales_por_moneda'] = []
        summary['moneda_unica'] = ''
        summary['total_general'] = 0.0
        summary['total_general_label'] = 'Sin importes'
    payload = {
        'reporte': report_id,
        'titulo': title,
        'descripcion': description,
        'descripcion_periodo': filtros.get('descripcion') or descripcion_periodo(filtros),
        'unidad_label': _unidad_label(filtros.get('unidad_negocio_id')),
        'columns': columns,
        'summary_cards': summary_cards_control(summary),
        'empty_title': empty_title,
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
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
    return aplicar_contexto_monetario(payload)
