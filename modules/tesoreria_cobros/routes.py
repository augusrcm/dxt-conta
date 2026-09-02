# ============================================================
# DXT CONTA - Módulo Tesorería Cobros
# Reingeniería unificada: compromiso + directo
# ============================================================

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Response, jsonify, render_template, request, session, url_for
from psycopg2 import errors

from database.db_manager import DatabaseManager
from modules.tesoreria_cobros import tesoreria_cobros_bp
from utils.decorators import login_required, roles_required
from modules.reportes_rapidos.core.utils import logo_path
from utils.documentos_pdf import build_accounting_document_pdf, format_date, format_money


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
MEDIOS_OPERABLES = ['CAJA', 'BANCO']
ESTADOS_DOCUMENTO = ['BORRADOR', 'CONFIRMADO', 'ANULADO']
ORIGENES_OPERACION = ['COMPROMISO', 'DIRECTO', 'DOCUMENTO_COBRAR']
CUANTIA = Decimal('0.01')
CUANTIA_TC = Decimal('0.000001')


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
    return (value or '').strip()



def _decimal(value, field_name, allow_zero=False, quant=CUANTIA, required=True):
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None

    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError):
        raise ValueError(f'El campo "{field_name}" no tiene un formato válido.')

    if allow_zero:
        if number < 0:
            raise ValueError(f'El campo "{field_name}" no puede ser negativo.')
    else:
        if number <= 0:
            raise ValueError(f'El campo "{field_name}" debe ser mayor a cero.')

    return number.quantize(quant, rounding=ROUND_HALF_UP)



def _parse_int(value, field_name, required=True):
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field_name}" debe ser numérico.')



def _parse_date(value, field_name='Fecha', required=True):
    if not value:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.')



def _truncate(value, max_len):
    value = value or ''
    return value[:max_len]



def _normalize_text(value, field_name, max_len, required=False):
    value = _clean(value)
    if required and not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(value) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return value or None



def _to_float(value):
    if value is None:
        return None
    return float(Decimal(str(value)))



def _usuario_actual():
    return (
        session.get('username')
        or session.get('usuario')
        or session.get('email')
        or session.get('user_id')
        or 'sistema'
    )



def _puede_editar():
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except Exception:
        return False



def _gestion_actual():
    return date.today().year



def _tabla_cuentas(db):
    rows = db.execute_query("SELECT to_regclass('contabilidad.cuentas') AS tabla_plural")
    if rows and rows[0]['tabla_plural']:
        return 'contabilidad.cuentas'
    return 'contabilidad.cuenta'



def _enum_values(db, type_name):
    rows = db.execute_query(
        """
        SELECT enumlabel
        FROM pg_enum
        WHERE enumtypid = %s::regtype
        ORDER BY enumsortorder
        """,
        (f'contabilidad.{type_name}',),
    )
    return [row['enumlabel'] for row in rows]


def _get_unidades_negocio(db, incluir_inactivas=False):
    condiciones = [] if incluir_inactivas else ['activo = TRUE']
    where_sql = f"WHERE {' AND '.join(condiciones)}" if condiciones else ''
    return db.execute_query(
        f"""
        SELECT id, codigo, nombre, COALESCE(nit, '') AS nit, activo
        FROM contabilidad.unidad_negocio
        {where_sql}
        ORDER BY nombre, codigo, id
        """
    )


def _get_unidad_row(db, unidad_negocio_id, permitir_inactiva=False):
    if not unidad_negocio_id:
        return None
    condiciones = ['id = %s']
    if not permitir_inactiva:
        condiciones.append('activo = TRUE')
    rows = db.execute_query(
        f"""
        SELECT id, codigo, nombre, COALESCE(nit, '') AS nit, activo
        FROM contabilidad.unidad_negocio
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        (unidad_negocio_id,),
    )
    return rows[0] if rows else None




def _get_rubros(db, incluir_inactivos=False):
    condiciones = [] if incluir_inactivos else ['activo = TRUE']
    where_sql = f"WHERE {' AND '.join(condiciones)}" if condiciones else ''
    return db.execute_query(
        f"""
        SELECT id, codigo, nombre, COALESCE(descripcion, '') AS descripcion, activo
        FROM contabilidad.rubro_operacion
        {where_sql}
        ORDER BY activo DESC, nombre, codigo, id
        """
    )



def _get_rubro_row(db, rubro_id, permitir_inactivo=False):
    if not rubro_id:
        return None
    condiciones = ['id = %s']
    if not permitir_inactivo:
        condiciones.append('activo = TRUE')
    rows = db.execute_query(
        f"""
        SELECT id, codigo, nombre, COALESCE(descripcion, '') AS descripcion, activo
        FROM contabilidad.rubro_operacion
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        (rubro_id,),
    )
    return rows[0] if rows else None

def _get_publicidad_elemento_row(db, elemento_id, unidad_negocio_id=None, permitir_inactivo=False):
    if not elemento_id:
        return None

    condiciones = ['e.id = %s', "COALESCE(btrim(e.codigo_gamlp), '') <> ''"]
    params = [elemento_id]

    if not permitir_inactivo:
        condiciones.extend(["e.estado = 'ACTIVA'", "s.estado = 'ACTIVA'"])

    if unidad_negocio_id:
        condiciones.append('s.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    rows = db.execute_query(
        f"""
        SELECT
            'ELEMENTO' AS ref_tipo,
            'E:' || e.id::text AS ref_key,
            e.id AS ref_id,
            e.id,
            e.codigo_gamlp,
            e.codigo AS elemento_codigo,
            e.nombre AS elemento_nombre,
            s.id AS estructura_id,
            s.codigo AS estructura_codigo,
            s.nombre AS estructura_nombre,
            s.unidad_negocio_id,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            e.codigo_gamlp || ' ' || e.nombre || ' - ELEMENTO' AS etiqueta
        FROM publicidad.elemento_publicitario e
        INNER JOIN publicidad.estructura_publicitaria s ON s.id = e.estructura_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = s.unidad_negocio_id
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        tuple(params),
    )
    return rows[0] if rows else None

def _get_publicidad_estructura_row(db, estructura_id, unidad_negocio_id=None, permitir_inactiva=False):
    if not estructura_id:
        return None

    condiciones = ['s.id = %s', "COALESCE(btrim(s.codigo_gamlp), '') <> ''"]
    params = [estructura_id]

    if not permitir_inactiva:
        condiciones.append("s.estado = 'ACTIVA'")

    if unidad_negocio_id:
        condiciones.append('s.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    rows = db.execute_query(
        f"""
        SELECT
            'ESTRUCTURA' AS ref_tipo,
            'S:' || s.id::text AS ref_key,
            s.id AS ref_id,
            NULL::bigint AS id,
            s.codigo_gamlp,
            NULL::text AS elemento_codigo,
            NULL::text AS elemento_nombre,
            s.id AS estructura_id,
            s.codigo AS estructura_codigo,
            s.nombre AS estructura_nombre,
            s.unidad_negocio_id,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            s.codigo_gamlp || ' ' || s.nombre || ' - ESTRUCTURA' AS etiqueta
        FROM publicidad.estructura_publicitaria s
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = s.unidad_negocio_id
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        tuple(params),
    )
    return rows[0] if rows else None



def _get_publicidad_reference_row(db, referencia_raw, unidad_negocio_id=None, permitir_inactivo=False):
    ref = str(referencia_raw or '').strip()
    if not ref:
        return None
    if ref.startswith('E:'):
        return _get_publicidad_elemento_row(db, _parse_int(ref.split(':', 1)[1], 'Elemento publicitario'), unidad_negocio_id=unidad_negocio_id, permitir_inactivo=permitir_inactivo)
    if ref.startswith('S:'):
        return _get_publicidad_estructura_row(db, _parse_int(ref.split(':', 1)[1], 'Estructura publicitaria'), unidad_negocio_id=unidad_negocio_id, permitir_inactiva=permitir_inactivo)
    return _get_publicidad_elemento_row(db, _parse_int(ref, 'Elemento publicitario'), unidad_negocio_id=unidad_negocio_id, permitir_inactivo=permitir_inactivo)



def _get_publicidad_elementos_catalog(db):
    return db.execute_query(
        """
        SELECT *
        FROM (
            SELECT
                'ELEMENTO' AS ref_tipo,
                'E:' || e.id::text AS ref_key,
                e.id AS ref_id,
                e.id,
                e.codigo_gamlp,
                e.codigo AS elemento_codigo,
                e.nombre AS elemento_nombre,
                s.id AS estructura_id,
                s.codigo AS estructura_codigo,
                s.nombre AS estructura_nombre,
                s.unidad_negocio_id,
                COALESCE(un.codigo, '') AS unidad_negocio_codigo,
                COALESCE(un.nombre, '') AS unidad_negocio_nombre,
                e.codigo_gamlp || ' ' || e.nombre || ' - ELEMENTO' AS etiqueta
            FROM publicidad.elemento_publicitario e
            INNER JOIN publicidad.estructura_publicitaria s ON s.id = e.estructura_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = s.unidad_negocio_id
            WHERE e.estado = 'ACTIVA'
              AND s.estado = 'ACTIVA'
              AND COALESCE(btrim(e.codigo_gamlp), '') <> ''
            UNION ALL
            SELECT
                'ESTRUCTURA' AS ref_tipo,
                'S:' || s.id::text AS ref_key,
                s.id AS ref_id,
                NULL::bigint AS id,
                s.codigo_gamlp,
                NULL::text AS elemento_codigo,
                NULL::text AS elemento_nombre,
                s.id AS estructura_id,
                s.codigo AS estructura_codigo,
                s.nombre AS estructura_nombre,
                s.unidad_negocio_id,
                COALESCE(un.codigo, '') AS unidad_negocio_codigo,
                COALESCE(un.nombre, '') AS unidad_negocio_nombre,
                s.codigo_gamlp || ' ' || s.nombre || ' - ESTRUCTURA' AS etiqueta
            FROM publicidad.estructura_publicitaria s
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = s.unidad_negocio_id
            WHERE s.estado = 'ACTIVA'
              AND COALESCE(btrim(s.codigo_gamlp), '') <> ''
        ) q
        ORDER BY codigo_gamlp ASC, etiqueta ASC
        """
    )


# ============================================================
# Catálogos y consultas
# ============================================================

def _get_tipo_cambio_row(db, fecha_operacion):
    rows = db.execute_query(
        """
        SELECT fecha, usd_paralelo, ufv
        FROM contabilidad.tipo_cambio
        WHERE fecha = %s
        LIMIT 1
        """,
        (fecha_operacion,),
    )
    if rows:
        row = rows[0]
        return {
            'existe': True,
            'fecha': row['fecha'],
            'usd_paralelo': Decimal(str(row['usd_paralelo'])).quantize(CUANTIA_TC),
            'ufv': Decimal(str(row['ufv'])).quantize(CUANTIA_TC),
        }
    return {
        'existe': False,
        'fecha': fecha_operacion,
        'usd_paralelo': Decimal('1').quantize(CUANTIA_TC),
        'ufv': Decimal('1').quantize(CUANTIA_TC),
    }



def _resolve_tipo_cambio_aplicado(moneda_codigo, tc_row):
    codigo = (moneda_codigo or '').upper()
    if codigo == 'USD':
        return tc_row['usd_paralelo']
    if codigo == 'UFV':
        return tc_row['ufv']
    return Decimal('1').quantize(CUANTIA_TC)



def _get_catalogs(db):
    tabla_cuentas = _tabla_cuentas(db)

    monedas = db.execute_query(
        """
        SELECT codigo, nombre, COALESCE(simbolo, '') AS simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        ORDER BY codigo
        """
    )

    cajas = db.execute_query(
        """
        SELECT id, codigo, nombre, cuenta_contable_codigo
        FROM contabilidad.caja
        WHERE activo = TRUE
        ORDER BY nombre
        """
    )

    bancos = db.execute_query(
        """
        SELECT
            b.id,
            b.nombre_banco,
            b.numero_cuenta,
            b.moneda_codigo,
            b.cuenta_contable_codigo,
            COALESCE(a.nombre, b.titular, '') AS titular
        FROM contabilidad.cuenta_bancaria b
        LEFT JOIN contabilidad.auxiliar a ON a.id = b.auxiliar_id
        WHERE b.activo = TRUE
        ORDER BY b.nombre_banco, b.numero_cuenta
        """
    )

    unidades_negocio = _get_unidades_negocio(db)
    rubros = _get_rubros(db)
    publicidad_elementos = _get_publicidad_elementos_catalog(db)
    medios = [m for m in _enum_values(db, 'medio_pago_enum') if m in MEDIOS_OPERABLES]

    cuentas = db.execute_query(
        f"""
        SELECT
            codigo,
            nombre,
            COALESCE(requiere_auxiliar, FALSE) AS requiere_auxiliar,
            COALESCE(requiere_cc, FALSE) AS requiere_cc
        FROM {tabla_cuentas}
        WHERE activo = TRUE
          AND es_postable = TRUE
        ORDER BY codigo
        LIMIT 300
        """
    )

    return {
        'unidades_negocio': unidades_negocio,
        'rubros': rubros,
        'medios': medios,
        'monedas': monedas,
        'cajas': cajas,
        'bancos': bancos,
        'cuentas': cuentas,
        'publicidad_elementos': publicidad_elementos,
        'tipo_cambio_url_base': url_for('tipo_cambio.gestion'),
    }


def _get_account_row(db, codigo):
    tabla_cuentas = _tabla_cuentas(db)
    rows = db.execute_query(
        f"""
        SELECT
            codigo,
            nombre,
            COALESCE(requiere_auxiliar, FALSE) AS requiere_auxiliar,
            COALESCE(requiere_cc, FALSE) AS requiere_cc
        FROM {tabla_cuentas}
        WHERE activo = TRUE
          AND es_postable = TRUE
          AND codigo = %s
        LIMIT 1
        """,
        (codigo,),
    )
    return rows[0] if rows else None



