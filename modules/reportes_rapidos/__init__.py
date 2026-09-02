# ============================================================
# DXT CONTA - Módulo Reportes Rápidos
# ============================================================

from flask import Blueprint

reportes_rapidos_bp = Blueprint(
    'reportes_rapidos',
    __name__,
    url_prefix='/contabilidad/reportes-rapidos',
    template_folder='templates',
    static_folder='static',
)

from . import routes  # noqa: E402,F401
