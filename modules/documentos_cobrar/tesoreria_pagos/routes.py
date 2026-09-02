# ============================================================
# DXT CONTA - Módulo Tesorería Pagos
# Reingeniería unificada: compromiso + directo
# ============================================================

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Response, jsonify, render_template, request, session, url_for
from psycopg2 import errors

from database.db_manager import DatabaseManager
from modules.tesoreria_pagos import tesoreria_pagos_bp
from utils.decorators import login_required, roles_required
from modules.reportes_rapidos.core.utils import logo_path
from utils.documentos_pdf import build_accounting_document_pdf, format_date, format_money


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
MEDIOS_OPERABLES = ['CAJA', 'BANCO']
ESTADOS_DOCUMENTO = ['BORRADOR', 'CONFIRMADO', 'ANULADO']
ORIGENES_OPERACION = ['COMPROMISO', 'DIRECTO']
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
            e.id,
            e.codigo_gamlp,
            e.codigo AS elemento_codigo,
            e.nombre AS elemento_nombre,
            s.id AS estructura_id,
            s.codigo AS estructura_codigo,
            COALESCE(s.codigo_gamlp, '') AS estructura_codigo_gamlp,
            s.nombre AS estructura_nombre,
            s.unidad_negocio_id,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            'ELEMENTO' AS ref_tipo
        FROM publicidad.elemento_publicitario e
        INNER JOIN publicidad.estructura_publicitaria s ON s.id = e.estructura_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = s.unidad_negocio_id
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        tuple(params),
    )
    if not rows:
        return None
    row = rows[0]
    row['ref_id'] = row['id']
    row['ref_key'] = f"ELEMENTO:{int(row['id'])}"
    row['codigo_ref'] = row['codigo_gamlp']
    row['nombre_ref'] = row['elemento_nombre']
    row['etiqueta'] = f"{row['codigo_gamlp']} {row['elemento_nombre']} - ELEMENTO"
    return row


