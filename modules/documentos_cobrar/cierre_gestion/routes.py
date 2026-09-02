# ============================================================
# DXT CONTA - Modulo Cierre y Apertura de Gestion
# Reingenieria completa de backend: cierre, apertura y reapertura
# ============================================================

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

import psycopg2
from flask import jsonify, render_template, request, session
from psycopg2.extras import Json, RealDictCursor

from modules.cierre_gestion import cierre_gestion_bp
from utils.db import get_db_connection
from utils.decorators import login_required, roles_required


ROLES_CIERRE = [9, 10, 11]

ESTADO_BORRADOR = 'BORRADOR'
ESTADO_CONFIRMADO = 'CONFIRMADO'
ESTADO_ANULADO = 'ANULADO'

ESTADO_GESTION_ABIERTA = 'ABIERTA'
ESTADO_GESTION_CERRADA = 'CERRADA'

TIPO_PROCESO_CIERRE = 'CIERRE'
TIPO_PROCESO_APERTURA = 'APERTURA'
TIPO_PROCESO_REAPERTURA = 'REAPERTURA'

ESTADO_BLOQUEO_EN_PROCESO = 'EN_PROCESO'
ESTADO_BLOQUEO_FINALIZADO = 'FINALIZADO'
ESTADO_BLOQUEO_FALLIDO = 'FALLIDO'

ESTADO_PROCESO_EJECUTADO = 'EJECUTADO'
ESTADO_PROCESO_FALLIDO = 'FALLIDO'

TIPO_INGRESO = 'INGRESO'
TIPO_COSTO = 'COSTO'
TIPO_GASTO = 'GASTO'
TIPO_ACTIVO = 'ACTIVO'
TIPO_PASIVO = 'PASIVO'
TIPO_PATRIMONIO = 'PATRIMONIO'

MONEDA_BASE = 'BOB'
MODULO_ORIGEN_CIERRE = 'CIERRE_GESTION'
TABLA_ORIGEN_CIERRE = 'contabilidad.gestion_control'

CENTAVO = Decimal('0.01')
CERO = Decimal('0.00')


# ============================================================
# Respuestas y conversiones
# ============================================================

def _json_ok(**kwargs):
    payload = {'ok': True}
    payload.update(kwargs)
    return jsonify(payload)


def _json_error(message: str, status: int = 400, **kwargs):
    payload = {'ok': False, 'msg': message}
    payload.update(kwargs)
    return jsonify(payload), status


def _clean(value: Any) -> str:
    return (value or '').strip()


def _upper_clean(value: Any) -> str:
    return _clean(value).upper()


def _parse_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field_name}" no es valido.')

    if parsed < 1900 or parsed > 2200:
        raise ValueError(f'El campo "{field_name}" no corresponde a una gestion valida.')

    return parsed


def _gestion_actual() -> int:
    return date.today().year


def _money(value: Any) -> Decimal:
    return Decimal(str(value or '0')).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _json_ready(value: Any) -> Any:
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _usuario_id_actual() -> int | None:
    raw = session.get('user_id') or session.get('id') or session.get('usuario_id')
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _usuario_nombre_actual() -> str:
    return (
        session.get('nombre_completo')
        or session.get('username')
        or session.get('usuario')
        or session.get('email')
        or 'Sistema'
    )


# ============================================================
# Acceso a datos sin ORM, siempre parametrizado
# ============================================================

@contextmanager
def _db_cursor(commit: bool = False):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _fetch_one(query: str, params: tuple[Any, ...] = (), cur=None) -> dict[str, Any] | None:
    if cur is not None:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None

    with _db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None


def _fetch_all(query: str, params: tuple[Any, ...] = (), cur=None) -> list[dict[str, Any]]:
    if cur is not None:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    with _db_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def _execute(query: str, params: tuple[Any, ...] = (), cur=None) -> int:
    if cur is not None:
        cur.execute(query, params)
        return cur.rowcount

    with _db_cursor(commit=True) as cursor:
        cursor.execute(query, params)
        return cursor.rowcount


def _insert_returning_id(query: str, params: tuple[Any, ...], cur) -> int:
    cur.execute(query, params)
    row = cur.fetchone()
    if not row or row.get('id') is None:
        raise ValueError('No se pudo obtener el identificador generado.')
    return int(row['id'])


# ============================================================
# Consultas base
# ============================================================

def _obtener_gestiones_con_asientos() -> list[int]:
    rows = _fetch_all(
        """
        SELECT gestion
        FROM (
            SELECT EXTRACT(YEAR FROM a.fecha)::int AS gestion
            FROM contabilidad.asiento a
            WHERE a.estado::text = %s

            UNION

            SELECT gc.gestion
            FROM contabilidad.gestion_control gc
            WHERE gc.comprobante_cierre_id IS NOT NULL
               OR gc.comprobante_apertura_id IS NOT NULL
               OR gc.fecha_cierre IS NOT NULL
               OR gc.fecha_apertura IS NOT NULL
               OR EXISTS (
                    SELECT 1
                    FROM contabilidad.asiento ax
                    WHERE EXTRACT(YEAR FROM ax.fecha)::int = gc.gestion
                      AND ax.estado::text = %s
               )
        ) s
        WHERE gestion IS NOT NULL
        ORDER BY gestion DESC
        """,
        (ESTADO_CONFIRMADO, ESTADO_CONFIRMADO),
    )
    gestiones = [int(row['gestion']) for row in rows]
    return gestiones or [_gestion_actual()]


