# ============================================================
# DXT CONTA - Reporte Especial
# Reporte: Cartera documental por auxiliar
# ============================================================

from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Response, jsonify, redirect, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from database.db_manager import DatabaseManager
from modules.facturas_auxiliar import facturas_auxiliar_bp
from modules.reportes_rapidos.core.utils import logo_path, usuario_actual
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
CENTAVO = Decimal('0.01')
MONEDA_BASE = 'BOB'
MAX_ROWS = 5000

FECHA_MODOS = {
    'TODAS': 'Todas',
    'RANGO_DOCUMENTO': 'Rango documento',
}

ORIGENES = {
    '': 'Todos',
    'COMPROMISO': 'Compromisos',
    'DOCUMENTO': 'Documentos',
    'FACTURA': 'Facturas electrónicas',
}

ESTADOS = {
    '': 'Todos',
    'VENCIDA': 'Vencida',
    'VENCE_HOY': 'Vence hoy',
    'POR_VENCER': 'Por vencer',
    'SIN_VENCIMIENTO': 'Sin vencimiento',
    'PARCIAL': 'Parcial',
    'SIN_COBRO': 'Sin cobro',
}

ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
TOTAL_FILL = colors.HexColor('#e8f1ff')


# ============================================================
# Helpers generales
# ============================================================

def _clean(value) -> str:
    return str(value or '').strip()


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal('0.00')
    try:
        return Decimal(str(value)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _amount(value) -> str:
    return f'{_to_decimal(value):,.2f}'


def _date_label(value) -> str:
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    text = str(value)
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return text


def _parse_date(value, field_name, default=None):
    raw = _clean(value)
    if not raw:
        return default
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no es válida.') from exc


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


def _json_ready(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _filename_safe(value):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or '')).strip('_')[:70]
    return cleaned or 'cartera_documental'


def _money_label(value, moneda=None):
    # Regla UI: cuando existe columna/campo Moneda, los importes no llevan prefijo ni sufijo.
    return _amount(value)


def _moneda_label(codigo, simbolo=None):
    return _clean(simbolo) or _clean(codigo).upper() or MONEDA_BASE


def _safe_text(value) -> str:
    return str(value if value is not None else '')


def _build_filters(args):
    today = date.today()
    first_day = today.replace(day=1)

    fecha_corte = _parse_date(args.get('fecha_corte'), 'La fecha de corte', default=today)
    fecha_modo = _clean(args.get('fecha_modo')).upper() or 'TODAS'
    if fecha_modo not in FECHA_MODOS:
        raise ValueError('El alcance de fecha seleccionado no es válido.')

    fecha_desde = _parse_date(args.get('fecha_desde'), 'La fecha desde', default=first_day)
    fecha_hasta = _parse_date(args.get('fecha_hasta'), 'La fecha hasta', default=today)
    if fecha_modo == 'RANGO_DOCUMENTO' and fecha_desde > fecha_hasta:
        raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')

    origen = _clean(args.get('origen')).upper()
    if origen not in ORIGENES:
        raise ValueError('El origen seleccionado no es válido.')

    estado = _clean(args.get('estado')).upper()
    if estado not in ESTADOS:
        raise ValueError('El estado seleccionado no es válido.')

    return {
        'fecha_corte': fecha_corte,
        'fecha_modo': fecha_modo,
        'fecha_modo_label': FECHA_MODOS[fecha_modo],
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'origen': origen,
        'origen_label': ORIGENES[origen],
        'estado': estado,
        'estado_label': ESTADOS[estado],
        'unidad_negocio_id': _parse_optional_int(args.get('unidad_negocio_id'), 'La unidad de negocio'),
        'auxiliar_id': _parse_optional_int(args.get('auxiliar_id'), 'El auxiliar'),
        'moneda': _clean(args.get('moneda')).upper(),
        'q': _clean(args.get('q')),
    }


def _periodo_label(filtros):
    corte = _date_label(filtros['fecha_corte'])
    if filtros['fecha_modo'] == 'TODAS':
        return f'Corte al {corte}'
    desde = _date_label(filtros['fecha_desde'])
    hasta = _date_label(filtros['fecha_hasta'])
    return f'Documento: {desde} al {hasta} · Corte {corte}'


def _estado_item(item):
    vencimiento = item.get('fecha_vencimiento')
    fecha_corte = item.get('fecha_corte')
    aplicado = _to_decimal(item.get('aplicado'))
    saldo = _to_decimal(item.get('saldo'))

    if aplicado > 0 and saldo > 0:
        cobro_codigo = 'PARCIAL'
        cobro_label = 'Parcial'
    else:
        cobro_codigo = 'SIN_COBRO'
        cobro_label = 'Sin cobro'

    if not isinstance(vencimiento, date):
        return {
            'codigo': 'SIN_VENCIMIENTO',
            'label': 'Sin vencimiento',
            'badge': 'secondary',
            'orden': 3,
            'cobro_codigo': cobro_codigo,
            'cobro_label': cobro_label,
            'dias': None,
            'dias_label': 'Sin vencimiento',
        }

    dias = (fecha_corte - vencimiento).days
    if dias > 0:
        codigo = 'VENCIDA'
        label = 'Vencida'
        badge = 'danger'
        orden = 0
        dias_label = f'{dias} d.'
    elif dias == 0:
        codigo = 'VENCE_HOY'
        label = 'Vence hoy'
        badge = 'warning'
        orden = 1
        dias_label = 'Hoy'
    else:
        codigo = 'POR_VENCER'
        label = 'Por vencer'
        badge = 'success'
        orden = 2
        dias_label = f'Faltan {abs(dias)} d.'

    return {
        'codigo': codigo,
        'label': label,
        'badge': badge,
        'orden': orden,
        'cobro_codigo': cobro_codigo,
        'cobro_label': cobro_label,
        'dias': dias,
        'dias_label': dias_label,
    }


