# ============================================================
# DXT CONTA - Módulo Tesorería Caja y Bancos
# Posición, maestros y movimientos de tesorería
# ============================================================

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Response, jsonify, render_template, request, session, url_for
from psycopg2 import errors

from database.db_manager import DatabaseManager
from modules.tesoreria_caja_bancos import tesoreria_caja_bancos_bp
from utils.decorators import login_required, roles_required
from modules.reportes_rapidos.core.utils import logo_path
from utils.documentos_pdf import build_accounting_document_pdf, format_date, format_money


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
ESTADOS_DOCUMENTO = ['BORRADOR', 'CONFIRMADO', 'ANULADO']
TIPOS_MOVIMIENTO = ['INGRESO', 'EGRESO', 'TRANSFERENCIA']
MEDIOS_TESORERIA = ['CAJA', 'BANCO']
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



def _truncate(value, max_len):
    value = value or ''
    return value[:max_len]



def _to_float(value):
    if value is None:
        return None
    return float(Decimal(str(value)))



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



def _normalize_text(value, field_name, max_len, required=False):
    value = _clean(value)
    if required and not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(value) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return value or None



def _usuario_actual():
    return (
        session.get('username')
        or session.get('usuario')
        or session.get('email')
        or session.get('nombre')
        or session.get('user_id')
        or 'sistema'
    )



def _puede_editar():
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except Exception:
        return False



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



def _get_unidad_negocio_info(db, unidad_negocio_id, required=True, active_only=False):
    unidad_negocio_id = _parse_int(unidad_negocio_id, 'Unidad de negocio', required=required)
    if unidad_negocio_id is None:
        return None
    rows = db.execute_query(
        """
        SELECT id, codigo, nombre, COALESCE(nit, '') AS nit, activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_negocio_id,),
    )
    if not rows:
        raise ValueError('La unidad de negocio seleccionada no existe.')
    row = rows[0]
    if active_only and not row['activo']:
        raise ValueError('La unidad de negocio seleccionada está inactiva.')
    return row



def _get_unidades_negocio_rows(db, incluir_inactivas=False):
    filtro = '' if incluir_inactivas else 'WHERE activo = TRUE'
    return db.execute_query(
        f"""
        SELECT id, codigo, nombre, COALESCE(nit, '') AS nit, activo,
               creado_en, actualizado_en
        FROM contabilidad.unidad_negocio
        {filtro}
        ORDER BY activo DESC, nombre, codigo
        """
    )


# ============================================================
# Catálogos y validación de maestros
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



def _get_cuenta_info(db, codigo, field_name='Cuenta contable'):
    codigo = _clean(codigo)
    if not codigo:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')

    tabla = _tabla_cuentas(db)
    rows = db.execute_query(
        f"""
        SELECT codigo, nombre, activo, es_postable
        FROM {tabla}
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,),
    )
    if not rows:
        raise ValueError(f'La cuenta contable "{codigo}" no existe.')
    row = rows[0]
    if not row['activo']:
        raise ValueError(f'La cuenta contable "{codigo}" está inactiva.')
    if not row['es_postable']:
        raise ValueError(f'La cuenta contable "{codigo}" no es postable.')
    return row



def _get_auxiliar_info(db, auxiliar_id, required=False, field_name='Auxiliar'):
    aux_id = _parse_int(auxiliar_id, field_name, required=required)
    if aux_id is None:
        return None
    rows = db.execute_query(
        """
        SELECT id, tipo, nombre, nit_ci, activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (aux_id,),
    )
    if not rows:
        raise ValueError(f'El {field_name.lower()} seleccionado no existe.')
    row = rows[0]
    if not row['activo']:
        raise ValueError(f'El {field_name.lower()} seleccionado está inactivo.')
    return row



def _get_moneda_info(db, codigo, required=True):
    codigo = _clean(codigo).upper()
    if not codigo:
        if required:
            raise ValueError('El campo "Moneda" es obligatorio.')
        return None
    rows = db.execute_query(
        """
        SELECT codigo, nombre, activo
        FROM contabilidad.moneda
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,),
    )
    if not rows:
        raise ValueError(f'La moneda "{codigo}" no existe.')
    row = rows[0]
    if not row['activo']:
        raise ValueError(f'La moneda "{codigo}" está inactiva.')
    return row



def _get_caja_info(db, caja_id, required=True, active_only=False):
    caja_id = _parse_int(caja_id, 'Caja', required=required)
    if caja_id is None:
        return None
    sql = """
        SELECT c.id, c.codigo, c.nombre, c.cuenta_contable_codigo, c.activo,
               NULL::bigint AS unidad_negocio_id,
               cu.nombre AS cuenta_contable_nombre,
               ''::text AS unidad_negocio_codigo,
               'General'::text AS unidad_negocio_nombre
        FROM contabilidad.caja c
        LEFT JOIN {tabla} cu ON cu.codigo = c.cuenta_contable_codigo
        WHERE c.id = %s
        LIMIT 1
    """.format(tabla=_tabla_cuentas(db))
    rows = db.execute_query(sql, (caja_id,))
    if not rows:
        raise ValueError('La caja seleccionada no existe.')
    row = rows[0]
    if active_only and not row['activo']:
        raise ValueError('La caja seleccionada está inactiva.')
    return row



def _get_banco_info(db, banco_id, required=True, active_only=False):
    banco_id = _parse_int(banco_id, 'Cuenta bancaria', required=required)
    if banco_id is None:
        return None
    sql = """
        SELECT b.id, b.auxiliar_id, b.nombre_banco, b.numero_cuenta,
               b.moneda_codigo, b.cuenta_contable_codigo, b.titular, b.activo,
               b.unidad_negocio_id,
               cu.nombre AS cuenta_contable_nombre,
               a.nombre AS auxiliar_nombre,
               un.codigo AS unidad_negocio_codigo,
               un.nombre AS unidad_negocio_nombre
        FROM contabilidad.cuenta_bancaria b
        LEFT JOIN {tabla} cu ON cu.codigo = b.cuenta_contable_codigo
        LEFT JOIN contabilidad.auxiliar a ON a.id = b.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = b.unidad_negocio_id
        WHERE b.id = %s
        LIMIT 1
    """.format(tabla=_tabla_cuentas(db))
    rows = db.execute_query(sql, (banco_id,))
    if not rows:
        raise ValueError('La cuenta bancaria seleccionada no existe.')
    row = rows[0]
    if active_only and not row['activo']:
        raise ValueError('La cuenta bancaria seleccionada está inactiva.')
    return row



def _get_tipo_movimientos_catalog(db):
    return [item for item in _enum_values(db, 'tipo_mov_tesoreria_enum') if item in TIPOS_MOVIMIENTO]



def _get_medios_catalog(db):
    return [item for item in _enum_values(db, 'medio_tesoreria_enum') if item in MEDIOS_TESORERIA]


# ============================================================
# Saldos y consultas consolidadas
# ============================================================

