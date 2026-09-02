# ============================================================
# DXT CONTA - Modulo Checklist Pre-Cierre
# Diagnostico previo al cierre de gestion, sin ejecutar cierre
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Response, jsonify, render_template, request

from database.db_manager import DatabaseManager
from modules.checklist_precierre import checklist_precierre_bp
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import format_money
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]

ESTADO_OK = 'OK'
ESTADO_OBSERVADO = 'OBSERVADO'
ESTADO_BLOQUEANTE = 'BLOQUEANTE'
ESTADO_INFORMATIVO = 'INFORMATIVO'

PRIORIDAD_LABEL = {
    'CRITICA': 'Crítica',
    'ALTA': 'Alta',
    'MEDIA': 'Media',
    'BAJA': 'Baja',
    'OK': 'OK',
}

PRIORIDAD_ORDEN = {
    'CRITICA': 1,
    'ALTA': 2,
    'MEDIA': 3,
    'BAJA': 4,
    'OK': 5,
}


# ============================================================
# Helpers generales
# ============================================================


def _json_ok(**kwargs):
    payload = {'ok': True}
    payload.update(kwargs)
    return jsonify(_json_ready(payload))


def _json_error(message: str, status: int = 400, **kwargs):
    payload = {'ok': False, 'msg': message}
    payload.update(kwargs)
    return jsonify(_json_ready(payload)), status


def _clean(value: Any) -> str:
    return (value or '').strip()


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _parse_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es válido.') from exc
    return parsed


def _date_label(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    raw = _clean(value)
    if not raw:
        return ''
    try:
        parsed = datetime.strptime(raw[:10], '%Y-%m-%d').date()
        return parsed.strftime('%d/%m/%Y')
    except ValueError:
        return raw


def _db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    return [dict(row) for row in rows]


def _db_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = _db_rows(sql, params)
    return rows[0] if rows else None


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = _db_one(sql, params)
    if not row:
        return 0
    try:
        return int(row.get('cantidad') or 0)
    except (TypeError, ValueError):
        return 0


def _gestion_actual() -> int:
    return date.today().year


def _obtener_gestiones() -> list[int]:
    sql = """
        SELECT gestion
        FROM (
            SELECT gestion::int AS gestion FROM contabilidad.gestion_control
            UNION
            SELECT EXTRACT(YEAR FROM fecha)::int AS gestion FROM contabilidad.asiento
            UNION
            SELECT EXTRACT(YEAR FROM CURRENT_DATE)::int AS gestion
        ) q
        WHERE gestion IS NOT NULL
        ORDER BY gestion DESC
    """
    rows = _db_rows(sql)
    return [int(row['gestion']) for row in rows] or [_gestion_actual()]


def _gestion_preferida() -> int:
    sql = """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
    """
    row = _db_one(sql)
    if row:
        return int(row['gestion'])
    return _gestion_actual()


def _parse_filters(args) -> dict[str, Any]:
    gestion = _parse_int(args.get('gestion') or _gestion_preferida(), 'Gestión')
    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestión indicada no es válida.')
    return {
        'gestion': gestion,
        'gestion_destino': gestion + 1,
        'fecha_desde': date(gestion, 1, 1),
        'fecha_hasta': date(gestion, 12, 31),
        'periodo_label': f'Gestión {gestion}',
        'unidad_label': 'Cierre global',
    }


def _estado_final(prioridad_codigo: str) -> str:
    if prioridad_codigo == 'CRITICA':
        return ESTADO_BLOQUEANTE
    if prioridad_codigo in {'ALTA', 'MEDIA'}:
        return ESTADO_OBSERVADO
    if prioridad_codigo == 'OK':
        return ESTADO_OK
    return ESTADO_INFORMATIVO


def _append_row(rows: list[dict[str, Any]], *, prioridad_codigo: str, categoria: str, criterio: str,
                resultado: str, detalle: str, accion: str, fuente: str = '', cantidad: Any = 0,
                monto: Any = 0, moneda_codigo: str = 'BOB') -> None:
    monto_dec = _decimal(monto)
    rows.append({
        'nro': len(rows) + 1,
        'prioridad_codigo': prioridad_codigo,
        'prioridad': PRIORIDAD_LABEL.get(prioridad_codigo, prioridad_codigo.title()),
        'prioridad_orden': PRIORIDAD_ORDEN.get(prioridad_codigo, 9),
        'estado': _estado_final(prioridad_codigo),
        'categoria': categoria,
        'criterio': criterio,
        'resultado': resultado,
        'detalle': detalle,
        'accion': accion,
        'fuente': fuente,
        'cantidad': int(cantidad or 0),
        'monto': float(monto_dec),
        'monto_label': format_money(monto_dec, moneda_codigo or 'BOB'),
        'moneda_codigo': moneda_codigo or 'BOB',
    })


# ============================================================
# Consultas de checklist
# ============================================================


def _check_estado_gestion(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> dict[str, Any] | None:
    row = _db_one(
        """
        SELECT
            gestion,
            estado::text AS estado,
            comprobante_cierre_id,
            fecha_cierre,
            comprobante_apertura_id,
            fecha_apertura
        FROM contabilidad.gestion_control
        WHERE gestion = %s
        LIMIT 1
        """,
        (filtros['gestion'],),
    )
    if not row:
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Gestión',
            criterio='La gestión debe existir en el control de gestión.',
            resultado='No registrada',
            detalle=f'No existe registro para la gestión {filtros["gestion"]} en gestion_control.',
            accion='Revisar Configuración Inicial antes de intentar el cierre.',
            fuente='contabilidad.gestion_control',
        )
        return None

    estado = row.get('estado') or ''
    if estado == 'ABIERTA':
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Gestión',
            criterio='La gestión debe estar abierta para ejecutar cierre.',
            resultado='Gestión abierta',
            detalle=f'La gestión {filtros["gestion"]} está abierta y puede evaluarse para cierre.',
            accion='Continuar con las demás revisiones del checklist.',
            fuente='contabilidad.gestion_control',
        )
    elif estado == 'CERRADA':
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Gestión',
            criterio='La gestión no debe estar cerrada previamente.',
            resultado='Gestión cerrada',
            detalle=f'La gestión ya fue cerrada. Fecha de cierre: {_date_label(row.get("fecha_cierre"))}.',
            accion='No ejecutar un nuevo cierre. Revisar el comprobante existente o el proceso de reapertura.',
            fuente='contabilidad.gestion_control',
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='ALTA',
            categoria='Gestión',
            criterio='La gestión debe tener estado operativo válido.',
            resultado=estado or 'Sin estado',
            detalle='El estado de gestión no corresponde a ABIERTA o CERRADA.',
            accion='Revisar el registro de gestión antes de ejecutar procesos críticos.',
            fuente='contabilidad.gestion_control',
        )
    return row


