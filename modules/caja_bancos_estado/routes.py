# ============================================================
# DXT CONTA - Reporte Especial
# Estado de Caja y Bancos
# ============================================================

from __future__ import annotations

import io
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.sax.saxutils import escape

from flask import Response, jsonify, render_template, request
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from database.db_manager import DatabaseManager
from modules.caja_bancos_estado import caja_bancos_estado_bp
from modules.reportes_rapidos.core.utils import logo_path, usuario_actual
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
CENTAVO = Decimal('0.01')
ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
GREEN = colors.HexColor('#107c41')
RED = colors.HexColor('#b42318')

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
    if value is None:
        return Decimal('0.00')
    try:
        return Decimal(str(value)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _to_float(value) -> float:
    return float(_to_decimal(value))


def _money(value, moneda='BOB') -> str:
    amount = _to_decimal(value)
    symbol = 'Bs' if (moneda or 'BOB').upper() == 'BOB' else (moneda or '')
    return f'{symbol} {amount:,.2f}'


def _amount(value) -> str:
    return f'{_to_decimal(value):,.2f}'


def _safe_text(value) -> str:
    return escape(str(value if value is not None else ''))


def _parse_date(value, field_name, default=None):
    value = _clean(value)
    if not value:
        if default is not None:
            return default
        raise ValueError(f'{field_name} es obligatorio.')
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no tiene formato válido.') from exc


def _parse_month(value, field_name):
    value = _clean(value)
    try:
        parsed = datetime.strptime(value, '%Y-%m').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no tiene formato válido.') from exc
    return date(parsed.year, parsed.month, 1)


def _month_end(month_start: date) -> date:
    return date(month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1])


def _add_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _month_list(start: date, end: date):
    months = []
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while current <= last:
        months.append({
            'key': current.strftime('%Y-%m'),
            'label': f'{MESES_ES[current.month]} {current.year}',
            'short': f'{MESES_ES[current.month][:3]} {current.year}',
            'date': current,
        })
        current = _add_month(current)
    return months


def _parse_optional_int(value, field_name):
    value = _clean(value)
    if not value:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} no es válido.') from exc
    if parsed <= 0:
        raise ValueError(f'{field_name} no es válido.')
    return parsed


def _catalogos(db):
    unidades = db.execute_query(
        """
        SELECT id, codigo, nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY codigo, nombre
        """
    )
    monedas = db.execute_query(
        """
        SELECT codigo, nombre, simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        ORDER BY CASE WHEN codigo = 'BOB' THEN 0 ELSE 1 END, codigo
        """
    )
    return unidades, monedas


def _ultima_fecha_movimiento(db):
    rows = db.execute_query(
        f"""
        {_entries_cte()}
        SELECT MAX(e.fecha)::date AS fecha
        FROM movimientos e
        """
    )
    if rows and rows[0].get('fecha'):
        return rows[0]['fecha']
    return date.today()


def _entry_filters(prefix=''):
    clauses = []
    params = []
    tipo = _clean(request.args.get(f'{prefix}tipo')).upper() or 'TODOS'
    unidad_id = _parse_optional_int(request.args.get(f'{prefix}unidad_id'), 'Unidad de negocio')
    moneda = _clean(request.args.get(f'{prefix}moneda')).upper()

    if tipo not in ('TODOS', 'CAJA', 'BANCO'):
        tipo = 'TODOS'
    if tipo != 'TODOS':
        clauses.append('e.tipo_objeto = %s')
        params.append(tipo)
    if unidad_id:
        clauses.append('e.unidad_negocio_id = %s')
        params.append(unidad_id)
    if moneda:
        clauses.append('e.moneda_codigo = %s')
        params.append(moneda)
    return tipo, unidad_id, moneda, clauses, params


