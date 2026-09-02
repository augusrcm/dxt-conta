# ============================================================
# DXT CONTA - Reporte Especial
# Resumen Ejecutivo Mensual
# ============================================================

from __future__ import annotations

import io
from collections import OrderedDict
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.sax.saxutils import escape

from flask import Response, render_template, request
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from database.db_manager import DatabaseManager
from modules.resumen_ejecutivo_mensual import resumen_ejecutivo_mensual_bp
from modules.reportes_rapidos.core.utils import logo_path, usuario_actual
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
CENTAVO = Decimal('0.01')
MONEDA_BASE = 'BOB'

ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
GREEN = colors.HexColor('#107c41')
RED = colors.HexColor('#b42318')
SOFT_ORANGE = colors.HexColor('#fff4ec')

MESES_ES = {
    1: 'Enero',
    2: 'Febrero',
    3: 'Marzo',
    4: 'Abril',
    5: 'Mayo',
    6: 'Junio',
    7: 'Julio',
    8: 'Agosto',
    9: 'Septiembre',
    10: 'Octubre',
    11: 'Noviembre',
    12: 'Diciembre',
}


def _clean(value) -> str:
    return str(value or '').strip()


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _to_float(value) -> float:
    return float(_to_decimal(value))


def _money(value) -> str:
    return f'{_to_decimal(value):,.2f}'




def _money_with_symbol(value, symbol='') -> str:
    prefix = _clean(symbol) or ''
    amount = _money(value)
    return f'{prefix} {amount}'.strip()


def _currency_key(row):
    codigo = _clean(row.get('moneda_codigo')).upper() or MONEDA_BASE
    simbolo = _clean(row.get('moneda_simbolo')) or codigo
    return codigo, simbolo


def _new_currency_total(codigo, simbolo):
    return {
        'moneda_codigo': codigo,
        'moneda_simbolo': simbolo,
        'monto': Decimal('0.00'),
        'documentos': 0,
    }


def _format_currency_totals(items, amount_key='monto', count_key=None):
    totals = []
    for item in items:
        total = dict(item)
        value = _to_decimal(total.get(amount_key))
        total[amount_key] = value
        total['monto_label'] = _money_with_symbol(value, total.get('moneda_simbolo') or total.get('moneda_codigo'))
        if count_key:
            total[count_key] = int(total.get(count_key) or 0)
        totals.append(total)

    if not totals:
        totals = [{
            'moneda_codigo': MONEDA_BASE,
            'moneda_simbolo': MONEDA_BASE,
            amount_key: Decimal('0.00'),
            'monto_label': _money_with_symbol(0, MONEDA_BASE),
            **({count_key: 0} if count_key else {}),
        }]

    if len(totals) == 1:
        label = totals[0]['monto_label']
    else:
        label = 'Por moneda'

    return {
        'label': label,
        'multiple': len(totals) > 1,
        'items': totals,
    }


def _date_label(value) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    raw = _clean(value)
    if not raw:
        return ''
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return raw


def _safe_text(value) -> str:
    return escape(str(value if value is not None else ''))


def _parse_year(value) -> int:
    raw = _clean(value)
    if not raw:
        return date.today().year
    try:
        year = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('La gestión seleccionada no es válida.') from exc
    if year < 1900 or year > 2200:
        raise ValueError('La gestión seleccionada no es válida.')
    return year


def _parse_month_number(value) -> int:
    raw = _clean(value)
    if not raw:
        return date.today().month
    try:
        month = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('El mes seleccionado no es válido.') from exc
    if month < 1 or month > 12:
        raise ValueError('El mes seleccionado no es válido.')
    return month


def _parse_optional_int(value, field_name):
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} no es válido.') from exc
    if parsed <= 0:
        raise ValueError(f'{field_name} no es válido.')
    return parsed


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _month_key(month_date: date) -> str:
    return month_date.strftime('%Y-%m')


def _month_label(year: int, month: int) -> str:
    return f'{MESES_ES.get(month, str(month))} {year}'


def _db_rows(sql: str, params=()):
    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))
    return [dict(row) for row in rows]


def _fetch_gestiones():
    sql = """
        SELECT DISTINCT EXTRACT(YEAR FROM fecha)::int AS gestion
        FROM contabilidad.asiento
        UNION
        SELECT EXTRACT(YEAR FROM CURRENT_DATE)::int AS gestion
        ORDER BY gestion DESC
    """
    rows = _db_rows(sql)
    return [int(row['gestion']) for row in rows if row.get('gestion')]


def _fetch_unidades():
    sql = """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
    """
    return _db_rows(sql)


def _resolve_unidad(unidad_id):
    if not unidad_id:
        return None
    rows = _db_rows(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_id,),
    )
    return rows[0] if rows else None


def _build_filters(args):
    today = date.today()
    gestion = _parse_year(args.get('gestion'))
    mes = _parse_month_number(args.get('mes'))
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'La unidad de negocio')

    fecha_desde = _month_start(gestion, mes)
    fecha_hasta = _month_end(gestion, mes)
    gestion_desde = date(gestion, 1, 1)
    gestion_hasta = date(gestion, 12, 31)

    return {
        'gestion': gestion,
        'mes': mes,
        'mes_label': _month_label(gestion, mes),
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_desde_label': _date_label(fecha_desde),
        'fecha_hasta_label': _date_label(fecha_hasta),
        'gestion_desde': gestion_desde,
        'gestion_hasta': gestion_hasta,
        'unidad_negocio_id': unidad_negocio_id,
        'emitido': datetime.now(),
        'hoy': today,
    }