def _get_publicidad_estructura_row(db, estructura_id, unidad_negocio_id=None, permitir_inactivo=False):
    if not estructura_id:
        return None

    condiciones = ['s.id = %s', "COALESCE(btrim(s.codigo_gamlp), '') <> ''"]
    params = [estructura_id]

    if not permitir_inactivo:
        condiciones.append("s.estado = 'ACTIVA'")

    if unidad_negocio_id:
        condiciones.append('s.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    rows = db.execute_query(
        f"""
        SELECT
            s.id,
            s.codigo_gamlp,
            s.codigo AS estructura_codigo,
            s.nombre AS estructura_nombre,
            s.unidad_negocio_id,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            'ESTRUCTURA' AS ref_tipo
        FROM publicidad.estructura_publicitaria s
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = s.unidad_negocio_id
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        tuple(params),
    )
    if not rows:
        return None
    row = rows[0]
    row['ref_id'] = row['id']
    row['ref_key'] = f"ESTRUCTURA:{int(row['id'])}"
    row['codigo_ref'] = row['codigo_gamlp']
    row['nombre_ref'] = row['estructura_nombre']
    row['etiqueta'] = f"{row['codigo_gamlp']} {row['estructura_nombre']} - ESTRUCTURA"
    return row


def _parse_publicidad_referencia(raw_value):
    raw = str(raw_value or '').strip()
    if not raw:
        return None, None
    if ':' in raw:
        tipo, rid = raw.split(':', 1)
        tipo = tipo.strip().upper()
        try:
            rid_int = int(rid.strip())
        except (TypeError, ValueError):
            return None, None
        if tipo in ('ELEMENTO', 'ESTRUCTURA'):
            return tipo, rid_int
        return None, None
    try:
        return 'ELEMENTO', int(raw)
    except (TypeError, ValueError):
        return None, None

def _get_publicidad_elementos_catalog(db):
    rows = db.execute_query(
        """
        SELECT * FROM (
            SELECT
                'ELEMENTO' AS ref_tipo,
                e.id AS ref_id,
                e.codigo_gamlp,
                e.nombre AS nombre_ref,
                s.unidad_negocio_id
            FROM publicidad.elemento_publicitario e
            INNER JOIN publicidad.estructura_publicitaria s ON s.id = e.estructura_id
            WHERE e.estado = 'ACTIVA'
              AND s.estado = 'ACTIVA'
              AND COALESCE(btrim(e.codigo_gamlp), '') <> ''

            UNION ALL

            SELECT
                'ESTRUCTURA' AS ref_tipo,
                s.id AS ref_id,
                s.codigo_gamlp,
                s.nombre AS nombre_ref,
                s.unidad_negocio_id
            FROM publicidad.estructura_publicitaria s
            WHERE s.estado = 'ACTIVA'
              AND COALESCE(btrim(s.codigo_gamlp), '') <> ''
        ) t
        ORDER BY codigo_gamlp ASC, nombre_ref ASC
        """
    )
    for row in rows:
        row['ref_key'] = f"{row['ref_tipo']}:{int(row['ref_id'])}"
        row['codigo_ref'] = row['codigo_gamlp']
        row['etiqueta'] = f"{row['codigo_gamlp']} {row['nombre_ref']} - {row['ref_tipo']}"
    return rows


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
        FROM {_tabla_cuentas(db)}
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



def _get_pago_header(db, pago_id):
    rows = db.execute_query(
        """
        SELECT
            p.id,
            p.fecha,
            p.unidad_negocio_id,
            p.proveedor_auxiliar_id,
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
            p.vigencia_desde,
            p.vigencia_hasta,
            p.cliente_nit_ci_ref,
            p.cliente_nombre_ref,
            p.creado_en,
            p.actualizado_en,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            COALESCE(aux.nombre, '') AS proveedor_nombre,
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
            END AS cuenta_salida_codigo
        FROM contabilidad.pago p
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = p.unidad_negocio_id
        LEFT JOIN contabilidad.rubro_operacion rub ON rub.id = p.rubro_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = p.proveedor_auxiliar_id
        LEFT JOIN contabilidad.caja caja ON caja.id = p.caja_id
        LEFT JOIN contabilidad.cuenta_bancaria banco ON banco.id = p.cuenta_bancaria_id
        LEFT JOIN contabilidad.cuenta cuenta ON cuenta.codigo = p.contra_cuenta_codigo
        LEFT JOIN publicidad.elemento_publicitario pe ON pe.id = p.publicidad_elemento_id_ref
        LEFT JOIN publicidad.estructura_publicitaria esp ON esp.id = pe.estructura_id
        LEFT JOIN publicidad.estructura_publicitaria se ON se.codigo_gamlp = p.publicidad_elemento_codigo_ref AND p.publicidad_elemento_id_ref IS NULL
        WHERE p.id = %s
        LIMIT 1
        """,
        (pago_id,),
    )
    return rows[0] if rows else None



def _get_pago_detail_rows(db, pago_id):
    rows = db.execute_query(
        """
        SELECT
            pd.id,
            pd.pago_id,
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
        FROM contabilidad.pago_detalle pd
        LEFT JOIN contabilidad.compromiso_detalle d ON d.id = pd.compromiso_detalle_id
        LEFT JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = c.unidad_negocio_id
        WHERE pd.pago_id = %s
        ORDER BY pd.secuencia, pd.id
        """,
        (pago_id,),
    )

    data = []
    for row in rows:
        data.append({
            'id': row['id'],
            'pago_id': row['pago_id'],
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



def _get_pending_commitments(db, current_pago_id=None, filtros=None):
    filtros = filtros or {}
    params = [current_pago_id, current_pago_id, current_pago_id, current_pago_id]
    condiciones = [
        "c.tipo = 'PAGAR'",
        "c.activo = TRUE",
    ]

    unidad_negocio_id = filtros.get('unidad_negocio_id')
    if unidad_negocio_id:
        condiciones.append('c.unidad_negocio_id = %s')
        params.append(int(unidad_negocio_id))

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

    cuenta_codigo = _clean(filtros.get('cuenta_codigo'))
    if cuenta_codigo:
        condiciones.append('c.cuenta_contable = %s')
        params.append(cuenta_codigo)

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
                    FROM contabilidad.pago_detalle pdx
                    INNER JOIN contabilidad.pago px ON px.id = pdx.pago_id
                    WHERE pdx.compromiso_detalle_id = d.id
                      AND pdx.tipo_linea = 'COMPROMISO'
                      AND px.estado = 'BORRADOR'
                      AND (%s IS NULL OR pdx.pago_id <> %s)
                ) THEN TRUE ELSE FALSE
            END AS reservado_en_otro_borrador,
            CASE
                WHEN %s IS NOT NULL AND EXISTS (
                    SELECT 1
                    FROM contabilidad.pago_detalle pdy
                    WHERE pdy.pago_id = %s
                      AND pdy.tipo_linea = 'COMPROMISO'
                      AND pdy.compromiso_detalle_id = d.id
                ) THEN TRUE ELSE FALSE
            END AS seleccionado_actual,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM contabilidad.pago_detalle pdc
                    INNER JOIN contabilidad.pago pc ON pc.id = pdc.pago_id
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
        if row['estado'] not in ('PENDIENTE', 'PAGADO') and not row['seleccionado_actual']:
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
            COALESCE(aux.nombre, 'Sin proveedor') AS proveedor_nombre,
            CASE
                WHEN p.caja_id IS NOT NULL THEN caja.nombre
                WHEN p.cuenta_bancaria_id IS NOT NULL THEN banco.nombre_banco || ' · ' || banco.numero_cuenta
                ELSE 'No definido'
            END AS salida_nombre,
            COALESCE(tot.cantidad_lineas, 0) AS cantidad_lineas,
            COALESCE(tot.cantidad_compromisos, 0) AS cantidad_compromisos,
            COALESCE(tot.cantidad_directas, 0) AS cantidad_directas
        FROM contabilidad.pago p
        LEFT JOIN contabilidad.unidad_negocio uneg ON uneg.id = p.unidad_negocio_id
        LEFT JOIN contabilidad.rubro_operacion rub ON rub.id = p.rubro_id
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = p.proveedor_auxiliar_id
        LEFT JOIN contabilidad.caja caja ON caja.id = p.caja_id
        LEFT JOIN contabilidad.cuenta_bancaria banco ON banco.id = p.cuenta_bancaria_id
        LEFT JOIN (
            SELECT
                pago_id,
                COUNT(*) AS cantidad_lineas,
                SUM(CASE WHEN tipo_linea = 'COMPROMISO' THEN 1 ELSE 0 END) AS cantidad_compromisos,
                SUM(CASE WHEN tipo_linea = 'DIRECTO' THEN 1 ELSE 0 END) AS cantidad_directas
            FROM contabilidad.pago_detalle
            GROUP BY pago_id
        ) tot ON tot.pago_id = p.id
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
            'proveedor_nombre': row['proveedor_nombre'],
            'salida_nombre': row['salida_nombre'],
            'cantidad_lineas': int(row['cantidad_lineas'] or 0),
            'cantidad_compromisos': int(row['cantidad_compromisos'] or 0),
            'cantidad_directas': int(row['cantidad_directas'] or 0),
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
    referencia = _normalize_text(payload.get('referencia'), 'Referencia', 150, required=False)
    glosa = _normalize_text(payload.get('glosa'), 'Glosa', 500, required=False)
    rubro_id = _parse_int(payload.get('rubro_id'), 'Rubro', required=False)
    publicidad_ref_tipo, publicidad_ref_id = _parse_publicidad_referencia(payload.get('publicidad_elemento_id_ref'))
    publicidad_elemento_id_ref = None
    publicidad_elemento_codigo_ref = _normalize_text(payload.get('publicidad_elemento_codigo_ref'), 'Código de referencia publicitaria', 30, required=False)
    vigencia_desde = _parse_date(payload.get('vigencia_desde'), 'Vigencia desde', required=False)
    vigencia_hasta = _parse_date(payload.get('vigencia_hasta'), 'Vigencia hasta', required=False)
    cliente_nit_ci_ref = _normalize_text(payload.get('cliente_nit_ci_ref'), 'NIT/CI cliente', 50, required=False)
    cliente_nombre_ref = _normalize_text(payload.get('cliente_nombre_ref'), 'Cliente referencia', 200, required=False)
    proveedor_auxiliar_id = _parse_int(payload.get('proveedor_auxiliar_id'), 'Proveedor', required=False)
    contra_cuenta_codigo = _normalize_text(payload.get('contra_cuenta_codigo'), 'Contra cuenta', 30, required=False)
    caja_id = _parse_int(payload.get('caja_id'), 'Caja', required=False)
    cuenta_bancaria_id = _parse_int(payload.get('cuenta_bancaria_id'), 'Cuenta bancaria', required=False)

    unidad = _get_unidad_row(db, unidad_negocio_id)
    if not unidad:
        raise ValueError('Debe seleccionar una unidad de negocio activa.')

    if medio_pago not in MEDIOS_OPERABLES:
        raise ValueError('Debe seleccionar un medio válido: Caja o Banco.')

    if medio_pago == 'CAJA':
        if not caja_id:
            raise ValueError('Debe seleccionar la caja de salida.')
        cuenta_bancaria_id = None
    if medio_pago == 'BANCO':
        if not cuenta_bancaria_id:
            raise ValueError('Debe seleccionar la cuenta bancaria de salida.')
        caja_id = None

    moneda = db.execute_query(
        """
        SELECT codigo
        FROM contabilidad.moneda
        WHERE activo = TRUE AND codigo = %s
        LIMIT 1
        """,
        (moneda_codigo,),
    )
    if not moneda:
        raise ValueError('La moneda seleccionada no existe o está inactiva.')

    if caja_id:
        caja = db.execute_query(
            """
            SELECT id, cuenta_contable_codigo
            FROM contabilidad.caja
            WHERE activo = TRUE AND id = %s
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
            WHERE activo = TRUE AND id = %s
            LIMIT 1
            """,
            (cuenta_bancaria_id,),
        )
        if not banco:
            raise ValueError('La cuenta bancaria seleccionada no existe o está inactiva.')

    rubro = _get_rubro_row(db, rubro_id) if rubro_id else None
    if rubro_id and not rubro:
        raise ValueError('El rubro seleccionado no existe o está inactivo.')

    if rubro_id:
        if not publicidad_ref_tipo or not publicidad_ref_id:
            raise ValueError('Debes seleccionar una referencia publicitaria cuando elijas un rubro.')

        if publicidad_ref_tipo == 'ESTRUCTURA':
            estructura_publicitaria = _get_publicidad_estructura_row(db, publicidad_ref_id, unidad_negocio_id=unidad_negocio_id)
            if not estructura_publicitaria:
                raise ValueError('La estructura publicitaria seleccionada no existe, está inactiva, no tiene código GAMLP o no pertenece a la unidad de negocio elegida.')
            publicidad_elemento_id_ref = None
            publicidad_elemento_codigo_ref = estructura_publicitaria['codigo_gamlp']
        else:
            elemento_publicitario = _get_publicidad_elemento_row(db, publicidad_ref_id, unidad_negocio_id=unidad_negocio_id)
            if not elemento_publicitario:
                raise ValueError('El elemento publicitario seleccionado no existe, está inactivo, no tiene código GAMLP o no pertenece a la unidad de negocio elegida.')
            publicidad_elemento_id_ref = elemento_publicitario['id']
            publicidad_elemento_codigo_ref = elemento_publicitario['codigo_gamlp']

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

    auxiliar = None
    if proveedor_auxiliar_id:
        auxiliar = _get_auxiliar_row(db, proveedor_auxiliar_id)
        if not auxiliar or not auxiliar.get('activo', True):
            raise ValueError('El proveedor seleccionado no existe o está inactivo.')

    cuenta = None
    if contra_cuenta_codigo:
        cuenta = _get_account_row(db, contra_cuenta_codigo)
        if not cuenta:
            raise ValueError('La cuenta contable seleccionada no existe o está inactiva.')

    tc_row = _get_tipo_cambio_row(db, fecha)
    tipo_cambio = _resolve_tipo_cambio_aplicado(moneda_codigo, tc_row)

    return {
        'fecha': fecha,
        'unidad_negocio_id': unidad_negocio_id,
        'unidad_negocio_codigo': unidad['codigo'],
        'unidad_negocio_nombre': unidad['nombre'],
        'medio_pago': medio_pago,
        'moneda_codigo': moneda_codigo,
        'tipo_cambio': tipo_cambio,
        'referencia': referencia,
        'glosa': glosa,
        'proveedor_auxiliar_id': proveedor_auxiliar_id,
        'contra_cuenta_codigo': contra_cuenta_codigo,
        'caja_id': caja_id,
        'cuenta_bancaria_id': cuenta_bancaria_id,
        'tipo_cambio_info': tc_row,
        'cuenta_row': cuenta,
        'auxiliar_row': auxiliar,
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



def _validate_commitment_lines(db, payload, current_pago_id=None):
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
          AND c.tipo = 'PAGAR'
          AND c.activo = TRUE
        ORDER BY d.fecha_vencimiento, d.id
        """,
        (detalle_ids,),
    )

    if len(rows) != len(set(detalle_ids)):
        raise ValueError('Una o más cuotas seleccionadas ya no están disponibles.')

    conflict_rows = db.execute_query(
        """
        SELECT DISTINCT pd.compromiso_detalle_id
        FROM contabilidad.pago_detalle pd
        INNER JOIN contabilidad.pago p ON p.id = pd.pago_id
        WHERE pd.compromiso_detalle_id = ANY(%s)
          AND pd.tipo_linea = 'COMPROMISO'
          AND p.estado IN ('BORRADOR', 'CONFIRMADO')
          AND (%s IS NULL OR p.id <> %s)
        """,
        (detalle_ids, current_pago_id, current_pago_id),
    )
    if conflict_rows:
        raise ValueError('Una o más cuotas ya fueron tomadas en otro pago.')

    cuentas = set()
    auxiliares = set()
    unidades = set()
    total = Decimal('0.00')
    lineas = []

    for secuencia, row in enumerate(rows, start=1):
        if row['estado'] not in ('PENDIENTE', 'PAGADO'):
            raise ValueError('Solo se pueden seleccionar cuotas vigentes del compromiso.')
        if not row['auxiliar_id']:
            raise ValueError(f'El compromiso {row["compromiso_codigo"]} no tiene proveedor asociado.')
        if not row['cuenta_contable']:
            raise ValueError(f'El compromiso {row["compromiso_codigo"]} no tiene cuenta contable configurada.')

        cuentas.add(row['cuenta_contable'])
        auxiliares.add(row['auxiliar_id'])
        unidades.add(row['unidad_negocio_id'])
        subtotal = Decimal(str(row['monto_programado'])).quantize(CUANTIA)
        total += subtotal
        lineas.append({
            'secuencia': secuencia,
            'tipo_linea': 'COMPROMISO',
            'compromiso_detalle_id': row['id'],
            'descripcion': _truncate(
                f"Compromiso {row['compromiso_codigo']} - {row['compromiso_nombre']} - {row['fecha_vencimiento'].strftime('%d/%m/%Y')}",
                300,
            ),
            'cantidad': Decimal('1.0000'),
            'precio_unitario': subtotal,
            'subtotal': subtotal,
            'observacion': _truncate(row['observacion'] or '', 300),
            'compromiso_codigo': row['compromiso_codigo'],
            'compromiso_nombre': row['compromiso_nombre'],
            'fecha_vencimiento': row['fecha_vencimiento'].isoformat() if row['fecha_vencimiento'] else None,
            'auxiliar_id': row['auxiliar_id'],
            'auxiliar_nombre': row['auxiliar_nombre'],
            'cuenta_contable': row['cuenta_contable'],
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
        })

    if len(cuentas) > 1:
        raise ValueError('Las cuotas seleccionadas deben pertenecer a la misma cuenta contable.')
    if len(auxiliares) > 1:
        raise ValueError('Las cuotas seleccionadas deben pertenecer al mismo proveedor.')
    if len(unidades) > 1:
        raise ValueError('Las cuotas seleccionadas deben pertenecer a la misma unidad de negocio.')

    return {
        'origen_operacion': 'COMPROMISO',
        'lineas': lineas,
        'monto_total': total.quantize(CUANTIA),
        'proveedor_auxiliar_id': lineas[0]['auxiliar_id'],
        'contra_cuenta_codigo': lineas[0]['cuenta_contable'],
        'unidad_negocio_id': lineas[0]['unidad_negocio_id'],
        'descripcion_resumen': f"Pago de {len(lineas)} cuota(s) de compromiso",
    }