def _entries_cte():
    return """
    WITH movimientos AS (
        SELECT
            c.fecha,
            'CAJA'::text AS tipo_objeto,
            c.caja_id AS objeto_id,
            'INGRESO'::text AS flujo,
            c.monto_total::numeric AS monto,
            c.moneda_codigo,
            c.unidad_negocio_id,
            CASE
                WHEN c.origen_operacion = 'DOCUMENTO_COBRAR' THEN 'Cobro Doc. CxC'
                WHEN c.origen_operacion = 'COMPROMISO' THEN 'Cobro compromiso'
                ELSE 'Cobro directo'
            END AS origen,
            c.id AS documento_id,
            COALESCE(NULLIF(doc.documentos, ''), NULLIF(c.referencia, ''), 'Cobro #' || c.id::text) AS documento,
            c.glosa
        FROM contabilidad.cobro c
        LEFT JOIN LATERAL (
            SELECT string_agg(x.documento, ', ' ORDER BY x.documento) AS documentos
            FROM (
                SELECT DISTINCT d.tipo_documento || ' ' || d.numero_documento AS documento
                FROM contabilidad.documento_por_cobrar_aplicacion a
                JOIN contabilidad.documento_por_cobrar d ON d.id = a.documento_por_cobrar_id
                WHERE a.cobro_id = c.id

                UNION

                SELECT DISTINCT 'Factura ' || f.numero_factura AS documento
                FROM contabilidad.factura_aplicacion fa
                JOIN contabilidad.factura_electronica f ON f.id = fa.factura_electronica_id
                WHERE fa.cobro_id = c.id
            ) x
        ) doc ON TRUE
        WHERE c.estado = 'CONFIRMADO'
          AND c.medio_pago = 'CAJA'
          AND c.caja_id IS NOT NULL

        UNION ALL

        SELECT
            c.fecha,
            'BANCO'::text AS tipo_objeto,
            c.cuenta_bancaria_id AS objeto_id,
            'INGRESO'::text AS flujo,
            c.monto_total::numeric AS monto,
            c.moneda_codigo,
            c.unidad_negocio_id,
            CASE
                WHEN c.origen_operacion = 'DOCUMENTO_COBRAR' THEN 'Cobro Doc. CxC'
                WHEN c.origen_operacion = 'COMPROMISO' THEN 'Cobro compromiso'
                ELSE 'Cobro directo'
            END AS origen,
            c.id AS documento_id,
            COALESCE(NULLIF(doc.documentos, ''), NULLIF(c.referencia, ''), 'Cobro #' || c.id::text) AS documento,
            c.glosa
        FROM contabilidad.cobro c
        LEFT JOIN LATERAL (
            SELECT string_agg(x.documento, ', ' ORDER BY x.documento) AS documentos
            FROM (
                SELECT DISTINCT d.tipo_documento || ' ' || d.numero_documento AS documento
                FROM contabilidad.documento_por_cobrar_aplicacion a
                JOIN contabilidad.documento_por_cobrar d ON d.id = a.documento_por_cobrar_id
                WHERE a.cobro_id = c.id

                UNION

                SELECT DISTINCT 'Factura ' || f.numero_factura AS documento
                FROM contabilidad.factura_aplicacion fa
                JOIN contabilidad.factura_electronica f ON f.id = fa.factura_electronica_id
                WHERE fa.cobro_id = c.id
            ) x
        ) doc ON TRUE
        WHERE c.estado = 'CONFIRMADO'
          AND c.medio_pago = 'BANCO'
          AND c.cuenta_bancaria_id IS NOT NULL

        UNION ALL

        SELECT
            p.fecha,
            'CAJA'::text AS tipo_objeto,
            p.caja_id AS objeto_id,
            'EGRESO'::text AS flujo,
            p.monto_total::numeric AS monto,
            p.moneda_codigo,
            p.unidad_negocio_id,
            CASE
                WHEN p.origen_operacion = 'COMPROMISO' THEN 'Pago compromiso'
                ELSE 'Pago directo'
            END AS origen,
            p.id AS documento_id,
            COALESCE(NULLIF(p.referencia, ''), 'Pago #' || p.id::text) AS documento,
            p.glosa
        FROM contabilidad.pago p
        WHERE p.estado = 'CONFIRMADO'
          AND p.medio_pago = 'CAJA'
          AND p.caja_id IS NOT NULL

        UNION ALL

        SELECT
            p.fecha,
            'BANCO'::text AS tipo_objeto,
            p.cuenta_bancaria_id AS objeto_id,
            'EGRESO'::text AS flujo,
            p.monto_total::numeric AS monto,
            p.moneda_codigo,
            p.unidad_negocio_id,
            CASE
                WHEN p.origen_operacion = 'COMPROMISO' THEN 'Pago compromiso'
                ELSE 'Pago directo'
            END AS origen,
            p.id AS documento_id,
            COALESCE(NULLIF(p.referencia, ''), 'Pago #' || p.id::text) AS documento,
            p.glosa
        FROM contabilidad.pago p
        WHERE p.estado = 'CONFIRMADO'
          AND p.medio_pago = 'BANCO'
          AND p.cuenta_bancaria_id IS NOT NULL

        UNION ALL

        SELECT
            m.fecha,
            'CAJA'::text AS tipo_objeto,
            m.caja_destino_id AS objeto_id,
            'INGRESO'::text AS flujo,
            m.monto::numeric AS monto,
            m.moneda_codigo,
            m.unidad_negocio_id,
            CASE
                WHEN m.tipo_movimiento = 'TRANSFERENCIA' THEN 'Transferencia recibida'
                ELSE 'Ingreso tesorería'
            END AS origen,
            m.id AS documento_id,
            COALESCE(NULLIF(m.referencia, ''), 'Movimiento #' || m.id::text) AS documento,
            m.glosa
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado = 'CONFIRMADO'
          AND m.medio_destino = 'CAJA'
          AND m.caja_destino_id IS NOT NULL

        UNION ALL

        SELECT
            m.fecha,
            'BANCO'::text AS tipo_objeto,
            m.banco_destino_id AS objeto_id,
            'INGRESO'::text AS flujo,
            m.monto::numeric AS monto,
            m.moneda_codigo,
            m.unidad_negocio_id,
            CASE
                WHEN m.tipo_movimiento = 'TRANSFERENCIA' THEN 'Transferencia recibida'
                ELSE 'Ingreso tesorería'
            END AS origen,
            m.id AS documento_id,
            COALESCE(NULLIF(m.referencia, ''), 'Movimiento #' || m.id::text) AS documento,
            m.glosa
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado = 'CONFIRMADO'
          AND m.medio_destino = 'BANCO'
          AND m.banco_destino_id IS NOT NULL

        UNION ALL

        SELECT
            m.fecha,
            'CAJA'::text AS tipo_objeto,
            m.caja_origen_id AS objeto_id,
            'EGRESO'::text AS flujo,
            m.monto::numeric AS monto,
            m.moneda_codigo,
            m.unidad_negocio_id,
            CASE
                WHEN m.tipo_movimiento = 'TRANSFERENCIA' THEN 'Transferencia enviada'
                ELSE 'Egreso tesorería'
            END AS origen,
            m.id AS documento_id,
            COALESCE(NULLIF(m.referencia, ''), 'Movimiento #' || m.id::text) AS documento,
            m.glosa
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado = 'CONFIRMADO'
          AND m.medio_origen = 'CAJA'
          AND m.caja_origen_id IS NOT NULL

        UNION ALL

        SELECT
            m.fecha,
            'BANCO'::text AS tipo_objeto,
            m.banco_origen_id AS objeto_id,
            'EGRESO'::text AS flujo,
            m.monto::numeric AS monto,
            m.moneda_codigo,
            m.unidad_negocio_id,
            CASE
                WHEN m.tipo_movimiento = 'TRANSFERENCIA' THEN 'Transferencia enviada'
                ELSE 'Egreso tesorería'
            END AS origen,
            m.id AS documento_id,
            COALESCE(NULLIF(m.referencia, ''), 'Movimiento #' || m.id::text) AS documento,
            m.glosa
        FROM contabilidad.movimiento_tesoreria m
        WHERE m.estado = 'CONFIRMADO'
          AND m.medio_origen = 'BANCO'
          AND m.banco_origen_id IS NOT NULL
    )
    """

