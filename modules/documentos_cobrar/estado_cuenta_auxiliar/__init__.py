# ============================================================
# DXT CONTA - Herramientas - Estado de Cuenta de Auxiliar
# ============================================================

from flask import Blueprint

estado_cuenta_auxiliar_bp = Blueprint(
    'estado_cuenta_auxiliar',
    __name__,
    url_prefix='/herramientas/estado-cuenta-auxiliar',
    template_folder='templates',
)

from . import routes
