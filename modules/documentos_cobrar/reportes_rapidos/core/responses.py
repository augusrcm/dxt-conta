# ============================================================
# DXT CONTA - Reportes Rápidos - Respuestas JSON
# ============================================================

from flask import jsonify


def json_ok(**kwargs):
    payload = {'success': True}
    payload.update(kwargs)
    return jsonify(payload)


def json_error(message, status=400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(payload), status
