# ============================================================
# DXT CONTA - Módulo Facturas Electrónicas
# Importación desde Excel / XLS HTML del sistema externo
# ============================================================

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Response, jsonify, render_template, request, session
from psycopg2.extras import Json

from database.db_manager import DatabaseManager
from modules.facturas_electronicas import facturas_electronicas_bp
from modules.reportes_rapidos.core.utils import logo_path
from utils.decorators import login_required, roles_required
from utils.documentos_pdf import build_accounting_document_pdf, format_date, format_money

ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
CUANTIA = Decimal('0.01')


# ============================================================
# Helpers generales
# ============================================================

def _clean(value):
    return str(value or '').strip()


def _upper_clean(value):
    return _clean(value).upper()


def _normalize_cuf(value):
    """Normaliza CUF para que marcadores de carga inicial no actúen como clave."""
    raw = _clean(value)[:255]
    if not raw:
        return None
    marker = raw.upper().replace(' ', '')
    if marker in {'0', '00', '000', 'CERO', 'SINCUF', 'S/NCUF', 'N/A', 'NA'}:
        return None
    return raw


def _es_saldo_inicial_por_cuf(value):
    raw = _clean(value)
    marker = raw.upper().replace(' ', '')
    return marker in {'0', '00', '000', 'CERO', 'SINCUF', 'S/NCUF', 'N/A', 'NA'}


def _business_key_code(nit_emisor, numero_factura, fecha_emision, nit_cliente):
    fecha_txt = fecha_emision.isoformat() if hasattr(fecha_emision, 'isoformat') else _clean(fecha_emision)
    return '|'.join([
        _upper_clean(nit_emisor),
        _upper_clean(numero_factura),
        fecha_txt,
        _upper_clean(nit_cliente),
    ])[:100]


def _can_edit():
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except Exception:
        return False