def _get_caja_balance_map(db, fecha_hasta=None, unidad_negocio_id=None):
    cobro_extra = []
    pago_extra = []
    mov_destino_extra = []
    mov_origen_extra = []
    params = []

    if fecha_hasta:
        cobro_extra.append('c.fecha <= %s')
        params.append(fecha_hasta)
        pago_extra.append('p.fecha <= %s')
        params.append(fecha_hasta)
        mov_destino_extra.append('m.fecha <= %s')
        params.append(fecha_hasta)
        mov_origen_extra.append('m.fecha <= %s')
        params.append(fecha_hasta)

    if unidad_negocio_id:
        cobro_extra.append('c.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
        pago_extra.append('p.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
        mov_destino_extra.append('m.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
        mov_origen_extra.append('m.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    where_cobro = ('AND ' + ' AND '.join(cobro_extra)) if cobro_extra else ''
    where_pago = ('AND ' + ' AND '.join(pago_extra)) if pago_extra else ''
    where_mov_destino = ('AND ' + ' AND '.join(mov_destino_extra)) if mov_destino_extra else ''
    where_mov_origen = ('AND ' + ' AND '.join(mov_origen_extra)) if mov_origen_extra else ''

    rows = db.execute_query(
        f"""
        SELECT caja_id, COALESCE(SUM(monto), 0) AS saldo
        FROM (
            SELECT c.caja_id AS caja_id, c.monto_total::numeric AS monto
            FROM contabilidad.cobro c
            WHERE c.estado = 'CONFIRMADO'
              AND c.medio_pago = 'CAJA'
              AND c.caja_id IS NOT NULL
              {where_cobro}

            UNION ALL

            SELECT p.caja_id AS caja_id, (p.monto_total * -1)::numeric AS monto
            FROM contabilidad.pago p
            WHERE p.estado = 'CONFIRMADO'
              AND p.medio_pago = 'CAJA'
              AND p.caja_id IS NOT NULL
              {where_pago}

            UNION ALL

            SELECT m.caja_destino_id AS caja_id, m.monto::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_destino = 'CAJA'
              AND m.caja_destino_id IS NOT NULL
              {where_mov_destino}

            UNION ALL

            SELECT m.caja_origen_id AS caja_id, (m.monto * -1)::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_origen = 'CAJA'
              AND m.caja_origen_id IS NOT NULL
              {where_mov_origen}
        ) s
        GROUP BY caja_id
        """,
        tuple(params),
    )
    return {int(row['caja_id']): Decimal(str(row['saldo'])).quantize(CUANTIA) for row in rows if row['caja_id'] is not None}



def _get_banco_balance_map(db, fecha_hasta=None, unidad_negocio_id=None):
    cobro_extra = []
    pago_extra = []
    mov_destino_extra = []
    mov_origen_extra = []
    params = []

    if fecha_hasta:
        cobro_extra.append('c.fecha <= %s')
        params.append(fecha_hasta)
        pago_extra.append('p.fecha <= %s')
        params.append(fecha_hasta)
        mov_destino_extra.append('m.fecha <= %s')
        params.append(fecha_hasta)
        mov_origen_extra.append('m.fecha <= %s')
        params.append(fecha_hasta)

    if unidad_negocio_id:
        cobro_extra.append('c.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
        pago_extra.append('p.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
        mov_destino_extra.append('m.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
        mov_origen_extra.append('m.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    where_cobro = ('AND ' + ' AND '.join(cobro_extra)) if cobro_extra else ''
    where_pago = ('AND ' + ' AND '.join(pago_extra)) if pago_extra else ''
    where_mov_destino = ('AND ' + ' AND '.join(mov_destino_extra)) if mov_destino_extra else ''
    where_mov_origen = ('AND ' + ' AND '.join(mov_origen_extra)) if mov_origen_extra else ''

    rows = db.execute_query(
        f"""
        SELECT banco_id, COALESCE(SUM(monto), 0) AS saldo
        FROM (
            SELECT c.cuenta_bancaria_id AS banco_id, c.monto_total::numeric AS monto
            FROM contabilidad.cobro c
            WHERE c.estado = 'CONFIRMADO'
              AND c.medio_pago = 'BANCO'
              AND c.cuenta_bancaria_id IS NOT NULL
              {where_cobro}

            UNION ALL

            SELECT p.cuenta_bancaria_id AS banco_id, (p.monto_total * -1)::numeric AS monto
            FROM contabilidad.pago p
            WHERE p.estado = 'CONFIRMADO'
              AND p.medio_pago = 'BANCO'
              AND p.cuenta_bancaria_id IS NOT NULL
              {where_pago}

            UNION ALL

            SELECT m.banco_destino_id AS banco_id, m.monto::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_destino = 'BANCO'
              AND m.banco_destino_id IS NOT NULL
              {where_mov_destino}

            UNION ALL

            SELECT m.banco_origen_id AS banco_id, (m.monto * -1)::numeric AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
              AND m.medio_origen = 'BANCO'
              AND m.banco_origen_id IS NOT NULL
              {where_mov_origen}
        ) s
        GROUP BY banco_id
        """,
        tuple(params),
    )
    return {int(row['banco_id']): Decimal(str(row['saldo'])).quantize(CUANTIA) for row in rows if row['banco_id'] is not None}



def _get_moneda_balance_rows(db):
    rows = db.execute_query(
        """
        SELECT moneda_codigo, COALESCE(SUM(monto), 0) AS saldo
        FROM (
            SELECT c.moneda_codigo, c.monto_total::numeric AS monto
            FROM contabilidad.cobro c
            WHERE c.estado = 'CONFIRMADO'

            UNION ALL

            SELECT p.moneda_codigo, (p.monto_total * -1)::numeric AS monto
            FROM contabilidad.pago p
            WHERE p.estado = 'CONFIRMADO'

            UNION ALL

            SELECT m.moneda_codigo,
                   CASE
                     WHEN m.tipo_movimiento = 'INGRESO' THEN m.monto::numeric
                     WHEN m.tipo_movimiento = 'EGRESO' THEN (m.monto * -1)::numeric
                     ELSE 0::numeric
                   END AS monto
            FROM contabilidad.movimiento_tesoreria m
            WHERE m.estado = 'CONFIRMADO'
        ) s
        GROUP BY moneda_codigo
        ORDER BY moneda_codigo
        """
    )
    return [
        {
            'moneda_codigo': row['moneda_codigo'],
            'saldo': _to_float(Decimal(str(row['saldo'])).quantize(CUANTIA)),
        }
        for row in rows
    ]



def _get_period_totals(db, fecha_desde, fecha_hasta):
    cobros = db.execute_query(
        """
        SELECT COALESCE(SUM(monto_total), 0) AS total
        FROM contabilidad.cobro
        WHERE estado = 'CONFIRMADO'
          AND fecha BETWEEN %s AND %s
        """,
        (fecha_desde, fecha_hasta),
    )[0]['total']

    pagos = db.execute_query(
        """
        SELECT COALESCE(SUM(monto_total), 0) AS total
        FROM contabilidad.pago
        WHERE estado = 'CONFIRMADO'
          AND fecha BETWEEN %s AND %s
        """,
        (fecha_desde, fecha_hasta),
    )[0]['total']

    movimientos = db.execute_query(
        """
        SELECT tipo_movimiento, COALESCE(SUM(monto), 0) AS total
        FROM contabilidad.movimiento_tesoreria
        WHERE estado = 'CONFIRMADO'
          AND fecha BETWEEN %s AND %s
        GROUP BY tipo_movimiento
        """,
        (fecha_desde, fecha_hasta),
    )
    mov_map = {row['tipo_movimiento']: Decimal(str(row['total'])).quantize(CUANTIA) for row in movimientos}

    ingresos = Decimal(str(cobros)).quantize(CUANTIA) + mov_map.get('INGRESO', Decimal('0.00'))
    egresos = Decimal(str(pagos)).quantize(CUANTIA) + mov_map.get('EGRESO', Decimal('0.00'))
    transferencias = mov_map.get('TRANSFERENCIA', Decimal('0.00'))

    return {
        'ingresos': _to_float(ingresos),
        'egresos': _to_float(egresos),
        'transferencias': _to_float(transferencias),
    }



def _get_cajas_rows(db, incluir_inactivas=False, unidad_negocio_id=None):
    balances = _get_caja_balance_map(db, unidad_negocio_id=unidad_negocio_id)
    tabla = _tabla_cuentas(db)
    filtros = []
    params = []
    if not incluir_inactivas:
        filtros.append('c.activo = TRUE')
    where_sql = ('WHERE ' + ' AND '.join(filtros)) if filtros else ''
    rows = db.execute_query(
        f"""
        SELECT c.id, c.codigo, c.nombre, c.cuenta_contable_codigo, c.activo,
               NULL::bigint AS unidad_negocio_id,
               cu.nombre AS cuenta_contable_nombre,
               ''::text AS unidad_negocio_codigo,
               'General'::text AS unidad_negocio_nombre,
               c.creado_en, c.actualizado_en
        FROM contabilidad.caja c
        LEFT JOIN {tabla} cu ON cu.codigo = c.cuenta_contable_codigo
        {where_sql}
        ORDER BY c.activo DESC, c.nombre, c.codigo
        """,
        tuple(params),
    )
    result = []
    for row in rows:
        saldo = balances.get(int(row['id']), Decimal('0.00'))
        row = dict(row)
        row['saldo_actual'] = _to_float(saldo)
        result.append(row)
    return result



def _get_bancos_rows(db, incluir_inactivas=False, unidad_negocio_id=None):
    balances = _get_banco_balance_map(db, unidad_negocio_id=unidad_negocio_id)
    tabla = _tabla_cuentas(db)
    filtros = []
    params = []
    if not incluir_inactivas:
        filtros.append('b.activo = TRUE')
    if unidad_negocio_id:
        filtros.append('b.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)
    where_sql = ('WHERE ' + ' AND '.join(filtros)) if filtros else ''
    rows = db.execute_query(
        f"""
        SELECT b.id, b.auxiliar_id, b.nombre_banco, b.numero_cuenta, b.moneda_codigo,
               b.cuenta_contable_codigo, b.titular, b.activo, b.unidad_negocio_id,
               cu.nombre AS cuenta_contable_nombre,
               a.nombre AS auxiliar_nombre,
               un.codigo AS unidad_negocio_codigo,
               un.nombre AS unidad_negocio_nombre,
               b.creado_en, b.actualizado_en
        FROM contabilidad.cuenta_bancaria b
        LEFT JOIN {tabla} cu ON cu.codigo = b.cuenta_contable_codigo
        LEFT JOIN contabilidad.auxiliar a ON a.id = b.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = b.unidad_negocio_id
        {where_sql}
        ORDER BY b.activo DESC, un.nombre, b.nombre_banco, b.numero_cuenta
        """,
        tuple(params),
    )
    result = []
    for row in rows:
        saldo = balances.get(int(row['id']), Decimal('0.00'))
        row = dict(row)
        row['saldo_actual'] = _to_float(saldo)
        result.append(row)
    return result



def _build_consolidated_movements(db, fecha_desde=None, fecha_hasta=None, unidad_negocio_id=None, limit=600):
    tabla = _tabla_cuentas(db)
    filtros = []
    params = []

    if fecha_desde:
        filtros.append('q.fecha >= %s')
        params.append(fecha_desde)
    if fecha_hasta:
        filtros.append('q.fecha <= %s')
        params.append(fecha_hasta)
    if unidad_negocio_id:
        filtros.append('q.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    where_sql = ('WHERE ' + ' AND '.join(filtros)) if filtros else ''
    params.append(limit)

    rows = db.execute_query(
        f"""
        SELECT * FROM (
            SELECT
                'COBRO'::text AS origen_doc,
                c.id AS id,
                c.fecha AS fecha,
                'INGRESO'::text AS tipo_movimiento,
                NULL::text AS medio_origen,
                NULL::bigint AS caja_origen_id,
                NULL::bigint AS banco_origen_id,
                NULL::text AS origen_nombre,
                c.medio_pago::text AS medio_destino,
                c.caja_id AS caja_destino_id,
                c.cuenta_bancaria_id AS banco_destino_id,
                CASE
                    WHEN c.medio_pago = 'CAJA' THEN cj.codigo || ' · ' || cj.nombre
                    WHEN c.medio_pago = 'BANCO' THEN bk.nombre_banco || ' · ' || bk.numero_cuenta
                    ELSE '—'
                END AS destino_nombre,
                c.cliente_auxiliar_id AS auxiliar_id,
                COALESCE(ax.nombre, '') AS auxiliar_nombre,
                c.contra_cuenta_codigo,
                cu.nombre AS contra_cuenta_nombre,
                c.moneda_codigo,
                c.tipo_cambio,
                c.monto_total AS monto,
                c.referencia,
                c.glosa,
                c.estado::text AS estado,
                c.creado_en,
                c.actualizado_en,
                c.unidad_negocio_id,
                un.codigo AS unidad_negocio_codigo,
                un.nombre AS unidad_negocio_nombre
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.caja cj ON cj.id = c.caja_id
            LEFT JOIN contabilidad.cuenta_bancaria bk ON bk.id = c.cuenta_bancaria_id
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = c.cliente_auxiliar_id
            LEFT JOIN {tabla} cu ON cu.codigo = c.contra_cuenta_codigo
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id

            UNION ALL

            SELECT
                'PAGO'::text AS origen_doc,
                p.id AS id,
                p.fecha AS fecha,
                'EGRESO'::text AS tipo_movimiento,
                p.medio_pago::text AS medio_origen,
                p.caja_id AS caja_origen_id,
                p.cuenta_bancaria_id AS banco_origen_id,
                CASE
                    WHEN p.medio_pago = 'CAJA' THEN cj.codigo || ' · ' || cj.nombre
                    WHEN p.medio_pago = 'BANCO' THEN bk.nombre_banco || ' · ' || bk.numero_cuenta
                    ELSE '—'
                END AS origen_nombre,
                NULL::text AS medio_destino,
                NULL::bigint AS caja_destino_id,
                NULL::bigint AS banco_destino_id,
                NULL::text AS destino_nombre,
                p.proveedor_auxiliar_id AS auxiliar_id,
                COALESCE(ax.nombre, '') AS auxiliar_nombre,
                p.contra_cuenta_codigo,
                cu.nombre AS contra_cuenta_nombre,
                p.moneda_codigo,
                p.tipo_cambio,
                p.monto_total AS monto,
                p.referencia,
                p.glosa,
                p.estado::text AS estado,
                p.creado_en,
                p.actualizado_en,
                p.unidad_negocio_id,
                un.codigo AS unidad_negocio_codigo,
                un.nombre AS unidad_negocio_nombre
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.caja cj ON cj.id = p.caja_id
            LEFT JOIN contabilidad.cuenta_bancaria bk ON bk.id = p.cuenta_bancaria_id
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = p.proveedor_auxiliar_id
            LEFT JOIN {tabla} cu ON cu.codigo = p.contra_cuenta_codigo
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id

            UNION ALL

            SELECT
                'MOVIMIENTO'::text AS origen_doc,
                m.id AS id,
                m.fecha AS fecha,
                m.tipo_movimiento::text AS tipo_movimiento,
                m.medio_origen::text AS medio_origen,
                m.caja_origen_id,
                m.banco_origen_id,
                CASE
                    WHEN m.medio_origen = 'CAJA' THEN cj1.codigo || ' · ' || cj1.nombre
                    WHEN m.medio_origen = 'BANCO' THEN bk1.nombre_banco || ' · ' || bk1.numero_cuenta
                    ELSE '—'
                END AS origen_nombre,
                m.medio_destino::text AS medio_destino,
                m.caja_destino_id,
                m.banco_destino_id,
                CASE
                    WHEN m.medio_destino = 'CAJA' THEN cj2.codigo || ' · ' || cj2.nombre
                    WHEN m.medio_destino = 'BANCO' THEN bk2.nombre_banco || ' · ' || bk2.numero_cuenta
                    ELSE '—'
                END AS destino_nombre,
                m.auxiliar_id,
                COALESCE(ax.nombre, '') AS auxiliar_nombre,
                m.contra_cuenta_codigo,
                cu.nombre AS contra_cuenta_nombre,
                m.moneda_codigo,
                m.tipo_cambio,
                m.monto,
                m.referencia,
                m.glosa,
                m.estado::text AS estado,
                m.creado_en,
                m.actualizado_en,
                m.unidad_negocio_id,
                un.codigo AS unidad_negocio_codigo,
                un.nombre AS unidad_negocio_nombre
            FROM contabilidad.movimiento_tesoreria m
            LEFT JOIN contabilidad.caja cj1 ON cj1.id = m.caja_origen_id
            LEFT JOIN contabilidad.cuenta_bancaria bk1 ON bk1.id = m.banco_origen_id
            LEFT JOIN contabilidad.caja cj2 ON cj2.id = m.caja_destino_id
            LEFT JOIN contabilidad.cuenta_bancaria bk2 ON bk2.id = m.banco_destino_id
            LEFT JOIN contabilidad.auxiliar ax ON ax.id = m.auxiliar_id
            LEFT JOIN {tabla} cu ON cu.codigo = m.contra_cuenta_codigo
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
        ) q
        {where_sql}
        ORDER BY q.fecha DESC, q.id DESC
        LIMIT %s
        """,
        tuple(params),
    )

    result = []
    for row in rows:
        item = dict(row)
        item['monto'] = _to_float(item['monto'])
        item['tipo_cambio'] = _to_float(item['tipo_cambio'])
        if item['origen_doc'] == 'COBRO':
            item['detalle_url'] = url_for('tesoreria_cobros.editar', cobro_id=item['id'])
            item['pdf_url'] = url_for('tesoreria_cobros.pdf', cobro_id=item['id'])
        elif item['origen_doc'] == 'PAGO':
            item['detalle_url'] = url_for('tesoreria_pagos.editar', pago_id=item['id'])
            item['pdf_url'] = url_for('tesoreria_pagos.pdf', pago_id=item['id'])
        else:
            item['detalle_url'] = url_for('tesoreria_caja_bancos.movimiento_edit', movimiento_id=item['id'])
            item['pdf_url'] = url_for('tesoreria_caja_bancos.movimiento_pdf', movimiento_id=item['id'])
        result.append(item)
    return result


def _get_dashboard_context(db, unidad_negocio_id=None):
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    cajas = _get_cajas_rows(db, incluir_inactivas=False, unidad_negocio_id=unidad_negocio_id)
    bancos = _get_bancos_rows(db, incluir_inactivas=False, unidad_negocio_id=unidad_negocio_id)
    movimientos = _build_consolidated_movements(db, unidad_negocio_id=unidad_negocio_id, limit=400)
    resumen_hoy_rows = _build_consolidated_movements(db, fecha_desde=hoy, fecha_hasta=hoy, unidad_negocio_id=unidad_negocio_id, limit=400)
    resumen_mes_rows = _build_consolidated_movements(db, fecha_desde=inicio_mes, fecha_hasta=hoy, unidad_negocio_id=unidad_negocio_id, limit=1000)

    def _sum_tipos(rows):
        out = {'ingresos': Decimal('0.00'), 'egresos': Decimal('0.00'), 'transferencias': Decimal('0.00')}
        for item in rows:
            monto = Decimal(str(item.get('monto') or 0)).quantize(CUANTIA)
            tipo = str(item.get('tipo_movimiento') or '').upper()
            if tipo == 'INGRESO':
                out['ingresos'] += monto
            elif tipo == 'EGRESO':
                out['egresos'] += monto
            elif tipo == 'TRANSFERENCIA':
                out['transferencias'] += monto
        return {k: _to_float(v) for k, v in out.items()}

    moneda_map = {}
    for item in movimientos:
        codigo = item.get('moneda_codigo') or 'BOB'
        moneda_map.setdefault(codigo, Decimal('0.00'))
        tipo = str(item.get('tipo_movimiento') or '').upper()
        monto = Decimal(str(item.get('monto') or 0)).quantize(CUANTIA)
        if tipo == 'INGRESO':
            moneda_map[codigo] += monto
        elif tipo == 'EGRESO':
            moneda_map[codigo] -= monto

    monedas = [
        {'moneda_codigo': codigo, 'saldo': _to_float(valor.quantize(CUANTIA))}
        for codigo, valor in sorted(moneda_map.items())
    ]

    total_cajas = sum(Decimal(str(item['saldo_actual'])) for item in cajas).quantize(CUANTIA) if cajas else Decimal('0.00')
    total_bancos = sum(Decimal(str(item['saldo_actual'])) for item in bancos).quantize(CUANTIA) if bancos else Decimal('0.00')

    return {
        'cajas': cajas,
        'bancos': bancos,
        'monedas': monedas,
        'resumen_hoy': _sum_tipos(resumen_hoy_rows),
        'resumen_mes': _sum_tipos(resumen_mes_rows),
        'movimientos': movimientos[:40],
        'total_cajas': _to_float(total_cajas),
        'total_bancos': _to_float(total_bancos),
    }


# ============================================================
# Lectura de movimiento de tesorería
# ============================================================

def _get_movimiento_header(db, movimiento_id):
    tabla = _tabla_cuentas(db)
    rows = db.execute_query(
        f"""
        SELECT
            m.*,
            ax.nombre AS auxiliar_nombre,
            cu.nombre AS contra_cuenta_nombre,
            cj1.codigo || ' · ' || cj1.nombre AS caja_origen_nombre,
            cj2.codigo || ' · ' || cj2.nombre AS caja_destino_nombre,
            bk1.nombre_banco || ' · ' || bk1.numero_cuenta AS banco_origen_nombre,
            bk2.nombre_banco || ' · ' || bk2.numero_cuenta AS banco_destino_nombre,
            un.codigo AS unidad_negocio_codigo,
            un.nombre AS unidad_negocio_nombre
        FROM contabilidad.movimiento_tesoreria m
        LEFT JOIN contabilidad.auxiliar ax ON ax.id = m.auxiliar_id
        LEFT JOIN {tabla} cu ON cu.codigo = m.contra_cuenta_codigo
        LEFT JOIN contabilidad.caja cj1 ON cj1.id = m.caja_origen_id
        LEFT JOIN contabilidad.caja cj2 ON cj2.id = m.caja_destino_id
        LEFT JOIN contabilidad.cuenta_bancaria bk1 ON bk1.id = m.banco_origen_id
        LEFT JOIN contabilidad.cuenta_bancaria bk2 ON bk2.id = m.banco_destino_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
        WHERE m.id = %s
        LIMIT 1
        """,
        (movimiento_id,),
    )
    if not rows:
        return None
    row = dict(rows[0])
    row['monto'] = _to_float(row['monto'])
    row['tipo_cambio'] = _to_float(row['tipo_cambio'])
    return row



def _get_movimiento_asiento_rows(db, asiento_id):
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


def _movimiento_medio_nombre(movimiento, rol):
    if rol == 'origen':
        medio = movimiento.get('medio_origen') or '-'
        caja = movimiento.get('caja_origen_nombre')
        banco = movimiento.get('banco_origen_nombre')
    else:
        medio = movimiento.get('medio_destino') or '-'
        caja = movimiento.get('caja_destino_nombre')
        banco = movimiento.get('banco_destino_nombre')

    if medio == 'CAJA':
        return caja or 'Caja no especificada'
    if medio == 'BANCO':
        return banco or 'Banco no especificado'
    return '-'


def _movimiento_contra_cuenta_label(movimiento):
    cuenta = movimiento.get('contra_cuenta_codigo') or ''
    nombre = movimiento.get('contra_cuenta_nombre') or ''
    if cuenta and nombre:
        return f'{cuenta} - {nombre}'
    return cuenta or '-'


def _build_movimiento_pdf_bytes(movimiento, asiento_rows):
    fecha = format_date(movimiento.get('fecha'))
    generado = datetime.now().strftime('%d/%m/%Y %H:%M')
    moneda = movimiento.get('moneda_codigo') or 'BOB'
    tipo_cambio = Decimal(str(movimiento.get('tipo_cambio') or 1)).quantize(CUANTIA_TC)
    asiento_label = f"#{movimiento.get('asiento_id')}" if movimiento.get('asiento_id') else 'Sin asiento'

    origen_nombre = _movimiento_medio_nombre(movimiento, 'origen')
    destino_nombre = _movimiento_medio_nombre(movimiento, 'destino')
    cuenta_operativa = _movimiento_contra_cuenta_label(movimiento)
    unidad = f"{movimiento.get('unidad_negocio_codigo') or ''} - {movimiento.get('unidad_negocio_nombre') or ''}".strip(' -')

    sections = [
        {
            'title': 'Identificacion del documento',
            'items': [
                {'label': 'Movimiento', 'value': f"#{movimiento.get('id')}"},
                {'label': 'Fecha de operacion', 'value': fecha},
                {'label': 'Estado', 'value': movimiento.get('estado') or '-'},
                {'label': 'Tipo', 'value': movimiento.get('tipo_movimiento') or '-'},
                {'label': 'Asiento contable', 'value': asiento_label},
                {'label': 'Referencia', 'value': movimiento.get('referencia') or '-'},
            ],
        },
        {
            'title': 'Datos operativos',
            'items': [
                {'label': 'Unidad de negocio', 'value': unidad or '-'},
                {'label': 'Auxiliar', 'value': movimiento.get('auxiliar_nombre') or 'Sin auxiliar'},
                {'label': 'Moneda', 'value': moneda},
                {'label': 'Tipo de cambio', 'value': f'{tipo_cambio}'},
                {'label': 'Medio origen', 'value': movimiento.get('medio_origen') or '-'},
                {'label': 'Origen', 'value': origen_nombre},
                {'label': 'Medio destino', 'value': movimiento.get('medio_destino') or '-'},
                {'label': 'Destino', 'value': destino_nombre},
                {'label': 'Contra cuenta', 'value': cuenta_operativa},
            ],
        },
    ]

    detalle_rows = [[
        '1',
        movimiento.get('tipo_movimiento') or '-',
        origen_nombre,
        destino_nombre,
        movimiento.get('glosa') or '-',
        format_money(movimiento.get('monto')),
    ]]

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
        title='Movimiento de Caja y Bancos',
        subtitle=f'DXT Conta - Tesoreria - Emitido {generado}',
        document_number=f"MOV-TES-{int(movimiento.get('id')):06d}",
        state=movimiento.get('estado') or '',
        sections=sections,
        detail_columns=[
            {'label': '#', 'width': 9, 'align': 'center'},
            {'label': 'Tipo', 'width': 24},
            {'label': 'Origen', 'width': 38},
            {'label': 'Destino', 'width': 38},
            {'label': 'Glosa / concepto', 'width': 45},
            {'label': 'Monto', 'width': 20, 'align': 'right'},
        ],
        detail_rows=detalle_rows,
        totals=[
            {'label': f'Total {moneda}', 'value': format_money(movimiento.get('monto'))},
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
        notes=[{'title': 'Glosa / concepto', 'text': movimiento.get('glosa') or '-'}],
        emitted_by=_usuario_actual(),
        logo_file=logo_path(),
        generated_at=generado,
    )


def _get_movimiento_catalogs(db, movimiento=None, unidad_negocio_id=None):
    medios = _get_medios_catalog(db)
    tipos = _get_tipo_movimientos_catalog(db)
    monedas = db.execute_query(
        """
        SELECT codigo, nombre, COALESCE(simbolo, '') AS simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        ORDER BY codigo
        """
    )
    es_edicion = movimiento is not None
    unidades = _get_unidades_negocio_rows(db, incluir_inactivas=es_edicion)
    effective_unidad = unidad_negocio_id or (movimiento['unidad_negocio_id'] if movimiento else None)
    cajas = _get_cajas_rows(db, incluir_inactivas=es_edicion, unidad_negocio_id=effective_unidad)
    bancos = _get_bancos_rows(db, incluir_inactivas=es_edicion, unidad_negocio_id=effective_unidad)
    return {
        'medios': medios,
        'tipos_movimiento': tipos,
        'monedas': monedas,
        'cajas': cajas,
        'bancos': bancos,
        'unidades_negocio': unidades,
        'tipo_cambio_url_base': url_for('tipo_cambio.gestion'),
        'movimiento_form_url': url_for('tesoreria_caja_bancos.movimiento_create'),
    }

# ============================================================
# Validación y persistencia: cajas / bancos
# ============================================================

def _validate_caja_payload(db, payload):
    caja_id = _parse_int(payload.get('id'), 'Caja', required=False)
    codigo = _normalize_text(payload.get('codigo'), 'Código', 30, required=True)
    nombre = _normalize_text(payload.get('nombre'), 'Nombre', 150, required=True)
    cuenta = _get_cuenta_info(db, payload.get('cuenta_contable_codigo'), 'Cuenta contable de caja')
    activo = bool(payload.get('activo', True))
    return {
        'id': caja_id,
        'codigo': codigo,
        'nombre': nombre,
        'cuenta_contable_codigo': cuenta['codigo'],
        'activo': activo,
    }



def _save_caja(db, payload):
    data = _validate_caja_payload(db, payload)
    if data['id']:
        updated = db.execute_update(
            """
            UPDATE contabilidad.caja
            SET codigo = %s,
                nombre = %s,
                cuenta_contable_codigo = %s,
                activo = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                data['codigo'],
                data['nombre'],
                data['cuenta_contable_codigo'],
                data['activo'],
                data['id'],
            ),
        )
        if not updated:
            raise ValueError('La caja no existe o no pudo ser actualizada.')
        return data['id']

    return db.execute_insert(
        """
        INSERT INTO contabilidad.caja (
            codigo,
            nombre,
            cuenta_contable_codigo,
            activo,
            actualizado_en
        ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            data['codigo'],
            data['nombre'],
            data['cuenta_contable_codigo'],
            data['activo'],
        ),
    )



def _validate_banco_payload(db, payload):
    banco_id = _parse_int(payload.get('id'), 'Cuenta bancaria', required=False)
    unidad = _get_unidad_negocio_info(db, payload.get('unidad_negocio_id'), required=True, active_only=True)
    auxiliar = _get_auxiliar_info(db, payload.get('auxiliar_id'), required=False, field_name='Auxiliar')
    nombre_banco = _normalize_text(payload.get('nombre_banco'), 'Banco', 150, required=True)
    numero_cuenta = _normalize_text(payload.get('numero_cuenta'), 'Número de cuenta', 100, required=True)
    moneda = _get_moneda_info(db, payload.get('moneda_codigo'), required=True)
    cuenta = _get_cuenta_info(db, payload.get('cuenta_contable_codigo'), 'Cuenta contable bancaria')
    titular = _normalize_text(payload.get('titular'), 'Titular', 200, required=False)
    activo = bool(payload.get('activo', True))
    return {
        'id': banco_id,
        'unidad_negocio_id': unidad['id'],
        'auxiliar_id': auxiliar['id'] if auxiliar else None,
        'nombre_banco': nombre_banco,
        'numero_cuenta': numero_cuenta,
        'moneda_codigo': moneda['codigo'],
        'cuenta_contable_codigo': cuenta['codigo'],
        'titular': titular,
        'activo': activo,
    }



def _save_banco(db, payload):
    data = _validate_banco_payload(db, payload)
    if data['id']:
        updated = db.execute_update(
            """
            UPDATE contabilidad.cuenta_bancaria
            SET unidad_negocio_id = %s,
                auxiliar_id = %s,
                nombre_banco = %s,
                numero_cuenta = %s,
                moneda_codigo = %s,
                cuenta_contable_codigo = %s,
                titular = %s,
                activo = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                data['unidad_negocio_id'],
                data['auxiliar_id'],
                data['nombre_banco'],
                data['numero_cuenta'],
                data['moneda_codigo'],
                data['cuenta_contable_codigo'],
                data['titular'],
                data['activo'],
                data['id'],
            ),
        )
        if not updated:
            raise ValueError('La cuenta bancaria no existe o no pudo ser actualizada.')
        return data['id']

    return db.execute_insert(
        """
        INSERT INTO contabilidad.cuenta_bancaria (
            unidad_negocio_id,
            auxiliar_id,
            nombre_banco,
            numero_cuenta,
            moneda_codigo,
            cuenta_contable_codigo,
            titular,
            activo,
            actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            data['unidad_negocio_id'],
            data['auxiliar_id'],
            data['nombre_banco'],
            data['numero_cuenta'],
            data['moneda_codigo'],
            data['cuenta_contable_codigo'],
            data['titular'],
            data['activo'],
        ),
    )


# ============================================================
# Validación y persistencia: movimientos
# ============================================================

def _validate_movement_payload(db, payload, movimiento_actual=None):
    tipo = _clean(payload.get('tipo_movimiento')).upper()
    if tipo not in _get_tipo_movimientos_catalog(db):
        raise ValueError('El tipo de movimiento no es válido.')

    unidad = _get_unidad_negocio_info(db, payload.get('unidad_negocio_id'), required=True, active_only=True)
    fecha = _parse_date(payload.get('fecha'), 'Fecha de operación')
    glosa = _normalize_text(payload.get('glosa'), 'Glosa', 500, required=True)
    referencia = _normalize_text(payload.get('referencia'), 'Referencia', 150, required=False)
    moneda = _get_moneda_info(db, payload.get('moneda_codigo'), required=True)
    monto = _decimal(payload.get('monto'), 'Monto', allow_zero=False)
    auxiliar = _get_auxiliar_info(db, payload.get('auxiliar_id'), required=False, field_name='Auxiliar')

    tc_row = _get_tipo_cambio_row(db, fecha)
    tc_aplicado_default = _resolve_tipo_cambio_aplicado(moneda['codigo'], tc_row)
    tipo_cambio = _decimal(
        payload.get('tipo_cambio') if payload.get('tipo_cambio') not in (None, '') else tc_aplicado_default,
        'Tipo de cambio',
        allow_zero=False,
        quant=CUANTIA_TC,
    )

    medio_origen = _clean(payload.get('medio_origen')).upper() or None
    medio_destino = _clean(payload.get('medio_destino')).upper() or None

    caja_origen = None
    banco_origen = None
    caja_destino = None
    banco_destino = None
    contra_cuenta = None

    if tipo == 'INGRESO':
        if medio_destino not in MEDIOS_TESORERIA:
            raise ValueError('Debes seleccionar el destino del ingreso.')
        if medio_origen:
            raise ValueError('Un ingreso no debe tener origen interno de tesorería.')
        if medio_destino == 'CAJA':
            caja_destino = _get_caja_info(db, payload.get('caja_destino_id'), required=True, active_only=True)
        else:
            banco_destino = _get_banco_info(db, payload.get('banco_destino_id'), required=True, active_only=True)
            if banco_destino['moneda_codigo'] != moneda['codigo']:
                raise ValueError('La moneda del movimiento no coincide con la moneda de la cuenta bancaria destino.')
            if int(banco_destino['unidad_negocio_id'] or 0) != int(unidad['id']):
                raise ValueError('La cuenta bancaria destino no pertenece a la unidad de negocio seleccionada.')
        contra_cuenta = _get_cuenta_info(db, payload.get('contra_cuenta_codigo'), 'Contra cuenta del ingreso')

    elif tipo == 'EGRESO':
        if medio_origen not in MEDIOS_TESORERIA:
            raise ValueError('Debes seleccionar el origen del egreso.')
        if medio_destino:
            raise ValueError('Un egreso no debe tener destino interno de tesorería.')
        if medio_origen == 'CAJA':
            caja_origen = _get_caja_info(db, payload.get('caja_origen_id'), required=True, active_only=True)
        else:
            banco_origen = _get_banco_info(db, payload.get('banco_origen_id'), required=True, active_only=True)
            if banco_origen['moneda_codigo'] != moneda['codigo']:
                raise ValueError('La moneda del movimiento no coincide con la moneda de la cuenta bancaria origen.')
            if int(banco_origen['unidad_negocio_id'] or 0) != int(unidad['id']):
                raise ValueError('La cuenta bancaria origen no pertenece a la unidad de negocio seleccionada.')
        contra_cuenta = _get_cuenta_info(db, payload.get('contra_cuenta_codigo'), 'Contra cuenta del egreso')

    else:  # TRANSFERENCIA
        if medio_origen not in MEDIOS_TESORERIA:
            raise ValueError('Debes seleccionar el origen de la transferencia.')
        if medio_destino not in MEDIOS_TESORERIA:
            raise ValueError('Debes seleccionar el destino de la transferencia.')

        if medio_origen == 'CAJA':
            caja_origen = _get_caja_info(db, payload.get('caja_origen_id'), required=True, active_only=True)
        else:
            banco_origen = _get_banco_info(db, payload.get('banco_origen_id'), required=True, active_only=True)
            if banco_origen['moneda_codigo'] != moneda['codigo']:
                raise ValueError('La moneda del movimiento no coincide con la moneda de la cuenta bancaria origen.')
            if int(banco_origen['unidad_negocio_id'] or 0) != int(unidad['id']):
                raise ValueError('La cuenta bancaria origen no pertenece a la unidad de negocio seleccionada.')

        if medio_destino == 'CAJA':
            caja_destino = _get_caja_info(db, payload.get('caja_destino_id'), required=True, active_only=True)
        else:
            banco_destino = _get_banco_info(db, payload.get('banco_destino_id'), required=True, active_only=True)
            if banco_destino['moneda_codigo'] != moneda['codigo']:
                raise ValueError('La moneda del movimiento no coincide con la moneda de la cuenta bancaria destino.')
            if int(banco_destino['unidad_negocio_id'] or 0) != int(unidad['id']):
                raise ValueError('La cuenta bancaria destino no pertenece a la unidad de negocio seleccionada.')

        if medio_origen == medio_destino:
            if medio_origen == 'CAJA' and caja_origen and caja_destino and int(caja_origen['id']) == int(caja_destino['id']):
                raise ValueError('La transferencia no puede tener la misma caja como origen y destino.')
            if medio_origen == 'BANCO' and banco_origen and banco_destino and int(banco_origen['id']) == int(banco_destino['id']):
                raise ValueError('La transferencia no puede tener la misma cuenta bancaria como origen y destino.')

    return {
        'id': _parse_int(payload.get('id'), 'Movimiento', required=False),
        'unidad_negocio_id': unidad['id'],
        'fecha': fecha,
        'tipo_movimiento': tipo,
        'medio_origen': medio_origen,
        'caja_origen_id': caja_origen['id'] if caja_origen else None,
        'banco_origen_id': banco_origen['id'] if banco_origen else None,
        'medio_destino': medio_destino,
        'caja_destino_id': caja_destino['id'] if caja_destino else None,
        'banco_destino_id': banco_destino['id'] if banco_destino else None,
        'auxiliar_id': auxiliar['id'] if auxiliar else None,
        'contra_cuenta_codigo': contra_cuenta['codigo'] if contra_cuenta else None,
        'moneda_codigo': moneda['codigo'],
        'tipo_cambio': tipo_cambio,
        'monto': monto,
        'referencia': referencia,
        'glosa': glosa,
    }



def _save_movimiento(db, payload):
    movimiento_actual = None
    movimiento_id = _parse_int(payload.get('id'), 'Movimiento', required=False)
    if movimiento_id:
        movimiento_actual = _get_movimiento_header(db, movimiento_id)
        if not movimiento_actual:
            raise ValueError('El movimiento de tesorería no existe.')
        if movimiento_actual['estado'] != 'BORRADOR':
            raise ValueError('Solo se pueden editar movimientos en borrador.')

    data = _validate_movement_payload(db, payload, movimiento_actual=movimiento_actual)

    if data['id']:
        updated = db.execute_update(
            """
            UPDATE contabilidad.movimiento_tesoreria
            SET unidad_negocio_id = %s,
                fecha = %s,
                tipo_movimiento = %s,
                medio_origen = %s,
                caja_origen_id = %s,
                banco_origen_id = %s,
                medio_destino = %s,
                caja_destino_id = %s,
                banco_destino_id = %s,
                auxiliar_id = %s,
                contra_cuenta_codigo = %s,
                moneda_codigo = %s,
                tipo_cambio = %s,
                monto = %s,
                referencia = %s,
                glosa = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
              AND estado = 'BORRADOR'
            """,
            (
                data['unidad_negocio_id'],
                data['fecha'],
                data['tipo_movimiento'],
                data['medio_origen'],
                data['caja_origen_id'],
                data['banco_origen_id'],
                data['medio_destino'],
                data['caja_destino_id'],
                data['banco_destino_id'],
                data['auxiliar_id'],
                data['contra_cuenta_codigo'],
                data['moneda_codigo'],
                data['tipo_cambio'],
                data['monto'],
                data['referencia'],
                data['glosa'],
                data['id'],
            ),
        )
        if not updated:
            raise ValueError('No se pudo actualizar el movimiento de tesorería.')
        return data['id']

    return db.execute_insert(
        """
        INSERT INTO contabilidad.movimiento_tesoreria (
            unidad_negocio_id,
            fecha,
            tipo_movimiento,
            medio_origen,
            caja_origen_id,
            banco_origen_id,
            medio_destino,
            caja_destino_id,
            banco_destino_id,
            auxiliar_id,
            contra_cuenta_codigo,
            moneda_codigo,
            tipo_cambio,
            monto,
            referencia,
            glosa,
            actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            data['unidad_negocio_id'],
            data['fecha'],
            data['tipo_movimiento'],
            data['medio_origen'],
            data['caja_origen_id'],
            data['banco_origen_id'],
            data['medio_destino'],
            data['caja_destino_id'],
            data['banco_destino_id'],
            data['auxiliar_id'],
            data['contra_cuenta_codigo'],
            data['moneda_codigo'],
            data['tipo_cambio'],
            data['monto'],
            data['referencia'],
            data['glosa'],
        ),
    )


# ============================================================
# Asientos automáticos
# ============================================================

def _get_medium_account_info(db, medio, caja_id=None, banco_id=None, role_label='origen'):
    if medio == 'CAJA':
        if not caja_id:
            raise ValueError(f'No se seleccionó caja de {role_label}.')
        caja = _get_caja_info(db, caja_id, required=True, active_only=False)
        return {
            'cuenta_codigo': caja['cuenta_contable_codigo'],
            'nombre': f"Caja {caja['codigo']} · {caja['nombre']}",
        }
    if medio == 'BANCO':
        if not banco_id:
            raise ValueError(f'No se seleccionó cuenta bancaria de {role_label}.')
        banco = _get_banco_info(db, banco_id, required=True, active_only=False)
        return {
            'cuenta_codigo': banco['cuenta_contable_codigo'],
            'nombre': f"{banco['nombre_banco']} · {banco['numero_cuenta']}",
        }
    raise ValueError(f'El medio de tesorería de {role_label} no es válido.')



def _create_asiento_movimiento(db, movimiento):
    total = Decimal(str(movimiento['monto'])).quantize(CUANTIA)
    if total <= 0:
        raise ValueError('El movimiento no tiene un monto válido para contabilizar.')

    asiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            unidad_negocio_id,
            fecha,
            moneda_codigo,
            tipo_cambio,
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado,
            atributos,
            actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, 'TESORERIA', 'contabilidad.movimiento_tesoreria', %s, 'CONFIRMADO', %s::jsonb, CURRENT_TIMESTAMP)
        """,
        (
            movimiento['unidad_negocio_id'],
            movimiento['fecha'],
            movimiento['moneda_codigo'],
            movimiento['tipo_cambio'],
            movimiento['glosa'],
            movimiento['referencia'],
            movimiento['id'],
            '{"origen":"tesoreria_caja_bancos","version":"v1"}',
        ),
    )

    secuencia = 1
    if movimiento['tipo_movimiento'] == 'INGRESO':
        destino = _get_medium_account_info(
            db,
            movimiento['medio_destino'],
            caja_id=movimiento['caja_destino_id'],
            banco_id=movimiento['banco_destino_id'],
            role_label='destino',
        )
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa,
                debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, NULL, %s, %s, 0, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                destino['cuenta_codigo'],
                _truncate(f"Ingreso a {destino['nombre']}", 300),
                total,
                total,
                movimiento['referencia'],
                '{"tipo":"debe_ingreso_tesoreria"}',
            ),
            return_id=False,
        )
        secuencia += 1
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa,
                debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                movimiento['contra_cuenta_codigo'],
                movimiento['auxiliar_id'],
                _truncate(movimiento['glosa'], 300),
                total,
                total,
                movimiento['referencia'],
                '{"tipo":"haber_ingreso_tesoreria"}',
            ),
            return_id=False,
        )

    elif movimiento['tipo_movimiento'] == 'EGRESO':
        origen = _get_medium_account_info(
            db,
            movimiento['medio_origen'],
            caja_id=movimiento['caja_origen_id'],
            banco_id=movimiento['banco_origen_id'],
            role_label='origen',
        )
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa,
                debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                movimiento['contra_cuenta_codigo'],
                movimiento['auxiliar_id'],
                _truncate(movimiento['glosa'], 300),
                total,
                total,
                movimiento['referencia'],
                '{"tipo":"debe_egreso_tesoreria"}',
            ),
            return_id=False,
        )
        secuencia += 1
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa,
                debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, NULL, %s, 0, %s, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                origen['cuenta_codigo'],
                _truncate(f"Salida desde {origen['nombre']}", 300),
                total,
                total,
                movimiento['referencia'],
                '{"tipo":"haber_egreso_tesoreria"}',
            ),
            return_id=False,
        )

    else:  # TRANSFERENCIA
        origen = _get_medium_account_info(
            db,
            movimiento['medio_origen'],
            caja_id=movimiento['caja_origen_id'],
            banco_id=movimiento['banco_origen_id'],
            role_label='origen',
        )
        destino = _get_medium_account_info(
            db,
            movimiento['medio_destino'],
            caja_id=movimiento['caja_destino_id'],
            banco_id=movimiento['banco_destino_id'],
            role_label='destino',
        )
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa,
                debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, NULL, %s, %s, 0, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                destino['cuenta_codigo'],
                _truncate(f"Ingreso por transferencia a {destino['nombre']}", 300),
                total,
                total,
                movimiento['referencia'],
                '{"tipo":"debe_transferencia_tesoreria"}',
            ),
            return_id=False,
        )
        secuencia += 1
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa,
                debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, NULL, %s, 0, %s, %s, %s, %s::jsonb)
            """,
            (
                asiento_id,
                secuencia,
                origen['cuenta_codigo'],
                _truncate(f"Salida por transferencia desde {origen['nombre']}", 300),
                total,
                total,
                movimiento['referencia'],
                '{"tipo":"haber_transferencia_tesoreria"}',
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
        ) VALUES ('TESORERIA', 'contabilidad.movimiento_tesoreria', %s, %s)
        """,
        (movimiento['id'], asiento_id),
        return_id=False,
    )

    return asiento_id