def _obtener_configuracion_activa(cur=None) -> dict[str, Any] | None:
    return _fetch_one(
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
        ORDER BY id ASC
        LIMIT 1
        """,
        cur=cur,
    )


def _obtener_control_gestion(gestion: int, cur=None, for_update: bool = False) -> dict[str, Any] | None:
    lock_sql = ' FOR UPDATE' if for_update else ''
    return _fetch_one(
        f"""
        SELECT
            gestion,
            estado::text AS estado,
            comprobante_cierre_id,
            fecha_cierre,
            usuario_cierre_id,
            observacion_cierre,
            comprobante_apertura_id,
            fecha_apertura,
            usuario_apertura_id,
            observacion_apertura,
            fecha_ultima_reapertura,
            usuario_ultima_reapertura_id,
            observacion_ultima_reapertura,
            creado_en,
            actualizado_en
        FROM contabilidad.gestion_control
        WHERE gestion = %s
        {lock_sql}
        """,
        (gestion,),
        cur=cur,
    )




def _control_virtual_gestion(gestion: int, estado: str = ESTADO_GESTION_ABIERTA) -> dict[str, Any]:
    return {
        'gestion': int(gestion),
        'estado': estado,
        'comprobante_cierre_id': None,
        'fecha_cierre': None,
        'usuario_cierre_id': None,
        'observacion_cierre': None,
        'comprobante_apertura_id': None,
        'fecha_apertura': None,
        'usuario_apertura_id': None,
        'observacion_apertura': None,
        'fecha_ultima_reapertura': None,
        'usuario_ultima_reapertura_id': None,
        'observacion_ultima_reapertura': None,
        'creado_en': None,
        'actualizado_en': None,
        'virtual': True,
    }


def _obtener_control_gestion_para_vista(gestion: int, cur=None) -> dict[str, Any]:
    control = _obtener_control_gestion(gestion, cur=cur)
    if control:
        control['virtual'] = False
        return control
    return _control_virtual_gestion(gestion)


def _obtener_control_gestion_requerido(gestion: int, cur=None) -> dict[str, Any]:
    control = _obtener_control_gestion(gestion, cur=cur)
    if not control:
        raise ValueError(f'La gestion {gestion} no tiene control contable registrado.')
    control['virtual'] = False
    return control


def _existen_movimientos_confirmados_gestion(
    gestion: int,
    excluir_asiento_id: int | None = None,
    cur=None,
) -> bool:
    params: list[Any] = [gestion, ESTADO_CONFIRMADO]
    extra = ''
    if excluir_asiento_id:
        extra = ' AND a.id <> %s'
        params.append(int(excluir_asiento_id))

    row = _fetch_one(
        f"""
        SELECT 1 AS existe
        FROM contabilidad.asiento a
        WHERE EXTRACT(YEAR FROM a.fecha)::int = %s
          AND a.estado::text = %s
          {extra}
        LIMIT 1
        """,
        tuple(params),
        cur=cur,
    )
    return bool(row)


def _obtener_gestion_abierta_operativa_posterior(gestion_base: int, cur=None) -> int | None:
    row = _fetch_one(
        """
        SELECT gc.gestion
        FROM contabilidad.gestion_control gc
        WHERE gc.gestion > %s
          AND gc.estado::text = %s
          AND (
                gc.comprobante_apertura_id IS NOT NULL
             OR gc.comprobante_cierre_id IS NOT NULL
             OR gc.fecha_apertura IS NOT NULL
             OR gc.fecha_cierre IS NOT NULL
             OR EXISTS (
                    SELECT 1
                    FROM contabilidad.asiento a
                    WHERE EXTRACT(YEAR FROM a.fecha)::int = gc.gestion
                      AND a.estado::text = %s
                )
          )
        ORDER BY gc.gestion ASC
        LIMIT 1
        """,
        (int(gestion_base), ESTADO_GESTION_ABIERTA, ESTADO_CONFIRMADO),
        cur=cur,
    )
    return int(row['gestion']) if row and row.get('gestion') is not None else None


def _validar_sin_gestion_abierta_operativa_posterior(gestion_base: int, cur=None) -> None:
    gestion_posterior = _obtener_gestion_abierta_operativa_posterior(gestion_base, cur=cur)
    if gestion_posterior:
        raise ValueError(
            f'No se puede continuar porque existe la gestion posterior {gestion_posterior} abierta. '
            'Debe resolver esa gestion antes de ejecutar este proceso.'
        )

def _asegurar_control_gestion(
    gestion: int,
    cur=None,
    for_update: bool = False,
) -> dict[str, Any]:
    if cur is None:
        with _db_cursor(commit=True) as cursor:
            return _asegurar_control_gestion(gestion, cur=cursor, for_update=for_update)

    cur.execute(
        """
        INSERT INTO contabilidad.gestion_control (gestion, estado)
        VALUES (%s, %s::contabilidad.estado_gestion_enum)
        ON CONFLICT (gestion) DO NOTHING
        """,
        (gestion, ESTADO_GESTION_ABIERTA),
    )
    control = _obtener_control_gestion(gestion, cur=cur, for_update=for_update)
    if not control:
        raise ValueError(f'No se pudo inicializar el control de la gestion {gestion}.')
    return control


def _bloquear_controles_gestion(cur, gestiones: Iterable[int]) -> None:
    for gestion in sorted(set(int(g) for g in gestiones)):
        _obtener_control_gestion(gestion, cur=cur, for_update=True)


def _obtener_asiento(asiento_id: int | None, cur=None) -> dict[str, Any] | None:
    if not asiento_id:
        return None

    return _fetch_one(
        """
        SELECT
            id,
            fecha,
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado::text AS estado,
            moneda_codigo,
            unidad_negocio_id,
            tipo_cambio,
            creado_en,
            actualizado_en
        FROM contabilidad.asiento
        WHERE id = %s
        LIMIT 1
        """,
        (asiento_id,),
        cur=cur,
    )


def _cuenta_existe_y_es_postable(codigo: str, cur=None) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT
            codigo,
            nombre,
            activo,
            es_postable,
            tipo::text AS tipo,
            naturaleza::text AS naturaleza
        FROM contabilidad.cuenta
        WHERE codigo = %s
          AND activo = TRUE
          AND es_postable = TRUE
        LIMIT 1
        """,
        (_upper_clean(codigo),),
        cur=cur,
    )


def _listar_cuentas_patrimoniales(q: str = '') -> list[dict[str, Any]]:
    termino = f"%{_clean(q)}%"
    return _fetch_all(
        """
        SELECT
            codigo,
            nombre,
            tipo::text AS tipo
        FROM contabilidad.cuenta
        WHERE activo = TRUE
          AND es_postable = TRUE
          AND tipo::text = %s
          AND (
                %s = '%%'
                OR codigo ILIKE %s
                OR nombre ILIKE %s
              )
        ORDER BY codigo ASC
        LIMIT 100
        """,
        (TIPO_PATRIMONIO, termino, termino, termino),
    )


def _actualizar_cuenta_resultado_ejercicio(cuenta_codigo: str) -> dict[str, Any]:
    codigo = _upper_clean(cuenta_codigo)
    if not codigo:
        raise ValueError('Debe seleccionar la cuenta patrimonial del resultado del ejercicio.')

    with _db_cursor(commit=True) as cur:
        cuenta = _cuenta_existe_y_es_postable(codigo, cur=cur)
        if not cuenta:
            raise ValueError('La cuenta seleccionada no existe o no es una cuenta postable activa.')
        if cuenta.get('tipo') != TIPO_PATRIMONIO:
            raise ValueError('La cuenta seleccionada debe ser de tipo PATRIMONIO.')

        config = _obtener_configuracion_activa(cur=cur)
        if not config:
            raise ValueError('No existe configuracion activa para cierre y apertura de gestion.')

        cur.execute(
            """
            UPDATE contabilidad.gestion_configuracion
            SET cuenta_resultado_ejercicio_codigo = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING
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
            """,
            (codigo, config['id']),
        )
        actualizado = cur.fetchone()
        if not actualizado:
            raise ValueError('No se pudo actualizar la configuracion activa.')
        return dict(actualizado)


# ============================================================
# Bitacora y bloqueo critico
# ============================================================

def _obtener_bloqueo_activo(gestion_origen: int, cur=None) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT
            id,
            tipo_proceso::text AS tipo_proceso,
            estado::text AS estado,
            gestion_origen,
            gestion_destino,
            usuario_id,
            usuario_nombre,
            motivo,
            fecha_hora_inicio,
            fecha_hora_fin,
            token_proceso,
            creado_en
        FROM contabilidad.gestion_bloqueo_critico
        WHERE gestion_origen = %s
          AND estado::text = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (gestion_origen, ESTADO_BLOQUEO_EN_PROCESO),
        cur=cur,
    )


def _validar_sin_bloqueo_activo(gestion: int, cur=None) -> None:
    bloqueo = _obtener_bloqueo_activo(gestion, cur=cur)
    if bloqueo:
        raise ValueError(
            f'La gestion {gestion} tiene un proceso critico en curso ({bloqueo["tipo_proceso"]}).'
        )


def _crear_bloqueo_critico(
    *,
    tipo_proceso: str,
    gestion_origen: int,
    gestion_destino: int | None,
    motivo: str | None,
    cur,
) -> int:
    return _insert_returning_id(
        """
        INSERT INTO contabilidad.gestion_bloqueo_critico (
            tipo_proceso,
            estado,
            gestion_origen,
            gestion_destino,
            usuario_id,
            usuario_nombre,
            motivo
        )
        VALUES (
            %s::contabilidad.tipo_proceso_critico_enum,
            %s::contabilidad.estado_bloqueo_critico_enum,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        RETURNING id
        """,
        (
            tipo_proceso,
            ESTADO_BLOQUEO_EN_PROCESO,
            gestion_origen,
            gestion_destino,
            _usuario_id_actual(),
            _usuario_nombre_actual(),
            motivo,
        ),
        cur,
    )