def _check_configuracion_cierre(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    config = _db_one(
        """
        SELECT
            gc.id,
            gc.activo,
            gc.cuenta_resultado_ejercicio_codigo,
            gc.generar_backup_pre_cierre,
            gc.permitir_reapertura,
            gc.bloquear_si_hay_borradores,
            gc.bloquear_si_hay_movimientos_destino,
            c.codigo AS cuenta_codigo,
            c.nombre AS cuenta_nombre,
            c.tipo::text AS cuenta_tipo,
            c.activo AS cuenta_activa,
            c.es_postable AS cuenta_postable
        FROM contabilidad.gestion_configuracion gc
        LEFT JOIN contabilidad.cuenta c ON c.codigo = gc.cuenta_resultado_ejercicio_codigo
        WHERE gc.activo = TRUE
        ORDER BY gc.id ASC
        LIMIT 1
        """
    )
    if not config:
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Configuración',
            criterio='Debe existir configuración activa para cierre y apertura.',
            resultado='No configurado',
            detalle='No se encontró configuración activa de gestión.',
            accion='Configurar la cuenta de resultado del ejercicio y reglas de cierre.',
            fuente='contabilidad.gestion_configuracion',
        )
        return None

    cuenta_ok = bool(
        config.get('cuenta_codigo')
        and config.get('cuenta_tipo') == 'PATRIMONIO'
        and config.get('cuenta_activa') is True
        and config.get('cuenta_postable') is True
    )
    if cuenta_ok:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Configuración',
            criterio='La cuenta de resultado debe ser patrimonial, activa y postable.',
            resultado='Configuración válida',
            detalle=f"Cuenta resultado: {config.get('cuenta_resultado_ejercicio_codigo')} · {config.get('cuenta_nombre')}",
            accion='Mantener esta configuración para ejecutar el cierre.',
            fuente='contabilidad.gestion_configuracion / contabilidad.cuenta',
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Configuración',
            criterio='La cuenta de resultado debe ser patrimonial, activa y postable.',
            resultado='Configuración inválida',
            detalle=(
                f"Cuenta configurada: {config.get('cuenta_resultado_ejercicio_codigo') or 'Sin cuenta'}. "
                f"Tipo: {config.get('cuenta_tipo') or 'No encontrada'}."
            ),
            accion='Corregir la configuración antes del cierre.',
            fuente='contabilidad.gestion_configuracion / contabilidad.cuenta',
        )
    return config


