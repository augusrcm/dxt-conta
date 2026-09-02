# ============================================================
# DXT CONTA - Personas de Planilla
# Base operativa para planillas de planta y colaboradores.
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import jsonify, render_template, request, session
from psycopg2.extras import Json, RealDictCursor

from database.db_manager import DatabaseManager
from modules.planilla_personas import planilla_personas_bp
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]

TIPOS_PERSONA = {'PLANTA', 'COLABORADOR'}
ESTADOS = {'ACTIVO', 'INACTIVO'}
ORIGEN_FUNCIONARIOS = 'funcionarios.funcionarios'
ORIGEN_PLANILLA_PERSONA = 'contabilidad.planilla_persona'

REGIONALES = {
    'LP': 'La Paz',
    'SC': 'Santa Cruz',
    'CB': 'Cochabamba',
    'OR': 'Oruro',
    'PT': 'Potosi',
    'CH': 'Chuquisaca',
    'TJ': 'Tarija',
    'BN': 'Beni',
    'PD': 'Pando',
}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def _usuario_actual() -> str:
    return str(
        session.get('username')
        or session.get('usuario')
        or session.get('email')
        or session.get('user_id')
        or 'sistema'
    )


def _puede_editar() -> bool:
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except (TypeError, ValueError):
        return False


def _json_ok(message: str | None = None, **kwargs):
    payload = {'success': True}
    if message:
        payload['message'] = message
    payload.update(kwargs)
    return jsonify(payload)


def _json_error(message: str, status: int = 400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(payload), status


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'sí', 'on')


def _parse_int(value: Any, field_name: str, required: bool = False) -> int | None:
    text = _clean(value)
    if not text:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        number = int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es válido.') from exc
    if number <= 0:
        raise ValueError(f'El campo "{field_name}" no es válido.')
    return number


def _parse_decimal(value: Any, field_name: str, required: bool = False, default: Decimal | None = None) -> Decimal | None:
    text = _clean(value).replace(',', '.')
    if not text:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return default
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" debe ser numérico.') from exc
    if number < 0:
        raise ValueError(f'El campo "{field_name}" no puede ser negativo.')
    return number


def _parse_date(value: Any, field_name: str, required: bool = False):
    text = _clean(value)
    if not text:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.') from exc


def _limit_text(value: Any, field_name: str, max_len: int, required: bool = False) -> str | None:
    text = _clean(value)
    if required and not text:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(text) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return text or None


def _json_ready(value: Any):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _auxiliar_tipo_para_persona(tipo_persona: str) -> str:
    # El respaldo del colaborador se define por cada planilla mensual.
    # Por eso el auxiliar base no debe quedar amarrado a FACTURA/SIN_FACTURA.
    return 'FUNCIONARIO' if tipo_persona == 'PLANTA' else 'OTRO'


def _identificador_auxiliar(payload: dict[str, Any]) -> str:
    if payload['tipo_persona'] == 'COLABORADOR' and payload.get('nit_referencia'):
        return payload['nit_referencia']
    return payload['ci_nit']


