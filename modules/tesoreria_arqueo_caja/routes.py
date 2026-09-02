# ============================================================
# DXT CONTA - Módulo Tesorería Arqueo de Caja
# Reingeniería puntual: cálculo trazable por caja/fecha
# ============================================================

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Response, flash, jsonify, redirect, render_template, request, session, url_for

from database.db_manager import DatabaseManager
from modules.tesoreria_arqueo_caja import tesoreria_arqueo_caja_bp
from utils.decorators import login_required, roles_required
from modules.reportes_rapidos.core.utils import logo_path
from utils.documentos_pdf import build_accounting_document_pdf, format_date, format_money


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
ESTADOS_DOCUMENTO = ['BORRADOR', 'CONFIRMADO', 'ANULADO']
CUANTIA = Decimal('0.01')


# ============================================================
# Helpers base
# ============================================================

def _json_ok(message=None, **kwargs):
    payload = {'success': True}
    if message:
        payload['message'] = message
    payload.update(kwargs)
    return jsonify(payload)



def _json_error(message, status=400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(payload), status



def _clean(value):
    return (value or '').strip()



def _money(value):
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value)).quantize(CUANTIA, rounding=ROUND_HALF_UP)



def _to_float(value):
    if value is None:
        return None
    return float(_money(value))



def _date_iso(value):
    if not value:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)



def _decimal(value, field_name, allow_zero=False, quant=CUANTIA, required=True):
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None

    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError):
        raise ValueError(f'El campo "{field_name}" no tiene un formato válido.')

    if allow_zero:
        if number < 0:
            raise ValueError(f'El campo "{field_name}" no puede ser negativo.')
    elif number <= 0:
        raise ValueError(f'El campo "{field_name}" debe ser mayor a cero.')

    return number.quantize(quant, rounding=ROUND_HALF_UP)



def _parse_int(value, field_name, required=True):
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field_name}" debe ser numérico.')



def _parse_date(value, field_name='Fecha', required=True):
    if not value:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.')



def _normalize_text(value, field_name, max_len, required=False):
    value = _clean(value)
    if required and not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(value) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return value or None



def _usuario_actual():
    return (
        session.get('username')
        or session.get('usuario')
        or session.get('usuario_nombre')
        or session.get('email')
        or session.get('nombre')
        or session.get('user_id')
        or 'sistema'
    )



def _puede_editar():
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except Exception:
        return False


# ============================================================
# Catálogos y caja
# ============================================================

def _tabla_cuentas(db):
    rows = db.execute_query("SELECT to_regclass('contabilidad.cuentas') AS tabla_plural")
    if rows and rows[0]['tabla_plural']:
        return 'contabilidad.cuentas'
    return 'contabilidad.cuenta'



def _get_cajas_activas(db, include_ids=None):
    include_ids = include_ids or []
    params = []

    if include_ids:
        where = '(c.activo = TRUE OR c.id = ANY(%s))'
        params.append(include_ids)
    else:
        where = 'c.activo = TRUE'

    sql = f"""
        SELECT
            c.id,
            c.codigo,
            c.nombre,
            c.cuenta_contable_codigo,
            c.activo,
            NULL::bigint AS unidad_negocio_id,
            cu.nombre AS cuenta_contable_nombre,
            ''::text AS unidad_negocio_codigo,
            'General'::text AS unidad_negocio_nombre
        FROM contabilidad.caja c
        LEFT JOIN {_tabla_cuentas(db)} cu ON cu.codigo = c.cuenta_contable_codigo
        WHERE {where}
        ORDER BY c.activo DESC, c.nombre ASC, c.codigo ASC
    """
    return db.execute_query(sql, tuple(params) if params else None)



def _get_caja_info(db, caja_id, required=True, active_only=False):
    caja_id = _parse_int(caja_id, 'Caja', required=required)
    if caja_id is None:
        return None

    rows = db.execute_query(
        f"""
        SELECT
            c.id,
            c.codigo,
            c.nombre,
            c.cuenta_contable_codigo,
            c.activo,
            NULL::bigint AS unidad_negocio_id,
            cu.nombre AS cuenta_contable_nombre,
            ''::text AS unidad_negocio_codigo,
            'General'::text AS unidad_negocio_nombre
        FROM contabilidad.caja c
        LEFT JOIN {_tabla_cuentas(db)} cu ON cu.codigo = c.cuenta_contable_codigo
        WHERE c.id = %s
        LIMIT 1
        """,
        (caja_id,),
    )
    if not rows:
        raise ValueError('La caja seleccionada no existe.')

    row = rows[0]
    if active_only and not row['activo']:
        raise ValueError('La caja seleccionada está inactiva.')
    return row


# ============================================================
# Snapshot trazable del arqueo
# ============================================================

