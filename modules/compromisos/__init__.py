# ============================================================
# DXT CONTA - Módulo Compromisos
# ============================================================

from flask import Blueprint

compromisos_bp = Blueprint(
    'compromisos',
    __name__,
    url_prefix='/compromisos',
    template_folder='templates',
    static_folder='static'
)

from modules.compromisos import routes