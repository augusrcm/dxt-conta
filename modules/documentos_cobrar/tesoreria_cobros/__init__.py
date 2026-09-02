# ============================================================
# DXT CONTA - Módulo Tesorería Cobros
# ============================================================

from flask import Blueprint

tesoreria_cobros_bp = Blueprint(
    'tesoreria_cobros',
    __name__,
    url_prefix='/tesoreria/cobros',
    template_folder='templates',
    static_folder='static'
)

from . import routes
