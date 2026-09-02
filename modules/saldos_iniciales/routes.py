# ============================================================
# DXT CONTA - Modulo Saldos Iniciales
# Comprobante inicial del sistema por unidad de negocio
# ============================================================

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import psycopg2
from flask import Response, jsonify, render_template, request, session
from psycopg2.extras import Json, RealDictCursor

from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.utils import date_label as _date_label
from modules.saldos_iniciales import saldos_iniciales_bp
from utils.db import get_db_connection
from utils.decorators import login_required, roles_required


ROLES_SALDOS_INICIALES = [9, 10, 11]

ESTADO_BORRADOR = 'BORRADOR'
ESTADO_CONFIRMADO = 'CONFIRMADO'
ESTADO_ANULADO = 'ANULADO'
ESTADO_GESTION_ABIERTA = 'ABIERTA'
ESTADO_GESTION_CERRADA = 'CERRADA'

MODULO_ORIGEN = 'SALDOS_INICIALES'
TABLA_ORIGEN = 'contabilidad.asiento'
MONEDA_BASE = 'BOB'

TIPOS_BALANCE = ('ACTIVO', 'PASIVO', 'PATRIMONIO')
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
    return parsed


def _parse_gestion(value: Any) -> int:
    gestion = _parse_int(value, 'Gestion')
    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestion indicada no es valida.')
    return gestion


def _parse_date(value: Any, field_name: str = 'Fecha') -> date:
    raw = _clean(value)
    if not raw:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'El campo "{field_name}" debe tener formato AAAA-MM-DD.')


def _parse_optional_int(value: Any) -> int | None:
    if value in (None, '', 'null'):
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _money(value: Any) -> Decimal:
    if value in (None, '', 'null'):
        return CERO
    try:
        return Decimal(str(value)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Existe un monto no valido en la grilla.')


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
        or session.get('usuario_nombre')
        or session.get('nombre')
        or session.get('username')
        or session.get('usuario')
        or session.get('email')
        or 'Sistema'
    )


# ============================================================
# Acceso a datos
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
# Catalogos y control de gestion
# ============================================================

def _obtener_gestiones_abiertas(cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            gestion,
            estado::text AS estado,
            fecha_cierre,
            comprobante_cierre_id
        FROM contabilidad.gestion_control
        WHERE estado::text = %s
        ORDER BY gestion DESC
        """,
        (ESTADO_GESTION_ABIERTA,),
        cur=cur,
    )


def _gestion_abierta_preferida() -> int:
    row = _fetch_one(
        """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = %s
        ORDER BY gestion DESC
        LIMIT 1
        """,
        (ESTADO_GESTION_ABIERTA,),
    )
    return int(row['gestion']) if row and row.get('gestion') is not None else date.today().year


def _obtener_control_gestion(gestion: int, cur=None, for_update: bool = False) -> dict[str, Any] | None:
    lock_sql = ' FOR UPDATE' if for_update else ''
    return _fetch_one(
        f"""
        SELECT
            gestion,
            estado::text AS estado,
            comprobante_cierre_id,
            fecha_cierre,
            comprobante_apertura_id,
            fecha_apertura,
            creado_en,
            actualizado_en
        FROM contabilidad.gestion_control
        WHERE gestion = %s
        {lock_sql}
        """,
        (gestion,),
        cur=cur,
    )


def _validar_gestion_abierta(gestion: int, cur=None, for_update: bool = False) -> dict[str, Any]:
    control = _obtener_control_gestion(gestion, cur=cur, for_update=for_update)
    if not control:
        raise ValueError(f'La gestion {gestion} no esta registrada en control de gestion.')

    if control.get('estado') != ESTADO_GESTION_ABIERTA:
        raise ValueError(
            f'La gestion {gestion} esta cerrada. Para modificar saldos iniciales debe reabrir la gestion '
            'o registrar un asiento de ajuste en un periodo posterior.'
        )

    if control.get('comprobante_cierre_id') or control.get('fecha_cierre'):
        raise ValueError(
            f'La gestion {gestion} ya tiene cierre registrado. No se permite modificar saldos iniciales directamente.'
        )

    return control


def _listar_unidades_negocio(cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(nit, '') AS nit
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY codigo ASC, nombre ASC
        """,
        cur=cur,
    )