def _saldos_actuales(db, fecha_corte, tipo='TODOS', unidad_id=None, moneda=None):
    moneda = _clean(moneda).upper() or None
    where = ['e.fecha <= %s']
    params = [fecha_corte]
    if tipo != 'TODOS':
        where.append('e.tipo_objeto = %s')
        params.append(tipo)
    if unidad_id:
        where.append('e.unidad_negocio_id = %s')
        params.append(unidad_id)
    if moneda:
        where.append('e.moneda_codigo = %s')
        params.append(moneda)

    sql = f"""
    {_entries_cte()}, saldos AS (
        SELECT
            e.tipo_objeto,
            e.objeto_id,
            e.moneda_codigo,
            COALESCE(SUM(CASE WHEN e.flujo = 'INGRESO' THEN e.monto ELSE e.monto * -1 END), 0) AS saldo,
            COALESCE(SUM(CASE WHEN e.flujo = 'INGRESO' THEN e.monto ELSE 0 END), 0) AS ingresos,
            COALESCE(SUM(CASE WHEN e.flujo = 'EGRESO' THEN e.monto ELSE 0 END), 0) AS egresos,
            COUNT(*) AS movimientos
        FROM movimientos e
        WHERE {' AND '.join(where)}
        GROUP BY e.tipo_objeto, e.objeto_id, e.moneda_codigo
    ), cuentas AS (
        SELECT
            'CAJA'::text AS tipo_objeto,
            c.id AS objeto_id,
            c.codigo,
            c.nombre,
            c.cuenta_contable_codigo,
            cu.nombre AS cuenta_contable_nombre,
            'BOB'::varchar AS moneda_codigo,
            NULL::bigint AS unidad_negocio_id,
            NULL::varchar AS unidad_codigo,
            NULL::varchar AS unidad_nombre,
            TRUE AS activo
        FROM contabilidad.caja c
        LEFT JOIN contabilidad.cuenta cu ON cu.codigo = c.cuenta_contable_codigo
        WHERE c.activo = TRUE

        UNION ALL

        SELECT
            'BANCO'::text AS tipo_objeto,
            b.id AS objeto_id,
            b.numero_cuenta AS codigo,
            b.nombre_banco AS nombre,
            b.cuenta_contable_codigo,
            cu.nombre AS cuenta_contable_nombre,
            b.moneda_codigo,
            b.unidad_negocio_id,
            un.codigo AS unidad_codigo,
            un.nombre AS unidad_nombre,
            b.activo
        FROM contabilidad.cuenta_bancaria b
        LEFT JOIN contabilidad.cuenta cu ON cu.codigo = b.cuenta_contable_codigo
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = b.unidad_negocio_id
        WHERE b.activo = TRUE
    )
    SELECT
        c.tipo_objeto,
        c.objeto_id,
        c.codigo,
        c.nombre,
        c.cuenta_contable_codigo,
        COALESCE(c.cuenta_contable_nombre, '') AS cuenta_contable_nombre,
        c.unidad_negocio_id,
        COALESCE(c.unidad_codigo, '') AS unidad_codigo,
        COALESCE(c.unidad_nombre, '') AS unidad_nombre,
        COALESCE(s.moneda_codigo, c.moneda_codigo, 'BOB') AS moneda_codigo,
        COALESCE(s.ingresos, 0) AS ingresos,
        COALESCE(s.egresos, 0) AS egresos,
        COALESCE(s.saldo, 0) AS saldo,
        COALESCE(s.movimientos, 0) AS movimientos
    FROM cuentas c
    LEFT JOIN saldos s
      ON s.tipo_objeto = c.tipo_objeto
     AND s.objeto_id = c.objeto_id
    WHERE (%s = 'TODOS' OR c.tipo_objeto = %s)
      AND (%s::bigint IS NULL OR c.tipo_objeto = 'CAJA' OR c.unidad_negocio_id = %s)
      AND (%s::varchar IS NULL OR COALESCE(s.moneda_codigo, c.moneda_codigo, 'BOB') = %s)
    ORDER BY c.tipo_objeto, c.nombre, c.codigo, COALESCE(s.moneda_codigo, c.moneda_codigo, 'BOB')
    """
    params.extend([tipo, tipo, unidad_id, unidad_id, moneda, moneda])
    rows = db.execute_query(sql, tuple(params))
    result = []
    for row in rows:
        result.append({
            'tipo_objeto': row['tipo_objeto'],
            'objeto_id': int(row['objeto_id']),
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'cuenta_codigo': row['cuenta_contable_codigo'],
            'cuenta_nombre': row['cuenta_contable_nombre'],
            'unidad': f"{row['unidad_codigo']} · {row['unidad_nombre']}" if row['unidad_codigo'] else 'Compartida / no definida',
            'moneda_codigo': row['moneda_codigo'] or 'BOB',
            'ingresos': _to_float(row['ingresos']),
            'egresos': _to_float(row['egresos']),
            'saldo': _to_float(row['saldo']),
            'movimientos': int(row['movimientos'] or 0),
        })
    return result

def _resumen_saldos(rows):
    por_moneda = {}
    for row in rows:
        moneda_codigo = row.get('moneda_codigo') or 'BOB'
        if moneda_codigo not in por_moneda:
            por_moneda[moneda_codigo] = {
                'moneda_codigo': moneda_codigo,
                'total_cajas': Decimal('0.00'),
                'total_bancos': Decimal('0.00'),
                'ingresos': Decimal('0.00'),
                'egresos': Decimal('0.00'),
                'cantidad': 0,
            }
        bucket = por_moneda[moneda_codigo]
        saldo = _to_decimal(row.get('saldo'))
        if row.get('tipo_objeto') == 'CAJA':
            bucket['total_cajas'] += saldo
        else:
            bucket['total_bancos'] += saldo
        bucket['ingresos'] += _to_decimal(row.get('ingresos'))
        bucket['egresos'] += _to_decimal(row.get('egresos'))
        bucket['cantidad'] += 1

    lista = []
    for moneda_codigo in sorted(por_moneda):
        bucket = por_moneda[moneda_codigo]
        total_general = bucket['total_cajas'] + bucket['total_bancos']
        lista.append({
            'moneda_codigo': moneda_codigo,
            'total_cajas': _to_float(bucket['total_cajas']),
            'total_bancos': _to_float(bucket['total_bancos']),
            'total_general': _to_float(total_general),
            'ingresos': _to_float(bucket['ingresos']),
            'egresos': _to_float(bucket['egresos']),
            'cantidad': bucket['cantidad'],
        })

    if lista:
        principal = lista[0]
    else:
        principal = {
            'moneda_codigo': 'BOB',
            'total_cajas': 0.0,
            'total_bancos': 0.0,
            'total_general': 0.0,
            'ingresos': 0.0,
            'egresos': 0.0,
            'cantidad': 0,
        }

    return {
        **principal,
        'por_moneda': lista,
        'monedas_count': len(lista),
        'cantidad': len(rows),
    }

