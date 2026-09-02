from flask import Blueprint

facturas_electronicas_bp = Blueprint(
    'facturas_electronicas',
    __name__,
    url_prefix='/tesoreria/facturas-electronicas',
    template_folder='templates',
    static_folder='static'
)

from . import routes