def _check_cierre_existente(rows: list[dict[str, Any]], filtros: dict[str, Any], control: dict[str, Any] | None) -> None:
    cierre_confirmado = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.asiento
        WHERE estado::text = 'CONFIRMADO'
          AND modulo_origen = 'CIERRE_GESTION'
          AND EXTRACT(YEAR FROM fecha)::int = %s
        """,
        (filtros['gestion'],),
    )
    tiene_cierre_control = bool(control and control.get('comprobante_cierre_id'))
    if cierre_confirmado or tiene_cierre_control:
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Duplicidad de cierre',
            criterio='No debe existir cierre confirmado previo para la gestión.',
            resultado='Cierre existente',
            detalle='Existe comprobante de cierre confirmado o registrado en control de gestión.',
            accion='No ejecutar cierre duplicado. Revisar el cierre existente o ejecutar reapertura si corresponde.',
            fuente='contabilidad.asiento / contabilidad.gestion_control',
            cantidad=max(cierre_confirmado, 1),
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Duplicidad de cierre',
            criterio='No debe existir cierre confirmado previo para la gestión.',
            resultado='Sin cierre previo',
            detalle='No se detectó comprobante de cierre confirmado para la gestión consultada.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.asiento / contabilidad.gestion_control',
        )


def _check_bloqueos(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    cantidad = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.gestion_bloqueo_critico
        WHERE gestion_origen = %s
          AND estado::text = 'EN_PROCESO'
        """,
        (filtros['gestion'],),
    )
    if cantidad:
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Bloqueos críticos',
            criterio='No debe existir otro proceso crítico en ejecución.',
            resultado='Bloqueo activo',
            detalle=f'Existen {cantidad} bloqueo(s) crítico(s) en proceso para esta gestión.',
            accion='Esperar a que finalice el proceso o revisar la bitácora si quedó bloqueado.',
            fuente='contabilidad.gestion_bloqueo_critico',
            cantidad=cantidad,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Bloqueos críticos',
            criterio='No debe existir otro proceso crítico en ejecución.',
            resultado='Sin bloqueos activos',
            detalle='No se detectaron procesos críticos activos para la gestión.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.gestion_bloqueo_critico',
        )


def _check_asientos_base(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    params = (filtros['fecha_desde'], filtros['fecha_hasta'])
    descuadrados = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM (
            SELECT a.id
            FROM contabilidad.asiento a
            LEFT JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
            WHERE a.fecha BETWEEN %s AND %s
              AND a.estado::text <> 'ANULADO'
            GROUP BY a.id
            HAVING ABS(COALESCE(SUM(ad.debe), 0) - COALESCE(SUM(ad.haber), 0)) > 0.01
        ) q
        """,
        params,
    )
    if descuadrados:
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Comprobantes',
            criterio='Todos los asientos deben estar cuadrados.',
            resultado='Asientos descuadrados',
            detalle=f'Se detectaron {descuadrados} asiento(s) con diferencia entre Debe y Haber.',
            accion='Corregir los comprobantes descuadrados antes de cerrar.',
            fuente='contabilidad.asiento / contabilidad.asiento_detalle',
            cantidad=descuadrados,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Comprobantes',
            criterio='Todos los asientos deben estar cuadrados.',
            resultado='Asientos cuadrados',
            detalle='No se detectaron diferencias entre Debe y Haber en los asientos de la gestión.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.asiento / contabilidad.asiento_detalle',
        )

    sin_detalle = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.asiento a
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND NOT EXISTS (
              SELECT 1 FROM contabilidad.asiento_detalle ad WHERE ad.asiento_id = a.id
          )
        """,
        params,
    )
    if sin_detalle:
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Comprobantes',
            criterio='Todo asiento debe tener líneas de detalle.',
            resultado='Asientos sin detalle',
            detalle=f'Se detectaron {sin_detalle} asiento(s) sin líneas contables.',
            accion='Completar o anular esos comprobantes antes del cierre.',
            fuente='contabilidad.asiento / contabilidad.asiento_detalle',
            cantidad=sin_detalle,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Comprobantes',
            criterio='Todo asiento debe tener líneas de detalle.',
            resultado='Detalle completo',
            detalle='Todos los asientos tienen detalle contable.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.asiento_detalle',
        )


def _check_borradores(rows: list[dict[str, Any]], filtros: dict[str, Any], config: dict[str, Any] | None) -> None:
    params = (filtros['fecha_desde'], filtros['fecha_hasta'])
    cantidad = _count(
        """
        WITH operaciones AS (
            SELECT fecha, estado::text AS estado FROM contabilidad.asiento
            UNION ALL SELECT fecha, estado::text FROM contabilidad.pago
            UNION ALL SELECT fecha, estado::text FROM contabilidad.cobro
            UNION ALL SELECT fecha, estado::text FROM contabilidad.movimiento_tesoreria
            UNION ALL SELECT fecha, estado::text FROM contabilidad.compra
            UNION ALL SELECT fecha, estado::text FROM contabilidad.venta
        )
        SELECT COUNT(*) AS cantidad
        FROM operaciones
        WHERE fecha BETWEEN %s AND %s
          AND estado = 'BORRADOR'
        """,
        params,
    )
    bloquea = bool(config and config.get('bloquear_si_hay_borradores'))
    if cantidad:
        _append_row(
            rows,
            prioridad_codigo='CRITICA' if bloquea else 'ALTA',
            categoria='Borradores',
            criterio='No deben quedar operaciones en borrador antes del cierre.',
            resultado='Borradores pendientes',
            detalle=f'Existen {cantidad} operación(es) en BORRADOR dentro de la gestión.',
            accion='Confirmar o anular los borradores antes de ejecutar el cierre.',
            fuente='asiento, pago, cobro, movimiento_tesoreria, compra, venta',
            cantidad=cantidad,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Borradores',
            criterio='No deben quedar operaciones en borrador antes del cierre.',
            resultado='Sin borradores',
            detalle='No se detectaron operaciones en borrador dentro de la gestión.',
            accion='Continuar con la revisión previa.',
            fuente='asiento, pago, cobro, movimiento_tesoreria, compra, venta',
        )


