# ============================================================
# DXT CONTA - Documentos por Cobrar - Saldo Inicial
# Registro de saldos iniciales operativos por cobrar.
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from io import BytesIO

from flask import Response, current_app, jsonify, render_template, request, session
from psycopg2.extras import Json
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database.db_manager import DatabaseManager
from modules.saldos_iniciales_cobrar import saldos_iniciales_cobrar_bp
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
CUANTIA = Decimal('0.01')
CUANTIA_TC = Decimal('0.000001')

CUENTA_CARTERA_HISTORICA = '1.1.2.014'
CUENTA_CXC_RECOMENDADA = '1.1.2.002'
CUENTA_CXC_RECOMENDADA_ALT = '1.1.2.001'
CUENTA_CONTRAPARTIDA_RECOMENDADA = '4.1.1.009'
MODULO_ORIGEN = 'SALDOS_INICIALES_COBRAR'
TABLA_ORIGEN = 'contabilidad.documento_por_cobrar'
ESTADO_CONFIRMADO = 'CONFIRMADO'
ESTADO_ANULADO = 'ANULADO'

TIPOS_DOCUMENTO = {
    'FACTURA': 'Factura',
    'DOCUMENTO': 'Documento',
    'CONTRATO': 'Contrato',
    'NOTA_COBRO': 'Nota de cobro',
    'OTRO': 'Otro',
}

ESTADOS_DOCUMENTO = {
    'PENDIENTE': 'Pendiente',
    'PARCIAL': 'Parcial',
    'COBRADO': 'Cobrado',
    'ANULADO': 'Anulado',
}

ORIGENES_DOCUMENTO = {
    'HISTORICO': 'Saldo inicial',
    'VIGENTE_MANUAL': 'Vigente manual',
    'FACTURA_ELECTRONICA': 'Factura electronica',
}

TRATAMIENTOS_CONTABLES = {
    'CARTERA_HISTORICA': 'Saldo inicial por cobrar',
    'CXC_NORMAL': 'Cuentas por cobrar normal',
    'CXC_ESPECIFICA': 'Cuenta por cobrar especifica',
}


# ============================================================
# Helpers base
# ============================================================


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


def _usuario_id_actual():
    return session.get('user_id')


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


