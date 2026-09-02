from flask import current_app, render_template, request, jsonify
from pathlib import Path
from uuid import uuid4

from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename

from utils.db import execute_query, execute_query_one, get_db_connection
from utils.decorators import login_required

from modules.unidad_negocio import unidad_negocio_bp


VINCULACION_PUBLICIDAD = 'PUBLICIDAD'
CAMPO_PUBLICIDAD = 'publicidad.estructura_publicitaria.unidad_negocio_id'

ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def _request_data():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict() or {}


def _logo_folder() -> Path:
    folder = current_app.config.get('LOGO_FOLDER')
    if not folder:
        folder = Path(current_app.config['DXT_CONTA_DATA_DIR']) / 'logo'
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _data_dir() -> Path:
    return Path(current_app.config['DXT_CONTA_DATA_DIR'])


def _logo_relative_path(filename: str) -> str:
    return str(Path('logo') / filename).replace('\\', '/')


def _logo_absolute_path(ruta_relativa: str | None) -> Path | None:
    if not ruta_relativa:
        return None
    return (_data_dir() / ruta_relativa).resolve()


def _validar_logo(file_storage):
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return None
    filename = secure_filename(file_storage.filename or '')
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        return 'El logo debe ser PNG, JPG, JPEG o WEBP.'
    return None


def _guardar_logo(file_storage, codigo: str):
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return None
    filename_original = secure_filename(file_storage.filename or '')
    ext = filename_original.rsplit('.', 1)[-1].lower()
    filename = f'unidad_{codigo}_{uuid4().hex[:10]}.{ext}'
    destino = _logo_folder() / filename
    file_storage.save(destino)
    return {
        'logo_ruta': _logo_relative_path(filename),
        'logo_nombre_original': filename_original,
    }


def _eliminar_logo_anterior(ruta_relativa: str | None):
    path = _logo_absolute_path(ruta_relativa)
    if not path:
        return
    try:
        logo_root = _logo_folder().resolve()
        if path.exists() and logo_root in path.parents:
            path.unlink()
    except Exception:
        pass


class UnidadNegocioError(Exception):
    pass


def _clean(value):
    return (value or '').strip()


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'sí', 'on')


def _normalize_nit(value):
    nit = _clean(value)
    return nit or None


def _normalize_vinculacion(value):
    vinc = _clean(value).upper()
    if vinc in ('', 'NINGUNO', 'NONE', 'NULL'):
        return None
    if vinc == VINCULACION_PUBLICIDAD:
        return VINCULACION_PUBLICIDAD
    return '__INVALID__'


def _campo_para_vinculacion(vinculacion):
    if vinculacion == VINCULACION_PUBLICIDAD:
        return CAMPO_PUBLICIDAD
    return None


def _validar_payload(data):
    nombre = _clean(data.get('nombre'))
    nit = _normalize_nit(data.get('nit'))
    activo = _parse_bool(data.get('activo', True))
    vinculacion = _normalize_vinculacion(data.get('vinculacion'))

    if not nombre:
        return None, 'El nombre es obligatorio.'

    if len(nombre) > 150:
        return None, 'El nombre no puede exceder 150 caracteres.'

    if nit and len(nit) > 50:
        return None, 'El NIT no puede exceder 50 caracteres.'

    if vinculacion == '__INVALID__':
        return None, 'La vinculación seleccionada no es válida.'

    if vinculacion == VINCULACION_PUBLICIDAD and not activo:
        return None, 'Una unidad vinculada a Publicidad debe estar activa.'

    payload = {
        'nombre': nombre,
        'nit': nit,
        'activo': activo,
        'vinculacion': vinculacion,
        'campo_vinculacion': _campo_para_vinculacion(vinculacion),
    }
    return payload, None


def _unidad_vinculacion_columns_status():
    row = execute_query_one(
        """
        SELECT COUNT(*)::int AS columnas
        FROM information_schema.columns
        WHERE table_schema = 'contabilidad'
          AND table_name = 'unidad_negocio'
          AND column_name IN ('vinculacion', 'campo_vinculacion')
        """
    ) or {}
    return int(row.get('columnas') or 0) == 2


