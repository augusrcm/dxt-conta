# ============================================================
# DXT CONTA - Módulo Balance de Comprobación
# ============================================================

from flask import Blueprint

balance_comprobacion_bp = Blueprint(
    'balance_comprobacion',
    __name__,
    url_prefix='/contabilidad/balance-comprobacion',
    template_folder='templates',
    static_folder='static'
)

from . import routes