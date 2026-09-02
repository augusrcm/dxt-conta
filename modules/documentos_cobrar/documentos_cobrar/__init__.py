# ============================================================
# DXT CONTA - Documentos por Cobrar
# ============================================================

from flask import Blueprint


documentos_cobrar_bp = Blueprint(
    'documentos_cobrar',
    __name__,
    url_prefix='/cuentas-por-cobrar/documentos',
    template_folder='templates',
)

from . import routes  # noqa: E402,F401
