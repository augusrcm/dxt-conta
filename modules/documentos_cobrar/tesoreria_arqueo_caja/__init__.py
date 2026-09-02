# ============================================================
# DXT CONTA - Módulo Tesorería Arqueo de Caja
# ============================================================

from flask import Blueprint


tesoreria_arqueo_caja_bp = Blueprint(
    'tesoreria_arqueo_caja',
    __name__,
    url_prefix='/tesoreria/arqueo-caja',
    template_folder='templates',
    static_folder='static'
)

from . import routes
