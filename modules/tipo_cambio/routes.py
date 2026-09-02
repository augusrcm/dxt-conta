# ============================================================
# DXT CONTA - Módulo Gestión de Tipo de Cambio
# ============================================================

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import psycopg2
from flask import render_template, request, jsonify, session

from . import tipo_cambio_bp
from database.db import get_db
from utils.decorators import login_required, roles_required


ROLES_EDICION = [9, 10]
ROLES_LECTURA = [9, 10, 11]


def _usuario_actual():
    """Obtiene el nombre del usuario logueado desde sesión."""
    return session.get('nombre') or session.get('correo') or session.get('ci_nit') or 'Sistema'


def _puede_editar():
    """Indica si el usuario actual puede editar."""
    return session.get('rol_id') in ROLES_EDICION


def _resumen_tipo_cambio_hoy():
    """Devuelve el estado operativo del tipo de cambio del día actual."""
    db = get_db()
    cursor = db.cursor()
    fecha_hoy = date.today()

    cursor.execute(
        """
        SELECT
            fecha,
            usd_paralelo,
            ufv,
            registrado_por,
            registrado_en,
            actualizado_por,
            actualizado_en
        FROM contabilidad.tipo_cambio
        WHERE fecha = %s
        """,
        (fecha_hoy,)
    )
    resultado = cursor.fetchone()
    cursor.close()

    if not resultado:
        return {
            'existe': False,
            'fecha': fecha_hoy.isoformat(),
            'puede_editar': _puede_editar(),
            'requiere_carga': True,
            'usd_paralelo': None,
            'ufv': None,
            'registrado_por': None,
            'registrado_en': None,
            'actualizado_por': None,
            'actualizado_en': None,
        }

    return {
        'existe': True,
        'fecha': resultado[0].isoformat(),
        'usd_paralelo': float(resultado[1]),
        'ufv': float(resultado[2]),
        'registrado_por': resultado[3],
        'registrado_en': resultado[4].isoformat() if resultado[4] else None,
        'actualizado_por': resultado[5],
        'actualizado_en': resultado[6].isoformat() if resultado[6] else None,
        'puede_editar': _puede_editar(),
        'requiere_carga': False,
    }


def _parse_fecha(valor, nombre_campo):
    """Convierte un string YYYY-MM-DD a date."""
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError(f'La fecha "{nombre_campo}" no es válida')


def _parse_decimal(valor, nombre_campo):
    """Convierte y valida un decimal positivo."""
    try:
        numero = Decimal(str(valor).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f'El campo "{nombre_campo}" no tiene un formato numérico válido')

    if numero <= 0:
        raise ValueError(f'El campo "{nombre_campo}" debe ser mayor a 0')

    return numero


