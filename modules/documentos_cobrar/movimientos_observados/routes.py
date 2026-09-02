# ============================================================
# DXT CONTA - Herramientas - Movimientos Observados
# Diagnostico de inconsistencias operativas y contables
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Response, jsonify, render_template, request

from database.db_manager import DatabaseManager
from modules.movimientos_observados import movimientos_observados_bp
from modules.reportes_rapidos.core.catalogos import obtener_unidades_negocio, unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import format_money
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

FUENTES = [
    {'value': 'TODAS', 'label': 'Todas'},
    {'value': 'ASIENTOS', 'label': 'Asientos'},
    {'value': 'VENTAS_COMPRAS', 'label': 'Ventas/Compras'},
    {'value': 'TESORERIA', 'label': 'Tesorería'},
    {'value': 'DOCUMENTOS_COBRAR', 'label': 'Documentos CxC'},
]

PRIORIDADES = [
    {'value': 'TODAS', 'label': 'Todas'},
    {'value': 'CRITICA', 'label': 'Crítica'},
    {'value': 'ALTA', 'label': 'Alta'},
    {'value': 'MEDIA', 'label': 'Media'},
    {'value': 'BAJA', 'label': 'Baja'},
]

TIPOS_OBSERVACION = [
    {'value': 'TODAS', 'label': 'Todas'},
    {'value': 'CUADRE', 'label': 'Cuadre'},
    {'value': 'ASIENTO', 'label': 'Asiento'},
    {'value': 'CUENTA', 'label': 'Cuenta'},
    {'value': 'AUXILIAR_CC', 'label': 'Auxiliar/C. costo'},
    {'value': 'OPERACION', 'label': 'Operación'},
    {'value': 'TESORERIA', 'label': 'Tesorería'},
    {'value': 'UNIDAD', 'label': 'Unidad'},
    {'value': 'DOCUMENTACION', 'label': 'Documentación'},
    {'value': 'CARTERA', 'label': 'Cartera'},
]

