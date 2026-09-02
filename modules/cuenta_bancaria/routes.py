from flask import render_template, request, jsonify
from utils.db import execute_query, execute_query_one
from utils.decorators import login_required

from modules.cuenta_bancaria import cuenta_bancaria_bp


CUENTA_BANCOS_RAIZ = '1.1.1.002'


def _clean(value):
    return (value or '').strip()


def _upper_clean(value):
    return _clean(value).upper()


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'sí', 'on')


def _parse_int(value):
    try:
        if value in (None, '', 'null'):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _obtener_unidad_negocio(unidad_negocio_id):
    if not unidad_negocio_id:
        return None

    return execute_query_one(
        """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(nit, '') AS nit,
            activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_negocio_id,)
    )


def _obtener_auxiliar_banco(auxiliar_id):
    if not auxiliar_id:
        return None

    return execute_query_one(
        """
        SELECT
            id,
            tipo,
            nombre,
            COALESCE(codigo_externo, '') AS codigo_externo,
            activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,)
    )


def _obtener_moneda(moneda_codigo):
    if not moneda_codigo:
        return None

    return execute_query_one(
        """
        SELECT
            codigo,
            nombre,
            simbolo,
            activo
        FROM contabilidad.moneda
        WHERE codigo = %s
        LIMIT 1
        """,
        (moneda_codigo,)
    )


def _obtener_cuenta_bancaria_contable(codigo):
    if not codigo:
        return None

    return execute_query_one(
        """
        SELECT
            codigo,
            nombre,
            activo,
            es_postable
        FROM contabilidad.cuenta
        WHERE codigo = %s
          AND activo = TRUE
          AND es_postable = TRUE
          AND (
                codigo = %s
                OR codigo LIKE %s
              )
        LIMIT 1
        """,
        (codigo, CUENTA_BANCOS_RAIZ, f'{CUENTA_BANCOS_RAIZ}.%')
    )


def _validar_payload(data):
    unidad_negocio_id = _parse_int(data.get('unidad_negocio_id'))
    auxiliar_id = _parse_int(data.get('auxiliar_id'))
    nombre_banco = _clean(data.get('nombre_banco'))
    numero_cuenta = _clean(data.get('numero_cuenta'))
    moneda_codigo = _upper_clean(data.get('moneda_codigo'))
    cuenta_contable_codigo = _upper_clean(data.get('cuenta_contable_codigo'))
    titular = _clean(data.get('titular'))
    activo = _parse_bool(data.get('activo', True))

    if not unidad_negocio_id:
        return None, 'La unidad de negocio es obligatoria.'

    unidad = _obtener_unidad_negocio(unidad_negocio_id)
    if not unidad:
        return None, 'La unidad de negocio seleccionada no existe.'

    if not bool(unidad['activo']):
        return None, 'La unidad de negocio seleccionada está inactiva.'

    if not auxiliar_id:
        return None, 'El banco auxiliar es obligatorio.'

    auxiliar = _obtener_auxiliar_banco(auxiliar_id)
    if not auxiliar:
        return None, 'El auxiliar seleccionado no existe.'

    if auxiliar['tipo'] != 'BANCO':
        return None, 'Solo se permiten auxiliares de tipo BANCO.'

    if not bool(auxiliar['activo']):
        return None, 'El auxiliar banco seleccionado está inactivo.'

    if not nombre_banco:
        return None, 'El nombre del banco es obligatorio.'

    if not numero_cuenta:
        return None, 'El número de cuenta es obligatorio.'

    if not moneda_codigo:
        return None, 'La moneda es obligatoria.'

    moneda = _obtener_moneda(moneda_codigo)
    if not moneda:
        return None, 'La moneda seleccionada no existe.'

    if not bool(moneda['activo']):
        return None, 'La moneda seleccionada está inactiva.'

    if not cuenta_contable_codigo:
        return None, 'La cuenta contable es obligatoria.'

    cuenta = _obtener_cuenta_bancaria_contable(cuenta_contable_codigo)
    if not cuenta:
        return None, 'La cuenta contable debe ser una cuenta bancaria activa y postable.'

    if len(nombre_banco) > 150:
        return None, 'El nombre del banco no puede exceder 150 caracteres.'

    if len(numero_cuenta) > 100:
        return None, 'El número de cuenta no puede exceder 100 caracteres.'

    if len(titular) > 200:
        return None, 'El titular no puede exceder 200 caracteres.'

    payload = {
        'unidad_negocio_id': unidad_negocio_id,
        'auxiliar_id': auxiliar_id,
        'nombre_banco': nombre_banco,
        'numero_cuenta': numero_cuenta,
        'moneda_codigo': moneda_codigo,
        'cuenta_contable_codigo': cuenta_contable_codigo,
        'titular': titular or None,
        'activo': activo
    }

    return payload, None


@cuenta_bancaria_bp.route('/')
@login_required
def index():
    return render_template('cuenta_bancaria_index.html')