# ============================================================
# Vistas del módulo
# ============================================================

@tesoreria_caja_bancos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def dashboard():
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)
    with DatabaseManager() as db:
        unidades = _get_unidades_negocio_rows(db, incluir_inactivas=True)
        selected_unidad = next((item for item in unidades if int(item['id']) == int(unidad_negocio_id)), None) if unidad_negocio_id else None
        context = _get_dashboard_context(db, unidad_negocio_id=unidad_negocio_id)
        return render_template(
            'caja_bancos_dashboard.html',
            puede_editar=_puede_editar(),
            unidades_negocio=unidades,
            filtro_unidad_negocio_id=unidad_negocio_id,
            unidad_negocio_actual=selected_unidad,
            **context,
        )


@tesoreria_caja_bancos_bp.route('/cajas')
@login_required
@roles_required(ROLES_LECTURA)
def cajas_index():
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)
    with DatabaseManager() as db:
        rows = _get_cajas_rows(db, incluir_inactivas=True, unidad_negocio_id=unidad_negocio_id)
        unidades = _get_unidades_negocio_rows(db, incluir_inactivas=True)
        return render_template(
            'cajas_index.html',
            puede_editar=_puede_editar(),
            rows=rows,
            unidades_negocio=unidades,
            filtro_unidad_negocio_id=unidad_negocio_id,
        )


