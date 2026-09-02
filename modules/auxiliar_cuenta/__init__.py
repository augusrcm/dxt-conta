from flask import Blueprint

auxiliar_cuenta_bp = Blueprint(
    'auxiliar_cuenta',
    __name__,
    url_prefix='/auxiliar-cuenta',
    template_folder='templates'
)

from . import routes