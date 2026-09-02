from flask import render_template, request, jsonify
from utils.db import execute_query, execute_query_one
from utils.decorators import login_required

from modules.auxiliar_cuenta import auxiliar_cuenta_bp


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


def _clean(value):
    return (value or '').strip()


def _upper_clean(value):
    return _clean(value).upper()


def _obtener_auxiliar(auxiliar_id):
    if not auxiliar_id:
        return None

    return execute_query_one(
        """
        SELECT
            id,
            tipo,
            nombre,
            activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,)
    )


def _obtener_cuenta(codigo):
    if not codigo:
        return None

    return execute_query_one(
        """
        SELECT
            codigo,
            nombre,
            activo,
            es_postable,
            requiere_auxiliar
        FROM contabilidad.cuenta
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,)
    )


def _validar_payload(data):
    auxiliar_id = _parse_int(data.get('auxiliar_id'))
    cuenta_codigo = _upper_clean(data.get('cuenta_codigo'))
    activo = _parse_bool(data.get('activo', True))

    if not auxiliar_id:
        return None, 'El auxiliar es obligatorio.'

    auxiliar = _obtener_auxiliar(auxiliar_id)
    if not auxiliar:
        return None, 'El auxiliar seleccionado no existe.'

    if not bool(auxiliar['activo']):
        return None, 'El auxiliar seleccionado está inactivo.'

    if not cuenta_codigo:
        return None, 'La cuenta contable es obligatoria.'

    cuenta = _obtener_cuenta(cuenta_codigo)
    if not cuenta:
        return None, 'La cuenta contable seleccionada no existe.'

    if not bool(cuenta['activo']):
        return None, 'La cuenta contable seleccionada está inactiva.'

    if not bool(cuenta['es_postable']):
        return None, 'La cuenta contable seleccionada no es postable.'

    if not bool(cuenta['requiere_auxiliar']):
        return None, 'Solo se permiten cuentas que requieren auxiliar.'

    payload = {
        'auxiliar_id': auxiliar_id,
        'cuenta_codigo': cuenta_codigo,
        'activo': activo
    }

    return payload, None


@auxiliar_cuenta_bp.route('/')
@login_required
def index():
    return render_template('auxiliar_cuenta_index.html')


@auxiliar_cuenta_bp.route('/data')
@login_required
def data():
    rows = execute_query(
        """
        SELECT
            ac.id,
            ac.auxiliar_id,
            a.tipo AS auxiliar_tipo,
            a.nombre AS auxiliar_nombre,
            ac.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            ac.activo
        FROM contabilidad.auxiliar_cuenta ac
        INNER JOIN contabilidad.auxiliar a
            ON a.id = ac.auxiliar_id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ac.cuenta_codigo
        ORDER BY a.nombre ASC, ac.cuenta_codigo ASC, ac.id ASC
        """,
        fetchall=True
    )

    return jsonify({'data': rows})


@auxiliar_cuenta_bp.route('/obtener/<int:registro_id>')
@login_required
def obtener(registro_id):
    row = execute_query_one(
        """
        SELECT
            ac.id,
            ac.auxiliar_id,
            a.tipo AS auxiliar_tipo,
            a.nombre AS auxiliar_nombre,
            ac.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            ac.activo
        FROM contabilidad.auxiliar_cuenta ac
        INNER JOIN contabilidad.auxiliar a
            ON a.id = ac.auxiliar_id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ac.cuenta_codigo
        WHERE ac.id = %s
        LIMIT 1
        """,
        (registro_id,)
    )

    if not row:
        return jsonify({'ok': False, 'msg': 'La relación auxiliar-cuenta no existe.'}), 404

    row['auxiliar_text'] = f"{row['auxiliar_nombre']} | {row['auxiliar_tipo']}"
    row['cuenta_text'] = f"{row['cuenta_codigo']} | {row['cuenta_nombre']}"

    return jsonify({'ok': True, 'data': row})


@auxiliar_cuenta_bp.route('/auxiliares/buscar')
@login_required
def buscar_auxiliares():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'
    rows = execute_query(
        """
        SELECT
            id,
            tipo,
            nombre,
            COALESCE(codigo_externo, '') AS codigo_externo
        FROM contabilidad.auxiliar
        WHERE activo = TRUE
        AND (
                %s = ''
                OR nombre ILIKE %s
                OR tipo::text ILIKE %s
                OR COALESCE(codigo_externo, '') ILIKE %s
            )
        ORDER BY nombre ASC
        LIMIT 30
        """,
        (q, q_like, q_like, q_like),
        fetchall=True
    )
    results = []
    for r in rows:
        text = f"{r['nombre']} | {r['tipo']}"
        if _clean(r['codigo_externo']):
            text += f" | COD: {r['codigo_externo']}"

        results.append({
            'id': r['id'],
            'text': text,
            'nombre': r['nombre'],
            'tipo': r['tipo']
        })

    return jsonify({'results': results})


