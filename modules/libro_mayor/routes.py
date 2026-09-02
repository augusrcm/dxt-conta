# ============================================================
# DXT CONTA - Módulo Libro Mayor
# ============================================================

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

from flask import Response, jsonify, render_template, request, session

from database.db_manager import DatabaseManager
from modules.libro_mayor import libro_mayor_bp
from utils.db import execute_query, execute_query_one
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

NATURALEZA_ACREEDORA = 'ACREEDORA'


# ============================================================
# Helpers base
# ============================================================

def _json_ok(**kwargs):
    payload = {'success': True}
    payload.update(kwargs)
    return jsonify(payload)


def _json_error(message, status=400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(payload), status


def _clean(value):
    return (value or '').strip()


def _gestion_actual():
    return date.today().year


def _parse_date(value, field_name):
    if not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.')


def _parse_optional_int(value, error_message='El valor seleccionado no es válido.'):
    value = _clean(value)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(error_message)


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

    return {
        'modo_periodo': modo,
        'gestion': gestion,
        'fecha_desde': desde,
        'fecha_hasta': hasta,
        'descripcion_periodo': descripcion,
    }


def _obtener_gestiones():
    sql = """
        SELECT DISTINCT EXTRACT(YEAR FROM fecha)::int AS gestion
        FROM contabilidad.asiento
        WHERE estado = %s
        ORDER BY gestion DESC
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (ESTADO_LIBRO,))
    if not rows:
        return [_gestion_actual()]
    return [row['gestion'] for row in rows]


def _obtener_cuenta(cuenta_codigo):
    if not cuenta_codigo:
        return None

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
        (cuenta_codigo,)
    )


def _obtener_auxiliar(auxiliar_id):
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


def _obtener_unidades_negocio():
    return execute_query(
        """
        SELECT
            id,
            codigo,
            nombre,
            activo
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
        """,
        fetchall=True
    )


def _obtener_unidad_negocio(unidad_negocio_id):
    if not unidad_negocio_id:
        return None

    return execute_query_one(
        """
        SELECT
            id,
            codigo,
            nombre,
            activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_negocio_id,)
    )


def _validar_filtros(args):
    periodo = _periodo_desde_filtros(args)

    cuenta_codigo = _clean(args.get('cuenta_codigo'))
    if not cuenta_codigo:
        raise ValueError('Debe seleccionar una cuenta contable.')

    cuenta = _obtener_cuenta(cuenta_codigo)
    if not cuenta:
        raise ValueError('La cuenta seleccionada no existe.')

    if not bool(cuenta.get('activo')):
        raise ValueError('La cuenta seleccionada no está activa.')

    if not bool(cuenta.get('es_postable')):
        raise ValueError('Solo se puede consultar Libro Mayor para cuentas postables.')

    auxiliar_id = _parse_optional_int(args.get('auxiliar_id'), 'El auxiliar seleccionado no es válido.')
    auxiliar = _obtener_auxiliar(auxiliar_id) if auxiliar_id else None
    if auxiliar_id and not auxiliar:
        raise ValueError('El auxiliar seleccionado no existe.')
    if auxiliar and not bool(auxiliar.get('activo')):
        raise ValueError('El auxiliar seleccionado no está activo.')

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'La unidad de negocio seleccionada no es válida.')
    unidad_negocio = _obtener_unidad_negocio(unidad_negocio_id) if unidad_negocio_id else None
    if unidad_negocio_id and not unidad_negocio:
        raise ValueError('La unidad de negocio seleccionada no existe.')
    if unidad_negocio and not bool(unidad_negocio.get('activo')):
        raise ValueError('La unidad de negocio seleccionada no está activa.')

    filtros = {
        **periodo,
        'cuenta_codigo': cuenta['codigo'],
        'cuenta_nombre': cuenta['nombre'] or '',
        'cuenta_naturaleza': cuenta.get('naturaleza') or '',
        'requiere_auxiliar': bool(cuenta.get('requiere_auxiliar')),
        'auxiliar_id': auxiliar['id'] if auxiliar else None,
        'auxiliar_nombre': auxiliar['nombre'] if auxiliar else '',
        'auxiliar_tipo': auxiliar.get('tipo') if auxiliar else '',
        'unidad_negocio_id': unidad_negocio['id'] if unidad_negocio else None,
        'unidad_negocio_codigo': unidad_negocio['codigo'] if unidad_negocio else '',
        'unidad_negocio_nombre': unidad_negocio['nombre'] if unidad_negocio else '',
    }

    return filtros


def _saldo_delta(naturaleza, debe, haber):
    debe = Decimal(debe or 0)
    haber = Decimal(haber or 0)
    if (naturaleza or '').upper() == NATURALEZA_ACREEDORA:
        return haber - debe
    return debe - haber


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


