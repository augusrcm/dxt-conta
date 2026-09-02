from flask import Blueprint

facturas_mantenimiento_bp = Blueprint(
    'facturas_mantenimiento',
    __name__,
    url_prefix='/tesoreria/facturas-mantenimiento',
    template_folder='templates',
    static_folder='static'
)

from . import routes
