# ============================================================
# DXT CONTA - Modulo Saldos Iniciales
# ============================================================

from flask import Blueprint

saldos_iniciales_bp = Blueprint(
    'saldos_iniciales',
    __name__,
    url_prefix='/contabilidad/saldos-iniciales',
    template_folder='templates',
    static_folder='static'
)

from . import routes
