# ============================================================
# DXT CONTA - Módulo Comprobantes
# ============================================================

from flask import Blueprint

comprobantes_bp = Blueprint(
    'comprobantes',
    __name__,
    url_prefix='/contabilidad/comprobantes',
    template_folder='templates',
    static_folder='static'
)

from . import routes
