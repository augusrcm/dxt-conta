# ============================================================
# DXT CONTA - Reporte Especial: Estado de Resultados por Mes
# ============================================================

from flask import Blueprint

estado_resultados_mes_bp = Blueprint(
    'estado_resultados_mes',
    __name__,
    url_prefix='/reportes-especiales/estado-resultados-mes',
    template_folder='templates',
    static_folder='static',
)

from . import routes  # noqa: E402,F401
