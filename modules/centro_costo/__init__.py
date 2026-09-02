# ============================================================
# DXT CONTA - Módulo Centro de Costo
# ============================================================

from flask import Blueprint

centro_costo_bp = Blueprint(
    'centro_costo',
    __name__,
    url_prefix='/centro-costo',
    template_folder='templates'
)

from . import routes