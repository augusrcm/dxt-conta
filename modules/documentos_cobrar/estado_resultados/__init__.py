# ============================================================
# DXT CONTA - Módulo Estado de Resultados
# ============================================================

from flask import Blueprint

estado_resultados_bp = Blueprint(
    'estado_resultados',
    __name__,
    url_prefix='/contabilidad/estado-resultados',
    template_folder='templates',
    static_folder='static'
)

from . import routes