@tipo_cambio_bp.route('/verificar-hoy', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def verificar_hoy():
    """Verifica si existe tipo de cambio para hoy."""
    try:
        return jsonify(_resumen_tipo_cambio_hoy())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@tipo_cambio_bp.route('/registrar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def registrar():
    """
    Registra o actualiza tipo de cambio para hoy.
    Se mantiene para compatibilidad con el dashboard/modal actual.
    """
    db = None

    try:
        data = request.get_json() or {}

        usd_paralelo = _parse_decimal(data.get('usd_paralelo'), 'USD Paralelo')
        ufv = _parse_decimal(data.get('ufv'), 'UFV')
        fecha_hoy = date.today()
        usuario = _usuario_actual()

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            SELECT fecha
            FROM contabilidad.tipo_cambio
            WHERE fecha = %s
        """, (fecha_hoy,))
        existe = cursor.fetchone()

        if existe:
            cursor.execute("""
                UPDATE contabilidad.tipo_cambio
                SET usd_paralelo = %s,
                    ufv = %s,
                    actualizado_por = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE fecha = %s
            """, (usd_paralelo, ufv, usuario, fecha_hoy))
            mensaje = 'Tipo de cambio actualizado correctamente'
        else:
            cursor.execute("""
                INSERT INTO contabilidad.tipo_cambio
                (fecha, usd_paralelo, ufv, registrado_por, registrado_en)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (fecha_hoy, usd_paralelo, ufv, usuario))
            mensaje = 'Tipo de cambio registrado correctamente'

        db.commit()
        cursor.close()

        return jsonify({
            'success': True,
            'mensaje': mensaje,
            'fecha': fecha_hoy.isoformat(),
            'usd_paralelo': float(usd_paralelo),
            'ufv': float(ufv)
        })

    except ValueError as e:
        if db:
            db.rollback()
        return jsonify({'error': str(e)}), 400

    except psycopg2.Error as e:
        if db:
            db.rollback()
        return jsonify({'error': f'Error de base de datos: {str(e)}'}), 500

    except Exception as e:
        if db:
            db.rollback()
        return jsonify({'error': str(e)}), 500


@tipo_cambio_bp.route('/gestion', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def gestion():
    """Pantalla principal de gestión de tipos de cambio."""
    hoy = date.today()
    primer_dia_mes = hoy.replace(day=1)

    if hoy.month == 12:
        primer_dia_mes_siguiente = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        primer_dia_mes_siguiente = hoy.replace(month=hoy.month + 1, day=1)

    ultimo_dia_mes = primer_dia_mes_siguiente - timedelta(days=1)

    return render_template(
        'tipo_cambio_gestion.html',
        fecha_desde=primer_dia_mes.strftime('%Y-%m-%d'),
        fecha_hasta=ultimo_dia_mes.strftime('%Y-%m-%d'),
        puede_editar=_puede_editar()
    )

@tipo_cambio_bp.route('/api/listado', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def api_listado():
    """
    Devuelve un listado diario por rango de fechas.
    Incluye días sin registro usando generate_series.
    """
    try:
        fecha_desde = _parse_fecha(request.args.get('desde'), 'Desde')
        fecha_hasta = _parse_fecha(request.args.get('hasta'), 'Hasta')

        if fecha_desde > fecha_hasta:
            return jsonify({'error': 'La fecha Desde no puede ser mayor que Hasta'}), 400

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            WITH dias AS (
                SELECT generate_series(%s::date, %s::date, interval '1 day')::date AS fecha
            )
            SELECT
                d.fecha,
                tc.usd_paralelo,
                tc.ufv,
                tc.registrado_por,
                tc.registrado_en,
                tc.actualizado_por,
                tc.actualizado_en
            FROM dias d
            LEFT JOIN contabilidad.tipo_cambio tc
                ON tc.fecha = d.fecha
            ORDER BY d.fecha DESC
        """, (fecha_desde, fecha_hasta))

        filas = cursor.fetchall()
        cursor.close()

        data = []
        for fila in filas:
            existe = fila[1] is not None and fila[2] is not None

            data.append({
                'fecha': fila[0].isoformat(),
                'fecha_display': fila[0].strftime('%d/%m/%Y'),
                'usd_paralelo': float(fila[1]) if fila[1] is not None else None,
                'ufv': float(fila[2]) if fila[2] is not None else None,
                'registrado_por': fila[3] if fila[3] else '-',
                'registrado_en': fila[4].isoformat() if fila[4] else None,
                'actualizado_por': fila[5] if fila[5] else None,
                'actualizado_en': fila[6].isoformat() if fila[6] else None,
                'existe': existe,
                'puede_editar': _puede_editar()
            })

        return jsonify({'data': data})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@tipo_cambio_bp.route('/api/guardar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def api_guardar():
    """
    Inserta o actualiza un tipo de cambio para una fecha específica.
    """
    db = None

    try:
        data = request.get_json() or {}

        fecha = _parse_fecha(data.get('fecha'), 'Fecha')
        usd_paralelo = _parse_decimal(data.get('usd_paralelo'), 'USD Paralelo')
        ufv = _parse_decimal(data.get('ufv'), 'UFV')
        usuario = _usuario_actual()

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            SELECT fecha
            FROM contabilidad.tipo_cambio
            WHERE fecha = %s
        """, (fecha,))
        existe = cursor.fetchone()

        if existe:
            cursor.execute("""
                UPDATE contabilidad.tipo_cambio
                SET usd_paralelo = %s,
                    ufv = %s,
                    actualizado_por = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE fecha = %s
            """, (usd_paralelo, ufv, usuario, fecha))
            accion = 'actualizado'
        else:
            cursor.execute("""
                INSERT INTO contabilidad.tipo_cambio
                (fecha, usd_paralelo, ufv, registrado_por, registrado_en)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (fecha, usd_paralelo, ufv, usuario))
            accion = 'registrado'

        db.commit()
        cursor.close()

        return jsonify({
            'success': True,
            'mensaje': f'Tipo de cambio {accion} correctamente para {fecha.strftime("%d/%m/%Y")}.'
        })

    except ValueError as e:
        if db:
            db.rollback()
        return jsonify({'error': str(e)}), 400

    except psycopg2.Error as e:
        if db:
            db.rollback()
        return jsonify({'error': f'Error de base de datos: {str(e)}'}), 500

    except Exception as e:
        if db:
            db.rollback()
        return jsonify({'error': str(e)}), 500


@tipo_cambio_bp.route('/obtener/<fecha>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def obtener_por_fecha(fecha):
    """Obtiene tipo de cambio de una fecha específica."""
    try:
        fecha_obj = _parse_fecha(fecha, 'Fecha')

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            SELECT
                fecha,
                usd_paralelo,
                ufv,
                registrado_por,
                registrado_en,
                actualizado_por,
                actualizado_en
            FROM contabilidad.tipo_cambio
            WHERE fecha = %s
        """, (fecha_obj,))

        resultado = cursor.fetchone()
        cursor.close()

        if resultado:
            return jsonify({
                'existe': True,
                'fecha': resultado[0].isoformat(),
                'usd_paralelo': float(resultado[1]),
                'ufv': float(resultado[2]),
                'registrado_por': resultado[3],
                'registrado_en': resultado[4].isoformat() if resultado[4] else None,
                'actualizado_por': resultado[5],
                'actualizado_en': resultado[6].isoformat() if resultado[6] else None
            })

        return jsonify({
            'existe': False,
            'mensaje': f'No existe tipo de cambio para {fecha}'
        }), 404

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# ------------------------------------------------------------
# AYUDA DEL MÓDULO
# ------------------------------------------------------------
@tipo_cambio_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('tipo_cambio_gestion_help.html')