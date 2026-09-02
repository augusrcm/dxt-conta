from datetime import datetime
from flask import flash, Blueprint, jsonify, redirect, render_template, request, session, url_for

from database.db_manager import DatabaseManager
from utils.decorators import login_required, roles_required

configuracion_inicial_bp = Blueprint(
    'configuracion_inicial',
    __name__,
    url_prefix='/configuracion-inicial',
    template_folder='templates',
)

ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]


DEFAULTS_CONFIG = {
    'glosa_cierre': 'CIERRE DE GESTIÓN',
    'glosa_apertura': 'APERTURA DE GESTIÓN',
    'permitir_reapertura': True,
    'bloquear_si_hay_borradores': True,
    'bloquear_si_hay_movimientos_destino': True,
}


def _usuario_actual():
    return (
        session.get('nombre')
        or session.get('correo')
        or session.get('ci_nit')
        or 'Sistema'
    )



def _valor_bool(nombre, default=False):
    valor = request.form.get(nombre)
    if valor is None:
        return default
    return str(valor).strip().lower() in {'1', 'true', 'on', 'si', 'sí'}



def _clean(value):
    return (value or '').strip()



def _obtener_configuracion_activa(db):
    filas = db.execute_query(
        """
        SELECT
            id,
            activo,
            cuenta_resultado_ejercicio_codigo,
            glosa_cierre,
            glosa_apertura,
            permitir_reapertura,
            bloquear_si_hay_borradores,
            bloquear_si_hay_movimientos_destino,
            creado_en,
            actualizado_en
        FROM contabilidad.gestion_configuracion
        WHERE activo = TRUE
        ORDER BY id DESC
        LIMIT 1
        """
    )
    return filas[0] if filas else None



def _obtener_gestiones_control(db):
    return db.execute_query(
        """
        SELECT
            gestion,
            estado,
            fecha_cierre,
            fecha_apertura,
            creado_en,
            actualizado_en
        FROM contabilidad.gestion_control
        ORDER BY gestion ASC
        """
    )



def _obtener_unidades_negocio(db):
    return db.execute_query(
        """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(nit, '') AS nit,
            activo,
            creado_en,
            actualizado_en
        FROM contabilidad.unidad_negocio
        ORDER BY id ASC
        """
    )



def _generar_codigo_unidad(unidad_id):
    return f'UN{int(unidad_id):04d}'



def _crear_unidad_negocio_inicial(db, nombre, nit):
    nombre = _clean(nombre)
    nit = _clean(nit) or None

    if not nombre:
        raise ValueError('Debe registrar el nombre de la primera unidad de negocio.')

    if len(nombre) > 150:
        raise ValueError('El nombre de la unidad de negocio no puede exceder 150 caracteres.')

    if nit and len(nit) > 50:
        raise ValueError('El NIT de la unidad de negocio no puede exceder 50 caracteres.')

    existe = db.execute_query(
        """
        SELECT id
        FROM contabilidad.unidad_negocio
        LIMIT 1
        """
    )
    if existe:
        return None

    if nit:
        nit_existente = db.execute_query(
            """
            SELECT id
            FROM contabilidad.unidad_negocio
            WHERE TRIM(COALESCE(nit, '')) = TRIM(%s)
            LIMIT 1
            """,
            (nit,),
        )
        if nit_existente:
            raise ValueError(f'Ya existe una unidad de negocio con NIT "{nit}".')

    nuevo_id = db.execute_insert(
        """
        INSERT INTO contabilidad.unidad_negocio (
            codigo,
            nombre,
            nit,
            activo,
            actualizado_en
        ) VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP)
        """,
        ('__PENDIENTE__', nombre, nit),
        return_id=True,
    )

    if not nuevo_id:
        raise ValueError('No se pudo crear la primera unidad de negocio.')

    codigo = _generar_codigo_unidad(nuevo_id)
    db.execute_update(
        """
        UPDATE contabilidad.unidad_negocio
        SET codigo = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (codigo, nuevo_id),
    )

    return {
        'id': nuevo_id,
        'codigo': codigo,
        'nombre': nombre,
        'nit': nit or '',
    }



def obtener_estado_inicializacion():
    with DatabaseManager() as db:
        configuracion = _obtener_configuracion_activa(db)
        gestiones = _obtener_gestiones_control(db)
        unidades = _obtener_unidades_negocio(db)

        gestion_abierta = None
        for fila in gestiones:
            if str(fila['estado']) == 'ABIERTA':
                gestion_abierta = fila
                break

        primera_unidad = unidades[0] if unidades else None
        initialized = configuracion is not None and gestion_abierta is not None and primera_unidad is not None

        return {
            'initialized': initialized,
            'configuracion': configuracion,
            'gestiones': gestiones,
            'gestion_abierta': gestion_abierta,
            'unidades_negocio': unidades,
            'primera_unidad': primera_unidad,
            'faltantes': {
                'configuracion': configuracion is None,
                'gestion_abierta': gestion_abierta is None,
                'unidad_negocio': primera_unidad is None,
            },
        }



def obtener_gestion_operativa_actual():
    estado = obtener_estado_inicializacion()
    gestion_abierta = estado.get('gestion_abierta')
    if gestion_abierta:
        return int(gestion_abierta['gestion'])
    return None



def _obtener_cuenta_patrimonial(db, codigo):
    filas = db.execute_query(
        """
        SELECT codigo, nombre, tipo, es_postable, activo
        FROM contabilidad.cuenta
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,),
    )
    return filas[0] if filas else None



