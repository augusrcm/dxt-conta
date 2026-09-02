from flask import render_template, request, jsonify
from utils.db import execute_query, execute_query_one
from utils.decorators import login_required

from modules.caja import caja_bp


def _clean(value):
    return (value or '').strip()


def _upper_clean(value):
    return _clean(value).upper()


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'sí', 'on')


def _validar_payload(data):
    codigo = _upper_clean(data.get('codigo'))
    nombre = _clean(data.get('nombre'))
    cuenta_contable_codigo = _upper_clean(data.get('cuenta_contable_codigo'))
    activo = _parse_bool(data.get('activo', True))

    if not codigo:
        return None, 'El código es obligatorio.'

    if not nombre:
        return None, 'El nombre es obligatorio.'

    if not cuenta_contable_codigo:
        return None, 'La cuenta contable es obligatoria.'

    if len(codigo) > 30:
        return None, 'El código no puede exceder 30 caracteres.'

    if len(nombre) > 150:
        return None, 'El nombre no puede exceder 150 caracteres.'

    cuenta = execute_query_one(
        """
        SELECT
            codigo,
            nombre,
            activo,
            es_postable
        FROM contabilidad.cuenta
        WHERE codigo = %s
        LIMIT 1
        """,
        (cuenta_contable_codigo,)
    )

    if not cuenta:
        return None, 'La cuenta contable seleccionada no existe.'

    if not bool(cuenta['activo']):
        return None, 'La cuenta contable seleccionada está inactiva.'

    if not bool(cuenta['es_postable']):
        return None, 'La cuenta contable seleccionada no es postable.'

    payload = {
        'codigo': codigo,
        'nombre': nombre,
        'cuenta_contable_codigo': cuenta_contable_codigo,
        'activo': activo
    }

    return payload, None


@caja_bp.route('/')
@login_required
def index():
    return render_template('caja_index.html')


@caja_bp.route('/data')
@login_required
def data():
    rows = execute_query(
        """
        SELECT
            c.id,
            c.codigo,
            c.nombre,
            c.cuenta_contable_codigo,
            cu.nombre AS cuenta_contable_nombre,
            c.activo
        FROM contabilidad.caja c
        INNER JOIN contabilidad.cuenta cu
            ON cu.codigo = c.cuenta_contable_codigo
        ORDER BY c.codigo ASC, c.id ASC
        """,
        fetchall=True
    )
    return jsonify({'data': rows})


@caja_bp.route('/obtener/<int:registro_id>')
@login_required
def obtener(registro_id):
    row = execute_query_one(
        """
        SELECT
            c.id,
            c.codigo,
            c.nombre,
            c.cuenta_contable_codigo,
            cu.nombre AS cuenta_contable_nombre,
            c.activo
        FROM contabilidad.caja c
        INNER JOIN contabilidad.cuenta cu
            ON cu.codigo = c.cuenta_contable_codigo
        WHERE c.id = %s
        LIMIT 1
        """,
        (registro_id,)
    )

    if not row:
        return jsonify({'ok': False, 'msg': 'La caja no existe.'}), 404

    row['cuenta_contable_text'] = f"{row['cuenta_contable_codigo']} | {row['cuenta_contable_nombre']}"
    return jsonify({'ok': True, 'data': row})


@caja_bp.route('/cuentas/buscar')
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


@caja_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    existe = execute_query_one(
        """
        SELECT id
        FROM contabilidad.caja
        WHERE UPPER(TRIM(codigo)) = UPPER(TRIM(%s))
        LIMIT 1
        """,
        (payload['codigo'],)
    )
    if existe:
        return jsonify({'ok': False, 'msg': f'Ya existe una caja con código "{payload["codigo"]}".'}), 409

    execute_query(
        """
        INSERT INTO contabilidad.caja (
            codigo,
            nombre,
            cuenta_contable_codigo,
            activo,
            actualizado_en
        )
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            payload['codigo'],
            payload['nombre'],
            payload['cuenta_contable_codigo'],
            payload['activo']
        )
    )

    return jsonify({'ok': True, 'msg': 'Caja creada correctamente.'})


@caja_bp.route('/editar/<int:registro_id>', methods=['PUT'])
@login_required
def editar(registro_id):
    actual = execute_query_one(
        """
        SELECT id
        FROM contabilidad.caja
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not actual:
        return jsonify({'ok': False, 'msg': 'La caja no existe.'}), 404

    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    existe = execute_query_one(
        """
        SELECT id
        FROM contabilidad.caja
        WHERE UPPER(TRIM(codigo)) = UPPER(TRIM(%s))
          AND id <> %s
        LIMIT 1
        """,
        (payload['codigo'], registro_id)
    )
    if existe:
        return jsonify({'ok': False, 'msg': f'Ya existe otra caja con código "{payload["codigo"]}".'}), 409

    execute_query(
        """
        UPDATE contabilidad.caja
        SET
            codigo = %s,
            nombre = %s,
            cuenta_contable_codigo = %s,
            activo = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            payload['codigo'],
            payload['nombre'],
            payload['cuenta_contable_codigo'],
            payload['activo'],
            registro_id
        )
    )

    return jsonify({'ok': True, 'msg': 'Caja actualizada correctamente.'})


@caja_bp.route('/toggle-activo/<int:registro_id>', methods=['POST'])
@login_required
def toggle_activo(registro_id):
    row = execute_query_one(
        """
        SELECT id, activo
        FROM contabilidad.caja
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not row:
        return jsonify({'ok': False, 'msg': 'La caja no existe.'}), 404

    nuevo_estado = not bool(row['activo'])

    execute_query(
        """
        UPDATE contabilidad.caja
        SET
            activo = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (nuevo_estado, registro_id)
    )

    return jsonify({
        'ok': True,
        'msg': 'Caja activada correctamente.' if nuevo_estado else 'Caja desactivada correctamente.'
    })