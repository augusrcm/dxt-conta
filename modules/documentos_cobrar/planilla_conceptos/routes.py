# ============================================================
# DXT CONTA - Conceptos de Planilla
# Configuracion base para planillas de planta y colaboradores.
# ============================================================

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import jsonify, render_template, request, session
from psycopg2 import errors
from psycopg2.extras import Json

from database.db_manager import DatabaseManager
from modules.planilla_conceptos import planilla_conceptos_bp
from utils.decorators import login_required, roles_required
from utils.planillas_security import mensaje_error_operacion


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]

TIPOS_PLANILLA = {
    'PLANTA': 'Planta',
    'COLABORADORES': 'Colaboradores',
    'AMBAS': 'Ambas',
}

TIPOS_CONCEPTO = {
    'INGRESO': 'Ingreso',
    'DESCUENTO': 'Descuento',
    'RETENCION': 'Retencion',
    'APORTE_PATRONAL': 'Aporte patronal',
    'NETO_INFORMATIVO': 'Informativo',
}

IMPACTOS = {
    'SUMA': 'Suma al liquido',
    'RESTA': 'Resta al liquido',
    'NO_AFECTA': 'No afecta liquido',
}

METODOS = {
    'MANUAL': 'Manual',
    'FIJO': 'Monto fijo',
    'PORCENTAJE': 'Porcentaje',
}

ESTADOS_FILTRO = {
    'ACTIVOS': 'Activos',
    'INACTIVOS': 'Inactivos',
    'TODOS': 'Todos',
}

IMPACTO_SUGERIDO = {
    'INGRESO': 'SUMA',
    'DESCUENTO': 'RESTA',
    'RETENCION': 'RESTA',
    'APORTE_PATRONAL': 'NO_AFECTA',
    'NETO_INFORMATIVO': 'NO_AFECTA',
}


# Catalogo base sugerido. No impone porcentajes ni cuentas; sirve para que el
# operador no tenga que memorizar nombres o codigos.
CONCEPTOS_SUGERIDOS = [
    {
        'codigo': 'HORAS_EXTRA', 'nombre': 'Horas extra', 'tipo_planilla': 'PLANTA',
        'tipo_concepto': 'INGRESO', 'impacto_liquido': 'SUMA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Ingresos adicionales', 'observacion': 'Ingreso adicional variable. La base mensual no se registra aquí.'
    },
    {
        'codigo': 'BONO_PRODUCCION', 'nombre': 'Bono de producción', 'tipo_planilla': 'PLANTA',
        'tipo_concepto': 'INGRESO', 'impacto_liquido': 'SUMA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Ingresos adicionales', 'observacion': 'Bono variable del mes con respaldo.'
    },
    {
        'codigo': 'OTROS_INGRESOS', 'nombre': 'Otros ingresos', 'tipo_planilla': 'AMBAS',
        'tipo_concepto': 'INGRESO', 'impacto_liquido': 'SUMA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Ingresos adicionales', 'observacion': 'Ingreso adicional no estructural.'
    },
    {
        'codigo': 'DESCUENTO_ATRASOS', 'nombre': 'Descuento por atrasos / faltas', 'tipo_planilla': 'PLANTA',
        'tipo_concepto': 'DESCUENTO', 'impacto_liquido': 'RESTA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Descuentos adicionales', 'observacion': 'Debe tener justificativo operativo.'
    },
    {
        'codigo': 'DESCUENTO_JUDICIAL', 'nombre': 'Descuento judicial / autorizado', 'tipo_planilla': 'PLANTA',
        'tipo_concepto': 'DESCUENTO', 'impacto_liquido': 'RESTA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Descuentos adicionales', 'observacion': 'Descuento autorizado o instruido formalmente.'
    },
    {
        'codigo': 'OTROS_DESCUENTOS', 'nombre': 'Otros descuentos', 'tipo_planilla': 'AMBAS',
        'tipo_concepto': 'DESCUENTO', 'impacto_liquido': 'RESTA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Descuentos adicionales', 'observacion': 'Descuento excepcional con explicación obligatoria.'
    },
    {
        'codigo': 'APORTE_PATRONAL_ADICIONAL', 'nombre': 'Aporte patronal adicional', 'tipo_planilla': 'PLANTA',
        'tipo_concepto': 'APORTE_PATRONAL', 'impacto_liquido': 'NO_AFECTA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': False,
        'grupo': 'Aportes patronales', 'observacion': 'Aporte o carga adicional, no reduce líquido del trabajador.'
    },
    {
        'codigo': 'SERVICIO_ADICIONAL', 'nombre': 'Servicio / tarea adicional', 'tipo_planilla': 'COLABORADORES',
        'tipo_concepto': 'INGRESO', 'impacto_liquido': 'SUMA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Honorarios colaboradores', 'observacion': 'Pago adicional al mínimo mensual referencial.'
    },
    {
        'codigo': 'RETENCION_SIN_FACTURA', 'nombre': 'Retención por servicio sin factura', 'tipo_planilla': 'COLABORADORES',
        'tipo_concepto': 'RETENCION', 'impacto_liquido': 'RESTA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Retenciones colaboradores', 'observacion': 'Retención aplicable cuando el pago no cuente con factura.'
    },
    {
        'codigo': 'DESCUENTO_COLABORADOR', 'nombre': 'Descuento colaborador', 'tipo_planilla': 'COLABORADORES',
        'tipo_concepto': 'DESCUENTO', 'impacto_liquido': 'RESTA', 'metodo_calculo': 'MANUAL', 'requiere_justificativo': True,
        'grupo': 'Descuentos colaboradores', 'observacion': 'Descuento operacional con justificativo.'
    },
]