@tesoreria_caja_bancos_bp.route('/bancos')
@login_required
@roles_required(ROLES_LECTURA)
def bancos_index():
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)
    with DatabaseManager() as db:
        rows = _get_bancos_rows(db, incluir_inactivas=True, unidad_negocio_id=unidad_negocio_id)
        unidades = _get_unidades_negocio_rows(db, incluir_inactivas=True)
        return render_template(
            'bancos_index.html',
            puede_editar=_puede_editar(),
            rows=rows,
            unidades_negocio=unidades,
            filtro_unidad_negocio_id=unidad_negocio_id,
        )


@tesoreria_caja_bancos_bp.route('/movimientos')
@login_required
@roles_required(ROLES_LECTURA)
def movimientos_index():
    fecha_desde = _parse_date(request.args.get('desde'), 'Desde', required=False)
    fecha_hasta = _parse_date(request.args.get('hasta'), 'Hasta', required=False)
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)
    with DatabaseManager() as db:
        rows = _build_consolidated_movements(db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, unidad_negocio_id=unidad_negocio_id, limit=800)
        catalogs = _get_movimiento_catalogs(db, unidad_negocio_id=unidad_negocio_id)
        catalogs['unidades_negocio'] = _get_unidades_negocio_rows(db, incluir_inactivas=True)
        return render_template(
            'movimientos_index.html',
            puede_editar=_puede_editar(),
            rows=rows,
            catalogs=catalogs,
            filtros={
                'desde': fecha_desde.isoformat() if fecha_desde else '',
                'hasta': fecha_hasta.isoformat() if fecha_hasta else '',
                'unidad_negocio_id': unidad_negocio_id or '',
            },
        )


