from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import Response, abort, jsonify, render_template, request, session
from psycopg2.extras import RealDictCursor

from database.db_manager import DatabaseManager
from modules.comprobantes import comprobantes_bp
from utils.db import execute_query, execute_query_one
from utils.decorators import login_required, roles_required
from modules.reportes_rapidos.core.utils import logo_path
from utils.documentos_pdf import build_accounting_document_pdf, format_date, format_money


ESTADO_BORRADOR = 'BORRADOR'
ESTADO_CONFIRMADO = 'CONFIRMADO'
ESTADO_ANULADO = 'ANULADO'
MODULO_MANUAL = 'CONTABILIDAD'
MONEDA_BASE = 'BOB'

ORIGEN_MANUAL = 'MANUAL'
ORIGEN_TESORERIA_PAGOS = 'TESORERIA_PAGOS'
ORIGEN_TESORERIA_COBROS = 'TESORERIA_COBROS'
ORIGEN_TESORERIA_MOVIMIENTOS = 'TESORERIA_MOVIMIENTOS'
ORIGEN_FACTURA_ELECTRONICA = 'FACTURA_ELECTRONICA'
ORIGEN_SALDOS_INICIALES = 'SALDOS_INICIALES'
ORIGEN_CIERRE_GESTION = 'CIERRE_GESTION'

ORIGEN_LABELS = {
    ORIGEN_MANUAL: 'Manual',
    ORIGEN_TESORERIA_PAGOS: 'Tesorería - Pagos',
    ORIGEN_TESORERIA_COBROS: 'Tesorería - Cobros',
    ORIGEN_TESORERIA_MOVIMIENTOS: 'Tesorería - Caja/Bancos',
    ORIGEN_FACTURA_ELECTRONICA: 'Facturas electrónicas',
    ORIGEN_SALDOS_INICIALES: 'Saldos iniciales',
    ORIGEN_CIERRE_GESTION: 'Cierre de gestión',
}


# ============================================================
# Helpers generales
# ============================================================

def _clean(value: Any) -> str:
    return (value or '').strip()



def _safe_str(value: Any) -> str:
    return _clean(value)



def _upper_clean(value: Any) -> str:
    return _clean(value).upper()



def _parse_date(value: Any) -> date | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None



def _decimal_or_none(value: Any, quantize: str = '0.01') -> Decimal | None:
    if value in (None, '', 'null'):
        return None
    try:
        decimal_value = Decimal(str(value)).quantize(Decimal(quantize), rounding=ROUND_HALF_UP)
        return decimal_value
    except (InvalidOperation, ValueError, TypeError):
        return None



def _decimal_or_zero(value: Any, quantize: str = '0.01') -> Decimal:
    decimal_value = _decimal_or_none(value, quantize=quantize)
    return decimal_value if decimal_value is not None else Decimal('0.00')



def _normalize_reference(value: Any) -> str | None:
    value = _clean(value)
    if value.lower() == 'none':
        return None
    return value or None



def _parse_int_or_none(value: Any) -> int | None:
    if value in (None, '', 'null'):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None



def _json_ready(value: Any) -> Any:
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value



def _make_error(message: str, status: int = 400):
    return jsonify({'ok': False, 'msg': message}), status


def _usuario_actual() -> str:
    return (
        _clean(session.get('nombre'))
        or _clean(session.get('username'))
        or _clean(session.get('usuario'))
        or _clean(session.get('correo'))
        or _clean(session.get('email'))
        or str(session.get('user_id') or 'sistema')
    )


def _label_origen_comprobante(asiento: dict[str, Any]) -> str:
    origen = _upper_clean(asiento.get('origen'))
    if origen in ORIGEN_LABELS:
        return ORIGEN_LABELS[origen]

    modulo = _upper_clean(asiento.get('modulo_origen'))
    if modulo in ORIGEN_LABELS:
        return ORIGEN_LABELS[modulo]

    return modulo.replace('_', ' ').title() if modulo else 'Manual'


def _label_documento_origen(asiento: dict[str, Any]) -> str:
    documento_relacionado = _clean(asiento.get('documento_relacionado'))
    if documento_relacionado:
        return documento_relacionado

    tabla = _clean(asiento.get('tabla_origen'))
    origen_id = asiento.get('origen_id')
    if not tabla or not origen_id:
        return '-'

    if tabla == 'contabilidad.pago':
        return f'PAGO #{origen_id}'
    if tabla == 'contabilidad.cobro':
        return f'COBRO #{origen_id}'
    if tabla == 'contabilidad.factura_electronica':
        return f'FACTURA ELECTRÓNICA #{origen_id}'
    if tabla == 'contabilidad.movimiento_tesoreria':
        return f'MOVIMIENTO TESORERÍA #{origen_id}'
    if tabla == 'contabilidad.gestion_control':
        return f'CIERRE GESTIÓN #{origen_id}'
    if tabla == 'contabilidad.asiento':
        return f'ASIENTO #{origen_id}'
    return f'{tabla} #{origen_id}'


def _build_comprobante_pdf_bytes(asiento: dict[str, Any], detalles: list[dict[str, Any]], detalle_fuente: list[dict[str, Any]]) -> bytes:
    generado = datetime.now().strftime('%d/%m/%Y %H:%M')
    moneda = asiento.get('moneda_codigo') or MONEDA_BASE
    tipo_cambio = Decimal(str(asiento.get('tipo_cambio') or 1)).quantize(Decimal('0.000001'))

    total_debe = sum((Decimal(str(item.get('debe') or 0)) for item in detalles), Decimal('0.00'))
    total_haber = sum((Decimal(str(item.get('haber') or 0)) for item in detalles), Decimal('0.00'))
    diferencia = total_debe - total_haber

    unidad = f"{asiento.get('unidad_negocio_codigo') or ''} - {asiento.get('unidad_negocio_nombre') or ''}".strip(' -')
    rubro = f"{asiento.get('rubro_codigo') or ''} - {asiento.get('rubro_nombre') or ''}".strip(' -')

    sections = [
        {
            'title': 'Identificacion del comprobante',
            'items': [
                {'label': 'Comprobante', 'value': f"#{asiento.get('id')}"},
                {'label': 'Fecha', 'value': format_date(asiento.get('fecha'))},
                {'label': 'Estado', 'value': asiento.get('estado') or '-'},
                {'label': 'Origen', 'value': _label_origen_comprobante(asiento)},
                {'label': 'Operacion origen', 'value': asiento.get('origen_operacion') or 'MANUAL'},
                {'label': 'Referencia', 'value': asiento.get('referencia') or '-'},
            ],
        },
        {
            'title': 'Datos contables',
            'items': [
                {'label': 'Unidad de negocio', 'value': unidad or '-'},
                {'label': 'Rubro', 'value': rubro or '-'},
                {'label': 'Moneda', 'value': moneda},
                {'label': 'Tipo de cambio', 'value': f'{tipo_cambio}'},
                {'label': 'Documento relacionado', 'value': _label_documento_origen(asiento)},
                {'label': 'Lineas contables', 'value': str(len(detalles or []))},
            ],
        },
    ]

    publicidad_etiqueta = asiento.get('publicidad_elemento_etiqueta') or asiento.get('publicidad_elemento_codigo_ref')
    if publicidad_etiqueta:
        sections.append({
            'title': 'Referencia publicitaria',
            'items': [
                {'label': 'Tipo', 'value': asiento.get('publicidad_referencia_tipo') or '-'},
                {'label': 'Codigo', 'value': asiento.get('publicidad_elemento_codigo_ref') or '-'},
                {'label': 'Referencia', 'value': publicidad_etiqueta},
                {'label': 'Vigencia desde', 'value': format_date(asiento.get('vigencia_desde')) or '-'},
                {'label': 'Vigencia hasta', 'value': format_date(asiento.get('vigencia_hasta')) or '-'},
                {'label': 'Referencia interna', 'value': asiento.get('publicidad_referencia_ref') or '-'},
            ],
        })

    detail_rows = []
    for row in detalles or []:
        cuenta = row.get('cuenta_codigo') or ''
        if row.get('cuenta_nombre'):
            cuenta = f"{cuenta} - {row.get('cuenta_nombre')}"
        auxiliar = row.get('auxiliar_nombre') or '-'
        centro_costo = row.get('centro_costo_codigo') or ''
        if row.get('centro_costo_nombre'):
            centro_costo = f"{centro_costo} - {row.get('centro_costo_nombre')}".strip(' -')
        detail_rows.append([
            row.get('secuencia') or '',
            cuenta,
            row.get('glosa') or '',
            auxiliar,
            centro_costo or '-',
            format_money(row.get('debe')),
            format_money(row.get('haber')),
        ])

    additional_tables = []
    if detalle_fuente:
        source_rows = []
        for item in detalle_fuente:
            source_rows.append([
                item.get('secuencia') or '',
                item.get('tipo_linea') or '',
                item.get('descripcion') or '',
                format_money(item.get('cantidad')),
                format_money(item.get('precio_unitario')),
                format_money(item.get('subtotal')),
            ])
        additional_tables.append({
            'title': 'Detalle operativo de origen',
            'columns': [
                {'label': '#', 'width': 10, 'align': 'center'},
                {'label': 'Tipo', 'width': 24},
                {'label': 'Descripcion', 'width': 66},
                {'label': 'Cant.', 'width': 18, 'align': 'right'},
                {'label': 'P. Unit.', 'width': 25, 'align': 'right'},
                {'label': 'Subtotal', 'width': 31, 'align': 'right'},
            ],
            'rows': source_rows,
            'empty_message': 'No hay detalle operativo de origen.',
        })

    return build_accounting_document_pdf(
        title='Comprobante Contable',
        subtitle=f'DXT Conta - Contabilidad - Emitido {generado}',
        document_number=f"COMP-{int(asiento.get('id')):06d}",
        state=asiento.get('estado') or '',
        sections=sections,
        detail_columns=[
            {'label': '#', 'width': 8, 'align': 'center'},
            {'label': 'Cuenta', 'width': 42},
            {'label': 'Glosa', 'width': 42},
            {'label': 'Auxiliar', 'width': 27},
            {'label': 'C.Costo', 'width': 24},
            {'label': 'Debe', 'width': 15.5, 'align': 'right'},
            {'label': 'Haber', 'width': 15.5, 'align': 'right'},
        ],
        detail_rows=detail_rows,
        totals=[
            {'label': f'Total debe {moneda}', 'value': format_money(total_debe)},
            {'label': f'Total haber {moneda}', 'value': format_money(total_haber)},
            {'label': 'Diferencia', 'value': format_money(diferencia)},
        ],
        additional_tables=additional_tables,
        notes=[{'title': 'Glosa general', 'text': asiento.get('glosa') or '-'}],
        emitted_by=_usuario_actual(),
        logo_file=logo_path(),
        generated_at=generado,
    )



