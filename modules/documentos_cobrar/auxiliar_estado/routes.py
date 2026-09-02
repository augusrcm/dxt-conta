# ============================================================
# DXT CONTA - Reporte Especial
# Reporte: Estado de Auxiliares
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import Response, jsonify, render_template, request, url_for

from database.db_manager import DatabaseManager
from modules.auxiliar_estado import auxiliar_estado_bp
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import format_money
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
ESTADO_CONFIRMADO = 'CONFIRMADO'
CENTAVO = Decimal('0.01')
MODOS_FECHA = {
    'GESTION': 'Gestión completa',
    'RANGO': 'Rango de fechas',
}


# ============================================================
# Helpers generales
# ============================================================


def _json_ok(**kwargs):
    payload = {'ok': True}
    payload.update(kwargs)
    return jsonify(_json_ready(payload))


def _json_error(message: str, status: int = 400, **kwargs):
    payload = {'ok': False, 'msg': message}
    payload.update(kwargs)
    return jsonify(_json_ready(payload)), status


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _parse_int(value: Any, field_name: str) -> int:
    raw = _clean(value)
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es válido.') from exc
    if parsed <= 0:
        raise ValueError(f'El campo "{field_name}" no es válido.')
    return parsed


def _parse_optional_int(value: Any, field_name: str) -> int | None:
    raw = _clean(value)
    if not raw:
        return None
    return _parse_int(raw, field_name)


def _parse_gestion(value: Any) -> int:
    raw = _clean(value)
    if not raw:
        return _gestion_preferida()
    try:
        gestion = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('La gestión seleccionada no es válida.') from exc
    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestión seleccionada no es válida.')
    return gestion


def _parse_date(value: Any, field_name: str) -> date:
    raw = _clean(value)
    if not raw:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.') from exc


def _date_label(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    raw = _clean(value)
    if not raw:
        return ''
    try:
        parsed = datetime.strptime(raw[:10], '%Y-%m-%d').date()
        return parsed.strftime('%d/%m/%Y')
    except ValueError:
        return raw


def _db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    return [dict(row) for row in rows]


def _gestion_preferida() -> int:
    rows = _db_rows(
        """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
        """
    )
    if rows:
        return int(rows[0]['gestion'])
    return date.today().year


def _obtener_gestiones() -> list[int]:
    rows = _db_rows(
        """
        SELECT DISTINCT gestion
        FROM contabilidad.gestion_control
        UNION
        SELECT DISTINCT EXTRACT(YEAR FROM fecha)::int AS gestion
        FROM contabilidad.asiento
        ORDER BY gestion DESC
        """
    )
    gestiones = [int(row['gestion']) for row in rows if row.get('gestion')]
    if not gestiones:
        gestiones = [date.today().year]
    return gestiones


def _obtener_unidades_negocio() -> list[dict[str, Any]]:
    rows = _db_rows(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
        """
    )
    return [dict(row) for row in rows]


def _unidad_label(unidad_negocio_id: int | None) -> str:
    if not unidad_negocio_id:
        return 'Todas las unidades de negocio'
    rows = _db_rows(
        """
        SELECT COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_negocio_id,),
    )
    if not rows:
        return f'Unidad #{unidad_negocio_id}'
    row = rows[0]
    codigo = row.get('codigo') or ''
    nombre = row.get('nombre') or ''
    return f'{codigo} · {nombre}' if codigo else nombre


