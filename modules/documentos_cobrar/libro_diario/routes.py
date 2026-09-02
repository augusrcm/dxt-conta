# ============================================================
# DXT CONTA - Módulo Libro Diario
# ============================================================

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

from flask import Response, jsonify, render_template, request, session

from database.db_manager import DatabaseManager
from modules.libro_diario import libro_diario_bp
from utils.decorators import login_required, roles_required
from utils.reportes_pdf import build_table_report_pdf


ROLES_LECTURA = [9, 10, 11]
ESTADO_LIBRO = 'CONFIRMADO'

ORIGENES_LEGIBLES = {
    'TESORERIA_PAGOS': 'Tesorería · Pagos',
    'TESORERIA_COBROS': 'Tesorería · Cobros',
    'TESORERIA_MOVIMIENTOS': 'Tesorería · Caja/Bancos',
    'FACTURA_ELECTRONICA': 'Facturas Electrónicas',
    'SALDOS_INICIALES': 'Saldos Iniciales',
    'CIERRE_GESTION': 'Cierre de Gestión',
    'ASISTENTE_AJUSTES': 'Asistente de Ajustes',
    'CONTABILIDAD_MANUAL': 'Manual',
}


# ============================================================
# Helpers
# ============================================================

def _json_ok(**kwargs):
    payload = {'success': True}
    payload.update(kwargs)
    return jsonify(payload)



def _json_error(message, status=400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(payload), status



def _gestion_actual():
    return date.today().year



def _parse_date(value, field_name):
    if not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.')



def _usuario_actual():
    return (
        session.get('nombre_completo')
        or session.get('username')
        or session.get('usuario')
        or session.get('email')
        or 'Sistema'
    )



def _periodo_desde_filtros(args):
    hoy = date.today()
    modo = (args.get('modo_periodo') or 'rango').strip().lower()
    gestion = int(args.get('gestion') or hoy.year)
    fecha_desde = args.get('fecha_desde') or hoy.isoformat()
    fecha_hasta = args.get('fecha_hasta') or hoy.isoformat()
    unidad_negocio_id_raw = (args.get('unidad_negocio_id') or '').strip()

    if modo == 'gestion':
        desde = date(gestion, 1, 1)
        hasta = date(gestion, 12, 31)
        descripcion = f'Gestión {gestion}'
    else:
        desde = _parse_date(fecha_desde, 'Fecha desde')
        hasta = _parse_date(fecha_hasta, 'Fecha hasta')
        if hasta < desde:
            raise ValueError('La fecha hasta no puede ser menor a la fecha desde.')
        descripcion = f'Del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'
        modo = 'rango'

    unidad_negocio_id = None
    if unidad_negocio_id_raw:
        try:
            unidad_negocio_id = int(unidad_negocio_id_raw)
        except ValueError:
            raise ValueError('La unidad de negocio no es válida.')

    return {
        'modo_periodo': modo,
        'gestion': gestion,
        'fecha_desde': desde,
        'fecha_hasta': hasta,
        'descripcion_periodo': descripcion,
        'unidad_negocio_id': unidad_negocio_id,
    }



def _obtener_gestiones():
    sql = """
        SELECT DISTINCT EXTRACT(YEAR FROM fecha)::int AS gestion
        FROM asiento
        WHERE estado = %s
        ORDER BY gestion DESC
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (ESTADO_LIBRO,))
    if not rows:
        return [_gestion_actual()]
    return [row['gestion'] for row in rows]



def _obtener_unidades_negocio():
    sql = """
        SELECT id, codigo, nombre
        FROM unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
    """
    with DatabaseManager() as db:
        return db.execute_query(sql)



def _nombre_unidad_negocio(unidad_negocio_id):
    if not unidad_negocio_id:
        return 'Todas las unidades'
    sql = """
        SELECT codigo, nombre
        FROM unidad_negocio
        WHERE id = %s
        LIMIT 1
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (unidad_negocio_id,))
    if not rows:
        return 'Unidad no encontrada'
    row = rows[0]
    return f"{row['codigo']} · {row['nombre']}"