def _tipo_cambio_para_fecha(fecha: date, moneda_codigo: str) -> dict[str, Any]:
    moneda_codigo = _upper_clean(moneda_codigo)

    if moneda_codigo == MONEDA_BASE:
        return {
            'valor': Decimal('1.000000'),
            'fecha_base': fecha,
            'exacto': True,
            'campo': None,
        }

    campo = None
    if moneda_codigo == 'USD':
        campo = 'usd_paralelo'
    elif moneda_codigo == 'UFV':
        campo = 'ufv'

    if not campo:
        return {
            'valor': None,
            'fecha_base': None,
            'exacto': False,
            'campo': None,
        }

    row = execute_query_one(
        f"""
        SELECT
            fecha,
            {campo} AS valor
        FROM contabilidad.tipo_cambio
        WHERE fecha <= %s
        ORDER BY fecha DESC
        LIMIT 1
        """,
        (fecha,)
    )

    if not row:
        return {
            'valor': None,
            'fecha_base': None,
            'exacto': False,
            'campo': campo,
        }

    valor = row.get('valor')
    if valor is not None and not isinstance(valor, Decimal):
        valor = Decimal(str(valor))

    return {
        'valor': valor,
        'fecha_base': row.get('fecha'),
        'exacto': row.get('fecha') == fecha,
        'campo': campo,
    }



def _obtener_asiento_basico(asiento_id: int) -> dict[str, Any] | None:
    return execute_query_one(
        """
        SELECT
            a.id,
            a.fecha,
            a.moneda_codigo,
            a.tipo_cambio,
            a.glosa,
            NULLIF(a.referencia, 'None') AS referencia,
            a.modulo_origen,
            a.tabla_origen,
            a.origen_id,
            a.estado,
            a.atributos,
            NULLIF(a.atributos->>'rubro_id', '')::int AS rubro_id,
            COALESCE(a.atributos->>'rubro_codigo', '') AS rubro_codigo,
            COALESCE(a.atributos->>'rubro_nombre', '') AS rubro_nombre,
            NULLIF(a.atributos->>'publicidad_referencia_ref', '') AS publicidad_referencia_ref,
            NULLIF(a.atributos->>'publicidad_referencia_tipo', '') AS publicidad_referencia_tipo,
            NULLIF(a.atributos->>'publicidad_elemento_id_ref', '')::int AS publicidad_elemento_id_ref,
            NULLIF(a.atributos->>'publicidad_estructura_id_ref', '')::int AS publicidad_estructura_id_ref,
            COALESCE(a.atributos->>'publicidad_elemento_codigo_ref', '') AS publicidad_elemento_codigo_ref,
            COALESCE(a.atributos->>'publicidad_elemento_etiqueta', '') AS publicidad_elemento_etiqueta,
            NULLIF(a.atributos->>'vigencia_desde', '') AS vigencia_desde,
            NULLIF(a.atributos->>'vigencia_hasta', '') AS vigencia_hasta,
            COALESCE(a.atributos->>'documento_relacionado', '') AS documento_relacionado,
            a.creado_en,
            a.actualizado_en,
            a.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            COALESCE(un.nit, '') AS unidad_negocio_nit,
            CASE
                WHEN a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.pago' THEN 'TESORERIA_PAGOS'
                WHEN a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.cobro' THEN 'TESORERIA_COBROS'
                WHEN a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.movimiento_tesoreria' THEN 'TESORERIA_MOVIMIENTOS'
                WHEN a.tabla_origen = 'contabilidad.factura_electronica' THEN 'FACTURA_ELECTRONICA'
                WHEN a.modulo_origen = 'SALDOS_INICIALES' THEN 'SALDOS_INICIALES'
                WHEN a.modulo_origen = 'CIERRE_GESTION' THEN 'CIERRE_GESTION'
                ELSE 'MANUAL'
            END AS origen,
            CASE
                WHEN a.tabla_origen = 'contabilidad.pago' THEN p.origen_operacion::text
                WHEN a.tabla_origen = 'contabilidad.cobro' THEN c.origen_operacion::text
                WHEN a.tabla_origen = 'contabilidad.movimiento_tesoreria' THEN mt.tipo_movimiento::text
                WHEN a.tabla_origen = 'contabilidad.factura_electronica' THEN 'FACTURA_ELECTRONICA'
                WHEN a.modulo_origen = 'SALDOS_INICIALES' THEN 'SALDOS_INICIALES'
                WHEN a.modulo_origen = 'CIERRE_GESTION' THEN COALESCE(a.atributos->>'tipo_asiento', 'CIERRE_GESTION')
                ELSE 'MANUAL'
            END AS origen_operacion,
            CASE
                WHEN COALESCE(a.modulo_origen, 'CONTABILIDAD') = 'CONTABILIDAD' THEN TRUE
                ELSE FALSE
            END AS es_manual,
            CASE
                WHEN COALESCE(a.modulo_origen, 'CONTABILIDAD') = 'CONTABILIDAD'
                     AND a.estado = 'BORRADOR' THEN TRUE
                ELSE FALSE
            END AS puede_editar
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.pago p
            ON a.tabla_origen = 'contabilidad.pago'
           AND a.origen_id = p.id
        LEFT JOIN contabilidad.cobro c
            ON a.tabla_origen = 'contabilidad.cobro'
           AND a.origen_id = c.id
        LEFT JOIN contabilidad.factura_electronica fe
            ON a.tabla_origen = 'contabilidad.factura_electronica'
           AND a.origen_id = fe.id
        LEFT JOIN contabilidad.movimiento_tesoreria mt
            ON a.tabla_origen = 'contabilidad.movimiento_tesoreria'
           AND a.origen_id = mt.id
        LEFT JOIN contabilidad.unidad_negocio un
            ON un.id = a.unidad_negocio_id
        WHERE a.id = %s
        LIMIT 1
        """,
        (asiento_id,)
    )



