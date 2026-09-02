# ============================================================
# DXT CONTA - Anticipos y Prestamos
# Registro, programacion por planilla y recupero directo.
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import calendar

from flask import jsonify, render_template, request, session
from psycopg2.extras import Json

from database.db_manager import DatabaseManager
from modules.planilla_prestamos import planilla_prestamos_bp
from utils.decorators import login_required, roles_required
from utils.planillas_security import assert_gestion_abierta, mensaje_error_operacion


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
MODULO_ORIGEN = 'PLANILLAS'
TABLA_PRESTAMO = 'contabilidad.planilla_prestamo'
Q2 = Decimal('0.01')

TIPOS_OPERACION = {'ANTICIPO', 'PRESTAMO'}
TIPOS_INTERES = {'NINGUNO', 'PORCENTAJE', 'VALOR'}
MODALIDADES_REGISTRO = {'DESEMBOLSO', 'SALDO_INICIAL'}
MEDIOS = {'CAJA', 'BANCO'}
ESTADOS = {'BORRADOR', 'CONFIRMADO', 'PARCIAL', 'PAGADO', 'ANULADO'}
MESES = [
    (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
    (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
    (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
]


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def _usuario_actual() -> str:
    return str(session.get('username') or session.get('usuario') or session.get('email') or session.get('user_id') or 'sistema')


def _usuario_id_actual():
    return session.get('user_id') or session.get('usuario_id') or session.get('id')


def _puede_editar() -> bool:
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except (TypeError, ValueError):
        return False


def _json_ready(value: Any):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
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


def _money(value: Any, field_name: str = 'Importe', positive: bool = True) -> Decimal:
    try:
        monto = Decimal(str(value or '0')).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise ValueError(f'{field_name} no tiene un valor válido.') from exc
    if positive and monto <= 0:
        raise ValueError(f'{field_name} debe ser mayor a cero.')
    if not positive and monto < 0:
        raise ValueError(f'{field_name} no puede ser negativo.')
    return monto


def _decimal(value: Any, field_name: str, minimum: Decimal = Decimal('0')) -> Decimal:
    try:
        monto = Decimal(str(value or '0')).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise ValueError(f'{field_name} no tiene un valor válido.') from exc
    if monto < minimum:
        raise ValueError(f'{field_name} no puede ser menor a {minimum}.')
    return monto


def _int_value(value: Any, field_name: str, minimum: int = 1) -> int:
    if not _clean(value):
        raise ValueError(f'{field_name} es obligatorio.')
    try:
        number = int(value)
    except Exception as exc:
        raise ValueError(f'{field_name} no tiene un valor válido.') from exc
    if number < minimum:
        raise ValueError(f'{field_name} debe ser mayor o igual a {minimum}.')
    return number


def _parse_date(value: Any, field_name: str, required: bool = True):
    text = _clean(value)
    if not text:
        if required:
            raise ValueError(f'{field_name} es obligatorio.')
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no tiene una fecha válida.') from exc


def _limit(value: Any, field_name: str, max_len: int, required: bool = False) -> str | None:
    text = _clean(value)
    if required and not text:
        raise ValueError(f'{field_name} es obligatorio.')
    if len(text) > max_len:
        raise ValueError(f'{field_name} no puede exceder {max_len} caracteres.')
    return text or None


def _first_day(gestion: int, mes: int) -> date:
    return date(int(gestion), int(mes), 1)


def _gestion_activa(db: DatabaseManager) -> int:
    rows = db.execute_query(
        """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
        """
    )
    if rows:
        return int(rows[0]['gestion'])
    return date.today().year


def _assert_tables_ready(db: DatabaseManager) -> None:
    rows = db.execute_query(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'contabilidad'
          AND table_name IN ('planilla_persona', 'planilla_prestamo', 'planilla_prestamo_cuota', 'planilla_prestamo_aplicacion')
        """
    )
    found = {row['table_name'] for row in rows}
    missing = sorted({'planilla_persona', 'planilla_prestamo', 'planilla_prestamo_cuota', 'planilla_prestamo_aplicacion'} - found)
    if missing:
        raise ValueError('Faltan tablas de anticipos/préstamos. Ejecute primero el SQL del módulo.')
    cols = db.execute_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'contabilidad'
          AND table_name = 'planilla_prestamo'
          AND column_name IN ('monto_capital','tipo_interes','interes_porcentaje','interes_monto','total_recuperar','cuenta_interes_codigo')
        """
    )
    found_cols = {row['column_name'] for row in cols}
    missing_cols = sorted({'monto_capital','tipo_interes','interes_porcentaje','interes_monto','total_recuperar','cuenta_interes_codigo'} - found_cols)
    if missing_cols:
        raise ValueError('Falta actualizar la estructura de anticipos/préstamos. Ejecute actualizar_tablas_planilla_prestamos_v2.sql.')


def _cuenta_existe(db: DatabaseManager, codigo: str | None, requiere_postable: bool = True):
    if not codigo:
        return None
    rows = db.execute_query(
        """
        SELECT codigo, nombre, tipo, es_postable, activo, requiere_auxiliar
        FROM contabilidad.cuenta
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,)
    )
    if not rows:
        raise ValueError(f'La cuenta {codigo} no existe.')
    row = rows[0]
    if requiere_postable and not row['es_postable']:
        raise ValueError(f'La cuenta {codigo} no es postable.')
    if not row['activo']:
        raise ValueError(f'La cuenta {codigo} no está activa.')
    return row


def _get_persona(db: DatabaseManager, persona_id: int) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT pp.*, a.tipo AS auxiliar_tipo, a.nombre AS auxiliar_nombre
        FROM contabilidad.planilla_persona pp
        LEFT JOIN contabilidad.auxiliar a ON a.id = pp.auxiliar_id
        WHERE pp.id = %s
          AND pp.estado = 'ACTIVO'
        LIMIT 1
        """,
        (persona_id,)
    )
    if not rows:
        raise ValueError('La persona de planilla no existe o está inactiva.')
    persona = dict(rows[0])
    if not persona.get('auxiliar_id'):
        raise ValueError('La persona no tiene auxiliar contable vinculado. Corrija primero Personas de Planilla.')
    return persona


def _get_caja(db: DatabaseManager, caja_id: int) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT id, codigo, nombre, cuenta_contable_codigo
        FROM contabilidad.caja
        WHERE id = %s AND activo = TRUE
        LIMIT 1
        """,
        (caja_id,)
    )
    if not rows:
        raise ValueError('La caja seleccionada no existe o está inactiva.')
    return dict(rows[0])


def _get_banco(db: DatabaseManager, banco_id: int) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT id, nombre_banco, numero_cuenta, moneda_codigo, cuenta_contable_codigo, unidad_negocio_id
        FROM contabilidad.cuenta_bancaria
        WHERE id = %s AND activo = TRUE
        LIMIT 1
        """,
        (banco_id,)
    )
    if not rows:
        raise ValueError('La cuenta bancaria seleccionada no existe o está inactiva.')
    return dict(rows[0])


def _prestamo_by_id(db: DatabaseManager, prestamo_id: int) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT p.*, un.codigo AS unidad_codigo, un.nombre AS unidad_nombre, a.nombre AS auxiliar_nombre
        FROM contabilidad.planilla_prestamo p
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
        LEFT JOIN contabilidad.auxiliar a ON a.id = p.auxiliar_id
        WHERE p.id = %s
        LIMIT 1
        """,
        (prestamo_id,)
    )
    if not rows:
        raise ValueError('El anticipo/préstamo no existe.')
    return dict(rows[0])


def _siguiente_codigo(db: DatabaseManager, tipo_operacion: str, fecha_otorgamiento: date) -> str:
    prefijo = 'ANT' if tipo_operacion == 'ANTICIPO' else 'PRE'
    base = f'{prefijo}-{fecha_otorgamiento.year}'
    rows = db.execute_query(
        """
        SELECT codigo
        FROM contabilidad.planilla_prestamo
        WHERE codigo LIKE %s
        ORDER BY codigo DESC
        LIMIT 1
        """,
        (f'{base}-%',)
    )
    sec = 1
    if rows:
        try:
            sec = int(str(rows[0]['codigo']).split('-')[-1]) + 1
        except Exception:
            sec = 1
    return f'{base}-{sec:04d}'


def _calcular_interes(monto_capital: Decimal, tipo_interes: str, valor_interes: Decimal) -> tuple[Decimal, Decimal]:
    if tipo_interes == 'NINGUNO':
        return Decimal('0.00'), Decimal('0.0000')
    if tipo_interes == 'PORCENTAJE':
        interes_monto = (monto_capital * valor_interes / Decimal('100')).quantize(Q2, rounding=ROUND_HALF_UP)
        return interes_monto, valor_interes.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    if tipo_interes == 'VALOR':
        return valor_interes.quantize(Q2, rounding=ROUND_HALF_UP), Decimal('0.0000')
    raise ValueError('El tipo de interés no es válido.')


def _validar_cuotas(data: dict[str, Any], tipo_operacion: str, total_recuperar: Decimal, gestion_activa: int) -> list[dict[str, Any]]:
    cuotas_raw = data.get('cuotas') or []
    if tipo_operacion == 'ANTICIPO':
        gestion = _int_value(data.get('anticipo_gestion') or gestion_activa, 'Gestión de descuento', 2000)
        mes = _int_value(data.get('anticipo_mes'), 'Mes de descuento', 1)
        cuotas_raw = [{'gestion': gestion, 'mes': mes, 'monto': str(total_recuperar)}]
    if not isinstance(cuotas_raw, list) or not cuotas_raw:
        raise ValueError('Debe definir la programación de descuento en planilla.')
    if tipo_operacion == 'ANTICIPO' and len(cuotas_raw) != 1:
        raise ValueError('El anticipo debe programarse en una sola planilla.')
    if tipo_operacion == 'PRESTAMO' and len(cuotas_raw) > 12:
        raise ValueError('El préstamo no puede superar 12 cuotas dentro de la gestión activa.')
    cuotas: list[dict[str, Any]] = []
    usados: set[tuple[int, int]] = set()
    total_cuotas = Decimal('0.00')
    for idx, row in enumerate(cuotas_raw, start=1):
        gestion = _int_value(row.get('gestion'), f'Gestión cuota {idx}', 2000)
        mes = _int_value(row.get('mes'), f'Mes cuota {idx}', 1)
        if mes > 12:
            raise ValueError(f'Mes inválido en cuota {idx}.')
        if gestion != gestion_activa:
            raise ValueError(f'La cuota {idx} debe estar dentro de la gestión activa {gestion_activa}.')
        if (gestion, mes) in usados:
            raise ValueError(f'Existe más de una cuota programada para {mes:02d}/{gestion}.')
        monto = _money(row.get('monto'), f'Monto cuota {idx}')
        usados.add((gestion, mes))
        total_cuotas += monto
        cuotas.append({
            'numero_cuota': idx,
            'gestion': gestion,
            'mes': mes,
            'fecha_programada': _first_day(gestion, mes),
            'monto_programado': monto,
            'saldo_pendiente': monto,
            'justificativo': _limit(row.get('justificativo'), f'Justificativo cuota {idx}', 800),
            'observacion': _limit(row.get('observacion'), f'Observación cuota {idx}', 500),
        })
    if total_cuotas != total_recuperar:
        raise ValueError(f'La suma de cuotas ({total_cuotas}) debe ser igual al total a recuperar ({total_recuperar}).')
    return cuotas


def _validar_payload(data: dict[str, Any], gestion_activa: int) -> dict[str, Any]:
    tipo_operacion = _upper(data.get('tipo_operacion'))
    persona_id = _int_value(data.get('persona_id'), 'Persona')
    unidad_negocio_id = _int_value(data.get('unidad_negocio_id'), 'Unidad de negocio')
    fecha_otorgamiento = _parse_date(data.get('fecha_otorgamiento'), 'Fecha de otorgamiento')
    moneda_codigo = _upper(data.get('moneda_codigo'))
    if not moneda_codigo:
        raise ValueError('Moneda es obligatoria.')
    tipo_cambio = _money(data.get('tipo_cambio'), 'Tipo de cambio')
    monto_capital = _money(data.get('monto_capital'), 'Monto inicial')
    tipo_interes = _upper(data.get('tipo_interes') or 'NINGUNO')
    valor_interes = _decimal(data.get('valor_interes') or '0', 'Interés')
    modalidad_registro = _upper(data.get('modalidad_registro'))
    cuenta_cobrar_codigo = _limit(data.get('cuenta_cobrar_codigo'), 'Cuenta por cobrar', 30, True)
    cuenta_interes_codigo = _limit(data.get('cuenta_interes_codigo'), 'Cuenta de interés', 30)
    medio_desembolso = _upper(data.get('medio_desembolso'))
    caja_id = data.get('caja_id')
    cuenta_bancaria_id = data.get('cuenta_bancaria_id')
    referencia = None
    glosa = _limit(data.get('glosa'), 'Glosa', 500, True)
    justificativo = _limit(data.get('justificativo'), 'Justificativo', 800, True)
    observacion = None

    if tipo_operacion not in TIPOS_OPERACION:
        raise ValueError('El tipo debe ser ANTICIPO o PRESTAMO.')
    if tipo_operacion == 'ANTICIPO':
        tipo_interes = 'NINGUNO'
        valor_interes = Decimal('0.0000')
        cuenta_interes_codigo = None
    if tipo_interes not in TIPOS_INTERES:
        raise ValueError('El tipo de interés no es válido.')
    if modalidad_registro not in MODALIDADES_REGISTRO:
        raise ValueError('La modalidad de registro no es válida.')
    if modalidad_registro == 'DESEMBOLSO':
        if medio_desembolso not in MEDIOS:
            raise ValueError('Seleccione Caja o Banco para el desembolso.')
        if medio_desembolso == 'CAJA':
            caja_id = _int_value(caja_id, 'Caja')
            cuenta_bancaria_id = None
        else:
            cuenta_bancaria_id = _int_value(cuenta_bancaria_id, 'Cuenta bancaria')
            caja_id = None
    else:
        medio_desembolso = 'NO_APLICA'
        caja_id = None
        cuenta_bancaria_id = None

    interes_monto, interes_porcentaje = _calcular_interes(monto_capital, tipo_interes, valor_interes)
    total_recuperar = (monto_capital + interes_monto).quantize(Q2, rounding=ROUND_HALF_UP)
    cuotas = _validar_cuotas(data, tipo_operacion, total_recuperar, gestion_activa)

    return {
        'tipo_operacion': tipo_operacion,
        'persona_id': persona_id,
        'unidad_negocio_id': unidad_negocio_id,
        'fecha_otorgamiento': fecha_otorgamiento,
        'moneda_codigo': moneda_codigo,
        'tipo_cambio': tipo_cambio,
        'monto_capital': monto_capital,
        'tipo_interes': tipo_interes,
        'interes_porcentaje': interes_porcentaje,
        'interes_monto': interes_monto,
        'total_recuperar': total_recuperar,
        'numero_cuotas': len(cuotas),
        'modalidad_registro': modalidad_registro,
        'cuenta_cobrar_codigo': cuenta_cobrar_codigo,
        'cuenta_interes_codigo': cuenta_interes_codigo,
        'medio_desembolso': medio_desembolso,
        'caja_id': caja_id,
        'cuenta_bancaria_id': cuenta_bancaria_id,
        'referencia': referencia,
        'glosa': glosa,
        'justificativo': justificativo,
        'observacion': observacion,
        'cuotas': cuotas,
    }


def _recrear_cuotas(db: DatabaseManager, prestamo_id: int, cuotas: list[dict[str, Any]]):
    db.execute_delete('DELETE FROM contabilidad.planilla_prestamo_cuota WHERE prestamo_id = %s', (prestamo_id,))
    for cuota in cuotas:
        db.execute_insert(
            """
            INSERT INTO contabilidad.planilla_prestamo_cuota (
                prestamo_id, numero_cuota, gestion, mes, fecha_programada,
                monto_programado, monto_aplicado, saldo_pendiente, estado,
                justificativo, observacion
            ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'PENDIENTE', %s, %s)
            """,
            (
                prestamo_id, cuota['numero_cuota'], cuota['gestion'], cuota['mes'], cuota['fecha_programada'],
                cuota['monto_programado'], cuota['saldo_pendiente'], cuota.get('justificativo'), cuota.get('observacion')
            ),
            return_id=False,
        )


def _stats(db: DatabaseManager) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT COUNT(*)::int AS total,
               COUNT(*) FILTER (WHERE estado IN ('CONFIRMADO','PARCIAL'))::int AS activos,
               COUNT(*) FILTER (WHERE estado = 'BORRADOR')::int AS borradores,
               COALESCE(SUM(saldo_pendiente) FILTER (WHERE estado IN ('CONFIRMADO','PARCIAL')), 0)::numeric AS pendiente,
               COALESCE(SUM(monto_capital) FILTER (WHERE estado <> 'ANULADO'), 0)::numeric AS capital,
               COALESCE(SUM(interes_monto) FILTER (WHERE estado <> 'ANULADO'), 0)::numeric AS interes
        FROM contabilidad.planilla_prestamo
        """
    )
    base = dict(rows[0]) if rows else {}
    return {
        'total': int(base.get('total') or 0),
        'activos': int(base.get('activos') or 0),
        'borradores': int(base.get('borradores') or 0),
        'pendiente': base.get('pendiente') or Decimal('0'),
        'capital': base.get('capital') or Decimal('0'),
        'interes': base.get('interes') or Decimal('0'),
    }


def _crear_asiento_otorgamiento(db: DatabaseManager, prestamo: dict[str, Any], salida_cuenta: str) -> int:
    glosa = prestamo['glosa'][:500]
    referencia = prestamo.get('referencia') or prestamo['codigo']
    asiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha, unidad_negocio_id, moneda_codigo, tipo_cambio, glosa, referencia,
            modulo_origen, tabla_origen, origen_id, estado, cliente_nit_ci_ref,
            cliente_nombre_ref, atributos, actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'CONFIRMADO', %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
        """,
        (
            prestamo['fecha_otorgamiento'], prestamo['unidad_negocio_id'], prestamo['moneda_codigo'], prestamo['tipo_cambio'],
            glosa, referencia, MODULO_ORIGEN, TABLA_PRESTAMO, prestamo['id'], prestamo['ci_nit'], prestamo['nombre_completo'],
            Json({'origen': 'planilla_prestamos', 'accion': 'otorgamiento', 'prestamo_id': prestamo['id']})
        ),
    )
    capital = Decimal(str(prestamo['monto_capital'])).quantize(Q2)
    interes = Decimal(str(prestamo.get('interes_monto') or 0)).quantize(Q2)
    total_recuperar = Decimal(str(prestamo['total_recuperar'])).quantize(Q2)
    sec = 1
    db.execute_insert(
        """
        INSERT INTO contabilidad.asiento_detalle (
            asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber,
            monto_moneda, referencia, atributos
        ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s::jsonb)
        """,
        (asiento_id, sec, prestamo['cuenta_cobrar_codigo'], prestamo['auxiliar_id'], glosa[:300], total_recuperar, total_recuperar, referencia, Json({'tipo': 'debe_prestamo_personal', 'incluye_interes': str(interes)})),
        return_id=False,
    )
    sec += 1
    db.execute_insert(
        """
        INSERT INTO contabilidad.asiento_detalle (
            asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber,
            monto_moneda, referencia, atributos
        ) VALUES (%s, %s, %s, NULL, %s, 0, %s, %s, %s, %s::jsonb)
        """,
        (asiento_id, sec, salida_cuenta, glosa[:300], capital, capital, referencia, Json({'tipo': 'haber_salida_tesoreria'})),
        return_id=False,
    )
    if interes > 0:
        if not prestamo.get('cuenta_interes_codigo'):
            raise ValueError('Debe seleccionar cuenta de interés si el préstamo tiene interés.')
        sec += 1
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber,
                monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, NULL, %s, 0, %s, %s, %s, %s::jsonb)
            """,
            (asiento_id, sec, prestamo['cuenta_interes_codigo'], glosa[:300], interes, interes, referencia, Json({'tipo': 'haber_interes_prestamo'})),
            return_id=False,
        )
    db.execute_insert(
        """
        INSERT INTO contabilidad.documento_asiento (modulo, tabla_origen, origen_id, asiento_id)
        VALUES (%s, %s, %s, %s)
        """,
        (MODULO_ORIGEN, TABLA_PRESTAMO, prestamo['id'], asiento_id),
        return_id=False,
    )
    return int(asiento_id)