def _validar_cuenta_patrimonial(db, codigo):
    cuenta = _obtener_cuenta_patrimonial(db, codigo)
    if not cuenta:
        raise ValueError('La cuenta patrimonial seleccionada no existe.')
    if not bool(cuenta['activo']):
        raise ValueError('La cuenta patrimonial seleccionada no está activa.')
    if not bool(cuenta['es_postable']):
        raise ValueError('La cuenta patrimonial seleccionada debe ser postable.')
    if str(cuenta['tipo']) != 'PATRIMONIO':
        raise ValueError('La cuenta seleccionada debe ser de tipo PATRIMONIO.')
    return cuenta


@configuracion_inicial_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    estado = obtener_estado_inicializacion()

    with DatabaseManager() as db:
        configuracion = estado.get('configuracion') or DEFAULTS_CONFIG.copy()
        if estado.get('configuracion'):
            configuracion = dict(estado['configuracion'])

        cuenta_actual = None
        codigo_actual = configuracion.get('cuenta_resultado_ejercicio_codigo')
        if codigo_actual:
            cuenta_actual = _obtener_cuenta_patrimonial(db, codigo_actual)

    gestion_sugerida = datetime.now().year
    if estado.get('gestion_abierta'):
        gestion_sugerida = int(estado['gestion_abierta']['gestion'])
    elif estado.get('gestiones'):
        gestion_sugerida = int(estado['gestiones'][0]['gestion'])

    puede_editar = int(session.get('rol_id') or 0) in ROLES_EDICION

    return render_template(
        'configuracion_inicial_index.html',
        estado_inicializacion=estado,
        configuracion=configuracion,
        cuenta_actual=cuenta_actual,
        gestion_sugerida=gestion_sugerida,
        puede_editar=puede_editar,
    )