def _to_decimal(value, default='0'):
    if value in (None, '', 'null'):
        return Decimal(default).quantize(CUANTIA, rounding=ROUND_HALF_UP)

    text = str(value).strip()
    if not text:
        return Decimal(default).quantize(CUANTIA, rounding=ROUND_HALF_UP)

    text = text.replace('Bs.', '').replace('Bs', '').replace(' ', '')
    if ',' in text and '.' in text:
        text = text.replace(',', '')
    elif ',' in text:
        text = text.replace(',', '.')

    try:
        return Decimal(text).quantize(CUANTIA, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal(default).quantize(CUANTIA, rounding=ROUND_HALF_UP)


def _to_money(value):
    return float(_to_decimal(value))


def _parse_date_iso(value):
    value = _clean(value)
    if not value:
        return None

    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _build_filters():
    return {
        'q': _clean(request.args.get('q')),
        'fecha_desde': _clean(request.args.get('fecha_desde')),
        'fecha_hasta': _clean(request.args.get('fecha_hasta')),
        'unidad_negocio_id': _clean(request.args.get('unidad_negocio_id')),
    }


def _buscar_cliente(cursor, nit_cliente):
    nit_cliente = _clean(nit_cliente)
    if not nit_cliente:
        return None

    cursor.execute(
        """
        SELECT
            a.id,
            a.ref_id AS cliente_empresa_id,
            COALESCE(a.origen_tabla, '') AS origen_tabla
        FROM contabilidad.auxiliar a
        WHERE a.tipo = 'CLIENTE'
          AND a.activo = TRUE
          AND UPPER(TRIM(COALESCE(a.nit_ci, ''))) = UPPER(TRIM(%s))
        ORDER BY a.es_ocasional ASC, a.id ASC
        LIMIT 1
        """,
        (nit_cliente,)
    )
    row = cursor.fetchone()
    if not row:
        return None

    return {
        'auxiliar_id': row['id'],
        'cliente_empresa_id': row['cliente_empresa_id']
        if _upper_clean(row['origen_tabla']) == 'CLIENTES.EMPRESAS'
        else None,
    }


def _buscar_unidad_por_nit(cursor, nit_emisor):
    nit_emisor = _clean(nit_emisor)
    if not nit_emisor:
        return None

    cursor.execute(
        """
        SELECT
            un.id,
            COALESCE(un.codigo, '') AS codigo,
            COALESCE(un.nombre, '') AS nombre,
            COALESCE(un.nit, '') AS nit
        FROM contabilidad.unidad_negocio un
        WHERE un.activo = TRUE
          AND UPPER(TRIM(COALESCE(un.nit, ''))) = UPPER(TRIM(%s))
        LIMIT 1
        """,
        (nit_emisor,)
    )
    row = cursor.fetchone()
    if not row:
        return None

    return {
        'id': row['id'],
        'codigo': row['codigo'],
        'nombre': row['nombre'],
        'nit': row['nit'],
    }



def _get_unidad_negocio_activa(cursor, unidad_negocio_id):
    cursor.execute(
        """
        SELECT
            un.id,
            COALESCE(un.codigo, '') AS codigo,
            COALESCE(un.nombre, '') AS nombre,
            COALESCE(un.nit, '') AS nit
        FROM contabilidad.unidad_negocio un
        WHERE un.id = %s
          AND un.activo = TRUE
        LIMIT 1
        """,
        (unidad_negocio_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        'id': row['id'],
        'codigo': row['codigo'],
        'nombre': row['nombre'],
        'nit': row['nit'],
    }


def _get_default_account(cursor, purpose):
    """Devuelve una cuenta postable sugerida para contabilizar facturas.

    purpose:
    - cobrar: cuenta por cobrar al debe.
    - ingreso: cuenta de ingresos al haber.
    """
    if purpose == 'cobrar':
        candidates = [
            ('exact', 'CUENTAS POR COBRAR', None),
            ('like', '%CUENTAS POR COBRAR%', None),
            ('like', '%CUENTA POR COBRAR%', None),
            ('like', '%POR COBRAR%', 'ACTIVO'),
        ]
    else:
        candidates = [
            ('exact', 'VENTAS DE SERVICIOS', 'INGRESO'),
            ('like', '%VENTAS DE SERVICIOS%', 'INGRESO'),
            ('like', '%VENTA%SERVICIO%', 'INGRESO'),
            ('exact', 'INGRESOS', None),
            ('like', '%INGRESOS%', 'INGRESO'),
            ('like', '%INGRESO%', 'INGRESO'),
            ('tipo', None, 'INGRESO'),
        ]

    for mode, text, tipo in candidates:
        params = []
        where = ['activo = TRUE', 'es_postable = TRUE']
        if mode == 'exact':
            where.append('UPPER(TRIM(nombre)) = UPPER(TRIM(%s))')
            params.append(text)
        elif mode == 'like':
            where.append('UPPER(nombre) LIKE UPPER(%s)')
            params.append(text)
        if tipo:
            where.append('tipo = %s::contabilidad.tipo_cuenta_enum')
            params.append(tipo)
        cursor.execute(
            f"""
            SELECT codigo, nombre, naturaleza, requiere_auxiliar
            FROM contabilidad.cuenta
            WHERE {' AND '.join(where)}
            ORDER BY
                CASE
                    WHEN UPPER(TRIM(nombre)) = UPPER(TRIM(%s)) THEN 0
                    ELSE 1
                END,
                LENGTH(codigo), codigo
            LIMIT 1
            """,
            tuple(params + [text or '']),
        )
        row = cursor.fetchone()
        if row:
            return {
                'codigo': row['codigo'],
                'nombre': row['nombre'],
                'text': f"{row['codigo']} · {row['nombre']}",
                'naturaleza': row['naturaleza'],
                'requiere_auxiliar': bool(row['requiere_auxiliar']),
            }
    return None


def _default_accounts(cursor):
    return {
        'cuenta_cobrar': _get_default_account(cursor, 'cobrar'),
        'cuenta_contra': _get_default_account(cursor, 'ingreso'),
    }

def _resolver_emisor_importacion(cursor, metadata):
    nit_emisor = _clean(metadata.get('nit_emisor'))
    razon_social_emisor = _clean(metadata.get('razon_social_emisor'))
    sucursal_cabecera = _clean(metadata.get('sucursal_cabecera'))

    if not nit_emisor:
        raise ValueError('El archivo no contiene NIT emisor válido en la celda D1.')

    unidad = _buscar_unidad_por_nit(cursor, nit_emisor)
    if not unidad:
        raise ValueError(
            f'No existe una unidad de negocio activa con NIT "{nit_emisor}". '
            'Debes registrar esa unidad antes de importar las facturas emitidas.'
        )

    return {
        'nit_emisor': nit_emisor,
        'razon_social_emisor': razon_social_emisor,
        'sucursal_cabecera': sucursal_cabecera,
        'unidad_negocio_id': unidad['id'],
        'unidad_negocio_codigo': unidad['codigo'],
        'unidad_negocio_nombre': unidad['nombre'],
    }


def _resumen_general(cursor, filters=None):
    filters = filters or {}
    params = []
    where = ["f.origen = 'EXTERNO'"]

    if filters.get('fecha_desde'):
        where.append('f.fecha_emision >= %s')
        params.append(filters['fecha_desde'])

    if filters.get('fecha_hasta'):
        where.append('f.fecha_emision <= %s')
        params.append(filters['fecha_hasta'])

    if filters.get('unidad_negocio_id'):
        where.append('f.unidad_negocio_id = %s')
        params.append(filters['unidad_negocio_id'])

    cursor.execute(
        f"""
        WITH reg AS (
            SELECT
                factura_electronica_id,
                COALESCE(SUM(CASE WHEN activo = TRUE THEN monto ELSE 0 END), 0) AS total_regularizado,
                BOOL_OR(activo = TRUE AND tipo_regularizacion = 'CIERRE_MANUAL') AS cierre_manual_activo
            FROM contabilidad.factura_regularizacion
            GROUP BY factura_electronica_id
        ), apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
            GROUP BY fa.factura_electronica_id
        ), doc AS (
            SELECT origen_id AS factura_electronica_id, asiento_id
            FROM contabilidad.documento_asiento
            WHERE tabla_origen = 'contabilidad.factura_electronica'
        ), base AS (
            SELECT
                f.id,
                f.estado,
                COALESCE(reg.cierre_manual_activo, FALSE) AS cierre_manual_activo,
                doc.asiento_id,
                CASE
                    WHEN f.estado = 'ANULADA' THEN 0
                    ELSE GREATEST(
                        COALESCE(f.importe_total, 0)
                        - COALESCE(reg.total_regularizado, 0)
                        - COALESCE(apps.total_aplicado, 0),
                        0
                    )
                END AS saldo_operativo
            FROM contabilidad.factura_electronica f
            LEFT JOIN reg ON reg.factura_electronica_id = f.id
            LEFT JOIN apps ON apps.factura_electronica_id = f.id
            LEFT JOIN doc ON doc.factura_electronica_id = f.id
            WHERE {' AND '.join(where)}
        )
        SELECT
            COUNT(*) FILTER (WHERE estado <> 'ANULADA') AS activas_total,
            COUNT(*) FILTER (
                WHERE estado <> 'ANULADA'
                  AND cierre_manual_activo = FALSE
                  AND asiento_id IS NULL
                  AND saldo_operativo > 0
            ) AS pendientes_contabilizar,
            COUNT(*) FILTER (
                WHERE estado <> 'ANULADA'
                  AND cierre_manual_activo = FALSE
                  AND asiento_id IS NOT NULL
                  AND saldo_operativo > 0
            ) AS contabilizadas_pendientes,
            COUNT(*) FILTER (
                WHERE estado <> 'ANULADA'
                  AND cierre_manual_activo = FALSE
                  AND saldo_operativo <= 0
            ) AS cobradas_total,
            COUNT(*) FILTER (WHERE cierre_manual_activo = TRUE) AS cerradas_manual,
            COUNT(*) FILTER (WHERE estado = 'ANULADA') AS anuladas_historicas
        FROM base
        """,
        tuple(params) if params else None,
    )
    row = cursor.fetchone() or {}
    return {
        'activas_total': int(row.get('activas_total') or 0),
        'pendientes_contabilizar': int(row.get('pendientes_contabilizar') or 0),
        'contabilizadas_pendientes': int(row.get('contabilizadas_pendientes') or 0),
        'cobradas_total': int(row.get('cobradas_total') or 0),
        'cerradas_manual': int(row.get('cerradas_manual') or 0),
        'anuladas_historicas': int(row.get('anuladas_historicas') or 0),
        # Compatibilidad con la interfaz anterior si algún JS local lo esperaba.
        'pendientes_vinculacion': int(row.get('pendientes_contabilizar') or 0),
        'listas_cobro': int(row.get('contabilizadas_pendientes') or 0),
    }


def _listar_facturas_operativas(cursor, filters):
    params = []
    where = ["f.origen = 'EXTERNO'"]

    if filters['fecha_desde']:
        where.append('f.fecha_emision >= %s')
        params.append(filters['fecha_desde'])

    if filters['fecha_hasta']:
        where.append('f.fecha_emision <= %s')
        params.append(filters['fecha_hasta'])

    if filters['unidad_negocio_id']:
        where.append('f.unidad_negocio_id = %s')
        params.append(filters['unidad_negocio_id'])

    if filters['q']:
        like_value = f"%{filters['q']}%"
        where.append(
            """
            (
                UPPER(COALESCE(f.numero_factura, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(f.nit_cliente, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(f.nombre_cliente, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(f.cuf, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(f.nit_emisor, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(un.codigo, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(un.nombre, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(aux.nombre, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(aux.nit_ci, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(cta_cobrar.codigo, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(cta_cobrar.nombre, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(cta_contra.codigo, '')) LIKE UPPER(%s)
                OR UPPER(COALESCE(cta_contra.nombre, '')) LIKE UPPER(%s)
            )
            """
        )
        params.extend([
            like_value, like_value, like_value, like_value, like_value,
            like_value, like_value, like_value, like_value, like_value,
            like_value, like_value, like_value,
        ])

    sql = f"""
        WITH reg AS (
            SELECT
                factura_electronica_id,
                COALESCE(SUM(CASE WHEN activo = TRUE THEN monto ELSE 0 END), 0) AS total_regularizado,
                BOOL_OR(activo = TRUE AND tipo_regularizacion = 'CIERRE_MANUAL') AS cierre_manual_activo,
                COUNT(*) FILTER (WHERE activo = TRUE) AS regularizaciones_activas
            FROM contabilidad.factura_regularizacion
            GROUP BY factura_electronica_id
        ), apps AS (
            SELECT
                fa.factura_electronica_id,
                COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado,
                COUNT(*) AS aplicaciones_activas
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
            GROUP BY fa.factura_electronica_id
        ), doc AS (
            SELECT origen_id AS factura_electronica_id, asiento_id
            FROM contabilidad.documento_asiento
            WHERE tabla_origen = 'contabilidad.factura_electronica'
        )
        SELECT
            f.id,
            TO_CHAR(f.fecha_emision, 'YYYY-MM-DD') AS fecha_emision_iso,
            TO_CHAR(f.fecha_emision, 'DD/MM/YYYY') AS fecha_emision,
            COALESCE(f.numero_factura, '') AS numero_factura,
            COALESCE(f.cuf, '') AS cuf,
            COALESCE(f.nit_cliente, '') AS nit_cliente,
            COALESCE(f.nombre_cliente, '') AS nombre_cliente,
            ROUND(f.importe_total::numeric, 2) AS importe_total,
            ROUND(COALESCE(f.saldo_pendiente, 0)::numeric, 2) AS saldo_registrado,
            ROUND((
                CASE
                    WHEN f.estado = 'ANULADA' THEN 0
                    ELSE GREATEST(
                        COALESCE(f.importe_total, 0)
                        - COALESCE(reg.total_regularizado, 0)
                        - COALESCE(apps.total_aplicado, 0),
                        0
                    )
                END
            )::numeric, 2) AS saldo_pendiente,
            ROUND(COALESCE(apps.total_aplicado, 0)::numeric, 2) AS total_aplicado,
            ROUND(COALESCE(reg.total_regularizado, 0)::numeric, 2) AS total_regularizado,
            COALESCE(f.estado::TEXT, '') AS estado,
            COALESCE(f.nit_emisor, '') AS nit_emisor,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre,
            COALESCE(f.payload->>'sucursal', '') AS sucursal,
            COALESCE(f.payload->>'metodo_pago', '') AS metodo_pago,
            COALESCE(f.payload->>'usuario', '') AS usuario_facturacion,
            COALESCE(f.es_saldo_inicial, FALSE) AS es_saldo_inicial,
            COALESCE(f.cuenta_cobrar_codigo, '') AS cuenta_cobrar_codigo,
            COALESCE(cta_cobrar.nombre, '') AS cuenta_cobrar_nombre,
            COALESCE(f.cuenta_contra_codigo, '') AS cuenta_contra_codigo,
            COALESCE(cta_contra.nombre, '') AS cuenta_contra_nombre,
            COALESCE(aux.id, 0) AS auxiliar_id,
            COALESCE(aux.nombre, '') AS auxiliar_nombre,
            COALESCE(aux.nit_ci, '') AS auxiliar_nit_ci,
            TO_CHAR(f.fecha_contabilizacion, 'YYYY-MM-DD') AS fecha_contabilizacion,
            doc.asiento_id,
            COALESCE(reg.cierre_manual_activo, FALSE) AS cierre_manual_activo,
            COALESCE(reg.regularizaciones_activas, 0) AS regularizaciones_activas,
            COALESCE(apps.aplicaciones_activas, 0) AS aplicaciones_activas,
            CASE
                WHEN f.estado = 'ANULADA' THEN 'ANULADA'
                WHEN COALESCE(reg.cierre_manual_activo, FALSE) = TRUE THEN 'CERRADA_TESORERIA'
                WHEN GREATEST(
                    COALESCE(f.importe_total, 0)
                    - COALESCE(reg.total_regularizado, 0)
                    - COALESCE(apps.total_aplicado, 0),
                    0
                ) <= 0 THEN 'COBRADA_TOTAL'
                WHEN doc.asiento_id IS NOT NULL THEN 'CONTABILIZADA'
                WHEN f.cliente_auxiliar_id IS NULL THEN 'RECIBIDA'
                ELSE 'DISPONIBLE'
            END AS proceso_estado
        FROM contabilidad.factura_electronica f
        LEFT JOIN contabilidad.unidad_negocio un
               ON un.id = f.unidad_negocio_id
        LEFT JOIN contabilidad.auxiliar aux
               ON aux.id = f.cliente_auxiliar_id
        LEFT JOIN contabilidad.cuenta cta_cobrar
               ON cta_cobrar.codigo = f.cuenta_cobrar_codigo
        LEFT JOIN contabilidad.cuenta cta_contra
               ON cta_contra.codigo = f.cuenta_contra_codigo
        LEFT JOIN reg ON reg.factura_electronica_id = f.id
        LEFT JOIN apps ON apps.factura_electronica_id = f.id
        LEFT JOIN doc ON doc.factura_electronica_id = f.id
        WHERE {' AND '.join(where)}
        ORDER BY f.fecha_emision DESC, f.numero_factura DESC, f.id DESC
    """
    cursor.execute(sql, tuple(params) if params else None)

    items = []
    for row in cursor.fetchall():
        items.append({
            'id': row['id'],
            'fecha_emision': row['fecha_emision'],
            'fecha_emision_iso': row['fecha_emision_iso'],
            'numero_factura': row['numero_factura'],
            'cuf': row['cuf'],
            'nit_cliente': row['nit_cliente'],
            'nombre_cliente': row['nombre_cliente'],
            'importe_total': _to_money(row['importe_total']),
            'saldo_pendiente': _to_money(row['saldo_pendiente']),
            'saldo_registrado': _to_money(row.get('saldo_registrado')),
            'total_aplicado': _to_money(row['total_aplicado']),
            'total_regularizado': _to_money(row['total_regularizado']),
            'estado': row['estado'],
            'proceso_estado': row['proceso_estado'],
            'nit_emisor': row['nit_emisor'],
            'unidad_negocio_codigo': row['unidad_negocio_codigo'],
            'unidad_negocio_nombre': row['unidad_negocio_nombre'],
            'sucursal': row['sucursal'],
            'metodo_pago': row['metodo_pago'],
            'usuario_facturacion': row['usuario_facturacion'],
            'es_saldo_inicial': bool(row['es_saldo_inicial']),
            'cuenta_cobrar_codigo': row['cuenta_cobrar_codigo'],
            'cuenta_cobrar_nombre': row['cuenta_cobrar_nombre'],
            'cuenta_contra_codigo': row['cuenta_contra_codigo'],
            'cuenta_contra_nombre': row['cuenta_contra_nombre'],
            'auxiliar_id': row['auxiliar_id'] if int(row['auxiliar_id'] or 0) > 0 else None,
            'auxiliar_nombre': row['auxiliar_nombre'],
            'auxiliar_nit_ci': row['auxiliar_nit_ci'],
            'fecha_contabilizacion': row['fecha_contabilizacion'],
            'asiento_id': row['asiento_id'],
            'cierre_manual_activo': bool(row['cierre_manual_activo']),
            'regularizaciones_activas': int(row['regularizaciones_activas'] or 0),
            'aplicaciones_activas': int(row['aplicaciones_activas'] or 0),
        })
    return items


def _listar_unidades_negocio_activas(cursor):
    cursor.execute(
        """
        SELECT
            un.id,
            COALESCE(un.codigo, '') AS codigo,
            COALESCE(un.nombre, '') AS nombre,
            COALESCE(un.nit, '') AS nit
        FROM contabilidad.unidad_negocio un
        WHERE un.activo = TRUE
        ORDER BY un.nombre ASC, un.codigo ASC
        """
    )
    return [
        {
            'id': row['id'],
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'nit': row['nit'],
        }
        for row in cursor.fetchall()
    ]


# ============================================================
# Helpers de importación
# ============================================================

def _validar_fila(row):
    numero_factura = _clean(row.get('numero_factura'))[:100]
    fecha_emision = _parse_date_iso(row.get('fecha_emision'))
    estado_archivo = _clean(row.get('estado_archivo') or row.get('estado'))[:100]
    cuf_raw = _clean(row.get('cuf'))[:255]
    cuf = _normalize_cuf(cuf_raw)
    es_saldo_inicial = _es_saldo_inicial_por_cuf(cuf_raw)
    nit_cliente = _clean(row.get('nit_cliente'))[:50]
    nombre_cliente = _clean(row.get('nombre_cliente'))[:200]
    sucursal = _clean(row.get('sucursal'))[:200]
    punto_venta = _clean(row.get('punto_venta'))[:200]
    tipo_emision = _clean(row.get('tipo_emision'))[:100]
    metodo_pago = _clean(row.get('metodo_pago'))[:100]
    usuario = _clean(row.get('usuario'))[:200]
    fila_origen = row.get('fila_origen')

    if not numero_factura:
        return None, 'La fila no tiene número de factura.'

    if not fecha_emision:
        return None, f'La factura {numero_factura} no tiene una fecha válida.'

    importe_total = _to_decimal(row.get('importe_total'))
    subtotal = _to_decimal(row.get('subtotal') or row.get('importe_total'))
    descuento = _to_decimal(row.get('descuento'))
    debito_fiscal = _to_decimal(row.get('debito_fiscal'))
    importe_base = _to_decimal(row.get('importe_base_debito') or row.get('importe_total'))

    if importe_total < 0:
        return None, f'La factura {numero_factura} tiene un importe total negativo.'

    payload = {
        'numero_factura': numero_factura,
        'fecha_emision': fecha_emision.isoformat(),
        'estado_archivo': estado_archivo,
        'cuf': cuf,
        'cuf_original': cuf_raw or None,
        'es_saldo_inicial': es_saldo_inicial,
        'nit_cliente': nit_cliente or None,
        'nombre_cliente': nombre_cliente or None,
        'sucursal': sucursal or None,
        'punto_venta': punto_venta or None,
        'tipo_emision': tipo_emision or None,
        'metodo_pago': metodo_pago or None,
        'usuario': usuario or None,
        'importe_total': str(importe_total),
        'subtotal': str(subtotal),
        'descuento': str(descuento),
        'debito_fiscal': str(debito_fiscal),
        'importe_base_debito': str(importe_base),
        'fila_origen': fila_origen,
        'raw': row.get('raw') if isinstance(row.get('raw'), dict) else {},
    }
    return payload, None


def _build_payload_db(payload, metadata, emisor):
    return {
        'sucursal': payload['sucursal'],
        'punto_venta': payload['punto_venta'],
        'tipo_emision': payload['tipo_emision'],
        'metodo_pago': payload['metodo_pago'],
        'usuario': payload['usuario'],
        'estado_archivo': payload['estado_archivo'],
        'debito_fiscal': payload['debito_fiscal'],
        'importe_base_debito': payload['importe_base_debito'],
        'file_name': metadata.get('nombre_archivo'),
        'fila_origen': payload['fila_origen'],
        'cuf_original': payload.get('cuf_original'),
        'es_saldo_inicial': payload.get('es_saldo_inicial'),
        'importado_por': session.get('usuario_nombre', ''),
        'importado_en': datetime.now().isoformat(),
        'nit_emisor': emisor['nit_emisor'],
        'razon_social_emisor': emisor['razon_social_emisor'],
        'sucursal_cabecera': emisor['sucursal_cabecera'],
        'unidad_negocio_id': emisor['unidad_negocio_id'],
        'unidad_negocio_codigo': emisor['unidad_negocio_codigo'],
        'unidad_negocio_nombre': emisor['unidad_negocio_nombre'],
        'raw': payload['raw'],
    }


def _desvincular_factura_anulada(cursor, factura_id):
    """Valida que una factura pueda marcarse anulada desde importación.

    No elimina aplicaciones ni vínculos financieros. Si una factura ya tiene
    cobros, ventas, regularizaciones activas o asiento contable, la anulación
    importada debe revisarse manualmente para no romper trazabilidad contable.
    """
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM contabilidad.factura_aplicacion fa
        LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
        LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
        WHERE fa.factura_electronica_id = %s
          AND (
                (fa.cobro_id IS NOT NULL AND COALESCE(c.estado::TEXT, '') <> 'ANULADO')
             OR (fa.venta_id IS NOT NULL AND COALESCE(v.estado::TEXT, '') <> 'ANULADO')
          )
        """,
        (factura_id,)
    )
    aplicaciones = int((cursor.fetchone() or {}).get('total') or 0)

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM contabilidad.factura_regularizacion
        WHERE factura_electronica_id = %s
          AND activo = TRUE
        """,
        (factura_id,)
    )
    regularizaciones = int((cursor.fetchone() or {}).get('total') or 0)

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM contabilidad.documento_asiento
        WHERE tabla_origen = 'contabilidad.factura_electronica'
          AND origen_id = %s
        """,
        (factura_id,)
    )
    asientos = int((cursor.fetchone() or {}).get('total') or 0)

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM contabilidad.venta
        WHERE factura_electronica_id = %s
          AND COALESCE(estado::TEXT, '') <> 'ANULADO'
        """,
        (factura_id,)
    )
    ventas = int((cursor.fetchone() or {}).get('total') or 0)

    if aplicaciones or regularizaciones or asientos or ventas:
        detalles = []
        if aplicaciones:
            detalles.append(f'{aplicaciones} aplicación(es) de cobro/venta')
        if regularizaciones:
            detalles.append(f'{regularizaciones} regularización(es) activa(s)')
        if asientos:
            detalles.append(f'{asientos} asiento(s) contable(s)')
        if ventas:
            detalles.append(f'{ventas} venta(s) vinculada(s)')
        raise ValueError(
            'La factura importada como ANULADA ya tiene movimiento en DXT-CONTA: '
            + ', '.join(detalles)
            + '. No se anuló automáticamente; debe revisarse y revertirse por el flujo correspondiente.'
        )

    return {
        'aplicaciones': 0,
        'ventas': 0,
        'regularizaciones': 0,
        'asientos': 0,
    }


