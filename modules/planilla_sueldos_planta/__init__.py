# ============================================================
# DXT CONTA - Planilla de Sueldos Planta
# ============================================================
from flask import Blueprint

planilla_sueldos_planta_bp = Blueprint(
    'planilla_sueldos_planta',
    __name__,
    url_prefix='/planillas/sueldos-planta',
    template_folder='templates'
)

from . import routes  # noqa: E402,F401
