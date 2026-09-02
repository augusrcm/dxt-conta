from flask import render_template, request, jsonify
from utils.db import execute_query, execute_query_one
from utils.decorators import login_required

from modules.auxiliar import auxiliar_bp


TIPOS_AUXILIAR = {'CLIENTE', 'PROVEEDOR', 'FUNCIONARIO', 'BANCO', 'OTRO'}
ORIGEN_CLIENTE_EMPRESA = 'clientes.empresas'


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


def _obtener_empresa_cliente(empresa_id):
    if not empresa_id:
        return None

    return execute_query_one(
        """
        SELECT
            id,
            nombre,
            COALESCE(nit, '') AS nit,
            COALESCE(razon_social, '') AS razon_social,
            COALESCE(direccion, '') AS direccion,
            COALESCE(telefono, '') AS telefono,
            COALESCE(email, '') AS email,
            TRIM(UPPER(COALESCE(estado, ''))) AS estado
        FROM clientes.empresas
        WHERE id = %s
        LIMIT 1
        """,
        (empresa_id,)
    )


def _validar_payload(data):
    tipo = _upper_clean(data.get('tipo'))
    codigo_externo = _clean(data.get('codigo_externo'))
    nit_ci = _clean(data.get('nit_ci'))
    nombre = _clean(data.get('nombre'))
    razon_social = _clean(data.get('razon_social'))
    telefono = _clean(data.get('telefono'))
    email = _clean(data.get('email'))
    direccion = _clean(data.get('direccion'))
    observaciones = _clean(data.get('observaciones'))
    es_ocasional = _parse_bool(data.get('es_ocasional', False))
    activo = _parse_bool(data.get('activo', True))

    cliente_referenciado = _parse_bool(data.get('cliente_referenciado', False))
    empresa_id = _parse_int(data.get('empresa_id'))

    if tipo not in TIPOS_AUXILIAR:
        return None, 'El tipo de auxiliar es inválido.'

    if tipo == 'CLIENTE' and cliente_referenciado:
        if not empresa_id:
            return None, 'Debes seleccionar una empresa para referenciar el cliente.'

        empresa = _obtener_empresa_cliente(empresa_id)
        if not empresa:
            return None, 'La empresa seleccionada no existe.'
        if empresa['estado'] != 'ACTIVO':
            return None, 'Solo se puede enlazar empresas activas.'

        nit_empresa = _clean(empresa.get('nit'))
        nombre_empresa = _clean(empresa.get('nombre'))
        razon_social_empresa = _clean(empresa.get('razon_social'))
        telefono_empresa = _clean(empresa.get('telefono'))
        email_empresa = _clean(empresa.get('email'))
        direccion_empresa = _clean(empresa.get('direccion'))

        if not nombre_empresa:
            return None, 'La empresa seleccionada no tiene nombre válido.'

        payload = {
            'tipo': 'CLIENTE',
            'cliente_referenciado': True,
            'empresa_id': empresa['id'],
            'origen_tabla': ORIGEN_CLIENTE_EMPRESA,
            'ref_id': empresa['id'],
            'codigo_externo': nit_empresa or str(empresa['id']),
            'nit_ci': nit_empresa or None,
            'nombre': nombre_empresa,
            'razon_social': razon_social_empresa or None,
            'telefono': telefono_empresa or None,
            'email': email_empresa or None,
            'direccion': direccion_empresa or None,
            'es_ocasional': es_ocasional,
            'activo': activo,
            'observaciones': observaciones or None
        }
        return payload, None

    if not nombre:
        return None, 'El nombre es obligatorio.'

    if len(codigo_externo) > 100:
        return None, 'El código externo no puede exceder 100 caracteres.'

    if len(nit_ci) > 50:
        return None, 'El NIT/CI no puede exceder 50 caracteres.'

    if len(nombre) > 200:
        return None, 'El nombre no puede exceder 200 caracteres.'

    if len(razon_social) > 200:
        return None, 'La razón social no puede exceder 200 caracteres.'

    if len(telefono) > 50:
        return None, 'El teléfono no puede exceder 50 caracteres.'

    if len(email) > 120:
        return None, 'El email no puede exceder 120 caracteres.'

    if len(direccion) > 250:
        return None, 'La dirección no puede exceder 250 caracteres.'

    payload = {
        'tipo': tipo,
        'cliente_referenciado': False,
        'empresa_id': None,
        'origen_tabla': None,
        'ref_id': None,
        'codigo_externo': codigo_externo or None,
        'nit_ci': nit_ci or None,
        'nombre': nombre,
        'razon_social': razon_social or None,
        'telefono': telefono or None,
        'email': email or None,
        'direccion': direccion or None,
        'es_ocasional': es_ocasional,
        'activo': activo,
        'observaciones': observaciones or None
    }

    return payload, None