def _registrar_movimiento_desembolso(db: DatabaseManager, prestamo: dict[str, Any], salida_cuenta: str) -> int:
    medio = prestamo['medio_desembolso']
    capital = Decimal(str(prestamo['monto_capital'])).quantize(Q2)
    movimiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.movimiento_tesoreria (
            fecha, tipo_movimiento, medio_origen, caja_origen_id, banco_origen_id,
            medio_destino, caja_destino_id, banco_destino_id, auxiliar_id,
            contra_cuenta_codigo, moneda_codigo, tipo_cambio, monto, referencia,
            glosa, estado, asiento_id, unidad_negocio_id, actualizado_en
        ) VALUES (
            %s, 'EGRESO', %s, %s, %s, NULL, NULL, NULL, %s,
            %s, %s, %s, %s, %s, %s, 'CONFIRMADO', NULL, %s, CURRENT_TIMESTAMP
        )
        """,
        (
            prestamo['fecha_otorgamiento'], medio,
            prestamo['caja_id'] if medio == 'CAJA' else None,
            prestamo['cuenta_bancaria_id'] if medio == 'BANCO' else None,
            prestamo['auxiliar_id'], prestamo['cuenta_cobrar_codigo'], prestamo['moneda_codigo'], prestamo['tipo_cambio'],
            capital, prestamo.get('referencia') or prestamo['codigo'], prestamo['glosa'], prestamo['unidad_negocio_id'],
        ),
    )
    asiento_id = _crear_asiento_otorgamiento(db, prestamo, salida_cuenta)
    db.execute_update('UPDATE contabilidad.movimiento_tesoreria SET asiento_id = %s, actualizado_en = CURRENT_TIMESTAMP WHERE id = %s', (asiento_id, movimiento_id))
    db.execute_update(
        """
        UPDATE contabilidad.planilla_prestamo
        SET movimiento_tesoreria_id = %s, asiento_otorgamiento_id = %s, cuenta_salida_codigo = %s, actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (movimiento_id, asiento_id, salida_cuenta, prestamo['id']),
    )
    return int(movimiento_id)