@cuenta_bancaria_bp.route('/data')
@login_required
def data():
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'))

    filtros = []
    params = []

    if unidad_negocio_id:
        filtros.append('cb.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    where_sql = ''
    if filtros:
        where_sql = 'WHERE ' + ' AND '.join(filtros)

    rows = execute_query(
        f"""
        SELECT
            cb.id,
            cb.unidad_negocio_id,
            un.codigo AS unidad_negocio_codigo,
            un.nombre AS unidad_negocio_nombre,
            COALESCE(un.nit, '') AS unidad_negocio_nit,
            cb.auxiliar_id,
            cb.nombre_banco,
            cb.numero_cuenta,
            cb.moneda_codigo,
            m.nombre AS moneda_nombre,
            cb.cuenta_contable_codigo,
            c.nombre AS cuenta_contable_nombre,
            COALESCE(cb.titular, '') AS titular,
            cb.activo,
            a.nombre AS auxiliar_nombre
        FROM contabilidad.cuenta_bancaria cb
        INNER JOIN contabilidad.unidad_negocio un
            ON un.id = cb.unidad_negocio_id
        INNER JOIN contabilidad.auxiliar a
            ON a.id = cb.auxiliar_id
        INNER JOIN contabilidad.moneda m
            ON m.codigo = cb.moneda_codigo
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = cb.cuenta_contable_codigo
        {where_sql}
        ORDER BY un.nombre ASC, cb.nombre_banco ASC, cb.numero_cuenta ASC, cb.id ASC
        """,
        tuple(params),
        fetchall=True
    )
    return jsonify({'data': rows})


@cuenta_bancaria_bp.route('/obtener/<int:registro_id>')
@login_required
def obtener(registro_id):
    row = execute_query_one(
        """
        SELECT
            cb.id,
            cb.unidad_negocio_id,
            un.codigo AS unidad_negocio_codigo,
            un.nombre AS unidad_negocio_nombre,
            COALESCE(un.nit, '') AS unidad_negocio_nit,
            cb.auxiliar_id,
            cb.nombre_banco,
            cb.numero_cuenta,
            cb.moneda_codigo,
            m.nombre AS moneda_nombre,
            cb.cuenta_contable_codigo,
            c.nombre AS cuenta_contable_nombre,
            COALESCE(cb.titular, '') AS titular,
            cb.activo,
            a.nombre AS auxiliar_nombre
        FROM contabilidad.cuenta_bancaria cb
        INNER JOIN contabilidad.unidad_negocio un
            ON un.id = cb.unidad_negocio_id
        INNER JOIN contabilidad.auxiliar a
            ON a.id = cb.auxiliar_id
        INNER JOIN contabilidad.moneda m
            ON m.codigo = cb.moneda_codigo
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = cb.cuenta_contable_codigo
        WHERE cb.id = %s
        LIMIT 1
        """,
        (registro_id,)
    )

    if not row:
        return jsonify({'ok': False, 'msg': 'La cuenta bancaria no existe.'}), 404

    row['unidad_negocio_text'] = f"{row['unidad_negocio_codigo']} | {row['unidad_negocio_nombre']}"
    row['auxiliar_text'] = row['auxiliar_nombre']
    row['cuenta_contable_text'] = f"{row['cuenta_contable_codigo']} | {row['cuenta_contable_nombre']}"
    row['moneda_text'] = f"{row['moneda_codigo']} | {row['moneda_nombre']}"

    return jsonify({'ok': True, 'data': row})


@cuenta_bancaria_bp.route('/unidades-negocio/buscar')
@login_required
def buscar_unidades_negocio():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'

    rows = execute_query(
        """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(nit, '') AS nit
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
          AND (
                %s = ''
                OR codigo ILIKE %s
                OR nombre ILIKE %s
                OR COALESCE(nit, '') ILIKE %s
              )
        ORDER BY nombre ASC, codigo ASC
        LIMIT 30
        """,
        (q, q_like, q_like, q_like),
        fetchall=True
    )

    results = []
    for r in rows:
        text = f"{r['codigo']} | {r['nombre']}"
        if _clean(r['nit']):
            text += f" | NIT: {r['nit']}"

        results.append({
            'id': r['id'],
            'text': text,
            'codigo': r['codigo'],
            'nombre': r['nombre'],
            'nit': r['nit']
        })

    return jsonify({'results': results})


@cuenta_bancaria_bp.route('/auxiliares-banco/buscar')
@login_required
def buscar_auxiliares_banco():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'

    rows = execute_query(
        """
        SELECT
            id,
            nombre,
            COALESCE(codigo_externo, '') AS codigo_externo,
            COALESCE(razon_social, '') AS razon_social,
            COALESCE(nit_ci, '') AS nit_ci
        FROM contabilidad.auxiliar
        WHERE tipo = 'BANCO'
          AND activo = TRUE
          AND (
                %s = ''
                OR nombre ILIKE %s
                OR COALESCE(codigo_externo, '') ILIKE %s
                OR COALESCE(razon_social, '') ILIKE %s
                OR COALESCE(nit_ci, '') ILIKE %s
              )
        ORDER BY nombre ASC, razon_social ASC, id ASC
        LIMIT 30
        """,
        (q, q_like, q_like, q_like, q_like),
        fetchall=True
    )

    results = []
    for r in rows:
        text = r['nombre']
        if _clean(r['razon_social']):
            text += f" | {r['razon_social']}"
        if _clean(r['nit_ci']):
            text += f" | NIT: {r['nit_ci']}"
        if _clean(r['codigo_externo']):
            text += f" | COD: {r['codigo_externo']}"

        results.append({
            'id': r['id'],
            'text': text,
            'nombre': r['nombre'],
            'razon_social': r['razon_social'],
            'nit_ci': r['nit_ci']
        })

    return jsonify({'results': results})


@cuenta_bancaria_bp.route('/cuentas-banco/buscar')
@login_required
def buscar_cuentas_banco():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'

    rows = execute_query(
        """
        SELECT
            codigo,
            nombre
        FROM contabilidad.cuenta
        WHERE activo = TRUE
          AND es_postable = TRUE
          AND (
                codigo = %s
                OR codigo LIKE %s
              )
          AND (
                %s = ''
                OR codigo ILIKE %s
                OR nombre ILIKE %s
              )
        ORDER BY codigo ASC
        LIMIT 30
        """,
        (CUENTA_BANCOS_RAIZ, f'{CUENTA_BANCOS_RAIZ}.%', q, q_like, q_like),
        fetchall=True
    )

    results = []
    for r in rows:
        results.append({
            'id': r['codigo'],
            'text': f"{r['codigo']} | {r['nombre']}",
            'codigo': r['codigo'],
            'nombre': r['nombre']
        })

    return jsonify({'results': results})


@cuenta_bancaria_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    existe = execute_query_one(
        """
        SELECT id
        FROM contabilidad.cuenta_bancaria
        WHERE UPPER(TRIM(numero_cuenta)) = UPPER(TRIM(%s))
        LIMIT 1
        """,
        (payload['numero_cuenta'],)
    )
    if existe:
        return jsonify({'ok': False, 'msg': 'Ya existe una cuenta bancaria con ese número de cuenta.'}), 409

    execute_query(
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
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            payload['unidad_negocio_id'],
            payload['auxiliar_id'],
            payload['nombre_banco'],
            payload['numero_cuenta'],
            payload['moneda_codigo'],
            payload['cuenta_contable_codigo'],
            payload['titular'],
            payload['activo']
        )
    )

    return jsonify({'ok': True, 'msg': 'Cuenta bancaria creada correctamente.'})