def _publicidad_tables_status():
    row = execute_query_one(
        """
        SELECT
            to_regclass('publicidad.estructura_publicitaria')::text AS estructura_table,
            to_regclass('publicidad.elemento_publicitario')::text AS elemento_table
        """
    ) or {}
    return {
        'estructura': bool(row.get('estructura_table')),
        'elemento': bool(row.get('elemento_table')),
    }


def _publicidad_summary_for_unidad(unidad_id):
    status = _publicidad_tables_status()
    if not status['estructura']:
        return {
            'publicidad_disponible': False,
            'publicidad_estructuras': 0,
            'publicidad_elementos': 0,
        }

    if status['elemento']:
        row = execute_query_one(
            """
            SELECT
                COUNT(DISTINCT s.id)::int AS estructuras,
                COUNT(DISTINCT e.id)::int AS elementos
            FROM publicidad.estructura_publicitaria s
            LEFT JOIN publicidad.elemento_publicitario e ON e.estructura_id = s.id
            WHERE s.unidad_negocio_id = %s
            """,
            (unidad_id,)
        ) or {}
    else:
        row = execute_query_one(
            """
            SELECT
                COUNT(DISTINCT s.id)::int AS estructuras,
                0::int AS elementos
            FROM publicidad.estructura_publicitaria s
            WHERE s.unidad_negocio_id = %s
            """,
            (unidad_id,)
        ) or {}

    return {
        'publicidad_disponible': True,
        'publicidad_estructuras': int(row.get('estructuras') or 0),
        'publicidad_elementos': int(row.get('elementos') or 0),
    }


def _publicidad_count_for_unidad(unidad_id):
    return _publicidad_summary_for_unidad(unidad_id)['publicidad_estructuras']


def _fetchone(cursor, query, params=None):
    cursor.execute(query, params or ())
    row = cursor.fetchone()
    return dict(row) if row else None


def _fetch_publicidad_status_cursor(cursor):
    cursor.execute(
        """
        SELECT
            to_regclass('publicidad.estructura_publicitaria')::text AS estructura_table,
            to_regclass('publicidad.elemento_publicitario')::text AS elemento_table
        """
    )
    row = cursor.fetchone() or {}
    return {
        'estructura': bool(row.get('estructura_table')),
        'elemento': bool(row.get('elemento_table')),
    }


def _sincronizar_vinculacion_cursor(cursor, unidad_id, vinculacion, estaba_vinculada_publicidad=False):
    if vinculacion == VINCULACION_PUBLICIDAD:
        status = _fetch_publicidad_status_cursor(cursor)
        if not status['estructura']:
            raise UnidadNegocioError(
                'No existe la tabla publicidad.estructura_publicitaria en la base de datos actual.'
            )

        cursor.execute(
            """
            UPDATE contabilidad.unidad_negocio
            SET
                vinculacion = NULL,
                campo_vinculacion = NULL,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id <> %s
              AND UPPER(COALESCE(vinculacion, '')) = %s
            """,
            (unidad_id, VINCULACION_PUBLICIDAD)
        )

        cursor.execute(
            """
            UPDATE contabilidad.unidad_negocio
            SET
                vinculacion = %s,
                campo_vinculacion = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (VINCULACION_PUBLICIDAD, CAMPO_PUBLICIDAD, unidad_id)
        )

        cursor.execute(
            """
            UPDATE publicidad.estructura_publicitaria
            SET unidad_negocio_id = %s
            WHERE unidad_negocio_id IS DISTINCT FROM %s
            """,
            (unidad_id, unidad_id)
        )
        return cursor.rowcount

    if estaba_vinculada_publicidad:
        status = _fetch_publicidad_status_cursor(cursor)
        if status['estructura']:
            cursor.execute(
                """
                SELECT COUNT(*)::int AS total
                FROM publicidad.estructura_publicitaria
                WHERE unidad_negocio_id = %s
                """,
                (unidad_id,)
            )
            row = cursor.fetchone() or {}
            total = int(row.get('total') or 0)
            if total > 0:
                raise UnidadNegocioError(
                    'Publicidad no puede quedar sin unidad de negocio vinculada. '
                    'Seleccione Publicidad en otra unidad activa para mover la vinculación.'
                )

    cursor.execute(
        """
        UPDATE contabilidad.unidad_negocio
        SET
            vinculacion = NULL,
            campo_vinculacion = NULL,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (unidad_id,)
    )
    return 0


