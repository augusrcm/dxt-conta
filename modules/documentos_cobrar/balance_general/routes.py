# ============================================================
# DXT CONTA - Módulo Balance General
# ============================================================

from __future__ import annotations

import os
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal

from flask import Response, jsonify, render_template, request, session

from database.db_manager import DatabaseManager
from modules.balance_general import balance_general_bp
from utils.decorators import login_required, roles_required
from utils.reportes_pdf import build_table_report_pdf


ROLES_LECTURA = [9, 10, 11]
ESTADO_CONFIRMADO = 'CONFIRMADO'

TIPO_ACTIVO = 'ACTIVO'
TIPO_PASIVO = 'PASIVO'
TIPO_PATRIMONIO = 'PATRIMONIO'
TIPO_INGRESO = 'INGRESO'
TIPO_GASTO = 'GASTO'
TIPO_COSTO = 'COSTO'
TIPOS_RESULTADO = (TIPO_INGRESO, TIPO_GASTO, TIPO_COSTO)
TIPOS_BALANCE = (TIPO_ACTIVO, TIPO_PASIVO, TIPO_PATRIMONIO)


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


def _obtener_unidades_negocio_activas():
    sql = """
        SELECT id, codigo, nombre, COALESCE(nit, '') AS nit
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY codigo ASC, nombre ASC
    """
    with DatabaseManager() as db:
        return db.execute_query(sql)


def _obtener_unidad_negocio(unidad_negocio_id):
    if not unidad_negocio_id:
        return None

    sql = """
        SELECT id, codigo, nombre, COALESCE(nit, '') AS nit, activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
    """
    with DatabaseManager() as db:
        rows = db.execute_query(sql, (unidad_negocio_id,))
    return rows[0] if rows else None


def _validar_filtros(args):
    hoy = date.today()
    try:
        gestion = int(args.get('gestion') or hoy.year)
    except (TypeError, ValueError) as exc:
        raise ValueError('La gestión seleccionada no es válida.') from exc

    if gestion < 1900 or gestion > 2200:
        raise ValueError('La gestión seleccionada está fuera de rango.')

    fecha_corte = _parse_date(args.get('fecha_corte') or hoy.isoformat(), 'Fecha de corte')
    if fecha_corte.year != gestion:
        raise ValueError('La fecha de corte debe pertenecer a la gestión seleccionada.')

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'Unidad de Negocio')
    unidad_negocio = _obtener_unidad_negocio(unidad_negocio_id) if unidad_negocio_id else None
    if unidad_negocio_id and not unidad_negocio:
        raise ValueError('La Unidad de Negocio seleccionada no existe.')
    if unidad_negocio and not unidad_negocio.get('activo'):
        raise ValueError('La Unidad de Negocio seleccionada está inactiva.')

    return {
        'gestion': gestion,
        'fecha_corte': fecha_corte,
        'descripcion_periodo': f'Al {fecha_corte.strftime("%d/%m/%Y")}',
        'inicio_gestion': date(gestion, 1, 1),
        'unidad_negocio_id': unidad_negocio_id,
        'unidad_negocio': unidad_negocio,
    }


def _fmt_money(value):
    return f"{Decimal(value or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _fmt_monto_moneda(value, simbolo):
    simbolo = simbolo or ''
    return f'{simbolo} {_fmt_money(value)}'.strip()


def _moneda_key(codigo, simbolo):
    codigo = codigo or 'SIN_MONEDA'
    simbolo = simbolo or codigo
    return codigo, simbolo


def _monto_normalizado(tipo_cuenta, debe, haber):
    debe = debe or Decimal('0')
    haber = haber or Decimal('0')

    if tipo_cuenta == TIPO_ACTIVO:
        return debe - haber

    if tipo_cuenta in (TIPO_PASIVO, TIPO_PATRIMONIO):
        return haber - debe

    return Decimal('0')