def _obtener_detalles_asiento(asiento_id: int) -> list[dict[str, Any]]:
    rows = execute_query(
        """
        SELECT
            ad.id,
            ad.asiento_id,
            ad.secuencia,
            ad.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            c.requiere_auxiliar,
            c.requiere_cc,
            c.naturaleza::text AS naturaleza,
            ad.auxiliar_id,
            ax.nombre AS auxiliar_nombre,
            ax.tipo::text AS auxiliar_tipo,
            ad.centro_costo_id,
            cc.codigo AS centro_costo_codigo,
            cc.nombre AS centro_costo_nombre,
            ad.glosa,
            ad.debe,
            ad.haber,
            ad.monto_moneda,
            NULLIF(ad.referencia, 'None') AS referencia,
            ad.atributos
        FROM contabilidad.asiento_detalle ad
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.auxiliar ax
            ON ax.id = ad.auxiliar_id
        LEFT JOIN contabilidad.centro_costo cc
            ON cc.id = ad.centro_costo_id
        WHERE ad.asiento_id = %s
        ORDER BY ad.secuencia ASC, ad.id ASC
        """,
        (asiento_id,),
        fetchall=True
    )

    for row in rows:
        row['cuenta_text'] = f"{row['cuenta_codigo']} | {row['cuenta_nombre']}"
        if row.get('auxiliar_id'):
            row['auxiliar_text'] = f"{row.get('auxiliar_nombre', '')} | {row.get('auxiliar_tipo', '')}"
        else:
            row['auxiliar_text'] = ''
        if row.get('centro_costo_id'):
            row['centro_costo_text'] = f"{row.get('centro_costo_codigo', '')} | {row.get('centro_costo_nombre', '')}"
        else:
            row['centro_costo_text'] = ''

    return rows



def _obtener_detalle_fuente(tabla_origen: str | None, origen_id: int | None) -> list[dict[str, Any]]:
    if not tabla_origen or not origen_id:
        return []

    if tabla_origen == 'contabilidad.pago':
        query = """
            SELECT
                pd.secuencia,
                pd.tipo_linea::text AS tipo_linea,
                pd.descripcion,
                pd.cantidad,
                pd.precio_unitario,
                pd.subtotal,
                pd.observacion
            FROM contabilidad.pago_detalle pd
            WHERE pd.pago_id = %s
            ORDER BY pd.secuencia ASC, pd.id ASC
        """
    elif tabla_origen == 'contabilidad.cobro':
        query = """
            SELECT
                cd.secuencia,
                cd.tipo_linea::text AS tipo_linea,
                cd.descripcion,
                cd.cantidad,
                cd.precio_unitario,
                cd.subtotal,
                cd.observacion
            FROM contabilidad.cobro_detalle cd
            WHERE cd.cobro_id = %s
            ORDER BY cd.secuencia ASC, cd.id ASC
        """
    elif tabla_origen == 'contabilidad.factura_electronica':
        query = """
            SELECT
                1 AS secuencia,
                'FACTURA_ELECTRONICA' AS tipo_linea,
                CONCAT('Factura ', fe.numero_factura, ' - ', COALESCE(fe.nombre_cliente, '')) AS descripcion,
                1::numeric AS cantidad,
                fe.importe_total AS precio_unitario,
                fe.importe_total AS subtotal,
                CONCAT('Estado: ', fe.estado::text, ' · Saldo: ', COALESCE(fe.saldo_pendiente, 0)::text) AS observacion
            FROM contabilidad.factura_electronica fe
            WHERE fe.id = %s
        """
    elif tabla_origen == 'contabilidad.movimiento_tesoreria':
        query = """
            SELECT
                1 AS secuencia,
                mt.tipo_movimiento::text AS tipo_linea,
                mt.glosa AS descripcion,
                1::numeric AS cantidad,
                mt.monto AS precio_unitario,
                mt.monto AS subtotal,
                CONCAT('Estado: ', mt.estado::text, ' · Medio origen: ', COALESCE(mt.medio_origen::text, '-'), ' · Medio destino: ', COALESCE(mt.medio_destino::text, '-')) AS observacion
            FROM contabilidad.movimiento_tesoreria mt
            WHERE mt.id = %s
        """
    else:
        return []

    return execute_query(query, (origen_id,), fetchall=True)



def _obtener_cuenta(codigo: str) -> dict[str, Any] | None:
    return execute_query_one(
        """
        SELECT
            codigo,
            nombre,
            activo,
            es_postable,
            requiere_auxiliar,
            requiere_cc,
            naturaleza::text AS naturaleza
        FROM contabilidad.cuenta
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,)
    )



def _obtener_auxiliar(auxiliar_id: int | None) -> dict[str, Any] | None:
    if not auxiliar_id:
        return None

    return execute_query_one(
        """
        SELECT
            id,
            tipo::text AS tipo,
            nombre,
            activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,)
    )



def _obtener_centro_costo(centro_costo_id: int | None) -> dict[str, Any] | None:
    if not centro_costo_id:
        return None

    return execute_query_one(
        """
        SELECT
            id,
            codigo,
            nombre,
            activo
        FROM contabilidad.centro_costo
        WHERE id = %s
        LIMIT 1
        """,
        (centro_costo_id,)
    )



def _moneda_activa(moneda_codigo: str) -> bool:
    row = execute_query_one(
        """
        SELECT codigo
        FROM contabilidad.moneda
        WHERE codigo = %s
          AND activo = TRUE
        LIMIT 1
        """,
        (moneda_codigo,)
    )
    return bool(row)



def _obtener_unidad_negocio(unidad_negocio_id: int | None, solo_activa: bool = False) -> dict[str, Any] | None:
    if not unidad_negocio_id:
        return None

    where_activa = ' AND activo = TRUE' if solo_activa else ''
    return execute_query_one(
        f"""
        SELECT
            id,
            codigo,
            nombre,
            activo,
            COALESCE(nit, '') AS nit
        FROM contabilidad.unidad_negocio
        WHERE id = %s{where_activa}
        LIMIT 1
        """,
        (unidad_negocio_id,)
    )



def _obtener_rubro(rubro_id: int | None, solo_activo: bool = False) -> dict[str, Any] | None:
    if not rubro_id:
        return None

    where_activo = ' AND activo = TRUE' if solo_activo else ''
    return execute_query_one(
        f"""
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(descripcion, '') AS descripcion,
            activo
        FROM contabilidad.rubro_operacion
        WHERE id = %s{where_activo}
        LIMIT 1
        """,
        (rubro_id,)
    )