def _cerrar_bloqueo_critico(bloqueo_id: int, estado: str, cur) -> None:
    _execute(
        """
        UPDATE contabilidad.gestion_bloqueo_critico
        SET estado = %s::contabilidad.estado_bloqueo_critico_enum,
            fecha_hora_fin = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (estado, bloqueo_id),
        cur=cur,
    )


def _registrar_bitacora(
    *,
    tipo_proceso: str,
    estado: str,
    gestion_origen: int,
    gestion_destino: int | None = None,
    comprobante_id: int | None = None,
    observacion: str | None = None,
    detalle: dict[str, Any] | None = None,
    finalizar: bool = True,
    cur=None,
) -> int:
    query = """
        INSERT INTO contabilidad.gestion_proceso_bitacora (
            tipo_proceso,
            estado,
            gestion_origen,
            gestion_destino,
            comprobante_id,
            usuario_id,
            usuario_nombre,
            observacion,
            detalle_json,
            fecha_hora_fin
        )
        VALUES (
            %s::contabilidad.tipo_proceso_gestion_enum,
            %s::contabilidad.estado_proceso_gestion_enum,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END
        )
        RETURNING id
    """
    params = (
        tipo_proceso,
        estado,
        gestion_origen,
        gestion_destino,
        comprobante_id,
        _usuario_id_actual(),
        _usuario_nombre_actual(),
        observacion,
        Json(_json_ready(detalle or {})),
        finalizar,
    )

    if cur is not None:
        return _insert_returning_id(query, params, cur)

    with _db_cursor(commit=True) as cursor:
        return _insert_returning_id(query, params, cursor)


def _registrar_fallo_proceso(
    *,
    tipo_proceso: str,
    gestion_origen: int,
    gestion_destino: int | None = None,
    observacion: str | None = None,
    detalle: dict[str, Any] | None = None,
) -> None:
    try:
        _registrar_bitacora(
            tipo_proceso=tipo_proceso,
            estado=ESTADO_PROCESO_FALLIDO,
            gestion_origen=gestion_origen,
            gestion_destino=gestion_destino,
            observacion=observacion,
            detalle=detalle or {},
            finalizar=True,
        )
    except Exception:
        # No se debe ocultar el error principal por una falla secundaria de bitacora.
        pass


# ============================================================
# Validaciones contables
# ============================================================

def _validar_configuracion_cierre(cur=None) -> dict[str, Any]:
    config = _obtener_configuracion_activa(cur=cur)
    if not config:
        raise ValueError('No existe configuracion activa para cierre y apertura de gestion.')

    cuenta_resultado = _upper_clean(config.get('cuenta_resultado_ejercicio_codigo'))
    if not cuenta_resultado:
        raise ValueError('Debe configurar la cuenta del resultado del ejercicio.')

    cuenta = _cuenta_existe_y_es_postable(cuenta_resultado, cur=cur)
    if not cuenta:
        raise ValueError('La cuenta configurada para resultado del ejercicio no existe o no es postable.')

    if cuenta.get('tipo') != TIPO_PATRIMONIO:
        raise ValueError('La cuenta configurada para resultado del ejercicio debe ser de tipo PATRIMONIO.')

    return config


def _obtener_borradores_en_gestion(gestion: int, cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            id,
            fecha,
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado::text AS estado
        FROM contabilidad.asiento
        WHERE EXTRACT(YEAR FROM fecha)::int = %s
          AND estado::text = %s
        ORDER BY fecha ASC, id ASC
        """,
        (gestion, ESTADO_BORRADOR),
        cur=cur,
    )


def _obtener_movimientos_confirmados_gestion(
    gestion: int,
    excluir_asiento_id: int | None = None,
    cur=None,
) -> list[dict[str, Any]]:
    if excluir_asiento_id:
        return _fetch_all(
            """
            SELECT
                id,
                fecha,
                glosa,
                referencia,
                modulo_origen,
                tabla_origen,
                origen_id,
                estado::text AS estado
            FROM contabilidad.asiento
            WHERE EXTRACT(YEAR FROM fecha)::int = %s
              AND estado::text = %s
              AND id <> %s
            ORDER BY fecha ASC, id ASC
            """,
            (gestion, ESTADO_CONFIRMADO, excluir_asiento_id),
            cur=cur,
        )

    return _fetch_all(
        """
        SELECT
            id,
            fecha,
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado::text AS estado
        FROM contabilidad.asiento
        WHERE EXTRACT(YEAR FROM fecha)::int = %s
          AND estado::text = %s
        ORDER BY fecha ASC, id ASC
        """,
        (gestion, ESTADO_CONFIRMADO),
        cur=cur,
    )


def _obtener_balance_comprobacion_para_gestion(gestion: int, cur=None) -> dict[str, Decimal]:
    row = _fetch_one(
        """
        SELECT
            COALESCE(SUM(ad.debe), 0) AS total_debe,
            COALESCE(SUM(ad.haber), 0) AS total_haber
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        WHERE EXTRACT(YEAR FROM a.fecha)::int = %s
          AND a.estado::text = %s
        """,
        (gestion, ESTADO_CONFIRMADO),
        cur=cur,
    ) or {}
    return {
        'total_debe': _money(row.get('total_debe')),
        'total_haber': _money(row.get('total_haber')),
    }


def _balance_esta_cuadrado(gestion: int, cur=None) -> bool:
    resumen = _obtener_balance_comprobacion_para_gestion(gestion, cur=cur)
    return resumen['total_debe'] == resumen['total_haber']


def _validar_gestion_para_cierre(
    gestion: int,
    cur=None,
    crear_control: bool = False,
) -> dict[str, Any]:
    config = _validar_configuracion_cierre(cur=cur)
    control = (
        _asegurar_control_gestion(gestion, cur=cur, for_update=crear_control)
        if crear_control
        else _obtener_control_gestion_para_vista(gestion, cur=cur)
    )

    _validar_sin_gestion_abierta_operativa_posterior(gestion, cur=cur)

    if control['estado'] == ESTADO_GESTION_CERRADA:
        raise ValueError(f'La gestion {gestion} ya esta cerrada.')

    if control.get('comprobante_cierre_id'):
        asiento_cierre = _obtener_asiento(control['comprobante_cierre_id'], cur=cur)
        if asiento_cierre and asiento_cierre.get('estado') == ESTADO_CONFIRMADO:
            raise ValueError(f'La gestion {gestion} ya tiene un comprobante de cierre confirmado.')

    _validar_sin_bloqueo_activo(gestion, cur=cur)

    if bool(config.get('bloquear_si_hay_borradores')):
        borradores = _obtener_borradores_en_gestion(gestion, cur=cur)
        if borradores:
            raise ValueError(
                f'La gestion {gestion} tiene comprobantes en borrador pendientes. '
                f'Debe resolverlos antes del cierre.'
            )

    if not _balance_esta_cuadrado(gestion, cur=cur):
        raise ValueError(
            f'La gestion {gestion} no esta cuadrada. Revise el Balance de Comprobacion antes del cierre.'
        )

    return {'configuracion': config, 'control': control}


def _validar_gestion_para_apertura(gestion_origen: int, gestion_destino: int, cur=None) -> dict[str, Any]:
    if gestion_destino != gestion_origen + 1:
        raise ValueError('La gestion destino debe ser la inmediata siguiente.')

    config = _validar_configuracion_cierre(cur=cur)
    control_origen = _obtener_control_gestion_requerido(gestion_origen, cur=cur)
    control_destino = _obtener_control_gestion_para_vista(gestion_destino, cur=cur)

    if control_origen['estado'] != ESTADO_GESTION_CERRADA:
        raise ValueError(f'La gestion origen {gestion_origen} debe estar cerrada antes de abrir la siguiente.')

    if not control_origen.get('comprobante_cierre_id'):
        raise ValueError(f'La gestion origen {gestion_origen} no tiene comprobante de cierre registrado.')

    asiento_cierre = _obtener_asiento(control_origen['comprobante_cierre_id'], cur=cur)
    if not asiento_cierre or asiento_cierre.get('estado') != ESTADO_CONFIRMADO:
        raise ValueError('El comprobante de cierre no existe o no esta confirmado.')

    if control_destino.get('estado') == ESTADO_GESTION_CERRADA:
        raise ValueError(f'La gestion destino {gestion_destino} ya se encuentra cerrada.')

    if control_destino.get('comprobante_cierre_id'):
        raise ValueError(f'La gestion destino {gestion_destino} tiene cierre registrado y no puede recibir una apertura nueva.')

    if control_destino.get('comprobante_apertura_id'):
        asiento_apertura = _obtener_asiento(control_destino['comprobante_apertura_id'], cur=cur)
        if asiento_apertura and asiento_apertura.get('estado') == ESTADO_CONFIRMADO:
            raise ValueError(f'La gestion destino {gestion_destino} ya tiene una apertura confirmada.')

    _validar_sin_bloqueo_activo(gestion_origen, cur=cur)
    _validar_sin_bloqueo_activo(gestion_destino, cur=cur)
    _validar_sin_gestion_abierta_operativa_posterior(gestion_destino, cur=cur)

    movimientos_destino = _obtener_movimientos_confirmados_gestion(gestion_destino, cur=cur)
    if movimientos_destino:
        raise ValueError(
            f'La gestion destino {gestion_destino} ya contiene movimientos confirmados. '
            f'La apertura debe realizarse sobre una gestion limpia.'
        )

    return {
        'configuracion': config,
        'control_origen': control_origen,
        'control_destino': control_destino,
    }


