# ============================================================
# DXT CONTA - Módulo Compromisos
# DXT-CONTA :: Compromisos Pendientes :: producción
# ============================================================

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import jsonify, render_template, request, session
from psycopg2 import errors

from database.db_manager import DatabaseManager
from modules.compromisos import compromisos_bp
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]

TIPOS_COMPROMISO = ['PAGAR', 'COBRAR']
ESTADOS_DETALLE = ['PENDIENTE', 'PAGADO', 'COBRADO']


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


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'sí', 'on')


def _parse_int(value, field_name, required=True):
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field_name}" debe ser numérico.')


def _parse_decimal(value, field_name, allow_zero=False):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f'El campo "{field_name}" no tiene un formato válido.')

    if allow_zero:
        if number < 0:
            raise ValueError(f'El campo "{field_name}" no puede ser negativo.')
    else:
        if number <= 0:
            raise ValueError(f'El campo "{field_name}" debe ser mayor a cero.')

    return number.quantize(Decimal('0.01'))


def _parse_date(value, field_name, required=True):
    if not value:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None

    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.')


def _gestion_actual():
    return date.today().year


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


def _siguiente_codigo(db):
    rows = db.execute_query("""
        SELECT
            GREATEST(
                COALESCE(
                    MAX(
                        CASE
                            WHEN codigo ~ '^C[0-9]+$' THEN SUBSTRING(codigo FROM 2)::INTEGER
                            WHEN codigo ~ '^[0-9]+$' THEN codigo::INTEGER
                            ELSE NULL
                        END
                    ),
                    3000
                ),
                3000
            ) + 1 AS siguiente
        FROM contabilidad.compromiso
    """)
    siguiente = int(rows[0]['siguiente']) if rows else 3001
    return f'C{siguiente:04d}'


def _estado_por_tipo(tipo, monto_registrado):
    if Decimal(str(monto_registrado)) > 0:
        return 'COBRADO' if tipo == 'COBRAR' else 'PAGADO'
    return 'PENDIENTE'


def _obtener_compromiso(db, compromiso_id):
    rows = db.execute_query("""
        SELECT
            c.id,
            c.codigo,
            c.tipo,
            c.nombre,
            c.descripcion,
            c.auxiliar_id,
            c.cuenta_contable,
            c.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            c.gestion,
            c.activo,
            c.creado_en,
            c.actualizado_en
        FROM contabilidad.compromiso c
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        WHERE c.id = %s
        LIMIT 1
    """, (compromiso_id,))
    return rows[0] if rows else None


def _obtener_detalles(db, compromiso_id):
    return db.execute_query("""
        SELECT
            d.id,
            d.compromiso_id,
            d.fecha_vencimiento,
            d.monto_programado,
            d.monto_registrado,
            d.estado,
            d.observacion,
            d.creado_en,
            d.actualizado_en,
            EXISTS (
                SELECT 1
                FROM contabilidad.compromiso_aplicacion a
                WHERE a.compromiso_detalle_id = d.id
            ) AS tiene_aplicaciones
        FROM contabilidad.compromiso_detalle d
        WHERE d.compromiso_id = %s
        ORDER BY d.fecha_vencimiento ASC, d.id ASC
    """, (compromiso_id,))


def _compromiso_tiene_registrados(db, compromiso_id):
    rows = db.execute_query("""
        SELECT 1
        FROM contabilidad.compromiso_detalle
        WHERE compromiso_id = %s
          AND monto_registrado > 0
        LIMIT 1
    """, (compromiso_id,))
    return bool(rows)


def _compromiso_tiene_aplicaciones(db, compromiso_id):
    rows = db.execute_query("""
        SELECT 1
        FROM contabilidad.compromiso_aplicacion a
        INNER JOIN contabilidad.compromiso_detalle d ON d.id = a.compromiso_detalle_id
        WHERE d.compromiso_id = %s
        LIMIT 1
    """, (compromiso_id,))
    return bool(rows)