def _procesar_fila(cursor, row, metadata, emisor):
    payload, error = _validar_fila(row)
    if error:
        return {
            'accion': 'error',
            'mensaje': error,
            'fila_origen': row.get('fila_origen'),
        }

    numero_factura = payload['numero_factura']
    fecha_emision = _parse_date_iso(payload['fecha_emision'])
    es_anulada = 'ANUL' in _upper_clean(payload['estado_archivo'])

    cliente_data = _buscar_cliente(cursor, payload['nit_cliente'])
    cliente_auxiliar_id = cliente_data['auxiliar_id'] if cliente_data else None
    cliente_empresa_id = cliente_data['cliente_empresa_id'] if cliente_data else None
    estado_destino = 'ANULADA' if es_anulada else ('DISPONIBLE' if cliente_auxiliar_id else 'RECIBIDA')
    saldo_pendiente = Decimal('0.00') if es_anulada else _to_decimal(payload['importe_total'])

    cursor.execute(
        """
        SELECT
            f.id,
            f.estado,
            f.payload,
            f.cliente_auxiliar_id,
            f.cliente_empresa_id
        FROM contabilidad.factura_electronica f
        WHERE f.origen = 'EXTERNO'
          AND UPPER(TRIM(COALESCE(f.nit_emisor, ''))) = UPPER(TRIM(%s))
          AND UPPER(TRIM(f.numero_factura)) = UPPER(TRIM(%s))
          AND f.fecha_emision = %s
          AND UPPER(TRIM(COALESCE(f.nit_cliente, ''))) = UPPER(TRIM(COALESCE(%s, '')))
        LIMIT 1
        """,
        (emisor['nit_emisor'], numero_factura, fecha_emision, payload['nit_cliente'] or None)
    )
    existente = cursor.fetchone()

    payload_db = _build_payload_db(payload, metadata, emisor)

    if existente:
        if es_anulada and existente['estado'] != 'ANULADA':
            desvinculacion = _desvincular_factura_anulada(cursor, existente['id'])
            payload_actual = existente.get('payload') if isinstance(existente.get('payload'), dict) else {}
            payload_actual = payload_actual.copy()
            payload_actual['ultima_anulacion_importada'] = payload_db

            cursor.execute(
                """
                UPDATE contabilidad.factura_electronica
                SET
                    estado = 'ANULADA',
                    saldo_pendiente = 0,
                    nit_emisor = %s,
                    unidad_negocio_id = %s,
                    payload = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (emisor['nit_emisor'], emisor['unidad_negocio_id'], Json(payload_actual), existente['id'])
            )
            return {
                'accion': 'actualizada_a_anulada',
                'mensaje': f'La factura {numero_factura} cambió a ANULADA.',
                'fila_origen': payload['fila_origen'],
                'desvinculadas_aplicaciones': desvinculacion['aplicaciones'],
                'desvinculadas_ventas': desvinculacion['ventas'],
            }

        return {
            'accion': 'omitida',
            'mensaje': f'La factura {numero_factura} ya estaba importada. Se omitió sin cambios.',
            'fila_origen': payload['fila_origen'],
            'desvinculadas_aplicaciones': 0,
            'desvinculadas_ventas': 0,
        }

    cursor.execute(
        """
        INSERT INTO contabilidad.factura_electronica (
            origen,
            codigo_externo,
            cliente_auxiliar_id,
            cliente_empresa_id,
            unidad_negocio_id,
            nit_emisor,
            nit_cliente,
            nombre_cliente,
            numero_factura,
            cuf,
            fecha_emision,
            moneda_codigo,
            subtotal,
            descuento,
            importe_total,
            saldo_pendiente,
            estado,
            payload,
            es_saldo_inicial,
            cuenta_cobrar_codigo,
            cuenta_contra_codigo,
            fecha_contabilizacion
        )
        VALUES (
            'EXTERNO',
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            'BOB',
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            NULL,
            NULL,
            NULL
        )
        """,
        (
            _business_key_code(emisor['nit_emisor'], numero_factura, fecha_emision, payload['nit_cliente'] or ''),
            cliente_auxiliar_id,
            cliente_empresa_id,
            emisor['unidad_negocio_id'],
            emisor['nit_emisor'],
            payload['nit_cliente'] or None,
            payload['nombre_cliente'] or None,
            numero_factura,
            payload['cuf'] or None,
            fecha_emision,
            _to_decimal(payload['subtotal']),
            _to_decimal(payload['descuento']),
            _to_decimal(payload['importe_total']),
            saldo_pendiente,
            estado_destino,
            Json(payload_db),
            bool(payload.get('es_saldo_inicial')),
        )
    )

    return {
        'accion': 'anulada_insertada' if es_anulada else 'insertada',
        'mensaje': (
            f'La factura anulada {numero_factura} fue registrada en histórico.'
            if es_anulada else
            f'La factura {numero_factura} fue importada.'
        ),
        'fila_origen': payload['fila_origen'],
        'desvinculadas_aplicaciones': 0,
        'desvinculadas_ventas': 0,
    }



# ============================================================
# Helpers de contabilización y cierre operativo
# ============================================================

def _usuario_actual():
    return (
        session.get('username')
        or session.get('usuario')
        or session.get('email')
        or session.get('user_id')
        or 'sistema'
    )


def _json_error(message, status=400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(payload), status


def _json_success(message, **kwargs):
    payload = {'success': True, 'message': message}
    payload.update(kwargs)
    return jsonify(payload)


def _parse_int(value, field_name, required=True):
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field_name}" debe ser numérico.')


def _normalize_text(value, field_name, max_len, required=False):
    value = _clean(value)
    if required and not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(value) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return value or None


def _decimal_from_db(value):
    return Decimal(str(value or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP)


def _saldo_operativo_factura(row):
    if not row or row.get('estado') == 'ANULADA':
        return Decimal('0.00')
    importe_total = _decimal_from_db(row.get('importe_total'))
    total_regularizado = _decimal_from_db(row.get('total_regularizado'))
    total_aplicado = _decimal_from_db(row.get('total_aplicado'))
    return max(
        importe_total - total_regularizado - total_aplicado,
        Decimal('0.00')
    ).quantize(CUANTIA, rounding=ROUND_HALF_UP)


def _get_factura_state(cursor, factura_id, for_update=False):
    lock = 'FOR UPDATE OF f' if for_update else ''
    cursor.execute(
        f"""
        WITH reg AS (
            SELECT
                COALESCE(SUM(CASE WHEN activo = TRUE THEN monto ELSE 0 END), 0) AS total_regularizado,
                BOOL_OR(activo = TRUE AND tipo_regularizacion = 'CIERRE_MANUAL') AS cierre_manual_activo
            FROM contabilidad.factura_regularizacion
            WHERE factura_electronica_id = %s
        ), apps AS (
            SELECT COALESCE(SUM(fa.monto_aplicado), 0) AS total_aplicado
            FROM contabilidad.factura_aplicacion fa
            LEFT JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            LEFT JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE fa.factura_electronica_id = %s
              AND (fa.cobro_id IS NULL OR c.estado <> 'ANULADO')
              AND (fa.venta_id IS NULL OR v.estado <> 'ANULADO')
        ), doc AS (
            SELECT asiento_id
            FROM contabilidad.documento_asiento
            WHERE tabla_origen = 'contabilidad.factura_electronica'
              AND origen_id = %s
            LIMIT 1
        )
        SELECT
            f.*,
            COALESCE(reg.total_regularizado, 0) AS total_regularizado,
            COALESCE(apps.total_aplicado, 0) AS total_aplicado,
            COALESCE(reg.cierre_manual_activo, FALSE) AS cierre_manual_activo,
            doc.asiento_id AS asiento_factura_id
        FROM contabilidad.factura_electronica f
        CROSS JOIN reg
        CROSS JOIN apps
        LEFT JOIN doc ON TRUE
        WHERE f.id = %s
        {lock}
        """,
        (factura_id, factura_id, factura_id, factura_id),
    )
    return cursor.fetchone()


def _get_account_row(cursor, codigo):
    cursor.execute(
        """
        SELECT codigo, nombre, naturaleza, requiere_auxiliar, es_postable, activo
        FROM contabilidad.cuenta
        WHERE codigo = %s
          AND activo = TRUE
          AND es_postable = TRUE
        LIMIT 1
        """,
        (_clean(codigo),),
    )
    return cursor.fetchone()


def _get_auxiliar_cliente(cursor, auxiliar_id):
    cursor.execute(
        """
        SELECT id, nombre, nit_ci, activo
        FROM contabilidad.auxiliar
        WHERE id = %s
          AND tipo = 'CLIENTE'
          AND activo = TRUE
        LIMIT 1
        """,
        (auxiliar_id,),
    )
    return cursor.fetchone()


def _recalcular_estado_factura(cursor, factura_id):
    factura = _get_factura_state(cursor, factura_id, for_update=False)
    if not factura:
        return
    if factura['estado'] == 'ANULADA':
        saldo = Decimal('0.00')
        nuevo_estado = 'ANULADA'
    else:
        importe_total = _decimal_from_db(factura['importe_total'])
        total_regularizado = _decimal_from_db(factura['total_regularizado'])
        total_aplicado = _decimal_from_db(factura['total_aplicado'])
        saldo = max(importe_total - total_regularizado - total_aplicado, Decimal('0.00')).quantize(CUANTIA)
        if saldo <= 0:
            nuevo_estado = 'COBRADA_TOTAL'
        elif (total_regularizado + total_aplicado) > 0:
            nuevo_estado = 'COBRADA_PARCIAL'
        elif factura.get('asiento_factura_id') or factura.get('cuenta_cobrar_codigo'):
            nuevo_estado = 'REGISTRADA'
        elif factura.get('cliente_auxiliar_id'):
            nuevo_estado = 'DISPONIBLE'
        else:
            nuevo_estado = 'RECIBIDA'

    cursor.execute(
        """
        UPDATE contabilidad.factura_electronica
        SET saldo_pendiente = %s,
            estado = %s::contabilidad.estado_factura_ext_enum,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (saldo, nuevo_estado, factura_id),
    )