def _to_decimal(value: Any, field_name: str, allow_zero: bool = False, quant=CUANTIA) -> Decimal:
    if value in (None, ''):
        raise ValueError(f'El campo "{field_name}" es obligatorio.')

    text = str(value).strip().replace('Bs.', '').replace('Bs', '').replace(' ', '')
    if ',' in text and '.' in text:
        text = text.replace(',', '')
    elif ',' in text:
        text = text.replace(',', '.')

    try:
        number = Decimal(text).quantize(quant, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no tiene un formato valido.') from exc

    if allow_zero:
        if number < 0:
            raise ValueError(f'El campo "{field_name}" no puede ser negativo.')
    elif number <= 0:
        raise ValueError(f'El campo "{field_name}" debe ser mayor a cero.')

    return number


def _parse_int(value: Any, field_name: str, required: bool = True) -> int | None:
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" debe ser numerico.') from exc
    if parsed <= 0:
        raise ValueError(f'El campo "{field_name}" no es valido.')
    return parsed


def _parse_date(value: Any, field_name: str, required: bool = True):
    value = _clean(value)
    if not value:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha valida.') from exc


def _limit_text(value: Any, field_name: str, max_len: int, required: bool = False) -> str | None:
    text = _clean(value)
    if required and not text:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(text) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return text or None


def _money_label(value: Any) -> str:
    try:
        number = Decimal(str(value or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        number = Decimal('0.00')
    return f'{number:,.2f}'


def _date_label(value: Any) -> str:
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    text = str(value)
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return text


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


def _documento_editable(row: dict[str, Any]) -> bool:
    if not row:
        return False
    if _upper(row.get('estado')) == 'ANULADO':
        return False
    try:
        if int(row.get('cobros_aplicados') or 0) > 0:
            return False
    except (TypeError, ValueError):
        return False
    importe_cobrado = Decimal(str(row.get('importe_cobrado') or 0)).quantize(CUANTIA)
    return importe_cobrado == Decimal('0.00')


# ============================================================
# Catalogos y validaciones
# ============================================================


def _assert_tables_ready(db: DatabaseManager) -> None:
    rows = db.execute_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'contabilidad'
          AND table_name = 'documento_por_cobrar'
          AND column_name IN ('id', 'unidad_negocio_id', 'asiento_registro_id')
        """
    )
    columns = {row['column_name'] for row in rows}
    required = {'id', 'unidad_negocio_id', 'asiento_registro_id'}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(
            'Falta ajustar la tabla documento_por_cobrar. Ejecute el script '
            'database/20260529_ajustar_documento_por_cobrar_unidad_negocio.sql.'
        )


def _gestion_actual(db: DatabaseManager) -> int:
    rows = db.execute_query(
        """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
        """
    )
    if rows and rows[0].get('gestion') is not None:
        return int(rows[0]['gestion'])
    return date.today().year


def _get_unidad(db: DatabaseManager, unidad_id: int) -> dict[str, Any] | None:
    rows = db.execute_query(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre, activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_id,),
    )
    return dict(rows[0]) if rows else None


def _get_auxiliar_cliente(db: DatabaseManager, auxiliar_id: int) -> dict[str, Any] | None:
    rows = db.execute_query(
        """
        SELECT
            id,
            COALESCE(nit_ci, '') AS nit_ci,
            COALESCE(nombre, '') AS nombre,
            tipo,
            activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,),
    )
    return dict(rows[0]) if rows else None


def _get_moneda(db: DatabaseManager, codigo: str) -> dict[str, Any] | None:
    rows = db.execute_query(
        """
        SELECT codigo, COALESCE(nombre, codigo) AS nombre, COALESCE(simbolo, '') AS simbolo, activo
        FROM contabilidad.moneda
        WHERE UPPER(codigo) = UPPER(%s)
        LIMIT 1
        """,
        (codigo,),
    )
    return dict(rows[0]) if rows else None


def _get_cuenta(db: DatabaseManager, codigo: str) -> dict[str, Any] | None:
    rows = db.execute_query(
        """
        SELECT codigo, COALESCE(nombre, '') AS nombre, tipo, naturaleza, es_postable, activo
        FROM contabilidad.cuenta
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,),
    )
    return dict(rows[0]) if rows else None


def _cuenta_label(cuenta: dict[str, Any] | None) -> str:
    if not cuenta:
        return ''
    return f"{cuenta.get('codigo')} · {cuenta.get('nombre')}"


def _primera_cuenta_postable(db: DatabaseManager, condiciones: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    rows = db.execute_query(
        f"""
        SELECT codigo, COALESCE(nombre, '') AS nombre, tipo, naturaleza, es_postable, activo
        FROM contabilidad.cuenta
        WHERE activo = TRUE
          AND es_postable = TRUE
          AND {condiciones}
        ORDER BY codigo ASC
        LIMIT 1
        """,
        params,
    )
    return dict(rows[0]) if rows else None


def _cuentas_recomendadas(db: DatabaseManager) -> dict[str, Any]:
    cuenta_cartera_vigente = _get_cuenta(db, CUENTA_CXC_RECOMENDADA)
    if not cuenta_cartera_vigente or not cuenta_cartera_vigente.get('activo') or not cuenta_cartera_vigente.get('es_postable'):
        cuenta_cartera_vigente = _get_cuenta(db, CUENTA_CXC_RECOMENDADA_ALT)
    if not cuenta_cartera_vigente or not cuenta_cartera_vigente.get('activo') or not cuenta_cartera_vigente.get('es_postable'):
        cuenta_cartera_vigente = _primera_cuenta_postable(
            db,
            "tipo::text = 'ACTIVO' AND naturaleza::text = 'DEUDORA' AND nombre ILIKE %s",
            ('%POR COBRAR%',),
        )

    cuenta_contrapartida = _get_cuenta(db, CUENTA_CONTRAPARTIDA_RECOMENDADA)
    if not cuenta_contrapartida or not cuenta_contrapartida.get('activo') or not cuenta_contrapartida.get('es_postable'):
        cuenta_contrapartida = _primera_cuenta_postable(
            db,
            "tipo::text = 'INGRESO' AND naturaleza::text = 'ACREEDORA'",
            (),
        )

    return {
        'cartera_vigente': cuenta_cartera_vigente,
        'contrapartida_vigente': cuenta_contrapartida,
    }


def _fetch_catalogos_index(db: DatabaseManager) -> dict[str, Any]:
    unidades = db.execute_query(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
        """
    )
    monedas = db.execute_query(
        """
        SELECT codigo, COALESCE(nombre, codigo) AS nombre, COALESCE(simbolo, '') AS simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        ORDER BY CASE WHEN codigo = 'BOB' THEN 0 ELSE 1 END, codigo ASC
        """
    )
    cuenta_cartera_historica = _get_cuenta(db, CUENTA_CARTERA_HISTORICA)
    recomendaciones = _cuentas_recomendadas(db)
    return {
        'unidades': [dict(row) for row in unidades],
        'monedas': [dict(row) for row in monedas],
        'cuenta_cartera_historica': cuenta_cartera_historica,
        'cuenta_cartera_vigente': recomendaciones['cartera_vigente'],
        'cuenta_contrapartida_vigente': recomendaciones['contrapartida_vigente'],
    }


def _clasificar_documento(gestion_origen: int, gestion_actual: int) -> dict[str, str | bool]:
    if gestion_origen > gestion_actual:
        raise ValueError('La gestion origen no puede ser mayor a la gestion activa.')
    return {
        'origen_documento': 'HISTORICO',
        'tratamiento_contable': 'CARTERA_HISTORICA',
        'genera_asiento_registro': False,
        'etiqueta': 'Saldo inicial',
    }


def _glosa_sugerida(payload: dict[str, Any]) -> str:
    tipo = TIPOS_DOCUMENTO.get(payload['tipo_documento'], payload['tipo_documento']).lower()
    simbolo = payload.get('moneda', {}).get('simbolo') or payload['moneda_codigo']
    partes = [
        f"Registro saldo inicial por cobrar {tipo} Nro. {payload['numero_documento']}",
        f"gestion {payload['gestion_origen']}",
        f"cliente {payload['cliente_nombre']}",
        f"importe {simbolo} {_money_label(payload['importe_total'])}",
    ]
    if payload.get('fecha_vencimiento'):
        partes.insert(3, f"vencimiento {_date_label(payload['fecha_vencimiento'])}")
    return ', '.join(partes)[:500]


def _validar_payload(db: DatabaseManager, data: dict[str, Any], documento_id: int | None = None) -> dict[str, Any]:
    _assert_tables_ready(db)

    gestion_actual = _gestion_actual(db)
    unidad_negocio_id = _parse_int(data.get('unidad_negocio_id'), 'Unidad de negocio')
    cliente_auxiliar_id = _parse_int(data.get('cliente_auxiliar_id'), 'Cliente')
    gestion_origen = _parse_int(data.get('gestion_origen'), 'Gestion origen')
    fecha_documento = _parse_date(data.get('fecha_documento'), 'Fecha del documento')
    fecha_vencimiento = _parse_date(data.get('fecha_vencimiento'), 'Fecha de vencimiento', required=False)
    tipo_documento = _upper(data.get('tipo_documento'))
    numero_documento = _limit_text(data.get('numero_documento'), 'Numero de documento', 100, required=True)
    referencia_externa = _limit_text(data.get('referencia_externa'), 'Referencia externa', 150, required=False)
    moneda_codigo = _upper(data.get('moneda_codigo'))
    tipo_cambio = _to_decimal(data.get('tipo_cambio'), 'Tipo de cambio', quant=CUANTIA_TC)
    importe_total = _to_decimal(data.get('importe_total'), 'Importe total')
    descripcion_in = _limit_text(data.get('descripcion'), 'Descripcion', 500, required=False)
    observacion = _limit_text(data.get('observacion'), 'Observacion', 500, required=False)

    if tipo_documento not in TIPOS_DOCUMENTO:
        raise ValueError('El tipo de documento no es valido.')

    if gestion_origen < 2000:
        raise ValueError('La gestion origen no es valida.')

    clasificacion = _clasificar_documento(gestion_origen, gestion_actual)

    if fecha_documento.year != gestion_origen:
        raise ValueError('La fecha del documento debe corresponder a la gestion origen.')

    if fecha_vencimiento and fecha_vencimiento < fecha_documento:
        raise ValueError('La fecha de vencimiento no puede ser anterior a la fecha del documento.')

    unidad = _get_unidad(db, unidad_negocio_id)
    if not unidad:
        raise ValueError('La unidad de negocio seleccionada no existe.')
    if not unidad.get('activo'):
        raise ValueError('La unidad de negocio seleccionada esta inactiva.')

    cliente = _get_auxiliar_cliente(db, cliente_auxiliar_id)
    if not cliente:
        raise ValueError('El cliente seleccionado no existe.')
    if cliente.get('tipo') != 'CLIENTE':
        raise ValueError('El auxiliar seleccionado no es de tipo CLIENTE.')
    if not cliente.get('activo'):
        raise ValueError('El cliente seleccionado esta inactivo.')

    moneda = _get_moneda(db, moneda_codigo)
    if not moneda:
        raise ValueError('La moneda seleccionada no existe.')
    if not moneda.get('activo'):
        raise ValueError('La moneda seleccionada esta inactiva.')

    if clasificacion['origen_documento'] == 'HISTORICO':
        cuenta_cartera_codigo = CUENTA_CARTERA_HISTORICA
        cuenta_contrapartida_codigo = None
        cuenta_cartera = _get_cuenta(db, cuenta_cartera_codigo)
        cuenta_contrapartida = None
        if not cuenta_cartera:
            raise ValueError(f'No existe la cuenta puente {CUENTA_CARTERA_HISTORICA}.')
        if not cuenta_cartera.get('activo') or not cuenta_cartera.get('es_postable'):
            raise ValueError(f'La cuenta puente {CUENTA_CARTERA_HISTORICA} debe estar activa y ser postable.')
    else:
        if tipo_documento == 'FACTURA':
            raise ValueError('Las facturas de la gestion activa deben registrarse en el modulo de Facturas Electronicas.')
        cuenta_cartera_codigo = _clean(data.get('cuenta_cartera_codigo'))
        cuenta_contrapartida_codigo = _clean(data.get('cuenta_contrapartida_codigo'))
        if not cuenta_cartera_codigo:
            raise ValueError('La cuenta por cobrar es obligatoria para documentos de la gestion actual.')
        if not cuenta_contrapartida_codigo:
            raise ValueError('La cuenta contrapartida es obligatoria para documentos de la gestion actual.')
        if cuenta_cartera_codigo == cuenta_contrapartida_codigo:
            raise ValueError('La cuenta por cobrar y la contrapartida no pueden ser la misma cuenta.')
        cuenta_cartera = _get_cuenta(db, cuenta_cartera_codigo)
        cuenta_contrapartida = _get_cuenta(db, cuenta_contrapartida_codigo)
        if not cuenta_cartera:
            raise ValueError('La cuenta por cobrar seleccionada no existe.')
        if not cuenta_cartera.get('activo') or not cuenta_cartera.get('es_postable'):
            raise ValueError('La cuenta por cobrar debe estar activa y ser postable.')
        if not cuenta_contrapartida:
            raise ValueError('La cuenta contrapartida seleccionada no existe.')
        if not cuenta_contrapartida.get('activo') or not cuenta_contrapartida.get('es_postable'):
            raise ValueError('La cuenta contrapartida debe estar activa y ser postable.')

    duplicate_params = [numero_documento, cliente_auxiliar_id, gestion_origen]
    duplicate_filter = ''
    if documento_id:
        duplicate_filter = 'AND id <> %s'
        duplicate_params.append(documento_id)
    rows = db.execute_query(
        f"""
        SELECT id
        FROM contabilidad.documento_por_cobrar
        WHERE UPPER(TRIM(numero_documento)) = UPPER(TRIM(%s))
          AND cliente_auxiliar_id = %s
          AND gestion_origen = %s
          AND estado <> 'ANULADO'
          {duplicate_filter}
        LIMIT 1
        """,
        tuple(duplicate_params),
    )
    if rows:
        raise ValueError('Ya existe un documento activo con ese numero, cliente y gestion.')

    payload = {
        'gestion_actual': gestion_actual,
        'unidad_negocio_id': unidad_negocio_id,
        'cliente_auxiliar_id': cliente_auxiliar_id,
        'cliente_nit': cliente.get('nit_ci') or None,
        'cliente_nombre': cliente.get('nombre') or 'Cliente sin nombre',
        'gestion_origen': gestion_origen,
        'fecha_documento': fecha_documento,
        'fecha_vencimiento': fecha_vencimiento,
        'tipo_documento': tipo_documento,
        'numero_documento': numero_documento,
        'referencia_externa': referencia_externa,
        'moneda_codigo': moneda_codigo,
        'tipo_cambio': tipo_cambio,
        'importe_total': importe_total,
        'origen_documento': clasificacion['origen_documento'],
        'tratamiento_contable': clasificacion['tratamiento_contable'],
        'genera_asiento_registro': bool(clasificacion['genera_asiento_registro']),
        'cuenta_cartera_codigo': cuenta_cartera_codigo,
        'cuenta_contrapartida_codigo': cuenta_contrapartida_codigo,
        'observacion': observacion,
        'unidad': unidad,
        'cliente': cliente,
        'moneda': moneda,
        'cuenta_cartera': cuenta_cartera,
        'cuenta_contrapartida': cuenta_contrapartida,
    }
    payload['descripcion'] = descripcion_in or _glosa_sugerida(payload)
    return payload


# ============================================================
# Asiento contable automatico para documentos vigentes
# ============================================================


def _asiento_glosa(payload: dict[str, Any]) -> str:
    return (payload.get('descripcion') or _glosa_sugerida(payload))[:500]


def _asiento_referencia(payload: dict[str, Any]) -> str:
    base = payload.get('referencia_externa') or payload.get('numero_documento') or 'DOC-CXC'
    return f'DOC-CXC {base}'[:150]


def _insertar_detalles_asiento(db: DatabaseManager, asiento_id: int, documento_id: int, payload: dict[str, Any]) -> None:
    importe = payload['importe_total']
    glosa = _asiento_glosa(payload)[:300]
    referencia = _asiento_referencia(payload)
    atributos_base = {
        'documento_por_cobrar_id': documento_id,
        'origen': MODULO_ORIGEN,
        'tratamiento_contable': payload['tratamiento_contable'],
    }

    db.execute_insert(
        """
        INSERT INTO contabilidad.asiento_detalle (
            asiento_id,
            secuencia,
            cuenta_codigo,
            auxiliar_id,
            glosa,
            debe,
            haber,
            monto_moneda,
            referencia,
            atributos
        ) VALUES (%s, 1, %s, %s, %s, %s, 0, %s, %s, %s::jsonb)
        """,
        (
            asiento_id,
            payload['cuenta_cartera_codigo'],
            payload['cliente_auxiliar_id'],
            glosa,
            importe,
            importe,
            referencia,
            Json({**atributos_base, 'tipo': 'debe_documento_por_cobrar'}),
        ),
        return_id=False,
    )

    db.execute_insert(
        """
        INSERT INTO contabilidad.asiento_detalle (
            asiento_id,
            secuencia,
            cuenta_codigo,
            auxiliar_id,
            glosa,
            debe,
            haber,
            monto_moneda,
            referencia,
            atributos
        ) VALUES (%s, 2, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
        """,
        (
            asiento_id,
            payload['cuenta_contrapartida_codigo'],
            payload['cliente_auxiliar_id'],
            glosa,
            importe,
            importe,
            referencia,
            Json({**atributos_base, 'tipo': 'haber_contrapartida_registro'}),
        ),
        return_id=False,
    )


def _crear_asiento_registro(db: DatabaseManager, documento_id: int, payload: dict[str, Any]) -> int:
    asiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha,
            unidad_negocio_id,
            moneda_codigo,
            tipo_cambio,
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado,
            atributos,
            actualizado_en
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s,
            %s,
            %s,
            %s::contabilidad.estado_generico_enum,
            %s::jsonb,
            CURRENT_TIMESTAMP
        )
        """,
        (
            payload['fecha_documento'],
            payload['unidad_negocio_id'],
            payload['moneda_codigo'],
            payload['tipo_cambio'],
            _asiento_glosa(payload),
            _asiento_referencia(payload),
            MODULO_ORIGEN,
            TABLA_ORIGEN,
            documento_id,
            ESTADO_CONFIRMADO,
            Json({
                'origen': MODULO_ORIGEN,
                'documento_por_cobrar_id': documento_id,
                'usuario_id': _usuario_id_actual(),
                'usuario_nombre': _usuario_actual(),
                'creado_en': datetime.utcnow().isoformat(),
            }),
        ),
    )
    _insertar_detalles_asiento(db, asiento_id, documento_id, payload)
    db.execute_insert(
        """
        INSERT INTO contabilidad.documento_asiento (modulo, tabla_origen, origen_id, asiento_id)
        VALUES (%s, %s, %s, %s)
        """,
        (MODULO_ORIGEN, TABLA_ORIGEN, documento_id, asiento_id),
        return_id=False,
    )
    return int(asiento_id)


def _reemplazar_asiento_registro(db: DatabaseManager, asiento_id: int, documento_id: int, payload: dict[str, Any]) -> None:
    db.execute_update(
        """
        UPDATE contabilidad.asiento
        SET fecha = %s,
            unidad_negocio_id = %s,
            moneda_codigo = %s,
            tipo_cambio = %s,
            glosa = %s,
            referencia = %s,
            modulo_origen = %s,
            tabla_origen = %s,
            origen_id = %s,
            estado = %s::contabilidad.estado_generico_enum,
            atributos = COALESCE(atributos, '{}'::jsonb) || %s::jsonb,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            payload['fecha_documento'],
            payload['unidad_negocio_id'],
            payload['moneda_codigo'],
            payload['tipo_cambio'],
            _asiento_glosa(payload),
            _asiento_referencia(payload),
            MODULO_ORIGEN,
            TABLA_ORIGEN,
            documento_id,
            ESTADO_CONFIRMADO,
            Json({
                'actualizado_por_modulo': MODULO_ORIGEN,
                'usuario_id': _usuario_id_actual(),
                'usuario_nombre': _usuario_actual(),
                'actualizado_en': datetime.utcnow().isoformat(),
            }),
            asiento_id,
        ),
    )
    db.execute_delete('DELETE FROM contabilidad.asiento_detalle WHERE asiento_id = %s', (asiento_id,))
    _insertar_detalles_asiento(db, asiento_id, documento_id, payload)


