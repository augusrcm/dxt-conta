# ============================================================
# DXT CONTA - Reporte Especial: Antigüedad de Saldos por Cobrar
# ============================================================

from flask import Blueprint

antiguedad_saldos_cobrar_bp = Blueprint(
    'antiguedad_saldos_cobrar',
    __name__,
    url_prefix='/reportes-especiales/antiguedad-saldos-cobrar',
    template_folder='templates',
)

from . import routes  # noqa: E402,F401
