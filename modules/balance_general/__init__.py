# ============================================================
# DXT CONTA - Módulo Balance General
# ============================================================

from flask import Blueprint

balance_general_bp = Blueprint(
    'balance_general',
    __name__,
    url_prefix='/contabilidad/balance-general',
    template_folder='templates',
    static_folder='static'
)

from . import routes