def _anular_asiento_registro(db: DatabaseManager, asiento_id: int, motivo: str) -> None:
    db.execute_update(
        """
        UPDATE contabilidad.asiento
        SET estado = %s::contabilidad.estado_generico_enum,
            glosa = LEFT(glosa || ' | Anulado: ' || %s, 500),
            atributos = COALESCE(atributos, '{}'::jsonb) || %s::jsonb,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            ESTADO_ANULADO,
            motivo,
            Json({
                'anulado_por_modulo': MODULO_ORIGEN,
                'motivo_anulacion': motivo,
                'usuario_id': _usuario_id_actual(),
                'usuario_nombre': _usuario_actual(),
                'fecha_anulacion': datetime.utcnow().isoformat(),
            }),
            asiento_id,
        ),
    )


# ============================================================
# Consultas de documentos
# ============================================================


def _documento_row(db: DatabaseManager, documento_id: int, for_update: bool = False) -> dict[str, Any] | None:
    lock_sql = 'FOR UPDATE OF d' if for_update else ''
    rows = db.execute_query(
        f"""
        SELECT
            d.*,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            COALESCE(mc.simbolo, '') AS moneda_simbolo,
            COALESCE(cc.nombre, '') AS cuenta_cartera_nombre,
            COALESCE(cp.nombre, '') AS cuenta_contrapartida_nombre,
            (
                SELECT COUNT(*)
                FROM contabilidad.documento_por_cobrar_aplicacion ap
                WHERE ap.documento_por_cobrar_id = d.id
            ) AS cobros_aplicados
        FROM contabilidad.documento_por_cobrar d
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
        LEFT JOIN contabilidad.moneda mc ON mc.codigo = d.moneda_codigo
        LEFT JOIN contabilidad.cuenta cc ON cc.codigo = d.cuenta_cartera_codigo
        LEFT JOIN contabilidad.cuenta cp ON cp.codigo = d.cuenta_contrapartida_codigo
        WHERE d.id = %s
        {lock_sql}
        """,
        (documento_id,),
    )
    return dict(rows[0]) if rows else None




def _movimientos_documento(db: DatabaseManager, documento_id: int) -> dict[str, Any] | None:
    documento = _documento_row(db, documento_id)
    if not documento:
        return None

    importe_total = Decimal(str(documento.get('importe_total') or 0)).quantize(CUANTIA)
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')
    data: list[dict[str, Any]] = []

    fecha_documento = documento.get('fecha_documento')
    numero = documento.get('numero_documento') or ''
    tipo = TIPOS_DOCUMENTO.get(documento.get('tipo_documento'), documento.get('tipo_documento') or 'Documento')
    cliente = documento.get('cliente_nombre') or 'Sin cliente'
    glosa_inicial = documento.get('descripcion') or f"Registro saldo inicial por cobrar {tipo} Nro. {numero}, cliente {cliente}"

    if importe_total > 0:
        total_debe += importe_total
        data.append({
            'fecha': fecha_documento,
            'fecha_label': _date_label(fecha_documento),
            'glosa': glosa_inicial,
            'debe': importe_total,
            'debe_label': _money_label(importe_total),
            'haber': Decimal('0.00'),
            'haber_label': _money_label(Decimal('0.00')),
            'asiento_id': documento.get('asiento_registro_id'),
            'origen': 'DOCUMENTO',
        })

    rows = db.execute_query(
        """
        SELECT
            c.fecha,
            COALESCE(c.glosa, 'Cobro aplicado al documento') AS glosa,
            COALESCE(da.monto_aplicado, 0) AS monto_aplicado,
            c.asiento_id,
            c.estado
        FROM contabilidad.documento_por_cobrar_aplicacion da
        INNER JOIN contabilidad.cobro c ON c.id = da.cobro_id
        WHERE da.documento_por_cobrar_id = %s
          AND c.estado <> 'ANULADO'::contabilidad.estado_generico_enum
        ORDER BY c.fecha ASC, c.id ASC
        """,
        (documento_id,),
    )

    for row in rows:
        monto = Decimal(str(row.get('monto_aplicado') or 0)).quantize(CUANTIA)
        if monto <= 0:
            continue
        total_haber += monto
        data.append({
            'fecha': row.get('fecha'),
            'fecha_label': _date_label(row.get('fecha')),
            'glosa': row.get('glosa') or 'Cobro aplicado al documento',
            'debe': Decimal('0.00'),
            'debe_label': _money_label(Decimal('0.00')),
            'haber': monto,
            'haber_label': _money_label(monto),
            'asiento_id': row.get('asiento_id'),
            'origen': 'COBRO',
        })

    return {
        'documento': _serialize_documento(documento),
        'movimientos': _json_ready(data),
        'total_debe_label': _money_label(total_debe),
        'total_haber_label': _money_label(total_haber),
        'saldo_label': _money_label(total_debe - total_haber),
    }

def _serialize_documento(row: dict[str, Any]) -> dict[str, Any]:
    cuenta_cartera_label = ''
    if row.get('cuenta_cartera_codigo'):
        cuenta_cartera_label = f"{row.get('cuenta_cartera_codigo')} · {row.get('cuenta_cartera_nombre') or ''}".strip()
    cuenta_contrapartida_label = ''
    if row.get('cuenta_contrapartida_codigo'):
        cuenta_contrapartida_label = f"{row.get('cuenta_contrapartida_codigo')} · {row.get('cuenta_contrapartida_nombre') or ''}".strip()
    unidad_label = ''
    if row.get('unidad_codigo') or row.get('unidad_nombre'):
        unidad_label = f"{row.get('unidad_codigo') or ''} · {row.get('unidad_nombre') or ''}".strip(' ·')
    importe_total = Decimal(str(row.get('importe_total') or 0)).quantize(CUANTIA)
    importe_cobrado = Decimal(str(row.get('importe_cobrado') or 0)).quantize(CUANTIA)
    saldo_pendiente = Decimal(str(row.get('saldo_pendiente') or 0)).quantize(CUANTIA)
    return _json_ready({
        'id': row.get('id'),
        'unidad_negocio_id': row.get('unidad_negocio_id'),
        'unidad_label': unidad_label,
        'origen_documento': row.get('origen_documento'),
        'origen_label': ORIGENES_DOCUMENTO.get(row.get('origen_documento'), row.get('origen_documento')),
        'tipo_documento': row.get('tipo_documento'),
        'tipo_documento_label': TIPOS_DOCUMENTO.get(row.get('tipo_documento'), row.get('tipo_documento')),
        'tratamiento_contable': row.get('tratamiento_contable'),
        'tratamiento_label': TRATAMIENTOS_CONTABLES.get(row.get('tratamiento_contable'), row.get('tratamiento_contable')),
        'gestion_origen': row.get('gestion_origen'),
        'fecha_documento': row.get('fecha_documento'),
        'fecha_documento_label': _date_label(row.get('fecha_documento')),
        'fecha_vencimiento': row.get('fecha_vencimiento'),
        'fecha_vencimiento_label': _date_label(row.get('fecha_vencimiento')),
        'cliente_auxiliar_id': row.get('cliente_auxiliar_id'),
        'cliente_nit': row.get('cliente_nit'),
        'cliente_nombre': row.get('cliente_nombre'),
        'numero_documento': row.get('numero_documento'),
        'referencia_externa': row.get('referencia_externa'),
        'descripcion': row.get('descripcion'),
        'moneda_codigo': row.get('moneda_codigo'),
        'moneda_simbolo': row.get('moneda_simbolo') or row.get('moneda_codigo'),
        'tipo_cambio': row.get('tipo_cambio'),
        'importe_total': importe_total,
        'importe_total_label': _money_label(importe_total),
        'importe_cobrado': importe_cobrado,
        'importe_cobrado_label': _money_label(importe_cobrado),
        'saldo_pendiente': saldo_pendiente,
        'saldo_pendiente_label': _money_label(saldo_pendiente),
        'estado': row.get('estado'),
        'estado_label': ESTADOS_DOCUMENTO.get(row.get('estado'), row.get('estado')),
        'cuenta_cartera_codigo': row.get('cuenta_cartera_codigo'),
        'cuenta_cartera_label': cuenta_cartera_label,
        'cuenta_contrapartida_codigo': row.get('cuenta_contrapartida_codigo'),
        'cuenta_contrapartida_label': cuenta_contrapartida_label,
        'asiento_registro_id': row.get('asiento_registro_id'),
        'asiento_anulacion_id': row.get('asiento_anulacion_id'),
        'observacion': row.get('observacion'),
        'activo': row.get('activo'),
        'cobros_aplicados': int(row.get('cobros_aplicados') or 0),
        'editable': _documento_editable(row),
    })




# ============================================================
# PDF de respaldo del saldo inicial
# ============================================================


def _pdf_paragraph(text: Any, style):
    value = '' if text is None else str(text)
    value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return Paragraph(value or '-', style)


def _build_documento_pdf(documento: dict[str, Any], titulo: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=titulo)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#0f2340'), alignment=TA_CENTER, spaceAfter=8)
    section_style = ParagraphStyle('SectionTitle', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor('#17406f'), spaceBefore=8, spaceAfter=5)
    normal = ParagraphStyle('DocNormal', parent=styles['Normal'], fontSize=8, leading=10)
    small = ParagraphStyle('DocSmall', parent=styles['Normal'], fontSize=7, leading=9, textColor=colors.HexColor('#475569'))
    story = [Paragraph(titulo, title_style), Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", small), Spacer(1, 4 * mm)]
    simbolo = documento.get('moneda_simbolo') or documento.get('moneda_codigo') or ''
    cuenta_cartera = f"{documento.get('cuenta_cartera_codigo') or ''} - {documento.get('cuenta_cartera_nombre') or ''}".strip(' -')
    unidad = f"{documento.get('unidad_codigo') or ''} - {documento.get('unidad_nombre') or ''}".strip(' -') or '-'
    def table(items):
        rows = [[Paragraph(f'<b>{label}</b>', small), _pdf_paragraph(value, normal)] for label, value in items]
        t = Table(rows, colWidths=[42 * mm, 136 * mm], hAlign='LEFT')
        t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#dbe4ef')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#eef3f8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        return t
    story.append(Paragraph('Identificacion', section_style))
    story.append(table([
        ('Documento', f"{TIPOS_DOCUMENTO.get(documento.get('tipo_documento'), documento.get('tipo_documento'))} Nro. {documento.get('numero_documento') or '-'}"),
        ('Cliente', f"{documento.get('cliente_nombre') or '-'} · {documento.get('cliente_nit') or '-'}"),
        ('Unidad de negocio', unidad),
        ('Gestion origen', documento.get('gestion_origen') or '-'),
        ('Fecha documento', _date_label(documento.get('fecha_documento')) or '-'),
        ('Vencimiento', _date_label(documento.get('fecha_vencimiento')) or '-'),
        ('Estado', ESTADOS_DOCUMENTO.get(documento.get('estado'), documento.get('estado'))),
    ]))
    story.append(Paragraph('Importes', section_style))
    t = Table([
        ['Moneda', 'Tipo de cambio', 'Importe total', 'Cobrado', 'Saldo'],
        [documento.get('moneda_codigo') or '-', str(documento.get('tipo_cambio') or '1'), f"{simbolo} {_money_label(documento.get('importe_total'))}", f"{simbolo} {_money_label(documento.get('importe_cobrado'))}", f"{simbolo} {_money_label(documento.get('saldo_pendiente'))}"],
    ], colWidths=[30*mm,32*mm,38*mm,38*mm,38*mm], hAlign='LEFT')
    t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#dbe4ef')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17406f')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('ALIGN',(2,1),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story.append(t)
    story.append(Paragraph('Tratamiento contable', section_style))
    story.append(table([
        ('Naturaleza', 'Saldo inicial operativo por cobrar'),
        ('Asiento al registrar', 'No genera asiento'),
        ('Cuenta al cobrar', cuenta_cartera),
        ('Regla de cobro', 'Debe Caja/Banco; Haber cuenta puente de cartera histórica'),
    ]))
    story.append(Paragraph('Glosa y respaldo', section_style))
    story.append(table([
        ('Referencia externa', documento.get('referencia_externa') or '-'),
        ('Descripcion / glosa', documento.get('descripcion') or '-'),
        ('Observacion', documento.get('observacion') or '-'),
    ]))
    doc.build(story)
    return buffer.getvalue()
# ============================================================
# Rutas
# ============================================================


@saldos_iniciales_cobrar_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    try:
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            gestion_actual = _gestion_actual(db)
            catalogos = _fetch_catalogos_index(db)
    except Exception as exc:
        gestion_actual = date.today().year
        catalogos = {
            'unidades': [],
            'monedas': [],
            'cuenta_cartera_historica': None,
            'cuenta_cartera_vigente': None,
            'cuenta_contrapartida_vigente': None,
        }
        return render_template(
            'saldos_iniciales_cobrar_index.html',
            error_inicial=str(exc),
            gestion_actual=gestion_actual,
            puede_editar=_puede_editar(),
            tipos_documento=TIPOS_DOCUMENTO,
            estados_documento=ESTADOS_DOCUMENTO,
            origenes_documento=ORIGENES_DOCUMENTO,
            cuenta_cartera_historica_codigo=CUENTA_CARTERA_HISTORICA,
            **catalogos,
        )

    return render_template(
        'saldos_iniciales_cobrar_index.html',
        error_inicial=None,
        gestion_actual=gestion_actual,
        puede_editar=_puede_editar(),
        tipos_documento=TIPOS_DOCUMENTO,
        estados_documento=ESTADOS_DOCUMENTO,
        origenes_documento=ORIGENES_DOCUMENTO,
        cuenta_cartera_historica_codigo=CUENTA_CARTERA_HISTORICA,
        **catalogos,
    )


@saldos_iniciales_cobrar_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('saldos_iniciales_cobrar_help.html')


@saldos_iniciales_cobrar_bp.route('/data')
@login_required
@roles_required(ROLES_LECTURA)
def data():
    try:
        draw = int(request.args.get('draw', 1))
        start = max(int(request.args.get('start', 0)), 0)
        length = int(request.args.get('length', 10))
        if length <= 0 or length > 200:
            length = 10
        search_value = _clean(request.args.get('search[value]'))
        estado = _upper(request.args.get('estado')) or 'ABIERTOS'
        origen_documento = _upper(request.args.get('origen_documento'))
        gestion_origen = _clean(request.args.get('gestion_origen'))
        cliente_auxiliar_id = _clean(request.args.get('cliente_auxiliar_id'))

        where = ["d.activo = TRUE", "d.origen_documento = 'HISTORICO'", "d.tratamiento_contable = 'CARTERA_HISTORICA'"]
        params: list[Any] = []

        if estado == 'ABIERTOS':
            where.append("d.estado IN ('PENDIENTE', 'PARCIAL')")
            where.append('d.saldo_pendiente > 0')
        elif estado and estado != 'TODOS':
            where.append('d.estado = %s')
            params.append(estado)
        if origen_documento:
            where.append('d.origen_documento = %s')
            params.append(origen_documento)
        if gestion_origen:
            where.append('d.gestion_origen = %s')
            params.append(int(gestion_origen))
        if cliente_auxiliar_id:
            where.append('d.cliente_auxiliar_id = %s')
            params.append(int(cliente_auxiliar_id))
        if search_value:
            like = f'%{search_value}%'
            where.append(
                """(
                    d.numero_documento ILIKE %s
                    OR COALESCE(d.cliente_nombre, '') ILIKE %s
                    OR COALESCE(d.cliente_nit, '') ILIKE %s
                    OR COALESCE(d.referencia_externa, '') ILIKE %s
                    OR COALESCE(d.descripcion, '') ILIKE %s
                )"""
            )
            params.extend([like, like, like, like, like])

        where_sql = ' AND '.join(where)
        with DatabaseManager() as db:
            total_rows = db.execute_query(
                "SELECT COUNT(*) AS total FROM contabilidad.documento_por_cobrar d WHERE d.activo = TRUE AND d.origen_documento = 'HISTORICO' AND d.tratamiento_contable = 'CARTERA_HISTORICA'"
            )
            filtered_rows = db.execute_query(
                f"SELECT COUNT(*) AS total FROM contabilidad.documento_por_cobrar d WHERE {where_sql}",
                tuple(params),
            )
            rows = db.execute_query(
                f"""
                SELECT
                    d.*,
                    COALESCE(un.codigo, '') AS unidad_codigo,
                    COALESCE(un.nombre, '') AS unidad_nombre,
                    COALESCE(mc.simbolo, '') AS moneda_simbolo,
                    COALESCE(cc.nombre, '') AS cuenta_cartera_nombre,
                    COALESCE(cp.nombre, '') AS cuenta_contrapartida_nombre,
                    (
                        SELECT COUNT(*)
                        FROM contabilidad.documento_por_cobrar_aplicacion ap
                        WHERE ap.documento_por_cobrar_id = d.id
                    ) AS cobros_aplicados
                FROM contabilidad.documento_por_cobrar d
                LEFT JOIN contabilidad.unidad_negocio un ON un.id = d.unidad_negocio_id
                LEFT JOIN contabilidad.moneda mc ON mc.codigo = d.moneda_codigo
                LEFT JOIN contabilidad.cuenta cc ON cc.codigo = d.cuenta_cartera_codigo
                LEFT JOIN contabilidad.cuenta cp ON cp.codigo = d.cuenta_contrapartida_codigo
                WHERE {where_sql}
                ORDER BY d.fecha_documento DESC, d.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params + [length, start]),
            )
        return jsonify({
            'draw': draw,
            'recordsTotal': int(total_rows[0]['total']) if total_rows else 0,
            'recordsFiltered': int(filtered_rows[0]['total']) if filtered_rows else 0,
            'data': [_serialize_documento(dict(row)) for row in rows],
        })
    except Exception as exc:
        return jsonify({'draw': 1, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': [], 'error': str(exc)})


@saldos_iniciales_cobrar_bp.route('/obtener/<int:documento_id>')
@login_required
@roles_required(ROLES_LECTURA)
def obtener(documento_id: int):
    with DatabaseManager() as db:
        row = _documento_row(db, documento_id)
    if not row:
        return _json_error('Documento no encontrado.', 404)
    return _json_ok(documento=_serialize_documento(row))


@saldos_iniciales_cobrar_bp.route('/crear', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def crear():
    try:
        payload_in = request.get_json(silent=True) or {}
        with DatabaseManager() as db:
            payload = _validar_payload(db, payload_in)
            documento_id = db.execute_insert(
                """
                INSERT INTO contabilidad.documento_por_cobrar (
                    unidad_negocio_id,
                    origen_documento,
                    tipo_documento,
                    tratamiento_contable,
                    gestion_origen,
                    fecha_documento,
                    fecha_vencimiento,
                    cliente_auxiliar_id,
                    cliente_nit,
                    cliente_nombre,
                    numero_documento,
                    referencia_externa,
                    descripcion,
                    moneda_codigo,
                    tipo_cambio,
                    importe_total,
                    importe_cobrado,
                    saldo_pendiente,
                    estado,
                    cuenta_cartera_codigo,
                    cuenta_contrapartida_codigo,
                    asiento_registro_id,
                    observacion,
                    activo,
                    actualizado_en
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, 0, %s, 'PENDIENTE',
                    %s, %s, NULL, %s, TRUE, CURRENT_TIMESTAMP
                )
                """,
                (
                    payload['unidad_negocio_id'],
                    payload['origen_documento'],
                    payload['tipo_documento'],
                    payload['tratamiento_contable'],
                    payload['gestion_origen'],
                    payload['fecha_documento'],
                    payload['fecha_vencimiento'],
                    payload['cliente_auxiliar_id'],
                    payload['cliente_nit'],
                    payload['cliente_nombre'],
                    payload['numero_documento'],
                    payload['referencia_externa'],
                    payload['descripcion'],
                    payload['moneda_codigo'],
                    payload['tipo_cambio'],
                    payload['importe_total'],
                    payload['importe_total'],
                    payload['cuenta_cartera_codigo'],
                    payload['cuenta_contrapartida_codigo'],
                    payload['observacion'],
                ),
            )
            asiento_id = None
            if payload['genera_asiento_registro']:
                asiento_id = _crear_asiento_registro(db, int(documento_id), payload)
                db.execute_update(
                    """
                    UPDATE contabilidad.documento_por_cobrar
                    SET asiento_registro_id = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (asiento_id, documento_id),
                )
        mensaje = 'Documento registrado correctamente.'
        if asiento_id:
            mensaje = 'Documento vigente registrado con asiento contable automatico.'
        return _json_ok(mensaje, id=documento_id, asiento_id=asiento_id)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo registrar el documento: {exc}', 500)


@saldos_iniciales_cobrar_bp.route('/editar/<int:documento_id>', methods=['PUT'])
@login_required
@roles_required(ROLES_EDICION)
def editar(documento_id: int):
    try:
        payload_in = request.get_json(silent=True) or {}
        with DatabaseManager() as db:
            row = _documento_row(db, documento_id, for_update=True)
            if not row:
                return _json_error('Documento no encontrado.', 404)
            if row.get('origen_documento') == 'FACTURA_ELECTRONICA':
                return _json_error('Los documentos originados en Facturas Electronicas no se editan desde este modulo.', 400)
            if not _documento_editable(row):
                return _json_error('Solo se puede editar un documento pendiente sin cobros aplicados.', 400)

            payload = _validar_payload(db, payload_in, documento_id=documento_id)
            asiento_previo_id = row.get('asiento_registro_id')
            asiento_id = asiento_previo_id

            if asiento_previo_id and not payload['genera_asiento_registro']:
                _anular_asiento_registro(
                    db,
                    int(asiento_previo_id),
                    'Documento reclasificado como historico sin asiento de registro',
                )
                asiento_id = None
            elif asiento_previo_id and payload['genera_asiento_registro']:
                _reemplazar_asiento_registro(db, int(asiento_previo_id), documento_id, payload)
                asiento_id = int(asiento_previo_id)
            elif not asiento_previo_id and payload['genera_asiento_registro']:
                asiento_id = _crear_asiento_registro(db, documento_id, payload)

            db.execute_update(
                """
                UPDATE contabilidad.documento_por_cobrar
                SET unidad_negocio_id = %s,
                    origen_documento = %s,
                    tipo_documento = %s,
                    tratamiento_contable = %s,
                    gestion_origen = %s,
                    fecha_documento = %s,
                    fecha_vencimiento = %s,
                    cliente_auxiliar_id = %s,
                    cliente_nit = %s,
                    cliente_nombre = %s,
                    numero_documento = %s,
                    referencia_externa = %s,
                    descripcion = %s,
                    moneda_codigo = %s,
                    tipo_cambio = %s,
                    importe_total = %s,
                    importe_cobrado = 0,
                    saldo_pendiente = %s,
                    estado = 'PENDIENTE',
                    cuenta_cartera_codigo = %s,
                    cuenta_contrapartida_codigo = %s,
                    asiento_registro_id = %s,
                    asiento_anulacion_id = CASE WHEN %s::bigint IS NOT NULL AND %s::bigint IS NULL THEN %s ELSE asiento_anulacion_id END,
                    observacion = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    payload['unidad_negocio_id'],
                    payload['origen_documento'],
                    payload['tipo_documento'],
                    payload['tratamiento_contable'],
                    payload['gestion_origen'],
                    payload['fecha_documento'],
                    payload['fecha_vencimiento'],
                    payload['cliente_auxiliar_id'],
                    payload['cliente_nit'],
                    payload['cliente_nombre'],
                    payload['numero_documento'],
                    payload['referencia_externa'],
                    payload['descripcion'],
                    payload['moneda_codigo'],
                    payload['tipo_cambio'],
                    payload['importe_total'],
                    payload['importe_total'],
                    payload['cuenta_cartera_codigo'],
                    payload['cuenta_contrapartida_codigo'],
                    asiento_id,
                    asiento_previo_id,
                    asiento_id,
                    asiento_previo_id,
                    payload['observacion'],
                    documento_id,
                ),
            )
        return _json_ok('Documento actualizado correctamente.', id=documento_id, asiento_id=asiento_id)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo actualizar el documento: {exc}', 500)


@saldos_iniciales_cobrar_bp.route('/anular/<int:documento_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def anular(documento_id: int):
    try:
        data_in = request.get_json(silent=True) or {}
        motivo = _limit_text(data_in.get('motivo'), 'Motivo de anulacion', 300, required=True)
        with DatabaseManager() as db:
            row = _documento_row(db, documento_id, for_update=True)
            if not row:
                return _json_error('Documento no encontrado.', 404)
            if row.get('origen_documento') == 'FACTURA_ELECTRONICA':
                return _json_error('Los documentos originados en Facturas Electronicas no se anulan desde este modulo.', 400)
            if not _documento_editable(row):
                return _json_error('Solo se puede anular un documento pendiente sin cobros aplicados.', 400)
            asiento_id = row.get('asiento_registro_id')
            if asiento_id:
                _anular_asiento_registro(db, int(asiento_id), motivo or 'Anulacion de documento por cobrar')
            db.execute_update(
                """
                UPDATE contabilidad.documento_por_cobrar
                SET estado = 'ANULADO',
                    activo = FALSE,
                    anulado_en = CURRENT_TIMESTAMP,
                    motivo_anulacion = %s,
                    asiento_anulacion_id = COALESCE(asiento_anulacion_id, %s),
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (motivo, asiento_id, documento_id),
            )
        return _json_ok('Documento anulado correctamente.')
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo anular el documento: {exc}', 500)



@saldos_iniciales_cobrar_bp.route('/api/<int:documento_id>/movimientos')
@login_required
@roles_required(ROLES_LECTURA)
def movimientos(documento_id: int):
    try:
        with DatabaseManager() as db:
            data = _movimientos_documento(db, documento_id)
        if data is None:
            return _json_error('Documento no encontrado.', 404)
        return _json_ok(**data)
    except Exception as exc:
        current_app.logger.exception('Error cargando movimientos del documento por cobrar %s', documento_id)
        return _json_error(f'No se pudieron cargar los movimientos del documento: {exc}', 500)


@saldos_iniciales_cobrar_bp.route('/pdf/<int:documento_id>')
@login_required
@roles_required(ROLES_LECTURA)
def pdf(documento_id: int):
    with DatabaseManager() as db:
        row = _documento_row(db, documento_id)
    if not row:
        return _json_error('Saldo inicial no encontrado.', 404)
    if row.get('origen_documento') != 'HISTORICO':
        return _json_error('Este PDF corresponde al módulo Documentos por Cobrar - Saldo Inicial.', 400)
    pdf_bytes = _build_documento_pdf(row, 'Documentos por Cobrar - Saldo Inicial - Respaldo')
    filename = f"saldo_inicial_por_cobrar_{int(documento_id):06d}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})


@saldos_iniciales_cobrar_bp.route('/api/clientes')
@login_required
@roles_required(ROLES_LECTURA)
def api_clientes():
    term = _clean(request.args.get('q'))
    where = ["tipo = 'CLIENTE'", 'activo = TRUE']
    params: list[Any] = []
    if term:
        like = f'%{term}%'
        where.append('(COALESCE(nombre, \'\') ILIKE %s OR COALESCE(nit_ci, \'\') ILIKE %s)')
        params.extend([like, like])
    with DatabaseManager() as db:
        rows = db.execute_query(
            f"""
            SELECT id, COALESCE(nombre, '') AS nombre, COALESCE(nit_ci, '') AS nit_ci
            FROM contabilidad.auxiliar
            WHERE {' AND '.join(where)}
            ORDER BY nombre ASC, nit_ci ASC
            LIMIT 30
            """,
            tuple(params),
        )
    results = [
        {
            'id': row['id'],
            'text': f"{row['nombre']} · {row['nit_ci']}" if row['nit_ci'] else row['nombre'],
            'nit_ci': row['nit_ci'],
            'nombre': row['nombre'],
        }
        for row in rows
    ]
    return jsonify({'results': results})


@saldos_iniciales_cobrar_bp.route('/api/cuentas')
@login_required
@roles_required(ROLES_LECTURA)
def api_cuentas():
    term = _clean(request.args.get('q'))
    rol = _upper(request.args.get('rol'))
    where = ['activo = TRUE', 'es_postable = TRUE']
    params: list[Any] = []
    if rol == 'CARTERA':
        where.append("tipo::text = 'ACTIVO'")
    elif rol == 'CONTRAPARTIDA':
        where.append("codigo <> %s")
        params.append(_clean(request.args.get('excluir')) or CUENTA_CARTERA_HISTORICA)
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
