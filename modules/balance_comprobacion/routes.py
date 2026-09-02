# ============================================================
# DXT CONTA - Módulo Balance de Comprobación
# ============================================================

from __future__ import annotations

import os
from datetime import date, datetime
from collections import OrderedDict
from decimal import Decimal

from flask import Response, jsonify, render_template, request, session

from database.db_manager import DatabaseManager
from modules.balance_comprobacion import balance_comprobacion_bp
from utils.db import execute_query
from utils.decorators import login_required, roles_required
from utils.reportes_pdf import build_table_report_pdf


ROLES_LECTURA = [9, 10, 11]
ESTADO_CONFIRMADO = 'CONFIRMADO'


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


def _clean(value):
    return (value or '').strip()


def _gestion_actual():
    return date.today().year


def _parse_date(value, field_name):
    if not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.') from exc


def _parse_optional_int(value, field_name):
    value = _clean(value)
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no es válido.') from exc


def _usuario_actual():
    return (
        session.get('nombre_completo')
        or session.get('username')
        or session.get('usuario')
        or session.get('email')
        or 'Sistema'
    )


def _obtener_gestiones():
    sql = """
        SELECT DISTINCT EXTRACT(YEAR FROM fecha)::int AS gestion
        FROM contabilidad.asiento
        WHERE estado = %s
        ORDER BY gestion DESC
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (ESTADO_CONFIRMADO,))
    if not rows:
        return [_gestion_actual()]
    return [row['gestion'] for row in rows]



def _obtener_unidades_negocio():
    sql = """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(nit, '') AS nit,
            activo
        FROM contabilidad.unidad_negocio
        ORDER BY activo DESC, codigo ASC, nombre ASC
    """
    with DatabaseManager() as db:
        return db.execute_query(sql)


def _obtener_unidad_negocio(unidad_negocio_id):
    if not unidad_negocio_id:
        return None

    sql = """
        SELECT
            id,
            codigo,
            nombre,
            COALESCE(nit, '') AS nit,
            activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (unidad_negocio_id,))
    return rows[0] if rows else None


def _periodo_desde_filtros(args):
    hoy = date.today()
    modo = (args.get('modo_periodo') or 'gestion').strip().lower()
    try:
        gestion = int(args.get('gestion') or hoy.year)
    except (TypeError, ValueError) as exc:
        raise ValueError('La gestión seleccionada no es válida.') from exc
    fecha_desde = args.get('fecha_desde') or hoy.isoformat()
    fecha_hasta = args.get('fecha_hasta') or hoy.isoformat()

    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestión seleccionada está fuera de rango.')

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


def _validar_rango_cuentas(cuenta_desde, cuenta_hasta):
    if cuenta_desde and cuenta_hasta and cuenta_desde > cuenta_hasta:
        raise ValueError('La cuenta desde no puede ser mayor a la cuenta hasta.')


def _validar_filtros(args):
    periodo = _periodo_desde_filtros(args)

    cuenta_desde = _clean(args.get('cuenta_desde'))
    cuenta_hasta = _clean(args.get('cuenta_hasta'))
    _validar_rango_cuentas(cuenta_desde, cuenta_hasta)

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de Negocio')
    unidad_negocio = _obtener_unidad_negocio(unidad_negocio_id) if unidad_negocio_id else None
    if unidad_negocio_id and not unidad_negocio:
        raise ValueError('La Unidad de Negocio seleccionada no existe.')

    return {
        **periodo,
        'cuenta_desde': cuenta_desde or None,
        'cuenta_hasta': cuenta_hasta or None,
        'unidad_negocio_id': unidad_negocio_id,
        'unidad_negocio': unidad_negocio,
    }


