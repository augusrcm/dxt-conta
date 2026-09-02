# ============================================================
# DXT CONTA - Reporte Especial
# Reporte: Antigüedad de Cartera por Cobrar
# ============================================================

from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Response, jsonify, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfgen.canvas import Canvas

from database.db_manager import DatabaseManager
from modules.antiguedad_saldos_cobrar import antiguedad_saldos_cobrar_bp
from modules.reportes_rapidos.core.utils import logo_path, usuario_actual
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
CENTAVO = Decimal('0.01')
MONEDA_BASE = 'BOB'
MAX_ROWS = 5000

ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
TOTAL_FILL = colors.HexColor('#e8f1ff')

ORIGENES = {
    '': 'Todos',
    'COMPROMISO': 'Compromisos',
    'DOCUMENTO': 'Documentos',
    'FACTURA': 'Facturas electrónicas',
}

BUCKETS = [
    ('por_vencer', 'Por vencer'),
    ('bucket_0_30', '0-30'),
    ('bucket_31_60', '31-60'),
    ('bucket_61_90', '61-90'),
    ('bucket_mas_90', '+90'),
    ('sin_vencimiento', 'Sin vencimiento'),
]

# ============================================================
# Helpers
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
        if default is not None:
            return default
        raise ValueError(f'{field_name} es obligatorio.')
    try:
        parsed = datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no es válida.') from exc
    return parsed


def _parse_optional_int(value, field_name):
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} no es válido.') from exc
    if parsed <= 0:
        return None
    return parsed


def _safe_text(value) -> str:
    return str(value or '').strip()


def _json_ready(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _filename_safe(value):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or '')).strip('_')[:70]
    return cleaned or 'cartera'


def _format_money(value, moneda=None):
    # Regla UI: los importes no llevan prefijo ni sufijo de moneda.
    # La moneda se informa en su propia columna/campo.
    return _amount(value)


def _moneda_label(codigo, simbolo=None):
    return _clean(simbolo) or _clean(codigo).upper() or MONEDA_BASE


def _fetch_currency_symbols(db):
    rows = db.execute_query(
        """
        SELECT UPPER(codigo) AS codigo, COALESCE(NULLIF(simbolo, ''), codigo) AS simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        """
    )
    data = {}
    for row in rows or []:
        data[_clean(row.get('codigo')).upper()] = _clean(row.get('simbolo')) or _clean(row.get('codigo')).upper()
    data.setdefault(MONEDA_BASE, MONEDA_BASE)
    return data


def _build_filters(args):
    today = date.today()
    fecha_corte = _parse_date(args.get('fecha_corte'), 'La fecha de corte', default=today)
    origen = _clean(args.get('origen')).upper()
    if origen not in ORIGENES:
        raise ValueError('El origen seleccionado no es válido.')
    return {
        'fecha_corte': fecha_corte,
        'unidad_negocio_id': _parse_optional_int(args.get('unidad_negocio_id'), 'La unidad de negocio'),
        'auxiliar_id': _parse_optional_int(args.get('auxiliar_id'), 'El auxiliar'),
        'moneda': _clean(args.get('moneda')).upper(),
        'origen': origen,
        'q': _clean(args.get('q')),
    }


def _periodo_label(filtros):
    return f"Corte al {_date_label(filtros['fecha_corte'])}"


def _bucket_for(fecha_vencimiento, fecha_corte):
    if not isinstance(fecha_vencimiento, date):
        return 'sin_vencimiento', 'Sin vencimiento', None, 5
    dias = (fecha_corte - fecha_vencimiento).days
    if dias < 0:
        return 'por_vencer', 'Por vencer', dias, 0
    if dias <= 30:
        return 'bucket_0_30', '0-30', dias, 1
    if dias <= 60:
        return 'bucket_31_60', '31-60', dias, 2
    if dias <= 90:
        return 'bucket_61_90', '61-90', dias, 3
    return 'bucket_mas_90', '+90', dias, 4


def _riesgo_from_row(row):
    if row.get('bucket_mas_90', Decimal('0.00')) > 0:
        return 'danger', '+90'
    if row.get('bucket_61_90', Decimal('0.00')) > 0:
        return 'warning', '61-90'
    if row.get('bucket_31_60', Decimal('0.00')) > 0:
        return 'warning', '31-60'
    if row.get('bucket_0_30', Decimal('0.00')) > 0:
        return 'primary', '0-30'
    if row.get('sin_vencimiento', Decimal('0.00')) > 0:
        return 'secondary', 'Sin venc.'
    return 'success', 'Normal'


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


