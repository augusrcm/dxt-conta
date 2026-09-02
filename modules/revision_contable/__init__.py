# ============================================================
# DXT CONTA - Modulo Revision Contable
# Herramienta de control previo para detectar pendientes e inconsistencias
# ============================================================

from flask import Blueprint

revision_contable_bp = Blueprint(
    'revision_contable',
    __name__,
    url_prefix='/herramientas/revision-contable',
    template_folder='templates',
    static_folder='static',
)

from . import routes  # noqa: E402,F401