def _crear_asiento_reverso_desde_asiento(
    db: DatabaseManager,
    asiento_id: int,
    fecha_reversion: date,
    glosa: str,
    referencia: str,
    modulo_origen: str,
    tabla_origen: str,
    origen_id: int,
    accion: str,
) -> int:
    asiento_rows = db.execute_query(
        """
        SELECT *
        FROM contabilidad.asiento
        WHERE id = %s
        LIMIT 1
        """,
        (asiento_id,)
    )
    if not asiento_rows:
        raise ValueError('No se encontró el asiento contable que debe revertirse.')

    detalles = db.execute_query(
        """
        SELECT *
        FROM contabilidad.asiento_detalle
        WHERE asiento_id = %s
        ORDER BY secuencia
        """,
        (asiento_id,)
    )
    if not detalles:
        raise ValueError('El asiento contable no tiene detalle para reversión.')

    total_debe = sum((_money(d.get('haber') or 0, 'haber reverso', positive=False) for d in detalles), Decimal('0.00')).quantize(Q2)
    total_haber = sum((_money(d.get('debe') or 0, 'debe reverso', positive=False) for d in detalles), Decimal('0.00')).quantize(Q2)
    if total_debe != total_haber:
        raise ValueError('El asiento de reversión no cuadra.')

    asiento = dict(asiento_rows[0])
    reverso_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha, unidad_negocio_id, moneda_codigo, tipo_cambio, glosa, referencia,
            modulo_origen, tabla_origen, origen_id, estado, cliente_nit_ci_ref,
            cliente_nombre_ref, atributos, actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'CONFIRMADO', %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
        """,
        (
            fecha_reversion,
            asiento['unidad_negocio_id'],
            asiento['moneda_codigo'],
            asiento['tipo_cambio'],
            glosa[:500],
            referencia[:150],
            modulo_origen,
            tabla_origen,
            origen_id,
            asiento.get('cliente_nit_ci_ref'),
            asiento.get('cliente_nombre_ref'),
            Json({'origen': 'planilla_prestamos', 'accion': accion, 'asiento_original_id': int(asiento_id)}),
        )
    )

    sec = 1
    for d in detalles:
        debe_original = _money(d.get('debe') or 0, 'Debe original', positive=False)
        haber_original = _money(d.get('haber') or 0, 'Haber original', positive=False)
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, centro_costo_id,
                glosa, debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                reverso_id,
                sec,
                d['cuenta_codigo'],
                d.get('auxiliar_id'),
                d.get('centro_costo_id'),
                f"Reverso {d.get('glosa') or ''}"[:300],
                haber_original,
                debe_original,
                max(debe_original, haber_original),
                referencia[:150],
                Json({'tipo': accion, 'asiento_original_id': int(asiento_id)}),
            ),
            return_id=False,
        )
        sec += 1

    db.execute_insert(
        """
        INSERT INTO contabilidad.documento_asiento (modulo, tabla_origen, origen_id, asiento_id)
        VALUES (%s, %s, %s, %s)
        """,
        (modulo_origen, tabla_origen, origen_id, reverso_id),
        return_id=False,
    )
    return int(reverso_id)


def _revertir_aplicacion_prestamo(db: DatabaseManager, aplicacion: dict[str, Any]) -> None:
    monto = _money(aplicacion['monto_aplicado'], 'Monto aplicado')
    cuota_id = aplicacion.get('cuota_id')
    if cuota_id:
        cuota_rows = db.execute_query(
            """
            SELECT monto_aplicado, saldo_pendiente
            FROM contabilidad.planilla_prestamo_cuota
            WHERE id = %s
            LIMIT 1
            """,
            (cuota_id,)
        )
        if cuota_rows:
            cuota = cuota_rows[0]
            aplicado_actual = _money(cuota.get('monto_aplicado') or 0, 'Aplicado cuota', positive=False)
            saldo_actual = _money(cuota.get('saldo_pendiente') or 0, 'Saldo cuota', positive=False)
            nuevo_aplicado = max(Decimal('0.00'), aplicado_actual - monto).quantize(Q2)
            nuevo_saldo = (saldo_actual + monto).quantize(Q2)
            nuevo_estado = 'PENDIENTE' if nuevo_aplicado <= 0 else 'PARCIAL'
            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo_cuota
                SET monto_aplicado = %s,
                    saldo_pendiente = %s,
                    estado = %s,
                    planilla_periodo_id = NULL,
                    planilla_detalle_id = NULL,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (nuevo_aplicado, nuevo_saldo, nuevo_estado, cuota_id)
            )

    db.execute_delete(
        "DELETE FROM contabilidad.planilla_prestamo_aplicacion WHERE id = %s",
        (aplicacion['id'],)
    )


def _aplicaciones_prestamo(db: DatabaseManager, prestamo_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute_query(
        """
        SELECT *
        FROM contabilidad.planilla_prestamo_aplicacion
        WHERE prestamo_id = %s
        ORDER BY fecha_aplicacion DESC, id DESC
        """,
        (prestamo_id,)
    )]


def _aplicar_monto_a_cuotas(db: DatabaseManager, prestamo_id: int, monto: Decimal) -> list[dict[str, Any]]:
    restante = monto
    aplicadas = []
    cuotas = db.execute_query(
        """
        SELECT *
        FROM contabilidad.planilla_prestamo_cuota
        WHERE prestamo_id = %s
          AND estado IN ('PENDIENTE','PARCIAL','POSTERGADA')
          AND saldo_pendiente > 0
        ORDER BY fecha_programada ASC, numero_cuota ASC
        """,
        (prestamo_id,),
    )
    for cuota in cuotas:
        if restante <= 0:
            break
        saldo = Decimal(str(cuota['saldo_pendiente'])).quantize(Q2)
        aplicar = min(saldo, restante).quantize(Q2)
        nuevo_aplicado = Decimal(str(cuota['monto_aplicado'])).quantize(Q2) + aplicar
        nuevo_saldo = saldo - aplicar
        nuevo_estado = 'APLICADA' if nuevo_saldo <= 0 else 'PARCIAL'
        db.execute_update(
            """
            UPDATE contabilidad.planilla_prestamo_cuota
            SET monto_aplicado = %s, saldo_pendiente = %s, estado = %s, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (nuevo_aplicado, nuevo_saldo, nuevo_estado, cuota['id']),
        )
        aplicadas.append({'cuota_id': cuota['id'], 'monto': aplicar})
        restante -= aplicar
    if restante > 0:
        raise ValueError('No existen cuotas pendientes suficientes para aplicar el monto indicado.')
    return aplicadas