def _obtener_elemento_publicitario(
    elemento_id: int | None,
    unidad_negocio_id: int | None = None,
    solo_activo: bool = False,
) -> dict[str, Any] | None:
    if not elemento_id:
        return None

    condiciones = ['e.id = %s', "COALESCE(btrim(e.codigo_gamlp), '') <> ''"]
    params: list[Any] = [elemento_id]

    if solo_activo:
        condiciones.extend(["e.estado = 'ACTIVA'", "s.estado = 'ACTIVA'"])

    if unidad_negocio_id:
        condiciones.append('s.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    return execute_query_one(
        f"""
        SELECT
            'ELEMENTO' AS ref_tipo,
            'E:' || e.id::text AS ref_key,
            e.id AS ref_id,
            e.id,
            e.codigo_gamlp,
            e.codigo AS elemento_codigo,
            e.nombre AS elemento_nombre,
            s.id AS estructura_id,
            s.codigo AS estructura_codigo,
            s.nombre AS estructura_nombre,
            s.unidad_negocio_id,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            e.codigo_gamlp || ' ' || e.nombre || ' - ELEMENTO' AS etiqueta
        FROM publicidad.elemento_publicitario e
        INNER JOIN publicidad.estructura_publicitaria s
            ON s.id = e.estructura_id
        LEFT JOIN contabilidad.unidad_negocio uneg
            ON uneg.id = s.unidad_negocio_id
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        tuple(params),
    )


def _obtener_estructura_publicitaria(
    estructura_id: int | None,
    unidad_negocio_id: int | None = None,
    solo_activo: bool = False,
) -> dict[str, Any] | None:
    if not estructura_id:
        return None

    condiciones = ['s.id = %s', "COALESCE(btrim(s.codigo_gamlp), '') <> ''"]
    params: list[Any] = [estructura_id]

    if solo_activo:
        condiciones.append("s.estado = 'ACTIVA'")

    if unidad_negocio_id:
        condiciones.append('s.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    return execute_query_one(
        f"""
        SELECT
            'ESTRUCTURA' AS ref_tipo,
            'S:' || s.id::text AS ref_key,
            s.id AS ref_id,
            NULL::bigint AS id,
            s.codigo_gamlp,
            NULL::text AS elemento_codigo,
            NULL::text AS elemento_nombre,
            s.id AS estructura_id,
            s.codigo AS estructura_codigo,
            s.nombre AS estructura_nombre,
            s.unidad_negocio_id,
            COALESCE(uneg.codigo, '') AS unidad_negocio_codigo,
            COALESCE(uneg.nombre, '') AS unidad_negocio_nombre,
            s.codigo_gamlp || ' ' || s.nombre || ' - ESTRUCTURA' AS etiqueta
        FROM publicidad.estructura_publicitaria s
        LEFT JOIN contabilidad.unidad_negocio uneg
            ON uneg.id = s.unidad_negocio_id
        WHERE {' AND '.join(condiciones)}
        LIMIT 1
        """,
        tuple(params),
    )


def _obtener_referencia_publicitaria(referencia_raw: Any, unidad_negocio_id: int | None = None, solo_activo: bool = False) -> dict[str, Any] | None:
    ref = str(referencia_raw or '').strip()
    if not ref:
        return None
    if ref.startswith('E:'):
        return _obtener_elemento_publicitario(_parse_int_or_none(ref.split(':', 1)[1]), unidad_negocio_id=unidad_negocio_id, solo_activo=solo_activo)
    if ref.startswith('S:'):
        return _obtener_estructura_publicitaria(_parse_int_or_none(ref.split(':', 1)[1]), unidad_negocio_id=unidad_negocio_id, solo_activo=solo_activo)
    return _obtener_elemento_publicitario(_parse_int_or_none(ref), unidad_negocio_id=unidad_negocio_id, solo_activo=solo_activo)



def _listar_rubros() -> list[dict[str, Any]]:
    return execute_query(
        """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(descripcion, '') AS descripcion,
            activo
        FROM contabilidad.rubro_operacion
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC, id ASC
        """,
        fetchall=True,
    )



def _listar_elementos_publicitarios() -> list[dict[str, Any]]:
    return execute_query(
        """
        SELECT *
        FROM (
            SELECT
                'ELEMENTO' AS ref_tipo,
                'E:' || e.id::text AS ref_key,
                e.id AS ref_id,
                e.id,
                e.codigo_gamlp,
                e.codigo AS elemento_codigo,
                e.nombre AS elemento_nombre,
                s.id AS estructura_id,
                s.codigo AS estructura_codigo,
                s.nombre AS estructura_nombre,
                s.unidad_negocio_id,
                COALESCE(un.codigo, '') AS unidad_negocio_codigo,
                COALESCE(un.nombre, '') AS unidad_negocio_nombre,
                e.codigo_gamlp || ' ' || e.nombre || ' - ELEMENTO' AS etiqueta
            FROM publicidad.elemento_publicitario e
            INNER JOIN publicidad.estructura_publicitaria s
                ON s.id = e.estructura_id
            LEFT JOIN contabilidad.unidad_negocio un
                ON un.id = s.unidad_negocio_id
            WHERE e.estado = 'ACTIVA'
              AND s.estado = 'ACTIVA'
              AND COALESCE(btrim(e.codigo_gamlp), '') <> ''
            UNION ALL
            SELECT
                'ESTRUCTURA' AS ref_tipo,
                'S:' || s.id::text AS ref_key,
                s.id AS ref_id,
                NULL::bigint AS id,
                s.codigo_gamlp,
                NULL::text AS elemento_codigo,
                NULL::text AS elemento_nombre,
                s.id AS estructura_id,
                s.codigo AS estructura_codigo,
                s.nombre AS estructura_nombre,
                s.unidad_negocio_id,
                COALESCE(un.codigo, '') AS unidad_negocio_codigo,
                COALESCE(un.nombre, '') AS unidad_negocio_nombre,
                s.codigo_gamlp || ' ' || s.nombre || ' - ESTRUCTURA' AS etiqueta
            FROM publicidad.estructura_publicitaria s
            LEFT JOIN contabilidad.unidad_negocio un
                ON un.id = s.unidad_negocio_id
            WHERE s.estado = 'ACTIVA'
              AND COALESCE(btrim(s.codigo_gamlp), '') <> ''
        ) q
        ORDER BY codigo_gamlp ASC, etiqueta ASC
        """,
        fetchall=True,
    )



def _validar_detalles(detalles: Any, glosa_cabecera: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(detalles, list) or len(detalles) < 2:
        return None, 'Debe registrar al menos dos líneas contables.'

    detalles_normalizados: list[dict[str, Any]] = []
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')

    for idx, item in enumerate(detalles, start=1):
        if not isinstance(item, dict):
            return None, f'La línea {idx} no tiene un formato válido.'

        cuenta_codigo = _upper_clean(item.get('cuenta_codigo'))
        auxiliar_raw = item.get('auxiliar_id')
        centro_costo_raw = item.get('centro_costo_id')
        glosa_linea = _clean(item.get('glosa')) or glosa_cabecera
        debe = _decimal_or_zero(item.get('debe'))
        haber = _decimal_or_zero(item.get('haber'))
        referencia = _normalize_reference(item.get('referencia'))

        try:
            auxiliar_id = int(auxiliar_raw) if auxiliar_raw not in (None, '', 'null') else None
        except (TypeError, ValueError):
            return None, f'El auxiliar de la línea {idx} es inválido.'

        try:
            centro_costo_id = int(centro_costo_raw) if centro_costo_raw not in (None, '', 'null') else None
        except (TypeError, ValueError):
            return None, f'El centro de costo de la línea {idx} es inválido.'

        if not cuenta_codigo:
            return None, f'La cuenta contable es obligatoria en la línea {idx}.'

        cuenta = _obtener_cuenta(cuenta_codigo)
        if not cuenta:
            return None, f'La cuenta {cuenta_codigo} de la línea {idx} no existe.'
        if not bool(cuenta['activo']):
            return None, f'La cuenta {cuenta_codigo} de la línea {idx} está inactiva.'
        if not bool(cuenta['es_postable']):
            return None, f'La cuenta {cuenta_codigo} de la línea {idx} no es postable.'

        if debe < 0 or haber < 0:
            return None, f'Los importes no pueden ser negativos en la línea {idx}.'
        if debe == Decimal('0.00') and haber == Decimal('0.00'):
            return None, f'Debe registrar Debe o Haber en la línea {idx}.'
        if debe > 0 and haber > 0:
            return None, f'La línea {idx} no puede tener Debe y Haber al mismo tiempo.'

        auxiliar = _obtener_auxiliar(auxiliar_id) if auxiliar_id else None
        if auxiliar_id and not auxiliar:
            return None, f'El auxiliar de la línea {idx} no existe.'
        if auxiliar and not bool(auxiliar['activo']):
            return None, f'El auxiliar de la línea {idx} está inactivo.'
        if bool(cuenta['requiere_auxiliar']) and not auxiliar_id:
            return None, f'La cuenta {cuenta_codigo} requiere auxiliar en la línea {idx}.'

        centro_costo = _obtener_centro_costo(centro_costo_id) if centro_costo_id else None
        if centro_costo_id and not centro_costo:
            return None, f'El centro de costo de la línea {idx} no existe.'
        if centro_costo and not bool(centro_costo['activo']):
            return None, f'El centro de costo de la línea {idx} está inactivo.'
        if bool(cuenta['requiere_cc']) and not centro_costo_id:
            return None, f'La cuenta {cuenta_codigo} requiere centro de costo en la línea {idx}.'

        monto_moneda = debe if debe > 0 else haber
        total_debe += debe
        total_haber += haber

        detalles_normalizados.append({
            'secuencia': idx,
            'cuenta_codigo': cuenta_codigo,
            'auxiliar_id': auxiliar_id,
            'centro_costo_id': centro_costo_id,
            'glosa': glosa_linea,
            'debe': debe,
            'haber': haber,
            'monto_moneda': monto_moneda,
            'referencia': referencia,
            'atributos': {
                'origen': 'manual',
                'cuenta_nombre': cuenta['nombre'],
                'naturaleza_cuenta': cuenta['naturaleza'],
            },
        })

    if total_debe != total_haber:
        return None, 'El comprobante no está balanceado. La suma del Debe debe ser igual al Haber.'

    if total_debe <= Decimal('0.00'):
        return None, 'El comprobante debe tener un monto mayor a cero.'

    return detalles_normalizados, None



def _validar_payload(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    fecha = _parse_date(data.get('fecha'))
    moneda_codigo = _upper_clean(data.get('moneda_codigo'))
    tipo_cambio = _decimal_or_none(data.get('tipo_cambio'), quantize='0.000001')
    glosa = _clean(data.get('glosa'))
    referencia = _normalize_reference(data.get('referencia'))
    documento_relacionado = _clean(data.get('documento_relacionado')) or None
    unidad_negocio_id = _parse_int_or_none(data.get('unidad_negocio_id'))
    rubro_id = _parse_int_or_none(data.get('rubro_id'))
    publicidad_referencia_raw = _safe_str(data.get('publicidad_elemento_id_ref'))
    publicidad_elemento_codigo_ref = _clean(data.get('publicidad_elemento_codigo_ref')) or None
    vigencia_desde = _parse_date(data.get('vigencia_desde'))
    vigencia_hasta = _parse_date(data.get('vigencia_hasta'))
    detalles = data.get('detalles') or []

    if not fecha:
        return None, 'La fecha del comprobante es obligatoria.'

    if not moneda_codigo:
        return None, 'La moneda es obligatoria.'

    if not _moneda_activa(moneda_codigo):
        return None, 'La moneda seleccionada no existe o está inactiva.'

    if moneda_codigo == MONEDA_BASE:
        tipo_cambio = Decimal('1.000000')
    else:
        if tipo_cambio is None or tipo_cambio <= 0:
            return None, 'El tipo de cambio es obligatorio y debe ser mayor a cero.'

    if not glosa:
        return None, 'La glosa es obligatoria.'

    unidad_negocio = _obtener_unidad_negocio(unidad_negocio_id, solo_activa=True)
    if not unidad_negocio:
        return None, 'Debe seleccionar una unidad de negocio activa.'

    rubro = _obtener_rubro(rubro_id, solo_activo=True) if rubro_id else None
    if rubro_id and not rubro:
        return None, 'El rubro seleccionado no existe o está inactivo.'

    publicidad_referencia_ref = None
    publicidad_referencia_tipo = None
    publicidad_elemento_id_ref = None
    publicidad_estructura_id_ref = None
    publicidad_elemento = None
    publicidad_elemento_etiqueta = None

    if rubro_id:
        if not publicidad_referencia_raw:
            return None, 'Debes seleccionar una referencia publicitaria cuando elijas un rubro.'

        publicidad_elemento = _obtener_referencia_publicitaria(
            publicidad_referencia_raw,
            unidad_negocio_id=unidad_negocio['id'],
            solo_activo=True,
        )
        if not publicidad_elemento:
            return None, 'La referencia publicitaria seleccionada no existe, está inactiva o no pertenece a la unidad de negocio.'

        publicidad_referencia_ref = publicidad_elemento.get('ref_key')
        publicidad_referencia_tipo = publicidad_elemento.get('ref_tipo')
        publicidad_elemento_id_ref = publicidad_elemento.get('id') if publicidad_elemento.get('ref_tipo') == 'ELEMENTO' else None
        publicidad_estructura_id_ref = publicidad_elemento.get('estructura_id') if publicidad_elemento.get('ref_tipo') == 'ESTRUCTURA' else None
        publicidad_elemento_codigo_ref = publicidad_elemento.get('codigo_gamlp')
        publicidad_elemento_etiqueta = publicidad_elemento.get('etiqueta')

        if not vigencia_desde or not vigencia_hasta:
            return None, 'Debes indicar la vigencia desde y hasta cuando selecciones un rubro.'
        if vigencia_hasta < vigencia_desde:
            return None, 'La vigencia hasta no puede ser menor que la vigencia desde.'
    else:
        publicidad_referencia_ref = None
        publicidad_referencia_tipo = None
        publicidad_elemento_id_ref = None
        publicidad_estructura_id_ref = None
        publicidad_elemento_codigo_ref = None
        publicidad_elemento_etiqueta = None
        vigencia_desde = None
        vigencia_hasta = None

    detalles_normalizados, error = _validar_detalles(detalles, glosa)
    if error:
        return None, error

    usuario = _clean(session.get('nombre')) or _clean(session.get('correo')) or f"USER-{session.get('user_id', 'NA')}"

    payload = {
        'fecha': fecha,
        'moneda_codigo': moneda_codigo,
        'tipo_cambio': tipo_cambio,
        'glosa': glosa,
        'referencia': referencia,
        'unidad_negocio_id': unidad_negocio['id'],
        'detalles': detalles_normalizados,
        'atributos': {
            'origen': 'manual',
            'tipo_comprobante': 'MANUAL',
            'registrado_por': usuario,
            'unidad_negocio_codigo': unidad_negocio['codigo'],
            'unidad_negocio_nombre': unidad_negocio['nombre'],
            'rubro_id': rubro['id'] if rubro else None,
            'rubro_codigo': rubro['codigo'] if rubro else None,
            'rubro_nombre': rubro['nombre'] if rubro else None,
            'publicidad_referencia_ref': publicidad_referencia_ref,
            'publicidad_referencia_tipo': publicidad_referencia_tipo,
            'publicidad_elemento_id_ref': publicidad_elemento_id_ref,
            'publicidad_estructura_id_ref': publicidad_estructura_id_ref,
            'publicidad_elemento_codigo_ref': publicidad_elemento_codigo_ref,
            'publicidad_elemento_etiqueta': publicidad_elemento_etiqueta,
            'vigencia_desde': vigencia_desde.isoformat() if vigencia_desde else None,
            'vigencia_hasta': vigencia_hasta.isoformat() if vigencia_hasta else None,
            'documento_relacionado': documento_relacionado,
        },
    }

    return payload, None


def _crear_asiento_manual(payload: dict[str, Any]) -> int:
    with DatabaseManager() as db:
        cursor = db.conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            INSERT INTO contabilidad.asiento (
                fecha,
                moneda_codigo,
                tipo_cambio,
                glosa,
                referencia,
                unidad_negocio_id,
                modulo_origen,
                tabla_origen,
                origen_id,
                estado,
                atributos,
                creado_en,
                actualizado_en
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NULL,
                NULL,
                %s,
                %s::jsonb,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            RETURNING id
            """,
            (
                payload['fecha'],
                payload['moneda_codigo'],
                payload['tipo_cambio'],
                payload['glosa'],
                payload['referencia'],
                payload['unidad_negocio_id'],
                MODULO_MANUAL,
                ESTADO_BORRADOR,
                json.dumps(payload['atributos'], ensure_ascii=False),
            )
        )
        row = cursor.fetchone()
        asiento_id = int(row['id'])

        for detalle in payload['detalles']:
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
                    json.dumps(detalle['atributos'], ensure_ascii=False),
                )
            )

        return asiento_id