def _get_caja_movimientos_confirmados(db, caja_id, fecha_arqueo):
    """
    Devuelve todos los movimientos confirmados que afectan la caja hasta la fecha
    de arqueo. Se usa una sola fuente normalizada para evitar que pantalla y
    backend sumen con criterios diferentes.
    """
    return db.execute_query(
        """
        SELECT *
        FROM (
            SELECT
                'COBRO'::text AS origen_doc,
                c.id AS documento_id,
                c.fecha,
                'INGRESO'::text AS flujo,
                c.medio_pago::text AS medio,
                c.caja_id,
                c.moneda_codigo,
                c.tipo_cambio,
                c.monto_total::numeric AS monto,
                c.referencia,
                c.glosa,
                c.estado::text AS estado,
                c.unidad_negocio_id,
                un.codigo AS unidad_negocio_codigo,
                un.nombre AS unidad_negocio_nombre
            FROM contabilidad.cobro c
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            WHERE c.estado = 'CONFIRMADO'
              AND c.medio_pago = 'CAJA'
              AND c.caja_id = %s
              AND c.fecha <= %s

            UNION ALL

            SELECT
                'PAGO'::text AS origen_doc,
                p.id AS documento_id,
                p.fecha,
                'EGRESO'::text AS flujo,
                p.medio_pago::text AS medio,
                p.caja_id,
                p.moneda_codigo,
                p.tipo_cambio,
                p.monto_total::numeric AS monto,
                p.referencia,
                p.glosa,
                p.estado::text AS estado,
                p.unidad_negocio_id,
                un.codigo AS unidad_negocio_codigo,
                un.nombre AS unidad_negocio_nombre
            FROM contabilidad.pago p
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
            WHERE p.estado = 'CONFIRMADO'
              AND p.medio_pago = 'CAJA'
              AND p.caja_id = %s
              AND p.fecha <= %s

            UNION ALL

            SELECT
                'MOVIMIENTO'::text AS origen_doc,
                m.id AS documento_id,
                m.fecha,
                CASE
                    WHEN m.medio_destino = 'CAJA' AND m.caja_destino_id = %s THEN 'INGRESO'
                    ELSE 'EGRESO'
                END AS flujo,
                CASE
                    WHEN m.medio_destino = 'CAJA' AND m.caja_destino_id = %s THEN m.medio_destino::text
                    ELSE m.medio_origen::text
                END AS medio,
                CASE
                    WHEN m.medio_destino = 'CAJA' AND m.caja_destino_id = %s THEN m.caja_destino_id
                    ELSE m.caja_origen_id
                END AS caja_id,
                m.moneda_codigo,
                m.tipo_cambio,
                m.monto::numeric AS monto,
                m.referencia,
                m.glosa,
                m.estado::text AS estado,
                m.unidad_negocio_id,
                un.codigo AS unidad_negocio_codigo,
                un.nombre AS unidad_negocio_nombre
            FROM contabilidad.movimiento_tesoreria m
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = m.unidad_negocio_id
            WHERE m.estado = 'CONFIRMADO'
              AND (
                    (m.medio_destino = 'CAJA' AND m.caja_destino_id = %s)
                 OR (m.medio_origen = 'CAJA' AND m.caja_origen_id = %s)
              )
              AND m.fecha <= %s
        ) q
        ORDER BY q.fecha ASC, q.origen_doc ASC, q.documento_id ASC, q.flujo ASC
        """,
        (
            caja_id,
            fecha_arqueo,
            caja_id,
            fecha_arqueo,
            caja_id,
            caja_id,
            caja_id,
            caja_id,
            caja_id,
            fecha_arqueo,
        ),
    )




def _movimiento_arqueo_key(row):
    """Clave estable para identificar un movimiento ya incluido en un arqueo confirmado."""
    return (
        str(row.get('origen_doc') or ''),
        int(row.get('documento_id') or 0),
        str(row.get('flujo') or ''),
    )


def _get_movimientos_arqueados_hasta(db, caja_id, fecha_corte):
    """
    Devuelve movimientos que ya fueron cerrados por arqueos confirmados anteriores.

    Esta validacion evita dos riesgos:
    - volver a contar movimientos ya incluidos en arqueos previos;
    - omitir movimientos confirmados de forma tardia con fecha anterior al ultimo arqueo,
      siempre que no hayan sido parte del detalle guardado.
    """
    if not _arqueo_detalle_table_exists(db) or not fecha_corte:
        return set()

    rows = db.execute_query(
        """
        SELECT
            d.origen_doc,
            d.documento_id,
            d.flujo
        FROM contabilidad.arqueo_caja_detalle d
        INNER JOIN contabilidad.arqueo_caja a ON a.id = d.arqueo_id
        WHERE a.caja_id = %s
          AND a.estado = 'CONFIRMADO'
          AND a.fecha_arqueo <= %s
        """,
        (caja_id, fecha_corte),
    )
    return {_movimiento_arqueo_key(row) for row in rows}


def _ultimo_arqueo_tiene_detalle(db, arqueo_id):
    if not _arqueo_detalle_table_exists(db) or not arqueo_id:
        return False
    rows = db.execute_query(
        """
        SELECT 1
        FROM contabilidad.arqueo_caja_detalle
        WHERE arqueo_id = %s
        LIMIT 1
        """,
        (arqueo_id,),
    )
    return bool(rows)


def _filtrar_movimientos_no_cerrados(db, caja_id, rows, ultimo_arqueo):
    """
    Mantiene solo movimientos pendientes de formar parte del nuevo arqueo.

    Si existe detalle guardado de arqueos anteriores, se excluyen por identidad del
    movimiento. Si no existe detalle historico, se usa el criterio antiguo por fecha
    como respaldo para no duplicar saldos previos.
    """
    if not ultimo_arqueo:
        return list(rows)

    fecha_base = ultimo_arqueo.get('fecha_arqueo')
    ultimo_id = ultimo_arqueo.get('id')

    if _ultimo_arqueo_tiene_detalle(db, ultimo_id):
        cerrados = _get_movimientos_arqueados_hasta(db, caja_id, fecha_base)
        if cerrados:
            return [row for row in rows if _movimiento_arqueo_key(row) not in cerrados]

    if fecha_base:
        return [row for row in rows if row['fecha'] > fecha_base]
    return list(rows)