def _consultar_balance(filtros):
    sql = """
        SELECT
            ad.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            c.naturaleza::text AS naturaleza,
            a.moneda_codigo,
            COALESCE(m.simbolo, a.moneda_codigo) AS moneda_simbolo,
            COALESCE(SUM(CASE WHEN a.fecha < %s THEN ad.debe ELSE 0 END), 0) AS debe_anterior,
            COALESCE(SUM(CASE WHEN a.fecha < %s THEN ad.haber ELSE 0 END), 0) AS haber_anterior,
            COALESCE(SUM(CASE WHEN a.fecha BETWEEN %s AND %s THEN ad.debe ELSE 0 END), 0) AS debe_periodo,
            COALESCE(SUM(CASE WHEN a.fecha BETWEEN %s AND %s THEN ad.haber ELSE 0 END), 0) AS haber_periodo
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.moneda m
            ON m.codigo = a.moneda_codigo
        WHERE a.estado = %s
          AND a.fecha <= %s
          AND c.es_postable = TRUE
          AND (%s IS NULL OR a.unidad_negocio_id = %s)
          AND (%s IS NULL OR ad.cuenta_codigo >= %s)
          AND (%s IS NULL OR ad.cuenta_codigo <= %s)
        GROUP BY
            ad.cuenta_codigo,
            c.nombre,
            c.naturaleza,
            a.moneda_codigo,
            m.simbolo
        HAVING
            COALESCE(SUM(CASE WHEN a.fecha < %s THEN ad.debe ELSE 0 END), 0)
          + COALESCE(SUM(CASE WHEN a.fecha < %s THEN ad.haber ELSE 0 END), 0)
          + COALESCE(SUM(CASE WHEN a.fecha BETWEEN %s AND %s THEN ad.debe ELSE 0 END), 0)
          + COALESCE(SUM(CASE WHEN a.fecha BETWEEN %s AND %s THEN ad.haber ELSE 0 END), 0) <> 0
        ORDER BY ad.cuenta_codigo ASC, a.moneda_codigo ASC
    """
    params = (
        filtros['fecha_desde'],
        filtros['fecha_desde'],
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        ESTADO_CONFIRMADO,
        filtros['fecha_hasta'],
        filtros['unidad_negocio_id'],
        filtros['unidad_negocio_id'],
        filtros['cuenta_desde'],
        filtros['cuenta_desde'],
        filtros['cuenta_hasta'],
        filtros['cuenta_hasta'],
        filtros['fecha_desde'],
        filtros['fecha_desde'],
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
    )

    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)

    return rows



def _contar_unidades(filtros):
    sql = """
        SELECT COUNT(DISTINCT a.unidad_negocio_id) AS total
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        WHERE a.estado = %s
          AND a.fecha <= %s
          AND c.es_postable = TRUE
          AND a.unidad_negocio_id IS NOT NULL
          AND (%s IS NULL OR a.unidad_negocio_id = %s)
          AND (%s IS NULL OR ad.cuenta_codigo >= %s)
          AND (%s IS NULL OR ad.cuenta_codigo <= %s)
    """
    params = (
        ESTADO_CONFIRMADO,
        filtros['fecha_hasta'],
        filtros['unidad_negocio_id'],
        filtros['unidad_negocio_id'],
        filtros['cuenta_desde'],
        filtros['cuenta_desde'],
        filtros['cuenta_hasta'],
        filtros['cuenta_hasta'],
    )
    with DatabaseManager() as db:
        rows = db.execute_query(sql, params)
    if not rows:
        return 0
    return int(rows[0].get('total') or 0)


def _separar_deudor_acreedor(saldo):
    saldo = saldo or Decimal('0')
    if saldo > 0:
        return saldo, Decimal('0')
    if saldo < 0:
        return Decimal('0'), abs(saldo)
    return Decimal('0'), Decimal('0')


def _unidad_label(filtros):
    unidad = filtros.get('unidad_negocio')
    if not unidad:
        return 'Todas las unidades'
    codigo = unidad.get('codigo') or ''
    nombre = unidad.get('nombre') or ''
    if codigo and nombre:
        return f'{codigo} · {nombre}'
    return codigo or nombre or 'Unidad filtrada'


