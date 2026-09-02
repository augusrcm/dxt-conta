# ============================================================
# DXT CONTA - Módulo Tesorería Pagos
# ============================================================

from flask import Blueprint

tesoreria_pagos_bp = Blueprint(
    'tesoreria_pagos',
    __name__,
    url_prefix='/tesoreria/pagos',
    template_folder='templates',
    static_folder='static'
)

from . import routes
from modules.monedas import routes