@configuracion_inicial_bp.route('/api/cuentas-patrimoniales', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_cuentas_patrimoniales():
    termino = (request.args.get('q') or '').strip()

    with DatabaseManager() as db:
        if termino:
            patron = f'%{termino}%'
            filas = db.execute_query(
                """
                SELECT codigo, nombre
                FROM contabilidad.cuenta
                WHERE activo = TRUE
                  AND es_postable = TRUE
                  AND tipo = 'PATRIMONIO'::contabilidad.tipo_cuenta_enum
                  AND (
                        codigo ILIKE %s
                        OR nombre ILIKE %s
                  )
                ORDER BY codigo ASC
                LIMIT 50
                """,
                (patron, patron),
            )
        else:
            filas = db.execute_query(
                """
                SELECT codigo, nombre
                FROM contabilidad.cuenta
                WHERE activo = TRUE
                  AND es_postable = TRUE
                  AND tipo = 'PATRIMONIO'::contabilidad.tipo_cuenta_enum
                ORDER BY codigo ASC
                LIMIT 50
                """
            )

    resultados = [
        {
            'id': fila['codigo'],
            'text': f"{fila['codigo']} - {fila['nombre']}",
        }
        for fila in filas
    ]
    return jsonify({'results': resultados})


@configuracion_inicial_bp.route('/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def guardar():
    gestion_inicial_raw = _clean(request.form.get('gestion_inicial'))
    cuenta_codigo = _clean(request.form.get('cuenta_resultado_ejercicio_codigo'))
    glosa_cierre = _clean(request.form.get('glosa_cierre') or DEFAULTS_CONFIG['glosa_cierre'])
    glosa_apertura = _clean(request.form.get('glosa_apertura') or DEFAULTS_CONFIG['glosa_apertura'])
    unidad_nombre = _clean(request.form.get('unidad_negocio_nombre'))
    unidad_nit = _clean(request.form.get('unidad_negocio_nit'))

    permitir_reapertura = _valor_bool('permitir_reapertura', DEFAULTS_CONFIG['permitir_reapertura'])
    bloquear_si_hay_borradores = _valor_bool(
        'bloquear_si_hay_borradores',
        DEFAULTS_CONFIG['bloquear_si_hay_borradores'],
    )
    bloquear_si_hay_movimientos_destino = _valor_bool(
        'bloquear_si_hay_movimientos_destino',
        DEFAULTS_CONFIG['bloquear_si_hay_movimientos_destino'],
    )

    if not gestion_inicial_raw:
        flash('Debe indicar la gestión inicial de trabajo.', 'warning')
        return redirect(url_for('configuracion_inicial.index'))

    try:
        gestion_inicial = int(gestion_inicial_raw)
    except ValueError:
        flash('La gestión inicial debe ser numérica.', 'warning')
        return redirect(url_for('configuracion_inicial.index'))

    if gestion_inicial < 2000:
        flash('La gestión inicial no es válida.', 'warning')
        return redirect(url_for('configuracion_inicial.index'))

    if not cuenta_codigo:
        flash('Debe seleccionar la cuenta patrimonial del resultado del ejercicio.', 'warning')
        return redirect(url_for('configuracion_inicial.index'))

    if not glosa_cierre:
        flash('La glosa de cierre es obligatoria.', 'warning')
        return redirect(url_for('configuracion_inicial.index'))

    if not glosa_apertura:
        flash('La glosa de apertura es obligatoria.', 'warning')
        return redirect(url_for('configuracion_inicial.index'))

    try:
        with DatabaseManager() as db:
            _validar_cuenta_patrimonial(db, cuenta_codigo)

            config_activa = _obtener_configuracion_activa(db)
            gestiones = _obtener_gestiones_control(db)
            unidades = _obtener_unidades_negocio(db)
            gestion_abierta = next((g for g in gestiones if str(g['estado']) == 'ABIERTA'), None)

            if gestion_abierta and int(gestion_abierta['gestion']) != gestion_inicial:
                raise ValueError(
                    f"Ya existe una gestión abierta ({gestion_abierta['gestion']}). No se puede reemplazar desde esta pantalla."
                )

            unidad_creada = None
            if not unidades:
                unidad_creada = _crear_unidad_negocio_inicial(db, unidad_nombre, unidad_nit)

            if config_activa:
                db.execute_update(
                    """
                    UPDATE contabilidad.gestion_configuracion
                    SET cuenta_resultado_ejercicio_codigo = %s,
                        glosa_cierre = %s,
                        glosa_apertura = %s,
                        permitir_reapertura = %s,
                        bloquear_si_hay_borradores = %s,
                        bloquear_si_hay_movimientos_destino = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        cuenta_codigo,
                        glosa_cierre,
                        glosa_apertura,
                        permitir_reapertura,
                        bloquear_si_hay_borradores,
                        bloquear_si_hay_movimientos_destino,
                        config_activa['id'],
                    ),
                )
            else:
                db.execute_insert(
                    """
                    INSERT INTO contabilidad.gestion_configuracion (
                        activo,
                        cuenta_resultado_ejercicio_codigo,
                        glosa_cierre,
                        glosa_apertura,
                        permitir_reapertura,
                        bloquear_si_hay_borradores,
                        bloquear_si_hay_movimientos_destino
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        True,
                        cuenta_codigo,
                        glosa_cierre,
                        glosa_apertura,
                        permitir_reapertura,
                        bloquear_si_hay_borradores,
                        bloquear_si_hay_movimientos_destino,
                    ),
                    return_id=False,
                )

            existe_gestion = next((g for g in gestiones if int(g['gestion']) == gestion_inicial), None)
            if existe_gestion:
                db.execute_update(
                    """
                    UPDATE contabilidad.gestion_control
                    SET estado = 'ABIERTA'::contabilidad.estado_gestion_enum,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE gestion = %s
                    """,
                    (gestion_inicial,),
                )
            else:
                db.execute_insert(
                    """
                    INSERT INTO contabilidad.gestion_control (
                        gestion,
                        estado
                    ) VALUES (%s, 'ABIERTA'::contabilidad.estado_gestion_enum)
                    """,
                    (gestion_inicial,),
                    return_id=False,
                )

        mensaje = f'Configuración inicial aplicada correctamente. La gestión {gestion_inicial} quedó habilitada para trabajo.'
        if unidad_creada:
            mensaje += f' También se creó la unidad de negocio inicial {unidad_creada["codigo"]} - {unidad_creada["nombre"]}.'

        flash(mensaje, 'success')
        return redirect(url_for('dashboard.index'))

    except ValueError as exc:
        flash(str(exc), 'warning')
        return redirect(url_for('configuracion_inicial.index'))
    except Exception as exc:
        flash(f'No se pudo guardar la configuración inicial. {exc}', 'danger')
        return redirect(url_for('configuracion_inicial.index'))


@configuracion_inicial_bp.route('/help', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('configuracion_inicial_help.html')