def _actualizar_asiento_manual(asiento_id: int, payload: dict[str, Any], atributos_actuales: dict[str, Any] | None) -> None:
    atributos = dict(atributos_actuales or {})
    atributos.update(payload['atributos'])
    atributos['ultima_actualizacion_por'] = payload['atributos'].get('registrado_por')
    atributos['ultima_actualizacion_en'] = datetime.now().isoformat(timespec='seconds')

    with DatabaseManager() as db:
        cursor = db.conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            UPDATE contabilidad.asiento
            SET
                fecha = %s,
                moneda_codigo = %s,
                tipo_cambio = %s,
                glosa = %s,
                referencia = %s,
                unidad_negocio_id = %s,
                atributos = %s::jsonb,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
              AND estado = %s
              AND COALESCE(modulo_origen, %s) = %s
            """,
            (
                payload['fecha'],
                payload['moneda_codigo'],
                payload['tipo_cambio'],
                payload['glosa'],
                payload['referencia'],
                payload['unidad_negocio_id'],
                json.dumps(atributos, ensure_ascii=False),
                asiento_id,
                ESTADO_BORRADOR,
                MODULO_MANUAL,
                MODULO_MANUAL,
            )
        )
        if cursor.rowcount != 1:
            raise ValueError('El comprobante ya no está disponible para edición. Recargue el módulo y verifique su estado.')

        cursor.execute(
            "DELETE FROM contabilidad.asiento_detalle WHERE asiento_id = %s",
            (asiento_id,)
        )

        for detalle in payload['detalles']:
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
                    json.dumps(detalle['atributos'], ensure_ascii=False),
                )
            )



def _marcar_estado_manual(asiento: dict[str, Any], nuevo_estado: str) -> tuple[bool, str | None]:
    if not bool(asiento.get('es_manual')):
        return False, 'Los comprobantes generados por Tesorería se muestran en solo lectura desde este módulo.'

    atributos = dict(asiento.get('atributos') or {})
    usuario = _clean(session.get('nombre')) or _clean(session.get('correo')) or f"USER-{session.get('user_id', 'NA')}"

    if nuevo_estado == ESTADO_CONFIRMADO:
        if asiento.get('estado') != ESTADO_BORRADOR:
            return False, 'Solo se pueden confirmar comprobantes en estado BORRADOR.'

        resumen = execute_query_one(
            """
            SELECT
                COUNT(*) AS total_lineas,
                COALESCE(SUM(debe), 0) AS total_debe,
                COALESCE(SUM(haber), 0) AS total_haber,
                contabilidad.fn_validar_asiento_balanceado(%s) AS balanceado
            FROM contabilidad.asiento_detalle
            WHERE asiento_id = %s
            """,
            (asiento['id'], asiento['id'])
        )

        if not resumen or int(resumen.get('total_lineas') or 0) < 2:
            return False, 'El comprobante debe tener al menos dos líneas contables.'
        if not bool(resumen.get('balanceado')):
            return False, 'El comprobante no está balanceado.'
        if Decimal(str(resumen.get('total_debe') or 0)) <= 0:
            return False, 'El comprobante debe tener un importe mayor a cero.'

        atributos['confirmado_por'] = usuario
        atributos['confirmado_en'] = datetime.now().isoformat(timespec='seconds')

    elif nuevo_estado == ESTADO_ANULADO:
        if asiento.get('estado') == ESTADO_ANULADO:
            return False, 'El comprobante ya se encuentra anulado.'
        atributos['anulado_por'] = usuario
        atributos['anulado_en'] = datetime.now().isoformat(timespec='seconds')

    with DatabaseManager() as db:
        cursor = db.conn.cursor()
        if nuevo_estado == ESTADO_CONFIRMADO:
            cursor.execute(
                """
                UPDATE contabilidad.asiento
                SET
                    estado = %s,
                    atributos = %s::jsonb,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND estado = %s
                  AND COALESCE(modulo_origen, %s) = %s
                """,
                (
                    nuevo_estado,
                    json.dumps(atributos, ensure_ascii=False),
                    asiento['id'],
                    ESTADO_BORRADOR,
                    MODULO_MANUAL,
                    MODULO_MANUAL,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE contabilidad.asiento
                SET
                    estado = %s,
                    atributos = %s::jsonb,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND estado <> %s
                  AND COALESCE(modulo_origen, %s) = %s
                """,
                (
                    nuevo_estado,
                    json.dumps(atributos, ensure_ascii=False),
                    asiento['id'],
                    ESTADO_ANULADO,
                    MODULO_MANUAL,
                    MODULO_MANUAL,
                ),
            )

        if cursor.rowcount != 1:
            return False, 'El comprobante cambió de estado o ya no está disponible para esta operación.'

    return True, None