def _monto_resultado(tipo_cuenta, debe, haber):
    debe = _to_decimal(debe)
    haber = _to_decimal(haber)
    if tipo_cuenta == 'INGRESO':
        return haber - debe
    if tipo_cuenta in {'COSTO', 'GASTO'}:
        return debe - haber
    return Decimal('0.00')


def _fetch_estado_mes(filtros):
    sql = """
        SELECT
            c.tipo::text AS tipo,
            COALESCE(a.moneda_codigo, %s) AS moneda_codigo,
            COALESCE(NULLIF(m.simbolo, ''), a.moneda_codigo, %s) AS moneda_simbolo,
            COALESCE(SUM(ad.debe), 0) AS debe_periodo,
            COALESCE(SUM(ad.haber), 0) AS haber_periodo
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.moneda m ON m.codigo = a.moneda_codigo
        WHERE a.estado::text = 'CONFIRMADO'
          AND a.fecha BETWEEN %s AND %s
          AND c.es_postable = TRUE
          AND c.tipo::text IN ('INGRESO', 'COSTO', 'GASTO')
    """
    params = [MONEDA_BASE, MONEDA_BASE, filtros['fecha_desde'], filtros['fecha_hasta']]
    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])
    sql += "\n        GROUP BY c.tipo::text, a.moneda_codigo, m.simbolo\n        ORDER BY moneda_codigo ASC, tipo ASC"

    rows = _db_rows(sql, params)
    totales = OrderedDict()
    for row in rows:
        codigo, simbolo = _currency_key(row)
        if codigo not in totales:
            totales[codigo] = {
                'moneda_codigo': codigo,
                'moneda_simbolo': simbolo,
                'ingresos': Decimal('0.00'),
                'costos': Decimal('0.00'),
                'gastos': Decimal('0.00'),
            }
        tipo = row.get('tipo') or ''
        monto = _monto_resultado(tipo, row.get('debe_periodo'), row.get('haber_periodo'))
        if tipo == 'INGRESO':
            totales[codigo]['ingresos'] += monto
        elif tipo == 'COSTO':
            totales[codigo]['costos'] += monto
        elif tipo == 'GASTO':
            totales[codigo]['gastos'] += monto

    if not totales:
        totales[MONEDA_BASE] = {
            'moneda_codigo': MONEDA_BASE,
            'moneda_simbolo': MONEDA_BASE,
            'ingresos': Decimal('0.00'),
            'costos': Decimal('0.00'),
            'gastos': Decimal('0.00'),
        }

    resumen = []
    for total in totales.values():
        total['egresos'] = total['costos'] + total['gastos']
        total['resultado_neto'] = total['ingresos'] - total['egresos']
        total['ingresos_label'] = _money_with_symbol(total['ingresos'], total['moneda_simbolo'])
        total['egresos_label'] = _money_with_symbol(total['egresos'], total['moneda_simbolo'])
        total['costos_label'] = _money_with_symbol(total['costos'], total['moneda_simbolo'])
        total['gastos_label'] = _money_with_symbol(total['gastos'], total['moneda_simbolo'])
        total['resultado_neto_label'] = _money_with_symbol(total['resultado_neto'], total['moneda_simbolo'])
        total['resultado_tipo'] = 'positivo' if total['resultado_neto'] >= 0 else 'negativo'
        resumen.append(total)

    principal = resumen[0]
    moneda_multiple = len(resumen) > 1
    return {
        'ingresos': principal['ingresos'],
        'costos': principal['costos'],
        'gastos': principal['gastos'],
        'egresos': principal['egresos'],
        'resultado_neto': principal['resultado_neto'],
        'ingresos_label': principal['ingresos_label'] if not moneda_multiple else 'Por moneda',
        'egresos_label': principal['egresos_label'] if not moneda_multiple else 'Por moneda',
        'costos_label': principal['costos_label'] if not moneda_multiple else 'Por moneda',
        'gastos_label': principal['gastos_label'] if not moneda_multiple else 'Por moneda',
        'resultado_neto_label': principal['resultado_neto_label'] if not moneda_multiple else 'Por moneda',
        'resultado_tipo': principal['resultado_tipo'],
        'moneda_multiple': moneda_multiple,
        'totales_por_moneda': resumen,
    }