def _validar_gestion_para_reapertura(gestion_origen: int, cur=None) -> dict[str, Any]:
    config = _validar_configuracion_cierre(cur=cur)
    gestion_destino = gestion_origen + 1
    control_origen = _obtener_control_gestion_requerido(gestion_origen, cur=cur)
    control_destino = _obtener_control_gestion_para_vista(gestion_destino, cur=cur)

    if not bool(config.get('permitir_reapertura')):
        raise ValueError('La configuracion actual no permite reapertura de gestion.')

    if control_origen['estado'] != ESTADO_GESTION_CERRADA:
        raise ValueError(f'La gestion {gestion_origen} no esta cerrada, por lo tanto no requiere reapertura.')

    if not control_origen.get('comprobante_cierre_id'):
        raise ValueError('No existe comprobante de cierre registrado para la gestion seleccionada.')

    asiento_cierre = _obtener_asiento(control_origen['comprobante_cierre_id'], cur=cur)
    if not asiento_cierre or asiento_cierre.get('estado') != ESTADO_CONFIRMADO:
        raise ValueError('El comprobante de cierre no existe o no esta confirmado.')

    apertura_asiento_id = control_destino.get('comprobante_apertura_id')
    asiento_apertura = _obtener_asiento(apertura_asiento_id, cur=cur) if apertura_asiento_id else None

    if asiento_apertura and asiento_apertura.get('estado') == ESTADO_CONFIRMADO:
        movimientos_conflictivos = _obtener_movimientos_confirmados_gestion(
            gestion_destino,
            excluir_asiento_id=apertura_asiento_id,
            cur=cur,
        )
        if movimientos_conflictivos:
            raise ValueError(
                f'No se puede reabrir la gestion {gestion_origen} porque la gestion '
                f'{gestion_destino} ya tiene movimientos confirmados posteriores a la apertura.'
            )
    elif _existen_movimientos_confirmados_gestion(gestion_destino, cur=cur):
        raise ValueError(
            f'No se puede reabrir la gestion {gestion_origen} porque la gestion '
            f'{gestion_destino} ya tiene movimientos confirmados.'
        )

    _validar_sin_bloqueo_activo(gestion_origen, cur=cur)
    _validar_sin_bloqueo_activo(gestion_destino, cur=cur)
    _validar_sin_gestion_abierta_operativa_posterior(gestion_destino, cur=cur)

    return {
        'configuracion': config,
        'control_origen': control_origen,
        'control_destino': control_destino,
        'gestion_destino': gestion_destino,
        'asiento_cierre': asiento_cierre,
        'asiento_apertura': asiento_apertura,
    }


# ============================================================
# Resumen contable de cierre
# ============================================================

def _consultar_resumen_resultados_gestion(gestion: int, cur=None) -> dict[str, Any]:
    rows = _fetch_all(
        """
        SELECT
            c.tipo::text AS tipo,
            c.codigo,
            c.nombre,
            c.requiere_auxiliar,
            c.requiere_cc,
            ad.auxiliar_id,
            ax.nombre AS auxiliar_nombre,
            ax.tipo::text AS auxiliar_tipo,
            ad.centro_costo_id,
            cc.codigo AS centro_costo_codigo,
            cc.nombre AS centro_costo_nombre,
            COALESCE(SUM(ad.debe), 0) AS total_debe,
            COALESCE(SUM(ad.haber), 0) AS total_haber
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.auxiliar ax
            ON ax.id = ad.auxiliar_id
        LEFT JOIN contabilidad.centro_costo cc
            ON cc.id = ad.centro_costo_id
        WHERE EXTRACT(YEAR FROM a.fecha)::int = %s
          AND a.estado::text = %s
          AND c.es_postable = TRUE
          AND c.tipo::text IN (%s, %s, %s)
        GROUP BY
            c.tipo,
            c.codigo,
            c.nombre,
            c.requiere_auxiliar,
            c.requiere_cc,
            ad.auxiliar_id,
            ax.nombre,
            ax.tipo,
            ad.centro_costo_id,
            cc.codigo,
            cc.nombre
        HAVING COALESCE(SUM(ad.debe), 0) <> 0
            OR COALESCE(SUM(ad.haber), 0) <> 0
        ORDER BY c.tipo, c.codigo, ad.auxiliar_id NULLS FIRST, ad.centro_costo_id NULLS FIRST
        """,
        (gestion, ESTADO_CONFIRMADO, TIPO_INGRESO, TIPO_COSTO, TIPO_GASTO),
        cur=cur,
    )

    ingresos: list[dict[str, Any]] = []
    costos: list[dict[str, Any]] = []
    gastos: list[dict[str, Any]] = []

    total_ingresos = CERO
    total_costos = CERO
    total_gastos = CERO

    for row in rows:
        tipo = row['tipo']
        debe = _money(row.get('total_debe'))
        haber = _money(row.get('total_haber'))

        base_item = {
            'tipo': tipo,
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'requiere_auxiliar': bool(row.get('requiere_auxiliar')),
            'requiere_cc': bool(row.get('requiere_cc')),
            'auxiliar_id': row.get('auxiliar_id'),
            'auxiliar_nombre': row.get('auxiliar_nombre') or '',
            'auxiliar_tipo': row.get('auxiliar_tipo') or '',
            'centro_costo_id': row.get('centro_costo_id'),
            'centro_costo_codigo': row.get('centro_costo_codigo') or '',
            'centro_costo_nombre': row.get('centro_costo_nombre') or '',
            'debe': debe,
            'haber': haber,
        }

        if tipo == TIPO_INGRESO:
            saldo_acreedor = _money(haber - debe)
            if saldo_acreedor:
                ingresos.append({**base_item, 'monto': saldo_acreedor})
                total_ingresos += saldo_acreedor
        elif tipo == TIPO_COSTO:
            saldo_deudor = _money(debe - haber)
            if saldo_deudor:
                costos.append({**base_item, 'monto': saldo_deudor})
                total_costos += saldo_deudor
        elif tipo == TIPO_GASTO:
            saldo_deudor = _money(debe - haber)
            if saldo_deudor:
                gastos.append({**base_item, 'monto': saldo_deudor})
                total_gastos += saldo_deudor

    utilidad_bruta = _money(total_ingresos - total_costos)
    utilidad_neta = _money(utilidad_bruta - total_gastos)

    return {
        'ingresos': ingresos,
        'costos': costos,
        'gastos': gastos,
        'total_ingresos': _money(total_ingresos),
        'total_costos': _money(total_costos),
        'total_gastos': _money(total_gastos),
        'utilidad_bruta': utilidad_bruta,
        'utilidad_neta': utilidad_neta,
        'cantidad_cuentas_cierre': len(ingresos) + len(costos) + len(gastos),
    }


# ============================================================
# Resumen contable de apertura
# ============================================================

def _consultar_saldos_balance_para_apertura(gestion_origen: int, cur=None) -> dict[str, Any]:
    rows = _fetch_all(
        """
        SELECT
            c.tipo::text AS tipo,
            c.codigo,
            c.nombre,
            c.requiere_auxiliar,
            c.requiere_cc,
            ad.auxiliar_id,
            ax.nombre AS auxiliar_nombre,
            ax.tipo::text AS auxiliar_tipo,
            ad.centro_costo_id,
            cc.codigo AS centro_costo_codigo,
            cc.nombre AS centro_costo_nombre,
            COALESCE(SUM(ad.debe), 0) AS total_debe,
            COALESCE(SUM(ad.haber), 0) AS total_haber
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.auxiliar ax
            ON ax.id = ad.auxiliar_id
        LEFT JOIN contabilidad.centro_costo cc
            ON cc.id = ad.centro_costo_id
        WHERE EXTRACT(YEAR FROM a.fecha)::int = %s
          AND a.estado::text = %s
          AND c.es_postable = TRUE
          AND c.tipo::text IN (%s, %s, %s)
        GROUP BY
            c.tipo,
            c.codigo,
            c.nombre,
            c.requiere_auxiliar,
            c.requiere_cc,
            ad.auxiliar_id,
            ax.nombre,
            ax.tipo,
            ad.centro_costo_id,
            cc.codigo,
            cc.nombre
        HAVING COALESCE(SUM(ad.debe), 0) <> 0
            OR COALESCE(SUM(ad.haber), 0) <> 0
        ORDER BY c.tipo, c.codigo, ad.auxiliar_id NULLS FIRST, ad.centro_costo_id NULLS FIRST
        """,
        (gestion_origen, ESTADO_CONFIRMADO, TIPO_ACTIVO, TIPO_PASIVO, TIPO_PATRIMONIO),
        cur=cur,
    )

    activo: list[dict[str, Any]] = []
    pasivo: list[dict[str, Any]] = []
    patrimonio: list[dict[str, Any]] = []

    total_activo = CERO
    total_pasivo = CERO
    total_patrimonio = CERO

    for row in rows:
        tipo = row['tipo']
        debe = _money(row.get('total_debe'))
        haber = _money(row.get('total_haber'))

        base_item = {
            'tipo': tipo,
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'requiere_auxiliar': bool(row.get('requiere_auxiliar')),
            'requiere_cc': bool(row.get('requiere_cc')),
            'auxiliar_id': row.get('auxiliar_id'),
            'auxiliar_nombre': row.get('auxiliar_nombre') or '',
            'auxiliar_tipo': row.get('auxiliar_tipo') or '',
            'centro_costo_id': row.get('centro_costo_id'),
            'centro_costo_codigo': row.get('centro_costo_codigo') or '',
            'centro_costo_nombre': row.get('centro_costo_nombre') or '',
            'debe': debe,
            'haber': haber,
        }

        if tipo == TIPO_ACTIVO:
            saldo = _money(debe - haber)
            total_activo += saldo
            if saldo:
                activo.append({
                    **base_item,
                    'monto': abs(saldo),
                    'saldo_neto': saldo,
                    'lado': 'DEBE' if saldo > 0 else 'HABER',
                })
        elif tipo == TIPO_PASIVO:
            saldo = _money(haber - debe)
            total_pasivo += saldo
            if saldo:
                pasivo.append({
                    **base_item,
                    'monto': abs(saldo),
                    'saldo_neto': saldo,
                    'lado': 'HABER' if saldo > 0 else 'DEBE',
                })
        elif tipo == TIPO_PATRIMONIO:
            saldo = _money(haber - debe)
            total_patrimonio += saldo
            if saldo:
                patrimonio.append({
                    **base_item,
                    'monto': abs(saldo),
                    'saldo_neto': saldo,
                    'lado': 'HABER' if saldo > 0 else 'DEBE',
                })

    return {
        'activo': activo,
        'pasivo': pasivo,
        'patrimonio': patrimonio,
        'total_activo': _money(total_activo),
        'total_pasivo': _money(total_pasivo),
        'total_patrimonio': _money(total_patrimonio),
        'total_pasivo_patrimonio': _money(total_pasivo + total_patrimonio),
        'cantidad_lineas_apertura': len(activo) + len(pasivo) + len(patrimonio),
    }