def _detalle_movimientos(db, tipo_objeto, objeto_id, fecha_hasta, unidad_id=None, moneda=None, fecha_desde=None):
    tipo_objeto = _clean(tipo_objeto).upper()
    if tipo_objeto not in ('CAJA', 'BANCO'):
        raise ValueError('Tipo de tesorería no válido.')
    objeto_id = int(objeto_id)

    base_where = ['e.tipo_objeto = %s', 'e.objeto_id = %s', 'e.fecha <= %s']
    params = [tipo_objeto, objeto_id, fecha_hasta]
    if unidad_id:
        base_where.append('e.unidad_negocio_id = %s')
        params.append(unidad_id)
    if moneda:
        base_where.append('e.moneda_codigo = %s')
        params.append(moneda)

    saldo_anterior = Decimal('0.00')
    if fecha_desde:
        before_where = ['e.tipo_objeto = %s', 'e.objeto_id = %s', 'e.fecha < %s']
        before_params = [tipo_objeto, objeto_id, fecha_desde]
        if unidad_id:
            before_where.append('e.unidad_negocio_id = %s')
            before_params.append(unidad_id)
        if moneda:
            before_where.append('e.moneda_codigo = %s')
            before_params.append(moneda)
        anterior_row = db.execute_query(
            f"""
            {_entries_cte()}
            SELECT COALESCE(SUM(CASE WHEN e.flujo = 'INGRESO' THEN e.monto ELSE e.monto * -1 END), 0) AS saldo
            FROM movimientos e
            WHERE {' AND '.join(before_where)}
            """,
            tuple(before_params),
        )[0]
        saldo_anterior = _to_decimal(anterior_row['saldo'])
        base_where.append('e.fecha >= %s')
        params.append(fecha_desde)

    rows = db.execute_query(
        f"""
        {_entries_cte()}
        SELECT
            e.fecha,
            e.flujo,
            e.monto,
            e.moneda_codigo,
            e.origen,
            e.documento_id,
            e.documento,
            e.glosa,
            un.codigo AS unidad_codigo,
            un.nombre AS unidad_nombre
        FROM movimientos e
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = e.unidad_negocio_id
        WHERE {' AND '.join(base_where)}
        ORDER BY e.fecha, e.origen, e.documento_id
        """,
        tuple(params),
    )

    saldo = saldo_anterior
    detalle = []
    total_ingresos = Decimal('0.00')
    total_egresos = Decimal('0.00')
    for row in rows:
        monto = _to_decimal(row['monto'])
        ingreso = monto if row['flujo'] == 'INGRESO' else Decimal('0.00')
        egreso = monto if row['flujo'] == 'EGRESO' else Decimal('0.00')
        saldo += ingreso - egreso
        total_ingresos += ingreso
        total_egresos += egreso
        detalle.append({
            'fecha': row['fecha'].strftime('%Y-%m-%d') if row['fecha'] else '',
            'flujo': row['flujo'],
            'origen': row['origen'],
            'documento': row['documento'],
            'glosa': row['glosa'],
            'unidad': f"{row['unidad_codigo']} · {row['unidad_nombre']}" if row['unidad_codigo'] else '',
            'moneda_codigo': row['moneda_codigo'],
            'ingreso': _to_float(ingreso),
            'egreso': _to_float(egreso),
            'saldo': _to_float(saldo),
        })

    return {
        'saldo_anterior': _to_float(saldo_anterior),
        'ingresos': _to_float(total_ingresos),
        'egresos': _to_float(total_egresos),
        'saldo_final': _to_float(saldo),
        'movimientos': detalle,
    }


def _nombre_objeto(db, tipo_objeto, objeto_id):
    if tipo_objeto == 'CAJA':
        rows = db.execute_query(
            """
            SELECT c.codigo, c.nombre, c.cuenta_contable_codigo, COALESCE(cu.nombre, '') AS cuenta_nombre
            FROM contabilidad.caja c
            LEFT JOIN contabilidad.cuenta cu ON cu.codigo = c.cuenta_contable_codigo
            WHERE c.id = %s
            """,
            (objeto_id,),
        )
    else:
        rows = db.execute_query(
            """
            SELECT b.numero_cuenta AS codigo, b.nombre_banco AS nombre,
                   b.cuenta_contable_codigo, COALESCE(cu.nombre, '') AS cuenta_nombre
            FROM contabilidad.cuenta_bancaria b
            LEFT JOIN contabilidad.cuenta cu ON cu.codigo = b.cuenta_contable_codigo
            WHERE b.id = %s
            """,
            (objeto_id,),
        )
    if not rows:
        raise ValueError('No se encontró la caja o banco seleccionado.')
    row = rows[0]
    return {
        'codigo': row['codigo'],
        'nombre': row['nombre'],
        'cuenta_codigo': row['cuenta_contable_codigo'],
        'cuenta_nombre': row['cuenta_nombre'],
    }


def _monthly_params():
    today = date.today()
    periodo = _clean(request.args.get('mensual_periodo')).lower() or 'gestion'
    gestion = _clean(request.args.get('mensual_gestion')) or str(today.year)
    tipo = _clean(request.args.get('mensual_tipo')).upper() or 'TODOS'
    unidad_id = _parse_optional_int(request.args.get('mensual_unidad_id'), 'Unidad de negocio')
    moneda = _clean(request.args.get('mensual_moneda')).upper()

    if tipo not in ('TODOS', 'CAJA', 'BANCO'):
        tipo = 'TODOS'
    if periodo not in ('gestion', 'rango'):
        periodo = 'gestion'

    if periodo == 'rango':
        mes_desde = _parse_month(request.args.get('mes_desde'), 'Mes desde')
        mes_hasta = _parse_month(request.args.get('mes_hasta'), 'Mes hasta')
        if mes_desde > mes_hasta:
            raise ValueError('El mes desde no puede ser posterior al mes hasta.')
    else:
        try:
            year = int(gestion)
        except (TypeError, ValueError) as exc:
            raise ValueError('La gestión no es válida.') from exc
        mes_desde = date(year, 1, 1)
        mes_hasta = date(year, 12, 1)

    return {
        'periodo': periodo,
        'gestion': gestion,
        'mes_desde': mes_desde,
        'mes_hasta': mes_hasta,
        'fecha_desde': mes_desde,
        'fecha_hasta': _month_end(mes_hasta),
        'tipo': tipo,
        'unidad_id': unidad_id,
        'moneda': moneda,
    }


