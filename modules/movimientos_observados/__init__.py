# ============================================================
# DXT CONTA - Herramientas - Movimientos Observados
# ============================================================

from flask import Blueprint

movimientos_observados_bp = Blueprint(
    'movimientos_observados',
    __name__,
    url_prefix='/herramientas/movimientos-observados',
    template_folder='templates',
    static_folder='static',
)

from modules.movimientos_observados import routes
