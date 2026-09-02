# ============================================================
# DXT CONTA - Herramientas - Bitacora de Procesos Especiales
# Consulta de auditoria sobre procesos criticos, backups y restauraciones
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from flask import Response, jsonify, render_template, request

from database.db_manager import DatabaseManager
from modules.bitacora_procesos import bitacora_procesos_bp
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]

FUENTES = [
    {'value': 'TODAS', 'label': 'Todas'},
    {'value': 'BITACORA_GESTION', 'label': 'Bitacora gestion'},
    {'value': 'BLOQUEO_CRITICO', 'label': 'Bloqueos criticos'},
    {'value': 'BACKUP', 'label': 'Backups'},
    {'value': 'RESTAURACION', 'label': 'Restauraciones'},
]

TIPOS_PROCESO = [
    {'value': 'TODAS', 'label': 'Todos'},
    {'value': 'VALIDACION_CIERRE', 'label': 'Validacion cierre'},
    {'value': 'CIERRE', 'label': 'Cierre'},
    {'value': 'VALIDACION_APERTURA', 'label': 'Validacion apertura'},
    {'value': 'APERTURA', 'label': 'Apertura'},
    {'value': 'REAPERTURA', 'label': 'Reapertura'},
    {'value': 'BACKUP_PRE_CIERRE', 'label': 'Backup pre-cierre'},
    {'value': 'RESTAURACION_BACKUP', 'label': 'Restauracion backup'},
    {'value': 'LIBERACION_BLOQUEO', 'label': 'Liberacion bloqueo'},
    {'value': 'RESTAURACION', 'label': 'Restauracion'},
    {'value': 'PRE_CIERRE', 'label': 'Pre-cierre'},
]

ESTADOS = [
    {'value': 'TODOS', 'label': 'Todos'},
    {'value': 'PENDIENTE', 'label': 'Pendiente'},
    {'value': 'EN_PROCESO', 'label': 'En proceso'},
    {'value': 'EJECUTADO', 'label': 'Ejecutado'},
    {'value': 'ANULADO', 'label': 'Anulado'},
    {'value': 'FALLIDO', 'label': 'Fallido'},
    {'value': 'BLOQUEADO', 'label': 'Bloqueado'},
    {'value': 'FINALIZADO', 'label': 'Finalizado'},
    {'value': 'GENERADO', 'label': 'Generado'},
    {'value': 'EJECUTADA', 'label': 'Ejecutada'},
    {'value': 'FALLIDA', 'label': 'Fallida'},
    {'value': 'PARCIAL', 'label': 'Parcial'},
]

FUENTE_LABELS = {item['value']: item['label'] for item in FUENTES}
TIPO_LABELS = {item['value']: item['label'] for item in TIPOS_PROCESO}
ESTADO_LABELS = {item['value']: item['label'] for item in ESTADOS}


def _json_ok(**kwargs):
    payload = {'ok': True}
    payload.update(kwargs)
    return jsonify(_json_ready(payload))


def _json_error(message: str, status: int = 400):
    return jsonify({'ok': False, 'msg': message}), status


def _clean(value: Any) -> str:
    return (value or '').strip()


def _upper_clean(value: Any) -> str:
    return _clean(value).upper()


def _gestion_actual() -> int:
    return date.today().year


def _parse_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es valido.') from exc
    if parsed < 1900 or parsed > 2200:
        raise ValueError(f'El campo "{field_name}" no corresponde a una gestion valida.')
    return parsed