def _check_operaciones_sin_asiento(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    cantidad = _count(
        """
        WITH operaciones AS (
            SELECT fecha, estado::text AS estado, asiento_id FROM contabilidad.pago
            UNION ALL SELECT fecha, estado::text, asiento_id FROM contabilidad.cobro
            UNION ALL SELECT fecha, estado::text, asiento_id FROM contabilidad.movimiento_tesoreria
            UNION ALL SELECT fecha, estado::text, asiento_id FROM contabilidad.compra
            UNION ALL SELECT fecha, estado::text, asiento_id FROM contabilidad.venta
        )
        SELECT COUNT(*) AS cantidad
        FROM operaciones
        WHERE fecha BETWEEN %s AND %s
          AND estado = 'CONFIRMADO'
          AND asiento_id IS NULL
        """,
        (filtros['fecha_desde'], filtros['fecha_hasta']),
    )
    if cantidad:
        _append_row(
            rows,
            prioridad_codigo='ALTA',
            categoria='Integración contable',
            criterio='Las operaciones confirmadas deben tener asiento asociado cuando corresponda.',
            resultado='Operaciones sin asiento',
            detalle=f'Se detectaron {cantidad} operación(es) confirmada(s) sin asiento_id.',
            accion='Revisar el módulo de origen y regenerar o vincular el asiento contable si corresponde.',
            fuente='pago, cobro, movimiento_tesoreria, compra, venta',
            cantidad=cantidad,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Integración contable',
            criterio='Las operaciones confirmadas deben tener asiento asociado cuando corresponda.',
            resultado='Integración correcta',
            detalle='No se detectaron operaciones confirmadas sin asiento asociado.',
            accion='Continuar con la revisión previa.',
            fuente='pago, cobro, movimiento_tesoreria, compra, venta',
        )


def _check_cuentas_detalle(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    params = (filtros['fecha_desde'], filtros['fecha_hasta'])
    cuentas_invalidas = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.asiento_detalle ad
        JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND (c.codigo IS NULL OR c.activo IS DISTINCT FROM TRUE OR c.es_postable IS DISTINCT FROM TRUE)
        """,
        params,
    )
    if cuentas_invalidas:
        _append_row(
            rows,
            prioridad_codigo='ALTA',
            categoria='Plan de cuentas',
            criterio='Los movimientos deben usar cuentas activas y postables.',
            resultado='Cuentas no válidas usadas',
            detalle=f'Existen {cuentas_invalidas} línea(s) con cuenta inexistente, inactiva o no postable.',
            accion='Revisar el comprobante y cambiar a cuentas contables válidas.',
            fuente='contabilidad.asiento_detalle / contabilidad.cuenta',
            cantidad=cuentas_invalidas,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Plan de cuentas',
            criterio='Los movimientos deben usar cuentas activas y postables.',
            resultado='Cuentas válidas',
            detalle='Las líneas contables usan cuentas activas y postables.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.cuenta',
        )

    faltantes = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.asiento_detalle ad
        JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text <> 'ANULADO'
          AND c.activo = TRUE
          AND c.es_postable = TRUE
          AND (
              (c.requiere_auxiliar = TRUE AND ad.auxiliar_id IS NULL)
              OR (c.requiere_cc = TRUE AND ad.centro_costo_id IS NULL)
          )
        """,
        params,
    )
    if faltantes:
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Datos de detalle',
            criterio='Las cuentas que requieren auxiliar o centro de costo deben tenerlo informado.',
            resultado='Datos requeridos faltantes',
            detalle=f'Existen {faltantes} línea(s) con auxiliar o centro de costo faltante.',
            accion='Completar los datos faltantes para mejorar reportes y trazabilidad.',
            fuente='contabilidad.asiento_detalle / contabilidad.cuenta',
            cantidad=faltantes,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Datos de detalle',
            criterio='Las cuentas que requieren auxiliar o centro de costo deben tenerlo informado.',
            resultado='Datos completos',
            detalle='No se detectaron auxiliares o centros de costo requeridos faltantes.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.asiento_detalle / contabilidad.cuenta',
        )


