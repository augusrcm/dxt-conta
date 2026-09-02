# ============================================================
# DXT CONTA - Dashboard Ejecutivo - Graficos
# ============================================================

from __future__ import annotations

from datetime import timedelta

from modules.dashboard.services.config import MONEDA_BASE, MAX_TOP_ITEMS
from modules.dashboard.services.utils import decimal_value, fetch_all, fetch_one, format_money


def _daily_range(filters: dict) -> tuple:
    return filters['fecha_desde'], filters['fecha_hasta']


def flujo_diario(filters: dict) -> dict:
    fecha_desde, fecha_hasta = _daily_range(filters)
    sql = """
        WITH cobros AS (
            SELECT COALESCE(SUM(monto_total), 0)::numeric(18,2) AS total
            FROM contabilidad.cobro
            WHERE estado = 'CONFIRMADO'
              AND moneda_codigo = %s
              AND fecha BETWEEN %s AND %s
              AND (%s IS NULL OR unidad_negocio_id = %s)
        ), pagos AS (
            SELECT COALESCE(SUM(monto_total), 0)::numeric(18,2) AS total
            FROM contabilidad.pago
            WHERE estado = 'CONFIRMADO'
              AND moneda_codigo = %s
              AND fecha BETWEEN %s AND %s
              AND (%s IS NULL OR unidad_negocio_id = %s)
        )
        SELECT c.total AS cobros,
               p.total AS pagos,
               (c.total - p.total)::numeric(18,2) AS neto
        FROM cobros c
        CROSS JOIN pagos p
    """
    params = (
        MONEDA_BASE, fecha_desde, fecha_hasta, filters['unidad_negocio_id'], filters['unidad_negocio_id'],
        MONEDA_BASE, fecha_desde, fecha_hasta, filters['unidad_negocio_id'], filters['unidad_negocio_id'],
    )
    row = fetch_one(sql, params)
    cobros = decimal_value(row.get('cobros'))
    pagos = decimal_value(row.get('pagos'))
    neto = decimal_value(row.get('neto'))
    return {
        'id': 'cobros_pagos_periodo',
        'titulo': 'Cobros y pagos del período',
        'subtitulo': 'Total confirmado en Bs según los filtros aplicados',
        'tipo': 'donut_balance',
        'data': [
            {
                'tipo': 'cobros',
                'label': 'Cobros',
                'total': float(cobros),
                'total_label': f"Bs {format_money(cobros)}",
            },
            {
                'tipo': 'pagos',
                'label': 'Pagos',
                'total': float(pagos),
                'total_label': f"Bs {format_money(pagos)}",
            },
        ],
        'resumen': {
            'cobros': float(cobros),
            'pagos': float(pagos),
            'neto': float(neto),
            'cobros_label': f"Bs {format_money(cobros)}",
            'pagos_label': f"Bs {format_money(pagos)}",
            'neto_label': f"Bs {format_money(neto)}",
        },
    }


def cuentas_vencidas(filters: dict) -> dict:
    sql = """
        SELECT c.tipo::text AS tipo,
               COUNT(*)::int AS cantidad,
               COALESCE(SUM(GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)), 0)::numeric(18,2) AS total
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        WHERE c.activo = TRUE
          AND c.tipo IN ('PAGAR', 'COBRAR')
          AND d.estado = 'PENDIENTE'
          AND d.fecha_vencimiento < %s
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
        GROUP BY c.tipo
    """
    rows = fetch_all(sql, (filters['fecha_corte'], filters['unidad_negocio_id'], filters['unidad_negocio_id']))
    by_type = {row['tipo']: row for row in rows}
    data = []
    for key, label in [('COBRAR', 'Cobros vencidos'), ('PAGAR', 'Pagos vencidos')]:
        row = by_type.get(key, {})
        data.append({
            'label': label,
            'cantidad': int(row.get('cantidad') or 0),
            'total': float(decimal_value(row.get('total'))),
            'total_label': format_money(row.get('total')),
        })
    return {
        'id': 'cuentas_vencidas',
        'titulo': 'Cuentas vencidas',
        'subtitulo': 'Compromisos pendientes anteriores a la fecha de corte',
        'tipo': 'donut_simple',
        'data': data,
    }


