from datetime import date, datetime
from decimal import Decimal

from flask import jsonify, render_template, request, session, url_for
from database.db_manager import DatabaseManager
from modules.agenda_financiera import agenda_financiera_bp
from utils.decorators import login_required, roles_required


ROLES_LECTURA = [9, 10, 11]


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


def _parse_date(value, field_name='Fecha', required=True):
    if not value:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.')


def _parse_optional_int(value, field_name='Valor'):
    if value in (None, '', 'null', 'None'):
        return None
    try:
        parsed = int(str(value).strip())
    except Exception:
        raise ValueError(f'El campo "{field_name}" no es válido.')
    if parsed <= 0:
        raise ValueError(f'El campo "{field_name}" no es válido.')
    return parsed


def _decimal(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


def _puede_editar():
    try:
        return int(session.get('rol_id', 0)) in [9, 10]
    except Exception:
        return False


def _fetch_unidades_negocio(db):
    return db.execute_query(
        """
        SELECT
            id,
            codigo,
            nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC, id ASC
        """
    )


def _fetch_agenda_rows(db, fecha_corte, unidad_negocio_id=None):
    params = []
    unidad_filter_sql = ''
    if unidad_negocio_id is not None:
        unidad_filter_sql = ' AND c.unidad_negocio_id = %s '
        params.append(unidad_negocio_id)

    rows = db.execute_query(
        f"""
        SELECT
            c.id AS compromiso_id,
            c.codigo,
            c.tipo,
            c.nombre,
            c.descripcion,
            c.unidad_negocio_id,
            COALESCE(ung.codigo, '') AS unidad_negocio_codigo,
            COALESCE(ung.nombre, '') AS unidad_negocio_nombre,
            COALESCE(a.nombre, '') AS auxiliar_nombre,
            c.cuenta_contable,
            d.id AS detalle_id,
            d.fecha_vencimiento,
            COALESCE(d.monto_programado, 0) AS monto_programado,
            COALESCE(d.monto_registrado, 0) AS monto_registrado,
            GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) AS monto_pendiente,
            COALESCE(d.observacion, '') AS observacion
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio ung ON ung.id = c.unidad_negocio_id
        WHERE c.activo = true
          AND GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(d.monto_registrado, 0), 0) > 0
          {unidad_filter_sql}
        ORDER BY
            d.fecha_vencimiento ASC,
            c.tipo ASC,
            c.codigo ASC,
            d.id ASC
        """,
        tuple(params),
    )

    mapped = []
    for row in rows:
        pendiente = _decimal(row['monto_pendiente'])
        due = row['fecha_vencimiento']
        dias = (fecha_corte - due).days if due else None
        counterpart = row['auxiliar_nombre'] or row['nombre'] or 'Sin referencia'
        unidad_codigo = row['unidad_negocio_codigo'] or ''
        unidad_nombre = row['unidad_negocio_nombre'] or ''
        if unidad_codigo and unidad_nombre:
            unidad_label = f'{unidad_codigo} · {unidad_nombre}'
        else:
            unidad_label = unidad_nombre or unidad_codigo or 'Sin unidad asignada'

        mapped.append({
            'compromiso_id': row['compromiso_id'],
            'detalle_id': row['detalle_id'],
            'codigo': row['codigo'],
            'tipo': row['tipo'],
            'nombre': row['nombre'] or '',
            'descripcion': row['descripcion'] or '',
            'auxiliar_nombre': row['auxiliar_nombre'] or '',
            'contraparte': counterpart,
            'cuenta_contable': row['cuenta_contable'] or '',
            'unidad_negocio_id': row['unidad_negocio_id'],
            'unidad_negocio_codigo': unidad_codigo,
            'unidad_negocio_nombre': unidad_nombre,
            'unidad_negocio_label': unidad_label,
            'fecha_vencimiento': due.isoformat() if due else '',
            'fecha_vencimiento_label': due.strftime('%d/%m/%Y') if due else '—',
            'monto_programado': float(_decimal(row['monto_programado'])),
            'monto_registrado': float(_decimal(row['monto_registrado'])),
            'monto_pendiente': float(pendiente),
            'observacion': row['observacion'] or '',
            'dias_atraso': dias if dias is not None and dias > 0 else 0,
            'es_hoy': bool(due and due == fecha_corte),
            'es_vencido': bool(due and due < fecha_corte),
            'detalle_url': url_for('compromisos.editar', compromiso_id=row['compromiso_id']),
        })

    return mapped


def _bucketize(rows):
    cobrar_hoy, pagar_hoy, cobrar_vencido, pagar_vencido = [], [], [], []

    for row in rows:
        if row['es_hoy']:
            if row['tipo'] == 'COBRAR':
                cobrar_hoy.append(row)
            elif row['tipo'] == 'PAGAR':
                pagar_hoy.append(row)
        elif row['es_vencido']:
            if row['tipo'] == 'COBRAR':
                cobrar_vencido.append(row)
            elif row['tipo'] == 'PAGAR':
                pagar_vencido.append(row)

    return {
        'cobrar_hoy': cobrar_hoy,
        'pagar_hoy': pagar_hoy,
        'cobrar_vencido': cobrar_vencido,
        'pagar_vencido': pagar_vencido,
    }


def _summary(rows):
    total = Decimal('0.00')
    for row in rows:
        total += _decimal(row['monto_pendiente'])
    return {'cantidad': len(rows), 'monto_total': float(total)}


def _build_payload(fecha_corte, unidad_negocio_id=None):
    with DatabaseManager() as db:
        unidades = _fetch_unidades_negocio(db)
        rows = _fetch_agenda_rows(db, fecha_corte, unidad_negocio_id=unidad_negocio_id)

    buckets = _bucketize(rows)

    selected_unidad = next((u for u in unidades if int(u['id']) == int(unidad_negocio_id)), None) if unidad_negocio_id else None

    return {
        'fecha_corte': fecha_corte.isoformat(),
        'fecha_corte_label': fecha_corte.strftime('%d/%m/%Y'),
        'puede_editar': _puede_editar(),
        'filtro_unidad_negocio_id': unidad_negocio_id,
        'filtro_unidad_negocio_label': (
            f"{selected_unidad['codigo']} · {selected_unidad['nombre']}" if selected_unidad else 'Todas las unidades'
        ),
        'unidades_negocio': [
            {
                'id': fila['id'],
                'codigo': fila['codigo'],
                'nombre': fila['nombre'],
                'label': f"{fila['codigo']} · {fila['nombre']}" if fila['codigo'] else fila['nombre'],
            }
            for fila in unidades
        ],
        'cards': {
            'cobrar_hoy': {
                'title': f'Cobrar {fecha_corte.strftime("%d/%m/%Y")}',
                'subtitle': 'Compromisos por cobrar en la fecha seleccionada.',
                'items': buckets['cobrar_hoy'],
                'summary': _summary(buckets['cobrar_hoy']),
                'empty': 'No tienes cobros pendientes para esta fecha.'
            },
            'pagar_hoy': {
                'title': f'Pagar {fecha_corte.strftime("%d/%m/%Y")}',
                'subtitle': 'Compromisos por pagar en la fecha seleccionada.',
                'items': buckets['pagar_hoy'],
                'summary': _summary(buckets['pagar_hoy']),
                'empty': 'No tienes pagos pendientes para esta fecha.'
            },
            'cobrar_vencido': {
                'title': 'Cobros vencidos',
                'subtitle': 'Quién debió pagarte y aún no lo hizo.',
                'items': buckets['cobrar_vencido'],
                'summary': _summary(buckets['cobrar_vencido']),
                'empty': 'No existen cobros vencidos pendientes.'
            },
            'pagar_vencido': {
                'title': 'Pagos vencidos',
                'subtitle': 'A quién debiste pagar y aún no registraste el pago.',
                'items': buckets['pagar_vencido'],
                'summary': _summary(buckets['pagar_vencido']),
                'empty': 'No existen pagos vencidos pendientes.'
            }
        }
    }


@agenda_financiera_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    payload = _build_payload(date.today())
    return render_template('agenda_financiera_index.html', payload=payload)


@agenda_financiera_bp.route('/api/resumen', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_resumen():
    try:
        fecha_corte = _parse_date(request.args.get('fecha'), 'Fecha', required=True)
        unidad_negocio_id = _parse_optional_int(request.args.get('unidad_negocio_id'), 'Unidad de Negocio')
        return _json_ok(data=_build_payload(fecha_corte, unidad_negocio_id=unidad_negocio_id))
    except ValueError as e:
        return _json_error(str(e))
    except Exception as e:
        return _json_error(f'No se pudo cargar la agenda financiera: {str(e)}', 500)


@agenda_financiera_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('agenda_financiera_help.html')