# ============================================================
# Rutas
# ============================================================

@facturas_electronicas_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    return render_template(
        'facturas_electronicas_index.html',
        can_edit=_can_edit(),
    )


@facturas_electronicas_bp.route('/data')
@login_required
@roles_required(ROLES_LECTURA)
def data():
    filters = _build_filters()

    with DatabaseManager.get_cursor() as cursor:
        items = _listar_facturas_operativas(cursor, filters)
        resumen = _resumen_general(cursor, filters)

    return jsonify({
        'data': items,
        'resumen': resumen,
    })


@facturas_electronicas_bp.route('/unidades-negocio')
@login_required
@roles_required(ROLES_LECTURA)
def unidades_negocio():
    with DatabaseManager.get_cursor() as cursor:
        items = _listar_unidades_negocio_activas(cursor)
    return jsonify({'data': items})


@facturas_electronicas_bp.route('/api/cuentas-postables')
@login_required
@roles_required(ROLES_LECTURA)
def api_cuentas_postables():
    q = _clean(request.args.get('q'))
    params = []
    where = ['activo = TRUE', 'es_postable = TRUE']
    if q:
        like = f'%{q}%'
        where.append('(codigo ILIKE %s OR nombre ILIKE %s)')
        params.extend([like, like])
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT codigo, nombre, naturaleza, requiere_auxiliar
            FROM contabilidad.cuenta
            WHERE {' AND '.join(where)}
            ORDER BY codigo ASC
            LIMIT 80
            """,
            tuple(params) if params else None,
        )
        rows = cursor.fetchall()
    return jsonify({
        'results': [
            {
                'id': row['codigo'],
                'text': f"{row['codigo']} · {row['nombre']}",
                'codigo': row['codigo'],
                'nombre': row['nombre'],
                'naturaleza': row['naturaleza'],
                'requiere_auxiliar': bool(row['requiere_auxiliar']),
            }
            for row in rows
        ]
    })


@facturas_electronicas_bp.route('/api/auxiliares-clientes')
@login_required
@roles_required(ROLES_LECTURA)
def api_auxiliares_clientes():
    q = _clean(request.args.get('q'))
    params = []
    where = ["tipo = 'CLIENTE'", 'activo = TRUE']
    if q:
        like = f'%{q}%'
        where.append('(nombre ILIKE %s OR COALESCE(razon_social, \'\') ILIKE %s OR COALESCE(nit_ci, \'\') ILIKE %s)')
        params.extend([like, like, like])
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, nombre, COALESCE(nit_ci, '') AS nit_ci
            FROM contabilidad.auxiliar
            WHERE {' AND '.join(where)}
            ORDER BY nombre ASC
            LIMIT 80
            """,
            tuple(params) if params else None,
        )
        rows = cursor.fetchall()
    return jsonify({
        'results': [
            {
                'id': row['id'],
                'text': f"{row['nombre']} · NIT/CI {row['nit_ci'] or '—'}",
                'nombre': row['nombre'],
                'nit_ci': row['nit_ci'],
            }
            for row in rows
        ]
    })