# ============================================================
# Catálogos
# ============================================================

def _fetch_catalogos():
    with DatabaseManager() as db:
        unidades = db.execute_query(
            """
            SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
            FROM contabilidad.unidad_negocio
            WHERE activo = TRUE
            ORDER BY nombre ASC, codigo ASC
            """
        )
        auxiliares = db.execute_query(
            """
            SELECT id, COALESCE(nombre, '') AS nombre, COALESCE(nit_ci, '') AS nit_ci
            FROM contabilidad.auxiliar
            WHERE activo = TRUE
            ORDER BY COALESCE(nombre, '') ASC, COALESCE(nit_ci, '') ASC
            """
        )
        monedas = db.execute_query(
            """
            SELECT codigo, COALESCE(nombre, codigo) AS nombre, COALESCE(simbolo, '') AS simbolo
            FROM contabilidad.moneda
            WHERE activo = TRUE
            ORDER BY CASE WHEN codigo = %s THEN 0 ELSE 1 END, codigo
            """,
            (MONEDA_BASE,),
        )
    return unidades, auxiliares, monedas


# ============================================================
# Fuente unificada de cartera
# ============================================================

def _filter_sql(alias_prefix, filtros, params, q_fields):
    clauses = []
    if filtros.get('unidad_negocio_id'):
        clauses.append(f'{alias_prefix}.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    if filtros.get('auxiliar_id'):
        clauses.append(f'{alias_prefix}.cliente_auxiliar_id = %s')
        params.append(filtros['auxiliar_id'])
    if filtros.get('moneda'):
        clauses.append(f"UPPER(COALESCE({alias_prefix}.moneda_codigo, %s)) = %s")
        params.extend([MONEDA_BASE, filtros['moneda']])
    if filtros.get('q') and q_fields:
        like_value = f"%{filtros['q']}%"
        clauses.append('(' + ' OR '.join([f"COALESCE({field}, '') ILIKE %s" for field in q_fields]) + ')')
        params.extend([like_value] * len(q_fields))
    return clauses


def _fetch_compromisos(db, filtros):
    if filtros['origen'] not in ('', 'COMPROMISO'):
        return []
    params_base = [filtros['fecha_corte'], MONEDA_BASE, filtros['fecha_corte']]
    extra_params = []
    extra = []
    if filtros.get('unidad_negocio_id'):
        extra.append('c.unidad_negocio_id = %s')
        extra_params.append(filtros['unidad_negocio_id'])
    if filtros.get('auxiliar_id'):
        extra.append('c.auxiliar_id = %s')
        extra_params.append(filtros['auxiliar_id'])
    if filtros.get('moneda') and filtros['moneda'] != MONEDA_BASE:
        return []
    if filtros.get('q'):
        like_value = f"%{filtros['q']}%"
        extra.append(
            """
            (
              COALESCE(c.codigo, '') ILIKE %s OR COALESCE(c.nombre, '') ILIKE %s OR
              COALESCE(c.descripcion, '') ILIKE %s OR COALESCE(aux.nombre, '') ILIKE %s OR
              COALESCE(aux.nit_ci, '') ILIKE %s OR COALESCE(c.cuenta_contable, '') ILIKE %s
            )
            """
        )
        extra_params.extend([like_value] * 6)
    where_extra = (' AND ' + ' AND '.join(extra)) if extra else ''

    return db.execute_query(
        f"""
        WITH apps AS (
            SELECT
                cd.compromiso_detalle_id,
                COALESCE(SUM(cd.subtotal), 0) AS aplicado
            FROM contabilidad.cobro_detalle cd
            INNER JOIN contabilidad.cobro co ON co.id = cd.cobro_id
            WHERE cd.tipo_linea = 'COMPROMISO'
              AND co.estado = 'CONFIRMADO'
              AND co.fecha <= %s
            GROUP BY cd.compromiso_detalle_id
        )
        SELECT
            'COMPROMISO'::text AS fuente_codigo,
            d.id::text AS fuente_id,
            d.fecha_vencimiento::date AS fecha_vencimiento,
            d.fecha_vencimiento::date AS fecha_documento,
            CASE WHEN c.auxiliar_id IS NOT NULL THEN 'A:' || c.auxiliar_id::text ELSE 'N:' || md5(COALESCE(aux.nombre, c.nombre, '') || '|') END AS cliente_key,
            c.auxiliar_id AS cliente_auxiliar_id,
            COALESCE(aux.nombre, c.nombre, 'Sin cliente') AS cliente_nombre,
            COALESCE(aux.nit_ci, '') AS cliente_doc,
            c.unidad_negocio_id,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '') AS unidad_label,
            %s::text AS moneda_codigo,
            COALESCE(d.monto_programado, 0)::numeric(18,2) AS total,
            COALESCE(apps.aplicado, 0)::numeric(18,2) AS aplicado,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(apps.aplicado, 0), 0)::numeric(18,2) AS saldo,
            COALESCE(c.codigo, '') AS referencia,
            COALESCE(NULLIF(c.descripcion, ''), c.nombre, 'Compromiso por cobrar') AS detalle,
            'Compromiso'::text AS origen_label,
            c.cuenta_contable AS cuenta_codigo,
            COALESCE(cta.nombre, '') AS cuenta_nombre,
            d.estado::text AS estado
        FROM contabilidad.compromiso_detalle d
        INNER JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        LEFT JOIN apps ON apps.compromiso_detalle_id = d.id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = c.cuenta_contable
        WHERE c.activo = TRUE
          AND c.tipo = 'COBRAR'
          AND d.fecha_vencimiento <= %s
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(apps.aplicado, 0), 0) > 0
          {where_extra}
        ORDER BY d.fecha_vencimiento ASC, cliente_nombre ASC, c.codigo ASC
        LIMIT {MAX_ROWS}
        """,
        tuple(params_base + extra_params),
    )


def _fetch_documentos(db, filtros):
    if filtros['origen'] not in ('', 'DOCUMENTO'):
        return []
    params_base = [filtros['fecha_corte'], MONEDA_BASE, filtros['fecha_corte']]
    extra_params = []
    extra = _filter_sql('d', filtros, extra_params, [
        'd.numero_documento', 'd.referencia_externa', 'd.descripcion', 'd.cliente_nombre', 'd.cliente_nit', 'd.cuenta_cartera_codigo'
    ])
    where_extra = (' AND ' + ' AND '.join(extra)) if extra else ''

    return db.execute_query(
        f"""
        WITH apps AS (
            SELECT
                da.documento_por_cobrar_id,
                COALESCE(SUM(da.monto_aplicado), 0) AS aplicado
            FROM contabilidad.documento_por_cobrar_aplicacion da
            INNER JOIN contabilidad.cobro co ON co.id = da.cobro_id
            WHERE co.estado = 'CONFIRMADO'
              AND co.fecha <= %s
            GROUP BY da.documento_por_cobrar_id
        )
        SELECT
            'DOCUMENTO'::text AS fuente_codigo,
            d.id::text AS fuente_id,
            d.fecha_vencimiento::date AS fecha_vencimiento,
            d.fecha_documento::date AS fecha_documento,
            CASE WHEN d.cliente_auxiliar_id IS NOT NULL THEN 'A:' || d.cliente_auxiliar_id::text ELSE 'N:' || md5(COALESCE(d.cliente_nit, '') || '|' || COALESCE(d.cliente_nombre, '')) END AS cliente_key,
            d.cliente_auxiliar_id,
            COALESCE(NULLIF(d.cliente_nombre, ''), aux.nombre, 'Sin cliente') AS cliente_nombre,
            COALESCE(NULLIF(d.cliente_nit, ''), aux.nit_ci, '') AS cliente_doc,
            d.unidad_negocio_id,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, '') AS unidad_label,
            COALESCE(d.moneda_codigo, %s)::text AS moneda_codigo,
            COALESCE(d.importe_total, 0)::numeric(18,2) AS total,
            COALESCE(apps.aplicado, 0)::numeric(18,2) AS aplicado,
            GREATEST(COALESCE(d.importe_total, 0) - COALESCE(apps.aplicado, 0), 0)::numeric(18,2) AS saldo,
            (COALESCE(d.tipo_documento, 'DOCUMENTO') || ' ' || COALESCE(d.numero_documento, '')) AS referencia,
            COALESCE(NULLIF(d.descripcion, ''), d.referencia_externa, d.numero_documento, 'Documento por cobrar') AS detalle,
            (_origen_label.origen)::text AS origen_label,
            d.cuenta_cartera_codigo AS cuenta_codigo,
            COALESCE(cta.nombre, '') AS cuenta_nombre,
            d.estado::text AS estado
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN apps ON apps.documento_por_cobrar_id = d.id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = d.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cta ON cta.codigo = d.cuenta_cartera_codigo
        CROSS JOIN LATERAL (
            SELECT CASE
                WHEN d.origen_documento = 'HISTORICO' THEN 'Documento histórico · ' || COALESCE(d.tipo_documento, 'DOCUMENTO')
                WHEN d.origen_documento = 'VIGENTE_MANUAL' THEN 'Documento vigente · ' || COALESCE(d.tipo_documento, 'DOCUMENTO')
                ELSE 'Documento por cobrar · ' || COALESCE(d.tipo_documento, 'DOCUMENTO')
            END AS origen
        ) AS _origen_label
        WHERE d.activo = TRUE
          AND d.estado IN ('PENDIENTE', 'PARCIAL')
          AND COALESCE(d.factura_electronica_id, 0) = 0
          AND COALESCE(d.origen_documento, '') <> 'FACTURA_ELECTRONICA'
          AND d.fecha_documento <= %s
          AND GREATEST(COALESCE(d.importe_total, 0) - COALESCE(apps.aplicado, 0), 0) > 0
          {where_extra}
        ORDER BY COALESCE(d.fecha_vencimiento, d.fecha_documento) ASC, cliente_nombre ASC, d.numero_documento ASC
        LIMIT {MAX_ROWS}
        """,
        tuple(params_base + extra_params),
    )


def _fetch_facturas(db, filtros):
    if filtros['origen'] not in ('', 'FACTURA'):
        return []
    params_base = [filtros['fecha_corte'], filtros['fecha_corte'], filtros['fecha_corte'], MONEDA_BASE, filtros['fecha_corte']]
    extra_params = []
    extra = []
    if filtros.get('unidad_negocio_id'):
        extra.append('fe.unidad_negocio_id = %s')
        extra_params.append(filtros['unidad_negocio_id'])
    if filtros.get('auxiliar_id'):
        extra.append('fe.cliente_auxiliar_id = %s')
        extra_params.append(filtros['auxiliar_id'])
    if filtros.get('moneda'):
        extra.append('UPPER(COALESCE(fe.moneda_codigo, %s)) = %s')
        extra_params.extend([MONEDA_BASE, filtros['moneda']])
    if filtros.get('q'):
        like_value = f"%{filtros['q']}%"
        extra.append(
            """
            (
              COALESCE(fe.numero_factura, '') ILIKE %s OR COALESCE(fe.nombre_cliente, '') ILIKE %s OR
              COALESCE(fe.nit_cliente, '') ILIKE %s OR COALESCE(aux.nombre, '') ILIKE %s OR
              COALESCE(aux.nit_ci, '') ILIKE %s OR COALESCE(fe.cuenta_cobrar_codigo, '') ILIKE %s
            )
            """
        )
        extra_params.extend([like_value] * 6)
    where_extra = (' AND ' + ' AND '.join(extra)) if extra else ''

    return db.execute_query(
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
            NULL::date AS fecha_vencimiento,
            fe.fecha_emision::date AS fecha_documento,
            CASE WHEN fe.cliente_auxiliar_id IS NOT NULL THEN 'A:' || fe.cliente_auxiliar_id::text ELSE 'N:' || md5(COALESCE(fe.nit_cliente, '') || '|' || COALESCE(fe.nombre_cliente, '')) END AS cliente_key,
            fe.cliente_auxiliar_id,
            COALESCE(NULLIF(fe.nombre_cliente, ''), aux.nombre, 'Sin cliente') AS cliente_nombre,
            COALESCE(NULLIF(fe.nit_cliente, ''), aux.nit_ci, '') AS cliente_doc,
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
            fe.estado::text AS estado
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
        tuple(params_base + extra_params),
    )


def _fetch_items(filtros):
    with DatabaseManager() as db:
        items = []
        items.extend(_fetch_compromisos(db, filtros))
        items.extend(_fetch_documentos(db, filtros))
        items.extend(_fetch_facturas(db, filtros))
        currency_symbols = _fetch_currency_symbols(db)

    normalized = []
    for row in items:
        data = dict(row)
        code = _clean(data.get('moneda_codigo')).upper() or MONEDA_BASE
        data['moneda_codigo'] = code
        data['moneda_simbolo'] = currency_symbols.get(code, code)
        normalized.append(data)
    return [_format_item(row, idx, filtros['fecha_corte']) for idx, row in enumerate(normalized, start=1)]


def _format_item(row, idx, fecha_corte):
    fecha_vencimiento = row.get('fecha_vencimiento')
    fecha_documento = row.get('fecha_documento')
    bucket_key, bucket_label, dias_vencido, orden_bucket = _bucket_for(fecha_vencimiento, fecha_corte)
    dias_documento = (fecha_corte - fecha_documento).days if isinstance(fecha_documento, date) else None
    total = _to_decimal(row.get('total'))
    aplicado = _to_decimal(row.get('aplicado'))
    saldo = _to_decimal(row.get('saldo'))
    moneda = _clean(row.get('moneda_codigo')).upper() or MONEDA_BASE
    moneda_simbolo = _moneda_label(moneda, row.get('moneda_simbolo'))
    return {
        'nro': idx,
        'fuente_codigo': row.get('fuente_codigo') or '',
        'fuente_id': row.get('fuente_id') or '',
        'cliente_key': row.get('cliente_key') or '',
        'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
        'cliente_nombre': row.get('cliente_nombre') or 'Sin cliente',
        'cliente_doc': row.get('cliente_doc') or '',
        'unidad_label': row.get('unidad_label') or '',
        'moneda_codigo': moneda,
        'moneda_simbolo': moneda_simbolo,
        'moneda_label': moneda_simbolo,
        'fecha_vencimiento': fecha_vencimiento.isoformat() if isinstance(fecha_vencimiento, date) else '',
        'fecha_vencimiento_label': _date_label(fecha_vencimiento) if isinstance(fecha_vencimiento, date) else 'Sin vencimiento',
        'fecha_documento': fecha_documento.isoformat() if isinstance(fecha_documento, date) else '',
        'fecha_documento_label': _date_label(fecha_documento),
        'dias_vencido': dias_vencido,
        'dias_documento': dias_documento,
        'dias_label': 'Sin vencimiento' if dias_vencido is None else (f'Por vencer {abs(dias_vencido)} d.' if dias_vencido < 0 else f'{dias_vencido} d.'),
        'bucket_key': bucket_key,
        'bucket_label': bucket_label,
        'orden_bucket': orden_bucket,
        'referencia': row.get('referencia') or '',
        'detalle': row.get('detalle') or '',
        'origen_label': row.get('origen_label') or '',
        'cuenta_codigo': row.get('cuenta_codigo') or '',
        'cuenta_nombre': row.get('cuenta_nombre') or '',
        'estado': row.get('estado') or '',
        'total': total,
        'aplicado': aplicado,
        'saldo': saldo,
        'total_label': _format_money(total, moneda),
        'aplicado_label': _format_money(aplicado, moneda),
        'saldo_label': _format_money(saldo, moneda),
    }


def _aggregate_general(items):
    grouped = {}
    for item in items:
        key = (item['cliente_key'], item['cliente_nombre'], item['cliente_doc'], item['moneda_codigo'])
        if key not in grouped:
            grouped[key] = {
                'cliente_key': item['cliente_key'],
                'auxiliar_id': item['cliente_auxiliar_id'],
                'cliente_nombre': item['cliente_nombre'],
                'cliente_doc': item['cliente_doc'],
                'moneda_codigo': item['moneda_codigo'],
                'moneda_simbolo': item.get('moneda_simbolo') or item['moneda_codigo'],
                'moneda_label': item.get('moneda_label') or item.get('moneda_simbolo') or item['moneda_codigo'],
                'registros': 0,
                'por_vencer': Decimal('0.00'),
                'bucket_0_30': Decimal('0.00'),
                'bucket_31_60': Decimal('0.00'),
                'bucket_61_90': Decimal('0.00'),
                'bucket_mas_90': Decimal('0.00'),
                'sin_vencimiento': Decimal('0.00'),
                'total_pendiente': Decimal('0.00'),
                'mayor_antiguedad': 0,
                'sin_vencimiento_count': 0,
                'origenes': set(),
                'unidades': set(),
            }
        row = grouped[key]
        bucket = item['bucket_key']
        row[bucket] += item['saldo']
        row['total_pendiente'] += item['saldo']
        row['registros'] += 1
        row['origenes'].add(item['origen_label'])
        if item.get('unidad_label'):
            row['unidades'].add(item['unidad_label'])
        if item['dias_vencido'] is not None and item['dias_vencido'] > row['mayor_antiguedad']:
            row['mayor_antiguedad'] = item['dias_vencido']
        if bucket == 'sin_vencimiento':
            row['sin_vencimiento_count'] += 1

    rows = []
    for idx, row in enumerate(grouped.values(), start=1):
        riesgo_badge, riesgo_label = _riesgo_from_row(row)
        row['nro'] = idx
        row['origenes_label'] = ' · '.join(sorted(row['origenes']))
        row['unidades_label'] = ' · '.join(sorted(row['unidades']))
        row['riesgo_badge'] = riesgo_badge
        row['riesgo_label'] = riesgo_label
        for key, _ in BUCKETS:
            row[f'{key}_label'] = _format_money(row[key], row['moneda_codigo'])
        row['total_pendiente_label'] = _format_money(row['total_pendiente'], row['moneda_codigo'])
        rows.append(row)

    rows.sort(key=lambda r: (
        -_to_decimal(r.get('bucket_mas_90')),
        -_to_decimal(r.get('bucket_61_90')),
        -_to_decimal(r.get('total_pendiente')),
        r.get('cliente_nombre') or '',
        r.get('moneda_codigo') or '',
    ))
    for idx, row in enumerate(rows, start=1):
        row['nro'] = idx
    return rows


def _build_summary(rows, items):
    totals = defaultdict(lambda: Decimal('0.00'))
    bucket_totals = defaultdict(lambda: defaultdict(lambda: Decimal('0.00')))
    registros = 0
    clientes = set()
    documentos = 0
    for item in items:
        moneda = item['moneda_codigo']
        saldo = item['saldo']
        totals[moneda] += saldo
        bucket_totals[moneda][item['bucket_key']] += saldo
        registros += 1
        clientes.add((item['cliente_key'], item['moneda_codigo']))
        documentos += 1
    monedas_sorted = sorted(totals.keys())
    if len(monedas_sorted) == 1:
        total_label = _amount(totals[monedas_sorted[0]])
    elif len(monedas_sorted) > 1:
        total_label = 'Por moneda'
    else:
        total_label = '0.00'
    return {
        'clientes': len(clientes),
        'registros': registros,
        'documentos': documentos,
        'total_label': total_label,
        'monedas': monedas_sorted,
        'bucket_totals': {m: {k: float(v) for k, v in vals.items()} for m, vals in bucket_totals.items()},
        'bucket_totals_label': {
            m: {k: _format_money(vals.get(k, Decimal('0.00')), m) for k, _label in BUCKETS}
            for m, vals in bucket_totals.items()
        },
    }


def _fetch_general(filtros):
    items = _fetch_items(filtros)
    return _aggregate_general(items), items


def _fetch_detalle(filtros, cliente_key, moneda_codigo):
    items = _fetch_items(filtros)
    cliente_key = _clean(cliente_key)
    moneda_codigo = _clean(moneda_codigo).upper()
    detalle = [item for item in items if item['cliente_key'] == cliente_key and item['moneda_codigo'].upper() == moneda_codigo]
    detalle.sort(key=lambda r: (
        r.get('orden_bucket', 9),
        -(r.get('dias_vencido') or 0),
        r.get('fecha_vencimiento') or '9999-12-31',
        r.get('referencia') or '',
    ))
    for idx, row in enumerate(detalle, start=1):
        row['nro'] = idx
    return detalle


def _build_detail_summary(detalle):
    total = Decimal('0.00')
    aplicado = Decimal('0.00')
    saldo = Decimal('0.00')
    mayor = 0
    cliente = ''
    cliente_doc = ''
    moneda = MONEDA_BASE
    moneda_simbolo = MONEDA_BASE
    for item in detalle:
        total += item['total']
        aplicado += item['aplicado']
        saldo += item['saldo']
        cliente = item.get('cliente_nombre') or cliente
        cliente_doc = item.get('cliente_doc') or cliente_doc
        moneda = item.get('moneda_codigo') or moneda
        moneda_simbolo = item.get('moneda_label') or item.get('moneda_simbolo') or moneda
        if item.get('dias_vencido') is not None and item['dias_vencido'] > mayor:
            mayor = item['dias_vencido']
    return {
        'cliente_nombre': cliente,
        'cliente_doc': cliente_doc,
        'moneda_codigo': moneda,
        'moneda_simbolo': moneda_simbolo,
        'moneda_label': moneda_simbolo,
        'registros': len(detalle),
        'total_label': _format_money(total, moneda),
        'aplicado_label': _format_money(aplicado, moneda),
        'saldo_label': _format_money(saldo, moneda),
        'mayor_antiguedad': mayor,
    }


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
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(page_count)
            Canvas.showPage(self)
        Canvas.save(self)

    def _draw_header_footer(self, page_count):
        width, height = self._pagesize
        self.saveState()
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.5)
        self.line(18 * mm, height - 18 * mm, width - 18 * mm, height - 18 * mm)
        self.setFillColor(NAVY)
        self.setFont('Helvetica-Bold', 8)
        self.drawString(18 * mm, height - 13 * mm, 'DXT-CONTA')
        self.setFillColor(MUTED)
        self.setFont('Helvetica', 7)
        self.drawRightString(width - 18 * mm, height - 13 * mm, self.report_context.get('emitido', ''))
        self.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        self.drawString(18 * mm, 8.5 * mm, self.report_context.get('usuario', ''))
        self.drawRightString(width - 18 * mm, 8.5 * mm, f'Página {self._pageNumber} de {page_count}')
        self.restoreState()