def _armar_balance(filtros):
    rows = _consultar_balance(filtros)

    filas = []
    total_saldo_ant_deudor = Decimal('0')
    total_saldo_ant_acreedor = Decimal('0')
    total_debe = Decimal('0')
    total_haber = Decimal('0')
    total_saldo_fin_deudor = Decimal('0')
    total_saldo_fin_acreedor = Decimal('0')
    total_por_moneda = OrderedDict()

    for row in rows:
        debe_anterior = row['debe_anterior'] or Decimal('0')
        haber_anterior = row['haber_anterior'] or Decimal('0')
        debe_periodo = row['debe_periodo'] or Decimal('0')
        haber_periodo = row['haber_periodo'] or Decimal('0')
        moneda_codigo = row.get('moneda_codigo') or 'SIN_MONEDA'
        moneda_simbolo = row.get('moneda_simbolo') or moneda_codigo

        saldo_anterior = debe_anterior - haber_anterior
        saldo_final = saldo_anterior + debe_periodo - haber_periodo

        saldo_ant_deudor, saldo_ant_acreedor = _separar_deudor_acreedor(saldo_anterior)
        saldo_fin_deudor, saldo_fin_acreedor = _separar_deudor_acreedor(saldo_final)

        total_saldo_ant_deudor += saldo_ant_deudor
        total_saldo_ant_acreedor += saldo_ant_acreedor
        total_debe += debe_periodo
        total_haber += haber_periodo
        total_saldo_fin_deudor += saldo_fin_deudor
        total_saldo_fin_acreedor += saldo_fin_acreedor

        if moneda_codigo not in total_por_moneda:
            total_por_moneda[moneda_codigo] = {
                'moneda_codigo': moneda_codigo,
                'moneda_simbolo': moneda_simbolo,
                'total_saldo_anterior_deudor': Decimal('0'),
                'total_saldo_anterior_acreedor': Decimal('0'),
                'total_debe': Decimal('0'),
                'total_haber': Decimal('0'),
                'total_saldo_final_deudor': Decimal('0'),
                'total_saldo_final_acreedor': Decimal('0'),
                'cantidad_cuentas': 0,
            }

        moneda_total = total_por_moneda[moneda_codigo]
        moneda_total['total_saldo_anterior_deudor'] += saldo_ant_deudor
        moneda_total['total_saldo_anterior_acreedor'] += saldo_ant_acreedor
        moneda_total['total_debe'] += debe_periodo
        moneda_total['total_haber'] += haber_periodo
        moneda_total['total_saldo_final_deudor'] += saldo_fin_deudor
        moneda_total['total_saldo_final_acreedor'] += saldo_fin_acreedor
        moneda_total['cantidad_cuentas'] += 1

        filas.append({
            'cuenta_codigo': row['cuenta_codigo'],
            'cuenta_nombre': row['cuenta_nombre'] or '',
            'naturaleza': row.get('naturaleza') or '',
            'moneda_codigo': moneda_codigo,
            'moneda_simbolo': moneda_simbolo,
            'saldo_anterior_deudor': saldo_ant_deudor,
            'saldo_anterior_acreedor': saldo_ant_acreedor,
            'debe_periodo': debe_periodo,
            'haber_periodo': haber_periodo,
            'saldo_final_deudor': saldo_fin_deudor,
            'saldo_final_acreedor': saldo_fin_acreedor,
        })

    for moneda_total in total_por_moneda.values():
        moneda_total['cuadrado_movimiento'] = moneda_total['total_debe'] == moneda_total['total_haber']
        moneda_total['cuadrado_saldo_final'] = (
            moneda_total['total_saldo_final_deudor'] == moneda_total['total_saldo_final_acreedor']
        )
        moneda_total['cuadrado'] = moneda_total['cuadrado_movimiento'] and moneda_total['cuadrado_saldo_final']

    resumen = {
        'total_saldo_anterior_deudor': total_saldo_ant_deudor,
        'total_saldo_anterior_acreedor': total_saldo_ant_acreedor,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'total_saldo_final_deudor': total_saldo_fin_deudor,
        'total_saldo_final_acreedor': total_saldo_fin_acreedor,
        'cantidad_cuentas': len(filas),
        'cantidad_unidades': _contar_unidades(filtros),
        'cantidad_monedas': len(total_por_moneda),
        'total_por_moneda': list(total_por_moneda.values()),
        'cuadrado_movimiento': all(item['cuadrado_movimiento'] for item in total_por_moneda.values()) if total_por_moneda else True,
        'cuadrado_saldo_final': all(item['cuadrado_saldo_final'] for item in total_por_moneda.values()) if total_por_moneda else True,
        'cuadrado': all(item['cuadrado'] for item in total_por_moneda.values()) if total_por_moneda else True,
    }

    return {
        'filtros': filtros,
        'filas': filas,
        'resumen': resumen,
    }



