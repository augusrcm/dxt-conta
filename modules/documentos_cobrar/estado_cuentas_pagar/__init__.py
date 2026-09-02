# ============================================================
# DXT CONTA - Reporte Especial
# Estado de Cuentas por Pagar
# ============================================================

from flask import Blueprint

estado_cuentas_pagar_bp = Blueprint(
    'estado_cuentas_pagar',
    __name__,
    url_prefix='/reportes-especiales/estado-cuentas-pagar',
    template_folder='templates',
)

from modules.estado_cuentas_pagar import routes  # noqa: E402,F401
