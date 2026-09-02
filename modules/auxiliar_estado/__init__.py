# ============================================================
# DXT CONTA - Reporte Especial: Estado de Auxiliares
# ============================================================

from flask import Blueprint

auxiliar_estado_bp = Blueprint(
    'auxiliar_estado',
    __name__,
    url_prefix='/reportes-especiales/auxiliar-estado',
    template_folder='templates',
    static_folder='static',
)

from . import routes  # noqa: E402,F401
