# ============================================================
# DXT CONTA - Herramientas - Conciliacion Caja/Banco
# ============================================================

from flask import Blueprint

conciliacion_caja_banco_bp = Blueprint(
    'conciliacion_caja_banco',
    __name__,
    url_prefix='/herramientas/conciliacion-caja-banco',
    template_folder='templates',
    static_folder='static',
)

from modules.conciliacion_caja_banco import routes