def _monto_resultado(tipo_cuenta, debe, haber):
    debe = debe or Decimal('0')
    haber = haber or Decimal('0')

    if tipo_cuenta == TIPO_INGRESO:
        return haber - debe

    if tipo_cuenta in (TIPO_GASTO, TIPO_COSTO):
        return -(debe - haber)

    return Decimal('0')


# ============================================================
# Consultas contables
# ============================================================

def _consultar_saldos_balance(filtros):
    sql = """
        SELECT
            c.tipo::text AS tipo,
            c.codigo,
            c.nombre,
            c.naturaleza::text AS naturaleza,
            a.moneda_codigo,
            COALESCE(m.simbolo, a.moneda_codigo, '') AS moneda_simbolo,
            COALESCE(SUM(ad.debe), 0) AS debe_acumulado,
            COALESCE(SUM(ad.haber), 0) AS haber_acumulado
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
          AND c.tipo IN (%s, %s, %s)
    """
    params = [
        ESTADO_CONFIRMADO,
        filtros['fecha_corte'],
        TIPO_ACTIVO,
        TIPO_PASIVO,
        TIPO_PATRIMONIO,
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
        ORDER BY c.tipo, a.moneda_codigo, c.codigo
    """

    with DatabaseManager() as db:
        return db.execute_query(sql, tuple(params))


def _consultar_resultado_periodo(filtros):
    sql = """
        SELECT
            c.tipo::text AS tipo,
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
        filtros['inicio_gestion'],
        filtros['fecha_corte'],
        TIPO_INGRESO,
        TIPO_GASTO,
        TIPO_COSTO,
    ]

    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])

    sql += """
        GROUP BY
            c.tipo,
            a.moneda_codigo,
            m.simbolo
        HAVING COALESCE(SUM(ad.debe), 0) <> 0
            OR COALESCE(SUM(ad.haber), 0) <> 0
        ORDER BY a.moneda_codigo, c.tipo
    """

    with DatabaseManager() as db:
        return db.execute_query(sql, tuple(params))


def _contar_unidades_presentes(filtros):
    sql = """
        SELECT COUNT(DISTINCT a.unidad_negocio_id) AS total
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        WHERE a.estado = %s
          AND a.fecha <= %s
          AND a.unidad_negocio_id IS NOT NULL
          AND c.es_postable = TRUE
          AND c.tipo IN (%s, %s, %s, %s, %s, %s)
    """
    params = [
        ESTADO_CONFIRMADO,
        filtros['fecha_corte'],
        TIPO_ACTIVO,
        TIPO_PASIVO,
        TIPO_PATRIMONIO,
        TIPO_INGRESO,
        TIPO_GASTO,
        TIPO_COSTO,
    ]

    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])

    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))
    return int(rows[0]['total'] or 0) if rows else 0


# ============================================================
# Armado del balance
# ============================================================

def _nuevo_total_moneda(codigo, simbolo):
    return {
        'moneda_codigo': codigo,
        'moneda_simbolo': simbolo,
        'total_activo': Decimal('0'),
        'total_pasivo': Decimal('0'),
        'total_patrimonio_base': Decimal('0'),
        'resultado_periodo': Decimal('0'),
        'total_patrimonio': Decimal('0'),
        'total_pasivo_patrimonio': Decimal('0'),
        'diferencia': Decimal('0'),
        'cuadrado': True,
    }


def _asegurar_total_moneda(totales, codigo, simbolo):
    if codigo not in totales:
        totales[codigo] = _nuevo_total_moneda(codigo, simbolo)
    return totales[codigo]


