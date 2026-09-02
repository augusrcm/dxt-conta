# ============================================================
# DXT CONTA - Módulo Estado de Resultados
# ============================================================

from __future__ import annotations

import os
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal

from flask import Response, jsonify, render_template, request, session

from database.db_manager import DatabaseManager
from modules.estado_resultados import estado_resultados_bp
from utils.decorators import login_required, roles_required
from utils.reportes_pdf import build_table_report_pdf


ROLES_LECTURA = [9, 10, 11]
ESTADO_CONFIRMADO = 'CONFIRMADO'

TIPO_INGRESO = 'INGRESO'
TIPO_COSTO = 'COSTO'
TIPO_GASTO = 'GASTO'
TIPOS_RESULTADO = (TIPO_INGRESO, TIPO_COSTO, TIPO_GASTO)


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


def _gestion_actual():
    return date.today().year


def _clean(value):
    return (value or '').strip()


def _parse_date(value, field_name):
    if not value:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.') from exc


def _parse_int(value, field_name):
    raw = _clean(value)
    if not raw:
        return None
    try:
        return int(raw)
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
        SELECT DISTINCT EXTRACT(YEAR FROM a.fecha)::int AS gestion
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        WHERE a.estado = %s
          AND c.tipo IN (%s, %s, %s)
        ORDER BY gestion DESC
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (ESTADO_CONFIRMADO, TIPO_INGRESO, TIPO_COSTO, TIPO_GASTO))
    if not rows:
        return [_gestion_actual()]
    return [row['gestion'] for row in rows]


def _obtener_unidades_negocio_activas():
    sql = """
        SELECT id, codigo, nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
    """
    with DatabaseManager() as db:
        return db.execute_query(sql)