def _actualizar_saldo_prestamo(db: DatabaseManager, prestamo_id: int):
    rows = db.execute_query(
        """
        SELECT total_recuperar,
               COALESCE((SELECT SUM(monto_aplicado) FROM contabilidad.planilla_prestamo_aplicacion WHERE prestamo_id = p.id), 0) AS aplicado
        FROM contabilidad.planilla_prestamo p
        WHERE id = %s
        """,
        (prestamo_id,),
    )
    if not rows:
        return
    total = Decimal(str(rows[0]['total_recuperar'])).quantize(Q2)
    aplicado = Decimal(str(rows[0]['aplicado'])).quantize(Q2)
    saldo = max(Decimal('0.00'), total - aplicado)
    estado = 'PAGADO' if saldo <= 0 else ('PARCIAL' if aplicado > 0 else 'CONFIRMADO')
    db.execute_update(
        """
        UPDATE contabilidad.planilla_prestamo
        SET monto_recuperado = %s, saldo_pendiente = %s, estado = %s, actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s AND estado <> 'ANULADO'
        """,
        (aplicado, saldo, estado, prestamo_id),
    )


@planilla_prestamos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    try:
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            stats = _stats(db)
            gestion_activa = _gestion_activa(db)
    except Exception as exc:
        stats = {'total': 0, 'activos': 0, 'borradores': 0, 'pendiente': Decimal('0'), 'capital': Decimal('0'), 'interes': Decimal('0')}
        return render_template('planilla_prestamos_index.html', stats=stats, gestion_activa=date.today().year, puede_editar=_puede_editar(), error='No se pudo cargar Anticipos y Préstamos. Revise la configuración operativa del módulo.')
    return render_template('planilla_prestamos_index.html', stats=stats, gestion_activa=gestion_activa, puede_editar=_puede_editar(), error=None)


