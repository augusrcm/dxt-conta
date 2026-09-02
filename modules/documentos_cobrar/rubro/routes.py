# ============================================================
# DXT CONTA - Módulo Rubros Operativos
# ============================================================

from flask import jsonify, render_template, request, session

from database.db_manager import DatabaseManager
from modules.rubro import rubro_bp
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]


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


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'sí', 'on')


def _puede_editar():
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except Exception:
        return False


def _validar_payload(data, rubro_id=None):
    nombre = _clean(data.get('nombre'))
    descripcion = _clean(data.get('descripcion')) or None
    activo = _parse_bool(data.get('activo'), True)

    if not nombre:
        raise ValueError('El nombre es obligatorio.')

    if len(nombre) > 150:
        raise ValueError('El nombre no puede exceder 150 caracteres.')

    if descripcion and len(descripcion) > 300:
        raise ValueError('La descripción no puede exceder 300 caracteres.')

    with DatabaseManager() as db:
        params = [nombre]
        sql = """
            SELECT id
            FROM contabilidad.rubro_operacion
            WHERE UPPER(TRIM(nombre)) = UPPER(TRIM(%s))
        """
        if rubro_id:
            sql += " AND id <> %s"
            params.append(rubro_id)

        sql += " LIMIT 1"

        rows = db.execute_query(sql, tuple(params))
        if rows:
            raise ValueError(f'Ya existe un rubro con el nombre "{nombre}".')

    return {
        'nombre': nombre,
        'descripcion': descripcion,
        'activo': activo,
    }


def _siguiente_codigo(rubro_id):
    return f"RB{int(rubro_id):04d}"


def _obtener_rubro(db, rubro_id):
    rows = db.execute_query(
        """
        SELECT
            id,
            codigo,
            nombre,
            descripcion,
            activo,
            creado_en,
            actualizado_en
        FROM contabilidad.rubro_operacion
        WHERE id = %s
        LIMIT 1
        """,
        (rubro_id,)
    )
    return rows[0] if rows else None


def _dependencias_rubro(db, rubro_id):
    pago = db.execute_query(
        "SELECT COUNT(*) AS total FROM contabilidad.pago WHERE rubro_id = %s",
        (rubro_id,)
    )
    cobro = db.execute_query(
        "SELECT COUNT(*) AS total FROM contabilidad.cobro WHERE rubro_id = %s",
        (rubro_id,)
    )
    asiento = db.execute_query(
        "SELECT COUNT(*) AS total FROM contabilidad.asiento WHERE rubro_id = %s",
        (rubro_id,)
    )

    total_pago = int(pago[0]['total']) if pago else 0
    total_cobro = int(cobro[0]['total']) if cobro else 0
    total_asiento = int(asiento[0]['total']) if asiento else 0

    return {
        'pago': total_pago,
        'cobro': total_cobro,
        'asiento': total_asiento,
        'total': total_pago + total_cobro + total_asiento,
    }


def _build_index_rows(db):
    rows = db.execute_query(
        """
        SELECT
            r.id,
            r.codigo,
            r.nombre,
            COALESCE(r.descripcion, '') AS descripcion,
            r.activo,
            r.creado_en,
            r.actualizado_en,
            COALESCE(p.total, 0) AS usos_pago,
            COALESCE(c.total, 0) AS usos_cobro,
            COALESCE(a.total, 0) AS usos_asiento
        FROM contabilidad.rubro_operacion r
        LEFT JOIN (
            SELECT rubro_id, COUNT(*) AS total
            FROM contabilidad.pago
            WHERE rubro_id IS NOT NULL
            GROUP BY rubro_id
        ) p ON p.rubro_id = r.id
        LEFT JOIN (
            SELECT rubro_id, COUNT(*) AS total
            FROM contabilidad.cobro
            WHERE rubro_id IS NOT NULL
            GROUP BY rubro_id
        ) c ON c.rubro_id = r.id
        LEFT JOIN (
            SELECT rubro_id, COUNT(*) AS total
            FROM contabilidad.asiento
            WHERE rubro_id IS NOT NULL
            GROUP BY rubro_id
        ) a ON a.rubro_id = r.id
        ORDER BY r.codigo ASC
        """
    )

    data = []
    for row in rows:
        usos_pago = int(row['usos_pago'] or 0)
        usos_cobro = int(row['usos_cobro'] or 0)
        usos_asiento = int(row['usos_asiento'] or 0)

        data.append({
            'id': row['id'],
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'descripcion': row['descripcion'] or '',
            'activo': bool(row['activo']),
            'usos_pago': usos_pago,
            'usos_cobro': usos_cobro,
            'usos_asiento': usos_asiento,
            'usos_total': usos_pago + usos_cobro + usos_asiento,
            'creado_en': row['creado_en'].isoformat() if row.get('creado_en') else None,
            'actualizado_en': row['actualizado_en'].isoformat() if row.get('actualizado_en') else None,
        })

    return data


# ============================================================
# Vistas
# ============================================================

@rubro_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return render_template(
        'rubro_index.html',
        puede_editar=_puede_editar()
    )


@rubro_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('rubro_help.html')


# ============================================================
# APIs
# ============================================================