# ============================================================
# Serializacion para la vista
# ============================================================

def _serializar_resumen_cierre(resumen: dict[str, Any]) -> dict[str, Any]:
    return {
        'ingresos': _json_ready(resumen['ingresos']),
        'costos': _json_ready(resumen['costos']),
        'gastos': _json_ready(resumen['gastos']),
        'total_ingresos': float(resumen['total_ingresos'] or 0),
        'total_costos': float(resumen['total_costos'] or 0),
        'total_gastos': float(resumen['total_gastos'] or 0),
        'utilidad_bruta': float(resumen['utilidad_bruta'] or 0),
        'utilidad_neta': float(resumen['utilidad_neta'] or 0),
        'cantidad_cuentas_cierre': resumen['cantidad_cuentas_cierre'],
    }


def _serializar_resumen_apertura(resumen: dict[str, Any]) -> dict[str, Any]:
    return {
        'activo': _json_ready(resumen['activo']),
        'pasivo': _json_ready(resumen['pasivo']),
        'patrimonio': _json_ready(resumen['patrimonio']),
        'total_activo': float(resumen['total_activo'] or 0),
        'total_pasivo': float(resumen['total_pasivo'] or 0),
        'total_patrimonio': float(resumen['total_patrimonio'] or 0),
        'total_pasivo_patrimonio': float(resumen['total_pasivo_patrimonio'] or 0),
        'cantidad_lineas_apertura': resumen['cantidad_lineas_apertura'],
    }


# ============================================================
# Asientos especiales
# ============================================================

def _obtener_unidad_negocio_id(cur) -> int:
    raw = session.get('unidad_negocio_id')
    if raw:
        try:
            unidad_id = int(raw)
        except (TypeError, ValueError):
            unidad_id = None
        if unidad_id:
            row = _fetch_one(
                """
                SELECT id
                FROM contabilidad.unidad_negocio
                WHERE id = %s
                  AND activo = TRUE
                LIMIT 1
                """,
                (unidad_id,),
                cur=cur,
            )
            if row:
                return int(row['id'])

    row = _fetch_one(
        """
        SELECT id
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY id ASC
        LIMIT 1
        """,
        cur=cur,
    )
    if not row:
        raise ValueError('No existe unidad de negocio activa.')
    return int(row['id'])


def _validar_detalles_asiento(detalles: list[dict[str, Any]]) -> tuple[Decimal, Decimal]:
    if not detalles or len(detalles) < 2:
        raise ValueError('El asiento debe tener al menos dos lineas.')

    total_debe = CERO
    total_haber = CERO

    for idx, item in enumerate(detalles, start=1):
        cuenta_codigo = _upper_clean(item.get('cuenta_codigo'))
        debe = _money(item.get('debe'))
        haber = _money(item.get('haber'))

        if not cuenta_codigo:
            raise ValueError(f'La linea {idx} no tiene cuenta contable.')
        if debe < 0 or haber < 0:
            raise ValueError(f'La linea {idx} tiene importes negativos.')
        if (debe > 0 and haber > 0) or (debe == 0 and haber == 0):
            raise ValueError(f'La linea {idx} debe registrar solo DEBE o solo HABER.')

        item['cuenta_codigo'] = cuenta_codigo
        item['debe'] = debe
        item['haber'] = haber
        total_debe += debe
        total_haber += haber

    total_debe = _money(total_debe)
    total_haber = _money(total_haber)

    if total_debe != total_haber:
        raise ValueError(
            f'El asiento no esta cuadrado. Debe: {total_debe}, Haber: {total_haber}.'
        )

    return total_debe, total_haber


def _insertar_asiento(
    *,
    fecha: date,
    glosa: str,
    referencia: str,
    estado: str,
    detalles: list[dict[str, Any]],
    modulo_origen: str,
    tabla_origen: str,
    origen_id: int,
    atributos: dict[str, Any] | None,
    cur,
) -> int:
    total_debe, total_haber = _validar_detalles_asiento(detalles)
    unidad_negocio_id = _obtener_unidad_negocio_id(cur)

    asiento_id = _insert_returning_id(
        """
        INSERT INTO contabilidad.asiento (
            fecha,
            moneda_codigo,
            tipo_cambio,
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado,
            atributos,
            unidad_negocio_id
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s::contabilidad.estado_generico_enum,
            %s,
            %s
        )
        RETURNING id
        """,
        (
            fecha,
            MONEDA_BASE,
            Decimal('1.000000'),
            glosa,
            referencia,
            modulo_origen,
            tabla_origen,
            origen_id,
            estado,
            Json(_json_ready({
                **(atributos or {}),
                'total_debe': total_debe,
                'total_haber': total_haber,
            })),
            unidad_negocio_id,
        ),
        cur,
    )

    for secuencia, item in enumerate(detalles, start=1):
        cur.execute(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id,
                secuencia,
                cuenta_codigo,
                auxiliar_id,
                centro_costo_id,
                glosa,
                debe,
                haber,
                monto_moneda,
                referencia,
                atributos
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                asiento_id,
                secuencia,
                item['cuenta_codigo'],
                item.get('auxiliar_id'),
                item.get('centro_costo_id'),
                item.get('glosa') or glosa,
                item['debe'],
                item['haber'],
                item['debe'] + item['haber'],
                item.get('referencia') or referencia,
                Json(_json_ready(item.get('atributos') or {})),
            ),
        )

    return asiento_id


def _anular_asiento(asiento_id: int, motivo: str, cur) -> None:
    row = _fetch_one(
        """
        SELECT id, estado::text AS estado
        FROM contabilidad.asiento
        WHERE id = %s
        FOR UPDATE
        """,
        (asiento_id,),
        cur=cur,
    )
    if not row:
        raise ValueError(f'No existe el asiento {asiento_id}.')
    if row['estado'] == ESTADO_ANULADO:
        return
    if row['estado'] != ESTADO_CONFIRMADO:
        raise ValueError(f'El asiento {asiento_id} no esta confirmado y no puede anularse aqui.')

    _execute(
        """
        UPDATE contabilidad.asiento
        SET estado = %s::contabilidad.estado_generico_enum,
            actualizado_en = CURRENT_TIMESTAMP,
            atributos = COALESCE(atributos, '{}'::jsonb) || %s::jsonb
        WHERE id = %s
        """,
        (
            ESTADO_ANULADO,
            Json(_json_ready({
                'anulado_por': 'REAPERTURA_GESTION',
                'motivo_anulacion': motivo,
                'usuario_anulacion_id': _usuario_id_actual(),
                'fecha_anulacion': datetime.now().isoformat(timespec='seconds'),
            })),
            asiento_id,
        ),
        cur=cur,
    )


# ============================================================
# Detalles para cierre y apertura
# ============================================================