def _validar_payload(data: dict[str, Any]) -> dict[str, Any]:
    tipo_persona = _upper(data.get('tipo_persona'))
    unidad_negocio_id = _parse_int(data.get('unidad_negocio_id'), 'Unidad de negocio', required=True)
    ci_nit = _limit_text(data.get('ci_nit'), 'CI / documento', 50, required=True)
    nit_referencia = _limit_text(data.get('nit_referencia'), 'NIT', 50)
    nombre_completo = _limit_text(data.get('nombre_completo'), 'Nombre completo', 250, required=True)
    correo = _limit_text(data.get('correo'), 'Correo', 150)
    telefono = _limit_text(data.get('telefono'), 'Teléfono', 80)
    cargo_referencia = _limit_text(data.get('cargo_referencia'), 'Cargo o servicio base', 150)
    regional_referencia = _upper(_limit_text(data.get('regional_referencia'), 'Regional', 50) or '') or None
    fecha_ingreso_referencia = _parse_date(data.get('fecha_ingreso_referencia'), 'Fecha de ingreso')
    fecha_nacimiento = _parse_date(data.get('fecha_nacimiento'), 'Fecha de nacimiento')
    nacionalidad = _limit_text(data.get('nacionalidad'), 'Nacionalidad', 80)
    sexo = _upper(_limit_text(data.get('sexo'), 'Sexo', 20) or '') or None
    ocupacion_referencia = _limit_text(data.get('ocupacion_referencia') or data.get('cargo_referencia'), 'Ocupación', 150)
    haber_basico_referencia = _parse_decimal(data.get('haber_basico_referencia'), 'Haber básico', default=Decimal('0.00')) or Decimal('0.00')
    monto_minimo_mensual_referencia = _parse_decimal(data.get('monto_minimo_mensual_referencia'), 'Mínimo mensual colaborador', default=Decimal('0.00')) or Decimal('0.00')
    banco_referencia = _limit_text(data.get('banco_referencia'), 'Banco', 120)
    cuenta_bancaria_referencia = _limit_text(data.get('cuenta_bancaria_referencia'), 'Cuenta bancaria', 80)
    cuenta_auxiliar_codigo = _upper(_limit_text(data.get('cuenta_auxiliar_codigo'), 'Cuenta contable auxiliar', 30) or '') or None
    estado = _upper(data.get('estado') or 'ACTIVO')
    observacion = _limit_text(data.get('observacion'), 'Observación', 500)
    crear_auxiliar = _parse_bool(data.get('crear_auxiliar'), default=True)
    if crear_auxiliar and not cuenta_auxiliar_codigo:
        raise ValueError('Debe seleccionar la cuenta contable auxiliar para crear o vincular el auxiliar contable.')

    origen_schema = _limit_text(data.get('origen_schema'), 'Esquema origen', 80)
    origen_tabla = _limit_text(data.get('origen_tabla'), 'Tabla origen', 80)
    origen_clave = _limit_text(data.get('origen_clave'), 'Clave origen', 100)

    if tipo_persona not in TIPOS_PERSONA:
        raise ValueError('El tipo de persona no es válido.')

    if tipo_persona == 'PLANTA':
        if haber_basico_referencia <= 0:
            raise ValueError('Para personal de planta debe registrar Haber Básico.')
        monto_minimo_mensual_referencia = Decimal('0.00')
        if not fecha_ingreso_referencia:
            raise ValueError('Para personal de planta debe registrar Fecha de ingreso.')
    else:
        if monto_minimo_mensual_referencia <= 0:
            raise ValueError('Para colaboradores debe registrar Mínimo mensual referencial.')
        haber_basico_referencia = Decimal('0.00')

    if estado not in ESTADOS:
        raise ValueError('El estado no es válido.')

    if correo and ('@' not in correo or len(correo.split('@', 1)[0]) == 0):
        raise ValueError('El correo no tiene un formato válido.')

    if sexo and sexo not in {'M', 'F', 'OTRO'}:
        raise ValueError('El sexo no es válido.')

    return {
        'tipo_persona': tipo_persona,
        'unidad_negocio_id': unidad_negocio_id,
        'ci_nit': ci_nit,
        'nit_referencia': nit_referencia,
        'nombre_completo': nombre_completo,
        'correo': correo,
        'telefono': telefono,
        'cargo_referencia': cargo_referencia,
        'regional_referencia': regional_referencia,
        'fecha_ingreso_referencia': fecha_ingreso_referencia,
        'fecha_nacimiento': fecha_nacimiento,
        'nacionalidad': nacionalidad,
        'sexo': sexo,
        'ocupacion_referencia': ocupacion_referencia,
        'haber_basico_referencia': haber_basico_referencia,
        'monto_minimo_mensual_referencia': monto_minimo_mensual_referencia,
        'banco_referencia': banco_referencia,
        'cuenta_bancaria_referencia': cuenta_bancaria_referencia,
        'cuenta_auxiliar_codigo': cuenta_auxiliar_codigo,
        'tipo_respaldo_habitual': 'NO_APLICA',
        'estado': estado,
        'observacion': observacion,
        'crear_auxiliar': crear_auxiliar,
        'origen_schema': origen_schema,
        'origen_tabla': origen_tabla,
        'origen_clave': origen_clave,
    }