def _filas_json(resultado):
    payload = []
    for row in resultado['filas']:
        payload.append({
            'cuenta_codigo': row['cuenta_codigo'],
            'moneda_codigo': row['moneda_codigo'],
            'moneda_simbolo': row['moneda_simbolo'],
            'cuenta_nombre': row['cuenta_nombre'],
            'saldo_anterior_deudor': float(row['saldo_anterior_deudor'] or 0),
            'saldo_anterior_acreedor': float(row['saldo_anterior_acreedor'] or 0),
            'debe_periodo': float(row['debe_periodo'] or 0),
            'haber_periodo': float(row['haber_periodo'] or 0),
            'saldo_final_deudor': float(row['saldo_final_deudor'] or 0),
            'saldo_final_acreedor': float(row['saldo_final_acreedor'] or 0),
        })
    return payload


def _money_json(value):
    return float(value or 0)


def _total_moneda_json(total):
    return {
        'moneda_codigo': total['moneda_codigo'],
        'moneda_simbolo': total['moneda_simbolo'],
        'total_saldo_anterior_deudor': _money_json(total['total_saldo_anterior_deudor']),
        'total_saldo_anterior_acreedor': _money_json(total['total_saldo_anterior_acreedor']),
        'total_debe': _money_json(total['total_debe']),
        'total_haber': _money_json(total['total_haber']),
        'total_saldo_final_deudor': _money_json(total['total_saldo_final_deudor']),
        'total_saldo_final_acreedor': _money_json(total['total_saldo_final_acreedor']),
        'cantidad_cuentas': total['cantidad_cuentas'],
        'cuadrado_movimiento': bool(total['cuadrado_movimiento']),
        'cuadrado_saldo_final': bool(total['cuadrado_saldo_final']),
        'cuadrado': bool(total['cuadrado']),
    }


def _resumen_json(resultado):
    filtros = resultado['filtros']
    resumen = resultado['resumen']
    return {
        'descripcion_periodo': filtros['descripcion_periodo'],
        'cuenta_desde': filtros['cuenta_desde'] or '',
        'cuenta_hasta': filtros['cuenta_hasta'] or '',
        'unidad_negocio_id': filtros['unidad_negocio_id'] or '',
        'unidad_negocio_label': _unidad_label(filtros),
        'total_saldo_anterior_deudor': _money_json(resumen['total_saldo_anterior_deudor']),
        'total_saldo_anterior_acreedor': _money_json(resumen['total_saldo_anterior_acreedor']),
        'total_debe': _money_json(resumen['total_debe']),
        'total_haber': _money_json(resumen['total_haber']),
        'total_saldo_final_deudor': _money_json(resumen['total_saldo_final_deudor']),
        'total_saldo_final_acreedor': _money_json(resumen['total_saldo_final_acreedor']),
        'cantidad_cuentas': resumen['cantidad_cuentas'],
        'cantidad_unidades': resumen['cantidad_unidades'],
        'cantidad_monedas': resumen['cantidad_monedas'],
        'total_por_moneda': [_total_moneda_json(item) for item in resumen['total_por_moneda']],
        'cuadrado_movimiento': resumen['cuadrado_movimiento'],
        'cuadrado_saldo_final': resumen['cuadrado_saldo_final'],
        'cuadrado': resumen['cuadrado'],
    }


def _fmt_money(value):
    return f"{Decimal(value or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _descripcion_rango_cuentas(filtros):
    desde = filtros.get('cuenta_desde') or ''
    hasta = filtros.get('cuenta_hasta') or ''
    if desde and hasta:
        return f'Desde {desde} hasta {hasta}'
    if desde:
        return f'Desde {desde}'
    if hasta:
        return f'Hasta {hasta}'
    return 'Todas las cuentas'


def _columnas_pdf():
    return [
        {'label': 'Código', 'width': 20, 'align': 'left'},
        {'label': 'Moneda', 'width': 16, 'align': 'left'},
        {'label': 'Cuenta', 'width': 54, 'align': 'left'},
        {'label': 'Saldo Ant. Deudor', 'width': 24, 'align': 'right'},
        {'label': 'Saldo Ant. Acreedor', 'width': 24, 'align': 'right'},
        {'label': 'Debe', 'width': 22, 'align': 'right'},
        {'label': 'Haber', 'width': 22, 'align': 'right'},
        {'label': 'Saldo Final Deudor', 'width': 24, 'align': 'right'},
        {'label': 'Saldo Final Acreedor', 'width': 24, 'align': 'right'},
    ]


