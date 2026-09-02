# ============================================================
# DXT CONTA - Parametros de Planilla
# Configuracion normativa/referencial por gestion.
# ============================================================

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from datetime import datetime

from flask import jsonify, render_template, request, session

from database.db_manager import DatabaseManager
from modules.planilla_parametros import planilla_parametros_bp
from utils.decorators import login_required, roles_required
from utils.planillas_security import mensaje_error_operacion

ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
TIPOS_EMPRESA = {
    'SERVICIOS_COMERCIAL': 'Servicios / Comercial',
    'PRODUCTIVA_INDUSTRIAL': 'Productiva / Industrial',
    'PERSONALIZADA': 'Personalizada',
}

CUENTAS_SUGERIDAS = {
    'cuenta_gasto_sueldos_codigo': '6.1.1.001',
    'cuenta_sueldos_por_pagar_codigo': '2.1.4.001',
    'cuenta_afp_por_pagar_codigo': '2.1.4.005',
    'cuenta_rc_iva_por_pagar_codigo': '2.1.4.008',
    'cuenta_descuentos_por_pagar_codigo': '2.1.4.009',
    'cuenta_gasto_aportes_patronales_codigo': '6.1.1.005',
    'cuenta_aportes_patronales_por_pagar_codigo': '2.1.4.005',
    'cuenta_gasto_honorarios_codigo': '6.1.1.017',
    'cuenta_honorarios_por_pagar_codigo': '2.1.1.001',
    'cuenta_retenciones_honorarios_por_pagar_codigo': '2.1.3.009',
}

CUENTAS_SUGERIDAS_LABEL = {
    'cuenta_gasto_sueldos_codigo': 'Gasto sueldos / salarios',
    'cuenta_sueldos_por_pagar_codigo': 'Sueldos por pagar',
    'cuenta_afp_por_pagar_codigo': 'AFP/Gestora por pagar',
    'cuenta_rc_iva_por_pagar_codigo': 'RC-IVA por pagar',
    'cuenta_descuentos_por_pagar_codigo': 'Otros descuentos por pagar',
    'cuenta_gasto_aportes_patronales_codigo': 'Gasto aportes patronales',
    'cuenta_aportes_patronales_por_pagar_codigo': 'Aportes patronales por pagar',
    'cuenta_gasto_honorarios_codigo': 'Gasto honorarios colaboradores',
    'cuenta_honorarios_por_pagar_codigo': 'Honorarios / colaboradores por pagar',
    'cuenta_retenciones_honorarios_por_pagar_codigo': 'Retenciones honorarios por pagar',
}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def _json_ready(value: Any):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    return value


def _json_ok(message: str | None = None, **kwargs):
    payload = {'success': True}
    if message:
        payload['message'] = message
    payload.update(kwargs)
    return jsonify(_json_ready(payload))


def _json_error(message: str, status: int = 400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(_json_ready(payload)), status


def _puede_editar() -> bool:
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except (TypeError, ValueError):
        return False


def _decimal(value: Any, field: str, required: bool = True) -> Decimal:
    text = _clean(value).replace(',', '.')
    if not text:
        if required:
            raise ValueError(f'El campo "{field}" es obligatorio.')
        return Decimal('0')
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'El campo "{field}" debe ser numérico.') from exc
    if number < 0:
        raise ValueError(f'El campo "{field}" no puede ser negativo.')
    return number


def _int(value: Any, field: str) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field}" debe ser numérico.') from exc
    if number < 2000:
        raise ValueError(f'El campo "{field}" no es válido.')
    return number


def _bool(value: Any, default: bool = False) -> bool:
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'si', 'sí', 'on', 'yes')


def _cuenta(value: Any) -> str | None:
    text = _clean(value)
    return text or None