def _assert_tables_ready(db: DatabaseManager) -> None:
    rows = db.execute_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'contabilidad'
          AND table_name = 'planilla_persona'
          AND column_name IN (
              'id', 'tipo_persona', 'ci_nit', 'nombre_completo', 'auxiliar_id',
              'nit_referencia', 'banco_referencia', 'cuenta_bancaria_referencia',
              'unidad_negocio_id', 'fecha_nacimiento', 'nacionalidad', 'sexo',
              'ocupacion_referencia', 'haber_basico_referencia',
              'monto_minimo_mensual_referencia'
          )
        """
    )
    columns = {row['column_name'] for row in rows}
    required = {
        'id', 'tipo_persona', 'ci_nit', 'nombre_completo', 'auxiliar_id',
        'nit_referencia', 'banco_referencia', 'cuenta_bancaria_referencia',
        'unidad_negocio_id', 'fecha_nacimiento', 'nacionalidad', 'sexo',
        'ocupacion_referencia', 'haber_basico_referencia',
        'monto_minimo_mensual_referencia'
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(
            'Faltan columnas de Personas de Planilla. Ejecute primero el script '
            'actualizar_planilla_persona_datos_pago.sql, actualizar_planillas_unidad_por_persona.sql y actualizar_planillas_datos_base_laboral.sql.'
        )


def _funcionarios_disponible(db: DatabaseManager) -> bool:
    row = db.execute_query("SELECT to_regclass('funcionarios.funcionarios')::text AS tabla")
    return bool(row and row[0].get('tabla'))


def _unidades_negocio(db: DatabaseManager) -> list[dict[str, Any]]:
    rows = db.execute_query(
        """
        SELECT id, codigo, nombre
        FROM contabilidad.unidad_negocio
        WHERE activo IS TRUE
        ORDER BY codigo ASC, nombre ASC
        """
    )
    return [dict(row) for row in rows]


def _row_to_option_funcionario(row: dict[str, Any]) -> dict[str, Any]:
    nombre = _clean(row.get('nombre_completo'))
    ci = _clean(row.get('ci'))
    cargo = _clean(row.get('cargo_referencia'))
    regional = _clean(row.get('regional_referencia'))
    nit = _clean(row.get('nit_referencia'))
    partes = [nombre]
    if ci:
        partes.append(f'CI: {ci}')
    if nit:
        partes.append(f'NIT: {nit}')
    if cargo:
        partes.append(cargo)
    if regional:
        partes.append(regional)
    return {
        'id': ci,
        'text': ' | '.join(partes),
        'ci': ci,
        'ci_nit': ci,
        'nit_referencia': nit,
        'nombre_completo': nombre,
        'telefono': _clean(row.get('telefono')),
        'correo': _clean(row.get('correo')),
        'cargo_referencia': cargo,
        'regional_referencia': regional,
        'fecha_ingreso_referencia': _json_ready(row.get('fecha_ingreso_referencia')),
        'fecha_nacimiento': _json_ready(row.get('fecha_nacimiento')),
        'nacionalidad': _clean(row.get('nacionalidad')),
        'sexo': _clean(row.get('sexo')),
        'ocupacion_referencia': cargo,
        'estado': _clean(row.get('estado')),
        'liquido_referencia': _json_ready(row.get('liquido_referencia')),
        'tipo_contrato_referencia': _clean(row.get('tipo_contrato_referencia')),
        'ya_importado': bool(row.get('ya_importado')),
    }


def _buscar_funcionario_externo(db: DatabaseManager, ci: str) -> dict[str, Any] | None:
    if not _funcionarios_disponible(db):
        return None
    rows = db.execute_query(
        """
        SELECT
            f.ci,
            f.nombre_completo,
            COALESCE(f.telefono, '') AS telefono,
            COALESCE(f.correo, '') AS correo,
            f.fecha_ingreso AS fecha_ingreso_referencia,
            COALESCE(f.regional::text, '') AS regional_referencia,
            COALESCE(p.descripcion, f.profesion, '') AS cargo_referencia,
            COALESCE(f.estado::text, '') AS estado,
            NULL::date AS fecha_nacimiento,
            ''::text AS nacionalidad,
            ''::text AS sexo,
            COALESCE(c.nit, '') AS nit_referencia,
            c.liquido_pagable AS liquido_referencia,
            COALESCE(c.tipo_contrato::text, '') AS tipo_contrato_referencia,
            EXISTS (
                SELECT 1
                FROM contabilidad.planilla_persona pp
                WHERE pp.origen_schema = 'funcionarios'
                  AND pp.origen_tabla = 'funcionarios'
                  AND pp.origen_clave = f.ci
            ) AS ya_importado
        FROM funcionarios.funcionarios f
        LEFT JOIN funcionarios.puestos p ON p.id_puesto = f.puesto_id
        LEFT JOIN LATERAL (
            SELECT c.nit, c.liquido_pagable, c.tipo_contrato, c.estado, c.inicio
            FROM funcionarios.contratos c
            WHERE c.ci = f.ci
            ORDER BY CASE WHEN c.estado::text = 'ACTIVO' THEN 0 ELSE 1 END,
                     c.inicio DESC NULLS LAST,
                     c.numcontrato DESC
            LIMIT 1
        ) c ON TRUE
        WHERE f.ci = %s
        LIMIT 1
        """,
        (ci,)
    )
    return dict(rows[0]) if rows else None


def _persona_duplicada(db: DatabaseManager, tipo_persona: str, ci_nit: str, exclude_id: int | None = None):
    identificador = _clean(ci_nit)
    params: list[Any] = [identificador, identificador]
    extra = ''
    if exclude_id:
        extra = 'AND id <> %s'
        params.append(exclude_id)
    rows = db.execute_query(
        f"""
        SELECT id, tipo_persona, nombre_completo, ci_nit
        FROM contabilidad.planilla_persona
        WHERE (
              COALESCE(ci_nit, '') = %s
              OR COALESCE(nit_referencia, '') = %s
        )
          {extra}
        LIMIT 1
        """,
        tuple(params)
    )
    return rows[0] if rows else None


def _auxiliar_existente(cursor, tipo_auxiliar: str, identificador: str):
    cursor.execute(
        """
        SELECT id
        FROM contabilidad.auxiliar
        WHERE tipo = %s
          AND COALESCE(nit_ci, '') = %s
        ORDER BY activo DESC, id ASC
        LIMIT 1
        """,
        (tipo_auxiliar, identificador)
    )
    row = cursor.fetchone()
    return row['id'] if row else None



def _cuenta_auxiliar_valida_db(db: DatabaseManager, cuenta_codigo: str | None):
    codigo = _upper(cuenta_codigo)
    if not codigo:
        return None
    rows = db.execute_query(
        """
        SELECT codigo, nombre
        FROM contabilidad.cuenta
        WHERE codigo = %s
          AND activo IS TRUE
          AND es_postable IS TRUE
          AND requiere_auxiliar IS TRUE
        LIMIT 1
        """,
        (codigo,)
    )
    return dict(rows[0]) if rows else None


def _asegurar_auxiliar_cuenta_cursor(cursor, auxiliar_id: int, cuenta_codigo: str) -> None:
    cursor.execute(
        """
        INSERT INTO contabilidad.auxiliar_cuenta (auxiliar_id, cuenta_codigo, activo)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (auxiliar_id, cuenta_codigo)
        DO UPDATE SET activo = TRUE
        """,
        (auxiliar_id, cuenta_codigo)
    )

def _asegurar_auxiliar_cursor(cursor, payload: dict[str, Any], persona_id: int) -> int:
    tipo_auxiliar = _auxiliar_tipo_para_persona(payload['tipo_persona'])
    identificador = _identificador_auxiliar(payload)

    existente = _auxiliar_existente(cursor, tipo_auxiliar, identificador)
    if existente:
        return existente

    codigo_externo = f'PLAN-PER-{persona_id}'
    observaciones = 'Auxiliar creado desde Personas de Planilla.'
    if payload.get('origen_schema') == 'funcionarios':
        observaciones += ' Origen: funcionarios.funcionarios.'

    cursor.execute(
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, FALSE, TRUE, CURRENT_TIMESTAMP, %s)
        RETURNING id
        """,
        (
            tipo_auxiliar,
            ORIGEN_PLANILLA_PERSONA,
            persona_id,
            codigo_externo,
            identificador,
            payload['nombre_completo'],
            payload['nombre_completo'],
            payload.get('telefono'),
            payload.get('correo'),
            observaciones,
        )
    )
    return cursor.fetchone()['id']