def _comparativo_mensual(db, params):
    months = _month_list(params['mes_desde'], params['mes_hasta'])
    where = ['e.fecha BETWEEN %s AND %s']
    sql_params = [params['fecha_desde'], params['fecha_hasta']]
    if params['tipo'] != 'TODOS':
        where.append('e.tipo_objeto = %s')
        sql_params.append(params['tipo'])
    if params['unidad_id']:
        where.append('e.unidad_negocio_id = %s')
        sql_params.append(params['unidad_id'])
    if params['moneda']:
        where.append('e.moneda_codigo = %s')
        sql_params.append(params['moneda'])

    rows = db.execute_query(
        f"""
        {_entries_cte()}, base AS (
            SELECT
                e.tipo_objeto,
                e.objeto_id,
                e.moneda_codigo,
                date_trunc('month', e.fecha)::date AS mes,
                COALESCE(SUM(CASE WHEN e.flujo = 'INGRESO' THEN e.monto ELSE 0 END), 0) AS ingresos,
                COALESCE(SUM(CASE WHEN e.flujo = 'EGRESO' THEN e.monto ELSE 0 END), 0) AS egresos,
                COUNT(*) AS movimientos
            FROM movimientos e
            WHERE {' AND '.join(where)}
            GROUP BY e.tipo_objeto, e.objeto_id, e.moneda_codigo, date_trunc('month', e.fecha)::date
        ), cuentas AS (
            SELECT
                'CAJA'::text AS tipo_objeto,
                c.id AS objeto_id,
                c.codigo,
                c.nombre,
                c.cuenta_contable_codigo,
                COALESCE(cu.nombre, '') AS cuenta_contable_nombre,
                'BOB'::varchar AS moneda_maestro,
                NULL::bigint AS unidad_negocio_id,
                NULL::varchar AS unidad_codigo,
                NULL::varchar AS unidad_nombre
            FROM contabilidad.caja c
            LEFT JOIN contabilidad.cuenta cu ON cu.codigo = c.cuenta_contable_codigo
            WHERE c.activo = TRUE

            UNION ALL

            SELECT
                'BANCO'::text AS tipo_objeto,
                b.id AS objeto_id,
                b.numero_cuenta AS codigo,
                b.nombre_banco AS nombre,
                b.cuenta_contable_codigo,
                COALESCE(cu.nombre, '') AS cuenta_contable_nombre,
                b.moneda_codigo AS moneda_maestro,
                b.unidad_negocio_id,
                un.codigo AS unidad_codigo,
                un.nombre AS unidad_nombre
            FROM contabilidad.cuenta_bancaria b
            LEFT JOIN contabilidad.cuenta cu ON cu.codigo = b.cuenta_contable_codigo
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = b.unidad_negocio_id
            WHERE b.activo = TRUE
        )
        SELECT
            b.tipo_objeto,
            b.objeto_id,
            b.moneda_codigo,
            b.mes,
            b.ingresos,
            b.egresos,
            b.movimientos,
            c.codigo,
            c.nombre,
            c.cuenta_contable_codigo,
            c.cuenta_contable_nombre,
            c.unidad_codigo,
            c.unidad_nombre
        FROM base b
        JOIN cuentas c
          ON c.tipo_objeto = b.tipo_objeto
         AND c.objeto_id = b.objeto_id
        ORDER BY b.tipo_objeto, c.nombre, c.codigo, b.moneda_codigo, b.mes
        """,
        tuple(sql_params),
    )

    account_map = {}
    for row in rows:
        key = (row['tipo_objeto'], int(row['objeto_id']), row['moneda_codigo'])
        if key not in account_map:
            account_map[key] = {
                'tipo_objeto': row['tipo_objeto'],
                'objeto_id': int(row['objeto_id']),
                'codigo': row['codigo'],
                'nombre': row['nombre'],
                'cuenta_codigo': row['cuenta_contable_codigo'],
                'cuenta_nombre': row['cuenta_contable_nombre'],
                'unidad': f"{row['unidad_codigo']} · {row['unidad_nombre']}" if row['unidad_codigo'] else 'Compartida / no definida',
                'moneda_codigo': row['moneda_codigo'],
                'months': {m['key']: {'ingresos': Decimal('0.00'), 'egresos': Decimal('0.00'), 'neto': Decimal('0.00')} for m in months},
                'total_ingresos': Decimal('0.00'),
                'total_egresos': Decimal('0.00'),
                'total_neto': Decimal('0.00'),
            }
        mes_key = row['mes'].strftime('%Y-%m')
        ingresos = _to_decimal(row['ingresos'])
        egresos = _to_decimal(row['egresos'])
        neto = ingresos - egresos
        account_map[key]['months'][mes_key] = {'ingresos': ingresos, 'egresos': egresos, 'neto': neto}
        account_map[key]['total_ingresos'] += ingresos
        account_map[key]['total_egresos'] += egresos
        account_map[key]['total_neto'] += neto

    accounts = []
    totals = {m['key']: {'ingresos': Decimal('0.00'), 'egresos': Decimal('0.00'), 'neto': Decimal('0.00')} for m in months}
    totals_by_currency = {}
    total_ingresos = Decimal('0.00')
    total_egresos = Decimal('0.00')
    total_neto = Decimal('0.00')

    for item in account_map.values():
        moneda_codigo = item['moneda_codigo'] or 'BOB'
        if moneda_codigo not in totals_by_currency:
            totals_by_currency[moneda_codigo] = {
                'moneda_codigo': moneda_codigo,
                'months': {m['key']: {'ingresos': Decimal('0.00'), 'egresos': Decimal('0.00'), 'neto': Decimal('0.00')} for m in months},
                'ingresos': Decimal('0.00'),
                'egresos': Decimal('0.00'),
                'neto': Decimal('0.00'),
                'cuentas': 0,
            }
        currency_bucket = totals_by_currency[moneda_codigo]
        currency_bucket['cuentas'] += 1

        month_float = {}
        for mes_key, values in item['months'].items():
            totals[mes_key]['ingresos'] += values['ingresos']
            totals[mes_key]['egresos'] += values['egresos']
            totals[mes_key]['neto'] += values['neto']
            currency_bucket['months'][mes_key]['ingresos'] += values['ingresos']
            currency_bucket['months'][mes_key]['egresos'] += values['egresos']
            currency_bucket['months'][mes_key]['neto'] += values['neto']
            month_float[mes_key] = {
                'ingresos': _to_float(values['ingresos']),
                'egresos': _to_float(values['egresos']),
                'neto': _to_float(values['neto']),
            }
        currency_bucket['ingresos'] += item['total_ingresos']
        currency_bucket['egresos'] += item['total_egresos']
        currency_bucket['neto'] += item['total_neto']
        total_ingresos += item['total_ingresos']
        total_egresos += item['total_egresos']
        total_neto += item['total_neto']
        accounts.append({
            **{k: item[k] for k in ('tipo_objeto', 'objeto_id', 'codigo', 'nombre', 'cuenta_codigo', 'cuenta_nombre', 'unidad', 'moneda_codigo')},
            'months': month_float,
            'total_ingresos': _to_float(item['total_ingresos']),
            'total_egresos': _to_float(item['total_egresos']),
            'total_neto': _to_float(item['total_neto']),
        })

    totals_float = {
        mes_key: {
            'ingresos': _to_float(values['ingresos']),
            'egresos': _to_float(values['egresos']),
            'neto': _to_float(values['neto']),
        }
        for mes_key, values in totals.items()
    }
    currency_float = {}
    currency_list = []
    for moneda_codigo in sorted(totals_by_currency):
        bucket = totals_by_currency[moneda_codigo]
        months_float = {
            mes_key: {
                'ingresos': _to_float(values['ingresos']),
                'egresos': _to_float(values['egresos']),
                'neto': _to_float(values['neto']),
            }
            for mes_key, values in bucket['months'].items()
        }
        item = {
            'moneda_codigo': moneda_codigo,
            'months': months_float,
            'ingresos': _to_float(bucket['ingresos']),
            'egresos': _to_float(bucket['egresos']),
            'neto': _to_float(bucket['neto']),
            'cuentas': bucket['cuentas'],
        }
        currency_float[moneda_codigo] = item
        currency_list.append(item)

    return {
        'months': months,
        'accounts': accounts,
        'totals_by_month': totals_float,
        'totals_by_currency': currency_float,
        'totals_by_currency_list': currency_list,
        'currency_count': len(currency_list),
        'totals': {
            'ingresos': _to_float(total_ingresos),
            'egresos': _to_float(total_egresos),
            'neto': _to_float(total_neto),
            'cuentas': len(accounts),
        },
    }