def _get_caja_trazabilidad_rows(db, caja_id, fecha_arqueo):
    """
    Devuelve los movimientos que explican un arqueo.

    Si existe un arqueo confirmado anterior, solo considera movimientos
    posteriores a ese corte para no volver a contar operaciones ya cerradas.
    La columna clasificacion separa movimientos del dia y movimientos previos
    que forman el saldo anterior.
    """
    caja_id = _parse_int(caja_id, 'Caja')
    fecha_arqueo = _parse_date(fecha_arqueo, 'Fecha de arqueo')

    ultimo_arqueo = _get_ultimo_arqueo_confirmado_anterior(db, caja_id, fecha_arqueo)
    fecha_base = ultimo_arqueo['fecha_arqueo'] if ultimo_arqueo else None

    rows = _get_caja_movimientos_confirmados(db, caja_id, fecha_arqueo)
    rows = _filtrar_movimientos_no_cerrados(db, caja_id, rows, ultimo_arqueo)

    trazabilidad = []
    for row in rows:
        item = dict(row)
        item['clasificacion'] = 'DIA' if item['fecha'] == fecha_arqueo else 'ANTERIOR'
        trazabilidad.append(item)

    return trazabilidad, ultimo_arqueo


def _arqueo_detalle_table_exists(db):
    rows = db.execute_query("SELECT to_regclass('contabilidad.arqueo_caja_detalle') AS tabla")
    return bool(rows and rows[0].get('tabla'))