@tesoreria_caja_bancos_bp.route('/movimientos/nuevo')
@login_required
@roles_required(ROLES_LECTURA)
def movimiento_create():
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)
    with DatabaseManager() as db:
        catalogs = _get_movimiento_catalogs(db, unidad_negocio_id=unidad_negocio_id)
        tc = _get_tipo_cambio_row(db, date.today())
        return render_template(
            'movimiento_form.html',
            mode='create',
            puede_editar=_puede_editar(),
            movimiento_data=None,
            catalogs=catalogs,
            tipo_cambio_data={
                'existe': tc['existe'],
                'usd_paralelo': _to_float(tc['usd_paralelo']),
                'ufv': _to_float(tc['ufv']),
            },
            unidad_negocio_id=unidad_negocio_id,
        )


@tesoreria_caja_bancos_bp.route('/movimientos/<int:movimiento_id>/editar')
@login_required
@roles_required(ROLES_LECTURA)
def movimiento_edit(movimiento_id):
    with DatabaseManager() as db:
        movimiento = _get_movimiento_header(db, movimiento_id)
        if not movimiento:
            return render_template('errors/404.html'), 404
        catalogs = _get_movimiento_catalogs(db, movimiento=movimiento, unidad_negocio_id=movimiento.get('unidad_negocio_id'))
        tc = _get_tipo_cambio_row(db, movimiento['fecha'])
        return render_template(
            'movimiento_form.html',
            mode='edit',
            puede_editar=_puede_editar(),
            movimiento_data=movimiento,
            catalogs=catalogs,
            tipo_cambio_data={
                'existe': tc['existe'],
                'usd_paralelo': _to_float(tc['usd_paralelo']),
                'ufv': _to_float(tc['ufv']),
            },
            unidad_negocio_id=movimiento.get('unidad_negocio_id'),
        )


