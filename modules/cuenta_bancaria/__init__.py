from flask import Blueprint

cuenta_bancaria_bp = Blueprint(
    'cuenta_bancaria',
    __name__,
    url_prefix='/cuenta-bancaria',
    template_folder='templates'
)

from . import routes