def _armar_balance_general(filtros):
    rows_balance = _consultar_saldos_balance(filtros)
    rows_resultado = _consultar_resultado_periodo(filtros)

    secciones = {
        TIPO_ACTIVO: [],
        TIPO_PASIVO: [],
        TIPO_PATRIMONIO: [],
    }
    totales_por_moneda = OrderedDict()

    for row in rows_balance:
        tipo = row['tipo']
        codigo = row['codigo']
        nombre = row['nombre'] or ''
        naturaleza = row.get('naturaleza') or ''
        moneda_codigo, moneda_simbolo = _moneda_key(row.get('moneda_codigo'), row.get('moneda_simbolo'))
        debe = row['debe_acumulado'] or Decimal('0')
        haber = row['haber_acumulado'] or Decimal('0')
        monto = _monto_normalizado(tipo, debe, haber)

        if monto == 0:
            continue

        total_moneda = _asegurar_total_moneda(totales_por_moneda, moneda_codigo, moneda_simbolo)
        item = {
            'tipo': tipo,
            'codigo': codigo,
            'nombre': nombre,
            'naturaleza': naturaleza,
            'moneda_codigo': moneda_codigo,
            'moneda_simbolo': moneda_simbolo,
            'debe_acumulado': debe,
            'haber_acumulado': haber,
            'monto': monto,
        }
        secciones[tipo].append(item)

        if tipo == TIPO_ACTIVO:
            total_moneda['total_activo'] += monto
        elif tipo == TIPO_PASIVO:
            total_moneda['total_pasivo'] += monto
        elif tipo == TIPO_PATRIMONIO:
            total_moneda['total_patrimonio_base'] += monto

    for row in rows_resultado:
        moneda_codigo, moneda_simbolo = _moneda_key(row.get('moneda_codigo'), row.get('moneda_simbolo'))
        total_moneda = _asegurar_total_moneda(totales_por_moneda, moneda_codigo, moneda_simbolo)
        total_moneda['resultado_periodo'] += _monto_resultado(
            row['tipo'],
            row['debe_periodo'] or Decimal('0'),
            row['haber_periodo'] or Decimal('0'),
        )

    patrimonio_items = list(secciones[TIPO_PATRIMONIO])
    for total in totales_por_moneda.values():
        resultado_periodo = total['resultado_periodo']
        if resultado_periodo != 0:
            patrimonio_items.append({
                'tipo': TIPO_PATRIMONIO,
                'codigo': '',
                'nombre': 'RESULTADO DEL PERÍODO',
                'naturaleza': 'ACREEDORA' if resultado_periodo >= 0 else 'DEUDORA',
                'moneda_codigo': total['moneda_codigo'],
                'moneda_simbolo': total['moneda_simbolo'],
                'debe_acumulado': Decimal('0'),
                'haber_acumulado': Decimal('0'),
                'monto': resultado_periodo,
                'es_resultado_periodo': True,
            })

        total['total_patrimonio'] = total['total_patrimonio_base'] + resultado_periodo
        total['total_pasivo_patrimonio'] = total['total_pasivo'] + total['total_patrimonio']
        total['diferencia'] = total['total_activo'] - total['total_pasivo_patrimonio']
        total['cuadrado'] = total['diferencia'] == 0

    totales_lista = list(totales_por_moneda.values())
    moneda_unica = len(totales_lista) == 1
    principal = totales_lista[0] if moneda_unica else None
    unidad = filtros.get('unidad_negocio')
    total_unidades = _contar_unidades_presentes(filtros)

    return {
        'filtros': filtros,
        'activo': secciones[TIPO_ACTIVO],
        'pasivo': secciones[TIPO_PASIVO],
        'patrimonio': patrimonio_items,
        'totales_por_moneda': totales_lista,
        'resumen': {
            'moneda_unica': moneda_unica,
            'moneda_principal': principal['moneda_codigo'] if principal else '',
            'moneda_principal_simbolo': principal['moneda_simbolo'] if principal else '',
            'total_activo': principal['total_activo'] if principal else None,
            'total_pasivo': principal['total_pasivo'] if principal else None,
            'total_patrimonio': principal['total_patrimonio'] if principal else None,
            'resultado_periodo': principal['resultado_periodo'] if principal else None,
            'total_pasivo_patrimonio': principal['total_pasivo_patrimonio'] if principal else None,
            'diferencia': principal['diferencia'] if principal else None,
            'cuadrado': all(total['cuadrado'] for total in totales_lista) if totales_lista else True,
            'cantidad_monedas': len(totales_lista),
            'cantidad_activo': len(secciones[TIPO_ACTIVO]),
            'cantidad_pasivo': len(secciones[TIPO_PASIVO]),
            'cantidad_patrimonio': len(patrimonio_items),
            'unidad_negocio_id': unidad['id'] if unidad else None,
            'unidad_negocio_codigo': unidad['codigo'] if unidad else '',
            'unidad_negocio_nombre': unidad['nombre'] if unidad else 'Todas las unidades',
            'unidad_negocio_nit': unidad['nit'] if unidad else '',
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
            'codigo': row.get('codigo') or '',
            'nombre': row['nombre'],
            'naturaleza': row.get('naturaleza') or '',
            'moneda_codigo': row.get('moneda_codigo') or '',
            'moneda_simbolo': row.get('moneda_simbolo') or '',
            'debe_acumulado': float(row.get('debe_acumulado') or 0),
            'haber_acumulado': float(row.get('haber_acumulado') or 0),
            'monto': float(row['monto'] or 0),
            'es_resultado_periodo': bool(row.get('es_resultado_periodo')),
        })
    return payload