def _rows_pdf(resultado):
    rows = []
    for row in resultado['filas']:
        rows.append([
            row['cuenta_codigo'],
            row['moneda_codigo'],
            row['cuenta_nombre'],
            _fmt_money(row['saldo_anterior_deudor']),
            _fmt_money(row['saldo_anterior_acreedor']),
            _fmt_money(row['debe_periodo']),
            _fmt_money(row['haber_periodo']),
            _fmt_money(row['saldo_final_deudor']),
            _fmt_money(row['saldo_final_acreedor']),
        ])

    for total in resultado['resumen']['total_por_moneda']:
        rows.append([
            '',
            total['moneda_codigo'],
            f'TOTAL {total["moneda_codigo"]}',
            _fmt_money(total['total_saldo_anterior_deudor']),
            _fmt_money(total['total_saldo_anterior_acreedor']),
            _fmt_money(total['total_debe']),
            _fmt_money(total['total_haber']),
            _fmt_money(total['total_saldo_final_deudor']),
            _fmt_money(total['total_saldo_final_acreedor']),
        ])

    return rows



# ============================================================
# Búsqueda de cuentas
# ============================================================

@balance_comprobacion_bp.route('/cuentas/buscar')
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
        fetchall=True,
    )

    results = []
    for row in rows:
        naturaleza = row.get('naturaleza') or ''
        suffix = f' [{naturaleza}]' if naturaleza else ''
        results.append({
            'id': row['codigo'],
            'text': f"{row['codigo']} | {row['nombre']}{suffix}",
            'codigo': row['codigo'],
            'nombre': row['nombre'],
        })

    return jsonify({'results': results})


# ============================================================
# Vistas principales
# ============================================================

@balance_comprobacion_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    hoy = date.today()
    return render_template(
        'balance_comprobacion_index.html',
        fecha_hoy=hoy.isoformat(),
        gestion_actual=hoy.year,
        gestiones=_obtener_gestiones(),
        unidades_negocio=_obtener_unidades_negocio(),
    )


@balance_comprobacion_bp.route('/datos')
@login_required
@roles_required(ROLES_LECTURA)
def datos():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_balance(filtros)

        return _json_ok(
            rows=_filas_json(resultado),
            resumen=_resumen_json(resultado),
            filtros={
                'descripcion_periodo': filtros['descripcion_periodo'],
                'fecha_desde': filtros['fecha_desde'].isoformat(),
                'fecha_hasta': filtros['fecha_hasta'].isoformat(),
                'modo_periodo': filtros['modo_periodo'],
                'gestion': filtros['gestion'],
                'cuenta_desde': filtros['cuenta_desde'] or '',
                'cuenta_hasta': filtros['cuenta_hasta'] or '',
                'unidad_negocio_id': filtros['unidad_negocio_id'] or '',
            },
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:  # pragma: no cover - error defensivo
        return _json_error(f'No se pudo consultar el balance de comprobación. {exc}', 500)


@balance_comprobacion_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_balance(filtros)

        rango_cuentas = _descripcion_rango_cuentas(filtros)
        estado_cuadre = 'CUADRADO' if resultado['resumen']['cuadrado'] else 'DESCUADRADO'
        unidad_label = _unidad_label(filtros)

        pdf_bytes = build_table_report_pdf(
            title='Balance de Comprobación',
            subtitle=filtros['descripcion_periodo'],
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
                f'Unidad: {unidad_label}. '
                f'Rango de cuentas: {rango_cuentas}. '
                f'Estado: {estado_cuadre}. '
                f'Cuentas incluidas: {resultado["resumen"]["cantidad_cuentas"]}. '
                f'Unidades presentes: {resultado["resumen"]["cantidad_unidades"]}. '
                f'Monedas: {resultado["resumen"]["cantidad_monedas"]}. '
                f'Fecha de emisión: {datetime.now().strftime("%d/%m/%Y %H:%M")}. '
            ),
        )

        nombre = (
            f'balance_comprobacion_'
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
    except Exception as exc:  # pragma: no cover - error defensivo
        return _json_error(f'No se pudo generar el PDF del balance de comprobación. {exc}', 500)


# ============================================================
# Ayuda
# ============================================================

@balance_comprobacion_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('balance_comprobacion_help.html')
