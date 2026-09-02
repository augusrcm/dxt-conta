from flask import Blueprint

planilla_personas_bp = Blueprint(
    'planilla_personas',
    __name__,
    url_prefix='/planillas/personas',
    template_folder='templates'
)

from . import routes