@cuenta_bancaria_bp.route('/editar/<int:registro_id>', methods=['PUT'])
@login_required
def editar(registro_id):
    actual = execute_query_one(
        """
        SELECT id
        FROM contabilidad.cuenta_bancaria
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not actual:
        return jsonify({'ok': False, 'msg': 'La cuenta bancaria no existe.'}), 404

    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    existe = execute_query_one(
        """
        SELECT id
        FROM contabilidad.cuenta_bancaria
        WHERE UPPER(TRIM(numero_cuenta)) = UPPER(TRIM(%s))
          AND id <> %s
        LIMIT 1
        """,
        (payload['numero_cuenta'], registro_id)
    )
    if existe:
        return jsonify({'ok': False, 'msg': 'Ya existe otra cuenta bancaria con ese número de cuenta.'}), 409

    execute_query(
        """
        UPDATE contabilidad.cuenta_bancaria
        SET
            unidad_negocio_id = %s,
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
            payload['unidad_negocio_id'],
            payload['auxiliar_id'],
            payload['nombre_banco'],
            payload['numero_cuenta'],
            payload['moneda_codigo'],
            payload['cuenta_contable_codigo'],
            payload['titular'],
            payload['activo'],
            registro_id
        )
    )

    return jsonify({'ok': True, 'msg': 'Cuenta bancaria actualizada correctamente.'})


@cuenta_bancaria_bp.route('/toggle-activo/<int:registro_id>', methods=['POST'])
@login_required
def toggle_activo(registro_id):
    row = execute_query_one(
        """
        SELECT id, activo
        FROM contabilidad.cuenta_bancaria
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not row:
        return jsonify({'ok': False, 'msg': 'La cuenta bancaria no existe.'}), 404

    nuevo_estado = not bool(row['activo'])

    execute_query(
        """
        UPDATE contabilidad.cuenta_bancaria
        SET
            activo = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (nuevo_estado, registro_id)
    )

    return jsonify({
        'ok': True,
        'msg': 'Cuenta bancaria activada correctamente.' if nuevo_estado else 'Cuenta bancaria desactivada correctamente.'
    })