def _pdf_paragraph(text, style):
    safe = str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return Paragraph(safe, style)


def _build_pdf(title, subtitle, columns, rows, col_widths, pagesize):
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'], alignment=TA_LEFT, fontSize=14, textColor=NAVY, spaceAfter=3)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=8.5, textColor=MUTED, spaceAfter=9)
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=7, leading=8.2, textColor=TEXT)
    head_style = ParagraphStyle('Head', parent=cell_style, alignment=TA_CENTER, textColor=NAVY, fontName='Helvetica-Bold')

    doc = BaseDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame])])

    story = [_pdf_paragraph(title, title_style), _pdf_paragraph(subtitle, subtitle_style), Spacer(1, 3)]
    data = [[_pdf_paragraph(col['label'], head_style) for col in columns]]
    for row in rows:
        values = row.get('_values') if isinstance(row, dict) and '_values' in row else row
        data.append([_pdf_paragraph(value, cell_style) for value in values])

    table = Table(data, colWidths=[w * mm for w in col_widths], repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), ROW_ALT))
    table.setStyle(TableStyle(style))
    story.append(table)

    context = {
        'emitido': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'usuario': usuario_actual() or '',
    }
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# Rutas
# ============================================================

@antiguedad_saldos_cobrar_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    error = ''
    try:
        filtros = _build_filters(request.args)
        rows, items = _fetch_general(filtros)
        resumen = _build_summary(rows, items)
    except ValueError as exc:
        filtros = _build_filters({})
        rows, items = [], []
        resumen = _build_summary(rows, items)
        error = str(exc)
    except Exception as exc:
        filtros = _build_filters({})
        rows, items = [], []
        resumen = _build_summary(rows, items)
        error = f'No se pudo cargar la antigüedad de cartera. {exc}'

    unidades, auxiliares, monedas = _fetch_catalogos()
    query_args = request.args.to_dict(flat=True)
    return render_template(
        'antiguedad_saldos_cobrar_index.html',
        filtros=filtros,
        unidades=unidades,
        auxiliares=auxiliares,
        monedas=monedas,
        rows=rows,
        resumen=resumen,
        periodo_label=_periodo_label(filtros),
        query_args=query_args,
        error=error,
        origenes=ORIGENES,
    )


