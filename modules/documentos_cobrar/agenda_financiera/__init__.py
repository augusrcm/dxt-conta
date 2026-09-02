from flask import Blueprint

agenda_financiera_bp = Blueprint(
    'agenda_financiera',
    __name__,
    url_prefix='/agenda-financiera',
    template_folder='templates',
    static_folder='static'
)

from modules.agenda_financiera import routes
