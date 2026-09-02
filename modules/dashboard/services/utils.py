# ============================================================
# DXT CONTA - Dashboard Ejecutivo - Utilidades comunes
# ============================================================

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from database.db_manager import DatabaseManager
from flask import session

from modules.dashboard.services.config import MONEDA_BASE, RANGOS, RANGO_DEFAULT


def clean(value: Any) -> str:
    return str(value or '').strip()


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else '0')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def format_money(value: Any) -> str:
    return f"{decimal_value(value):,.2f}"


def parse_date(value: Any, field_name: str, default: date | None = None) -> date:
    raw = clean(value)
    if not raw:
        if default is not None:
            return default
        raise ValueError(f'{field_name} es obligatoria.')
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no tiene un formato válido.') from exc


def parse_optional_int(value: Any, field_name: str) -> int | None:
    raw = clean(value)
    if not raw:
        return None
    try:
        number = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} no es válido.') from exc
    if number <= 0:
        raise ValueError(f'{field_name} no es válido.')
    return number


def build_filters(args) -> dict:
    hoy = date.today()
    rango = clean(args.get('rango')) or RANGO_DEFAULT
    if rango not in RANGOS:
        raise ValueError('El rango seleccionado no es válido.')

    fecha_corte = parse_date(args.get('fecha_corte'), 'Fecha de corte', default=hoy)
    unidad_negocio_id = parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    if rango == 'hoy':
        fecha_desde = fecha_corte
        fecha_hasta = fecha_corte
    elif rango == 'ultimos_7':
        fecha_desde = fecha_corte - timedelta(days=6)
        fecha_hasta = fecha_corte
    elif rango == 'mes':
        fecha_desde = fecha_corte.replace(day=1)
        fecha_hasta = fecha_corte
    else:
        fecha_desde = parse_date(args.get('fecha_desde'), 'Fecha desde')
        fecha_hasta = parse_date(args.get('fecha_hasta'), 'Fecha hasta')
        if fecha_desde > fecha_hasta:
            raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')

    return {
        'rango': rango,
        'rango_label': RANGOS[rango],
        'fecha_corte': fecha_corte,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
    }


def date_label(value: date | None) -> str:
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    return ''


def period_label(filters: dict) -> str:
    if filters['fecha_desde'] == filters['fecha_hasta']:
        return f"{filters['rango_label']} · {date_label(filters['fecha_corte'])}"
    return f"{filters['rango_label']} · {date_label(filters['fecha_desde'])} al {date_label(filters['fecha_hasta'])}"


def usuario_actual() -> str:
    return clean(session.get('nombre')) or clean(session.get('username')) or clean(session.get('user_name')) or 'Usuario del sistema'


def fetch_one(sql: str, params: tuple = ()) -> dict:
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    return dict(rows[0]) if rows else {}


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    return [dict(row) for row in rows]


def obtener_simbolo_moneda(codigo: str = MONEDA_BASE) -> str:
    sql = """
        SELECT COALESCE(NULLIF(simbolo, ''), codigo)::text AS simbolo
        FROM contabilidad.moneda
        WHERE codigo = %s
        LIMIT 1
    """
    try:
        row = fetch_one(sql, (codigo,))
        return clean(row.get('simbolo')) or {'BOB': 'Bs', 'USD': '$us', 'UFV': 'UFV'}.get(codigo, codigo)
    except Exception:
        return {'BOB': 'Bs', 'USD': '$us', 'UFV': 'UFV'}.get(codigo, codigo)


def money_note(codigo: str = MONEDA_BASE) -> str:
    return f'Expresado en {obtener_simbolo_moneda(codigo)}.'


def report_detail_url(report_id: str, filters: dict, alcance: str = 'hoy', grupo: str = '', fecha_base=None, extra: dict | None = None) -> str:
    """Construye un enlace seguro hacia Reportes Rapidos con filtros preseleccionados.

    Si el módulo de reportes no está registrado, devuelve '#', evitando romper el dashboard.
    """
    from flask import url_for

    base_date = fecha_base or filters.get('fecha_corte') or date.today()
    params = {
        'reporte': report_id,
        'alcance': alcance,
        'fecha_base': base_date.isoformat() if isinstance(base_date, date) else str(base_date),
        'grupo': grupo or '',
        'unidad_negocio_id': filters.get('unidad_negocio_id') or '',
    }
    if extra:
        for key, value in extra.items():
            if value is not None:
                params[key] = value
    try:
        return url_for('reportes_rapidos.index', **params)
    except Exception:
        return '#'
