# ============================================================
# DXT CONTA - Saldos Iniciales por Cobrar
# ============================================================

from flask import Blueprint


saldos_iniciales_cobrar_bp = Blueprint(
    'saldos_iniciales_cobrar',
    __name__,
    url_prefix='/cuentas-por-cobrar/saldos-iniciales',
    template_folder='templates',
)

from . import routes  # noqa: E402,F401
