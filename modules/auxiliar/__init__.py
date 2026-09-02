from flask import Blueprint

auxiliar_bp = Blueprint(
    'auxiliar',
    __name__,
    url_prefix='/auxiliares',
    template_folder='templates'
)

from . import routes