def _validar_cuentas_existentes(db: DatabaseManager, payload: dict[str, Any]):
    cuentas = [v for k, v in payload.items() if k.startswith('cuenta_') and v]
    if not cuentas:
        return
    rows = db.execute_query(
        """
        SELECT codigo
        FROM contabilidad.cuenta
        WHERE codigo = ANY(%s)
          AND activo IS TRUE
          AND es_postable IS TRUE
        """,
        (cuentas,)
    )
    existentes = {r['codigo'] for r in rows}
    faltantes = [c for c in cuentas if c not in existentes]
    if faltantes:
        raise ValueError('Una o más cuentas contables no existen, no están activas o no son postables: ' + ', '.join(faltantes))



def _cuentas_por_codigo(db: DatabaseManager, codigos: list[str]) -> dict[str, dict[str, Any]]:
    codigos_limpios = [c for c in dict.fromkeys(codigos) if c]
    if not codigos_limpios:
        return {}
    rows = db.execute_query(
        """
        SELECT codigo, COALESCE(nombre, '') AS nombre, tipo, naturaleza, activo, es_postable
        FROM contabilidad.cuenta
        WHERE codigo = ANY(%s)
        """,
        (codigos_limpios,)
    )
    return {r['codigo']: dict(r) for r in rows}


def _adjuntar_labels_cuentas(db: DatabaseManager, row: dict[str, Any]) -> dict[str, Any]:
    codigos = [row.get(k) for k in CUENTAS_SUGERIDAS.keys() if row.get(k)]
    cuentas = _cuentas_por_codigo(db, codigos)
    labels = {}
    for key in CUENTAS_SUGERIDAS.keys():
        codigo = row.get(key)
        cuenta = cuentas.get(codigo or '')
        if codigo and cuenta:
            labels[key] = f"{codigo} · {cuenta.get('nombre') or ''}"
        elif codigo:
            labels[key] = codigo
    row['cuentas_labels'] = labels
    return row