def _check_balance_comprobacion(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    row = _db_one(
        """
        SELECT
            COALESCE(SUM(ad.debe), 0)::numeric(18,2) AS total_debe,
            COALESCE(SUM(ad.haber), 0)::numeric(18,2) AS total_haber,
            ABS(COALESCE(SUM(ad.debe), 0) - COALESCE(SUM(ad.haber), 0))::numeric(18,2) AS diferencia
        FROM contabilidad.asiento a
        JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text = 'CONFIRMADO'
        """,
        (filtros['fecha_desde'], filtros['fecha_hasta']),
    ) or {}
    diferencia = _decimal(row.get('diferencia'))
    detalle = (
        f"Debe {format_money(row.get('total_debe'), 'BOB')} / "
        f"Haber {format_money(row.get('total_haber'), 'BOB')} / "
        f"Diferencia {format_money(diferencia, 'BOB')}"
    )
    if abs(diferencia) > Decimal('0.01'):
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Balance de comprobación',
            criterio='El total Debe debe ser igual al total Haber en asientos confirmados.',
            resultado='Balance descuadrado',
            detalle=detalle,
            accion='Corregir diferencias antes de ejecutar el cierre.',
            fuente='contabilidad.asiento / contabilidad.asiento_detalle',
            monto=diferencia,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Balance de comprobación',
            criterio='El total Debe debe ser igual al total Haber en asientos confirmados.',
            resultado='Balance cuadrado',
            detalle=detalle,
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.asiento / contabilidad.asiento_detalle',
        )


def _check_movimientos_destino(rows: list[dict[str, Any]], filtros: dict[str, Any], config: dict[str, Any] | None) -> None:
    cantidad = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.asiento
        WHERE fecha BETWEEN %s AND %s
          AND estado::text = 'CONFIRMADO'
          AND COALESCE(modulo_origen, '') NOT IN ('APERTURA_GESTION', 'CIERRE_GESTION')
        """,
        (date(filtros['gestion_destino'], 1, 1), date(filtros['gestion_destino'], 12, 31)),
    )
    bloquea = bool(config and config.get('bloquear_si_hay_movimientos_destino'))
    if cantidad:
        _append_row(
            rows,
            prioridad_codigo='ALTA' if bloquea else 'MEDIA',
            categoria='Gestión siguiente',
            criterio='La gestión siguiente no debería tener movimientos confirmados antes de apertura.',
            resultado='Movimientos en destino',
            detalle=f'Se detectaron {cantidad} asiento(s) confirmado(s) en la gestión {filtros["gestion_destino"]}.',
            accion='Revisar si corresponden o si deben anularse antes de abrir la nueva gestión.',
            fuente='contabilidad.asiento',
            cantidad=cantidad,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Gestión siguiente',
            criterio='La gestión siguiente no debería tener movimientos confirmados antes de apertura.',
            resultado='Sin movimientos destino',
            detalle=f'No se detectaron movimientos confirmados en la gestión {filtros["gestion_destino"]}.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.asiento',
        )


def _check_backup_precierre(rows: list[dict[str, Any]], filtros: dict[str, Any], config: dict[str, Any] | None) -> None:
    if not config or not config.get('generar_backup_pre_cierre'):
        _append_row(
            rows,
            prioridad_codigo='BAJA',
            categoria='Backup pre-cierre',
            criterio='El respaldo pre-cierre depende de la configuración activa.',
            resultado='Backup no exigido',
            detalle='La configuración activa no exige respaldo pre-cierre automático.',
            accion='Puede generar un backup manual si el procedimiento interno lo requiere.',
            fuente='contabilidad.gestion_configuracion',
        )
        return

    cantidad = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.esquema_backup_catalogo
        WHERE gestion_origen = %s
          AND tipo_respaldo = 'PRE_CIERRE'
          AND estado::text IN ('GENERADO', 'VALIDADO')
        """,
        (filtros['gestion'],),
    )
    if cantidad:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Backup pre-cierre',
            criterio='Debe existir respaldo pre-cierre cuando la configuración lo exige.',
            resultado='Backup encontrado',
            detalle=f'Existe(n) {cantidad} respaldo(s) pre-cierre generado(s) para esta gestión.',
            accion='Verificar que el respaldo sea reciente antes de ejecutar el cierre.',
            fuente='contabilidad.esquema_backup_catalogo',
            cantidad=cantidad,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Backup pre-cierre',
            criterio='Debe existir respaldo pre-cierre cuando la configuración lo exige.',
            resultado='Sin backup pre-cierre',
            detalle='La configuración exige backup pre-cierre, pero no se encontró respaldo registrado.',
            accion='Generar backup antes de ejecutar el cierre.',
            fuente='contabilidad.esquema_backup_catalogo',
        )


