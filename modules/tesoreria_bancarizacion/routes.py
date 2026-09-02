# ============================================================
# DXT CONTA - Módulo Tesorería Bancarización Básica
# ============================================================

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from flask import render_template, request, session, url_for

from database.db_manager import DatabaseManager
from modules.tesoreria_bancarizacion import tesoreria_bancarizacion_bp
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
CUANTIA = Decimal('0.01')

ORIGEN_DETALLE_LABELS = {
    'DIRECTO': 'Directo',
    'COMPROMISO': 'Compromiso',
    'DOCUMENTO_COBRAR': 'Documento por cobrar',
    'DOCUMENTO_PAGAR': 'Documento por pagar',
}


# ============================================================
# Helpers
# ============================================================

def _clean(value):
    return (value or '').strip()


def _parse_date(value):
    value = _clean(value)
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def _to_money(value):
    return float(Decimal(str(value or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP))


def _origen_detalle_label(value, fallback='Directo'):
    value = _clean(value).upper()
    if not value:
        return fallback
    return ORIGEN_DETALLE_LABELS.get(value, value.replace('_', ' ').title())


def _can_edit():
    try:
        return int(session.get('rol_id', 0)) in [9, 10]
    except Exception:
        return False


def _build_query_filters(prefix, filters, params):
    where = []
    if filters.get('fecha_desde'):
        where.append(f"{prefix}.fecha >= %s")
        params.append(filters['fecha_desde'])
    if filters.get('fecha_hasta'):
        where.append(f"{prefix}.fecha <= %s")
        params.append(filters['fecha_hasta'])
    if filters.get('estado'):
        where.append(f"{prefix}.estado = %s")
        params.append(filters['estado'])
    return where


def _get_bancos_catalog(db):
    rows = db.execute_query(
        """
        SELECT
            b.id,
            b.nombre_banco,
            b.numero_cuenta,
            b.moneda_codigo,
            b.activo,
            b.unidad_negocio_id,
            un.codigo AS unidad_codigo,
            un.nombre AS unidad_nombre
        FROM contabilidad.cuenta_bancaria b
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = b.unidad_negocio_id
        ORDER BY b.nombre_banco, b.numero_cuenta
        """
    )
    items = []
    for row in rows:
        etiqueta = f"{row['nombre_banco']} · {row['numero_cuenta']} · {row['moneda_codigo']}"
        if row.get('unidad_codigo') and row.get('unidad_nombre'):
            etiqueta = f"{etiqueta} · {row['unidad_codigo']} - {row['unidad_nombre']}"
        items.append({
            'id': row['id'],
            'nombre_banco': row['nombre_banco'],
            'numero_cuenta': row['numero_cuenta'],
            'moneda_codigo': row['moneda_codigo'],
            'activo': bool(row['activo']),
            'unidad_negocio_id': row.get('unidad_negocio_id'),
            'unidad_codigo': row.get('unidad_codigo') or '',
            'unidad_nombre': row.get('unidad_nombre') or '',
            'etiqueta': etiqueta,
        })
    return items


def _get_unidades_catalog(db):
    rows = db.execute_query(
        """
        SELECT id, codigo, nombre, activo
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY codigo, nombre
        """
    )
    return [
        {
            'id': row['id'],
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'activo': bool(row['activo']),
            'etiqueta': f"{row['codigo']} · {row['nombre']}",
        }
        for row in rows
    ]


def _fetch_cobros_banco(db, filters):
    params = []
    where = [
        "c.medio_pago = 'BANCO'",
        "c.cuenta_bancaria_id IS NOT NULL",
    ]
    where.extend(_build_query_filters('c', filters, params))
    if filters.get('banco_id'):
        where.append("c.cuenta_bancaria_id = %s")
        params.append(filters['banco_id'])
    if filters.get('unidad_negocio_id'):
        where.append("c.unidad_negocio_id = %s")
        params.append(filters['unidad_negocio_id'])

    sql = f"""
        SELECT
            c.id,
            c.fecha,
            c.estado,
            'COBRO' AS origen_modulo,
            'INGRESO' AS tipo_operacion,
            c.cuenta_bancaria_id AS banco_id,
            c.unidad_negocio_id,
            b.nombre_banco,
            b.numero_cuenta,
            c.moneda_codigo,
            c.tipo_cambio,
            c.monto_total AS monto,
            c.referencia,
            c.glosa AS glosa,
            c.origen_operacion,
            a.nombre AS tercero_nombre,
            a.nit_ci AS tercero_documento,
            un.codigo AS unidad_codigo,
            un.nombre AS unidad_nombre
        FROM contabilidad.cobro c
        INNER JOIN contabilidad.cuenta_bancaria b ON b.id = c.cuenta_bancaria_id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.cliente_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        WHERE {" AND ".join(where)}
        ORDER BY c.fecha DESC, c.id DESC
    """
    rows = db.execute_query(sql, tuple(params) if params else None)
    items = []
    for row in rows:
        referencia = _clean(row['referencia'])
        items.append({
            'id': row['id'],
            'fecha': row['fecha'],
            'estado': row['estado'],
            'origen_modulo': 'COBRO',
            'origen_detalle': _origen_detalle_label(row.get('origen_operacion')),
            'tipo_operacion': 'INGRESO',
            'banco_id': row['banco_id'],
            'cuenta_bancaria': f"{row['nombre_banco']} · {row['numero_cuenta']}",
            'unidad_negocio_id': row.get('unidad_negocio_id'),
            'unidad_codigo': row.get('unidad_codigo') or '',
            'unidad_nombre': row.get('unidad_nombre') or '',
            'moneda_codigo': row['moneda_codigo'],
            'tipo_cambio': _to_money(row['tipo_cambio'] or 1),
            'monto': _to_money(row['monto']),
            'referencia': referencia,
            'glosa': row['glosa'] or '',
            'tercero_nombre': row['tercero_nombre'] or 'Sin cliente',
            'tercero_documento': row['tercero_documento'] or '',
            'bancarizacion_estado': 'COMPLETA' if referencia else 'OBSERVADA',
            'detalle_url': url_for('tesoreria_cobros.editar', cobro_id=row['id']),
        })
    return items


def _fetch_pagos_banco(db, filters):
    params = []
    where = [
        "p.medio_pago = 'BANCO'",
        "p.cuenta_bancaria_id IS NOT NULL",
    ]
    where.extend(_build_query_filters('p', filters, params))
    if filters.get('banco_id'):
        where.append("p.cuenta_bancaria_id = %s")
        params.append(filters['banco_id'])
    if filters.get('unidad_negocio_id'):
        where.append("p.unidad_negocio_id = %s")
        params.append(filters['unidad_negocio_id'])

    sql = f"""
        SELECT
            p.id,
            p.fecha,
            p.estado,
            'PAGO' AS origen_modulo,
            'EGRESO' AS tipo_operacion,
            p.cuenta_bancaria_id AS banco_id,
            p.unidad_negocio_id,
            b.nombre_banco,
            b.numero_cuenta,
            p.moneda_codigo,
            p.tipo_cambio,
            p.monto_total AS monto,
            p.referencia,
            p.glosa AS glosa,
            p.origen_operacion,
            a.nombre AS tercero_nombre,
            a.nit_ci AS tercero_documento,
            un.codigo AS unidad_codigo,
            un.nombre AS unidad_nombre
        FROM contabilidad.pago p
        INNER JOIN contabilidad.cuenta_bancaria b ON b.id = p.cuenta_bancaria_id
        LEFT JOIN contabilidad.auxiliar a ON a.id = p.proveedor_auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
        WHERE {" AND ".join(where)}
        ORDER BY p.fecha DESC, p.id DESC
    """
    rows = db.execute_query(sql, tuple(params) if params else None)
    items = []
    for row in rows:
        referencia = _clean(row['referencia'])
        items.append({
            'id': row['id'],
            'fecha': row['fecha'],
            'estado': row['estado'],
            'origen_modulo': 'PAGO',
            'origen_detalle': _origen_detalle_label(row.get('origen_operacion')),
            'tipo_operacion': 'EGRESO',
            'banco_id': row['banco_id'],
            'cuenta_bancaria': f"{row['nombre_banco']} · {row['numero_cuenta']}",
            'unidad_negocio_id': row.get('unidad_negocio_id'),
            'unidad_codigo': row.get('unidad_codigo') or '',
            'unidad_nombre': row.get('unidad_nombre') or '',
            'moneda_codigo': row['moneda_codigo'],
            'tipo_cambio': _to_money(row['tipo_cambio'] or 1),
            'monto': _to_money(row['monto']),
            'referencia': referencia,
            'glosa': row['glosa'] or '',
            'tercero_nombre': row['tercero_nombre'] or 'Sin proveedor',
            'tercero_documento': row['tercero_documento'] or '',
            'bancarizacion_estado': 'COMPLETA' if referencia else 'OBSERVADA',
            'detalle_url': url_for('tesoreria_pagos.editar', pago_id=row['id']),
        })
    return items


def _fetch_movimientos_banco(db, filters):
    params_out = []
    where_out = [
        "m.medio_origen = 'BANCO'",
        "m.banco_origen_id IS NOT NULL",
    ]
    where_out.extend(_build_query_filters('m', filters, params_out))
    if filters.get('banco_id'):
        where_out.append("m.banco_origen_id = %s")
        params_out.append(filters['banco_id'])
    if filters.get('unidad_negocio_id'):
        where_out.append("m.unidad_negocio_id = %s")
        params_out.append(filters['unidad_negocio_id'])

    sql_out = f"""
        SELECT
            m.id,
            m.fecha,
            m.estado,
            'TESORERIA' AS origen_modulo,
            CASE
                WHEN m.tipo_movimiento = 'INGRESO' THEN 'EGRESO'
                WHEN m.tipo_movimiento = 'EGRESO' THEN 'EGRESO'
                ELSE 'EGRESO'
            END AS tipo_operacion,
            m.banco_origen_id AS banco_id,
            m.unidad_negocio_id,
            b.nombre_banco,
            b.numero_cuenta,
            m.moneda_codigo,
            m.tipo_cambio,
            m.monto,
            m.referencia,
            m.glosa,
            a.nombre AS tercero_nombre,
            a.nit_ci AS tercero_documento,
            un.codigo AS unidad_codigo,
            un.nombre AS unidad_nombre
        FROM contabilidad.movimiento_tesoreria m
        INNER JOIN contabilidad.cuenta_bancaria b ON b.id = m.banco_origen_id
        LEFT JOIN contabilidad.auxiliar a ON a.id = m.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
        WHERE {" AND ".join(where_out)}
    """

    params_in = []
    where_in = [
        "m.medio_destino = 'BANCO'",
        "m.banco_destino_id IS NOT NULL",
    ]
    where_in.extend(_build_query_filters('m', filters, params_in))
    if filters.get('banco_id'):
        where_in.append("m.banco_destino_id = %s")
        params_in.append(filters['banco_id'])
    if filters.get('unidad_negocio_id'):
        where_in.append("m.unidad_negocio_id = %s")
        params_in.append(filters['unidad_negocio_id'])

    sql_in = f"""
        SELECT
            m.id,
            m.fecha,
            m.estado,
            'TESORERIA' AS origen_modulo,
            'INGRESO' AS tipo_operacion,
            m.banco_destino_id AS banco_id,
            m.unidad_negocio_id,
            b.nombre_banco,
            b.numero_cuenta,
            m.moneda_codigo,
            m.tipo_cambio,
            m.monto,
            m.referencia,
            m.glosa,
            a.nombre AS tercero_nombre,
            a.nit_ci AS tercero_documento,
            un.codigo AS unidad_codigo,
            un.nombre AS unidad_nombre
        FROM contabilidad.movimiento_tesoreria m
        INNER JOIN contabilidad.cuenta_bancaria b ON b.id = m.banco_destino_id
        LEFT JOIN contabilidad.auxiliar a ON a.id = m.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
        WHERE {" AND ".join(where_in)}
    """

    rows = []
    rows.extend(db.execute_query(sql_out, tuple(params_out) if params_out else None))
    rows.extend(db.execute_query(sql_in, tuple(params_in) if params_in else None))

    items = []
    for row in rows:
        referencia = _clean(row['referencia'])
        items.append({
            'id': row['id'],
            'fecha': row['fecha'],
            'estado': row['estado'],
            'origen_modulo': 'TESORERIA',
            'origen_detalle': 'Movimiento bancario',
            'tipo_operacion': row['tipo_operacion'],
            'banco_id': row['banco_id'],
            'cuenta_bancaria': f"{row['nombre_banco']} · {row['numero_cuenta']}",
            'unidad_negocio_id': row.get('unidad_negocio_id'),
            'unidad_codigo': row.get('unidad_codigo') or '',
            'unidad_nombre': row.get('unidad_nombre') or '',
            'moneda_codigo': row['moneda_codigo'],
            'tipo_cambio': _to_money(row['tipo_cambio'] or 1),
            'monto': _to_money(row['monto']),
            'referencia': referencia,
            'glosa': row['glosa'] or '',
            'tercero_nombre': row['tercero_nombre'] or 'Sin auxiliar',
            'tercero_documento': row['tercero_documento'] or '',
            'bancarizacion_estado': 'COMPLETA' if referencia else 'OBSERVADA',
            'detalle_url': url_for('tesoreria_caja_bancos.movimiento_edit', movimiento_id=row['id']),
        })
    return items


def _apply_post_filters(items, filters):
    search = _clean(filters.get('q', '')).lower()
    filtered = []

    for item in items:
        if filters.get('tipo_operacion') and item['tipo_operacion'] != filters['tipo_operacion']:
            continue
        if filters.get('origen_modulo') and item['origen_modulo'] != filters['origen_modulo']:
            continue
        if filters.get('completitud') == 'COMPLETA' and item['bancarizacion_estado'] != 'COMPLETA':
            continue
        if filters.get('completitud') == 'OBSERVADA' and item['bancarizacion_estado'] != 'OBSERVADA':
            continue

        if search:
            haystack = " ".join([
                str(item['id']),
                str(item['fecha']),
                item['origen_modulo'],
                item.get('origen_detalle', ''),
                item['tipo_operacion'],
                item['cuenta_bancaria'],
                item.get('unidad_codigo', ''),
                item.get('unidad_nombre', ''),
                item['moneda_codigo'],
                item['referencia'],
                item['glosa'],
                item['tercero_nombre'],
                item['tercero_documento'],
            ]).lower()
            if search not in haystack:
                continue

        filtered.append(item)

    filtered.sort(key=lambda x: (str(x['fecha']), x['origen_modulo'], x['id']), reverse=True)
    return filtered


def _money_rows(buckets):
    rows = []
    for moneda, amount in sorted(buckets.items(), key=lambda item: item[0]):
        rows.append({
            'moneda': moneda,
            'monto': float(amount.quantize(CUANTIA, rounding=ROUND_HALF_UP)),
        })
    return rows


def _build_summary(items):
    ingresos = {}
    egresos = {}
    observadas = 0

    for item in items:
        moneda = item.get('moneda_codigo') or 'N/D'
        amount = Decimal(str(item['monto'] or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP)
        if item['tipo_operacion'] == 'INGRESO':
            ingresos[moneda] = ingresos.get(moneda, Decimal('0.00')) + amount
        else:
            egresos[moneda] = egresos.get(moneda, Decimal('0.00')) + amount
        if item['bancarizacion_estado'] == 'OBSERVADA':
            observadas += 1

    monedas = set(ingresos) | set(egresos)
    netos = {
        moneda: ingresos.get(moneda, Decimal('0.00')) - egresos.get(moneda, Decimal('0.00'))
        for moneda in monedas
    }

    return {
        'total_operaciones': len(items),
        'ingresos_por_moneda': _money_rows(ingresos),
        'egresos_por_moneda': _money_rows(egresos),
        'neto_por_moneda': _money_rows(netos),
        'observadas': observadas,
    }


def _get_filters():
    estado_arg = request.args.get('estado')
    filters = {
        'fecha_desde': _clean(request.args.get('fecha_desde')),
        'fecha_hasta': _clean(request.args.get('fecha_hasta')),
        'banco_id': _clean(request.args.get('banco_id')),
        'unidad_negocio_id': _clean(request.args.get('unidad_negocio_id')),
        'tipo_operacion': _clean(request.args.get('tipo_operacion')),
        'origen_modulo': _clean(request.args.get('origen_modulo')),
        'estado': 'CONFIRMADO' if estado_arg is None else _clean(estado_arg),
        'completitud': _clean(request.args.get('completitud')),
        'q': _clean(request.args.get('q')),
    }
    if filters['banco_id']:
        try:
            filters['banco_id'] = int(filters['banco_id'])
        except ValueError:
            filters['banco_id'] = None
    else:
        filters['banco_id'] = None

    if filters['unidad_negocio_id']:
        try:
            filters['unidad_negocio_id'] = int(filters['unidad_negocio_id'])
        except ValueError:
            filters['unidad_negocio_id'] = None
    else:
        filters['unidad_negocio_id'] = None
    return filters


# ============================================================
# Rutas
# ============================================================

@tesoreria_bancarizacion_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    filters = _get_filters()

    with DatabaseManager() as db:
        bancos = _get_bancos_catalog(db)
        unidades = _get_unidades_catalog(db)

        items = []
        items.extend(_fetch_cobros_banco(db, filters))
        items.extend(_fetch_pagos_banco(db, filters))
        items.extend(_fetch_movimientos_banco(db, filters))
        items = _apply_post_filters(items, filters)
        summary = _build_summary(items)

    return render_template(
        'bancarizacion_index.html',
        filtros=filters,
        bancos=bancos,
        unidades_negocio=unidades,
        rows=items,
        summary=summary,
        puede_editar=_can_edit(),
    )