def _totales_moneda_json(totales):
    payload = []
    for row in totales:
        payload.append({
            'moneda_codigo': row['moneda_codigo'],
            'moneda_simbolo': row['moneda_simbolo'],
            'total_activo': float(row['total_activo'] or 0),
            'total_pasivo': float(row['total_pasivo'] or 0),
            'total_patrimonio': float(row['total_patrimonio'] or 0),
            'resultado_periodo': float(row['resultado_periodo'] or 0),
            'total_pasivo_patrimonio': float(row['total_pasivo_patrimonio'] or 0),
            'diferencia': float(row['diferencia'] or 0),
            'cuadrado': bool(row['cuadrado']),
        })
    return payload


def _resumen_json(resultado):
    resumen = resultado['resumen']
    filtros = resultado['filtros']
    return {
        'descripcion_periodo': filtros['descripcion_periodo'],
        'gestion': filtros['gestion'],
        'fecha_corte': filtros['fecha_corte'].isoformat(),
        'moneda_unica': resumen.get('moneda_unica', False),
        'moneda_principal': resumen.get('moneda_principal', ''),
        'moneda_principal_simbolo': resumen.get('moneda_principal_simbolo', ''),
        'cantidad_monedas': resumen.get('cantidad_monedas', 0),
        'total_activo': _decimal_to_float(resumen['total_activo']),
        'total_pasivo': _decimal_to_float(resumen['total_pasivo']),
        'total_patrimonio': _decimal_to_float(resumen['total_patrimonio']),
        'resultado_periodo': _decimal_to_float(resumen['resultado_periodo']),
        'total_pasivo_patrimonio': _decimal_to_float(resumen['total_pasivo_patrimonio']),
        'diferencia': _decimal_to_float(resumen['diferencia']),
        'cuadrado': resumen['cuadrado'],
        'cantidad_activo': resumen['cantidad_activo'],
        'cantidad_pasivo': resumen['cantidad_pasivo'],
        'cantidad_patrimonio': resumen['cantidad_patrimonio'],
        'unidad_negocio_id': resumen.get('unidad_negocio_id'),
        'unidad_negocio_codigo': resumen.get('unidad_negocio_codigo') or '',
        'unidad_negocio_nombre': resumen.get('unidad_negocio_nombre') or 'Todas las unidades',
        'unidad_negocio_nit': resumen.get('unidad_negocio_nit') or '',
        'cantidad_unidades': resumen.get('cantidad_unidades', 0),
    }


# ============================================================
# PDF
# ============================================================