def _buscar_duplicado(payload, exclude_id=None):
    params = []
    sql = ""

    if payload['tipo'] == 'CLIENTE' and payload['cliente_referenciado'] and payload['ref_id']:
        sql = """
            SELECT id
            FROM contabilidad.auxiliar
            WHERE tipo = 'CLIENTE'
              AND origen_tabla = %s
              AND ref_id = %s
        """
        params = [payload['origen_tabla'], payload['ref_id']]
    else:
        tipo = payload['tipo']
        nombre = payload['nombre']
        nit_ci = payload['nit_ci']

        params = [tipo, nombre]
        sql = """
            SELECT id
            FROM contabilidad.auxiliar
            WHERE tipo = %s
              AND UPPER(TRIM(nombre)) = UPPER(TRIM(%s))
        """

        if nit_ci:
            sql += " AND UPPER(TRIM(COALESCE(nit_ci, ''))) = UPPER(TRIM(%s))"
            params.append(nit_ci)
        else:
            sql += " AND COALESCE(TRIM(nit_ci), '') = ''"

    if exclude_id is not None:
        sql += " AND id <> %s"
        params.append(exclude_id)

    sql += " LIMIT 1"

    return execute_query_one(sql, tuple(params))


@auxiliar_bp.route('/')
@login_required
def index():
    return render_template('auxiliar_index.html')


@auxiliar_bp.route('/data')
@login_required
def data():
    rows = execute_query(
        """
        SELECT
            a.id,
            a.tipo,
            COALESCE(a.codigo_externo, '') AS codigo_externo,
            COALESCE(a.nit_ci, '') AS nit_ci,
            a.nombre,
            COALESCE(a.razon_social, '') AS razon_social,
            a.es_ocasional,
            a.activo,
            COALESCE(a.telefono, '') AS telefono,
            COALESCE(a.email, '') AS email,
            COALESCE(a.direccion, '') AS direccion,
            COALESCE(a.observaciones, '') AS observaciones,
            COALESCE(a.origen_tabla, '') AS origen_tabla,
            a.ref_id,
            CASE
                WHEN a.tipo = 'CLIENTE' AND a.origen_tabla = %s AND a.ref_id IS NOT NULL
                THEN TRUE
                ELSE FALSE
            END AS cliente_referenciado
        FROM contabilidad.auxiliar a
        ORDER BY a.tipo ASC, a.nombre ASC, a.id ASC
        """,
        (ORIGEN_CLIENTE_EMPRESA,),
        fetchall=True
    )
    return jsonify({'data': rows})


@auxiliar_bp.route('/obtener/<int:registro_id>')
@login_required
def obtener(registro_id):
    row = execute_query_one(
        """
        SELECT
            a.id,
            a.tipo,
            COALESCE(a.codigo_externo, '') AS codigo_externo,
            COALESCE(a.nit_ci, '') AS nit_ci,
            a.nombre,
            COALESCE(a.razon_social, '') AS razon_social,
            COALESCE(a.telefono, '') AS telefono,
            COALESCE(a.email, '') AS email,
            COALESCE(a.direccion, '') AS direccion,
            a.es_ocasional,
            a.activo,
            COALESCE(a.observaciones, '') AS observaciones,
            COALESCE(a.origen_tabla, '') AS origen_tabla,
            a.ref_id,
            CASE
                WHEN a.tipo = 'CLIENTE' AND a.origen_tabla = %s AND a.ref_id IS NOT NULL
                THEN TRUE
                ELSE FALSE
            END AS cliente_referenciado
        FROM contabilidad.auxiliar a
        WHERE a.id = %s
        LIMIT 1
        """,
        (ORIGEN_CLIENTE_EMPRESA, registro_id)
    )

    if not row:
        return jsonify({'ok': False, 'msg': 'El auxiliar no existe.'}), 404

    empresa_text = ''
    if row['cliente_referenciado'] and row['ref_id']:
        empresa = _obtener_empresa_cliente(row['ref_id'])
        if empresa:
            nit = _clean(empresa.get('nit'))
            empresa_text = f"{empresa['nombre']} | NIT: {nit or 'S/N'}"
            if _clean(empresa.get('razon_social')):
                empresa_text += f" | RS: {empresa['razon_social']}"

    row['empresa_id'] = row['ref_id']
    row['empresa_text'] = empresa_text

    return jsonify({'ok': True, 'data': row})


