# ============================================================
# DXT CONTA - Reporte Especial: Cartera documental por auxiliar
# ============================================================

from flask import Blueprint

facturas_auxiliar_bp = Blueprint(
    'facturas_auxiliar',
    __name__,
    url_prefix='/reportes-especiales/facturas-auxiliar',
    template_folder='templates',
    static_folder='static',
)

from . import routes  # noqa: E402,F401