@planilla_prestamos_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('planilla_prestamos_help.html')


@planilla_prestamos_bp.route('/opciones')
@login_required
@roles_required(ROLES_LECTURA)
def opciones():
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        gestion_activa = _gestion_activa(db)
        personas = db.execute_query(
            """
            SELECT id, tipo_persona, ci_nit, nombre_completo, auxiliar_id
            FROM contabilidad.planilla_persona
            WHERE estado = 'ACTIVO' AND auxiliar_id IS NOT NULL
            ORDER BY tipo_persona, nombre_completo
            """
        )
        unidades = db.execute_query("SELECT id, codigo, nombre FROM contabilidad.unidad_negocio WHERE activo = TRUE ORDER BY codigo")
        monedas = db.execute_query("SELECT codigo, nombre FROM contabilidad.moneda WHERE activo = TRUE ORDER BY codigo")
        cuentas_cobrar = db.execute_query(
            """
            SELECT codigo, nombre, requiere_auxiliar
            FROM contabilidad.cuenta
            WHERE activo = TRUE AND es_postable = TRUE AND tipo = 'ACTIVO' AND codigo LIKE '1.%'
            ORDER BY CASE WHEN codigo IN ('1.1.2.011','1.1.2.003','1.1.2.005') THEN 0 ELSE 1 END, codigo
            """
        )
        cuentas_interes = db.execute_query(
            """
            SELECT codigo, nombre
            FROM contabilidad.cuenta
            WHERE activo = TRUE AND es_postable = TRUE AND tipo = 'INGRESO'
            ORDER BY CASE WHEN codigo = '4.2.1.001' THEN 0 ELSE 1 END, codigo
            """
        )
        cajas = db.execute_query("SELECT id, codigo, nombre, cuenta_contable_codigo FROM contabilidad.caja WHERE activo = TRUE ORDER BY codigo")
        bancos = db.execute_query(
            """
            SELECT id, nombre_banco, numero_cuenta, moneda_codigo, cuenta_contable_codigo, unidad_negocio_id
            FROM contabilidad.cuenta_bancaria
            WHERE activo = TRUE
            ORDER BY nombre_banco, numero_cuenta
            """
        )
    return _json_ok(
        personas=[dict(x) for x in personas],
        unidades=[dict(x) for x in unidades],
        monedas=[dict(x) for x in monedas],
        cuentas_cobrar=[dict(x) for x in cuentas_cobrar],
        cuentas_interes=[dict(x) for x in cuentas_interes],
        cajas=[dict(x) for x in cajas],
        bancos=[dict(x) for x in bancos],
        meses=[{'id': m, 'nombre': n} for m, n in MESES],
        gestion_activa=gestion_activa,
    )


@planilla_prestamos_bp.route('/listar')
@login_required
@roles_required(ROLES_LECTURA)
def listar():
    estado = _upper(request.args.get('estado'))
    tipo = _upper(request.args.get('tipo'))
    persona_tipo = _upper(request.args.get('persona_tipo'))
    q = _clean(request.args.get('q'))
    filtros = []
    params: list[Any] = []
    if estado in ESTADOS:
        filtros.append('p.estado = %s')
        params.append(estado)
    if tipo in TIPOS_OPERACION:
        filtros.append('p.tipo_operacion = %s')
        params.append(tipo)
    if persona_tipo in {'PLANTA', 'COLABORADOR'}:
        filtros.append('p.tipo_persona = %s')
        params.append(persona_tipo)
    if q:
        filtros.append("(p.codigo ILIKE %s OR p.nombre_completo ILIKE %s OR p.ci_nit ILIKE %s OR COALESCE(p.glosa,'') ILIKE %s)")
        like = f'%{q}%'
        params.extend([like, like, like, like])
    where = 'WHERE ' + ' AND '.join(filtros) if filtros else ''
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        rows = db.execute_query(
            f"""
            SELECT p.*, un.codigo AS unidad_codigo, un.nombre AS unidad_nombre,
                   COALESCE(cuotas.total, 0)::int AS cuotas_total,
                   COALESCE(cuotas.pendientes, 0)::int AS cuotas_pendientes
            FROM contabilidad.planilla_prestamo p
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            LEFT JOIN (
                SELECT prestamo_id, COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE estado IN ('PENDIENTE','PARCIAL','POSTERGADA')) AS pendientes
                FROM contabilidad.planilla_prestamo_cuota
                GROUP BY prestamo_id
            ) cuotas ON cuotas.prestamo_id = p.id
            {where}
            ORDER BY p.creado_en DESC, p.id DESC
            """,
            tuple(params),
        )
    return jsonify({'data': _json_ready([dict(r) for r in rows])})