@facturas_electronicas_bp.route('/api/<int:factura_id>')
@login_required
@roles_required(ROLES_LECTURA)
def api_factura_detalle(factura_id):
    with DatabaseManager.get_cursor() as cursor:
        row = _get_factura_state(cursor, factura_id, for_update=False)
        if not row:
            return _json_error('La factura no existe.', status=404)
        defaults = _default_accounts(cursor)
        return jsonify({
            'success': True,
            'data': {
                'id': row['id'],
                'numero_factura': row['numero_factura'],
                'fecha_emision': row['fecha_emision'].isoformat() if row['fecha_emision'] else None,
                'nit_cliente': row['nit_cliente'] or '',
                'nombre_cliente': row['nombre_cliente'] or '',
                'importe_total': _to_money(row['importe_total']),
                'saldo_pendiente': _to_money(_saldo_operativo_factura(row)),
                'estado': row['estado'],
                'cliente_auxiliar_id': row['cliente_auxiliar_id'],
                'cuenta_cobrar_codigo': row.get('cuenta_cobrar_codigo') or '',
                'cuenta_contra_codigo': row.get('cuenta_contra_codigo') or '',
                'default_cuenta_cobrar_codigo': (defaults.get('cuenta_cobrar') or {}).get('codigo') or '',
                'default_cuenta_cobrar_nombre': (defaults.get('cuenta_cobrar') or {}).get('nombre') or '',
                'default_cuenta_cobrar_text': (defaults.get('cuenta_cobrar') or {}).get('text') or '',
                'default_cuenta_contra_codigo': (defaults.get('cuenta_contra') or {}).get('codigo') or '',
                'default_cuenta_contra_nombre': (defaults.get('cuenta_contra') or {}).get('nombre') or '',
                'default_cuenta_contra_text': (defaults.get('cuenta_contra') or {}).get('text') or '',
                'fecha_contabilizacion': row.get('fecha_contabilizacion').isoformat() if row.get('fecha_contabilizacion') else None,
                'asiento_factura_id': row.get('asiento_factura_id'),
                'cierre_manual_activo': bool(row.get('cierre_manual_activo')),
                'total_aplicado': _to_money(row.get('total_aplicado')),
                'total_regularizado': _to_money(row.get('total_regularizado')),
            },
        })


@facturas_electronicas_bp.route('/api/<int:factura_id>/movimientos')
@login_required
@roles_required(ROLES_LECTURA)
def api_factura_movimientos(factura_id):
    with DatabaseManager.get_cursor() as cursor:
        factura = _get_factura_state(cursor, factura_id, for_update=False)
        if not factura:
            return _json_error('La factura no existe.', status=404)

        cursor.execute(
            """
            SELECT
                c.id AS cobro_id,
                c.fecha,
                COALESCE(c.glosa, '') AS glosa,
                COALESCE(c.referencia, '') AS referencia,
                COALESCE(c.estado::TEXT, '') AS estado,
                COALESCE(fa.monto_aplicado, 0) AS monto_aplicado
            FROM contabilidad.factura_aplicacion fa
            INNER JOIN contabilidad.cobro c ON c.id = fa.cobro_id
            WHERE fa.factura_electronica_id = %s
              AND c.estado <> 'ANULADO'
            ORDER BY c.fecha ASC, c.id ASC
            """,
            (factura_id,),
        )
        cobros = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                v.id AS venta_id,
                v.fecha,
                COALESCE(v.glosa, '') AS glosa,
                COALESCE(v.estado::TEXT, '') AS estado,
                COALESCE(fa.monto_aplicado, 0) AS monto_aplicado
            FROM contabilidad.factura_aplicacion fa
            INNER JOIN contabilidad.venta v ON v.id = fa.venta_id
            WHERE fa.factura_electronica_id = %s
              AND v.estado <> 'ANULADO'
            ORDER BY v.fecha ASC, v.id ASC
            """,
            (factura_id,),
        )
        ventas = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                id,
                tipo_regularizacion,
                monto,
                motivo,
                COALESCE(observacion, '') AS observacion,
                creado_en
            FROM contabilidad.factura_regularizacion
            WHERE factura_electronica_id = %s
              AND activo = TRUE
            ORDER BY creado_en ASC, id ASC
            """,
            (factura_id,),
        )
        regularizaciones = cursor.fetchall()

    movimientos = []
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')

    importe_total = Decimal('0.00') if factura.get('estado') == 'ANULADA' else _decimal_from_db(factura.get('importe_total'))
    total_debe += importe_total
    movimientos.append({
        'fecha': factura.get('fecha_emision').isoformat() if factura.get('fecha_emision') else '',
        'glosa': f"Factura {factura.get('numero_factura') or ''} - {factura.get('nombre_cliente') or factura.get('nit_cliente') or ''}",
        'origen': 'Registro de factura',
        'debe': _to_money(importe_total),
        'haber': 0.0,
    })

    for row in ventas:
        monto = _decimal_from_db(row.get('monto_aplicado'))
        total_haber += monto
        movimientos.append({
            'fecha': row.get('fecha').isoformat() if row.get('fecha') else '',
            'glosa': row.get('glosa') or f"Aplicación venta #{row.get('venta_id')}",
            'origen': f"Venta #{row.get('venta_id')}",
            'debe': 0.0,
            'haber': _to_money(monto),
        })

    for row in cobros:
        monto = _decimal_from_db(row.get('monto_aplicado'))
        total_haber += monto
        movimientos.append({
            'fecha': row.get('fecha').isoformat() if row.get('fecha') else '',
            'glosa': row.get('glosa') or row.get('referencia') or f"Cobro #{row.get('cobro_id')}",
            'origen': f"Cobro #{row.get('cobro_id')}",
            'debe': 0.0,
            'haber': _to_money(monto),
        })

    for row in regularizaciones:
        monto = _decimal_from_db(row.get('monto'))
        total_haber += monto
        movimientos.append({
            'fecha': row.get('creado_en').date().isoformat() if row.get('creado_en') else '',
            'glosa': row.get('motivo') or row.get('observacion') or row.get('tipo_regularizacion') or 'Regularización',
            'origen': row.get('tipo_regularizacion') or 'Regularización',
            'debe': 0.0,
            'haber': _to_money(monto),
        })

    saldo = max(total_debe - total_haber, Decimal('0.00')).quantize(CUANTIA, rounding=ROUND_HALF_UP)
    return jsonify({
        'success': True,
        'data': {
            'factura': {
                'id': factura.get('id'),
                'numero_factura': factura.get('numero_factura') or '',
                'cliente': factura.get('nombre_cliente') or factura.get('nit_cliente') or '',
                'estado': factura.get('estado') or '',
                'importe_total': _to_money(importe_total),
                'saldo_pendiente': _to_money(saldo),
            },
            'movimientos': movimientos,
            'totales': {
                'debe': _to_money(total_debe),
                'haber': _to_money(total_haber),
                'saldo': _to_money(saldo),
            },
        },
    })