def _parse_date(value: Any, field_name: str, default: date | None = None) -> date:
    value = _clean(value)
    if not value:
        if default is not None:
            return default
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(value[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha valida.') from exc


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


def _date_label(value: Any, with_time: bool = True) -> str:
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M') if with_time else value.strftime('%d/%m/%Y')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    raw = str(value)
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        return parsed.strftime('%d/%m/%Y %H:%M') if with_time else parsed.strftime('%d/%m/%Y')
    except Exception:
        return raw


def _short_text(value: Any, max_len: int = 180) -> str:
    text = ' '.join(str(value or '').split())
    if len(text) <= max_len:
        return text
    return f'{text[:max_len - 3]}...'


def _format_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return ''
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size = size / 1024
        unit_index += 1
    return f'{size:.2f} {units[unit_index]}'


def _duration_label(value: Any) -> str:
    try:
        minutes = float(value or 0)
    except (TypeError, ValueError):
        return ''
    if minutes <= 0:
        return ''
    if minutes < 1:
        return '< 1 min'
    if minutes < 60:
        return f'{minutes:.1f} min'
    hours = minutes / 60
    return f'{hours:.1f} h'


def _priority_for_estado(estado: str) -> str:
    estado = _upper_clean(estado)
    if estado in {'FALLIDO', 'FALLIDA'}:
        return 'CRITICA'
    if estado in {'BLOQUEADO', 'EN_PROCESO'}:
        return 'ALTA'
    if estado in {'PENDIENTE', 'ANULADO', 'PARCIAL'}:
        return 'MEDIA'
    return 'BAJA'


def _priority_label(priority: str) -> str:
    return {
        'CRITICA': 'Critica',
        'ALTA': 'Alta',
        'MEDIA': 'Media',
        'BAJA': 'Baja',
    }.get(priority, priority or '')


def _documento_label(row: dict[str, Any]) -> str:
    parts = []
    if row.get('comprobante_id'):
        parts.append(f"Comp. {row.get('comprobante_id')}")
    if row.get('backup_id'):
        parts.append(f"Backup {row.get('backup_id')}")
    if row.get('restauracion_id'):
        parts.append(f"Rest. {row.get('restauracion_id')}")
    archivo = _clean(row.get('archivo'))
    if archivo:
        parts.append(_short_text(archivo, 70))
    size = _format_bytes(row.get('tamanio_bytes'))
    if size:
        parts.append(size)
    return ' · '.join(parts)


def _gestion_texto(row: dict[str, Any]) -> str:
    origen = row.get('gestion_origen') or ''
    destino = row.get('gestion_destino') or ''
    if origen and destino:
        return f'{origen} -> {destino}'
    return str(origen or destino or '')


def _enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    estado = _upper_clean(row.get('estado'))
    tipo = _upper_clean(row.get('tipo_proceso'))
    fuente = _upper_clean(row.get('fuente_codigo'))
    prioridad = _priority_for_estado(estado)

    observacion = row.get('observacion') or ''
    if not observacion and row.get('detalle_json'):
        observacion = row.get('detalle_json')

    return {
        'codigo_evento': row.get('codigo_evento') or '',
        'fecha': row.get('fecha'),
        'fecha_display': _date_label(row.get('fecha')),
        'fecha_fin_display': _date_label(row.get('fecha_hora_fin')),
        'fuente_codigo': fuente,
        'fuente_label': FUENTE_LABELS.get(fuente, row.get('fuente_label') or fuente),
        'tipo_proceso': tipo,
        'tipo_label': TIPO_LABELS.get(tipo, tipo.replace('_', ' ').title()),
        'estado_codigo': estado,
        'estado_label': ESTADO_LABELS.get(estado, estado.replace('_', ' ').title()),
        'prioridad_codigo': prioridad,
        'prioridad_label': _priority_label(prioridad),
        'gestion_origen': row.get('gestion_origen'),
        'gestion_destino': row.get('gestion_destino'),
        'gestion_texto': _gestion_texto(row),
        'usuario_nombre': row.get('usuario_nombre') or 'Sistema',
        'documento': _documento_label(row),
        'duracion_minutos': row.get('duracion_minutos'),
        'duracion_display': _duration_label(row.get('duracion_minutos')),
        'observacion': _short_text(observacion, 500),
        'observacion_corta': _short_text(observacion, 160),
    }


def _obtener_gestiones() -> list[int]:
    sql = """
        SELECT DISTINCT gestion
        FROM (
            SELECT gestion FROM contabilidad.gestion_control
            UNION ALL
            SELECT gestion_origen AS gestion FROM contabilidad.gestion_proceso_bitacora
            UNION ALL
            SELECT gestion_destino AS gestion FROM contabilidad.gestion_proceso_bitacora WHERE gestion_destino IS NOT NULL
            UNION ALL
            SELECT gestion_origen AS gestion FROM contabilidad.gestion_bloqueo_critico
            UNION ALL
            SELECT gestion_destino AS gestion FROM contabilidad.gestion_bloqueo_critico WHERE gestion_destino IS NOT NULL
            UNION ALL
            SELECT gestion_origen AS gestion FROM contabilidad.esquema_backup_catalogo
            UNION ALL
            SELECT gestion_destino AS gestion FROM contabilidad.esquema_backup_catalogo WHERE gestion_destino IS NOT NULL
            UNION ALL
            SELECT gestion_origen AS gestion FROM contabilidad.esquema_restauracion_log
            UNION ALL
            SELECT gestion_destino AS gestion FROM contabilidad.esquema_restauracion_log WHERE gestion_destino IS NOT NULL
        ) data
        WHERE gestion IS NOT NULL
        ORDER BY gestion DESC
    """
    try:
        with DatabaseManager() as db:
            rows = db.execute_query(sql)
    except Exception:
        rows = []
    gestiones = [int(row['gestion']) for row in rows if row.get('gestion')]
    return gestiones or [_gestion_actual()]


def _fetch_rows(
    *,
    gestion: int,
    fecha_desde: date,
    fecha_hasta: date,
    fuente: str,
    tipo_proceso: str,
    estado: str,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    sql = """
        WITH eventos AS (
            SELECT
                'BITACORA_GESTION'::text AS fuente_codigo,
                'Bitacora gestion'::text AS fuente_label,
                ('GPB-' || b.id::text) AS codigo_evento,
                b.id::bigint AS evento_id,
                b.fecha_hora_inicio AS fecha,
                b.fecha_hora_fin AS fecha_hora_fin,
                b.tipo_proceso::text AS tipo_proceso,
                b.estado::text AS estado,
                b.gestion_origen,
                b.gestion_destino,
                b.usuario_nombre,
                b.comprobante_id::bigint AS comprobante_id,
                b.backup_id::bigint AS backup_id,
                b.restauracion_id::bigint AS restauracion_id,
                b.observacion,
                b.detalle_json::text AS detalle_json,
                NULL::text AS archivo,
                NULL::numeric AS tamanio_bytes
            FROM contabilidad.gestion_proceso_bitacora b
            WHERE (b.gestion_origen = %s OR b.gestion_destino = %s)
              AND b.fecha_hora_inicio::date BETWEEN %s AND %s

            UNION ALL

            SELECT
                'BLOQUEO_CRITICO'::text AS fuente_codigo,
                'Bloqueo critico'::text AS fuente_label,
                ('BLQ-' || bl.id::text) AS codigo_evento,
                bl.id::bigint AS evento_id,
                bl.fecha_hora_inicio AS fecha,
                bl.fecha_hora_fin AS fecha_hora_fin,
                bl.tipo_proceso::text AS tipo_proceso,
                bl.estado::text AS estado,
                bl.gestion_origen,
                bl.gestion_destino,
                bl.usuario_nombre,
                NULL::bigint AS comprobante_id,
                NULL::bigint AS backup_id,
                NULL::bigint AS restauracion_id,
                bl.motivo AS observacion,
                bl.token_proceso::text AS detalle_json,
                NULL::text AS archivo,
                NULL::numeric AS tamanio_bytes
            FROM contabilidad.gestion_bloqueo_critico bl
            WHERE (bl.gestion_origen = %s OR bl.gestion_destino = %s)
              AND bl.fecha_hora_inicio::date BETWEEN %s AND %s

            UNION ALL

            SELECT
                'BACKUP'::text AS fuente_codigo,
                'Backup'::text AS fuente_label,
                ('BKP-' || bk.id::text) AS codigo_evento,
                bk.id::bigint AS evento_id,
                bk.fecha_generacion AS fecha,
                NULL::timestamp AS fecha_hora_fin,
                bk.tipo_respaldo::text AS tipo_proceso,
                bk.estado::text AS estado,
                bk.gestion_origen,
                bk.gestion_destino,
                bk.usuario_nombre,
                NULL::bigint AS comprobante_id,
                bk.id::bigint AS backup_id,
                NULL::bigint AS restauracion_id,
                bk.observacion,
                bk.detalle_json::text AS detalle_json,
                bk.nombre_archivo AS archivo,
                bk.tamanio_bytes::numeric AS tamanio_bytes
            FROM contabilidad.esquema_backup_catalogo bk
            WHERE (bk.gestion_origen = %s OR bk.gestion_destino = %s)
              AND bk.fecha_generacion::date BETWEEN %s AND %s

            UNION ALL

            SELECT
                'RESTAURACION'::text AS fuente_codigo,
                'Restauracion'::text AS fuente_label,
                ('RST-' || r.id::text) AS codigo_evento,
                r.id::bigint AS evento_id,
                r.fecha_hora_inicio AS fecha,
                r.fecha_hora_fin AS fecha_hora_fin,
                'RESTAURACION_BACKUP'::text AS tipo_proceso,
                r.estado::text AS estado,
                r.gestion_origen,
                r.gestion_destino,
                r.usuario_nombre,
                NULL::bigint AS comprobante_id,
                r.backup_id::bigint AS backup_id,
                r.id::bigint AS restauracion_id,
                r.motivo AS observacion,
                r.detalle_json::text AS detalle_json,
                NULL::text AS archivo,
                NULL::numeric AS tamanio_bytes
            FROM contabilidad.esquema_restauracion_log r
            WHERE (r.gestion_origen = %s OR r.gestion_destino = %s)
              AND r.fecha_hora_inicio::date BETWEEN %s AND %s
        )
        SELECT
            *,
            ROUND(EXTRACT(EPOCH FROM (COALESCE(fecha_hora_fin, now()) - fecha)) / 60.0, 2) AS duracion_minutos
        FROM eventos
        WHERE (%s = 'TODAS' OR fuente_codigo = %s)
          AND (%s = 'TODOS' OR estado = %s)
          AND (%s = 'TODAS' OR tipo_proceso = %s)
        ORDER BY fecha DESC, codigo_evento DESC
        LIMIT %s
    """
    params = (
        gestion, gestion, fecha_desde, fecha_hasta,
        gestion, gestion, fecha_desde, fecha_hasta,
        gestion, gestion, fecha_desde, fecha_hasta,
        gestion, gestion, fecha_desde, fecha_hasta,
        fuente, fuente,
        estado, estado,
        tipo_proceso, tipo_proceso,
        limit + 1,
    )
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    enriched = [_enrich_row(dict(row)) for row in rows]
    truncated = len(enriched) > limit
    return enriched[:limit], truncated


def _summary(rows: list[dict[str, Any]], truncated: bool) -> dict[str, Any]:
    total = len(rows)
    criticos = sum(1 for row in rows if row.get('prioridad_codigo') == 'CRITICA')
    altas = sum(1 for row in rows if row.get('prioridad_codigo') == 'ALTA')
    fallidos = sum(1 for row in rows if row.get('estado_codigo') in {'FALLIDO', 'FALLIDA'})
    en_proceso = sum(1 for row in rows if row.get('estado_codigo') == 'EN_PROCESO')
    backups = sum(1 for row in rows if row.get('fuente_codigo') == 'BACKUP')
    restauraciones = sum(1 for row in rows if row.get('fuente_codigo') == 'RESTAURACION')
    ultimo = rows[0].get('fecha_display') if rows else ''
    return {
        'total': total,
        'criticos': criticos,
        'altas': altas,
        'fallidos': fallidos,
        'en_proceso': en_proceso,
        'backups': backups,
        'restauraciones': restauraciones,
        'ultimo_evento': ultimo,
        'truncated': truncated,
        'moneda_display_note': '',
    }


def _payload(limit: int) -> dict[str, Any]:
    gestion = _parse_int(request.args.get('gestion') or _gestion_actual(), 'Gestion')
    fecha_desde = _parse_date(request.args.get('fecha_desde'), 'Fecha desde', date(gestion, 1, 1))
    fecha_hasta = _parse_date(request.args.get('fecha_hasta'), 'Fecha hasta', date(gestion, 12, 31))
    if fecha_desde > fecha_hasta:
        raise ValueError('La fecha desde no puede ser mayor que la fecha hasta.')

    fuente = _upper_clean(request.args.get('fuente') or 'TODAS')
    tipo_proceso = _upper_clean(request.args.get('tipo_proceso') or 'TODAS')
    estado = _upper_clean(request.args.get('estado') or 'TODOS')

    fuentes_validas = {item['value'] for item in FUENTES}
    tipos_validos = {item['value'] for item in TIPOS_PROCESO}
    estados_validos = {item['value'] for item in ESTADOS}

    if fuente not in fuentes_validas:
        raise ValueError('La fuente seleccionada no es valida.')
    if tipo_proceso not in tipos_validos:
        raise ValueError('El tipo de proceso seleccionado no es valido.')
    if estado not in estados_validos:
        raise ValueError('El estado seleccionado no es valido.')

    rows, truncated = _fetch_rows(
        gestion=gestion,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        fuente=fuente,
        tipo_proceso=tipo_proceso,
        estado=estado,
        limit=limit,
    )

    periodo = f'{_date_label(fecha_desde, False)} al {_date_label(fecha_hasta, False)}'
    criterio = (
        f'Gestion {gestion} · Fuente: {FUENTE_LABELS.get(fuente, fuente)} · '
        f'Tipo: {TIPO_LABELS.get(tipo_proceso, tipo_proceso)} · Estado: {ESTADO_LABELS.get(estado, estado)}'
    )
    if truncated:
        criterio = f'{criterio} · Resultado limitado por seguridad operativa'

    return {
        'titulo': 'Bitacora de Procesos',
        'descripcion_periodo': periodo,
        'unidad_label': 'No aplica',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'gestion': gestion,
        'fecha_desde': fecha_desde.isoformat(),
        'fecha_hasta': fecha_hasta.isoformat(),
        'fuente': fuente,
        'tipo_proceso': tipo_proceso,
        'estado': estado,
        'rows': rows,
        'summary': _summary(rows, truncated),
        'criterio_reporte': criterio,
        'fuente_datos': 'gestion_proceso_bitacora, gestion_bloqueo_critico, esquema_backup_catalogo y esquema_restauracion_log.',
    }


class BitacoraProcesosExport:
    TITLE = 'Bitacora de Procesos'
    WORKSHEET_TITLE = 'Bitacora Procesos'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = set()

    @staticmethod
    def excel_columns():
        return [
            ('codigo_evento', 'Codigo', 16),
            ('fecha_display', 'Fecha', 20),
            ('fuente_label', 'Fuente', 24),
            ('tipo_label', 'Proceso', 28),
            ('estado_label', 'Estado', 18),
            ('prioridad_label', 'Prioridad', 16),
            ('gestion_texto', 'Gestion', 16),
            ('usuario_nombre', 'Usuario', 24),
            ('documento', 'Referencia', 34),
            ('duracion_display', 'Duracion', 14),
            ('observacion', 'Observacion', 60),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Total: {summary.get('total', 0)} · "
            f"Criticos: {summary.get('criticos', 0)} · "
            f"Altas: {summary.get('altas', 0)} · "
            f"Fallidos: {summary.get('fallidos', 0)} · "
            f"En proceso: {summary.get('en_proceso', 0)}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Codigo', 'width': 17, 'align': 'center'},
            {'label': 'Fecha', 'width': 23, 'align': 'center'},
            {'label': 'Fuente', 'width': 26, 'align': 'left'},
            {'label': 'Proceso', 'width': 27, 'align': 'left'},
            {'label': 'Estado', 'width': 20, 'align': 'center'},
            {'label': 'Prioridad', 'width': 18, 'align': 'center'},
            {'label': 'Gestion', 'width': 18, 'align': 'center'},
            {'label': 'Usuario', 'width': 24, 'align': 'left'},
            {'label': 'Referencia', 'width': 31, 'align': 'left'},
            {'label': 'Dur.', 'width': 14, 'align': 'center'},
            {'label': 'Observacion', 'width': 42, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        return [
            [
                row.get('codigo_evento', ''),
                row.get('fecha_display', ''),
                row.get('fuente_label', ''),
                row.get('tipo_label', ''),
                row.get('estado_label', ''),
                row.get('prioridad_label', ''),
                row.get('gestion_texto', ''),
                row.get('usuario_nombre', ''),
                row.get('documento', ''),
                row.get('duracion_display', ''),
                row.get('observacion_corta', ''),
            ]
            for row in payload.get('rows', [])
        ]

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"Total: {summary.get('total', 0)}. "
            f"Criticos: {summary.get('criticos', 0)}. "
            f"Altas: {summary.get('altas', 0)}. "
            f"Fallidos: {summary.get('fallidos', 0)}. "
            f"En proceso: {summary.get('en_proceso', 0)}."
        )


@bitacora_procesos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    gestion = _gestion_actual()
    gestiones = _obtener_gestiones()
    if gestiones:
        gestion = gestiones[0]
    return render_template(
        'bitacora_procesos_index.html',
        gestion_actual=gestion,
        gestiones=gestiones,
        fuentes=FUENTES,
        tipos_proceso=TIPOS_PROCESO,
        estados=ESTADOS,
    )


@bitacora_procesos_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_bitacora():
    try:
        return _json_ok(payload=_payload(MAX_ROWS_SCREEN))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar la bitacora de procesos. {exc}', 500)


@bitacora_procesos_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_bitacora():
    try:
        payload = _payload(MAX_ROWS_EXPORT)
        excel_bytes = build_excel(BitacoraProcesosExport, payload)
        filename = f"bitacora_procesos_{payload.get('gestion')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo exportar la bitacora a Excel. {exc}', 500)


@bitacora_procesos_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_bitacora():
    try:
        payload = _payload(MAX_ROWS_PDF)
        pdf_bytes = build_pdf(BitacoraProcesosExport, payload)
        filename = f"bitacora_procesos_{payload.get('gestion')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename="{filename}"'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF de la bitacora. {exc}', 500)


@bitacora_procesos_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('bitacora_procesos_help.html')