def _resolver_unidad_negocio(filtros):
    unidad_id = filtros.get('unidad_negocio_id')
    if not unidad_id:
        return None

    sql = """
        SELECT id, codigo, nombre
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (unidad_id,))
    return rows[0] if rows else None


def _periodo_desde_filtros(args):
    hoy = date.today()
    modo = (args.get('modo_periodo') or 'gestion').strip().lower()
    try:
        gestion = int(args.get('gestion') or hoy.year)
    except (TypeError, ValueError) as exc:
        raise ValueError('La gestión seleccionada no es válida.') from exc

    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestión seleccionada está fuera de rango.')

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


def _validar_filtros(args):
    filtros = _periodo_desde_filtros(args)
    filtros['unidad_negocio_id'] = _parse_int(args.get('unidad_negocio_id'), 'Unidad de Negocio')

    if filtros['unidad_negocio_id'] and not _resolver_unidad_negocio(filtros):
        raise ValueError('La Unidad de Negocio seleccionada no existe.')

    return filtros


def _fmt_money(value):
    return f"{Decimal(value or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _fmt_monto_moneda(value, simbolo):
    simbolo = simbolo or ''
    return f'{simbolo} {_fmt_money(value)}'.strip()


def _monto_resultado(tipo_cuenta, debe, haber):
    debe = debe or Decimal('0')
    haber = haber or Decimal('0')

    if tipo_cuenta == TIPO_INGRESO:
        return haber - debe

    if tipo_cuenta in (TIPO_COSTO, TIPO_GASTO):
        return debe - haber

    return Decimal('0')


def _moneda_key(codigo, simbolo):
    codigo = codigo or 'SIN_MONEDA'
    simbolo = simbolo or codigo
    return codigo, simbolo


# ============================================================
# Consulta contable
# ============================================================

def _consultar_estado_resultados(filtros):
    sql = """
        SELECT
            c.tipo::text AS tipo,
            c.codigo,
            c.nombre,
            c.naturaleza::text AS naturaleza,
            a.moneda_codigo,
            COALESCE(m.simbolo, a.moneda_codigo, '') AS moneda_simbolo,
            COALESCE(SUM(ad.debe), 0) AS debe_periodo,
            COALESCE(SUM(ad.haber), 0) AS haber_periodo
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.moneda m
            ON m.codigo = a.moneda_codigo
        WHERE a.estado = %s
          AND a.fecha BETWEEN %s AND %s
          AND c.es_postable = TRUE
          AND c.tipo IN (%s, %s, %s)
    """
    params = [
        ESTADO_CONFIRMADO,
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        TIPO_INGRESO,
        TIPO_COSTO,
        TIPO_GASTO,
    ]

    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])

    sql += """
        GROUP BY
            c.tipo,
            c.codigo,
            c.nombre,
            c.naturaleza,
            a.moneda_codigo,
            m.simbolo
        HAVING COALESCE(SUM(ad.debe), 0) <> 0
            OR COALESCE(SUM(ad.haber), 0) <> 0
        ORDER BY c.tipo, c.codigo, a.moneda_codigo
    """

    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))

    return rows


def _contar_unidades_presentes(filtros):
    sql = """
        SELECT COUNT(DISTINCT a.unidad_negocio_id) AS total
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        WHERE a.estado = %s
          AND a.fecha BETWEEN %s AND %s
          AND c.es_postable = TRUE
          AND c.tipo IN (%s, %s, %s)
    """
    params = [
        ESTADO_CONFIRMADO,
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        TIPO_INGRESO,
        TIPO_COSTO,
        TIPO_GASTO,
    ]

    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])

    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))

    return int((rows[0]['total'] if rows else 0) or 0)


def _nuevo_total_moneda(codigo, simbolo):
    return {
        'moneda_codigo': codigo,
        'moneda_simbolo': simbolo,
        'total_ingresos': Decimal('0'),
        'total_costos': Decimal('0'),
        'total_gastos': Decimal('0'),
        'utilidad_bruta': Decimal('0'),
        'utilidad_neta': Decimal('0'),
    }


def _armar_estado_resultados(filtros):
    rows = _consultar_estado_resultados(filtros)

    secciones = {
        TIPO_INGRESO: [],
        TIPO_COSTO: [],
        TIPO_GASTO: [],
    }
    totales_por_moneda = OrderedDict()

    for row in rows:
        tipo = row['tipo']
        codigo = row['codigo']
        nombre = row['nombre'] or ''
        naturaleza = row.get('naturaleza') or ''
        moneda_codigo, moneda_simbolo = _moneda_key(row.get('moneda_codigo'), row.get('moneda_simbolo'))
        debe = row['debe_periodo'] or Decimal('0')
        haber = row['haber_periodo'] or Decimal('0')
        monto = _monto_resultado(tipo, debe, haber)

        if monto == 0:
            continue

        if moneda_codigo not in totales_por_moneda:
            totales_por_moneda[moneda_codigo] = _nuevo_total_moneda(moneda_codigo, moneda_simbolo)

        item = {
            'tipo': tipo,
            'codigo': codigo,
            'nombre': nombre,
            'naturaleza': naturaleza,
            'moneda_codigo': moneda_codigo,
            'moneda_simbolo': moneda_simbolo,
            'debe_periodo': debe,
            'haber_periodo': haber,
            'monto': monto,
        }
        secciones[tipo].append(item)

        if tipo == TIPO_INGRESO:
            totales_por_moneda[moneda_codigo]['total_ingresos'] += monto
        elif tipo == TIPO_COSTO:
            totales_por_moneda[moneda_codigo]['total_costos'] += monto
        elif tipo == TIPO_GASTO:
            totales_por_moneda[moneda_codigo]['total_gastos'] += monto

    for total in totales_por_moneda.values():
        total['utilidad_bruta'] = total['total_ingresos'] - total['total_costos']
        total['utilidad_neta'] = total['utilidad_bruta'] - total['total_gastos']

    unidad = _resolver_unidad_negocio(filtros)
    total_unidades = _contar_unidades_presentes(filtros)
    totales_lista = list(totales_por_moneda.values())
    moneda_unica = len(totales_lista) == 1
    principal = totales_lista[0] if moneda_unica else None

    return {
        'filtros': filtros,
        'unidad_negocio': unidad,
        'ingresos': secciones[TIPO_INGRESO],
        'costos': secciones[TIPO_COSTO],
        'gastos': secciones[TIPO_GASTO],
        'totales_por_moneda': totales_lista,
        'resumen': {
            'moneda_unica': moneda_unica,
            'moneda_principal': principal['moneda_codigo'] if principal else '',
            'moneda_principal_simbolo': principal['moneda_simbolo'] if principal else '',
            'total_ingresos': principal['total_ingresos'] if principal else None,
            'total_costos': principal['total_costos'] if principal else None,
            'total_gastos': principal['total_gastos'] if principal else None,
            'utilidad_bruta': principal['utilidad_bruta'] if principal else None,
            'utilidad_neta': principal['utilidad_neta'] if principal else None,
            'cantidad_monedas': len(totales_lista),
            'cantidad_ingresos': len(secciones[TIPO_INGRESO]),
            'cantidad_costos': len(secciones[TIPO_COSTO]),
            'cantidad_gastos': len(secciones[TIPO_GASTO]),
            'cantidad_unidades': total_unidades,
        },
    }


# ============================================================
# Serialización
# ============================================================

def _decimal_to_float(value):
    if value is None:
        return None
    return float(value or 0)


def _items_json(items):
    payload = []
    for row in items:
        payload.append({
            'tipo': row['tipo'],
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'naturaleza': row.get('naturaleza') or '',
            'moneda_codigo': row.get('moneda_codigo') or '',
            'moneda_simbolo': row.get('moneda_simbolo') or '',
            'debe_periodo': float(row['debe_periodo'] or 0),
            'haber_periodo': float(row['haber_periodo'] or 0),
            'monto': float(row['monto'] or 0),
        })
    return payload


def _totales_moneda_json(totales):
    payload = []
    for row in totales:
        payload.append({
            'moneda_codigo': row['moneda_codigo'],
            'moneda_simbolo': row['moneda_simbolo'],
            'total_ingresos': float(row['total_ingresos'] or 0),
            'total_costos': float(row['total_costos'] or 0),
            'total_gastos': float(row['total_gastos'] or 0),
            'utilidad_bruta': float(row['utilidad_bruta'] or 0),
            'utilidad_neta': float(row['utilidad_neta'] or 0),
        })
    return payload


def _resumen_json(resultado):
    filtros = resultado['filtros']
    resumen = resultado['resumen']
    unidad = resultado.get('unidad_negocio')
    return {
        'descripcion_periodo': filtros['descripcion_periodo'],
        'gestion': filtros['gestion'],
        'fecha_desde': filtros['fecha_desde'].isoformat(),
        'fecha_hasta': filtros['fecha_hasta'].isoformat(),
        'unidad_negocio_id': filtros.get('unidad_negocio_id'),
        'unidad_negocio_codigo': unidad['codigo'] if unidad else '',
        'unidad_negocio_nombre': unidad['nombre'] if unidad else '',
        'cantidad_unidades': resumen.get('cantidad_unidades', 0),
        'moneda_unica': resumen.get('moneda_unica', False),
        'moneda_principal': resumen.get('moneda_principal', ''),
        'moneda_principal_simbolo': resumen.get('moneda_principal_simbolo', ''),
        'cantidad_monedas': resumen.get('cantidad_monedas', 0),
        'total_ingresos': _decimal_to_float(resumen['total_ingresos']),
        'total_costos': _decimal_to_float(resumen['total_costos']),
        'total_gastos': _decimal_to_float(resumen['total_gastos']),
        'utilidad_bruta': _decimal_to_float(resumen['utilidad_bruta']),
        'utilidad_neta': _decimal_to_float(resumen['utilidad_neta']),
        'cantidad_ingresos': resumen['cantidad_ingresos'],
        'cantidad_costos': resumen['cantidad_costos'],
        'cantidad_gastos': resumen['cantidad_gastos'],
    }


# ============================================================
# PDF
# ============================================================

def _columnas_pdf():
    return [
        {'label': 'Sección', 'width': 24, 'align': 'left'},
        {'label': 'Moneda', 'width': 20, 'align': 'left'},
        {'label': 'Código', 'width': 24, 'align': 'left'},
        {'label': 'Cuenta', 'width': 78, 'align': 'left'},
        {'label': 'Monto', 'width': 28, 'align': 'right'},
    ]


def _totales_seccion_por_moneda(items):
    totales = OrderedDict()
    for item in items:
        codigo = item['moneda_codigo']
        if codigo not in totales:
            totales[codigo] = {
                'moneda_codigo': codigo,
                'moneda_simbolo': item.get('moneda_simbolo') or codigo,
                'total': Decimal('0'),
            }
        totales[codigo]['total'] += item['monto'] or Decimal('0')
    return list(totales.values())


def _rows_pdf(resultado):
    rows = []

    def agregar_bloque(nombre_seccion, items):
        rows.append([nombre_seccion, '', '', '', ''])
        for item in items:
            rows.append([
                '',
                item['moneda_codigo'],
                item['codigo'],
                item['nombre'],
                _fmt_monto_moneda(item['monto'], item.get('moneda_simbolo')),
            ])
        for total in _totales_seccion_por_moneda(items):
            rows.append([
                '',
                total['moneda_codigo'],
                '',
                f'TOTAL {nombre_seccion}',
                _fmt_monto_moneda(total['total'], total.get('moneda_simbolo')),
            ])

    agregar_bloque('INGRESOS', resultado['ingresos'])
    rows.append(['', '', '', '', ''])
    agregar_bloque('COSTOS', resultado['costos'])
    rows.append(['', '', '', '', ''])
    agregar_bloque('GASTOS', resultado['gastos'])
    rows.append(['', '', '', '', ''])

    rows.append(['RESULTADO', '', '', '', ''])
    for total in resultado['totales_por_moneda']:
        rows.append([
            '',
            total['moneda_codigo'],
            '',
            'UTILIDAD BRUTA',
            _fmt_monto_moneda(total['utilidad_bruta'], total.get('moneda_simbolo')),
        ])
        rows.append([
            '',
            total['moneda_codigo'],
            '',
            'UTILIDAD / PÉRDIDA NETA',
            _fmt_monto_moneda(total['utilidad_neta'], total.get('moneda_simbolo')),
        ])

    if not resultado['totales_por_moneda']:
        rows.append(['RESULTADO', '', '', 'Sin movimientos en el período', '0,00'])

    return rows


def _resultado_neto_pdf_texto(resultado):
    totales = resultado['totales_por_moneda']
    if not totales:
        return '0,00'
    if len(totales) == 1:
        total = totales[0]
        return _fmt_monto_moneda(total['utilidad_neta'], total.get('moneda_simbolo'))
    return 'Por moneda en detalle'


# ============================================================
# Vistas principales
# ============================================================

@estado_resultados_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    hoy = date.today()
    return render_template(
        'estado_resultados_index.html',
        fecha_hoy=hoy.isoformat(),
        gestion_actual=hoy.year,
        gestiones=_obtener_gestiones(),
        unidades_negocio=_obtener_unidades_negocio_activas(),
    )


@estado_resultados_bp.route('/datos')
@login_required
@roles_required(ROLES_LECTURA)
def datos():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_estado_resultados(filtros)

        return _json_ok(
            ingresos=_items_json(resultado['ingresos']),
            costos=_items_json(resultado['costos']),
            gastos=_items_json(resultado['gastos']),
            totales_por_moneda=_totales_moneda_json(resultado['totales_por_moneda']),
            resumen=_resumen_json(resultado),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo consultar el estado de resultados. {exc}', 500)


@estado_resultados_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_estado_resultados(filtros)
        unidad = resultado.get('unidad_negocio')
        subtitle = filtros['descripcion_periodo']
        if unidad:
            subtitle = f"{subtitle} · Unidad: {unidad['codigo']} - {unidad['nombre']}"

        pdf_bytes = build_table_report_pdf(
            title='Estado de Resultados',
            subtitle=subtitle,
            columns=_columnas_pdf(),
            rows=_rows_pdf(resultado),
            orientation='portrait',
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
                f'Gestión: {filtros["gestion"]}. '
                f'Período: {filtros["descripcion_periodo"]}. '
                f'Unidad: {(unidad["codigo"] + " - " + unidad["nombre"]) if unidad else "Todas las unidades"}. '
                f'Monedas: {resultado["resumen"].get("cantidad_monedas", 0)}. '
                f'Utilidad / Pérdida neta: {_resultado_neto_pdf_texto(resultado)}. '
                f'Fecha de emisión: {datetime.now().strftime("%d/%m/%Y %H:%M")}. '
            ),
        )

        nombre = (
            f'estado_resultados_'
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
        return _json_error(f'No se pudo generar el PDF del estado de resultados. {exc}', 500)


# ============================================================
# Ayuda
# ============================================================

@estado_resultados_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('estado_resultados_help.html')