def _get_auxiliar_row(db, auxiliar_id):
    rows = db.execute_query(
        """
        SELECT id, nombre, activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,),
    )
    return rows[0] if rows else None



def _get_cobro_header(db, cobro_id):
    rows = db.execute_query(
        """
        SELECT
            p.id,
            p.fecha,
            p.unidad_negocio_id,
            p.cliente_auxiliar_id,
            p.medio_pago,
            p.contra_cuenta_codigo,
            p.caja_id,
            p.cuenta_bancaria_id,
            p.moneda_codigo,
            p.tipo_cambio,
            p.monto_total,
            p.referencia,
            p.glosa,
            p.estado,
            p.asiento_id,
            p.origen_operacion,
            p.rubro_id,
            p.publicidad_elemento_id_ref,
            COALESCE(pe.codigo_gamlp, se.codigo_gamlp, p.publicidad_elemento_codigo_ref, '') AS publicidad_elemento_codigo_ref,
            CASE
                WHEN pe.id IS NOT NULL THEN pe.codigo_gamlp || ' ' || pe.nombre || ' - ELEMENTO'
                WHEN se.id IS NOT NULL THEN se.codigo_gamlp || ' ' || se.nombre || ' - ESTRUCTURA'
                ELSE COALESCE(p.publicidad_elemento_codigo_ref, '')
            END AS publicidad_elemento_etiqueta,
            CASE
                WHEN pe.id IS NOT NULL THEN 'E:' || pe.id::text
                WHEN se.id IS NOT NULL THEN 'S:' || se.id::text
                ELSE NULL
            END AS publicidad_referencia_key,
            p.vigencia_desde,
            p.vigencia_hasta,
            p.cliente_nit_ci_ref,
            p.cliente_nombre_ref,
            p.creado_en,
            p.actualizado_en,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(aux.nombre, '') AS cliente_nombre,
            COALESCE(cuenta.nombre, '') AS contra_cuenta_nombre,
            COALESCE(rub.codigo, '') AS rubro_codigo,
            COALESCE(rub.nombre, '') AS rubro_nombre,
            CASE
                WHEN p.caja_id IS NOT NULL THEN caja.nombre
                WHEN p.cuenta_bancaria_id IS NOT NULL THEN banco.nombre_banco || ' · ' || banco.numero_cuenta
                ELSE ''
            END AS medio_nombre,
            CASE
                WHEN p.caja_id IS NOT NULL THEN caja.cuenta_contable_codigo
                WHEN p.cuenta_bancaria_id IS NOT NULL THEN banco.cuenta_contable_codigo
                ELSE NULL
            END AS cuenta_ingreso_codigo
        FROM contabilidad.cobro p
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = p.unidad_negocio_id
        LEFT JOIN contabilidad.rubro_operacion rub ON rub.id = p.rubro_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = p.cliente_auxiliar_id
        LEFT JOIN contabilidad.caja caja ON caja.id = p.caja_id
        LEFT JOIN contabilidad.cuenta_bancaria banco ON banco.id = p.cuenta_bancaria_id
        LEFT JOIN contabilidad.cuenta cuenta ON cuenta.codigo = p.contra_cuenta_codigo
        LEFT JOIN publicidad.elemento_publicitario pe ON pe.id = p.publicidad_elemento_id_ref
        LEFT JOIN publicidad.estructura_publicitaria esp ON esp.id = pe.estructura_id
        LEFT JOIN publicidad.estructura_publicitaria se ON se.codigo_gamlp = p.publicidad_elemento_codigo_ref AND p.publicidad_elemento_id_ref IS NULL
        WHERE p.id = %s
        LIMIT 1
        """,
        (cobro_id,),
    )
    return rows[0] if rows else None


def _get_cobro_detail_rows(db, cobro_id):
    rows = db.execute_query(
        """
        SELECT
            pd.id,
            pd.cobro_id,
            pd.secuencia,
            pd.tipo_linea,
            pd.compromiso_detalle_id,
            pd.descripcion,
            pd.cantidad,
            pd.precio_unitario,
            pd.subtotal,
            pd.observacion,
            d.fecha_vencimiento,
            d.monto_programado,
            d.monto_registrado,
            d.estado AS compromiso_estado,
            c.id AS compromiso_id,
            c.codigo AS compromiso_codigo,
            c.nombre AS compromiso_nombre,
            c.cuenta_contable,
            c.auxiliar_id,
            c.unidad_negocio_id,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre
        FROM contabilidad.cobro_detalle pd
        LEFT JOIN contabilidad.compromiso_detalle d ON d.id = pd.compromiso_detalle_id
        LEFT JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = c.unidad_negocio_id
        WHERE pd.cobro_id = %s
        ORDER BY pd.secuencia, pd.id
        """,
        (cobro_id,),
    )

    data = []
    for row in rows:
        data.append({
            'id': row['id'],
            'cobro_id': row['cobro_id'],
            'secuencia': row['secuencia'],
            'tipo_linea': row['tipo_linea'],
            'compromiso_detalle_id': row['compromiso_detalle_id'],
            'descripcion': row['descripcion'],
            'cantidad': _to_float(row['cantidad']),
            'precio_unitario': _to_float(row['precio_unitario']),
            'subtotal': _to_float(row['subtotal']),
            'observacion': row['observacion'] or '',
            'fecha_vencimiento': row['fecha_vencimiento'].isoformat() if row['fecha_vencimiento'] else None,
            'monto_programado': _to_float(row['monto_programado']) if row['monto_programado'] is not None else None,
            'monto_registrado': _to_float(row['monto_registrado']) if row['monto_registrado'] is not None else None,
            'compromiso_estado': row['compromiso_estado'],
            'compromiso_id': row['compromiso_id'],
            'compromiso_codigo': row['compromiso_codigo'],
            'compromiso_nombre': row['compromiso_nombre'],
            'cuenta_contable': row['cuenta_contable'],
            'auxiliar_id': row['auxiliar_id'],
            'auxiliar_nombre': row['auxiliar_nombre'],
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
        })
    return data



def _get_cobro_factura_ids(db, cobro_id):
    rows = db.execute_query(
        """
        SELECT factura_electronica_id
        FROM contabilidad.factura_aplicacion
        WHERE cobro_id = %s
        ORDER BY factura_electronica_id
        """,
        (cobro_id,),
    )
    return [int(row['factura_electronica_id']) for row in rows if row.get('factura_electronica_id')]



def _get_cobro_factura_rows(db, cobro_id):
    rows = db.execute_query(
        """
        WITH reg AS (
            SELECT
                factura_electronica_id,
                COALESCE(SUM(monto), 0) AS total_regularizado
            FROM contabilidad.factura_regularizacion
            WHERE activo = TRUE
            GROUP BY factura_electronica_id
        ), apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
            GROUP BY fa.factura_electronica_id
        )
        SELECT
            fa.factura_electronica_id AS factura_id,
            fe.numero_factura,
            fe.fecha_emision,
            COALESCE(fe.nombre_cliente, '') AS nombre_cliente,
            COALESCE(fe.nit_cliente, '') AS nit_cliente,
            fe.moneda_codigo,
            fe.estado,
            fe.cliente_auxiliar_id,
            fe.unidad_negocio_id,
            COALESCE(fe.cuenta_cobrar_codigo, '') AS cuenta_cobrar_codigo,
            COALESCE(fe.cuenta_contra_codigo, '') AS cuenta_contra_codigo,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            fe.importe_total,
            COALESCE(fa.monto_aplicado, 0) AS monto_aplicado,
            GREATEST(
                COALESCE(fe.importe_total, 0)
                - COALESCE(reg.total_regularizado, 0)
                - GREATEST(COALESCE(apps.total_aplicado, 0) - COALESCE(fa.monto_aplicado, 0), 0),
                0
            ) AS saldo_disponible
        FROM contabilidad.factura_aplicacion fa
        INNER JOIN contabilidad.factura_electronica fe ON fe.id = fa.factura_electronica_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = fe.unidad_negocio_id
        LEFT JOIN reg ON reg.factura_electronica_id = fe.id
        LEFT JOIN apps ON apps.factura_electronica_id = fe.id
        WHERE fa.cobro_id = %s
        ORDER BY fe.fecha_emision DESC, fe.numero_factura DESC, fe.id DESC
        """,
        (cobro_id,),
    )

    data = []
    for row in rows:
        data.append({
            'factura_id': int(row['factura_id']),
            'numero_factura': row['numero_factura'] or '',
            'fecha_emision': row['fecha_emision'].isoformat() if row['fecha_emision'] else None,
            'nombre_cliente': row['nombre_cliente'] or '',
            'nit_cliente': row['nit_cliente'] or '',
            'moneda_codigo': row['moneda_codigo'] or 'BOB',
            'estado': row['estado'],
            'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
            'cuenta_cobrar_codigo': row.get('cuenta_cobrar_codigo') or '',
            'cuenta_contra_codigo': row.get('cuenta_contra_codigo') or '',
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
            'importe_total': _to_float(row['importe_total']),
            'monto_aplicado': _to_float(row['monto_aplicado']),
            'saldo_disponible': _to_float(row['saldo_disponible']),
        })
    return data


def _get_factura_financial_map(db, factura_ids, current_cobro_id=None):
    factura_ids = [int(item) for item in factura_ids if item]
    if not factura_ids:
        return {}

    params = []
    exclude_current = ''
    if current_cobro_id:
        exclude_current = ' AND (fa.cobro_id IS NULL OR fa.cobro_id <> %s)'
        params.append(current_cobro_id)

    current_cte = 'SELECT NULL::BIGINT AS factura_electronica_id, NULL::NUMERIC AS monto_actual WHERE FALSE'
    if current_cobro_id:
        current_cte = """
            SELECT
                factura_electronica_id,
                COALESCE(SUM(monto_aplicado), 0) AS monto_actual
            FROM contabilidad.factura_aplicacion
            WHERE cobro_id = %s
            GROUP BY factura_electronica_id
        """
        params.append(current_cobro_id)

    params.append(factura_ids)
    rows = db.execute_query(
        f"""
        WITH reg AS (
            SELECT
                factura_electronica_id,
                COALESCE(SUM(monto), 0) AS total_regularizado
            FROM contabilidad.factura_regularizacion
            WHERE activo = TRUE
            GROUP BY factura_electronica_id
        ), apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
              {exclude_current}
            GROUP BY fa.factura_electronica_id
        ), current_apps AS (
            {current_cte}
        )
        SELECT
            fe.id,
            fe.numero_factura,
            fe.fecha_emision,
            COALESCE(fe.nombre_cliente, '') AS nombre_cliente,
            COALESCE(fe.nit_cliente, '') AS nit_cliente,
            fe.moneda_codigo,
            fe.estado,
            fe.cliente_auxiliar_id,
            fe.unidad_negocio_id,
            COALESCE(fe.cuenta_cobrar_codigo, '') AS cuenta_cobrar_codigo,
            COALESCE(fe.cuenta_contra_codigo, '') AS cuenta_contra_codigo,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(fe.importe_total, 0) AS importe_total,
            COALESCE(reg.total_regularizado, 0) AS total_regularizado,
            COALESCE(apps.total_aplicado, 0) AS total_aplicado,
            COALESCE(current_apps.monto_actual, 0) AS monto_actual_cobro,
            GREATEST(
                COALESCE(fe.importe_total, 0)
                - COALESCE(reg.total_regularizado, 0)
                - COALESCE(apps.total_aplicado, 0),
                0
            ) AS saldo_disponible
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = fe.unidad_negocio_id
        LEFT JOIN reg ON reg.factura_electronica_id = fe.id
        LEFT JOIN apps ON apps.factura_electronica_id = fe.id
        LEFT JOIN current_apps ON current_apps.factura_electronica_id = fe.id
        WHERE fe.id = ANY(%s)
        """,
        tuple(params),
    )

    data = {}
    for row in rows:
        data[int(row['id'])] = row
    return data



def _search_facturas_disponibles(db, current_cobro_id=None, texto=None, unidad_negocio_id=None, factura_id=None, limit=80):
    texto = _clean(texto)
    params = []
    exclude_current = ''
    if current_cobro_id:
        exclude_current = ' AND (fa.cobro_id IS NULL OR fa.cobro_id <> %s)'
        params.append(current_cobro_id)

    current_cte = 'SELECT NULL::BIGINT AS factura_electronica_id, NULL::NUMERIC AS monto_actual WHERE FALSE'
    if current_cobro_id:
        current_cte = """
            SELECT
                factura_electronica_id,
                COALESCE(SUM(monto_aplicado), 0) AS monto_actual
            FROM contabilidad.factura_aplicacion
            WHERE cobro_id = %s
            GROUP BY factura_electronica_id
        """
        params.append(current_cobro_id)

    where_unidad = ''
    if unidad_negocio_id:
        where_unidad = ' AND fe.unidad_negocio_id = %s'
        params.append(int(unidad_negocio_id))

    where_factura = ''
    if factura_id:
        where_factura = ' AND fe.id = %s'
        params.append(int(factura_id))

    where_search = ''
    if texto:
        like = f'%{texto}%'
        params.extend([like, like, like, like, like])
        where_search = """
          AND (
                fe.numero_factura ILIKE %s
             OR COALESCE(fe.nombre_cliente, '') ILIKE %s
             OR COALESCE(fe.nit_cliente, '') ILIKE %s
             OR CAST(COALESCE(fe.importe_total, 0) AS TEXT) ILIKE %s
             OR CAST(
                  GREATEST(
                    COALESCE(fe.importe_total, 0)
                    - COALESCE(reg.total_regularizado, 0)
                    - COALESCE(apps.total_aplicado, 0),
                    0
                  ) AS TEXT
                ) ILIKE %s
          )
        """

    params.append(limit)
    rows = db.execute_query(
        f"""
        WITH reg AS (
            SELECT
                factura_electronica_id,
                COALESCE(SUM(monto), 0) AS total_regularizado
            FROM contabilidad.factura_regularizacion
            WHERE activo = TRUE
            GROUP BY factura_electronica_id
        ), apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
              {exclude_current}
            GROUP BY fa.factura_electronica_id
        ), current_apps AS (
            {current_cte}
        )
        SELECT
            fe.id,
            fe.numero_factura,
            fe.fecha_emision,
            COALESCE(fe.nombre_cliente, '') AS nombre_cliente,
            COALESCE(fe.nit_cliente, '') AS nit_cliente,
            fe.moneda_codigo,
            fe.estado,
            fe.cliente_auxiliar_id,
            fe.unidad_negocio_id,
            COALESCE(fe.cuenta_cobrar_codigo, '') AS cuenta_cobrar_codigo,
            COALESCE(fe.cuenta_contra_codigo, '') AS cuenta_contra_codigo,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(fe.importe_total, 0) AS importe_total,
            COALESCE(current_apps.monto_actual, 0) AS monto_actual_cobro,
            GREATEST(
                COALESCE(fe.importe_total, 0)
                - COALESCE(reg.total_regularizado, 0)
                - COALESCE(apps.total_aplicado, 0),
                0
            ) AS saldo_disponible
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = fe.unidad_negocio_id
        LEFT JOIN reg ON reg.factura_electronica_id = fe.id
        LEFT JOIN apps ON apps.factura_electronica_id = fe.id
        LEFT JOIN current_apps ON current_apps.factura_electronica_id = fe.id
        WHERE fe.estado <> 'ANULADA'
          AND COALESCE(fe.cuenta_cobrar_codigo, '') <> ''
          AND (
                GREATEST(
                    COALESCE(fe.importe_total, 0)
                    - COALESCE(reg.total_regularizado, 0)
                    - COALESCE(apps.total_aplicado, 0),
                    0
                ) > 0
                OR COALESCE(current_apps.monto_actual, 0) > 0
              )
          {where_unidad}
          {where_factura}
          {where_search}
        ORDER BY fe.fecha_emision DESC, fe.id DESC
        LIMIT %s
        """,
        tuple(params),
    )

    data = []
    for row in rows:
        data.append({
            'id': int(row['id']),
            'numero_factura': row['numero_factura'] or '',
            'fecha_emision': row['fecha_emision'].isoformat() if row['fecha_emision'] else None,
            'nombre_cliente': row['nombre_cliente'] or '',
            'nit_cliente': row['nit_cliente'] or '',
            'moneda_codigo': row['moneda_codigo'] or 'BOB',
            'estado': row['estado'],
            'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
            'cuenta_cobrar_codigo': row.get('cuenta_cobrar_codigo') or '',
            'cuenta_contra_codigo': row.get('cuenta_contra_codigo') or '',
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
            'importe_total': _to_float(row['importe_total']),
            'saldo_disponible': _to_float(row['saldo_disponible']),
            'monto_actual_cobro': _to_float(row['monto_actual_cobro']),
        })
    return data



def _validate_factura_links(db, payload, monto_total, current_cobro_id=None):
    items = payload.get('facturas_aplicadas') or []
    if items in (None, ''):
        items = []
    if not isinstance(items, list):
        raise ValueError('Las facturas aplicadas no tienen un formato válido.')

    if not items:
        return {'facturas': [], 'monto_total': Decimal('0.00')}

    cleaned = []
    seen = set()
    factura_ids = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError('Una factura aplicada no tiene un formato válido.')
        factura_id = _parse_int(item.get('factura_id'), f'Factura {idx}')
        if factura_id in seen:
            raise ValueError('No puedes repetir la misma factura dentro del cobro.')
        monto_aplicado = _decimal(item.get('monto_aplicado'), f'Monto aplicado de la factura {idx}')
        seen.add(factura_id)
        factura_ids.append(factura_id)
        cleaned.append({'factura_id': factura_id, 'monto_aplicado': monto_aplicado})

    financials = _get_factura_financial_map(
        db,
        factura_ids,
        current_cobro_id=current_cobro_id,
    )

    unidad_negocio_id = _parse_int(payload.get('unidad_negocio_id'), 'Unidad de negocio')

    total_aplicado = Decimal('0.00')
    rows = []
    clientes = set()
    for item in cleaned:
        row = financials.get(item['factura_id'])
        if not row:
            raise ValueError(f'La factura #{item["factura_id"]} ya no está disponible.')
        if row['estado'] == 'ANULADA':
            raise ValueError(f'La factura {row["numero_factura"]} está anulada.')
        if int(row['unidad_negocio_id'] or 0) != int(unidad_negocio_id):
            raise ValueError(f'La factura {row["numero_factura"]} pertenece a otra unidad de negocio.')
        if not _clean(row.get('cuenta_cobrar_codigo')):
            raise ValueError(
                f'La factura {row["numero_factura"]} aún no está contabilizada. '
                'Primero debe generarse el asiento desde Facturas Electrónicas.'
            )

        disponible = Decimal(str(row['saldo_disponible'] or 0)).quantize(CUANTIA)
        monto = item['monto_aplicado'].quantize(CUANTIA)
        if monto <= 0:
            raise ValueError(f'La factura {row["numero_factura"]} debe tener un monto aplicado mayor a cero.')
        if monto > disponible:
            raise ValueError(
                f'La factura {row["numero_factura"]} solo tiene {disponible} disponible para este cobro.'
            )

        total_aplicado += monto
        rows.append({
            'factura_id': int(row['id']),
            'numero_factura': row['numero_factura'] or '',
            'nombre_cliente': row['nombre_cliente'] or '',
            'nit_cliente': row['nit_cliente'] or '',
            'moneda_codigo': row['moneda_codigo'] or 'BOB',
            'unidad_negocio_id': row['unidad_negocio_id'],
            'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
            'cuenta_cobrar_codigo': row.get('cuenta_cobrar_codigo') or '',
            'cuenta_contra_codigo': row.get('cuenta_contra_codigo') or '',
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
            'monto_aplicado': monto,
            'saldo_disponible': disponible,
        })

    if total_aplicado > monto_total:
        raise ValueError('El total aplicado a facturas no puede exceder el total del cobro.')

    return {'facturas': rows, 'monto_total': total_aplicado.quantize(CUANTIA)}

def _sync_factura_aplicacion(db, cobro_id, facturas):
    db.execute_delete(
        'DELETE FROM contabilidad.factura_aplicacion WHERE cobro_id = %s',
        (cobro_id,),
    )

    for item in facturas:
        db.execute_insert(
            """
            INSERT INTO contabilidad.factura_aplicacion (
                cobro_id,
                factura_electronica_id,
                monto_aplicado
            ) VALUES (%s, %s, %s)
            """,
            (
                cobro_id,
                item['factura_id'],
                item['monto_aplicado'],
            ),
            return_id=False,
        )


def _recalculate_factura(db, factura_id):
    rows = db.execute_query(
        """
        WITH reg AS (
            SELECT COALESCE(SUM(monto), 0) AS total_regularizado
            FROM contabilidad.factura_regularizacion
            WHERE factura_electronica_id = %s
              AND activo = TRUE
        ), apps AS (
            SELECT COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE fa.factura_electronica_id = %s
              AND (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
        )
        SELECT
            fe.id,
            fe.estado,
            fe.cliente_auxiliar_id,
            fe.unidad_negocio_id,
            COALESCE(fe.cuenta_cobrar_codigo, '') AS cuenta_cobrar_codigo,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(fe.importe_total, 0) AS importe_total,
            COALESCE(reg.total_regularizado, 0) AS total_regularizado,
            COALESCE(apps.total_aplicado, 0) AS total_aplicado
        FROM contabilidad.factura_electronica fe
        LEFT JOIN contabilidad.unidad_negocio uneg 
            ON uneg.id = fe.unidad_negocio_id
        CROSS JOIN reg
        CROSS JOIN apps
        WHERE fe.id = %s
        LIMIT 1
        """,
        (factura_id, factura_id, factura_id),
    )
    if not rows:
        return

    row = rows[0]
    if row['estado'] == 'ANULADA':
        saldo = Decimal('0.00')
        nuevo_estado = 'ANULADA'
    else:
        importe_total = Decimal(str(row['importe_total'] or 0)).quantize(CUANTIA)
        total_regularizado = Decimal(str(row['total_regularizado'] or 0)).quantize(CUANTIA)
        total_aplicado = Decimal(str(row['total_aplicado'] or 0)).quantize(CUANTIA)
        saldo = max(importe_total - total_regularizado - total_aplicado, Decimal('0.00')).quantize(CUANTIA)
        if saldo <= 0:
            nuevo_estado = 'COBRADA_TOTAL'
        elif (total_regularizado + total_aplicado) > 0:
            nuevo_estado = 'COBRADA_PARCIAL'
        elif row.get('cuenta_cobrar_codigo'):
            nuevo_estado = 'REGISTRADA'
        elif row['cliente_auxiliar_id']:
            nuevo_estado = 'DISPONIBLE'
        else:
            nuevo_estado = 'RECIBIDA'

    db.execute_update(
        """
        UPDATE contabilidad.factura_electronica
        SET saldo_pendiente = %s,
            estado = %s::contabilidad.estado_factura_ext_enum,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (saldo, nuevo_estado, factura_id),
    )