def _fetch_resultado_mensual(filtros):
    sql = """
        SELECT
            EXTRACT(MONTH FROM a.fecha)::int AS mes,
            c.tipo::text AS tipo,
            COALESCE(a.moneda_codigo, %s) AS moneda_codigo,
            COALESCE(NULLIF(m.simbolo, ''), a.moneda_codigo, %s) AS moneda_simbolo,
            COALESCE(SUM(ad.debe), 0) AS debe_periodo,
            COALESCE(SUM(ad.haber), 0) AS haber_periodo
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.moneda m ON m.codigo = a.moneda_codigo
        WHERE a.estado::text = 'CONFIRMADO'
          AND a.fecha BETWEEN %s AND %s
          AND c.es_postable = TRUE
          AND c.tipo::text IN ('INGRESO', 'COSTO', 'GASTO')
    """
    params = [MONEDA_BASE, MONEDA_BASE, filtros['gestion_desde'], filtros['gestion_hasta']]
    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])
    sql += """
        GROUP BY EXTRACT(MONTH FROM a.fecha)::int, c.tipo::text, a.moneda_codigo, m.simbolo
        ORDER BY moneda_codigo ASC, mes ASC, tipo ASC
    """

    rows = _db_rows(sql, params)
    monedas = OrderedDict()
    for row in rows:
        codigo, simbolo = _currency_key(row)
        monedas[codigo] = simbolo
    if not monedas:
        monedas[MONEDA_BASE] = MONEDA_BASE

    data = OrderedDict()
    for codigo, simbolo in monedas.items():
        data[codigo] = {}
        for month in range(1, 13):
            data[codigo][month] = {
                'mes': month,
                'mes_key': f"{filtros['gestion']}-{month:02d}",
                'mes_label': MESES_ES[month],
                'moneda_codigo': codigo,
                'moneda_simbolo': simbolo,
                'ingresos': Decimal('0.00'),
                'costos': Decimal('0.00'),
                'gastos': Decimal('0.00'),
                'resultado_neto': Decimal('0.00'),
            }

    for row in rows:
        mes = int(row.get('mes') or 0)
        codigo, simbolo = _currency_key(row)
        if codigo not in data:
            data[codigo] = {}
        if mes not in data[codigo]:
            data[codigo][mes] = {
                'mes': mes,
                'mes_key': f"{filtros['gestion']}-{mes:02d}",
                'mes_label': MESES_ES.get(mes, str(mes)),
                'moneda_codigo': codigo,
                'moneda_simbolo': simbolo,
                'ingresos': Decimal('0.00'),
                'costos': Decimal('0.00'),
                'gastos': Decimal('0.00'),
                'resultado_neto': Decimal('0.00'),
            }
        tipo = row.get('tipo') or ''
        monto = _monto_resultado(tipo, row.get('debe_periodo'), row.get('haber_periodo'))
        if tipo == 'INGRESO':
            data[codigo][mes]['ingresos'] += monto
        elif tipo == 'COSTO':
            data[codigo][mes]['costos'] += monto
        elif tipo == 'GASTO':
            data[codigo][mes]['gastos'] += monto

    currency_activity = []
    for codigo, months in data.items():
        activity = Decimal('0.00')
        for item in months.values():
            item['resultado_neto'] = item['ingresos'] - item['costos'] - item['gastos']
            item['resultado_neto_label'] = _money_with_symbol(item['resultado_neto'], item.get('moneda_simbolo'))
            item['resultado_tipo'] = 'positivo' if item['resultado_neto'] >= 0 else 'negativo'
            activity += abs(item['ingresos']) + abs(item['costos']) + abs(item['gastos'])
        currency_activity.append((activity, codigo))

    currency_activity.sort(reverse=True)
    principal_codigo = currency_activity[0][1] if currency_activity else MONEDA_BASE
    monthly = [data[principal_codigo][mes] for mes in range(1, 13)]
    return monthly

def _fetch_cuentas_por_cobrar(filtros):
    condiciones_doc = [
        "d.activo = TRUE",
        "d.estado IN ('PENDIENTE', 'PARCIAL')",
        "COALESCE(d.saldo_pendiente, 0) > 0",
        "d.fecha_documento <= %s",
    ]
    condiciones_fe = [
        "f.fecha_emision <= %s",
        "f.estado::text <> 'ANULADA'",
        "COALESCE(f.saldo_pendiente, 0) > 0",
        "NOT EXISTS (SELECT 1 FROM contabilidad.documento_por_cobrar dx WHERE dx.factura_electronica_id = f.id AND dx.activo = TRUE AND dx.estado <> 'ANULADO')",
    ]
    params_doc = [filtros['fecha_hasta']]
    params_fe = [filtros['fecha_hasta']]
    if filtros.get('unidad_negocio_id'):
        condiciones_doc.append('d.unidad_negocio_id = %s')
        condiciones_fe.append('f.unidad_negocio_id = %s')
        params_doc.append(filtros['unidad_negocio_id'])
        params_fe.append(filtros['unidad_negocio_id'])

    cartera_cte = f"""
        WITH cartera AS (
            SELECT
                'DOCUMENTO_COBRAR'::text AS fuente,
                d.id AS item_id,
                COALESCE(d.cliente_auxiliar_id, 0) AS auxiliar_id,
                COALESCE(NULLIF(aux.nombre, ''), NULLIF(aux.razon_social, ''), NULLIF(d.cliente_nombre, ''), 'Sin auxiliar') AS auxiliar,
                COALESCE(NULLIF(aux.nit_ci, ''), NULLIF(d.cliente_nit, ''), '') AS documento,
                COALESCE(d.origen_documento, 'DOCUMENTO') AS origen,
                COALESCE(d.moneda_codigo, %s) AS moneda_codigo,
                COALESCE(d.saldo_pendiente, 0) AS saldo_pendiente
            FROM contabilidad.documento_por_cobrar d
            LEFT JOIN contabilidad.auxiliar aux ON aux.id = d.cliente_auxiliar_id
            WHERE {' AND '.join(condiciones_doc)}

            UNION ALL

            SELECT
                'FACTURA_ELECTRONICA'::text AS fuente,
                f.id AS item_id,
                COALESCE(f.cliente_auxiliar_id, 0) AS auxiliar_id,
                COALESCE(NULLIF(aux.nombre, ''), NULLIF(aux.razon_social, ''), NULLIF(f.nombre_cliente, ''), 'Sin auxiliar') AS auxiliar,
                COALESCE(NULLIF(aux.nit_ci, ''), NULLIF(f.nit_cliente, ''), '') AS documento,
                'FACTURA_ELECTRONICA'::text AS origen,
                COALESCE(f.moneda_codigo, %s) AS moneda_codigo,
                COALESCE(f.saldo_pendiente, 0) AS saldo_pendiente
            FROM contabilidad.factura_electronica f
            LEFT JOIN contabilidad.auxiliar aux ON aux.id = f.cliente_auxiliar_id
            WHERE {' AND '.join(condiciones_fe)}
        )
    """
    base_params = [MONEDA_BASE] + params_doc + [MONEDA_BASE] + params_fe

    total_sql = cartera_cte + """
        SELECT
            c.moneda_codigo,
            COALESCE(NULLIF(m.simbolo, ''), c.moneda_codigo) AS moneda_simbolo,
            COUNT(*)::int AS documentos,
            COALESCE(SUM(c.saldo_pendiente), 0) AS monto
        FROM cartera c
        LEFT JOIN contabilidad.moneda m ON m.codigo = c.moneda_codigo
        GROUP BY c.moneda_codigo, m.simbolo
        ORDER BY c.moneda_codigo ASC
    """
    total_rows = _db_rows(total_sql, base_params)

    top_sql = cartera_cte + """
        SELECT
            c.auxiliar_id,
            c.auxiliar,
            c.documento,
            c.moneda_codigo,
            COALESCE(NULLIF(m.simbolo, ''), c.moneda_codigo) AS moneda_simbolo,
            COUNT(*)::int AS documentos,
            COUNT(DISTINCT c.origen)::int AS origenes,
            CASE WHEN COUNT(DISTINCT c.origen) > 1 THEN 'MIXTO' ELSE MIN(c.origen) END AS origen,
            COALESCE(SUM(c.saldo_pendiente), 0) AS saldo_pendiente
        FROM cartera c
        LEFT JOIN contabilidad.moneda m ON m.codigo = c.moneda_codigo
        GROUP BY c.auxiliar_id, c.auxiliar, c.documento, c.moneda_codigo, m.simbolo
        ORDER BY saldo_pendiente DESC, c.auxiliar ASC
        LIMIT 5
    """
    top = _db_rows(top_sql, base_params)

    origen_labels = {
        'HISTORICO': 'Historico',
        'VIGENTE_MANUAL': 'Vigente',
        'FACTURA_ELECTRONICA': 'Factura electronica',
        'MIXTO': 'Mixto',
    }

    for row in top:
        row['saldo_pendiente'] = _to_decimal(row.get('saldo_pendiente'))
        row['saldo_pendiente_label'] = _money_with_symbol(row['saldo_pendiente'], row.get('moneda_simbolo') or row.get('moneda_codigo'))
        row['origen_label'] = origen_labels.get(row.get('origen'), row.get('origen') or 'Documento')

    totals = _format_currency_totals(total_rows, amount_key='monto', count_key='documentos')
    documentos_total = sum(int(row.get('documentos') or 0) for row in total_rows)

    return {
        'documentos_pendientes': documentos_total,
        'facturas_pendientes': documentos_total,
        'saldo_pendiente': sum((_to_decimal(row.get('monto')) for row in total_rows), Decimal('0.00')),
        'saldo_pendiente_label': totals['label'],
        'moneda_multiple': totals['multiple'],
        'totales_por_moneda': totals['items'],
        'top': top,
    }

