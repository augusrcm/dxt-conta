# ============================================================
# DXT CONTA - Reportes Rápidos - Contexto monetario
# ============================================================

from __future__ import annotations

from typing import Iterable

from database.db_manager import DatabaseManager
from modules.reportes_rapidos.core.utils import decimal_value


FALLBACK_SIMBOLOS = {
    'BOB': 'Bs',
    'USD': '$us',
    'UFV': 'UFV',
}


def _normalizar_codigo(codigo) -> str:
    return str(codigo or '').strip().upper()


def obtener_simbolos_monedas(codigos: Iterable[str]) -> dict[str, str]:
    codigos_limpios = sorted({_normalizar_codigo(codigo) for codigo in codigos if _normalizar_codigo(codigo)})
    simbolos = {codigo: FALLBACK_SIMBOLOS.get(codigo, codigo) for codigo in codigos_limpios}

    if not codigos_limpios:
        return simbolos

    placeholders = ', '.join(['%s'] * len(codigos_limpios))
    sql = f"""
        SELECT codigo::text AS codigo, COALESCE(NULLIF(simbolo, ''), codigo)::text AS simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
          AND codigo IN ({placeholders})
    """
    try:
        with DatabaseManager() as db:
            rows = db.execute_query(sql, tuple(codigos_limpios))
        for row in rows:
            codigo = _normalizar_codigo(row.get('codigo'))
            simbolo = str(row.get('simbolo') or '').strip()
            if codigo and simbolo:
                simbolos[codigo] = simbolo
    except Exception:
        pass

    return simbolos


def expresion_moneda(codigo: str, simbolo: str) -> str:
    simbolo = str(simbolo or '').strip()
    codigo = _normalizar_codigo(codigo)
    if simbolo:
        return f'Expresado en {simbolo}.'
    if codigo:
        return f'Expresado en {codigo}.'
    return ''


def aplicar_contexto_monetario(payload: dict) -> dict:
    rows = payload.get('rows') or []
    summary = payload.get('summary') or {}
    codigos = set()

    for row in rows:
        codigo = _normalizar_codigo(row.get('moneda_codigo'))
        if codigo:
            codigos.add(codigo)

    for item in summary.get('totales_por_moneda') or []:
        codigo = _normalizar_codigo(item.get('moneda_codigo'))
        if codigo:
            codigos.add(codigo)

    moneda_unica = _normalizar_codigo(summary.get('moneda_unica'))
    if moneda_unica:
        codigos.add(moneda_unica)

    simbolos = obtener_simbolos_monedas(codigos)

    for row in rows:
        codigo = _normalizar_codigo(row.get('moneda_codigo'))
        if codigo:
            row['moneda_codigo'] = codigo
            row['moneda_simbolo'] = simbolos.get(codigo, codigo)

    totales_por_moneda = summary.get('totales_por_moneda') or []
    for item in totales_por_moneda:
        codigo = _normalizar_codigo(item.get('moneda_codigo'))
        item['moneda_codigo'] = codigo
        item['moneda_simbolo'] = simbolos.get(codigo, codigo) if codigo else ''
        item['total_label'] = f"{decimal_value(item.get('total')):,.2f}"

    if moneda_unica:
        simbolo = simbolos.get(moneda_unica, moneda_unica)
        summary['moneda_unica'] = moneda_unica
        summary['moneda_unica_simbolo'] = simbolo
        summary['moneda_display_note'] = expresion_moneda(moneda_unica, simbolo)
    elif totales_por_moneda:
        visibles = [item.get('moneda_simbolo') or item.get('moneda_codigo') for item in totales_por_moneda if item.get('moneda_codigo')]
        summary['moneda_display_note'] = 'Montos por moneda: ' + ', '.join(visibles) + '.' if visibles else ''
    else:
        summary['moneda_display_note'] = 'Sin importes monetarios'

    payload['summary'] = summary
    return payload