# ============================================================
# PDF helpers
# ============================================================

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

    def _draw_footer(self, total_pages):
        page_width, _ = self._pagesize
        user = self.report_context.get('emitted_by') or 'Sistema'
        self.saveState()
        self.setFont('Helvetica', 7.5)
        self.setFillColor(MUTED)
        self.drawString(18 * mm, 10 * mm, f'Generado por: {user}')
        self.drawRightString(page_width - 18 * mm, 10 * mm, f'Página {self._pageNumber} de {total_pages}')
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
        header_top = page_height - 20 * mm

        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 16)
        canvas.drawString(x_left, header_top - 21, title)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 8.5)
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
    styles.add(ParagraphStyle(name='DXTMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8.4, textColor=TEXT, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTBodyCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8.4, textColor=TEXT, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTBodyRight', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8.4, textColor=TEXT, alignment=TA_RIGHT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=NAVY, spaceAfter=5))
    styles.add(ParagraphStyle(name='DXTHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.4, leading=7.2, textColor=colors.white, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTHeaderCenter', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.4, leading=7.2, textColor=colors.white, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTHeaderRight', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.4, leading=7.2, textColor=colors.white, alignment=TA_RIGHT, wordWrap='CJK'))
    return styles


def _pdf_response(story, filename, title, subtitle='', pagesize=A4):
    buffer = io.BytesIO()
    context = {
        'title': title,
        'subtitle': subtitle,
        'logo_path': logo_path(),
        'emitted_by': usuario_actual(),
    }
    doc = BrandedDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=36 * mm,
        bottomMargin=18 * mm,
        report_context=context,
    )
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{filename}"'},
    )


def _meta_table(meta, styles):
    data = []
    for label, value in meta:
        data.append([
            Paragraph(f'<b>{_safe_text(label)}</b>', styles['DXTMeta']),
            Paragraph(_safe_text(value), styles['DXTMeta']),
        ])
    table = Table(data, colWidths=[38 * mm, 130 * mm])
    table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('BACKGROUND', (0, 0), (0, -1), HEAD_FILL),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return table


def _pdf_table(data, col_widths, repeat_header=True):
    table = Table(data, colWidths=col_widths, repeatRows=1 if repeat_header else 0)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('GRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.2),
        ('TOPPADDING', (0, 0), (-1, -1), 3.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.2),
    ])
    for idx in range(1, len(data)):
        if idx % 2 == 0:
            style.add('BACKGROUND', (0, idx), (-1, idx), ROW_ALT)
    table.setStyle(style)
    return table


def _unidad_label(unidades, unidad_id):
    if not unidad_id:
        return 'Todas'
    for unidad in unidades:
        if int(unidad['id']) == int(unidad_id):
            return f"{unidad['codigo']} · {unidad['nombre']}"
    return f'Unidad #{unidad_id}'


# ============================================================
# Rutas
# ============================================================

@caja_bancos_estado_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    today = date.today()
    errors = []

    fecha_corte_arg = request.args.get('fecha_corte')
    fecha_corte = None
    if fecha_corte_arg:
        try:
            fecha_corte = _parse_date(fecha_corte_arg, 'Fecha de corte', today)
        except ValueError as exc:
            fecha_corte = today
            errors.append(str(exc))

    try:
        tipo_saldo, unidad_saldo_id, moneda_saldo, _, _ = _entry_filters('saldo_')
    except ValueError as exc:
        tipo_saldo, unidad_saldo_id, moneda_saldo = 'TODOS', None, ''
        errors.append(str(exc))

    try:
        mensual_params = _monthly_params()
    except ValueError as exc:
        current_year = today.year
        mensual_params = {
            'periodo': 'gestion',
            'gestion': str(current_year),
            'mes_desde': date(current_year, 1, 1),
            'mes_hasta': date(current_year, 12, 1),
            'fecha_desde': date(current_year, 1, 1),
            'fecha_hasta': date(current_year, 12, 31),
            'tipo': 'TODOS',
            'unidad_id': None,
            'moneda': '',
        }
        errors.append(str(exc))

    with DatabaseManager() as db:
        unidades, monedas = _catalogos(db)
        if fecha_corte is None:
            fecha_corte = _ultima_fecha_movimiento(db)
        saldos = _saldos_actuales(db, fecha_corte, tipo_saldo, unidad_saldo_id, moneda_saldo)
        resumen_saldos = _resumen_saldos(saldos)
        mensual = _comparativo_mensual(db, mensual_params)

    return render_template(
        'caja_bancos_estado_index.html',
        unidades=unidades,
        monedas=monedas,
        errors=errors,
        today=today.strftime('%Y-%m-%d'),
        current_year=today.year,
        saldo_filters={
            'fecha_corte': fecha_corte.strftime('%Y-%m-%d'),
            'tipo': tipo_saldo,
            'unidad_id': unidad_saldo_id,
            'moneda': moneda_saldo,
        },
        saldos=saldos,
        resumen_saldos=resumen_saldos,
        mensual_filters={
            'periodo': mensual_params['periodo'],
            'gestion': mensual_params['gestion'],
            'mes_desde': mensual_params['mes_desde'].strftime('%Y-%m'),
            'mes_hasta': mensual_params['mes_hasta'].strftime('%Y-%m'),
            'tipo': mensual_params['tipo'],
            'unidad_id': mensual_params['unidad_id'],
            'moneda': mensual_params['moneda'],
        },
        mensual=mensual,
    )


@caja_bancos_estado_bp.route('/api/detalle')
@login_required
@roles_required(ROLES_LECTURA)
def api_detalle():
    try:
        tipo = _clean(request.args.get('tipo')).upper()
        objeto_id = _parse_optional_int(request.args.get('id'), 'Identificador')
        fecha_corte = _parse_date(request.args.get('fecha_corte'), 'Fecha de corte', date.today())
        unidad_id = _parse_optional_int(request.args.get('unidad_id'), 'Unidad de negocio')
        moneda = _clean(request.args.get('moneda')).upper()
        fecha_desde = _parse_date(request.args.get('fecha_desde'), 'Fecha desde', None) if _clean(request.args.get('fecha_desde')) else None
        if not objeto_id:
            raise ValueError('No se recibió la caja o banco seleccionado.')
        with DatabaseManager() as db:
            objeto = _nombre_objeto(db, tipo, objeto_id)
            detalle = _detalle_movimientos(db, tipo, objeto_id, fecha_corte, unidad_id, moneda, fecha_desde)
        return jsonify({'success': True, 'objeto': objeto, 'detalle': detalle})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