def _eliminar_asiento_manual(asiento: dict[str, Any]) -> tuple[bool, str | None]:
    if not bool(asiento.get('es_manual')):
        return False, 'Los comprobantes generados por otros módulos se muestran en solo lectura desde este módulo.'
    if asiento.get('estado') != ESTADO_BORRADOR:
        return False, 'Solo se pueden eliminar comprobantes manuales en BORRADOR.'

    with DatabaseManager() as db:
        cursor = db.conn.cursor()
        # La relación asiento_detalle tiene ON DELETE CASCADE. Eliminar la cabecera
        # evita borrar líneas si la cabecera ya cambió de estado por otra sesión.
        cursor.execute(
            """
            DELETE FROM contabilidad.asiento
            WHERE id = %s
              AND estado = %s
              AND COALESCE(modulo_origen, %s) = %s
            """,
            (asiento['id'], ESTADO_BORRADOR, MODULO_MANUAL, MODULO_MANUAL),
        )
        if cursor.rowcount != 1:
            return False, 'No se pudo eliminar el comprobante. Recargue el módulo y verifique su estado.'

    return True, None


# ============================================================
# Rutas
# ============================================================

@comprobantes_bp.route('/')
@login_required
def index():
    return render_template('comprobantes_index.html', fecha_hoy=date.today().isoformat())


@comprobantes_bp.route('/nuevo')
@login_required
def nuevo():
    return render_template(
        'comprobantes_form.html',
        fecha_hoy=date.today().isoformat(),
        vista_modo='new',
        asiento_id=None,
    )


@comprobantes_bp.route('/ver/<int:asiento_id>')
@login_required
def ver(asiento_id: int):
    asiento = _obtener_asiento_basico(asiento_id)
    if not asiento:
        abort(404)

    return render_template(
        'comprobantes_form.html',
        fecha_hoy=date.today().isoformat(),
        vista_modo='view',
        asiento_id=asiento_id,
    )


@comprobantes_bp.route('/editar/<int:asiento_id>')
@login_required
def editar(asiento_id: int):
    asiento = _obtener_asiento_basico(asiento_id)
    if not asiento:
        abort(404)

    vista_modo = 'edit' if bool(asiento.get('puede_editar')) else 'view'

    return render_template(
        'comprobantes_form.html',
        fecha_hoy=date.today().isoformat(),
        vista_modo=vista_modo,
        asiento_id=asiento_id,
    )