@antiguedad_saldos_cobrar_bp.route('/api/detalle')
@login_required
@roles_required(ROLES_LECTURA)
def api_detalle_unificado():
    try:
        filtros = _build_filters(request.args)
        detalle = _fetch_detalle(filtros, request.args.get('cliente_key'), request.args.get('moneda'))
        resumen = _build_detail_summary(detalle)
        return jsonify({'ok': True, 'detalle': _json_ready(detalle), 'resumen': _json_ready(resumen)})
    except Exception as exc:
        return jsonify({'ok': False, 'message': f'No se pudo cargar el detalle. {exc}'}), 500


@antiguedad_saldos_cobrar_bp.route('/api/<int:auxiliar_id>/<moneda>/detalle')
@login_required
@roles_required(ROLES_LECTURA)
def api_detalle(auxiliar_id, moneda):
    try:
        filtros = _build_filters(request.args)
        detalle = _fetch_detalle(filtros, f'A:{auxiliar_id}', moneda)
        resumen = _build_detail_summary(detalle)
        return jsonify({'ok': True, 'detalle': _json_ready(detalle), 'resumen': _json_ready(resumen)})
    except Exception as exc:
        return jsonify({'ok': False, 'message': f'No se pudo cargar el detalle. {exc}'}), 500


@antiguedad_saldos_cobrar_bp.route('/pdf')
@antiguedad_saldos_cobrar_bp.route('/pdf/general')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_general():
    try:
        filtros = _build_filters(request.args)
        rows, items = _fetch_general(filtros)
        pdf_rows = []
        for row in rows:
            pdf_rows.append([
                f"{row['cliente_nombre']}\n{row['cliente_doc']}",
                row.get('moneda_label') or row.get('moneda_simbolo') or row['moneda_codigo'],
                str(row['registros']),
                row['por_vencer_label'],
                row['bucket_0_30_label'],
                row['bucket_31_60_label'],
                row['bucket_61_90_label'],
                row['bucket_mas_90_label'],
                row['sin_vencimiento_label'],
                row['total_pendiente_label'],
            ])
        pdf_bytes = _build_pdf(
            title='Antigüedad de Cartera por Cobrar',
            subtitle=f"{_periodo_label(filtros)} · Origen: {ORIGENES.get(filtros['origen'], 'Todos')}",
            columns=[
                {'label': 'Cliente'}, {'label': 'Mon.'}, {'label': 'Reg.'}, {'label': 'Por vencer'},
                {'label': '0-30'}, {'label': '31-60'}, {'label': '61-90'}, {'label': '+90'},
                {'label': 'Sin venc.'}, {'label': 'Total'},
            ],
            rows=pdf_rows,
            col_widths=[54, 13, 12, 24, 24, 24, 24, 24, 28, 29],
            pagesize=landscape(A4),
        )
        filename = f"antiguedad_cartera_cobrar_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF. {exc}', status=500, mimetype='text/plain')


