# ============================================================
# DXT CONTA - Módulo Tipo de Cambio
# ============================================================

from flask import Blueprint

# Crear blueprint
tipo_cambio_bp = Blueprint(
    'tipo_cambio',
    __name__,
    url_prefix='/tipo-cambio',
    template_folder='templates',
    static_folder='static'
)

# Importar rutas
from modules.tipo_cambio import routes
