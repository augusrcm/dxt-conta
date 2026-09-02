# ============================================================
# DXT CONTA - Herramientas - Estado de Cuenta de Auxiliar
# Trazabilidad de movimientos contables por auxiliar y cuenta
# ============================================================

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import Response, jsonify, render_template, request, url_for

from database.db_manager import DatabaseManager
from modules.estado_cuenta_auxiliar import estado_cuenta_auxiliar_bp
from modules.reportes_rapidos.core.catalogos import obtener_unidades_negocio, unidad_label
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_PDF, MAX_ROWS_SCREEN
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.formatos import format_money
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]
ESTADO_CONFIRMADO = 'CONFIRMADO'


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
    raw = _clean(value)
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es valido.') from exc
    if parsed <= 0:
        raise ValueError(f'El campo "{field_name}" no es valido.')
    return parsed


def _parse_optional_int(value: Any, field_name: str) -> int | None:
    raw = _clean(value)
    if not raw:
        return None
    return _parse_int(raw, field_name)


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



def _obtener_monedas() -> list[dict[str, str]]:
    rows = _db_rows(
        """
        SELECT codigo, COALESCE(simbolo, codigo) AS simbolo, nombre
        FROM contabilidad.moneda
        WHERE activo = TRUE
        ORDER BY CASE WHEN codigo = 'BOB' THEN 0 ELSE 1 END, codigo ASC
        """
    )
    if not rows:
        return [{'codigo': 'BOB', 'label': 'BOB'}]
    return [
        {
            'codigo': row.get('codigo') or '',
            'label': f"{row.get('codigo') or ''} · {row.get('nombre') or ''}".strip(' ·'),
        }
        for row in rows
    ]


def _obtener_auxiliares() -> list[dict[str, Any]]:
    rows = _db_rows(
        """
        SELECT
            id,
            tipo::text AS tipo,
            COALESCE(codigo_externo, '') AS codigo_externo,
            COALESCE(nit_ci, '') AS nit_ci,
            nombre,
            COALESCE(razon_social, '') AS razon_social
        FROM contabilidad.auxiliar
        WHERE activo = TRUE
        ORDER BY nombre ASC, id ASC
        LIMIT 1500
        """
    )
    results = []
    for row in rows:
        parts = [row['nombre']]
        if row.get('tipo'):
            parts.append(row['tipo'])
        if row.get('codigo_externo'):
            parts.append(f"COD: {row['codigo_externo']}")
        if row.get('nit_ci'):
            parts.append(f"NIT/CI: {row['nit_ci']}")
        results.append({
            'id': int(row['id']),
            'tipo': row.get('tipo') or '',
            'codigo_externo': row.get('codigo_externo') or '',
            'nit_ci': row.get('nit_ci') or '',
            'nombre': row.get('nombre') or '',
            'razon_social': row.get('razon_social') or '',
            'label': ' | '.join(parts),
        })
    return results


def _obtener_cuentas() -> list[dict[str, Any]]:
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
        LIMIT 2000
        """
    )
    return [
        {
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'tipo': row.get('tipo') or '',
            'naturaleza': row.get('naturaleza') or '',
            'requiere_auxiliar': bool(row.get('requiere_auxiliar')),
            'requiere_cc': bool(row.get('requiere_cc')),
            'label': f"{row['codigo']} · {row['nombre']}",
        }
        for row in rows
    ]


def _auxiliar_label(auxiliar_id: int) -> str:
    rows = _db_rows(
        """
        SELECT
            tipo::text AS tipo,
            nombre,
            COALESCE(codigo_externo, '') AS codigo_externo,
            COALESCE(nit_ci, '') AS nit_ci
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,),
    )
    if not rows:
        return f'Auxiliar #{auxiliar_id}'
    row = rows[0]
    parts = [row.get('nombre') or f'Auxiliar #{auxiliar_id}']
    if row.get('tipo'):
        parts.append(row['tipo'])
    if row.get('codigo_externo'):
        parts.append(f"COD: {row['codigo_externo']}")
    if row.get('nit_ci'):
        parts.append(f"NIT/CI: {row['nit_ci']}")
    return ' | '.join(parts)