def _replace_arqueo_detalle_guardado(db, arqueo_id, caja_id, fecha_arqueo):
    """Guarda el detalle usado al confirmar el arqueo, si existe la tabla de detalle."""
    if not _arqueo_detalle_table_exists(db):
        return

    detalle_rows, _ultimo_arqueo = _get_caja_trazabilidad_rows(db, caja_id, fecha_arqueo)

    db.execute_delete(
        "DELETE FROM contabilidad.arqueo_caja_detalle WHERE arqueo_id = %s",
        (arqueo_id,),
    )

    for row in detalle_rows:
        db.execute_insert(
            """
            INSERT INTO contabilidad.arqueo_caja_detalle (
                arqueo_id,
                origen_doc,
                documento_id,
                fecha,
                clasificacion,
                flujo,
                medio,
                caja_id,
                moneda_codigo,
                tipo_cambio,
                monto,
                referencia,
                glosa,
                estado,
                unidad_negocio_id,
                unidad_negocio_codigo,
                unidad_negocio_nombre
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                arqueo_id,
                row.get('origen_doc'),
                row.get('documento_id'),
                row.get('fecha'),
                row.get('clasificacion'),
                row.get('flujo'),
                row.get('medio'),
                row.get('caja_id'),
                row.get('moneda_codigo'),
                row.get('tipo_cambio'),
                row.get('monto'),
                row.get('referencia'),
                row.get('glosa'),
                row.get('estado'),
                row.get('unidad_negocio_id'),
                row.get('unidad_negocio_codigo'),
                row.get('unidad_negocio_nombre'),
            ),
            return_id=False,
        )


def _get_arqueo_detalle_guardado(db, arqueo_id):
    if not _arqueo_detalle_table_exists(db):
        return []

    return db.execute_query(
        """
        SELECT
            origen_doc,
            documento_id,
            fecha,
            clasificacion,
            flujo,
            medio,
            caja_id,
            moneda_codigo,
            tipo_cambio,
            monto,
            referencia,
            glosa,
            estado,
            unidad_negocio_id,
            unidad_negocio_codigo,
            unidad_negocio_nombre
        FROM contabilidad.arqueo_caja_detalle
        WHERE arqueo_id = %s
        ORDER BY
            CASE clasificacion WHEN 'ANTERIOR' THEN 0 ELSE 1 END,
            fecha ASC,
            origen_doc ASC,
            documento_id ASC,
            flujo ASC
        """,
        (arqueo_id,),
    )


def _get_arqueo_detalle_pdf_rows(db, arqueo):
    detalle_guardado = _get_arqueo_detalle_guardado(db, arqueo['id'])
    if detalle_guardado:
        return detalle_guardado, 'Detalle guardado al confirmar el arqueo.'

    detalle_actual, _ultimo_arqueo = _get_caja_trazabilidad_rows(db, arqueo['caja_id'], arqueo['fecha_arqueo'])
    return detalle_actual, 'Detalle reconstruido desde los movimientos confirmados actuales de la base de datos.'


def _public_movimiento(row):
    monto = _money(row['monto'])
    return {
        'origen_doc': row['origen_doc'],
        'documento_id': row['documento_id'],
        'fecha': _date_iso(row['fecha']),
        'flujo': row['flujo'],
        'medio': row['medio'],
        'caja_id': row['caja_id'],
        'moneda_codigo': row['moneda_codigo'],
        'tipo_cambio_f': _to_float(row['tipo_cambio']),
        'monto_f': _to_float(monto),
        'referencia': row['referencia'] or '',
        'glosa': row['glosa'] or '',
        'estado': row['estado'],
        'unidad_negocio_id': row['unidad_negocio_id'],
        'unidad_negocio_codigo': row['unidad_negocio_codigo'] or '',
        'unidad_negocio_nombre': row['unidad_negocio_nombre'] or '',
    }



def _snapshot_public(snapshot):
    return {
        'caja_id': snapshot['caja_id'],
        'fecha_arqueo': _date_iso(snapshot['fecha_arqueo']),
        'saldo_anterior_f': _to_float(snapshot['saldo_anterior']),
        'ingresos_dia_f': _to_float(snapshot['ingresos_dia']),
        'egresos_dia_f': _to_float(snapshot['egresos_dia']),
        'saldo_teorico_f': _to_float(snapshot['saldo_teorico']),
        'movimientos_dia': snapshot.get('movimientos_dia', []),
        'conteo_movimientos_dia': snapshot.get('conteo_movimientos_dia', 0),
        'conteo_movimientos_anteriores': snapshot.get('conteo_movimientos_anteriores', 0),
        'ingresos_anteriores_f': _to_float(snapshot.get('ingresos_anteriores', Decimal('0.00'))),
        'egresos_anteriores_f': _to_float(snapshot.get('egresos_anteriores', Decimal('0.00'))),
        'saldo_base_f': _to_float(snapshot.get('saldo_base', Decimal('0.00'))),
        'fecha_base': _date_iso(snapshot.get('fecha_base')),
        'ultimo_arqueo_id': snapshot.get('ultimo_arqueo_id'),
        'criterio': 'CONFIRMADOS · misma caja · movimientos no cerrados en arqueos anteriores · fecha exacta para movimientos del día.',
    }



def _stored_snapshot_public(arqueo):
    return {
        'caja_id': arqueo['caja_id'],
        'fecha_arqueo': _date_iso(arqueo['fecha_arqueo']),
        'saldo_anterior_f': _to_float(arqueo['saldo_anterior']),
        'ingresos_dia_f': _to_float(arqueo['ingresos_dia']),
        'egresos_dia_f': _to_float(arqueo['egresos_dia']),
        'saldo_teorico_f': _to_float(arqueo['saldo_teorico']),
        'diferencia_f': _to_float(arqueo['diferencia']) if arqueo['diferencia'] is not None else None,
        'movimientos_dia': [],
        'conteo_movimientos_dia': None,
        'conteo_movimientos_anteriores': None,
        'ingresos_anteriores_f': None,
        'egresos_anteriores_f': None,
        'saldo_base_f': None,
        'fecha_base': None,
        'ultimo_arqueo_id': None,
        'criterio': 'Snapshot guardado en el arqueo. Los arqueos confirmados no se recalculan visualmente.',
    }



def _get_ultimo_arqueo_confirmado_anterior(db, caja_id, fecha_arqueo):
    rows = db.execute_query(
        """
        SELECT
            id,
            fecha_arqueo,
            saldo_teorico
        FROM contabilidad.arqueo_caja
        WHERE caja_id = %s
          AND estado = 'CONFIRMADO'
          AND fecha_arqueo < %s
        ORDER BY fecha_arqueo DESC, id DESC
        LIMIT 1
        """,
        (caja_id, fecha_arqueo),
    )
    return rows[0] if rows else None



def _get_caja_snapshot(db, caja_id, fecha_arqueo):
    caja_id = _parse_int(caja_id, 'Caja')
    fecha_arqueo = _parse_date(fecha_arqueo, 'Fecha de arqueo')

    ultimo_arqueo = _get_ultimo_arqueo_confirmado_anterior(db, caja_id, fecha_arqueo)
    fecha_base = ultimo_arqueo['fecha_arqueo'] if ultimo_arqueo else None
    saldo_base = _money(ultimo_arqueo['saldo_teorico']) if ultimo_arqueo else Decimal('0.00')

    # Se consulta hasta la fecha del arqueo y se descartan los movimientos ya
    # cerrados por arqueos confirmados anteriores. Cuando existe detalle guardado,
    # el filtro se hace por identidad del movimiento para no perder operaciones
    # confirmadas tardíamente con fecha anterior al último corte.
    rows = _get_caja_movimientos_confirmados(db, caja_id, fecha_arqueo)
    rows = _filtrar_movimientos_no_cerrados(db, caja_id, rows, ultimo_arqueo)

    ingresos_anteriores = Decimal('0.00')
    egresos_anteriores = Decimal('0.00')
    ingresos_dia = Decimal('0.00')
    egresos_dia = Decimal('0.00')
    movimientos_dia = []
    conteo_anteriores = 0

    for row in rows:
        monto = _money(row['monto'])
        es_dia = row['fecha'] == fecha_arqueo
        es_ingreso = row['flujo'] == 'INGRESO'

        if es_dia:
            movimientos_dia.append(_public_movimiento(row))
            if es_ingreso:
                ingresos_dia += monto
            else:
                egresos_dia += monto
        else:
            conteo_anteriores += 1
            if es_ingreso:
                ingresos_anteriores += monto
            else:
                egresos_anteriores += monto

    saldo_anterior = (saldo_base + ingresos_anteriores - egresos_anteriores).quantize(CUANTIA, rounding=ROUND_HALF_UP)
    ingresos_dia = ingresos_dia.quantize(CUANTIA, rounding=ROUND_HALF_UP)
    egresos_dia = egresos_dia.quantize(CUANTIA, rounding=ROUND_HALF_UP)
    saldo_teorico = (saldo_anterior + ingresos_dia - egresos_dia).quantize(CUANTIA, rounding=ROUND_HALF_UP)

    return {
        'caja_id': caja_id,
        'fecha_arqueo': fecha_arqueo,
        'saldo_anterior': saldo_anterior,
        'ingresos_dia': ingresos_dia,
        'egresos_dia': egresos_dia,
        'saldo_teorico': saldo_teorico,
        'saldo_base': saldo_base.quantize(CUANTIA, rounding=ROUND_HALF_UP),
        'fecha_base': fecha_base,
        'ultimo_arqueo_id': ultimo_arqueo['id'] if ultimo_arqueo else None,
        'ingresos_anteriores': ingresos_anteriores.quantize(CUANTIA, rounding=ROUND_HALF_UP),
        'egresos_anteriores': egresos_anteriores.quantize(CUANTIA, rounding=ROUND_HALF_UP),
        'movimientos_dia': movimientos_dia,
        'conteo_movimientos_dia': len(movimientos_dia),
        'conteo_movimientos_anteriores': conteo_anteriores,
    }


def _compute_difference(saldo_teorico, monto_contado):
    if monto_contado is None:
        return None
    return (monto_contado - _money(saldo_teorico)).quantize(CUANTIA, rounding=ROUND_HALF_UP)



def _validate_confirmable(record):
    if record['monto_contado'] is None:
        raise ValueError('Debes registrar el monto contado antes de confirmar el arqueo.')

    diferencia = _money(record['diferencia'])
    observacion = _clean(record.get('observacion'))
    if diferencia != Decimal('0.00') and not observacion:
        raise ValueError('Cuando existe diferencia en el arqueo, la observación es obligatoria.')



def _assert_unique_confirmed(db, caja_id, fecha_arqueo, exclude_id=None):
    sql = """
        SELECT id
        FROM contabilidad.arqueo_caja
        WHERE caja_id = %s
          AND fecha_arqueo = %s
          AND estado = 'CONFIRMADO'
    """
    params = [caja_id, fecha_arqueo]
    if exclude_id:
        sql += ' AND id <> %s'
        params.append(exclude_id)
    sql += ' LIMIT 1'
    rows = db.execute_query(sql, tuple(params))
    if rows:
        raise ValueError('Ya existe un arqueo confirmado para esa caja en la fecha seleccionada.')


# ============================================================
# Consultas del módulo
# ============================================================

def _get_arqueo(db, arqueo_id):
    rows = db.execute_query(
        """
        SELECT
            a.id,
            a.caja_id,
            a.fecha_arqueo,
            a.saldo_anterior,
            a.ingresos_dia,
            a.egresos_dia,
            a.saldo_teorico,
            a.monto_contado,
            a.diferencia,
            a.observacion,
            a.estado,
            a.usuario_nombre,
            a.creado_en,
            a.actualizado_en,
            c.codigo AS caja_codigo,
            c.nombre AS caja_nombre,
            c.cuenta_contable_codigo,
            NULL::bigint AS unidad_negocio_id,
            ''::text AS unidad_negocio_codigo,
            'General'::text AS unidad_negocio_nombre,
            cu.nombre AS cuenta_contable_nombre
        FROM contabilidad.arqueo_caja a
        INNER JOIN contabilidad.caja c ON c.id = a.caja_id
        LEFT JOIN {tabla} cu ON cu.codigo = c.cuenta_contable_codigo
        WHERE a.id = %s
        LIMIT 1
        """.format(tabla=_tabla_cuentas(db)),
        (arqueo_id,),
    )
    return rows[0] if rows else None



def _get_index_rows(db, filtros):
    clauses = []
    params = []

    if filtros.get('fecha_desde'):
        clauses.append('a.fecha_arqueo >= %s')
        params.append(filtros['fecha_desde'])
    if filtros.get('fecha_hasta'):
        clauses.append('a.fecha_arqueo <= %s')
        params.append(filtros['fecha_hasta'])
    if filtros.get('caja_id'):
        clauses.append('a.caja_id = %s')
        params.append(filtros['caja_id'])
    if filtros.get('estado'):
        clauses.append('a.estado = %s')
        params.append(filtros['estado'])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''

    rows = db.execute_query(
        f"""
        SELECT
            a.id,
            a.caja_id,
            a.fecha_arqueo,
            a.saldo_anterior,
            a.ingresos_dia,
            a.egresos_dia,
            a.saldo_teorico,
            a.monto_contado,
            a.diferencia,
            a.observacion,
            a.estado,
            a.usuario_nombre,
            a.creado_en,
            a.actualizado_en,
            c.codigo AS caja_codigo,
            c.nombre AS caja_nombre,
            NULL::bigint AS unidad_negocio_id,
            ''::text AS unidad_negocio_codigo,
            'General'::text AS unidad_negocio_nombre
        FROM contabilidad.arqueo_caja a
        INNER JOIN contabilidad.caja c ON c.id = a.caja_id
        {where}
        ORDER BY a.fecha_arqueo DESC, a.id DESC
        """,
        tuple(params) if params else None,
    )

    result = []
    for row in rows:
        diferencia = _money(row['diferencia']) if row['diferencia'] is not None else None
        item = dict(row)
        item['fecha_arqueo_iso'] = _date_iso(row['fecha_arqueo'])
        item['saldo_anterior_f'] = _to_float(row['saldo_anterior'])
        item['ingresos_dia_f'] = _to_float(row['ingresos_dia'])
        item['egresos_dia_f'] = _to_float(row['egresos_dia'])
        item['saldo_teorico_f'] = _to_float(row['saldo_teorico'])
        item['monto_contado_f'] = _to_float(row['monto_contado']) if row['monto_contado'] is not None else None
        item['diferencia_f'] = _to_float(diferencia) if diferencia is not None else None
        result.append(item)
    return result



def _build_index_summary(rows):
    total = len(rows)
    confirmados = sum(1 for row in rows if row['estado'] == 'CONFIRMADO')
    con_diferencia = sum(1 for row in rows if _money(row['diferencia_f'] or 0) != Decimal('0.00'))
    monto_diferencia = sum((_money(row['diferencia_f']) for row in rows if row['diferencia_f'] is not None), Decimal('0.00'))

    return {
        'total': total,
        'confirmados': confirmados,
        'con_diferencia': con_diferencia,
        'monto_diferencia': _to_float(monto_diferencia),
    }



def _build_form_context(db, arqueo=None):
    include_ids = [arqueo['caja_id']] if arqueo else []
    cajas = _get_cajas_activas(db, include_ids=include_ids)

    if arqueo:
        selected_caja_id = arqueo['caja_id']
        selected_fecha = arqueo['fecha_arqueo']
        resumen = _stored_snapshot_public(arqueo)
    else:
        selected_caja_id = cajas[0]['id'] if cajas else None
        selected_fecha = date.today()
        snapshot = _get_caja_snapshot(db, selected_caja_id, selected_fecha) if selected_caja_id else None
        resumen = _snapshot_public(snapshot) if snapshot else {
            'caja_id': None,
            'fecha_arqueo': _date_iso(selected_fecha),
            'saldo_anterior_f': 0.0,
            'ingresos_dia_f': 0.0,
            'egresos_dia_f': 0.0,
            'saldo_teorico_f': 0.0,
            'movimientos_dia': [],
            'conteo_movimientos_dia': 0,
            'conteo_movimientos_anteriores': 0,
            'saldo_base_f': 0.0,
            'fecha_base': None,
            'ultimo_arqueo_id': None,
            'criterio': 'No existen cajas activas para calcular el arqueo.',
        }

    return {
        'catalogs': {
            'cajas': cajas,
            'estados': ESTADOS_DOCUMENTO,
        },
        'form_defaults': {
            'caja_id': selected_caja_id,
            'fecha_arqueo': _date_iso(selected_fecha),
        },
        'resumen': resumen,
    }


# ============================================================
# PDF del comprobante de arqueo
# ============================================================

def _detalle_operaciones_pdf(detalle_rows):
    rows = []
    for idx, row in enumerate(detalle_rows or [], start=1):
        unidad = f"{row.get('unidad_negocio_codigo') or ''} - {row.get('unidad_negocio_nombre') or ''}".strip(' -')
        referencia = row.get('referencia') or ''
        glosa = row.get('glosa') or ''
        glosa_ref = glosa
        if referencia:
            glosa_ref = f'{glosa} / Ref: {referencia}' if glosa else f'Ref: {referencia}'

        rows.append([
            idx,
            format_date(row.get('fecha')),
            'Del dia' if row.get('clasificacion') == 'DIA' else 'Anterior',
            row.get('origen_doc') or '-',
            f"#{row.get('documento_id')}",
            row.get('flujo') or '-',
            unidad or '-',
            glosa_ref or '-',
            format_money(row.get('monto')),
        ])
    return rows


def _build_arqueo_pdf_bytes(arqueo, detalle_rows, fuente_trazabilidad):
    generado = datetime.now().strftime('%d/%m/%Y %H:%M')
    caja_nombre = f"{arqueo.get('caja_codigo') or ''} - {arqueo.get('caja_nombre') or ''}".strip(' -')
    cuenta_caja = f"{arqueo.get('cuenta_contable_codigo') or ''} - {arqueo.get('cuenta_contable_nombre') or ''}".strip(' -')
    diferencia = _money(arqueo.get('diferencia')) if arqueo.get('diferencia') is not None else Decimal('0.00')

    ingresos_anteriores = sum(
        (_money(row.get('monto')) for row in detalle_rows or [] if row.get('clasificacion') == 'ANTERIOR' and row.get('flujo') == 'INGRESO'),
        Decimal('0.00'),
    )
    egresos_anteriores = sum(
        (_money(row.get('monto')) for row in detalle_rows or [] if row.get('clasificacion') == 'ANTERIOR' and row.get('flujo') == 'EGRESO'),
        Decimal('0.00'),
    )

    movimientos_dia = sum(1 for row in detalle_rows or [] if row.get('clasificacion') == 'DIA')
    movimientos_anteriores = sum(1 for row in detalle_rows or [] if row.get('clasificacion') == 'ANTERIOR')

    sections = [
        {
            'title': 'Identificacion del arqueo',
            'items': [
                {'label': 'Arqueo', 'value': f"#{arqueo.get('id')}"},
                {'label': 'Fecha del arqueo', 'value': format_date(arqueo.get('fecha_arqueo'))},
                {'label': 'Estado', 'value': arqueo.get('estado') or '-'},
                {'label': 'Caja', 'value': caja_nombre or '-'},
                {'label': 'Cuenta contable', 'value': cuenta_caja or '-'},
                {'label': 'Usuario', 'value': arqueo.get('usuario_nombre') or '-'},
                {'label': 'Creado en', 'value': format_date(arqueo.get('creado_en'))},
                {'label': 'Actualizado en', 'value': format_date(arqueo.get('actualizado_en'))},
                {'label': 'Fuente detalle', 'value': fuente_trazabilidad},
            ],
        },
        {
            'title': 'Resumen del arqueo',
            'items': [
                {'label': 'Saldo anterior', 'value': format_money(arqueo.get('saldo_anterior'))},
                {'label': 'Ingresos del dia', 'value': format_money(arqueo.get('ingresos_dia'))},
                {'label': 'Egresos del dia', 'value': format_money(arqueo.get('egresos_dia'))},
                {'label': 'Saldo teorico', 'value': format_money(arqueo.get('saldo_teorico'))},
                {'label': 'Monto contado', 'value': format_money(arqueo.get('monto_contado'))},
                {'label': 'Diferencia', 'value': format_money(diferencia)},
            ],
        },
        {
            'title': 'Trazabilidad del calculo',
            'items': [
                {'label': 'Movimientos del dia', 'value': movimientos_dia},
                {'label': 'Movimientos anteriores', 'value': movimientos_anteriores},
                {'label': 'Ingresos anteriores', 'value': format_money(ingresos_anteriores)},
                {'label': 'Egresos anteriores', 'value': format_money(egresos_anteriores)},
                {'label': 'Criterio', 'value': 'Solo movimientos CONFIRMADOS, misma caja y no cerrados en arqueos anteriores.'},
                {'label': 'Corte', 'value': 'Los movimientos anteriores no cerrados forman el saldo anterior.'},
            ],
        },
    ]

    notes = []
    if arqueo.get('observacion'):
        notes.append({'title': 'Observacion', 'text': arqueo.get('observacion')})

    detalle_columns = [
        {'label': '#', 'width': 6, 'align': 'center'},
        {'label': 'Fecha', 'width': 16, 'align': 'center'},
        {'label': 'Corte', 'width': 18, 'align': 'center'},
        {'label': 'Origen', 'width': 22, 'align': 'center'},
        {'label': 'Doc.', 'width': 12, 'align': 'center'},
        {'label': 'Flujo', 'width': 14, 'align': 'center'},
        {'label': 'Unidad', 'width': 28, 'align': 'left'},
        {'label': 'Glosa / referencia', 'width': 40, 'align': 'left'},
        {'label': 'Monto', 'width': 18, 'align': 'right'},
    ]

    return build_accounting_document_pdf(
        title='Comprobante de Arqueo de Caja',
        subtitle=f'DXT Conta - Tesoreria - Emitido {generado}',
        document_number=f"ARQ-{int(arqueo.get('id') or 0):06d}",
        state=arqueo.get('estado') or '-',
        sections=sections,
        notes=notes,
        detail_columns=detalle_columns,
        detail_rows=_detalle_operaciones_pdf(detalle_rows),
        totals=[
            {'label': 'Saldo teorico', 'value': format_money(arqueo.get('saldo_teorico'))},
            {'label': 'Monto contado', 'value': format_money(arqueo.get('monto_contado'))},
            {'label': 'Diferencia', 'value': format_money(diferencia)},
        ],
        emitted_by=_usuario_actual(),
        logo_file=logo_path(),
        generated_at=generado,
    )


# ============================================================
# Persistencia
# ============================================================

def _payload_to_record(db, payload, existing=None):
    caja = _get_caja_info(db, payload.get('caja_id'), required=True, active_only=True)
    fecha_arqueo = _parse_date(payload.get('fecha_arqueo'), 'Fecha de arqueo')
    observacion = _normalize_text(payload.get('observacion'), 'Observación', 500, required=False)
    monto_contado = _decimal(
        payload.get('monto_contado'),
        'Monto contado',
        allow_zero=True,
        quant=CUANTIA,
        required=False,
    )

    snapshot = _get_caja_snapshot(db, caja['id'], fecha_arqueo)
    diferencia = _compute_difference(snapshot['saldo_teorico'], monto_contado)

    return {
        'caja_id': caja['id'],
        'fecha_arqueo': fecha_arqueo,
        'saldo_anterior': snapshot['saldo_anterior'],
        'ingresos_dia': snapshot['ingresos_dia'],
        'egresos_dia': snapshot['egresos_dia'],
        'saldo_teorico': snapshot['saldo_teorico'],
        'monto_contado': monto_contado,
        'diferencia': diferencia,
        'observacion': observacion,
        'estado': existing['estado'] if existing else 'BORRADOR',
        'usuario_nombre': existing['usuario_nombre'] if existing else _usuario_actual(),
        'snapshot_ui': snapshot,
    }



def _insert_arqueo(db, record):
    return db.execute_insert(
        """
        INSERT INTO contabilidad.arqueo_caja (
            caja_id,
            fecha_arqueo,
            saldo_anterior,
            ingresos_dia,
            egresos_dia,
            saldo_teorico,
            monto_contado,
            diferencia,
            observacion,
            estado,
            usuario_nombre
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record['caja_id'],
            record['fecha_arqueo'],
            record['saldo_anterior'],
            record['ingresos_dia'],
            record['egresos_dia'],
            record['saldo_teorico'],
            record['monto_contado'],
            record['diferencia'],
            record['observacion'],
            record['estado'],
            record['usuario_nombre'],
        ),
    )



