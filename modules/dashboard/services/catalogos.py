# ============================================================
# DXT CONTA - Dashboard Ejecutivo - Catalogos
# ============================================================

from __future__ import annotations

from modules.dashboard.services.utils import fetch_all


def obtener_unidades_negocio() -> list[dict]:
    sql = """
        SELECT id::text AS id,
               COALESCE(NULLIF(codigo, ''), '') ||
               CASE WHEN COALESCE(NULLIF(codigo, ''), '') <> '' THEN ' · ' ELSE '' END ||
               nombre AS label
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC
    """
    rows = fetch_all(sql)
    return [{'id': '', 'label': 'Todas las unidades'}] + rows
