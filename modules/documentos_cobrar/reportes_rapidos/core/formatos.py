# ============================================================
# DXT CONTA - Reportes Rápidos - Formatos comunes
# ============================================================

from modules.reportes_rapidos.core.utils import decimal_value


def dias_label(dias):
    if dias is None:
        return ''
    try:
        dias = int(dias)
    except (TypeError, ValueError):
        return ''
    if dias < 0:
        return f'{abs(dias)} día(s) vencido'
    if dias == 0:
        return 'Hoy'
    if dias == 1:
        return 'Mañana'
    return f'En {dias} día(s)'


def format_money(value, moneda=None):
    """Devuelve importes sin prefijo de moneda."""
    value = decimal_value(value)
    return f'{value:,.2f}'