def _recalculate_facturas(db, factura_ids):
    for factura_id in sorted({int(item) for item in factura_ids if item}):
        _recalculate_factura(db, factura_id)




def _get_cobro_documento_ids(db, cobro_id):
    rows = db.execute_query(
        """
        SELECT documento_por_cobrar_id
        FROM contabilidad.documento_por_cobrar_aplicacion
        WHERE cobro_id = %s
        ORDER BY documento_por_cobrar_id
        """,
        (cobro_id,),
    )
    return [int(row['documento_por_cobrar_id']) for row in rows if row.get('documento_por_cobrar_id')]


def _documento_cobrar_disponible_sql(current_cobro_id=False):
    current_cte = "SELECT NULL::BIGINT AS documento_por_cobrar_id, NULL::NUMERIC AS monto_actual WHERE FALSE"
    if current_cobro_id:
        current_cte = """
            SELECT
                documento_por_cobrar_id,
                COALESCE(SUM(monto_aplicado), 0) AS monto_actual
            FROM contabilidad.documento_por_cobrar_aplicacion
            WHERE cobro_id = %s
            GROUP BY documento_por_cobrar_id
        """
    return current_cte


def _get_documento_cobrar_financial_map(db, documento_ids, current_cobro_id=None):
    documento_ids = [int(item) for item in documento_ids if item]
    if not documento_ids:
        return {}

    params = []
    current_cte = _documento_cobrar_disponible_sql(bool(current_cobro_id))
    if current_cobro_id:
        params.append(current_cobro_id)
    params.append(documento_ids)

    rows = db.execute_query(
        f"""
        WITH current_apps AS (
            {current_cte}
        )
        SELECT
            d.id,
            d.unidad_negocio_id,
            d.cliente_auxiliar_id,
            d.cliente_nombre,
            d.cliente_nit,
            d.numero_documento,
            d.tipo_documento,
            d.origen_documento,
            d.tratamiento_contable,
            d.gestion_origen,
            d.fecha_documento,
            d.moneda_codigo,
            d.estado,
            d.importe_total,
            d.importe_cobrado,
            d.saldo_pendiente,
            d.cuenta_cartera_codigo,
            COALESCE(cuenta.nombre, '') AS cuenta_cartera_nombre,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(current_apps.monto_actual, 0) AS monto_actual_cobro,
            (COALESCE(d.saldo_pendiente, 0) + COALESCE(current_apps.monto_actual, 0)) AS saldo_disponible
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = d.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cuenta ON cuenta.codigo = d.cuenta_cartera_codigo
        LEFT JOIN current_apps ON current_apps.documento_por_cobrar_id = d.id
        WHERE d.id = ANY(%s)
        """,
        tuple(params),
    )

    return {int(row['id']): row for row in rows}