def _fetch_cuentas_por_pagar(filtros):
    where = [
        "c.activo = TRUE",
        "c.tipo = 'PAGAR'",
        "d.estado IN ('PENDIENTE', 'PARCIAL', 'INCUMPLIDO')",
        "GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0",
        "d.fecha_vencimiento <= %s",
    ]
    params = [filtros['fecha_hasta']]
    if filtros.get('unidad_negocio_id'):
        where.append('c.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])

    total_sql = f"""
        SELECT
            COUNT(*)::int AS documentos,
            COALESCE(SUM(GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)), 0) AS saldo_pendiente
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        WHERE {' AND '.join(where)}
    """
    total = _db_rows(total_sql, params)[0]
    saldo = _to_decimal(total.get('saldo_pendiente'))
    return {
        'documentos': int(total.get('documentos') or 0),
        'saldo_pendiente': saldo,
        'saldo_pendiente_label': _money_with_symbol(saldo, 'Bs'),
    }

def _fetch_top_gastos(filtros):
    sql = """
        SELECT
            c.codigo,
            COALESCE(c.nombre, '') AS cuenta,
            COALESCE(a.moneda_codigo, %s) AS moneda_codigo,
            COALESCE(NULLIF(m.simbolo, ''), a.moneda_codigo, %s) AS moneda_simbolo,
            COALESCE(SUM(ad.debe - ad.haber), 0) AS monto
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.moneda m ON m.codigo = a.moneda_codigo
        WHERE a.estado::text = 'CONFIRMADO'
          AND a.fecha BETWEEN %s AND %s
          AND c.es_postable = TRUE
          AND c.tipo::text IN ('GASTO', 'COSTO')
    """
    params = [MONEDA_BASE, MONEDA_BASE, filtros['fecha_desde'], filtros['fecha_hasta']]
    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])
    sql += """
        GROUP BY c.codigo, c.nombre, a.moneda_codigo, m.simbolo
        HAVING ABS(COALESCE(SUM(ad.debe - ad.haber), 0)) > 0
        ORDER BY monto DESC, c.nombre ASC
        LIMIT 5
    """
    rows = _db_rows(sql, params)
    for row in rows:
        row['monto'] = _to_decimal(row.get('monto'))
        row['monto_label'] = _money_with_symbol(row['monto'], row.get('moneda_simbolo') or row.get('moneda_codigo'))
    return rows

