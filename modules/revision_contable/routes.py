# ============================================================
# DXT CONTA - Modulo Revision Contable
# Centro de control de pendientes e inconsistencias contables
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Response, jsonify, render_template, request

from database.db_manager import DatabaseManager
from modules.reportes_rapidos.core.catalogos import obtener_unidades_negocio, unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import format_money
from modules.revision_contable import revision_contable_bp
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]

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

MESES = [
    {'value': '0', 'label': 'Toda la gestión'},
    {'value': '1', 'label': 'Enero'},
    {'value': '2', 'label': 'Febrero'},
    {'value': '3', 'label': 'Marzo'},
    {'value': '4', 'label': 'Abril'},
    {'value': '5', 'label': 'Mayo'},
    {'value': '6', 'label': 'Junio'},
    {'value': '7', 'label': 'Julio'},
    {'value': '8', 'label': 'Agosto'},
    {'value': '9', 'label': 'Septiembre'},
    {'value': '10', 'label': 'Octubre'},
    {'value': '11', 'label': 'Noviembre'},
    {'value': '12', 'label': 'Diciembre'},
]


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


def _month_range(gestion: int, mes: int) -> tuple[date, date]:
    if mes == 0:
        return date(gestion, 1, 1), date(gestion, 12, 31)
    if mes < 1 or mes > 12:
        raise ValueError('El mes seleccionado no es válido.')
    inicio = date(gestion, mes, 1)
    if mes == 12:
        fin = date(gestion, 12, 31)
    else:
        fin = date(gestion, mes + 1, 1).replace(day=1)
        fin = date.fromordinal(fin.toordinal() - 1)
    return inicio, fin


def _periodo_label(gestion: int, mes: int, fecha_desde: date, fecha_hasta: date) -> str:
    if mes == 0:
        return f'Gestión {gestion}'
    mes_label = next((item['label'] for item in MESES if item['value'] == str(mes)), '')
    return f'{mes_label} {gestion} · {fecha_desde.strftime("%d/%m/%Y")} al {fecha_hasta.strftime("%d/%m/%Y")}'


def _db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    return [dict(row) for row in rows]


def _obtener_gestiones() -> list[int]:
    sql = """
        SELECT gestion
        FROM (
            SELECT gestion::int AS gestion FROM contabilidad.gestion_control
            UNION
            SELECT EXTRACT(YEAR FROM fecha)::int AS gestion FROM contabilidad.asiento
            UNION
            SELECT EXTRACT(YEAR FROM CURRENT_DATE)::int AS gestion
        ) q
        WHERE gestion IS NOT NULL
        ORDER BY gestion DESC
    """
    rows = _db_rows(sql)
    return [int(row['gestion']) for row in rows]


def _gestion_preferida() -> int:
    sql = """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
    """
    rows = _db_rows(sql)
    if rows:
        return int(rows[0]['gestion'])
    return date.today().year


def _parse_filters(args) -> dict[str, Any]:
    gestion = _parse_int(args.get('gestion') or _gestion_preferida(), 'Gestión')
    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestión indicada no es válida.')

    mes = _parse_int(args.get('mes') or 0, 'Mes')
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')
    fecha_desde, fecha_hasta = _month_range(gestion, mes)
    return {
        'gestion': gestion,
        'mes': mes,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
        'periodo_label': _periodo_label(gestion, mes, fecha_desde, fecha_hasta),
        'unidad_label': unidad_label(unidad_negocio_id),
    }


def _unit_filter(alias: str = 'x') -> str:
    return f'(%s IS NULL OR {alias}.unidad_negocio_id = %s)'


def _base_params(filtros: dict[str, Any]) -> tuple[Any, ...]:
    return (
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        filtros['unidad_negocio_id'],
        filtros['unidad_negocio_id'],
    )


def _append_row(rows: list[dict[str, Any]], *, prioridad_codigo: str, categoria: str, fecha: Any,
                origen: str, referencia: str, detalle: str, estado: str, unidad: str, monto: Any = 0,
                moneda_codigo: str = 'BOB', impacto: str = '', accion: str = '') -> None:
    monto_dec = _decimal(monto)
    rows.append({
        'nro': len(rows) + 1,
        'prioridad_codigo': prioridad_codigo,
        'prioridad': PRIORIDAD_LABEL.get(prioridad_codigo, prioridad_codigo.title()),
        'prioridad_orden': PRIORIDAD_ORDEN.get(prioridad_codigo, 9),
        'categoria': categoria,
        'fecha': fecha.isoformat() if isinstance(fecha, date) else _clean(fecha),
        'fecha_label': _date_label(fecha),
        'origen': origen,
        'referencia': referencia,
        'detalle': detalle,
        'estado': estado,
        'estado_codigo': estado,
        'unidad': unidad or 'Sin unidad',
        'monto': float(monto_dec),
        'monto_label': format_money(monto_dec, moneda_codigo or 'BOB'),
        'moneda_codigo': moneda_codigo or 'BOB',
        'impacto': impacto,
        'accion': accion,
    })