def _consultar_libro_diario(filtros):
    sql = """
        SELECT
            a.id AS asiento_id,
            a.fecha,
            a.moneda_codigo,
            a.tipo_cambio,
            a.glosa,
            COALESCE(NULLIF(a.referencia, 'None'), '') AS referencia,
            a.modulo_origen,
            a.tabla_origen,
            a.origen_id,
            a.estado,
            a.unidad_negocio_id,
            un.codigo AS unidad_negocio_codigo,
            un.nombre AS unidad_negocio_nombre,
            ad.secuencia,
            ad.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            aux.nombre AS auxiliar_nombre,
            cc.codigo AS centro_costo_codigo,
            cc.nombre AS centro_costo_nombre,
            COALESCE(ad.glosa, '') AS glosa_linea,
            COALESCE(NULLIF(ad.referencia, 'None'), '') AS referencia_linea,
            ad.debe,
            ad.haber
        FROM asiento a
        JOIN asiento_detalle ad ON ad.asiento_id = a.id
        LEFT JOIN cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN auxiliar aux ON aux.id = ad.auxiliar_id
        LEFT JOIN centro_costo cc ON cc.id = ad.centro_costo_id
        LEFT JOIN unidad_negocio un ON un.id = a.unidad_negocio_id
        WHERE a.estado = %s
          AND a.fecha BETWEEN %s AND %s
    """
    params = [ESTADO_LIBRO, filtros['fecha_desde'], filtros['fecha_hasta']]

    if filtros['unidad_negocio_id']:
        sql += " AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])

    sql += " ORDER BY a.fecha ASC, a.id ASC, ad.secuencia ASC"

    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))
    return rows



def _resumir(rows):
    asientos = set()
    total_debe = Decimal('0')
    total_haber = Decimal('0')
    unidades = set()
    lineas_sin_unidad = 0
    monedas = {}

    for row in rows:
        asientos.add(row['asiento_id'])
        unidad_id = row.get('unidad_negocio_id')
        if unidad_id:
            unidades.add(unidad_id)
        else:
            lineas_sin_unidad += 1

        debe = row['debe'] or Decimal('0')
        haber = row['haber'] or Decimal('0')
        total_debe += debe
        total_haber += haber

        moneda = (row.get('moneda_codigo') or 'SIN MONEDA').strip() or 'SIN MONEDA'
        if moneda not in monedas:
            monedas[moneda] = {'debe': Decimal('0'), 'haber': Decimal('0')}
        monedas[moneda]['debe'] += debe
        monedas[moneda]['haber'] += haber

    diferencia = (total_debe - total_haber).quantize(Decimal('0.01'))
    return {
        'asientos': len(asientos),
        'lineas': len(rows),
        'unidades': len(unidades),
        'lineas_sin_unidad': lineas_sin_unidad,
        'total_debe': float(total_debe),
        'total_haber': float(total_haber),
        'diferencia': float(diferencia),
        'cuadrado': diferencia == Decimal('0.00'),
        'monedas': [
            {
                'moneda': moneda,
                'debe': float(valores['debe']),
                'haber': float(valores['haber']),
                'diferencia': float((valores['debe'] - valores['haber']).quantize(Decimal('0.01'))),
            }
            for moneda, valores in sorted(monedas.items())
        ],
    }


def _clasificar_origen(row):
    origen = (row.get('modulo_origen') or '').strip().upper()
    tabla = (row.get('tabla_origen') or '').strip().lower()

    if origen == 'TESORERIA' and tabla == 'contabilidad.pago':
        return 'TESORERIA_PAGOS'
    if origen == 'TESORERIA' and tabla == 'contabilidad.cobro':
        return 'TESORERIA_COBROS'
    if origen == 'TESORERIA' and tabla == 'contabilidad.movimiento_tesoreria':
        return 'TESORERIA_MOVIMIENTOS'
    if tabla == 'contabilidad.factura_electronica':
        return 'FACTURA_ELECTRONICA'
    if origen == 'SALDOS_INICIALES':
        return 'SALDOS_INICIALES'
    if origen == 'CIERRE_GESTION':
        return 'CIERRE_GESTION'
    if origen == 'ASISTENTE_AJUSTES':
        return 'ASISTENTE_AJUSTES'
    if origen in {'MANUAL', 'CONTABILIDAD', ''}:
        return 'CONTABILIDAD_MANUAL'
    return origen or 'CONTABILIDAD_MANUAL'


def _origen_legible(row):
    clave = _clasificar_origen(row)
    base = ORIGENES_LEGIBLES.get(clave, clave.replace('_', ' ').title())
    origen_id = row.get('origen_id')
    return f'{base} #{origen_id}' if origen_id else base


def _unidad_legible(row):
    codigo = (row.get('unidad_negocio_codigo') or '').strip()
    nombre = (row.get('unidad_negocio_nombre') or '').strip()
    if codigo and nombre:
        return f'{codigo} | {nombre}'
    if nombre:
        return nombre
    if codigo:
        return codigo
    return 'Sin unidad'



