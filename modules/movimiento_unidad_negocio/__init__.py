# ============================================================
# DXT CONTA - Reporte Especial: Movimiento por Unidad de Negocio
# ============================================================

from flask import Blueprint

movimiento_unidad_negocio_bp = Blueprint(
    'movimiento_unidad_negocio',
    __name__,
    url_prefix='/reportes-especiales/movimiento-unidad-negocio',
    template_folder='templates',
)

from . import routes  # noqa: E402,F401