def _tesoreria_entries_cte():
    return """
    WITH movimientos AS (
        SELECT c.fecha, 'CAJA'::text AS tipo_objeto, c.caja_id AS objeto_id, 'INGRESO'::text AS flujo,
               c.monto_total::numeric AS monto, c.moneda_codigo, c.unidad_negocio_id
        FROM contabilidad.cobro c
        WHERE c.estado::text = 'CONFIRMADO' AND c.medio_pago::text = 'CAJA' AND c.caja_id IS NOT NULL

        UNION ALL
        SELECT c.fecha, 'BANCO'::text AS tipo_objeto, c.cuenta_bancaria_id AS objeto_id, 'INGRESO'::text AS flujo,
               c.monto_total::numeric AS monto, c.moneda_codigo, c.unidad_negocio_id
        FROM contabilidad.cobro c
        WHERE c.estado::text = 'CONFIRMADO' AND c.medio_pago::text = 'BANCO' AND c.cuenta_bancaria_id IS NOT NULL

        UNION ALL
        SELECT p.fecha, 'CAJA'::text AS tipo_objeto, p.caja_id AS objeto_id, 'EGRESO'::text AS flujo,
               p.monto_total::numeric AS monto, p.moneda_codigo, p.unidad_negocio_id
        FROM contabilidad.pago p
        WHERE p.estado::text = 'CONFIRMADO' AND p.medio_pago::text = 'CAJA' AND p.caja_id IS NOT NULL

        UNION ALL
        SELECT p.fecha, 'BANCO'::text AS tipo_objeto, p.cuenta_bancaria_id AS objeto_id, 'EGRESO'::text AS flujo,
               p.monto_total::numeric AS monto, p.moneda_codigo, p.unidad_negocio_id
        FROM contabilidad.pago p
        WHERE p.estado::text = 'CONFIRMADO' AND p.medio_pago::text = 'BANCO' AND p.cuenta_bancaria_id IS NOT NULL

        UNION ALL
        SELECT m.fecha, 'CAJA'::text AS tipo_objeto, m.caja_destino_id AS objeto_id, 'INGRESO'::text AS flujo,
               m.monto::numeric AS monto, m.moneda_codigo, m.unidad_negocio_id
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado::text = 'CONFIRMADO' AND m.medio_destino::text = 'CAJA' AND m.caja_destino_id IS NOT NULL

        UNION ALL
        SELECT m.fecha, 'BANCO'::text AS tipo_objeto, m.banco_destino_id AS objeto_id, 'INGRESO'::text AS flujo,
               m.monto::numeric AS monto, m.moneda_codigo, m.unidad_negocio_id
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado::text = 'CONFIRMADO' AND m.medio_destino::text = 'BANCO' AND m.banco_destino_id IS NOT NULL

        UNION ALL
        SELECT m.fecha, 'CAJA'::text AS tipo_objeto, m.caja_origen_id AS objeto_id, 'EGRESO'::text AS flujo,
               m.monto::numeric AS monto, m.moneda_codigo, m.unidad_negocio_id
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado::text = 'CONFIRMADO' AND m.medio_origen::text = 'CAJA' AND m.caja_origen_id IS NOT NULL

        UNION ALL
        SELECT m.fecha, 'BANCO'::text AS tipo_objeto, m.banco_origen_id AS objeto_id, 'EGRESO'::text AS flujo,
               m.monto::numeric AS monto, m.moneda_codigo, m.unidad_negocio_id
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado::text = 'CONFIRMADO' AND m.medio_origen::text = 'BANCO' AND m.banco_origen_id IS NOT NULL
    )
    """