@planilla_prestamos_bp.route('/obtener/<int:prestamo_id>')
@login_required
@roles_required(ROLES_LECTURA)
def obtener(prestamo_id: int):
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        prestamo = _prestamo_by_id(db, prestamo_id)
        cuotas = db.execute_query("SELECT * FROM contabilidad.planilla_prestamo_cuota WHERE prestamo_id = %s ORDER BY numero_cuota", (prestamo_id,))
        aplicaciones = db.execute_query("SELECT * FROM contabilidad.planilla_prestamo_aplicacion WHERE prestamo_id = %s ORDER BY fecha_aplicacion DESC, id DESC", (prestamo_id,))
    return _json_ok(data=prestamo, cuotas=[dict(c) for c in cuotas], aplicaciones=[dict(a) for a in aplicaciones])


@planilla_prestamos_bp.route('/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def guardar():
    data = request.get_json() or {}
    try:
        prestamo_id = data.get('id')
        prestamo_id = int(prestamo_id) if prestamo_id not in (None, '', 'null') else None
    except Exception:
        return _json_error('Identificador inválido.')

    with DatabaseManager() as db:
        _assert_tables_ready(db)
        gestion_activa = _gestion_activa(db)
        try:
            payload = _validar_payload(data, gestion_activa)
            assert_gestion_abierta(db, int(payload['fecha_otorgamiento'].year), 'registrar anticipos o préstamos')
            persona = _get_persona(db, payload['persona_id'])
            _cuenta_existe(db, payload['cuenta_cobrar_codigo'])
            if payload['interes_monto'] > 0:
                if not payload.get('cuenta_interes_codigo'):
                    raise ValueError('Debe seleccionar cuenta de ingreso por interés.')
                cuenta_interes = _cuenta_existe(db, payload['cuenta_interes_codigo'])
                if cuenta_interes['tipo'] != 'INGRESO':
                    raise ValueError('La cuenta de interés debe ser de tipo INGRESO.')
            cuenta_salida = None
            if payload['modalidad_registro'] == 'DESEMBOLSO':
                if payload['medio_desembolso'] == 'CAJA':
                    caja = _get_caja(db, payload['caja_id'])
                    cuenta_salida = caja['cuenta_contable_codigo']
                else:
                    banco = _get_banco(db, payload['cuenta_bancaria_id'])
                    cuenta_salida = banco['cuenta_contable_codigo']
                    if banco['moneda_codigo'] != payload['moneda_codigo']:
                        return _json_error('La moneda de la cuenta bancaria no coincide con la moneda del anticipo/préstamo.')
                _cuenta_existe(db, cuenta_salida)
        except ValueError as exc:
            return _json_error(str(exc))

        if prestamo_id:
            actual = _prestamo_by_id(db, prestamo_id)
            if actual['estado'] != 'BORRADOR':
                return _json_error('Solo se pueden editar registros en estado BORRADOR.', 409)
            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo
                SET tipo_operacion = %s, persona_id = %s, auxiliar_id = %s,
                    tipo_persona = %s, ci_nit = %s, nombre_completo = %s,
                    unidad_negocio_id = %s, fecha_otorgamiento = %s, fecha_primera_cuota = %s,
                    moneda_codigo = %s, tipo_cambio = %s, monto_capital = %s, tipo_interes = %s,
                    interes_porcentaje = %s, interes_monto = %s, total_recuperar = %s,
                    monto_total = %s, monto_recuperado = 0, saldo_pendiente = %s, numero_cuotas = %s,
                    frecuencia = 'MENSUAL', modalidad_registro = %s, modalidad_recuperacion = 'MIXTA',
                    cuenta_cobrar_codigo = %s, cuenta_interes_codigo = %s, medio_desembolso = %s,
                    caja_id = %s, cuenta_bancaria_id = %s, cuenta_salida_codigo = %s,
                    referencia = %s, glosa = %s, justificativo = %s, observacion = %s,
                    atributos = %s::jsonb, actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    payload['tipo_operacion'], payload['persona_id'], persona['auxiliar_id'], persona['tipo_persona'], persona['ci_nit'], persona['nombre_completo'],
                    payload['unidad_negocio_id'], payload['fecha_otorgamiento'], payload['cuotas'][0]['fecha_programada'], payload['moneda_codigo'], payload['tipo_cambio'],
                    payload['monto_capital'], payload['tipo_interes'], payload['interes_porcentaje'], payload['interes_monto'], payload['total_recuperar'],
                    payload['total_recuperar'], payload['total_recuperar'], payload['numero_cuotas'], payload['modalidad_registro'], payload['cuenta_cobrar_codigo'],
                    payload['cuenta_interes_codigo'], payload['medio_desembolso'], payload['caja_id'], payload['cuenta_bancaria_id'], cuenta_salida,
                    payload['referencia'], payload['glosa'], payload['justificativo'], payload['observacion'], Json({'origen': 'planilla_prestamos', 'gestion_activa': gestion_activa, 'usuario_id': _usuario_id_actual()}), prestamo_id,
                ),
            )
        else:
            codigo = _siguiente_codigo(db, payload['tipo_operacion'], payload['fecha_otorgamiento'])
            prestamo_id = db.execute_insert(
                """
                INSERT INTO contabilidad.planilla_prestamo (
                    codigo, tipo_operacion, persona_id, auxiliar_id, tipo_persona, ci_nit, nombre_completo,
                    unidad_negocio_id, fecha_otorgamiento, fecha_primera_cuota, moneda_codigo, tipo_cambio,
                    monto_capital, tipo_interes, interes_porcentaje, interes_monto, total_recuperar,
                    monto_total, monto_recuperado, saldo_pendiente, numero_cuotas, frecuencia,
                    modalidad_registro, modalidad_recuperacion, cuenta_cobrar_codigo, cuenta_interes_codigo,
                    medio_desembolso, caja_id, cuenta_bancaria_id, cuenta_salida_codigo, estado,
                    referencia, glosa, justificativo, observacion, creado_por, atributos
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, 0, %s, %s, 'MENSUAL',
                    %s, 'MIXTA', %s, %s,
                    %s, %s, %s, %s, 'BORRADOR',
                    %s, %s, %s, %s, %s, %s::jsonb
                ) RETURNING id
                """,
                (
                    codigo, payload['tipo_operacion'], payload['persona_id'], persona['auxiliar_id'], persona['tipo_persona'], persona['ci_nit'], persona['nombre_completo'],
                    payload['unidad_negocio_id'], payload['fecha_otorgamiento'], payload['cuotas'][0]['fecha_programada'], payload['moneda_codigo'], payload['tipo_cambio'],
                    payload['monto_capital'], payload['tipo_interes'], payload['interes_porcentaje'], payload['interes_monto'], payload['total_recuperar'],
                    payload['total_recuperar'], payload['total_recuperar'], payload['numero_cuotas'], payload['modalidad_registro'], payload['cuenta_cobrar_codigo'],
                    payload['cuenta_interes_codigo'], payload['medio_desembolso'], payload['caja_id'], payload['cuenta_bancaria_id'], cuenta_salida,
                    payload['referencia'], payload['glosa'], payload['justificativo'], payload['observacion'], _usuario_actual(),
                    Json({'origen': 'planilla_prestamos', 'gestion_activa': gestion_activa, 'usuario_id': _usuario_id_actual()}),
                ),
            )
        _recrear_cuotas(db, int(prestamo_id), payload['cuotas'])
    return _json_ok('Anticipo/préstamo guardado.', id=prestamo_id)


