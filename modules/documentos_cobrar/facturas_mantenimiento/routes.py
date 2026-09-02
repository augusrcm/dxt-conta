# ============================================================
# DXT CONTA - Módulo Facturas · Auditoría / Mantenimiento
# Propósito: consulta, trazabilidad y diagnóstico de facturas.
# Las acciones operativas se centralizan en Tesorería -> Facturas Electrónicas.
# ============================================================

from decimal import Decimal, ROUND_HALF_UP

from flask import jsonify, render_template, request, url_for

from database.db_manager import DatabaseManager
from modules.facturas_mantenimiento import facturas_mantenimiento_bp
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
CUANTIA = Decimal('0.01')
FILTROS_ESTADO = [
    'PENDIENTES',
    'CONTABILIZADAS',
    'COBRADAS',
    'CERRADAS_MANUAL',
    'ANULADAS',
    'TODAS',
]

SALDO_OPERATIVO_SQL = """
CASE
    WHEN fe.estado::TEXT = 'ANULADA' THEN 0
    ELSE GREATEST(
        COALESCE(fe.importe_total, 0)
        - COALESCE(reg.total_regularizado, 0)
        - COALESCE(apps.total_aplicado, 0),
        0
    )
END
"""


# ============================================================
# Helpers base
# ============================================================

def _json_ok(message=None, **kwargs):
    payload = {'success': True}
    if message:
        payload['message'] = message
    payload.update(kwargs)
    return jsonify(payload)