def _assert_ready(db: DatabaseManager):
    rows = db.execute_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'contabilidad'
          AND table_name = 'planilla_parametro'
        """
    )
    cols = {r['column_name'] for r in rows}
    required = {
        'gestion', 'salario_minimo_nacional', 'tipo_empresa_bono',
        'base_bono_smn_multiplicador', 'porcentaje_afp_laboral',
        'jornada_semanal_horas', 'multiplo_rc_iva_smn',
        'aplica_bono_antiguedad', 'aplica_afp_laboral', 'activo',
        'cuenta_gasto_sueldos_codigo', 'cuenta_sueldos_por_pagar_codigo',
        'cuenta_afp_por_pagar_codigo', 'cuenta_rc_iva_por_pagar_codigo',
        'cuenta_descuentos_por_pagar_codigo', 'cuenta_gasto_aportes_patronales_codigo',
        'cuenta_aportes_patronales_por_pagar_codigo',
        'cuenta_gasto_honorarios_codigo', 'cuenta_honorarios_por_pagar_codigo',
        'cuenta_retenciones_honorarios_por_pagar_codigo'
    }
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError('Falta ejecutar el SQL de parámetros de planilla.')


def _validar(data: dict[str, Any]) -> dict[str, Any]:
    gestion = _int(data.get('gestion'), 'Gestión')
    smn = _decimal(data.get('salario_minimo_nacional'), 'Salario mínimo nacional')
    tipo_empresa = _upper(data.get('tipo_empresa_bono') or 'SERVICIOS_COMERCIAL')
    if tipo_empresa not in TIPOS_EMPRESA:
        raise ValueError('El tipo de empresa para bono no es válido.')
    base = _decimal(data.get('base_bono_smn_multiplicador'), 'Base bono SMN')
    afp = _decimal(data.get('porcentaje_afp_laboral'), 'Porcentaje AFP/Gestora')
    jornada = _decimal(data.get('jornada_semanal_horas'), 'Jornada semanal')
    rciva = _decimal(data.get('multiplo_rc_iva_smn'), 'Múltiplo RC-IVA')
    observacion = _clean(data.get('observacion'))[:800] or None
    return {
        'gestion': gestion,
        'salario_minimo_nacional': smn,
        'tipo_empresa_bono': tipo_empresa,
        'base_bono_smn_multiplicador': base,
        'porcentaje_afp_laboral': afp,
        'jornada_semanal_horas': jornada,
        'multiplo_rc_iva_smn': rciva,
        'aplica_bono_antiguedad': _bool(data.get('aplica_bono_antiguedad'), True),
        'aplica_afp_laboral': _bool(data.get('aplica_afp_laboral'), True),
        'activo': _bool(data.get('activo'), True),
        'cuenta_gasto_sueldos_codigo': _cuenta(data.get('cuenta_gasto_sueldos_codigo')),
        'cuenta_sueldos_por_pagar_codigo': _cuenta(data.get('cuenta_sueldos_por_pagar_codigo')),
        'cuenta_afp_por_pagar_codigo': _cuenta(data.get('cuenta_afp_por_pagar_codigo')),
        'cuenta_rc_iva_por_pagar_codigo': _cuenta(data.get('cuenta_rc_iva_por_pagar_codigo')),
        'cuenta_descuentos_por_pagar_codigo': _cuenta(data.get('cuenta_descuentos_por_pagar_codigo')),
        'cuenta_gasto_aportes_patronales_codigo': _cuenta(data.get('cuenta_gasto_aportes_patronales_codigo')),
        'cuenta_aportes_patronales_por_pagar_codigo': _cuenta(data.get('cuenta_aportes_patronales_por_pagar_codigo')),
        'cuenta_gasto_honorarios_codigo': _cuenta(data.get('cuenta_gasto_honorarios_codigo')),
        'cuenta_honorarios_por_pagar_codigo': _cuenta(data.get('cuenta_honorarios_por_pagar_codigo')),
        'cuenta_retenciones_honorarios_por_pagar_codigo': _cuenta(data.get('cuenta_retenciones_honorarios_por_pagar_codigo')),
        'observacion': observacion,
    }


@planilla_parametros_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    error = None
    stats = {'total': 0, 'activos': 0}
    try:
        with DatabaseManager() as db:
            _assert_ready(db)
            row = db.execute_query("SELECT COUNT(*)::int total, COUNT(*) FILTER (WHERE activo)::int activos FROM contabilidad.planilla_parametro")[0]
            stats = dict(row)
    except Exception as exc:
        error = 'No se pudo cargar Parámetros de Planilla. Revise la configuración operativa del módulo.'
    return render_template('planilla_parametros_index.html', error=error, stats=stats, puede_editar=_puede_editar(), tipos_empresa=TIPOS_EMPRESA)


@planilla_parametros_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('planilla_parametros_help.html')


@planilla_parametros_bp.route('/listar')
@login_required
@roles_required(ROLES_LECTURA)
def listar():
    estado = _upper(request.args.get('estado') or 'ACTIVOS')
    q = _clean(request.args.get('q'))
    where = []
    params = []
    if estado == 'ACTIVOS':
        where.append('activo IS TRUE')
    elif estado == 'INACTIVOS':
        where.append('activo IS FALSE')
    if q:
        where.append('(gestion::text ILIKE %s OR COALESCE(observacion,\'\') ILIKE %s)')
        params.extend([f'%{q}%', f'%{q}%'])
    where_sql = 'WHERE ' + ' AND '.join(where) if where else ''
    with DatabaseManager() as db:
        _assert_ready(db)
        rows = db.execute_query(
            f"""
            SELECT *,
                   CASE tipo_empresa_bono
                     WHEN 'SERVICIOS_COMERCIAL' THEN 'Servicios / Comercial'
                     WHEN 'PRODUCTIVA_INDUSTRIAL' THEN 'Productiva / Industrial'
                     ELSE 'Personalizada'
                   END AS tipo_empresa_label
            FROM contabilidad.planilla_parametro
            {where_sql}
            ORDER BY gestion DESC
            """,
            tuple(params),
        )
    return jsonify({'data': _json_ready([dict(r) for r in rows])})


@planilla_parametros_bp.route('/obtener/<int:parametro_id>')
@login_required
@roles_required(ROLES_LECTURA)
def obtener(parametro_id: int):
    with DatabaseManager() as db:
        _assert_ready(db)
        rows = db.execute_query("SELECT * FROM contabilidad.planilla_parametro WHERE id = %s", (parametro_id,))
    if not rows:
        return _json_error('El parámetro de planilla no existe.', 404)
    with DatabaseManager() as db:
        data = _adjuntar_labels_cuentas(db, dict(rows[0]))
    return _json_ok(data=data)


@planilla_parametros_bp.route('/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def guardar():
    data = request.get_json(silent=True) or {}
    try:
        parametro_id = data.get('id')
        parametro_id = int(parametro_id) if parametro_id not in (None, '', 'null') else None
        payload = _validar(data)
    except ValueError as exc:
        return _json_error(str(exc))
    with DatabaseManager() as db:
        _assert_ready(db)
        try:
            _validar_cuentas_existentes(db, payload)
        except ValueError as exc:
            return _json_error(str(exc))
        if parametro_id:
            afect = db.execute_update(
                """
                UPDATE contabilidad.planilla_parametro
                SET gestion=%s, salario_minimo_nacional=%s, tipo_empresa_bono=%s,
                    base_bono_smn_multiplicador=%s, porcentaje_afp_laboral=%s,
                    jornada_semanal_horas=%s, multiplo_rc_iva_smn=%s,
                    aplica_bono_antiguedad=%s, aplica_afp_laboral=%s,
                    activo=%s,
                    cuenta_gasto_sueldos_codigo=%s,
                    cuenta_sueldos_por_pagar_codigo=%s,
                    cuenta_afp_por_pagar_codigo=%s,
                    cuenta_rc_iva_por_pagar_codigo=%s,
                    cuenta_descuentos_por_pagar_codigo=%s,
                    cuenta_gasto_aportes_patronales_codigo=%s,
                    cuenta_aportes_patronales_por_pagar_codigo=%s,
                    cuenta_gasto_honorarios_codigo=%s,
                    cuenta_honorarios_por_pagar_codigo=%s,
                    cuenta_retenciones_honorarios_por_pagar_codigo=%s,
                    observacion=%s, actualizado_en=CURRENT_TIMESTAMP
                WHERE id=%s
                """,
                (*payload.values(), parametro_id),
            )
            if afect == 0:
                return _json_error('El parámetro de planilla no existe.', 404)
            return _json_ok('Parámetro actualizado correctamente.')
        try:
            db.execute_insert(
                """
                INSERT INTO contabilidad.planilla_parametro
                (gestion, salario_minimo_nacional, tipo_empresa_bono, base_bono_smn_multiplicador,
                 porcentaje_afp_laboral, jornada_semanal_horas, multiplo_rc_iva_smn,
                 aplica_bono_antiguedad, aplica_afp_laboral, activo,
                 cuenta_gasto_sueldos_codigo, cuenta_sueldos_por_pagar_codigo,
                 cuenta_afp_por_pagar_codigo, cuenta_rc_iva_por_pagar_codigo,
                 cuenta_descuentos_por_pagar_codigo, cuenta_gasto_aportes_patronales_codigo,
                 cuenta_aportes_patronales_por_pagar_codigo, cuenta_gasto_honorarios_codigo,
                 cuenta_honorarios_por_pagar_codigo, cuenta_retenciones_honorarios_por_pagar_codigo, observacion)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                tuple(payload.values()),
                return_id=True,
            )
        except Exception as exc:
            if 'uq_planilla_parametro_gestion' in str(exc) or 'duplicate key' in str(exc):
                return _json_error('Ya existe configuración para esa gestión.', 409)
            return _json_error(mensaje_error_operacion('guardar los parámetros de planilla'), 500)
    return _json_ok('Parámetro creado correctamente.')


