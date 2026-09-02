# ============================================================
# DXT CONTA - Herramientas - Asistente de Ajustes Contables
# Preparacion controlada de comprobantes de ajuste en BORRADOR
# ============================================================

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import Response, jsonify, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

from database.db_manager import DatabaseManager
from modules.asistente_ajustes import asistente_ajustes_bp
from modules.reportes_rapidos.core.catalogos import obtener_unidades_negocio, unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import format_money
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]
MONEDA_BASE = 'BOB'
MODULO_MANUAL = 'CONTABILIDAD'
HERRAMIENTA_CODIGO = 'ASISTENTE_AJUSTES'

TIPOS_AJUSTE = [
    {'value': 'RECLASIFICACION', 'label': 'Reclasificacion de cuenta'},
    {'value': 'CORRECCION_MONTO', 'label': 'Correccion de monto'},
    {'value': 'DIFERENCIA_CAJA', 'label': 'Diferencia de caja'},
    {'value': 'REGULARIZACION_CLIENTE', 'label': 'Regularizacion de cliente'},
    {'value': 'REGULARIZACION_PROVEEDOR', 'label': 'Regularizacion de proveedor'},
    {'value': 'OTRO', 'label': 'Otro ajuste contable'},
]

ESTADOS = [
    {'value': 'TODOS', 'label': 'Todos'},
    {'value': 'BORRADOR', 'label': 'Borrador'},
    {'value': 'CONFIRMADO', 'label': 'Confirmado'},
    {'value': 'ANULADO', 'label': 'Anulado'},
]