def _search_documentos_cobrar_disponibles(db, current_cobro_id=None, texto=None, unidad_negocio_id=None, auxiliar_id=None, documento_id=None, limit=80):
    texto = _clean(texto)
    params = []
    current_cte = _documento_cobrar_disponible_sql(bool(current_cobro_id))
    if current_cobro_id:
        params.append(current_cobro_id)

    condiciones = [
        "d.activo = TRUE",
        "d.estado IN ('PENDIENTE', 'PARCIAL')",
        "(COALESCE(d.saldo_pendiente, 0) + COALESCE(current_apps.monto_actual, 0)) > 0"
    ]

    if unidad_negocio_id:
        condiciones.append('d.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    if auxiliar_id:
        condiciones.append('d.cliente_auxiliar_id = %s')
        params.append(auxiliar_id)

    if documento_id:
        condiciones.append('d.id = %s')
        params.append(int(documento_id))

    if texto:
        like = f'%{texto}%'
        condiciones.append(
            """
            (
                d.numero_documento ILIKE %s
                OR COALESCE(d.cliente_nombre, '') ILIKE %s
                OR COALESCE(d.cliente_nit, '') ILIKE %s
                OR COALESCE(d.referencia_externa, '') ILIKE %s
                OR COALESCE(d.descripcion, '') ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like])

    params.append(limit)
    rows = db.execute_query(
        f"""
        WITH current_apps AS (
            {current_cte}
        )
        SELECT
            d.id,
            d.unidad_negocio_id,
            d.cliente_auxiliar_id,
            d.cliente_nombre,
            d.cliente_nit,
            d.numero_documento,
            d.tipo_documento,
            d.origen_documento,
            d.tratamiento_contable,
            d.gestion_origen,
            d.fecha_documento,
            d.moneda_codigo,
            d.estado,
            d.importe_total,
            d.importe_cobrado,
            d.saldo_pendiente,
            d.cuenta_cartera_codigo,
            COALESCE(cuenta.nombre, '') AS cuenta_cartera_nombre,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(current_apps.monto_actual, 0) AS monto_actual_cobro,
            (COALESCE(d.saldo_pendiente, 0) + COALESCE(current_apps.monto_actual, 0)) AS saldo_disponible
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = d.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cuenta ON cuenta.codigo = d.cuenta_cartera_codigo
        LEFT JOIN current_apps ON current_apps.documento_por_cobrar_id = d.id
        WHERE {' AND '.join(condiciones)}
        ORDER BY d.fecha_documento DESC NULLS LAST, d.id DESC
        LIMIT %s
        """,
        tuple(params),
    )

    data = []
    for row in rows:
        data.append({
            'id': int(row['id']),
            'documento_id': int(row['id']),
            'unidad_negocio_id': row['unidad_negocio_id'],
            'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
            'cliente_nombre': row.get('cliente_nombre') or '',
            'cliente_nit': row.get('cliente_nit') or '',
            'numero_documento': row.get('numero_documento') or '',
            'tipo_documento': row.get('tipo_documento') or '',
            'origen_documento': row.get('origen_documento') or '',
            'tratamiento_contable': row.get('tratamiento_contable') or '',
            'gestion_origen': row.get('gestion_origen'),
            'fecha_documento': row['fecha_documento'].isoformat() if row.get('fecha_documento') else None,
            'moneda_codigo': row.get('moneda_codigo') or 'BOB',
            'estado': row.get('estado') or '',
            'unidad_negocio_codigo': row.get('unidad_negocio_codigo') or '',
            'unidad_negocio_nombre': row.get('unidad_negocio_nombre') or '',
            'cuenta_cartera_codigo': row.get('cuenta_cartera_codigo') or '',
            'cuenta_cartera_nombre': row.get('cuenta_cartera_nombre') or '',
            'importe_total': _to_float(row.get('importe_total')),
            'importe_cobrado': _to_float(row.get('importe_cobrado')),
            'saldo_pendiente': _to_float(row.get('saldo_pendiente')),
            'saldo_disponible': _to_float(row.get('saldo_disponible')),
            'monto_actual_cobro': _to_float(row.get('monto_actual_cobro')),
        })
    return data


def _get_cobro_documento_rows(db, cobro_id):
    rows = db.execute_query(
        """
        WITH apps AS (
            SELECT
                documento_por_cobrar_id,
                COALESCE(SUM(monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.documento_por_cobrar_aplicacion da
            LEFT JOIN contabilidad.cobro c ON c.id = da.cobro_id
            WHERE c.estado <> 'ANULADO'
            GROUP BY documento_por_cobrar_id
        )
        SELECT
            da.documento_por_cobrar_id AS documento_id,
            d.numero_documento,
            d.tipo_documento,
            d.origen_documento,
            d.tratamiento_contable,
            d.gestion_origen,
            d.fecha_documento,
            d.cliente_auxiliar_id,
            d.cliente_nombre,
            d.cliente_nit,
            d.moneda_codigo,
            d.estado,
            d.unidad_negocio_id,
            d.cuenta_cartera_codigo,
            COALESCE(cuenta.nombre, '') AS cuenta_cartera_nombre,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            d.importe_total,
            d.importe_cobrado,
            d.saldo_pendiente,
            COALESCE(da.monto_aplicado, 0) AS monto_aplicado,
            GREATEST(COALESCE(d.saldo_pendiente, 0) + COALESCE(da.monto_aplicado, 0), 0) AS saldo_disponible
        FROM contabilidad.documento_por_cobrar_aplicacion da
        INNER JOIN contabilidad.documento_por_cobrar d ON d.id = da.documento_por_cobrar_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = d.unidad_negocio_id
        LEFT JOIN contabilidad.cuenta cuenta ON cuenta.codigo = d.cuenta_cartera_codigo
        LEFT JOIN apps ON apps.documento_por_cobrar_id = d.id
        WHERE da.cobro_id = %s
        ORDER BY d.fecha_documento ASC, d.id ASC
        """,
        (cobro_id,),
    )

    data = []
    for row in rows:
        data.append({
            'documento_id': int(row['documento_id']),
            'numero_documento': row.get('numero_documento') or '',
            'tipo_documento': row.get('tipo_documento') or '',
            'origen_documento': row.get('origen_documento') or '',
            'tratamiento_contable': row.get('tratamiento_contable') or '',
            'gestion_origen': row.get('gestion_origen'),
            'fecha_documento': row['fecha_documento'].isoformat() if row.get('fecha_documento') else None,
            'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
            'cliente_nombre': row.get('cliente_nombre') or '',
            'cliente_nit': row.get('cliente_nit') or '',
            'moneda_codigo': row.get('moneda_codigo') or 'BOB',
            'estado': row.get('estado') or '',
            'unidad_negocio_id': row.get('unidad_negocio_id'),
            'unidad_negocio_codigo': row.get('unidad_negocio_codigo') or '',
            'unidad_negocio_nombre': row.get('unidad_negocio_nombre') or '',
            'cuenta_cartera_codigo': row.get('cuenta_cartera_codigo') or '',
            'cuenta_cartera_nombre': row.get('cuenta_cartera_nombre') or '',
            'importe_total': _to_float(row.get('importe_total')),
            'importe_cobrado': _to_float(row.get('importe_cobrado')),
            'saldo_pendiente': _to_float(row.get('saldo_pendiente')),
            'monto_aplicado': _to_float(row.get('monto_aplicado')),
            'saldo_disponible': _to_float(row.get('saldo_disponible')),
        })
    return data


def _validate_documento_cobrar_links(db, payload, monto_total, current_cobro_id=None):
    items = payload.get('documentos_aplicados') or []
    if items in (None, ''):
        items = []
    if not isinstance(items, list):
        raise ValueError('Los documentos aplicados no tienen un formato válido.')
    if not items:
        return {'documentos': [], 'monto_total': Decimal('0.00')}

    unidad_negocio_id = _parse_int(payload.get('unidad_negocio_id'), 'Unidad de negocio')
    cleaned = []
    seen = set()
    documento_ids = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError('Un documento aplicado no tiene un formato válido.')
        documento_id = _parse_int(item.get('documento_id'), f'Documento {idx}')
        if documento_id in seen:
            raise ValueError('No puedes repetir el mismo documento dentro del cobro.')
        monto_aplicado = _decimal(item.get('monto_aplicado'), f'Monto aplicado del documento {idx}')
        seen.add(documento_id)
        documento_ids.append(documento_id)
        cleaned.append({'documento_id': documento_id, 'monto_aplicado': monto_aplicado})

    financials = _get_documento_cobrar_financial_map(
        db,
        documento_ids,
        current_cobro_id=current_cobro_id,
    )

    total_aplicado = Decimal('0.00')
    rows = []
    clientes = set()
    for item in cleaned:
        row = financials.get(item['documento_id'])
        if not row:
            raise ValueError(f'El documento #{item["documento_id"]} ya no está disponible.')
        estado_documento = str(row.get('estado') or '').upper()
        monto_actual_cobro = Decimal(str(row.get('monto_actual_cobro') or 0)).quantize(CUANTIA)
        if estado_documento == 'ANULADO':
            raise ValueError(f'El documento {row["numero_documento"]} está anulado.')
        if estado_documento not in ('PENDIENTE', 'PARCIAL'):
            # Cuando se confirma un cobro en BORRADOR, el documento puede figurar como COBRADO
            # porque la aplicación del mismo borrador ya reservó el saldo. En ese caso sí debe
            # permitirse confirmar usando el monto reservado por el cobro actual.
            es_reserva_del_cobro_actual = bool(current_cobro_id and monto_actual_cobro > 0)
            if not es_reserva_del_cobro_actual:
                raise ValueError(f'El documento {row["numero_documento"]} no tiene saldo pendiente.')
        if int(row['unidad_negocio_id'] or 0) != int(unidad_negocio_id):
            raise ValueError(f'El documento {row["numero_documento"]} pertenece a otra unidad de negocio.')
        if not _clean(row.get('cuenta_cartera_codigo')):
            raise ValueError(f'El documento {row["numero_documento"]} no tiene cuenta de cartera configurada.')
        cliente_key = row.get('cliente_auxiliar_id') or f"NOMBRE:{row.get('cliente_nombre') or ''}"
        clientes.add(str(cliente_key))

        disponible = Decimal(str(row['saldo_disponible'] or 0)).quantize(CUANTIA)
        monto = item['monto_aplicado'].quantize(CUANTIA)
        if monto <= 0:
            raise ValueError(f'El documento {row["numero_documento"]} debe tener un monto aplicado mayor a cero.')
        if monto > disponible:
            raise ValueError(
                f'El documento {row["numero_documento"]} solo tiene {disponible} disponible para este cobro.'
            )

        total_aplicado += monto
        rows.append({
            'documento_id': int(row['id']),
            'numero_documento': row.get('numero_documento') or '',
            'tipo_documento': row.get('tipo_documento') or '',
            'origen_documento': row.get('origen_documento') or '',
            'tratamiento_contable': row.get('tratamiento_contable') or '',
            'gestion_origen': row.get('gestion_origen'),
            'fecha_documento': row['fecha_documento'].isoformat() if row.get('fecha_documento') else None,
            'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
            'cliente_nombre': row.get('cliente_nombre') or '',
            'cliente_nit': row.get('cliente_nit') or '',
            'moneda_codigo': row.get('moneda_codigo') or 'BOB',
            'unidad_negocio_id': row.get('unidad_negocio_id'),
            'unidad_negocio_codigo': row.get('unidad_negocio_codigo') or '',
            'unidad_negocio_nombre': row.get('unidad_negocio_nombre') or '',
            'cuenta_cartera_codigo': row.get('cuenta_cartera_codigo') or '',
            'cuenta_cartera_nombre': row.get('cuenta_cartera_nombre') or '',
            'monto_aplicado': monto,
            'saldo_disponible': disponible,
        })

    if len(clientes) > 1:
        raise ValueError('No puedes mezclar documentos de distintos clientes en el mismo cobro.')

    if total_aplicado > monto_total:
        raise ValueError('El total aplicado a documentos no puede exceder el total del cobro.')

    return {'documentos': rows, 'monto_total': total_aplicado.quantize(CUANTIA)}


def _sync_documento_cobrar_aplicacion(db, cobro_id, documentos, fecha_aplicacion):
    db.execute_delete(
        'DELETE FROM contabilidad.documento_por_cobrar_aplicacion WHERE cobro_id = %s',
        (cobro_id,),
    )
    for item in documentos:
        db.execute_insert(
            """
            INSERT INTO contabilidad.documento_por_cobrar_aplicacion (
                documento_por_cobrar_id,
                cobro_id,
                fecha_aplicacion,
                monto_aplicado,
                observacion
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                item['documento_id'],
                cobro_id,
                fecha_aplicacion,
                item['monto_aplicado'],
                None,
            ),
            return_id=False,
        )


def _recalculate_documento_cobrar(db, documento_id):
    rows = db.execute_query(
        """
        WITH apps AS (
            SELECT COALESCE(SUM(da.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.documento_por_cobrar_aplicacion da
            LEFT JOIN contabilidad.cobro c ON c.id = da.cobro_id
            WHERE da.documento_por_cobrar_id = %s
              AND c.estado <> 'ANULADO'
        )
        SELECT
            d.id,
            d.estado,
            COALESCE(d.importe_total, 0) AS importe_total,
            COALESCE(apps.total_aplicado, 0) AS total_aplicado
        FROM contabilidad.documento_por_cobrar d
        CROSS JOIN apps
        WHERE d.id = %s
        LIMIT 1
        """,
        (documento_id, documento_id),
    )
    if not rows:
        return
    row = rows[0]
    if row['estado'] == 'ANULADO':
        return
    importe_total = Decimal(str(row['importe_total'] or 0)).quantize(CUANTIA)
    total_aplicado = Decimal(str(row['total_aplicado'] or 0)).quantize(CUANTIA)
    saldo = max(importe_total - total_aplicado, Decimal('0.00')).quantize(CUANTIA)
    if saldo <= 0:
        estado = 'COBRADO'
    elif total_aplicado > 0:
        estado = 'PARCIAL'
    else:
        estado = 'PENDIENTE'
    db.execute_update(
        """
        UPDATE contabilidad.documento_por_cobrar
        SET importe_cobrado = %s,
            saldo_pendiente = %s,
            estado = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (total_aplicado, saldo, estado, documento_id),
    )


def _recalculate_documentos_cobrar(db, documento_ids):
    for documento_id in sorted({int(item) for item in documento_ids if item}):
        _recalculate_documento_cobrar(db, documento_id)

def _get_pending_commitments(db, current_cobro_id=None, filtros=None):
    filtros = filtros or {}
    params = [current_cobro_id, current_cobro_id, current_cobro_id, current_cobro_id]
    condiciones = [
        "c.tipo = 'COBRAR'",
        "c.activo = TRUE",
    ]

    texto = _clean(filtros.get('q'))
    if texto:
        like = f'%{texto}%'
        condiciones.append(
            """
            (
                c.codigo ILIKE %s
                OR c.nombre ILIKE %s
                OR COALESCE(aux.nombre, '') ILIKE %s
                OR COALESCE(c.cuenta_contable, '') ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like])

    auxiliar_id = filtros.get('auxiliar_id')
    if auxiliar_id:
        condiciones.append('c.auxiliar_id = %s')
        params.append(int(auxiliar_id))

    unidad_negocio_id = filtros.get('unidad_negocio_id')
    if unidad_negocio_id:
        condiciones.append('c.unidad_negocio_id = %s')
        params.append(int(unidad_negocio_id))

    cuenta_codigo = _clean(filtros.get('cuenta_codigo'))
    if cuenta_codigo:
        condiciones.append('c.cuenta_contable = %s')
        params.append(cuenta_codigo)

    compromiso_detalle_id = filtros.get('compromiso_detalle_id')
    if compromiso_detalle_id:
        condiciones.append('d.id = %s')
        params.append(int(compromiso_detalle_id))

    rows = db.execute_query(
        f"""
        SELECT
            d.id,
            d.compromiso_id,
            d.fecha_vencimiento,
            d.monto_programado,
            d.monto_registrado,
            d.estado,
            d.observacion,
            c.codigo AS compromiso_codigo,
            c.nombre AS compromiso_nombre,
            c.cuenta_contable,
            c.auxiliar_id,
            c.unidad_negocio_id,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM contabilidad.cobro_detalle pdx
                    INNER JOIN contabilidad.cobro px ON px.id = pdx.cobro_id
                    WHERE pdx.compromiso_detalle_id = d.id
                      AND pdx.tipo_linea = 'COMPROMISO'
                      AND px.estado = 'BORRADOR'
                      AND (%s IS NULL OR pdx.cobro_id <> %s)
                ) THEN TRUE ELSE FALSE
            END AS reservado_en_otro_borrador,
            CASE
                WHEN %s IS NOT NULL AND EXISTS (
                    SELECT 1
                    FROM contabilidad.cobro_detalle pdy
                    WHERE pdy.cobro_id = %s
                      AND pdy.tipo_linea = 'COMPROMISO'
                      AND pdy.compromiso_detalle_id = d.id
                ) THEN TRUE ELSE FALSE
            END AS seleccionado_actual,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM contabilidad.cobro_detalle pdc
                    INNER JOIN contabilidad.cobro pc ON pc.id = pdc.cobro_id
                    WHERE pdc.compromiso_detalle_id = d.id
                      AND pdc.tipo_linea = 'COMPROMISO'
                      AND pc.estado = 'CONFIRMADO'
                ) THEN TRUE ELSE FALSE
            END AS ya_confirmado
        FROM contabilidad.compromiso_detalle d
        INNER JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = c.unidad_negocio_id
        WHERE {' AND '.join(condiciones)}
        ORDER BY d.fecha_vencimiento ASC, c.codigo ASC, d.id ASC
        """,
        tuple(params),
    )

    visibles = []
    for row in rows:
        if row['ya_confirmado']:
            continue
        if row['reservado_en_otro_borrador'] and not row['seleccionado_actual']:
            continue
        if row['estado'] not in ('PENDIENTE', 'COBRADO') and not row['seleccionado_actual']:
            continue
        visibles.append({
            'id': row['id'],
            'compromiso_id': row['compromiso_id'],
            'fecha_vencimiento': row['fecha_vencimiento'].isoformat() if row['fecha_vencimiento'] else None,
            'monto_programado': _to_float(row['monto_programado']),
            'monto_registrado': _to_float(row['monto_registrado']),
            'estado': row['estado'],
            'observacion': row['observacion'] or '',
            'compromiso_codigo': row['compromiso_codigo'],
            'compromiso_nombre': row['compromiso_nombre'],
            'cuenta_contable': row['cuenta_contable'],
            'auxiliar_id': row['auxiliar_id'],
            'auxiliar_nombre': row['auxiliar_nombre'],
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
            'reservado_en_otro_borrador': bool(row['reservado_en_otro_borrador']),
            'seleccionado_actual': bool(row['seleccionado_actual']),
        })
    return visibles



def _build_index_rows(db):
    rows = db.execute_query(
        """
        SELECT
            p.id,
            p.fecha,
            p.unidad_negocio_id,
            p.medio_pago,
            p.moneda_codigo,
            p.tipo_cambio,
            p.monto_total,
            p.referencia,
            p.glosa,
            p.estado,
            p.origen_operacion,
            p.rubro_id,
            p.publicidad_elemento_codigo_ref,
            p.vigencia_desde,
            p.vigencia_hasta,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(rub.codigo, '') AS rubro_codigo,
            COALESCE(rub.nombre, '') AS rubro_nombre,
            COALESCE(aux.nombre, 'Sin cliente') AS cliente_nombre,
            CASE
                WHEN p.caja_id IS NOT NULL THEN caja.nombre
                WHEN p.cuenta_bancaria_id IS NOT NULL THEN banco.nombre_banco || ' · ' || banco.numero_cuenta
                ELSE 'No definido'
            END AS ingreso_nombre,
            COALESCE(tot.cantidad_lineas, 0) AS cantidad_lineas,
            COALESCE(tot.cantidad_compromisos, 0) AS cantidad_compromisos,
            COALESCE(tot.cantidad_directas, 0) AS cantidad_directas,
            COALESCE(doc.cantidad_documentos, 0) AS cantidad_documentos
        FROM contabilidad.cobro p
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = p.unidad_negocio_id
        LEFT JOIN contabilidad.rubro_operacion rub ON rub.id = p.rubro_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = p.cliente_auxiliar_id
        LEFT JOIN contabilidad.caja caja ON caja.id = p.caja_id
        LEFT JOIN contabilidad.cuenta_bancaria banco ON banco.id = p.cuenta_bancaria_id
        LEFT JOIN (
            SELECT
                cobro_id,
                COUNT(*) AS cantidad_lineas,
                SUM(CASE WHEN tipo_linea = 'COMPROMISO' THEN 1 ELSE 0 END) AS cantidad_compromisos,
                SUM(CASE WHEN tipo_linea = 'DIRECTO' THEN 1 ELSE 0 END) AS cantidad_directas
            FROM contabilidad.cobro_detalle
            GROUP BY cobro_id
        ) tot ON tot.cobro_id = p.id
        LEFT JOIN (
            SELECT
                cobro_id,
                COUNT(*) AS cantidad_documentos
            FROM contabilidad.documento_por_cobrar_aplicacion
            GROUP BY cobro_id
        ) doc ON doc.cobro_id = p.id
        ORDER BY p.fecha DESC, p.id DESC
        """
    )

    data = []
    for row in rows:
        data.append({
            'id': row['id'],
            'fecha': row['fecha'].isoformat() if row['fecha'] else None,
            'medio_pago': row['medio_pago'],
            'moneda_codigo': row['moneda_codigo'],
            'tipo_cambio': _to_float(row['tipo_cambio']),
            'monto_total': _to_float(row['monto_total']),
            'referencia': row['referencia'] or '',
            'glosa': row['glosa'] or '',
            'estado': row['estado'],
            'origen_operacion': row['origen_operacion'],
            'rubro_id': row['rubro_id'],
            'rubro_codigo': row['rubro_codigo'],
            'rubro_nombre': row['rubro_nombre'],
            'publicidad_elemento_codigo_ref': row['publicidad_elemento_codigo_ref'] or '',
            'vigencia_desde': row['vigencia_desde'].isoformat() if row.get('vigencia_desde') else None,
            'vigencia_hasta': row['vigencia_hasta'].isoformat() if row.get('vigencia_hasta') else None,
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
            'cliente_nombre': row['cliente_nombre'],
            'ingreso_nombre': row['ingreso_nombre'],
            'cantidad_lineas': int(row['cantidad_lineas'] or 0),
            'cantidad_compromisos': int(row['cantidad_compromisos'] or 0),
            'cantidad_directas': int(row['cantidad_directas'] or 0),
            'cantidad_documentos': int(row.get('cantidad_documentos') or 0),
        })
    return data


# ============================================================
# Validaciones y composición de payload
# ============================================================

def _validate_header(db, payload):
    fecha = _parse_date(payload.get('fecha'), 'Fecha')
    unidad_negocio_id = _parse_int(payload.get('unidad_negocio_id'), 'Unidad de negocio')
    medio_pago = _clean(payload.get('medio_pago')).upper()
    moneda_codigo = _clean(payload.get('moneda_codigo')).upper()
    caja_id = _parse_int(payload.get('caja_id'), 'Caja', required=False)
    cuenta_bancaria_id = _parse_int(payload.get('cuenta_bancaria_id'), 'Cuenta bancaria', required=False)
    cliente_auxiliar_id = _parse_int(payload.get('cliente_auxiliar_id'), 'Cliente', required=False)
    contra_cuenta_codigo = _normalize_text(payload.get('contra_cuenta_codigo'), 'Contra cuenta', 30, required=False)
    referencia = _normalize_text(payload.get('referencia'), 'Referencia', 150, required=False)
    glosa = _normalize_text(payload.get('glosa'), 'Glosa', 500, required=False)
    tipo_cambio = _decimal(payload.get('tipo_cambio'), 'Tipo de cambio', allow_zero=False, quant=CUANTIA_TC)
    rubro_id = _parse_int(payload.get('rubro_id'), 'Rubro', required=False)
    publicidad_referencia_raw = _clean(payload.get('publicidad_elemento_id_ref'))
    publicidad_elemento_id_ref = None
    publicidad_elemento_codigo_ref = _normalize_text(payload.get('publicidad_elemento_codigo_ref'), 'Código de elemento publicitario', 30, required=False)
    vigencia_desde = _parse_date(payload.get('vigencia_desde'), 'Vigencia desde', required=False)
    vigencia_hasta = _parse_date(payload.get('vigencia_hasta'), 'Vigencia hasta', required=False)
    cliente_nit_ci_ref = _normalize_text(payload.get('cliente_nit_ci_ref'), 'NIT/CI cliente', 50, required=False)
    cliente_nombre_ref = _normalize_text(payload.get('cliente_nombre_ref'), 'Cliente referencia', 200, required=False)

    if medio_pago not in MEDIOS_OPERABLES:
        raise ValueError('El medio de ingreso seleccionado no es válido.')
    if not moneda_codigo:
        raise ValueError('Debe seleccionar la moneda del cobro.')

    unidad = _get_unidad_row(db, unidad_negocio_id)
    if not unidad:
        raise ValueError('La unidad de negocio seleccionada no existe o está inactiva.')

    if medio_pago == 'CAJA':
        if not caja_id:
            raise ValueError('Debe seleccionar la caja de ingreso.')
        cuenta_bancaria_id = None
    elif medio_pago == 'BANCO':
        if not cuenta_bancaria_id:
            raise ValueError('Debe seleccionar la cuenta bancaria de ingreso.')
        caja_id = None

    moneda_rows = db.execute_query(
        """
        SELECT codigo
        FROM contabilidad.moneda
        WHERE activo = TRUE AND codigo = %s
        LIMIT 1
        """,
        (moneda_codigo,),
    )
    if not moneda_rows:
        raise ValueError('La moneda seleccionada no existe o está inactiva.')

    if caja_id:
        caja = db.execute_query(
            """
            SELECT id, cuenta_contable_codigo
            FROM contabilidad.caja
            WHERE id = %s AND activo = TRUE
            LIMIT 1
            """,
            (caja_id,),
        )
        if not caja:
            raise ValueError('La caja seleccionada no existe o está inactiva.')

    if cuenta_bancaria_id:
        banco = db.execute_query(
            """
            SELECT id, cuenta_contable_codigo, moneda_codigo
            FROM contabilidad.cuenta_bancaria
            WHERE id = %s AND activo = TRUE
            LIMIT 1
            """,
            (cuenta_bancaria_id,),
        )
        if not banco:
            raise ValueError('La cuenta bancaria seleccionada no existe o está inactiva.')

    if cliente_auxiliar_id:
        auxiliar = _get_auxiliar_row(db, cliente_auxiliar_id)
        if not auxiliar or not auxiliar.get('activo'):
            raise ValueError('El cliente seleccionado no existe o está inactivo.')

    rubro = _get_rubro_row(db, rubro_id) if rubro_id else None
    if rubro_id and not rubro:
        raise ValueError('El rubro seleccionado no existe o está inactivo.')

    if rubro_id:
        if not publicidad_referencia_raw:
            raise ValueError('Debes seleccionar una referencia publicitaria cuando elijas un rubro.')

        publicidad_referencia = _get_publicidad_reference_row(
            db,
            publicidad_referencia_raw,
            unidad_negocio_id=unidad_negocio_id,
        )
        if not publicidad_referencia:
            raise ValueError('La referencia publicitaria seleccionada no existe, está inactiva, no tiene código GAMLP o no pertenece a la unidad de negocio elegida.')

        if publicidad_referencia.get('ref_tipo') == 'ESTRUCTURA':
            publicidad_elemento_id_ref = None
            publicidad_elemento_codigo_ref = publicidad_referencia['codigo_gamlp']
        else:
            publicidad_elemento_id_ref = publicidad_referencia['id']
            publicidad_elemento_codigo_ref = publicidad_referencia['codigo_gamlp']

        if not vigencia_desde or not vigencia_hasta:
            raise ValueError('Debes indicar la vigencia desde y hasta cuando selecciones un rubro.')
        if vigencia_hasta < vigencia_desde:
            raise ValueError('La vigencia final no puede ser menor a la vigencia inicial.')
    else:
        publicidad_elemento_id_ref = None
        publicidad_elemento_codigo_ref = None
        vigencia_desde = None
        vigencia_hasta = None
        cliente_nit_ci_ref = None
        cliente_nombre_ref = None

    cuenta_row = None
    if contra_cuenta_codigo:
        cuenta_row = _get_account_row(db, contra_cuenta_codigo)
        if not cuenta_row:
            raise ValueError('La contra cuenta seleccionada no existe o no es postable.')
        if cuenta_row['requiere_auxiliar'] and not cliente_auxiliar_id:
            raise ValueError('La contra cuenta seleccionada requiere cliente/auxiliar.')

    return {
        'fecha': fecha,
        'unidad_negocio_id': unidad_negocio_id,
        'unidad_negocio_codigo': unidad['codigo'],
        'unidad_negocio_nombre': unidad['nombre'],
        'medio_pago': medio_pago,
        'caja_id': caja_id,
        'cuenta_bancaria_id': cuenta_bancaria_id,
        'moneda_codigo': moneda_codigo,
        'tipo_cambio': tipo_cambio,
        'cliente_auxiliar_id': cliente_auxiliar_id,
        'contra_cuenta_codigo': contra_cuenta_codigo,
        'contra_cuenta': cuenta_row,
        'cuenta_row': cuenta_row,
        'referencia': referencia,
        'glosa': glosa,
        'rubro_id': rubro_id,
        'rubro_codigo': rubro['codigo'] if rubro else None,
        'rubro_nombre': rubro['nombre'] if rubro else None,
        'publicidad_elemento_id_ref': publicidad_elemento_id_ref,
        'publicidad_elemento_codigo_ref': publicidad_elemento_codigo_ref,
        'vigencia_desde': vigencia_desde,
        'vigencia_hasta': vigencia_hasta,
        'cliente_nit_ci_ref': cliente_nit_ci_ref,
        'cliente_nombre_ref': cliente_nombre_ref,
    }


def _validate_commitment_lines(db, payload, current_cobro_id=None):
    compromiso_ids = payload.get('compromiso_detalle_ids') or []
    if not isinstance(compromiso_ids, list) or not compromiso_ids:
        raise ValueError('Debe seleccionar al menos una cuota de compromiso.')

    try:
        detalle_ids = [int(item) for item in compromiso_ids]
    except (TypeError, ValueError):
        raise ValueError('El listado de compromisos enviados no es válido.')

    rows = db.execute_query(
        """
        SELECT
            d.id,
            d.compromiso_id,
            d.fecha_vencimiento,
            d.monto_programado,
            d.monto_registrado,
            d.estado,
            d.observacion,
            c.codigo AS compromiso_codigo,
            c.nombre AS compromiso_nombre,
            c.cuenta_contable,
            c.auxiliar_id,
            c.unidad_negocio_id,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre
        FROM contabilidad.compromiso_detalle d
        INNER JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = c.unidad_negocio_id
        WHERE d.id = ANY(%s)
          AND c.tipo = 'COBRAR'
          AND c.activo = TRUE
        """,
        (detalle_ids,),
    )
    if len(rows) != len(set(detalle_ids)):
        raise ValueError('Alguna cuota seleccionada ya no existe o no corresponde a compromisos por cobrar.')

    reserved_rows = db.execute_query(
        """
        SELECT DISTINCT pd.compromiso_detalle_id
        FROM contabilidad.cobro_detalle pd
        INNER JOIN contabilidad.cobro p ON p.id = pd.cobro_id
        WHERE pd.compromiso_detalle_id = ANY(%s)
          AND pd.tipo_linea = 'COMPROMISO'
          AND p.estado = 'BORRADOR'
          AND (%s IS NULL OR pd.cobro_id <> %s)
        """,
        (detalle_ids, current_cobro_id, current_cobro_id),
    )
    reserved_ids = {int(row['compromiso_detalle_id']) for row in reserved_rows}

    current_rows = db.execute_query(
        """
        SELECT DISTINCT pd.compromiso_detalle_id
        FROM contabilidad.cobro_detalle pd
        WHERE pd.cobro_id = %s
          AND pd.tipo_linea = 'COMPROMISO'
        """,
        (current_cobro_id,),
    ) if current_cobro_id else []
    current_ids = {int(row['compromiso_detalle_id']) for row in current_rows}

    lineas = []
    total = Decimal('0.00')
    cliente_ids = set()
    cuenta_ids = set()
    unidades = set()

    for idx, row in enumerate(rows, start=1):
        if row['id'] in reserved_ids and row['id'] not in current_ids:
            raise ValueError('Una de las cuotas seleccionadas está siendo utilizada en otro cobro en borrador.')
        if row['estado'] not in ('PENDIENTE', 'COBRADO') and row['id'] not in current_ids:
            raise ValueError('Solo se pueden seleccionar cuotas vigentes del compromiso.')
        if not row['auxiliar_id']:
            raise ValueError(f'El compromiso {row["compromiso_codigo"]} no tiene cliente asociado.')
        if not row['cuenta_contable']:
            raise ValueError(f'El compromiso {row["compromiso_codigo"]} no tiene cuenta contable configurada.')
        if not row['unidad_negocio_id']:
            raise ValueError(f'El compromiso {row["compromiso_codigo"]} no tiene unidad de negocio configurada.')

        cliente_ids.add(row['auxiliar_id'])
        cuenta_ids.add(row['cuenta_contable'])
        unidades.add(row['unidad_negocio_id'])

        subtotal = Decimal(str(row['monto_programado'] or 0)).quantize(CUANTIA)
        lineas.append({
            'secuencia': idx,
            'tipo_linea': 'COMPROMISO',
            'compromiso_detalle_id': row['id'],
            'descripcion': (
                f"Compromiso {row['compromiso_codigo']} - {row['compromiso_nombre']} - {row['fecha_vencimiento'].strftime('%d/%m/%Y')}"
                if row['fecha_vencimiento'] else f"Compromiso {row['compromiso_codigo']}"
            ),
            'cantidad': Decimal('1.0000'),
            'precio_unitario': subtotal,
            'subtotal': subtotal,
            'observacion': _truncate(row['observacion'] or '', 300) if row['observacion'] else None,
            'auxiliar_id': row['auxiliar_id'],
            'auxiliar_nombre': row['auxiliar_nombre'],
            'compromiso_codigo': row['compromiso_codigo'],
            'compromiso_nombre': row['compromiso_nombre'],
            'fecha_vencimiento': row['fecha_vencimiento'].isoformat() if row['fecha_vencimiento'] else None,
            'cuenta_contable': row['cuenta_contable'],
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
        })
        total += subtotal

    if len(cliente_ids) > 1:
        raise ValueError('No puedes mezclar compromisos de distintos clientes en el mismo cobro.')
    if len(cuenta_ids) > 1:
        raise ValueError('No puedes mezclar compromisos con distinta cuenta contable en el mismo cobro.')
    if len(unidades) > 1:
        raise ValueError('No puedes mezclar compromisos de distintas unidades de negocio en el mismo cobro.')

    return {
        'origen_operacion': 'COMPROMISO',
        'lineas': lineas,
        'monto_total': total.quantize(CUANTIA),
        'cliente_auxiliar_id': lineas[0]['auxiliar_id'],
        'contra_cuenta_codigo': lineas[0]['cuenta_contable'],
        'unidad_negocio_id': lineas[0]['unidad_negocio_id'],
        'descripcion_resumen': f"Cobro de {len(lineas)} cuota(s) de compromiso",
    }


def _validate_direct_lines(db, payload, header):
    use_detail = bool(payload.get('usar_detalle_directo'))
    items = payload.get('direct_items') or []
    if not isinstance(items, list):
        raise ValueError('El detalle directo enviado no tiene un formato válido.')

    if not header['contra_cuenta_codigo']:
        raise ValueError('Debe seleccionar la contra cuenta del cobro.')

    cuenta = header['cuenta_row'] or _get_account_row(db, header['contra_cuenta_codigo'])
    if not cuenta:
        raise ValueError('La contra cuenta seleccionada no existe.')

    cliente_auxiliar_id = header['cliente_auxiliar_id']
    if cuenta['requiere_auxiliar'] and not cliente_auxiliar_id:
        raise ValueError('La cuenta seleccionada requiere cliente/auxiliar.')

    total = Decimal('0.00')
    lineas = []

    if use_detail:
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError('Una línea del detalle no tiene un formato válido.')

            descripcion = _normalize_text(item.get('descripcion'), f'Descripción de la fila {idx}', 300, required=True)
            observacion = _normalize_text(item.get('observacion'), f'Observación de la fila {idx}', 300, required=False)
            cantidad = _decimal(item.get('cantidad'), f'Cantidad de la fila {idx}', allow_zero=False, quant=Decimal('0.0001'))
            precio_unitario = _decimal(item.get('precio_unitario'), f'Precio unitario de la fila {idx}', allow_zero=True, quant=CUANTIA)
            subtotal = (cantidad * precio_unitario).quantize(CUANTIA, rounding=ROUND_HALF_UP)
            if subtotal <= 0:
                raise ValueError(f'La fila {idx} debe tener un subtotal mayor a cero.')

            total += subtotal
            lineas.append({
                'secuencia': idx,
                'tipo_linea': 'DIRECTO',
                'compromiso_detalle_id': None,
                'descripcion': descripcion,
                'cantidad': cantidad,
                'precio_unitario': precio_unitario,
                'subtotal': subtotal,
                'observacion': observacion,
            })

        descripcion_resumen = f"Cobro directo con {len(lineas)} ítem(s)"
    else:
        total_manual = _decimal(
            payload.get('monto_total_manual'),
            'Total del cobro',
            allow_zero=True,
            quant=CUANTIA,
            required=False,
        )
        total = total_manual or Decimal('0.00')
        descripcion_resumen = 'Cobro directo simple'

    return {
        'origen_operacion': 'DIRECTO',
        'lineas': lineas,
        'monto_total': total.quantize(CUANTIA),
        'cliente_auxiliar_id': cliente_auxiliar_id,
        'contra_cuenta_codigo': header['contra_cuenta_codigo'],
        'descripcion_resumen': descripcion_resumen,
        'usa_detalle_directo': use_detail,
    }



def _compose_save_payload(db, payload, current_cobro_id=None):
    header = _validate_header(db, payload)
    origen = _clean(payload.get('origen_operacion')).upper()
    if origen not in ORIGENES_OPERACION:
        raise ValueError('Debe seleccionar el origen del cobro.')

    documentos = {'documentos': [], 'monto_total': Decimal('0.00')}

    if origen == 'COMPROMISO':
        detalle = _validate_commitment_lines(db, payload, current_cobro_id=current_cobro_id)
        header['cliente_auxiliar_id'] = detalle['cliente_auxiliar_id']
        header['contra_cuenta_codigo'] = detalle['contra_cuenta_codigo']
        if int(header['unidad_negocio_id']) != int(detalle['unidad_negocio_id']):
            raise ValueError('La unidad de negocio del cobro no coincide con la de las cuotas seleccionadas.')
        if not header['glosa']:
            header['glosa'] = _truncate(detalle['descripcion_resumen'], 500)
    elif origen == 'DOCUMENTO_COBRAR':
        monto_documentos_base = _decimal(
            payload.get('monto_total_manual'),
            'Total del cobro',
            allow_zero=True,
            quant=CUANTIA,
            required=False,
        ) or Decimal('0.00')
        documentos = _validate_documento_cobrar_links(
            db,
            payload,
            monto_documentos_base,
            current_cobro_id=current_cobro_id,
        )
        facturas = _validate_factura_links(
            db,
            payload,
            monto_documentos_base,
            current_cobro_id=current_cobro_id,
        )
        if not documentos['documentos'] and not facturas['facturas']:
            raise ValueError('Debe seleccionar al menos un documento o factura por cobrar.')
        first = (documentos['documentos'] or facturas['facturas'])[0]
        header['cliente_auxiliar_id'] = first.get('cliente_auxiliar_id') or header['cliente_auxiliar_id']
        header['contra_cuenta_codigo'] = first.get('cuenta_cartera_codigo') or first.get('cuenta_cobrar_codigo')
        total_documentos_cobro = (documentos['monto_total'] + facturas['monto_total']).quantize(CUANTIA)
        cantidad_documentos = len(documentos['documentos']) + len(facturas['facturas'])
        detalle = {
            'origen_operacion': 'DOCUMENTO_COBRAR',
            'lineas': [],
            'monto_total': total_documentos_cobro,
            'descripcion_resumen': f"Cobro de {cantidad_documentos} documento(s) por cobrar",
            'usa_detalle_directo': False,
        }
        if not header['glosa']:
            header['glosa'] = _truncate(detalle['descripcion_resumen'], 500)
    else:
        detalle = _validate_direct_lines(db, payload, header)
        if not header['glosa']:
            header['glosa'] = _truncate(detalle['descripcion_resumen'], 500)

    if not header['glosa']:
        raise ValueError('La glosa es obligatoria.')

    if origen != 'DOCUMENTO_COBRAR':
        facturas = _validate_factura_links(
            db,
            payload,
            detalle['monto_total'],
            current_cobro_id=current_cobro_id,
        )

    total_aplicado = (facturas['monto_total'] + documentos['monto_total']).quantize(CUANTIA)
    if total_aplicado > detalle['monto_total']:
        raise ValueError('El total aplicado a documentos y facturas no puede exceder el total del cobro.')

    return {
        'header': header,
        'origen_operacion': detalle['origen_operacion'],
        'lineas': detalle['lineas'],
        'monto_total': detalle['monto_total'],
        'usa_detalle_directo': detalle.get('usa_detalle_directo', False),
        'facturas_aplicadas': facturas['facturas'],
        'monto_facturas_aplicadas': facturas['monto_total'],
        'documentos_aplicados': documentos['documentos'],
        'monto_documentos_aplicados': documentos['monto_total'],
    }


# ============================================================
# Persistencia
# ============================================================

def _insert_cobro(db, header, origen_operacion, monto_total):
    return db.execute_insert(
        """
        INSERT INTO contabilidad.cobro (
            fecha,
            unidad_negocio_id,
            cliente_auxiliar_id,
            medio_pago,
            contra_cuenta_codigo,
            caja_id,
            cuenta_bancaria_id,
            moneda_codigo,
            tipo_cambio,
            monto_total,
            referencia,
            glosa,
            estado,
            origen_operacion,
            rubro_id,
            publicidad_elemento_id_ref,
            publicidad_elemento_codigo_ref,
            vigencia_desde,
            vigencia_hasta,
            cliente_nit_ci_ref,
            cliente_nombre_ref,
            actualizado_en
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            'BORRADOR',
            %s, %s, %s, %s, %s, %s, %s, %s,
            CURRENT_TIMESTAMP
        )
        """,
        (
            header['fecha'],
            header['unidad_negocio_id'],
            header['cliente_auxiliar_id'],
            header['medio_pago'],
            header['contra_cuenta_codigo'],
            header['caja_id'],
            header['cuenta_bancaria_id'],
            header['moneda_codigo'],
            header['tipo_cambio'],
            monto_total,
            header['referencia'],
            header['glosa'],
            origen_operacion,
            header['rubro_id'],
            header['publicidad_elemento_id_ref'],
            header['publicidad_elemento_codigo_ref'],
            header['vigencia_desde'],
            header['vigencia_hasta'],
            header['cliente_nit_ci_ref'],
            header['cliente_nombre_ref'],
        ),
    )


def _update_cobro(db, cobro_id, header, origen_operacion, monto_total):
    updated = db.execute_update(
        """
        UPDATE contabilidad.cobro
        SET
            fecha = %s,
            unidad_negocio_id = %s,
            cliente_auxiliar_id = %s,
            medio_pago = %s,
            contra_cuenta_codigo = %s,
            caja_id = %s,
            cuenta_bancaria_id = %s,
            moneda_codigo = %s,
            tipo_cambio = %s,
            monto_total = %s,
            referencia = %s,
            glosa = %s,
            origen_operacion = %s,
            rubro_id = %s,
            publicidad_elemento_id_ref = %s,
            publicidad_elemento_codigo_ref = %s,
            vigencia_desde = %s,
            vigencia_hasta = %s,
            cliente_nit_ci_ref = %s,
            cliente_nombre_ref = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
          AND estado = 'BORRADOR'
        """,
        (
            header['fecha'],
            header['unidad_negocio_id'],
            header['cliente_auxiliar_id'],
            header['medio_pago'],
            header['contra_cuenta_codigo'],
            header['caja_id'],
            header['cuenta_bancaria_id'],
            header['moneda_codigo'],
            header['tipo_cambio'],
            monto_total,
            header['referencia'],
            header['glosa'],
            origen_operacion,
            header['rubro_id'],
            header['publicidad_elemento_id_ref'],
            header['publicidad_elemento_codigo_ref'],
            header['vigencia_desde'],
            header['vigencia_hasta'],
            header['cliente_nit_ci_ref'],
            header['cliente_nombre_ref'],
            cobro_id,
        ),
    )
    if not updated:
        raise ValueError('Solo se pueden editar cobros en borrador.')


def _sync_cobro_detalle(db, cobro_id, lineas):
    db.execute_delete('DELETE FROM contabilidad.cobro_detalle WHERE cobro_id = %s', (cobro_id,))
    for linea in lineas:
        db.execute_insert(
            """
            INSERT INTO contabilidad.cobro_detalle (
                cobro_id,
                secuencia,
                tipo_linea,
                compromiso_detalle_id,
                descripcion,
                cantidad,
                precio_unitario,
                subtotal,
                observacion,
                actualizado_en
            ) VALUES (%s, %s, %s::contabilidad.tipo_linea_tesoreria_enum, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (
                cobro_id,
                linea['secuencia'],
                linea['tipo_linea'],
                linea['compromiso_detalle_id'],
                linea['descripcion'],
                linea['cantidad'],
                linea['precio_unitario'],
                linea['subtotal'],
                linea['observacion'],
            ),
            return_id=False,
        )



def _get_cuenta_ingreso(db, cobro):
    if cobro['medio_pago'] == 'CAJA':
        rows = db.execute_query(
            """
            SELECT nombre, cuenta_contable_codigo
            FROM contabilidad.caja
            WHERE id = %s
            LIMIT 1
            """,
            (cobro['caja_id'],),
        )
    else:
        rows = db.execute_query(
            """
            SELECT nombre_banco || ' · ' || numero_cuenta AS nombre, cuenta_contable_codigo
            FROM contabilidad.cuenta_bancaria
            WHERE id = %s
            LIMIT 1
            """,
            (cobro['cuenta_bancaria_id'],),
        )
    if not rows:
        raise ValueError('No se pudo obtener la cuenta de ingreso del cobro.')
    return rows[0]



def _create_asiento_cobro(db, cobro, lineas, facturas=None, documentos=None):
    facturas = facturas or []
    documentos = documentos or []
    ingreso = _get_cuenta_ingreso(db, cobro)
    total = Decimal(str(cobro['monto_total'])).quantize(CUANTIA)
    if total <= 0:
        raise ValueError('El cobro no tiene un total válido para contabilizar.')

    total_facturas = sum(
        (Decimal(str(item.get('monto_aplicado') or 0)).quantize(CUANTIA) for item in facturas),
        Decimal('0.00'),
    ).quantize(CUANTIA)
    total_documentos = sum(
        (Decimal(str(item.get('monto_aplicado') or 0)).quantize(CUANTIA) for item in documentos),
        Decimal('0.00'),
    ).quantize(CUANTIA)
    if total_facturas > total:
        raise ValueError('El total aplicado a facturas excede el total del cobro.')
    if (total_facturas + total_documentos) > total:
        raise ValueError('El total aplicado a documentos y facturas excede el total del cobro.')

    asiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha,
            unidad_negocio_id,
            moneda_codigo,
            tipo_cambio,
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado,
            rubro_id,
            publicidad_elemento_id_ref,
            publicidad_elemento_codigo_ref,
            vigencia_desde,
            vigencia_hasta,
            cliente_nit_ci_ref,
            cliente_nombre_ref,
            atributos,
            actualizado_en
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            'TESORERIA',
            'contabilidad.cobro',
            %s,
            'CONFIRMADO',
            %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb,
            CURRENT_TIMESTAMP
        )
        """,
        (
            cobro['fecha'],
            cobro['unidad_negocio_id'],
            cobro['moneda_codigo'],
            cobro['tipo_cambio'],
            cobro['glosa'],
            cobro['referencia'],
            cobro['id'],
            cobro.get('rubro_id'),
            cobro.get('publicidad_elemento_id_ref'),
            cobro.get('publicidad_elemento_codigo_ref'),
            cobro.get('vigencia_desde'),
            cobro.get('vigencia_hasta'),
            cobro.get('cliente_nit_ci_ref'),
            cobro.get('cliente_nombre_ref'),
            '{"origen":"tesoreria_cobros","version":"v6_documentos_cobrar"}',
        ),
    )

    secuencia = 1

    # Haber por facturas ya contabilizadas: se acredita la cuenta por cobrar,
    # no una cuenta de ingreso. Así se evita duplicar ingresos.
    for factura in facturas:
        monto = Decimal(str(factura.get('monto_aplicado') or 0)).quantize(CUANTIA)
        if monto <= 0:
            continue
        cuenta_cobrar = _clean(factura.get('cuenta_cobrar_codigo'))
        if not cuenta_cobrar:
            raise ValueError(
                f'La factura {factura.get("numero_factura") or factura.get("factura_id")} no tiene cuenta por cobrar registrada.'
            )
        auxiliar_id = factura.get('cliente_auxiliar_id') or cobro.get('cliente_auxiliar_id')
        glosa_factura = _truncate(
            f"Cobro factura {factura.get('numero_factura') or factura.get('factura_id')} - {factura.get('nombre_cliente') or cobro['glosa']}",
            300,
        )
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id,
                secuencia,
                cuenta_codigo,
                auxiliar_id,
                glosa,
                debe,
                haber,
                monto_moneda,
                referencia,
                atributos
            ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                cuenta_cobrar,
                auxiliar_id,
                glosa_factura,
                monto,
                monto,
                cobro['referencia'],
                '{"tipo":"haber_cuenta_por_cobrar_factura"}',
            ),
            return_id=False,
        )
        secuencia += 1

    # Haber por documentos por cobrar: se acredita la cuenta de cartera del documento.
    for documento in documentos:
        monto = Decimal(str(documento.get('monto_aplicado') or 0)).quantize(CUANTIA)
        if monto <= 0:
            continue
        cuenta_cartera = _clean(documento.get('cuenta_cartera_codigo'))
        if not cuenta_cartera:
            raise ValueError(
                f'El documento {documento.get("numero_documento") or documento.get("documento_id")} no tiene cuenta de cartera registrada.'
            )
        auxiliar_id = documento.get('cliente_auxiliar_id') or cobro.get('cliente_auxiliar_id')
        glosa_documento = _truncate(
            f"Cobro documento {documento.get('numero_documento') or documento.get('documento_id')} - {documento.get('cliente_nombre') or cobro['glosa']}",
            300,
        )
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id,
                secuencia,
                cuenta_codigo,
                auxiliar_id,
                glosa,
                debe,
                haber,
                monto_moneda,
                referencia,
                atributos
            ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                cuenta_cartera,
                auxiliar_id,
                glosa_documento,
                monto,
                monto,
                cobro['referencia'],
                '{"tipo":"haber_documento_por_cobrar"}',
            ),
            return_id=False,
        )
        secuencia += 1

    restante = (total - total_facturas - total_documentos).quantize(CUANTIA)
    lineas_validas = [item for item in lineas if Decimal(str(item['subtotal'])).quantize(CUANTIA) > 0]

    if restante > 0:
        pendiente_resto = restante
        if lineas_validas:
            for linea in lineas_validas:
                if pendiente_resto <= 0:
                    break
                subtotal = Decimal(str(linea['subtotal'])).quantize(CUANTIA)
                monto_linea = min(subtotal, pendiente_resto).quantize(CUANTIA)
                if monto_linea <= 0:
                    continue
                glosa_linea = _truncate(linea['descripcion'] or cobro['glosa'], 300)
                db.execute_insert(
                    """
                    INSERT INTO contabilidad.asiento_detalle (
                        asiento_id,
                        secuencia,
                        cuenta_codigo,
                        auxiliar_id,
                        glosa,
                        debe,
                        haber,
                        monto_moneda,
                        referencia,
                        atributos
                    ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        asiento_id,
                        secuencia,
                        cobro['contra_cuenta_codigo'],
                        cobro['cliente_auxiliar_id'],
                        glosa_linea,
                        monto_linea,
                        monto_linea,
                        cobro['referencia'],
                        '{"tipo":"haber_cobro_directo_resto"}',
                    ),
                    return_id=False,
                )
                secuencia += 1
                pendiente_resto = (pendiente_resto - monto_linea).quantize(CUANTIA)
        else:
            pendiente_resto = restante

        if pendiente_resto > 0:
            db.execute_insert(
                """
                INSERT INTO contabilidad.asiento_detalle (
                    asiento_id,
                    secuencia,
                    cuenta_codigo,
                    auxiliar_id,
                    glosa,
                    debe,
                    haber,
                    monto_moneda,
                    referencia,
                    atributos
                ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
                """,
                (
                    asiento_id,
                    secuencia,
                    cobro['contra_cuenta_codigo'],
                    cobro['cliente_auxiliar_id'],
                    _truncate(cobro['glosa'], 300),
                    pendiente_resto,
                    pendiente_resto,
                    cobro['referencia'],
                    '{"tipo":"haber_cobro_directo_resto_simple"}',
                ),
                return_id=False,
            )
            secuencia += 1

    db.execute_insert(
        """
        INSERT INTO contabilidad.asiento_detalle (
            asiento_id,
            secuencia,
            cuenta_codigo,
            auxiliar_id,
            glosa,
            debe,
            haber,
            monto_moneda,
            referencia,
            atributos
        ) VALUES (%s, %s, %s, NULL, %s, %s, 0, %s, %s, %s::jsonb)
        """,
        (
            asiento_id,
            secuencia,
            ingreso['cuenta_contable_codigo'],
            _truncate(f"Ingreso por {cobro['medio_pago']} - {ingreso['nombre']}", 300),
            total,
            total,
            cobro['referencia'],
            '{"tipo":"debe_ingreso_cobro"}',
        ),
        return_id=False,
    )

    db.execute_insert(
        """
        INSERT INTO contabilidad.documento_asiento (
            modulo,
            tabla_origen,
            origen_id,
            asiento_id
        ) VALUES ('TESORERIA', 'contabilidad.cobro', %s, %s)
        """,
        (cobro['id'], asiento_id),
        return_id=False,
    )

    return asiento_id


# ============================================================
# PDF del documento de cobro
# ============================================================

def _get_cobro_asiento_rows(db, asiento_id):
    if not asiento_id:
        return []
    tabla_cuentas = _tabla_cuentas(db)
    rows = db.execute_query(
        f"""
        SELECT
            ad.secuencia,
            ad.cuenta_codigo,
            COALESCE(cuenta.nombre, '') AS cuenta_nombre,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(ad.glosa, '') AS glosa,
            ad.debe,
            ad.haber,
            COALESCE(ad.referencia, '') AS referencia
        FROM contabilidad.asiento_detalle ad
        LEFT JOIN {tabla_cuentas} cuenta ON cuenta.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = ad.auxiliar_id
        WHERE ad.asiento_id = %s
        ORDER BY ad.secuencia, ad.id
        """,
        (asiento_id,),
    )
    return rows


def _linea_pdf_compromiso_cobro(linea):
    if linea.get('compromiso_codigo'):
        return f"{linea.get('compromiso_codigo')} - {linea.get('compromiso_nombre') or ''}"
    if linea.get('fecha_vencimiento'):
        return f"Cuota vence {format_date(linea.get('fecha_vencimiento'))}"
    return '-'


def _build_cobro_pdf_bytes(cobro, lineas, facturas, documentos, asiento_rows):
    fecha = format_date(cobro.get('fecha'))
    generado = datetime.now().strftime('%d/%m/%Y %H:%M')
    moneda = cobro.get('moneda_codigo') or 'BOB'
    tipo_cambio = Decimal(str(cobro.get('tipo_cambio') or 1)).quantize(CUANTIA_TC)
    asiento_label = f"#{cobro.get('asiento_id')}" if cobro.get('asiento_id') else 'Sin asiento'
    ingreso_label = cobro.get('medio_nombre') or '-'
    cuenta_ingreso = cobro.get('cuenta_ingreso_codigo') or '-'
    contra_cuenta = cobro.get('contra_cuenta_codigo') or '-'
    if cobro.get('contra_cuenta_nombre'):
        contra_cuenta = f"{contra_cuenta} - {cobro.get('contra_cuenta_nombre')}"

    sections = [
        {
            'title': 'Identificacion del documento',
            'items': [
                {'label': 'Cobro', 'value': f"#{cobro.get('id')}"},
                {'label': 'Fecha de operacion', 'value': fecha},
                {'label': 'Estado', 'value': cobro.get('estado') or '-'},
                {'label': 'Origen', 'value': cobro.get('origen_operacion') or '-'},
                {'label': 'Asiento contable', 'value': asiento_label},
                {'label': 'Referencia', 'value': cobro.get('referencia') or '-'},
            ],
        },
        {
            'title': 'Datos operativos',
            'items': [
                {'label': 'Unidad de negocio', 'value': f"{cobro.get('unidad_negocio_codigo') or ''} - {cobro.get('unidad_negocio_nombre') or ''}".strip(' -')},
                {'label': 'Rubro', 'value': f"{cobro.get('rubro_codigo') or ''} - {cobro.get('rubro_nombre') or ''}".strip(' -') or '-'},
                {'label': 'Cliente', 'value': cobro.get('cliente_nombre') or 'Sin cliente'},
                {'label': 'Medio de entrada', 'value': cobro.get('medio_pago') or '-'},
                {'label': 'Caja / banco', 'value': ingreso_label},
                {'label': 'Cuenta ingreso', 'value': cuenta_ingreso},
                {'label': 'Contra cuenta', 'value': contra_cuenta},
                {'label': 'Moneda', 'value': moneda},
                {'label': 'Tipo de cambio', 'value': f'{tipo_cambio}'},
            ],
        },
    ]

    publicidad_etiqueta = cobro.get('publicidad_elemento_etiqueta') or cobro.get('publicidad_elemento_codigo_ref')
    if publicidad_etiqueta:
        sections.append({
            'title': 'Referencia publicitaria',
            'items': [
                {'label': 'Codigo', 'value': cobro.get('publicidad_elemento_codigo_ref') or '-'},
                {'label': 'Referencia', 'value': publicidad_etiqueta},
                {'label': 'Vigencia', 'value': f"{format_date(cobro.get('vigencia_desde')) or '-'} a {format_date(cobro.get('vigencia_hasta')) or '-'}"},
                {'label': 'NIT / CI cliente', 'value': cobro.get('cliente_nit_ci_ref') or '-'},
                {'label': 'Cliente referencia', 'value': cobro.get('cliente_nombre_ref') or '-'},
                {'label': 'Unidad ref.', 'value': f"{cobro.get('unidad_negocio_codigo') or ''} - {cobro.get('unidad_negocio_nombre') or ''}".strip(' -')},
            ],
        })

    detalle_rows = []
    if lineas:
        for linea in lineas:
            cantidad = Decimal(str(linea.get('cantidad') or 0)).quantize(Decimal('0.0001'))
            precio_unitario = Decimal(str(linea.get('precio_unitario') or 0)).quantize(CUANTIA)
            subtotal = Decimal(str(linea.get('subtotal') or 0)).quantize(CUANTIA)
            detalle_rows.append([
                linea.get('secuencia') or '',
                linea.get('tipo_linea') or '',
                linea.get('descripcion') or '',
                _linea_pdf_compromiso_cobro(linea),
                f'{cantidad}',
                format_money(precio_unitario),
                format_money(subtotal),
            ])
    else:
        detalle_rows.append([
            '1',
            cobro.get('origen_operacion') or 'DIRECTO',
            cobro.get('glosa') or 'Cobro directo',
            '-',
            '1.0000',
            format_money(cobro.get('monto_total')),
            format_money(cobro.get('monto_total')),
        ])

    facturas_rows = []
    for factura in facturas or []:
        facturas_rows.append([
            factura.get('numero_factura') or '-',
            format_date(factura.get('fecha_emision')),
            factura.get('nombre_cliente') or '-',
            factura.get('nit_cliente') or '-',
            factura.get('moneda_codigo') or moneda,
            format_money(factura.get('importe_total')),
            format_money(factura.get('monto_aplicado')),
        ])

    documentos_rows = []
    for documento in documentos or []:
        documentos_rows.append([
            documento.get('numero_documento') or '-',
            documento.get('tipo_documento') or '-',
            format_date(documento.get('fecha_documento')),
            documento.get('cliente_nombre') or '-',
            str(documento.get('gestion_origen') or '-'),
            documento.get('moneda_codigo') or moneda,
            format_money(documento.get('importe_total')),
            format_money(documento.get('monto_aplicado')),
        ])

    accounting_rows = []
    for row in asiento_rows or []:
        cuenta = row.get('cuenta_codigo') or ''
        if row.get('cuenta_nombre'):
            cuenta = f"{cuenta} - {row.get('cuenta_nombre')}"
        accounting_rows.append([
            row.get('secuencia') or '',
            cuenta,
            row.get('glosa') or '',
            row.get('auxiliar_nombre') or '-',
            format_money(row.get('debe')),
            format_money(row.get('haber')),
        ])

    additional_tables = []
    if facturas_rows:
        additional_tables.append({
            'title': 'Facturas aplicadas',
            'columns': [
                {'label': 'Factura', 'width': 20},
                {'label': 'Fecha', 'width': 20, 'align': 'center'},
                {'label': 'Cliente', 'width': 45},
                {'label': 'NIT', 'width': 24},
                {'label': 'Mon.', 'width': 12, 'align': 'center'},
                {'label': 'Importe', 'width': 25, 'align': 'right'},
                {'label': 'Aplicado', 'width': 28, 'align': 'right'},
            ],
            'rows': facturas_rows,
            'empty_message': 'Este cobro no tiene facturas aplicadas.',
        })

    if documentos_rows:
        additional_tables.append({
            'title': 'Documentos por cobrar aplicados',
            'columns': [
                {'label': 'Documento', 'width': 22},
                {'label': 'Tipo', 'width': 20},
                {'label': 'Fecha', 'width': 18, 'align': 'center'},
                {'label': 'Cliente', 'width': 40},
                {'label': 'Gest.', 'width': 12, 'align': 'center'},
                {'label': 'Mon.', 'width': 12, 'align': 'center'},
                {'label': 'Importe', 'width': 24, 'align': 'right'},
                {'label': 'Aplicado', 'width': 26, 'align': 'right'},
            ],
            'rows': documentos_rows,
            'empty_message': 'Este cobro no tiene documentos aplicados.',
        })

    return build_accounting_document_pdf(
        title='Comprobante de Cobro',
        subtitle=f'DXT Conta - Tesoreria - Emitido {generado}',
        document_number=f"COBRO-{int(cobro.get('id')):06d}",
        state=cobro.get('estado') or '',
        sections=sections,
        detail_columns=[
            {'label': '#', 'width': 10, 'align': 'center'},
            {'label': 'Tipo', 'width': 22},
            {'label': 'Descripcion', 'width': 60},
            {'label': 'Compromiso', 'width': 30},
            {'label': 'Cant.', 'width': 14, 'align': 'right'},
            {'label': 'P. Unit.', 'width': 18, 'align': 'right'},
            {'label': 'Subtotal', 'width': 20, 'align': 'right'},
        ],
        detail_rows=detalle_rows,
        totals=[
            {'label': f'Total {moneda}', 'value': format_money(cobro.get('monto_total'))},
            {'label': 'Tipo cambio', 'value': f'{tipo_cambio}'},
        ],
        additional_tables=additional_tables,
        accounting_columns=[
            {'label': '#', 'width': 10, 'align': 'center'},
            {'label': 'Cuenta', 'width': 45},
            {'label': 'Glosa', 'width': 59},
            {'label': 'Auxiliar', 'width': 25},
            {'label': 'Debe', 'width': 17.5, 'align': 'right'},
            {'label': 'Haber', 'width': 17.5, 'align': 'right'},
        ],
        accounting_rows=accounting_rows,
        notes=[{'title': 'Glosa / concepto', 'text': cobro.get('glosa') or '-'}],
        emitted_by=_usuario_actual(),
        logo_file=logo_path(),
        generated_at=generado,
    )


def _get_form_context(cobro_id=None):
    with DatabaseManager() as db:
        catalogs = _get_catalogs(db)
        cobro = _get_cobro_header(db, cobro_id) if cobro_id else None
        lineas = _get_cobro_detail_rows(db, cobro_id) if cobro_id else []
        facturas = _get_cobro_factura_rows(db, cobro_id) if cobro_id else []
        documentos = _get_cobro_documento_rows(db, cobro_id) if cobro_id else []
        fecha_referencia = cobro['fecha'] if cobro else date.today()
        tc = _get_tipo_cambio_row(db, fecha_referencia)
        return {
            'catalogs': catalogs,
            'cobro_data': cobro,
            'lineas_data': lineas,
            'facturas_data': facturas,
            'documentos_data': documentos,
            'tipo_cambio_data': {
                'fecha': fecha_referencia.isoformat(),
                'existe': tc['existe'],
                'usd_paralelo': _to_float(tc['usd_paralelo']),
                'ufv': _to_float(tc['ufv']),
            },
            'mode': 'edit' if cobro_id else 'create',
            'puede_editar': _puede_editar(),
            'gestion_actual': _gestion_actual(),
            'prefill_data': {
                'origen': _clean(request.args.get('origen')).upper(),
                'documento_id': request.args.get('documento_id', type=int),
                'factura_id': request.args.get('factura_id', type=int),
                'compromiso_detalle_id': request.args.get('compromiso_detalle_id', type=int),
            },
        }


# ============================================================
# Rutas vistas
# ============================================================
@tesoreria_cobros_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    with DatabaseManager() as db:
        unidades_negocio = _get_unidades_negocio(db)
    return render_template(
        'cobros_index.html',
        puede_editar=_puede_editar(),
        gestion_actual=_gestion_actual(),
        unidades_negocio=unidades_negocio,
    )


@tesoreria_cobros_bp.route('/nuevo')
@login_required
@roles_required(ROLES_EDICION)
def nuevo():
    return render_template('cobros_form.html', **_get_form_context())


@tesoreria_cobros_bp.route('/<int:cobro_id>/editar')
@login_required
@roles_required(ROLES_LECTURA)
def editar(cobro_id):
    context = _get_form_context(cobro_id)
    if not context['cobro_data']:
        return render_template('errors/404.html'), 404
    return render_template('cobros_form.html', **context)


@tesoreria_cobros_bp.route('/<int:cobro_id>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf(cobro_id):
    try:
        with DatabaseManager() as db:
            cobro = _get_cobro_header(db, cobro_id)
            if not cobro:
                return render_template('errors/404.html'), 404
            lineas = _get_cobro_detail_rows(db, cobro_id)
            facturas = _get_cobro_factura_rows(db, cobro_id)
            documentos = _get_cobro_documento_rows(db, cobro_id)
            asiento_rows = _get_cobro_asiento_rows(db, cobro.get('asiento_id'))
            pdf_bytes = _build_cobro_pdf_bytes(cobro, lineas, facturas, documentos, asiento_rows)
            fecha_doc = cobro['fecha'].strftime('%Y%m%d') if cobro.get('fecha') else datetime.now().strftime('%Y%m%d')
            nombre = f"cobro_{int(cobro_id):06d}_{fecha_doc}.pdf"
            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'inline; filename={nombre}'},
            )
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del cobro. {exc}', status=500)


# ============================================================
# APIs catálogo y consulta
# ============================================================
@tesoreria_cobros_bp.route('/api/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_lista():
    with DatabaseManager() as db:
        return _json_ok(data=_build_index_rows(db))


@tesoreria_cobros_bp.route('/api/<int:cobro_id>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_obtener(cobro_id):
    with DatabaseManager() as db:
        cobro = _get_cobro_header(db, cobro_id)
        if not cobro:
            return _json_error('El cobro no existe.', status=404)
        lineas = _get_cobro_detail_rows(db, cobro_id)
        facturas = _get_cobro_factura_rows(db, cobro_id)
        documentos = _get_cobro_documento_rows(db, cobro_id)
        return _json_ok(data={'header': cobro, 'lineas': lineas, 'facturas': facturas, 'documentos': documentos})


@tesoreria_cobros_bp.route('/api/auxiliares', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_auxiliares():
    texto = _clean(request.args.get('q'))
    condiciones = ['activo = TRUE']
    params = []
    if texto:
        like = f'%{texto}%'
        condiciones.append('(nombre ILIKE %s OR COALESCE(codigo_externo, \'\') ILIKE %s OR CAST(id AS TEXT) ILIKE %s)')
        params.extend([like, like, like])

    with DatabaseManager() as db:
        rows = db.execute_query(
            f"""
            SELECT id, nombre, COALESCE(nit_ci, '') AS nit_ci
            FROM contabilidad.auxiliar
            WHERE {' AND '.join(condiciones)}
            ORDER BY nombre
            LIMIT 150
            """,
            tuple(params),
        )
        return _json_ok(data=rows)


@tesoreria_cobros_bp.route('/api/cuentas', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_cuentas():
    texto = _clean(request.args.get('q'))
    tabla_cuentas = None
    with DatabaseManager() as db:
        tabla_cuentas = _tabla_cuentas(db)
        condiciones = ['activo = TRUE', 'es_postable = TRUE']
        params = []
        if texto:
            like = f'%{texto}%'
            condiciones.append('(codigo ILIKE %s OR nombre ILIKE %s)')
            params.extend([like, like])
        rows = db.execute_query(
            f"""
            SELECT
                codigo,
                nombre,
                COALESCE(requiere_auxiliar, FALSE) AS requiere_auxiliar,
                COALESCE(requiere_cc, FALSE) AS requiere_cc,
                (codigo || ' - ' || nombre) AS etiqueta
            FROM {tabla_cuentas}
            WHERE {' AND '.join(condiciones)}
            ORDER BY codigo
            LIMIT 150
            """,
            tuple(params),
        )
        return _json_ok(data=rows)


@tesoreria_cobros_bp.route('/api/publicidad-elementos', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_publicidad_elementos():
    q = _clean(request.args.get('q'))
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)

    condiciones = [
        "e.estado = 'ACTIVA'",
        "s.estado = 'ACTIVA'",
        "COALESCE(btrim(e.codigo_gamlp), '') <> ''",
    ]
    params = []

    if unidad_negocio_id:
        condiciones.append('s.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    if q:
        condiciones.append("(e.codigo_gamlp ILIKE %s OR s.nombre ILIKE %s OR e.codigo ILIKE %s OR e.nombre ILIKE %s)")
        like = f'%{q}%'
        params.extend([like, like, like, like])

    with DatabaseManager() as db:
        rows = db.execute_query(
            f"""
            SELECT
                e.id,
                e.codigo_gamlp,
                e.codigo AS elemento_codigo,
                e.nombre AS elemento_nombre,
                s.id AS estructura_id,
                s.codigo AS estructura_codigo,
                s.nombre AS estructura_nombre,
                s.unidad_negocio_id,
                COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
                COALESCE(uneg.nombre, '') AS unidad_negocio_nombre
            FROM publicidad.elemento_publicitario e
            INNER JOIN publicidad.estructura_publicitaria s ON s.id = e.estructura_id
            LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = s.unidad_negocio_id
            WHERE {' AND '.join(condiciones)}
            ORDER BY e.codigo_gamlp ASC, s.nombre ASC
            LIMIT 40
            """,
            tuple(params),
        )

    data = []
    for row in rows:
        etiqueta = f"{row['codigo_gamlp']} · {row['estructura_nombre']}"
        if row['unidad_negocio_codigo'] or row['unidad_negocio_nombre']:
            etiqueta += f" · UN {str(row['unidad_negocio_codigo'] or '').strip()} {str(row['unidad_negocio_nombre'] or '').strip()}".rstrip()
        data.append({
            'id': row['id'],
            'codigo_gamlp': row['codigo_gamlp'],
            'unidad_negocio_id': row['unidad_negocio_id'],
            'estructura_nombre': row['estructura_nombre'],
            'text': etiqueta,
        })

    return _json_ok(data=data)


def _search_cobrables_unificados(db, current_cobro_id=None, texto=None, unidad_negocio_id=None, limit=120):
    """Devuelve una bandeja operativa unificada de todo lo pendiente por cobrar.

    Mantiene separada la persistencia real: documentos manuales/historicos siguen en
    documento_por_cobrar y facturas electronicas siguen en factura_electronica.
    La unificacion es solo para que el operador vea una sola lista cobrable.
    """
    documentos = _search_documentos_cobrar_disponibles(
        db,
        current_cobro_id=current_cobro_id,
        texto=texto,
        unidad_negocio_id=unidad_negocio_id,
        limit=limit,
    )
    facturas = _search_facturas_disponibles(
        db,
        current_cobro_id=current_cobro_id,
        texto=texto,
        unidad_negocio_id=unidad_negocio_id,
        limit=limit,
    )

    rows = []
    for row in documentos:
        item = dict(row)
        item['fuente_cobro'] = 'DOCUMENTO_COBRAR'
        item['fuente_label'] = 'Documento por cobrar'
        item['item_id'] = item.get('documento_id') or item.get('id')
        item['factura_id'] = None
        rows.append(item)

    for row in facturas:
        fecha = row.get('fecha_emision')
        gestion = None
        if fecha:
            try:
                gestion = int(str(fecha)[:4])
            except (TypeError, ValueError):
                gestion = None
        importe_total = Decimal(str(row.get('importe_total') or 0)).quantize(CUANTIA)
        disponible = Decimal(str(row.get('saldo_disponible') or 0)).quantize(CUANTIA)
        cobrado = (importe_total - disponible).quantize(CUANTIA)
        rows.append({
            'id': f"FE-{int(row['id'])}",
            'item_id': int(row['id']),
            'factura_id': int(row['id']),
            'documento_id': None,
            'fuente_cobro': 'FACTURA_ELECTRONICA',
            'fuente_label': 'Factura electronica',
            'unidad_negocio_id': row.get('unidad_negocio_id'),
            'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
            'cliente_nombre': row.get('nombre_cliente') or '',
            'cliente_nit': row.get('nit_cliente') or '',
            'numero_documento': row.get('numero_factura') or '',
            'tipo_documento': 'FACTURA',
            'origen_documento': 'FACTURA_ELECTRONICA',
            'tratamiento_contable': 'FACTURA_ELECTRONICA_CXC',
            'gestion_origen': gestion,
            'fecha_documento': fecha,
            'moneda_codigo': row.get('moneda_codigo') or 'BOB',
            'estado': row.get('estado') or '',
            'unidad_negocio_codigo': row.get('unidad_negocio_codigo') or '',
            'unidad_negocio_nombre': row.get('unidad_negocio_nombre') or '',
            'cuenta_cartera_codigo': row.get('cuenta_cobrar_codigo') or '',
            'cuenta_cartera_nombre': 'Cuenta por cobrar de factura electronica',
            'importe_total': _to_float(importe_total),
            'importe_cobrado': _to_float(cobrado),
            'saldo_pendiente': _to_float(disponible),
            'saldo_disponible': _to_float(disponible),
            'monto_actual_cobro': _to_float(row.get('monto_actual_cobro')),
        })

    
    def _pending_sort_id(item):
        for key in ('item_id', 'documento_id', 'factura_id', 'id'):
            value = item.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return 0

    rows.sort(
        key=lambda item: (
            str(item.get('fecha_documento') or ''),
            _pending_sort_id(item),
            str(item.get('numero_documento') or '')
        ),
        reverse=True,
    )
    return rows[:limit]


@tesoreria_cobros_bp.route('/api/facturas-pendientes', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_facturas_pendientes():
    cobro_id = request.args.get('cobro_id', type=int)
    texto = request.args.get('q', '')
    unidad_negocio_id = request.args.get('unidad_negocio_id', type=int)
    factura_id = request.args.get('factura_id', type=int)
    with DatabaseManager() as db:
        rows = _search_facturas_disponibles(
            db,
            current_cobro_id=cobro_id,
            texto=texto,
            unidad_negocio_id=unidad_negocio_id,
            factura_id=factura_id,
        )
        return _json_ok(rows=rows)



@tesoreria_cobros_bp.route('/api/documentos-pendientes', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_documentos_pendientes():
    cobro_id = request.args.get('cobro_id', type=int)
    texto = request.args.get('q', '')
    unidad_negocio_id = request.args.get('unidad_negocio_id', type=int)
    auxiliar_id = request.args.get('auxiliar_id', type=int)
    documento_id = request.args.get('documento_id', type=int)
    unificado = request.args.get('unificado', '').lower() in ('1', 'true', 'si', 'sí')
    with DatabaseManager() as db:
        if unificado:
            rows = _search_cobrables_unificados(
                db,
                current_cobro_id=cobro_id,
                texto=texto,
                unidad_negocio_id=unidad_negocio_id,
            )
        else:
            rows = _search_documentos_cobrar_disponibles(
                db,
                current_cobro_id=cobro_id,
                texto=texto,
                unidad_negocio_id=unidad_negocio_id,
                auxiliar_id=auxiliar_id,
                documento_id=documento_id,
            )
        return _json_ok(rows=rows)


@tesoreria_cobros_bp.route('/api/pendientes', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_pendientes():
    cobro_id = request.args.get('cobro_id', type=int)
    filtros = {
        'q': request.args.get('q', ''),
        'auxiliar_id': request.args.get('auxiliar_id'),
        'cuenta_codigo': request.args.get('cuenta_codigo', ''),
        'unidad_negocio_id': request.args.get('unidad_negocio_id'),
        'compromiso_detalle_id': request.args.get('compromiso_detalle_id'),
    }
    with DatabaseManager() as db:
        rows = _get_pending_commitments(db, current_cobro_id=cobro_id, filtros=filtros)
        return _json_ok(rows=rows)


@tesoreria_cobros_bp.route('/api/tipo-cambio/<fecha>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_tipo_cambio_fecha(fecha):
    try:
        fecha_operacion = _parse_date(fecha, 'Fecha')
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    moneda_codigo = _clean(request.args.get('moneda', 'BOB')).upper() or 'BOB'

    with DatabaseManager() as db:
        row = _get_tipo_cambio_row(db, fecha_operacion)
        aplicado = _resolve_tipo_cambio_aplicado(moneda_codigo, row)

    return _json_ok(
        existe=row['existe'],
        fecha=fecha_operacion.isoformat(),
        moneda_codigo=moneda_codigo,
        usd_paralelo=_to_float(row['usd_paralelo']),
        ufv=_to_float(row['ufv']),
        tipo_cambio_aplicado=_to_float(aplicado),
        tipo_cambio_url=url_for('tipo_cambio.gestion'),
        message=None if row['existe'] else 'No existe tipo de cambio para la fecha seleccionada. Se aplicará valor 1.',
    )


# ============================================================
# APIs transaccionales
# ============================================================
@tesoreria_cobros_bp.route('/api/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_guardar():
    payload = request.get_json(silent=True) or {}
    cobro_id = payload.get('id')

    try:
        with DatabaseManager() as db:
            previous_factura_ids = []
            previous_documento_ids = []
            if cobro_id:
                cobro_id = _parse_int(cobro_id, 'Cobro')
                cobro = _get_cobro_header(db, cobro_id)
                if not cobro:
                    raise ValueError('El cobro no existe.')
                if cobro['estado'] != 'BORRADOR':
                    raise ValueError('Solo se pueden editar cobros en borrador.')
                previous_factura_ids = _get_cobro_factura_ids(db, cobro_id)
                previous_documento_ids = _get_cobro_documento_ids(db, cobro_id)

            composed = _compose_save_payload(db, payload, current_cobro_id=cobro_id)
            header = composed['header']
            lineas = composed['lineas']
            monto_total = composed['monto_total']
            origen_operacion = composed['origen_operacion']
            facturas_aplicadas = composed['facturas_aplicadas']
            documentos_aplicados = composed['documentos_aplicados']

            if cobro_id:
                _update_cobro(db, cobro_id, header, origen_operacion, monto_total)
            else:
                cobro_id = _insert_cobro(db, header, origen_operacion, monto_total)

            _sync_cobro_detalle(db, cobro_id, lineas)
            _sync_factura_aplicacion(db, cobro_id, facturas_aplicadas)
            _sync_documento_cobrar_aplicacion(db, cobro_id, documentos_aplicados, header['fecha'])
            _recalculate_facturas(
                db,
                previous_factura_ids + [item['factura_id'] for item in facturas_aplicadas],
            )
            _recalculate_documentos_cobrar(
                db,
                previous_documento_ids + [item['documento_id'] for item in documentos_aplicados],
            )

            cobro = _get_cobro_header(db, cobro_id)
            return _json_ok(
                'Cobro guardado correctamente.',
                cobro_id=cobro_id,
                origen_operacion=origen_operacion,
                monto_total=_to_float(cobro['monto_total']) if cobro else _to_float(monto_total),
                total_facturas=len(facturas_aplicadas),
                monto_facturas=_to_float(composed['monto_facturas_aplicadas']),
                total_documentos=len(documentos_aplicados),
                monto_documentos=_to_float(composed['monto_documentos_aplicados']),
            )

    except ValueError as exc:
        return _json_error(str(exc))
    except errors.UniqueViolation:
        return _json_error('Una de las cuotas, facturas o documentos ya fue tomada por otro usuario.', status=409)
    except Exception as exc:
        return _json_error(f'No se pudo guardar el cobro. {exc}', status=500)


@tesoreria_cobros_bp.route('/api/<int:cobro_id>/confirmar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_confirmar(cobro_id):
    try:
        with DatabaseManager() as db:
            cobro = _get_cobro_header(db, cobro_id)
            if not cobro:
                raise ValueError('El cobro no existe.')
            if cobro['estado'] != 'BORRADOR':
                raise ValueError('Solo se pueden confirmar cobros en borrador.')

            lineas = _get_cobro_detail_rows(db, cobro_id)
            facturas = _get_cobro_factura_rows(db, cobro_id)
            documentos = _get_cobro_documento_rows(db, cobro_id)
            total_facturas = sum(
                (Decimal(str(item['monto_aplicado'] or 0)).quantize(CUANTIA) for item in facturas),
                Decimal('0.00'),
            ).quantize(CUANTIA)
            total_documentos = sum(
                (Decimal(str(item['monto_aplicado'] or 0)).quantize(CUANTIA) for item in documentos),
                Decimal('0.00'),
            ).quantize(CUANTIA)
            total_cobro = Decimal(str(cobro['monto_total'])).quantize(CUANTIA)

            if cobro['origen_operacion'] == 'COMPROMISO':
                if not lineas:
                    raise ValueError('Debe registrar al menos una cuota antes de confirmar.')
                total_lineas = sum(
                    (Decimal(str(item['subtotal'])) for item in lineas),
                    Decimal('0.00'),
                ).quantize(CUANTIA)
                if total_lineas != total_cobro:
                    raise ValueError('El total de la cabecera no coincide con el detalle del cobro.')
                detalle_ids = [item['compromiso_detalle_id'] for item in lineas if item['tipo_linea'] == 'COMPROMISO']
                _validate_commitment_lines(
                    db,
                    {
                        'compromiso_detalle_ids': detalle_ids,
                        'unidad_negocio_id': cobro['unidad_negocio_id']
                    },
                    current_cobro_id=cobro_id
                )
            elif cobro['origen_operacion'] == 'DOCUMENTO_COBRAR':
                if not documentos:
                    raise ValueError('Debe seleccionar al menos un documento por cobrar.')
                if total_documentos != total_cobro:
                    raise ValueError('El total de documentos aplicados debe coincidir con el total del cobro.')
            else:
                if lineas:
                    total_lineas = sum(
                        (Decimal(str(item['subtotal'])) for item in lineas),
                        Decimal('0.00'),
                    ).quantize(CUANTIA)
                    if total_lineas != total_cobro:
                        raise ValueError('El total de la cabecera no coincide con el detalle del cobro.')
                elif total_cobro <= 0:
                    raise ValueError('Debes indicar un total válido para confirmar el cobro directo.')
            _validate_factura_links(
                db,
                {
                    'unidad_negocio_id': cobro['unidad_negocio_id'],  # 🔥 ESTA ES LA CLAVE
                    'facturas_aplicadas': [
                        {
                            'factura_id': item['factura_id'],
                            'monto_aplicado': item['monto_aplicado'],
                        }
                        for item in facturas
                    ]
                },
                total_cobro,
                current_cobro_id=cobro_id,
            )
            documentos_validados = _validate_documento_cobrar_links(
                db,
                {
                    'unidad_negocio_id': cobro['unidad_negocio_id'],
                    'documentos_aplicados': [
                        {
                            'documento_id': item['documento_id'],
                            'monto_aplicado': item['monto_aplicado'],
                        }
                        for item in documentos
                    ]
                },
                total_cobro,
                current_cobro_id=cobro_id,
            )
            if total_facturas > total_cobro:
                raise ValueError('El total aplicado a facturas excede el total del cobro.')
            if (total_facturas + total_documentos) > total_cobro:
                raise ValueError('El total aplicado a documentos y facturas excede el total del cobro.')

            asiento_id = _create_asiento_cobro(db, cobro, lineas, facturas, documentos_validados['documentos'])

            updated = db.execute_update(
                """
                UPDATE contabilidad.cobro
                SET estado = 'CONFIRMADO',
                    asiento_id = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND estado = 'BORRADOR'
                """,
                (asiento_id, cobro_id),
            )
            if not updated:
                raise ValueError('No se pudo confirmar el cobro.')

            _recalculate_facturas(db, [item['factura_id'] for item in facturas])
            _recalculate_documentos_cobrar(db, [item['documento_id'] for item in documentos])
            return _json_ok('Cobro confirmado correctamente.', cobro_id=cobro_id, asiento_id=asiento_id)

    except ValueError as exc:
        return _json_error(str(exc))
    except errors.UniqueViolation:
        return _json_error('Una de las cuotas, facturas o documentos ya fue tomada por otro usuario.', status=409)
    except Exception as exc:
        return _json_error(f'No se pudo confirmar el cobro. {exc}', status=500)

@tesoreria_cobros_bp.route('/api/<int:cobro_id>/eliminar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_eliminar(cobro_id):
    try:
        with DatabaseManager() as db:
            cobro = _get_cobro_header(db, cobro_id)
            if not cobro:
                raise ValueError('El cobro no existe.')
            if cobro['estado'] != 'BORRADOR':
                raise ValueError('Solo se pueden eliminar cobros en borrador.')

            factura_ids = _get_cobro_factura_ids(db, cobro_id)
            documento_ids = _get_cobro_documento_ids(db, cobro_id)

            if cobro.get('asiento_id'):
                raise ValueError('El cobro no se puede eliminar porque ya tiene asiento contable asociado.')

            db.execute_delete(
                'DELETE FROM contabilidad.factura_aplicacion WHERE cobro_id = %s',
                (cobro_id,),
            )
            db.execute_delete(
                'DELETE FROM contabilidad.documento_por_cobrar_aplicacion WHERE cobro_id = %s',
                (cobro_id,),
            )
            db.execute_delete(
                'DELETE FROM contabilidad.cobro_detalle WHERE cobro_id = %s',
                (cobro_id,),
            )
            deleted = db.execute_delete(
                "DELETE FROM contabilidad.cobro WHERE id = %s AND estado = 'BORRADOR'",
                (cobro_id,),
            )
            if not deleted:
                raise ValueError('No se pudo eliminar el cobro.')

            _recalculate_facturas(db, factura_ids)
            _recalculate_documentos_cobrar(db, documento_ids)
            return _json_ok('Cobro eliminado correctamente.', cobro_id=cobro_id)

    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo eliminar el cobro. {exc}', status=500)

# ------------------------------------------------------------
# AYUDA DEL MÓDULO
# ------------------------------------------------------------
@tesoreria_cobros_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('tesoreria_cobros_help.html')