# Mapa de sugerencias contables para el asistente "Cargar base".
# Los codigos reales no se queman aqui: se toman de Planilla / Parametros
# de la gestion activa, para que el usuario pueda modificar su plan contable
# sin tocar codigo.
CUENTAS_SUGERIDAS_CONCEPTO = {
    # Planta - ingresos adicionales: aumentan el total ganado y el liquido por pagar.
    'HORAS_EXTRA': {
        'debe': 'cuenta_gasto_sueldos_codigo',
        'haber': 'cuenta_sueldos_por_pagar_codigo',
    },
    'BONO_PRODUCCION': {
        'debe': 'cuenta_gasto_sueldos_codigo',
        'haber': 'cuenta_sueldos_por_pagar_codigo',
    },
    'OTROS_INGRESOS': {
        'debe': 'cuenta_gasto_sueldos_codigo',
        'haber': 'cuenta_sueldos_por_pagar_codigo',
    },

    # Planta - descuentos/retenciones: disminuyen el liquido y generan obligacion o compensacion.
    'DESCUENTO_ATRASOS': {
        'debe': 'cuenta_sueldos_por_pagar_codigo',
        'haber': 'cuenta_descuentos_por_pagar_codigo',
    },
    'DESCUENTO_JUDICIAL': {
        'debe': 'cuenta_sueldos_por_pagar_codigo',
        'haber': 'cuenta_descuentos_por_pagar_codigo',
    },
    'OTROS_DESCUENTOS': {
        'debe': 'cuenta_sueldos_por_pagar_codigo',
        'haber': 'cuenta_descuentos_por_pagar_codigo',
    },

    # Planta - aportes patronales: no afectan el liquido del trabajador.
    'APORTE_PATRONAL_ADICIONAL': {
        'debe': 'cuenta_gasto_aportes_patronales_codigo',
        'haber': 'cuenta_aportes_patronales_por_pagar_codigo',
    },

    # Colaboradores - honorarios y retenciones.
    'SERVICIO_ADICIONAL': {
        'debe': 'cuenta_gasto_honorarios_codigo',
        'haber': 'cuenta_honorarios_por_pagar_codigo',
    },
    'RETENCION_SIN_FACTURA': {
        'debe': 'cuenta_honorarios_por_pagar_codigo',
        'haber': 'cuenta_retenciones_honorarios_por_pagar_codigo',
    },
    'DESCUENTO_COLABORADOR': {
        'debe': 'cuenta_honorarios_por_pagar_codigo',
        'haber': 'cuenta_descuentos_por_pagar_codigo',
    },
}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


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


def _limit_text(value: Any, field_name: str, max_len: int, required: bool = False) -> str | None:
    text = _clean(value)
    if required and not text:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(text) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return text or None


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'si', 'on')


def _parse_int(value: Any, field_name: str, default: int = 0) -> int:
    text = _clean(value)
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" debe ser numerico.') from exc


def _parse_decimal(value: Any, field_name: str) -> Decimal | None:
    text = _clean(value).replace(',', '.')
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" debe ser numerico.') from exc
    if parsed < 0:
        raise ValueError(f'El campo "{field_name}" no puede ser negativo.')
    return parsed


def _normalizar_codigo(value: Any, nombre: Any = None) -> str:
    raw = _upper(value)
    if not raw and nombre:
        raw = _upper(nombre)
    raw = re.sub(r'[^A-Z0-9_\-]+', '_', raw)
    raw = re.sub(r'_+', '_', raw).strip('_')
    return raw[:40]