def _validate_direct_lines(db, payload, header):
    use_detail = bool(payload.get('usar_detalle_directo'))
    items = payload.get('direct_items') or []
    if not isinstance(items, list):
        raise ValueError('El detalle directo enviado no tiene un formato válido.')

    if not header['contra_cuenta_codigo']:
        raise ValueError('Debe seleccionar la contra cuenta del pago.')

    cuenta = header['cuenta_row'] or _get_account_row(db, header['contra_cuenta_codigo'])
    if not cuenta:
        raise ValueError('La contra cuenta seleccionada no existe.')

    proveedor_auxiliar_id = header['proveedor_auxiliar_id']
    if cuenta['requiere_auxiliar'] and not proveedor_auxiliar_id:
        raise ValueError('La cuenta seleccionada requiere proveedor/auxiliar.')

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

        descripcion_resumen = f"Pago directo con {len(lineas)} ítem(s)"
    else:
        total_manual = _decimal(
            payload.get('monto_total_manual'),
            'Total del pago',
            allow_zero=True,
            quant=CUANTIA,
            required=False,
        )
        total = total_manual or Decimal('0.00')
        descripcion_resumen = 'Pago directo simple'

    return {
        'origen_operacion': 'DIRECTO',
        'lineas': lineas,
        'monto_total': total.quantize(CUANTIA),
        'proveedor_auxiliar_id': proveedor_auxiliar_id,
        'contra_cuenta_codigo': header['contra_cuenta_codigo'],
        'descripcion_resumen': descripcion_resumen,
        'usa_detalle_directo': use_detail,
    }



