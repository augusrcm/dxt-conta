from flask import Blueprint

tesoreria_bancarizacion_bp = Blueprint(
    'tesoreria_bancarizacion',
    __name__,
    url_prefix='/tesoreria/bancarizacion',
    template_folder='templates',
    static_folder='static'
)

from . import routes