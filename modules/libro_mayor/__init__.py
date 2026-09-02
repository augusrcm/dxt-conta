# ============================================================
# DXT CONTA - Módulo Libro Mayor
# ============================================================

from flask import Blueprint

libro_mayor_bp = Blueprint(
    'libro_mayor',
    __name__,
    url_prefix='/contabilidad/libro-mayor',
    template_folder='templates',
    static_folder='static'
)

from . import routes