def _compose_save_payload(db, payload, current_pago_id=None):
    header = _validate_header(db, payload)
    origen = _clean(payload.get('origen_operacion')).upper()
    if origen not in ORIGENES_OPERACION:
        raise ValueError('Debe seleccionar el origen del pago.')

    if origen == 'COMPROMISO':
        detalle = _validate_commitment_lines(db, payload, current_pago_id=current_pago_id)
        header['proveedor_auxiliar_id'] = detalle['proveedor_auxiliar_id']
        header['contra_cuenta_codigo'] = detalle['contra_cuenta_codigo']
        if int(header['unidad_negocio_id']) != int(detalle['unidad_negocio_id']):
            raise ValueError('La unidad de negocio del pago no coincide con la de las cuotas seleccionadas.')
        if not header['glosa']:
            header['glosa'] = _truncate(detalle['descripcion_resumen'], 500)
    else:
        detalle = _validate_direct_lines(db, payload, header)
        if not header['glosa']:
            header['glosa'] = _truncate(detalle['descripcion_resumen'], 500)

    if not header['glosa']:
        raise ValueError('La glosa es obligatoria.')

    return {
        'header': header,
        'origen_operacion': detalle['origen_operacion'],
        'lineas': detalle['lineas'],
        'monto_total': detalle['monto_total'],
        'usa_detalle_directo': detalle.get('usa_detalle_directo', False),
    }