def _detalle_cierre_desde_resumen(
    *,
    resumen: dict[str, Any],
    cuenta_resultado_codigo: str,
    glosa: str,
    referencia: str,
) -> list[dict[str, Any]]:
    detalles: list[dict[str, Any]] = []

    def agregar(item: dict[str, Any], tag: str) -> None:
        tipo = item['tipo']
        debe_original = _money(item.get('debe'))
        haber_original = _money(item.get('haber'))

        if tipo == TIPO_INGRESO:
            saldo = _money(haber_original - debe_original)
            debe_cierre = abs(saldo) if saldo > 0 else CERO
            haber_cierre = abs(saldo) if saldo < 0 else CERO
        elif tipo in (TIPO_COSTO, TIPO_GASTO):
            saldo = _money(debe_original - haber_original)
            debe_cierre = abs(saldo) if saldo < 0 else CERO
            haber_cierre = abs(saldo) if saldo > 0 else CERO
        else:
            return

        if not saldo:
            return

        detalles.append({
            'cuenta_codigo': item['codigo'],
            'auxiliar_id': item.get('auxiliar_id'),
            'centro_costo_id': item.get('centro_costo_id'),
            'glosa': glosa,
            'debe': debe_cierre,
            'haber': haber_cierre,
            'referencia': referencia,
            'atributos': {
                'tipo_linea_cierre': tag,
                'saldo_origen': saldo,
                'auxiliar_nombre': item.get('auxiliar_nombre') or '',
                'centro_costo_nombre': item.get('centro_costo_nombre') or '',
            },
        })

    for item in resumen['ingresos']:
        agregar(item, 'CIERRE_INGRESO')
    for item in resumen['costos']:
        agregar(item, 'CIERRE_COSTO')
    for item in resumen['gastos']:
        agregar(item, 'CIERRE_GASTO')

    utilidad_neta = _money(resumen.get('utilidad_neta'))
    if utilidad_neta > 0:
        detalles.append({
            'cuenta_codigo': cuenta_resultado_codigo,
            'auxiliar_id': None,
            'centro_costo_id': None,
            'glosa': glosa,
            'debe': CERO,
            'haber': utilidad_neta,
            'referencia': referencia,
            'atributos': {
                'tipo_linea_cierre': 'RESULTADO_EJERCICIO',
                'resultado_neto': utilidad_neta,
            },
        })
    elif utilidad_neta < 0:
        detalles.append({
            'cuenta_codigo': cuenta_resultado_codigo,
            'auxiliar_id': None,
            'centro_costo_id': None,
            'glosa': glosa,
            'debe': abs(utilidad_neta),
            'haber': CERO,
            'referencia': referencia,
            'atributos': {
                'tipo_linea_cierre': 'RESULTADO_EJERCICIO',
                'resultado_neto': utilidad_neta,
            },
        })

    return detalles


def _detalle_apertura_desde_saldos(
    *,
    resumen: dict[str, Any],
    glosa: str,
    referencia: str,
) -> list[dict[str, Any]]:
    detalles: list[dict[str, Any]] = []

    for grupo_nombre in ('activo', 'pasivo', 'patrimonio'):
        for item in resumen[grupo_nombre]:
            monto = _money(item.get('monto'))
            if not monto:
                continue
            lado = item.get('lado')
            if lado not in ('DEBE', 'HABER'):
                raise ValueError('El saldo de apertura tiene un lado contable invalido.')

            detalles.append({
                'cuenta_codigo': item['codigo'],
                'auxiliar_id': item.get('auxiliar_id'),
                'centro_costo_id': item.get('centro_costo_id'),
                'glosa': glosa,
                'debe': monto if lado == 'DEBE' else CERO,
                'haber': monto if lado == 'HABER' else CERO,
                'referencia': referencia,
                'atributos': {
                    'tipo_linea_apertura': grupo_nombre.upper(),
                    'lado': lado,
                    'saldo_neto': item.get('saldo_neto'),
                    'auxiliar_nombre': item.get('auxiliar_nombre') or '',
                    'centro_costo_nombre': item.get('centro_costo_nombre') or '',
                },
            })

    return detalles


# ============================================================
# Procesos criticos transaccionales
# ============================================================

def _ejecutar_cierre_gestion(gestion: int, observacion: str | None = None) -> dict[str, Any]:
    observacion_final = _clean(observacion) or 'Cierre ejecutado correctamente.'
    gestion_destino = None

    try:
        with _db_cursor(commit=True) as cur:
            _bloquear_controles_gestion(cur, [gestion])
            validacion = _validar_gestion_para_cierre(gestion, cur=cur, crear_control=True)
            config = validacion['configuracion']

            bloqueo_id = _crear_bloqueo_critico(
                tipo_proceso=TIPO_PROCESO_CIERRE,
                gestion_origen=gestion,
                gestion_destino=None,
                motivo=observacion_final,
                cur=cur,
            )

            resumen = _consultar_resumen_resultados_gestion(gestion, cur=cur)
            cuenta_resultado = _upper_clean(config.get('cuenta_resultado_ejercicio_codigo'))
            glosa = _clean(config.get('glosa_cierre')) or 'CIERRE DE GESTION'
            referencia = f'CIERRE GESTION {gestion}'

            detalles = _detalle_cierre_desde_resumen(
                resumen=resumen,
                cuenta_resultado_codigo=cuenta_resultado,
                glosa=glosa,
                referencia=referencia,
            )
            if len(detalles) < 2:
                raise ValueError('No existen suficientes movimientos para generar el cierre.')

            asiento_id = _insertar_asiento(
                fecha=date(gestion, 12, 31),
                glosa=glosa,
                referencia=referencia,
                estado=ESTADO_CONFIRMADO,
                detalles=detalles,
                modulo_origen=MODULO_ORIGEN_CIERRE,
                tabla_origen=TABLA_ORIGEN_CIERRE,
                origen_id=gestion,
                atributos={
                    'tipo_proceso_especial': 'CIERRE_GESTION',
                    'gestion': gestion,
                },
                cur=cur,
            )

            _execute(
                """
                UPDATE contabilidad.gestion_control
                SET estado = %s::contabilidad.estado_gestion_enum,
                    comprobante_cierre_id = %s,
                    fecha_cierre = CURRENT_TIMESTAMP,
                    usuario_cierre_id = %s,
                    observacion_cierre = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE gestion = %s
                """,
                (
                    ESTADO_GESTION_CERRADA,
                    asiento_id,
                    _usuario_id_actual(),
                    observacion_final,
                    gestion,
                ),
                cur=cur,
            )

            _registrar_bitacora(
                tipo_proceso=TIPO_PROCESO_CIERRE,
                estado=ESTADO_PROCESO_EJECUTADO,
                gestion_origen=gestion,
                gestion_destino=gestion_destino,
                comprobante_id=asiento_id,
                observacion=observacion_final,
                detalle={
                    'resumen': _serializar_resumen_cierre(resumen),
                    'asiento_id': asiento_id,
                },
                finalizar=True,
                cur=cur,
            )
            _cerrar_bloqueo_critico(bloqueo_id, ESTADO_BLOQUEO_FINALIZADO, cur=cur)

            return {'asiento_id': asiento_id, 'resumen': resumen}
    except Exception as exc:
        _registrar_fallo_proceso(
            tipo_proceso=TIPO_PROCESO_CIERRE,
            gestion_origen=gestion,
            gestion_destino=gestion_destino,
            observacion=str(exc),
            detalle={'error': str(exc)},
        )
        raise