def _listar_cuentas_balance(cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            codigo,
            nombre,
            tipo::text AS tipo,
            naturaleza::text AS naturaleza,
            requiere_auxiliar,
            requiere_cc
        FROM contabilidad.cuenta
        WHERE activo = TRUE
          AND es_postable = TRUE
          AND tipo::text IN %s
        ORDER BY codigo ASC
        """,
        (TIPOS_BALANCE,),
        cur=cur,
    )


def _listar_auxiliares(cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            id,
            COALESCE(NULLIF(codigo_externo, ''), nit_ci, id::text) AS codigo,
            nombre,
            tipo::text AS tipo
        FROM contabilidad.auxiliar
        WHERE activo = TRUE
        ORDER BY nombre ASC, id ASC
        """,
        cur=cur,
    )


def _listar_centros_costo(cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            id,
            codigo,
            nombre
        FROM contabilidad.centro_costo
        WHERE activo = TRUE
        ORDER BY codigo ASC, nombre ASC
        """,
        cur=cur,
    )


def _catalogos(cur=None) -> dict[str, Any]:
    return {
        'gestiones': _json_ready(_obtener_gestiones_abiertas(cur=cur)),
        'unidades': _json_ready(_listar_unidades_negocio(cur=cur)),
        'cuentas': _json_ready(_listar_cuentas_balance(cur=cur)),
        'auxiliares': _json_ready(_listar_auxiliares(cur=cur)),
        'centrosCosto': _json_ready(_listar_centros_costo(cur=cur)),
    }


def _mapa_unidades(cur=None) -> dict[int, dict[str, Any]]:
    return {int(row['id']): row for row in _listar_unidades_negocio(cur=cur)}


def _mapa_cuentas(cur=None) -> dict[str, dict[str, Any]]:
    return {str(row['codigo']).upper(): row for row in _listar_cuentas_balance(cur=cur)}


def _mapa_auxiliares(cur=None) -> set[int]:
    rows = _fetch_all(
        """
        SELECT id
        FROM contabilidad.auxiliar
        WHERE activo = TRUE
        """,
        cur=cur,
    )
    return {int(row['id']) for row in rows}


def _mapa_centros_costo(cur=None) -> set[int]:
    rows = _fetch_all(
        """
        SELECT id
        FROM contabilidad.centro_costo
        WHERE activo = TRUE
        """,
        cur=cur,
    )
    return {int(row['id']) for row in rows}


# ============================================================
# Saldos iniciales existentes
# ============================================================

def _obtener_asientos_saldos_iniciales(gestion: int, cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            a.id,
            a.fecha,
            a.glosa,
            a.referencia,
            a.estado::text AS estado,
            a.unidad_negocio_id,
            u.codigo AS unidad_codigo,
            u.nombre AS unidad_nombre,
            a.creado_en,
            a.actualizado_en,
            COALESCE(SUM(ad.debe), 0)::numeric(18,2) AS total_debe,
            COALESCE(SUM(ad.haber), 0)::numeric(18,2) AS total_haber,
            COUNT(ad.id)::int AS total_lineas
        FROM contabilidad.asiento a
        JOIN contabilidad.unidad_negocio u ON u.id = a.unidad_negocio_id
        LEFT JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        WHERE EXTRACT(YEAR FROM a.fecha)::int = %s
          AND a.modulo_origen = %s
          AND a.estado::text <> %s
        GROUP BY
            a.id,
            a.fecha,
            a.glosa,
            a.referencia,
            a.estado,
            a.unidad_negocio_id,
            u.codigo,
            u.nombre,
            a.creado_en,
            a.actualizado_en
        ORDER BY u.codigo ASC, a.id ASC
        """,
        (gestion, MODULO_ORIGEN, ESTADO_ANULADO),
        cur=cur,
    )