@comprobantes_bp.route('/data')
@login_required
def data():
    fecha_desde = _parse_date(request.args.get('fecha_desde'))
    fecha_hasta = _parse_date(request.args.get('fecha_hasta'))
    estado = _upper_clean(request.args.get('estado'))
    origen = _upper_clean(request.args.get('origen'))
    moneda = _upper_clean(request.args.get('moneda_codigo'))
    unidad_negocio_id_raw = request.args.get('unidad_negocio_id')
    texto = _clean(request.args.get('texto'))

    try:
        unidad_negocio_id = int(unidad_negocio_id_raw) if _clean(unidad_negocio_id_raw) else None
    except (TypeError, ValueError):
        unidad_negocio_id = None

    where = ["1 = 1"]
    params: list[Any] = []

    if fecha_desde:
        where.append('a.fecha >= %s')
        params.append(fecha_desde)

    if fecha_hasta:
        where.append('a.fecha <= %s')
        params.append(fecha_hasta)

    if estado and estado != 'TODOS':
        where.append('a.estado = %s')
        params.append(estado)

    if moneda and moneda != 'TODAS':
        where.append('a.moneda_codigo = %s')
        params.append(moneda)

    if unidad_negocio_id:
        where.append('a.unidad_negocio_id = %s')
        params.append(unidad_negocio_id)

    if origen == 'MANUAL':
        where.append("COALESCE(a.modulo_origen, 'CONTABILIDAD') = 'CONTABILIDAD'")
    elif origen == 'TESORERIA_PAGOS':
        where.append("a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.pago'")
    elif origen == 'TESORERIA_COBROS':
        where.append("a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.cobro'")
    elif origen == 'TESORERIA_MOVIMIENTOS':
        where.append("a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.movimiento_tesoreria'")
    elif origen == 'FACTURA_ELECTRONICA':
        where.append("a.tabla_origen = 'contabilidad.factura_electronica'")
    elif origen == 'SALDOS_INICIALES':
        where.append("a.modulo_origen = 'SALDOS_INICIALES'")
    elif origen == 'CIERRE_GESTION':
        where.append("a.modulo_origen = 'CIERRE_GESTION'")

    if texto:
        texto_like = f'%{texto}%'
        where.append(
            """
            (
                CAST(a.id AS TEXT) ILIKE %s
                OR a.glosa ILIKE %s
                OR COALESCE(a.referencia, '') ILIKE %s
                OR COALESCE(ax_pago.nombre, '') ILIKE %s
                OR COALESCE(ax_cobro.nombre, '') ILIKE %s
                OR COALESCE(ax_mov.nombre, '') ILIKE %s
                OR COALESCE(fe.numero_factura, '') ILIKE %s
                OR COALESCE(fe.nombre_cliente, '') ILIKE %s
                OR COALESCE(fe.nit_cliente, '') ILIKE %s
                OR COALESCE(mt.glosa, '') ILIKE %s
                OR COALESCE(un.nombre, '') ILIKE %s
                OR COALESCE(un.codigo, '') ILIKE %s
            )
            """
        )
        params.extend([
            texto_like, texto_like, texto_like, texto_like, texto_like,
            texto_like, texto_like, texto_like, texto_like, texto_like,
            texto_like, texto_like,
        ])

    query = f"""
        WITH detalle AS (
            SELECT
                asiento_id,
                COUNT(*) AS total_lineas,
                COALESCE(SUM(debe), 0) AS total_debe,
                COALESCE(SUM(haber), 0) AS total_haber
            FROM contabilidad.asiento_detalle
            GROUP BY asiento_id
        )
        SELECT
            a.id,
            a.fecha,
            a.estado,
            a.moneda_codigo,
            a.tipo_cambio,
            a.glosa,
            NULLIF(a.referencia, 'None') AS referencia,
            a.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            COALESCE(d.total_debe, 0) AS total_debe,
            COALESCE(d.total_haber, 0) AS total_haber,
            COALESCE(d.total_lineas, 0) AS total_lineas,
            CASE
                WHEN a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.pago' THEN 'TESORERIA_PAGOS'
                WHEN a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.cobro' THEN 'TESORERIA_COBROS'
                WHEN a.modulo_origen = 'TESORERIA' AND a.tabla_origen = 'contabilidad.movimiento_tesoreria' THEN 'TESORERIA_MOVIMIENTOS'
                WHEN a.tabla_origen = 'contabilidad.factura_electronica' THEN 'FACTURA_ELECTRONICA'
                WHEN a.modulo_origen = 'SALDOS_INICIALES' THEN 'SALDOS_INICIALES'
                WHEN a.modulo_origen = 'CIERRE_GESTION' THEN 'CIERRE_GESTION'
                ELSE 'MANUAL'
            END AS origen,
            CASE
                WHEN a.tabla_origen = 'contabilidad.pago' THEN p.origen_operacion::text
                WHEN a.tabla_origen = 'contabilidad.cobro' THEN c.origen_operacion::text
                WHEN a.tabla_origen = 'contabilidad.movimiento_tesoreria' THEN mt.tipo_movimiento::text
                WHEN a.tabla_origen = 'contabilidad.factura_electronica' THEN 'FACTURA_ELECTRONICA'
                WHEN a.modulo_origen = 'SALDOS_INICIALES' THEN 'SALDOS_INICIALES'
                WHEN a.modulo_origen = 'CIERRE_GESTION' THEN COALESCE(a.atributos->>'tipo_asiento', 'CIERRE_GESTION')
                ELSE 'MANUAL'
            END AS origen_operacion,
            CASE
                WHEN a.tabla_origen = 'contabilidad.pago' THEN COALESCE(ax_pago.nombre, '')
                WHEN a.tabla_origen = 'contabilidad.cobro' THEN COALESCE(ax_cobro.nombre, '')
                WHEN a.tabla_origen = 'contabilidad.movimiento_tesoreria' THEN COALESCE(ax_mov.nombre, '')
                WHEN a.tabla_origen = 'contabilidad.factura_electronica' THEN COALESCE(fe.nombre_cliente, '')
                ELSE ''
            END AS auxiliar_nombre,
            CASE
                WHEN COALESCE(a.modulo_origen, 'CONTABILIDAD') = 'CONTABILIDAD'
                     AND a.estado = 'BORRADOR' THEN TRUE
                ELSE FALSE
            END AS puede_editar
        FROM contabilidad.asiento a
        LEFT JOIN detalle d
            ON d.asiento_id = a.id
        LEFT JOIN contabilidad.pago p
            ON a.tabla_origen = 'contabilidad.pago'
           AND a.origen_id = p.id
        LEFT JOIN contabilidad.cobro c
            ON a.tabla_origen = 'contabilidad.cobro'
           AND a.origen_id = c.id
        LEFT JOIN contabilidad.factura_electronica fe
            ON a.tabla_origen = 'contabilidad.factura_electronica'
           AND a.origen_id = fe.id
        LEFT JOIN contabilidad.movimiento_tesoreria mt
            ON a.tabla_origen = 'contabilidad.movimiento_tesoreria'
           AND a.origen_id = mt.id
        LEFT JOIN contabilidad.auxiliar ax_pago
            ON ax_pago.id = p.proveedor_auxiliar_id
        LEFT JOIN contabilidad.auxiliar ax_cobro
            ON ax_cobro.id = c.cliente_auxiliar_id
        LEFT JOIN contabilidad.auxiliar ax_mov
            ON ax_mov.id = mt.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un
            ON un.id = a.unidad_negocio_id
        WHERE {' AND '.join(where)}
        ORDER BY a.fecha DESC, a.id DESC
    """

    rows = execute_query(query, tuple(params), fetchall=True)

    stats = {
        'total': len(rows),
        'borradores': sum(1 for row in rows if row.get('estado') == ESTADO_BORRADOR),
        'confirmados': sum(1 for row in rows if row.get('estado') == ESTADO_CONFIRMADO),
        'manuales': sum(1 for row in rows if row.get('origen') == 'MANUAL'),
    }

    return jsonify({'data': _json_ready(rows), 'stats': stats})


@comprobantes_bp.route('/<int:asiento_id>/pdf')
@login_required
def pdf(asiento_id: int):
    asiento = _obtener_asiento_basico(asiento_id)
    if not asiento:
        abort(404)

    try:
        detalles = _obtener_detalles_asiento(asiento_id)
        detalle_fuente = _obtener_detalle_fuente(asiento.get('tabla_origen'), asiento.get('origen_id'))
        pdf_bytes = _build_comprobante_pdf_bytes(asiento, detalles, detalle_fuente)
        fecha_doc = asiento['fecha'].strftime('%Y%m%d') if asiento.get('fecha') else datetime.now().strftime('%Y%m%d')
        nombre = f"comprobante_contable_{int(asiento_id):06d}_{fecha_doc}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except Exception as exc:
        return _make_error(f'No se pudo generar el PDF del comprobante. {exc}', 500)


@comprobantes_bp.route('/obtener/<int:asiento_id>')
@login_required
def obtener(asiento_id: int):
    asiento = _obtener_asiento_basico(asiento_id)
    if not asiento:
        return _make_error('El comprobante solicitado no existe.', 404)

    detalles = _obtener_detalles_asiento(asiento_id)
    detalle_fuente = _obtener_detalle_fuente(asiento.get('tabla_origen'), asiento.get('origen_id'))

    resumen = {
        'total_debe': sum((Decimal(str(item.get('debe') or 0)) for item in detalles), Decimal('0.00')),
        'total_haber': sum((Decimal(str(item.get('haber') or 0)) for item in detalles), Decimal('0.00')),
        'total_lineas': len(detalles),
    }

    data = {
        'asiento': asiento,
        'detalles': detalles,
        'detalle_fuente': detalle_fuente,
        'resumen': resumen,
    }
    return jsonify({'ok': True, 'data': _json_ready(data)})


