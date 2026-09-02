from flask import Blueprint

planilla_conceptos_bp = Blueprint(
    'planilla_conceptos',
    __name__,
    url_prefix='/planillas/conceptos',
    template_folder='templates'
)

from . import routes  # noqa: E402,F401