OPERACIONES = [
    {
        'table': 'venta',
        'label': 'Venta',
        'fuente': 'VENTAS_COMPRAS',
        'modulo': 'VENTAS',
        'amount_col': 'total',
        'referencia_expr': "COALESCE(NULLIF(o.numero_factura_ext, ''), CONCAT('Venta ', o.id::text))",
    },
    {
        'table': 'compra',
        'label': 'Compra',
        'fuente': 'VENTAS_COMPRAS',
        'modulo': 'COMPRAS',
        'amount_col': 'total',
        'referencia_expr': "COALESCE(NULLIF(o.numero_factura, ''), CONCAT('Compra ', o.id::text))",
    },
    {
        'table': 'cobro',
        'label': 'Cobro',
        'fuente': 'TESORERIA',
        'modulo': 'COBROS',
        'amount_col': 'monto_total',
        'referencia_expr': "COALESCE(NULLIF(o.referencia, ''), CONCAT('Cobro ', o.id::text))",
    },
    {
        'table': 'pago',
        'label': 'Pago',
        'fuente': 'TESORERIA',
        'modulo': 'PAGOS',
        'amount_col': 'monto_total',
        'referencia_expr': "COALESCE(NULLIF(o.referencia, ''), CONCAT('Pago ', o.id::text))",
    },
    {
        'table': 'movimiento_tesoreria',
        'label': 'Movimiento de tesorería',
        'fuente': 'TESORERIA',
        'modulo': 'TESORERIA',
        'amount_col': 'monto',
        'referencia_expr': "COALESCE(NULLIF(o.referencia, ''), CONCAT('Movimiento ', o.id::text))",
    },
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
    actual = date.today().year
    if actual not in gestiones:
        gestiones.insert(0, actual)
    return sorted(set(gestiones), reverse=True)


def _fuente_label(value: str) -> str:
    return next((item['label'] for item in FUENTES if item['value'] == value), 'Todas')


def _prioridad_label(value: str) -> str:
    return PRIORIDAD_LABEL.get(value, value or '')


def _tipo_label(value: str) -> str:
    return next((item['label'] for item in TIPOS_OBSERVACION if item['value'] == value), 'Todas')


def _parse_filters(args) -> dict[str, Any]:
    gestion = _parse_int(args.get('gestion') or _gestion_preferida(), 'Gestión')
    fecha_desde = _parse_date(args.get('fecha_desde') or f'{gestion}-01-01', 'Fecha desde')
    fecha_hasta = _parse_date(args.get('fecha_hasta') or f'{gestion}-12-31', 'Fecha hasta')
    if fecha_desde > fecha_hasta:
        raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')

    fuente = _clean(args.get('fuente') or 'TODAS').upper()
    if fuente not in {item['value'] for item in FUENTES}:
        raise ValueError('La fuente seleccionada no es válida.')

    prioridad = _clean(args.get('prioridad') or 'TODAS').upper()
    if prioridad not in {item['value'] for item in PRIORIDADES}:
        raise ValueError('La prioridad seleccionada no es válida.')

    tipo = _clean(args.get('tipo_observacion') or 'TODAS').upper()
    if tipo not in {item['value'] for item in TIPOS_OBSERVACION}:
        raise ValueError('El tipo de observación seleccionado no es válido.')

    min_glosa = _parse_int(args.get('min_glosa') or 8, 'Mínimo de caracteres en glosa')
    if min_glosa < 3:
        min_glosa = 3
    if min_glosa > 80:
        min_glosa = 80

    return {
        'gestion': gestion,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
        'fuente': fuente,
        'prioridad': prioridad,
        'tipo_observacion': tipo,
        'min_glosa': min_glosa,
        'periodo_label': f'{fecha_desde.strftime("%d/%m/%Y")} al {fecha_hasta.strftime("%d/%m/%Y")}',
        'unidad_label': unidad_label(unidad_negocio_id),
        'fuente_label': _fuente_label(fuente),
        'prioridad_label': 'Todas' if prioridad == 'TODAS' else _prioridad_label(prioridad),
        'tipo_label': _tipo_label(tipo),
    }


def _base_params(filtros: dict[str, Any]) -> list[Any]:
    return [filtros['fecha_desde'], filtros['fecha_hasta']]


def _unidad_where(alias: str, filtros: dict[str, Any]) -> tuple[str, list[Any]]:
    if filtros.get('unidad_negocio_id'):
        return f' AND {alias}.unidad_negocio_id = %s ', [filtros['unidad_negocio_id']]
    return '', []


def _should_include(row: dict[str, Any], filtros: dict[str, Any]) -> bool:
    if filtros['prioridad'] != 'TODAS' and row.get('prioridad_codigo') != filtros['prioridad']:
        return False
    if filtros['tipo_observacion'] != 'TODAS' and row.get('tipo_codigo') != filtros['tipo_observacion']:
        return False
    fuente = filtros['fuente']
    if fuente == 'ASIENTOS' and row.get('fuente_codigo') != 'ASIENTOS':
        return False
    if fuente == 'VENTAS_COMPRAS' and row.get('fuente_codigo') != 'VENTAS_COMPRAS':
        return False
    if fuente == 'TESORERIA' and row.get('fuente_codigo') != 'TESORERIA':
        return False
    return True


def _row(
    *,
    prioridad: str,
    tipo_codigo: str,
    categoria: str,
    fecha: Any,
    modulo: str,
    documento: str,
    unidad: str,
    monto: Any,
    detalle: str,
    accion: str,
    fuente: str,
    fuente_codigo: str,
) -> dict[str, Any]:
    monto_dec = _decimal(monto)
    return {
        'prioridad_codigo': prioridad,
        'prioridad': PRIORIDAD_LABEL.get(prioridad, prioridad),
        'tipo_codigo': tipo_codigo,
        'categoria': categoria,
        'fecha': _date_label(fecha),
        'fecha_sort': fecha.isoformat() if isinstance(fecha, date) else str(fecha or ''),
        'modulo': modulo or '',
        'documento': documento or '',
        'unidad': unidad or 'Sin unidad',
        'monto': monto_dec,
        'monto_label': format_money(monto_dec),
        'detalle': detalle or '',
        'accion': accion or '',
        'fuente': fuente or '',
        'fuente_codigo': fuente_codigo,
    }


def _unidad_nombre(row: dict[str, Any]) -> str:
    codigo = _clean(row.get('unidad_codigo'))
    nombre = _clean(row.get('unidad_nombre'))
    if codigo and nombre:
        return f'{codigo} · {nombre}'
    return nombre or codigo or 'Sin unidad'


# ============================================================
# Observaciones sobre asientos
# ============================================================


def _asientos_descuadrados(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('a', filtros)
    rows = _db_rows(
        f"""
        SELECT
            a.id,
            a.fecha,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, 'COMPROBANTE') AS modulo_origen,
            a.estado::text AS estado,
            COALESCE(a.glosa, '') AS glosa,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            COALESCE(SUM(ad.debe), 0) AS total_debe,
            COALESCE(SUM(ad.haber), 0) AS total_haber,
            ABS(COALESCE(SUM(ad.debe), 0) - COALESCE(SUM(ad.haber), 0)) AS diferencia
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          {unidad_sql}
        GROUP BY a.id, a.fecha, a.referencia, a.modulo_origen, a.estado, a.glosa, un.codigo, un.nombre
        HAVING ABS(COALESCE(SUM(ad.debe), 0) - COALESCE(SUM(ad.haber), 0)) > 0.01
        """,
        tuple(_base_params(filtros) + unidad_params),
    )
    return [
        _row(
            prioridad='CRITICA',
            tipo_codigo='CUADRE',
            categoria='Asiento descuadrado',
            fecha=item['fecha'],
            modulo=item['modulo_origen'],
            documento=f"Asiento #{item['id']} {item['referencia']}",
            unidad=_unidad_nombre(item),
            monto=item['diferencia'],
            detalle=f"Debe {format_money(item['total_debe'])} / Haber {format_money(item['total_haber'])}. Estado: {item['estado']}.",
            accion='Revisar el comprobante y corregir el detalle hasta que Debe y Haber sean iguales.',
            fuente='contabilidad.asiento / asiento_detalle',
            fuente_codigo='ASIENTOS',
        )
        for item in rows
    ]


def _asientos_sin_detalle(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('a', filtros)
    rows = _db_rows(
        f"""
        SELECT
            a.id,
            a.fecha,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, 'COMPROBANTE') AS modulo_origen,
            a.estado::text AS estado,
            COALESCE(a.glosa, '') AS glosa,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND NOT EXISTS (
              SELECT 1 FROM contabilidad.asiento_detalle ad WHERE ad.asiento_id = a.id
          )
          {unidad_sql}
        ORDER BY a.fecha, a.id
        """,
        tuple(_base_params(filtros) + unidad_params),
    )
    return [
        _row(
            prioridad='CRITICA',
            tipo_codigo='ASIENTO',
            categoria='Asiento sin detalle',
            fecha=item['fecha'],
            modulo=item['modulo_origen'],
            documento=f"Asiento #{item['id']} {item['referencia']}",
            unidad=_unidad_nombre(item),
            monto=0,
            detalle=f"El asiento no tiene líneas contables. Estado: {item['estado']}.",
            accion='Completar el detalle del comprobante o anularlo si fue creado por error.',
            fuente='contabilidad.asiento',
            fuente_codigo='ASIENTOS',
        )
        for item in rows
    ]


def _lineas_invalidas(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('a', filtros)
    rows = _db_rows(
        f"""
        SELECT
            a.id AS asiento_id,
            a.fecha,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, 'COMPROBANTE') AS modulo_origen,
            ad.secuencia,
            ad.cuenta_codigo,
            ad.debe,
            ad.haber,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre
        FROM contabilidad.asiento_detalle ad
        JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND (
            (COALESCE(ad.debe, 0) = 0 AND COALESCE(ad.haber, 0) = 0)
            OR (COALESCE(ad.debe, 0) > 0 AND COALESCE(ad.haber, 0) > 0)
          )
          {unidad_sql}
        ORDER BY a.fecha, a.id, ad.secuencia
        """,
        tuple(_base_params(filtros) + unidad_params),
    )
    return [
        _row(
            prioridad='CRITICA',
            tipo_codigo='CUADRE',
            categoria='Línea contable inválida',
            fecha=item['fecha'],
            modulo=item['modulo_origen'],
            documento=f"Asiento #{item['asiento_id']} / línea {item['secuencia']}",
            unidad=_unidad_nombre(item),
            monto=max(_decimal(item['debe']), _decimal(item['haber'])),
            detalle=f"Cuenta {item['cuenta_codigo']} con Debe {format_money(item['debe'])} y Haber {format_money(item['haber'])}.",
            accion='Cada línea debe tener importe solo en Debe o solo en Haber, nunca ambos ni ambos en cero.',
            fuente='contabilidad.asiento_detalle',
            fuente_codigo='ASIENTOS',
        )
        for item in rows
    ]


def _cuentas_observadas(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('a', filtros)
    rows = _db_rows(
        f"""
        SELECT
            a.id AS asiento_id,
            a.fecha,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, 'COMPROBANTE') AS modulo_origen,
            ad.secuencia,
            ad.cuenta_codigo,
            COALESCE(ad.debe, 0) + COALESCE(ad.haber, 0) AS monto,
            c.codigo AS cuenta_existe,
            COALESCE(c.nombre, '') AS cuenta_nombre,
            COALESCE(c.activo, FALSE) AS cuenta_activa,
            COALESCE(c.es_postable, FALSE) AS es_postable,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre
        FROM contabilidad.asiento_detalle ad
        JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND (c.codigo IS NULL OR COALESCE(c.activo, FALSE) = FALSE OR COALESCE(c.es_postable, FALSE) = FALSE)
          {unidad_sql}
        ORDER BY a.fecha, a.id, ad.secuencia
        """,
        tuple(_base_params(filtros) + unidad_params),
    )
    results = []
    for item in rows:
        if not item.get('cuenta_existe'):
            categoria = 'Cuenta inexistente en asiento'
            detalle = f"La cuenta {item['cuenta_codigo']} no existe en el plan de cuentas."
            accion = 'Crear/corregir la cuenta usada o reclasificar la línea contable.'
            prioridad = 'CRITICA'
        elif not item.get('cuenta_activa'):
            categoria = 'Cuenta inactiva usada'
            detalle = f"La cuenta {item['cuenta_codigo']} · {item['cuenta_nombre']} está inactiva."
            accion = 'Revisar si corresponde activar la cuenta o reclasificar el movimiento.'
            prioridad = 'ALTA'
        else:
            categoria = 'Cuenta no postable usada'
            detalle = f"La cuenta {item['cuenta_codigo']} · {item['cuenta_nombre']} no es postable."
            accion = 'Cambiar la línea a una cuenta de movimiento/postable.'
            prioridad = 'ALTA'
        results.append(_row(
            prioridad=prioridad,
            tipo_codigo='CUENTA',
            categoria=categoria,
            fecha=item['fecha'],
            modulo=item['modulo_origen'],
            documento=f"Asiento #{item['asiento_id']} / línea {item['secuencia']}",
            unidad=_unidad_nombre(item),
            monto=item['monto'],
            detalle=detalle,
            accion=accion,
            fuente='contabilidad.cuenta / asiento_detalle',
            fuente_codigo='ASIENTOS',
        ))
    return results


def _auxiliar_cc_faltante(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('a', filtros)
    rows = _db_rows(
        f"""
        SELECT
            a.id AS asiento_id,
            a.fecha,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, 'COMPROBANTE') AS modulo_origen,
            ad.secuencia,
            ad.cuenta_codigo,
            COALESCE(c.nombre, '') AS cuenta_nombre,
            c.requiere_auxiliar,
            c.requiere_cc,
            ad.auxiliar_id,
            ad.centro_costo_id,
            COALESCE(ad.debe, 0) + COALESCE(ad.haber, 0) AS monto,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre
        FROM contabilidad.asiento_detalle ad
        JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND ((c.requiere_auxiliar = TRUE AND ad.auxiliar_id IS NULL) OR (c.requiere_cc = TRUE AND ad.centro_costo_id IS NULL))
          {unidad_sql}
        ORDER BY a.fecha, a.id, ad.secuencia
        """,
        tuple(_base_params(filtros) + unidad_params),
    )
    results = []
    for item in rows:
        faltantes = []
        if item.get('requiere_auxiliar') and item.get('auxiliar_id') is None:
            faltantes.append('auxiliar')
        if item.get('requiere_cc') and item.get('centro_costo_id') is None:
            faltantes.append('centro de costo')
        results.append(_row(
            prioridad='MEDIA',
            tipo_codigo='AUXILIAR_CC',
            categoria='Clasificación incompleta',
            fecha=item['fecha'],
            modulo=item['modulo_origen'],
            documento=f"Asiento #{item['asiento_id']} / línea {item['secuencia']}",
            unidad=_unidad_nombre(item),
            monto=item['monto'],
            detalle=f"La cuenta {item['cuenta_codigo']} · {item['cuenta_nombre']} requiere {', '.join(faltantes)}.",
            accion='Completar la clasificación para que los reportes por auxiliar o centro de costo sean confiables.',
            fuente='contabilidad.cuenta / asiento_detalle',
            fuente_codigo='ASIENTOS',
        ))
    return results


def _glosas_cortas_asientos(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('a', filtros)
    rows = _db_rows(
        f"""
        SELECT
            a.id,
            a.fecha,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, 'COMPROBANTE') AS modulo_origen,
            COALESCE(a.glosa, '') AS glosa,
            a.estado::text AS estado,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            COALESCE(SUM(ad.debe), 0) AS monto
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND LENGTH(TRIM(COALESCE(a.glosa, ''))) < %s
          {unidad_sql}
        GROUP BY a.id, a.fecha, a.referencia, a.modulo_origen, a.glosa, a.estado, un.codigo, un.nombre
        ORDER BY a.fecha, a.id
        """,
        tuple(_base_params(filtros) + [filtros['min_glosa']] + unidad_params),
    )
    return [
        _row(
            prioridad='BAJA',
            tipo_codigo='DOCUMENTACION',
            categoria='Glosa insuficiente',
            fecha=item['fecha'],
            modulo=item['modulo_origen'],
            documento=f"Asiento #{item['id']} {item['referencia']}",
            unidad=_unidad_nombre(item),
            monto=item['monto'],
            detalle=f"La glosa tiene menos de {filtros['min_glosa']} caracteres.",
            accion='Completar una glosa clara para facilitar revisión, auditoría y soporte.',
            fuente='contabilidad.asiento',
            fuente_codigo='ASIENTOS',
        )
        for item in rows
    ]


def _unidades_observadas_asientos(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('a', filtros)
    rows = _db_rows(
        f"""
        SELECT
            a.id,
            a.fecha,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, 'COMPROBANTE') AS modulo_origen,
            COALESCE(SUM(ad.debe), 0) AS monto,
            a.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            COALESCE(un.activo, FALSE) AS unidad_activa,
            un.id AS unidad_existe
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND (un.id IS NULL OR COALESCE(un.activo, FALSE) = FALSE)
          {unidad_sql}
        GROUP BY a.id, a.fecha, a.referencia, a.modulo_origen, a.unidad_negocio_id, un.id, un.codigo, un.nombre, un.activo
        ORDER BY a.fecha, a.id
        """,
        tuple(_base_params(filtros) + unidad_params),
    )
    return [
        _row(
            prioridad='ALTA',
            tipo_codigo='UNIDAD',
            categoria='Unidad de negocio observada',
            fecha=item['fecha'],
            modulo=item['modulo_origen'],
            documento=f"Asiento #{item['id']} {item['referencia']}",
            unidad=_unidad_nombre(item),
            monto=item['monto'],
            detalle='La unidad de negocio no existe o está inactiva.',
            accion='Corregir la unidad del comprobante o reactivar la unidad si corresponde.',
            fuente='contabilidad.asiento / unidad_negocio',
            fuente_codigo='ASIENTOS',
        )
        for item in rows
    ]


# ============================================================
# Observaciones sobre operaciones
# ============================================================


def _operacion_rows(op: dict[str, Any], filtros: dict[str, Any], where_extra: str, params_extra: list[Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('o', filtros)
    sql = f"""
        SELECT
            o.id,
            o.fecha,
            {op['referencia_expr']} AS referencia,
            COALESCE(o.glosa, '') AS glosa,
            o.estado::text AS estado,
            o.asiento_id,
            o.{op['amount_col']} AS monto,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            COALESCE(un.activo, FALSE) AS unidad_activa,
            un.id AS unidad_existe,
            a.estado::text AS asiento_estado
        FROM contabilidad.{op['table']} o
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = o.unidad_negocio_id
        LEFT JOIN contabilidad.asiento a ON a.id = o.asiento_id
        WHERE o.fecha BETWEEN %s AND %s
          {unidad_sql}
          {where_extra}
        ORDER BY o.fecha, o.id
    """
    return _db_rows(sql, tuple(_base_params(filtros) + unidad_params + params_extra))


def _operaciones_confirmadas_sin_asiento(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for op in OPERACIONES:
        rows = _operacion_rows(
            op,
            filtros,
            "AND o.estado::text = 'CONFIRMADO' AND o.asiento_id IS NULL",
            [],
        )
        for item in rows:
            results.append(_row(
                prioridad='ALTA',
                tipo_codigo='OPERACION',
                categoria='Operación confirmada sin asiento',
                fecha=item['fecha'],
                modulo=op['modulo'],
                documento=f"{op['label']} #{item['id']} · {item['referencia']}",
                unidad=_unidad_nombre(item),
                monto=item['monto'],
                detalle='La operación está confirmada, pero no tiene asiento contable asociado.',
                accion='Revisar la operación y regenerar/asociar el asiento contable correspondiente.',
                fuente=f"contabilidad.{op['table']}",
                fuente_codigo=op['fuente'],
            ))
    return results


def _operaciones_con_asiento_no_confirmado(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for op in OPERACIONES:
        rows = _operacion_rows(
            op,
            filtros,
            "AND o.estado::text = 'CONFIRMADO' AND o.asiento_id IS NOT NULL AND (a.id IS NULL OR a.estado::text <> 'CONFIRMADO')",
            [],
        )
        for item in rows:
            estado_asiento = item.get('asiento_estado') or 'No encontrado'
            results.append(_row(
                prioridad='CRITICA',
                tipo_codigo='OPERACION',
                categoria='Operación con asiento no confirmado',
                fecha=item['fecha'],
                modulo=op['modulo'],
                documento=f"{op['label']} #{item['id']} · {item['referencia']}",
                unidad=_unidad_nombre(item),
                monto=item['monto'],
                detalle=f"La operación está confirmada, pero el asiento asociado está en estado {estado_asiento}.",
                accion='Corregir el estado del asiento o revisar si la operación debe anularse/reprocesarse.',
                fuente=f"contabilidad.{op['table']} / asiento",
                fuente_codigo=op['fuente'],
            ))
    return results


def _operaciones_monto_no_valido(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for op in OPERACIONES:
        rows = _operacion_rows(
            op,
            filtros,
            f"AND o.estado::text <> 'ANULADO' AND COALESCE(o.{op['amount_col']}, 0) <= 0",
            [],
        )
        for item in rows:
            results.append(_row(
                prioridad='CRITICA',
                tipo_codigo='OPERACION',
                categoria='Monto no válido',
                fecha=item['fecha'],
                modulo=op['modulo'],
                documento=f"{op['label']} #{item['id']} · {item['referencia']}",
                unidad=_unidad_nombre(item),
                monto=item['monto'],
                detalle='La operación tiene monto cero o negativo.',
                accion='Corregir el importe o anular la operación si fue registrada por error.',
                fuente=f"contabilidad.{op['table']}",
                fuente_codigo=op['fuente'],
            ))
    return results


def _operaciones_glosa_corta(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for op in OPERACIONES:
        rows = _operacion_rows(
            op,
            filtros,
            "AND o.estado::text <> 'ANULADO' AND LENGTH(TRIM(COALESCE(o.glosa, ''))) < %s",
            [filtros['min_glosa']],
        )
        for item in rows:
            results.append(_row(
                prioridad='BAJA',
                tipo_codigo='DOCUMENTACION',
                categoria='Glosa insuficiente',
                fecha=item['fecha'],
                modulo=op['modulo'],
                documento=f"{op['label']} #{item['id']} · {item['referencia']}",
                unidad=_unidad_nombre(item),
                monto=item['monto'],
                detalle=f"La glosa tiene menos de {filtros['min_glosa']} caracteres.",
                accion='Completar una glosa útil para revisión posterior.',
                fuente=f"contabilidad.{op['table']}",
                fuente_codigo=op['fuente'],
            ))
    return results


def _operaciones_fecha_futura(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for op in OPERACIONES:
        rows = _operacion_rows(
            op,
            filtros,
            "AND o.estado::text <> 'ANULADO' AND o.fecha > CURRENT_DATE",
            [],
        )
        for item in rows:
            results.append(_row(
                prioridad='MEDIA',
                tipo_codigo='OPERACION',
                categoria='Fecha futura',
                fecha=item['fecha'],
                modulo=op['modulo'],
                documento=f"{op['label']} #{item['id']} · {item['referencia']}",
                unidad=_unidad_nombre(item),
                monto=item['monto'],
                detalle='La operación tiene fecha posterior al día actual.',
                accion='Verificar si la fecha es intencional o corregirla antes de reportar.',
                fuente=f"contabilidad.{op['table']}",
                fuente_codigo=op['fuente'],
            ))
    return results


def _operaciones_unidad_observada(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for op in OPERACIONES:
        rows = _operacion_rows(
            op,
            filtros,
            "AND o.estado::text <> 'ANULADO' AND (un.id IS NULL OR COALESCE(un.activo, FALSE) = FALSE)",
            [],
        )
        for item in rows:
            results.append(_row(
                prioridad='ALTA',
                tipo_codigo='UNIDAD',
                categoria='Unidad de negocio observada',
                fecha=item['fecha'],
                modulo=op['modulo'],
                documento=f"{op['label']} #{item['id']} · {item['referencia']}",
                unidad=_unidad_nombre(item),
                monto=item['monto'],
                detalle='La unidad de negocio no existe o está inactiva.',
                accion='Corregir la unidad de negocio para no distorsionar reportes por unidad.',
                fuente=f"contabilidad.{op['table']} / unidad_negocio",
                fuente_codigo=op['fuente'],
            ))
    return results


def _tesoreria_medio_incompleto(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for table, label, modulo in [('cobro', 'Cobro', 'COBROS'), ('pago', 'Pago', 'PAGOS')]:
        unidad_sql, unidad_params = _unidad_where('o', filtros)
        rows = _db_rows(
            f"""
            SELECT
                o.id,
                o.fecha,
                COALESCE(NULLIF(o.referencia, ''), CONCAT('{label} ', o.id::text)) AS referencia,
                o.medio_pago::text AS medio_pago,
                o.caja_id,
                o.cuenta_bancaria_id,
                o.monto_total AS monto,
                COALESCE(un.codigo, '') AS unidad_codigo,
                COALESCE(un.nombre, '') AS unidad_nombre
            FROM contabilidad.{table} o
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = o.unidad_negocio_id
            WHERE o.fecha BETWEEN %s AND %s
              AND o.estado::text <> 'ANULADO'
              AND (
                (o.medio_pago::text = 'CAJA' AND o.caja_id IS NULL)
                OR (o.medio_pago::text = 'BANCO' AND o.cuenta_bancaria_id IS NULL)
              )
              {unidad_sql}
            ORDER BY o.fecha, o.id
            """,
            tuple(_base_params(filtros) + unidad_params),
        )
        for item in rows:
            results.append(_row(
                prioridad='ALTA',
                tipo_codigo='TESORERIA',
                categoria='Medio de pago incompleto',
                fecha=item['fecha'],
                modulo=modulo,
                documento=f"{label} #{item['id']} · {item['referencia']}",
                unidad=_unidad_nombre(item),
                monto=item['monto'],
                detalle=f"Medio {item['medio_pago']} sin caja/cuenta bancaria correspondiente.",
                accion='Completar la caja o cuenta bancaria para que caja/bancos y reportes cuadren.',
                fuente=f"contabilidad.{table}",
                fuente_codigo='TESORERIA',
            ))

    unidad_sql, unidad_params = _unidad_where('m', filtros)
    rows = _db_rows(
        f"""
        SELECT
            m.id,
            m.fecha,
            COALESCE(NULLIF(m.referencia, ''), CONCAT('Movimiento ', m.id::text)) AS referencia,
            m.tipo_movimiento::text AS tipo_movimiento,
            m.medio_origen::text AS medio_origen,
            m.medio_destino::text AS medio_destino,
            m.caja_origen_id,
            m.banco_origen_id,
            m.caja_destino_id,
            m.banco_destino_id,
            m.monto,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre
        FROM contabilidad.movimiento_tesoreria m
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
        WHERE m.fecha BETWEEN %s AND %s
          AND m.estado::text <> 'ANULADO'
          AND (
            (m.medio_origen::text = 'CAJA' AND m.caja_origen_id IS NULL)
            OR (m.medio_origen::text = 'BANCO' AND m.banco_origen_id IS NULL)
            OR (m.medio_destino::text = 'CAJA' AND m.caja_destino_id IS NULL)
            OR (m.medio_destino::text = 'BANCO' AND m.banco_destino_id IS NULL)
            OR (m.medio_origen::text = 'CAJA' AND m.medio_destino::text = 'CAJA' AND m.caja_origen_id IS NOT NULL AND m.caja_origen_id = m.caja_destino_id)
            OR (m.medio_origen::text = 'BANCO' AND m.medio_destino::text = 'BANCO' AND m.banco_origen_id IS NOT NULL AND m.banco_origen_id = m.banco_destino_id)
          )
          {unidad_sql}
        ORDER BY m.fecha, m.id
        """,
        tuple(_base_params(filtros) + unidad_params),
    )
    for item in rows:
        results.append(_row(
            prioridad='ALTA',
            tipo_codigo='TESORERIA',
            categoria='Movimiento tesorería observado',
            fecha=item['fecha'],
            modulo='TESORERIA',
            documento=f"Movimiento #{item['id']} · {item['referencia']}",
            unidad=_unidad_nombre(item),
            monto=item['monto'],
            detalle='Origen/destino incompleto o transferencia hacia la misma caja/cuenta.',
            accion='Revisar origen y destino del movimiento antes de usarlo en conciliación o reportes.',
            fuente='contabilidad.movimiento_tesoreria',
            fuente_codigo='TESORERIA',
        ))
    return results


def _documentos_cobrar_observados(filtros: dict[str, Any]) -> list[dict[str, Any]]:
    unidad_sql, unidad_params = _unidad_where('d', filtros)
    rows = _db_rows(
        f"""
        SELECT
            d.id,
            d.fecha_documento AS fecha,
            d.tipo_documento,
            d.numero_documento,
            d.cliente_nombre,
            d.tratamiento_contable,
            d.gestion_origen,
            d.estado,
            d.moneda_codigo,
            d.importe_total,
            d.importe_cobrado,
            d.saldo_pendiente,
            d.asiento_registro_id,
            d.factura_electronica_id,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            ABS(COALESCE(d.saldo_pendiente, 0) - GREATEST(COALESCE(d.importe_total, 0) - COALESCE(d.importe_cobrado, 0), 0)) AS diferencia_saldo
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        WHERE d.fecha_documento BETWEEN %s AND %s
          AND COALESCE(d.activo, TRUE) = TRUE
          AND COALESCE(d.estado, '') <> 'ANULADO'
          {unidad_sql}
          AND (
                ABS(COALESCE(d.saldo_pendiente, 0) - GREATEST(COALESCE(d.importe_total, 0) - COALESCE(d.importe_cobrado, 0), 0)) > 0.01
                OR (COALESCE(d.tratamiento_contable, '') <> 'CARTERA_HISTORICA' AND d.factura_electronica_id IS NULL AND d.asiento_registro_id IS NULL)
                OR (COALESCE(d.tratamiento_contable, '') = 'CARTERA_HISTORICA' AND d.asiento_registro_id IS NOT NULL)
                OR (d.gestion_origen > %s)
                OR (COALESCE(d.saldo_pendiente, 0) <= 0.01 AND COALESCE(d.estado, '') <> 'COBRADO')
                OR (COALESCE(d.saldo_pendiente, 0) > 0.01 AND COALESCE(d.estado, '') = 'COBRADO')
          )
        ORDER BY d.fecha_documento, d.id
        """,
        tuple(_base_params(filtros) + unidad_params + [filtros['gestion']]),
    )
    results = []
    for item in rows:
        documento = f"{item.get('tipo_documento') or 'DOC'} {item.get('numero_documento') or item.get('id')} · {item.get('cliente_nombre') or 'Sin cliente'}"
        tratamiento = item.get('tratamiento_contable') or ''
        prioridad = 'ALTA'
        detalle = []
        accion = []
        monto = item.get('saldo_pendiente')
        if _decimal(item.get('diferencia_saldo')) > Decimal('0.01'):
            prioridad = 'CRITICA'
            detalle.append('Saldo pendiente no coincide con importe total menos importe cobrado.')
            accion.append('Corregir importes o aplicaciones antes de continuar cobrando.')
            monto = item.get('diferencia_saldo')
        if tratamiento != 'CARTERA_HISTORICA' and not item.get('factura_electronica_id') and not item.get('asiento_registro_id'):
            prioridad = 'CRITICA'
            detalle.append('Documento vigente manual sin asiento de registro.')
            accion.append('Generar o vincular el asiento de registro del documento vigente.')
        if tratamiento == 'CARTERA_HISTORICA' and item.get('asiento_registro_id'):
            detalle.append('Documento histórico con asiento de registro; la regla histórica no debe contabilizar al alta.')
            accion.append('Revisar asiento de registro y reclasificar/anular si corresponde.')
        if int(item.get('gestion_origen') or 0) > int(filtros['gestion']):
            prioridad = 'CRITICA'
            detalle.append('Gestión de origen futura respecto a la gestión revisada.')
            accion.append('Corregir gestión de origen o anular el documento.')
        if _decimal(item.get('saldo_pendiente')) <= Decimal('0.01') and (item.get('estado') or '') != 'COBRADO':
            detalle.append('Saldo cero con estado distinto de COBRADO.')
            accion.append('Actualizar estado operativo del documento.')
        if _decimal(item.get('saldo_pendiente')) > Decimal('0.01') and (item.get('estado') or '') == 'COBRADO':
            prioridad = 'CRITICA'
            detalle.append('Documento marcado como COBRADO con saldo pendiente.')
            accion.append('Corregir estado o aplicaciones de cobro.')
        results.append(_row(
            prioridad=prioridad,
            tipo_codigo='CARTERA',
            categoria='Documento por cobrar observado',
            fecha=item['fecha'],
            modulo='DOCUMENTOS CXC',
            documento=documento,
            unidad=_unidad_nombre(item),
            monto=monto,
            detalle=' '.join(detalle),
            accion=' '.join(accion),
            fuente='contabilidad.documento_por_cobrar',
            fuente_codigo='DOCUMENTOS_COBRAR',
        ))
    return results


# ============================================================
# Construccion de payload
# ============================================================


def _build_rows(filtros: dict[str, Any], limit_rows: int = MAX_ROWS_SCREEN) -> list[dict[str, Any]]:
    checks = [
        _asientos_descuadrados,
        _asientos_sin_detalle,
        _lineas_invalidas,
        _cuentas_observadas,
        _auxiliar_cc_faltante,
        _glosas_cortas_asientos,
        _unidades_observadas_asientos,
        _operaciones_confirmadas_sin_asiento,
        _operaciones_con_asiento_no_confirmado,
        _operaciones_monto_no_valido,
        _operaciones_glosa_corta,
        _operaciones_fecha_futura,
        _operaciones_unidad_observada,
        _tesoreria_medio_incompleto,
        _documentos_cobrar_observados,
    ]
    rows: list[dict[str, Any]] = []
    for check in checks:
        for item in check(filtros):
            if _should_include(item, filtros):
                rows.append(item)

    rows.sort(key=lambda item: (
        PRIORIDAD_ORDEN.get(item.get('prioridad_codigo'), 9),
        item.get('fecha_sort') or '',
        item.get('categoria') or '',
        item.get('documento') or '',
    ))
    return rows[:limit_rows]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {'CRITICA': 0, 'ALTA': 0, 'MEDIA': 0, 'BAJA': 0}
    for item in rows:
        code = item.get('prioridad_codigo')
        if code in counts:
            counts[code] += 1
    return {
        'total': len(rows),
        'criticas': counts['CRITICA'],
        'altas': counts['ALTA'],
        'medias': counts['MEDIA'],
        'bajas': counts['BAJA'],
        'estado_general': 'Sin observaciones' if not rows else ('Atención crítica' if counts['CRITICA'] else 'Con observaciones'),
        'moneda_display_note': 'Importes expresados en moneda original del movimiento cuando corresponde.',
    }


def _summary_cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {'label': 'Estado general', 'value': summary['estado_general'], 'note': 'Según filtros aplicados', 'kind': 'group'},
        {'label': 'Total observaciones', 'value': summary['total'], 'note': 'Registros encontrados', 'kind': 'medium'},
        {'label': 'Críticas', 'value': summary['criticas'], 'note': 'Revisar primero', 'kind': 'critical'},
        {'label': 'Altas', 'value': summary['altas'], 'note': 'Revisión prioritaria', 'kind': 'high'},
        {'label': 'Medias/Bajas', 'value': summary['medias'] + summary['bajas'], 'note': 'Limpieza y documentación', 'kind': 'low'},
    ]


def _display_columns() -> list[dict[str, str]]:
    return [
        {'field': 'prioridad', 'label': 'Prioridad', 'type': 'badge', 'code_key': 'prioridad_codigo'},
        {'field': 'categoria', 'label': 'Observación'},
        {'field': 'fecha', 'label': 'Fecha'},
        {'field': 'modulo', 'label': 'Módulo'},
        {'field': 'documento', 'label': 'Documento'},
        {'field': 'unidad', 'label': 'Unidad'},
        {'field': 'monto', 'label': 'Monto ref.', 'type': 'money', 'align': 'right'},
        {'field': 'detalle', 'label': 'Detalle'},
        {'field': 'accion', 'label': 'Acción sugerida'},
    ]


def _build_payload(filtros: dict[str, Any], limit_rows: int = MAX_ROWS_SCREEN) -> dict[str, Any]:
    rows = _build_rows(filtros, limit_rows=limit_rows)
    summary = _summary(rows)
    return {
        'titulo': 'Movimientos Observados',
        'descripcion_periodo': filtros['periodo_label'],
        'unidad_label': filtros['unidad_label'],
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'gestion': filtros['gestion'],
        'fecha_desde': filtros['fecha_desde'],
        'fecha_hasta': filtros['fecha_hasta'],
        'fuente_label': filtros['fuente_label'],
        'prioridad_label': filtros['prioridad_label'],
        'tipo_label': filtros['tipo_label'],
        'rows': rows,
        'columns': _display_columns(),
        'summary': summary,
        'summary_cards': _summary_cards(summary),
        'fuente_datos': 'Asientos, detalles contables, Tesorería y documentos por cobrar del esquema contabilidad.',
        'criterio_reporte': 'Diagnóstico de inconsistencias. No modifica datos ni corrige movimientos automáticamente.',
        'empty_title': 'Sin movimientos observados',
        'empty_icon': 'fas fa-circle-check',
    }


class MovimientosObservadosExport:
    TITLE = 'Movimientos Observados'
    WORKSHEET_TITLE = 'Movimientos Observados'
    FILE_SLUG = 'movimientos_observados'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'monto'}

    @staticmethod
    def excel_columns():
        return [
            ('prioridad', 'Prioridad', 16),
            ('categoria', 'Observacion', 28),
            ('fecha', 'Fecha', 14),
            ('modulo', 'Modulo', 18),
            ('documento', 'Documento', 34),
            ('unidad', 'Unidad de negocio', 28),
            ('monto', 'Monto ref.', 16),
            ('detalle', 'Detalle', 60),
            ('accion', 'Accion sugerida', 60),
            ('fuente', 'Fuente', 38),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Estado: {summary.get('estado_general', '')} · "
            f"Total: {summary.get('total', 0)} · "
            f"Críticas: {summary.get('criticas', 0)} · "
            f"Altas: {summary.get('altas', 0)} · "
            f"Medias: {summary.get('medias', 0)} · "
            f"Bajas: {summary.get('bajas', 0)}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Prioridad', 'width': 20, 'align': 'center'},
            {'label': 'Observación', 'width': 32, 'align': 'left'},
            {'label': 'Fecha', 'width': 18, 'align': 'center'},
            {'label': 'Módulo', 'width': 22, 'align': 'left'},
            {'label': 'Documento', 'width': 38, 'align': 'left'},
            {'label': 'Unidad', 'width': 34, 'align': 'left'},
            {'label': 'Monto ref.', 'width': 23, 'align': 'right'},
            {'label': 'Detalle', 'width': 58, 'align': 'left'},
            {'label': 'Acción sugerida', 'width': 52, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('prioridad', ''),
                item.get('categoria', ''),
                item.get('fecha', ''),
                item.get('modulo', ''),
                item.get('documento', ''),
                item.get('unidad', ''),
                item.get('monto_label', ''),
                item.get('detalle', ''),
                item.get('accion', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['', 'Límite PDF', '', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} filas. Use Excel para el detalle completo.', ''])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"{payload.get('descripcion_periodo', '')}. "
            f"Unidad: {payload.get('unidad_label', '')}. "
            f"Fuente: {payload.get('fuente_label', '')}. "
            f"Estado: {summary.get('estado_general', '')}. "
            f"Críticas: {summary.get('criticas', 0)}. "
            f"Altas: {summary.get('altas', 0)}. "
            f"Total: {summary.get('total', 0)}."
        )


# ============================================================
# Rutas
# ============================================================


@movimientos_observados_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    gestion = _gestion_preferida()
    return render_template(
        'movimientos_observados_index.html',
        gestiones=_obtener_gestiones(),
        gestion_preferida=gestion,
        fecha_desde=f'{gestion}-01-01',
        fecha_hasta=f'{gestion}-12-31',
        unidades_negocio=obtener_unidades_negocio(),
        fuentes=FUENTES,
        prioridades=PRIORIDADES,
        tipos_observacion=TIPOS_OBSERVACION,
    )


@movimientos_observados_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_movimientos_observados():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar la revisión de movimientos observados. {exc}', 500)


@movimientos_observados_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_movimientos_observados():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        excel_bytes = build_excel(MovimientosObservadosExport, payload)
        nombre = f"movimientos_observados_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el Excel de movimientos observados. {exc}', 500)


@movimientos_observados_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_movimientos_observados():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(MovimientosObservadosExport, payload)
        nombre = f"movimientos_observados_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF de movimientos observados. {exc}', 500)


@movimientos_observados_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('movimientos_observados_help.html')