@planilla_prestamos_bp.route('/confirmar/<int:prestamo_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def confirmar(prestamo_id: int):
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        prestamo = _prestamo_by_id(db, prestamo_id)
        assert_gestion_abierta(db, int(prestamo['fecha_otorgamiento'].year), 'confirmar anticipos o préstamos')
        if prestamo['estado'] != 'BORRADOR':
            return _json_error('Solo se pueden confirmar registros en estado BORRADOR.', 409)
        if prestamo['modalidad_registro'] == 'DESEMBOLSO':
            if not prestamo.get('cuenta_salida_codigo'):
                if prestamo['medio_desembolso'] == 'CAJA':
                    prestamo['cuenta_salida_codigo'] = _get_caja(db, prestamo['caja_id'])['cuenta_contable_codigo']
                elif prestamo['medio_desembolso'] == 'BANCO':
                    prestamo['cuenta_salida_codigo'] = _get_banco(db, prestamo['cuenta_bancaria_id'])['cuenta_contable_codigo']
            _registrar_movimiento_desembolso(db, prestamo, prestamo['cuenta_salida_codigo'])
        db.execute_update(
            """
            UPDATE contabilidad.planilla_prestamo
            SET estado = 'CONFIRMADO', confirmado_por = %s, confirmado_en = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (_usuario_actual(), prestamo_id),
        )
    return _json_ok('Anticipo/préstamo confirmado.')


@planilla_prestamos_bp.route('/recuperar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def recuperar_directo():
    data = request.get_json() or {}
    try:
        prestamo_id = _int_value(data.get('prestamo_id'), 'Anticipo/préstamo')
        fecha = _parse_date(data.get('fecha_aplicacion'), 'Fecha de cobro')
        monto = _money(data.get('monto_aplicado'), 'Monto recuperado')
        medio = _upper(data.get('medio_cobro'))
        referencia = _limit(data.get('referencia'), 'Referencia', 150)
        justificativo = _limit(data.get('justificativo'), 'Justificativo', 800, True)
        if medio not in MEDIOS:
            raise ValueError('Seleccione Caja o Banco para el cobro directo.')
        caja_id = _int_value(data.get('caja_id'), 'Caja') if medio == 'CAJA' else None
        banco_id = _int_value(data.get('cuenta_bancaria_id'), 'Cuenta bancaria') if medio == 'BANCO' else None
    except ValueError as exc:
        return _json_error(str(exc))

    try:
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            prestamo = _prestamo_by_id(db, prestamo_id)
            assert_gestion_abierta(db, int(fecha.year), 'registrar recuperos de anticipos o préstamos')
            if prestamo['estado'] not in {'CONFIRMADO', 'PARCIAL'}:
                return _json_error('Solo se pueden recuperar registros confirmados o parciales.', 409)
            saldo = Decimal(str(prestamo['saldo_pendiente'])).quantize(Q2)
            if monto > saldo:
                return _json_error('El monto recuperado no puede superar el saldo pendiente.', 409)
            if medio == 'CAJA':
                caja = _get_caja(db, caja_id)
                cuenta_ingreso = caja['cuenta_contable_codigo']
            else:
                banco = _get_banco(db, banco_id)
                cuenta_ingreso = banco['cuenta_contable_codigo']
                if banco['moneda_codigo'] != prestamo['moneda_codigo']:
                    return _json_error('La moneda de la cuenta bancaria no coincide con la moneda del anticipo/préstamo.')
            glosa = f"Recupero directo de {prestamo['tipo_operacion'].lower()} {prestamo['codigo']} - {prestamo['nombre_completo']}"
            ref = referencia or f"REC-{prestamo['codigo']}"
            cobro_id = db.execute_insert(
                """
                INSERT INTO contabilidad.cobro (
                    fecha, cliente_auxiliar_id, medio_pago, contra_cuenta_codigo,
                    caja_id, cuenta_bancaria_id, moneda_codigo, tipo_cambio, monto_total,
                    referencia, glosa, estado, asiento_id, origen_operacion, unidad_negocio_id, actualizado_en
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'CONFIRMADO', NULL, 'DIRECTO', %s, CURRENT_TIMESTAMP)
                """,
                (
                    fecha, prestamo['auxiliar_id'], medio, prestamo['cuenta_cobrar_codigo'], caja_id, banco_id,
                    prestamo['moneda_codigo'], prestamo['tipo_cambio'], monto, ref, glosa, prestamo['unidad_negocio_id'],
                ),
            )
            db.execute_insert(
                """
                INSERT INTO contabilidad.cobro_detalle (
                    cobro_id, secuencia, tipo_linea, descripcion, cantidad, precio_unitario,
                    subtotal, observacion
                ) VALUES (%s, 1, 'DIRECTO', %s, 1, %s, %s, %s)
                """,
                (cobro_id, glosa[:300], monto, monto, justificativo[:300]),
                return_id=False,
            )
            asiento_id = db.execute_insert(
                """
                INSERT INTO contabilidad.asiento (
                    fecha, unidad_negocio_id, moneda_codigo, tipo_cambio, glosa, referencia,
                    modulo_origen, tabla_origen, origen_id, estado, cliente_nit_ci_ref,
                    cliente_nombre_ref, atributos, actualizado_en
                ) VALUES (%s, %s, %s, %s, %s, %s, 'TESORERIA', 'contabilidad.cobro', %s, 'CONFIRMADO', %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                """,
                (
                    fecha, prestamo['unidad_negocio_id'], prestamo['moneda_codigo'], prestamo['tipo_cambio'], glosa, ref,
                    cobro_id, prestamo['ci_nit'], prestamo['nombre_completo'],
                    Json({'origen': 'planilla_prestamos', 'accion': 'recupero_directo', 'prestamo_id': prestamo_id})
                ),
            )
            db.execute_insert(
                """
                INSERT INTO contabilidad.asiento_detalle (
                    asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber, monto_moneda, referencia, atributos
                ) VALUES (%s, 1, %s, NULL, %s, %s, 0, %s, %s, %s::jsonb)
                """,
                (asiento_id, cuenta_ingreso, glosa[:300], monto, monto, ref, Json({'tipo': 'debe_ingreso_caja_banco'})),
                return_id=False,
            )
            db.execute_insert(
                """
                INSERT INTO contabilidad.asiento_detalle (
                    asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber, monto_moneda, referencia, atributos
                ) VALUES (%s, 2, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
                """,
                (asiento_id, prestamo['cuenta_cobrar_codigo'], prestamo['auxiliar_id'], glosa[:300], monto, monto, ref, Json({'tipo': 'haber_recupero_prestamo'})),
                return_id=False,
            )
            db.execute_update('UPDATE contabilidad.cobro SET asiento_id = %s, actualizado_en = CURRENT_TIMESTAMP WHERE id = %s', (asiento_id, cobro_id))
            db.execute_insert("INSERT INTO contabilidad.documento_asiento (modulo, tabla_origen, origen_id, asiento_id) VALUES (%s, 'contabilidad.cobro', %s, %s)", ('TESORERIA', cobro_id, asiento_id), return_id=False)
            aplicadas = _aplicar_monto_a_cuotas(db, prestamo_id, monto)
            for item in aplicadas:
                db.execute_insert(
                    """
                    INSERT INTO contabilidad.planilla_prestamo_aplicacion (
                        prestamo_id, cuota_id, tipo_aplicacion, fecha_aplicacion, monto_aplicado,
                        moneda_codigo, tipo_cambio, cobro_id, asiento_id, referencia, justificativo,
                        observacion, creado_por, atributos
                    ) VALUES (%s, %s, 'COBRO_DIRECTO', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        prestamo_id, item['cuota_id'], fecha, item['monto'], prestamo['moneda_codigo'], prestamo['tipo_cambio'],
                        cobro_id, asiento_id, ref, justificativo, 'Recupero directo registrado desde Anticipos y Préstamos.', _usuario_actual(),
                        Json({'origen': 'planilla_prestamos', 'medio': medio})
                    ),
                    return_id=False,
                )
            _actualizar_saldo_prestamo(db, prestamo_id)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        return _json_error('No se pudo registrar el recupero directo. Revise la configuración de caja/banco, cuentas contables y estructura de Tesorería.', 500)
    return _json_ok('Recupero directo registrado.')


@planilla_prestamos_bp.route('/anular-borrador/<int:prestamo_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def anular_borrador(prestamo_id: int):
    data = request.get_json() or {}
    try:
        motivo = _limit(data.get('motivo'), 'Motivo', 800, True)
    except ValueError as exc:
        return _json_error(str(exc))

    try:
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            prestamo = _prestamo_by_id(db, prestamo_id)
            assert_gestion_abierta(db, int(prestamo['fecha_otorgamiento'].year), 'anular anticipos o préstamos')

            if prestamo['estado'] == 'ANULADO':
                return _json_error('El anticipo/préstamo ya se encuentra anulado.', 409)

            aplicaciones = _aplicaciones_prestamo(db, prestamo_id)
            aplicaciones_planilla = [a for a in aplicaciones if a.get('planilla_periodo_id') or str(a.get('tipo_aplicacion') or '').upper() == 'PLANILLA']
            if aplicaciones_planilla:
                return _json_error(
                    'El anticipo/préstamo tiene recuperos aplicados en planillas. Primero revierta las planillas relacionadas desde el módulo correspondiente.',
                    409
                )

            aplicaciones_no_reversibles = [
                a for a in aplicaciones
                if str(a.get('tipo_aplicacion') or '').upper() not in ('COBRO_DIRECTO', 'AJUSTE', 'CONDONACION')
            ]
            if aplicaciones_no_reversibles:
                return _json_error(
                    'El anticipo/préstamo tiene aplicaciones originadas en otro proceso. Primero revierta ese proceso desde su módulo de origen.',
                    409
                )

            reversos: list[int] = []
            for aplicacion in aplicaciones:
                tipo_aplicacion = str(aplicacion.get('tipo_aplicacion') or '').upper()
                if tipo_aplicacion == 'COBRO_DIRECTO':
                    if aplicacion.get('asiento_id'):
                        reverso_cobro_id = _crear_asiento_reverso_desde_asiento(
                            db,
                            int(aplicacion['asiento_id']),
                            date.today(),
                            f"Reverso recupero {prestamo['codigo']}: {motivo}",
                            f"REV-REC-{prestamo['codigo']}",
                            'PLANILLAS',
                            'contabilidad.planilla_prestamo',
                            prestamo_id,
                            'reverso_recupero_prestamo',
                        )
                        reversos.append(reverso_cobro_id)
                    if aplicacion.get('cobro_id'):
                        db.execute_update(
                            """
                            UPDATE contabilidad.cobro
                            SET estado = 'ANULADO',
                                glosa = COALESCE(glosa || E'\n', '') || %s,
                                actualizado_en = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """,
                            (f'Reverso por anulación de anticipo/préstamo: {motivo}', aplicacion['cobro_id'])
                        )
                _revertir_aplicacion_prestamo(db, aplicacion)

            reverso_otorgamiento_id = None
            if prestamo.get('asiento_otorgamiento_id'):
                reverso_otorgamiento_id = _crear_asiento_reverso_desde_asiento(
                    db,
                    int(prestamo['asiento_otorgamiento_id']),
                    date.today(),
                    f"Reverso otorgamiento {prestamo['codigo']}: {motivo}",
                    f"REV-{prestamo['codigo']}",
                    'PLANILLAS',
                    'contabilidad.planilla_prestamo',
                    prestamo_id,
                    'reverso_otorgamiento_prestamo',
                )
                reversos.append(reverso_otorgamiento_id)

            if prestamo.get('movimiento_tesoreria_id'):
                db.execute_update(
                    """
                    UPDATE contabilidad.movimiento_tesoreria
                    SET estado = 'ANULADO',
                        glosa = COALESCE(glosa || E'\n', '') || %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (f'Anulado por reversión de anticipo/préstamo: {motivo}', prestamo['movimiento_tesoreria_id'])
                )

            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo_cuota
                SET estado = 'ANULADA',
                    saldo_pendiente = 0,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE prestamo_id = %s
                """,
                (prestamo_id,)
            )
            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo
                SET estado = 'ANULADO',
                    monto_recuperado = 0,
                    saldo_pendiente = 0,
                    asiento_anulacion_id = %s,
                    anulado_por = %s,
                    anulado_en = CURRENT_TIMESTAMP,
                    observacion = CONCAT(COALESCE(observacion,''), CASE WHEN COALESCE(observacion,'') = '' THEN '' ELSE E'\n' END, %s),
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (reverso_otorgamiento_id, _usuario_actual(), f'Anulado/revertido desde sistema. Motivo: {motivo}', prestamo_id),
            )
        return _json_ok('Anticipo/préstamo anulado y reversado correctamente.', reversos=reversos)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        return _json_error(mensaje_error_operacion('anular el anticipo o préstamo'), 500)
