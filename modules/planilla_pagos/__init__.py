# ============================================================
# DXT CONTA - Módulo Pago de Planillas
# ============================================================

from flask import Blueprint

planilla_pagos_bp = Blueprint(
    'planilla_pagos',
    __name__,
    url_prefix='/planillas/pagos',
    template_folder='templates',
    static_folder='static'
)

from . import routes