def _fetch_tesoreria(filtros):
    where = ['e.fecha <= %s']
    params = [filtros['fecha_hasta']]
    if filtros.get('unidad_negocio_id'):
        where.append('e.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])

    sql = f"""
        {_tesoreria_entries_cte()}, saldos AS (
            SELECT
                e.tipo_objeto,
                e.objeto_id,
                e.moneda_codigo,
                COALESCE(SUM(CASE WHEN e.flujo = 'INGRESO' THEN e.monto ELSE e.monto * -1 END), 0) AS saldo
            FROM movimientos e
            WHERE {' AND '.join(where)}
            GROUP BY e.tipo_objeto, e.objeto_id, e.moneda_codigo
        ), objetos AS (
            SELECT
                'CAJA'::text AS tipo_objeto,
                c.id AS objeto_id,
                c.codigo AS codigo,
                c.nombre AS nombre,
                %s::text AS moneda_codigo
            FROM contabilidad.caja c
            WHERE c.activo = TRUE

            UNION ALL

            SELECT
                'BANCO'::text AS tipo_objeto,
                b.id AS objeto_id,
                b.numero_cuenta AS codigo,
                b.nombre_banco AS nombre,
                COALESCE(b.moneda_codigo, %s)::text AS moneda_codigo
            FROM contabilidad.cuenta_bancaria b
            WHERE b.activo = TRUE
        )
        SELECT
            o.tipo_objeto,
            o.codigo,
            o.nombre,
            COALESCE(s.moneda_codigo, o.moneda_codigo, %s) AS moneda_codigo,
            COALESCE(NULLIF(m.simbolo, ''), COALESCE(s.moneda_codigo, o.moneda_codigo, %s)) AS moneda_simbolo,
            COALESCE(s.saldo, 0) AS saldo
        FROM objetos o
        LEFT JOIN saldos s ON s.tipo_objeto = o.tipo_objeto AND s.objeto_id = o.objeto_id
        LEFT JOIN contabilidad.moneda m ON m.codigo = COALESCE(s.moneda_codigo, o.moneda_codigo, %s)
        ORDER BY ABS(COALESCE(s.saldo, 0)) DESC, o.tipo_objeto ASC, o.nombre ASC
    """
    rows = _db_rows(sql, params + [MONEDA_BASE, MONEDA_BASE, MONEDA_BASE, MONEDA_BASE, MONEDA_BASE])
    total_cajas = OrderedDict()
    total_bancos = OrderedDict()
    top = []
    for row in rows:
        saldo = _to_decimal(row.get('saldo'))
        codigo, simbolo = _currency_key(row)
        row['saldo'] = saldo
        row['saldo_label'] = _money_with_symbol(saldo, simbolo)
        target = total_cajas if row.get('tipo_objeto') == 'CAJA' else total_bancos
        if codigo not in target:
            target[codigo] = _new_currency_total(codigo, simbolo)
        target[codigo]['monto'] += saldo
        if saldo != 0 and len(top) < 5:
            top.append(row)

    cajas = _format_currency_totals(total_cajas.values(), amount_key='monto')
    bancos = _format_currency_totals(total_bancos.values(), amount_key='monto')
    return {
        'saldo_cajas': sum((item['monto'] for item in cajas['items']), Decimal('0.00')),
        'saldo_bancos': sum((item['monto'] for item in bancos['items']), Decimal('0.00')),
        'saldo_cajas_label': cajas['label'],
        'saldo_bancos_label': bancos['label'],
        'saldo_cajas_moneda_multiple': cajas['multiple'],
        'saldo_bancos_moneda_multiple': bancos['multiple'],
        'totales_cajas_por_moneda': cajas['items'],
        'totales_bancos_por_moneda': bancos['items'],
        'top': top,
    }

def _chart_view(monthly):
    values = [_to_decimal(row.get('resultado_neto')) for row in monthly]
    max_abs = max((abs(value) for value in values), default=Decimal('0.00'))
    width = 980
    height = 280
    pad_left = 44
    pad_right = 22
    pad_top = 28
    pad_bottom = 55
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    zero_y = pad_top + (plot_h / 2)
    step = plot_w / max(len(monthly), 1)
    bar_w = min(42, step * 0.56)
    max_h = (plot_h / 2) - 10
    series = []
    for idx, row in enumerate(monthly):
        value = _to_decimal(row.get('resultado_neto'))
        center_x = pad_left + (step * idx) + (step / 2)
        bar_h = 0
        if max_abs:
            bar_h = float((abs(value) / max_abs) * Decimal(str(max_h)))
        bar_h = max(bar_h, 1 if value else 0)
        if value >= 0:
            y = zero_y - bar_h
            value_y = max(y - 8, 10)
        else:
            y = zero_y
            value_y = min(zero_y + bar_h + 16, height - 8)
        series.append({
            'label': str(row.get('mes_label') or '')[:3],
            'value_label': _money(value),
            'tipo': 'positivo' if value >= 0 else 'negativo',
            'x': round(center_x - (bar_w / 2), 2),
            'center_x': round(center_x, 2),
            'bar_y': round(y, 2),
            'bar_width': round(bar_w, 2),
            'bar_height': round(bar_h, 2),
            'value_y': round(value_y, 2),
        })
    chart_currency = monthly[0] if monthly else {}
    return {
        'width': width,
        'height': height,
        'moneda_codigo': chart_currency.get('moneda_codigo') or '',
        'moneda_simbolo': chart_currency.get('moneda_simbolo') or '',
        'zero_y': round(zero_y, 2),
        'pad_left': pad_left,
        'pad_right': pad_right,
        'series': series,
        'has_data': bool(monthly) and max_abs != 0,
    }


def _build_report(filtros):
    estado_mes = _fetch_estado_mes(filtros)
    cxc = _fetch_cuentas_por_cobrar(filtros)
    cxp = _fetch_cuentas_por_pagar(filtros)
    tesoreria = _fetch_tesoreria(filtros)
    top_gastos = _fetch_top_gastos(filtros)
    monthly = _fetch_resultado_mensual(filtros)
    chart = _chart_view(monthly)
    return {
        'estado_mes': estado_mes,
        'cxc': cxc,
        'cxp': cxp,
        'tesoreria': tesoreria,
        'top_gastos': top_gastos,
        'monthly': monthly,
        'chart': chart,
    }


class ReportCanvas(Canvas):
    def __init__(self, *args, report_context=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_context = report_context or {}
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, total_pages: int):
        page_width, _ = self._pagesize
        user = self.report_context.get('emitted_by') or 'Sistema'
        self.saveState()
        self.setFont('Helvetica', 7.5)
        self.setFillColor(MUTED)
        self.drawString(16 * mm, 10 * mm, f'Generado por: {user}')
        self.drawRightString(page_width - 16 * mm, 10 * mm, f'Página {self._pageNumber} de {total_pages}')
        self.restoreState()


class BrandedDocTemplate(BaseDocTemplate):
    def __init__(self, *args, report_context=None, **kwargs):
        self.report_context = report_context or {}
        super().__init__(*args, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        template = PageTemplate(id='branded', frames=[frame], onPage=self._draw_header)
        self.addPageTemplates([template])

    def _draw_header(self, canvas, doc):
        title = self.report_context.get('title') or 'Reporte'
        subtitle = self.report_context.get('subtitle') or ''
        logo_file = self.report_context.get('logo_path')
        page_width, page_height = doc.pagesize
        x_left = doc.leftMargin
        x_right = page_width - doc.rightMargin
        header_top = page_height - 18 * mm

        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 18)
        canvas.drawString(x_left, header_top - 20, title)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(x_left, header_top - 37, subtitle)
        if logo_file:
            try:
                logo = ImageReader(logo_file)
                canvas.drawImage(
                    logo,
                    x_right - 38 * mm,
                    header_top - 42,
                    width=38 * mm,
                    height=12 * mm,
                    preserveAspectRatio=True,
                    mask='auto',
                    anchor='ne',
                )
            except Exception:
                pass
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(1)
        canvas.line(x_left, header_top - 54, x_right, header_top - 54)
        canvas.restoreState()


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DXTMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=8.2, leading=10, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTSection', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.6, leading=12, textColor=NAVY, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTRight', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_RIGHT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTCardLabel', parent=styles['Normal'], fontName='Helvetica', fontSize=6.8, leading=8, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTCardValue', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10.3, leading=12, textColor=NAVY, alignment=TA_LEFT))
    return styles