def _cuenta_label(cuenta_codigo: str | None) -> str:
    if not cuenta_codigo:
        return 'Todas las cuentas con movimiento del auxiliar'
    rows = _db_rows(
        """
        SELECT codigo, nombre
        FROM contabilidad.cuenta
        WHERE codigo = %s
        LIMIT 1
        """,
        (cuenta_codigo,),
    )
    if not rows:
        return cuenta_codigo
    row = rows[0]
    return f"{row['codigo']} · {row['nombre']}"


def _descripcion_periodo(fecha_desde: date, fecha_hasta: date) -> str:
    if fecha_desde == fecha_hasta:
        return f"Fecha: {_date_label(fecha_desde)}"
    return f"Periodo: {_date_label(fecha_desde)} al {_date_label(fecha_hasta)}"


# ============================================================
# Filtros y consulta contable
# ============================================================


def _parse_filters(args) -> dict[str, Any]:
    gestion_default = _gestion_preferida()
    gestion = int(args.get('gestion') or gestion_default)
    fecha_desde = _parse_date(args.get('fecha_desde') or f'{gestion}-01-01', 'Fecha desde')
    fecha_hasta = _parse_date(args.get('fecha_hasta') or f'{gestion}-12-31', 'Fecha hasta')
    if fecha_hasta < fecha_desde:
        raise ValueError('La fecha hasta no puede ser menor que la fecha desde.')

    auxiliar_id = _parse_int(args.get('auxiliar_id'), 'Auxiliar')
    cuenta_codigo = _clean(args.get('cuenta_codigo')) or None
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de negocio')
    moneda_codigo = _clean(args.get('moneda_codigo') or 'BOB').upper()
    if not moneda_codigo:
        moneda_codigo = 'BOB'
    incluir_posteriores = _clean(args.get('incluir_posteriores')).lower() not in {'0', 'false', 'no'}

    return {
        'gestion': gestion,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'auxiliar_id': auxiliar_id,
        'cuenta_codigo': cuenta_codigo,
        'unidad_negocio_id': unidad_negocio_id,
        'moneda_codigo': moneda_codigo,
        'incluir_posteriores': incluir_posteriores,
    }