TIPO_LABEL = {item['value']: item['label'] for item in TIPOS_AJUSTE}
ESTADO_LABEL = {item['value']: item['label'] for item in ESTADOS}


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
        return Decimal(str(value if value is not None else 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
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
        raise ValueError(f'El campo "{field_name}" no es valido.') from exc
    return parsed


def _parse_optional_int(value: Any, field_name: str) -> int | None:
    raw = _clean(value)
    if not raw:
        return None
    parsed = _parse_int(raw, field_name)
    return parsed if parsed > 0 else None


def _parse_date(value: Any, field_name: str) -> date:
    raw = _clean(value)
    if not raw:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha valida.') from exc


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


def _gestion_preferida() -> int:
    rows = _db_rows(
        """
        SELECT gestion
        FROM contabilidad.gestion_control
        WHERE estado::text = 'ABIERTA'
        ORDER BY gestion DESC
        LIMIT 1
        """
    )
    if rows:
        return int(rows[0]['gestion'])
    return date.today().year


def _obtener_gestiones() -> list[int]:
    rows = _db_rows(
        """
        SELECT DISTINCT gestion
        FROM contabilidad.gestion_control
        UNION
        SELECT DISTINCT EXTRACT(YEAR FROM fecha)::int AS gestion
        FROM contabilidad.asiento
        ORDER BY gestion DESC
        """
    )
    gestiones = [int(row['gestion']) for row in rows if row.get('gestion')]
    if not gestiones:
        gestiones = [date.today().year]
    return gestiones


def _obtener_cuentas_postables() -> list[dict[str, Any]]:
    rows = _db_rows(
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
        ORDER BY codigo ASC
        """
    )
    return [
        {
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'tipo': row['tipo'],
            'naturaleza': row['naturaleza'],
            'requiere_auxiliar': bool(row['requiere_auxiliar']),
            'requiere_cc': bool(row['requiere_cc']),
            'label': f"{row['codigo']} · {row['nombre']}",
        }
        for row in rows
    ]


def _obtener_auxiliares() -> list[dict[str, Any]]:
    rows = _db_rows(
        """
        SELECT id, COALESCE(nit_ci, '') AS nit_ci, nombre
        FROM contabilidad.auxiliar
        WHERE activo = TRUE
        ORDER BY nombre ASC, id ASC
        LIMIT 1000
        """
    )
    return [
        {
            'id': int(row['id']),
            'nombre': row['nombre'],
            'nit_ci': row['nit_ci'] or '',
            'label': f"{row['nit_ci']} · {row['nombre']}" if row['nit_ci'] else row['nombre'],
        }
        for row in rows
    ]


def _obtener_centros_costo() -> list[dict[str, Any]]:
    rows = _db_rows(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, nombre
        FROM contabilidad.centro_costo
        WHERE activo = TRUE
        ORDER BY codigo ASC, nombre ASC, id ASC
        LIMIT 1000
        """
    )
    return [
        {
            'id': int(row['id']),
            'codigo': row['codigo'] or '',
            'nombre': row['nombre'],
            'label': f"{row['codigo']} · {row['nombre']}" if row['codigo'] else row['nombre'],
        }
        for row in rows
    ]


def _usuario_actual() -> str:
    return (
        _clean(session.get('nombre_completo'))
        or _clean(session.get('usuario_nombre'))
        or _clean(session.get('username'))
        or _clean(session.get('usuario'))
        or _clean(session.get('email'))
        or f"USER-{session.get('user_id', 'NA')}"
    )


def _descripcion_periodo(fecha_desde: date, fecha_hasta: date) -> str:
    if fecha_desde == fecha_hasta:
        return f"Fecha: {_date_label(fecha_desde)}"
    return f"Periodo: {_date_label(fecha_desde)} al {_date_label(fecha_hasta)}"


# ============================================================
# Filtros y listados
# ============================================================


def _parse_filters(args) -> dict[str, Any]:
    gestion_default = _gestion_preferida()
    gestion = _parse_int(args.get('gestion') or gestion_default, 'Gestion')
    fecha_desde = _parse_date(args.get('fecha_desde') or f'{gestion}-01-01', 'Fecha desde')
    fecha_hasta = _parse_date(args.get('fecha_hasta') or f'{gestion}-12-31', 'Fecha hasta')
    if fecha_hasta < fecha_desde:
        raise ValueError('La fecha hasta no puede ser menor que la fecha desde.')

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')
    estado = _clean(args.get('estado')).upper() or 'TODOS'
    if estado not in ESTADO_LABEL:
        estado = 'TODOS'
    tipo_ajuste = _clean(args.get('tipo_ajuste')).upper() or 'TODOS'
    if tipo_ajuste != 'TODOS' and tipo_ajuste not in TIPO_LABEL:
        tipo_ajuste = 'TODOS'

    return {
        'gestion': gestion,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'unidad_negocio_id': unidad_negocio_id,
        'estado': estado,
        'tipo_ajuste': tipo_ajuste,
    }


def _fetch_ajustes(filtros: dict[str, Any], limit_rows: int | None = None) -> list[dict[str, Any]]:
    where = [
        "a.fecha BETWEEN %s AND %s",
        "a.atributos->>'herramienta' = %s",
    ]
    params: list[Any] = [filtros['fecha_desde'], filtros['fecha_hasta'], HERRAMIENTA_CODIGO]

    if filtros.get('unidad_negocio_id'):
        where.append('a.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    if filtros.get('estado') and filtros['estado'] != 'TODOS':
        where.append('a.estado::text = %s')
        params.append(filtros['estado'])
    if filtros.get('tipo_ajuste') and filtros['tipo_ajuste'] != 'TODOS':
        where.append("COALESCE(a.atributos->>'tipo_ajuste', 'OTRO') = %s")
        params.append(filtros['tipo_ajuste'])

    limit_sql = ''
    if limit_rows:
        limit_sql = 'LIMIT %s'
        params.append(limit_rows)

    rows = _db_rows(
        f"""
        WITH detalle AS (
            SELECT
                asiento_id,
                COUNT(*) AS total_lineas,
                SUM(COALESCE(debe, 0)) AS total_debe,
                SUM(COALESCE(haber, 0)) AS total_haber
            FROM contabilidad.asiento_detalle
            GROUP BY asiento_id
        )
        SELECT
            a.id,
            a.fecha,
            a.estado::text AS estado,
            COALESCE(a.referencia, '') AS referencia,
            COALESCE(a.glosa, '') AS glosa,
            COALESCE(a.atributos->>'tipo_ajuste', 'OTRO') AS tipo_ajuste,
            COALESCE(a.atributos->>'registrado_por', '') AS registrado_por,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            COALESCE(d.total_lineas, 0) AS total_lineas,
            COALESCE(d.total_debe, 0) AS total_debe,
            COALESCE(d.total_haber, 0) AS total_haber,
            a.creado_en,
            a.actualizado_en
        FROM contabilidad.asiento a
        LEFT JOIN detalle d ON d.asiento_id = a.id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE {' AND '.join(where)}
        ORDER BY a.fecha DESC, a.id DESC
        {limit_sql}
        """,
        tuple(params),
    )

    results = []
    for row in rows:
        total_debe = _decimal(row.get('total_debe'))
        total_haber = _decimal(row.get('total_haber'))
        diferencia = abs(total_debe - total_haber)
        tipo = row.get('tipo_ajuste') or 'OTRO'
        estado = row.get('estado') or ''
        results.append({
            'id': int(row['id']),
            'fecha': _date_label(row.get('fecha')),
            'fecha_iso': row.get('fecha').isoformat() if row.get('fecha') else '',
            'estado': ESTADO_LABEL.get(estado, estado.title()),
            'estado_codigo': estado,
            'tipo_ajuste': TIPO_LABEL.get(tipo, TIPO_LABEL['OTRO']),
            'tipo_ajuste_codigo': tipo,
            'referencia': row.get('referencia') or f"Asiento #{row['id']}",
            'glosa': row.get('glosa') or '',
            'unidad': f"{row['unidad_codigo']} · {row['unidad_nombre']}" if row.get('unidad_codigo') else (row.get('unidad_nombre') or ''),
            'total_debe': total_debe,
            'total_haber': total_haber,
            'total_debe_label': format_money(total_debe),
            'total_haber_label': format_money(total_haber),
            'diferencia': diferencia,
            'diferencia_label': format_money(diferencia),
            'total_lineas': int(row.get('total_lineas') or 0),
            'registrado_por': row.get('registrado_por') or '',
            'creado_en': _date_label(row.get('creado_en')),
            'actualizado_en': _date_label(row.get('actualizado_en')),
            'url_editar': url_for('comprobantes.editar', asiento_id=int(row['id'])),
            'url_ver': url_for('comprobantes.ver', asiento_id=int(row['id'])),
        })
    return results


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    borradores = sum(1 for row in rows if row.get('estado_codigo') == 'BORRADOR')
    confirmados = sum(1 for row in rows if row.get('estado_codigo') == 'CONFIRMADO')
    anulados = sum(1 for row in rows if row.get('estado_codigo') == 'ANULADO')
    total_debe = sum((_decimal(row.get('total_debe')) for row in rows), Decimal('0.00'))
    total_haber = sum((_decimal(row.get('total_haber')) for row in rows), Decimal('0.00'))
    return {
        'total': len(rows),
        'borradores': borradores,
        'confirmados': confirmados,
        'anulados': anulados,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'total_debe_label': format_money(total_debe),
        'total_haber_label': format_money(total_haber),
        'moneda_display_note': 'Importes expresados en BOB',
    }


def _build_payload(filtros: dict[str, Any], limit_rows: int | None = None) -> dict[str, Any]:
    rows = _fetch_ajustes(filtros, limit_rows=limit_rows)
    tipo_label = 'Todos los tipos' if filtros['tipo_ajuste'] == 'TODOS' else TIPO_LABEL.get(filtros['tipo_ajuste'], 'Tipo seleccionado')
    estado_label = ESTADO_LABEL.get(filtros['estado'], 'Todos')
    return {
        'titulo': 'Asistente de Ajustes Contables',
        'descripcion_periodo': _descripcion_periodo(filtros['fecha_desde'], filtros['fecha_hasta']),
        'gestion': filtros['gestion'],
        'fecha_desde': filtros['fecha_desde'],
        'fecha_hasta': filtros['fecha_hasta'],
        'unidad_label': unidad_label(filtros.get('unidad_negocio_id')),
        'tipo_label': tipo_label,
        'estado_label': estado_label,
        'criterio_reporte': f"Tipo: {tipo_label}. Estado: {estado_label}.",
        'fuente_datos': 'contabilidad.asiento / contabilidad.asiento_detalle',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'rows': rows,
        'summary': _build_summary(rows),
    }


# ============================================================
# Validacion y creacion del borrador
# ============================================================


def _obtener_estado_gestion(gestion: int) -> str | None:
    rows = _db_rows(
        """
        SELECT estado::text AS estado
        FROM contabilidad.gestion_control
        WHERE gestion = %s
        LIMIT 1
        """,
        (gestion,),
    )
    return rows[0]['estado'] if rows else None


def _validar_unidad(unidad_negocio_id: int) -> dict[str, Any]:
    rows = _db_rows(
        """
        SELECT id, codigo, nombre
        FROM contabilidad.unidad_negocio
        WHERE id = %s AND activo = TRUE
        LIMIT 1
        """,
        (unidad_negocio_id,),
    )
    if not rows:
        raise ValueError('La unidad de negocio seleccionada no existe o esta inactiva.')
    return rows[0]


def _validar_catalogo_simple(table: str, item_id: int, label: str) -> None:
    rows = _db_rows(
        f"SELECT id FROM contabilidad.{table} WHERE id = %s AND activo = TRUE LIMIT 1",
        (item_id,),
    )
    if not rows:
        raise ValueError(f'El {label} seleccionado no existe o esta inactivo.')


def _validar_borrador(data: dict[str, Any]) -> dict[str, Any]:
    fecha = _parse_date(data.get('fecha'), 'Fecha')
    gestion = fecha.year
    estado_gestion = _obtener_estado_gestion(gestion)
    if estado_gestion != 'ABIERTA':
        raise ValueError('Solo se pueden preparar ajustes en una gestion abierta.')

    unidad_negocio_id = _parse_int(data.get('unidad_negocio_id'), 'Unidad de negocio')
    unidad = _validar_unidad(unidad_negocio_id)

    tipo_ajuste = _clean(data.get('tipo_ajuste')).upper()
    if tipo_ajuste not in TIPO_LABEL:
        raise ValueError('Debe seleccionar un tipo de ajuste valido.')

    glosa = _clean(data.get('glosa'))
    if len(glosa) < 8:
        raise ValueError('La glosa debe tener al menos 8 caracteres.')

    referencia = _clean(data.get('referencia'))
    if not referencia:
        referencia = f"AJUSTE {tipo_ajuste} {fecha.strftime('%Y%m%d')}"

    detalles_raw = data.get('detalles') or []
    if not isinstance(detalles_raw, list) or len(detalles_raw) < 2:
        raise ValueError('Debe registrar al menos dos lineas de detalle.')

    codigos = [_clean(item.get('cuenta_codigo')) for item in detalles_raw if _clean(item.get('cuenta_codigo'))]
    if not codigos:
        raise ValueError('Debe indicar cuentas contables en el detalle.')

    cuentas_rows = _db_rows(
        """
        SELECT codigo, nombre, activo, es_postable, requiere_auxiliar, requiere_cc
        FROM contabilidad.cuenta
        WHERE codigo = ANY(%s)
        """,
        (codigos,),
    )
    cuentas = {row['codigo']: row for row in cuentas_rows}

    detalles = []
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')

    for idx, item in enumerate(detalles_raw, start=1):
        cuenta_codigo = _clean(item.get('cuenta_codigo'))
        if not cuenta_codigo:
            raise ValueError(f'La linea {idx} no tiene cuenta contable.')
        cuenta = cuentas.get(cuenta_codigo)
        if not cuenta:
            raise ValueError(f'La cuenta {cuenta_codigo} no existe.')
        if not bool(cuenta.get('activo')):
            raise ValueError(f'La cuenta {cuenta_codigo} esta inactiva.')
        if not bool(cuenta.get('es_postable')):
            raise ValueError(f'La cuenta {cuenta_codigo} no es postable.')

        debe = _decimal(item.get('debe'))
        haber = _decimal(item.get('haber'))
        if debe < 0 or haber < 0:
            raise ValueError(f'La linea {idx} no puede tener importes negativos.')
        if (debe > 0 and haber > 0) or (debe == 0 and haber == 0):
            raise ValueError(f'La linea {idx} debe tener importe solo en Debe o solo en Haber.')

        auxiliar_id = _parse_optional_int(item.get('auxiliar_id'), 'Auxiliar')
        centro_costo_id = _parse_optional_int(item.get('centro_costo_id'), 'Centro de costo')
        if bool(cuenta.get('requiere_auxiliar')) and not auxiliar_id:
            raise ValueError(f'La cuenta {cuenta_codigo} requiere auxiliar.')
        if bool(cuenta.get('requiere_cc')) and not centro_costo_id:
            raise ValueError(f'La cuenta {cuenta_codigo} requiere centro de costo.')
        if auxiliar_id:
            _validar_catalogo_simple('auxiliar', auxiliar_id, 'auxiliar')
        if centro_costo_id:
            _validar_catalogo_simple('centro_costo', centro_costo_id, 'centro de costo')

        detalle_glosa = _clean(item.get('glosa')) or glosa
        total_debe += debe
        total_haber += haber
        detalles.append({
            'secuencia': len(detalles) + 1,
            'cuenta_codigo': cuenta_codigo,
            'cuenta_nombre': cuenta.get('nombre'),
            'auxiliar_id': auxiliar_id,
            'centro_costo_id': centro_costo_id,
            'glosa': detalle_glosa[:300],
            'debe': debe,
            'haber': haber,
            'monto_moneda': debe if debe > 0 else haber,
            'referencia': referencia[:150],
        })

    if total_debe != total_haber:
        raise ValueError(f'El ajuste no cuadra. Debe: {format_money(total_debe)} / Haber: {format_money(total_haber)}.')

    return {
        'fecha': fecha,
        'gestion': gestion,
        'unidad': unidad,
        'unidad_negocio_id': unidad_negocio_id,
        'tipo_ajuste': tipo_ajuste,
        'glosa': glosa[:500],
        'referencia': referencia[:150],
        'detalles': detalles,
        'total_debe': total_debe,
        'total_haber': total_haber,
    }


def _crear_borrador_ajuste(payload: dict[str, Any]) -> int:
    usuario = _usuario_actual()
    atributos = {
        'origen': 'herramienta_asistente_ajustes',
        'herramienta': HERRAMIENTA_CODIGO,
        'tipo_comprobante': 'AJUSTE',
        'tipo_ajuste': payload['tipo_ajuste'],
        'tipo_ajuste_label': TIPO_LABEL.get(payload['tipo_ajuste'], 'Ajuste contable'),
        'registrado_por': usuario,
        'unidad_negocio_codigo': payload['unidad'].get('codigo') or '',
        'unidad_negocio_nombre': payload['unidad'].get('nombre') or '',
        'creado_desde': 'Herramientas > Asistente de Ajustes',
    }

    with DatabaseManager() as db:
        cursor = db.conn.cursor(cursor_factory=RealDictCursor)
        db.cursor = cursor
        cursor.execute(
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
                creado_en,
                actualizado_en,
                unidad_negocio_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, 'BORRADOR', %s::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)
            RETURNING id
            """,
            (
                payload['fecha'],
                MONEDA_BASE,
                Decimal('1.000000'),
                payload['glosa'],
                payload['referencia'],
                MODULO_MANUAL,
                json.dumps(atributos, ensure_ascii=False),
                payload['unidad_negocio_id'],
            ),
        )
        asiento_id = int(cursor.fetchone()['id'])

        for detalle in payload['detalles']:
            detalle_atributos = {
                'origen': 'herramienta_asistente_ajustes',
                'tipo_ajuste': payload['tipo_ajuste'],
                'cuenta_nombre': detalle.get('cuenta_nombre') or '',
            }
            cursor.execute(
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    asiento_id,
                    detalle['secuencia'],
                    detalle['cuenta_codigo'],
                    detalle['auxiliar_id'],
                    detalle['centro_costo_id'],
                    detalle['glosa'],
                    detalle['debe'],
                    detalle['haber'],
                    detalle['monto_moneda'],
                    detalle['referencia'],
                    json.dumps(detalle_atributos, ensure_ascii=False),
                ),
            )
    return asiento_id


# ============================================================
# Exportacion
# ============================================================


class AsistenteAjustesExport:
    TITLE = 'Asistente de Ajustes Contables'
    WORKSHEET_TITLE = 'Ajustes'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'total_debe', 'total_haber', 'diferencia'}

    @staticmethod
    def excel_columns():
        return [
            ('fecha', 'Fecha', 14),
            ('id', 'Comprobante', 14),
            ('estado', 'Estado', 15),
            ('tipo_ajuste', 'Tipo de ajuste', 28),
            ('referencia', 'Referencia', 28),
            ('unidad', 'Unidad de negocio', 32),
            ('total_lineas', 'Lineas', 10),
            ('total_debe', 'Total Debe', 16),
            ('total_haber', 'Total Haber', 16),
            ('diferencia', 'Diferencia', 16),
            ('glosa', 'Glosa', 60),
            ('registrado_por', 'Preparado por', 28),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Total: {summary.get('total', 0)} · "
            f"Borradores: {summary.get('borradores', 0)} · "
            f"Confirmados: {summary.get('confirmados', 0)} · "
            f"Anulados: {summary.get('anulados', 0)} · "
            f"Debe: {summary.get('total_debe_label', '0.00')} · "
            f"Haber: {summary.get('total_haber_label', '0.00')}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Fecha', 'width': 18, 'align': 'center'},
            {'label': 'Comp.', 'width': 16, 'align': 'center'},
            {'label': 'Estado', 'width': 20, 'align': 'center'},
            {'label': 'Tipo de ajuste', 'width': 34, 'align': 'left'},
            {'label': 'Referencia', 'width': 36, 'align': 'left'},
            {'label': 'Unidad', 'width': 38, 'align': 'left'},
            {'label': 'Debe', 'width': 23, 'align': 'right'},
            {'label': 'Haber', 'width': 23, 'align': 'right'},
            {'label': 'Glosa', 'width': 70, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('fecha', ''),
                str(item.get('id', '')),
                item.get('estado', ''),
                item.get('tipo_ajuste', ''),
                item.get('referencia', ''),
                item.get('unidad', ''),
                item.get('total_debe_label', ''),
                item.get('total_haber_label', ''),
                item.get('glosa', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['', '', '', 'Limite PDF', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} filas. Use Excel para el detalle completo.'])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"{payload.get('descripcion_periodo', '')}. "
            f"Unidad: {payload.get('unidad_label', '')}. "
            f"Tipo: {payload.get('tipo_label', '')}. "
            f"Estado: {payload.get('estado_label', '')}. "
            f"Borradores: {summary.get('borradores', 0)}. "
            f"Confirmados: {summary.get('confirmados', 0)}. "
            f"Total: {summary.get('total', 0)}."
        )


# ============================================================
# Rutas
# ============================================================


@asistente_ajustes_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    gestion = _gestion_preferida()
    bootstrap = {
        'cuentas': _obtener_cuentas_postables(),
        'auxiliares': _obtener_auxiliares(),
        'centros_costo': _obtener_centros_costo(),
        'tipos_ajuste': TIPOS_AJUSTE,
        'estados': ESTADOS,
    }
    return render_template(
        'asistente_ajustes_index.html',
        gestiones=_obtener_gestiones(),
        gestion_preferida=gestion,
        fecha_desde=f'{gestion}-01-01',
        fecha_hasta=f'{gestion}-12-31',
        fecha_hoy=date.today().isoformat(),
        unidades_negocio=obtener_unidades_negocio(),
        tipos_ajuste=TIPOS_AJUSTE,
        estados=ESTADOS,
        bootstrap=bootstrap,
    )


@asistente_ajustes_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_ajustes():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar la revision de ajustes. {exc}', 500)


@asistente_ajustes_bp.route('/crear-borrador', methods=['POST'])
@login_required
@roles_required(ROLES_LECTURA)
def crear_borrador():
    try:
        data = request.get_json() or {}
        payload = _validar_borrador(data)
        asiento_id = _crear_borrador_ajuste(payload)
        return _json_ok(
            msg=f'Comprobante de ajuste #{asiento_id} creado en BORRADOR.',
            asiento_id=asiento_id,
            url_editar=url_for('comprobantes.editar', asiento_id=asiento_id),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo crear el borrador de ajuste. {exc}', 500)


@asistente_ajustes_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_ajustes():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        excel_bytes = build_excel(AsistenteAjustesExport, payload)
        nombre = f"asistente_ajustes_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el Excel de ajustes. {exc}', 500)


@asistente_ajustes_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_ajustes():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(AsistenteAjustesExport, payload)
        nombre = f"asistente_ajustes_{filtros['gestion']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF de ajustes. {exc}', 500)


@asistente_ajustes_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('asistente_ajustes_help.html')