@comprobantes_bp.route('/cuentas/buscar')
@login_required
def buscar_cuentas():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'

    rows = execute_query(
        """
        SELECT
            codigo,
            nombre,
            requiere_auxiliar,
            requiere_cc,
            naturaleza::text AS naturaleza
        FROM contabilidad.cuenta
        WHERE activo = TRUE
          AND es_postable = TRUE
          AND (
                %s = ''
                OR codigo ILIKE %s
                OR nombre ILIKE %s
              )
        ORDER BY codigo ASC
        LIMIT 30
        """,
        (q, q_like, q_like),
        fetchall=True
    )

    results = []
    for row in rows:
        suffix = []
        if row.get('requiere_auxiliar'):
            suffix.append('Req. Aux.')
        if row.get('requiere_cc'):
            suffix.append('Req. C.C.')
        extra = f" [{' · '.join(suffix)}]" if suffix else ''
        results.append({
            'id': row['codigo'],
            'text': f"{row['codigo']} | {row['nombre']}{extra}",
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'requiere_auxiliar': bool(row.get('requiere_auxiliar')),
            'requiere_cc': bool(row.get('requiere_cc')),
            'naturaleza': row.get('naturaleza'),
        })

    return jsonify({'results': results})


@comprobantes_bp.route('/auxiliares/buscar')
@login_required
def buscar_auxiliares():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'

    rows = execute_query(
        """
        SELECT
            id,
            tipo::text AS tipo,
            nombre,
            COALESCE(codigo_externo, '') AS codigo_externo,
            COALESCE(nit_ci, '') AS nit_ci
        FROM contabilidad.auxiliar
        WHERE activo = TRUE
          AND (
                %s = ''
                OR nombre ILIKE %s
                OR COALESCE(codigo_externo, '') ILIKE %s
                OR COALESCE(nit_ci, '') ILIKE %s
              )
        ORDER BY nombre ASC
        LIMIT 30
        """,
        (q, q_like, q_like, q_like),
        fetchall=True
    )

    results = []
    for row in rows:
        descriptor = [row['nombre'], row['tipo']]
        if _clean(row.get('codigo_externo')):
            descriptor.append(f"COD: {row['codigo_externo']}")
        if _clean(row.get('nit_ci')):
            descriptor.append(f"NIT/CI: {row['nit_ci']}")
        results.append({
            'id': row['id'],
            'text': ' | '.join(descriptor),
            'nombre': row['nombre'],
            'tipo': row['tipo'],
        })

    return jsonify({'results': results})


@comprobantes_bp.route('/centros-costo/buscar')
@login_required
def buscar_centros_costo():
    q = _clean(request.args.get('q'))
    q_like = f'%{q}%'

    rows = execute_query(
        """
        SELECT
            id,
            codigo,
            nombre
        FROM contabilidad.centro_costo
        WHERE activo = TRUE
          AND (
                %s = ''
                OR codigo ILIKE %s
                OR nombre ILIKE %s
              )
        ORDER BY codigo ASC
        LIMIT 30
        """,
        (q, q_like, q_like),
        fetchall=True
    )

    results = [{
        'id': row['id'],
        'text': f"{row['codigo']} | {row['nombre']}",
        'codigo': row['codigo'],
        'nombre': row['nombre'],
    } for row in rows]

    return jsonify({'results': results})


@comprobantes_bp.route('/catalogos')
@login_required
def catalogos():
    monedas = execute_query(
        """
        SELECT codigo, nombre, simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        ORDER BY CASE WHEN codigo = 'BOB' THEN 0 ELSE 1 END, codigo ASC
        """,
        fetchall=True
    )

    unidades = execute_query(
        """
        SELECT id, codigo, nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY codigo ASC, nombre ASC
        """,
        fetchall=True
    )

    rubros = _listar_rubros()
    publicidad_elementos = _listar_elementos_publicitarios()

    return jsonify({
        'ok': True,
        'data': {
            'monedas': _json_ready(monedas),
            'unidades_negocio': _json_ready(unidades),
            'rubros': _json_ready(rubros),
            'publicidad_elementos': _json_ready(publicidad_elementos),
        }
    })


@comprobantes_bp.route('/tipo-cambio-sugerido')
@login_required
def tipo_cambio_sugerido():
    fecha = _parse_date(request.args.get('fecha'))
    moneda_codigo = _upper_clean(request.args.get('moneda_codigo'))

    if not fecha:
        return _make_error('Debe indicar una fecha válida.')
    if not moneda_codigo:
        return _make_error('Debe indicar una moneda.')

    tipo_cambio = _tipo_cambio_para_fecha(fecha, moneda_codigo)

    if tipo_cambio['valor'] is None:
        return jsonify({
            'ok': False,
            'msg': 'No existe tipo de cambio registrado para la moneda y fecha solicitadas.',
            'data': _json_ready(tipo_cambio),
        }), 404

    return jsonify({'ok': True, 'data': _json_ready(tipo_cambio)})


@comprobantes_bp.route('/crear', methods=['POST'])
@login_required
def crear():
    data = request.get_json() or {}
    payload, error = _validar_payload(data)
    if error:
        return _make_error(error)

    try:
        asiento_id = _crear_asiento_manual(payload)
        return jsonify({
            'ok': True,
            'msg': f'Comprobante {asiento_id} registrado en BORRADOR.',
            'asiento_id': asiento_id,
        })
    except Exception as exc:
        return _make_error(f'No se pudo registrar el comprobante: {exc}', 500)


@comprobantes_bp.route('/actualizar/<int:asiento_id>', methods=['PUT'])
@login_required
def actualizar(asiento_id: int):
    asiento = _obtener_asiento_basico(asiento_id)
    if not asiento:
        return _make_error('El comprobante solicitado no existe.', 404)
    if not bool(asiento.get('puede_editar')):
        return _make_error('Solo se pueden editar comprobantes manuales en BORRADOR.')

    data = request.get_json() or {}
    payload, error = _validar_payload(data)
    if error:
        return _make_error(error)

    try:
        _actualizar_asiento_manual(asiento_id, payload, asiento.get('atributos'))
        return jsonify({
            'ok': True,
            'msg': f'Comprobante {asiento_id} actualizado correctamente.',
        })
    except ValueError as exc:
        return _make_error(str(exc), 409)
    except Exception as exc:
        return _make_error(f'No se pudo actualizar el comprobante: {exc}', 500)


@comprobantes_bp.route('/confirmar/<int:asiento_id>', methods=['POST'])
@login_required
def confirmar(asiento_id: int):
    asiento = _obtener_asiento_basico(asiento_id)
    if not asiento:
        return _make_error('El comprobante solicitado no existe.', 404)

    ok, error = _marcar_estado_manual(asiento, ESTADO_CONFIRMADO)
    if not ok:
        return _make_error(error or 'No se pudo confirmar el comprobante.')

    return jsonify({'ok': True, 'msg': f'Comprobante {asiento_id} confirmado correctamente.'})


@comprobantes_bp.route('/eliminar/<int:asiento_id>', methods=['POST'])
@login_required
def eliminar(asiento_id: int):
    asiento = _obtener_asiento_basico(asiento_id)
    if not asiento:
        return _make_error('El comprobante solicitado no existe.', 404)

    ok, error = _eliminar_asiento_manual(asiento)
    if not ok:
        return _make_error(error or 'No se pudo eliminar el comprobante.')

    return jsonify({'ok': True, 'msg': f'Comprobante {asiento_id} eliminado correctamente.'})

# ------------------------------------------------------------
# AYUDA DEL MÓDULO
# ------------------------------------------------------------
@comprobantes_bp.route('/help')
@login_required
def help():
    return render_template('comprobantes_help.html')