# ============================================================
# Consultas de revisión
# ============================================================


def _check_gestion_control(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = """
        SELECT
            gestion,
            estado::text AS estado,
            comprobante_cierre_id,
            fecha_cierre,
            comprobante_apertura_id,
            fecha_apertura
        FROM contabilidad.gestion_control
        WHERE gestion = %s
        LIMIT 1
    """
    result = _db_rows(sql, (filtros['gestion'],))
    if not result:
        _append_row(
            rows,
            prioridad_codigo='ALTA',
            categoria='Control de gestión',
            fecha=None,
            origen='Gestión',
            referencia=f'Gestión {filtros["gestion"]}',
            detalle='La gestión no está registrada en gestion_control.',
            estado='SIN CONTROL',
            unidad='Todas las unidades',
            impacto='Puede afectar validaciones de cierre, apertura y bloqueo operativo.',
            accion='Registrar o revisar la configuración inicial de la gestión.',
        )
        return

    estado = result[0].get('estado') or ''
    if estado == 'CERRADA':
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Control de gestión',
            fecha=result[0].get('fecha_cierre'),
            origen='Gestión',
            referencia=f'Gestión {filtros["gestion"]}',
            detalle='La gestión consultada está cerrada.',
            estado=estado,
            unidad='Todas las unidades',
            impacto='Las correcciones directas no deberían realizarse sin reapertura o ajuste formal.',
            accion='Usar la información solo como revisión o aplicar el procedimiento de reapertura/ajuste si corresponde.',
        )


def _check_asientos_descuadrados(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        SELECT
            a.id,
            a.fecha,
            COALESCE(a.referencia, 'Asiento #' || a.id::text) AS referencia,
            COALESCE(a.glosa, '') AS glosa,
            a.estado::text AS estado,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad') AS unidad,
            a.moneda_codigo,
            COALESCE(SUM(ad.debe), 0)::numeric(18,2) AS total_debe,
            COALESCE(SUM(ad.haber), 0)::numeric(18,2) AS total_haber,
            ABS(COALESCE(SUM(ad.debe), 0) - COALESCE(SUM(ad.haber), 0))::numeric(18,2) AS diferencia
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND {_unit_filter('a')}
        GROUP BY a.id, a.fecha, a.referencia, a.glosa, a.estado, un.codigo, un.nombre, a.moneda_codigo
        HAVING ABS(COALESCE(SUM(ad.debe), 0) - COALESCE(SUM(ad.haber), 0)) > 0.01
        ORDER BY a.fecha DESC, a.id DESC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Asiento descuadrado',
            fecha=row.get('fecha'),
            origen='Comprobantes',
            referencia=row.get('referencia') or '',
            detalle=f"Debe {format_money(row.get('total_debe'), row.get('moneda_codigo'))} / Haber {format_money(row.get('total_haber'), row.get('moneda_codigo'))}. {row.get('glosa') or ''}",
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=row.get('diferencia'),
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='El balance y los reportes pueden quedar inconsistentes.',
            accion='Corregir el comprobante hasta que el Debe sea igual al Haber.',
        )


def _check_asientos_sin_detalle(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        SELECT
            a.id,
            a.fecha,
            COALESCE(a.referencia, 'Asiento #' || a.id::text) AS referencia,
            COALESCE(a.glosa, '') AS glosa,
            a.estado::text AS estado,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad') AS unidad,
            a.moneda_codigo
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND {_unit_filter('a')}
          AND NOT EXISTS (
              SELECT 1
              FROM contabilidad.asiento_detalle ad
              WHERE ad.asiento_id = a.id
          )
        ORDER BY a.fecha DESC, a.id DESC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Asiento incompleto',
            fecha=row.get('fecha'),
            origen='Comprobantes',
            referencia=row.get('referencia') or '',
            detalle=row.get('glosa') or 'Asiento sin líneas de detalle.',
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='El comprobante no tiene efecto contable verificable.',
            accion='Completar el detalle del asiento o anularlo si no corresponde.',
        )


