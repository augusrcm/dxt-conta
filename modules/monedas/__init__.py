# ============================================================
# DXT CONTA - Módulo Monedas
# ============================================================

from flask import Blueprint

monedas_bp = Blueprint(
    'monedas',
    __name__,
    url_prefix='/monedas',
    template_folder='templates'
)

from . import routes

