import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request, session, url_for
from utils.decorators import login_required
from database.db import get_db

backups_gestion_bp = Blueprint(
    'backups_gestion',
    __name__,
    url_prefix='/contabilidad/backups-gestion',
    template_folder='templates',
)


def _json_error(message, status=400, detail=None):
    payload = {'ok': False, 'msg': message}
    if detail:
        payload['detail'] = detail
    return jsonify(payload), status


def _get_backup_dir():
    env_dir = (os.getenv('CONTA_BACKUP_DIR') or '').strip()
    default_dir = r'F:\laragon\www\contabackup'
    backup_dir = env_dir or default_dir
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _resolve_pg_binary(binary_name):
    env_bin_dir = (os.getenv('PG_BIN_DIR') or '').strip()
    candidates = []

    if env_bin_dir:
        candidates.append(os.path.join(env_bin_dir, f'{binary_name}.exe'))
        candidates.append(os.path.join(env_bin_dir, binary_name))

    path_resolved = shutil.which(binary_name)
    if path_resolved:
        candidates.append(path_resolved)

    path_resolved_exe = shutil.which(f'{binary_name}.exe')
    if path_resolved_exe:
        candidates.append(path_resolved_exe)

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(
        f'No se encontró el ejecutable "{binary_name}". Configure PG_BIN_DIR o agregue PostgreSQL al PATH del servidor.'
    )


def _db_conn_info():
    return {
        'host': current_app.config.get('DB_HOST', 'localhost'),
        'port': str(current_app.config.get('DB_PORT', 5432)),
        'dbname': current_app.config.get('DB_NAME', 'dxtsys'),
        'user': current_app.config.get('DB_USER', 'postgres'),
        'password': current_app.config.get('DB_PASSWORD') or os.getenv('PGPASSWORD', ''),
    }


def _build_pg_dump_command(output_path):
    info = _db_conn_info()
    command = [
        _resolve_pg_binary('pg_dump'),
        '--file', output_path,
        '--host', info['host'],
        '--port', info['port'],
        '--username', info['user'],
        '--no-password',
        '--format=p',
        '--clean',
        '--if-exists',
        '--schema=contabilidad',
        '--verbose',
        info['dbname'],
    ]
    return command, info


def _build_psql_command(input_path):
    info = _db_conn_info()
    command = [
        _resolve_pg_binary('psql'),
        '--file', input_path,
        '--host', info['host'],
        '--port', info['port'],
        '--username', info['user'],
        '--no-password',
        '--dbname', info['dbname'],
        '--set', 'ON_ERROR_STOP=1',
    ]
    return command, info


def _run_command(command, password):
    env = os.environ.copy()
    if password:
        env['PGPASSWORD'] = password

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    if process.returncode != 0:
        stderr = (process.stderr or '').strip()
        stdout = (process.stdout or '').strip()
        detail = stderr or stdout or 'No se recibió detalle del proceso.'
        raise RuntimeError(detail)

    return {
        'stdout': (process.stdout or '').strip(),
        'stderr': (process.stderr or '').strip(),
    }


def _sanitize_filename(name):
    cleaned = (name or '').strip()
    cleaned = re.sub(r'\.sql$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', cleaned)
    cleaned = cleaned.strip('._-')
    return cleaned[:180]


def _suggest_filename():
    return f'contabilidad_{datetime.now().strftime("%Y%m%d_%H%M%S")}'


def _get_open_gestion():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado = 'ABIERTA'::contabilidad.estado_gestion_enum
        ORDER BY gestion DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    if row and row[0] is not None:
        return int(row[0])
    return datetime.now().year


def _current_user():
    return {
        'id': session.get('user_id'),
        'name': session.get('usuario_nombre') or session.get('username') or 'Usuario'
    }


def _hash_file(path):
    sha256 = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def _format_size(size):
    if size is None:
        return '—'
    size = int(size)
    if size < 1024:
        return f'{size} B'
    if size < 1024 ** 2:
        return f'{size / 1024:.2f} KB'
    if size < 1024 ** 3:
        return f'{size / (1024 ** 2):.2f} MB'
    return f'{size / (1024 ** 3):.2f} GB'