def _moneda_legible(row):
    moneda = (row.get('moneda_codigo') or '').strip()
    return moneda or 'Sin moneda'


def _consultar_saldo_anterior(filtros):
    sql = """
        SELECT
            COALESCE(SUM(ad.debe), 0) AS debe_anterior,
            COALESCE(SUM(ad.haber), 0) AS haber_anterior
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        WHERE a.estado = %s
          AND ad.cuenta_codigo = %s
          AND a.fecha < %s
          AND (%s IS NULL OR ad.auxiliar_id = %s)
          AND (%s IS NULL OR a.unidad_negocio_id = %s)
    """
    params = (
        ESTADO_LIBRO,
        filtros['cuenta_codigo'],
        filtros['fecha_desde'],
        filtros['auxiliar_id'],
        filtros['auxiliar_id'],
        filtros['unidad_negocio_id'],
        filtros['unidad_negocio_id'],
    )
    with DatabaseManager() as db:
        row = db.execute_query(sql, params)[0]

    debe_anterior = row['debe_anterior'] or Decimal('0')
    haber_anterior = row['haber_anterior'] or Decimal('0')
    saldo_anterior = _saldo_delta(filtros.get('cuenta_naturaleza'), debe_anterior, haber_anterior)

    return {
        'debe_anterior': debe_anterior,
        'haber_anterior': haber_anterior,
        'saldo_anterior': saldo_anterior,
    }


def _consultar_movimientos(filtros):
    sql = """
        SELECT
            a.id AS asiento_id,
            a.fecha,
            COALESCE(a.moneda_codigo, '') AS moneda_codigo,
            a.tipo_cambio,
            COALESCE(a.modulo_origen, '') AS modulo_origen,
            COALESCE(a.tabla_origen, '') AS tabla_origen,
            a.origen_id,
            COALESCE(NULLIF(a.referencia, 'None'), '') AS referencia_cabecera,
            COALESCE(a.glosa, '') AS glosa_cabecera,
            ad.id AS asiento_detalle_id,
            ad.secuencia,
            ad.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            ad.auxiliar_id,
            aux.nombre AS auxiliar_nombre,
            aux.tipo::text AS auxiliar_tipo,
            COALESCE(ad.glosa, '') AS glosa_linea,
            COALESCE(NULLIF(ad.referencia, 'None'), '') AS referencia_linea,
            COALESCE(ad.debe, 0) AS debe,
            COALESCE(ad.haber, 0) AS haber,
            a.unidad_negocio_id,
            COALESCE(un.codigo, '') AS unidad_negocio_codigo,
            COALESCE(un.nombre, '') AS unidad_negocio_nombre
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.auxiliar aux
            ON aux.id = ad.auxiliar_id
        LEFT JOIN contabilidad.unidad_negocio un
            ON un.id = a.unidad_negocio_id
        WHERE a.estado = %s
          AND ad.cuenta_codigo = %s
          AND a.fecha BETWEEN %s AND %s
          AND (%s IS NULL OR ad.auxiliar_id = %s)
          AND (%s IS NULL OR a.unidad_negocio_id = %s)
        ORDER BY a.fecha ASC, a.id ASC, ad.secuencia ASC, ad.id ASC
    """
    params = (
        ESTADO_LIBRO,
        filtros['cuenta_codigo'],
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        filtros['auxiliar_id'],
        filtros['auxiliar_id'],
        filtros['unidad_negocio_id'],
        filtros['unidad_negocio_id'],
    )
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    return rows


