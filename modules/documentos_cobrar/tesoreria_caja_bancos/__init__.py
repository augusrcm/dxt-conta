# ============================================================
# DXT CONTA - Módulo Tesorería Caja y Bancos
# ============================================================

from flask import Blueprint


tesoreria_caja_bancos_bp = Blueprint(
    'tesoreria_caja_bancos',
    __name__,
    url_prefix='/tesoreria/caja-bancos',
    template_folder='templates',
    static_folder='static'
)

from . import routes