def _check_compromisos_y_arqueos(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    vencidos = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.compromiso_detalle cd
        JOIN contabilidad.compromiso c ON c.id = cd.compromiso_id
        WHERE c.activo = TRUE
          AND c.gestion = %s
          AND cd.estado IN ('PENDIENTE', 'PARCIAL', 'INCUMPLIDO')
          AND cd.fecha_vencimiento <= %s
          AND GREATEST(COALESCE(cd.monto_programado, 0) - COALESCE(cd.monto_registrado, 0), 0) > 0
        """,
        (filtros['gestion'], filtros['fecha_hasta']),
    )
    if vencidos:
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Compromisos',
            criterio='Conviene revisar compromisos vencidos o pendientes antes del cierre.',
            resultado='Compromisos pendientes',
            detalle=f'Existen {vencidos} cuota(s) de compromiso pendiente(s) hasta el cierre de gestión.',
            accion='Revisar pagos/cobros pendientes o dejar documentado que quedan para seguimiento.',
            fuente='contabilidad.compromiso / contabilidad.compromiso_detalle',
            cantidad=vencidos,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Compromisos',
            criterio='Conviene revisar compromisos vencidos o pendientes antes del cierre.',
            resultado='Sin compromisos vencidos pendientes',
            detalle='No se detectaron compromisos vencidos pendientes hasta la fecha de cierre.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.compromiso / contabilidad.compromiso_detalle',
        )

    arqueos = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.arqueo_caja
        WHERE fecha_arqueo BETWEEN %s AND %s
          AND estado::text = 'CONFIRMADO'
          AND ABS(COALESCE(diferencia, 0)) > 0.01
        """,
        (filtros['fecha_desde'], filtros['fecha_hasta']),
    )
    if arqueos:
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Caja',
            criterio='Los arqueos confirmados con diferencia deben estar justificados.',
            resultado='Arqueos con diferencia',
            detalle=f'Existen {arqueos} arqueo(s) confirmado(s) con diferencia.',
            accion='Revisar observaciones o registrar ajustes si corresponde.',
            fuente='contabilidad.arqueo_caja',
            cantidad=arqueos,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Caja',
            criterio='Los arqueos confirmados con diferencia deben estar justificados.',
            resultado='Sin diferencias de arqueo',
            detalle='No se detectaron arqueos confirmados con diferencia en la gestión.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.arqueo_caja',
        )


def _check_documentos_cobrar(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    params = (filtros['fecha_desde'], filtros['fecha_hasta'])
    saldo_inconsistente = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.documento_por_cobrar d
        WHERE d.fecha_documento BETWEEN %s AND %s
          AND COALESCE(d.activo, TRUE) = TRUE
          AND COALESCE(d.estado, '') <> 'ANULADO'
          AND ABS(COALESCE(d.saldo_pendiente, 0) - GREATEST(COALESCE(d.importe_total, 0) - COALESCE(d.importe_cobrado, 0), 0)) > 0.01
        """,
        params,
    )
    vigente_sin_asiento = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.documento_por_cobrar d
        WHERE d.fecha_documento BETWEEN %s AND %s
          AND COALESCE(d.activo, TRUE) = TRUE
          AND COALESCE(d.estado, '') <> 'ANULADO'
          AND COALESCE(d.tratamiento_contable, '') <> 'CARTERA_HISTORICA'
          AND d.factura_electronica_id IS NULL
          AND d.asiento_registro_id IS NULL
        """,
        params,
    )
    historico_con_asiento = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.documento_por_cobrar d
        WHERE d.fecha_documento BETWEEN %s AND %s
          AND COALESCE(d.activo, TRUE) = TRUE
          AND COALESCE(d.estado, '') <> 'ANULADO'
          AND COALESCE(d.tratamiento_contable, '') = 'CARTERA_HISTORICA'
          AND d.asiento_registro_id IS NOT NULL
        """,
        params,
    )
    pendientes = _count(
        """
        SELECT COUNT(*) AS cantidad
        FROM contabilidad.documento_por_cobrar d
        WHERE d.fecha_documento <= %s
          AND COALESCE(d.activo, TRUE) = TRUE
          AND COALESCE(d.estado, '') NOT IN ('ANULADO', 'COBRADO')
          AND COALESCE(d.saldo_pendiente, 0) > 0.01
        """,
        (filtros['fecha_hasta'],),
    )

    bloqueantes = saldo_inconsistente + vigente_sin_asiento
    observados = historico_con_asiento
    if bloqueantes:
        partes = []
        if saldo_inconsistente:
            partes.append(f'{saldo_inconsistente} con saldo inconsistente')
        if vigente_sin_asiento:
            partes.append(f'{vigente_sin_asiento} vigente(s) sin asiento')
        _append_row(
            rows,
            prioridad_codigo='CRITICA',
            categoria='Documentos por cobrar',
            criterio='La cartera debe cerrar con saldos consistentes y documentos vigentes contabilizados.',
            resultado='Documentos CxC bloqueantes',
            detalle='; '.join(partes) + '.',
            accion='Corregir documentos por cobrar antes de cerrar la gestión.',
            fuente='contabilidad.documento_por_cobrar',
            cantidad=bloqueantes,
        )
    elif observados:
        _append_row(
            rows,
            prioridad_codigo='MEDIA',
            categoria='Documentos por cobrar',
            criterio='Los documentos históricos no deben generar asiento al registro.',
            resultado='Históricos observados',
            detalle=f'Existen {historico_con_asiento} documento(s) histórico(s) con asiento de registro asociado.',
            accion='Revisar si corresponde anular/reclasificar el asiento de registro.',
            fuente='contabilidad.documento_por_cobrar',
            cantidad=observados,
        )
    else:
        _append_row(
            rows,
            prioridad_codigo='OK',
            categoria='Documentos por cobrar',
            criterio='La cartera documental debe respetar el tratamiento histórico/vigente.',
            resultado='Cartera documental consistente',
            detalle='No se detectaron inconsistencias bloqueantes en documentos por cobrar.',
            accion='Continuar con la revisión previa.',
            fuente='contabilidad.documento_por_cobrar',
        )

    if pendientes:
        _append_row(
            rows,
            prioridad_codigo='BAJA',
            categoria='Documentos por cobrar',
            criterio='Los saldos pendientes de cartera deben quedar identificados para seguimiento.',
            resultado='Cartera pendiente informativa',
            detalle=f'Quedan {pendientes} documento(s) por cobrar con saldo pendiente al corte.',
            accion='Verificar que el saldo pendiente corresponda y continúe su seguimiento desde Tesorería → Cobros.',
            fuente='contabilidad.documento_por_cobrar',
            cantidad=pendientes,
        )


def _check_resultado_ejercicio(rows: list[dict[str, Any]], filtros: dict[str, Any]) -> None:
    row = _db_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN c.tipo::text = 'INGRESO' THEN ad.haber - ad.debe ELSE 0 END), 0)::numeric(18,2) AS ingresos,
            COALESCE(SUM(CASE WHEN c.tipo::text = 'COSTO' THEN ad.debe - ad.haber ELSE 0 END), 0)::numeric(18,2) AS costos,
            COALESCE(SUM(CASE WHEN c.tipo::text = 'GASTO' THEN ad.debe - ad.haber ELSE 0 END), 0)::numeric(18,2) AS gastos
        FROM contabilidad.asiento a
        JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        WHERE a.fecha BETWEEN %s AND %s
          AND a.estado::text = 'CONFIRMADO'
          AND COALESCE(a.modulo_origen, '') <> 'CIERRE_GESTION'
          AND c.tipo::text IN ('INGRESO', 'COSTO', 'GASTO')
        """,
        (filtros['fecha_desde'], filtros['fecha_hasta']),
    ) or {}
    ingresos = _decimal(row.get('ingresos'))
    costos = _decimal(row.get('costos'))
    gastos = _decimal(row.get('gastos'))
    resultado = ingresos - costos - gastos
    _append_row(
        rows,
        prioridad_codigo='BAJA',
        categoria='Resultado del ejercicio',
        criterio='El cierre cancelará ingresos, costos y gastos contra resultado del ejercicio.',
        resultado='Información de resultado',
        detalle=(
            f"Ingresos {format_money(ingresos, 'BOB')} / "
            f"Costos {format_money(costos, 'BOB')} / "
            f"Gastos {format_money(gastos, 'BOB')} / "
            f"Resultado neto {format_money(resultado, 'BOB')}"
        ),
        accion='Usar esta información como referencia antes de ejecutar el cierre.',
        fuente='contabilidad.asiento_detalle / contabilidad.cuenta',
        monto=resultado,
    )


