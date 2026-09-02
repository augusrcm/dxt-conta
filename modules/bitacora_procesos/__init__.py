# ============================================================
# DXT CONTA - Herramientas - Bitacora de Procesos
# ============================================================

from flask import Blueprint

bitacora_procesos_bp = Blueprint(
    'bitacora_procesos',
    __name__,
    url_prefix='/herramientas/bitacora-procesos',
    template_folder='templates',
    static_folder='static',
)

from modules.bitacora_procesos import routes
