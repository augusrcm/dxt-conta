# ============================================================
# DXT CONTA - Reportes Rápidos - Catálogos comunes
# ============================================================

from database.db_manager import DatabaseManager


def obtener_unidades_negocio():
    sql = """
        SELECT
            id,
            COALESCE(codigo, '') AS codigo,
            nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC, id ASC
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql)
    return [
        {
            'id': row['id'],
            'codigo': row['codigo'] or '',
            'nombre': row['nombre'],
            'label': f"{row['codigo']} · {row['nombre']}" if row['codigo'] else row['nombre'],
        }
        for row in rows
    ]


def unidad_label(unidad_negocio_id):
    if not unidad_negocio_id:
        return 'Todas las unidades'
    sql = """
        SELECT COALESCE(codigo, '') AS codigo, nombre
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (unidad_negocio_id,))
    if not rows:
        return 'Unidad seleccionada'
    row = rows[0]
    return f"{row['codigo']} · {row['nombre']}" if row['codigo'] else row['nombre']