def _stats(db: DatabaseManager) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE tipo_persona = 'PLANTA')::int AS planta,
            COUNT(*) FILTER (WHERE tipo_persona = 'COLABORADOR')::int AS colaboradores,
            COUNT(*) FILTER (WHERE estado = 'ACTIVO')::int AS activos,
            COUNT(*) FILTER (WHERE auxiliar_id IS NOT NULL)::int AS con_auxiliar,
            COUNT(*) FILTER (WHERE estado = 'ACTIVO' AND unidad_negocio_id IS NULL)::int AS sin_unidad,
            COUNT(*) FILTER (WHERE estado = 'ACTIVO' AND tipo_persona = 'PLANTA' AND COALESCE(haber_basico_referencia,0) <= 0)::int AS planta_sin_basico,
            COUNT(*) FILTER (WHERE estado = 'ACTIVO' AND tipo_persona = 'COLABORADOR' AND COALESCE(monto_minimo_mensual_referencia,0) <= 0)::int AS colaborador_sin_minimo
        FROM contabilidad.planilla_persona
        """
    )
    base = dict(rows[0]) if rows else {}
    return {
        'total': int(base.get('total') or 0),
        'planta': int(base.get('planta') or 0),
        'colaboradores': int(base.get('colaboradores') or 0),
        'activos': int(base.get('activos') or 0),
        'con_auxiliar': int(base.get('con_auxiliar') or 0),
        'sin_unidad': int(base.get('sin_unidad') or 0),
        'planta_sin_basico': int(base.get('planta_sin_basico') or 0),
        'colaborador_sin_minimo': int(base.get('colaborador_sin_minimo') or 0),
    }


@planilla_personas_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    try:
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            stats = _stats(db)
            funcionarios_ok = _funcionarios_disponible(db)
            unidades = _unidades_negocio(db)
    except Exception as exc:
        stats = {'total': 0, 'planta': 0, 'colaboradores': 0, 'activos': 0, 'con_auxiliar': 0, 'sin_unidad': 0, 'planta_sin_basico': 0, 'colaborador_sin_minimo': 0}
        funcionarios_ok = False
        unidades = []
        return render_template(
            'planilla_personas_index.html',
            stats=stats,
            funcionarios_ok=funcionarios_ok,
            puede_editar=_puede_editar(),
            error='No se pudo cargar la pantalla de personas de planilla. Revise la configuración operativa del módulo.',
            regionales=REGIONALES,
            unidades=unidades,
        )

    return render_template(
        'planilla_personas_index.html',
        stats=stats,
        funcionarios_ok=funcionarios_ok,
        puede_editar=_puede_editar(),
        error=None,
        regionales=REGIONALES,
        unidades=unidades,
    )


@planilla_personas_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('planilla_personas_help.html')


@planilla_personas_bp.route('/listar')
@login_required
@roles_required(ROLES_LECTURA)
def listar():
    tipo = _upper(request.args.get('tipo'))
    estado = _upper(request.args.get('estado'))
    q = _clean(request.args.get('q'))

    filtros = []
    params: list[Any] = []

    if tipo in TIPOS_PERSONA:
        filtros.append('pp.tipo_persona = %s')
        params.append(tipo)
    if estado in ESTADOS:
        filtros.append('pp.estado = %s')
        params.append(estado)
    if q:
        filtros.append("""
            (
                pp.nombre_completo ILIKE %s
                OR pp.ci_nit ILIKE %s
                OR COALESCE(pp.nit_referencia, '') ILIKE %s
                OR COALESCE(pp.cargo_referencia, '') ILIKE %s
                OR COALESCE(pp.ocupacion_referencia, '') ILIKE %s
                OR COALESCE(pp.regional_referencia, '') ILIKE %s
                OR COALESCE(pp.banco_referencia, '') ILIKE %s
                OR COALESCE(un.codigo, '') ILIKE %s
                OR COALESCE(un.nombre, '') ILIKE %s
            )
        """)
        like = f'%{q}%'
        params.extend([like, like, like, like, like, like, like, like, like])

    where = 'WHERE ' + ' AND '.join(filtros) if filtros else ''

    with DatabaseManager() as db:
        _assert_tables_ready(db)
        rows = db.execute_query(
            f"""
            SELECT
                pp.id,
                pp.tipo_persona,
                pp.ci_nit,
                COALESCE(pp.nit_referencia, '') AS nit_referencia,
                pp.nombre_completo,
                COALESCE(pp.correo, '') AS correo,
                COALESCE(pp.telefono, '') AS telefono,
                COALESCE(pp.cargo_referencia, '') AS cargo_referencia,
                COALESCE(pp.regional_referencia, '') AS regional_referencia,
                pp.fecha_ingreso_referencia,
                pp.fecha_nacimiento,
                COALESCE(pp.nacionalidad, '') AS nacionalidad,
                COALESCE(pp.sexo, '') AS sexo,
                COALESCE(pp.ocupacion_referencia, '') AS ocupacion_referencia,
                COALESCE(pp.haber_basico_referencia, 0) AS haber_basico_referencia,
                COALESCE(pp.monto_minimo_mensual_referencia, 0) AS monto_minimo_mensual_referencia,
                COALESCE(pp.banco_referencia, '') AS banco_referencia,
                COALESCE(pp.cuenta_bancaria_referencia, '') AS cuenta_bancaria_referencia,
                pp.unidad_negocio_id,
                COALESCE(un.codigo, '') AS unidad_negocio_codigo,
                COALESCE(un.nombre, '') AS unidad_negocio_nombre,
                pp.estado,
                COALESCE(pp.origen_schema, '') AS origen_schema,
                COALESCE(pp.origen_tabla, '') AS origen_tabla,
                COALESCE(pp.origen_clave, '') AS origen_clave,
                COALESCE(pp.observacion, '') AS observacion,
                pp.auxiliar_id,
                COALESCE(a.tipo::text, '') AS auxiliar_tipo,
                COALESCE(a.nombre, '') AS auxiliar_nombre,
                COALESCE(caux.cuenta_codigo, '') AS cuenta_auxiliar_codigo,
                COALESCE(caux.cuenta_nombre, '') AS cuenta_auxiliar_nombre,
                COALESCE(det.usos, 0)::int AS usos_planilla
            FROM contabilidad.planilla_persona pp
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = pp.unidad_negocio_id
            LEFT JOIN contabilidad.auxiliar a ON a.id = pp.auxiliar_id
            LEFT JOIN LATERAL (
                SELECT ac.cuenta_codigo, c.nombre AS cuenta_nombre
                FROM contabilidad.auxiliar_cuenta ac
                INNER JOIN contabilidad.cuenta c ON c.codigo = ac.cuenta_codigo
                WHERE ac.auxiliar_id = pp.auxiliar_id
                  AND ac.activo IS TRUE
                ORDER BY ac.creado_en DESC NULLS LAST, ac.id DESC
                LIMIT 1
            ) caux ON TRUE
            LEFT JOIN (
                SELECT persona_id, COUNT(*)::int AS usos
                FROM contabilidad.planilla_detalle
                WHERE persona_id IS NOT NULL
                  AND estado <> 'EXCLUIDO'
                GROUP BY persona_id
            ) det ON det.persona_id = pp.id
            {where}
            ORDER BY pp.estado ASC, pp.tipo_persona ASC, pp.nombre_completo ASC, pp.id ASC
            """,
            tuple(params)
        )

    return jsonify({'data': _json_ready([dict(row) for row in rows])})


@planilla_personas_bp.route('/obtener/<int:persona_id>')
@login_required
@roles_required(ROLES_LECTURA)
def obtener(persona_id: int):
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        rows = db.execute_query(
            """
            SELECT
                pp.*,
                COALESCE(un.codigo, '') AS unidad_negocio_codigo,
                COALESCE(un.nombre, '') AS unidad_negocio_nombre,
                COALESCE(a.tipo::text, '') AS auxiliar_tipo,
                COALESCE(a.nombre, '') AS auxiliar_nombre,
                COALESCE(caux.cuenta_codigo, '') AS cuenta_auxiliar_codigo,
                COALESCE(caux.cuenta_nombre, '') AS cuenta_auxiliar_nombre
            FROM contabilidad.planilla_persona pp
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = pp.unidad_negocio_id
            LEFT JOIN contabilidad.auxiliar a ON a.id = pp.auxiliar_id
            LEFT JOIN LATERAL (
                SELECT ac.cuenta_codigo, c.nombre AS cuenta_nombre
                FROM contabilidad.auxiliar_cuenta ac
                INNER JOIN contabilidad.cuenta c ON c.codigo = ac.cuenta_codigo
                WHERE ac.auxiliar_id = pp.auxiliar_id
                  AND ac.activo IS TRUE
                ORDER BY ac.creado_en DESC NULLS LAST, ac.id DESC
                LIMIT 1
            ) caux ON TRUE
            WHERE pp.id = %s
            LIMIT 1
            """,
            (persona_id,)
        )
    if not rows:
        return _json_error('La persona de planilla no existe.', 404)
    return _json_ok(data=_json_ready(dict(rows[0])))


@planilla_personas_bp.route('/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def guardar():
    data = request.get_json() or {}
    try:
        persona_id = data.get('id')
        persona_id = int(persona_id) if persona_id not in (None, '', 'null') else None
        payload = _validar_payload(data)
    except (TypeError, ValueError) as exc:
        return _json_error(str(exc))

    with DatabaseManager() as db:
        _assert_tables_ready(db)

        if persona_id:
            estado_rows = db.execute_query(
                """
                SELECT estado
                FROM contabilidad.planilla_persona
                WHERE id = %s
                LIMIT 1
                """,
                (persona_id,)
            )
            if not estado_rows:
                return _json_error('La persona de planilla no existe.', 404)
            # El estado se administra solo desde las acciones del grid.
            payload['estado'] = estado_rows[0]['estado']
        else:
            # Toda alta nueva se crea activa. No tiene sentido registrar una persona nueva inactiva.
            payload['estado'] = 'ACTIVO'

        unidad_rows = db.execute_query(
            """
            SELECT id
            FROM contabilidad.unidad_negocio
            WHERE id = %s
              AND activo IS TRUE
            LIMIT 1
            """,
            (payload['unidad_negocio_id'],)
        )
        if not unidad_rows:
            return _json_error('La unidad de negocio seleccionada no existe o está inactiva.')

        duplicado = _persona_duplicada(db, payload['tipo_persona'], payload['ci_nit'], persona_id)
        if duplicado:
            return _json_error(
                f"Ya existe {duplicado['nombre_completo']} con el mismo CI/NIT/documento. No se permite duplicar identificadores en personas de planilla.",
                409
            )

        if payload['crear_auxiliar'] and not _cuenta_auxiliar_valida_db(db, payload['cuenta_auxiliar_codigo']):
            return _json_error('La cuenta contable auxiliar seleccionada no existe, está inactiva, no es postable o no requiere auxiliares.')

        cursor = db.conn.cursor(cursor_factory=RealDictCursor)
        try:
            if persona_id:
                cursor.execute(
                    """
                    UPDATE contabilidad.planilla_persona
                    SET
                        tipo_persona = %s,
                        unidad_negocio_id = %s,
                        ci_nit = %s,
                        nit_referencia = %s,
                        nombre_completo = %s,
                        correo = %s,
                        telefono = %s,
                        cargo_referencia = %s,
                        regional_referencia = %s,
                        fecha_ingreso_referencia = %s,
                        fecha_nacimiento = %s,
                        nacionalidad = %s,
                        sexo = %s,
                        ocupacion_referencia = %s,
                        haber_basico_referencia = %s,
                        monto_minimo_mensual_referencia = %s,
                        banco_referencia = %s,
                        cuenta_bancaria_referencia = %s,
                        tipo_respaldo_habitual = %s,
                        estado = %s,
                        observacion = %s,
                        origen_schema = %s,
                        origen_tabla = %s,
                        origen_clave = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        payload['tipo_persona'],
                        payload['unidad_negocio_id'],
                        payload['ci_nit'],
                        payload['nit_referencia'],
                        payload['nombre_completo'],
                        payload['correo'],
                        payload['telefono'],
                        payload['cargo_referencia'],
                        payload['regional_referencia'],
                        payload['fecha_ingreso_referencia'],
                        payload['fecha_nacimiento'],
                        payload['nacionalidad'],
                        payload['sexo'],
                        payload['ocupacion_referencia'],
                        payload['haber_basico_referencia'],
                        payload['monto_minimo_mensual_referencia'],
                        payload['banco_referencia'],
                        payload['cuenta_bancaria_referencia'],
                        payload['tipo_respaldo_habitual'],
                        payload['estado'],
                        payload['observacion'],
                        payload['origen_schema'],
                        payload['origen_tabla'],
                        payload['origen_clave'],
                        persona_id,
                    )
                )
                row = cursor.fetchone()
                if not row:
                    return _json_error('La persona de planilla no existe.', 404)
            else:
                cursor.execute(
                    """
                    INSERT INTO contabilidad.planilla_persona (
                        tipo_persona,
                        unidad_negocio_id,
                        ci_nit,
                        nit_referencia,
                        nombre_completo,
                        correo,
                        telefono,
                        cargo_referencia,
                        regional_referencia,
                        fecha_ingreso_referencia,
                        fecha_nacimiento,
                        nacionalidad,
                        sexo,
                        ocupacion_referencia,
                        haber_basico_referencia,
                        monto_minimo_mensual_referencia,
                        banco_referencia,
                        cuenta_bancaria_referencia,
                        tipo_respaldo_habitual,
                        estado,
                        observacion,
                        origen_schema,
                        origen_tabla,
                        origen_clave,
                        atributos
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        payload['tipo_persona'],
                        payload['unidad_negocio_id'],
                        payload['ci_nit'],
                        payload['nit_referencia'],
                        payload['nombre_completo'],
                        payload['correo'],
                        payload['telefono'],
                        payload['cargo_referencia'],
                        payload['regional_referencia'],
                        payload['fecha_ingreso_referencia'],
                        payload['fecha_nacimiento'],
                        payload['nacionalidad'],
                        payload['sexo'],
                        payload['ocupacion_referencia'],
                        payload['haber_basico_referencia'],
                        payload['monto_minimo_mensual_referencia'],
                        payload['banco_referencia'],
                        payload['cuenta_bancaria_referencia'],
                        payload['tipo_respaldo_habitual'],
                        payload['estado'],
                        payload['observacion'],
                        payload['origen_schema'],
                        payload['origen_tabla'],
                        payload['origen_clave'],
                        Json({'creado_por': _usuario_actual()}),
                    )
                )
                persona_id = cursor.fetchone()['id']

            auxiliar_id = None
            if payload['crear_auxiliar']:
                auxiliar_id = _asegurar_auxiliar_cursor(cursor, payload, persona_id)
                _asegurar_auxiliar_cuenta_cursor(cursor, auxiliar_id, payload['cuenta_auxiliar_codigo'])

            cursor.execute(
                """
                UPDATE contabilidad.planilla_persona
                SET auxiliar_id = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (auxiliar_id, persona_id)
            )
        finally:
            cursor.close()

    return _json_ok('Persona de planilla guardada correctamente.', id=persona_id)