def _paragraph(value, style):
    return Paragraph(_safe_text(value), style)


def _make_table(columns, rows, widths, styles):
    header = [_paragraph(col.get('label', ''), styles['DXTCenter']) for col in columns]
    data = [header]
    for row in rows:
        rendered = []
        for idx, value in enumerate(row):
            align = columns[idx].get('align', 'left') if idx < len(columns) else 'left'
            style = styles['DXTRight'] if align == 'right' else styles['DXTCenter'] if align == 'center' else styles['DXTBody']
            rendered.append(_paragraph(value, style))
        data.append(rendered)
    table = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            table.setStyle(TableStyle([('BACKGROUND', (0, row_idx), (-1, row_idx), ROW_ALT)]))
    return table


def _build_chart_drawing(chart, width_pt, height_pt):
    width_pt = float(width_pt)
    height_pt = float(height_pt)
    base_w = float(chart.get('width') or 980)
    base_h = float(chart.get('height') or 280)
    sx = width_pt / base_w if base_w else 1.0
    sy = height_pt / base_h if base_h else 1.0

    drawing = Drawing(width_pt, height_pt)
    drawing.add(Rect(0, 0, width_pt, height_pt, rx=10, ry=10, fillColor=colors.white, strokeColor=BORDER, strokeWidth=0.9))

    zero_top = float(chart.get('zero_y') or 0)
    zero_y = height_pt - (zero_top * sy)
    drawing.add(Line((chart.get('pad_left', 0) * sx), zero_y, width_pt - (chart.get('pad_right', 0) * sx), zero_y, strokeColor=colors.HexColor('#c8d3df'), strokeWidth=0.8, strokeDashArray=[4, 3]))

    if chart.get('has_data'):
        for bar in chart.get('series', []):
            x = float(bar.get('x') or 0) * sx
            bar_y_top = float(bar.get('bar_y') or 0) * sy
            bar_h = float(bar.get('bar_height') or 0) * sy
            bar_w = float(bar.get('bar_width') or 0) * sx
            y = height_pt - bar_y_top - bar_h
            fill = GREEN if bar.get('tipo') == 'positivo' else RED
            drawing.add(Rect(x, y, bar_w, max(bar_h, 0), rx=3, ry=3, fillColor=fill, strokeColor=fill, strokeWidth=0.6))

            center_x = float(bar.get('center_x') or 0) * sx
            value_y = height_pt - (float(bar.get('value_y') or 0) * sy)
            label_y = height_pt - ((base_h - 22) * sy)
            drawing.add(String(center_x, value_y, str(bar.get('value_label') or '0.00'), textAnchor='middle', fontName='Helvetica', fontSize=7, fillColor=MUTED))
            drawing.add(String(center_x, label_y, str(bar.get('label') or ''), textAnchor='middle', fontName='Helvetica', fontSize=7.5, fillColor=TEXT))
    else:
        drawing.add(String(width_pt / 2, height_pt / 2, 'No existen datos suficientes para graficar.', textAnchor='middle', fontName='Helvetica', fontSize=9, fillColor=MUTED))

    return drawing