def _ejecutar_apertura_gestion(gestion_origen: int, observacion: str | None = None) -> dict[str, Any]:
    gestion_destino = gestion_origen + 1
    observacion_final = _clean(observacion) or 'Apertura ejecutada correctamente.'

    try:
        with _db_cursor(commit=True) as cur:
            _bloquear_controles_gestion(cur, [gestion_origen, gestion_destino])
            validacion = _validar_gestion_para_apertura(gestion_origen, gestion_destino, cur=cur)
            config = validacion['configuracion']

            bloqueo_id = _crear_bloqueo_critico(
                tipo_proceso=TIPO_PROCESO_APERTURA,
                gestion_origen=gestion_origen,
                gestion_destino=gestion_destino,
                motivo=observacion_final,
                cur=cur,
            )

            resumen = _consultar_saldos_balance_para_apertura(gestion_origen, cur=cur)
            glosa = _clean(config.get('glosa_apertura')) or 'APERTURA DE GESTION'
            referencia = f'APERTURA GESTION {gestion_destino}'
            detalles = _detalle_apertura_desde_saldos(
                resumen=resumen,
                glosa=glosa,
                referencia=referencia,
            )
            if len(detalles) < 2:
                raise ValueError(
                    f'No existen suficientes saldos de balance para generar la apertura de la gestion {gestion_destino}.'
                )

            total_activo = _money(resumen['total_activo'])
            total_pasivo_patrimonio = _money(resumen['total_pasivo_patrimonio'])
            if total_activo != total_pasivo_patrimonio:
                raise ValueError(
                    'Los saldos de apertura no estan cuadrados. '
                    f'Activo: {total_activo}, Pasivo + Patrimonio: {total_pasivo_patrimonio}.'
                )

            asiento_id = _insertar_asiento(
                fecha=date(gestion_destino, 1, 1),
                glosa=glosa,
                referencia=referencia,
                estado=ESTADO_CONFIRMADO,
                detalles=detalles,
                modulo_origen=MODULO_ORIGEN_CIERRE,
                tabla_origen=TABLA_ORIGEN_CIERRE,
                origen_id=gestion_destino,
                atributos={
                    'tipo_proceso_especial': 'APERTURA_GESTION',
                    'gestion_origen': gestion_origen,
                    'gestion_destino': gestion_destino,
                },
                cur=cur,
            )

            _asegurar_control_gestion(gestion_destino, cur=cur, for_update=True)

            _execute(
                """
                UPDATE contabilidad.gestion_control
                SET estado = %s::contabilidad.estado_gestion_enum,
                    comprobante_apertura_id = %s,
                    fecha_apertura = CURRENT_TIMESTAMP,
                    usuario_apertura_id = %s,
                    observacion_apertura = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE gestion = %s
                """,
                (
                    ESTADO_GESTION_ABIERTA,
                    asiento_id,
                    _usuario_id_actual(),
                    observacion_final,
                    gestion_destino,
                ),
                cur=cur,
            )

            _registrar_bitacora(
                tipo_proceso=TIPO_PROCESO_APERTURA,
                estado=ESTADO_PROCESO_EJECUTADO,
                gestion_origen=gestion_origen,
                gestion_destino=gestion_destino,
                comprobante_id=asiento_id,
                observacion=observacion_final,
                detalle={
                    'resumen': _serializar_resumen_apertura(resumen),
                    'asiento_id': asiento_id,
                },
                finalizar=True,
                cur=cur,
            )
            _cerrar_bloqueo_critico(bloqueo_id, ESTADO_BLOQUEO_FINALIZADO, cur=cur)

            return {'asiento_id': asiento_id, 'resumen': resumen}
    except Exception as exc:
        _registrar_fallo_proceso(
            tipo_proceso=TIPO_PROCESO_APERTURA,
            gestion_origen=gestion_origen,
            gestion_destino=gestion_destino,
            observacion=str(exc),
            detalle={'error': str(exc)},
        )
        raise


def _ejecutar_reapertura_gestion(gestion_origen: int, observacion: str) -> dict[str, Any]:
    observacion_final = _clean(observacion)
    if not observacion_final:
        raise ValueError('Debe registrar una observacion para la reapertura.')

    gestion_destino = gestion_origen + 1

    try:
        with _db_cursor(commit=True) as cur:
            _bloquear_controles_gestion(cur, [gestion_origen, gestion_destino])
            validacion = _validar_gestion_para_reapertura(gestion_origen, cur=cur)
            asiento_cierre = validacion['asiento_cierre']
            asiento_apertura = validacion['asiento_apertura']

            bloqueo_id = _crear_bloqueo_critico(
                tipo_proceso=TIPO_PROCESO_REAPERTURA,
                gestion_origen=gestion_origen,
                gestion_destino=gestion_destino,
                motivo=observacion_final,
                cur=cur,
            )

            asiento_apertura_anulado = None
            if asiento_apertura and asiento_apertura.get('estado') == ESTADO_CONFIRMADO:
                asiento_apertura_anulado = int(asiento_apertura['id'])
                _anular_asiento(asiento_apertura_anulado, observacion_final, cur=cur)
                _execute(
                    """
                    UPDATE contabilidad.gestion_control
                    SET comprobante_apertura_id = NULL,
                        fecha_apertura = NULL,
                        usuario_apertura_id = NULL,
                        observacion_apertura = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE gestion = %s
                    """,
                    ('APERTURA ANULADA POR REAPERTURA DE GESTION', gestion_destino),
                    cur=cur,
                )

            asiento_cierre_anulado = int(asiento_cierre['id'])
            _anular_asiento(asiento_cierre_anulado, observacion_final, cur=cur)

            _execute(
                """
                UPDATE contabilidad.gestion_control
                SET estado = %s::contabilidad.estado_gestion_enum,
                    comprobante_cierre_id = NULL,
                    fecha_cierre = NULL,
                    usuario_cierre_id = NULL,
                    observacion_cierre = %s,
                    fecha_ultima_reapertura = CURRENT_TIMESTAMP,
                    usuario_ultima_reapertura_id = %s,
                    observacion_ultima_reapertura = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE gestion = %s
                """,
                (
                    ESTADO_GESTION_ABIERTA,
                    'CIERRE ANULADO POR REAPERTURA DE GESTION',
                    _usuario_id_actual(),
                    observacion_final,
                    gestion_origen,
                ),
                cur=cur,
            )

            _registrar_bitacora(
                tipo_proceso=TIPO_PROCESO_REAPERTURA,
                estado=ESTADO_PROCESO_EJECUTADO,
                gestion_origen=gestion_origen,
                gestion_destino=gestion_destino,
                comprobante_id=asiento_cierre_anulado,
                observacion=observacion_final,
                detalle={
                    'asiento_cierre_anulado': asiento_cierre_anulado,
                    'asiento_apertura_anulado': asiento_apertura_anulado,
                },
                finalizar=True,
                cur=cur,
            )
            _cerrar_bloqueo_critico(bloqueo_id, ESTADO_BLOQUEO_FINALIZADO, cur=cur)

            return {
                'asiento_cierre_anulado': asiento_cierre_anulado,
                'asiento_apertura_anulado': asiento_apertura_anulado,
            }
    except Exception as exc:
        _registrar_fallo_proceso(
            tipo_proceso=TIPO_PROCESO_REAPERTURA,
            gestion_origen=gestion_origen,
            gestion_destino=gestion_destino,
            observacion=str(exc),
            detalle={'error': str(exc)},
        )
        raise


# ============================================================
# Consultas para vista
# ============================================================

def _obtener_resumen_historico(tipo_proceso: str, gestion_origen: int) -> dict[str, Any] | None:
    row = _fetch_one(
        """
        SELECT detalle_json -> 'resumen' AS resumen
        FROM contabilidad.gestion_proceso_bitacora
        WHERE gestion_origen = %s
          AND tipo_proceso::text = %s
          AND estado::text = %s
          AND detalle_json ? 'resumen'
        ORDER BY fecha_hora_inicio DESC, id DESC
        LIMIT 1
        """,
        (gestion_origen, tipo_proceso, ESTADO_PROCESO_EJECUTADO),
    )
    if row and isinstance(row.get('resumen'), dict):
        return row['resumen']
    return None


def _evaluar_accion_estado(callback, *args) -> dict[str, Any]:
    try:
        callback(*args)
        return {'ok': True, 'mensaje': ''}
    except ValueError as exc:
        return {'ok': False, 'mensaje': str(exc)}
    except Exception as exc:
        return {'ok': False, 'mensaje': f'No se pudo evaluar la accion. {exc}'}


def _estado_general_gestion(gestion: int) -> dict[str, Any]:
    control_origen = _obtener_control_gestion_para_vista(gestion)
    gestion_destino = gestion + 1
    control_destino = _obtener_control_gestion_para_vista(gestion_destino)

    cierre = _obtener_asiento(control_origen.get('comprobante_cierre_id'))
    apertura = _obtener_asiento(control_destino.get('comprobante_apertura_id'))
    bloqueo_origen = _obtener_bloqueo_activo(gestion)
    bloqueo_destino = _obtener_bloqueo_activo(gestion_destino)

    resumen_cierre = _consultar_resumen_resultados_gestion(gestion)
    resumen_apertura = _consultar_saldos_balance_para_apertura(gestion)

    resumen_cierre_view = _serializar_resumen_cierre(resumen_cierre)
    resumen_apertura_view = _serializar_resumen_apertura(resumen_apertura)

    if cierre and not resumen_cierre_view.get('cantidad_cuentas_cierre'):
        historico_cierre = _obtener_resumen_historico(TIPO_PROCESO_CIERRE, gestion)
        if historico_cierre:
            resumen_cierre_view = historico_cierre

    if apertura:
        historico_apertura = _obtener_resumen_historico(TIPO_PROCESO_APERTURA, gestion)
        if historico_apertura:
            resumen_apertura_view = historico_apertura

    acciones = {
        'cerrar': _evaluar_accion_estado(_validar_gestion_para_cierre, gestion),
        'abrir': _evaluar_accion_estado(_validar_gestion_para_apertura, gestion, gestion_destino),
        'reabrir': _evaluar_accion_estado(_validar_gestion_para_reapertura, gestion),
    }

    return {
        'gestion_origen': gestion,
        'gestion_destino': gestion_destino,
        'control_origen': _json_ready(control_origen),
        'control_destino': _json_ready(control_destino),
        'comprobante_cierre': _json_ready(cierre),
        'comprobante_apertura': _json_ready(apertura),
        'bloqueo_origen': _json_ready(bloqueo_origen),
        'bloqueo_destino': _json_ready(bloqueo_destino),
        'resumen_cierre': resumen_cierre_view,
        'resumen_apertura': resumen_apertura_view,
        'balance_cuadrado': _balance_esta_cuadrado(gestion),
        'acciones': acciones,
    }