@facturas_electronicas_bp.route('/api/<int:factura_id>/asiento')
@login_required
@roles_required(ROLES_LECTURA)
def api_factura_asiento(factura_id):
    with DatabaseManager.get_cursor() as cursor:
        factura = _get_factura_state(cursor, factura_id, for_update=False)
        if not factura:
            return _json_error('La factura no existe.', status=404)
        asiento_id = factura.get('asiento_factura_id')
        if not asiento_id:
            return _json_error('La factura todavía no tiene asiento contable asociado.', status=404)

        cursor.execute(
            """
            SELECT
                a.id,
                TO_CHAR(a.fecha, 'DD/MM/YYYY') AS fecha,
                COALESCE(a.estado::TEXT, '') AS estado,
                COALESCE(a.moneda_codigo, '') AS moneda_codigo,
                COALESCE(a.tipo_cambio, 1) AS tipo_cambio,
                COALESCE(a.glosa, '') AS glosa,
                COALESCE(a.referencia, '') AS referencia,
                COALESCE(a.modulo_origen, '') AS modulo_origen,
                COALESCE(un.codigo, '') AS unidad_codigo,
                COALESCE(un.nombre, '') AS unidad_nombre,
                TO_CHAR(a.creado_en, 'DD/MM/YYYY HH24:MI') AS creado_en
            FROM contabilidad.asiento a
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
            WHERE a.id = %s
            LIMIT 1
            """,
            (asiento_id,),
        )
        asiento = cursor.fetchone()
        if not asiento:
            return _json_error('No se encontró el asiento contable asociado.', status=404)

        cursor.execute(
            """
            SELECT
                ad.secuencia,
                ad.cuenta_codigo,
                COALESCE(c.nombre, '') AS cuenta_nombre,
                COALESCE(aux.nombre, '') AS auxiliar_nombre,
                COALESCE(aux.nit_ci, '') AS auxiliar_nit_ci,
                COALESCE(cc.codigo, '') AS centro_costo_codigo,
                COALESCE(cc.nombre, '') AS centro_costo_nombre,
                COALESCE(ad.glosa, '') AS glosa,
                ROUND(COALESCE(ad.debe, 0)::numeric, 2) AS debe,
                ROUND(COALESCE(ad.haber, 0)::numeric, 2) AS haber,
                COALESCE(ad.referencia, '') AS referencia
            FROM contabilidad.asiento_detalle ad
            LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
            LEFT JOIN contabilidad.auxiliar aux ON aux.id = ad.auxiliar_id
            LEFT JOIN contabilidad.centro_costo cc ON cc.id = ad.centro_costo_id
            WHERE ad.asiento_id = %s
            ORDER BY ad.secuencia ASC, ad.id ASC
            """,
            (asiento_id,),
        )
        detalle_rows = cursor.fetchall()

    detalle = []
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')
    for row in detalle_rows:
        debe = _decimal_from_db(row.get('debe'))
        haber = _decimal_from_db(row.get('haber'))
        total_debe += debe
        total_haber += haber
        detalle.append({
            'secuencia': row.get('secuencia'),
            'cuenta_codigo': row.get('cuenta_codigo') or '',
            'cuenta_nombre': row.get('cuenta_nombre') or '',
            'auxiliar_nombre': row.get('auxiliar_nombre') or '',
            'auxiliar_nit_ci': row.get('auxiliar_nit_ci') or '',
            'centro_costo_codigo': row.get('centro_costo_codigo') or '',
            'centro_costo_nombre': row.get('centro_costo_nombre') or '',
            'glosa': row.get('glosa') or '',
            'debe': _to_money(debe),
            'haber': _to_money(haber),
            'referencia': row.get('referencia') or '',
        })

    unidad = ' · '.join([p for p in [asiento.get('unidad_codigo'), asiento.get('unidad_nombre')] if p])
    diferencia = total_debe - total_haber
    return jsonify({
        'success': True,
        'data': {
            'asiento': {
                'id': asiento.get('id'),
                'fecha': asiento.get('fecha') or '',
                'estado': asiento.get('estado') or '',
                'moneda_codigo': asiento.get('moneda_codigo') or '',
                'tipo_cambio': str(asiento.get('tipo_cambio') or '1'),
                'glosa': asiento.get('glosa') or '',
                'referencia': asiento.get('referencia') or '',
                'modulo_origen': asiento.get('modulo_origen') or '',
                'unidad': unidad or '—',
                'creado_en': asiento.get('creado_en') or '',
            },
            'factura': {
                'id': factura.get('id'),
                'numero_factura': factura.get('numero_factura') or '',
                'fecha_emision': factura.get('fecha_emision').isoformat() if factura.get('fecha_emision') else '',
                'nit_cliente': factura.get('nit_cliente') or '',
                'nombre_cliente': factura.get('nombre_cliente') or '',
                'importe_total': _to_money(factura.get('importe_total')),
                'saldo_pendiente': _to_money(factura.get('saldo_pendiente')),
            },
            'detalle': detalle,
            'totales': {
                'debe': _to_money(total_debe),
                'haber': _to_money(total_haber),
                'diferencia': _to_money(diferencia),
            },
        },
    })


def _build_factura_asiento_pdf_bytes(factura, asiento, detalle_rows):
    generado = datetime.now().strftime('%d/%m/%Y %H:%M')
    moneda = asiento.get('moneda_codigo') or 'BOB'

    total_debe = sum((_decimal_from_db(row.get('debe')) for row in detalle_rows or []), Decimal('0.00'))
    total_haber = sum((_decimal_from_db(row.get('haber')) for row in detalle_rows or []), Decimal('0.00'))
    diferencia = (total_debe - total_haber).quantize(CUANTIA, rounding=ROUND_HALF_UP)

    unidad = ' · '.join([p for p in [asiento.get('unidad_codigo'), asiento.get('unidad_nombre')] if p])
    cliente = factura.get('nombre_cliente') or '-'
    nit_cliente = factura.get('nit_cliente') or '-'
    auxiliar = '-'
    cuenta_cobrar = '-'
    cuenta_contra = '-'

    for row in detalle_rows or []:
        debe = _decimal_from_db(row.get('debe'))
        haber = _decimal_from_db(row.get('haber'))
        cuenta_label = ' · '.join([p for p in [row.get('cuenta_codigo'), row.get('cuenta_nombre')] if p]) or '-'
        if debe > 0 and cuenta_cobrar == '-':
            cuenta_cobrar = cuenta_label
            if row.get('auxiliar_nombre'):
                auxiliar = row.get('auxiliar_nombre')
        if haber > 0 and cuenta_contra == '-':
            cuenta_contra = cuenta_label

    detail_rows = []
    for row in detalle_rows or []:
        cuenta = row.get('cuenta_codigo') or ''
        if row.get('cuenta_nombre'):
            cuenta = f"{cuenta} - {row.get('cuenta_nombre')}".strip(' -')
        auxiliar_linea = row.get('auxiliar_nombre') or '-'
        if row.get('auxiliar_nit_ci'):
            auxiliar_linea = f"{auxiliar_linea} · NIT/CI {row.get('auxiliar_nit_ci')}"
        centro_costo = row.get('centro_costo_codigo') or ''
        if row.get('centro_costo_nombre'):
            centro_costo = f"{centro_costo} - {row.get('centro_costo_nombre')}".strip(' -')
        detail_rows.append([
            row.get('secuencia') or '',
            cuenta or '-',
            auxiliar_linea,
            centro_costo or '-',
            row.get('glosa') or '-',
            format_money(row.get('debe')),
            format_money(row.get('haber')),
        ])

    sections = [
        {
            'title': 'Identificacion de la factura',
            'items': [
                {'label': 'Factura', 'value': factura.get('numero_factura') or '-'},
                {'label': 'Fecha emision', 'value': format_date(factura.get('fecha_emision'))},
                {'label': 'Estado factura', 'value': factura.get('estado') or '-'},
                {'label': 'Cliente', 'value': cliente},
                {'label': 'NIT cliente', 'value': nit_cliente},
                {'label': 'Auxiliar', 'value': auxiliar},
            ],
        },
        {
            'title': 'Datos de contabilizacion',
            'items': [
                {'label': 'Asiento', 'value': f"#{asiento.get('id')}"},
                {'label': 'Fecha asiento', 'value': format_date(asiento.get('fecha'))},
                {'label': 'Estado asiento', 'value': asiento.get('estado') or '-'},
                {'label': 'Unidad de negocio', 'value': unidad or '-'},
                {'label': 'Moneda', 'value': moneda},
                {'label': 'Tipo de cambio', 'value': asiento.get('tipo_cambio') or '1'},
            ],
        },
        {
            'title': 'Cuentas vinculadas',
            'items': [
                {'label': 'Cuenta por cobrar', 'value': cuenta_cobrar},
                {'label': 'Contra cuenta', 'value': cuenta_contra},
                {'label': 'Referencia', 'value': asiento.get('referencia') or '-'},
                {'label': 'Importe factura', 'value': f"{format_money(factura.get('importe_total'))} {moneda}"},
                {'label': 'Saldo pendiente', 'value': f"{format_money(factura.get('saldo_pendiente'))} {moneda}"},
                {'label': 'Lineas contables', 'value': str(len(detail_rows))},
            ],
        },
    ]

    return build_accounting_document_pdf(
        title='Asiento Contable de Factura',
        subtitle=f'DXT Conta - Tesoreria - Facturas Electronicas - Emitido {generado}',
        document_number=f"FACT-{int(factura.get('id')):06d}-ASI-{int(asiento.get('id')):06d}",
        state=asiento.get('estado') or '',
        sections=sections,
        detail_columns=[
            {'label': '#', 'width': 8, 'align': 'center'},
            {'label': 'Cuenta', 'width': 38},
            {'label': 'Auxiliar', 'width': 28},
            {'label': 'C.Costo', 'width': 22},
            {'label': 'Glosa', 'width': 38},
            {'label': 'Debe', 'width': 20, 'align': 'right'},
            {'label': 'Haber', 'width': 20, 'align': 'right'},
        ],
        detail_rows=detail_rows,
        totals=[
            {'label': f'Total debe {moneda}', 'value': format_money(total_debe)},
            {'label': f'Total haber {moneda}', 'value': format_money(total_haber)},
            {'label': 'Diferencia', 'value': format_money(diferencia)},
        ],
        notes=[{'title': 'Glosa general del asiento', 'text': asiento.get('glosa') or '-'}],
        emitted_by=_usuario_actual(),
        logo_file=logo_path(),
        generated_at=generado,
    )