# ============================================================
# Construcción de payload
# ============================================================


def _build_rows(filtros: dict[str, Any], limit_rows: int = MAX_ROWS_SCREEN) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    control = _check_estado_gestion(rows, filtros)
    config = _check_configuracion_cierre(rows)
    _check_cierre_existente(rows, filtros, control)
    _check_bloqueos(rows, filtros)
    _check_asientos_base(rows, filtros)
    _check_borradores(rows, filtros, config)
    _check_operaciones_sin_asiento(rows, filtros)
    _check_documentos_cobrar(rows, filtros)
    _check_cuentas_detalle(rows, filtros)
    _check_balance_comprobacion(rows, filtros)
    _check_movimientos_destino(rows, filtros, config)
    _check_backup_precierre(rows, filtros, config)
    _check_compromisos_y_arqueos(rows, filtros)
    _check_resultado_ejercicio(rows, filtros)
    rows.sort(key=lambda item: (item.get('prioridad_orden', 9), item.get('categoria', ''), item.get('nro', 0)))
    for idx, item in enumerate(rows, start=1):
        item['nro'] = idx
    return rows[:limit_rows]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        'cantidad': len(rows),
        'bloqueantes': 0,
        'observados': 0,
        'ok': 0,
        'informativos': 0,
        'estado_general': 'Listo para cierre',
        'moneda_display_note': 'Importes expresados sin símbolo de moneda.',
    }
    for row in rows:
        prioridad = row.get('prioridad_codigo')
        if prioridad == 'CRITICA':
            summary['bloqueantes'] += 1
        elif prioridad in {'ALTA', 'MEDIA'}:
            summary['observados'] += 1
        elif prioridad == 'OK':
            summary['ok'] += 1
        else:
            summary['informativos'] += 1

    if summary['bloqueantes']:
        summary['estado_general'] = 'No listo para cierre'
    elif summary['observados']:
        summary['estado_general'] = 'Requiere revisión'
    return summary


