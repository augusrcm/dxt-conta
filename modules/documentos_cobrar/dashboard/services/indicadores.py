# ============================================================
# DXT CONTA - Dashboard Ejecutivo - Indicadores principales
# ============================================================

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from modules.dashboard.services.utils import decimal_value, fetch_one, format_money, report_detail_url


def _commitment_amount(tipo: str, operator: str, filters: dict) -> dict:
    if operator not in {'=', '<'}:
        raise ValueError('Operador interno no válido.')

    sql = f"""
        SELECT
            COUNT(*)::int AS cantidad,
            COALESCE(SUM(GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)), 0)::numeric(18,2) AS total
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        WHERE c.activo = TRUE
          AND c.tipo = %s
          AND d.estado = 'PENDIENTE'
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
          AND d.fecha_vencimiento {operator} %s
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
    """
    row = fetch_one(sql, (tipo, filters['fecha_corte'], filters['unidad_negocio_id'], filters['unidad_negocio_id']))
    return {'cantidad': int(row.get('cantidad') or 0), 'total': decimal_value(row.get('total'))}


def _licencias_por_vencer(filters: dict) -> int:
    fecha_hasta = filters['fecha_corte'] + timedelta(days=30)
    sql = """
        SELECT COUNT(*)::int AS cantidad
        FROM publicidad.licencia_publicidad l
        INNER JOIN publicidad.elemento_publicitario e ON e.id = l.elemento_id
        WHERE l.estado = 'HABILITADO'
          AND e.estado = 'ACTIVA'
          AND l.fecha_fin BETWEEN %s AND %s
          AND (%s IS NULL OR EXISTS (
              SELECT 1
              FROM publicidad.estructura_publicitaria ep
              WHERE ep.id = e.estructura_id
                AND ep.unidad_negocio_id = %s
          ))
    """
    row = fetch_one(sql, (filters['fecha_corte'], fecha_hasta, filters['unidad_negocio_id'], filters['unidad_negocio_id']))
    return int(row.get('cantidad') or 0)


def _contratos_por_vencer(filters: dict) -> int:
    fecha_hasta = filters['fecha_corte'] + timedelta(days=30)
    sql = """
        SELECT COUNT(*)::int AS cantidad
        FROM publicidad.contrato c
        INNER JOIN publicidad.contrato_detalle d ON d.contrato_id = c.id
        WHERE c.estado = 'HABILITADO'
          AND d.estado = 'HABILITADO'
          AND d.fecha_hasta BETWEEN %s AND %s
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
    """
    row = fetch_one(sql, (filters['fecha_corte'], fecha_hasta, filters['unidad_negocio_id'], filters['unidad_negocio_id']))
    return int(row.get('cantidad') or 0)


def _alertas_criticas(filters: dict) -> int:
    sql = """
        SELECT
            (
                SELECT COUNT(*)
                FROM contabilidad.arqueo_caja a
                WHERE COALESCE(a.diferencia, 0) <> 0
                  AND a.estado <> 'ANULADO'
            ) + (
                SELECT COUNT(*)
                FROM contabilidad.gestion_bloqueo_critico b
                WHERE b.estado = 'EN_PROCESO'
            ) + (
                SELECT COUNT(*)
                FROM contabilidad.pago p
                WHERE p.estado = 'BORRADOR'
                  AND p.fecha <= %s
                  AND (%s IS NULL OR p.unidad_negocio_id = %s)
            ) + (
                SELECT COUNT(*)
                FROM contabilidad.cobro c
                WHERE c.estado = 'BORRADOR'
                  AND c.fecha <= %s
                  AND (%s IS NULL OR c.unidad_negocio_id = %s)
            ) AS cantidad
    """
    params = (
        filters['fecha_corte'], filters['unidad_negocio_id'], filters['unidad_negocio_id'],
        filters['fecha_corte'], filters['unidad_negocio_id'], filters['unidad_negocio_id'],
    )
    row = fetch_one(sql, params)
    return int(row.get('cantidad') or 0)