def _estado_match(item, estado):
    if not estado:
        return True
    meta = _estado_item(item)
    if estado in {'PARCIAL', 'SIN_COBRO'}:
        return meta['cobro_codigo'] == estado
    return meta['codigo'] == estado


# ============================================================
# Catálogos
# ============================================================

def _fetch_currency_symbols(cursor):
    cursor.execute(
        """
        SELECT UPPER(codigo) AS codigo, COALESCE(NULLIF(simbolo, ''), codigo) AS simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        """
    )
    data = {}
    for row in cursor.fetchall():
        item = dict(row)
        codigo = _clean(item.get('codigo')).upper()
        if codigo:
            data[codigo] = _clean(item.get('simbolo')) or codigo
    data.setdefault(MONEDA_BASE, MONEDA_BASE)
    return data


def _fetch_catalogos():
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
            FROM contabilidad.unidad_negocio
            WHERE activo = TRUE
            ORDER BY nombre ASC, codigo ASC
            """
        )
        unidades = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            WITH base AS (
                SELECT c.auxiliar_id AS auxiliar_id
                FROM contabilidad.compromiso c
                WHERE c.tipo = 'COBRAR' AND c.auxiliar_id IS NOT NULL
                UNION
                SELECT d.cliente_auxiliar_id AS auxiliar_id
                FROM contabilidad.documento_por_cobrar d
                WHERE d.cliente_auxiliar_id IS NOT NULL
                UNION
                SELECT fe.cliente_auxiliar_id AS auxiliar_id
                FROM contabilidad.factura_electronica fe
                WHERE fe.cliente_auxiliar_id IS NOT NULL
            )
            SELECT DISTINCT
                a.id,
                COALESCE(a.nombre, '') AS nombre,
                COALESCE(a.nit_ci, '') AS nit_ci
            FROM base b
            JOIN contabilidad.auxiliar a ON a.id = b.auxiliar_id
            ORDER BY COALESCE(a.nombre, '') ASC, COALESCE(a.nit_ci, '') ASC
            """
        )
        auxiliares = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT UPPER(codigo) AS codigo,
                   COALESCE(NULLIF(simbolo, ''), codigo) AS simbolo,
                   COALESCE(nombre, '') AS nombre
            FROM contabilidad.moneda
            WHERE activo = TRUE
            ORDER BY codigo ASC
            """
        )
        monedas = [dict(row) for row in cursor.fetchall()]

    return unidades, auxiliares, monedas


# ============================================================
# Fuente unificada
# ============================================================

def _date_filter_sql(alias, filtros, params):
    clauses = []
    if filtros['fecha_modo'] == 'RANGO_DOCUMENTO':
        clauses.append(f'{alias} >= %s')
        clauses.append(f'{alias} <= %s')
        params.extend([filtros['fecha_desde'], filtros['fecha_hasta']])
    return clauses


def _fetch_compromisos(cursor, filtros):
    if filtros['origen'] not in ('', 'COMPROMISO'):
        return []
    if filtros.get('moneda') and filtros['moneda'] != MONEDA_BASE:
        return []

    params = [filtros['fecha_corte'], MONEDA_BASE]
    extra = []

    if filtros.get('unidad_negocio_id'):
        extra.append('c.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    if filtros.get('auxiliar_id'):
        extra.append('c.auxiliar_id = %s')
        params.append(filtros['auxiliar_id'])
    extra.extend(_date_filter_sql('d.fecha_vencimiento', filtros, params))
    if filtros.get('q'):
        like = f"%{filtros['q']}%"
        extra.append(
            """
            (
                COALESCE(c.codigo, '') ILIKE %s OR COALESCE(c.nombre, '') ILIKE %s OR
                COALESCE(c.descripcion, '') ILIKE %s OR COALESCE(aux.nombre, '') ILIKE %s OR
                COALESCE(aux.nit_ci, '') ILIKE %s OR COALESCE(c.cuenta_contable, '') ILIKE %s
            )
            """
        )
        params.extend([like] * 6)

    where_extra = (' AND ' + ' AND '.join(extra)) if extra else ''
    cursor.execute(
        f"""
        WITH apps AS (
            SELECT
                cd.compromiso_detalle_id,
                COALESCE(SUM(cd.subtotal), 0) AS aplicado
            FROM contabilidad.cobro_detalle cd
            JOIN contabilidad.cobro co ON co.id = cd.cobro_id
            WHERE cd.tipo_linea = 'COMPROMISO'
              AND co.estado = 'CONFIRMADO'
              AND co.fecha <= %s
            GROUP BY cd.compromiso_detalle_id
        )
        SELECT
            'COMPROMISO'::text AS fuente_codigo,
            d.id::text AS fuente_id,
            d.fecha_vencimiento::date AS fecha_documento,
            d.fecha_vencimiento::date AS fecha_vencimiento,
            c.auxiliar_id AS auxiliar_id,
            CASE WHEN c.auxiliar_id IS NOT NULL THEN 'A:' || c.auxiliar_id::text ELSE 'N:' || md5(COALESCE(aux.nombre, c.nombre, '') || '|') END AS auxiliar_key,
            COALESCE(aux.nombre, c.nombre, 'Sin auxiliar') AS auxiliar_nombre,
            COALESCE(aux.nit_ci, '') AS auxiliar_doc,
            c.unidad_negocio_id,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '') AS unidad_label,
            %s::text AS moneda_codigo,
            COALESCE(d.monto_programado, 0)::numeric(18,2) AS total,
            COALESCE(apps.aplicado, 0)::numeric(18,2) AS aplicado,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(apps.aplicado, 0), 0)::numeric(18,2) AS saldo,
            COALESCE(c.codigo, 'Compromiso #' || c.id::text) AS referencia,
            COALESCE(NULLIF(c.descripcion, ''), c.nombre, 'Compromiso por cobrar') AS detalle,
            'Compromiso'::text AS origen_label,
            c.cuenta_contable AS cuenta_codigo,
            COALESCE(cta.nombre, '') AS cuenta_nombre,
            d.estado::text AS estado_original
        FROM contabilidad.compromiso_detalle d
        JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        LEFT JOIN apps ON apps.compromiso_detalle_id = d.id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = c.cuenta_contable
        WHERE c.activo = TRUE
          AND c.tipo = 'COBRAR'
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(apps.aplicado, 0), 0) > 0
          {where_extra}
        ORDER BY d.fecha_vencimiento ASC, auxiliar_nombre ASC, c.codigo ASC
        LIMIT {MAX_ROWS}
        """,
        tuple(params),
    )
    return [dict(row) for row in cursor.fetchall()]


def _fetch_documentos(cursor, filtros):
    if filtros['origen'] not in ('', 'DOCUMENTO'):
        return []

    params = [filtros['fecha_corte'], MONEDA_BASE, filtros['fecha_corte']]
    extra = []

    if filtros.get('unidad_negocio_id'):
        extra.append('d.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    if filtros.get('auxiliar_id'):
        extra.append('d.cliente_auxiliar_id = %s')
        params.append(filtros['auxiliar_id'])
    if filtros.get('moneda'):
        extra.append('UPPER(COALESCE(d.moneda_codigo, %s)) = %s')
        params.extend([MONEDA_BASE, filtros['moneda']])
    extra.extend(_date_filter_sql('d.fecha_documento', filtros, params))
    if filtros.get('q'):
        like = f"%{filtros['q']}%"
        extra.append(
            """
            (
                COALESCE(d.numero_documento, '') ILIKE %s OR COALESCE(d.referencia_externa, '') ILIKE %s OR
                COALESCE(d.descripcion, '') ILIKE %s OR COALESCE(d.cliente_nombre, '') ILIKE %s OR
                COALESCE(d.cliente_nit, '') ILIKE %s OR COALESCE(aux.nombre, '') ILIKE %s OR
                COALESCE(aux.nit_ci, '') ILIKE %s OR COALESCE(d.cuenta_cartera_codigo, '') ILIKE %s
            )
            """
        )
        params.extend([like] * 8)

    where_extra = (' AND ' + ' AND '.join(extra)) if extra else ''
    cursor.execute(
        f"""
        WITH apps AS (
            SELECT
                da.documento_por_cobrar_id,
                COALESCE(SUM(da.monto_aplicado), 0) AS aplicado
            FROM contabilidad.documento_por_cobrar_aplicacion da
            JOIN contabilidad.cobro co ON co.id = da.cobro_id
            WHERE co.estado = 'CONFIRMADO'
              AND co.fecha <= %s
            GROUP BY da.documento_por_cobrar_id
        )
        SELECT
            'DOCUMENTO'::text AS fuente_codigo,
            d.id::text AS fuente_id,
            d.fecha_documento::date AS fecha_documento,
            d.fecha_vencimiento::date AS fecha_vencimiento,
            d.cliente_auxiliar_id AS auxiliar_id,
            CASE WHEN d.cliente_auxiliar_id IS NOT NULL THEN 'A:' || d.cliente_auxiliar_id::text ELSE 'N:' || md5(COALESCE(d.cliente_nit, '') || '|' || COALESCE(d.cliente_nombre, '')) END AS auxiliar_key,
            COALESCE(NULLIF(d.cliente_nombre, ''), aux.nombre, 'Sin auxiliar') AS auxiliar_nombre,
            COALESCE(NULLIF(d.cliente_nit, ''), aux.nit_ci, '') AS auxiliar_doc,
            d.unidad_negocio_id,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '') AS unidad_label,
            COALESCE(d.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(d.importe_total, 0)::numeric(18,2) AS total,
            COALESCE(apps.aplicado, 0)::numeric(18,2) AS aplicado,
            GREATEST(COALESCE(d.importe_total, 0) - COALESCE(apps.aplicado, 0), 0)::numeric(18,2) AS saldo,
            TRIM(CONCAT(COALESCE(d.tipo_documento, 'DOCUMENTO'), ' ', COALESCE(d.numero_documento, ''))) AS referencia,
            COALESCE(NULLIF(d.descripcion, ''), d.referencia_externa, d.numero_documento, 'Documento por cobrar') AS detalle,
            CASE
                WHEN d.origen_documento = 'HISTORICO' THEN 'Documento histórico'
                WHEN d.origen_documento = 'VIGENTE_MANUAL' THEN 'Documento vigente'
                ELSE 'Documento por cobrar'
            END AS origen_label,
            d.cuenta_cartera_codigo AS cuenta_codigo,
            COALESCE(cta.nombre, '') AS cuenta_nombre,
            d.estado::text AS estado_original
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN apps ON apps.documento_por_cobrar_id = d.id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = d.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = d.cuenta_cartera_codigo
        WHERE d.activo = TRUE
          AND d.estado IN ('PENDIENTE', 'PARCIAL')
          AND COALESCE(d.factura_electronica_id, 0) = 0
          AND COALESCE(d.origen_documento, '') <> 'FACTURA_ELECTRONICA'
          AND d.fecha_documento <= %s
          AND GREATEST(COALESCE(d.importe_total, 0) - COALESCE(apps.aplicado, 0), 0) > 0
          {where_extra}
        ORDER BY COALESCE(d.fecha_vencimiento, d.fecha_documento) ASC, auxiliar_nombre ASC, d.numero_documento ASC
        LIMIT {MAX_ROWS}
        """,
        tuple(params),
    )
    return [dict(row) for row in cursor.fetchall()]


def _fetch_facturas(cursor, filtros):
    if filtros['origen'] not in ('', 'FACTURA'):
        return []

    params = [filtros['fecha_corte'], filtros['fecha_corte'], filtros['fecha_corte'], MONEDA_BASE, filtros['fecha_corte']]
    extra = []

    if filtros.get('unidad_negocio_id'):
        extra.append('fe.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    if filtros.get('auxiliar_id'):
        extra.append('fe.cliente_auxiliar_id = %s')
        params.append(filtros['auxiliar_id'])
    if filtros.get('moneda'):
        extra.append('UPPER(COALESCE(fe.moneda_codigo, %s)) = %s')
        params.extend([MONEDA_BASE, filtros['moneda']])
    extra.extend(_date_filter_sql('fe.fecha_emision', filtros, params))
    if filtros.get('q'):
        like = f"%{filtros['q']}%"
        extra.append(
            """
            (
                COALESCE(fe.numero_factura, '') ILIKE %s OR COALESCE(fe.nombre_cliente, '') ILIKE %s OR
                COALESCE(fe.nit_cliente, '') ILIKE %s OR COALESCE(aux.nombre, '') ILIKE %s OR
                COALESCE(aux.nit_ci, '') ILIKE %s OR COALESCE(fe.cuenta_cobrar_codigo, '') ILIKE %s
            )
            """
        )
        params.extend([like] * 6)

    where_extra = (' AND ' + ' AND '.join(extra)) if extra else ''
    cursor.execute(
        f"""
        WITH apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro co ON co.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR (co.estado = 'CONFIRMADO' AND co.fecha <= %s))
              AND (fa.venta_id IS NULL OR (v.estado <> 'ANULADO' AND v.fecha <= %s))
            GROUP BY fa.factura_electronica_id
        ), reg AS (
            SELECT
                factura_electronica_id,
                COALESCE(SUM(CASE WHEN activo = TRUE AND creado_en::date <= %s THEN monto ELSE 0 END), 0) AS regularizado
            FROM contabilidad.factura_regularizacion
            GROUP BY factura_electronica_id
        )
        SELECT
            'FACTURA'::text AS fuente_codigo,
            fe.id::text AS fuente_id,
            fe.fecha_emision::date AS fecha_documento,
            NULL::date AS fecha_vencimiento,
            fe.cliente_auxiliar_id AS auxiliar_id,
            CASE WHEN fe.cliente_auxiliar_id IS NOT NULL THEN 'A:' || fe.cliente_auxiliar_id::text ELSE 'N:' || md5(COALESCE(fe.nit_cliente, '') || '|' || COALESCE(fe.nombre_cliente, '')) END AS auxiliar_key,
            COALESCE(NULLIF(fe.nombre_cliente, ''), aux.nombre, 'Sin auxiliar') AS auxiliar_nombre,
            COALESCE(NULLIF(fe.nit_cliente, ''), aux.nit_ci, '') AS auxiliar_doc,
            fe.unidad_negocio_id,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '') AS unidad_label,
            COALESCE(fe.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(fe.importe_total, 0)::numeric(18,2) AS total,
            (COALESCE(apps.aplicado, 0) + COALESCE(reg.regularizado, 0))::numeric(18,2) AS aplicado,
            GREATEST(COALESCE(fe.importe_total, 0) - COALESCE(apps.aplicado, 0) - COALESCE(reg.regularizado, 0), 0)::numeric(18,2) AS saldo,
            ('Factura ' || COALESCE(fe.numero_factura, '')) AS referencia,
            ('Emitida ' || TO_CHAR(fe.fecha_emision, 'DD/MM/YYYY')) AS detalle,
            'Factura electrónica'::text AS origen_label,
            fe.cuenta_cobrar_codigo AS cuenta_codigo,
            COALESCE(cta.nombre, '') AS cuenta_nombre,
            fe.estado::text AS estado_original
        FROM contabilidad.factura_electronica fe
        LEFT JOIN apps ON apps.factura_electronica_id = fe.id
        LEFT JOIN reg ON reg.factura_electronica_id = fe.id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = fe.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = fe.cuenta_cobrar_codigo
        WHERE fe.estado <> 'ANULADA'
          AND COALESCE(fe.cuenta_cobrar_codigo, '') <> ''
          AND fe.fecha_emision <= %s
          AND GREATEST(COALESCE(fe.importe_total, 0) - COALESCE(apps.aplicado, 0) - COALESCE(reg.regularizado, 0), 0) > 0
          {where_extra}
        ORDER BY fe.fecha_emision ASC, fe.numero_factura ASC
        LIMIT {MAX_ROWS}
        """,
        tuple(params),
    )
    return [dict(row) for row in cursor.fetchall()]


def _fetch_items(filtros):
    with DatabaseManager.get_cursor() as cursor:
        raw = []
        raw.extend(_fetch_compromisos(cursor, filtros))
        raw.extend(_fetch_documentos(cursor, filtros))
        raw.extend(_fetch_facturas(cursor, filtros))
        currency_symbols = _fetch_currency_symbols(cursor)

    items = []
    for idx, row in enumerate(raw, start=1):
        item = _format_item(row, idx, filtros, currency_symbols)
        if _estado_match(item, filtros['estado']):
            items.append(item)

    items.sort(key=lambda r: (
        r.get('estado_orden', 9),
        -int(r.get('dias_vencido') or 0),
        r.get('auxiliar_nombre') or '',
        r.get('moneda_codigo') or '',
        r.get('fecha_vencimiento') or '9999-12-31',
        r.get('fecha_documento') or '9999-12-31',
    ))
    for idx, item in enumerate(items, start=1):
        item['nro'] = idx
    return items


def _format_item(row, idx, filtros, currency_symbols):
    total = _to_decimal(row.get('total'))
    aplicado = _to_decimal(row.get('aplicado'))
    saldo = _to_decimal(row.get('saldo'))
    moneda_codigo = _clean(row.get('moneda_codigo')).upper() or MONEDA_BASE
    moneda_simbolo = _moneda_label(moneda_codigo, currency_symbols.get(moneda_codigo))
    fecha_documento = row.get('fecha_documento')
    fecha_vencimiento = row.get('fecha_vencimiento')
    base = {
        'nro': idx,
        'fuente_codigo': row.get('fuente_codigo') or '',
        'fuente_id': row.get('fuente_id') or '',
        'auxiliar_key': row.get('auxiliar_key') or '',
        'auxiliar_id': row.get('auxiliar_id'),
        'auxiliar_nombre': row.get('auxiliar_nombre') or 'Sin auxiliar',
        'auxiliar_doc': row.get('auxiliar_doc') or '',
        'unidad_label': row.get('unidad_label') or '',
        'moneda_codigo': moneda_codigo,
        'moneda_simbolo': moneda_simbolo,
        'moneda_label': moneda_simbolo,
        'fecha_corte': filtros['fecha_corte'],
        'fecha_documento': fecha_documento,
        'fecha_documento_label': _date_label(fecha_documento),
        'fecha_vencimiento': fecha_vencimiento,
        'fecha_vencimiento_iso': fecha_vencimiento.isoformat() if isinstance(fecha_vencimiento, date) else '',
        'fecha_vencimiento_label': _date_label(fecha_vencimiento) if isinstance(fecha_vencimiento, date) else 'Sin vencimiento',
        'referencia': row.get('referencia') or '',
        'detalle': row.get('detalle') or '',
        'origen_label': row.get('origen_label') or '',
        'cuenta_codigo': row.get('cuenta_codigo') or '',
        'cuenta_nombre': row.get('cuenta_nombre') or '',
        'estado_original': row.get('estado_original') or '',
        'total': total,
        'aplicado': aplicado,
        'saldo': saldo,
        'total_label': _money_label(total, moneda_codigo),
        'aplicado_label': _money_label(aplicado, moneda_codigo),
        'saldo_label': _money_label(saldo, moneda_codigo),
    }
    meta = _estado_item(base)
    base.update({
        'estado_codigo': meta['codigo'],
        'estado_label': meta['label'],
        'estado_badge': meta['badge'],
        'estado_orden': meta['orden'],
        'cobro_codigo': meta['cobro_codigo'],
        'cobro_label': meta['cobro_label'],
        'dias_vencido': meta['dias'],
        'dias_label': meta['dias_label'],
    })
    return base


def _build_summary(items):
    totals = defaultdict(lambda: {'total': Decimal('0.00'), 'aplicado': Decimal('0.00'), 'saldo': Decimal('0.00')})
    auxiliares = set()
    vencidos = parciales = sin_vencimiento = 0
    for item in items:
        moneda = item['moneda_codigo']
        totals[moneda]['total'] += item['total']
        totals[moneda]['aplicado'] += item['aplicado']
        totals[moneda]['saldo'] += item['saldo']
        auxiliares.add((item['auxiliar_key'], item['moneda_codigo']))
        if item['estado_codigo'] == 'VENCIDA':
            vencidos += 1
        if item['cobro_codigo'] == 'PARCIAL':
            parciales += 1
        if item['estado_codigo'] == 'SIN_VENCIMIENTO':
            sin_vencimiento += 1

    monedas = []
    for moneda, data in sorted(totals.items()):
        label = next((item['moneda_label'] for item in items if item['moneda_codigo'] == moneda), moneda)
        monedas.append({
            'moneda_codigo': moneda,
            'moneda_label': label,
            'total_label': _money_label(data['total'], moneda),
            'aplicado_label': _money_label(data['aplicado'], moneda),
            'saldo_label': _money_label(data['saldo'], moneda),
        })

    saldo_label = '0.00'
    if len(monedas) == 1:
        saldo_label = monedas[0]['saldo_label']
    elif len(monedas) > 1:
        saldo_label = 'Por moneda'

    return {
        'auxiliares': len(auxiliares),
        'registros': len(items),
        'vencidos': vencidos,
        'parciales': parciales,
        'sin_vencimiento': sin_vencimiento,
        'saldo_label': saldo_label,
        'monedas': monedas,
    }


# ============================================================
# Extractos
# ============================================================

def _source_table_label(fuente):
    valores = {
        'COMPROMISO': 'Compromiso',
        'DOCUMENTO': 'Documento',
        'FACTURA': 'Factura electrónica',
    }
    return valores.get(_clean(fuente).upper(), 'Documento')


def _fetch_item_by_source(fuente, fuente_id):
    filtros = {
        'fecha_corte': date.today(),
        'fecha_modo': 'TODAS',
        'fecha_desde': date.today(),
        'fecha_hasta': date.today(),
        'origen': _clean(fuente).upper(),
        'estado': '',
        'unidad_negocio_id': None,
        'auxiliar_id': None,
        'moneda': '',
        'q': '',
    }
    items = _fetch_items(filtros)
    for item in items:
        if item['fuente_codigo'] == filtros['origen'] and str(item['fuente_id']) == str(fuente_id):
            return item
    return None


def _fetch_movimientos(fuente, fuente_id):
    fuente = _clean(fuente).upper()
    if fuente not in {'COMPROMISO', 'DOCUMENTO', 'FACTURA'}:
        raise ValueError('El origen del documento no es válido.')

    if fuente == 'COMPROMISO':
        return _fetch_movimientos_compromiso(fuente_id)
    if fuente == 'DOCUMENTO':
        return _fetch_movimientos_documento(fuente_id)
    return _fetch_movimientos_factura(fuente_id)


def _build_movimientos(rows, moneda_label):
    movimientos = []
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')
    saldo = Decimal('0.00')
    for idx, row in enumerate(rows, start=1):
        debe = _to_decimal(row.get('debe'))
        haber = _to_decimal(row.get('haber'))
        total_debe += debe
        total_haber += haber
        saldo += debe - haber
        movimientos.append({
            'nro': idx,
            'fecha': row.get('fecha'),
            'fecha_label': _date_label(row.get('fecha')),
            'documento': row.get('documento') or '',
            'glosa': row.get('glosa') or '',
            'debe': debe,
            'haber': haber,
            'saldo': saldo,
            'debe_label': _money_label(debe),
            'haber_label': _money_label(haber),
            'saldo_label': _money_label(saldo),
        })

    resumen = {
        'moneda_label': moneda_label,
        'debe': total_debe,
        'haber': total_haber,
        'saldo': total_debe - total_haber,
        'debe_label': _money_label(total_debe),
        'haber_label': _money_label(total_haber),
        'saldo_label': _money_label(total_debe - total_haber),
    }
    return movimientos, resumen


def _fetch_movimientos_compromiso(fuente_id):
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            """
            WITH base AS (
                SELECT
                    d.id AS detalle_id,
                    d.fecha_vencimiento::date AS fecha,
                    COALESCE(c.codigo, 'Compromiso #' || c.id::text) AS referencia,
                    COALESCE(NULLIF(c.descripcion, ''), c.nombre, 'Compromiso por cobrar') AS glosa,
                    COALESCE(d.monto_programado, 0) AS total,
                    %s::text AS moneda_codigo
                FROM contabilidad.compromiso_detalle d
                JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
                WHERE d.id = %s
            )
            SELECT fecha, referencia AS documento, glosa, total AS debe, 0::numeric AS haber, 1 AS orden, 0 AS suborden
            FROM base
            UNION ALL
            SELECT
                co.fecha::date AS fecha,
                ('Cobro #' || co.id::text || COALESCE(' · Asiento #' || co.asiento_id::text, '')) AS documento,
                COALESCE(co.glosa, co.referencia, 'Cobro aplicado') AS glosa,
                0::numeric AS debe,
                COALESCE(cd.subtotal, 0) AS haber,
                2 AS orden,
                cd.id AS suborden
            FROM contabilidad.cobro_detalle cd
            JOIN contabilidad.cobro co ON co.id = cd.cobro_id
            WHERE cd.tipo_linea = 'COMPROMISO'
              AND cd.compromiso_detalle_id = %s
              AND co.estado = 'CONFIRMADO'
            ORDER BY orden ASC, fecha ASC, suborden ASC
            """,
            (MONEDA_BASE, fuente_id, fuente_id),
        )
        rows = [dict(row) for row in cursor.fetchall()]
    return _build_movimientos(rows, MONEDA_BASE)


def _fetch_movimientos_documento(fuente_id):
    with DatabaseManager.get_cursor() as cursor:
        currency_symbols = _fetch_currency_symbols(cursor)
        cursor.execute(
            """
            WITH base AS (
                SELECT
                    d.id,
                    d.fecha_documento::date AS fecha,
                    TRIM(CONCAT(COALESCE(d.tipo_documento, 'DOCUMENTO'), ' ', COALESCE(d.numero_documento, ''))) AS referencia,
                    COALESCE(NULLIF(d.descripcion, ''), d.referencia_externa, d.numero_documento, 'Documento por cobrar') AS glosa,
                    COALESCE(d.importe_total, 0) AS total,
                    COALESCE(d.moneda_codigo, %s) AS moneda_codigo
                FROM contabilidad.documento_por_cobrar d
                WHERE d.id = %s
            )
            SELECT fecha, referencia AS documento, glosa, total AS debe, 0::numeric AS haber, 1 AS orden, 0 AS suborden, moneda_codigo
            FROM base
            UNION ALL
            SELECT
                co.fecha::date AS fecha,
                ('Cobro #' || co.id::text || COALESCE(' · Asiento #' || co.asiento_id::text, '')) AS documento,
                COALESCE(co.glosa, co.referencia, 'Cobro aplicado') AS glosa,
                0::numeric AS debe,
                COALESCE(da.monto_aplicado, 0) AS haber,
                2 AS orden,
                da.id AS suborden,
                base.moneda_codigo
            FROM contabilidad.documento_por_cobrar_aplicacion da
            JOIN contabilidad.cobro co ON co.id = da.cobro_id
            JOIN base ON base.id = da.documento_por_cobrar_id
            WHERE da.documento_por_cobrar_id = %s
              AND co.estado = 'CONFIRMADO'
            ORDER BY orden ASC, fecha ASC, suborden ASC
            """,
            (MONEDA_BASE, fuente_id, fuente_id),
        )
        rows = [dict(row) for row in cursor.fetchall()]
    moneda = _clean(rows[0].get('moneda_codigo')).upper() if rows else MONEDA_BASE
    return _build_movimientos(rows, _moneda_label(moneda, currency_symbols.get(moneda)))


def _fetch_movimientos_factura(fuente_id):
    with DatabaseManager.get_cursor() as cursor:
        currency_symbols = _fetch_currency_symbols(cursor)
        cursor.execute(
            """
            WITH base AS (
                SELECT
                    fe.id,
                    fe.fecha_emision::date AS fecha,
                    ('Factura ' || COALESCE(fe.numero_factura, '')) AS referencia,
                    ('Factura electrónica emitida') AS glosa,
                    COALESCE(fe.importe_total, 0) AS total,
                    COALESCE(fe.moneda_codigo, %s) AS moneda_codigo
                FROM contabilidad.factura_electronica fe
                WHERE fe.id = %s
            )
            SELECT fecha, referencia AS documento, glosa, total AS debe, 0::numeric AS haber, 1 AS orden, 0 AS suborden, moneda_codigo
            FROM base
            UNION ALL
            SELECT
                co.fecha::date AS fecha,
                ('Cobro #' || co.id::text || COALESCE(' · Asiento #' || co.asiento_id::text, '')) AS documento,
                COALESCE(co.glosa, co.referencia, 'Cobro aplicado a factura') AS glosa,
                0::numeric AS debe,
                COALESCE(fa.monto_aplicado, 0) AS haber,
                2 AS orden,
                fa.id AS suborden,
                base.moneda_codigo
            FROM contabilidad.factura_aplicacion fa
            JOIN contabilidad.cobro co ON co.id = fa.cobro_id
            JOIN base ON base.id = fa.factura_electronica_id
            WHERE fa.factura_electronica_id = %s
              AND co.estado = 'CONFIRMADO'
            UNION ALL
            SELECT
                v.fecha::date AS fecha,
                ('Venta #' || v.id::text || COALESCE(' · Asiento #' || v.asiento_id::text, '')) AS documento,
                COALESCE(v.glosa, 'Venta aplicada a factura') AS glosa,
                0::numeric AS debe,
                COALESCE(fa.monto_aplicado, 0) AS haber,
                3 AS orden,
                fa.id AS suborden,
                base.moneda_codigo
            FROM contabilidad.factura_aplicacion fa
            JOIN contabilidad.venta v ON v.id = fa.venta_id
            JOIN base ON base.id = fa.factura_electronica_id
            WHERE fa.factura_electronica_id = %s
              AND v.estado <> 'ANULADO'
            UNION ALL
            SELECT
                fr.creado_en::date AS fecha,
                ('Regularización #' || fr.id::text) AS documento,
                TRIM(CONCAT(COALESCE(fr.motivo, ''), ' ', COALESCE(fr.observacion, ''))) AS glosa,
                0::numeric AS debe,
                COALESCE(fr.monto, 0) AS haber,
                4 AS orden,
                fr.id AS suborden,
                base.moneda_codigo
            FROM contabilidad.factura_regularizacion fr
            JOIN base ON base.id = fr.factura_electronica_id
            WHERE fr.factura_electronica_id = %s
              AND fr.activo = TRUE
            ORDER BY orden ASC, fecha ASC, suborden ASC
            """,
            (MONEDA_BASE, fuente_id, fuente_id, fuente_id, fuente_id),
        )
        rows = [dict(row) for row in cursor.fetchall()]
    moneda = _clean(rows[0].get('moneda_codigo')).upper() if rows else MONEDA_BASE
    return _build_movimientos(rows, _moneda_label(moneda, currency_symbols.get(moneda)))


# ============================================================
# PDF
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

    def _draw_footer(self, total_pages: int):
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
        canvas.setFont('Helvetica-Bold', 18)
        canvas.drawString(x_left, header_top - 21, title)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(x_left, header_top - 38, subtitle)
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
        canvas.line(x_left, header_top - 56, x_right, header_top - 56)
        canvas.restoreState()


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DXTMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=8.2, leading=10.2, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTBody', parent=styles['Normal'], fontName='Helvetica', fontSize=6.8, leading=8.2, textColor=TEXT, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTBodyCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=6.8, leading=8.2, textColor=TEXT, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTBodyRight', parent=styles['Normal'], fontName='Helvetica', fontSize=6.8, leading=8.2, textColor=TEXT, alignment=TA_RIGHT, wordWrap='CJK'))
    return styles


def _build_pdf_bytes(*, title, subtitle, header_note, columns, rows, col_widths, pagesize=landscape(A4)):
    buffer = io.BytesIO()
    context = {
        'title': title,
        'subtitle': subtitle,
        'emitted_by': usuario_actual(),
        'logo_path': logo_path(),
    }
    doc = BrandedDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=48 * mm,
        bottomMargin=18 * mm,
        report_context=context,
    )
    styles = _pdf_styles()
    story = [Paragraph(_safe_text(header_note), styles['DXTMeta']), Spacer(1, 4 * mm)]
    data = [[Paragraph(_safe_text(col['label']), styles['DXTBodyCenter']) for col in columns]]
    for row in rows:
        rendered = []
        for idx, value in enumerate(row):
            align = columns[idx].get('align', 'left') if idx < len(columns) else 'left'
            style = styles['DXTBodyRight'] if align == 'right' else styles['DXTBodyCenter'] if align == 'center' else styles['DXTBody']
            rendered.append(Paragraph(_safe_text(value), style))
        data.append(rendered)

    table = Table(data, colWidths=[w * mm for w in col_widths], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            table.setStyle(TableStyle([('BACKGROUND', (0, row_idx), (-1, row_idx), ROW_ALT)]))
        if row_idx == len(data) - 1 and rows and str(rows[-1][0]).upper() == 'TOTAL':
            table.setStyle(TableStyle([('BACKGROUND', (0, row_idx), (-1, row_idx), TOTAL_FILL), ('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold')]))

    story.append(table)
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# Rutas
# ============================================================

@facturas_auxiliar_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return redirect(url_for('facturas_auxiliar.facturas_estado'))


@facturas_auxiliar_bp.route('/facturas-estado')
@login_required
@roles_required(ROLES_LECTURA)
def facturas_estado():
    error = ''
    try:
        filtros = _build_filters(request.args)
        items = _fetch_items(filtros)
        resumen = _build_summary(items)
    except ValueError as exc:
        filtros = _build_filters({})
        items = []
        resumen = _build_summary([])
        error = str(exc)
    except Exception as exc:
        filtros = _build_filters({})
        items = []
        resumen = _build_summary([])
        error = f'No se pudo cargar el reporte. {exc}'

    unidades, auxiliares, monedas = _fetch_catalogos()
    query_args = request.args.to_dict(flat=True)

    return render_template(
        'facturas_auxiliar_index.html',
        filtros=filtros,
        fecha_modos=FECHA_MODOS,
        origenes=ORIGENES,
        estados=ESTADOS,
        unidades=unidades,
        auxiliares=auxiliares,
        monedas=monedas,
        items=items,
        resumen=resumen,
        periodo_label=_periodo_label(filtros),
        query_args=query_args,
        error=error,
    )


@facturas_auxiliar_bp.route('/facturas-estado/api/<fuente>/<int:fuente_id>/detalle')
@login_required
@roles_required(ROLES_LECTURA)
def facturas_estado_api_detalle(fuente, fuente_id):
    try:
        item = _fetch_item_by_source(fuente, fuente_id)
        if not item:
            return jsonify({'ok': False, 'message': 'No se encontró un documento pendiente con ese identificador.'}), 404
        movimientos, resumen = _fetch_movimientos(fuente, fuente_id)
        return jsonify({
            'ok': True,
            'item': _json_ready(item),
            'movimientos': _json_ready(movimientos),
            'resumen': _json_ready(resumen),
        })
    except Exception as exc:
        return jsonify({'ok': False, 'message': f'No se pudo cargar el detalle. {exc}'}), 500


@facturas_auxiliar_bp.route('/facturas-estado/pdf')
@facturas_auxiliar_bp.route('/facturas-estado/pdf/general')
@login_required
@roles_required(ROLES_LECTURA)
def facturas_estado_pdf_general():
    try:
        filtros = _build_filters(request.args)
        items = _fetch_items(filtros)
        resumen = _build_summary(items)
        rows = []
        for row in items:
            rows.append([
                row['auxiliar_nombre'],
                row['origen_label'],
                row['referencia'],
                row['fecha_documento_label'],
                row['fecha_vencimiento_label'],
                row['estado_label'],
                row['moneda_label'],
                row['total_label'],
                row['aplicado_label'],
                row['saldo_label'],
            ])
        if len(resumen['monedas']) == 1:
            data = resumen['monedas'][0]
            rows.append(['TOTAL', '', '', '', '', '', data['moneda_label'], data['total_label'], data['aplicado_label'], data['saldo_label']])

        pdf_bytes = _build_pdf_bytes(
            title='Cartera documental por auxiliar',
            subtitle=f"{_periodo_label(filtros)} · {filtros['origen_label']} · {filtros['estado_label']}",
            header_note='Cartera pendiente agrupada documentalmente por auxiliar.',
            columns=[
                {'label': 'Auxiliar'},
                {'label': 'Origen'},
                {'label': 'Referencia'},
                {'label': 'Documento', 'align': 'center'},
                {'label': 'Vencimiento', 'align': 'center'},
                {'label': 'Estado', 'align': 'center'},
                {'label': 'Moneda', 'align': 'center'},
                {'label': 'Total', 'align': 'right'},
                {'label': 'Aplicado', 'align': 'right'},
                {'label': 'Saldo', 'align': 'right'},
            ],
            rows=rows,
            col_widths=[38, 28, 32, 22, 24, 24, 18, 24, 24, 24],
            pagesize=landscape(A4),
        )
        filename = f"cartera_documental_auxiliar_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF de cartera documental. {exc}', status=500, mimetype='text/plain')


@facturas_auxiliar_bp.route('/facturas-estado/<fuente>/<int:fuente_id>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def facturas_estado_pdf_detalle(fuente, fuente_id):
    try:
        item = _fetch_item_by_source(fuente, fuente_id)
        if not item:
            return Response('No se encontró un documento pendiente con ese identificador.', status=404, mimetype='text/plain')
        movimientos, resumen = _fetch_movimientos(fuente, fuente_id)
        rows = []
        for row in movimientos:
            rows.append([
                row['fecha_label'],
                row['documento'],
                row['glosa'],
                row['debe_label'],
                row['haber_label'],
                row['saldo_label'],
            ])
        rows.append(['', 'TOTAL', '', resumen['debe_label'], resumen['haber_label'], resumen['saldo_label']])
        pdf_bytes = _build_pdf_bytes(
            title='Extracto documental',
            subtitle=f"{_source_table_label(fuente)} · {item['referencia']} · Auxiliar: {item['auxiliar_nombre']}",
            header_note=f"Moneda: {item['moneda_label']} · Saldo: {resumen['saldo_label']}",
            columns=[
                {'label': 'Fecha', 'align': 'center'},
                {'label': 'Documento', 'align': 'center'},
                {'label': 'Glosa'},
                {'label': 'Debe', 'align': 'right'},
                {'label': 'Haber', 'align': 'right'},
                {'label': 'Saldo', 'align': 'right'},
            ],
            rows=rows,
            col_widths=[22, 42, 78, 24, 24, 24],
            pagesize=portrait(A4),
        )
        filename = f"extracto_documental_{_filename_safe(item['referencia'])}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF del extracto. {exc}', status=500, mimetype='text/plain')


@facturas_auxiliar_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('facturas_auxiliar_help.html')