def _obtener_unidad_negocio(db, unidad_negocio_id):
    rows = db.execute_query(
        """
        SELECT
            id,
            codigo,
            nombre,
            activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_negocio_id,)
    )
    return rows[0] if rows else None


def _listar_unidades_negocio(db, texto=''):
    condiciones = ['activo = true']
    params = []

    if texto:
        like = f'%{texto}%'
        condiciones.append("(codigo ILIKE %s OR nombre ILIKE %s OR COALESCE(nit, '') ILIKE %s)")
        params.extend([like, like, like])

    where_sql = ' AND '.join(condiciones)

    return db.execute_query(f"""
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(nit, '') AS nit,
            activo
        FROM contabilidad.unidad_negocio
        WHERE {where_sql}
        ORDER BY nombre ASC, codigo ASC
        LIMIT 150
    """, tuple(params))


def _validar_header(db, payload):
    tipo = _clean(payload.get('tipo'))
    nombre = _clean(payload.get('nombre'))
    descripcion = _clean(payload.get('descripcion'))
    cuenta_contable = _clean(payload.get('cuenta_contable')) or None
    auxiliar_id = payload.get('auxiliar_id')
    unidad_negocio_id = _parse_int(payload.get('unidad_negocio_id'), 'Unidad de negocio')
    gestion = _parse_int(payload.get('gestion'), 'Gestión')
    activo = _parse_bool(payload.get('activo', True))

    if gestion < _gestion_actual():
        raise ValueError('No se permite crear compromisos para gestiones anteriores a la actual.')

    if tipo not in TIPOS_COMPROMISO:
        raise ValueError('El tipo de compromiso es inválido.')

    if not nombre:
        raise ValueError('El nombre es obligatorio.')

    if len(nombre) > 150:
        raise ValueError('El nombre no puede exceder 150 caracteres.')

    if descripcion and len(descripcion) > 5000:
        raise ValueError('La descripción es demasiado larga.')

    auxiliar_id = _parse_int(auxiliar_id, 'Auxiliar', required=False)

    if cuenta_contable:
        tabla_cuentas = _tabla_cuentas(db)
        rows = db.execute_query(
            f"SELECT codigo FROM {tabla_cuentas} WHERE codigo = %s LIMIT 1",
            (cuenta_contable,)
        )
        if not rows:
            raise ValueError('La cuenta contable seleccionada no existe.')

    unidad = _obtener_unidad_negocio(db, unidad_negocio_id)
    if not unidad:
        raise ValueError('La unidad de negocio seleccionada no existe.')

    return {
        'tipo': tipo,
        'nombre': nombre,
        'descripcion': descripcion or None,
        'auxiliar_id': auxiliar_id,
        'cuenta_contable': cuenta_contable,
        'unidad_negocio_id': unidad_negocio_id,
        'unidad_negocio_codigo': unidad['codigo'],
        'unidad_negocio_nombre': unidad['nombre'],
        'gestion': gestion,
        'activo': activo
    }


def _validar_detalles(detalles, gestion):
    if not isinstance(detalles, list) or not detalles:
        raise ValueError('Debe registrar al menos un vencimiento.')

    detalle_limpio = []

    for idx, item in enumerate(detalles, start=1):
        detalle_id = item.get('id')
        fecha_vencimiento = _parse_date(item.get('fecha_vencimiento'), f'Fecha del registro {idx}')
        monto_programado = _parse_decimal(item.get('monto_programado'), f'Monto del registro {idx}')
        observacion = _clean(item.get('observacion'))

        if fecha_vencimiento.year < gestion:
            raise ValueError('La fecha de vencimiento no puede ser anterior a la gestión base del compromiso.')

        detalle_limpio.append({
            'id': _parse_int(detalle_id, 'ID detalle', required=False),
            'fecha_vencimiento': fecha_vencimiento,
            'monto_programado': monto_programado,
            'observacion': observacion or None
        })

    return detalle_limpio

@compromisos_bp.route('/pendientes', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def pendientes():
    return render_template(
        'compromisos_pendientes.html',
        gestion_actual=_gestion_actual(),
        tipos_compromiso=TIPOS_COMPROMISO,
        puede_editar=_puede_editar()
    )

@compromisos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return render_template(
        'compromisos_index.html',
        gestion_actual=_gestion_actual(),
        tipos_compromiso=TIPOS_COMPROMISO,
        puede_editar=_puede_editar()
    )


@compromisos_bp.route('/nuevo')
@login_required
@roles_required(ROLES_EDICION)
def nuevo():
    return render_template(
        'compromisos_form.html',
        mode='create',
        gestion_actual=_gestion_actual(),
        tipos_compromiso=TIPOS_COMPROMISO,
        compromiso_data=None
    )


@compromisos_bp.route('/editar/<int:compromiso_id>')
@login_required
@roles_required(ROLES_LECTURA)
def editar(compromiso_id):
    try:
        with DatabaseManager() as db:
            header = _obtener_compromiso(db, compromiso_id)
            if not header:
                return render_template(
                    'compromisos_form.html',
                    mode='view',
                    gestion_actual=_gestion_actual(),
                    tipos_compromiso=TIPOS_COMPROMISO,
                    compromiso_data=None
                )

            detalles = _obtener_detalles(db, compromiso_id)
            data = {
                'id': header['id'],
                'codigo': header['codigo'],
                'tipo': header['tipo'],
                'nombre': header['nombre'],
                'descripcion': header['descripcion'] or '',
                'auxiliar_id': header['auxiliar_id'],
                'cuenta_contable': header['cuenta_contable'],
                'unidad_negocio_id': header['unidad_negocio_id'],
                'unidad_negocio_codigo': header['unidad_negocio_codigo'],
                'unidad_negocio_nombre': header['unidad_negocio_nombre'],
                'gestion': header['gestion'],
                'activo': header['activo'],
                'generator_enabled': not any(Decimal(str(d['monto_registrado'])) > 0 for d in detalles),
                'detalle': [
                    {
                        'id': d['id'],
                        'fecha_vencimiento': d['fecha_vencimiento'].isoformat(),
                        'monto_programado': float(d['monto_programado']),
                        'monto_registrado': float(d['monto_registrado']),
                        'estado': d['estado'],
                        'observacion': d['observacion'] or '',
                        'tiene_aplicaciones': d['tiene_aplicaciones']
                    }
                    for d in detalles
                ]
            }

        return render_template(
            'compromisos_form.html',
            mode='edit',
            gestion_actual=_gestion_actual(),
            tipos_compromiso=TIPOS_COMPROMISO,
            compromiso_data=data
        )
    except Exception:
        return render_template(
            'compromisos_form.html',
            mode='view',
            gestion_actual=_gestion_actual(),
            tipos_compromiso=TIPOS_COMPROMISO,
            compromiso_data=None
        )


@compromisos_bp.route('/api/siguiente-codigo', methods=['GET'])
@login_required
@roles_required(ROLES_EDICION)
def siguiente_codigo():
    try:
        with DatabaseManager() as db:
            codigo = _siguiente_codigo(db)
        return _json_ok(data={'codigo': codigo})
    except Exception as e:
        return _json_error(f'No se pudo generar el código: {str(e)}', 500)


@compromisos_bp.route('/api/auxiliares', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def auxiliares():
    texto = _clean(request.args.get('q'))
    params = []
    where_sql = ''

    if texto:
        where_sql = "WHERE nombre ILIKE %s OR CAST(id AS TEXT) ILIKE %s"
        like = f'%{texto}%'
        params = [like, like]

    try:
        with DatabaseManager() as db:
            rows = db.execute_query(f"""
                SELECT id, nombre
                FROM contabilidad.auxiliar
                {where_sql}
                ORDER BY nombre
                LIMIT 150
            """, tuple(params))

        return _json_ok(data=rows)
    except Exception as e:
        return _json_error(f'No se pudo listar auxiliares: {str(e)}', 500)


@compromisos_bp.route('/api/cuentas', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def cuentas():
    texto = _clean(request.args.get('q'))
    params = []

    try:
        with DatabaseManager() as db:
            tabla_cuentas = _tabla_cuentas(db)
            condiciones = ["activo = true", "es_postable = true"]

            if texto:
                condiciones.append("(codigo ILIKE %s OR nombre ILIKE %s)")
                like = f'%{texto}%'
                params.extend([like, like])

            rows = db.execute_query(f"""
                SELECT
                    codigo,
                    nombre,
                    (codigo || ' - ' || nombre) AS etiqueta
                FROM {tabla_cuentas}
                WHERE {' AND '.join(condiciones)}
                ORDER BY codigo
                LIMIT 150
            """, tuple(params))

        return _json_ok(data=rows)
    except Exception as e:
        return _json_error(f'No se pudo listar cuentas: {str(e)}', 500)


@compromisos_bp.route('/api/unidades-negocio', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def unidades_negocio():
    texto = _clean(request.args.get('q'))

    try:
        with DatabaseManager() as db:
            rows = _listar_unidades_negocio(db, texto)

        data = [
            {
                'id': row['id'],
                'codigo': row['codigo'],
                'nombre': row['nombre'],
                'nit': row['nit'],
                'etiqueta': f"{row['codigo']} - {row['nombre']}",
            }
            for row in rows
        ]
        return _json_ok(data=data)
    except Exception as e:
        return _json_error(f'No se pudo listar unidades de negocio: {str(e)}', 500)


@compromisos_bp.route('/api/listar', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def listar():
    gestion = _parse_int(request.args.get('gestion'), 'Gestión')
    tipo = _clean(request.args.get('tipo'))
    estado = _clean(request.args.get('estado'))
    texto = _clean(request.args.get('texto'))
    unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)
    solo_activos = request.args.get('solo_activos', 'true')

    condiciones = ["EXISTS (SELECT 1 FROM contabilidad.compromiso_detalle df WHERE df.compromiso_id = c.id AND EXTRACT(YEAR FROM df.fecha_vencimiento)::int = %s)"]
    params = [gestion]

    if tipo:
        condiciones.append('c.tipo = %s')
        params.append(tipo)

    if unidad_negocio_id:
        condiciones.append('c.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    if texto:
        condiciones.append("""
            (
                c.codigo ILIKE %s
                OR c.nombre ILIKE %s
                OR COALESCE(a.nombre, '') ILIKE %s
                OR COALESCE(un.nombre, '') ILIKE %s
                OR COALESCE(c.descripcion, '') ILIKE %s
            )
        """)
        like = f'%{texto}%'
        params.extend([like, like, like, like, like])

    if str(solo_activos).lower() in ('true', '1', 't'):
        condiciones.append('c.activo = true')

    where_sql = ' AND '.join(condiciones)

    having_sql = ''
    if estado == 'PENDIENTE':
        having_sql = """
            HAVING SUM(CASE WHEN d.monto_registrado > 0 THEN 1 ELSE 0 END) = 0
        """
    elif estado == 'PAGADO':
        having_sql = """
            HAVING c.tipo = 'PAGAR'
               AND COUNT(*) = SUM(CASE WHEN d.monto_registrado > 0 THEN 1 ELSE 0 END)
        """
    elif estado == 'COBRADO':
        having_sql = """
            HAVING c.tipo = 'COBRAR'
               AND COUNT(*) = SUM(CASE WHEN d.monto_registrado > 0 THEN 1 ELSE 0 END)
        """

    try:
        with DatabaseManager() as db:
            tabla_cuentas = _tabla_cuentas(db)

            rows = db.execute_query(f"""
                SELECT
                    c.id AS compromiso_id,
                    c.codigo,
                    c.tipo,
                    c.nombre,
                    c.descripcion,
                    c.auxiliar_id,
                    COALESCE(a.nombre, '') AS auxiliar_nombre,
                    c.unidad_negocio_id,
                    COALESCE(un.codigo, '') AS unidad_negocio_codigo,
                    COALESCE(un.nombre, '') AS unidad_negocio_nombre,
                    c.cuenta_contable,
                    COALESCE(cta.nombre, '') AS cuenta_nombre,
                    c.gestion,
                    c.activo,
                    COUNT(d.id) AS cantidad_detalles,
                    MIN(d.fecha_vencimiento) AS primer_vencimiento,
                    MAX(d.fecha_vencimiento) AS ultimo_vencimiento,
                    SUM(d.monto_programado) AS total_programado,
                    SUM(d.monto_registrado) AS total_registrado,
                    CASE
                        WHEN SUM(CASE WHEN d.monto_registrado > 0 THEN 1 ELSE 0 END) = 0
                            THEN 'PENDIENTE'
                        WHEN c.tipo = 'PAGAR'
                             AND COUNT(*) = SUM(CASE WHEN d.monto_registrado > 0 THEN 1 ELSE 0 END)
                            THEN 'PAGADO'
                        WHEN c.tipo = 'COBRAR'
                             AND COUNT(*) = SUM(CASE WHEN d.monto_registrado > 0 THEN 1 ELSE 0 END)
                            THEN 'COBRADO'
                        ELSE 'PENDIENTE'
                    END AS estado_general,
                    EXISTS (
                        SELECT 1
                        FROM contabilidad.compromiso_detalle dx
                        WHERE dx.compromiso_id = c.id
                          AND dx.monto_registrado > 0
                    ) AS compromiso_tiene_registrados
                FROM contabilidad.compromiso c
                INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
                LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
                LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
                LEFT JOIN {tabla_cuentas} cta ON cta.codigo = c.cuenta_contable
                WHERE {where_sql}
                GROUP BY
                    c.id,
                    c.codigo,
                    c.tipo,
                    c.nombre,
                    c.descripcion,
                    c.auxiliar_id,
                    a.nombre,
                    c.unidad_negocio_id,
                    un.codigo,
                    un.nombre,
                    c.cuenta_contable,
                    cta.nombre,
                    c.gestion,
                    c.activo
                {having_sql}
                ORDER BY c.codigo ASC
            """, tuple(params))

        data = []
        for row in rows:
            data.append({
                'compromiso_id': row['compromiso_id'],
                'codigo': row['codigo'],
                'tipo': row['tipo'],
                'nombre': row['nombre'],
                'descripcion': row['descripcion'] or '',
                'auxiliar_nombre': row['auxiliar_nombre'],
                'unidad_negocio_id': row['unidad_negocio_id'],
                'unidad_negocio_codigo': row['unidad_negocio_codigo'],
                'unidad_negocio_nombre': row['unidad_negocio_nombre'],
                'cuenta_contable': row['cuenta_contable'],
                'cuenta_nombre': row['cuenta_nombre'],
                'gestion': row['gestion'],
                'activo': row['activo'],
                'cantidad_detalles': int(row['cantidad_detalles']),
                'primer_vencimiento': row['primer_vencimiento'].isoformat() if row['primer_vencimiento'] else '',
                'ultimo_vencimiento': row['ultimo_vencimiento'].isoformat() if row['ultimo_vencimiento'] else '',
                'total_programado': float(row['total_programado'] or 0),
                'total_registrado': float(row['total_registrado'] or 0),
                'estado_general': row['estado_general'],
                'compromiso_tiene_registrados': row['compromiso_tiene_registrados'],
            })

        return jsonify({'data': data})

    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        return _json_error(f'No se pudo listar compromisos: {str(e)}', 500)


@compromisos_bp.route('/api/crear', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def crear():
    payload = request.get_json() or {}

    try:
        with DatabaseManager() as db:
            header = _validar_header(db, payload)
            detalles = _validar_detalles(payload.get('detalle', []), header['gestion'])
            codigo = _siguiente_codigo(db)

            insert_rows = db.execute_query("""
                INSERT INTO contabilidad.compromiso (
                    codigo,
                    tipo,
                    nombre,
                    descripcion,
                    auxiliar_id,
                    cuenta_contable,
                    unidad_negocio_id,
                    gestion,
                    activo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, codigo
            """, (
                codigo,
                header['tipo'],
                header['nombre'],
                header['descripcion'],
                header['auxiliar_id'],
                header['cuenta_contable'],
                header['unidad_negocio_id'],
                header['gestion'],
                header['activo']
            ))

            if not insert_rows:
                raise ValueError('No se pudo obtener el ID interno del compromiso creado.')

            compromiso_id = int(insert_rows[0]['id'])

            for item in detalles:
                estado = _estado_por_tipo(header['tipo'], 0)
                db.execute_insert("""
                    INSERT INTO contabilidad.compromiso_detalle (
                        compromiso_id,
                        fecha_vencimiento,
                        monto_programado,
                        monto_registrado,
                        estado,
                        observacion
                    )
                    VALUES (%s, %s, %s, 0, %s, %s)
                """, (
                    compromiso_id,
                    item['fecha_vencimiento'],
                    item['monto_programado'],
                    estado,
                    item['observacion']
                ), return_id=False)

        return _json_ok('Compromiso registrado correctamente.')

    except ValueError as e:
        return _json_error(str(e))
    except errors.UniqueViolation:
        return _json_error('No se pudo generar un código único para el compromiso.')
    except Exception as e:
        return _json_error(f'No se pudo crear el compromiso: {str(e)}', 500)


@compromisos_bp.route('/api/actualizar/<int:compromiso_id>', methods=['PUT'])
@login_required
@roles_required(ROLES_EDICION)
def actualizar(compromiso_id):
    payload = request.get_json() or {}

    try:
        with DatabaseManager() as db:
            actual = _obtener_compromiso(db, compromiso_id)
            if not actual:
                return _json_error('El compromiso no existe.', 404)

            header = _validar_header(db, payload)
            if header['gestion'] != actual['gestion']:
                return _json_error('La gestión no puede modificarse.')

            detalles_payload = _validar_detalles(payload.get('detalle', []), header['gestion'])
            detalles_db = _obtener_detalles(db, compromiso_id)
            detalles_db_map = {d['id']: d for d in detalles_db}
            ids_payload = {d['id'] for d in detalles_payload if d['id']}

            for detalle_existente in detalles_db:
                detalle_id = detalle_existente['id']
                registrado = Decimal(str(detalle_existente['monto_registrado']))

                if registrado > 0:
                    if detalle_id not in ids_payload:
                        return _json_error('No se puede eliminar una fila ya registrada.')

                    fila_payload = next(x for x in detalles_payload if x['id'] == detalle_id)

                    if (
                        fila_payload['fecha_vencimiento'] != detalle_existente['fecha_vencimiento']
                        or fila_payload['monto_programado'] != Decimal(str(detalle_existente['monto_programado']))
                        or (fila_payload['observacion'] or '') != (detalle_existente['observacion'] or '')
                    ):
                        return _json_error('No se puede modificar una fila ya registrada.')

            db.execute_update("""
                UPDATE contabilidad.compromiso
                SET
                    tipo = %s,
                    nombre = %s,
                    descripcion = %s,
                    auxiliar_id = %s,
                    cuenta_contable = %s,
                    unidad_negocio_id = %s,
                    activo = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                header['tipo'],
                header['nombre'],
                header['descripcion'],
                header['auxiliar_id'],
                header['cuenta_contable'],
                header['unidad_negocio_id'],
                header['activo'],
                compromiso_id
            ))

            for detalle_existente in detalles_db:
                detalle_id = detalle_existente['id']
                registrado = Decimal(str(detalle_existente['monto_registrado']))
                if detalle_id not in ids_payload and registrado == 0:
                    db.execute_delete("""
                        DELETE FROM contabilidad.compromiso_detalle
                        WHERE id = %s
                    """, (detalle_id,))

            for item in detalles_payload:
                if item['id']:
                    detalle_existente = detalles_db_map[item['id']]
                    registrado = Decimal(str(detalle_existente['monto_registrado']))

                    if registrado == 0:
                        estado = _estado_por_tipo(header['tipo'], registrado)
                        db.execute_update("""
                            UPDATE contabilidad.compromiso_detalle
                            SET
                                fecha_vencimiento = %s,
                                monto_programado = %s,
                                estado = %s,
                                observacion = %s,
                                actualizado_en = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (
                            item['fecha_vencimiento'],
                            item['monto_programado'],
                            estado,
                            item['observacion'],
                            item['id']
                        ))
                else:
                    estado = _estado_por_tipo(header['tipo'], 0)
                    db.execute_insert("""
                        INSERT INTO contabilidad.compromiso_detalle (
                            compromiso_id,
                            fecha_vencimiento,
                            monto_programado,
                            monto_registrado,
                            estado,
                            observacion
                        )
                        VALUES (%s, %s, %s, 0, %s, %s)
                    """, (
                        compromiso_id,
                        item['fecha_vencimiento'],
                        item['monto_programado'],
                        estado,
                        item['observacion']
                    ), return_id=False)

        return _json_ok('Compromiso actualizado correctamente.')

    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        return _json_error(f'No se pudo actualizar el compromiso: {str(e)}', 500)


@compromisos_bp.route('/api/eliminar/<int:compromiso_id>', methods=['DELETE'])
@login_required
@roles_required(ROLES_EDICION)
def eliminar(compromiso_id):
    try:
        with DatabaseManager() as db:
            actual = _obtener_compromiso(db, compromiso_id)
            if not actual:
                return _json_error('El compromiso no existe.', 404)

            if _compromiso_tiene_registrados(db, compromiso_id):
                return _json_error('No se puede eliminar el compromiso porque ya tiene pagos/cobros registrados.')

            if _compromiso_tiene_aplicaciones(db, compromiso_id):
                return _json_error('No se puede eliminar el compromiso porque ya tiene aplicaciones registradas.')

            db.execute_delete("""
                DELETE FROM contabilidad.compromiso
                WHERE id = %s
            """, (compromiso_id,))

        return _json_ok('Compromiso eliminado correctamente.')

    except Exception as e:
        return _json_error(f'No se pudo eliminar el compromiso: {str(e)}', 500)


# ============================================================
# Seguimiento de compromisos pendientes
# ============================================================
ESTADOS_SEGUIMIENTO = ['PENDIENTE', 'VENCIDO', 'CUMPLIDO', 'TODOS']
VENTANAS_ALERTA = ['TODOS', 'HOY_VENCIDOS', '1_DIA', '2_3_DIAS', '4_7_DIAS', '8_30_DIAS', '31_MAS', 'RANGO']


def _decimal_or_zero(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


def _compromiso_estado_alerta(fecha_vencimiento, total_pendiente):
    pendiente = _decimal_or_zero(total_pendiente)
    today = date.today()

    if pendiente <= 0:
        return {
            'estado': 'CUMPLIDO',
            'dias': None,
            'alerta_key': 'CUMPLIDO',
            'alerta_label': 'Cumplido',
            'color_key': 'cumplido',
            'proximo_vencimiento': fecha_vencimiento,
        }

    if not fecha_vencimiento:
        return {
            'estado': 'PENDIENTE',
            'dias': None,
            'alerta_key': 'SIN_FECHA',
            'alerta_label': 'Sin fecha',
            'color_key': 'neutro',
            'proximo_vencimiento': None,
        }

    dias = (fecha_vencimiento - today).days

    if dias <= 0:
        return {
            'estado': 'VENCIDO',
            'dias': dias,
            'alerta_key': 'HOY_VENCIDOS',
            'alerta_label': 'Vence hoy' if dias == 0 else f'Vencido hace {abs(dias)} día(s)',
            'color_key': 'rojo',
            'proximo_vencimiento': fecha_vencimiento,
        }
    if dias == 1:
        return {
            'estado': 'PENDIENTE',
            'dias': dias,
            'alerta_key': '1_DIA',
            'alerta_label': 'Vence en 1 día',
            'color_key': 'amarillo',
            'proximo_vencimiento': fecha_vencimiento,
        }
    if 2 <= dias <= 3:
        return {
            'estado': 'PENDIENTE',
            'dias': dias,
            'alerta_key': '2_3_DIAS',
            'alerta_label': 'Vence en 2 a 3 días',
            'color_key': 'naranja',
            'proximo_vencimiento': fecha_vencimiento,
        }
    if 4 <= dias <= 7:
        return {
            'estado': 'PENDIENTE',
            'dias': dias,
            'alerta_key': '4_7_DIAS',
            'alerta_label': 'Vence en 4 a 7 días',
            'color_key': 'verde',
            'proximo_vencimiento': fecha_vencimiento,
        }
    if 8 <= dias <= 30:
        return {
            'estado': 'PENDIENTE',
            'dias': dias,
            'alerta_key': '8_30_DIAS',
            'alerta_label': 'Vence en 8 a 30 días',
            'color_key': 'neutro',
            'proximo_vencimiento': fecha_vencimiento,
        }

    return {
        'estado': 'PENDIENTE',
        'dias': dias,
        'alerta_key': '31_MAS',
        'alerta_label': 'Vence en más de 30 días',
        'color_key': 'neutro',
        'proximo_vencimiento': fecha_vencimiento,
    }


def _build_pendientes_row(row):
    total_programado = _decimal_or_zero(row['total_programado'])
    total_registrado = _decimal_or_zero(row['total_registrado'])
    total_pendiente = _decimal_or_zero(row['total_pendiente'])
    meta = _compromiso_estado_alerta(row['proximo_vencimiento'], total_pendiente)

    return {
        'compromiso_id': row['compromiso_id'],
        'codigo': row['codigo'],
        'tipo': row['tipo'],
        'nombre': row['nombre'],
        'descripcion': row['descripcion'] or '',
        'auxiliar_nombre': row['auxiliar_nombre'] or '',
        'unidad_negocio_id': row['unidad_negocio_id'],
        'unidad_negocio_codigo': row['unidad_negocio_codigo'] or '',
        'unidad_negocio_nombre': row['unidad_negocio_nombre'] or '',
        'cuenta_contable': row['cuenta_contable'] or '',
        'cuenta_nombre': row['cuenta_nombre'] or '',
        'gestion': row['gestion'],
        'activo': row['activo'],
        'total_detalles': int(row['total_detalles'] or 0),
        'detalles_pendientes': int(row['detalles_pendientes'] or 0),
        'detalles_cumplidos': int(row['detalles_cumplidos'] or 0),
        'primer_vencimiento': row['primer_vencimiento'].isoformat() if row['primer_vencimiento'] else '',
        'ultimo_vencimiento': row['ultimo_vencimiento'].isoformat() if row['ultimo_vencimiento'] else '',
        'proximo_vencimiento': row['proximo_vencimiento'].isoformat() if row['proximo_vencimiento'] else '',
        'total_programado': float(total_programado),
        'total_registrado': float(total_registrado),
        'total_pendiente': float(total_pendiente),
        'estado_seguimiento': meta['estado'],
        'dias_alerta': meta['dias'],
        'alerta_key': meta['alerta_key'],
        'alerta_label': meta['alerta_label'],
        'color_key': meta['color_key'],
    }


def _filter_pendientes_rows(rows, filters):
    estado = filters['estado']
    ventana = filters['ventana']
    fecha_desde = filters['fecha_desde']
    fecha_hasta = filters['fecha_hasta']

    data = rows

    if estado and estado != 'TODOS':
        data = [r for r in data if r['estado_seguimiento'] == estado]

    if ventana == 'RANGO' and (fecha_desde or fecha_hasta):
        filtered = []
        for row in data:
            if row['estado_seguimiento'] == 'CUMPLIDO':
                continue
            if not row['proximo_vencimiento']:
                continue
            due = datetime.strptime(row['proximo_vencimiento'], '%Y-%m-%d').date()
            if fecha_desde and due < fecha_desde:
                continue
            if fecha_hasta and due > fecha_hasta:
                continue
            filtered.append(row)
        data = filtered
    elif ventana and ventana != 'TODOS':
        data = [r for r in data if r['alerta_key'] == ventana]

    return data


def _pendientes_summary(rows):
    summary = {
        'total': len(rows),
        'pendientes': 0,
        'vencidos': 0,
        'cumplidos': 0,
        'hoy_vencidos': 0,
        'un_dia': 0,
        'dos_tres': 0,
        'cuatro_siete': 0,
        'ocho_treinta': 0,
        'monto_pendiente': 0.0,
    }

    monto_pendiente = Decimal('0.00')

    for row in rows:
        if row['estado_seguimiento'] == 'CUMPLIDO':
            summary['cumplidos'] += 1
        elif row['estado_seguimiento'] == 'VENCIDO':
            summary['vencidos'] += 1
            summary['hoy_vencidos'] += 1
        else:
            summary['pendientes'] += 1

        if row['alerta_key'] == '1_DIA':
            summary['un_dia'] += 1
        elif row['alerta_key'] == '2_3_DIAS':
            summary['dos_tres'] += 1
        elif row['alerta_key'] == '4_7_DIAS':
            summary['cuatro_siete'] += 1
        elif row['alerta_key'] == '8_30_DIAS':
            summary['ocho_treinta'] += 1

        monto_pendiente += _decimal_or_zero(row['total_pendiente'])

    summary['monto_pendiente'] = float(monto_pendiente)
    return summary


def _fetch_compromisos_pendientes(db, filters):
    texto = filters['texto']
    condiciones = ["EXISTS (SELECT 1 FROM contabilidad.compromiso_detalle df WHERE df.compromiso_id = c.id AND EXTRACT(YEAR FROM df.fecha_vencimiento)::int = %s)"]
    params = [filters['gestion']]

    if filters['tipo']:
        condiciones.append('c.tipo = %s')
        params.append(filters['tipo'])

    if filters['unidad_negocio_id']:
        condiciones.append('c.unidad_negocio_id = %s')
        params.append(filters['unidad_negocio_id'])

    if filters['solo_activos']:
        condiciones.append('c.activo = true')

    if texto:
        like = f'%{texto}%'
        condiciones.append("""
            (
                c.codigo ILIKE %s
                OR c.nombre ILIKE %s
                OR COALESCE(a.nombre, '') ILIKE %s
                OR COALESCE(un.nombre, '') ILIKE %s
                OR COALESCE(c.descripcion, '') ILIKE %s
                OR COALESCE(cta.nombre, '') ILIKE %s
            )
        """)
        params.extend([like, like, like, like, like, like])

    tabla_cuentas = _tabla_cuentas(db)
    where_sql = ' AND '.join(condiciones)

    rows = db.execute_query(f"""
        SELECT
            c.id AS compromiso_id,
            c.codigo,
            c.tipo,
            c.nombre,
            c.descripcion,
            COALESCE(a.nombre, '') AS auxiliar_nombre,
            c.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            c.cuenta_contable,
            COALESCE(cta.nombre, '') AS cuenta_nombre,
            c.gestion,
            c.activo,
            COUNT(d.id) AS total_detalles,
            SUM(CASE WHEN d.monto_registrado < d.monto_programado THEN 1 ELSE 0 END) AS detalles_pendientes,
            SUM(CASE WHEN d.monto_registrado >= d.monto_programado THEN 1 ELSE 0 END) AS detalles_cumplidos,
            MIN(d.fecha_vencimiento) AS primer_vencimiento,
            MAX(d.fecha_vencimiento) AS ultimo_vencimiento,
            MIN(CASE WHEN d.monto_registrado < d.monto_programado THEN d.fecha_vencimiento END) AS proximo_vencimiento,
            SUM(COALESCE(d.monto_programado, 0)) AS total_programado,
            SUM(COALESCE(d.monto_registrado, 0)) AS total_registrado,
            SUM(GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0)) AS total_pendiente
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        LEFT JOIN {tabla_cuentas} cta ON cta.codigo = c.cuenta_contable
        WHERE {where_sql}
        GROUP BY
            c.id,
            c.codigo,
            c.tipo,
            c.nombre,
            c.descripcion,
            a.nombre,
            c.unidad_negocio_id,
            un.codigo,
            un.nombre,
            c.cuenta_contable,
            cta.nombre,
            c.gestion,
            c.activo
        ORDER BY
            MIN(CASE WHEN d.monto_registrado < d.monto_programado THEN d.fecha_vencimiento END) ASC NULLS LAST,
            c.codigo ASC
    """, tuple(params))

    mapped = [_build_pendientes_row(row) for row in rows]
    return mapped


def _fetch_compromiso_detalle_movimientos(db, compromiso_id):
    header_rows = db.execute_query("""
        SELECT
            c.id,
            c.codigo,
            c.tipo,
            c.nombre,
            c.descripcion,
            c.gestion,
            c.activo,
            COALESCE(a.nombre, '') AS auxiliar_nombre,
            c.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            c.cuenta_contable
        FROM contabilidad.compromiso c
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
        WHERE c.id = %s
        LIMIT 1
    """, (compromiso_id,))
    if not header_rows:
        return None

    header = header_rows[0]
    detail_rows = db.execute_query("""
        SELECT
            d.id,
            d.fecha_vencimiento,
            d.monto_programado,
            d.monto_registrado,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) AS monto_pendiente,
            d.estado,
            d.observacion
        FROM contabilidad.compromiso_detalle d
        WHERE d.compromiso_id = %s
        ORDER BY d.fecha_vencimiento ASC, d.id ASC
    """, (compromiso_id,))

    movimientos = []
    if header['tipo'] == 'PAGAR':
        movimientos_rows = db.execute_query("""
            SELECT
                d.id AS compromiso_detalle_id,
                'PAGO' AS documento_tipo,
                p.id AS documento_id,
                p.fecha,
                p.estado,
                pd.subtotal AS monto_aplicado,
                COALESCE(p.referencia, '') AS referencia,
                COALESCE(p.glosa, '') AS glosa
            FROM contabilidad.compromiso_detalle d
            INNER JOIN contabilidad.pago_detalle pd ON pd.compromiso_detalle_id = d.id
            INNER JOIN contabilidad.pago p ON p.id = pd.pago_id
            WHERE d.compromiso_id = %s
            ORDER BY p.fecha DESC, p.id DESC
        """, (compromiso_id,))
        for row in movimientos_rows:
            movimientos.append({
                'compromiso_detalle_id': row['compromiso_detalle_id'],
                'documento_tipo': row['documento_tipo'],
                'documento_id': row['documento_id'],
                'fecha': row['fecha'].isoformat() if row['fecha'] else '',
                'estado': row['estado'],
                'monto_aplicado': float(_decimal_or_zero(row['monto_aplicado'])),
                'referencia': row['referencia'],
                'glosa': row['glosa'],
                'editar_url': f"/tesoreria/pagos/{row['documento_id']}/editar",
            })
    else:
        movimientos_rows = db.execute_query("""
            SELECT
                d.id AS compromiso_detalle_id,
                'COBRO' AS documento_tipo,
                c.id AS documento_id,
                c.fecha,
                c.estado,
                cd.subtotal AS monto_aplicado,
                COALESCE(c.referencia, '') AS referencia,
                COALESCE(c.glosa, '') AS glosa
            FROM contabilidad.compromiso_detalle d
            INNER JOIN contabilidad.cobro_detalle cd ON cd.compromiso_detalle_id = d.id
            INNER JOIN contabilidad.cobro c ON c.id = cd.cobro_id
            WHERE d.compromiso_id = %s
            ORDER BY c.fecha DESC, c.id DESC
        """, (compromiso_id,))
        for row in movimientos_rows:
            movimientos.append({
                'compromiso_detalle_id': row['compromiso_detalle_id'],
                'documento_tipo': row['documento_tipo'],
                'documento_id': row['documento_id'],
                'fecha': row['fecha'].isoformat() if row['fecha'] else '',
                'estado': row['estado'],
                'monto_aplicado': float(_decimal_or_zero(row['monto_aplicado'])),
                'referencia': row['referencia'],
                'glosa': row['glosa'],
                'editar_url': f"/tesoreria/cobros/{row['documento_id']}/editar",
            })

    details = []
    for row in detail_rows:
        pendiente = _decimal_or_zero(row['monto_pendiente'])
        meta = _compromiso_estado_alerta(row['fecha_vencimiento'], pendiente)
        details.append({
            'id': row['id'],
            'fecha_vencimiento': row['fecha_vencimiento'].isoformat() if row['fecha_vencimiento'] else '',
            'monto_programado': float(_decimal_or_zero(row['monto_programado'])),
            'monto_registrado': float(_decimal_or_zero(row['monto_registrado'])),
            'monto_pendiente': float(pendiente),
            'estado': row['estado'],
            'observacion': row['observacion'] or '',
            'estado_seguimiento': meta['estado'],
            'alerta_key': meta['alerta_key'],
            'alerta_label': meta['alerta_label'],
            'color_key': meta['color_key'],
        })

    payload = {
        'header': {
            'id': header['id'],
            'codigo': header['codigo'],
            'tipo': header['tipo'],
            'nombre': header['nombre'],
            'descripcion': header['descripcion'] or '',
            'gestion': header['gestion'],
            'activo': header['activo'],
            'auxiliar_nombre': header['auxiliar_nombre'],
            'unidad_negocio_id': header['unidad_negocio_id'],
            'unidad_negocio_codigo': header['unidad_negocio_codigo'] or '',
            'unidad_negocio_nombre': header['unidad_negocio_nombre'] or '',
            'cuenta_contable': header['cuenta_contable'] or '',
        },
        'details': details,
        'movimientos': movimientos,
    }
    return payload


@compromisos_bp.route('/api/pendientes/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_pendientes_lista():
    try:
        gestion = _parse_int(request.args.get('gestion'), 'Gestión')
        tipo = _clean(request.args.get('tipo'))
        estado = _clean(request.args.get('estado')) or 'PENDIENTE'
        texto = _clean(request.args.get('texto'))
        unidad_negocio_id = _parse_int(request.args.get('unidad_negocio_id'), 'Unidad de negocio', required=False)
        ventana = _clean(request.args.get('ventana')) or 'TODOS'
        fecha_desde = _parse_date(request.args.get('fecha_desde'), 'Fecha desde', required=False)
        fecha_hasta = _parse_date(request.args.get('fecha_hasta'), 'Fecha hasta', required=False)
        solo_activos = str(request.args.get('solo_activos', 'true')).lower() in ('true', '1', 't')

        if tipo and tipo not in TIPOS_COMPROMISO:
            raise ValueError('El tipo de compromiso es inválido.')
        if estado not in ESTADOS_SEGUIMIENTO:
            raise ValueError('El estado de seguimiento es inválido.')
        if ventana not in VENTANAS_ALERTA:
            raise ValueError('La ventana de alerta es inválida.')
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')
        if ventana != 'RANGO':
            fecha_desde = None
            fecha_hasta = None

        filters = {
            'gestion': gestion,
            'tipo': tipo,
            'estado': estado,
            'texto': texto,
            'unidad_negocio_id': unidad_negocio_id,
            'ventana': ventana,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'solo_activos': solo_activos,
        }

        with DatabaseManager() as db:
            raw_rows = _fetch_compromisos_pendientes(db, filters)

        resumen = _pendientes_summary(raw_rows)
        data = _filter_pendientes_rows(raw_rows, filters)
        resumen_filtrado = _pendientes_summary(data)

        return _json_ok(
            data=data,
            resumen=resumen,
            resumen_filtrado=resumen_filtrado,
            filters={
                'gestion': gestion,
                'tipo': tipo,
                'estado': estado,
                'texto': texto,
                'unidad_negocio_id': unidad_negocio_id,
                'ventana': ventana,
                'fecha_desde': fecha_desde.isoformat() if fecha_desde else '',
                'fecha_hasta': fecha_hasta.isoformat() if fecha_hasta else '',
                'solo_activos': solo_activos,
            }
        )
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        return _json_error(f'No se pudo listar el control de pendientes: {str(e)}', 500)


@compromisos_bp.route('/api/pendientes/detalle/<int:compromiso_id>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_pendientes_detalle(compromiso_id):
    try:
        with DatabaseManager() as db:
            payload = _fetch_compromiso_detalle_movimientos(db, compromiso_id)

        if not payload:
            return _json_error('El compromiso no existe.', 404)

        return _json_ok(data=payload)
    except Exception as e:
        return _json_error(f'No se pudo obtener el detalle del compromiso: {str(e)}', 500)
# ------------------------------------------------------------
# AYUDA DEL MÓDULO
# ------------------------------------------------------------
@compromisos_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('compromisos_help.html')