# ============================================================
# Persistencia
# ============================================================

def _insert_pago(db, header, origen_operacion, monto_total):
    return db.execute_insert(
        """
        INSERT INTO contabilidad.pago (
            fecha,
            unidad_negocio_id,
            proveedor_auxiliar_id,
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
            header['proveedor_auxiliar_id'],
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


def _update_pago(db, pago_id, header, origen_operacion, monto_total):
    updated = db.execute_update(
        """
        UPDATE contabilidad.pago
        SET
            fecha = %s,
            unidad_negocio_id = %s,
            proveedor_auxiliar_id = %s,
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
            header['proveedor_auxiliar_id'],
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
            pago_id,
        ),
    )
    if not updated:
        raise ValueError('Solo se pueden editar pagos en borrador.')



def _sync_pago_detalle(db, pago_id, lineas):
    db.execute_delete('DELETE FROM contabilidad.pago_detalle WHERE pago_id = %s', (pago_id,))
    for linea in lineas:
        db.execute_insert(
            """
            INSERT INTO contabilidad.pago_detalle (
                pago_id,
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
                pago_id,
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



def _get_cuenta_salida(db, pago):
    if pago['medio_pago'] == 'CAJA':
        rows = db.execute_query(
            """
            SELECT nombre, cuenta_contable_codigo
            FROM contabilidad.caja
            WHERE id = %s
            LIMIT 1
            """,
            (pago['caja_id'],),
        )
    else:
        rows = db.execute_query(
            """
            SELECT nombre_banco || ' · ' || numero_cuenta AS nombre, cuenta_contable_codigo
            FROM contabilidad.cuenta_bancaria
            WHERE id = %s
            LIMIT 1
            """,
            (pago['cuenta_bancaria_id'],),
        )
    if not rows:
        raise ValueError('No se pudo obtener la cuenta de salida del pago.')
    return rows[0]



def _create_asiento_pago(db, pago, lineas):
    salida = _get_cuenta_salida(db, pago)
    total = Decimal(str(pago['monto_total'])).quantize(CUANTIA)
    if total <= 0:
        raise ValueError('El pago no tiene un total válido para contabilizar.')

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
            'contabilidad.pago',
            %s,
            'CONFIRMADO',
            %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb,
            CURRENT_TIMESTAMP
        )
        """,
        (
            pago['fecha'],
            pago['unidad_negocio_id'],
            pago['moneda_codigo'],
            pago['tipo_cambio'],
            pago['glosa'],
            pago['referencia'],
            pago['id'],
            pago.get('rubro_id'),
            pago.get('publicidad_elemento_id_ref'),
            pago.get('publicidad_elemento_codigo_ref'),
            pago.get('vigencia_desde'),
            pago.get('vigencia_hasta'),
            pago.get('cliente_nit_ci_ref'),
            pago.get('cliente_nombre_ref'),
            '{"origen":"tesoreria_pagos","version":"v4"}',
        ),
    )

    secuencia = 1
    lineas_validas = [item for item in lineas if Decimal(str(item['subtotal'])).quantize(CUANTIA) > 0]

    if lineas_validas:
        for linea in lineas_validas:
            subtotal = Decimal(str(linea['subtotal'])).quantize(CUANTIA)
            glosa_linea = _truncate(linea['descripcion'] or pago['glosa'], 300)
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
                ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s::jsonb)
                """,
                (
                    asiento_id,
                    secuencia,
                    pago['contra_cuenta_codigo'],
                    pago['proveedor_auxiliar_id'],
                    glosa_linea,
                    subtotal,
                    subtotal,
                    pago['referencia'],
                    '{"tipo":"debe_pago"}',
                ),
                return_id=False,
            )
            secuencia += 1
    else:
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
            ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                pago['contra_cuenta_codigo'],
                pago['proveedor_auxiliar_id'],
                _truncate(pago['glosa'], 300),
                total,
                total,
                pago['referencia'],
                '{"tipo":"debe_pago_simple"}',
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
        ) VALUES (%s, %s, %s, NULL, %s, 0, %s, %s, %s, %s::jsonb)
        """,
        (
            asiento_id,
            secuencia,
            salida['cuenta_contable_codigo'],
            _truncate(f"Salida por {pago['medio_pago']} - {salida['nombre']}", 300),
            total,
            total,
            pago['referencia'],
            '{"tipo":"haber_pago"}',
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
        ) VALUES ('TESORERIA', 'contabilidad.pago', %s, %s)
        """,
        (pago['id'], asiento_id),
        return_id=False,
    )

    return asiento_id



# ============================================================
# PDF del documento de pago
# ============================================================

def _get_pago_asiento_rows(db, asiento_id):
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


def _linea_pdf_compromiso(linea):
    if linea.get('compromiso_codigo'):
        return f"{linea.get('compromiso_codigo')} - {linea.get('compromiso_nombre') or ''}"
    if linea.get('fecha_vencimiento'):
        return f"Cuota vence {format_date(linea.get('fecha_vencimiento'))}"
    return '-'


def _build_pago_pdf_bytes(pago, lineas, asiento_rows):
    fecha = format_date(pago.get('fecha'))
    generado = datetime.now().strftime('%d/%m/%Y %H:%M')
    moneda = pago.get('moneda_codigo') or 'BOB'
    tipo_cambio = Decimal(str(pago.get('tipo_cambio') or 1)).quantize(CUANTIA_TC)
    asiento_label = f"#{pago.get('asiento_id')}" if pago.get('asiento_id') else 'Sin asiento'
    salida_label = pago.get('medio_nombre') or '-'
    cuenta_salida = pago.get('cuenta_salida_codigo') or '-'
    contra_cuenta = pago.get('contra_cuenta_codigo') or '-'
    if pago.get('contra_cuenta_nombre'):
        contra_cuenta = f"{contra_cuenta} - {pago.get('contra_cuenta_nombre')}"

    sections = [
        {
            'title': 'Identificacion del documento',
            'items': [
                {'label': 'Pago', 'value': f"#{pago.get('id')}"},
                {'label': 'Fecha de operacion', 'value': fecha},
                {'label': 'Estado', 'value': pago.get('estado') or '-'},
                {'label': 'Origen', 'value': pago.get('origen_operacion') or '-'},
                {'label': 'Asiento contable', 'value': asiento_label},
                {'label': 'Referencia', 'value': pago.get('referencia') or '-'},
            ],
        },
        {
            'title': 'Datos operativos',
            'items': [
                {'label': 'Unidad de negocio', 'value': f"{pago.get('unidad_negocio_codigo') or ''} - {pago.get('unidad_negocio_nombre') or ''}".strip(' -')},
                {'label': 'Rubro', 'value': f"{pago.get('rubro_codigo') or ''} - {pago.get('rubro_nombre') or ''}".strip(' -') or '-'},
                {'label': 'Proveedor / cliente', 'value': pago.get('proveedor_nombre') or 'Sin proveedor'},
                {'label': 'Medio de salida', 'value': pago.get('medio_pago') or '-'},
                {'label': 'Caja / banco', 'value': salida_label},
                {'label': 'Cuenta salida', 'value': cuenta_salida},
                {'label': 'Contra cuenta', 'value': contra_cuenta},
                {'label': 'Moneda', 'value': moneda},
                {'label': 'Tipo de cambio', 'value': f'{tipo_cambio}'},
            ],
        },
    ]

    publicidad_etiqueta = pago.get('publicidad_elemento_etiqueta') or pago.get('publicidad_elemento_codigo_ref')
    if publicidad_etiqueta:
        sections.append({
            'title': 'Referencia publicitaria',
            'items': [
                {'label': 'Codigo', 'value': pago.get('publicidad_elemento_codigo_ref') or '-'},
                {'label': 'Referencia', 'value': publicidad_etiqueta},
                {'label': 'Vigencia', 'value': f"{format_date(pago.get('vigencia_desde')) or '-'} a {format_date(pago.get('vigencia_hasta')) or '-'}"},
                {'label': 'NIT / CI cliente', 'value': pago.get('cliente_nit_ci_ref') or '-'},
                {'label': 'Cliente', 'value': pago.get('cliente_nombre_ref') or '-'},
                {'label': 'Unidad ref.', 'value': f"{pago.get('unidad_negocio_codigo') or ''} - {pago.get('unidad_negocio_nombre') or ''}".strip(' -')},
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
                _linea_pdf_compromiso(linea),
                f'{cantidad}',
                format_money(precio_unitario),
                format_money(subtotal),
            ])
    else:
        detalle_rows.append([
            '1',
            pago.get('origen_operacion') or 'DIRECTO',
            pago.get('glosa') or 'Pago directo',
            '-',
            '1.0000',
            format_money(pago.get('monto_total')),
            format_money(pago.get('monto_total')),
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

    return build_accounting_document_pdf(
        title='Comprobante de Pago',
        subtitle=f'DXT Conta - Tesoreria - Emitido {generado}',
        document_number=f"PAGO-{int(pago.get('id')):06d}",
        state=pago.get('estado') or '',
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
            {'label': f'Total {moneda}', 'value': format_money(pago.get('monto_total'))},
            {'label': 'Tipo cambio', 'value': f'{tipo_cambio}'},
        ],
        accounting_columns=[
            {'label': '#', 'width': 10, 'align': 'center'},
            {'label': 'Cuenta', 'width': 45},
            {'label': 'Glosa', 'width': 59},
            {'label': 'Auxiliar', 'width': 25},
            {'label': 'Debe', 'width': 17.5, 'align': 'right'},
            {'label': 'Haber', 'width': 17.5, 'align': 'right'},
        ],
        accounting_rows=accounting_rows,
        notes=[{'title': 'Glosa / concepto', 'text': pago.get('glosa') or '-'}],
        emitted_by=_usuario_actual(),
        logo_file=logo_path(),
        generated_at=generado,
    )


def _get_form_context(pago_id=None):
    with DatabaseManager() as db:
        catalogs = _get_catalogs(db)
        pago = _get_pago_header(db, pago_id) if pago_id else None
        lineas = _get_pago_detail_rows(db, pago_id) if pago_id else []
        fecha_referencia = pago['fecha'] if pago else date.today()
        tc = _get_tipo_cambio_row(db, fecha_referencia)
        if pago:
            pago['publicidad_ref_key'] = f"ELEMENTO:{int(pago['publicidad_elemento_id_ref'])}" if pago.get('publicidad_elemento_id_ref') else None
            if not pago.get('publicidad_ref_key') and str(pago.get('publicidad_elemento_codigo_ref') or '').strip():
                estructura = db.execute_query("SELECT id FROM publicidad.estructura_publicitaria WHERE codigo_gamlp = %s LIMIT 1", (pago['publicidad_elemento_codigo_ref'],))
                if estructura:
                    pago['publicidad_ref_key'] = f"ESTRUCTURA:{int(estructura[0]['id'])}"
        return {
            'catalogs': catalogs,
            'pago_data': pago,
            'lineas_data': lineas,
            'tipo_cambio_data': {
                'fecha': fecha_referencia.isoformat(),
                'existe': tc['existe'],
                'usd_paralelo': _to_float(tc['usd_paralelo']),
                'ufv': _to_float(tc['ufv']),
            },
            'mode': 'edit' if pago_id else 'create',
            'puede_editar': _puede_editar(),
            'gestion_actual': _gestion_actual(),
        }


# ============================================================
# Rutas vistas
# ============================================================
@tesoreria_pagos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    with DatabaseManager() as db:
        unidades_negocio = _get_unidades_negocio(db)
        rubros = _get_rubros(db)
    return render_template(
        'pagos_index.html',
        puede_editar=_puede_editar(),
        gestion_actual=_gestion_actual(),
        unidades_negocio=unidades_negocio,
        rubros=rubros,
    )


@tesoreria_pagos_bp.route('/nuevo')
@login_required
@roles_required(ROLES_EDICION)
def nuevo():
    return render_template('pagos_form.html', **_get_form_context())


@tesoreria_pagos_bp.route('/<int:pago_id>/editar')
@login_required
@roles_required(ROLES_LECTURA)
def editar(pago_id):
    context = _get_form_context(pago_id)
    if not context['pago_data']:
        return render_template('errors/404.html'), 404
    return render_template('pagos_form.html', **context)


@tesoreria_pagos_bp.route('/<int:pago_id>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf(pago_id):
    try:
        with DatabaseManager() as db:
            pago = _get_pago_header(db, pago_id)
            if not pago:
                return render_template('errors/404.html'), 404
            lineas = _get_pago_detail_rows(db, pago_id)
            asiento_rows = _get_pago_asiento_rows(db, pago.get('asiento_id'))
            pdf_bytes = _build_pago_pdf_bytes(pago, lineas, asiento_rows)
            fecha_doc = pago['fecha'].strftime('%Y%m%d') if pago.get('fecha') else datetime.now().strftime('%Y%m%d')
            nombre = f"pago_{int(pago_id):06d}_{fecha_doc}.pdf"
            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'inline; filename={nombre}'},
            )
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del pago. {exc}', status=500)


# ============================================================
# APIs catálogo y consulta
# ============================================================
@tesoreria_pagos_bp.route('/api/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_lista():
    with DatabaseManager() as db:
        return jsonify({'data': _build_index_rows(db)})


@tesoreria_pagos_bp.route('/api/<int:pago_id>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_obtener(pago_id):
    with DatabaseManager() as db:
        pago = _get_pago_header(db, pago_id)
        if not pago:
            return _json_error('El pago no existe.', status=404)
        lineas = _get_pago_detail_rows(db, pago_id)
        return _json_ok(data={'header': pago, 'lineas': lineas})


@tesoreria_pagos_bp.route('/api/auxiliares', methods=['GET'])
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


@tesoreria_pagos_bp.route('/api/cuentas', methods=['GET'])
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


@tesoreria_pagos_bp.route('/api/publicidad-elementos', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_publicidad_elementos():
    q = _clean(request.args.get('q'))
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)

    condiciones_elemento = ["e.estado = 'ACTIVA'", "s.estado = 'ACTIVA'", "COALESCE(btrim(e.codigo_gamlp), '') <> ''"]
    condiciones_estructura = ["s.estado = 'ACTIVA'", "COALESCE(btrim(s.codigo_gamlp), '') <> ''"]
    params = []
    params2 = []
    if unidad_negocio_id:
        condiciones_elemento.append('s.unidad_negocio_id = %s')
        condiciones_estructura.append('s.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
        params2.append(unidad_negocio_id)
    if q:
        like = f'%{q}%'
        condiciones_elemento.append("(e.codigo_gamlp ILIKE %s OR e.nombre ILIKE %s OR s.codigo_gamlp ILIKE %s OR s.nombre ILIKE %s OR e.codigo ILIKE %s OR s.codigo ILIKE %s)")
        condiciones_estructura.append("(s.codigo_gamlp ILIKE %s OR s.nombre ILIKE %s OR s.codigo ILIKE %s)")
        params.extend([like, like, like, like, like, like])
        params2.extend([like, like, like])

    with DatabaseManager() as db:
        rows = db.execute_query(
            f"""
            SELECT * FROM (
                SELECT 'ELEMENTO' AS ref_tipo, e.id AS ref_id, e.codigo_gamlp, e.nombre AS nombre_ref, s.unidad_negocio_id
                FROM publicidad.elemento_publicitario e
                INNER JOIN publicidad.estructura_publicitaria s ON s.id = e.estructura_id
                WHERE {' AND '.join(condiciones_elemento)}
                UNION ALL
                SELECT 'ESTRUCTURA' AS ref_tipo, s.id AS ref_id, s.codigo_gamlp, s.nombre AS nombre_ref, s.unidad_negocio_id
                FROM publicidad.estructura_publicitaria s
                WHERE {' AND '.join(condiciones_estructura)}
            ) t
            ORDER BY codigo_gamlp ASC, nombre_ref ASC
            LIMIT 60
            """,
            tuple(params + params2),
        )
    data = []
    for row in rows:
        data.append({
            'id': f"{row['ref_tipo']}:{int(row['ref_id'])}",
            'ref_tipo': row['ref_tipo'],
            'ref_id': row['ref_id'],
            'codigo_ref': row['codigo_gamlp'],
            'codigo_gamlp': row['codigo_gamlp'],
            'unidad_negocio_id': row['unidad_negocio_id'],
            'etiqueta': f"{row['codigo_gamlp']} {row['nombre_ref']} - {row['ref_tipo']}",
        })
    return jsonify({'success': True, 'data': data})


@tesoreria_pagos_bp.route('/api/pendientes', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_pendientes():
    pago_id = request.args.get('pago_id', type=int)
    filtros = {
        'q': request.args.get('q', ''),
        'auxiliar_id': request.args.get('auxiliar_id'),
        'cuenta_codigo': request.args.get('cuenta_codigo', ''),
        'unidad_negocio_id': request.args.get('unidad_negocio_id'),
    }
    with DatabaseManager() as db:
        rows = _get_pending_commitments(db, current_pago_id=pago_id, filtros=filtros)
        return _json_ok(rows=rows)


@tesoreria_pagos_bp.route('/api/tipo-cambio/<fecha>', methods=['GET'])
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
@tesoreria_pagos_bp.route('/api/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_guardar():
    payload = request.get_json(silent=True) or {}
    pago_id = payload.get('id')

    try:
        with DatabaseManager() as db:
            if pago_id:
                pago_id = _parse_int(pago_id, 'Pago')
                pago = _get_pago_header(db, pago_id)
                if not pago:
                    raise ValueError('El pago no existe.')
                if pago['estado'] != 'BORRADOR':
                    raise ValueError('Solo se pueden editar pagos en borrador.')

            composed = _compose_save_payload(db, payload, current_pago_id=pago_id)
            header = composed['header']
            lineas = composed['lineas']
            monto_total = composed['monto_total']
            origen_operacion = composed['origen_operacion']

            if pago_id:
                _update_pago(db, pago_id, header, origen_operacion, monto_total)
            else:
                pago_id = _insert_pago(db, header, origen_operacion, monto_total)

            _sync_pago_detalle(db, pago_id, lineas)
            pago = _get_pago_header(db, pago_id)
            return _json_ok(
                'Pago guardado correctamente.',
                pago_id=pago_id,
                origen_operacion=origen_operacion,
                monto_total=_to_float(pago['monto_total']) if pago else _to_float(monto_total),
            )

    except ValueError as exc:
        return _json_error(str(exc))
    except errors.UniqueViolation:
        return _json_error('Una de las cuotas ya fue tomada por otro usuario.', status=409)
    except Exception as exc:
        return _json_error(f'No se pudo guardar el pago. {exc}', status=500)


@tesoreria_pagos_bp.route('/api/<int:pago_id>/confirmar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_confirmar(pago_id):
    try:
        with DatabaseManager() as db:
            pago = _get_pago_header(db, pago_id)
            if not pago:
                raise ValueError('El pago no existe.')
            if pago['estado'] != 'BORRADOR':
                raise ValueError('Solo se pueden confirmar pagos en borrador.')

            lineas = _get_pago_detail_rows(db, pago_id)
            total_pago = Decimal(str(pago['monto_total'])).quantize(CUANTIA)

            if pago['origen_operacion'] == 'COMPROMISO':
                if not lineas:
                    raise ValueError('Debe registrar al menos una cuota antes de confirmar.')
                total_lineas = sum(Decimal(str(item['subtotal'])) for item in lineas).quantize(CUANTIA)
                if total_lineas != total_pago:
                    raise ValueError('El total de la cabecera no coincide con el detalle del pago.')
                detalle_ids = [item['compromiso_detalle_id'] for item in lineas if item['tipo_linea'] == 'COMPROMISO']
                _validate_commitment_lines(db, {'compromiso_detalle_ids': detalle_ids}, current_pago_id=pago_id)
            else:
                if lineas:
                    total_lineas = sum(Decimal(str(item['subtotal'])) for item in lineas).quantize(CUANTIA)
                    if total_lineas != total_pago:
                        raise ValueError('El total de la cabecera no coincide con el detalle del pago.')
                elif total_pago <= 0:
                    raise ValueError('Debes indicar un total válido para confirmar el pago directo.')

            asiento_id = _create_asiento_pago(db, pago, lineas)

            updated = db.execute_update(
                """
                UPDATE contabilidad.pago
                SET estado = 'CONFIRMADO',
                    asiento_id = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND estado = 'BORRADOR'
                """,
                (asiento_id, pago_id),
            )
            if not updated:
                raise ValueError('No se pudo confirmar el pago.')

            return _json_ok('Pago confirmado correctamente.', pago_id=pago_id, asiento_id=asiento_id)

    except ValueError as exc:
        return _json_error(str(exc))
    except errors.UniqueViolation:
        return _json_error('Una de las cuotas ya fue tomada por otro usuario.', status=409)
    except Exception as exc:
        return _json_error(f'No se pudo confirmar el pago. {exc}', status=500)


@tesoreria_pagos_bp.route('/api/<int:pago_id>/eliminar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_eliminar(pago_id):
    try:
        with DatabaseManager() as db:
            pago = _get_pago_header(db, pago_id)
            if not pago:
                raise ValueError('El pago no existe.')
            if pago['estado'] != 'BORRADOR':
                raise ValueError('Solo se pueden eliminar pagos en borrador.')
            if pago.get('asiento_id'):
                raise ValueError('El pago no se puede eliminar porque ya tiene asiento contable asociado.')

            deleted = db.execute_delete(
                "DELETE FROM contabilidad.pago WHERE id = %s AND estado = 'BORRADOR'",
                (pago_id,),
            )
            if not deleted:
                raise ValueError('No se pudo eliminar el pago.')

            return _json_ok('Pago eliminado correctamente.', pago_id=pago_id)

    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo eliminar el pago. {exc}', status=500)

# ------------------------------------------------------------
# AYUDA DEL MÓDULO
# ------------------------------------------------------------
@tesoreria_pagos_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('tesoreria_pagos_help.html')