def _fetch_backups():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            id,
            gestion_origen,
            gestion_destino,
            tipo_respaldo,
            estado::text,
            nombre_archivo,
            ruta_archivo,
            hash_archivo,
            tamanio_bytes,
            usuario_id,
            usuario_nombre,
            fecha_generacion,
            observacion,
            detalle_json
        FROM contabilidad.esquema_backup_catalogo
        ORDER BY fecha_generacion DESC, id DESC
    """)
    rows = cur.fetchall()
    cur.close()

    items = []
    for row in rows:
        ruta = row[6]
        archivo_existe = bool(ruta and os.path.isfile(ruta))
        items.append({
            'id': row[0],
            'gestion_origen': row[1],
            'gestion_destino': row[2],
            'tipo_respaldo': row[3],
            'estado': row[4],
            'nombre_archivo': row[5],
            'ruta_archivo': ruta,
            'hash_archivo': row[7],
            'tamanio_bytes': row[8],
            'tamanio_label': _format_size(row[8]),
            'usuario_id': row[9],
            'usuario_nombre': row[10],
            'fecha_generacion': row[11],
            'fecha_generacion_label': row[11].strftime('%d/%m/%Y %H:%M:%S') if row[11] else '—',
            'observacion': row[12],
            'detalle_json': row[13],
            'archivo_existe': archivo_existe,
        })
    return items


def _registrar_invalidacion_global(usuario_nombre):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE contabilidad.sistema_control_sesion
        SET
            forzar_relogin_desde = CURRENT_TIMESTAMP,
            actualizado_en = CURRENT_TIMESTAMP,
            actualizado_por = %s
        WHERE id = 1
    """, (usuario_nombre,))
    conn.commit()
    cur.close()


def _build_restore_input(original_path):
    """
    Prepara un SQL seguro para restaurar solo el esquema contabilidad.

    Corrige backups antiguos generados con --create, eliminando sentencias
    de base de datos completa que no corresponden a un restore parcial.
    """
    temp_fd, temp_path = tempfile.mkstemp(prefix='restore_contabilidad_', suffix='.sql')
    os.close(temp_fd)

    skip_patterns = (
        r'^CREATE DATABASE\b',
        r'^DROP DATABASE\b',
        r'^ALTER DATABASE\b',
        r'^\\connect\b',
    )

    with open(original_path, 'r', encoding='utf-8', errors='replace') as src, \
         open(temp_path, 'w', encoding='utf-8', newline='\n') as dst:
        for line in src:
            stripped = line.strip()
            upper = stripped.upper()

            if any(re.match(pattern, stripped, flags=re.IGNORECASE) for pattern in skip_patterns):
                continue

            if upper.startswith('-- Name: ') and 'DATABASE ' in upper:
                continue

            dst.write(line)

    return temp_path


@backups_gestion_bp.route('/')
@login_required
def index():
    return render_template(
        'backups_gestion_index.html',
        backups=_fetch_backups(),
        nombre_sugerido=_suggest_filename(),
        backup_dir_label=_get_backup_dir(),
    )


@backups_gestion_bp.route('/help')
@login_required
def help():
    return render_template('backups_gestion_help.html')


