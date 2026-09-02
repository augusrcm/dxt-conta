from flask import Blueprint

caja_bp = Blueprint(
    'caja',
    __name__,
    url_prefix='/caja',
    template_folder='templates'
)

from . import routes