@facturas_electronicas_bp.route('/<int:factura_id>/asiento/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_factura_asiento(factura_id):
    try:
        with DatabaseManager.get_cursor() as cursor:
            factura = _get_factura_state(cursor, factura_id, for_update=False)
            if not factura:
                return _json_error('La factura no existe.', status=404)
            asiento_id = factura.get('asiento_factura_id')
            if not asiento_id:
                return _json_error('La factura todavía no tiene asiento contable asociado.', status=404)

            cursor.execute(
                """
                SELECT
                    a.id,
                    a.fecha,
                    COALESCE(a.estado::TEXT, '') AS estado,
                    COALESCE(a.moneda_codigo, 'BOB') AS moneda_codigo,
                    COALESCE(a.tipo_cambio, 1) AS tipo_cambio,
                    COALESCE(a.glosa, '') AS glosa,
                    COALESCE(a.referencia, '') AS referencia,
                    COALESCE(a.modulo_origen, '') AS modulo_origen,
                    COALESCE(un.codigo, '') AS unidad_codigo,
                    COALESCE(un.nombre, '') AS unidad_nombre,
                    a.creado_en
                FROM contabilidad.asiento a
                LEFT JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
                WHERE a.id = %s
                LIMIT 1
                """,
                (asiento_id,),
            )
            asiento = cursor.fetchone()
            if not asiento:
                return _json_error('No se encontró el asiento contable asociado.', status=404)

            cursor.execute(
                """
                SELECT
                    ad.secuencia,
                    ad.cuenta_codigo,
                    COALESCE(c.nombre, '') AS cuenta_nombre,
                    COALESCE(aux.nombre, '') AS auxiliar_nombre,
                    COALESCE(aux.nit_ci, '') AS auxiliar_nit_ci,
                    COALESCE(cc.codigo, '') AS centro_costo_codigo,
                    COALESCE(cc.nombre, '') AS centro_costo_nombre,
                    COALESCE(ad.glosa, '') AS glosa,
                    ROUND(COALESCE(ad.debe, 0)::numeric, 2) AS debe,
                    ROUND(COALESCE(ad.haber, 0)::numeric, 2) AS haber,
                    COALESCE(ad.referencia, '') AS referencia
                FROM contabilidad.asiento_detalle ad
                LEFT JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
                LEFT JOIN contabilidad.auxiliar aux ON aux.id = ad.auxiliar_id
                LEFT JOIN contabilidad.centro_costo cc ON cc.id = ad.centro_costo_id
                WHERE ad.asiento_id = %s
                ORDER BY ad.secuencia ASC, ad.id ASC
                """,
                (asiento_id,),
            )
            detalle_rows = cursor.fetchall()

        pdf_bytes = _build_factura_asiento_pdf_bytes(factura, asiento, detalle_rows)
        fecha_txt = factura['fecha_emision'].strftime('%Y%m%d') if factura.get('fecha_emision') else datetime.now().strftime('%Y%m%d')
        numero = _clean(factura.get('numero_factura')).replace('/', '-').replace('\\', '-').replace(' ', '_') or str(factura_id)
        nombre = f"asiento_factura_{numero}_{fecha_txt}_{int(asiento_id):06d}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del asiento contable. {exc}', status=500)


@facturas_electronicas_bp.route('/api/<int:factura_id>/contabilizar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_contabilizar_factura(factura_id):
    payload = request.get_json(silent=True) or {}
    try:
        auxiliar_id = _parse_int(payload.get('auxiliar_id'), 'Auxiliar')
        cuenta_cobrar_codigo = _normalize_text(payload.get('cuenta_cobrar_codigo'), 'Cuenta por cobrar', 30, required=True)
        cuenta_contra_codigo = _normalize_text(payload.get('cuenta_contra_codigo'), 'Contra cuenta', 30, required=True)
        fecha_asiento = _parse_date_iso(payload.get('fecha_asiento'))
        if not fecha_asiento:
            raise ValueError('La fecha del asiento no es válida.')
        glosa = _normalize_text(payload.get('glosa'), 'Glosa', 500, required=False)
        usuario = str(_usuario_actual())

        with DatabaseManager.get_cursor() as cursor:
            factura = _get_factura_state(cursor, factura_id, for_update=True)
            if not factura:
                raise ValueError('La factura seleccionada no existe.')
            if factura['estado'] == 'ANULADA':
                raise ValueError('La factura está anulada y no puede contabilizarse.')
            if factura.get('cierre_manual_activo'):
                raise ValueError('La factura tiene cierre de tesorería activo y no puede contabilizarse.')
            if factura.get('asiento_factura_id'):
                raise ValueError('La factura ya tiene un asiento contable asociado.')
            if _saldo_operativo_factura(factura) <= 0:
                raise ValueError('La factura no tiene saldo pendiente para contabilizar.')
            if _decimal_from_db(factura.get('total_aplicado')) > 0 or _decimal_from_db(factura.get('total_regularizado')) > 0:
                raise ValueError('La factura ya tiene cobros o regularizaciones. Debe contabilizarse antes de aplicar movimientos.')

            auxiliar = _get_auxiliar_cliente(cursor, auxiliar_id)
            if not auxiliar:
                raise ValueError('El auxiliar seleccionado no existe, no es cliente o está inactivo.')
            cuenta_cobrar = _get_account_row(cursor, cuenta_cobrar_codigo)
            if not cuenta_cobrar:
                raise ValueError('La cuenta por cobrar no existe, no está activa o no es postable.')
            cuenta_contra = _get_account_row(cursor, cuenta_contra_codigo)
            if not cuenta_contra:
                raise ValueError('La contra cuenta no existe, no está activa o no es postable.')

            importe = _decimal_from_db(factura['importe_total'])
            if importe <= 0:
                raise ValueError('El importe de la factura debe ser mayor a cero.')

            glosa_final = glosa or f"Contabilización factura {factura['numero_factura']} - {factura.get('nombre_cliente') or factura.get('nit_cliente') or ''}"
            referencia = f"Factura {factura['numero_factura']} · {factura['fecha_emision'].isoformat()} · NIT {factura.get('nit_cliente') or '—'}"
            atributos = Json({
                'origen': 'facturas_electronicas',
                'accion': 'contabilizacion_factura',
                'factura_id': factura_id,
                'usuario': usuario,
                'clave_negocio': {
                    'nit_emisor': factura.get('nit_emisor'),
                    'numero_factura': factura.get('numero_factura'),
                    'fecha_emision': factura['fecha_emision'].isoformat() if factura.get('fecha_emision') else None,
                    'nit_cliente': factura.get('nit_cliente'),
                },
            })
            cursor.execute(
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
                    cliente_nit_ci_ref,
                    cliente_nombre_ref,
                    atributos,
                    actualizado_en
                ) VALUES (
                    %s, %s, %s, 1, %s, %s,
                    'TESORERIA',
                    'contabilidad.factura_electronica',
                    %s,
                    'CONFIRMADO',
                    %s, %s,
                    %s,
                    CURRENT_TIMESTAMP
                )
                RETURNING id
                """,
                (
                    fecha_asiento,
                    factura['unidad_negocio_id'],
                    factura.get('moneda_codigo') or 'BOB',
                    glosa_final,
                    referencia,
                    factura_id,
                    factura.get('nit_cliente'),
                    factura.get('nombre_cliente'),
                    atributos,
                ),
            )
            asiento_id = cursor.fetchone()['id']

            cursor.execute(
                """
                INSERT INTO contabilidad.asiento_detalle (
                    asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa,
                    debe, haber, monto_moneda, referencia, atributos
                ) VALUES
                (%s, 1, %s, %s, %s, %s, 0, %s, %s, %s::jsonb),
                (%s, 2, %s, NULL, %s, 0, %s, %s, %s, %s::jsonb)
                """,
                (
                    asiento_id,
                    cuenta_cobrar_codigo,
                    auxiliar_id,
                    f"Cuenta por cobrar factura {factura['numero_factura']}",
                    importe,
                    importe,
                    referencia,
                    '{"tipo":"debe_cuenta_por_cobrar_factura"}',
                    asiento_id,
                    cuenta_contra_codigo,
                    f"Contrapartida factura {factura['numero_factura']}",
                    importe,
                    importe,
                    referencia,
                    '{"tipo":"haber_contra_factura"}',
                ),
            )

            cursor.execute(
                """
                INSERT INTO contabilidad.documento_asiento (
                    modulo, tabla_origen, origen_id, asiento_id
                ) VALUES ('TESORERIA', 'contabilidad.factura_electronica', %s, %s)
                """,
                (factura_id, asiento_id),
            )

            cursor.execute(
                """
                UPDATE contabilidad.factura_electronica
                SET cliente_auxiliar_id = %s,
                    cuenta_cobrar_codigo = %s,
                    cuenta_contra_codigo = %s,
                    fecha_contabilizacion = %s,
                    estado = 'REGISTRADA'::contabilidad.estado_factura_ext_enum,
                    actualizado_en = CURRENT_TIMESTAMP,
                    payload = COALESCE(payload, '{}'::jsonb) || jsonb_build_object(
                        'contabilizacion',
                        jsonb_build_object(
                            'asiento_id', %s,
                            'auxiliar_id', %s,
                            'cuenta_cobrar_codigo', %s,
                            'cuenta_contra_codigo', %s,
                            'fecha_asiento', %s,
                            'usuario', %s,
                            'registrado_en', %s
                        )
                    )
                WHERE id = %s
                """,
                (
                    auxiliar_id,
                    cuenta_cobrar_codigo,
                    cuenta_contra_codigo,
                    fecha_asiento,
                    asiento_id,
                    auxiliar_id,
                    cuenta_cobrar_codigo,
                    cuenta_contra_codigo,
                    fecha_asiento.isoformat(),
                    usuario,
                    datetime.now().isoformat(),
                    factura_id,
                ),
            )

        return _json_success('Factura contabilizada correctamente.', factura_id=factura_id, asiento_id=asiento_id)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo contabilizar la factura. {exc}', status=500)


@facturas_electronicas_bp.route('/api/cerrar-manual', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_cerrar_manual():
    payload = request.get_json(silent=True) or {}
    try:
        factura_id = _parse_int(payload.get('factura_id'), 'Factura')
        motivo = _normalize_text(payload.get('motivo'), 'Motivo', 200, required=True)
        observacion = _normalize_text(payload.get('observacion'), 'Observación', 500, required=False)
        usuario = str(_usuario_actual())
        with DatabaseManager.get_cursor() as cursor:
            factura = _get_factura_state(cursor, factura_id, for_update=True)
            if not factura:
                raise ValueError('La factura seleccionada no existe.')
            if factura['estado'] == 'ANULADA':
                raise ValueError('La factura ya está anulada y no puede cerrarse.')
            if factura.get('cierre_manual_activo'):
                raise ValueError('La factura ya tiene un cierre de tesorería activo.')
            saldo = _saldo_operativo_factura(factura)
            if saldo <= 0:
                raise ValueError('La factura no tiene saldo pendiente para cierre de tesorería.')
            cursor.execute(
                """
                INSERT INTO contabilidad.factura_regularizacion (
                    factura_electronica_id, tipo_regularizacion, monto, motivo,
                    observacion, creado_por, actualizado_en
                ) VALUES (%s, 'CIERRE_MANUAL', %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (factura_id, saldo, motivo, observacion, usuario),
            )
            _recalcular_estado_factura(cursor, factura_id)
        return _json_success('Factura cerrada en tesorería.', factura_id=factura_id)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo cerrar la factura. {exc}', status=500)


@facturas_electronicas_bp.route('/api/reabrir-cierre', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_reabrir_cierre():
    payload = request.get_json(silent=True) or {}
    try:
        factura_id = _parse_int(payload.get('factura_id'), 'Factura')
        usuario = str(_usuario_actual())
        with DatabaseManager.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE contabilidad.factura_regularizacion
                SET activo = FALSE,
                    anulado_por = %s,
                    anulado_en = CURRENT_TIMESTAMP,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE factura_electronica_id = %s
                  AND tipo_regularizacion = 'CIERRE_MANUAL'
                  AND activo = TRUE
                """,
                (usuario, factura_id),
            )
            if cursor.rowcount <= 0:
                raise ValueError('La factura no tiene cierre de tesorería activo para reabrir.')
            _recalcular_estado_factura(cursor, factura_id)
        return _json_success('Cierre de tesorería reabierto.', factura_id=factura_id)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo reabrir el cierre. {exc}', status=500)



@facturas_electronicas_bp.route('/api/factura-manual', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_crear_factura_manual():
    payload = request.get_json(silent=True) or {}
    try:
        unidad_negocio_id = _parse_int(payload.get('unidad_negocio_id'), 'Unidad de negocio')
        numero_factura = _normalize_text(payload.get('numero_factura'), 'Número de factura', 100, required=True)
        fecha_emision = _parse_date_iso(payload.get('fecha_emision'))
        if not fecha_emision:
            raise ValueError('La fecha de emisión no es válida.')
        nit_cliente = _normalize_text(payload.get('nit_cliente'), 'NIT del cliente', 50, required=True)
        nombre_cliente = _normalize_text(payload.get('nombre_cliente'), 'Nombre del cliente', 200, required=True)
        cuf_original = _normalize_text(payload.get('cuf'), 'CUF', 255, required=False)
        cuf = _normalize_cuf(cuf_original)
        estado_archivo = _normalize_text(payload.get('estado_archivo'), 'Estado', 100, required=False) or 'Recepcionada'
        es_anulada = 'ANUL' in _upper_clean(estado_archivo)
        importe_total = _to_decimal(payload.get('importe_total'))
        descuento = _to_decimal(payload.get('descuento'))
        subtotal = _to_decimal(payload.get('subtotal') or (importe_total + descuento))
        metodo_pago = _normalize_text(payload.get('metodo_pago'), 'Método de pago', 100, required=False)
        observacion = _normalize_text(payload.get('observacion'), 'Observación', 500, required=False)
        usuario = str(_usuario_actual())

        if importe_total < 0:
            raise ValueError('El total de la factura no puede ser negativo.')
        if not es_anulada and importe_total <= 0:
            raise ValueError('El total de la factura debe ser mayor a cero.')
        if descuento < 0:
            raise ValueError('El descuento no puede ser negativo.')
        if subtotal < 0:
            raise ValueError('El subtotal no puede ser negativo.')

        with DatabaseManager.get_cursor() as cursor:
            unidad = _get_unidad_negocio_activa(cursor, unidad_negocio_id)
            if not unidad:
                raise ValueError('La unidad de negocio seleccionada no existe o está inactiva.')
            nit_emisor = _clean(unidad.get('nit'))
            if not nit_emisor:
                raise ValueError('La unidad de negocio seleccionada no tiene NIT registrado. No se puede individualizar la factura.')

            cursor.execute(
                """
                SELECT id, estado, saldo_pendiente
                FROM contabilidad.factura_electronica
                WHERE origen = 'EXTERNO'
                  AND UPPER(TRIM(COALESCE(nit_emisor, ''))) = UPPER(TRIM(%s))
                  AND UPPER(TRIM(numero_factura)) = UPPER(TRIM(%s))
                  AND fecha_emision = %s
                  AND UPPER(TRIM(COALESCE(nit_cliente, ''))) = UPPER(TRIM(COALESCE(%s, '')))
                LIMIT 1
                """,
                (nit_emisor, numero_factura, fecha_emision, nit_cliente),
            )
            existente = cursor.fetchone()
            if existente:
                raise ValueError(
                    'Ya existe una factura con el mismo NIT emisor, número, fecha de emisión y NIT cliente. '
                    f'Factura existente ID #{existente["id"]}.'
                )

            cliente_data = _buscar_cliente(cursor, nit_cliente)
            cliente_auxiliar_id = cliente_data['auxiliar_id'] if cliente_data else None
            cliente_empresa_id = cliente_data['cliente_empresa_id'] if cliente_data else None
            estado_destino = 'ANULADA' if es_anulada else ('DISPONIBLE' if cliente_auxiliar_id else 'RECIBIDA')
            saldo_pendiente = Decimal('0.00') if es_anulada else importe_total
            payload_db = {
                'modo_carga': 'MANUAL',
                'estado_archivo': estado_archivo,
                'cuf_original': cuf_original,
                'metodo_pago': metodo_pago,
                'observacion': observacion,
                'registrado_por': usuario,
                'registrado_en': datetime.now().isoformat(),
                'nit_emisor': nit_emisor,
                'unidad_negocio_id': unidad['id'],
                'unidad_negocio_codigo': unidad['codigo'],
                'unidad_negocio_nombre': unidad['nombre'],
                'raw': {
                    'numero_factura': numero_factura,
                    'fecha_emision': fecha_emision.isoformat(),
                    'nit_cliente': nit_cliente,
                    'nombre_cliente': nombre_cliente,
                    'importe_total': str(importe_total),
                    'subtotal': str(subtotal),
                    'descuento': str(descuento),
                },
            }

            cursor.execute(
                """
                INSERT INTO contabilidad.factura_electronica (
                    origen,
                    codigo_externo,
                    cliente_auxiliar_id,
                    cliente_empresa_id,
                    unidad_negocio_id,
                    nit_emisor,
                    nit_cliente,
                    nombre_cliente,
                    numero_factura,
                    cuf,
                    fecha_emision,
                    moneda_codigo,
                    subtotal,
                    descuento,
                    importe_total,
                    saldo_pendiente,
                    estado,
                    payload,
                    es_saldo_inicial,
                    cuenta_cobrar_codigo,
                    cuenta_contra_codigo,
                    fecha_contabilizacion
                ) VALUES (
                    'EXTERNO',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'BOB',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    FALSE,
                    NULL,
                    NULL,
                    NULL
                )
                RETURNING id
                """,
                (
                    _business_key_code(nit_emisor, numero_factura, fecha_emision, nit_cliente),
                    cliente_auxiliar_id,
                    cliente_empresa_id,
                    unidad['id'],
                    nit_emisor,
                    nit_cliente,
                    nombre_cliente,
                    numero_factura,
                    cuf,
                    fecha_emision,
                    subtotal,
                    descuento,
                    importe_total,
                    saldo_pendiente,
                    estado_destino,
                    Json(payload_db),
                ),
            )
            factura_id = cursor.fetchone()['id']

        return _json_success('Factura manual registrada correctamente.', factura_id=factura_id)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo registrar la factura manual. {exc}', status=500)


@facturas_electronicas_bp.route('/importar-lote', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def importar_lote():
    payload = request.get_json(silent=True) or {}
    filas = payload.get('filas') or []

    if not isinstance(filas, list) or not filas:
        return jsonify({
            'ok': False,
            'message': 'No se recibieron filas para importar.',
        }), 400

    metadata = {
        'nombre_archivo': _clean(payload.get('nombre_archivo')),
        'lote_numero': payload.get('lote_numero'),
        'total_lotes': payload.get('total_lotes'),
        'nit_emisor': _clean(payload.get('nit_emisor')),
        'razon_social_emisor': _clean(payload.get('razon_social_emisor')),
        'sucursal_cabecera': _clean(payload.get('sucursal_cabecera')),
    }

    resumen = {
        'procesadas': 0,
        'insertadas': 0,
        'omitidas': 0,
        'anuladas_insertadas': 0,
        'actualizadas_a_anulada': 0,
        'desvinculadas_aplicaciones': 0,
        'desvinculadas_ventas': 0,
        'errores': 0,
    }
    detalles = []

    try:
        with DatabaseManager.get_cursor() as cursor:
            emisor = _resolver_emisor_importacion(cursor, metadata)
            for row in filas:
                resumen['procesadas'] += 1
                cursor.execute('SAVEPOINT sp_factura_lote')
                try:
                    result = _procesar_fila(cursor, row, metadata, emisor)
                    accion = result['accion']

                    if accion == 'insertada':
                        resumen['insertadas'] += 1
                    elif accion == 'omitida':
                        resumen['omitidas'] += 1
                    elif accion == 'anulada_insertada':
                        resumen['anuladas_insertadas'] += 1
                    elif accion == 'actualizada_a_anulada':
                        resumen['actualizadas_a_anulada'] += 1
                    else:
                        resumen['errores'] += 1

                    resumen['desvinculadas_aplicaciones'] += int(result.get('desvinculadas_aplicaciones') or 0)
                    resumen['desvinculadas_ventas'] += int(result.get('desvinculadas_ventas') or 0)

                    if len(detalles) < 80:
                        detalles.append({
                            'accion': accion,
                            'mensaje': result['mensaje'],
                            'fila_origen': result.get('fila_origen'),
                        })

                    cursor.execute('RELEASE SAVEPOINT sp_factura_lote')
                except Exception as exc:
                    cursor.execute('ROLLBACK TO SAVEPOINT sp_factura_lote')
                    cursor.execute('RELEASE SAVEPOINT sp_factura_lote')
                    resumen['errores'] += 1
                    if len(detalles) < 80:
                        detalles.append({
                            'accion': 'error',
                            'mensaje': str(exc),
                            'fila_origen': row.get('fila_origen'),
                        })

            resumen_general = _resumen_general(cursor)
    except ValueError as exc:
        return jsonify({
            'ok': False,
            'message': str(exc),
        }), 400

    return jsonify({
        'ok': True,
        'message': 'Lote procesado correctamente.',
        'emisor': emisor,
        'resumen': resumen,
        'resumen_general': resumen_general,
        'detalles': detalles,
    })