def _historial_procesos(gestion_origen: int) -> list[dict[str, Any]]:
    """Devuelve la bitacora de procesos asociados a la gestion seleccionada.

    Se usa en la carga de estado y en el endpoint /historial.
    No crea ni modifica datos.
    """
    rows = _fetch_all(
        """
        SELECT
            id,
            tipo_proceso::text AS tipo_proceso,
            estado::text AS estado,
            gestion_origen,
            gestion_destino,
            comprobante_id,
            usuario_id,
            usuario_nombre,
            observacion,
            detalle_json,
            fecha_hora_inicio,
            fecha_hora_fin,
            creado_en
        FROM contabilidad.gestion_proceso_bitacora
        WHERE gestion_origen = %s
           OR gestion_destino = %s
        ORDER BY fecha_hora_inicio DESC, id DESC
        LIMIT 200
        """,
        (gestion_origen, gestion_origen),
    )
    return _json_ready(rows)

@cierre_gestion_bp.route('/')
@login_required
@roles_required(ROLES_CIERRE)
def index():
    gestiones = _obtener_gestiones_con_asientos()
    gestion_base = max(gestiones) if gestiones else _gestion_actual()
    return render_template(
        'cierre_gestion_index.html',
        gestion_actual=gestion_base,
        gestiones=gestiones,
    )


@cierre_gestion_bp.route('/estado')
@login_required
@roles_required(ROLES_CIERRE)
def estado():
    try:
        gestion = _parse_int(request.args.get('gestion') or _gestion_actual(), 'Gestion')
        payload = _estado_general_gestion(gestion)
        payload['historial'] = _historial_procesos(gestion)
        return _json_ok(data=payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo obtener el estado de la gestion. {exc}', 500)


@cierre_gestion_bp.route('/configuracion')
@login_required
@roles_required(ROLES_CIERRE)
def configuracion():
    try:
        config = _validar_configuracion_cierre()
        cuenta = _cuenta_existe_y_es_postable(config['cuenta_resultado_ejercicio_codigo'])
        return _json_ok(configuracion=_json_ready(config), cuenta=_json_ready(cuenta))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo obtener la configuracion. {exc}', 500)


@cierre_gestion_bp.route('/cuentas-patrimoniales')
@login_required
@roles_required(ROLES_CIERRE)
def cuentas_patrimoniales():
    try:
        q = _clean(request.args.get('q'))
        rows = _listar_cuentas_patrimoniales(q)
        return _json_ok(
            rows=[
                {
                    'codigo': row['codigo'],
                    'nombre': row['nombre'],
                    'tipo': row['tipo'],
                    'etiqueta': f"{row['codigo']} - {row['nombre']}",
                }
                for row in rows
            ]
        )
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo obtener las cuentas patrimoniales. {exc}', 500)


@cierre_gestion_bp.route('/configuracion/cuenta-resultado', methods=['POST'])
@login_required
@roles_required(ROLES_CIERRE)
def actualizar_cuenta_resultado():
    try:
        payload = request.get_json(silent=True) or {}
        config = _actualizar_cuenta_resultado_ejercicio(payload.get('cuenta_codigo'))
        cuenta = _cuenta_existe_y_es_postable(config['cuenta_resultado_ejercicio_codigo'])
        return _json_ok(
            msg='La cuenta patrimonial del resultado del ejercicio fue actualizada correctamente.',
            configuracion=_json_ready(config),
            cuenta=_json_ready(cuenta),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo actualizar la cuenta patrimonial. {exc}', 500)


@cierre_gestion_bp.route('/validar-cierre')
@login_required
@roles_required(ROLES_CIERRE)
def validar_cierre():
    try:
        gestion = _parse_int(request.args.get('gestion'), 'Gestion')
        validacion = _validar_gestion_para_cierre(gestion)
        resumen = _consultar_resumen_resultados_gestion(gestion)
        return _json_ok(
            gestion=gestion,
            balance_cuadrado=_balance_esta_cuadrado(gestion),
            configuracion=_json_ready(validacion['configuracion']),
            control=_json_ready(validacion['control']),
            resumen=_serializar_resumen_cierre(resumen),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo validar el cierre. {exc}', 500)


@cierre_gestion_bp.route('/ejecutar-cierre', methods=['POST'])
@login_required
@roles_required(ROLES_CIERRE)
def ejecutar_cierre():
    try:
        payload = request.get_json(silent=True) or {}
        gestion = _parse_int(payload.get('gestion'), 'Gestion')
        observacion = _clean(payload.get('observacion'))
        resultado = _ejecutar_cierre_gestion(gestion=gestion, observacion=observacion)
        return _json_ok(
            msg=f'Se genero correctamente el cierre de la gestion {gestion}.',
            asiento_id=resultado['asiento_id'],
            resumen=_serializar_resumen_cierre(resultado['resumen']),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo ejecutar el cierre. {exc}', 500)


@cierre_gestion_bp.route('/validar-apertura')
@login_required
@roles_required(ROLES_CIERRE)
def validar_apertura():
    try:
        gestion_origen = _parse_int(request.args.get('gestion_origen'), 'Gestion origen')
        gestion_destino = gestion_origen + 1
        validacion = _validar_gestion_para_apertura(gestion_origen, gestion_destino)
        resumen = _consultar_saldos_balance_para_apertura(gestion_origen)
        return _json_ok(
            gestion_origen=gestion_origen,
            gestion_destino=gestion_destino,
            configuracion=_json_ready(validacion['configuracion']),
            control_origen=_json_ready(validacion['control_origen']),
            control_destino=_json_ready(validacion['control_destino']),
            resumen=_serializar_resumen_apertura(resumen),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo validar la apertura. {exc}', 500)


@cierre_gestion_bp.route('/ejecutar-apertura', methods=['POST'])
@login_required
@roles_required(ROLES_CIERRE)
def ejecutar_apertura():
    try:
        payload = request.get_json(silent=True) or {}
        gestion_origen = _parse_int(payload.get('gestion_origen'), 'Gestion origen')
        observacion = _clean(payload.get('observacion'))
        resultado = _ejecutar_apertura_gestion(gestion_origen=gestion_origen, observacion=observacion)
        return _json_ok(
            msg=f'Se genero correctamente la apertura de la gestion {gestion_origen + 1}.',
            asiento_id=resultado['asiento_id'],
            resumen=_serializar_resumen_apertura(resultado['resumen']),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo ejecutar la apertura. {exc}', 500)


@cierre_gestion_bp.route('/reabrir', methods=['POST'])
@login_required
@roles_required(ROLES_CIERRE)
def reabrir():
    try:
        payload = request.get_json(silent=True) or {}
        gestion_origen = _parse_int(payload.get('gestion_origen'), 'Gestion origen')
        observacion = _clean(payload.get('observacion'))
        resultado = _ejecutar_reapertura_gestion(gestion_origen=gestion_origen, observacion=observacion)
        return _json_ok(
            msg=f'Se reabrio correctamente la gestion {gestion_origen}.',
            data=_json_ready(resultado),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo reabrir la gestion. {exc}', 500)


@cierre_gestion_bp.route('/historial')
@login_required
@roles_required(ROLES_CIERRE)
def historial():
    try:
        gestion = _parse_int(request.args.get('gestion'), 'Gestion')
        return _json_ok(rows=_historial_procesos(gestion))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo obtener el historial. {exc}', 500)


@cierre_gestion_bp.route('/help')
@login_required
@roles_required(ROLES_CIERRE)
def help():
    return render_template('cierre_gestion_help.html')