def _columnas_pdf():
    return [
        {'label': 'Sección', 'width': 24, 'align': 'left'},
        {'label': 'Moneda', 'width': 18, 'align': 'left'},
        {'label': 'Código', 'width': 23, 'align': 'left'},
        {'label': 'Cuenta', 'width': 82, 'align': 'left'},
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
                item.get('moneda_codigo') or '',
                item.get('codigo') or '',
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

    agregar_bloque('ACTIVO', resultado['activo'])
    rows.append(['', '', '', '', ''])
    agregar_bloque('PASIVO', resultado['pasivo'])
    rows.append(['', '', '', '', ''])
    agregar_bloque('PATRIMONIO', resultado['patrimonio'])
    rows.append(['', '', '', '', ''])

    rows.append(['CUADRE', '', '', '', ''])
    for total in resultado['totales_por_moneda']:
        estado = 'CUADRADO' if total['cuadrado'] else 'DIFERENCIA'
        rows.append([
            '',
            total['moneda_codigo'],
            '',
            'TOTAL ACTIVO',
            _fmt_monto_moneda(total['total_activo'], total.get('moneda_simbolo')),
        ])
        rows.append([
            '',
            total['moneda_codigo'],
            '',
            'TOTAL PASIVO + PATRIMONIO',
            _fmt_monto_moneda(total['total_pasivo_patrimonio'], total.get('moneda_simbolo')),
        ])
        rows.append([
            '',
            total['moneda_codigo'],
            '',
            f'{estado} / DIFERENCIA',
            _fmt_monto_moneda(total['diferencia'], total.get('moneda_simbolo')),
        ])

    if not resultado['totales_por_moneda']:
        rows.append(['CUADRE', '', '', 'Sin movimientos al corte', '0,00'])

    return rows


def _resultado_periodo_pdf_texto(resultado):
    totales = resultado['totales_por_moneda']
    if not totales:
        return '0,00'
    if len(totales) == 1:
        total = totales[0]
        return _fmt_monto_moneda(total['resultado_periodo'], total.get('moneda_simbolo'))
    return 'Por moneda en detalle'


# ============================================================
# Vistas principales
# ============================================================

@balance_general_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    hoy = date.today()
    return render_template(
        'balance_general_index.html',
        fecha_hoy=hoy.isoformat(),
        gestion_actual=hoy.year,
        gestiones=_obtener_gestiones(),
        unidades_negocio=_obtener_unidades_negocio_activas(),
    )


@balance_general_bp.route('/datos')
@login_required
@roles_required(ROLES_LECTURA)
def datos():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_balance_general(filtros)

        return _json_ok(
            activo=_items_json(resultado['activo']),
            pasivo=_items_json(resultado['pasivo']),
            patrimonio=_items_json(resultado['patrimonio']),
            totales_por_moneda=_totales_moneda_json(resultado['totales_por_moneda']),
            resumen=_resumen_json(resultado),
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo consultar el balance general. {exc}', 500)


@balance_general_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _validar_filtros(request.args)
        resultado = _armar_balance_general(filtros)
        estado = 'CUADRADO' if resultado['resumen']['cuadrado'] else 'DESCUADRADO'

        unidad_label = resultado['resumen'].get('unidad_negocio_nombre') or 'Todas las unidades'
        subtitle = filtros['descripcion_periodo']
        if filtros.get('unidad_negocio_id'):
            unidad_codigo = resultado['resumen'].get('unidad_negocio_codigo') or ''
            subtitle = f'{subtitle} · Unidad: {unidad_codigo} - {unidad_label}'.strip()

        pdf_bytes = build_table_report_pdf(
            title='Balance General',
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
                f'Fecha de corte: {filtros["fecha_corte"].strftime("%d/%m/%Y")}. '
                f'Unidad: {unidad_label}. '
                f'Monedas: {resultado["resumen"].get("cantidad_monedas", 0)}. '
                f'Estado: {estado}. '
                f'Resultado del período: {_resultado_periodo_pdf_texto(resultado)}. '
                f'Fecha de emisión: {datetime.now().strftime("%d/%m/%Y %H:%M")}.'
            ),
        )

        nombre = f'balance_general_{filtros["fecha_corte"].strftime("%Y%m%d")}.pdf'
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(f'No se pudo generar el PDF del balance general. {exc}', 500)


# ============================================================
# Ayuda
# ============================================================

@balance_general_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('balance_general_help.html')