def _update_arqueo(db, arqueo_id, record):
    db.execute_update(
        """
        UPDATE contabilidad.arqueo_caja
        SET
            caja_id = %s,
            fecha_arqueo = %s,
            saldo_anterior = %s,
            ingresos_dia = %s,
            egresos_dia = %s,
            saldo_teorico = %s,
            monto_contado = %s,
            diferencia = %s,
            observacion = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            record['caja_id'],
            record['fecha_arqueo'],
            record['saldo_anterior'],
            record['ingresos_dia'],
            record['egresos_dia'],
            record['saldo_teorico'],
            record['monto_contado'],
            record['diferencia'],
            record['observacion'],
            arqueo_id,
        ),
    )


# ============================================================
# Vistas
# ============================================================

@tesoreria_arqueo_caja_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    filtros = {
        'fecha_desde': _parse_date(request.args.get('fecha_desde'), 'Fecha desde', required=False),
        'fecha_hasta': _parse_date(request.args.get('fecha_hasta'), 'Fecha hasta', required=False),
        'caja_id': _parse_int(request.args.get('caja_id'), 'Caja', required=False),
        'estado': _clean(request.args.get('estado')) or None,
    }

    with DatabaseManager() as db:
        cajas = _get_cajas_activas(db)
        rows = _get_index_rows(db, filtros)
        resumen = _build_index_summary(rows)

    return render_template(
        'arqueos_index.html',
        filtros=filtros,
        rows=rows,
        resumen=resumen,
        cajas=cajas,
        puede_editar=_puede_editar(),
    )


@tesoreria_arqueo_caja_bp.route('/nuevo')
@login_required
@roles_required(ROLES_LECTURA)
def nuevo():
    with DatabaseManager() as db:
        context = _build_form_context(db, arqueo=None)

    return render_template(
        'arqueo_form.html',
        mode='create',
        arqueo_data=None,
        puede_editar=_puede_editar(),
        **context,
    )


@tesoreria_arqueo_caja_bp.route('/<int:arqueo_id>/editar')
@login_required
@roles_required(ROLES_LECTURA)
def editar(arqueo_id):
    with DatabaseManager() as db:
        arqueo = _get_arqueo(db, arqueo_id)
        if not arqueo:
            flash('El arqueo solicitado no existe.', 'warning')
            return redirect(url_for('tesoreria_arqueo_caja.index'))
        context = _build_form_context(db, arqueo=arqueo)

    return render_template(
        'arqueo_form.html',
        mode='edit',
        arqueo_data=arqueo,
        puede_editar=_puede_editar(),
        **context,
    )


@tesoreria_arqueo_caja_bp.route('/<int:arqueo_id>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def arqueo_pdf(arqueo_id):
    try:
        with DatabaseManager() as db:
            arqueo = _get_arqueo(db, arqueo_id)
            if not arqueo:
                return render_template('errors/404.html'), 404

            detalle_rows, fuente_trazabilidad = _get_arqueo_detalle_pdf_rows(db, arqueo)
            pdf_bytes = _build_arqueo_pdf_bytes(arqueo, detalle_rows, fuente_trazabilidad)
            fecha_doc = arqueo['fecha_arqueo'].strftime('%Y%m%d') if arqueo.get('fecha_arqueo') else datetime.now().strftime('%Y%m%d')
            nombre = f"arqueo_caja_{int(arqueo_id):06d}_{fecha_doc}.pdf"
            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'inline; filename={nombre}'},
            )
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del arqueo de caja. {exc}', status=500)


# ============================================================
# APIs
# ============================================================

@tesoreria_arqueo_caja_bp.route('/api/resumen-caja')
@login_required
@roles_required(ROLES_LECTURA)
def api_resumen_caja():
    try:
        caja_id = _parse_int(request.args.get('caja_id'), 'Caja')
        fecha_arqueo = _parse_date(request.args.get('fecha_arqueo'), 'Fecha de arqueo')
        with DatabaseManager() as db:
            caja = _get_caja_info(db, caja_id, required=True, active_only=True)
            snapshot = _get_caja_snapshot(db, caja_id, fecha_arqueo)
            resumen = _snapshot_public(snapshot)
            resumen['caja_codigo'] = caja['codigo']
            resumen['caja_nombre'] = caja['nombre']
        return _json_ok(resumen=resumen, data=resumen)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo recalcular el resumen de caja. {exc}', status=500)


@tesoreria_arqueo_caja_bp.route('/api/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_guardar():
    payload = request.get_json(silent=True) or {}
    arqueo_id = payload.get('id')

    try:
        with DatabaseManager() as db:
            existing = None
            if arqueo_id:
                existing = _get_arqueo(db, _parse_int(arqueo_id, 'ID', required=True))
                if not existing:
                    return _json_error('El arqueo solicitado no existe.', status=404)
                if existing['estado'] != 'BORRADOR':
                    return _json_error('Solo se puede editar un arqueo en borrador.', status=409)

            record = _payload_to_record(db, payload, existing=existing)
            if existing:
                _update_arqueo(db, existing['id'], record)
                target_id = existing['id']
                message = 'El arqueo fue actualizado correctamente.'
            else:
                target_id = _insert_arqueo(db, record)
                message = 'El arqueo fue guardado correctamente.'

            resumen = _snapshot_public(record['snapshot_ui'])
            return _json_ok(
                message,
                arqueo_id=target_id,
                resumen=resumen,
                data=resumen,
                diferencia=_to_float(record['diferencia']) if record['diferencia'] is not None else None,
            )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo guardar el arqueo. {exc}', status=500)


@tesoreria_arqueo_caja_bp.route('/api/<int:arqueo_id>/confirmar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_confirmar(arqueo_id):
    try:
        with DatabaseManager() as db:
            existing = _get_arqueo(db, arqueo_id)
            if not existing:
                return _json_error('El arqueo solicitado no existe.', status=404)
            if existing['estado'] != 'BORRADOR':
                return _json_error('Solo se puede confirmar un arqueo en borrador.', status=409)

            snapshot = _get_caja_snapshot(db, existing['caja_id'], existing['fecha_arqueo'])
            monto_contado = _money(existing['monto_contado']) if existing['monto_contado'] is not None else None
            diferencia = _compute_difference(snapshot['saldo_teorico'], monto_contado)

            record = {
                **existing,
                'saldo_anterior': snapshot['saldo_anterior'],
                'ingresos_dia': snapshot['ingresos_dia'],
                'egresos_dia': snapshot['egresos_dia'],
                'saldo_teorico': snapshot['saldo_teorico'],
                'monto_contado': monto_contado,
                'diferencia': diferencia,
            }

            _validate_confirmable(record)
            _assert_unique_confirmed(db, existing['caja_id'], existing['fecha_arqueo'], exclude_id=existing['id'])

            db.execute_update(
                """
                UPDATE contabilidad.arqueo_caja
                SET
                    saldo_anterior = %s,
                    ingresos_dia = %s,
                    egresos_dia = %s,
                    saldo_teorico = %s,
                    diferencia = %s,
                    estado = 'CONFIRMADO',
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    record['saldo_anterior'],
                    record['ingresos_dia'],
                    record['egresos_dia'],
                    record['saldo_teorico'],
                    record['diferencia'],
                    existing['id'],
                ),
            )
            _replace_arqueo_detalle_guardado(db, existing['id'], existing['caja_id'], existing['fecha_arqueo'])
            resumen = _snapshot_public(snapshot)
            return _json_ok(
                'El arqueo fue confirmado correctamente.',
                arqueo_id=existing['id'],
                resumen=resumen,
                data=resumen,
                diferencia=_to_float(diferencia) if diferencia is not None else None,
            )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f'No se pudo confirmar el arqueo. {exc}', status=500)


@tesoreria_arqueo_caja_bp.route('/api/<int:arqueo_id>/anular', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_anular(arqueo_id):
    try:
        with DatabaseManager() as db:
            existing = _get_arqueo(db, arqueo_id)
            if not existing:
                return _json_error('El arqueo solicitado no existe.', status=404)
            if existing['estado'] == 'ANULADO':
                return _json_error('El arqueo ya se encuentra anulado.', status=409)

            db.execute_update(
                """
                UPDATE contabilidad.arqueo_caja
                SET estado = 'ANULADO', actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (arqueo_id,),
            )
            return _json_ok('El arqueo fue anulado correctamente.', arqueo_id=arqueo_id)
    except Exception as exc:
        return _json_error(f'No se pudo anular el arqueo. {exc}', status=500)
