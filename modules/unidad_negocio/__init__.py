from flask import Blueprint

unidad_negocio_bp = Blueprint(
    'unidad_negocio',
    __name__,
    url_prefix='/unidad-negocio',
    template_folder='templates'
)

from . import routes