def _check_borradores(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        WITH asiento_totales AS (
            SELECT asiento_id, SUM(COALESCE(debe, 0))::numeric(18,2) AS monto
            FROM contabilidad.asiento_detalle
            GROUP BY asiento_id
        ), operaciones AS (
            SELECT
                a.fecha,
                'Asiento contable'::text AS origen,
                COALESCE(a.referencia, 'Asiento #' || a.id::text)::text AS referencia,
                COALESCE(a.glosa, '')::text AS detalle,
                a.estado::text AS estado,
                a.unidad_negocio_id,
                COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad')::text AS unidad,
                a.moneda_codigo::text AS moneda_codigo,
                COALESCE(at.monto, 0)::numeric(18,2) AS monto
            FROM contabilidad.asiento a
            LEFT JOIN asiento_totales at ON at.asiento_id = a.id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
            WHERE a.estado::text = 'BORRADOR'

            UNION ALL
            SELECT p.fecha, 'Pago', COALESCE(p.referencia, 'Pago #' || p.id::text), COALESCE(p.glosa, ''),
                   p.estado::text, p.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   p.moneda_codigo::text, COALESCE(p.monto_total, 0)::numeric(18,2)
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE p.estado::text = 'BORRADOR'

            UNION ALL
            SELECT c.fecha, 'Cobro', COALESCE(c.referencia, 'Cobro #' || c.id::text), COALESCE(c.glosa, ''),
                   c.estado::text, c.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   c.moneda_codigo::text, COALESCE(c.monto_total, 0)::numeric(18,2)
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE c.estado::text = 'BORRADOR'

            UNION ALL
            SELECT cp.fecha, 'Compra', COALESCE(cp.numero_factura, 'Compra #' || cp.id::text), COALESCE(cp.glosa, ''),
                   cp.estado::text, cp.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   cp.moneda_codigo::text, COALESCE(cp.total, 0)::numeric(18,2)
            FROM contabilidad.compra cp
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = cp.unidad_negocio_id
            WHERE cp.estado::text = 'BORRADOR'

            UNION ALL
            SELECT v.fecha, 'Venta', COALESCE(v.numero_factura_ext, 'Venta #' || v.id::text), COALESCE(v.glosa, ''),
                   v.estado::text, v.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   v.moneda_codigo::text, COALESCE(v.total, 0)::numeric(18,2)
            FROM contabilidad.venta v
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = v.unidad_negocio_id
            WHERE v.estado::text = 'BORRADOR'

            UNION ALL
            SELECT mt.fecha, 'Movimiento tesorería', COALESCE(mt.referencia, 'Movimiento #' || mt.id::text), COALESCE(mt.glosa, ''),
                   mt.estado::text, mt.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   mt.moneda_codigo::text, COALESCE(mt.monto, 0)::numeric(18,2)
            FROM contabilidad.movimiento_tesoreria mt
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = mt.unidad_negocio_id
            WHERE mt.estado::text = 'BORRADOR'
        )
        SELECT *
        FROM operaciones op
        WHERE op.fecha BETWEEN %s AND %s
          AND (%s IS NULL OR op.unidad_negocio_id = %s)
        ORDER BY op.fecha DESC, op.origen ASC, op.referencia ASC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        _append_row(
            rows,
            prioridad_codigo='ALTA',
            categoria='Operación en borrador',
            fecha=row.get('fecha'),
            origen=row.get('origen') or '',
            referencia=row.get('referencia') or '',
            detalle=row.get('detalle') or '',
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=row.get('monto'),
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='La operación puede no estar afectando definitivamente la contabilidad.',
            accion='Confirmar, completar o anular según corresponda.',
        )


def _check_confirmados_sin_asiento(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        WITH operaciones AS (
            SELECT p.fecha, 'Pago'::text AS origen, COALESCE(p.referencia, 'Pago #' || p.id::text)::text AS referencia,
                   COALESCE(p.glosa, '')::text AS detalle, p.estado::text AS estado, p.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad')::text AS unidad,
                   p.moneda_codigo::text AS moneda_codigo, COALESCE(p.monto_total, 0)::numeric(18,2) AS monto
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE p.estado::text = 'CONFIRMADO' AND p.asiento_id IS NULL

            UNION ALL
            SELECT c.fecha, 'Cobro', COALESCE(c.referencia, 'Cobro #' || c.id::text), COALESCE(c.glosa, ''),
                   c.estado::text, c.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   c.moneda_codigo::text, COALESCE(c.monto_total, 0)::numeric(18,2)
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE c.estado::text = 'CONFIRMADO' AND c.asiento_id IS NULL

            UNION ALL
            SELECT cp.fecha, 'Compra', COALESCE(cp.numero_factura, 'Compra #' || cp.id::text), COALESCE(cp.glosa, ''),
                   cp.estado::text, cp.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   cp.moneda_codigo::text, COALESCE(cp.total, 0)::numeric(18,2)
            FROM contabilidad.compra cp
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = cp.unidad_negocio_id
            WHERE cp.estado::text = 'CONFIRMADO' AND cp.asiento_id IS NULL

            UNION ALL
            SELECT v.fecha, 'Venta', COALESCE(v.numero_factura_ext, 'Venta #' || v.id::text), COALESCE(v.glosa, ''),
                   v.estado::text, v.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   v.moneda_codigo::text, COALESCE(v.total, 0)::numeric(18,2)
            FROM contabilidad.venta v
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = v.unidad_negocio_id
            WHERE v.estado::text = 'CONFIRMADO' AND v.asiento_id IS NULL

            UNION ALL
            SELECT mt.fecha, 'Movimiento tesorería', COALESCE(mt.referencia, 'Movimiento #' || mt.id::text), COALESCE(mt.glosa, ''),
                   mt.estado::text, mt.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad'),
                   mt.moneda_codigo::text, COALESCE(mt.monto, 0)::numeric(18,2)
            FROM contabilidad.movimiento_tesoreria mt
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = mt.unidad_negocio_id
            WHERE mt.estado::text = 'CONFIRMADO' AND mt.asiento_id IS NULL
        )
        SELECT *
        FROM operaciones op
        WHERE op.fecha BETWEEN %s AND %s
          AND (%s IS NULL OR op.unidad_negocio_id = %s)
        ORDER BY op.fecha DESC, op.origen ASC, op.referencia ASC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Confirmado sin asiento',
            fecha=row.get('fecha'),
            origen=row.get('origen') or '',
            referencia=row.get('referencia') or '',
            detalle=row.get('detalle') or '',
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=row.get('monto'),
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='La operación está confirmada, pero puede no estar reflejada contablemente.',
            accion='Revisar el módulo de origen y generar/asociar el asiento correspondiente.',
        )


def _check_detalles_con_cuenta_no_valida(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        SELECT
            a.fecha,
            COALESCE(a.referencia, 'Asiento #' || a.id::text) AS referencia,
            a.estado::text AS estado,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad') AS unidad,
            a.moneda_codigo,
            ad.cuenta_codigo,
            COALESCE(c.nombre, 'Cuenta no encontrada') AS cuenta_nombre,
            COALESCE(c.activo, FALSE) AS cuenta_activa,
            COALESCE(c.es_postable, FALSE) AS es_postable,
            GREATEST(COALESCE(ad.debe, 0), COALESCE(ad.haber, 0))::numeric(18,2) AS monto
        FROM contabilidad.asiento_detalle ad
        JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND {_unit_filter('a')}
          AND (c.codigo IS NULL OR c.activo IS DISTINCT FROM TRUE OR c.es_postable IS DISTINCT FROM TRUE)
        ORDER BY a.fecha DESC, a.id DESC, ad.secuencia ASC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        condicion = 'no postable'
        if not row.get('cuenta_activa'):
            condicion = 'inactiva'
        if not row.get('es_postable') and not row.get('cuenta_activa'):
            condicion = 'inactiva/no postable'
        _append_row(
            rows,
            prioridad_codigo='ALTA',
            categoria='Cuenta no válida',
            fecha=row.get('fecha'),
            origen='Comprobantes',
            referencia=row.get('referencia') or '',
            detalle=f"Cuenta {row.get('cuenta_codigo')} · {row.get('cuenta_nombre')} ({condicion}).",
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=row.get('monto'),
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='El movimiento usa una cuenta que no debería recibir imputaciones directas.',
            accion='Cambiar por una cuenta activa y postable.',
        )


def _check_detalles_requisitos(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        SELECT
            a.fecha,
            COALESCE(a.referencia, 'Asiento #' || a.id::text) AS referencia,
            a.estado::text AS estado,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad') AS unidad,
            a.moneda_codigo,
            ad.cuenta_codigo,
            COALESCE(c.nombre, '') AS cuenta_nombre,
            c.requiere_auxiliar,
            c.requiere_cc,
            ad.auxiliar_id,
            ad.centro_costo_id,
            GREATEST(COALESCE(ad.debe, 0), COALESCE(ad.haber, 0))::numeric(18,2) AS monto
        FROM contabilidad.asiento_detalle ad
        JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND {_unit_filter('a')}
          AND c.activo = TRUE
          AND c.es_postable = TRUE
          AND (
              (c.requiere_auxiliar = TRUE AND ad.auxiliar_id IS NULL)
              OR (c.requiere_cc = TRUE AND ad.centro_costo_id IS NULL)
          )
        ORDER BY a.fecha DESC, a.id DESC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        faltantes = []
        if row.get('requiere_auxiliar') and row.get('auxiliar_id') is None:
            faltantes.append('auxiliar')
        if row.get('requiere_cc') and row.get('centro_costo_id') is None:
            faltantes.append('centro de costo')
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Dato requerido faltante',
            fecha=row.get('fecha'),
            origen='Comprobantes',
            referencia=row.get('referencia') or '',
            detalle=f"Cuenta {row.get('cuenta_codigo')} · {row.get('cuenta_nombre')}. Falta: {', '.join(faltantes)}.",
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=row.get('monto'),
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='Los auxiliares o centros de costo pueden quedar incompletos en reportes y análisis.',
            accion='Completar el dato requerido en el detalle del asiento.',
        )



def _check_documentos_cobrar(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    """Valida consistencia operativa de documentos por cobrar."""
    sql = """
        SELECT
            d.id,
            d.fecha_documento AS fecha,
            d.numero_documento,
            d.tipo_documento,
            d.origen_documento,
            d.tratamiento_contable,
            d.gestion_origen,
            d.estado,
            d.moneda_codigo,
            d.importe_total,
            d.importe_cobrado,
            d.saldo_pendiente,
            d.asiento_registro_id,
            d.factura_electronica_id,
            d.cliente_nombre,
            d.unidad_negocio_id,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad') AS unidad,
            ABS(COALESCE(d.saldo_pendiente, 0) - GREATEST(COALESCE(d.importe_total, 0) - COALESCE(d.importe_cobrado, 0), 0))::numeric(18,2) AS diferencia_saldo
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        WHERE d.fecha_documento BETWEEN %s AND %s
          AND COALESCE(d.activo, TRUE) = TRUE
          AND COALESCE(d.estado, '') <> 'ANULADO'
          AND (%s IS NULL OR d.unidad_negocio_id = %s)
          AND (
                ABS(COALESCE(d.saldo_pendiente, 0) - GREATEST(COALESCE(d.importe_total, 0) - COALESCE(d.importe_cobrado, 0), 0)) > 0.01
                OR (COALESCE(d.tratamiento_contable, '') <> 'CARTERA_HISTORICA' AND d.factura_electronica_id IS NULL AND d.asiento_registro_id IS NULL)
                OR (COALESCE(d.tratamiento_contable, '') = 'CARTERA_HISTORICA' AND d.asiento_registro_id IS NOT NULL)
                OR (d.gestion_origen > %s)
                OR (COALESCE(d.saldo_pendiente, 0) <= 0.01 AND COALESCE(d.estado, '') <> 'COBRADO')
                OR (COALESCE(d.saldo_pendiente, 0) > 0.01 AND COALESCE(d.estado, '') = 'COBRADO')
          )
        ORDER BY d.fecha_documento DESC, d.id DESC
        LIMIT %s
    """
    params = _base_params(filtros) + (filtros['gestion'], MAX_ROWS_SCREEN)
    for row in _db_rows(sql, params):
        referencia = f"{row.get('tipo_documento') or 'DOC'} {row.get('numero_documento') or row.get('id')} · {row.get('cliente_nombre') or 'Sin cliente'}"
        tratamiento = row.get('tratamiento_contable') or ''
        prioridad = 'ALTA'
        detalle = []
        accion = []
        monto = row.get('saldo_pendiente')
        if _decimal(row.get('diferencia_saldo')) > Decimal('0.01'):
            prioridad = 'CRITICA'
            detalle.append('El saldo pendiente no coincide con importe total menos importe cobrado.')
            accion.append('Recalcular o corregir importes del documento antes de usarlo en reportes/cobros.')
            monto = row.get('diferencia_saldo')
        if tratamiento != 'CARTERA_HISTORICA' and not row.get('factura_electronica_id') and not row.get('asiento_registro_id'):
            prioridad = 'CRITICA'
            detalle.append('Documento vigente manual sin asiento de registro asociado.')
            accion.append('Revisar el registro del documento y generar/vincular el asiento contable correspondiente.')
        if tratamiento == 'CARTERA_HISTORICA' and row.get('asiento_registro_id'):
            detalle.append('Documento histórico con asiento de registro asociado; la regla histórica no debe registrar asiento al alta.')
            accion.append('Verificar si corresponde anular/reclasificar el asiento de registro.')
        if int(row.get('gestion_origen') or 0) > int(filtros['gestion']):
            prioridad = 'CRITICA'
            detalle.append('Documento con gestión de origen futura respecto a la gestión revisada.')
            accion.append('Corregir gestión de origen o anular el registro si no corresponde.')
        if _decimal(row.get('saldo_pendiente')) <= Decimal('0.01') and (row.get('estado') or '') != 'COBRADO':
            detalle.append('Saldo agotado con estado distinto de COBRADO.')
            accion.append('Actualizar estado operativo del documento.')
        if _decimal(row.get('saldo_pendiente')) > Decimal('0.01') and (row.get('estado') or '') == 'COBRADO':
            prioridad = 'CRITICA'
            detalle.append('Documento marcado como COBRADO con saldo pendiente mayor a cero.')
            accion.append('Corregir estado o aplicaciones de cobro.')
        _append_row(
            rows,
            prioridad_codigo=prioridad,
            categoria='Documento por cobrar',
            fecha=row.get('fecha'),
            origen='Documentos CxC',
            referencia=referencia,
            detalle=' '.join(detalle),
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=monto,
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='Puede afectar cartera, cobros y consistencia de reportes auxiliares.',
            accion=' '.join(accion),
        )

def _check_compromisos_vencidos(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = """
        SELECT
            cd.fecha_vencimiento AS fecha,
            c.tipo,
            c.codigo,
            c.nombre,
            cd.estado::text AS estado,
            c.unidad_negocio_id,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad') AS unidad,
            GREATEST(COALESCE(cd.monto_programado, 0) - COALESCE(cd.monto_registrado, 0), 0)::numeric(18,2) AS saldo
        FROM contabilidad.compromiso_detalle cd
        JOIN contabilidad.compromiso c ON c.id = cd.compromiso_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        WHERE c.activo = TRUE
          AND cd.estado::text = 'PENDIENTE'
          AND cd.fecha_vencimiento < LEAST(%s::date, CURRENT_DATE)
          AND c.gestion = %s
          AND (%s IS NULL OR c.unidad_negocio_id = %s)
        ORDER BY cd.fecha_vencimiento ASC, c.tipo ASC, c.codigo ASC
        LIMIT %s
    """
    params = (
        filtros['fecha_hasta'],
        filtros['gestion'],
        filtros['unidad_negocio_id'],
        filtros['unidad_negocio_id'],
        MAX_ROWS_SCREEN,
    )
    for row in _db_rows(sql, params):
        tipo = row.get('tipo') or ''
        _append_row(
            rows,
            prioridad_codigo='ALTA',
            categoria='Compromiso vencido',
            fecha=row.get('fecha'),
            origen='Compromisos',
            referencia=f"{row.get('codigo') or ''} · {row.get('nombre') or ''}".strip(' ·'),
            detalle=f"Compromiso por {tipo.lower()} pendiente de registro.",
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=row.get('saldo'),
            moneda_codigo='BOB',
            impacto='Puede existir una obligación o derecho pendiente de atender.',
            accion='Revisar el compromiso y registrar el pago/cobro si corresponde.',
        )


def _check_unidades_inactivas(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        WITH operaciones AS (
            SELECT a.fecha, 'Asiento contable'::text AS origen, COALESCE(a.referencia, 'Asiento #' || a.id::text)::text AS referencia,
                   COALESCE(a.glosa, '')::text AS detalle, a.estado::text AS estado, a.unidad_negocio_id,
                   COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Unidad inactiva')::text AS unidad,
                   a.moneda_codigo::text AS moneda_codigo, 0::numeric(18,2) AS monto, un.activo AS unidad_activa
            FROM contabilidad.asiento a
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
            WHERE a.estado::text <> 'ANULADO'

            UNION ALL
            SELECT p.fecha, 'Pago', COALESCE(p.referencia, 'Pago #' || p.id::text), COALESCE(p.glosa, ''),
                   p.estado::text, p.unidad_negocio_id, COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Unidad inactiva'),
                   p.moneda_codigo::text, COALESCE(p.monto_total, 0)::numeric(18,2), un.activo
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE p.estado::text <> 'ANULADO'

            UNION ALL
            SELECT c.fecha, 'Cobro', COALESCE(c.referencia, 'Cobro #' || c.id::text), COALESCE(c.glosa, ''),
                   c.estado::text, c.unidad_negocio_id, COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Unidad inactiva'),
                   c.moneda_codigo::text, COALESCE(c.monto_total, 0)::numeric(18,2), un.activo
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE c.estado::text <> 'ANULADO'
        )
        SELECT *
        FROM operaciones op
        WHERE op.fecha BETWEEN %s AND %s
          AND (%s IS NULL OR op.unidad_negocio_id = %s)
          AND op.unidad_activa IS DISTINCT FROM TRUE
        ORDER BY op.fecha DESC, op.origen ASC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Unidad inactiva',
            fecha=row.get('fecha'),
            origen=row.get('origen') or '',
            referencia=row.get('referencia') or '',
            detalle=row.get('detalle') or '',
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            monto=row.get('monto'),
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='La operación puede aparecer en una unidad que ya no debería operar.',
            accion='Revisar si la unidad debe reactivarse o corregir la operación.',
        )


def _check_glosas_vacias(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    sql = f"""
        SELECT
            a.fecha,
            COALESCE(a.referencia, 'Asiento #' || a.id::text) AS referencia,
            a.estado::text AS estado,
            COALESCE(un.codigo || ' · ' || un.nombre, un.nombre, 'Sin unidad') AS unidad,
            a.moneda_codigo,
            COALESCE(a.glosa, '') AS glosa
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND {_unit_filter('a')}
          AND LENGTH(TRIM(COALESCE(a.glosa, ''))) < 6
        ORDER BY a.fecha DESC, a.id DESC
        LIMIT %s
    """
    for row in _db_rows(sql, _base_params(filtros) + (MAX_ROWS_SCREEN,)):
        _append_row(
            rows,
            prioridad_codigo='BAJA',
            categoria='Glosa insuficiente',
            fecha=row.get('fecha'),
            origen='Comprobantes',
            referencia=row.get('referencia') or '',
            detalle='El asiento tiene glosa vacía o demasiado breve.',
            estado=row.get('estado') or '',
            unidad=row.get('unidad') or '',
            moneda_codigo=row.get('moneda_codigo') or 'BOB',
            impacto='La revisión futura del comprobante puede ser menos clara.',
            accion='Completar una glosa operativa y verificable.',
        )


def _build_rows(filtros: dict[str, Any], limit_rows: int = MAX_ROWS_SCREEN) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _check_gestion_control(rows, filtros)
    _check_asientos_descuadrados(rows, filtros)
    _check_asientos_sin_detalle(rows, filtros)
    _check_confirmados_sin_asiento(rows, filtros)
    _check_borradores(rows, filtros)
    _check_detalles_con_cuenta_no_valida(rows, filtros)
    _check_detalles_requisitos(rows, filtros)
    _check_compromisos_vencidos(rows, filtros)
    _check_documentos_cobrar(rows, filtros)
    _check_unidades_inactivas(rows, filtros)
    _check_glosas_vacias(rows, filtros)

    rows.sort(key=lambda item: (item.get('prioridad_orden', 9), item.get('fecha') or '9999-12-31', item.get('origen') or ''))
    for idx, row in enumerate(rows[:limit_rows], start=1):
        row['nro'] = idx
    return rows[:limit_rows]


# ============================================================
# Payload y exportadores
# ============================================================


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        'cantidad': len(rows),
        'criticas': 0,
        'altas': 0,
        'medias': 0,
        'bajas': 0,
        'estado_general': 'Sin alertas',
        'total_general': 0.0,
        'total_general_label': 'Sin importe',
        'totales_por_moneda': [],
        'moneda_display_note': 'Importes expresados en la moneda original de cada operación',
    }
    totales: dict[str, Decimal] = {}
    for row in rows:
        prioridad = row.get('prioridad_codigo') or ''
        if prioridad == 'CRITICA':
            summary['criticas'] += 1
        elif prioridad == 'ALTA':
            summary['altas'] += 1
        elif prioridad == 'MEDIA':
            summary['medias'] += 1
        else:
            summary['bajas'] += 1
        moneda = row.get('moneda_codigo') or ''
        monto = _decimal(row.get('monto'))
        if moneda and monto:
            totales[moneda] = totales.get(moneda, Decimal('0.00')) + monto

    if summary['criticas']:
        summary['estado_general'] = 'Revisión crítica'
    elif summary['altas']:
        summary['estado_general'] = 'Pendientes prioritarios'
    elif summary['medias'] or summary['bajas']:
        summary['estado_general'] = 'Revisión operativa'

    summary['totales_por_moneda'] = [
        {'moneda_codigo': moneda, 'total': float(total), 'total_label': format_money(total, moneda)}
        for moneda, total in sorted(totales.items())
    ]
    if len(summary['totales_por_moneda']) == 1:
        summary['total_general_label'] = summary['totales_por_moneda'][0]['total_label']
        summary['total_general'] = summary['totales_por_moneda'][0]['total']
    elif len(summary['totales_por_moneda']) > 1:
        summary['total_general_label'] = 'Por moneda'
    return summary


def _summary_cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {'label': 'Alertas', 'value': summary.get('cantidad', 0), 'note': summary.get('estado_general', ''), 'kind': 'group'},
        {'label': 'Críticas', 'value': summary.get('criticas', 0), 'note': 'Corregir primero', 'kind': 'critical'},
        {'label': 'Altas', 'value': summary.get('altas', 0), 'note': 'Prioridad operativa', 'kind': 'high'},
        {'label': 'Medias', 'value': summary.get('medias', 0), 'note': 'Revisión recomendada', 'kind': 'medium'},
        {'label': 'Bajas', 'value': summary.get('bajas', 0), 'note': 'Mejora de calidad', 'kind': 'low'},
    ]


def _display_columns() -> list[dict[str, str]]:
    return [
        {'key': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo', 'align': 'center'},
        {'key': 'categoria', 'label': 'Categoría', 'align': 'left'},
        {'key': 'fecha_label', 'label': 'Fecha', 'align': 'center'},
        {'key': 'origen', 'label': 'Origen', 'align': 'left'},
        {'key': 'referencia', 'label': 'Referencia', 'align': 'left'},
        {'key': 'detalle', 'label': 'Detalle observado', 'align': 'left', 'strong': True},
        {'key': 'estado', 'label': 'Estado', 'type': 'badge', 'code_key': 'estado_codigo', 'align': 'center'},
        {'key': 'unidad', 'label': 'Unidad', 'align': 'left'},
        {'key': 'monto', 'label': 'Monto', 'type': 'money', 'align': 'right'},
        {'key': 'accion', 'label': 'Acción sugerida', 'align': 'left'},
    ]


def _build_payload(filtros: dict[str, Any], limit_rows: int = MAX_ROWS_SCREEN) -> dict[str, Any]:
    rows = _build_rows(filtros, limit_rows=limit_rows)
    summary = _summary(rows)
    return {
        'titulo': 'Revisión Contable',
        'descripcion': 'Alertas y pendientes contables detectados automáticamente.',
        'descripcion_periodo': filtros['periodo_label'],
        'unidad_label': filtros['unidad_label'],
        'criterio_reporte': 'Incluye asientos descuadrados, borradores, operaciones confirmadas sin asiento, documentos por cobrar observados, cuentas no válidas, datos requeridos faltantes y compromisos vencidos.',
        'fuente_datos': 'Tablas contables y operativas existentes de DXT-CONTA.',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'filtros': {
            'gestion': filtros['gestion'],
            'mes': filtros['mes'],
            'fecha_desde': filtros['fecha_desde'].isoformat(),
            'fecha_hasta': filtros['fecha_hasta'].isoformat(),
            'unidad_negocio_id': filtros.get('unidad_negocio_id') or '',
        },
        'columns': _display_columns(),
        'summary': summary,
        'summary_cards': _summary_cards(summary),
        'rows': rows,
        'empty_title': 'No se detectaron alertas para los filtros seleccionados',
        'empty_icon': 'fas fa-circle-check',
    }


class RevisionContableExport:
    TITLE = 'Revisión Contable'
    WORKSHEET_TITLE = 'Revision Contable'
    FILE_SLUG = 'revision_contable'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'monto'}

    @staticmethod
    def excel_columns():
        return [
            ('prioridad', 'Prioridad', 16),
            ('categoria', 'Categoria', 24),
            ('fecha_label', 'Fecha', 13),
            ('origen', 'Origen', 25),
            ('referencia', 'Referencia', 28),
            ('detalle', 'Detalle observado', 52),
            ('estado', 'Estado', 16),
            ('unidad', 'Unidad', 30),
            ('moneda_codigo', 'Moneda', 10),
            ('monto', 'Monto', 16),
            ('impacto', 'Impacto', 42),
            ('accion', 'Accion sugerida', 44),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Alertas: {summary.get('cantidad', 0)} · "
            f"Críticas: {summary.get('criticas', 0)} · "
            f"Altas: {summary.get('altas', 0)} · "
            f"Medias: {summary.get('medias', 0)} · "
            f"Bajas: {summary.get('bajas', 0)}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Prioridad', 'width': 20, 'align': 'center'},
            {'label': 'Categoría', 'width': 30, 'align': 'left'},
            {'label': 'Fecha', 'width': 20, 'align': 'center'},
            {'label': 'Origen', 'width': 32, 'align': 'left'},
            {'label': 'Referencia', 'width': 30, 'align': 'left'},
            {'label': 'Detalle observado', 'width': 62, 'align': 'left'},
            {'label': 'Unidad', 'width': 32, 'align': 'left'},
            {'label': 'Acción sugerida', 'width': 35, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('prioridad', ''),
                item.get('categoria', ''),
                item.get('fecha_label', ''),
                item.get('origen', ''),
                item.get('referencia', ''),
                item.get('detalle', ''),
                item.get('unidad', ''),
                item.get('accion', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['', '', '', 'Límite PDF', '', f'Se muestran {MAX_ROWS_PDF} alertas. Use Excel para el detalle completo.', '', ''])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"{payload.get('descripcion_periodo', '')}. "
            f"Unidad: {payload.get('unidad_label', '')}. "
            f"Alertas: {summary.get('cantidad', 0)}. "
            f"Críticas: {summary.get('criticas', 0)}. "
            f"Altas: {summary.get('altas', 0)}. "
            f"Medias: {summary.get('medias', 0)}. "
            f"Bajas: {summary.get('bajas', 0)}."
        )


# ============================================================
# Rutas
# ============================================================


@revision_contable_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return render_template(
        'revision_contable_index.html',
        gestiones=_obtener_gestiones(),
        gestion_preferida=_gestion_preferida(),
        meses=MESES,
        unidades_negocio=obtener_unidades_negocio(),
    )


@revision_contable_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_revision():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar la revisión contable. {exc}', 500)


@revision_contable_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_revision():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        excel_bytes = build_excel(RevisionContableExport, payload)
        nombre = f"revision_contable_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el Excel de revisión contable. {exc}', 500)


@revision_contable_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_revision():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(RevisionContableExport, payload)
        nombre = f"revision_contable_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF de revisión contable. {exc}', 500)


@revision_contable_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('revision_contable_help.html')