def _cuenta_label(row: dict[str, Any]) -> str:
    codigo = _clean(row.get('codigo'))
    nombre = _clean(row.get('nombre'))
    return f'{codigo} · {nombre}' if nombre else codigo


def _obtener_parametros_cuentas_activos(db: DatabaseManager) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT
            cuenta_gasto_sueldos_codigo,
            cuenta_sueldos_por_pagar_codigo,
            cuenta_afp_por_pagar_codigo,
            cuenta_rc_iva_por_pagar_codigo,
            cuenta_descuentos_por_pagar_codigo,
            cuenta_gasto_aportes_patronales_codigo,
            cuenta_aportes_patronales_por_pagar_codigo,
            cuenta_gasto_honorarios_codigo,
            cuenta_honorarios_por_pagar_codigo,
            cuenta_retenciones_honorarios_por_pagar_codigo
        FROM contabilidad.planilla_parametro
        WHERE activo = TRUE
        ORDER BY gestion DESC, id DESC
        LIMIT 1
        """
    )
    return rows[0] if rows else {}


def _obtener_cuentas_postables(db: DatabaseManager, codigos: list[str]) -> dict[str, dict[str, Any]]:
    codigos = sorted({codigo for codigo in codigos if codigo})
    if not codigos:
        return {}
    placeholders = ', '.join(['%s'] * len(codigos))
    rows = db.execute_query(
        f"""
        SELECT codigo, COALESCE(nombre, '') AS nombre, tipo, naturaleza
        FROM contabilidad.cuenta
        WHERE codigo IN ({placeholders})
          AND activo = TRUE
          AND es_postable = TRUE
        """,
        tuple(codigos),
    )
    return {row['codigo']: row for row in rows}


def _resolver_cuentas_sugeridas_base(db: DatabaseManager) -> dict[str, dict[str, str]]:
    parametros = _obtener_parametros_cuentas_activos(db)
    if not parametros:
        return {}

    codigos: list[str] = []
    for mapping in CUENTAS_SUGERIDAS_CONCEPTO.values():
        for key in mapping.values():
            codigo = _clean(parametros.get(key))
            if codigo:
                codigos.append(codigo)

    cuentas = _obtener_cuentas_postables(db, codigos)
    sugerencias: dict[str, dict[str, str]] = {}
    for concepto_codigo, mapping in CUENTAS_SUGERIDAS_CONCEPTO.items():
        item: dict[str, str] = {}
        for lado, param_key in mapping.items():
            cuenta_codigo = _clean(parametros.get(param_key))
            cuenta = cuentas.get(cuenta_codigo)
            if not cuenta:
                continue
            item[f'cuenta_{lado}_codigo'] = cuenta_codigo
            item[f'cuenta_{lado}_label'] = _cuenta_label(cuenta)
            item[f'cuenta_{lado}_origen'] = param_key
        if item:
            sugerencias[concepto_codigo] = item
    return sugerencias


def _validar_cuentas_postables_payload(db: DatabaseManager, payload: dict[str, Any]) -> None:
    codigos = [
        _clean(payload.get('cuenta_debe_codigo')),
        _clean(payload.get('cuenta_haber_codigo')),
    ]
    codigos = [codigo for codigo in codigos if codigo]
    if not codigos:
        return
    disponibles = _obtener_cuentas_postables(db, codigos)
    faltantes = sorted(set(codigos) - set(disponibles.keys()))
    if faltantes:
        raise ValueError('Una de las cuentas seleccionadas no existe, no esta activa o no es imputable.')


def _assert_tables_ready(db: DatabaseManager) -> None:
    rows = db.execute_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'contabilidad'
          AND table_name = 'planilla_concepto'
          AND column_name IN (
              'id', 'codigo', 'nombre', 'tipo_planilla', 'tipo_concepto',
              'impacto_liquido', 'metodo_calculo', 'cuenta_debe_codigo',
              'cuenta_haber_codigo', 'requiere_justificativo', 'activo'
          )
        """
    )
    columns = {row['column_name'] for row in rows}
    required = {
        'id', 'codigo', 'nombre', 'tipo_planilla', 'tipo_concepto',
        'impacto_liquido', 'metodo_calculo', 'cuenta_debe_codigo',
        'cuenta_haber_codigo', 'requiere_justificativo', 'activo'
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError('Faltan tablas o columnas de Conceptos de Planilla. Ejecute primero el script SQL base de planillas.')


def _validar_payload(data: dict[str, Any]) -> dict[str, Any]:
    nombre = _limit_text(data.get('nombre'), 'Nombre', 180, required=True)
    codigo = _normalizar_codigo(data.get('codigo'), nombre)
    tipo_planilla = _upper(data.get('tipo_planilla') or 'AMBAS')
    tipo_concepto = _upper(data.get('tipo_concepto'))
    impacto_liquido = _upper(data.get('impacto_liquido') or IMPACTO_SUGERIDO.get(tipo_concepto, 'NO_AFECTA'))
    metodo_calculo = _upper(data.get('metodo_calculo') or 'MANUAL')
    porcentaje = _parse_decimal(data.get('porcentaje_referencial'), 'Porcentaje referencial')
    monto = _parse_decimal(data.get('monto_referencial'), 'Monto referencial')
    cuenta_debe_codigo = _limit_text(data.get('cuenta_debe_codigo'), 'Cuenta debe', 30)
    cuenta_haber_codigo = _limit_text(data.get('cuenta_haber_codigo'), 'Cuenta haber', 30)
    requiere_justificativo = _parse_bool(data.get('requiere_justificativo'), default=False)
    observacion = _limit_text(data.get('observacion'), 'Observacion', 500)

    if not codigo:
        raise ValueError('El codigo del concepto es obligatorio.')
    if codigo != _normalizar_codigo(codigo):
        raise ValueError('El codigo del concepto solo puede contener letras, numeros, guion y guion bajo.')
    if tipo_planilla not in TIPOS_PLANILLA:
        raise ValueError('El tipo de planilla no es valido.')
    if tipo_concepto not in TIPOS_CONCEPTO:
        raise ValueError('El tipo de concepto no es valido.')
    if impacto_liquido not in IMPACTOS:
        raise ValueError('El impacto al liquido no es valido.')
    if metodo_calculo not in METODOS:
        raise ValueError('El metodo de calculo no es valido.')
    if metodo_calculo == 'PORCENTAJE' and porcentaje is not None and porcentaje > Decimal('100'):
        raise ValueError('El porcentaje referencial no puede exceder 100.')
    atributos = {
        'impacto_sugerido': IMPACTO_SUGERIDO.get(tipo_concepto),
        'editable_en_planilla': True,
    }

    return {
        'codigo': codigo,
        'nombre': nombre,
        'tipo_planilla': tipo_planilla,
        'tipo_concepto': tipo_concepto,
        'impacto_liquido': impacto_liquido,
        'metodo_calculo': metodo_calculo,
        'porcentaje_referencial': porcentaje,
        'monto_referencial': monto,
        'cuenta_debe_codigo': cuenta_debe_codigo,
        'cuenta_haber_codigo': cuenta_haber_codigo,
        'requiere_justificativo': requiere_justificativo,
        'orden': 0,
        'observacion': observacion,
        'atributos': atributos,
    }



def _catalogo_sugerido_para_template(existing_codes: set[str] | None = None, cuentas_sugeridas: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    existing_codes = existing_codes or set()
    cuentas_sugeridas = cuentas_sugeridas or {}
    items = []
    for item in CONCEPTOS_SUGERIDOS:
        copy = dict(item)
        copy['tipo_planilla_label'] = TIPOS_PLANILLA.get(copy['tipo_planilla'], copy['tipo_planilla'])
        copy['tipo_concepto_label'] = TIPOS_CONCEPTO.get(copy['tipo_concepto'], copy['tipo_concepto'])
        copy['impacto_label'] = IMPACTOS.get(copy['impacto_liquido'], copy['impacto_liquido'])
        copy['metodo_label'] = METODOS.get(copy['metodo_calculo'], copy['metodo_calculo'])
        copy['ya_configurado'] = copy['codigo'] in existing_codes
        sugerencia = cuentas_sugeridas.get(copy['codigo'], {})
        copy['cuenta_debe_codigo'] = sugerencia.get('cuenta_debe_codigo', '')
        copy['cuenta_debe_label'] = sugerencia.get('cuenta_debe_label', '')
        copy['cuenta_haber_codigo'] = sugerencia.get('cuenta_haber_codigo', '')
        copy['cuenta_haber_label'] = sugerencia.get('cuenta_haber_label', '')
        items.append(copy)
    return items


def _concepto_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item['tipo_planilla_label'] = TIPOS_PLANILLA.get(_upper(row.get('tipo_planilla')), row.get('tipo_planilla'))
    item['tipo_concepto_label'] = TIPOS_CONCEPTO.get(_upper(row.get('tipo_concepto')), row.get('tipo_concepto'))
    item['impacto_label'] = IMPACTOS.get(_upper(row.get('impacto_liquido')), row.get('impacto_liquido'))
    item['metodo_label'] = METODOS.get(_upper(row.get('metodo_calculo')), row.get('metodo_calculo'))
    item['estado_label'] = 'Activo' if row.get('activo') else 'Inactivo'
    item['cuenta_debe_label'] = f"{row.get('cuenta_debe_codigo')} · {row.get('cuenta_debe_nombre')}" if row.get('cuenta_debe_codigo') else ''
    item['cuenta_haber_label'] = f"{row.get('cuenta_haber_codigo')} · {row.get('cuenta_haber_nombre')}" if row.get('cuenta_haber_codigo') else ''
    return _json_ready(item)


def _obtener_concepto(db: DatabaseManager, concepto_id: int):
    rows = db.execute_query(
        """
        SELECT pc.*, cd.nombre AS cuenta_debe_nombre, ch.nombre AS cuenta_haber_nombre
        FROM contabilidad.planilla_concepto pc
        LEFT JOIN contabilidad.cuenta cd ON cd.codigo = pc.cuenta_debe_codigo
        LEFT JOIN contabilidad.cuenta ch ON ch.codigo = pc.cuenta_haber_codigo
        WHERE pc.id = %s
        """,
        (concepto_id,),
    )
    return rows[0] if rows else None


@planilla_conceptos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    tipo_planilla = _upper(request.args.get('tipo_planilla'))
    tipo_concepto = _upper(request.args.get('tipo_concepto'))
    estado = _upper(request.args.get('estado') or 'ACTIVOS')
    q = _clean(request.args.get('q'))

    if tipo_planilla not in TIPOS_PLANILLA:
        tipo_planilla = ''
    if tipo_concepto not in TIPOS_CONCEPTO:
        tipo_concepto = ''
    if estado not in ESTADOS_FILTRO:
        estado = 'ACTIVOS'

    where = []
    params: list[Any] = []
    if tipo_planilla:
        where.append('pc.tipo_planilla = %s')
        params.append(tipo_planilla)
    if tipo_concepto:
        where.append('pc.tipo_concepto = %s')
        params.append(tipo_concepto)
    if estado == 'ACTIVOS':
        where.append('pc.activo = TRUE')
    elif estado == 'INACTIVOS':
        where.append('pc.activo = FALSE')
    if q:
        like = f'%{q}%'
        where.append('(pc.codigo ILIKE %s OR pc.nombre ILIKE %s OR COALESCE(pc.observacion, \'\') ILIKE %s)')
        params.extend([like, like, like])

    where_sql = 'WHERE ' + ' AND '.join(where) if where else ''

    try:
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            rows = db.execute_query(
                f"""
                SELECT pc.*, cd.nombre AS cuenta_debe_nombre, ch.nombre AS cuenta_haber_nombre
                FROM contabilidad.planilla_concepto pc
                LEFT JOIN contabilidad.cuenta cd ON cd.codigo = pc.cuenta_debe_codigo
                LEFT JOIN contabilidad.cuenta ch ON ch.codigo = pc.cuenta_haber_codigo
                {where_sql}
                ORDER BY pc.activo DESC, pc.tipo_planilla, pc.tipo_concepto, pc.codigo
                """,
                tuple(params),
            )
            stats_rows = db.execute_query(
                """
                SELECT
                  COUNT(*)::int AS total,
                  COUNT(*) FILTER (WHERE activo = TRUE)::int AS activos,
                  COUNT(*) FILTER (WHERE activo = FALSE)::int AS inactivos,
                  COUNT(*) FILTER (WHERE activo = TRUE AND tipo_planilla IN ('PLANTA','AMBAS'))::int AS planta,
                  COUNT(*) FILTER (WHERE activo = TRUE AND tipo_planilla IN ('COLABORADORES','AMBAS'))::int AS colaboradores
                FROM contabilidad.planilla_concepto
                """
            )
            stats = stats_rows[0] if stats_rows else {}
            code_rows = db.execute_query(
                """
                SELECT codigo
                FROM contabilidad.planilla_concepto
                """
            )
            existing_codes = {row['codigo'] for row in code_rows}
            cuentas_sugeridas = _resolver_cuentas_sugeridas_base(db)
    except Exception as exc:
        rows = []
        stats = {'total': 0, 'activos': 0, 'inactivos': 0, 'planta': 0, 'colaboradores': 0}
        error = 'No se pudo cargar Conceptos de Planilla. Revise la configuración operativa del módulo.'
        existing_codes = set()
        cuentas_sugeridas = {}
    else:
        error = None

    conceptos = [_concepto_to_dict(row) for row in rows]
    filtros = {
        'tipo_planilla': tipo_planilla,
        'tipo_concepto': tipo_concepto,
        'estado': estado,
        'q': q,
    }
    return render_template(
        'planilla_conceptos_index.html',
        conceptos=conceptos,
        stats=stats,
        filtros=filtros,
        error=error,
        puede_editar=_puede_editar(),
        tipos_planilla=TIPOS_PLANILLA,
        tipos_concepto=TIPOS_CONCEPTO,
        impactos=IMPACTOS,
        metodos=METODOS,
        estados_filtro=ESTADOS_FILTRO,
        conceptos_sugeridos=_catalogo_sugerido_para_template(existing_codes, cuentas_sugeridas),
    )


@planilla_conceptos_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('planilla_conceptos_help.html')


@planilla_conceptos_bp.route('/api/cuentas')
@login_required
@roles_required(ROLES_LECTURA)
def api_cuentas():
    term = _clean(request.args.get('q'))
    where = ['activo = TRUE', 'es_postable = TRUE']
    params: list[Any] = []
    if term:
        like = f'%{term}%'
        where.append('(codigo ILIKE %s OR COALESCE(nombre, \'\') ILIKE %s)')
        params.extend([like, like])
    with DatabaseManager() as db:
        rows = db.execute_query(
            f"""
            SELECT codigo, COALESCE(nombre, '') AS nombre, tipo, naturaleza
            FROM contabilidad.cuenta
            WHERE {' AND '.join(where)}
            ORDER BY codigo ASC
            LIMIT 40
            """,
            tuple(params),
        )
    results = [
        {
            'id': row['codigo'],
            'text': f"{row['codigo']} · {row['nombre']}",
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'tipo': row['tipo'],
            'naturaleza': row['naturaleza'],
        }
        for row in rows
    ]
    return jsonify({'results': results})


@planilla_conceptos_bp.route('/api/<int:concepto_id>')
@login_required
@roles_required(ROLES_LECTURA)
def api_obtener(concepto_id: int):
    with DatabaseManager() as db:
        row = _obtener_concepto(db, concepto_id)
    if not row:
        return _json_error('El concepto de planilla no existe.', 404)
    return _json_ok(concepto=_concepto_to_dict(row))



@planilla_conceptos_bp.route('/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def guardar():
    data = request.get_json(silent=True) or request.form.to_dict()
    concepto_id = _clean(data.get('id'))
    try:
        payload = _validar_payload(data)
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            _validar_cuentas_postables_payload(db, payload)
            if concepto_id:
                try:
                    cid = int(concepto_id)
                except ValueError as exc:
                    raise ValueError('El identificador del concepto no es valido.') from exc
                row = _obtener_concepto(db, cid)
                if not row:
                    return _json_error('El concepto de planilla no existe.', 404)
                afectados = db.execute_update(
                    """
                    UPDATE contabilidad.planilla_concepto
                    SET codigo = %s,
                        nombre = %s,
                        tipo_planilla = %s,
                        tipo_concepto = %s,
                        impacto_liquido = %s,
                        metodo_calculo = %s,
                        porcentaje_referencial = %s,
                        monto_referencial = %s,
                        cuenta_debe_codigo = %s,
                        cuenta_haber_codigo = %s,
                        requiere_justificativo = %s,
                        orden = 0,
                        observacion = %s,
                        atributos = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        payload['codigo'], payload['nombre'], payload['tipo_planilla'], payload['tipo_concepto'],
                        payload['impacto_liquido'], payload['metodo_calculo'], payload['porcentaje_referencial'],
                        payload['monto_referencial'], payload['cuenta_debe_codigo'], payload['cuenta_haber_codigo'],
                        payload['requiere_justificativo'], payload['observacion'], Json(payload['atributos']), cid,
                    ),
                )
                if afectados == 0:
                    return _json_error('No se actualizo el concepto.', 400)
                message = 'Concepto actualizado correctamente.'
            else:
                db.execute_insert(
                    """
                    INSERT INTO contabilidad.planilla_concepto
                    (codigo, nombre, tipo_planilla, tipo_concepto, impacto_liquido, metodo_calculo,
                     porcentaje_referencial, monto_referencial, cuenta_debe_codigo, cuenta_haber_codigo,
                     requiere_justificativo, activo, orden, observacion, atributos)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, 0, %s, %s)
                    """,
                    (
                        payload['codigo'], payload['nombre'], payload['tipo_planilla'], payload['tipo_concepto'],
                        payload['impacto_liquido'], payload['metodo_calculo'], payload['porcentaje_referencial'],
                        payload['monto_referencial'], payload['cuenta_debe_codigo'], payload['cuenta_haber_codigo'],
                        payload['requiere_justificativo'], payload['observacion'], Json(payload['atributos']),
                    ),
                    return_id=True,
                )
                message = 'Concepto creado correctamente.'
        return _json_ok(message)
    except errors.UniqueViolation:
        return _json_error('Ya existe un concepto con ese codigo.', 409)
    except errors.ForeignKeyViolation:
        return _json_error('Una de las cuentas seleccionadas no existe o no esta disponible.', 400)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(mensaje_error_operacion('guardar el concepto'), 500)


@planilla_conceptos_bp.route('/cargar-sugeridos', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def cargar_sugeridos():
    data = request.get_json(silent=True) or request.form.to_dict()
    filtro = _upper(data.get('tipo_planilla') or 'TODAS')
    if filtro not in ('TODAS', 'PLANTA', 'COLABORADORES'):
        return _json_error('El tipo de planilla seleccionado no es valido.', 400)

    def aplica(item: dict[str, Any]) -> bool:
        if filtro == 'TODAS':
            return True
        return item['tipo_planilla'] in (filtro, 'AMBAS')

    creados = 0
    actualizados = 0
    omitidos = 0
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        cuentas_sugeridas = _resolver_cuentas_sugeridas_base(db)
        for item in CONCEPTOS_SUGERIDOS:
            if not aplica(item):
                continue
            exists = db.execute_query(
                """
                SELECT id, cuenta_debe_codigo, cuenta_haber_codigo
                FROM contabilidad.planilla_concepto
                WHERE codigo = %s
                LIMIT 1
                """,
                (item['codigo'],),
            )
            sugerencia = cuentas_sugeridas.get(item['codigo'], {})
            cuenta_debe_codigo = sugerencia.get('cuenta_debe_codigo')
            cuenta_haber_codigo = sugerencia.get('cuenta_haber_codigo')
            if exists:
                row = exists[0]
                set_parts = []
                update_params: list[Any] = []
                if not row.get('cuenta_debe_codigo') and cuenta_debe_codigo:
                    set_parts.append('cuenta_debe_codigo = %s')
                    update_params.append(cuenta_debe_codigo)
                if not row.get('cuenta_haber_codigo') and cuenta_haber_codigo:
                    set_parts.append('cuenta_haber_codigo = %s')
                    update_params.append(cuenta_haber_codigo)
                if set_parts:
                    set_parts.append('actualizado_en = CURRENT_TIMESTAMP')
                    update_params.append(row['id'])
                    db.execute_update(
                        f"""
                        UPDATE contabilidad.planilla_concepto
                        SET {', '.join(set_parts)}
                        WHERE id = %s
                        """,
                        tuple(update_params),
                    )
                    actualizados += 1
                else:
                    omitidos += 1
                continue
            attrs = {
                'catalogo_base': True,
                'grupo': item.get('grupo'),
                'editable_en_planilla': True,
                'cuentas_sugeridas': {
                    'debe_origen': sugerencia.get('cuenta_debe_origen'),
                    'haber_origen': sugerencia.get('cuenta_haber_origen'),
                },
            }
            db.execute_insert(
                """
                INSERT INTO contabilidad.planilla_concepto
                (codigo, nombre, tipo_planilla, tipo_concepto, impacto_liquido, metodo_calculo,
                 porcentaje_referencial, monto_referencial, cuenta_debe_codigo, cuenta_haber_codigo,
                 requiere_justificativo, activo, orden, observacion, atributos)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, TRUE, 0, %s, %s)
                """,
                (
                    item['codigo'], item['nombre'], item['tipo_planilla'], item['tipo_concepto'],
                    item['impacto_liquido'], item['metodo_calculo'], cuenta_debe_codigo, cuenta_haber_codigo,
                    item['requiere_justificativo'], item.get('observacion'), Json(attrs),
                ),
                return_id=True,
            )
            creados += 1
    if creados == 0 and actualizados == 0:
        return _json_ok('No hay conceptos nuevos para cargar ni cuentas sugeridas pendientes por completar.', creados=creados, actualizados=actualizados, omitidos=omitidos)
    mensaje = f'Base sugerida cargada: {creados} concepto(s) creado(s)'
    if actualizados:
        mensaje += f' y {actualizados} concepto(s) actualizado(s) con cuentas sugeridas'
    mensaje += '.'
    return _json_ok(mensaje, creados=creados, actualizados=actualizados, omitidos=omitidos)


@planilla_conceptos_bp.route('/limpiar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def limpiar_conceptos():
    data = request.get_json(silent=True) or request.form.to_dict()
    motivo = _limit_text(data.get('motivo'), 'Motivo', 500) or 'Limpieza global de conceptos base.'
    usuario = _clean(session.get('usuario') or session.get('username') or session.get('nombre_usuario') or 'sistema')
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        total_rows = db.execute_query("SELECT COUNT(*)::int AS total FROM contabilidad.planilla_concepto")
        total = int(total_rows[0]['total'] or 0) if total_rows else 0
        if total == 0:
            return _json_ok('No existen conceptos para limpiar.', eliminados=0, referencias=0)
        refs = db.execute_update(
            """
            UPDATE contabilidad.planilla_detalle_concepto pdc
            SET atributos = COALESCE(pdc.atributos, '{}'::jsonb) || jsonb_build_object(
                    'concepto_base_eliminado', jsonb_build_object(
                        'id', pc.id,
                        'codigo', pc.codigo,
                        'nombre', pc.nombre,
                        'eliminado_en', CURRENT_TIMESTAMP,
                        'eliminado_por', %s,
                        'motivo', %s
                    )
                ),
                concepto_id = NULL,
                actualizado_en = CURRENT_TIMESTAMP
            FROM contabilidad.planilla_concepto pc
            WHERE pdc.concepto_id = pc.id
            """,
            (usuario, motivo),
        )
        eliminados = db.execute_delete("DELETE FROM contabilidad.planilla_concepto")
    return _json_ok(
        f'Se eliminaron {eliminados} concepto(s). Las planillas ya generadas conservan su copia histórica.',
        eliminados=eliminados,
        referencias=refs,
    )


@planilla_conceptos_bp.route('/eliminar/<int:concepto_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def eliminar_concepto(concepto_id: int):
    data = request.get_json(silent=True) or request.form.to_dict()
    motivo = _limit_text(data.get('motivo'), 'Motivo', 500) or 'Eliminación de concepto base.'
    usuario = _clean(session.get('usuario') or session.get('username') or session.get('nombre_usuario') or 'sistema')
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        row = _obtener_concepto(db, concepto_id)
        if not row:
            return _json_error('El concepto de planilla no existe.', 404)
        refs = db.execute_update(
            """
            UPDATE contabilidad.planilla_detalle_concepto
            SET atributos = COALESCE(atributos, '{}'::jsonb) || jsonb_build_object(
                    'concepto_base_eliminado', jsonb_build_object(
                        'id', %s,
                        'codigo', %s,
                        'nombre', %s,
                        'eliminado_en', CURRENT_TIMESTAMP,
                        'eliminado_por', %s,
                        'motivo', %s
                    )
                ),
                concepto_id = NULL,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE concepto_id = %s
            """,
            (concepto_id, row.get('codigo'), row.get('nombre'), usuario, motivo, concepto_id),
        )
        eliminados = db.execute_delete("DELETE FROM contabilidad.planilla_concepto WHERE id = %s", (concepto_id,))
        if eliminados == 0:
            return _json_error('No se eliminó el concepto.', 400)
    return _json_ok(
        'Concepto eliminado correctamente. Las planillas ya generadas conservan su copia histórica.',
        referencias=refs,
    )


@planilla_conceptos_bp.route('/estado-global', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def cambiar_estado_global():
    data = request.get_json(silent=True) or request.form.to_dict()
    activo = _parse_bool(data.get('activo'), default=False)
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        afectados = db.execute_update(
            """
            UPDATE contabilidad.planilla_concepto
            SET activo = %s, actualizado_en = CURRENT_TIMESTAMP
            WHERE activo IS DISTINCT FROM %s
            """,
            (activo, activo),
        )
    return _json_ok(
        f'Se {"activaron" if activo else "inactivaron"} {afectados} concepto(s).',
        afectados=afectados,
    )


@planilla_conceptos_bp.route('/estado/<int:concepto_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def cambiar_estado(concepto_id: int):
    data = request.get_json(silent=True) or request.form.to_dict()
    activo = _parse_bool(data.get('activo'), default=True)
    with DatabaseManager() as db:
        row = _obtener_concepto(db, concepto_id)
        if not row:
            return _json_error('El concepto de planilla no existe.', 404)
        db.execute_update(
            """
            UPDATE contabilidad.planilla_concepto
            SET activo = %s, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (activo, concepto_id),
        )
    return _json_ok('Concepto activado correctamente.' if activo else 'Concepto inactivado correctamente.')
