# ============================================================
# DXT CONTA - Herramientas - Conciliacion Caja/Banco
# Control operativo de saldos, arqueos, borradores y asientos
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Response, jsonify, render_template, request

from database.db_manager import DatabaseManager
from modules.conciliacion_caja_banco import conciliacion_caja_banco_bp
from modules.reportes_rapidos.core.catalogos import obtener_unidades_negocio, unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import format_money
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]

MEDIOS = [
    {'value': 'TODOS', 'label': 'Todos'},
    {'value': 'CAJA', 'label': 'Caja'},
    {'value': 'BANCO', 'label': 'Banco'},
]

ESTADOS_REVISION = [
    {'value': 'TODOS', 'label': 'Todos'},
    {'value': 'OBSERVADOS', 'label': 'Con observación'},
    {'value': 'OK', 'label': 'Sin observación'},
]

DIAS_ARQUEO = [7, 15, 30, 60]

PRIORIDAD_LABEL = {
    'CRITICA': 'Crítica',
    'ALTA': 'Alta',
    'MEDIA': 'Media',
    'BAJA': 'Baja',
}

PRIORIDAD_ORDEN = {
    'CRITICA': 1,
    'ALTA': 2,
    'MEDIA': 3,
    'BAJA': 4,
}

ESTADO_LABEL = {
    'OBSERVADO': 'Observado',
    'OK': 'Sin observación',
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
    return (value or '').strip()


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0)).quantize(Decimal('0.01'))
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
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es válido.') from exc
    return parsed


def _parse_optional_int(value: Any, field_name: str) -> int | None:
    raw = _clean(value)
    if not raw:
        return None
    parsed = _parse_int(raw, field_name)
    return parsed if parsed > 0 else None


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
        return value.strftime('%d/%m/%Y %H:%M')
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