@planilla_parametros_bp.route('/api/cuentas')
@login_required
@roles_required(ROLES_LECTURA)
def api_cuentas():
    term = _clean(request.args.get('q'))
    where = ['activo = TRUE', 'es_postable = TRUE']
    params: list[Any] = []
    if term:
        like = f'%{term}%'
        where.append("(codigo ILIKE %s OR COALESCE(nombre, '') ILIKE %s)")
        params.extend([like, like])
    with DatabaseManager() as db:
        rows = db.execute_query(
            f"""
            SELECT codigo, COALESCE(nombre, '') AS nombre, tipo, naturaleza
            FROM contabilidad.cuenta
            WHERE {' AND '.join(where)}
            ORDER BY codigo ASC
            LIMIT 50
            """,
            tuple(params),
        )
    return jsonify({'results': [{'id': r['codigo'], 'text': f"{r['codigo']} · {r['nombre']}", 'tipo': r['tipo'], 'naturaleza': r['naturaleza']} for r in rows]})



@planilla_parametros_bp.route('/api/sugerir-cuentas')
@login_required
@roles_required(ROLES_LECTURA)
def sugerir_cuentas():
    with DatabaseManager() as db:
        cuentas = _cuentas_por_codigo(db, list(CUENTAS_SUGERIDAS.values()))
    sugeridas = {}
    faltantes = []
    for campo, codigo in CUENTAS_SUGERIDAS.items():
        cuenta = cuentas.get(codigo)
        if cuenta and cuenta.get('activo') is True and cuenta.get('es_postable') is True:
            sugeridas[campo] = {
                'codigo': codigo,
                'nombre': cuenta.get('nombre') or '',
                'label': f"{codigo} · {cuenta.get('nombre') or ''}",
                'uso': CUENTAS_SUGERIDAS_LABEL.get(campo, campo),
            }
        else:
            faltantes.append({'campo': campo, 'codigo': codigo, 'uso': CUENTAS_SUGERIDAS_LABEL.get(campo, campo)})
    return _json_ok(data=sugeridas, faltantes=faltantes)