def _obtener_detalle_saldos_iniciales(gestion: int, cur=None) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            a.id AS asiento_id,
            a.fecha,
            a.glosa AS asiento_glosa,
            a.referencia AS asiento_referencia,
            a.estado::text AS asiento_estado,
            a.unidad_negocio_id,
            u.codigo AS unidad_codigo,
            u.nombre AS unidad_nombre,
            ad.id AS detalle_id,
            ad.secuencia,
            ad.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            c.tipo::text AS cuenta_tipo,
            c.naturaleza::text AS cuenta_naturaleza,
            c.requiere_auxiliar,
            c.requiere_cc,
            ad.auxiliar_id,
            aux.nombre AS auxiliar_nombre,
            ad.centro_costo_id,
            cc.nombre AS centro_costo_nombre,
            COALESCE(ad.glosa, '') AS glosa,
            ad.debe,
            ad.haber,
            COALESCE(ad.referencia, '') AS referencia
        FROM contabilidad.asiento a
        JOIN contabilidad.unidad_negocio u ON u.id = a.unidad_negocio_id
        JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.auxiliar aux ON aux.id = ad.auxiliar_id
        LEFT JOIN contabilidad.centro_costo cc ON cc.id = ad.centro_costo_id
        WHERE EXTRACT(YEAR FROM a.fecha)::int = %s
          AND a.modulo_origen = %s
          AND a.estado::text <> %s
        ORDER BY u.codigo ASC, a.id ASC, ad.secuencia ASC
        """,
        (gestion, MODULO_ORIGEN, ESTADO_ANULADO),
        cur=cur,
    )


def _contar_movimientos_no_iniciales(gestion: int, cur=None) -> int:
    row = _fetch_one(
        """
        SELECT COUNT(*)::int AS cantidad
        FROM contabilidad.asiento a
        WHERE EXTRACT(YEAR FROM a.fecha)::int = %s
          AND a.estado::text = %s
          AND COALESCE(a.modulo_origen, '') <> %s
        """,
        (gestion, ESTADO_CONFIRMADO, MODULO_ORIGEN),
        cur=cur,
    )
    return int(row['cantidad']) if row and row.get('cantidad') is not None else 0


def _resumen_por_unidad(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resumen: dict[int, dict[str, Any]] = {}
    for row in rows:
        unidad_id = int(row['unidad_negocio_id'])
        if unidad_id not in resumen:
            resumen[unidad_id] = {
                'unidad_negocio_id': unidad_id,
                'unidad_codigo': row.get('unidad_codigo'),
                'unidad_nombre': row.get('unidad_nombre'),
                'total_debe': CERO,
                'total_haber': CERO,
                'diferencia': CERO,
                'lineas': 0,
                'asientos': [],
            }
        item = resumen[unidad_id]
        item['total_debe'] += _money(row.get('total_debe'))
        item['total_haber'] += _money(row.get('total_haber'))
        item['lineas'] += int(row.get('total_lineas') or 0)
        item['asientos'].append({
            'id': row.get('id'),
            'fecha': row.get('fecha'),
            'referencia': row.get('referencia'),
            'estado': row.get('estado'),
            'total_debe': row.get('total_debe'),
            'total_haber': row.get('total_haber'),
            'total_lineas': row.get('total_lineas'),
        })
    for item in resumen.values():
        item['diferencia'] = _money(item['total_debe'] - item['total_haber'])
    return list(resumen.values())


# ============================================================
# Validacion y grabacion
# ============================================================

def _normalizar_filas(payload_rows: list[dict[str, Any]], cur=None) -> dict[int, list[dict[str, Any]]]:
    if not payload_rows:
        raise ValueError('Debe registrar al menos dos lineas de saldos iniciales.')

    unidades = _mapa_unidades(cur=cur)
    cuentas = _mapa_cuentas(cur=cur)
    auxiliares = _mapa_auxiliares(cur=cur)
    centros = _mapa_centros_costo(cur=cur)

    grupos: dict[int, list[dict[str, Any]]] = {}

    for index, raw in enumerate(payload_rows, start=1):
        unidad_id = _parse_optional_int(raw.get('unidad_negocio_id'))
        if not unidad_id or unidad_id not in unidades:
            raise ValueError(f'Linea {index}: seleccione una unidad de negocio activa.')

        cuenta_codigo = _upper_clean(raw.get('cuenta_codigo'))
        cuenta = cuentas.get(cuenta_codigo)
        if not cuenta:
            raise ValueError(
                f'Linea {index}: la cuenta {cuenta_codigo or "sin codigo"} no existe, no es postable, '
                'no esta activa o no pertenece a ACTIVO, PASIVO o PATRIMONIO.'
            )

        auxiliar_id = _parse_optional_int(raw.get('auxiliar_id'))
        centro_costo_id = _parse_optional_int(raw.get('centro_costo_id'))
        if auxiliar_id and auxiliar_id not in auxiliares:
            raise ValueError(f'Linea {index}: el auxiliar seleccionado no existe o no esta activo.')
        if centro_costo_id and centro_costo_id not in centros:
            raise ValueError(f'Linea {index}: el centro de costo seleccionado no existe o no esta activo.')

        if cuenta.get('requiere_auxiliar') and not auxiliar_id:
            raise ValueError(f'Linea {index}: la cuenta {cuenta_codigo} requiere auxiliar.')
        if cuenta.get('requiere_cc') and not centro_costo_id:
            raise ValueError(f'Linea {index}: la cuenta {cuenta_codigo} requiere centro de costo.')

        debe = _money(raw.get('debe'))
        haber = _money(raw.get('haber'))
        if debe < CERO or haber < CERO:
            raise ValueError(f'Linea {index}: los montos no pueden ser negativos.')
        if debe > CERO and haber > CERO:
            raise ValueError(f'Linea {index}: una linea no puede tener Debe y Haber al mismo tiempo.')
        if debe == CERO and haber == CERO:
            raise ValueError(f'Linea {index}: registre un importe en Debe o Haber.')

        glosa = _clean(raw.get('glosa'))[:300]
        referencia = _clean(raw.get('referencia'))[:150]

        fila = {
            'unidad_negocio_id': unidad_id,
            'cuenta_codigo': cuenta_codigo,
            'auxiliar_id': auxiliar_id,
            'centro_costo_id': centro_costo_id,
            'debe': debe,
            'haber': haber,
            'glosa': glosa,
            'referencia': referencia,
        }
        grupos.setdefault(unidad_id, []).append(fila)

    for unidad_id, filas in grupos.items():
        total_debe = sum((fila['debe'] for fila in filas), CERO).quantize(CENTAVO)
        total_haber = sum((fila['haber'] for fila in filas), CERO).quantize(CENTAVO)
        if total_debe <= CERO or total_haber <= CERO:
            unidad = unidades[unidad_id]
            raise ValueError(f'La unidad {unidad["codigo"]} - {unidad["nombre"]} debe tener Debe y Haber mayores a cero.')
        if total_debe != total_haber:
            unidad = unidades[unidad_id]
            diferencia = (total_debe - total_haber).quantize(CENTAVO)
            raise ValueError(
                f'La unidad {unidad["codigo"]} - {unidad["nombre"]} no cuadra. '
                f'Diferencia: {diferencia}.'
            )

    return grupos


def _asientos_activos_por_unidad(gestion: int, cur=None) -> dict[int, list[dict[str, Any]]]:
    rows = _fetch_all(
        """
        SELECT
            id,
            unidad_negocio_id,
            fecha,
            estado::text AS estado
        FROM contabilidad.asiento
        WHERE EXTRACT(YEAR FROM fecha)::int = %s
          AND modulo_origen = %s
          AND estado::text <> %s
        ORDER BY unidad_negocio_id ASC, id DESC
        FOR UPDATE
        """,
        (gestion, MODULO_ORIGEN, ESTADO_ANULADO),
        cur=cur,
    )
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row['unidad_negocio_id']), []).append(row)
    return grouped


def _insertar_detalles(asiento_id: int, filas: list[dict[str, Any]], glosa_general: str, cur) -> None:
    for secuencia, fila in enumerate(filas, start=1):
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
                fila['cuenta_codigo'],
                fila['auxiliar_id'],
                fila['centro_costo_id'],
                fila['glosa'] or glosa_general,
                fila['debe'],
                fila['haber'],
                fila['debe'] if fila['debe'] > CERO else fila['haber'],
                fila['referencia'] or None,
                Json({'origen': MODULO_ORIGEN}),
            ),
        )


def _actualizar_asiento_existente(asiento_id: int, fecha: date, referencia: str, glosa: str, filas: list[dict[str, Any]], cur) -> int:
    cur.execute(
        """
        UPDATE contabilidad.asiento
        SET fecha = %s,
            moneda_codigo = %s,
            tipo_cambio = 1,
            glosa = %s,
            referencia = %s,
            modulo_origen = %s,
            tabla_origen = %s,
            origen_id = NULL,
            estado = %s::contabilidad.estado_generico_enum,
            atributos = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            fecha,
            MONEDA_BASE,
            glosa,
            referencia,
            MODULO_ORIGEN,
            TABLA_ORIGEN,
            ESTADO_CONFIRMADO,
            Json({
                'tipo': 'COMPROBANTE_INICIAL_SISTEMA',
                'actualizado_por_id': _usuario_id_actual(),
                'actualizado_por': _usuario_nombre_actual(),
                'actualizado_en': datetime.utcnow().isoformat(),
            }),
            asiento_id,
        ),
    )
    cur.execute('DELETE FROM contabilidad.asiento_detalle WHERE asiento_id = %s', (asiento_id,))
    _insertar_detalles(asiento_id, filas, glosa, cur)
    return asiento_id


