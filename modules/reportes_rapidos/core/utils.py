# ============================================================
# DXT CONTA - Reportes Rápidos - Utilidades comunes
# ============================================================

import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app, session


def clean(value):
    return (value or '').strip()


def parse_date(value, field_name, default=None):
    value = clean(value)
    if not value:
        if default is not None:
            return default
        raise ValueError(f'El campo "{field_name}" es obligatorio.')

    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.') from exc


def parse_optional_int(value, field_name):
    value = clean(value)
    if not value:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es válido.') from exc
    if parsed <= 0:
        raise ValueError(f'El campo "{field_name}" no es válido.')
    return parsed


def decimal_value(value):
    try:
        return Decimal(str(value if value is not None else 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def date_label(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    return str(value)


def usuario_actual():
    return (
        session.get('nombre_completo')
        or session.get('usuario_nombre')
        or session.get('username')
        or session.get('usuario')
        or session.get('email')
        or 'Sistema'
    )


def logo_path():
    logo_folder = current_app.config.get('LOGO_FOLDER') or os.getenv('LOGO_FOLDER') or ''
    candidates = [
        current_app.config.get('SIDEBAR_LOGO_FILENAME'),
        current_app.config.get('LOGIN_LOGO_FILENAME'),
        'dxt_logo.jpg',
        'logo.jpg',
        'logo.png',
    ]

    if logo_folder:
        base = Path(logo_folder)
        for filename in candidates:
            if filename:
                candidate = base / filename
                if candidate.exists() and candidate.is_file():
                    return str(candidate)
        for candidate in sorted(base.glob('*')):
            if candidate.is_file():
                return str(candidate)

    return None