@unidad_negocio_bp.route('/')
@login_required
def index():
    return render_template('unidad_negocio_index.html')


@unidad_negocio_bp.route('/help')
@login_required
def help():
    return render_template('unidad_negocio_help.html')


@unidad_negocio_bp.route('/data')
@login_required
def data():
    status = _publicidad_tables_status()
    tiene_vinculacion = _unidad_vinculacion_columns_status()

    if tiene_vinculacion:
        vinculacion_select = "un.vinculacion, un.campo_vinculacion"
    else:
        vinculacion_select = "NULL::varchar AS vinculacion, NULL::varchar AS campo_vinculacion"

    if status['estructura'] and status['elemento']:
        rows = execute_query(
            f"""
            SELECT
                un.id,
                un.codigo,
                un.nombre,
                un.nit,
                un.activo,
                un.logo_ruta,
                un.logo_nombre_original,
                {vinculacion_select},
                TRUE AS publicidad_disponible,
                COALESCE(pub.estructuras, 0)::int AS publicidad_estructuras,
                COALESCE(pub.elementos, 0)::int AS publicidad_elementos
            FROM contabilidad.unidad_negocio un
            LEFT JOIN (
                SELECT
                    s.unidad_negocio_id,
                    COUNT(DISTINCT s.id)::int AS estructuras,
                    COUNT(DISTINCT e.id)::int AS elementos
                FROM publicidad.estructura_publicitaria s
                LEFT JOIN publicidad.elemento_publicitario e ON e.estructura_id = s.id
                GROUP BY s.unidad_negocio_id
            ) pub ON pub.unidad_negocio_id = un.id
            ORDER BY un.codigo ASC, un.id ASC
            """,
            fetchall=True
        )
    elif status['estructura']:
        rows = execute_query(
            f"""
            SELECT
                un.id,
                un.codigo,
                un.nombre,
                un.nit,
                un.activo,
                un.logo_ruta,
                un.logo_nombre_original,
                {vinculacion_select},
                TRUE AS publicidad_disponible,
                COALESCE(pub.estructuras, 0)::int AS publicidad_estructuras,
                0::int AS publicidad_elementos
            FROM contabilidad.unidad_negocio un
            LEFT JOIN (
                SELECT
                    s.unidad_negocio_id,
                    COUNT(DISTINCT s.id)::int AS estructuras
                FROM publicidad.estructura_publicitaria s
                GROUP BY s.unidad_negocio_id
            ) pub ON pub.unidad_negocio_id = un.id
            ORDER BY un.codigo ASC, un.id ASC
            """,
            fetchall=True
        )
    else:
        rows = execute_query(
            f"""
            SELECT
                id,
                codigo,
                nombre,
                nit,
                activo,
                logo_ruta,
                logo_nombre_original,
                {vinculacion_select},
                FALSE AS publicidad_disponible,
                0::int AS publicidad_estructuras,
                0::int AS publicidad_elementos
            FROM contabilidad.unidad_negocio un
            ORDER BY codigo ASC, id ASC
            """,
            fetchall=True
        )

    for row in rows:
        row['vinculacion'] = _normalize_vinculacion(row.get('vinculacion'))
        if row['vinculacion'] == '__INVALID__':
            row['vinculacion'] = None
        row['campo_vinculacion'] = row.get('campo_vinculacion') or _campo_para_vinculacion(row['vinculacion'])
        row['vinculacion_columnas_ok'] = tiene_vinculacion

    return jsonify({'data': rows})