def _has_column(db: DatabaseManager, table_name: str, column_name: str) -> bool:
    rows = db.execute_query(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'contabilidad'
              AND table_name = %s
              AND column_name = %s
        ) AS existe
        """,
        (table_name, column_name),
    )
    return bool(rows and rows[0].get('existe'))


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


def _gestion_desde_fecha(fecha_corte: date) -> int:
    return int(fecha_corte.year)


def _estado_label(value: str) -> str:
    return ESTADO_LABEL.get(value, value or 'Sin estado')


def _medio_label(value: str) -> str:
    if value == 'CAJA':
        return 'Caja'
    if value == 'BANCO':
        return 'Banco'
    return 'Todos'


def _parse_filters(args) -> dict[str, Any]:
    fecha_corte = _parse_date(args.get('fecha_corte') or date.today().isoformat(), 'Fecha corte')

    medio = _clean(args.get('medio') or 'TODOS').upper()
    if medio not in {'TODOS', 'CAJA', 'BANCO'}:
        raise ValueError('El medio seleccionado no es válido.')

    estado_revision = _clean(args.get('estado_revision') or 'TODOS').upper()
    if estado_revision not in {'TODOS', 'OBSERVADOS', 'OK'}:
        raise ValueError('El estado de revisión seleccionado no es válido.')

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    dias_sin_arqueo = _parse_int(args.get('dias_sin_arqueo') or 7, 'Días sin arqueo')
    if dias_sin_arqueo not in set(DIAS_ARQUEO):
        raise ValueError('El rango de días sin arqueo no es válido.')

    incluir_inactivos = _clean(args.get('incluir_inactivos')).lower() in {'1', 'true', 'si', 'sí'}

    return {
        'fecha_corte': fecha_corte,
        'gestion': _gestion_desde_fecha(fecha_corte),
        'medio': medio,
        'estado_revision': estado_revision,
        'unidad_negocio_id': unidad_negocio_id,
        'dias_sin_arqueo': dias_sin_arqueo,
        'incluir_inactivos': incluir_inactivos,
        'periodo_label': f'Corte al {fecha_corte.strftime("%d/%m/%Y")}',
        'unidad_label': unidad_label(unidad_negocio_id),
        'medio_label': _medio_label(medio),
    }


# ============================================================
# Mapas de saldos y observaciones
# ============================================================


def _get_caja_balance_map(db: DatabaseManager, fecha_corte: date) -> dict[int, Decimal]:
    rows = db.execute_query(
        """
        SELECT caja_id, COALESCE(SUM(monto), 0) AS saldo
        FROM (
            SELECT c.caja_id AS caja_id, c.monto_total::numeric AS monto
            FROM contabilidad.cobro c
            WHERE c.estado = 'CONFIRMADO'
              AND c.medio_pago = 'CAJA'
              AND c.caja_id IS NOT NULL
              AND c.fecha <= %s

            UNION ALL

            SELECT p.caja_id AS caja_id, (p.monto_total * -1)::numeric AS monto
            FROM contabilidad.pago p
            WHERE p.estado = 'CONFIRMADO'
              AND p.medio_pago = 'CAJA'
              AND p.caja_id IS NOT NULL
              AND p.fecha <= %s

            UNION ALL

            SELECT m.caja_destino_id AS caja_id, m.monto::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_destino = 'CAJA'
              AND m.caja_destino_id IS NOT NULL
              AND m.fecha <= %s

            UNION ALL

            SELECT m.caja_origen_id AS caja_id, (m.monto * -1)::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_origen = 'CAJA'
              AND m.caja_origen_id IS NOT NULL
              AND m.fecha <= %s
        ) s
        GROUP BY caja_id
        """,
        (fecha_corte, fecha_corte, fecha_corte, fecha_corte),
    )
    return {int(row['caja_id']): _decimal(row['saldo']) for row in rows if row.get('caja_id') is not None}


def _get_banco_balance_map(db: DatabaseManager, fecha_corte: date) -> dict[int, Decimal]:
    rows = db.execute_query(
        """
        SELECT banco_id, COALESCE(SUM(monto), 0) AS saldo
        FROM (
            SELECT c.cuenta_bancaria_id AS banco_id, c.monto_total::numeric AS monto
            FROM contabilidad.cobro c
            WHERE c.estado = 'CONFIRMADO'
              AND c.medio_pago = 'BANCO'
              AND c.cuenta_bancaria_id IS NOT NULL
              AND c.fecha <= %s

            UNION ALL

            SELECT p.cuenta_bancaria_id AS banco_id, (p.monto_total * -1)::numeric AS monto
            FROM contabilidad.pago p
            WHERE p.estado = 'CONFIRMADO'
              AND p.medio_pago = 'BANCO'
              AND p.cuenta_bancaria_id IS NOT NULL
              AND p.fecha <= %s

            UNION ALL

            SELECT m.banco_destino_id AS banco_id, m.monto::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_destino = 'BANCO'
              AND m.banco_destino_id IS NOT NULL
              AND m.fecha <= %s

            UNION ALL

            SELECT m.banco_origen_id AS banco_id, (m.monto * -1)::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_origen = 'BANCO'
              AND m.banco_origen_id IS NOT NULL
              AND m.fecha <= %s
        ) s
        GROUP BY banco_id
        """,
        (fecha_corte, fecha_corte, fecha_corte, fecha_corte),
    )
    return {int(row['banco_id']): _decimal(row['saldo']) for row in rows if row.get('banco_id') is not None}


def _get_operacion_map(db: DatabaseManager, medio: str, fecha_corte: date, estado: str, asiento_nulo: bool = False) -> dict[int, dict[str, Any]]:
    if medio == 'CAJA':
        id_col_cobro = 'c.caja_id'
        id_col_pago = 'p.caja_id'
        id_col_mov_destino = 'm.caja_destino_id'
        id_col_mov_origen = 'm.caja_origen_id'
        filtro_cobro = "c.medio_pago = 'CAJA' AND c.caja_id IS NOT NULL"
        filtro_pago = "p.medio_pago = 'CAJA' AND p.caja_id IS NOT NULL"
        filtro_mov_destino = "m.medio_destino = 'CAJA' AND m.caja_destino_id IS NOT NULL"
        filtro_mov_origen = "m.medio_origen = 'CAJA' AND m.caja_origen_id IS NOT NULL"
        id_alias = 'item_id'
    else:
        id_col_cobro = 'c.cuenta_bancaria_id'
        id_col_pago = 'p.cuenta_bancaria_id'
        id_col_mov_destino = 'm.banco_destino_id'
        id_col_mov_origen = 'm.banco_origen_id'
        filtro_cobro = "c.medio_pago = 'BANCO' AND c.cuenta_bancaria_id IS NOT NULL"
        filtro_pago = "p.medio_pago = 'BANCO' AND p.cuenta_bancaria_id IS NOT NULL"
        filtro_mov_destino = "m.medio_destino = 'BANCO' AND m.banco_destino_id IS NOT NULL"
        filtro_mov_origen = "m.medio_origen = 'BANCO' AND m.banco_origen_id IS NOT NULL"
        id_alias = 'item_id'

    asiento_filter_c = 'AND c.asiento_id IS NULL' if asiento_nulo else ''
    asiento_filter_p = 'AND p.asiento_id IS NULL' if asiento_nulo else ''
    asiento_filter_m = 'AND m.asiento_id IS NULL' if asiento_nulo else ''

    rows = db.execute_query(
        f"""
        SELECT {id_alias}, COUNT(*) AS cantidad, COALESCE(SUM(impacto), 0) AS impacto
        FROM (
            SELECT {id_col_cobro} AS {id_alias}, c.monto_total::numeric AS impacto
            FROM contabilidad.cobro c
            WHERE c.estado = %s
              AND {filtro_cobro}
              AND c.fecha <= %s
              {asiento_filter_c}

            UNION ALL

            SELECT {id_col_pago} AS {id_alias}, (p.monto_total * -1)::numeric AS impacto
            FROM contabilidad.pago p
            WHERE p.estado = %s
              AND {filtro_pago}
              AND p.fecha <= %s
              {asiento_filter_p}

            UNION ALL

            SELECT {id_col_mov_destino} AS {id_alias}, m.monto::numeric AS impacto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = %s
              AND {filtro_mov_destino}
              AND m.fecha <= %s
              {asiento_filter_m}

            UNION ALL

            SELECT {id_col_mov_origen} AS {id_alias}, (m.monto * -1)::numeric AS impacto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = %s
              AND {filtro_mov_origen}
              AND m.fecha <= %s
              {asiento_filter_m}
        ) q
        GROUP BY {id_alias}
        """,
        (estado, fecha_corte, estado, fecha_corte, estado, fecha_corte, estado, fecha_corte),
    )
    return {
        int(row[id_alias]): {
            'cantidad': int(row.get('cantidad') or 0),
            'impacto': _decimal(row.get('impacto')),
        }
        for row in rows
        if row.get(id_alias) is not None
    }


def _get_ultimo_movimiento_map(db: DatabaseManager, medio: str, fecha_corte: date) -> dict[int, date]:
    if medio == 'CAJA':
        id_col_cobro = 'c.caja_id'
        id_col_pago = 'p.caja_id'
        id_col_mov_destino = 'm.caja_destino_id'
        id_col_mov_origen = 'm.caja_origen_id'
        filtro_cobro = "c.medio_pago = 'CAJA' AND c.caja_id IS NOT NULL"
        filtro_pago = "p.medio_pago = 'CAJA' AND p.caja_id IS NOT NULL"
        filtro_mov_destino = "m.medio_destino = 'CAJA' AND m.caja_destino_id IS NOT NULL"
        filtro_mov_origen = "m.medio_origen = 'CAJA' AND m.caja_origen_id IS NOT NULL"
    else:
        id_col_cobro = 'c.cuenta_bancaria_id'
        id_col_pago = 'p.cuenta_bancaria_id'
        id_col_mov_destino = 'm.banco_destino_id'
        id_col_mov_origen = 'm.banco_origen_id'
        filtro_cobro = "c.medio_pago = 'BANCO' AND c.cuenta_bancaria_id IS NOT NULL"
        filtro_pago = "p.medio_pago = 'BANCO' AND p.cuenta_bancaria_id IS NOT NULL"
        filtro_mov_destino = "m.medio_destino = 'BANCO' AND m.banco_destino_id IS NOT NULL"
        filtro_mov_origen = "m.medio_origen = 'BANCO' AND m.banco_origen_id IS NOT NULL"

    rows = db.execute_query(
        f"""
        SELECT item_id, MAX(fecha) AS ultima_fecha
        FROM (
            SELECT {id_col_cobro} AS item_id, c.fecha
            FROM contabilidad.cobro c
            WHERE c.estado = 'CONFIRMADO'
              AND {filtro_cobro}
              AND c.fecha <= %s

            UNION ALL

            SELECT {id_col_pago} AS item_id, p.fecha
            FROM contabilidad.pago p
            WHERE p.estado = 'CONFIRMADO'
              AND {filtro_pago}
              AND p.fecha <= %s

            UNION ALL

            SELECT {id_col_mov_destino} AS item_id, m.fecha
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND {filtro_mov_destino}
              AND m.fecha <= %s

            UNION ALL

            SELECT {id_col_mov_origen} AS item_id, m.fecha
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND {filtro_mov_origen}
              AND m.fecha <= %s
        ) q
        GROUP BY item_id
        """,
        (fecha_corte, fecha_corte, fecha_corte, fecha_corte),
    )
    return {int(row['item_id']): row['ultima_fecha'] for row in rows if row.get('item_id') is not None}


def _get_ultimo_arqueo_map(db: DatabaseManager, fecha_corte: date) -> dict[int, dict[str, Any]]:
    rows = db.execute_query(
        """
        SELECT DISTINCT ON (a.caja_id)
            a.caja_id,
            a.fecha_arqueo,
            a.saldo_teorico,
            a.monto_contado,
            a.diferencia,
            a.estado::text AS estado,
            COALESCE(a.observacion, '') AS observacion
        FROM contabilidad.arqueo_caja a
        WHERE a.fecha_arqueo <= %s
        ORDER BY a.caja_id, a.fecha_arqueo DESC, a.id DESC
        """,
        (fecha_corte,),
    )
    return {int(row['caja_id']): dict(row) for row in rows if row.get('caja_id') is not None}


# ============================================================
# Consulta principal
# ============================================================


def _master_cajas(db: DatabaseManager, filtros: dict[str, Any]) -> list[dict[str, Any]]:
    has_unidad = _has_column(db, 'caja', 'unidad_negocio_id')
    unidad_select = 'c.unidad_negocio_id' if has_unidad else 'NULL::bigint AS unidad_negocio_id'
    unidad_join = 'LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id' if has_unidad else ''
    unidad_fields = "COALESCE(un.codigo, '') AS unidad_codigo, COALESCE(un.nombre, '') AS unidad_nombre" if has_unidad else "'' AS unidad_codigo, '' AS unidad_nombre"

    where = []
    params: list[Any] = []
    if not filtros['incluir_inactivos']:
        where.append('c.activo = TRUE')
    if has_unidad and filtros.get('unidad_negocio_id'):
        where.append('c.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    where_sql = 'WHERE ' + ' AND '.join(where) if where else ''

    return [
        dict(row)
        for row in db.execute_query(
            f"""
            SELECT
                c.id,
                'CAJA'::text AS medio,
                c.codigo,
                c.nombre AS nombre,
                c.cuenta_contable_codigo,
                c.activo,
                {unidad_select},
                {unidad_fields}
            FROM contabilidad.caja c
            {unidad_join}
            {where_sql}
            ORDER BY c.activo DESC, c.nombre ASC, c.codigo ASC
            """,
            tuple(params),
        )
    ]


def _master_bancos(db: DatabaseManager, filtros: dict[str, Any]) -> list[dict[str, Any]]:
    has_unidad = _has_column(db, 'cuenta_bancaria', 'unidad_negocio_id')
    unidad_select = 'b.unidad_negocio_id' if has_unidad else 'NULL::bigint AS unidad_negocio_id'
    unidad_join = 'LEFT JOIN contabilidad.unidad_negocio un ON un.id = b.unidad_negocio_id' if has_unidad else ''
    unidad_fields = "COALESCE(un.codigo, '') AS unidad_codigo, COALESCE(un.nombre, '') AS unidad_nombre" if has_unidad else "'' AS unidad_codigo, '' AS unidad_nombre"

    where = []
    params: list[Any] = []
    if not filtros['incluir_inactivos']:
        where.append('b.activo = TRUE')
    if has_unidad and filtros.get('unidad_negocio_id'):
        where.append('b.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    where_sql = 'WHERE ' + ' AND '.join(where) if where else ''

    return [
        dict(row)
        for row in db.execute_query(
            f"""
            SELECT
                b.id,
                'BANCO'::text AS medio,
                b.numero_cuenta AS codigo,
                b.nombre_banco || ' · ' || b.numero_cuenta AS nombre,
                b.cuenta_contable_codigo,
                b.moneda_codigo,
                b.activo,
                {unidad_select},
                {unidad_fields}
            FROM contabilidad.cuenta_bancaria b
            {unidad_join}
            {where_sql}
            ORDER BY b.activo DESC, b.nombre_banco ASC, b.numero_cuenta ASC
            """,
            tuple(params),
        )
    ]


def _accion_sugerida(item: dict[str, Any]) -> str:
    if item['confirmados_sin_asiento'] > 0:
        return 'Revisar operaciones confirmadas sin asiento contable.'
    if item['diferencia_arqueo'] != Decimal('0.00'):
        return 'Revisar diferencia del último arqueo antes de emitir reportes.'
    if item['saldo_sistema'] < Decimal('0.00'):
        return 'Verificar operaciones que generaron saldo negativo.'
    if item['borradores'] > 0:
        return 'Confirmar, corregir o anular operaciones en borrador.'
    if item['medio'] == 'CAJA' and item['dias_desde_arqueo'] is None:
        return 'Registrar arqueo inicial de caja.'
    if item['medio'] == 'CAJA' and item['dias_desde_arqueo'] > item['dias_sin_arqueo']:
        return 'Actualizar arqueo de caja para respaldar el saldo físico.'
    if item['medio'] == 'BANCO':
        return 'Comparar saldo del sistema con el extracto bancario externo.'
    return 'Sin acción inmediata.'


def _prioridad_item(item: dict[str, Any]) -> str:
    if item['confirmados_sin_asiento'] > 0 or item['diferencia_arqueo'] != Decimal('0.00') or item['saldo_sistema'] < Decimal('0.00'):
        return 'CRITICA'
    if item['borradores'] > 0:
        return 'ALTA'
    if item['medio'] == 'CAJA' and (item['dias_desde_arqueo'] is None or item['dias_desde_arqueo'] > item['dias_sin_arqueo']):
        return 'MEDIA'
    return 'BAJA'


def _row_from_master(master: dict[str, Any], maps: dict[str, Any], filtros: dict[str, Any], nro: int) -> dict[str, Any]:
    item_id = int(master['id'])
    medio = master['medio']
    saldo_map = maps['caja_saldos'] if medio == 'CAJA' else maps['banco_saldos']
    borrador_map = maps['caja_borradores'] if medio == 'CAJA' else maps['banco_borradores']
    sin_asiento_map = maps['caja_sin_asiento'] if medio == 'CAJA' else maps['banco_sin_asiento']
    movimiento_map = maps['caja_ultimo_mov'] if medio == 'CAJA' else maps['banco_ultimo_mov']

    saldo_sistema = saldo_map.get(item_id, Decimal('0.00'))
    borrador = borrador_map.get(item_id, {'cantidad': 0, 'impacto': Decimal('0.00')})
    sin_asiento = sin_asiento_map.get(item_id, {'cantidad': 0, 'impacto': Decimal('0.00')})
    ultimo_movimiento = movimiento_map.get(item_id)
    arqueo = maps['arqueos'].get(item_id) if medio == 'CAJA' else None

    diferencia_arqueo = Decimal('0.00')
    ultimo_arqueo_fecha = None
    ultimo_arqueo_estado = ''
    ultimo_arqueo_label = 'No aplica'
    dias_desde_arqueo = None
    saldo_fisico_label = 'No aplica'

    if medio == 'CAJA':
        if arqueo:
            ultimo_arqueo_fecha = arqueo.get('fecha_arqueo')
            ultimo_arqueo_estado = arqueo.get('estado') or ''
            diferencia_arqueo = _decimal(arqueo.get('diferencia'))
            ultimo_arqueo_label = _date_label(ultimo_arqueo_fecha)
            if ultimo_arqueo_fecha:
                dias_desde_arqueo = (filtros['fecha_corte'] - ultimo_arqueo_fecha).days
            if arqueo.get('monto_contado') is not None:
                saldo_fisico_label = format_money(_decimal(arqueo.get('monto_contado')), 'BOB')
            else:
                saldo_fisico_label = 'Sin conteo'
        else:
            ultimo_arqueo_label = 'Sin arqueo'
            saldo_fisico_label = 'Sin arqueo'

    unidad = master.get('unidad_nombre') or 'Sin unidad asociada'
    if master.get('unidad_codigo'):
        unidad = f"{master.get('unidad_codigo')} · {unidad}"

    item_base = {
        'medio': medio,
        'dias_sin_arqueo': filtros['dias_sin_arqueo'],
        'saldo_sistema': saldo_sistema,
        'borradores': int(borrador.get('cantidad') or 0),
        'confirmados_sin_asiento': int(sin_asiento.get('cantidad') or 0),
        'diferencia_arqueo': diferencia_arqueo,
        'dias_desde_arqueo': dias_desde_arqueo,
    }
    prioridad_codigo = _prioridad_item(item_base)
    estado_codigo = 'OK' if prioridad_codigo == 'BAJA' else 'OBSERVADO'
    item_base['prioridad_codigo'] = prioridad_codigo
    item_base['estado_codigo'] = estado_codigo
    accion = _accion_sugerida(item_base)

    nombre = master.get('nombre') or ''
    cuenta = master.get('cuenta_contable_codigo') or ''
    moneda = master.get('moneda_codigo') or 'BOB'

    return {
        'nro': nro,
        'medio': medio,
        'medio_label': _medio_label(medio),
        'item_id': item_id,
        'codigo': master.get('codigo') or '',
        'nombre': nombre,
        'unidad': unidad,
        'cuenta': cuenta or 'Sin cuenta',
        'moneda_codigo': moneda,
        'activo': bool(master.get('activo')),
        'activo_label': 'Activo' if master.get('activo') else 'Inactivo',
        'prioridad_codigo': prioridad_codigo,
        'prioridad': PRIORIDAD_LABEL.get(prioridad_codigo, prioridad_codigo),
        'prioridad_orden': PRIORIDAD_ORDEN.get(prioridad_codigo, 9),
        'estado_codigo': estado_codigo,
        'estado_revision': _estado_label(estado_codigo),
        'saldo_sistema': float(saldo_sistema),
        'saldo_sistema_label': format_money(saldo_sistema, moneda),
        'saldo_fisico_label': saldo_fisico_label,
        'diferencia_arqueo': float(diferencia_arqueo),
        'diferencia_arqueo_label': format_money(diferencia_arqueo, moneda),
        'ultimo_arqueo': ultimo_arqueo_label,
        'ultimo_arqueo_estado': ultimo_arqueo_estado,
        'dias_desde_arqueo': dias_desde_arqueo,
        'dias_desde_arqueo_label': 'No aplica' if dias_desde_arqueo is None else f'{dias_desde_arqueo} día(s)',
        'ultimo_movimiento': _date_label(ultimo_movimiento) if ultimo_movimiento else 'Sin movimiento',
        'borradores': int(borrador.get('cantidad') or 0),
        'impacto_borrador': float(_decimal(borrador.get('impacto'))),
        'impacto_borrador_label': format_money(_decimal(borrador.get('impacto')), moneda),
        'confirmados_sin_asiento': int(sin_asiento.get('cantidad') or 0),
        'impacto_sin_asiento': float(_decimal(sin_asiento.get('impacto'))),
        'impacto_sin_asiento_label': format_money(_decimal(sin_asiento.get('impacto')), moneda),
        'accion': accion,
    }


def _consultar_conciliacion(filtros: dict[str, Any], limit_rows: int) -> list[dict[str, Any]]:
    with DatabaseManager() as db:
        maps = {
            'caja_saldos': _get_caja_balance_map(db, filtros['fecha_corte']),
            'banco_saldos': _get_banco_balance_map(db, filtros['fecha_corte']),
            'caja_borradores': _get_operacion_map(db, 'CAJA', filtros['fecha_corte'], 'BORRADOR'),
            'banco_borradores': _get_operacion_map(db, 'BANCO', filtros['fecha_corte'], 'BORRADOR'),
            'caja_sin_asiento': _get_operacion_map(db, 'CAJA', filtros['fecha_corte'], 'CONFIRMADO', asiento_nulo=True),
            'banco_sin_asiento': _get_operacion_map(db, 'BANCO', filtros['fecha_corte'], 'CONFIRMADO', asiento_nulo=True),
            'caja_ultimo_mov': _get_ultimo_movimiento_map(db, 'CAJA', filtros['fecha_corte']),
            'banco_ultimo_mov': _get_ultimo_movimiento_map(db, 'BANCO', filtros['fecha_corte']),
            'arqueos': _get_ultimo_arqueo_map(db, filtros['fecha_corte']),
        }

        masters: list[dict[str, Any]] = []
        if filtros['medio'] in {'TODOS', 'CAJA'}:
            masters.extend(_master_cajas(db, filtros))
        if filtros['medio'] in {'TODOS', 'BANCO'}:
            masters.extend(_master_bancos(db, filtros))

    rows: list[dict[str, Any]] = []
    for master in masters:
        row = _row_from_master(master, maps, filtros, nro=len(rows) + 1)
        if filtros['estado_revision'] == 'OBSERVADOS' and row['estado_codigo'] == 'OK':
            continue
        if filtros['estado_revision'] == 'OK' and row['estado_codigo'] != 'OK':
            continue
        rows.append(row)

    rows.sort(key=lambda item: (item['prioridad_orden'], item['medio'], item['nombre']))
    for index, row in enumerate(rows, start=1):
        row['nro'] = index
    return rows[:limit_rows]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    saldo_total = Decimal('0.00')
    impacto_borrador = Decimal('0.00')
    observados = 0
    criticos = 0
    cajas = 0
    bancos = 0
    sin_asiento = 0
    borradores = 0

    for row in rows:
        saldo_total += _decimal(row.get('saldo_sistema'))
        impacto_borrador += _decimal(row.get('impacto_borrador'))
        if row.get('estado_codigo') != 'OK':
            observados += 1
        if row.get('prioridad_codigo') == 'CRITICA':
            criticos += 1
        if row.get('medio') == 'CAJA':
            cajas += 1
        elif row.get('medio') == 'BANCO':
            bancos += 1
        sin_asiento += int(row.get('confirmados_sin_asiento') or 0)
        borradores += int(row.get('borradores') or 0)

    return {
        'cantidad': len(rows),
        'observados': observados,
        'sin_observacion': max(len(rows) - observados, 0),
        'criticos': criticos,
        'cajas': cajas,
        'bancos': bancos,
        'sin_asiento': sin_asiento,
        'borradores': borradores,
        'saldo_total': float(saldo_total),
        'saldo_total_label': format_money(saldo_total, 'BOB'),
        'impacto_borrador': float(impacto_borrador),
        'impacto_borrador_label': format_money(impacto_borrador, 'BOB'),
        'moneda_unica': 'BOB',
        'moneda_unica_simbolo': 'Bs',
        'moneda_display_note': 'Saldos e impactos expresados según la moneda de cada caja o banco; el resumen global se presenta en Bs. cuando aplica.',
    }


def _summary_cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'kind': 'group',
            'label': 'Ítems revisados',
            'value': summary.get('cantidad', 0),
            'note': f"{summary.get('cajas', 0)} caja(s), {summary.get('bancos', 0)} banco(s)",
        },
        {
            'kind': 'critical',
            'label': 'Críticos',
            'value': summary.get('criticos', 0),
            'note': 'requieren revisión inmediata',
        },
        {
            'kind': 'high',
            'label': 'Observados',
            'value': summary.get('observados', 0),
            'note': 'con acción sugerida',
        },
        {
            'kind': 'medium',
            'label': 'Borradores',
            'value': summary.get('borradores', 0),
            'note': 'operaciones no confirmadas',
        },
        {
            'kind': 'low',
            'label': 'Sin asiento',
            'value': summary.get('sin_asiento', 0),
            'note': 'confirmadas pendientes de asiento',
        },
    ]


def _display_columns() -> list[dict[str, str]]:
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'medio_label', 'label': 'Medio', 'type': 'badge', 'code_key': 'medio', 'align': 'center'},
        {'key': 'estado_revision', 'label': 'Estado', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
        {'key': 'nombre', 'label': 'Caja / banco', 'strong': True},
        {'key': 'unidad', 'label': 'Unidad'},
        {'key': 'saldo_sistema', 'label': 'Saldo sistema', 'type': 'money', 'align': 'right'},
        {'key': 'ultimo_arqueo', 'label': 'Último arqueo', 'align': 'center'},
        {'key': 'diferencia_arqueo', 'label': 'Dif. arqueo', 'type': 'money', 'align': 'right'},
        {'key': 'borradores', 'label': 'Borr.', 'align': 'center'},
        {'key': 'confirmados_sin_asiento', 'label': 'Sin asiento', 'align': 'center'},
        {'key': 'accion', 'label': 'Acción sugerida'},
    ]


def _build_payload(filtros: dict[str, Any], limit_rows: int) -> dict[str, Any]:
    rows = _consultar_conciliacion(filtros, limit_rows)
    summary = _summary(rows)
    return {
        'titulo': 'Conciliación Caja/Banco',
        'descripcion': 'Control operativo de saldos de caja y bancos contra arqueos, borradores y asientos pendientes.',
        'descripcion_periodo': filtros['periodo_label'],
        'unidad_label': filtros['unidad_label'],
        'criterio_reporte': 'Consulta cajas y cuentas bancarias, calcula saldos con operaciones confirmadas hasta la fecha de corte y marca observaciones por arqueos, borradores o asientos faltantes.',
        'fuente_datos': 'contabilidad.caja, cuenta_bancaria, cobro, pago, movimiento_tesoreria y arqueo_caja.',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'filtros': {
            'fecha_corte': filtros['fecha_corte'].isoformat(),
            'medio': filtros['medio'],
            'estado_revision': filtros['estado_revision'],
            'unidad_negocio_id': filtros.get('unidad_negocio_id') or '',
            'dias_sin_arqueo': filtros['dias_sin_arqueo'],
            'incluir_inactivos': '1' if filtros['incluir_inactivos'] else '',
        },
        'columns': _display_columns(),
        'summary': summary,
        'summary_cards': _summary_cards(summary),
        'rows': rows,
        'empty_title': 'No hay cajas o bancos para los filtros seleccionados',
        'empty_icon': 'fas fa-circle-check',
        'medio_label': filtros['medio_label'],
    }


class ConciliacionCajaBancoExport:
    TITLE = 'Conciliación Caja/Banco'
    WORKSHEET_TITLE = 'Conciliacion Caja Banco'
    FILE_SLUG = 'conciliacion_caja_banco'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'saldo_sistema', 'diferencia_arqueo', 'impacto_borrador', 'impacto_sin_asiento'}

    @staticmethod
    def excel_columns():
        return [
            ('prioridad', 'Prioridad', 14),
            ('medio_label', 'Medio', 12),
            ('estado_revision', 'Estado', 18),
            ('codigo', 'Codigo', 18),
            ('nombre', 'Caja / Banco', 34),
            ('unidad', 'Unidad', 30),
            ('cuenta', 'Cuenta contable', 20),
            ('activo_label', 'Activo', 12),
            ('saldo_sistema', 'Saldo sistema', 16),
            ('saldo_fisico_label', 'Saldo fisico / arqueo', 20),
            ('ultimo_arqueo', 'Ultimo arqueo', 16),
            ('ultimo_arqueo_estado', 'Estado arqueo', 16),
            ('dias_desde_arqueo_label', 'Dias desde arqueo', 18),
            ('diferencia_arqueo', 'Diferencia arqueo', 18),
            ('ultimo_movimiento', 'Ultimo movimiento', 18),
            ('borradores', 'Borradores', 12),
            ('impacto_borrador', 'Impacto borrador', 18),
            ('confirmados_sin_asiento', 'Sin asiento', 12),
            ('impacto_sin_asiento', 'Impacto sin asiento', 18),
            ('accion', 'Accion sugerida', 48),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Ítems: {summary.get('cantidad', 0)} · "
            f"Críticos: {summary.get('criticos', 0)} · "
            f"Observados: {summary.get('observados', 0)} · "
            f"Borradores: {summary.get('borradores', 0)} · "
            f"Sin asiento: {summary.get('sin_asiento', 0)}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Prioridad', 'width': 20, 'align': 'center'},
            {'label': 'Medio', 'width': 16, 'align': 'center'},
            {'label': 'Estado', 'width': 24, 'align': 'center'},
            {'label': 'Caja / Banco', 'width': 46, 'align': 'left'},
            {'label': 'Unidad', 'width': 34, 'align': 'left'},
            {'label': 'Saldo sistema', 'width': 24, 'align': 'right'},
            {'label': 'Último arqueo', 'width': 22, 'align': 'center'},
            {'label': 'Dif. arqueo', 'width': 24, 'align': 'right'},
            {'label': 'Borr.', 'width': 14, 'align': 'center'},
            {'label': 'Sin asiento', 'width': 20, 'align': 'center'},
            {'label': 'Acción sugerida', 'width': 58, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('prioridad', ''),
                item.get('medio_label', ''),
                item.get('estado_revision', ''),
                item.get('nombre', ''),
                item.get('unidad', ''),
                item.get('saldo_sistema_label', ''),
                item.get('ultimo_arqueo', ''),
                item.get('diferencia_arqueo_label', ''),
                str(item.get('borradores', 0)),
                str(item.get('confirmados_sin_asiento', 0)),
                item.get('accion', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['', '', '', 'Límite PDF', '', '', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} registros. Use Excel para el detalle completo.'])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"{payload.get('descripcion_periodo', '')}. "
            f"Unidad: {payload.get('unidad_label', '')}. "
            f"Medio: {payload.get('medio_label', '')}. "
            f"Ítems: {summary.get('cantidad', 0)}. "
            f"Observados: {summary.get('observados', 0)}. "
            f"Borradores: {summary.get('borradores', 0)}. "
            f"Sin asiento: {summary.get('sin_asiento', 0)}."
        )


# ============================================================
# Rutas
# ============================================================


@conciliacion_caja_banco_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return render_template(
        'conciliacion_caja_banco_index.html',
        fecha_corte=date.today().isoformat(),
        medios=MEDIOS,
        estados_revision=ESTADOS_REVISION,
        dias_arqueo=DIAS_ARQUEO,
        unidades_negocio=obtener_unidades_negocio(),
    )


@conciliacion_caja_banco_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_conciliacion_caja_banco():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar la conciliación caja/banco. {exc}', 500)


@conciliacion_caja_banco_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_conciliacion_caja_banco():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        excel_bytes = build_excel(ConciliacionCajaBancoExport, payload)
        nombre = f"conciliacion_caja_banco_{filtros['fecha_corte'].strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el Excel de conciliación caja/banco. {exc}', 500)


@conciliacion_caja_banco_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_conciliacion_caja_banco():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(ConciliacionCajaBancoExport, payload)
        nombre = f"conciliacion_caja_banco_{filtros['fecha_corte'].strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF de conciliación caja/banco. {exc}', 500)


@conciliacion_caja_banco_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('conciliacion_caja_banco_help.html')
