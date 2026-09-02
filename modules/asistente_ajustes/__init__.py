# ============================================================
# DXT CONTA - Herramientas - Asistente de Ajustes Contables
# ============================================================

from flask import Blueprint

asistente_ajustes_bp = Blueprint(
    'asistente_ajustes',
    __name__,
    url_prefix='/herramientas/asistente-ajustes',
    template_folder='templates',
    static_folder='static',
)

from modules.asistente_ajustes import routes
