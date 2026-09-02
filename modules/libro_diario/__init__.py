# ============================================================
# DXT CONTA - Módulo Libro Diario
# ============================================================

from flask import Blueprint

libro_diario_bp = Blueprint(
    'libro_diario',
    __name__,
    url_prefix='/contabilidad/libro-diario',
    template_folder='templates',
    static_folder='static'
)

from . import routes