def _crear_asiento(fecha: date, referencia: str, glosa: str, unidad_id: int, filas: list[dict[str, Any]], cur) -> int:
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
            unidad_negocio_id,
            estado_uso
        )
        VALUES (
            %s,
            %s,
            1,
            %s,
            %s,
            %s,
            %s,
            NULL,
            %s::contabilidad.estado_generico_enum,
            %s,
            %s,
            FALSE
        )
        RETURNING id
        """,
        (
            fecha,
            MONEDA_BASE,
            glosa,
            referencia,
            MODULO_ORIGEN,
            TABLA_ORIGEN,
            ESTADO_CONFIRMADO,
            Json({
                'tipo': 'COMPROBANTE_INICIAL_SISTEMA',
                'creado_por_id': _usuario_id_actual(),
                'creado_por': _usuario_nombre_actual(),
                'creado_en': datetime.utcnow().isoformat(),
            }),
            unidad_id,
        ),
        cur,
    )
    _insertar_detalles(asiento_id, filas, glosa, cur)
    return asiento_id


def _anular_asientos(asientos: list[dict[str, Any]], motivo: str, cur) -> list[int]:
    anulados: list[int] = []
    for asiento in asientos:
        asiento_id = int(asiento['id'])
        cur.execute(
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
                    'usuario_nombre': _usuario_nombre_actual(),
                    'fecha_anulacion': datetime.utcnow().isoformat(),
                }),
                asiento_id,
            ),
        )
        anulados.append(asiento_id)
    return anulados


def _guardar_saldos_iniciales(gestion: int, fecha: date, glosa_general: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if fecha.year != gestion:
        raise ValueError('La fecha de saldos iniciales debe pertenecer a la gestion seleccionada.')

    glosa_general = _clean(glosa_general) or f'Saldos iniciales del sistema - gestion {gestion}'
    if len(glosa_general) > 500:
        raise ValueError('La glosa general no puede exceder 500 caracteres.')

    with _db_cursor(commit=True) as cur:
        control = _validar_gestion_abierta(gestion, cur=cur, for_update=True)
        grupos = _normalizar_filas(rows, cur=cur)
        unidades = _mapa_unidades(cur=cur)
        existentes = _asientos_activos_por_unidad(gestion, cur=cur)

        procesados: list[dict[str, Any]] = []
        anulados: list[int] = []

        for unidad_id, filas in grupos.items():
            unidad = unidades[unidad_id]
            referencia = f'SALDOS INICIALES {gestion} - {unidad["codigo"]}'
            asientos_unidad = existentes.get(unidad_id, [])
            principal = asientos_unidad[0] if asientos_unidad else None

            if principal:
                asiento_id = _actualizar_asiento_existente(int(principal['id']), fecha, referencia, glosa_general, filas, cur)
                if len(asientos_unidad) > 1:
                    anulados.extend(_anular_asientos(asientos_unidad[1:], 'Duplicado de saldos iniciales por unidad', cur))
                accion = 'ACTUALIZADO'
            else:
                asiento_id = _crear_asiento(fecha, referencia, glosa_general, unidad_id, filas, cur)
                accion = 'CREADO'

            total_debe = sum((fila['debe'] for fila in filas), CERO).quantize(CENTAVO)
            total_haber = sum((fila['haber'] for fila in filas), CERO).quantize(CENTAVO)
            procesados.append({
                'accion': accion,
                'asiento_id': asiento_id,
                'unidad_negocio_id': unidad_id,
                'unidad_codigo': unidad['codigo'],
                'unidad_nombre': unidad['nombre'],
                'total_debe': total_debe,
                'total_haber': total_haber,
                'lineas': len(filas),
            })

        unidades_payload = set(grupos.keys())
        for unidad_id, asientos_unidad in existentes.items():
            if unidad_id not in unidades_payload:
                anulados.extend(_anular_asientos(asientos_unidad, 'Unidad removida desde el modulo de saldos iniciales', cur))

        movimientos_no_iniciales = _contar_movimientos_no_iniciales(gestion, cur=cur)
        return {
            'gestion': gestion,
            'fecha': fecha,
            'control': control,
            'procesados': procesados,
            'anulados': anulados,
            'movimientos_no_iniciales': movimientos_no_iniciales,
        }


# ============================================================
# Reporte PDF / Excel
# ============================================================

def _format_money(value: Any) -> str:
    return f'{_money(value):,.2f}'


def _build_reporte_payload(gestion: int) -> dict[str, Any]:
    rows = _obtener_detalle_saldos_iniciales(gestion)
    asientos = _obtener_asientos_saldos_iniciales(gestion)

    total_debe = sum((_money(row.get('debe')) for row in rows), CERO).quantize(CENTAVO)
    total_haber = sum((_money(row.get('haber')) for row in rows), CERO).quantize(CENTAVO)
    diferencia = (total_debe - total_haber).quantize(CENTAVO)
    unidades = {int(row['unidad_negocio_id']) for row in rows if row.get('unidad_negocio_id') is not None}

    reporte_rows = []
    for row in rows:
        unidad = f"{row.get('unidad_codigo') or ''} - {row.get('unidad_nombre') or ''}".strip(' -')
        cuenta = f"{row.get('cuenta_codigo') or ''} - {row.get('cuenta_nombre') or ''}".strip(' -')
        centro = row.get('centro_costo_nombre') or ''
        auxiliar = row.get('auxiliar_nombre') or ''
        reporte_rows.append({
            'fecha_label': _date_label(row.get('fecha')),
            'asiento_id': row.get('asiento_id'),
            'unidad': unidad,
            'cuenta': cuenta,
            'auxiliar': auxiliar,
            'centro_costo': centro,
            'glosa': row.get('glosa') or row.get('asiento_glosa') or '',
            'debe': _money(row.get('debe')),
            'haber': _money(row.get('haber')),
            'debe_label': _format_money(row.get('debe')),
            'haber_label': _format_money(row.get('haber')),
        })

    return {
        'titulo': 'Saldos iniciales del sistema',
        'descripcion_periodo': f'Gestion {gestion}',
        'unidad_label': 'Todas las unidades',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'criterio_reporte': 'Comprobantes activos generados por el modulo SALDOS_INICIALES.',
        'fuente_datos': 'contabilidad.asiento y contabilidad.asiento_detalle.',
        'filtros': {'gestion': gestion},
        'rows': reporte_rows,
        'summary': {
            'gestion': gestion,
            'total_debe': total_debe,
            'total_haber': total_haber,
            'diferencia': diferencia,
            'total_debe_label': _format_money(total_debe),
            'total_haber_label': _format_money(total_haber),
            'diferencia_label': _format_money(diferencia),
            'unidades': len(unidades),
            'asientos': len(asientos),
            'lineas': len(rows),
            'moneda_display_note': 'Importes expresados en BOB.',
        },
    }


class _SaldosInicialesReport:
    TITLE = 'Saldos iniciales del sistema'
    WORKSHEET_TITLE = 'Saldos iniciales'
    FILE_SLUG = 'saldos_iniciales'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'debe', 'haber'}

    @staticmethod
    def excel_columns():
        return [
            ('fecha_label', 'Fecha', 13),
            ('asiento_id', 'Asiento', 11),
            ('unidad', 'Unidad de negocio', 30),
            ('cuenta', 'Cuenta', 42),
            ('auxiliar', 'Auxiliar', 28),
            ('centro_costo', 'Centro costo', 26),
            ('glosa', 'Glosa', 44),
            ('debe', 'Debe', 15),
            ('haber', 'Haber', 15),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Total Debe: {summary.get('total_debe_label', '0.00')} · "
            f"Total Haber: {summary.get('total_haber_label', '0.00')} · "
            f"Diferencia: {summary.get('diferencia_label', '0.00')} · "
            f"Unidades: {summary.get('unidades', 0)} · "
            f"Asientos: {summary.get('asientos', 0)} · "
            f"Lineas: {summary.get('lineas', 0)}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Fecha', 'width': 18, 'align': 'center'},
            {'label': 'Asiento', 'width': 16, 'align': 'center'},
            {'label': 'Unidad', 'width': 38, 'align': 'left'},
            {'label': 'Cuenta', 'width': 56, 'align': 'left'},
            {'label': 'Auxiliar', 'width': 33, 'align': 'left'},
            {'label': 'C. costo', 'width': 31, 'align': 'left'},
            {'label': 'Glosa', 'width': 39, 'align': 'left'},
            {'label': 'Debe', 'width': 15, 'align': 'right'},
            {'label': 'Haber', 'width': 15, 'align': 'right'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('fecha_label', ''),
                item.get('asiento_id', ''),
                item.get('unidad', ''),
                item.get('cuenta', ''),
                item.get('auxiliar', ''),
                item.get('centro_costo', ''),
                item.get('glosa', ''),
                item.get('debe_label', '0.00'),
                item.get('haber_label', '0.00'),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append([
                '',
                '',
                f'Se muestran {MAX_ROWS_PDF} de {len(payload.get("rows", []))} lineas. Use Excel para el detalle completo.',
                '',
                '',
                '',
                '',
                '',
                '',
            ])
        if not rows:
            rows.append(['', '', 'No existen saldos iniciales registrados para la gestion seleccionada.', '', '', '', '', '', ''])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"Gestion: {summary.get('gestion', '')}. "
            f"Total Debe: {summary.get('total_debe_label', '0.00')}. "
            f"Total Haber: {summary.get('total_haber_label', '0.00')}. "
            f"Diferencia: {summary.get('diferencia_label', '0.00')}. "
            f"Unidades: {summary.get('unidades', 0)}. "
            f"Asientos: {summary.get('asientos', 0)}. "
            f"Lineas: {summary.get('lineas', 0)}. "
            'Documento de respaldo para revision y firma.'
        )


# ============================================================
# Endpoints
# ============================================================

@saldos_iniciales_bp.route('/')
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def index():
    gestion = _gestion_abierta_preferida()
    fecha_sugerida = date(gestion, 1, 1)
    with _db_cursor(commit=False) as cur:
        catalogos = _catalogos(cur=cur)
    return render_template(
        'saldos_iniciales_index.html',
        gestion_actual=gestion,
        fecha_sugerida=fecha_sugerida.isoformat(),
        catalogos=catalogos,
    )


@saldos_iniciales_bp.route('/help')
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def help():
    return render_template('saldos_iniciales_help.html')


@saldos_iniciales_bp.route('/catalogos')
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def catalogos():
    try:
        with _db_cursor(commit=False) as cur:
            return _json_ok(data=_catalogos(cur=cur))
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo obtener los catalogos. {exc}', 500)


@saldos_iniciales_bp.route('/estado')
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def estado():
    try:
        gestion = _parse_gestion(request.args.get('gestion'))
        control = _obtener_control_gestion(gestion)
        asientos = _obtener_asientos_saldos_iniciales(gestion)
        movimientos = _contar_movimientos_no_iniciales(gestion)
        bloqueado = not control or control.get('estado') != ESTADO_GESTION_ABIERTA or bool(control.get('comprobante_cierre_id'))
        return _json_ok(
            gestion=gestion,
            control=_json_ready(control),
            bloqueado=bloqueado,
            movimientos_no_iniciales=movimientos,
            resumen=_json_ready(_resumen_por_unidad(asientos)),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo obtener el estado de saldos iniciales. {exc}', 500)


@saldos_iniciales_bp.route('/datos')
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def datos():
    try:
        gestion = _parse_gestion(request.args.get('gestion'))
        control = _obtener_control_gestion(gestion)
        rows = _obtener_detalle_saldos_iniciales(gestion)
        asientos = _obtener_asientos_saldos_iniciales(gestion)
        movimientos = _contar_movimientos_no_iniciales(gestion)
        bloqueado = not control or control.get('estado') != ESTADO_GESTION_ABIERTA or bool(control.get('comprobante_cierre_id'))
        return _json_ok(
            gestion=gestion,
            control=_json_ready(control),
            bloqueado=bloqueado,
            movimientos_no_iniciales=movimientos,
            rows=_json_ready(rows),
            resumen=_json_ready(_resumen_por_unidad(asientos)),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo cargar los saldos iniciales. {exc}', 500)


@saldos_iniciales_bp.route('/pdf')
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def pdf():
    try:
        gestion = _parse_gestion(request.args.get('gestion'))
        payload = _build_reporte_payload(gestion)
        pdf_bytes = build_pdf(_SaldosInicialesReport, payload)
        nombre = f"saldos_iniciales_{gestion}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo generar el PDF de saldos iniciales. {exc}', 500)


@saldos_iniciales_bp.route('/excel')
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def excel():
    try:
        gestion = _parse_gestion(request.args.get('gestion'))
        payload = _build_reporte_payload(gestion)
        payload['rows'] = payload['rows'][:MAX_ROWS_EXPORT]
        excel_bytes = build_excel(_SaldosInicialesReport, payload)
        nombre = f"saldos_iniciales_{gestion}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo generar el Excel de saldos iniciales. {exc}', 500)


@saldos_iniciales_bp.route('/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_SALDOS_INICIALES)
def guardar():
    try:
        payload = request.get_json(silent=True) or {}
        gestion = _parse_gestion(payload.get('gestion'))
        fecha = _parse_date(payload.get('fecha'), 'Fecha inicial')
        glosa = _clean(payload.get('glosa'))
        rows = payload.get('rows') or []
        if not isinstance(rows, list):
            raise ValueError('El detalle enviado no es valido.')

        resultado = _guardar_saldos_iniciales(gestion, fecha, glosa, rows)
        return _json_ok(
            msg='Saldos iniciales guardados correctamente.',
            data=_json_ready(resultado),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except (psycopg2.Error, Exception) as exc:
        return _json_error(f'No se pudo guardar los saldos iniciales. {exc}', 500)
