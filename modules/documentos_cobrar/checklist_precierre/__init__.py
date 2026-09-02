# ============================================================
# DXT CONTA - Modulo Checklist Pre-Cierre
# Herramienta de verificacion previa al cierre de gestion
# ============================================================

from flask import Blueprint

checklist_precierre_bp = Blueprint(
    'checklist_precierre',
    __name__,
    url_prefix='/herramientas/checklist-pre-cierre',
    template_folder='templates',
    static_folder='static',
)

from . import routes  # noqa: E402,F401
