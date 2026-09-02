# ============================================================
# DXT CONTA - Módulo Cierre y Apertura de Gestión
# ============================================================

from flask import Blueprint

cierre_gestion_bp = Blueprint(
    'cierre_gestion',
    __name__,
    url_prefix='/contabilidad/cierre-gestion',
    template_folder='templates',
    static_folder='static'
)

from . import routes