@backups_gestion_bp.route('/generar', methods=['POST'])
@login_required
def generar_backup():
    payload = request.get_json(silent=True) or {}
    nombre = _sanitize_filename(payload.get('nombre_archivo'))
    observacion = (payload.get('observacion') or '').strip() or None

    if not nombre:
        return _json_error('Debe indicar el nombre del archivo de backup.')

    nombre_archivo = f'{nombre}.sql'
    backup_dir = _get_backup_dir()
    output_path = os.path.join(backup_dir, nombre_archivo)

    if os.path.exists(output_path):
        return _json_error('Ya existe un archivo con ese nombre en el directorio de backups.', 409)

    command, info = _build_pg_dump_command(output_path)
    execution = _run_command(command, info['password'])

    if not os.path.isfile(output_path):
        return _json_error('El proceso finalizó, pero no se encontró el archivo generado.', 500)

    tamanio_bytes = os.path.getsize(output_path)
    hash_archivo = _hash_file(output_path)
    gestion_origen = _get_open_gestion()
    user = _current_user()

    detalle_json = json.dumps({
        'command': command,
        'stdout': execution['stdout'],
        'stderr': execution['stderr'],
        'directorio': backup_dir,
    }, ensure_ascii=False)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contabilidad.esquema_backup_catalogo (
            gestion_origen,
            gestion_destino,
            tipo_respaldo,
            estado,
            nombre_archivo,
            ruta_archivo,
            hash_archivo,
            tamanio_bytes,
            usuario_id,
            usuario_nombre,
            observacion,
            detalle_json
        )
        VALUES (
            %s, NULL, 'MANUAL', 'GENERADO'::contabilidad.estado_backup_esquema_enum,
            %s, %s, %s, %s, %s, %s, %s, %s::jsonb
        )
        RETURNING id
    """, (
        gestion_origen,
        nombre_archivo,
        output_path,
        hash_archivo,
        tamanio_bytes,
        user['id'],
        user['name'],
        observacion,
        detalle_json,
    ))
    backup_id = cur.fetchone()[0]
    conn.commit()
    cur.close()

    return jsonify({
        'ok': True,
        'msg': 'El backup se generó correctamente.',
        'backup_id': backup_id,
        'ruta_archivo': output_path,
    })


@backups_gestion_bp.route('/restaurar', methods=['POST'])
@login_required
def restaurar_backup():
    payload = request.get_json(silent=True) or {}
    backup_id = payload.get('backup_id')
    motivo = (payload.get('motivo') or '').strip()

    if not backup_id:
        return _json_error('Debe seleccionar un backup para restaurar.')

    if not motivo:
        return _json_error('Debe registrar el motivo de la restauración.')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            id, gestion_origen, gestion_destino, nombre_archivo, ruta_archivo
        FROM contabilidad.esquema_backup_catalogo
        WHERE id = %s
    """, (backup_id,))
    backup = cur.fetchone()

    if not backup:
        cur.close()
        return _json_error('El backup seleccionado no existe.', 404)

    ruta_archivo = backup[4]
    if not ruta_archivo or not os.path.isfile(ruta_archivo):
        cur.close()
        return _json_error('El archivo físico del backup no fue encontrado.', 404)

    user = _current_user()

    cur.execute("""
        INSERT INTO contabilidad.esquema_restauracion_log (
            backup_id,
            estado,
            gestion_origen,
            gestion_destino,
            usuario_id,
            usuario_nombre,
            motivo,
            detalle_json
        )
        VALUES (
            %s,
            'PARCIAL'::contabilidad.estado_restauracion_esquema_enum,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s::jsonb
        )
        RETURNING id
    """, (
        backup[0],
        backup[1],
        backup[2],
        user['id'],
        user['name'],
        motivo,
        json.dumps({'archivo': ruta_archivo}, ensure_ascii=False),
    ))
    restore_id = cur.fetchone()[0]
    conn.commit()

    restore_input_path = None

    try:
        restore_input_path = _build_restore_input(ruta_archivo)
        command, info = _build_psql_command(restore_input_path)
        execution = _run_command(command, info['password'])

        cur.execute("""
            UPDATE contabilidad.esquema_restauracion_log
            SET
                estado = 'EJECUTADA'::contabilidad.estado_restauracion_esquema_enum,
                fecha_hora_fin = CURRENT_TIMESTAMP,
                detalle_json = %s::jsonb
            WHERE id = %s
        """, (
            json.dumps({
                'archivo': ruta_archivo,
                'archivo_restore': restore_input_path,
                'stdout': execution['stdout'],
                'stderr': execution['stderr'],
            }, ensure_ascii=False),
            restore_id,
        ))
        cur.execute("""
            UPDATE contabilidad.esquema_backup_catalogo
            SET estado = 'RESTAURADO'::contabilidad.estado_backup_esquema_enum
            WHERE id = %s
        """, (backup[0],))
        conn.commit()
    except Exception as exc:
        cur.execute("""
            UPDATE contabilidad.esquema_restauracion_log
            SET
                estado = 'FALLIDA'::contabilidad.estado_restauracion_esquema_enum,
                fecha_hora_fin = CURRENT_TIMESTAMP,
                detalle_json = %s::jsonb
            WHERE id = %s
        """, (
            json.dumps({
                'archivo': ruta_archivo,
                'archivo_restore': restore_input_path,
                'error': str(exc)
            }, ensure_ascii=False),
            restore_id,
        ))
        conn.commit()
        cur.close()
        return _json_error('No se pudo completar la restauración.', 500, str(exc))
    finally:
        if restore_input_path and os.path.isfile(restore_input_path):
            try:
                os.remove(restore_input_path)
            except Exception:
                pass

    cur.close()
    _registrar_invalidacion_global(user['name'])
    session.clear()

    return jsonify({
        'ok': True,
        'msg': 'La restauración se completó correctamente. El sistema volverá al login.',
        'redirect_url': url_for('auth.login'),
    })


@backups_gestion_bp.route('/eliminar', methods=['POST'])
@login_required
def eliminar_backup():
    payload = request.get_json(silent=True) or {}
    backup_id = payload.get('backup_id')

    if not backup_id:
        return _json_error('Debe seleccionar un backup para eliminar.')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nombre_archivo, ruta_archivo
        FROM contabilidad.esquema_backup_catalogo
        WHERE id = %s
    """, (backup_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        return _json_error('El backup seleccionado no existe.', 404)

    cur.execute("""
        SELECT COUNT(*)
        FROM contabilidad.esquema_restauracion_log
        WHERE backup_id = %s
    """, (backup_id,))
    restore_count = cur.fetchone()[0]

    if restore_count and int(restore_count) > 0:
        cur.close()
        return _json_error(
            'No se puede eliminar el backup porque ya tiene restauraciones registradas.'
        )

    ruta_archivo = row[2]
    archivo_encontrado = bool(ruta_archivo and os.path.isfile(ruta_archivo))

    if archivo_encontrado:
        try:
            os.remove(ruta_archivo)
        except Exception as exc:
            cur.close()
            return _json_error(
                'No se pudo eliminar el archivo físico del backup.',
                500,
                str(exc),
            )

    cur.execute("""
        DELETE FROM contabilidad.esquema_backup_catalogo
        WHERE id = %s
    """, (backup_id,))
    conn.commit()
    cur.close()

    mensaje = 'El backup se eliminó correctamente.'
    if not archivo_encontrado:
        mensaje += ' El archivo físico ya no existía, pero el registro fue retirado del catálogo.'

    return jsonify({'ok': True, 'msg': mensaje})