def _where_base(filtros: dict[str, Any]) -> tuple[list[str], list[Any]]:
    where = [
        'a.estado::text = %s',
        'ad.auxiliar_id = %s',
    ]
    params: list[Any] = [ESTADO_CONFIRMADO, filtros['auxiliar_id']]

    if filtros.get('cuenta_codigo'):
        where.append('ad.cuenta_codigo = %s')
        params.append(filtros['cuenta_codigo'])
    if filtros.get('unidad_negocio_id'):
        where.append('a.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    if filtros.get('moneda_codigo'):
        where.append('a.moneda_codigo = %s')
        params.append(filtros['moneda_codigo'])

    return where, params


def _fetch_total_before(filtros: dict[str, Any]) -> dict[str, Decimal]:
    where, params = _where_base(filtros)
    where.append('a.fecha < %s')
    params.append(filtros['fecha_desde'])

    rows = _db_rows(
        f"""
        SELECT
            COALESCE(SUM(COALESCE(ad.debe, 0)), 0) AS total_debe,
            COALESCE(SUM(COALESCE(ad.haber, 0)), 0) AS total_haber
        FROM contabilidad.asiento_detalle ad
        INNER JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    )
    row = rows[0] if rows else {}
    total_debe = _decimal(row.get('total_debe'))
    total_haber = _decimal(row.get('total_haber'))
    return {
        'debe': total_debe,
        'haber': total_haber,
        'saldo': total_debe - total_haber,
    }


def _fetch_movements(
    filtros: dict[str, Any],
    fecha_condicion: str,
    fecha_params: tuple[Any, ...],
    limit_rows: int | None = None,
) -> list[dict[str, Any]]:
    where, params = _where_base(filtros)
    where.append(fecha_condicion)
    params.extend(fecha_params)

    limit_sql = ''
    if limit_rows:
        limit_sql = 'LIMIT %s'
        params.append(limit_rows)

    rows = _db_rows(
        f"""
        SELECT
            ad.id AS detalle_id,
            a.id AS asiento_id,
            a.fecha,
            COALESCE(a.referencia, '') AS asiento_referencia,
            COALESCE(ad.referencia, '') AS detalle_referencia,
            COALESCE(a.glosa, '') AS asiento_glosa,
            COALESCE(ad.glosa, '') AS detalle_glosa,
            COALESCE(a.modulo_origen, '') AS modulo_origen,
            a.moneda_codigo,
            ad.secuencia,
            ad.cuenta_codigo,
            COALESCE(c.nombre, '') AS cuenta_nombre,
            COALESCE(c.naturaleza::text, '') AS cuenta_naturaleza,
            COALESCE(ad.debe, 0) AS debe,
            COALESCE(ad.haber, 0) AS haber,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, '') AS unidad_nombre,
            COALESCE(cc.codigo, '') AS centro_codigo,
            COALESCE(cc.nombre, '') AS centro_nombre
        FROM contabilidad.asiento_detalle ad
        INNER JOIN contabilidad.asiento a ON a.id = ad.asiento_id
        LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        LEFT JOIN contabilidad.centro_costo cc ON cc.id = ad.centro_costo_id
        WHERE {' AND '.join(where)}
        ORDER BY a.fecha ASC, a.id ASC, ad.secuencia ASC, ad.id ASC
        {limit_sql}
        """,
        tuple(params),
    )
    return rows


def _movement_to_row(row: dict[str, Any], bloque: str, saldo: Decimal) -> dict[str, Any]:
    debe = _decimal(row.get('debe'))
    haber = _decimal(row.get('haber'))
    referencia = row.get('detalle_referencia') or row.get('asiento_referencia') or f"Asiento #{row.get('asiento_id')}"
    glosa_detalle = row.get('detalle_glosa') or ''
    glosa_asiento = row.get('asiento_glosa') or ''
    glosa = glosa_detalle or glosa_asiento
    cuenta_label = f"{row.get('cuenta_codigo')} · {row.get('cuenta_nombre')}" if row.get('cuenta_nombre') else row.get('cuenta_codigo')
    unidad = f"{row.get('unidad_codigo')} · {row.get('unidad_nombre')}" if row.get('unidad_codigo') else (row.get('unidad_nombre') or '')
    centro_costo = f"{row.get('centro_codigo')} · {row.get('centro_nombre')}" if row.get('centro_codigo') else (row.get('centro_nombre') or '')

    moneda = row.get('moneda_codigo') or 'BOB'

    return {
        'tipo_linea': 'MOVIMIENTO',
        'bloque': bloque,
        'fecha': _date_label(row.get('fecha')),
        'fecha_iso': row.get('fecha').isoformat() if row.get('fecha') else '',
        'asiento_id': int(row.get('asiento_id') or 0),
        'detalle_id': int(row.get('detalle_id') or 0),
        'referencia': referencia,
        'cuenta_codigo': row.get('cuenta_codigo') or '',
        'cuenta': cuenta_label or '',
        'cuenta_naturaleza': row.get('cuenta_naturaleza') or '',
        'unidad': unidad,
        'centro_costo': centro_costo,
        'modulo_origen': row.get('modulo_origen') or '',
        'moneda_codigo': moneda,
        'glosa': glosa,
        'debe': debe,
        'haber': haber,
        'saldo': saldo,
        'debe_label': format_money(debe, moneda),
        'haber_label': format_money(haber, moneda),
        'saldo_label': format_money(saldo, moneda),
        'url_comprobante': url_for('comprobantes.ver', asiento_id=int(row.get('asiento_id') or 0)),
    }


def _control_row(tipo_linea: str, bloque: str, glosa: str, saldo: Decimal, fecha_label: str = '', moneda_codigo: str = 'BOB') -> dict[str, Any]:
    return {
        'tipo_linea': tipo_linea,
        'bloque': bloque,
        'fecha': fecha_label,
        'fecha_iso': '',
        'asiento_id': '',
        'detalle_id': '',
        'referencia': '',
        'cuenta_codigo': '',
        'cuenta': '',
        'cuenta_naturaleza': '',
        'unidad': '',
        'centro_costo': '',
        'modulo_origen': '',
        'moneda_codigo': moneda_codigo,
        'glosa': glosa,
        'debe': Decimal('0.00'),
        'haber': Decimal('0.00'),
        'saldo': saldo,
        'debe_label': '',
        'haber_label': '',
        'saldo_label': format_money(saldo, moneda_codigo),
        'url_comprobante': '',
    }


def _build_estado_cuenta(filtros: dict[str, Any], limit_rows: int | None = None) -> dict[str, Any]:
    saldo_anterior_info = _fetch_total_before(filtros)
    saldo_anterior = saldo_anterior_info['saldo']

    rango_movs = _fetch_movements(
        filtros,
        'a.fecha BETWEEN %s AND %s',
        (filtros['fecha_desde'], filtros['fecha_hasta']),
        limit_rows=limit_rows,
    )

    remaining_limit = None
    if limit_rows:
        remaining_limit = max(0, limit_rows - len(rango_movs))
    posteriores = []
    if filtros.get('incluir_posteriores') and (remaining_limit is None or remaining_limit > 0):
        posteriores = _fetch_movements(
            filtros,
            'a.fecha > %s',
            (filtros['fecha_hasta'],),
            limit_rows=remaining_limit,
        )

    rows: list[dict[str, Any]] = []
    rows.append(
        _control_row(
            'SALDO_ANTERIOR',
            'Saldo anterior',
            f"Saldo acumulado antes del {_date_label(filtros['fecha_desde'])}",
            saldo_anterior,
            moneda_codigo=filtros['moneda_codigo'],
        )
    )

    saldo = saldo_anterior
    total_debe_rango = Decimal('0.00')
    total_haber_rango = Decimal('0.00')
    for item in rango_movs:
        debe = _decimal(item.get('debe'))
        haber = _decimal(item.get('haber'))
        total_debe_rango += debe
        total_haber_rango += haber
        saldo += debe - haber
        rows.append(_movement_to_row(item, 'Rango solicitado', saldo))

    saldo_corte = saldo
    rows.append(
        _control_row(
            'SALDO_CORTE',
            'Saldo al corte',
            f"Saldo al {_date_label(filtros['fecha_hasta'])}",
            saldo_corte,
            _date_label(filtros['fecha_hasta']),
            filtros['moneda_codigo'],
        )
    )

    total_debe_posterior = Decimal('0.00')
    total_haber_posterior = Decimal('0.00')
    for item in posteriores:
        debe = _decimal(item.get('debe'))
        haber = _decimal(item.get('haber'))
        total_debe_posterior += debe
        total_haber_posterior += haber
        saldo += debe - haber
        rows.append(_movement_to_row(item, 'Posterior al corte', saldo))

    saldo_actual = saldo
    if filtros.get('incluir_posteriores'):
        rows.append(
            _control_row(
                'SALDO_ACTUAL',
                'Saldo actual',
                f"Saldo actual del auxiliar posterior al {_date_label(filtros['fecha_hasta'])}",
                saldo_actual,
                moneda_codigo=filtros['moneda_codigo'],
            )
        )

    summary = {
        'saldo_anterior': saldo_anterior,
        'saldo_anterior_label': format_money(saldo_anterior, filtros['moneda_codigo']),
        'total_debe_rango': total_debe_rango,
        'total_debe_rango_label': format_money(total_debe_rango, filtros['moneda_codigo']),
        'total_haber_rango': total_haber_rango,
        'total_haber_rango_label': format_money(total_haber_rango, filtros['moneda_codigo']),
        'saldo_corte': saldo_corte,
        'saldo_corte_label': format_money(saldo_corte, filtros['moneda_codigo']),
        'total_debe_posterior': total_debe_posterior,
        'total_debe_posterior_label': format_money(total_debe_posterior, filtros['moneda_codigo']),
        'total_haber_posterior': total_haber_posterior,
        'total_haber_posterior_label': format_money(total_haber_posterior, filtros['moneda_codigo']),
        'saldo_actual': saldo_actual,
        'saldo_actual_label': format_money(saldo_actual, filtros['moneda_codigo']),
        'movimientos_rango': len(rango_movs),
        'movimientos_posteriores': len(posteriores),
        'total_lineas': len(rows),
        'moneda_display_note': f"Importes expresados en {filtros['moneda_codigo']}. Saldo calculado como Debe menos Haber.",
    }

    return {
        'rows': rows,
        'summary': summary,
    }


def _build_payload(filtros: dict[str, Any], limit_rows: int | None = None) -> dict[str, Any]:
    estado = _build_estado_cuenta(filtros, limit_rows=limit_rows)
    auxiliar_texto = _auxiliar_label(filtros['auxiliar_id'])
    cuenta_texto = _cuenta_label(filtros.get('cuenta_codigo'))
    unidad_texto = unidad_label(filtros.get('unidad_negocio_id'))
    descripcion_periodo = _descripcion_periodo(filtros['fecha_desde'], filtros['fecha_hasta'])

    return {
        'titulo': 'Estado de Cuenta de Auxiliar',
        'descripcion_periodo': descripcion_periodo,
        'gestion': filtros['gestion'],
        'fecha_desde': filtros['fecha_desde'],
        'fecha_hasta': filtros['fecha_hasta'],
        'auxiliar_id': filtros['auxiliar_id'],
        'auxiliar_label': auxiliar_texto,
        'cuenta_label': cuenta_texto,
        'unidad_label': unidad_texto,
        'incluir_posteriores': filtros.get('incluir_posteriores'),
        'criterio_reporte': (
            f"Auxiliar: {auxiliar_texto}. Cuenta: {cuenta_texto}. "
            f"Posteriores: {'Si' if filtros.get('incluir_posteriores') else 'No'}."
        ),
        'fuente_datos': 'contabilidad.asiento / contabilidad.asiento_detalle / contabilidad.auxiliar',
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'rows': estado['rows'],
        'summary': estado['summary'],
    }


# ============================================================
# Exportacion
# ============================================================


class EstadoCuentaAuxiliarExport:
    TITLE = 'Estado de Cuenta de Auxiliar'
    WORKSHEET_TITLE = 'Auxiliar'
    PDF_ORIENTATION = 'landscape'
    MONEY_FIELDS = {'debe', 'haber', 'saldo'}

    @staticmethod
    def excel_columns():
        return [
            ('bloque', 'Bloque', 22),
            ('fecha', 'Fecha', 14),
            ('asiento_id', 'Comprobante', 14),
            ('referencia', 'Referencia', 28),
            ('cuenta', 'Cuenta', 36),
            ('unidad', 'Unidad de negocio', 30),
            ('moneda_codigo', 'Moneda', 10),
            ('centro_costo', 'Centro de costo', 28),
            ('modulo_origen', 'Modulo origen', 18),
            ('debe', 'Debe', 16),
            ('haber', 'Haber', 16),
            ('saldo', 'Saldo', 16),
            ('glosa', 'Glosa', 70),
        ]

    @staticmethod
    def excel_summary_text(summary):
        return (
            f"Saldo anterior: {summary.get('saldo_anterior_label', '0.00')} · "
            f"Debe rango: {summary.get('total_debe_rango_label', '0.00')} · "
            f"Haber rango: {summary.get('total_haber_rango_label', '0.00')} · "
            f"Saldo al corte: {summary.get('saldo_corte_label', '0.00')} · "
            f"Saldo actual: {summary.get('saldo_actual_label', '0.00')}"
        )

    @staticmethod
    def pdf_columns():
        return [
            {'label': 'Bloque', 'width': 28, 'align': 'left'},
            {'label': 'Fecha', 'width': 18, 'align': 'center'},
            {'label': 'Comp.', 'width': 14, 'align': 'center'},
            {'label': 'Referencia', 'width': 34, 'align': 'left'},
            {'label': 'Cuenta', 'width': 38, 'align': 'left'},
            {'label': 'Mon.', 'width': 12, 'align': 'center'},
            {'label': 'Debe', 'width': 22, 'align': 'right'},
            {'label': 'Haber', 'width': 22, 'align': 'right'},
            {'label': 'Saldo', 'width': 24, 'align': 'right'},
            {'label': 'Glosa', 'width': 66, 'align': 'left'},
        ]

    @staticmethod
    def pdf_rows(payload):
        rows = []
        for item in payload.get('rows', [])[:MAX_ROWS_PDF]:
            rows.append([
                item.get('bloque', ''),
                item.get('fecha', ''),
                str(item.get('asiento_id') or ''),
                item.get('referencia', ''),
                item.get('cuenta', ''),
                item.get('moneda_codigo', ''),
                item.get('debe_label', ''),
                item.get('haber_label', ''),
                item.get('saldo_label', ''),
                item.get('glosa', ''),
            ])
        if len(payload.get('rows', [])) > MAX_ROWS_PDF:
            rows.append(['Limite PDF', '', '', '', '', '', '', '', '', f'Se muestran {MAX_ROWS_PDF} filas. Use Excel para el detalle completo.'])
        return rows

    @staticmethod
    def pdf_header_note(payload):
        summary = payload.get('summary') or {}
        return (
            f"{payload.get('descripcion_periodo', '')}. "
            f"Auxiliar: {payload.get('auxiliar_label', '')}. "
            f"Cuenta: {payload.get('cuenta_label', '')}. "
            f"Unidad: {payload.get('unidad_label', '')}. "
            f"Saldo anterior: {summary.get('saldo_anterior_label', '0.00')}. "
            f"Saldo al corte: {summary.get('saldo_corte_label', '0.00')}. "
            f"Saldo actual: {summary.get('saldo_actual_label', '0.00')}."
        )


# ============================================================
# Rutas
# ============================================================


@estado_cuenta_auxiliar_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    gestion = _gestion_preferida()
    bootstrap = {
        'auxiliares': _obtener_auxiliares(),
        'cuentas': _obtener_cuentas(),
        'urls': {
            'api': url_for('estado_cuenta_auxiliar.api_estado_cuenta'),
            'pdf': url_for('estado_cuenta_auxiliar.pdf_estado_cuenta'),
            'excel': url_for('estado_cuenta_auxiliar.excel_estado_cuenta'),
        },
    }
    return render_template(
        'estado_cuenta_auxiliar_index.html',
        gestiones=_obtener_gestiones(),
        gestion_preferida=gestion,
        fecha_desde=f'{gestion}-01-01',
        fecha_hasta=f'{gestion}-12-31',
        fecha_hoy=date.today().isoformat(),
        unidades_negocio=obtener_unidades_negocio(),
        bootstrap=bootstrap,
    )


@estado_cuenta_auxiliar_bp.route('/api')
@login_required
@roles_required(ROLES_LECTURA)
def api_estado_cuenta():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        return _json_ok(**payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el estado de cuenta del auxiliar. {exc}', 500)


@estado_cuenta_auxiliar_bp.route('/excel')
@login_required
@roles_required(ROLES_LECTURA)
def excel_estado_cuenta():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        excel_bytes = build_excel(EstadoCuentaAuxiliarExport, payload)
        nombre = f"estado_cuenta_auxiliar_{filtros['auxiliar_id']}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el Excel del estado de cuenta. {exc}', 500)


@estado_cuenta_auxiliar_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_estado_cuenta():
    try:
        filtros = _parse_filters(request.args)
        payload = _build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        pdf_bytes = build_pdf(EstadoCuentaAuxiliarExport, payload)
        nombre = f"estado_cuenta_auxiliar_{filtros['auxiliar_id']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del estado de cuenta. {exc}', 500)


@estado_cuenta_auxiliar_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('estado_cuenta_auxiliar_help.html')
