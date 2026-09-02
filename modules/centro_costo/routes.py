from flask import render_template, request, jsonify
from utils.db import execute_query, execute_query_one
from utils.decorators import login_required

from modules.centro_costo import centro_costo_bp


def _clean(value):
    return (value or '').strip()


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'sí', 'on')


@centro_costo_bp.route('/')
@login_required
def index():
    return render_template('centro_costo_index.html')


@centro_costo_bp.route('/data')
@login_required
def data():
    rows = execute_query(
        """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(descripcion, '') AS descripcion,
            activo
        FROM contabilidad.centro_costo
        ORDER BY codigo ASC
        """,
        fetchall=True
    )

    return jsonify({'data': rows})


@centro_costo_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    d = request.get_json() or {}

    codigo = _clean(d.get('codigo')).upper()
    nombre = _clean(d.get('nombre'))
    descripcion = _clean(d.get('descripcion'))
    activo = _parse_bool(d.get('activo', True))

    if not codigo:
        return jsonify({'ok': False, 'msg': 'El código es obligatorio.'}), 400

    if not nombre:
        return jsonify({'ok': False, 'msg': 'El nombre es obligatorio.'}), 400

    if len(codigo) > 30:
        return jsonify({'ok': False, 'msg': 'El código no puede exceder 30 caracteres.'}), 400

    if len(nombre) > 150:
        return jsonify({'ok': False, 'msg': 'El nombre no puede exceder 150 caracteres.'}), 400

    existe = execute_query_one(
        """
        SELECT 1
        FROM contabilidad.centro_costo
        WHERE UPPER(codigo) = %s
        LIMIT 1
        """,
        (codigo,)
    )
    if existe:
        return jsonify({'ok': False, 'msg': f'Ya existe un centro de costo con código "{codigo}".'}), 409

    execute_query(
        """
        INSERT INTO contabilidad.centro_costo (
            codigo,
            nombre,
            descripcion,
            activo,
            actualizado_en
        )
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (codigo, nombre, descripcion or None, activo)
    )

    return jsonify({'ok': True, 'msg': 'Centro de costo creado correctamente.'})


@centro_costo_bp.route('/editar/<int:registro_id>', methods=['PUT'])
@login_required
def editar(registro_id):
    row = execute_query_one(
        """
        SELECT id, codigo, nombre, descripcion, activo
        FROM contabilidad.centro_costo
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not row:
        return jsonify({'ok': False, 'msg': 'El centro de costo no existe.'}), 404

    d = request.get_json() or {}

    codigo = _clean(d.get('codigo')).upper()
    nombre = _clean(d.get('nombre'))
    descripcion = _clean(d.get('descripcion'))
    activo = _parse_bool(d.get('activo', True))

    if not codigo:
        return jsonify({'ok': False, 'msg': 'El código es obligatorio.'}), 400

    if not nombre:
        return jsonify({'ok': False, 'msg': 'El nombre es obligatorio.'}), 400

    if len(codigo) > 30:
        return jsonify({'ok': False, 'msg': 'El código no puede exceder 30 caracteres.'}), 400

    if len(nombre) > 150:
        return jsonify({'ok': False, 'msg': 'El nombre no puede exceder 150 caracteres.'}), 400

    existe = execute_query_one(
        """
        SELECT 1
        FROM contabilidad.centro_costo
        WHERE UPPER(codigo) = %s
          AND id <> %s
        LIMIT 1
        """,
        (codigo, registro_id)
    )
    if existe:
        return jsonify({'ok': False, 'msg': f'Ya existe otro centro de costo con código "{codigo}".'}), 409

    execute_query(
        """
        UPDATE contabilidad.centro_costo
        SET
            codigo = %s,
            nombre = %s,
            descripcion = %s,
            activo = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (codigo, nombre, descripcion or None, activo, registro_id)
    )

    return jsonify({'ok': True, 'msg': 'Centro de costo actualizado correctamente.'})


@centro_costo_bp.route('/eliminar/<int:registro_id>', methods=['DELETE'])
@login_required
def eliminar(registro_id):
    row = execute_query_one(
        """
        SELECT id, codigo
        FROM contabilidad.centro_costo
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not row:
        return jsonify({'ok': False, 'msg': 'El centro de costo no existe.'}), 404

    en_uso = execute_query_one(
        """
        SELECT 1
        FROM (
            SELECT 1 FROM contabilidad.asiento_detalle WHERE centro_costo_id = %s
            UNION ALL
            SELECT 1 FROM contabilidad.compra_detalle WHERE centro_costo_id = %s
            UNION ALL
            SELECT 1 FROM contabilidad.venta_detalle WHERE centro_costo_id = %s
        ) t
        LIMIT 1
        """,
        (registro_id, registro_id, registro_id)
    )

    if en_uso:
        return jsonify({
            'ok': False,
            'msg': 'No se puede eliminar el centro de costo porque está siendo utilizado en otros registros.'
        }), 409

    execute_query(
        "DELETE FROM contabilidad.centro_costo WHERE id = %s",
        (registro_id,)
    )

    return jsonify({'ok': True, 'msg': 'Centro de costo eliminado correctamente.'})