from flask import Blueprint

rubro_bp = Blueprint(
    'rubro',
    __name__,
    url_prefix='/rubro',
    template_folder='templates'
)

from . import routes