@planilla_personas_bp.route('/cuentas-auxiliares/buscar')
@login_required
@roles_required(ROLES_LECTURA)
def buscar_cuentas_auxiliares():
    q = _clean(request.args.get('q'))
    tipo_persona = _upper(request.args.get('tipo_persona') or 'PLANTA')
    q_like = f'%{q}%'

    if tipo_persona == 'COLABORADOR':
        preferidas = ['6.1.1.017', '2.1.1.001']
        patrones = ['%HONORARIOS%', '%CUENTAS POR PAGAR%']
    else:
        preferidas = ['1.1.2.005', '2.1.1.001']
        patrones = ['%PERSONAL%', '%CUENTAS POR PAGAR%']

    with DatabaseManager() as db:
        rows = db.execute_query(
            """
            SELECT codigo, nombre
            FROM contabilidad.cuenta
            WHERE activo IS TRUE
              AND es_postable IS TRUE
              AND requiere_auxiliar IS TRUE
              AND (
                    %s = ''
                    OR codigo ILIKE %s
                    OR nombre ILIKE %s
                  )
            ORDER BY
                CASE
                    WHEN codigo = %s THEN 0
                    WHEN codigo = %s THEN 1
                    WHEN nombre ILIKE %s THEN 2
                    WHEN nombre ILIKE %s THEN 3
                    ELSE 9
                END,
                codigo ASC
            LIMIT 30
            """,
            (q, q_like, q_like, preferidas[0], preferidas[1], patrones[0], patrones[1])
        )

    results = [
        {
            'id': row['codigo'],
            'text': f"{row['codigo']} | {row['nombre']}",
            'codigo': row['codigo'],
            'nombre': row['nombre'],
        }
        for row in rows
    ]
    return jsonify({'results': results})