def _build_pdf(filtros, data, unidad):
    buffer = io.BytesIO()
    unidad_label = f"{unidad['codigo']} · {unidad['nombre']}" if unidad else 'Todas las unidades'
    context = {
        'title': 'Resumen ejecutivo mensual',
        'subtitle': f"{filtros['mes_label']} · {unidad_label} · Corte {filtros['fecha_hasta_label']}",
        'emitted_by': usuario_actual(),
        'logo_path': logo_path(),
    }
    doc = BrandedDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=48 * mm,
        bottomMargin=18 * mm,
        report_context=context,
    )
    styles = _pdf_styles()
    story = [
        _paragraph(
            'Reporte gerencial basado en comprobantes confirmados, cartera por cobrar, compromisos por pagar y tesorería confirmada. Los importes se presentan por moneda cuando corresponde.',
            styles['DXTMeta'],
        ),
        Spacer(1, 4 * mm),
    ]

    estado = data['estado_mes']
    cxc = data['cxc']
    cxp = data['cxp']
    tes = data['tesoreria']
    cards = [
        ('Ingresos del mes', estado['ingresos_label']),
        ('Egresos del mes', estado['egresos_label']),
        ('Resultado neto', estado['resultado_neto_label']),
        ('Cuentas por cobrar', cxc['saldo_pendiente_label']),
        ('Cuentas por pagar', cxp['saldo_pendiente_label']),
        ('Saldo en bancos', tes['saldo_bancos_label']),
        ('Saldo en cajas', tes['saldo_cajas_label']),
        ('Docs. CxC pendientes', str(cxc.get('documentos_pendientes', cxc.get('facturas_pendientes', 0)))),
    ]
    card_rows = []
    for idx in range(0, len(cards), 4):
        row = []
        for label, value in cards[idx:idx + 4]:
            row.append([_paragraph(label, styles['DXTCardLabel']), _paragraph(value, styles['DXTCardValue'])])
        card_rows.append(row)
    card_table = Table(card_rows, colWidths=[(doc.width / 4)] * 4)
    card_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT_ORANGE),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(card_table)
    story.append(Spacer(1, 5 * mm))

    # Secciones en dos columnas para ahorrar espacio.
    cxc_rows = [[str(i), row.get('auxiliar') or '', row.get('origen_label') or '', str(row.get('documentos') or 0), row.get('saldo_pendiente_label') or '0.00'] for i, row in enumerate(cxc['top'], 1)]
    if not cxc_rows:
        cxc_rows = [['-', 'Sin datos pendientes', '-', '-', '0.00']]
    gastos_rows = [[str(i), f"{row.get('codigo') or ''} · {row.get('cuenta') or ''}", row.get('monto_label') or '0.00'] for i, row in enumerate(data['top_gastos'], 1)]
    if not gastos_rows:
        gastos_rows = [['-', 'Sin gastos registrados', '0.00']]

    left_story = [
        _paragraph('Top 5 clientes deudores', styles['DXTSection']),
        Spacer(1, 2 * mm),
        _make_table(
            [{'label': '#', 'align': 'center'}, {'label': 'Cliente'}, {'label': 'Origen'}, {'label': 'Docs.', 'align': 'center'}, {'label': 'Saldo', 'align': 'right'}],
            cxc_rows,
            [8, 49, 24, 12, 26],
            styles,
        ),
    ]
    right_story = [
        _paragraph('Top 5 gastos/costos del mes', styles['DXTSection']),
        Spacer(1, 2 * mm),
        _make_table(
            [{'label': '#', 'align': 'center'}, {'label': 'Cuenta'}, {'label': 'Monto', 'align': 'right'}],
            gastos_rows,
            [8, 78, 28],
            styles,
        ),
    ]
    two_col = Table([[left_story, right_story]], colWidths=[doc.width / 2 - 3 * mm, doc.width / 2 - 3 * mm])
    two_col.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story.append(two_col)
    story.append(Spacer(1, 5 * mm))

    tes_rows = [[str(i), row.get('tipo_objeto') or '', f"{row.get('nombre') or ''} {row.get('codigo') or ''}", row.get('saldo_label') or '0.00'] for i, row in enumerate(tes['top'], 1)]
    if not tes_rows:
        tes_rows = [['-', '-', 'Sin saldos registrados', '0.00']]
    monthly_rows = [[row['mes_label'], row['resultado_neto_label']] for row in data['monthly']]

    left_story = [
        _paragraph('Top 5 bancos/cajas con saldo', styles['DXTSection']),
        Spacer(1, 2 * mm),
        _make_table(
            [{'label': '#', 'align': 'center'}, {'label': 'Tipo', 'align': 'center'}, {'label': 'Cuenta/Caja'}, {'label': 'Saldo', 'align': 'right'}],
            tes_rows,
            [8, 18, 58, 28],
            styles,
        ),
    ]
    right_story = [
        _paragraph(f"Resultado neto por mes · {filtros['gestion']}", styles['DXTSection']),
        Spacer(1, 2 * mm),
        _make_table(
            [{'label': 'Mes'}, {'label': 'Resultado', 'align': 'right'}],
            monthly_rows,
            [58, 55],
            styles,
        ),
    ]
    two_col = Table([[left_story, right_story]], colWidths=[doc.width / 2 - 3 * mm, doc.width / 2 - 3 * mm])
    two_col.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story.append(two_col)
    story.append(Spacer(1, 5 * mm))

    story.append(_paragraph(f"Gráfico de resultado neto por mes · {filtros['gestion']}", styles['DXTSection']))
    story.append(Spacer(1, 2 * mm))
    chart_width = max(float(doc.width), 320.0)
    chart_height = 62 * mm
    story.append(_build_chart_drawing(data['chart'], chart_width, chart_height))

    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


@resumen_ejecutivo_mensual_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    error = ''
    try:
        filtros = _build_filters(request.args)
        data = _build_report(filtros)
    except ValueError as exc:
        filtros = _build_filters({})
        data = _build_report(filtros)
        error = str(exc)
    except Exception as exc:
        filtros = _build_filters({})
        data = {
            'estado_mes': {'ingresos_label': 'BOB 0.00', 'egresos_label': 'BOB 0.00', 'resultado_neto_label': 'BOB 0.00', 'resultado_tipo': 'positivo', 'moneda_multiple': False, 'totales_por_moneda': []},
            'cxc': {'saldo_pendiente_label': 'BOB 0.00', 'facturas_pendientes': 0, 'documentos_pendientes': 0, 'moneda_multiple': False, 'totales_por_moneda': [], 'top': []},
            'cxp': {'saldo_pendiente_label': 'Bs 0.00', 'documentos': 0},
            'tesoreria': {'saldo_bancos_label': 'BOB 0.00', 'saldo_cajas_label': 'BOB 0.00', 'saldo_bancos_moneda_multiple': False, 'saldo_cajas_moneda_multiple': False, 'totales_bancos_por_moneda': [], 'totales_cajas_por_moneda': [], 'top': []},
            'top_gastos': [],
            'monthly': [],
            'chart': _chart_view([]),
        }
        error = f'No se pudo cargar el resumen ejecutivo mensual. {exc}'

    unidades = _fetch_unidades()
    gestiones = _fetch_gestiones()
    unidad = _resolve_unidad(filtros.get('unidad_negocio_id'))
    return render_template(
        'resumen_ejecutivo_mensual_index.html',
        filtros=filtros,
        gestiones=gestiones,
        meses=MESES_ES,
        unidades=unidades,
        unidad=unidad,
        data=data,
        error=error,
        query_args=request.args.to_dict(flat=True),
    )


@resumen_ejecutivo_mensual_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _build_filters(request.args)
        data = _build_report(filtros)
        unidad = _resolve_unidad(filtros.get('unidad_negocio_id'))
        pdf_bytes = _build_pdf(filtros, data, unidad)
        filename = f"resumen_ejecutivo_mensual_{filtros['gestion']}_{filtros['mes']:02d}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF del resumen ejecutivo mensual. {exc}', status=500, mimetype='text/plain')


@resumen_ejecutivo_mensual_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('resumen_ejecutivo_mensual_help.html')