def _armar_resultado_mayor(filtros):
    saldo_info = _consultar_saldo_anterior(filtros)
    rows = _consultar_movimientos(filtros)

    saldo_corriente = saldo_info['saldo_anterior']
    total_debe = Decimal('0')
    total_haber = Decimal('0')
    movimientos = []
    unidades_presentes = set()
    monedas_presentes = set()

    for row in rows:
        debe = row['debe'] or Decimal('0')
        haber = row['haber'] or Decimal('0')
        total_debe += debe
        total_haber += haber
        saldo_corriente += _saldo_delta(filtros.get('cuenta_naturaleza'), debe, haber)

        referencia = row['referencia_linea'] or row['referencia_cabecera'] or ''
        detalle = row['glosa_linea'] or row['glosa_cabecera'] or ''

        unidad_id = row.get('unidad_negocio_id')
        unidad_codigo = row.get('unidad_negocio_codigo') or ''
        unidad_nombre = row.get('unidad_negocio_nombre') or ''
        if unidad_id:
            unidades_presentes.add(unidad_id)

        moneda = _moneda_legible(row)
        if moneda:
            monedas_presentes.add(moneda)

        movimientos.append({
            'fecha': row['fecha'],
            'asiento_id': row['asiento_id'],
            'moneda': moneda,
            'origen': _origen_legible(row),
            'secuencia': row['secuencia'],
            'referencia': referencia,
            'detalle': detalle,
            'debe': debe,
            'haber': haber,
            'saldo': saldo_corriente,
            'auxiliar_nombre': row['auxiliar_nombre'] or '',
            'unidad_negocio_id': unidad_id,
            'unidad_negocio_codigo': unidad_codigo,
            'unidad_negocio_nombre': unidad_nombre,
        })

    saldo_final = saldo_info['saldo_anterior'] + _saldo_delta(filtros.get('cuenta_naturaleza'), total_debe, total_haber)

    resumen = {
        'saldo_inicial': saldo_info['saldo_anterior'],
        'debe_periodo': total_debe,
        'haber_periodo': total_haber,
        'saldo_final': saldo_final,
        'movimientos': len(movimientos),
        'unidades_presentes': len(unidades_presentes),
        'monedas_presentes': len(monedas_presentes),
        'monedas': sorted(monedas_presentes),
    }

    return {
        'filtros': filtros,
        'movimientos': movimientos,
        'resumen': resumen,
    }


def _filas_json(movimientos):
    payload = []
    for row in movimientos:
        payload.append({
            'fecha': row['fecha'].strftime('%d/%m/%Y') if row['fecha'] else '',
            'fecha_iso': row['fecha'].isoformat() if row['fecha'] else '',
            'asiento': row['asiento_id'],
            'origen': row.get('origen') or '',
            'moneda': row.get('moneda') or '',
            'unidad': f"{row['unidad_negocio_codigo']} | {row['unidad_negocio_nombre']}" if row.get('unidad_negocio_codigo') else (row.get('unidad_negocio_nombre') or 'Sin unidad'),
            'secuencia': row['secuencia'],
            'referencia': row['referencia'] or '',
            'detalle': row['detalle'] or '',
            'debe': float(row['debe'] or 0),
            'haber': float(row['haber'] or 0),
            'saldo': float(row['saldo'] or 0),
        })
    return payload


def _resumen_json(resultado):
    resumen = resultado['resumen']
    filtros = resultado['filtros']
    return {
        'cuenta_codigo': filtros['cuenta_codigo'],
        'cuenta_nombre': filtros['cuenta_nombre'],
        'cuenta_naturaleza': filtros['cuenta_naturaleza'],
        'auxiliar_id': filtros['auxiliar_id'],
        'auxiliar_nombre': filtros['auxiliar_nombre'],
        'unidad_negocio_id': filtros['unidad_negocio_id'],
        'unidad_negocio_codigo': filtros['unidad_negocio_codigo'],
        'unidad_negocio_nombre': filtros['unidad_negocio_nombre'],
        'descripcion_periodo': filtros['descripcion_periodo'],
        'saldo_inicial': float(resumen['saldo_inicial'] or 0),
        'debe_periodo': float(resumen['debe_periodo'] or 0),
        'haber_periodo': float(resumen['haber_periodo'] or 0),
        'saldo_final': float(resumen['saldo_final'] or 0),
        'movimientos': resumen['movimientos'],
        'unidades_presentes': resumen['unidades_presentes'],
        'monedas_presentes': resumen['monedas_presentes'],
        'monedas': resumen['monedas'],
    }


def _fmt_money(value):
    return f"{Decimal(value or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _columnas_pdf():
    return [
        {'label': 'Fecha', 'width': 15, 'align': 'center'},
        {'label': 'Asiento', 'width': 13, 'align': 'center'},
        {'label': 'Origen', 'width': 28, 'align': 'left'},
        {'label': 'Mon.', 'width': 10, 'align': 'center'},
        {'label': 'Unidad', 'width': 27, 'align': 'left'},
        {'label': 'Ref.', 'width': 22, 'align': 'left'},
        {'label': 'Detalle', 'width': 58, 'align': 'left'},
        {'label': 'Debe', 'width': 19, 'align': 'right'},
        {'label': 'Haber', 'width': 19, 'align': 'right'},
        {'label': 'Saldo', 'width': 19, 'align': 'right'},
    ]