@rubro_bp.route('/api/lista', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_lista():
    try:
        estado = (request.args.get('estado') or 'activos').strip().lower()

        where_sql = ""
        params = ()

        if estado == 'activos':
            where_sql = "WHERE r.activo = TRUE"
        elif estado == 'inactivos':
            where_sql = "WHERE r.activo = FALSE"
        else:
            estado = 'todos'

        with DatabaseManager() as db:
            rows = db.execute_query(
                f"""
                SELECT
                    r.id,
                    r.codigo,
                    r.nombre,
                    COALESCE(r.descripcion, '') AS descripcion,
                    r.activo,
                    r.creado_en,
                    r.actualizado_en,
                    COALESCE(p.total, 0) AS usos_pago,
                    COALESCE(c.total, 0) AS usos_cobro,
                    COALESCE(a.total, 0) AS usos_asiento
                FROM contabilidad.rubro_operacion r
                LEFT JOIN (
                    SELECT rubro_id, COUNT(*) AS total
                    FROM contabilidad.pago
                    WHERE rubro_id IS NOT NULL
                    GROUP BY rubro_id
                ) p ON p.rubro_id = r.id
                LEFT JOIN (
                    SELECT rubro_id, COUNT(*) AS total
                    FROM contabilidad.cobro
                    WHERE rubro_id IS NOT NULL
                    GROUP BY rubro_id
                ) c ON c.rubro_id = r.id
                LEFT JOIN (
                    SELECT rubro_id, COUNT(*) AS total
                    FROM contabilidad.asiento
                    WHERE rubro_id IS NOT NULL
                    GROUP BY rubro_id
                ) a ON a.rubro_id = r.id
                {where_sql}
                ORDER BY r.activo DESC, r.codigo ASC
                """,
                params
            )

        data = []
        for row in rows:
            usos_pago = int(row['usos_pago'] or 0)
            usos_cobro = int(row['usos_cobro'] or 0)
            usos_asiento = int(row['usos_asiento'] or 0)

            data.append({
                'id': row['id'],
                'codigo': row['codigo'],
                'nombre': row['nombre'],
                'descripcion': row['descripcion'] or '',
                'activo': bool(row['activo']),
                'usos_pago': usos_pago,
                'usos_cobro': usos_cobro,
                'usos_asiento': usos_asiento,
                'usos_total': usos_pago + usos_cobro + usos_asiento,
                'creado_en': row['creado_en'].isoformat() if row.get('creado_en') else None,
                'actualizado_en': row['actualizado_en'].isoformat() if row.get('actualizado_en') else None,
            })

        return jsonify({
            'data': data,
            'estado': estado
        })

    except Exception as exc:
        return jsonify({
            'data': [],
            'success': False,
            'message': f'No se pudo cargar la lista de rubros: {exc}'
        }), 500

@rubro_bp.route('/api/<int:rubro_id>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_obtener(rubro_id):
    try:
        with DatabaseManager() as db:
            rubro = _obtener_rubro(db, rubro_id)
            if not rubro:
                return _json_error('El rubro no existe.', status=404)

            dependencias = _dependencias_rubro(db, rubro_id)
            rubro['dependencias'] = dependencias

        return _json_ok(data=rubro)
    except Exception as exc:
        return _json_error(f'No se pudo obtener el rubro. {exc}', status=500)


@rubro_bp.route('/api/crear', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_crear():
    data = request.get_json() or {}

    try:
        payload = _validar_payload(data)

        with DatabaseManager() as db:
            rubro_id = db.execute_insert(
                """
                INSERT INTO contabilidad.rubro_operacion (
                    codigo,
                    nombre,
                    descripcion,
                    activo,
                    actualizado_en
                ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                ('__PENDIENTE__', payload['nombre'], payload['descripcion'], payload['activo']),
                return_id=True,
            )

            if not rubro_id:
                raise ValueError('No se pudo crear el rubro.')

            codigo = _siguiente_codigo(rubro_id)

            db.execute_update(
                """
                UPDATE contabilidad.rubro_operacion
                SET
                    codigo = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (codigo, rubro_id),
            )

        return _json_ok(
            message=f'Rubro creado correctamente con código {codigo}.',
            rubro_id=rubro_id,
            codigo=codigo,
        )

    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo crear el rubro. {exc}', status=500)


@rubro_bp.route('/api/editar/<int:rubro_id>', methods=['PUT'])
@login_required
@roles_required(ROLES_EDICION)
def api_editar(rubro_id):
    data = request.get_json() or {}

    try:
        payload = _validar_payload(data, rubro_id=rubro_id)

        with DatabaseManager() as db:
            rubro = _obtener_rubro(db, rubro_id)
            if not rubro:
                return _json_error('El rubro no existe.', status=404)

            updated = db.execute_update(
                """
                UPDATE contabilidad.rubro_operacion
                SET
                    nombre = %s,
                    descripcion = %s,
                    activo = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    payload['nombre'],
                    payload['descripcion'],
                    payload['activo'],
                    rubro_id,
                ),
            )

            if not updated:
                return _json_error('No se pudo actualizar el rubro.', status=400)

        return _json_ok(message='Rubro actualizado correctamente.')

    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo actualizar el rubro. {exc}', status=500)


@rubro_bp.route('/api/toggle-activo/<int:rubro_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_toggle_activo(rubro_id):
    try:
        with DatabaseManager() as db:
            rubro = _obtener_rubro(db, rubro_id)
            if not rubro:
                return _json_error('El rubro no existe.', status=404)

            nuevo_estado = not bool(rubro['activo'])

            if not nuevo_estado:
                dependencias = _dependencias_rubro(db, rubro_id)
                if dependencias['total'] > 0:
                    return _json_error(
                        'No se puede desactivar el rubro porque ya está siendo usado en pagos, cobros o comprobantes.',
                        status=409
                    )

            updated = db.execute_update(
                """
                UPDATE contabilidad.rubro_operacion
                SET
                    activo = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (nuevo_estado, rubro_id),
            )

            if not updated:
                return _json_error('No se pudo actualizar el estado del rubro.', status=400)

        accion = 'activado' if nuevo_estado else 'desactivado'
        return _json_ok(message=f'Rubro {accion} correctamente.')

    except Exception as exc:
        return _json_error(f'No se pudo actualizar el estado del rubro. {exc}', status=500)