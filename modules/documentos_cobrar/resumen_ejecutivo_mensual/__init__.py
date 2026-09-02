# ============================================================
# DXT CONTA - Reporte Especial: Resumen Ejecutivo Mensual
# ============================================================

from flask import Blueprint

resumen_ejecutivo_mensual_bp = Blueprint(
    'resumen_ejecutivo_mensual',
    __name__,
    url_prefix='/reportes-especiales/resumen-ejecutivo-mensual',
    template_folder='templates',
)

from . import routes  # noqa: E402,F401
