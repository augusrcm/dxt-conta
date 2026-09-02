from flask import Blueprint

planilla_parametros_bp = Blueprint(
    'planilla_parametros',
    __name__,
    url_prefix='/planillas/parametros',
    template_folder='templates',
)

from . import routes  # noqa: E402,F401