@unidad_negocio_bp.route('/obtener/<int:registro_id>')
@login_required
def obtener(registro_id):
    tiene_vinculacion = _unidad_vinculacion_columns_status()
    if tiene_vinculacion:
        vinculacion_select = "vinculacion, campo_vinculacion"
    else:
        vinculacion_select = "NULL::varchar AS vinculacion, NULL::varchar AS campo_vinculacion"

    row = execute_query_one(
        f"""
        SELECT
            id,
            codigo,
            nombre,
            nit,
            activo,
            logo_ruta,
            logo_nombre_original,
            {vinculacion_select}
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )

    if not row:
        return jsonify({'ok': False, 'msg': 'La unidad de negocio no existe.'}), 404

    row['vinculacion'] = _normalize_vinculacion(row.get('vinculacion'))
    if row['vinculacion'] == '__INVALID__':
        row['vinculacion'] = None
    row['campo_vinculacion'] = row.get('campo_vinculacion') or _campo_para_vinculacion(row['vinculacion'])
    row.update(_publicidad_summary_for_unidad(registro_id))
    return jsonify({'ok': True, 'data': row})


@unidad_negocio_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    data = _request_data()
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    logo_file = request.files.get('logo_archivo')
    logo_error = _validar_logo(logo_file)
    if logo_error:
        return jsonify({'ok': False, 'msg': logo_error}), 400

    tiene_vinculacion = _unidad_vinculacion_columns_status()
    if payload['vinculacion'] and not tiene_vinculacion:
        return jsonify({
            'ok': False,
            'msg': 'Faltan los campos vinculacion y campo_vinculacion. Ejecute primero el script SQL incluido.'
        }), 400

    if payload['nit']:
        existe_nit = execute_query_one(
            """
            SELECT id
            FROM contabilidad.unidad_negocio
            WHERE TRIM(COALESCE(nit, '')) = TRIM(%s)
            LIMIT 1
            """,
            (payload['nit'],)
        )
        if existe_nit:
            return jsonify({'ok': False, 'msg': f'Ya existe una unidad de negocio con NIT "{payload["nit"]}".'}), 409

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            INSERT INTO contabilidad.unidad_negocio (
                codigo,
                nombre,
                nit,
                activo,
                actualizado_en
            )
            VALUES ('__PENDIENTE__', %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (payload['nombre'], payload['nit'], payload['activo'])
        )
        nuevo = cursor.fetchone()
        if not nuevo or not nuevo.get('id'):
            raise UnidadNegocioError('No se pudo generar el registro de unidad de negocio.')

        nuevo_id = int(nuevo['id'])
        codigo_generado = f'UN{nuevo_id:04d}'

        cursor.execute(
            """
            UPDATE contabilidad.unidad_negocio
            SET
                codigo = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (codigo_generado, nuevo_id)
        )

        logo_info = _guardar_logo(logo_file, codigo_generado) if logo_file else None
        if logo_info:
            cursor.execute(
                """
                UPDATE contabilidad.unidad_negocio
                SET logo_ruta = %s,
                    logo_nombre_original = %s,
                    logo_actualizado_en = CURRENT_TIMESTAMP,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (logo_info['logo_ruta'], logo_info['logo_nombre_original'], nuevo_id)
            )

        estructuras_actualizadas = 0
        if tiene_vinculacion:
            estructuras_actualizadas = _sincronizar_vinculacion_cursor(
                cursor,
                nuevo_id,
                payload['vinculacion'],
                estaba_vinculada_publicidad=False,
            )

        conn.commit()
    except UnidadNegocioError as exc:
        if conn:
            conn.rollback()
        return jsonify({'ok': False, 'msg': str(exc)}), 400
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    msg = f'Unidad de negocio creada correctamente con código {codigo_generado}.'
    if payload['vinculacion'] == VINCULACION_PUBLICIDAD:
        msg += f' Publicidad quedó vinculada a esta unidad. Estructuras actualizadas: {estructuras_actualizadas}.'

    return jsonify({
        'ok': True,
        'msg': msg,
        'data': {'id': nuevo_id, 'codigo': codigo_generado}
    })


@unidad_negocio_bp.route('/editar/<int:registro_id>', methods=['PUT'])
@login_required
def editar(registro_id):
    tiene_vinculacion = _unidad_vinculacion_columns_status()
    if tiene_vinculacion:
        actual_select = "id, codigo, activo, vinculacion, logo_ruta"
    else:
        actual_select = "id, codigo, activo, NULL::varchar AS vinculacion, logo_ruta"

    actual = execute_query_one(
        f"""
        SELECT {actual_select}
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not actual:
        return jsonify({'ok': False, 'msg': 'La unidad de negocio no existe.'}), 404

    data = _request_data()
    payload, error = _validar_payload(data)

    if error:
        return jsonify({'ok': False, 'msg': error}), 400

    logo_file = request.files.get('logo_archivo')
    logo_error = _validar_logo(logo_file)
    if logo_error:
        return jsonify({'ok': False, 'msg': logo_error}), 400

    if payload['vinculacion'] and not tiene_vinculacion:
        return jsonify({
            'ok': False,
            'msg': 'Faltan los campos vinculacion y campo_vinculacion. Ejecute primero el script SQL incluido.'
        }), 400

    estaba_publicidad = _normalize_vinculacion(actual.get('vinculacion')) == VINCULACION_PUBLICIDAD

    if actual['codigo'] == 'BASE' and payload['activo'] is False:
        return jsonify({'ok': False, 'msg': 'La unidad BASE no puede desactivarse.'}), 400

    if estaba_publicidad and payload['activo'] is False:
        return jsonify({
            'ok': False,
            'msg': 'No se puede desactivar una unidad vinculada a Publicidad. Primero vincule Publicidad con otra unidad activa.'
        }), 400

    if payload['nit']:
        existe_nit = execute_query_one(
            """
            SELECT id
            FROM contabilidad.unidad_negocio
            WHERE TRIM(COALESCE(nit, '')) = TRIM(%s)
              AND id <> %s
            LIMIT 1
            """,
            (payload['nit'], registro_id)
        )
        if existe_nit:
            return jsonify({'ok': False, 'msg': f'Ya existe otra unidad de negocio con NIT "{payload["nit"]}".'}), 409

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            UPDATE contabilidad.unidad_negocio
            SET
                nombre = %s,
                nit = %s,
                activo = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (payload['nombre'], payload['nit'], payload['activo'], registro_id)
        )

        logo_info = _guardar_logo(logo_file, actual['codigo']) if logo_file else None
        if logo_info:
            cursor.execute(
                """
                UPDATE contabilidad.unidad_negocio
                SET logo_ruta = %s,
                    logo_nombre_original = %s,
                    logo_actualizado_en = CURRENT_TIMESTAMP,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (logo_info['logo_ruta'], logo_info['logo_nombre_original'], registro_id)
            )

        estructuras_actualizadas = 0
        if tiene_vinculacion:
            estructuras_actualizadas = _sincronizar_vinculacion_cursor(
                cursor,
                registro_id,
                payload['vinculacion'],
                estaba_vinculada_publicidad=estaba_publicidad,
            )

        conn.commit()
    except UnidadNegocioError as exc:
        if conn:
            conn.rollback()
        return jsonify({'ok': False, 'msg': str(exc)}), 400
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if logo_file:
        _eliminar_logo_anterior(actual.get('logo_ruta'))

    msg = 'Unidad de negocio actualizada correctamente.'
    if payload['vinculacion'] == VINCULACION_PUBLICIDAD:
        msg += f' Publicidad quedó vinculada a esta unidad. Estructuras actualizadas: {estructuras_actualizadas}.'

    return jsonify({'ok': True, 'msg': msg})


@unidad_negocio_bp.route('/toggle-activo/<int:registro_id>', methods=['POST'])
@login_required
def toggle_activo(registro_id):
    tiene_vinculacion = _unidad_vinculacion_columns_status()
    if tiene_vinculacion:
        actual_select = "id, codigo, activo, vinculacion"
    else:
        actual_select = "id, codigo, activo, NULL::varchar AS vinculacion"

    row = execute_query_one(
        f"""
        SELECT {actual_select}
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (registro_id,)
    )
    if not row:
        return jsonify({'ok': False, 'msg': 'La unidad de negocio no existe.'}), 404

    nuevo_estado = not bool(row['activo'])
    vinculacion_actual = _normalize_vinculacion(row.get('vinculacion'))

    if row['codigo'] == 'BASE' and not nuevo_estado:
        return jsonify({'ok': False, 'msg': 'La unidad BASE no puede desactivarse.'}), 400

    if vinculacion_actual == VINCULACION_PUBLICIDAD and not nuevo_estado:
        return jsonify({
            'ok': False,
            'msg': 'No se puede desactivar una unidad vinculada a Publicidad. Primero vincule Publicidad con otra unidad activa.'
        }), 400

    execute_query(
        """
        UPDATE contabilidad.unidad_negocio
        SET
            activo = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (nuevo_estado, registro_id)
    )

    mensaje = (
        'Unidad de negocio activada correctamente.'
        if nuevo_estado
        else 'Unidad de negocio desactivada correctamente. Sus registros históricos se conservan.'
    )

    return jsonify({'ok': True, 'msg': mensaje})