@caja_bancos_estado_bp.route('/saldos/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_saldos():
    fecha_arg = request.args.get('fecha_corte')
    fecha_corte = _parse_date(fecha_arg, 'Fecha de corte', date.today()) if fecha_arg else None
    tipo, unidad_id, moneda, _, _ = _entry_filters('saldo_')
    with DatabaseManager() as db:
        unidades, _ = _catalogos(db)
        if fecha_corte is None:
            fecha_corte = _ultima_fecha_movimiento(db)
        rows = _saldos_actuales(db, fecha_corte, tipo, unidad_id, moneda)
        resumen = _resumen_saldos(rows)

    styles = _pdf_styles()
    story = [
        _meta_table([
            ('Fecha de corte', fecha_corte.strftime('%d/%m/%Y')),
            ('Tipo', {'TODOS': 'Cajas y bancos', 'CAJA': 'Solo cajas', 'BANCO': 'Solo bancos'}.get(tipo, tipo)),
            ('Unidad de negocio', _unidad_label(unidades, unidad_id)),
            ('Moneda', moneda or 'Todas'),
            ('Cuentas listadas', str(resumen['cantidad'])),
        ], styles),
        Spacer(1, 7 * mm),
        Paragraph('Resumen por moneda', styles['DXTSection']),
    ]
    resumen_data = [[
        Paragraph('Moneda', styles['DXTHeaderCenter']),
        Paragraph('Cajas', styles['DXTHeaderRight']),
        Paragraph('Bancos', styles['DXTHeaderRight']),
        Paragraph('Saldo', styles['DXTHeaderRight']),
        Paragraph('Ingresos', styles['DXTHeaderRight']),
        Paragraph('Egresos', styles['DXTHeaderRight']),
    ]]
    for item in resumen['por_moneda']:
        resumen_data.append([
            Paragraph(_safe_text(item['moneda_codigo']), styles['DXTBodyCenter']),
            Paragraph(_amount(item['total_cajas']), styles['DXTBodyRight']),
            Paragraph(_amount(item['total_bancos']), styles['DXTBodyRight']),
            Paragraph(_amount(item['total_general']), styles['DXTBodyRight']),
            Paragraph(_amount(item['ingresos']), styles['DXTBodyRight']),
            Paragraph(_amount(item['egresos']), styles['DXTBodyRight']),
        ])
    if len(resumen_data) == 1:
        resumen_data.append([Paragraph('Sin saldos para los filtros seleccionados.', styles['DXTBody']), '', '', '', '', ''])
    story.append(_pdf_table(resumen_data, [22 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm]))
    story.extend([
        Spacer(1, 7 * mm),
        Paragraph('Saldos actuales por caja y banco', styles['DXTSection']),
    ])
    data = [[
        Paragraph('Tipo', styles['DXTHeaderCenter']),
        Paragraph('Caja / Banco', styles['DXTHeader']),
        Paragraph('Cuenta contable', styles['DXTHeader']),
        Paragraph('Unidad', styles['DXTHeader']),
        Paragraph('Ingresos', styles['DXTHeaderRight']),
        Paragraph('Egresos', styles['DXTHeaderRight']),
        Paragraph('Saldo', styles['DXTHeaderRight']),
    ]]
    for row in rows:
        data.append([
            Paragraph(_safe_text(row['tipo_objeto']), styles['DXTBodyCenter']),
            Paragraph(_safe_text(f"{row['codigo']} · {row['nombre']} · {row['moneda_codigo']}"), styles['DXTBody']),
            Paragraph(_safe_text(f"{row['cuenta_codigo']} · {row['cuenta_nombre']}"), styles['DXTBody']),
            Paragraph(_safe_text(row['unidad']), styles['DXTBody']),
            Paragraph(_amount(row['ingresos']), styles['DXTBodyRight']),
            Paragraph(_amount(row['egresos']), styles['DXTBodyRight']),
            Paragraph(_amount(row['saldo']), styles['DXTBodyRight']),
        ])
    if len(data) == 1:
        data.append([Paragraph('No existen saldos para los filtros seleccionados.', styles['DXTBody']), '', '', '', '', '', ''])
    story.append(_pdf_table(data, [17 * mm, 48 * mm, 44 * mm, 38 * mm, 25 * mm, 25 * mm, 25 * mm]))
    return _pdf_response(story, 'estado_caja_bancos_saldos.pdf', 'Estado de Caja y Bancos', 'Saldos actuales por fecha de corte', landscape(A4))


@caja_bancos_estado_bp.route('/detalle/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_detalle():
    tipo = _clean(request.args.get('tipo')).upper()
    objeto_id = _parse_optional_int(request.args.get('id'), 'Identificador')
    fecha_corte = _parse_date(request.args.get('fecha_corte'), 'Fecha de corte', date.today())
    unidad_id = _parse_optional_int(request.args.get('unidad_id'), 'Unidad de negocio')
    moneda = _clean(request.args.get('moneda')).upper()
    fecha_desde = _parse_date(request.args.get('fecha_desde'), 'Fecha desde', None) if _clean(request.args.get('fecha_desde')) else None
    if not objeto_id:
        raise ValueError('No se recibió la caja o banco seleccionado.')
    with DatabaseManager() as db:
        unidades, _ = _catalogos(db)
        objeto = _nombre_objeto(db, tipo, objeto_id)
        detalle = _detalle_movimientos(db, tipo, objeto_id, fecha_corte, unidad_id, moneda, fecha_desde)

    styles = _pdf_styles()
    periodo = f"Hasta {fecha_corte.strftime('%d/%m/%Y')}"
    if fecha_desde:
        periodo = f"Del {fecha_desde.strftime('%d/%m/%Y')} al {fecha_corte.strftime('%d/%m/%Y')}"
    story = [
        _meta_table([
            ('Tipo', tipo),
            ('Caja / Banco', f"{objeto['codigo']} · {objeto['nombre']}"),
            ('Cuenta contable', f"{objeto['cuenta_codigo']} · {objeto['cuenta_nombre']}"),
            ('Período', periodo),
            ('Unidad de negocio', _unidad_label(unidades, unidad_id)),
            ('Moneda', moneda or 'Todas'),
            ('Saldo anterior', _amount(detalle['saldo_anterior'])),
            ('Saldo final', _amount(detalle['saldo_final'])),
        ], styles),
        Spacer(1, 7 * mm),
        Paragraph('Extracto de movimientos', styles['DXTSection']),
    ]
    data = [[
        Paragraph('Fecha', styles['DXTHeaderCenter']),
        Paragraph('Origen', styles['DXTHeaderCenter']),
        Paragraph('Documento', styles['DXTHeader']),
        Paragraph('Glosa', styles['DXTHeader']),
        Paragraph('Ingreso', styles['DXTHeaderRight']),
        Paragraph('Egreso', styles['DXTHeaderRight']),
        Paragraph('Saldo', styles['DXTHeaderRight']),
    ]]
    for row in detalle['movimientos']:
        data.append([
            Paragraph(_safe_text(row['fecha']), styles['DXTBodyCenter']),
            Paragraph(_safe_text(row['origen']), styles['DXTBodyCenter']),
            Paragraph(_safe_text(row['documento']), styles['DXTBody']),
            Paragraph(_safe_text(row['glosa']), styles['DXTBody']),
            Paragraph(_amount(row['ingreso']), styles['DXTBodyRight']),
            Paragraph(_amount(row['egreso']), styles['DXTBodyRight']),
            Paragraph(_amount(row['saldo']), styles['DXTBodyRight']),
        ])
    if len(data) == 1:
        data.append([Paragraph('No existen movimientos para los filtros seleccionados.', styles['DXTBody']), '', '', '', '', '', ''])
    story.append(_pdf_table(data, [20 * mm, 22 * mm, 38 * mm, 82 * mm, 26 * mm, 26 * mm, 26 * mm]))
    return _pdf_response(story, 'estado_caja_bancos_detalle.pdf', 'Extracto de Caja / Banco', 'Detalle de movimientos confirmados', landscape(A4))


@caja_bancos_estado_bp.route('/mensual/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_mensual():
    params = _monthly_params()
    with DatabaseManager() as db:
        unidades, _ = _catalogos(db)
        mensual = _comparativo_mensual(db, params)

    styles = _pdf_styles()
    if params['periodo'] == 'gestion':
        periodo_label = f"Gestión {params['gestion']}"
    else:
        periodo_label = f"{params['mes_desde'].strftime('%Y-%m')} a {params['mes_hasta'].strftime('%Y-%m')}"

    story = [
        _meta_table([
            ('Período', periodo_label),
            ('Tipo', {'TODOS': 'Cajas y bancos', 'CAJA': 'Solo cajas', 'BANCO': 'Solo bancos'}.get(params['tipo'], params['tipo'])),
            ('Unidad de negocio', _unidad_label(unidades, params['unidad_id'])),
            ('Moneda', params['moneda'] or 'Todas'),
            ('Cuentas con movimiento', str(mensual['totals']['cuentas'])),
        ], styles),
        Spacer(1, 7 * mm),
        Paragraph('Resumen por moneda', styles['DXTSection']),
    ]
    resumen_data = [[
        Paragraph('Moneda', styles['DXTHeaderCenter']),
        Paragraph('Cuentas', styles['DXTHeaderRight']),
        Paragraph('Ingresos', styles['DXTHeaderRight']),
        Paragraph('Egresos', styles['DXTHeaderRight']),
        Paragraph('Neto', styles['DXTHeaderRight']),
    ]]
    for item in mensual['totals_by_currency_list']:
        resumen_data.append([
            Paragraph(_safe_text(item['moneda_codigo']), styles['DXTBodyCenter']),
            Paragraph(str(item['cuentas']), styles['DXTBodyRight']),
            Paragraph(_amount(item['ingresos']), styles['DXTBodyRight']),
            Paragraph(_amount(item['egresos']), styles['DXTBodyRight']),
            Paragraph(_amount(item['neto']), styles['DXTBodyRight']),
        ])
    if len(resumen_data) == 1:
        resumen_data.append([Paragraph('Sin movimientos para los filtros seleccionados.', styles['DXTBody']), '', '', '', ''])
    story.append(_pdf_table(resumen_data, [24 * mm, 24 * mm, 34 * mm, 34 * mm, 34 * mm]))
    story.extend([
        Spacer(1, 7 * mm),
        Paragraph('Comparativo mensual por caja y banco', styles['DXTSection']),
    ])
    header = [Paragraph('Caja / Banco', styles['DXTHeader']), Paragraph('Movimiento', styles['DXTHeaderCenter'])]
    for mes in mensual['months']:
        header.append(Paragraph(_safe_text(mes['short']), styles['DXTHeaderRight']))
    header.append(Paragraph('Total', styles['DXTHeaderRight']))
    data = [header]
    group_rows = []
    total_rows = []

    for account in mensual['accounts']:
        group_rows.append(len(data))
        label = (
            f"<b>{_safe_text(account['tipo_objeto'])} · {_safe_text(account['codigo'])} · {_safe_text(account['nombre'])}</b>"
            f"<br/><font size='6'>{_safe_text(account['cuenta_codigo'])} · {_safe_text(account['cuenta_nombre'])}"
            f" · {_safe_text(account['unidad'])} · {_safe_text(account['moneda_codigo'])}</font>"
        )
        data.append([Paragraph(label, styles['DXTBody']), *([''] * (len(mensual['months']) + 2))])
        for movement, total_key in [('Ingresos', 'total_ingresos'), ('Egresos', 'total_egresos'), ('Neto', 'total_neto')]:
            row = ['', Paragraph(movement, styles['DXTBodyCenter'])]
            key_map = {'Ingresos': 'ingresos', 'Egresos': 'egresos', 'Neto': 'neto'}
            for mes in mensual['months']:
                row.append(Paragraph(_amount(account['months'][mes['key']][key_map[movement]]), styles['DXTBodyRight']))
            row.append(Paragraph(_amount(account[total_key]), styles['DXTBodyRight']))
            data.append(row)

    if not mensual['accounts']:
        data.append([Paragraph('No existen movimientos para los filtros seleccionados.', styles['DXTBody']), '', *([''] * len(mensual['months'])), ''])
    else:
        key_map = {'Ingresos': 'ingresos', 'Egresos': 'egresos', 'Neto': 'neto'}
        for currency in mensual['totals_by_currency_list']:
            group_rows.append(len(data))
            data.append([Paragraph(f"<b>Total {currency['moneda_codigo']}</b>", styles['DXTBody']), *([''] * (len(mensual['months']) + 2))])
            for movement, total_key in [('Ingresos', 'ingresos'), ('Egresos', 'egresos'), ('Neto', 'neto')]:
                total_rows.append(len(data))
                row = ['', Paragraph(f'<b>{movement}</b>', styles['DXTBodyCenter'])]
                for mes in mensual['months']:
                    row.append(Paragraph(f"<b>{_amount(currency['months'][mes['key']][key_map[movement]])}</b>", styles['DXTBodyRight']))
                row.append(Paragraph(f"<b>{_amount(currency[total_key])}</b>", styles['DXTBodyRight']))
                data.append(row)

    usable_width = landscape(A4)[0] - (32 * mm)
    fixed_width = 50 * mm + 18 * mm + 18 * mm
    month_width = max(12 * mm, (usable_width - fixed_width) / max(1, len(mensual['months'])))
    col_widths = [50 * mm, 18 * mm] + [month_width for _ in mensual['months']] + [18 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2.2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2.2),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])
    for idx in range(1, len(data)):
        if idx % 2 == 0:
            style.add('BACKGROUND', (0, idx), (-1, idx), ROW_ALT)
    for idx in group_rows:
        style.add('SPAN', (0, idx), (-1, idx))
        style.add('BACKGROUND', (0, idx), (-1, idx), HEAD_FILL)
        style.add('LINEABOVE', (0, idx), (-1, idx), 1.0, NAVY)
    for idx in total_rows:
        style.add('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#eef3f8'))
    table.setStyle(style)
    story.append(table)
    return _pdf_response(story, 'estado_caja_bancos_comparativo_mensual.pdf', 'Comparativo Mensual de Caja y Bancos', 'Ingresos, egresos y neto por mes', landscape(A4))


@caja_bancos_estado_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('caja_bancos_estado_help.html')
