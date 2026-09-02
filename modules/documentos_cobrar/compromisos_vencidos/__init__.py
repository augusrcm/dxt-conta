# ============================================================
# DXT CONTA - Herramientas - Compromisos Vencidos
# ============================================================

from flask import Blueprint

compromisos_vencidos_bp = Blueprint(
    'compromisos_vencidos',
    __name__,
    url_prefix='/herramientas/compromisos-vencidos',
    template_folder='templates',
    static_folder='static',
)

from modules.compromisos_vencidos import routes