@auxiliar_cuenta_bp.route('/cuentas/buscar')
@login_required
def buscar_cuentas():
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
          AND requiere_auxiliar = TRUE
          AND (
                %s = ''
                OR codigo ILIKE %s
                OR nombre ILIKE %s
              )
        ORDER BY codigo ASC
        LIMIT 30
        """,
        (q, q_like, q_like),
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


@auxiliar_cuenta_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    existe = execute_query_one(
        """
        SELECT id
        FROM contabilidad.auxiliar_cuenta
        WHERE auxiliar_id = %s
          AND cuenta_codigo = %s
        LIMIT 1
        """,
        (payload['auxiliar_id'], payload['cuenta_codigo'])
    )
    if existe:
        return jsonify({
            'ok': False,
            'msg': 'Ya existe esta asignación entre auxiliar y cuenta.'
        }), 409

    execute_query(
        """
        INSERT INTO contabilidad.auxiliar_cuenta (
            auxiliar_id,
            cuenta_codigo,
            activo,
            creado_en
        )
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            payload['auxiliar_id'],
            payload['cuenta_codigo'],
            payload['activo']
        )
    )

    return jsonify({'ok': True, 'msg': 'Asignación auxiliar-cuenta creada correctamente.'})


@auxiliar_cuenta_bp.route('/editar/<int:registro_id>', methods=['PUT'])
@login_required
def editar(registro_id):
    actual = execute_query_one(
        """
        SELECT id
        FROM contabilidad.auxiliar_cuenta
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not actual:
        return jsonify({'ok': False, 'msg': 'La relación auxiliar-cuenta no existe.'}), 404

    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    existe = execute_query_one(
        """
        SELECT id
        FROM contabilidad.auxiliar_cuenta
        WHERE auxiliar_id = %s
          AND cuenta_codigo = %s
          AND id <> %s
        LIMIT 1
        """,
        (payload['auxiliar_id'], payload['cuenta_codigo'], registro_id)
    )
    if existe:
        return jsonify({
            'ok': False,
            'msg': 'Ya existe otra asignación con ese auxiliar y esa cuenta.'
        }), 409

    execute_query(
        """
        UPDATE contabilidad.auxiliar_cuenta
        SET
            auxiliar_id = %s,
            cuenta_codigo = %s,
            activo = %s
        WHERE id = %s
        """,
        (
            payload['auxiliar_id'],
            payload['cuenta_codigo'],
            payload['activo'],
            registro_id
        )
    )

    return jsonify({'ok': True, 'msg': 'Asignación auxiliar-cuenta actualizada correctamente.'})


@auxiliar_cuenta_bp.route('/toggle-activo/<int:registro_id>', methods=['POST'])
@login_required
def toggle_activo(registro_id):
    row = execute_query_one(
        """
        SELECT id, activo
        FROM contabilidad.auxiliar_cuenta
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not row:
        return jsonify({'ok': False, 'msg': 'La relación auxiliar-cuenta no existe.'}), 404

    nuevo_estado = not bool(row['activo'])

    execute_query(
        """
        UPDATE contabilidad.auxiliar_cuenta
        SET activo = %s
        WHERE id = %s
        """,
        (nuevo_estado, registro_id)
    )

    return jsonify({
        'ok': True,
        'msg': 'Asignación activada correctamente.' if nuevo_estado else 'Asignación desactivada correctamente.'
    })


@auxiliar_cuenta_bp.route('/eliminar/<int:registro_id>', methods=['DELETE'])
@login_required
def eliminar(registro_id):
    actual = execute_query_one(
        """
        SELECT id
        FROM contabilidad.auxiliar_cuenta
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not actual:
        return jsonify({'ok': False, 'msg': 'La relación auxiliar-cuenta no existe.'}), 404

    execute_query(
        """
        DELETE FROM contabilidad.auxiliar_cuenta
        WHERE id = %s
        """,
        (registro_id,)
    )

    return jsonify({'ok': True, 'msg': 'Asignación eliminada correctamente.'})