def _filas_json(rows):
    payload = []
    for row in rows:
        payload.append({
            'fecha': row['fecha'].strftime('%d/%m/%Y') if row['fecha'] else '',
            'fecha_iso': row['fecha'].isoformat() if row['fecha'] else '',
            'asiento': row['asiento_id'],
            'secuencia': row['secuencia'],
            'glosa': row['glosa'] or '',
            'referencia': row['referencia'] or '',
            'cuenta': f"{row['cuenta_codigo']} | {row['cuenta_nombre'] or ''}",
            'auxiliar': row['auxiliar_nombre'] or '',
            'centro_costo': (
                f"{row['centro_costo_codigo']} | {row['centro_costo_nombre']}"
                if row['centro_costo_codigo'] else ''
            ),
            'glosa_linea': row['glosa_linea'] or '',
            'debe': float(row['debe'] or 0),
            'haber': float(row['haber'] or 0),
            'origen': _origen_legible(row),
            'origen_clave': _clasificar_origen(row),
            'unidad_negocio': _unidad_legible(row),
            'moneda': row['moneda_codigo'] or '',
            'tipo_cambio': float(row['tipo_cambio'] or 0),
        })
    return payload



def _columnas_pdf():
    return [
        {'label': 'Fecha', 'width': 16, 'align': 'center'},
        {'label': 'Asiento', 'width': 14, 'align': 'center'},
        {'label': 'Sec.', 'width': 10, 'align': 'center'},
        {'label': 'Unidad', 'width': 28, 'align': 'left'},
        {'label': 'Cuenta', 'width': 24, 'align': 'left'},
        {'label': 'Nombre de cuenta', 'width': 36, 'align': 'left'},
        {'label': 'Auxiliar', 'width': 24, 'align': 'left'},
        {'label': 'Glosa línea', 'width': 34, 'align': 'left'},
        {'label': 'Origen', 'width': 30, 'align': 'left'},
        {'label': 'Debe', 'width': 18, 'align': 'right'},
        {'label': 'Haber', 'width': 18, 'align': 'right'},
    ]



def _rows_pdf(rows):
    pdf_rows = []
    for row in rows:
        pdf_rows.append([
            row['fecha'].strftime('%d/%m/%Y') if row['fecha'] else '',
            row['asiento_id'],
            row['secuencia'],
            _unidad_legible(row),
            row['cuenta_codigo'],
            row['cuenta_nombre'] or '',
            row['auxiliar_nombre'] or '',
            row['glosa_linea'] or row['glosa'] or '',
            _origen_legible(row),
            f"{Decimal(row['debe'] or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
            f"{Decimal(row['haber'] or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
        ])
    return pdf_rows


# ============================================================
# Vistas
# ============================================================

@libro_diario_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    hoy = date.today()
    return render_template(
        'libro_diario_index.html',
        fecha_hoy=hoy.isoformat(),
        gestion_actual=hoy.year,
        gestiones=_obtener_gestiones(),
        unidades_negocio=_obtener_unidades_negocio(),
    )


@libro_diario_bp.route('/datos')
@login_required
@roles_required(ROLES_LECTURA)
def datos():
    try:
        filtros = _periodo_desde_filtros(request.args)
        rows = _consultar_libro_diario(filtros)
        resumen = _resumir(rows)
        return _json_ok(rows=_filas_json(rows), resumen=resumen, filtros={
            'descripcion_periodo': filtros['descripcion_periodo'],
            'fecha_desde': filtros['fecha_desde'].isoformat(),
            'fecha_hasta': filtros['fecha_hasta'].isoformat(),
            'modo_periodo': filtros['modo_periodo'],
            'gestion': filtros['gestion'],
            'unidad_negocio_id': filtros['unidad_negocio_id'] or '',
            'unidad_negocio_nombre': _nombre_unidad_negocio(filtros['unidad_negocio_id']),
        })
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo consultar el libro diario. {exc}', 500)


@libro_diario_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _periodo_desde_filtros(request.args)
        rows = _consultar_libro_diario(filtros)
        unidad_label = _nombre_unidad_negocio(filtros['unidad_negocio_id'])
        subtitulo = filtros['descripcion_periodo']
        if filtros['unidad_negocio_id']:
            subtitulo += f' · {unidad_label}'
        pdf_bytes = build_table_report_pdf(
            title='Libro Diario',
            subtitle=subtitulo,
            columns=_columnas_pdf(),
            rows=_rows_pdf(rows),
            orientation='landscape',
            emitted_by=_usuario_actual(),
            organization='DXT Conta',
            logo_path=os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                '..',
                'public',
                'images',
                'dxt',
                'dxt_logo.jpg',
            ),
            header_note=(
                f'Comprobantes confirmados. Fecha de emisión: {datetime.now().strftime("%d/%m/%Y %H:%M")}. '
                f'Registros: {len(rows)} líneas.'
            ),
        )
        nombre = f'libro_diario_{filtros["fecha_desde"].strftime("%Y%m%d")}_{filtros["fecha_hasta"].strftime("%Y%m%d")}.pdf'
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del libro diario. {exc}', 500)


# ============================================================
# Ayuda del módulo
# ============================================================
@libro_diario_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('libro_diario_help.html')
