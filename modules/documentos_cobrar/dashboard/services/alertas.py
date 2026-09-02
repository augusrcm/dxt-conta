# ============================================================
# DXT CONTA - Dashboard Ejecutivo - Atencion prioritaria
# ============================================================

from __future__ import annotations

from datetime import date

from modules.dashboard.services.config import MAX_ALERTAS
from modules.dashboard.services.utils import date_label, decimal_value, fetch_all, format_money, report_detail_url


def _detalle_url_por_tipo(tipo: str, filters: dict, fecha_evento=None) -> str:
    tipo_normalizado = (tipo or '').strip().lower()
    fecha_base = fecha_evento if isinstance(fecha_evento, date) else filters.get('fecha_corte')
    if tipo_normalizado == 'pago vencido':
        return report_detail_url('cuentas_por_pagar_pendientes', filters, alcance='vencidas', fecha_base=filters.get('fecha_corte'))
    if tipo_normalizado == 'cobro vencido':
        return report_detail_url('cuentas_por_cobrar_pendientes', filters, alcance='vencidas', fecha_base=filters.get('fecha_corte'))
    if tipo_normalizado == 'licencia vencida':
        return report_detail_url('publicidad_licencias_vencidas', filters, alcance='vencidas_a_fecha', grupo='todas', fecha_base=filters.get('fecha_corte'))
    if tipo_normalizado == 'contrato por vencer':
        return report_detail_url('publicidad_contratos_por_vencer', filters, alcance='proximos_30', grupo='pendientes', fecha_base=filters.get('fecha_corte'))
    if tipo_normalizado in {'arqueo con diferencia', 'proceso crítico activo'}:
        return report_detail_url('atencion_inmediata', filters, alcance='hoy', grupo='control', fecha_base=filters.get('fecha_corte'))
    return report_detail_url('atencion_inmediata', filters, alcance='hoy', fecha_base=fecha_base)


def build_alertas(filters: dict) -> list[dict]:
    sql = """
        SELECT *
        FROM (
            SELECT
                'CRITICA'::text AS prioridad,
                1::int AS orden,
                d.fecha_vencimiento::date AS fecha,
                'Pago vencido'::text AS tipo,
                COALESCE(a.nombre, c.nombre, 'Sin proveedor')::text AS descripcion,
                GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)::numeric(18,2) AS monto,
                'Revisar y programar pago.'::text AS accion
            FROM contabilidad.compromiso c
            INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
            LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
            WHERE c.activo = TRUE
              AND c.tipo = 'PAGAR'
              AND d.estado = 'PENDIENTE'
              AND d.fecha_vencimiento < %s
              AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
              AND (%s IS NULL OR c.unidad_negocio_id = %s)

            UNION ALL

            SELECT
                'ALTA'::text AS prioridad,
                2::int AS orden,
                d.fecha_vencimiento::date AS fecha,
                'Cobro vencido'::text AS tipo,
                COALESCE(a.nombre, c.nombre, 'Sin cliente')::text AS descripcion,
                GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)::numeric(18,2) AS monto,
                'Gestionar cobranza.'::text AS accion
            FROM contabilidad.compromiso c
            INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
            LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
            WHERE c.activo = TRUE
              AND c.tipo = 'COBRAR'
              AND d.estado = 'PENDIENTE'
              AND d.fecha_vencimiento < %s
              AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
              AND (%s IS NULL OR c.unidad_negocio_id = %s)

            UNION ALL

            SELECT
                'CRITICA'::text AS prioridad,
                1::int AS orden,
                l.fecha_fin::date AS fecha,
                'Licencia vencida'::text AS tipo,
                COALESCE(e.codigo || ' · ' || e.nombre, e.codigo, 'Elemento publicitario')::text AS descripcion,
                0::numeric(18,2) AS monto,
                'Regularizar licencia.'::text AS accion
            FROM publicidad.licencia_publicidad l
            INNER JOIN publicidad.elemento_publicitario e ON e.id = l.elemento_id
            LEFT JOIN publicidad.estructura_publicitaria ep ON ep.id = e.estructura_id
            WHERE l.estado = 'HABILITADO'
              AND e.estado = 'ACTIVA'
              AND l.fecha_fin < %s
              AND (%s IS NULL OR ep.unidad_negocio_id = %s)

            UNION ALL

            SELECT
                'ALTA'::text AS prioridad,
                2::int AS orden,
                d.fecha_hasta::date AS fecha,
                'Contrato por vencer'::text AS tipo,
                COALESCE(c.contrato_id || ' · ' || c.empresa_nombre, c.empresa_nombre, 'Contrato publicitario')::text AS descripcion,
                0::numeric(18,2) AS monto,
                'Coordinar renovación o cierre.'::text AS accion
            FROM publicidad.contrato c
            INNER JOIN publicidad.contrato_detalle d ON d.contrato_id = c.id
            WHERE c.estado = 'HABILITADO'
              AND d.estado = 'HABILITADO'
              AND d.fecha_hasta BETWEEN %s AND (%s::date + interval '30 day')::date
              AND (%s IS NULL OR c.unidad_negocio_id = %s)

            UNION ALL

            SELECT
                'CRITICA'::text AS prioridad,
                1::int AS orden,
                a.fecha_arqueo::date AS fecha,
                'Arqueo con diferencia'::text AS tipo,
                COALESCE('Caja ID ' || a.caja_id::text, 'Caja')::text AS descripcion,
                ABS(COALESCE(a.diferencia, 0))::numeric(18,2) AS monto,
                'Revisar diferencia de caja.'::text AS accion
            FROM contabilidad.arqueo_caja a
            WHERE COALESCE(a.diferencia, 0) <> 0
              AND a.estado <> 'ANULADO'

            UNION ALL

            SELECT
                'CRITICA'::text AS prioridad,
                1::int AS orden,
                b.fecha_hora_inicio::date AS fecha,
                'Proceso crítico activo'::text AS tipo,
                COALESCE(b.tipo_proceso::text || ' gestión ' || b.gestion_origen::text, 'Proceso crítico')::text AS descripcion,
                0::numeric(18,2) AS monto,
                'Verificar si el proceso sigue en ejecución.'::text AS accion
            FROM contabilidad.gestion_bloqueo_critico b
            WHERE b.estado = 'EN_PROCESO'
        ) base
        ORDER BY orden ASC, fecha ASC, monto DESC, tipo ASC
        LIMIT %s
    """
    corte = filters['fecha_corte']
    unidad = filters['unidad_negocio_id']
    params = (
        corte, unidad, unidad,
        corte, unidad, unidad,
        corte, unidad, unidad,
        corte, corte, unidad, unidad,
        MAX_ALERTAS,
    )
    rows = fetch_all(sql, params)
    mapped = []
    for row in rows:
        monto = decimal_value(row.get('monto'))
        tipo = row.get('tipo') or ''
        detalle_url = _detalle_url_por_tipo(tipo, filters, row.get('fecha'))
        mapped.append({
            'prioridad': row.get('prioridad') or 'MEDIA',
            'fecha': row.get('fecha').isoformat() if isinstance(row.get('fecha'), date) else '',
            'fecha_label': date_label(row.get('fecha')),
            'tipo': tipo,
            'descripcion': row.get('descripcion') or '',
            'monto': float(monto),
            'monto_label': format_money(monto) if monto else '',
            'accion': row.get('accion') or '',
            'detalle_url': detalle_url,
        })
    return mapped