def _rows_pdf(resultado):
    rows = []
    resumen = resultado['resumen']

    rows.append([
        '',
        '',
        '',
        '',
        '',
        '',
        'SALDO INICIAL',
        '',
        '',
        _fmt_money(resumen['saldo_inicial']),
    ])

    for row in resultado['movimientos']:
        rows.append([
            row['fecha'].strftime('%d/%m/%Y') if row['fecha'] else '',
            row['asiento_id'],
            row.get('origen') or '',
            row.get('moneda') or '',
            f"{row['unidad_negocio_codigo']} | {row['unidad_negocio_nombre']}" if row.get('unidad_negocio_codigo') else (row.get('unidad_negocio_nombre') or 'Sin unidad'),
            row['referencia'] or '',
            row['detalle'] or '',
            _fmt_money(row['debe']),
            _fmt_money(row['haber']),
            _fmt_money(row['saldo']),
        ])

    rows.append([
        '',
        '',
        '',
        '',
        '',
        '',
        'TOTALES DEL PERÍODO',
        _fmt_money(resumen['debe_periodo']),
        _fmt_money(resumen['haber_periodo']),
        '',
    ])

    rows.append([
        '',
        '',
        '',
        '',
        '',
        '',
        'SALDO FINAL',
        '',
        '',
        _fmt_money(resumen['saldo_final']),
    ])

    return rows


# ============================================================
# Rutas auxiliares de búsqueda
# ============================================================

@libro_mayor_bp.route('/cuentas/buscar')
@login_required
@roles_required(ROLES_LECTURA)
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
            'naturaleza': row.get('naturaleza') or '',
        })

    return jsonify({'results': results})


@libro_mayor_bp.route('/auxiliares/buscar')
@login_required
@roles_required(ROLES_LECTURA)
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


# ============================================================
# Vistas principales
# ============================================================

@libro_mayor_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    hoy = date.today()
    return render_template(
        'libro_mayor_index.html',
        fecha_hoy=hoy.isoformat(),
        gestion_actual=hoy.year,
        gestiones=_obtener_gestiones(),
        unidades_negocio=_obtener_unidades_negocio(),
    )


@libro_mayor_bp.route('/datos')
@login_required
@roles_required(ROLES_LECTURA)
def datos():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_resultado_mayor(filtros)

        return _json_ok(
            rows=_filas_json(resultado['movimientos']),
            resumen=_resumen_json(resultado),
            filtros={
                'descripcion_periodo': filtros['descripcion_periodo'],
                'fecha_desde': filtros['fecha_desde'].isoformat(),
                'fecha_hasta': filtros['fecha_hasta'].isoformat(),
                'modo_periodo': filtros['modo_periodo'],
                'gestion': filtros['gestion'],
                'cuenta_codigo': filtros['cuenta_codigo'],
                'cuenta_nombre': filtros['cuenta_nombre'],
                'auxiliar_id': filtros['auxiliar_id'],
                'auxiliar_nombre': filtros['auxiliar_nombre'],
                'unidad_negocio_id': filtros['unidad_negocio_id'],
                'unidad_negocio_nombre': filtros['unidad_negocio_nombre'],
                'unidad_negocio_codigo': filtros['unidad_negocio_codigo'],
            },
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo consultar el libro mayor. {exc}', 500)


@libro_mayor_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_resultado_mayor(filtros)

        cuenta_texto = f"{filtros['cuenta_codigo']} | {filtros['cuenta_nombre']}"
        auxiliar_texto = filtros['auxiliar_nombre'] or 'Todos'
        unidad_texto = (f"{filtros['unidad_negocio_codigo']} | {filtros['unidad_negocio_nombre']}" if filtros.get('unidad_negocio_codigo') else (filtros.get('unidad_negocio_nombre') or 'Todas las unidades'))

        pdf_bytes = build_table_report_pdf(
            title='Libro Mayor',
            subtitle=f"{filtros['descripcion_periodo']} · Unidad: {unidad_texto}",
            columns=_columnas_pdf(),
            rows=_rows_pdf(resultado),
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
                f'Cuenta: {cuenta_texto}. '
                f'Naturaleza: {filtros.get("cuenta_naturaleza") or "No definida"}. '
                f'Auxiliar: {auxiliar_texto}. '
                f'Unidad: {unidad_texto}. '
                f'Comprobantes confirmados. '
                f'Fecha de emisión: {datetime.now().strftime("%d/%m/%Y %H:%M")}. '
                f'Movimientos: {resultado["resumen"]["movimientos"]}. '
                f'Monedas: {", ".join(resultado["resumen"].get("monedas") or []) or "Sin moneda"}.'
            ),
        )

        nombre = (
            f'libro_mayor_{filtros["cuenta_codigo"]}_'
            f'{filtros["fecha_desde"].strftime("%Y%m%d")}_'
            f'{filtros["fecha_hasta"].strftime("%Y%m%d")}.pdf'
        )
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del libro mayor. {exc}', 500)


# ============================================================
# Ayuda del módulo
# ============================================================

@libro_mayor_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('libro_mayor_help.html')