def top_clientes(filters: dict) -> dict:
    sql = """
        SELECT COALESCE(a.nombre, c.nombre, 'Sin cliente')::text AS cliente,
               COUNT(*)::int AS cantidad,
               COALESCE(SUM(GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)), 0)::numeric(18,2) AS total
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        WHERE c.activo = TRUE
          AND c.tipo = 'COBRAR'
          AND d.estado = 'PENDIENTE'
          AND d.fecha_vencimiento <= %s
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
        GROUP BY COALESCE(a.nombre, c.nombre, 'Sin cliente')
        ORDER BY total DESC, cliente ASC
        LIMIT %s
    """
    rows = fetch_all(sql, (filters['fecha_corte'], filters['unidad_negocio_id'], filters['unidad_negocio_id'], MAX_TOP_ITEMS))
    data = []
    for row in rows:
        data.append({
            'label': row.get('cliente') or 'Sin cliente',
            'cantidad': int(row.get('cantidad') or 0),
            'total': float(decimal_value(row.get('total'))),
            'total_label': format_money(row.get('total')),
        })
    return {
        'id': 'top_clientes',
        'titulo': 'Top clientes con saldo pendiente',
        'subtitulo': 'Concentración de cobranza pendiente hasta la fecha de corte',
        'tipo': 'bar_horizontal',
        'data': data,
    }


def vencimientos_publicidad(filters: dict) -> dict:
    corte = filters['fecha_corte']
    proximo = corte + timedelta(days=30)
    sql = """
        SELECT 'Licencias vencidas'::text AS label, COUNT(*)::int AS cantidad
        FROM publicidad.licencia_publicidad l
        INNER JOIN publicidad.elemento_publicitario e ON e.id = l.elemento_id
        LEFT JOIN publicidad.estructura_publicitaria ep ON ep.id = e.estructura_id
        WHERE l.estado = 'HABILITADO'
          AND e.estado = 'ACTIVA'
          AND l.fecha_fin < %s
          AND (%s IS NULL OR ep.unidad_negocio_id = %s)
        UNION ALL
        SELECT 'Licencias por vencer'::text AS label, COUNT(*)::int AS cantidad
        FROM publicidad.licencia_publicidad l
        INNER JOIN publicidad.elemento_publicitario e ON e.id = l.elemento_id
        LEFT JOIN publicidad.estructura_publicitaria ep ON ep.id = e.estructura_id
        WHERE l.estado = 'HABILITADO'
          AND e.estado = 'ACTIVA'
          AND l.fecha_fin BETWEEN %s AND %s
          AND (%s IS NULL OR ep.unidad_negocio_id = %s)
        UNION ALL
        SELECT 'Contratos vencidos'::text AS label, COUNT(*)::int AS cantidad
        FROM publicidad.contrato c
        INNER JOIN publicidad.contrato_detalle d ON d.contrato_id = c.id
        WHERE c.estado = 'HABILITADO'
          AND d.estado = 'HABILITADO'
          AND d.fecha_hasta < %s
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
        UNION ALL
        SELECT 'Contratos por vencer'::text AS label, COUNT(*)::int AS cantidad
        FROM publicidad.contrato c
        INNER JOIN publicidad.contrato_detalle d ON d.contrato_id = c.id
        WHERE c.estado = 'HABILITADO'
          AND d.estado = 'HABILITADO'
          AND d.fecha_hasta BETWEEN %s AND %s
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
    """
    params = (
        corte, filters['unidad_negocio_id'], filters['unidad_negocio_id'],
        corte, proximo, filters['unidad_negocio_id'], filters['unidad_negocio_id'],
        corte, filters['unidad_negocio_id'], filters['unidad_negocio_id'],
        corte, proximo, filters['unidad_negocio_id'], filters['unidad_negocio_id'],
    )
    rows = fetch_all(sql, params)
    return {
        'id': 'vencimientos_publicidad',
        'titulo': 'Vencimientos de publicidad',
        'subtitulo': 'Licencias y contratos que requieren seguimiento',
        'tipo': 'priority_list',
        'data': [{'label': row.get('label'), 'cantidad': int(row.get('cantidad') or 0)} for row in rows],
    }


def build_charts(filters: dict) -> list[dict]:
    return [
        flujo_diario(filters),
        cuentas_vencidas(filters),
        top_clientes(filters),
        vencimientos_publicidad(filters),
    ]