def _summary_cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {'label': 'Estado', 'value': summary.get('estado_general', ''), 'note': 'Resultado del checklist', 'kind': 'group'},
        {'label': 'Bloqueantes', 'value': summary.get('bloqueantes', 0), 'note': 'Corregir antes de cerrar', 'kind': 'critical'},
        {'label': 'Observados', 'value': summary.get('observados', 0), 'note': 'Revisión recomendada', 'kind': 'medium'},
        {'label': 'OK', 'value': summary.get('ok', 0), 'note': 'Validaciones conformes', 'kind': 'low'},
    ]


def _display_columns() -> list[dict[str, str]]:
    return [
        {'field': 'prioridad', 'label': 'Prioridad'},
        {'field': 'categoria', 'label': 'Categoría'},
        {'field': 'resultado', 'label': 'Resultado'},
        {'field': 'criterio', 'label': 'Criterio'},
        {'field': 'detalle', 'label': 'Detalle'},
        {'field': 'accion', 'label': 'Acción sugerida'},
    ]


def _build_payload(filtros: dict[str, Any], limit_rows: int = MAX_ROWS_SCREEN) -> dict[str, Any]:
    rows = _build_rows(filtros, limit_rows=limit_rows)
    summary = _summary(rows)
    return {
        'titulo': 'Checklist Pre-Cierre',
        'descripcion_periodo': filtros['periodo_label'],
        'unidad_label': filtros['unidad_label'],
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'gestion': filtros['gestion'],
        'gestion_destino': filtros['gestion_destino'],
        'fecha_desde': filtros['fecha_desde'],
        'fecha_hasta': filtros['fecha_hasta'],
        'rows': rows,
        'columns': _display_columns(),
        'summary': summary,
        'summary_cards': _summary_cards(summary),
        'fuente_datos': 'Tablas contables y operativas del esquema contabilidad.',
        'criterio_reporte': 'Validación previa al cierre global de gestión. No ejecuta cierre ni modifica datos.',
        'empty_title': 'No se generaron resultados para la gestión seleccionada',
        'empty_icon': 'fas fa-clipboard-check',
    }


class ChecklistPreCierreExport:
    TITLE = 'Checklist Pre-Cierre'
    WORKSHEET_TITLE = 'Checklist Pre Cierre'
    FILE_SLUG = 'checklist_pre_cierre'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'monto'}

    @staticmethod
    def excel_columns():
        return [
            ('prioridad', 'Prioridad', 16),
            ('estado', 'Estado', 18),
            ('categoria', 'Categoria', 24),
            ('resultado', 'Resultado', 28),
            ('criterio', 'Criterio evaluado', 52),
            ('detalle', 'Detalle', 62),
            ('accion', 'Accion sugerida', 54),
            ('fuente', 'Fuente', 44),
            ('cantidad', 'Cantidad', 12),
            ('monto', 'Monto ref.', 16),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Estado: {summary.get('estado_general', '')} · "
            f"Bloqueantes: {summary.get('bloqueantes', 0)} · "
            f"Observados: {summary.get('observados', 0)} · "
            f"OK: {summary.get('ok', 0)}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Prioridad', 'width': 20, 'align': 'center'},
            {'label': 'Categoría', 'width': 30, 'align': 'left'},
            {'label': 'Resultado', 'width': 35, 'align': 'left'},
            {'label': 'Criterio evaluado', 'width': 70, 'align': 'left'},
            {'label': 'Detalle', 'width': 70, 'align': 'left'},
            {'label': 'Acción sugerida', 'width': 54, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('prioridad', ''),
                item.get('categoria', ''),
                item.get('resultado', ''),
                item.get('criterio', ''),
                item.get('detalle', ''),
                item.get('accion', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['', 'Límite PDF', '', '', f'Se muestran {MAX_ROWS_PDF} filas. Use Excel para el detalle completo.', ''])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"{payload.get('descripcion_periodo', '')}. "
            f"Tipo: cierre global. "
            f"Estado: {summary.get('estado_general', '')}. "
            f"Bloqueantes: {summary.get('bloqueantes', 0)}. "
            f"Observados: {summary.get('observados', 0)}. "
            f"Validaciones OK: {summary.get('ok', 0)}."
        )


# ============================================================
# Rutas
# ============================================================


@checklist_precierre_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return render_template(
        'checklist_precierre_index.html',
        gestiones=_obtener_gestiones(),
        gestion_preferida=_gestion_preferida(),
    )


@checklist_precierre_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_checklist():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el checklist pre-cierre. {exc}', 500)


@checklist_precierre_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_checklist():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        excel_bytes = build_excel(ChecklistPreCierreExport, payload)
        nombre = f"checklist_pre_cierre_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el Excel del checklist pre-cierre. {exc}', 500)


@checklist_precierre_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_checklist():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(ChecklistPreCierreExport, payload)
        nombre = f"checklist_pre_cierre_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del checklist pre-cierre. {exc}', 500)


@checklist_precierre_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('checklist_precierre_help.html')