@planilla_parametros_bp.route('/api/copiar-anterior')
@login_required
@roles_required(ROLES_LECTURA)
def copiar_anterior():
    gestion_txt = _clean(request.args.get('gestion'))
    gestion = None
    if gestion_txt:
        try:
            gestion = int(gestion_txt)
        except ValueError:
            return _json_error('La gestión no es válida.')
    where = 'WHERE activo IS TRUE'
    params: list[Any] = []
    if gestion:
        where += ' AND gestion < %s'
        params.append(gestion)
    with DatabaseManager() as db:
        _assert_ready(db)
        rows = db.execute_query(
            f"""
            SELECT *
            FROM contabilidad.planilla_parametro
            {where}
            ORDER BY gestion DESC
            LIMIT 1
            """,
            tuple(params),
        )
        if not rows:
            return _json_error('No existe una gestión anterior activa para copiar.', 404)
        data = _adjuntar_labels_cuentas(db, dict(rows[0]))
    data.pop('id', None)
    if gestion:
        data['gestion'] = gestion
    return _json_ok(data=data)


@planilla_parametros_bp.route('/estado/<int:parametro_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def estado(parametro_id: int):
    data = request.get_json(silent=True) or {}
    activo = _bool(data.get('activo'), True)
    with DatabaseManager() as db:
        _assert_ready(db)
        afect = db.execute_update(
            """
            UPDATE contabilidad.planilla_parametro
            SET activo=%s, actualizado_en=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (activo, parametro_id),
        )
    if afect == 0:
        return _json_error('El parámetro de planilla no existe.', 404)
    return _json_ok('Parámetro activado correctamente.' if activo else 'Parámetro inactivado correctamente.')
