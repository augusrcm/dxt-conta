# ============================================================
# DXT CONTA - Reporte Especial: Estado de Cuentas por Cobrar
# ============================================================

from flask import Blueprint


estado_cuentas_cobrar_bp = Blueprint(
    'estado_cuentas_cobrar',
    __name__,
    url_prefix='/reportes-especiales/estado-cuentas-cobrar',
    template_folder='templates',
)

from . import routes  # noqa: E402,F401
