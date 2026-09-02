# ============================================================
# DXT-CONTA - Decoradores de Seguridad
# ============================================================

from functools import wraps
from flask import flash, redirect, session, url_for


def login_required(f):
    """
    Decorador que verifica si el usuario está autenticado.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debe iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def roles_required(roles):
    """
    Decorador que verifica si el usuario tiene uno de los roles permitidos.
    """
    roles_permitidos = {int(r) for r in roles}

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Debe iniciar sesión para acceder a esta página.', 'warning')
                return redirect(url_for('auth.login'))

            rol_id = session.get('rol_id')

            if rol_id is None:
                flash('Acceso denegado.', 'danger')
                return redirect(url_for('dashboard.index'))

            try:
                rol_id = int(rol_id)
            except (TypeError, ValueError):
                flash('Rol de usuario inválido.', 'danger')
                return redirect(url_for('dashboard.index'))

            if rol_id not in roles_permitidos:
                flash('No tiene permisos para acceder a esta sección.', 'danger')
                return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator