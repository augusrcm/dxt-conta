# ============================================================
# DXT CONTA - Reporte Especial: Estado de Caja y Bancos
# ============================================================

from flask import Blueprint


caja_bancos_estado_bp = Blueprint(
    'caja_bancos_estado',
    __name__,
    url_prefix='/reportes-especiales/caja-bancos-estado',
    template_folder='templates',
)

from . import routes
