# ============================================================
# DXT CONTA - Módulo Plan de Cuentas
# ============================================================

from flask import Blueprint

# Crear blueprint
plandecuentas_bp = Blueprint(
    'plandecuentas',
    __name__,
    url_prefix='/plandecuentas',
    template_folder='templates',
    static_folder='static'
)

# Importar rutas
from modules.plandecuentas import routes
