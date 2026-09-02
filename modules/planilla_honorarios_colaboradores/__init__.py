# ============================================================
# DXT CONTA - Planilla de Honorarios Colaboradores
# ============================================================
from flask import Blueprint

planilla_honorarios_colaboradores_bp = Blueprint(
    'planilla_honorarios_colaboradores',
    __name__,
    url_prefix='/planillas/honorarios-colaboradores',
    template_folder='templates'
)

from . import routes  # noqa: E402,F401
