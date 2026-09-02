from flask import Blueprint

planilla_prestamos_bp = Blueprint(
    'planilla_prestamos',
    __name__,
    url_prefix='/planillas/prestamos',
    template_folder='templates'
)

from . import routes  # noqa: E402,F401