def _auxiliar_info(auxiliar_id: int) -> dict[str, Any]:
    rows = _db_rows(
        """
        SELECT
            id,
            tipo::text AS tipo,
            COALESCE(codigo_externo, '') AS codigo_externo,
            COALESCE(nit_ci, '') AS nit_ci,
            COALESCE(nombre, '') AS nombre,
            COALESCE(razon_social, '') AS razon_social
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,),
    )
    if not rows:
        raise ValueError('No se encontró el auxiliar solicitado.')
    row = dict(rows[0])
    row['label'] = _auxiliar_label_row(row)
    return row


def _auxiliar_label_row(row: dict[str, Any]) -> str:
    nombre = row.get('nombre') or f"Auxiliar #{row.get('id', '')}"
    nit_ci = row.get('nit_ci') or ''
    tipo = row.get('tipo') or ''
    parts = [nombre]
    if nit_ci:
        parts.append(f'NIT/CI: {nit_ci}')
    if tipo:
        parts.append(tipo)
    return ' | '.join(parts)


def _periodo_label(fecha_modo: str, gestion: int, fecha_desde: date, fecha_hasta: date) -> str:
    if fecha_modo == 'GESTION':
        return f'Gestión {gestion}'
    if fecha_desde == fecha_hasta:
        return f'Fecha: {_date_label(fecha_desde)}'
    return f'Rango: {_date_label(fecha_desde)} al {_date_label(fecha_hasta)}'


def _origen_movimiento_label(row: dict[str, Any]) -> str:
    tabla = _clean(row.get('tabla_origen')).lower()
    modulo = _clean(row.get('modulo_origen')).upper()
    origen_cobro = _clean(row.get('origen_cobro')).upper()

    if tabla == 'contabilidad.cobro' or modulo == 'TESORERIA':
        if origen_cobro == 'DOCUMENTO_COBRAR':
            return 'Cobro Doc. CxC'
        if origen_cobro == 'COMPROMISO':
            return 'Cobro compromiso'
        if origen_cobro == 'DIRECTO':
            return 'Cobro directo'
        return 'Tesorería'
    if tabla == 'contabilidad.documento_por_cobrar' or modulo == 'DOCUMENTOS_COBRAR':
        return 'Doc. por cobrar'
    if modulo == 'SALDOS_INICIALES':
        return 'Saldo inicial'
    if modulo == 'VENTAS':
        return 'Venta'
    if modulo == 'COMPRAS':
        return 'Compra'
    if modulo:
        return modulo.replace('_', ' ').title()
    return 'Contable'


# ============================================================
# Filtros
# ============================================================


def _parse_main_filters(args) -> dict[str, Any]:
    gestion = _parse_gestion(args.get('gestion'))
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')
    q = _clean(args.get('q'))
    return {
        'gestion': gestion,
        'fecha_desde': date(gestion, 1, 1),
        'fecha_hasta': date(gestion, 12, 31),
        'unidad_negocio_id': unidad_negocio_id,
        'q': q,
    }


def _parse_detail_filters(args) -> dict[str, Any]:
    gestion = _parse_gestion(args.get('gestion'))
    fecha_modo = _clean(args.get('fecha_modo')).upper() or 'GESTION'
    if fecha_modo not in MODOS_FECHA:
        raise ValueError('El modo de fecha seleccionado no es válido.')

    if fecha_modo == 'GESTION':
        fecha_desde = date(gestion, 1, 1)
        fecha_hasta = date(gestion, 12, 31)
    else:
        fecha_desde = _parse_date(args.get('fecha_desde'), 'Fecha desde')
        fecha_hasta = _parse_date(args.get('fecha_hasta'), 'Fecha hasta')
        if fecha_hasta < fecha_desde:
            raise ValueError('La fecha hasta no puede ser menor que la fecha desde.')

    return {
        'auxiliar_id': _parse_int(args.get('auxiliar_id'), 'Auxiliar'),
        'gestion': gestion,
        'fecha_modo': fecha_modo,
        'fecha_modo_label': MODOS_FECHA[fecha_modo],
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio'),
    }


# ============================================================
# Consulta principal de auxiliares
# ============================================================


def _fetch_auxiliares_estado(filtros: dict[str, Any], limit_rows: int | None = None) -> dict[str, Any]:
    params: list[Any] = [ESTADO_CONFIRMADO, filtros['fecha_desde'], filtros['fecha_hasta']]
    unidad_join = ''
    if filtros.get('unidad_negocio_id'):
        unidad_join = 'AND a.unidad_negocio_id = %s'
        params.append(filtros['unidad_negocio_id'])

    where_aux = ['aux.activo = TRUE']
    if filtros.get('q'):
        like = f"%{filtros['q']}%"
        where_aux.append(
            """
            (
                UPPER(COALESCE(aux.nombre, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(aux.razon_social, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(aux.nit_ci, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(aux.codigo_externo, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(aux.tipo::text, '')) LIKE UPPER(%s)
            )
            """
        )
        params.extend([like] * 5)

    limit_sql = ''
    if limit_rows:
        limit_sql = 'LIMIT %s'
        params.append(limit_rows)

    rows = _db_rows(
        f"""
        WITH mov AS (
            SELECT
                ad.auxiliar_id,
                COUNT(*) AS movimientos,
                COALESCE(SUM(COALESCE(ad.debe, 0)), 0) AS debe,
                COALESCE(SUM(COALESCE(ad.haber, 0)), 0) AS haber,
                MAX(a.fecha) AS ultima_fecha
            FROM contabilidad.asiento_detalle ad
            INNER JOIN contabilidad.asiento a ON a.id = ad.asiento_id
            WHERE ad.auxiliar_id IS NOT NULL
              AND a.estado::text = %s
              AND a.fecha BETWEEN %s AND %s
              {unidad_join}
            GROUP BY ad.auxiliar_id
        ), base AS (
            SELECT
                aux.id,
                aux.tipo::text AS tipo,
                COALESCE(aux.codigo_externo, '') AS codigo_externo,
                COALESCE(aux.nit_ci, '') AS nit_ci,
                COALESCE(aux.nombre, '') AS nombre,
                COALESCE(aux.razon_social, '') AS razon_social,
                COALESCE(mov.movimientos, 0) AS movimientos,
                COALESCE(mov.debe, 0) AS debe,
                COALESCE(mov.haber, 0) AS haber,
                COALESCE(mov.debe, 0) - COALESCE(mov.haber, 0) AS saldo,
                mov.ultima_fecha
            FROM contabilidad.auxiliar aux
            LEFT JOIN mov ON mov.auxiliar_id = aux.id
            WHERE {' AND '.join(where_aux)}
        )
        SELECT
            base.*,
            COUNT(*) OVER() AS total_filtrado,
            COALESCE(SUM(base.debe) OVER(), 0) AS total_debe_filtrado,
            COALESCE(SUM(base.haber) OVER(), 0) AS total_haber_filtrado,
            COALESCE(SUM(base.saldo) OVER(), 0) AS total_saldo_filtrado,
            COALESCE(SUM(CASE WHEN base.movimientos > 0 THEN 1 ELSE 0 END) OVER(), 0) AS auxiliares_con_movimiento_filtrado
        FROM base
        ORDER BY base.movimientos DESC, base.nombre ASC, base.id ASC
        {limit_sql}
        """,
        tuple(params),
    )

    result_rows: list[dict[str, Any]] = []
    for row in rows:
        debe = _decimal(row.get('debe'))
        haber = _decimal(row.get('haber'))
        saldo = debe - haber
        movimientos = int(row.get('movimientos') or 0)
        item = {
            'id': int(row.get('id')),
            'tipo': row.get('tipo') or '',
            'codigo_externo': row.get('codigo_externo') or '',
            'nit_ci': row.get('nit_ci') or '',
            'nombre': row.get('nombre') or '',
            'razon_social': row.get('razon_social') or '',
            'auxiliar_label': _auxiliar_label_row(row),
            'movimientos': movimientos,
            'debe': debe,
            'haber': haber,
            'saldo': saldo,
            'debe_label': format_money(debe),
            'haber_label': format_money(haber),
            'saldo_label': format_money(saldo),
            'ultima_fecha': _date_label(row.get('ultima_fecha')),
        }
        result_rows.append(item)

    summary_source = rows[0] if rows else {}
    total_debe = _decimal(summary_source.get('total_debe_filtrado'))
    total_haber = _decimal(summary_source.get('total_haber_filtrado'))
    total_saldo = _decimal(summary_source.get('total_saldo_filtrado'))
    total_filtrado = int(summary_source.get('total_filtrado') or 0)
    total_con_mov = int(summary_source.get('auxiliares_con_movimiento_filtrado') or 0)
    summary = {
        'gestion': filtros['gestion'],
        'periodo': _periodo_label('GESTION', filtros['gestion'], filtros['fecha_desde'], filtros['fecha_hasta']),
        'unidad_label': _unidad_label(filtros.get('unidad_negocio_id')),
        'total_auxiliares': total_filtrado,
        'auxiliares_listados': len(result_rows),
        'auxiliares_con_movimiento': total_con_mov,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'total_saldo': total_saldo,
        'total_debe_label': format_money(total_debe),
        'total_haber_label': format_money(total_haber),
        'total_saldo_label': format_money(total_saldo),
        'moneda_display_note': 'BOB · Saldo = Debe - Haber',
    }
    return {'rows': result_rows, 'summary': summary}


# ============================================================
# Consulta detalle del auxiliar
# ============================================================


def _where_auxiliar_movs(filtros: dict[str, Any]) -> tuple[list[str], list[Any]]:
    where = [
        'a.estado::text = %s',
        'ad.auxiliar_id = %s',
    ]
    params: list[Any] = [ESTADO_CONFIRMADO, filtros['auxiliar_id']]
    if filtros.get('unidad_negocio_id'):
        where.append('a.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    return where, params


def _fetch_total_before(filtros: dict[str, Any]) -> dict[str, Decimal]:
    where, params = _where_auxiliar_movs(filtros)
    where.append('a.fecha < %s')
    params.append(filtros['fecha_desde'])
    rows = _db_rows(
        f"""
        SELECT
            COALESCE(SUM(COALESCE(ad.debe, 0)), 0) AS debe,
            COALESCE(SUM(COALESCE(ad.haber, 0)), 0) AS haber
        FROM contabilidad.asiento_detalle ad
        INNER JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    )
    row = rows[0] if rows else {}
    debe = _decimal(row.get('debe'))
    haber = _decimal(row.get('haber'))
    return {'debe': debe, 'haber': haber, 'saldo': debe - haber}


def _fetch_period_totals(filtros: dict[str, Any]) -> dict[str, Decimal | int]:
    where, params = _where_auxiliar_movs(filtros)
    where.append('a.fecha BETWEEN %s AND %s')
    params.extend([filtros['fecha_desde'], filtros['fecha_hasta']])
    rows = _db_rows(
        f"""
        SELECT
            COUNT(*) AS movimientos,
            COALESCE(SUM(COALESCE(ad.debe, 0)), 0) AS debe,
            COALESCE(SUM(COALESCE(ad.haber, 0)), 0) AS haber
        FROM contabilidad.asiento_detalle ad
        INNER JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    )
    row = rows[0] if rows else {}
    debe = _decimal(row.get('debe'))
    haber = _decimal(row.get('haber'))
    return {
        'movimientos': int(row.get('movimientos') or 0),
        'debe': debe,
        'haber': haber,
        'saldo': debe - haber,
    }


def _fetch_movements(filtros: dict[str, Any], limit_rows: int | None = None) -> list[dict[str, Any]]:
    where, params = _where_auxiliar_movs(filtros)
    where.append('a.fecha BETWEEN %s AND %s')
    params.extend([filtros['fecha_desde'], filtros['fecha_hasta']])
    limit_sql = ''
    if limit_rows:
        limit_sql = 'LIMIT %s'
        params.append(limit_rows)
    return _db_rows(
        f"""
        SELECT
            ad.id AS detalle_id,
            a.id AS asiento_id,
            a.fecha,
            COALESCE(a.referencia, '') AS asiento_referencia,
            COALESCE(ad.referencia, '') AS detalle_referencia,
            COALESCE(a.glosa, '') AS asiento_glosa,
            COALESCE(ad.glosa, '') AS detalle_glosa,
            COALESCE(a.modulo_origen, '') AS modulo_origen,
            COALESCE(a.tabla_origen, '') AS tabla_origen,
            a.origen_id,
            COALESCE(co.origen_operacion::text, '') AS origen_cobro,
            ad.secuencia,
            ad.cuenta_codigo,
            COALESCE(c.nombre, '') AS cuenta_nombre,
            COALESCE(ad.debe, 0) AS debe,
            COALESCE(ad.haber, 0) AS haber,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre
        FROM contabilidad.asiento_detalle ad
        INNER JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        LEFT JOIN contabilidad.cobro co ON a.tabla_origen = 'contabilidad.cobro' AND co.id = a.origen_id
        WHERE {' AND '.join(where)}
        ORDER BY a.fecha ASC, a.id ASC, ad.secuencia ASC, ad.id ASC
        {limit_sql}
        """,
        tuple(params),
    )


def _control_row(tipo_linea: str, bloque: str, glosa: str, saldo: Decimal, fecha_label: str = '') -> dict[str, Any]:
    return {
        'tipo_linea': tipo_linea,
        'bloque': bloque,
        'fecha': fecha_label,
        'asiento_id': '',
        'referencia': '',
        'cuenta': '',
        'unidad': '',
        'glosa': glosa,
        'debe': Decimal('0.00'),
        'haber': Decimal('0.00'),
        'saldo': saldo,
        'debe_label': '',
        'haber_label': '',
        'saldo_label': format_money(saldo),
        'url_comprobante': '',
    }


def _movement_row(row: dict[str, Any], saldo: Decimal) -> dict[str, Any]:
    debe = _decimal(row.get('debe'))
    haber = _decimal(row.get('haber'))
    cuenta = row.get('cuenta_codigo') or ''
    if row.get('cuenta_nombre'):
        cuenta = f"{cuenta} · {row.get('cuenta_nombre')}"
    unidad = row.get('unidad_nombre') or ''
    if row.get('unidad_codigo'):
        unidad = f"{row.get('unidad_codigo')} · {unidad}"
    referencia = row.get('detalle_referencia') or row.get('asiento_referencia') or f"Asiento #{row.get('asiento_id')}"
    glosa = row.get('detalle_glosa') or row.get('asiento_glosa') or ''
    asiento_id = int(row.get('asiento_id') or 0)
    return {
        'tipo_linea': 'MOVIMIENTO',
        'bloque': _origen_movimiento_label(row),
        'fecha': _date_label(row.get('fecha')),
        'asiento_id': asiento_id,
        'referencia': referencia,
        'cuenta': cuenta,
        'unidad': unidad,
        'glosa': glosa,
        'debe': debe,
        'haber': haber,
        'saldo': saldo,
        'debe_label': format_money(debe),
        'haber_label': format_money(haber),
        'saldo_label': format_money(saldo),
        'url_comprobante': url_for('comprobantes.ver', asiento_id=asiento_id) if asiento_id else '',
    }


def _build_detalle_auxiliar(filtros: dict[str, Any], limit_rows: int | None = None) -> dict[str, Any]:
    auxiliar = _auxiliar_info(filtros['auxiliar_id'])
    saldo_anterior_info = _fetch_total_before(filtros)
    periodo_totals = _fetch_period_totals(filtros)
    saldo = saldo_anterior_info['saldo']
    movimientos = _fetch_movements(filtros, limit_rows=limit_rows)
    total_movimientos = int(periodo_totals.get('movimientos') or 0)
    detalle_limitado = limit_rows is not None and total_movimientos > len(movimientos)

    rows: list[dict[str, Any]] = [
        _control_row(
            'SALDO_ANTERIOR',
            'Saldo anterior',
            f"Saldo antes del {_date_label(filtros['fecha_desde'])}",
            saldo,
        )
    ]

    for mov in movimientos:
        debe = _decimal(mov.get('debe'))
        haber = _decimal(mov.get('haber'))
        saldo += debe - haber
        rows.append(_movement_row(mov, saldo))

    saldo_final = saldo_anterior_info['saldo'] + _decimal(periodo_totals.get('debe')) - _decimal(periodo_totals.get('haber'))
    if detalle_limitado:
        rows.append(
            _control_row(
                'LIMITE',
                'Límite de pantalla',
                f"Se muestran {len(movimientos)} de {total_movimientos} movimientos.",
                saldo,
            )
        )

    rows.append(
        _control_row(
            'SALDO_FINAL',
            'Saldo final',
            f"Saldo hasta el {_date_label(filtros['fecha_hasta'])}",
            saldo_final,
            _date_label(filtros['fecha_hasta']),
        )
    )

    total_debe_periodo = _decimal(periodo_totals.get('debe'))
    total_haber_periodo = _decimal(periodo_totals.get('haber'))
    periodo_label = _periodo_label(filtros['fecha_modo'], filtros['gestion'], filtros['fecha_desde'], filtros['fecha_hasta'])
    summary = {
        'periodo_label': periodo_label,
        'unidad_label': _unidad_label(filtros.get('unidad_negocio_id')),
        'saldo_anterior': saldo_anterior_info['saldo'],
        'saldo_anterior_label': format_money(saldo_anterior_info['saldo']),
        'debe_periodo': total_debe_periodo,
        'debe_periodo_label': format_money(total_debe_periodo),
        'haber_periodo': total_haber_periodo,
        'haber_periodo_label': format_money(total_haber_periodo),
        'saldo_periodo': total_debe_periodo - total_haber_periodo,
        'saldo_periodo_label': format_money(total_debe_periodo - total_haber_periodo),
        'saldo_final': saldo_final,
        'saldo_final_label': format_money(saldo_final),
        'movimientos': total_movimientos,
        'movimientos_listados': len(movimientos),
        'detalle_limitado': detalle_limitado,
        'moneda_display_note': 'BOB · Saldo = Debe - Haber',
    }
    return {
        'titulo': 'Estado de Auxiliar',
        'auxiliar': auxiliar,
        'auxiliar_label': auxiliar['label'],
        'gestion': filtros['gestion'],
        'fecha_modo': filtros['fecha_modo'],
        'fecha_modo_label': filtros['fecha_modo_label'],
        'fecha_desde': filtros['fecha_desde'],
        'fecha_hasta': filtros['fecha_hasta'],
        'descripcion_periodo': periodo_label,
        'criterio_reporte': f"Auxiliar: {auxiliar['label']}. Unidad: {summary['unidad_label']}.",
        'fuente_datos': 'contabilidad.asiento / contabilidad.asiento_detalle / contabilidad.auxiliar',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'rows': rows,
        'summary': summary,
    }


# ============================================================
# PDF
# ============================================================


class AuxiliaresEstadoListadoPDF:
    TITLE = 'Estado de Auxiliares'
    PDF_ORIENTATION = 'landscape'

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Auxiliar', 'width': 64, 'align': 'left'},
            {'label': 'Tipo', 'width': 22, 'align': 'center'},
            {'label': 'NIT/CI', 'width': 28, 'align': 'left'},
            {'label': 'Movs.', 'width': 16, 'align': 'center'},
            {'label': 'Debe', 'width': 28, 'align': 'right'},
            {'label': 'Haber', 'width': 28, 'align': 'right'},
            {'label': 'Saldo', 'width': 28, 'align': 'right'},
            {'label': 'Últ. fecha', 'width': 24, 'align': 'center'},
            {'label': 'Razón social', 'width': 62, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('nombre', ''),
                item.get('tipo', ''),
                item.get('nit_ci', ''),
                str(item.get('movimientos', 0)),
                item.get('debe_label', ''),
                item.get('haber_label', ''),
                item.get('saldo_label', ''),
                item.get('ultima_fecha', ''),
                item.get('razon_social', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['Límite PDF', '', '', '', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} filas. Use la pantalla para filtrar.'])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"Periodo: {summary.get('periodo', '')}. Unidad: {summary.get('unidad_label', '')}. "
            f"Auxiliares: {summary.get('total_auxiliares', 0)}. Con movimiento: {summary.get('auxiliares_con_movimiento', 0)}. "
            f"Debe: {summary.get('total_debe_label', '0.00')}. Haber: {summary.get('total_haber_label', '0.00')}. "
            f"Saldo: {summary.get('total_saldo_label', '0.00')}"
        )


class AuxiliarEstadoDetallePDF:
    TITLE = 'Extracto de Auxiliar'
    PDF_ORIENTATION = 'landscape'

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Origen', 'width': 30, 'align': 'left'},
            {'label': 'Fecha', 'width': 20, 'align': 'center'},
            {'label': 'Comp.', 'width': 16, 'align': 'center'},
            {'label': 'Cuenta', 'width': 48, 'align': 'left'},
            {'label': 'Unidad', 'width': 36, 'align': 'left'},
            {'label': 'Glosa', 'width': 62, 'align': 'left'},
            {'label': 'Debe', 'width': 24, 'align': 'right'},
            {'label': 'Haber', 'width': 24, 'align': 'right'},
            {'label': 'Saldo', 'width': 24, 'align': 'right'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('bloque', ''),
                item.get('fecha', ''),
                str(item.get('asiento_id') or ''),
                item.get('cuenta', ''),
                item.get('unidad', ''),
                item.get('glosa', ''),
                item.get('debe_label', ''),
                item.get('haber_label', ''),
                item.get('saldo_label', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['Límite PDF', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} filas.', '', '', ''])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"Auxiliar: {payload.get('auxiliar_label', '')}. Periodo: {payload.get('descripcion_periodo', '')}. "
            f"Unidad: {summary.get('unidad_label', '')}. Saldo anterior: {summary.get('saldo_anterior_label', '0.00')}. "
            f"Debe período: {summary.get('debe_periodo_label', '0.00')}. Haber período: {summary.get('haber_periodo_label', '0.00')}. "
            f"Saldo final: {summary.get('saldo_final_label', '0.00')}"
        )


# ============================================================
# Rutas
# ============================================================


@auxiliar_estado_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    gestion = _gestion_preferida()
    bootstrap = {
        'urls': {
            'apiAuxiliares': url_for('auxiliar_estado.api_auxiliares'),
            'apiDetalle': url_for('auxiliar_estado.api_detalle'),
            'pdfAuxiliares': url_for('auxiliar_estado.pdf_auxiliares'),
            'pdfDetalle': url_for('auxiliar_estado.pdf_detalle'),
        }
    }
    return render_template(
        'auxiliar_estado_index.html',
        gestiones=_obtener_gestiones(),
        gestion_preferida=gestion,
        fecha_desde=f'{gestion}-01-01',
        fecha_hasta=f'{gestion}-12-31',
        unidades_negocio=_obtener_unidades_negocio(),
        bootstrap=bootstrap,
    )


@auxiliar_estado_bp.route('/api/auxiliares')
@login_required
@roles_required(ROLES_LECTURA)
def api_auxiliares():
    try:
        filtros = _parse_main_filters(request.args)
        payload = _fetch_auxiliares_estado(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo consultar el estado de auxiliares. {exc}', 500)


@auxiliar_estado_bp.route('/api/detalle')
@login_required
@roles_required(ROLES_LECTURA)
def api_detalle():
    try:
        filtros = _parse_detail_filters(request.args)
        payload = _build_detalle_auxiliar(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo consultar el detalle del auxiliar. {exc}', 500)


@auxiliar_estado_bp.route('/pdf/auxiliares')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_auxiliares():
    try:
        filtros = _parse_main_filters(request.args)
        payload = _fetch_auxiliares_estado(filtros, limit_rows=MAX_ROWS_EXPORT)
        payload.update({
            'titulo': 'Estado de Auxiliares',
            'criterio_reporte': f"Gestión {filtros['gestion']}. Unidad: {_unidad_label(filtros.get('unidad_negocio_id'))}.",
            'fuente_datos': 'contabilidad.auxiliar / contabilidad.asiento_detalle',
            'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        })
        pdf_bytes = build_pdf(AuxiliaresEstadoListadoPDF, payload)
        nombre = f"estado_auxiliares_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF de auxiliares. {exc}', 500)


@auxiliar_estado_bp.route('/pdf/detalle')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_detalle():
    try:
        filtros = _parse_detail_filters(request.args)
        payload = _build_detalle_auxiliar(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(AuxiliarEstadoDetallePDF, payload)
        nombre = f"extracto_auxiliar_{filtros['auxiliar_id']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del detalle. {exc}', 500)


@auxiliar_estado_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('auxiliar_estado_help.html')