@auxiliar_bp.route('/empresas/buscar')
@login_required
def buscar_empresas():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'

    rows = execute_query(
        """
        SELECT
            id,
            nombre,
            COALESCE(nit, '') AS nit,
            COALESCE(razon_social, '') AS razon_social,
            COALESCE(telefono, '') AS telefono,
            COALESCE(email, '') AS email,
            COALESCE(direccion, '') AS direccion,
            COALESCE(estado, '') AS estado
        FROM clientes.empresas
        WHERE TRIM(UPPER(COALESCE(estado, ''))) = 'ACTIVO'
          AND (
                %s = ''
                OR nombre ILIKE %s
                OR COALESCE(nit, '') ILIKE %s
                OR COALESCE(razon_social, '') ILIKE %s
              )
        ORDER BY nombre ASC
        LIMIT 30
        """,
        (q, q_like, q_like, q_like),
        fetchall=True
    )

    results = []
    for r in rows:
        nit = _clean(r.get('nit'))
        razon_social = _clean(r.get('razon_social'))

        text = f"{r['nombre']} | NIT: {nit or 'S/N'}"
        if razon_social:
            text += f" | RS: {razon_social}"

        results.append({
            'id': r['id'],
            'text': text,
            'nombre': r['nombre'],
            'nit': r['nit'],
            'razon_social': r['razon_social'],
            'telefono': r['telefono'],
            'email': r['email'],
            'direccion': r['direccion']
        })

    return jsonify({'results': results})

@auxiliar_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    duplicado = _buscar_duplicado(payload)
    if duplicado:
        if payload['tipo'] == 'CLIENTE' and payload['cliente_referenciado']:
            return jsonify({
                'ok': False,
                'msg': 'La empresa seleccionada ya está enlazada a un auxiliar cliente.'
            }), 409

        return jsonify({
            'ok': False,
            'msg': 'Ya existe un auxiliar con el mismo tipo, nombre y NIT/CI.'
        }), 409

    execute_query(
        """
        INSERT INTO contabilidad.auxiliar (
            tipo,
            origen_tabla,
            ref_id,
            codigo_externo,
            nit_ci,
            nombre,
            razon_social,
            telefono,
            email,
            direccion,
            es_ocasional,
            activo,
            actualizado_en,
            observaciones
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
        """,
        (
            payload['tipo'],
            payload['origen_tabla'],
            payload['ref_id'],
            payload['codigo_externo'],
            payload['nit_ci'],
            payload['nombre'],
            payload['razon_social'],
            payload['telefono'],
            payload['email'],
            payload['direccion'],
            payload['es_ocasional'],
            payload['activo'],
            payload['observaciones']
        )
    )

    return jsonify({'ok': True, 'msg': 'Auxiliar creado correctamente.'})


@auxiliar_bp.route('/editar/<int:registro_id>', methods=['PUT'])
@login_required
def editar(registro_id):
    actual = execute_query_one(
        """
        SELECT id
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not actual:
        return jsonify({'ok': False, 'msg': 'El auxiliar no existe.'}), 404

    data = request.get_json() or {}
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    duplicado = _buscar_duplicado(payload, exclude_id=registro_id)
    if duplicado:
        if payload['tipo'] == 'CLIENTE' and payload['cliente_referenciado']:
            return jsonify({
                'ok': False,
                'msg': 'La empresa seleccionada ya está enlazada a otro auxiliar cliente.'
            }), 409

        return jsonify({
            'ok': False,
            'msg': 'Ya existe otro auxiliar con el mismo tipo, nombre y NIT/CI.'
        }), 409

    execute_query(
        """
        UPDATE contabilidad.auxiliar
        SET
            tipo = %s,
            origen_tabla = %s,
            ref_id = %s,
            codigo_externo = %s,
            nit_ci = %s,
            nombre = %s,
            razon_social = %s,
            telefono = %s,
            email = %s,
            direccion = %s,
            es_ocasional = %s,
            activo = %s,
            actualizado_en = CURRENT_TIMESTAMP,
            observaciones = %s
        WHERE id = %s
        """,
        (
            payload['tipo'],
            payload['origen_tabla'],
            payload['ref_id'],
            payload['codigo_externo'],
            payload['nit_ci'],
            payload['nombre'],
            payload['razon_social'],
            payload['telefono'],
            payload['email'],
            payload['direccion'],
            payload['es_ocasional'],
            payload['activo'],
            payload['observaciones'],
            registro_id
        )
    )

    return jsonify({'ok': True, 'msg': 'Auxiliar actualizado correctamente.'})


@auxiliar_bp.route('/toggle-activo/<int:registro_id>', methods=['POST'])
@login_required
def toggle_activo(registro_id):
    row = execute_query_one(
        """
        SELECT id, activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not row:
        return jsonify({'ok': False, 'msg': 'El auxiliar no existe.'}), 404

    nuevo_estado = not bool(row['activo'])

    execute_query(
        """
        UPDATE contabilidad.auxiliar
        SET
            activo = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (nuevo_estado, registro_id)
    )

    return jsonify({
        'ok': True,
        'msg': 'Auxiliar activado correctamente.' if nuevo_estado else 'Auxiliar desactivado correctamente.'
    })