@antiguedad_saldos_cobrar_bp.route('/detalle/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_detalle_unificado():
    try:
        filtros = _build_filters(request.args)
        detalle = _fetch_detalle(filtros, request.args.get('cliente_key'), request.args.get('moneda'))
        resumen = _build_detail_summary(detalle)
        if not detalle:
            return Response('No se encontraron pendientes para el cliente seleccionado.', status=404, mimetype='text/plain')
        pdf_rows = []
        for row in detalle:
            pdf_rows.append([
                row['origen_label'],
                row['referencia'],
                row['fecha_vencimiento_label'],
                row['bucket_label'],
                row['total_label'],
                row['aplicado_label'],
                row['saldo_label'],
                row['estado'],
            ])
        cliente = resumen['cliente_nombre'] or 'Cliente'
        pdf_bytes = _build_pdf(
            title='Detalle de Antigüedad de Cartera',
            subtitle=f"{cliente} · {resumen.get('moneda_label') or resumen['moneda_codigo']} · {_periodo_label(filtros)}",
            columns=[
                {'label': 'Origen'}, {'label': 'Referencia'}, {'label': 'Venc.'}, {'label': 'Rango'},
                {'label': 'Total'}, {'label': 'Cobrado'}, {'label': 'Saldo'}, {'label': 'Estado'},
            ],
            rows=pdf_rows,
            col_widths=[33, 30, 21, 22, 27, 27, 27, 25],
            pagesize=portrait(A4),
        )
        filename = f"antiguedad_detalle_{_filename_safe(cliente)}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF del detalle. {exc}', status=500, mimetype='text/plain')


@antiguedad_saldos_cobrar_bp.route('/<int:auxiliar_id>/<moneda>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_auxiliar(auxiliar_id, moneda):
    try:
        filtros = _build_filters(request.args)
        detalle = _fetch_detalle(filtros, f'A:{auxiliar_id}', moneda)
        resumen = _build_detail_summary(detalle)
        if not detalle:
            return Response('No se encontraron pendientes para el cliente seleccionado.', status=404, mimetype='text/plain')
        pdf_rows = []
        for row in detalle:
            pdf_rows.append([
                row['origen_label'], row['referencia'], row['fecha_vencimiento_label'], row['bucket_label'],
                row['total_label'], row['aplicado_label'], row['saldo_label'], row['estado'],
            ])
        cliente = resumen['cliente_nombre'] or 'Cliente'
        pdf_bytes = _build_pdf(
            title='Detalle de Antigüedad de Cartera',
            subtitle=f"{cliente} · {resumen.get('moneda_label') or resumen['moneda_codigo']} · {_periodo_label(filtros)}",
            columns=[
                {'label': 'Origen'}, {'label': 'Referencia'}, {'label': 'Venc.'}, {'label': 'Rango'},
                {'label': 'Total'}, {'label': 'Cobrado'}, {'label': 'Saldo'}, {'label': 'Estado'},
            ],
            rows=pdf_rows,
            col_widths=[33, 30, 21, 22, 27, 27, 27, 25],
            pagesize=portrait(A4),
        )
        filename = f"antiguedad_detalle_{_filename_safe(cliente)}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF del detalle. {exc}', status=500, mimetype='text/plain')


@antiguedad_saldos_cobrar_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('antiguedad_saldos_cobrar_help.html')