def _json_error(message, status=400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(payload), status


def _clean(value):
    return str(value or '').strip()


def _to_decimal(value):
    return Decimal(str(value or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP)


def _to_float(value):
    if value is None:
        return 0.0
    return float(_to_decimal(value))


def _parse_int(value, field_name='ID'):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field_name}" debe ser numérico.')


def _obtener_unidades_negocio_activas(db):
    return db.execute_query(
        """
        SELECT id, codigo, nombre, COALESCE(nit, '') AS nit
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
        """
    )


def _estado_label(value):
    labels = {
        'RECIBIDA': 'Recibida',
        'DISPONIBLE': 'Disponible',
        'REGISTRADA': 'Contabilizada',
        'COBRADA_PARCIAL': 'Cobrada parcial',
        'COBRADA_TOTAL': 'Cobrada total',
        'ANULADA': 'Anulada',
    }
    return labels.get(value or '', value or '—')


def _proceso_label(value):
    labels = {
        'RECIBIDA': 'Recibida',
        'DISPONIBLE': 'Disponible',
        'CONTABILIZADA': 'Contabilizada',
        'COBRADA_PARCIAL': 'Cobrada parcial',
        'COBRADA_TOTAL': 'Cobrada total',
        'CERRADA_MANUAL': 'Cerrada tesorería',
        'ANULADA': 'Anulada',
    }
    return labels.get(value or '', value or '—')


# ============================================================
# Consultas de facturas
# ============================================================

def _build_filters():
    estado = (_clean(request.args.get('estado')) or 'PENDIENTES').upper()
    if estado not in FILTROS_ESTADO:
        estado = 'PENDIENTES'
    return {
        'q': _clean(request.args.get('q')),
        'estado': estado,
        'unidad_negocio_id': _clean(request.args.get('unidad_negocio_id')),
    }


def _where_sql(filters, params):
    where = ["fe.origen = 'EXTERNO'"]

    texto = filters.get('q')
    if texto:
        like = f'%{texto}%'
        where.append(
            """
            (
                COALESCE(fe.numero_factura, '') ILIKE %s
                OR COALESCE(fe.nombre_cliente, '') ILIKE %s
                OR COALESCE(fe.nit_cliente, '') ILIKE %s
                OR COALESCE(fe.nit_emisor, '') ILIKE %s
                OR COALESCE(fe.cuf, '') ILIKE %s
                OR COALESCE(un.codigo, '') ILIKE %s
                OR COALESCE(un.nombre, '') ILIKE %s
                OR COALESCE(aux.nombre, '') ILIKE %s
                OR COALESCE(aux.nit_ci, '') ILIKE %s
                OR COALESCE(fe.cuenta_cobrar_codigo, '') ILIKE %s
                OR COALESCE(cta_cobrar.nombre, '') ILIKE %s
                OR COALESCE(fe.cuenta_contra_codigo, '') ILIKE %s
                OR COALESCE(cta_contra.nombre, '') ILIKE %s
                OR CAST(COALESCE(fe.importe_total, 0) AS TEXT) ILIKE %s
                OR CAST(COALESCE(fe.saldo_pendiente, 0) AS TEXT) ILIKE %s
            )
            """
        )
        params.extend([like] * 15)

    unidad_negocio_id = filters.get('unidad_negocio_id')
    if unidad_negocio_id:
        where.append('fe.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    estado = filters.get('estado')
    if estado == 'PENDIENTES':
        where.append("fe.estado::TEXT <> 'ANULADA'")
        where.append(f'({SALDO_OPERATIVO_SQL}) > 0')
        where.append('COALESCE(reg.cierre_manual_activo, FALSE) = FALSE')
    elif estado == 'CONTABILIZADAS':
        where.append('doc.asiento_id IS NOT NULL')
        where.append("fe.estado::TEXT <> 'ANULADA'")
    elif estado == 'COBRADAS':
        where.append("fe.estado::TEXT <> 'ANULADA'")
        where.append(f'({SALDO_OPERATIVO_SQL}) <= 0')
        where.append('COALESCE(reg.cierre_manual_activo, FALSE) = FALSE')
    elif estado == 'CERRADAS_MANUAL':
        where.append('COALESCE(reg.cierre_manual_activo, FALSE) = TRUE')
    elif estado == 'ANULADAS':
        where.append("fe.estado::TEXT = 'ANULADA'")

    return where


def _fetch_facturas(db, filters):
    params = []
    where = _where_sql(filters, params)
    where_sql = 'WHERE ' + ' AND '.join(where)

    rows = db.execute_query(
        f"""
        WITH reg AS (
            SELECT
                fr.factura_electronica_id,
                COALESCE(SUM(CASE WHEN fr.activo = TRUE THEN fr.monto ELSE 0 END), 0) AS total_regularizado,
                BOOL_OR(fr.activo = TRUE AND fr.tipo_regularizacion = 'CIERRE_MANUAL') AS cierre_manual_activo,
                COUNT(*) FILTER (WHERE fr.activo = TRUE) AS regularizaciones_activas
            FROM contabilidad.factura_regularizacion fr
            GROUP BY fr.factura_electronica_id
        ), apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado,
                COUNT(*) AS aplicaciones_activas
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR c.estado::TEXT <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado::TEXT <> 'ANULADO')
            GROUP BY fa.factura_electronica_id
        ), doc AS (
            SELECT
                da.origen_id AS factura_electronica_id,
                MAX(da.asiento_id) AS asiento_id
            FROM contabilidad.documento_asiento da
            WHERE da.tabla_origen = 'contabilidad.factura_electronica'
            GROUP BY da.origen_id
        )
        SELECT
            fe.id,
            COALESCE(fe.numero_factura, '') AS numero_factura,
            TO_CHAR(fe.fecha_emision, 'YYYY-MM-DD') AS fecha_emision_iso,
            TO_CHAR(fe.fecha_emision, 'DD/MM/YYYY') AS fecha_emision,
            COALESCE(fe.nombre_cliente, '') AS nombre_cliente,
            COALESCE(fe.nit_cliente, '') AS nit_cliente,
            COALESCE(fe.cuf, '') AS cuf,
            COALESCE(fe.moneda_codigo, '') AS moneda_codigo,
            fe.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            COALESCE(fe.nit_emisor, '') AS nit_emisor,
            COALESCE(fe.importe_total, 0) AS importe_total,
            COALESCE(fe.saldo_pendiente, 0) AS saldo_registrado,
            ROUND((
                CASE
                    WHEN fe.estado::TEXT = 'ANULADA' THEN 0
                    ELSE GREATEST(
                        COALESCE(fe.importe_total, 0)
                        - COALESCE(reg.total_regularizado, 0)
                        - COALESCE(apps.total_aplicado, 0),
                        0
                    )
                END
            )::numeric, 2) AS saldo_pendiente,
            COALESCE(fe.estado::TEXT, '') AS estado,
            COALESCE(fe.es_saldo_inicial, FALSE) AS es_saldo_inicial,
            COALESCE(fe.cuenta_cobrar_codigo, '') AS cuenta_cobrar_codigo,
            COALESCE(cta_cobrar.nombre, '') AS cuenta_cobrar_nombre,
            COALESCE(fe.cuenta_contra_codigo, '') AS cuenta_contra_codigo,
            COALESCE(cta_contra.nombre, '') AS cuenta_contra_nombre,
            fe.cliente_auxiliar_id,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(aux.nit_ci, '') AS auxiliar_nit_ci,
            TO_CHAR(fe.fecha_contabilizacion, 'DD/MM/YYYY') AS fecha_contabilizacion,
            doc.asiento_id,
            COALESCE(apps.total_aplicado, 0) AS total_aplicado,
            COALESCE(apps.aplicaciones_activas, 0) AS aplicaciones_activas,
            COALESCE(reg.total_regularizado, 0) AS total_regularizado,
            COALESCE(reg.regularizaciones_activas, 0) AS regularizaciones_activas,
            COALESCE(reg.cierre_manual_activo, FALSE) AS cierre_manual_activo,
            CASE
                WHEN fe.estado::TEXT = 'ANULADA' THEN 'ANULADA'
                WHEN COALESCE(reg.cierre_manual_activo, FALSE) = TRUE THEN 'CERRADA_MANUAL'
                WHEN ({SALDO_OPERATIVO_SQL}) <= 0 THEN 'COBRADA_TOTAL'
                WHEN COALESCE(apps.total_aplicado, 0) > 0 THEN 'COBRADA_PARCIAL'
                WHEN doc.asiento_id IS NOT NULL THEN 'CONTABILIZADA'
                WHEN fe.cliente_auxiliar_id IS NOT NULL THEN 'DISPONIBLE'
                ELSE 'RECIBIDA'
            END AS proceso_estado
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = fe.cliente_auxiliar_id
        LEFT JOIN contabilidad.cuenta cta_cobrar ON cta_cobrar.codigo = fe.cuenta_cobrar_codigo
        LEFT JOIN contabilidad.cuenta cta_contra ON cta_contra.codigo = fe.cuenta_contra_codigo
        LEFT JOIN reg ON reg.factura_electronica_id = fe.id
        LEFT JOIN apps ON apps.factura_electronica_id = fe.id
        LEFT JOIN doc ON doc.factura_electronica_id = fe.id
        {where_sql}
        ORDER BY fe.fecha_emision DESC, fe.numero_factura DESC, fe.id DESC
        """,
        tuple(params),
    )

    data = []
    for row in rows:
        proceso = row['proceso_estado'] or ''
        estado = row['estado'] or ''
        data.append({
            'id': int(row['id']),
            'numero_factura': row['numero_factura'] or '',
            'fecha_emision': row['fecha_emision'] or '',
            'fecha_emision_iso': row['fecha_emision_iso'] or '',
            'nombre_cliente': row['nombre_cliente'] or '',
            'nit_cliente': row['nit_cliente'] or '',
            'cuf': row['cuf'] or '',
            'moneda_codigo': row['moneda_codigo'] or '',
            'unidad_negocio_id': int(row['unidad_negocio_id']) if row.get('unidad_negocio_id') is not None else None,
            'unidad_negocio_codigo': row['unidad_negocio_codigo'] or '',
            'unidad_negocio_nombre': row['unidad_negocio_nombre'] or '',
            'nit_emisor': row['nit_emisor'] or '',
            'importe_total': _to_float(row['importe_total']),
            'saldo_registrado': _to_float(row['saldo_registrado']),
            'saldo_pendiente': _to_float(row['saldo_pendiente']),
            'total_aplicado': _to_float(row['total_aplicado']),
            'total_regularizado': _to_float(row['total_regularizado']),
            'estado': estado,
            'estado_label': _estado_label(estado),
            'proceso_estado': proceso,
            'proceso_label': _proceso_label(proceso),
            'es_saldo_inicial': bool(row['es_saldo_inicial']),
            'cuenta_cobrar_codigo': row['cuenta_cobrar_codigo'] or '',
            'cuenta_cobrar_nombre': row['cuenta_cobrar_nombre'] or '',
            'cuenta_contra_codigo': row['cuenta_contra_codigo'] or '',
            'cuenta_contra_nombre': row['cuenta_contra_nombre'] or '',
            'cliente_auxiliar_id': int(row['cliente_auxiliar_id']) if row.get('cliente_auxiliar_id') is not None else None,
            'auxiliar_nombre': row['auxiliar_nombre'] or '',
            'auxiliar_nit_ci': row['auxiliar_nit_ci'] or '',
            'fecha_contabilizacion': row['fecha_contabilizacion'] or '',
            'asiento_id': int(row['asiento_id']) if row.get('asiento_id') is not None else None,
            'aplicaciones_activas': int(row['aplicaciones_activas'] or 0),
            'regularizaciones_activas': int(row['regularizaciones_activas'] or 0),
            'cierre_manual_activo': bool(row['cierre_manual_activo']),
        })
    return data


def _build_summary(rows):
    pendientes = 0
    contabilizadas = 0
    cobradas_o_cerradas = 0
    observadas = 0
    monto_pendiente = Decimal('0.00')

    for row in rows:
        saldo = _to_decimal(row.get('saldo_pendiente'))
        proceso = row.get('proceso_estado')

        if proceso == 'ANULADA':
            observadas += 1
        elif proceso == 'CERRADA_MANUAL':
            cobradas_o_cerradas += 1
            observadas += 1
        elif proceso == 'COBRADA_TOTAL':
            cobradas_o_cerradas += 1
        elif saldo > 0:
            pendientes += 1
            monto_pendiente += saldo

        if row.get('asiento_id'):
            contabilizadas += 1

    return {
        'pendientes': pendientes,
        'contabilizadas': contabilizadas,
        'cobradas_o_cerradas': cobradas_o_cerradas,
        'observadas': observadas,
        'monto_pendiente': _to_float(monto_pendiente),
        'total': len(rows),
    }


def _get_factura_basica(db, factura_id):
    rows = db.execute_query(
        """
        WITH doc AS (
            SELECT MAX(asiento_id) AS asiento_id
            FROM contabilidad.documento_asiento
            WHERE tabla_origen = 'contabilidad.factura_electronica'
              AND origen_id = %s
        ), reg AS (
            SELECT
                COALESCE(SUM(CASE WHEN activo = TRUE THEN monto ELSE 0 END), 0) AS total_regularizado,
                COUNT(*) FILTER (WHERE activo = TRUE) AS regularizaciones_activas,
                BOOL_OR(activo = TRUE AND tipo_regularizacion = 'CIERRE_MANUAL') AS cierre_manual_activo
            FROM contabilidad.factura_regularizacion
            WHERE factura_electronica_id = %s
        ), apps AS (
            SELECT
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado,
                COUNT(*) AS aplicaciones_activas
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE fa.factura_electronica_id = %s
              AND (fa.cobro_id IS NULL OR c.estado::TEXT <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado::TEXT <> 'ANULADO')
        )
        SELECT
            fe.*,
            COALESCE(fe.saldo_pendiente, 0) AS saldo_registrado,
            ROUND((
                CASE
                    WHEN fe.estado::TEXT = 'ANULADA' THEN 0
                    ELSE GREATEST(
                        COALESCE(fe.importe_total, 0)
                        - COALESCE(reg.total_regularizado, 0)
                        - COALESCE(apps.total_aplicado, 0),
                        0
                    )
                END
            )::numeric, 2) AS saldo_operativo,
            COALESCE(apps.total_aplicado, 0) AS total_aplicado,
            COALESCE(apps.aplicaciones_activas, 0) AS aplicaciones_activas,
            COALESCE(reg.total_regularizado, 0) AS total_regularizado,
            COALESCE(reg.regularizaciones_activas, 0) AS regularizaciones_activas,
            COALESCE(reg.cierre_manual_activo, FALSE) AS cierre_manual_activo,
            doc.asiento_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(aux.nit_ci, '') AS auxiliar_nit_ci,
            COALESCE(cta_cobrar.nombre, '') AS cuenta_cobrar_nombre,
            COALESCE(cta_contra.nombre, '') AS cuenta_contra_nombre
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = fe.unidad_negocio_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = fe.cliente_auxiliar_id
        LEFT JOIN contabilidad.cuenta cta_cobrar ON cta_cobrar.codigo = fe.cuenta_cobrar_codigo
        LEFT JOIN contabilidad.cuenta cta_contra ON cta_contra.codigo = fe.cuenta_contra_codigo
        CROSS JOIN doc
        CROSS JOIN reg
        CROSS JOIN apps
        WHERE fe.id = %s
        LIMIT 1
        """,
        (factura_id, factura_id, factura_id, factura_id),
    )
    return rows[0] if rows else None


def _fetch_aplicaciones(db, factura_id):
    rows = db.execute_query(
        """
        SELECT
            fa.id,
            COALESCE(fa.monto_aplicado, 0) AS monto_aplicado,
            COALESCE(fa.estado_resultante::TEXT, '') AS estado_resultante,
            TO_CHAR(fa.creado_en, 'DD/MM/YYYY HH24:MI') AS creado_en,
            CASE
                WHEN fa.cobro_id IS NOT NULL THEN 'Cobro'
                WHEN fa.venta_id IS NOT NULL THEN 'Venta'
                ELSE 'Aplicación manual'
            END AS origen,
            COALESCE(fa.cobro_id, fa.venta_id) AS documento_id,
            TO_CHAR(COALESCE(c.fecha, v.fecha), 'DD/MM/YYYY') AS fecha_documento,
            COALESCE(c.estado::TEXT, v.estado::TEXT, '') AS estado_documento,
            COALESCE(c.glosa, v.glosa, '') AS glosa_documento,
            COALESCE(c.referencia, '') AS referencia_documento,
            COALESCE(c.monto_total, v.total, 0) AS total_documento
        FROM contabilidad.factura_aplicacion fa
        LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
        LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
        WHERE fa.factura_electronica_id = %s
        ORDER BY fa.creado_en DESC, fa.id DESC
        """,
        (factura_id,),
    )
    return [
        {
            'id': int(row['id']),
            'monto_aplicado': _to_float(row['monto_aplicado']),
            'estado_resultante': row['estado_resultante'] or '',
            'creado_en': row['creado_en'] or '',
            'origen': row['origen'] or '',
            'documento_id': int(row['documento_id']) if row.get('documento_id') is not None else None,
            'fecha_documento': row['fecha_documento'] or '',
            'estado_documento': row['estado_documento'] or '',
            'glosa_documento': row['glosa_documento'] or '',
            'referencia_documento': row['referencia_documento'] or '',
            'total_documento': _to_float(row['total_documento']),
        }
        for row in rows
    ]


def _fetch_regularizaciones(db, factura_id):
    rows = db.execute_query(
        """
        SELECT
            id,
            COALESCE(tipo_regularizacion, '') AS tipo_regularizacion,
            COALESCE(monto, 0) AS monto,
            COALESCE(motivo, '') AS motivo,
            COALESCE(observacion, '') AS observacion,
            COALESCE(activo, FALSE) AS activo,
            COALESCE(creado_por, '') AS creado_por,
            TO_CHAR(creado_en, 'DD/MM/YYYY HH24:MI') AS creado_en,
            COALESCE(anulado_por, '') AS anulado_por,
            TO_CHAR(anulado_en, 'DD/MM/YYYY HH24:MI') AS anulado_en
        FROM contabilidad.factura_regularizacion
        WHERE factura_electronica_id = %s
        ORDER BY creado_en DESC, id DESC
        """,
        (factura_id,),
    )
    return [
        {
            'id': int(row['id']),
            'tipo_regularizacion': row['tipo_regularizacion'] or '',
            'monto': _to_float(row['monto']),
            'motivo': row['motivo'] or '',
            'observacion': row['observacion'] or '',
            'activo': bool(row['activo']),
            'creado_por': row['creado_por'] or '',
            'creado_en': row['creado_en'] or '',
            'anulado_por': row['anulado_por'] or '',
            'anulado_en': row['anulado_en'] or '',
        }
        for row in rows
    ]


def _fetch_asiento(db, asiento_id):
    asiento_rows = db.execute_query(
        """
        SELECT
            a.id,
            TO_CHAR(a.fecha, 'DD/MM/YYYY') AS fecha,
            COALESCE(a.estado::TEXT, '') AS estado,
            COALESCE(a.moneda_codigo, '') AS moneda_codigo,
            COALESCE(a.tipo_cambio, 1) AS tipo_cambio,
            COALESCE(a.glosa, '') AS glosa,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.modulo_origen, '') AS modulo_origen,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            TO_CHAR(a.creado_en, 'DD/MM/YYYY HH24:MI') AS creado_en
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.id = %s
        LIMIT 1
        """,
        (asiento_id,),
    )
    if not asiento_rows:
        return None

    detalle_rows = db.execute_query(
        """
        SELECT
            ad.secuencia,
            ad.cuenta_codigo,
            COALESCE(c.nombre, '') AS cuenta_nombre,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(aux.nit_ci, '') AS auxiliar_nit_ci,
            COALESCE(cc.codigo, '') AS centro_costo_codigo,
            COALESCE(cc.nombre, '') AS centro_costo_nombre,
            COALESCE(ad.glosa, '') AS glosa,
            COALESCE(ad.debe, 0) AS debe,
            COALESCE(ad.haber, 0) AS haber,
            COALESCE(ad.referencia, '') AS referencia
        FROM contabilidad.asiento_detalle ad
        LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = ad.auxiliar_id
        LEFT JOIN contabilidad.centro_costo cc ON cc.id = ad.centro_costo_id
        WHERE ad.asiento_id = %s
        ORDER BY ad.secuencia ASC, ad.id ASC
        """,
        (asiento_id,),
    )

    asiento = asiento_rows[0]
    detalle = []
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')
    for row in detalle_rows:
        debe = _to_decimal(row['debe'])
        haber = _to_decimal(row['haber'])
        total_debe += debe
        total_haber += haber
        detalle.append({
            'secuencia': row['secuencia'],
            'cuenta_codigo': row['cuenta_codigo'] or '',
            'cuenta_nombre': row['cuenta_nombre'] or '',
            'auxiliar_nombre': row['auxiliar_nombre'] or '',
            'auxiliar_nit_ci': row['auxiliar_nit_ci'] or '',
            'centro_costo_codigo': row['centro_costo_codigo'] or '',
            'centro_costo_nombre': row['centro_costo_nombre'] or '',
            'glosa': row['glosa'] or '',
            'debe': _to_float(debe),
            'haber': _to_float(haber),
            'referencia': row['referencia'] or '',
        })

    unidad = ' · '.join([p for p in [asiento['unidad_codigo'], asiento['unidad_nombre']] if p])
    return {
        'asiento': {
            'id': int(asiento['id']),
            'fecha': asiento['fecha'] or '',
            'estado': asiento['estado'] or '',
            'moneda_codigo': asiento['moneda_codigo'] or '',
            'tipo_cambio': str(asiento['tipo_cambio'] or '1'),
            'glosa': asiento['glosa'] or '',
            'referencia': asiento['referencia'] or '',
            'modulo_origen': asiento['modulo_origen'] or '',
            'unidad': unidad or '—',
            'creado_en': asiento['creado_en'] or '',
        },
        'detalle': detalle,
        'totales': {
            'debe': _to_float(total_debe),
            'haber': _to_float(total_haber),
            'diferencia': _to_float(total_debe - total_haber),
        },
    }


# ============================================================
# Vistas y APIs
# ============================================================

@facturas_mantenimiento_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    with DatabaseManager() as db:
        unidades_negocio = _obtener_unidades_negocio_activas(db)

    return render_template(
        'facturas_mantenimiento_index.html',
        unidades_negocio=unidades_negocio,
        facturas_operativas_url=url_for('facturas_electronicas.index'),
    )


@facturas_mantenimiento_bp.route('/api/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_lista():
    filters = _build_filters()
    with DatabaseManager() as db:
        rows = _fetch_facturas(db, filters)
        summary = _build_summary(rows)
    return _json_ok(data=rows, summary=summary, filters=filters)


@facturas_mantenimiento_bp.route('/api/<int:factura_id>/detalle', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_detalle(factura_id):
    try:
        factura_id = _parse_int(factura_id, 'Factura')
        with DatabaseManager() as db:
            factura = _get_factura_basica(db, factura_id)
            if not factura:
                raise ValueError('La factura seleccionada no existe.')
            aplicaciones = _fetch_aplicaciones(db, factura_id)
            regularizaciones = _fetch_regularizaciones(db, factura_id)

        factura_data = {
            'id': int(factura['id']),
            'numero_factura': factura.get('numero_factura') or '',
            'fecha_emision': factura.get('fecha_emision').strftime('%d/%m/%Y') if factura.get('fecha_emision') else '',
            'nit_cliente': factura.get('nit_cliente') or '',
            'nombre_cliente': factura.get('nombre_cliente') or '',
            'cuf': factura.get('cuf') or '',
            'nit_emisor': factura.get('nit_emisor') or '',
            'moneda_codigo': factura.get('moneda_codigo') or '',
            'importe_total': _to_float(factura.get('importe_total')),
            'saldo_registrado': _to_float(factura.get('saldo_registrado')),
            'saldo_pendiente': _to_float(factura.get('saldo_operativo')),
            'total_aplicado': _to_float(factura.get('total_aplicado')),
            'total_regularizado': _to_float(factura.get('total_regularizado')),
            'estado': factura.get('estado') or '',
            'estado_label': _estado_label(factura.get('estado') or ''),
            'es_saldo_inicial': bool(factura.get('es_saldo_inicial')),
            'unidad': ' · '.join(
                [p for p in [factura.get('unidad_negocio_codigo'), factura.get('unidad_negocio_nombre')] if p]
            ),
            'auxiliar': ' · '.join(
                [p for p in [factura.get('auxiliar_nit_ci'), factura.get('auxiliar_nombre')] if p]
            ),
            'cuenta_cobrar': ' · '.join(
                [p for p in [factura.get('cuenta_cobrar_codigo'), factura.get('cuenta_cobrar_nombre')] if p]
            ),
            'cuenta_contra': ' · '.join(
                [p for p in [factura.get('cuenta_contra_codigo'), factura.get('cuenta_contra_nombre')] if p]
            ),
            'fecha_contabilizacion': factura.get('fecha_contabilizacion').strftime('%d/%m/%Y') if factura.get('fecha_contabilizacion') else '',
            'asiento_id': int(factura['asiento_id']) if factura.get('asiento_id') else None,
        }
        return _json_ok(
            data={
                'factura': factura_data,
                'aplicaciones': aplicaciones,
                'regularizaciones': regularizaciones,
            }
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception:
        return _json_error('No se pudo cargar el detalle de auditoría.', status=500)


@facturas_mantenimiento_bp.route('/api/<int:factura_id>/asiento', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_asiento(factura_id):
    try:
        factura_id = _parse_int(factura_id, 'Factura')
        with DatabaseManager() as db:
            factura = _get_factura_basica(db, factura_id)
            if not factura:
                raise ValueError('La factura seleccionada no existe.')
            asiento_id = factura.get('asiento_id')
            if not asiento_id:
                return _json_error('La factura todavía no tiene asiento contable asociado.', status=404)
            asiento_data = _fetch_asiento(db, asiento_id)
            if not asiento_data:
                return _json_error('No se encontró el asiento contable asociado.', status=404)

        asiento_data['factura'] = {
            'id': int(factura['id']),
            'numero_factura': factura.get('numero_factura') or '',
            'fecha_emision': factura.get('fecha_emision').strftime('%d/%m/%Y') if factura.get('fecha_emision') else '',
            'nit_cliente': factura.get('nit_cliente') or '',
            'nombre_cliente': factura.get('nombre_cliente') or '',
            'importe_total': _to_float(factura.get('importe_total')),
            'saldo_pendiente': _to_float(factura.get('saldo_operativo')),
        }
        return _json_ok(data=asiento_data)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception:
        return _json_error('No se pudo cargar el asiento contable.', status=500)