@planilla_personas_bp.route('/cambiar-estado/<int:persona_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def cambiar_estado(persona_id: int):
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        rows = db.execute_query(
            """
            SELECT id, estado
            FROM contabilidad.planilla_persona
            WHERE id = %s
            LIMIT 1
            """,
            (persona_id,)
        )
        if not rows:
            return _json_error('La persona de planilla no existe.', 404)
        actual = rows[0]['estado']
        nuevo = 'INACTIVO' if actual == 'ACTIVO' else 'ACTIVO'
        db.execute_update(
            """
            UPDATE contabilidad.planilla_persona
            SET estado = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (nuevo, persona_id)
        )
    return _json_ok('Estado actualizado correctamente.', estado=nuevo)


@planilla_personas_bp.route('/funcionarios/buscar')
@login_required
@roles_required(ROLES_LECTURA)
def buscar_funcionarios():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'
    solo_activos = _parse_bool(request.args.get('solo_activos'), default=True)
    solo_pendientes = _parse_bool(request.args.get('solo_pendientes'), default=True)

    with DatabaseManager() as db:
        if not _funcionarios_disponible(db):
            return jsonify({'disponible': False, 'results': []})

        filtros = [
            "(%s = '' OR f.ci ILIKE %s OR f.nombre_completo ILIKE %s OR COALESCE(p.descripcion, '') ILIKE %s OR COALESCE(c.nit, '') ILIKE %s)"
        ]
        params: list[Any] = [q, q_like, q_like, q_like, q_like]
        if solo_activos:
            filtros.append("COALESCE(f.estado::text, '') = 'ACTIVO'")
        if solo_pendientes:
            filtros.append("""
                NOT EXISTS (
                    SELECT 1
                    FROM contabilidad.planilla_persona pp
                    WHERE (
                            (pp.origen_schema = 'funcionarios'
                             AND pp.origen_tabla = 'funcionarios'
                             AND pp.origen_clave = f.ci)
                         OR pp.ci_nit = f.ci
                      )
                )
            """)
        where = ' AND '.join(filtros)

        rows = db.execute_query(
            f"""
            SELECT
                f.ci,
                f.nombre_completo,
                COALESCE(f.telefono, '') AS telefono,
                COALESCE(f.correo, '') AS correo,
                f.fecha_ingreso AS fecha_ingreso_referencia,
                COALESCE(f.regional::text, '') AS regional_referencia,
                COALESCE(p.descripcion, f.profesion, '') AS cargo_referencia,
                COALESCE(f.estado::text, '') AS estado,
                COALESCE(c.nit, '') AS nit_referencia,
                c.liquido_pagable AS liquido_referencia,
                COALESCE(c.tipo_contrato::text, '') AS tipo_contrato_referencia,
                EXISTS (
                    SELECT 1
                    FROM contabilidad.planilla_persona pp
                    WHERE pp.origen_schema = 'funcionarios'
                      AND pp.origen_tabla = 'funcionarios'
                      AND pp.origen_clave = f.ci
                ) AS ya_importado
            FROM funcionarios.funcionarios f
            LEFT JOIN funcionarios.puestos p ON p.id_puesto = f.puesto_id
            LEFT JOIN LATERAL (
                SELECT c.nit, c.liquido_pagable, c.tipo_contrato, c.estado, c.inicio
                FROM funcionarios.contratos c
                WHERE c.ci = f.ci
                ORDER BY CASE WHEN c.estado::text = 'ACTIVO' THEN 0 ELSE 1 END,
                         c.inicio DESC NULLS LAST,
                         c.numcontrato DESC
                LIMIT 1
            ) c ON TRUE
            WHERE {where}
            ORDER BY CASE WHEN COALESCE(f.estado::text, '') = 'ACTIVO' THEN 0 ELSE 1 END,
                     f.nombre_completo ASC
            LIMIT 50
            """,
            tuple(params)
        )
    return jsonify({'disponible': True, 'results': _json_ready([_row_to_option_funcionario(dict(r)) for r in rows])})


@planilla_personas_bp.route('/funcionarios/obtener/<path:ci>')
@login_required
@roles_required(ROLES_LECTURA)
def obtener_funcionario(ci: str):
    ci = _clean(ci)
    if not ci:
        return _json_error('Debe seleccionar un funcionario.', 400)
    with DatabaseManager() as db:
        funcionario = _buscar_funcionario_externo(db, ci)
    if not funcionario:
        return _json_error('No se encontró el funcionario seleccionado.', 404)
    return _json_ok(data=_json_ready(_row_to_option_funcionario(funcionario)))


@planilla_personas_bp.route('/funcionarios/importar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def importar_funcionario():
    data = request.get_json() or {}
    ci = _clean(data.get('ci'))
    if not ci:
        return _json_error('Debe seleccionar un funcionario de origen.')

    with DatabaseManager() as db:
        _assert_tables_ready(db)
        funcionario = _buscar_funcionario_externo(db, ci)
        if not funcionario:
            return _json_error('No se encontró el funcionario seleccionado.', 404)

    payload_data = {
        'tipo_persona': data.get('tipo_persona') or 'PLANTA',
        'unidad_negocio_id': data.get('unidad_negocio_id'),
        'ci_nit': funcionario.get('ci'),
        'nit_referencia': funcionario.get('nit_referencia'),
        'nombre_completo': funcionario.get('nombre_completo'),
        'telefono': funcionario.get('telefono'),
        'correo': funcionario.get('correo'),
        'cargo_referencia': funcionario.get('cargo_referencia'),
        'regional_referencia': funcionario.get('regional_referencia'),
        'fecha_ingreso_referencia': _json_ready(funcionario.get('fecha_ingreso_referencia')),
        'banco_referencia': data.get('banco_referencia'),
        'cuenta_bancaria_referencia': data.get('cuenta_bancaria_referencia'),
        'cuenta_auxiliar_codigo': data.get('cuenta_auxiliar_codigo'),
        'estado': 'ACTIVO',
        'observacion': _clean(data.get('observacion')),
        'crear_auxiliar': data.get('crear_auxiliar', True),
        'origen_schema': 'funcionarios',
        'origen_tabla': 'funcionarios',
        'origen_clave': funcionario.get('ci'),
    }

    try:
        payload = _validar_payload(payload_data)
    except ValueError as exc:
        return _json_error(str(exc))

    with DatabaseManager() as db:
        _assert_tables_ready(db)
        unidad_rows = db.execute_query(
            """
            SELECT id
            FROM contabilidad.unidad_negocio
            WHERE id = %s
              AND activo IS TRUE
            LIMIT 1
            """,
            (payload['unidad_negocio_id'],)
        )
        if not unidad_rows:
            return _json_error('La unidad de negocio seleccionada no existe o está inactiva.')

        duplicado = _persona_duplicada(db, payload['tipo_persona'], payload['ci_nit'])
        if duplicado:
            return _json_error(
                f"Ya existe {duplicado['nombre_completo']} con el mismo CI/NIT/documento. No se permite duplicar identificadores en personas de planilla.",
                409,
                id=duplicado['id']
            )
        if payload['crear_auxiliar'] and not _cuenta_auxiliar_valida_db(db, payload['cuenta_auxiliar_codigo']):
            return _json_error('La cuenta contable auxiliar seleccionada no existe, está inactiva, no es postable o no requiere auxiliares.')
        cursor = db.conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(
                """
                INSERT INTO contabilidad.planilla_persona (
                    tipo_persona,
                    unidad_negocio_id,
                    ci_nit,
                    nit_referencia,
                    nombre_completo,
                    correo,
                    telefono,
                    cargo_referencia,
                    regional_referencia,
                    fecha_ingreso_referencia,
                    fecha_nacimiento,
                    nacionalidad,
                    sexo,
                    ocupacion_referencia,
                    haber_basico_referencia,
                    monto_minimo_mensual_referencia,
                    banco_referencia,
                    cuenta_bancaria_referencia,
                    tipo_respaldo_habitual,
                    estado,
                    observacion,
                    origen_schema,
                    origen_tabla,
                    origen_clave,
                    atributos
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    payload['tipo_persona'],
                    payload['unidad_negocio_id'],
                    payload['ci_nit'],
                    payload['nit_referencia'],
                    payload['nombre_completo'],
                    payload['correo'],
                    payload['telefono'],
                    payload['cargo_referencia'],
                    payload['regional_referencia'],
                    payload['fecha_ingreso_referencia'],
                    payload['fecha_nacimiento'],
                    payload['nacionalidad'],
                    payload['sexo'],
                    payload['ocupacion_referencia'],
                    payload['haber_basico_referencia'],
                    payload['monto_minimo_mensual_referencia'],
                    payload['banco_referencia'],
                    payload['cuenta_bancaria_referencia'],
                    payload['tipo_respaldo_habitual'],
                    payload['estado'],
                    payload['observacion'],
                    payload['origen_schema'],
                    payload['origen_tabla'],
                    payload['origen_clave'],
                    Json({'creado_por': _usuario_actual(), 'origen': ORIGEN_FUNCIONARIOS}),
                )
            )
            persona_id = cursor.fetchone()['id']
            auxiliar_id = None
            if payload['crear_auxiliar']:
                auxiliar_id = _asegurar_auxiliar_cursor(cursor, payload, persona_id)
                _asegurar_auxiliar_cuenta_cursor(cursor, auxiliar_id, payload['cuenta_auxiliar_codigo'])
            cursor.execute(
                """
                UPDATE contabilidad.planilla_persona
                SET auxiliar_id = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (auxiliar_id, persona_id)
            )
        finally:
            cursor.close()

    return _json_ok('Funcionario importado a Personas de Planilla.', id=persona_id)