@tesoreria_caja_bancos_bp.route('/movimientos/<int:movimiento_id>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def movimiento_pdf(movimiento_id):
    try:
        with DatabaseManager() as db:
            movimiento = _get_movimiento_header(db, movimiento_id)
            if not movimiento:
                return render_template('errors/404.html'), 404
            asiento_rows = _get_movimiento_asiento_rows(db, movimiento.get('asiento_id'))
            pdf_bytes = _build_movimiento_pdf_bytes(movimiento, asiento_rows)
            fecha_doc = movimiento['fecha'].strftime('%Y%m%d') if movimiento.get('fecha') else datetime.now().strftime('%Y%m%d')
            nombre = f"movimiento_tesoreria_{int(movimiento_id):06d}_{fecha_doc}.pdf"
            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'inline; filename={nombre}'},
            )
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del movimiento de tesorería. {exc}', status=500)


# ============================================================
# APIs auxiliares
# ============================================================

@tesoreria_caja_bancos_bp.route('/api/tipo-cambio/<fecha>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_tipo_cambio_fecha(fecha):
    try:
        fecha_operacion = _parse_date(fecha, 'Fecha')
        moneda = _clean(request.args.get('moneda')).upper() or 'BOB'
        with DatabaseManager() as db:
            tc = _get_tipo_cambio_row(db, fecha_operacion)
            aplicado = _resolve_tipo_cambio_aplicado(moneda, tc)
            return _json_ok(
                fecha=fecha_operacion.isoformat(),
                existe=tc['existe'],
                usd_paralelo=_to_float(tc['usd_paralelo']),
                ufv=_to_float(tc['ufv']),
                tipo_cambio_aplicado=_to_float(aplicado),
                moneda=moneda,
            )
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo consultar el tipo de cambio. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/auxiliares', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_auxiliares():
    q = _clean(request.args.get('q'))
    limit = min(max(int(request.args.get('limit', 25) or 25), 1), 50)
    with DatabaseManager() as db:
        rows = db.execute_query(
            """
            SELECT id, tipo, nombre, COALESCE(nit_ci, '') AS nit_ci
            FROM contabilidad.auxiliar
            WHERE activo = TRUE
              AND (
                    %s = ''
                 OR nombre ILIKE %s
                 OR COALESCE(nit_ci, '') ILIKE %s
                 OR tipo::text ILIKE %s
              )
            ORDER BY nombre
            LIMIT %s
            """,
            (q, f'%{q}%', f'%{q}%', f'%{q}%', limit),
        )
        return _json_ok(data=rows)


@tesoreria_caja_bancos_bp.route('/api/cuentas', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_cuentas():
    q = _clean(request.args.get('q'))
    limit = min(max(int(request.args.get('limit', 40) or 40), 1), 80)
    with DatabaseManager() as db:
        tabla = _tabla_cuentas(db)
        rows = db.execute_query(
            f"""
            SELECT codigo, nombre,
                   (codigo || ' · ' || nombre) AS etiqueta,
                   COALESCE(requiere_auxiliar, FALSE) AS requiere_auxiliar,
                   COALESCE(requiere_cc, FALSE) AS requiere_cc
            FROM {tabla}
            WHERE activo = TRUE
              AND es_postable = TRUE
              AND (
                    %s = ''
                 OR codigo ILIKE %s
                 OR nombre ILIKE %s
              )
            ORDER BY codigo
            LIMIT %s
            """,
            (q, f'%{q}%', f'%{q}%', limit),
        )
        return _json_ok(data=rows)


@tesoreria_caja_bancos_bp.route('/api/unidades-negocio', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_unidades_negocio():
    q = _clean(request.args.get('q'))
    with DatabaseManager() as db:
        rows = db.execute_query(
            """
            SELECT id, codigo, nombre, COALESCE(nit, '') AS nit
            FROM contabilidad.unidad_negocio
            WHERE activo = TRUE
              AND (
                    %s = ''
                 OR codigo ILIKE %s
                 OR nombre ILIKE %s
                 OR COALESCE(nit, '') ILIKE %s
              )
            ORDER BY nombre, codigo
            LIMIT 50
            """,
            (q, f'%{q}%', f'%{q}%', f'%{q}%'),
        )
        return _json_ok(data=rows)


# ============================================================
# APIs de cajas y bancos
# ============================================================

@tesoreria_caja_bancos_bp.route('/api/cajas/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_cajas_lista():
    with DatabaseManager() as db:
        return _json_ok(rows=_get_cajas_rows(db, incluir_inactivas=True, unidad_negocio_id=_parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)))


@tesoreria_caja_bancos_bp.route('/api/cajas/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_cajas_guardar():
    try:
        payload = request.get_json(silent=True) or {}
        with DatabaseManager() as db:
            caja_id = _save_caja(db, payload)
            return _json_ok('Caja guardada correctamente.', caja_id=caja_id)
    except ValueError as exc:
        return _json_error(str(exc))
    except errors.UniqueViolation:
        return _json_error('Ya existe otra caja con ese código.', status=409)
    except Exception as exc:
        return _json_error(f'No se pudo guardar la caja. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/cajas/<int:caja_id>/toggle', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_cajas_toggle(caja_id):
    try:
        with DatabaseManager() as db:
            caja = _get_caja_info(db, caja_id, required=True, active_only=False)
            nuevo_estado = not bool(caja['activo'])
            db.execute_update(
                """
                UPDATE contabilidad.caja
                SET activo = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (nuevo_estado, caja_id),
            )
            return _json_ok('Estado de la caja actualizado correctamente.', caja_id=caja_id, activo=nuevo_estado)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo actualizar la caja. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/bancos/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_bancos_lista():
    with DatabaseManager() as db:
        return _json_ok(rows=_get_bancos_rows(db, incluir_inactivas=True, unidad_negocio_id=_parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)))


@tesoreria_caja_bancos_bp.route('/api/bancos/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_bancos_guardar():
    try:
        payload = request.get_json(silent=True) or {}
        with DatabaseManager() as db:
            banco_id = _save_banco(db, payload)
            return _json_ok('Cuenta bancaria guardada correctamente.', banco_id=banco_id)
    except ValueError as exc:
        return _json_error(str(exc))
    except errors.UniqueViolation:
        return _json_error('Ya existe otra cuenta bancaria con ese número.', status=409)
    except Exception as exc:
        return _json_error(f'No se pudo guardar la cuenta bancaria. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/bancos/<int:banco_id>/toggle', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_bancos_toggle(banco_id):
    try:
        with DatabaseManager() as db:
            banco = _get_banco_info(db, banco_id, required=True, active_only=False)
            nuevo_estado = not bool(banco['activo'])
            db.execute_update(
                """
                UPDATE contabilidad.cuenta_bancaria
                SET activo = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (nuevo_estado, banco_id),
            )
            return _json_ok('Estado de la cuenta bancaria actualizado correctamente.', banco_id=banco_id, activo=nuevo_estado)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo actualizar la cuenta bancaria. {exc}', status=500)


# ============================================================
# APIs de movimientos y dashboard
# ============================================================

@tesoreria_caja_bancos_bp.route('/api/dashboard', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_dashboard():
    try:
        with DatabaseManager() as db:
            context = _get_dashboard_context(db)
            return _json_ok(**context)
    except Exception as exc:
        return _json_error(f'No se pudo cargar el tablero de tesorería. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/movimientos/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_movimientos_lista():
    try:
        fecha_desde = _parse_date(request.args.get('desde'), 'Desde', required=False)
        fecha_hasta = _parse_date(request.args.get('hasta'), 'Hasta', required=False)
        with DatabaseManager() as db:
            rows = _build_consolidated_movements(db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, unidad_negocio_id=_parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False), limit=1000)
            return _json_ok(rows=rows)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo cargar el libro de movimientos. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/movimientos/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_movimientos_guardar():
    try:
        payload = request.get_json(silent=True) or {}
        with DatabaseManager() as db:
            movimiento_id = _save_movimiento(db, payload)
            movimiento = _get_movimiento_header(db, movimiento_id)
            return _json_ok(
                'Movimiento de tesorería guardado correctamente.',
                movimiento_id=movimiento_id,
                tipo_movimiento=movimiento['tipo_movimiento'] if movimiento else None,
                monto=movimiento['monto'] if movimiento else None,
            )
    except ValueError as exc:
        return _json_error(str(exc))
    except errors.ForeignKeyViolation:
        return _json_error('Uno de los datos relacionados ya no existe o fue desactivado.', status=409)
    except Exception as exc:
        return _json_error(f'No se pudo guardar el movimiento de tesorería. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/movimientos/<int:movimiento_id>/confirmar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_movimientos_confirmar(movimiento_id):
    try:
        with DatabaseManager() as db:
            movimiento = _get_movimiento_header(db, movimiento_id)
            if not movimiento:
                raise ValueError('El movimiento de tesorería no existe.')
            if movimiento['estado'] != 'BORRADOR':
                raise ValueError('Solo se pueden confirmar movimientos en borrador.')

            asiento_id = _create_asiento_movimiento(db, movimiento)
            updated = db.execute_update(
                """
                UPDATE contabilidad.movimiento_tesoreria
                SET estado = 'CONFIRMADO',
                    asiento_id = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND estado = 'BORRADOR'
                """,
                (asiento_id, movimiento_id),
            )
            if not updated:
                raise ValueError('No se pudo confirmar el movimiento de tesorería.')

            return _json_ok('Movimiento confirmado correctamente.', movimiento_id=movimiento_id, asiento_id=asiento_id)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo confirmar el movimiento de tesorería. {exc}', status=500)


@tesoreria_caja_bancos_bp.route('/api/movimientos/<int:movimiento_id>/anular', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_movimientos_anular(movimiento_id):
    try:
        with DatabaseManager() as db:
            movimiento = _get_movimiento_header(db, movimiento_id)
            if not movimiento:
                raise ValueError('El movimiento de tesorería no existe.')
            if movimiento['estado'] != 'CONFIRMADO':
                raise ValueError('Solo se pueden anular movimientos confirmados.')

            if movimiento.get('asiento_id'):
                db.execute_update(
                    """
                    UPDATE contabilidad.asiento
                    SET estado = 'ANULADO', actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (movimiento['asiento_id'],),
                )

            db.execute_update(
                """
                UPDATE contabilidad.movimiento_tesoreria
                SET estado = 'ANULADO', actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (movimiento_id,),
            )
            return _json_ok('Movimiento anulado correctamente.', movimiento_id=movimiento_id)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'No se pudo anular el movimiento de tesorería. {exc}', status=500)