def build_cards(filters: dict) -> list[dict]:
    cobrar_hoy = _commitment_amount('COBRAR', '=', filters)
    pagar_hoy = _commitment_amount('PAGAR', '=', filters)
    cobros_vencidos = _commitment_amount('COBRAR', '<', filters)
    pagos_vencidos = _commitment_amount('PAGAR', '<', filters)

    saldo_neto = cobrar_hoy['total'] - pagar_hoy['total']
    saldo_kind = 'success' if saldo_neto >= Decimal('0.00') else 'danger'

    cards = [
        {
            'id': 'por_cobrar_hoy',
            'titulo': 'Por cobrar hoy',
            'valor': format_money(cobrar_hoy['total']),
            'detalle': f"{cobrar_hoy['cantidad']} compromiso(s) · Ver detalle",
            'icono': 'fas fa-arrow-trend-up',
            'tipo': 'success',
            'detalle_url': report_detail_url('cuentas_por_cobrar_pendientes', filters, alcance='hoy'),
        },
        {
            'id': 'por_pagar_hoy',
            'titulo': 'Por pagar hoy',
            'valor': format_money(pagar_hoy['total']),
            'detalle': f"{pagar_hoy['cantidad']} compromiso(s) · Ver detalle",
            'icono': 'fas fa-arrow-trend-down',
            'tipo': 'warning',
            'detalle_url': report_detail_url('cuentas_por_pagar_pendientes', filters, alcance='hoy'),
        },
        {
            'id': 'saldo_neto',
            'titulo': 'Saldo neto del día',
            'valor': format_money(saldo_neto),
            'detalle': 'Cobros menos pagos · Ver agenda',
            'icono': 'fas fa-scale-balanced',
            'tipo': saldo_kind,
            'detalle_url': report_detail_url('agenda_financiera_hoy', filters, alcance='hoy'),
        },
        {
            'id': 'cobros_vencidos',
            'titulo': 'Cobros vencidos',
            'valor': format_money(cobros_vencidos['total']),
            'detalle': f"{cobros_vencidos['cantidad']} pendiente(s) · Ver detalle",
            'icono': 'fas fa-clock-rotate-left',
            'tipo': 'danger' if cobros_vencidos['cantidad'] else 'neutral',
            'detalle_url': report_detail_url('cuentas_por_cobrar_pendientes', filters, alcance='vencidas'),
        },
        {
            'id': 'pagos_vencidos',
            'titulo': 'Pagos vencidos',
            'valor': format_money(pagos_vencidos['total']),
            'detalle': f"{pagos_vencidos['cantidad']} pendiente(s) · Ver detalle",
            'icono': 'fas fa-triangle-exclamation',
            'tipo': 'danger' if pagos_vencidos['cantidad'] else 'neutral',
            'detalle_url': report_detail_url('cuentas_por_pagar_pendientes', filters, alcance='vencidas'),
        },
        {
            'id': 'alertas_criticas',
            'titulo': 'Alertas críticas',
            'valor': _alertas_criticas(filters),
            'detalle': 'Requieren revisión · Ver alertas',
            'icono': 'fas fa-bell',
            'tipo': 'danger',
            'detalle_url': report_detail_url('atencion_inmediata', filters, alcance='hoy'),
        },
        {
            'id': 'licencias_por_vencer',
            'titulo': 'Licencias por vencer',
            'valor': _licencias_por_vencer(filters),
            'detalle': 'Próximos 30 días · Ver detalle',
            'icono': 'fas fa-id-card',
            'tipo': 'warning',
            'detalle_url': report_detail_url('publicidad_licencias_por_vencer', filters, alcance='proximos_30', grupo='todos'),
        },
        {
            'id': 'contratos_por_vencer',
            'titulo': 'Contratos por vencer',
            'valor': _contratos_por_vencer(filters),
            'detalle': 'Próximos 30 días · Ver detalle',
            'icono': 'fas fa-file-signature',
            'tipo': 'info',
            'detalle_url': report_detail_url('publicidad_contratos_por_vencer', filters, alcance='proximos_30', grupo='pendientes'),
        },
    ]
    return cards
