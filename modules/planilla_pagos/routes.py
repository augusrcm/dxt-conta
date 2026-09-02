# ============================================================
# DXT CONTA - Pago de Planillas
# Pago individual/global de sueldos y honorarios, reversión y PDFs.
# ============================================================

from __future__ import annotations

import io
from html import escape
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from flask import Response, current_app, jsonify, render_template, request, session, url_for
from psycopg2 import errors as pg_errors
from psycopg2.extras import Json
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle, Image

from database.db_manager import DatabaseManager
from modules.planilla_pagos import planilla_pagos_bp
from config import Config
from utils.decorators import login_required, roles_required
from utils.planillas_security import assert_gestion_abierta, mensaje_error_operacion


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
CUANTIA = Decimal('0.01')
MESES = [
    (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
    (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
    (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
]
TIPOS_PLANILLA = {'PLANTA': 'Sueldos - Planta', 'COLABORADORES': 'Honorarios - Colaboradores'}
MEDIOS_ENTREGA_INDIVIDUAL = {'EFECTIVO', 'TRANSFERENCIA', 'QR', 'CHEQUE'}

ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
GREEN = colors.HexColor('#107c41')
RED = colors.HexColor('#b42318')
LETTER_WIDTH, LETTER_HEIGHT = letter
HALF_LETTER_HEIGHT = LETTER_HEIGHT / 2
BOLETA_SIDE_MARGIN = 7 * mm
BOLETA_VERTICAL_MARGIN = 6 * mm
BOLETA_BORDER_PADDING = 4


# ============================================================
# Helpers base
# ============================================================

def _clean(value: Any) -> str:
    return str(value or '').strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def _usuario_actual() -> str:
    return str(
        session.get('username')
        or session.get('usuario')
        or session.get('email')
        or session.get('user_id')
        or 'sistema'
    )


def _puede_editar() -> bool:
    try:
        return int(session.get('rol_id', 0)) in ROLES_EDICION
    except (TypeError, ValueError):
        return False


def _json_ready(value: Any):
    if isinstance(value, Decimal):
        return str(value.quantize(CUANTIA, rounding=ROUND_HALF_UP))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    return value


def _json_ok(message: str | None = None, **kwargs):
    payload = {'success': True}
    if message:
        payload['message'] = message
    payload.update(kwargs)
    return jsonify(_json_ready(payload))


def _json_error(message: str, status: int = 400, **kwargs):
    payload = {'success': False, 'message': message}
    payload.update(kwargs)
    return jsonify(_json_ready(payload)), status


def _decimal(value: Any, field_name: str, allow_zero: bool = True, required: bool = True) -> Decimal:
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return Decimal('0.00')
    try:
        number = Decimal(str(value).replace(',', '.').strip())
    except (InvalidOperation, AttributeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" no tiene un formato válido.') from exc
    if allow_zero:
        if number < 0:
            raise ValueError(f'El campo "{field_name}" no puede ser negativo.')
    elif number <= 0:
        raise ValueError(f'El campo "{field_name}" debe ser mayor a cero.')
    return number.quantize(CUANTIA, rounding=ROUND_HALF_UP)


def _parse_date(value: Any, field_name: str, required: bool = True) -> date | None:
    text = _clean(value)
    if not text:
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'El campo "{field_name}" no tiene una fecha válida.') from exc


def _int_or_none(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _limit_text(value: Any, field_name: str, max_len: int, required: bool = False) -> str | None:
    text = _clean(value)
    if required and not text:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(text) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return text or None


def _mes_nombre(mes: int) -> str:
    return dict(MESES).get(int(mes), str(mes))


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP)


def moneyfmt(value: Any) -> str:
    return f'{money(value):,.2f}'


_LITERAL_0_29 = {
    0: 'cero',
    1: 'uno',
    2: 'dos',
    3: 'tres',
    4: 'cuatro',
    5: 'cinco',
    6: 'seis',
    7: 'siete',
    8: 'ocho',
    9: 'nueve',
    10: 'diez',
    11: 'once',
    12: 'doce',
    13: 'trece',
    14: 'catorce',
    15: 'quince',
    16: 'dieciseis',
    17: 'diecisiete',
    18: 'dieciocho',
    19: 'diecinueve',
    20: 'veinte',
    21: 'veintiuno',
    22: 'veintidos',
    23: 'veintitres',
    24: 'veinticuatro',
    25: 'veinticinco',
    26: 'veintiseis',
    27: 'veintisiete',
    28: 'veintiocho',
    29: 'veintinueve',
}
_LITERAL_DECENAS = {
    30: 'treinta',
    40: 'cuarenta',
    50: 'cincuenta',
    60: 'sesenta',
    70: 'setenta',
    80: 'ochenta',
    90: 'noventa',
}
_LITERAL_CENTENAS = {
    100: 'cien',
    200: 'doscientos',
    300: 'trescientos',
    400: 'cuatrocientos',
    500: 'quinientos',
    600: 'seiscientos',
    700: 'setecientos',
    800: 'ochocientos',
    900: 'novecientos',
}


def _apocopar_uno_literal(texto: str) -> str:
    if texto == 'uno':
        return 'un'
    if texto.endswith('veintiuno'):
        return texto[:-9] + 'veintiun'
    if texto.endswith(' y uno'):
        return texto[:-6] + ' y un'
    if texto.endswith(' uno'):
        return texto[:-4] + ' un'
    return texto


def _entero_literal_es(numero: int, apocopar_uno: bool = False) -> str:
    numero = int(numero)
    if numero < 0:
        texto = 'menos ' + _entero_literal_es(abs(numero), apocopar_uno=False)
        return _apocopar_uno_literal(texto) if apocopar_uno else texto
    if numero < 30:
        texto = _LITERAL_0_29[numero]
    elif numero < 100:
        decena = (numero // 10) * 10
        unidad = numero % 10
        texto = _LITERAL_DECENAS[decena]
        if unidad:
            texto += ' y ' + _entero_literal_es(unidad)
    elif numero < 1000:
        if numero in _LITERAL_CENTENAS:
            texto = _LITERAL_CENTENAS[numero]
        else:
            centena = (numero // 100) * 100
            resto = numero % 100
            texto = ('ciento' if centena == 100 else _LITERAL_CENTENAS[centena]) + ' ' + _entero_literal_es(resto)
    elif numero < 1000000:
        miles, resto = divmod(numero, 1000)
        texto = 'mil' if miles == 1 else _entero_literal_es(miles, apocopar_uno=True) + ' mil'
        if resto:
            texto += ' ' + _entero_literal_es(resto)
    elif numero < 1000000000000:
        millones, resto = divmod(numero, 1000000)
        texto = 'un millon' if millones == 1 else _entero_literal_es(millones, apocopar_uno=True) + ' millones'
        if resto:
            texto += ' ' + _entero_literal_es(resto)
    else:
        texto = str(numero)
    return _apocopar_uno_literal(texto) if apocopar_uno else texto


def monto_literal_bolivianos(value: Any) -> str:
    importe = money(value)
    signo = 'menos ' if importe < 0 else ''
    total_centavos = int((abs(importe) * 100).to_integral_value(rounding=ROUND_HALF_UP))
    enteros, centavos = divmod(total_centavos, 100)
    literal = _entero_literal_es(enteros, apocopar_uno=True)
    return f'{signo}{literal} {centavos:02d}/100 bolivianos'


# ============================================================
# Datos base
# ============================================================

def _parametros_gestion(db: DatabaseManager, gestion: int) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT *
        FROM contabilidad.planilla_parametro
        WHERE gestion = %s AND activo IS TRUE
        LIMIT 1
        """,
        (gestion,)
    )
    if not rows:
        raise ValueError(f'No existe Parámetros de Planilla activo para la gestión {gestion}.')
    return dict(rows[0])


def _cuenta_pasivo_planilla(parametros: dict[str, Any], tipo_planilla: str) -> str:
    if tipo_planilla == 'PLANTA':
        cuenta = parametros.get('cuenta_sueldos_por_pagar_codigo')
        nombre = 'Sueldos por pagar'
    else:
        cuenta = parametros.get('cuenta_honorarios_por_pagar_codigo')
        nombre = 'Honorarios por pagar'
    if not cuenta:
        raise ValueError(f'No está configurada la cuenta {nombre} en Parámetros de Planilla.')
    return cuenta


def _obtener_planilla(db: DatabaseManager, planilla_id: int) -> dict[str, Any] | None:
    rows = db.execute_query(
        """
        WITH pagos AS (
            SELECT ppa.planilla_periodo_id,
                   COALESCE(SUM(CASE WHEN ppa.estado = 'VIGENTE' AND p.estado = 'CONFIRMADO' THEN ppa.monto_aplicado ELSE 0 END),0) AS total_pagado
            FROM contabilidad.planilla_pago_aplicacion ppa
            JOIN contabilidad.pago p ON p.id = ppa.pago_id
            WHERE ppa.planilla_periodo_id = %s
            GROUP BY ppa.planilla_periodo_id
        )
        SELECT pp.*,
               COALESCE(pagos.total_pagado,0) AS total_pagado_real,
               GREATEST(pp.total_liquido - COALESCE(pagos.total_pagado,0),0) AS saldo_pendiente_real,
               CASE
                 WHEN COALESCE(pagos.total_pagado,0) <= 0 THEN pp.estado
                 WHEN COALESCE(pagos.total_pagado,0) < pp.total_liquido THEN 'PAGADA_PARCIAL'
                 ELSE 'PAGADA'
               END AS estado_visual
        FROM contabilidad.planilla_periodo pp
        LEFT JOIN pagos ON pagos.planilla_periodo_id = pp.id
        WHERE pp.id = %s
          AND pp.tipo_planilla IN ('PLANTA','COLABORADORES')
        """,
        (planilla_id, planilla_id)
    )
    return dict(rows[0]) if rows else None


def _planillas_listado(db: DatabaseManager, filtros: dict[str, Any]) -> list[dict[str, Any]]:
    where = ["pp.tipo_planilla IN ('PLANTA','COLABORADORES')", "pp.estado IN ('CONSOLIDADA','PAGADA')"]
    params: list[Any] = []
    if filtros.get('tipo'):
        where.append('pp.tipo_planilla = %s')
        params.append(filtros['tipo'])
    if filtros.get('gestion'):
        where.append('pp.gestion = %s')
        params.append(int(filtros['gestion']))
    if filtros.get('mes'):
        where.append('pp.mes = %s')
        params.append(int(filtros['mes']))
    if filtros.get('buscar'):
        like = f"%{filtros['buscar']}%"
        where.append('(pp.codigo ILIKE %s OR pp.glosa ILIKE %s)')
        params.extend([like, like])
    query = f"""
        WITH pagos AS (
            SELECT ppa.planilla_periodo_id,
                   COALESCE(SUM(CASE WHEN ppa.estado = 'VIGENTE' AND p.estado = 'CONFIRMADO' THEN ppa.monto_aplicado ELSE 0 END),0) AS total_pagado
            FROM contabilidad.planilla_pago_aplicacion ppa
            JOIN contabilidad.pago p ON p.id = ppa.pago_id
            GROUP BY ppa.planilla_periodo_id
        ), unidades AS (
            SELECT planilla_periodo_id, COUNT(DISTINCT unidad_negocio_id) AS unidades
            FROM contabilidad.planilla_detalle
            WHERE estado <> 'EXCLUIDO'
            GROUP BY planilla_periodo_id
        )
        SELECT pp.id, pp.codigo, pp.tipo_planilla, pp.gestion, pp.mes, pp.fecha_planilla,
               pp.estado, pp.moneda_codigo, pp.total_liquido,
               COALESCE(pagos.total_pagado,0) AS total_pagado,
               GREATEST(pp.total_liquido - COALESCE(pagos.total_pagado,0),0) AS saldo_pendiente,
               COALESCE(unidades.unidades,0) AS unidades,
               CASE
                 WHEN COALESCE(pagos.total_pagado,0) <= 0 THEN pp.estado
                 WHEN COALESCE(pagos.total_pagado,0) < pp.total_liquido THEN 'PAGADA_PARCIAL'
                 ELSE 'PAGADA'
               END AS estado_visual
        FROM contabilidad.planilla_periodo pp
        LEFT JOIN pagos ON pagos.planilla_periodo_id = pp.id
        LEFT JOIN unidades ON unidades.planilla_periodo_id = pp.id
        WHERE {' AND '.join(where)}
        ORDER BY pp.gestion DESC, pp.mes DESC, pp.id DESC
    """
    return [dict(r) for r in db.execute_query(query, tuple(params))]


def _detalles_planilla(db: DatabaseManager, planilla_id: int, unidad_id: int | None = None, solo_pendientes: bool = False) -> list[dict[str, Any]]:
    params: list[Any] = [planilla_id]
    where = ["pd.planilla_periodo_id = %s", "pd.estado <> 'EXCLUIDO'"]
    if unidad_id:
        where.append('pd.unidad_negocio_id = %s')
        params.append(unidad_id)
    rows = db.execute_query(
        f"""
        WITH pagos AS (
            SELECT ppa.planilla_detalle_id,
                   COALESCE(SUM(CASE WHEN ppa.estado = 'VIGENTE' AND p.estado = 'CONFIRMADO' THEN ppa.monto_aplicado ELSE 0 END),0) AS pagado
            FROM contabilidad.planilla_pago_aplicacion ppa
            JOIN contabilidad.pago p ON p.id = ppa.pago_id
            WHERE ppa.planilla_periodo_id = %s
            GROUP BY ppa.planilla_detalle_id
        )
        SELECT pd.*, un.nit AS unidad_nit, un.logo_ruta AS unidad_logo_ruta, un.logo_nombre_original AS unidad_logo_nombre,
               COALESCE(pagos.pagado,0) AS pagado_real,
               GREATEST(pd.liquido_pagable - COALESCE(pagos.pagado,0),0) AS saldo_real,
               CASE
                 WHEN COALESCE(pagos.pagado,0) <= 0 THEN 'PENDIENTE'
                 WHEN COALESCE(pagos.pagado,0) < pd.liquido_pagable THEN 'PARCIAL'
                 ELSE 'PAGADO'
               END AS estado_pago_real
        FROM contabilidad.planilla_detalle pd
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = pd.unidad_negocio_id
        LEFT JOIN pagos ON pagos.planilla_detalle_id = pd.id
        WHERE {' AND '.join(where)}
        ORDER BY pd.unidad_negocio_codigo NULLS LAST, pd.secuencia, pd.nombre_completo
        """,
        tuple([planilla_id] + params)
    )
    result = []
    for r in rows:
        item = dict(r)
        if solo_pendientes and money(item['saldo_real']) <= 0:
            continue
        result.append(item)
    return result


def _unidades_planilla(db: DatabaseManager, planilla_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute_query(
        """
        SELECT unidad_negocio_id AS id,
               COALESCE(unidad_negocio_codigo,'S/U') AS codigo,
               COALESCE(unidad_negocio_nombre,'Sin unidad') AS nombre,
               COUNT(*) AS personas,
               COALESCE(SUM(liquido_pagable),0) AS liquido
        FROM contabilidad.planilla_detalle
        WHERE planilla_periodo_id = %s AND estado <> 'EXCLUIDO'
        GROUP BY unidad_negocio_id, unidad_negocio_codigo, unidad_negocio_nombre
        ORDER BY unidad_negocio_codigo
        """,
        (planilla_id,)
    )]


def _cajas(db: DatabaseManager):
    return db.execute_query(
        """
        SELECT id, codigo, nombre, cuenta_contable_codigo
        FROM contabilidad.caja
        WHERE activo IS TRUE
        ORDER BY codigo
        """
    )


def _bancos(db: DatabaseManager):
    return db.execute_query(
        """
        SELECT id,
               nombre_banco,
               nombre_banco AS banco,
               numero_cuenta,
               moneda_codigo,
               titular,
               cuenta_contable_codigo
        FROM contabilidad.cuenta_bancaria
        WHERE activo IS TRUE
        ORDER BY nombre_banco, numero_cuenta
        """
    )


def _cuenta_salida(db: DatabaseManager, medio: str, caja_id: int | None, cuenta_bancaria_id: int | None) -> dict[str, Any]:
    if medio == 'CAJA':
        rows = db.execute_query(
            """
            SELECT id, nombre, cuenta_contable_codigo, NULL::bigint AS auxiliar_id
            FROM contabilidad.caja
            WHERE id = %s AND activo IS TRUE
            """,
            (caja_id,)
        )
    elif medio == 'BANCO':
        rows = db.execute_query(
            """
            SELECT id,
                   nombre_banco || ' · ' || numero_cuenta AS nombre,
                   cuenta_contable_codigo,
                   auxiliar_id
            FROM contabilidad.cuenta_bancaria
            WHERE id = %s AND activo IS TRUE
            """,
            (cuenta_bancaria_id,)
        )
    else:
        raise ValueError('El medio de pago debe ser CAJA o BANCO.')
    if not rows:
        raise ValueError('No se pudo obtener la cuenta contable de caja/banco.')
    row = dict(rows[0])
    if not row.get('cuenta_contable_codigo'):
        raise ValueError('La caja/banco seleccionado no tiene cuenta contable configurada.')
    if medio == 'BANCO' and not row.get('auxiliar_id'):
        raise ValueError('La cuenta bancaria seleccionada no tiene auxiliar configurado.')
    return row


# ============================================================
# Rutas vista
# ============================================================

@planilla_pagos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    filtros = {
        'tipo': _upper(request.args.get('tipo')) if request.args.get('tipo') else '',
        'gestion': _clean(request.args.get('gestion')),
        'mes': _clean(request.args.get('mes')),
        'buscar': _clean(request.args.get('buscar')),
    }
    try:
        with DatabaseManager() as db:
            planillas = _planillas_listado(db, filtros)
        stats = {
            'planillas': len(planillas),
            'pendiente': sum((money(p['saldo_pendiente']) for p in planillas), Decimal('0.00')),
            'pagado': sum((money(p['total_pagado']) for p in planillas), Decimal('0.00')),
        }
    except Exception as exc:
        planillas = []
        stats = {'planillas': 0, 'pendiente': Decimal('0.00'), 'pagado': Decimal('0.00')}
        session['last_error'] = 'No se pudo cargar Pago de Planillas. Revise la configuración operativa del módulo.'
    return render_template(
        'planilla_pagos_index.html',
        planillas=planillas,
        filtros=filtros,
        stats=stats,
        meses=MESES,
        tipos=TIPOS_PLANILLA,
        moneyfmt=moneyfmt,
        puede_editar=_puede_editar(),
    )


@planilla_pagos_bp.route('/<int:planilla_id>')
@login_required
@roles_required(ROLES_LECTURA)
def detalle(planilla_id: int):
    with DatabaseManager() as db:
        planilla = _obtener_planilla(db, planilla_id)
        if not planilla:
            return render_template('404.html'), 404
        detalles = _detalles_planilla(db, planilla_id)
        unidades = _unidades_planilla(db, planilla_id)
        cajas = _cajas(db)
        bancos = _bancos(db)
        pagos = _pagos_planilla(db, planilla_id)
    grupos = OrderedDict()
    for d in detalles:
        key = d.get('unidad_negocio_codigo') or 'S/U'
        grupos.setdefault(key, {'nombre': d.get('unidad_negocio_nombre') or 'Sin unidad', 'items': []})
        grupos[key]['items'].append(d)
    return render_template(
        'planilla_pagos_detalle.html',
        planilla=planilla,
        detalles=detalles,
        grupos=grupos,
        unidades=unidades,
        cajas=cajas,
        bancos=bancos,
        pagos=pagos,
        meses=MESES,
        tipos=TIPOS_PLANILLA,
        moneyfmt=moneyfmt,
        puede_editar=_puede_editar(),
    )


@planilla_pagos_bp.route('/ayuda')
@login_required
@roles_required(ROLES_LECTURA)
def ayuda():
    return render_template('planilla_pagos_help.html')


# ============================================================
# APIs de pago / reversión
# ============================================================

@planilla_pagos_bp.route('/api/<int:planilla_id>/pagar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def pagar(planilla_id: int):
    data = request.get_json(silent=True) or {}
    try:
        fecha_pago = _parse_date(data.get('fecha'), 'Fecha de pago')
        medio = _upper(data.get('medio_pago'))
        caja_id = _int_or_none(data.get('caja_id'))
        cuenta_bancaria_id = _int_or_none(data.get('cuenta_bancaria_id'))
        unidad_id = _int_or_none(data.get('unidad_id'))
        if medio == 'CAJA':
            cuenta_bancaria_id = None
        elif medio == 'BANCO':
            caja_id = None
        detalle_ids = data.get('detalle_ids') or []
        if isinstance(detalle_ids, str):
            detalle_ids = [x for x in detalle_ids.split(',') if x]
        detalle_ids = [int(x) for x in detalle_ids if str(x).isdigit()]
        scope = _upper(data.get('scope') or 'SELECCION')
        referencia = _limit_text(data.get('referencia'), 'Referencia', 150, required=False)
        glosa = _limit_text(data.get('glosa'), 'Glosa', 500, required=True)

        datos_destino = None
        if scope == 'INDIVIDUAL':
            if len(detalle_ids) != 1:
                raise ValueError('El pago individual requiere exactamente un beneficiario.')
            medio_entrega = _upper(data.get('medio_entrega') or 'EFECTIVO')
            if medio_entrega not in MEDIOS_ENTREGA_INDIVIDUAL:
                raise ValueError('El medio de entrega al beneficiario no es válido.')
            banco_destino = _limit_text(data.get('banco_destino'), 'Banco destino', 120, required=medio_entrega in ('TRANSFERENCIA', 'QR'))
            cuenta_destino = _limit_text(data.get('cuenta_destino'), 'Cuenta destino', 120, required=medio_entrega in ('TRANSFERENCIA', 'QR'))
            numero_cheque = _limit_text(data.get('numero_cheque'), 'Número de cheque', 80, required=medio_entrega == 'CHEQUE')
            referencia_destino = _limit_text(data.get('referencia_destino'), 'Referencia destino', 180, required=False)
            datos_destino = {
                'medio_entrega': medio_entrega,
                'banco_destino': banco_destino,
                'cuenta_destino': cuenta_destino,
                'numero_cheque': numero_cheque,
                'referencia_destino': referencia_destino,
            }

        with DatabaseManager() as db:
            # Serializa cualquier intento de pago sobre la misma planilla.
            # Esto evita que dos solicitudes concurrentes lean el mismo saldo
            # pendiente y generen dos pagos/asientos antes del COMMIT.
            lock_rows = db.execute_query(
                """
                SELECT id
                FROM contabilidad.planilla_periodo
                WHERE id = %s
                  AND tipo_planilla IN ('PLANTA','COLABORADORES')
                FOR UPDATE
                """,
                (planilla_id,)
            )
            if not lock_rows:
                return _json_error('La planilla no existe.', 404)

            # Recalcular SIEMPRE despues de adquirir el lock, de modo que un
            # segundo request vea el pago confirmado por la transaccion previa.
            planilla = _obtener_planilla(db, planilla_id)
            if not planilla:
                return _json_error('La planilla no existe.', 404)
            assert_gestion_abierta(db, int(planilla['gestion']), 'registrar pagos de planilla')
            if planilla['estado'] not in ('CONSOLIDADA', 'PAGADA'):
                return _json_error('Solo se pueden pagar planillas CONSOLIDADAS.')
            if money(planilla['saldo_pendiente_real']) <= 0:
                return _json_error('La planilla no tiene saldo pendiente de pago.')
            _cuenta_salida(db, medio, caja_id, cuenta_bancaria_id)
            detalles = _detalles_para_pago(db, planilla_id, scope, detalle_ids, unidad_id)
            if not detalles:
                return _json_error('No hay beneficiarios pendientes para pagar con los criterios seleccionados.')
            parametros = _parametros_gestion(db, int(planilla['gestion']))
            cuenta_pasivo = _cuenta_pasivo_planilla(parametros, planilla['tipo_planilla'])
            pagos_creados = _registrar_pagos_por_unidad(db, planilla, detalles, fecha_pago, medio, caja_id, cuenta_bancaria_id, cuenta_pasivo, referencia, glosa, datos_destino=datos_destino)
            _recalcular_estado_pago(db, planilla_id)
        return _json_ok('Pago registrado correctamente.', pagos=pagos_creados, redirect=url_for('planilla_pagos.detalle', planilla_id=planilla_id))
    except ValueError as exc:
        return _json_error(str(exc))
    except pg_errors.CheckViolation as exc:
        # La BD actua como segunda barrera contra sobrepago/concurrencia.
        current_app.logger.warning(
            'Pago de planilla rechazado por regla de integridad planilla_id=%s: %s',
            planilla_id,
            exc
        )
        return _json_error(
            'El saldo de la planilla cambio mientras se registraba el pago. '
            'Actualice la pantalla y verifique los pagos ya registrados antes de volver a intentar.',
            409
        )
    except pg_errors.UniqueViolation:
        current_app.logger.exception('Error de correlativo duplicado al registrar pago de planilla %s', planilla_id)
        return _json_error(
            'No se pudo registrar el pago porque los correlativos internos de la base de datos requieren mantenimiento. ' \
            'Ejecute el script de ajuste de correlativos y vuelva a intentarlo.',
            500
        )
    except Exception:
        current_app.logger.exception('Error inesperado al registrar pago de planilla %s', planilla_id)
        return _json_error(mensaje_error_operacion('registrar el pago'), 500)


@planilla_pagos_bp.route('/api/<int:planilla_id>/revertir-pagos', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def revertir_pagos(planilla_id: int):
    data = request.get_json(silent=True) or {}
    try:
        justificativo = _limit_text(data.get('justificativo'), 'Justificativo', 800, required=True)
        pago_ids = data.get('pago_ids') or []
        if isinstance(pago_ids, str):
            pago_ids = [x for x in pago_ids.split(',') if x]
        pago_ids = [int(x) for x in pago_ids if str(x).isdigit()]
        scope = _upper(data.get('scope') or 'SELECCION')
        with DatabaseManager() as db:
            planilla = _obtener_planilla(db, planilla_id)
            if not planilla:
                return _json_error('La planilla no existe.', 404)
            assert_gestion_abierta(db, int(planilla['gestion']), 'revertir pagos de planilla')
            pagos = _pagos_para_reversion(db, planilla_id, scope, pago_ids)
            if not pagos:
                return _json_error('No hay pagos vigentes para revertir.')
            reversos = []
            for pago in pagos:
                reverso_id = _crear_asiento_reverso_pago(db, pago, justificativo)
                db.execute_update(
                    """
                    UPDATE contabilidad.pago
                    SET estado = 'ANULADO',
                        glosa = COALESCE(glosa || E'\n', '') || %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s AND estado = 'CONFIRMADO'
                    """,
                    (f'Anulación/reversión de pago de planilla: {justificativo}', pago['id'])
                )
                db.execute_update(
                    """
                    UPDATE contabilidad.planilla_pago_aplicacion
                    SET estado = 'ANULADO',
                        fecha_anulacion = CURRENT_DATE,
                        asiento_reversion_id = %s,
                        justificativo_anulacion = %s,
                        anulado_por = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE pago_id = %s
                      AND planilla_periodo_id = %s
                      AND estado = 'VIGENTE'
                    """,
                    (reverso_id, justificativo, _usuario_actual(), pago['id'], planilla_id)
                )
                reversos.append(reverso_id)
            _recalcular_estado_pago(db, planilla_id)
        return _json_ok('Pago(s) revertido(s) correctamente.', reversos=reversos, redirect=url_for('planilla_pagos.detalle', planilla_id=planilla_id))
    except ValueError as exc:
        return _json_error(str(exc))
    except pg_errors.UniqueViolation:
        current_app.logger.exception('Error de correlativo duplicado al revertir pagos de planilla %s', planilla_id)
        return _json_error(
            'No se pudo revertir el pago porque los correlativos internos de la base de datos requieren mantenimiento. ' \
            'Ejecute el script de ajuste de correlativos y vuelva a intentarlo.',
            500
        )
    except Exception:
        current_app.logger.exception('Error inesperado al revertir pagos de planilla %s', planilla_id)
        return _json_error(mensaje_error_operacion('revertir el pago'), 500)


# ============================================================
# Persistencia de pagos
# ============================================================

def _detalles_para_pago(db: DatabaseManager, planilla_id: int, scope: str, detalle_ids: list[int], unidad_id: int | None) -> list[dict[str, Any]]:
    detalles = _detalles_planilla(db, planilla_id, unidad_id=unidad_id, solo_pendientes=True)
    if scope == 'GLOBAL':
        return detalles
    if scope == 'UNIDAD':
        return detalles
    if not detalle_ids:
        raise ValueError('Debe seleccionar al menos un beneficiario.')
    wanted = set(detalle_ids)
    return [d for d in detalles if int(d['id']) in wanted]


def _registrar_pagos_por_unidad(db: DatabaseManager, planilla: dict[str, Any], detalles: list[dict[str, Any]], fecha_pago: date,
                                medio: str, caja_id: int | None, cuenta_bancaria_id: int | None, cuenta_pasivo: str,
                                referencia: str | None, glosa: str, datos_destino: dict[str, Any] | None = None) -> list[int]:
    grupos: OrderedDict[tuple[int, str], list[dict[str, Any]]] = OrderedDict()
    for d in detalles:
        unidad_id = int(d['unidad_negocio_id'])
        unidad_codigo = d.get('unidad_negocio_codigo') or 'S/U'
        grupos.setdefault((unidad_id, unidad_codigo), []).append(d)
    pagos: list[int] = []
    for (unidad_id, unidad_codigo), items in grupos.items():
        total = sum((money(d['saldo_real']) for d in items), Decimal('0.00')).quantize(CUANTIA)
        if total <= 0:
            continue
        ref = referencia or f'PAGO-{planilla["codigo"]}-{unidad_codigo}'[:150]
        glosa_pago = f'{glosa} - {unidad_codigo}'[:500]
        pago_id = db.execute_insert(
            """
            INSERT INTO contabilidad.pago (
                fecha, unidad_negocio_id, proveedor_auxiliar_id, medio_pago, contra_cuenta_codigo,
                caja_id, cuenta_bancaria_id, moneda_codigo, tipo_cambio, monto_total,
                referencia, glosa, estado, origen_operacion, actualizado_en
            ) VALUES (%s, %s, NULL, %s::contabilidad.medio_pago_enum, %s, %s, %s, %s, %s, %s, %s, %s,
                      'CONFIRMADO'::contabilidad.estado_generico_enum, 'PLANILLA'::contabilidad.origen_tesoreria_enum, CURRENT_TIMESTAMP)
            """,
            (fecha_pago, unidad_id, medio, cuenta_pasivo, caja_id if medio == 'CAJA' else None,
             cuenta_bancaria_id if medio == 'BANCO' else None, planilla['moneda_codigo'], planilla['tipo_cambio'],
             total, ref, glosa_pago)
        )
        sec = 1
        for d in items:
            monto = money(d['saldo_real'])
            db.execute_insert(
                """
                INSERT INTO contabilidad.pago_detalle (
                    pago_id, secuencia, tipo_linea, compromiso_detalle_id, descripcion,
                    cantidad, precio_unitario, subtotal, observacion, actualizado_en
                ) VALUES (%s, %s, 'DIRECTO'::contabilidad.tipo_linea_tesoreria_enum, NULL, %s, 1, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (pago_id, sec, f'Pago planilla {planilla["codigo"]} - {d["nombre_completo"]}'[:300], monto, monto, d.get('observacion')),
                return_id=False
            )
            db.execute_insert(
                """
                INSERT INTO contabilidad.planilla_pago_aplicacion (
                    planilla_periodo_id, planilla_detalle_id, pago_id, fecha_aplicacion,
                    monto_aplicado, observacion, estado, medio_entrega, banco_destino,
                    cuenta_destino, numero_cheque, referencia_destino, creado_en, actualizado_en
                ) VALUES (%s, %s, %s, %s, %s, %s, 'VIGENTE', %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (planilla['id'], d['id'], pago_id, fecha_pago, monto, f'Pago aplicado desde módulo Pago de Planillas. {ref}',
                 datos_destino.get('medio_entrega') if datos_destino else None,
                 datos_destino.get('banco_destino') if datos_destino else None,
                 datos_destino.get('cuenta_destino') if datos_destino else None,
                 datos_destino.get('numero_cheque') if datos_destino else None,
                 datos_destino.get('referencia_destino') if datos_destino else None),
                return_id=False
            )
            sec += 1
        asiento_id = _crear_asiento_pago_planilla(db, pago_id, planilla, items, cuenta_pasivo)
        db.execute_update('UPDATE contabilidad.pago SET asiento_id = %s, actualizado_en = CURRENT_TIMESTAMP WHERE id = %s', (asiento_id, pago_id))
        pagos.append(pago_id)
    return pagos


def _crear_asiento_pago_planilla(db: DatabaseManager, pago_id: int, planilla: dict[str, Any], detalles: list[dict[str, Any]], cuenta_pasivo: str) -> int:
    pago = db.execute_query('SELECT * FROM contabilidad.pago WHERE id = %s', (pago_id,))[0]
    salida = _cuenta_salida(db, pago['medio_pago'], pago.get('caja_id'), pago.get('cuenta_bancaria_id'))
    total = money(pago['monto_total'])
    asiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha, unidad_negocio_id, moneda_codigo, tipo_cambio, glosa, referencia,
            modulo_origen, tabla_origen, origen_id, estado, atributos, actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, 'PLANILLAS', 'contabilidad.pago', %s,
                  'CONFIRMADO', %s::jsonb, CURRENT_TIMESTAMP)
        """,
        (pago['fecha'], pago['unidad_negocio_id'], pago['moneda_codigo'], pago['tipo_cambio'], pago['glosa'], pago['referencia'], pago_id,
         Json({'origen': 'planilla_pagos', 'accion': 'pago_planilla', 'planilla_id': int(planilla['id'])}))
    )
    sec = 1
    for d in detalles:
        monto = money(d['saldo_real'])
        if monto <= 0:
            continue
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber,
                monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s::jsonb)
            """,
            (asiento_id, sec, cuenta_pasivo, d.get('auxiliar_id'), f'Pago planilla {planilla["codigo"]} - {d["nombre_completo"]}'[:300], monto, monto, pago['referencia'], Json({'tipo': 'debe_pago_planilla', 'detalle_id': int(d['id'])})),
            return_id=False
        )
        sec += 1
    db.execute_insert(
        """
        INSERT INTO contabilidad.asiento_detalle (
            asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber,
            monto_moneda, referencia, atributos
        ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s::jsonb)
        """,
        (asiento_id, sec, salida['cuenta_contable_codigo'], salida.get('auxiliar_id'), f'Salida {pago["medio_pago"]} - {salida["nombre"]}'[:300], total, total, pago['referencia'], Json({'tipo': 'haber_salida_planilla'})),
        return_id=False
    )
    db.execute_insert(
        """
        INSERT INTO contabilidad.documento_asiento (modulo, tabla_origen, origen_id, asiento_id)
        VALUES ('PLANILLAS', 'contabilidad.pago', %s, %s)
        ON CONFLICT (tabla_origen, origen_id)
        DO UPDATE SET modulo = EXCLUDED.modulo, asiento_id = EXCLUDED.asiento_id
        """,
        (pago_id, asiento_id),
        return_id=False
    )
    return asiento_id


def _pagos_planilla(db: DatabaseManager, planilla_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute_query(
        """
        SELECT p.id, p.fecha, p.medio_pago, p.monto_total, p.referencia, p.glosa, p.estado,
               p.asiento_id, p.caja_id, p.cuenta_bancaria_id,
               un.codigo AS unidad_codigo, un.nombre AS unidad_nombre,
               COUNT(ppa.id) FILTER (WHERE ppa.estado = 'VIGENTE') AS aplicaciones,
               MAX(ppa.medio_entrega) FILTER (WHERE ppa.estado = 'VIGENTE') AS medio_entrega,
               MAX(ppa.banco_destino) FILTER (WHERE ppa.estado = 'VIGENTE') AS banco_destino,
               MAX(ppa.cuenta_destino) FILTER (WHERE ppa.estado = 'VIGENTE') AS cuenta_destino,
               MAX(ppa.numero_cheque) FILTER (WHERE ppa.estado = 'VIGENTE') AS numero_cheque,
               MAX(ppa.referencia_destino) FILTER (WHERE ppa.estado = 'VIGENTE') AS referencia_destino
        FROM contabilidad.pago p
        JOIN contabilidad.planilla_pago_aplicacion ppa ON ppa.pago_id = p.id
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = p.unidad_negocio_id
        WHERE ppa.planilla_periodo_id = %s
        GROUP BY p.id, un.codigo, un.nombre
        ORDER BY p.fecha DESC, p.id DESC
        """,
        (planilla_id,)
    )]


def _pagos_para_reversion(db: DatabaseManager, planilla_id: int, scope: str, pago_ids: list[int]) -> list[dict[str, Any]]:
    params: list[Any] = [planilla_id]
    where = ["ppa.planilla_periodo_id = %s", "ppa.estado = 'VIGENTE'", "p.estado = 'CONFIRMADO'"]
    if scope != 'GLOBAL':
        if not pago_ids:
            raise ValueError('Debe seleccionar al menos un pago para revertir.')
        where.append('p.id = ANY(%s)')
        params.append(pago_ids)
    return [dict(r) for r in db.execute_query(
        f"""
        SELECT DISTINCT p.*
        FROM contabilidad.pago p
        JOIN contabilidad.planilla_pago_aplicacion ppa ON ppa.pago_id = p.id
        WHERE {' AND '.join(where)}
        ORDER BY p.fecha DESC, p.id DESC
        """,
        tuple(params)
    )]


def _crear_asiento_reverso_pago(db: DatabaseManager, pago: dict[str, Any], justificativo: str) -> int:
    if not pago.get('asiento_id'):
        raise ValueError(f'El pago {pago["id"]} no tiene asiento para revertir.')
    detalles = db.execute_query(
        """
        SELECT *
        FROM contabilidad.asiento_detalle
        WHERE asiento_id = %s
        ORDER BY secuencia
        """,
        (pago['asiento_id'],)
    )
    if not detalles:
        raise ValueError(f'No se encontró detalle contable del pago {pago["id"]}.')
    total_debe = sum((money(d['haber']) for d in detalles), Decimal('0.00')).quantize(CUANTIA)
    total_haber = sum((money(d['debe']) for d in detalles), Decimal('0.00')).quantize(CUANTIA)
    if total_debe != total_haber:
        raise ValueError(f'El reverso del pago {pago["id"]} no cuadra.')
    reverso_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha, unidad_negocio_id, moneda_codigo, tipo_cambio, glosa, referencia,
            modulo_origen, tabla_origen, origen_id, estado, atributos, actualizado_en
        ) VALUES (CURRENT_DATE, %s, %s, %s, %s, %s, 'PLANILLAS', 'contabilidad.pago', %s,
                  'CONFIRMADO', %s::jsonb, CURRENT_TIMESTAMP)
        """,
        (pago['unidad_negocio_id'], pago['moneda_codigo'], pago['tipo_cambio'], f'Reverso pago planilla: {justificativo}'[:500], f'REV-{pago["referencia"]}'[:150], pago['id'],
         Json({'origen': 'planilla_pagos', 'accion': 'reverso_pago_planilla', 'pago_original_id': int(pago['id'])}))
    )
    sec = 1
    for d in detalles:
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber,
                monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (reverso_id, sec, d['cuenta_codigo'], d.get('auxiliar_id'), f'Reverso {d["glosa"]}'[:300], money(d['haber']), money(d['debe']), max(money(d['debe']), money(d['haber'])), f'REV-{pago["referencia"]}'[:150], Json({'tipo': 'reverso_pago_planilla', 'asiento_original_id': int(pago['asiento_id'])})),
            return_id=False
        )
        sec += 1
    return reverso_id


def _recalcular_estado_pago(db: DatabaseManager, planilla_id: int):
    rows = db.execute_query(
        """
        WITH pagos AS (
            SELECT ppa.planilla_detalle_id,
                   COALESCE(SUM(CASE WHEN ppa.estado = 'VIGENTE' AND p.estado = 'CONFIRMADO' THEN ppa.monto_aplicado ELSE 0 END),0) AS pagado
            FROM contabilidad.planilla_pago_aplicacion ppa
            JOIN contabilidad.pago p ON p.id = ppa.pago_id
            WHERE ppa.planilla_periodo_id = %s
            GROUP BY ppa.planilla_detalle_id
        )
        SELECT pd.id, pd.liquido_pagable, COALESCE(pagos.pagado,0) AS pagado
        FROM contabilidad.planilla_detalle pd
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = pd.unidad_negocio_id
        LEFT JOIN pagos ON pagos.planilla_detalle_id = pd.id
        WHERE pd.planilla_periodo_id = %s
          AND pd.estado <> 'EXCLUIDO'
        """,
        (planilla_id, planilla_id)
    )
    total_pagado = Decimal('0.00')
    total_liquido = Decimal('0.00')
    for r in rows:
        liquido = money(r['liquido_pagable'])
        pagado = min(money(r['pagado']), liquido)
        saldo = (liquido - pagado).quantize(CUANTIA)
        estado = 'PAGADO' if saldo <= 0 and liquido > 0 else ('PARCIAL' if pagado > 0 else 'PENDIENTE')
        db.execute_update(
            """
            UPDATE contabilidad.planilla_detalle
            SET monto_pagado = %s,
                saldo_pendiente = %s,
                estado = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (pagado, saldo, estado, r['id'])
        )
        total_pagado += pagado
        total_liquido += liquido
    saldo_total = max(total_liquido - total_pagado, Decimal('0.00')).quantize(CUANTIA)
    estado_planilla = 'PAGADA' if total_liquido > 0 and saldo_total <= 0 else 'CONSOLIDADA'
    db.execute_update(
        """
        UPDATE contabilidad.planilla_periodo
        SET total_pagado = %s,
            saldo_pendiente = %s,
            estado = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (total_pagado.quantize(CUANTIA), saldo_total, estado_planilla, planilla_id)
    )


# ============================================================
# PDFs
# ============================================================

@planilla_pagos_bp.route('/<int:planilla_id>/boletas/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_masivo(planilla_id: int):
    with DatabaseManager() as db:
        planilla = _obtener_planilla(db, planilla_id)
        if not planilla:
            return render_template('404.html'), 404
        detalles = _attach_conceptos_boleta(db, _detalles_planilla(db, planilla_id))
    pdf = _build_boletas_pdf(planilla, detalles)
    filename = ('boletas' if planilla['tipo_planilla'] == 'PLANTA' else 'comprobantes') + f'_{planilla["codigo"]}.pdf'
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{filename}"'})


@planilla_pagos_bp.route('/detalle/<int:detalle_id>/boleta/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_individual(detalle_id: int):
    with DatabaseManager() as db:
        rows = db.execute_query(
            """
            SELECT pd.*, un.nit AS unidad_nit, un.logo_ruta AS unidad_logo_ruta, un.logo_nombre_original AS unidad_logo_nombre,
                   pp.codigo, pp.tipo_planilla, pp.gestion, pp.mes, pp.moneda_codigo,
                   pp.estado AS estado_planilla, pp.fecha_planilla,
                   COALESCE(pagos_det.pagado_real, COALESCE(pd.monto_pagado, 0)) AS pagado_real_calculado,
                   GREATEST(pd.liquido_pagable - COALESCE(pagos_det.pagado_real, COALESCE(pd.monto_pagado, 0)), 0) AS saldo_real_calculado,
                   pay.medio_entrega, pay.banco_destino, pay.cuenta_destino,
                   pay.numero_cheque, pay.referencia_destino
            FROM contabilidad.planilla_detalle pd
            JOIN contabilidad.planilla_periodo pp ON pp.id = pd.planilla_periodo_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = pd.unidad_negocio_id
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(ppa.monto_aplicado), 0) AS pagado_real
                FROM contabilidad.planilla_pago_aplicacion ppa
                JOIN contabilidad.pago p ON p.id = ppa.pago_id
                WHERE ppa.planilla_detalle_id = pd.id
                  AND ppa.estado = 'VIGENTE'
                  AND p.estado = 'CONFIRMADO'
            ) pagos_det ON TRUE
            LEFT JOIN LATERAL (
                SELECT ppa.medio_entrega, ppa.banco_destino, ppa.cuenta_destino,
                       ppa.numero_cheque, ppa.referencia_destino
                FROM contabilidad.planilla_pago_aplicacion ppa
                JOIN contabilidad.pago p ON p.id = ppa.pago_id
                WHERE ppa.planilla_detalle_id = pd.id
                  AND ppa.estado = 'VIGENTE'
                  AND p.estado = 'CONFIRMADO'
                ORDER BY p.fecha DESC, p.id DESC
                LIMIT 1
            ) pay ON TRUE
            WHERE pd.id = %s
            """,
            (detalle_id,)
        )
        if not rows:
            return render_template('404.html'), 404
        detalle = dict(rows[0])
        planilla = {
            'id': detalle['planilla_periodo_id'], 'codigo': detalle['codigo'], 'tipo_planilla': detalle['tipo_planilla'],
            'gestion': detalle['gestion'], 'mes': detalle['mes'], 'moneda_codigo': detalle['moneda_codigo'],
            'estado': detalle['estado_planilla'], 'fecha_planilla': detalle['fecha_planilla']
        }
        detalle['pagado_real'] = detalle.get('pagado_real_calculado') if detalle.get('pagado_real_calculado') is not None else (detalle.get('monto_pagado') if detalle.get('monto_pagado') is not None else Decimal('0.00'))
        detalle['saldo_real'] = detalle.get('saldo_real_calculado') if detalle.get('saldo_real_calculado') is not None else (detalle.get('saldo_pendiente') if detalle.get('saldo_pendiente') is not None else money(detalle.get('liquido_pagable')))
        detalle = _attach_conceptos_boleta(db, [detalle])[0]
    pdf = _build_boletas_pdf(planilla, [detalle])
    nombre = 'boleta' if planilla['tipo_planilla'] == 'PLANTA' else 'comprobante'
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{nombre}_{detalle_id}.pdf"'})


def _styles():
    ss = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('dxt_title', parent=ss['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=12, textColor=NAVY),
        'small': ParagraphStyle('dxt_small', parent=ss['Normal'], fontName='Helvetica', fontSize=6.7, leading=7.8, textColor=TEXT),
        'bold': ParagraphStyle('dxt_bold', parent=ss['Normal'], fontName='Helvetica-Bold', fontSize=6.7, leading=7.8, textColor=TEXT),
        'section': ParagraphStyle('dxt_section', parent=ss['Normal'], fontName='Helvetica-Bold', fontSize=6.8, leading=7.8, textColor=TEXT, alignment=TA_CENTER),
        'center': ParagraphStyle('dxt_center', parent=ss['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=NAVY, alignment=TA_CENTER),
        'right': ParagraphStyle('dxt_right', parent=ss['Normal'], fontName='Helvetica', fontSize=6.7, leading=7.8, alignment=TA_RIGHT, textColor=TEXT),
        'right_bold': ParagraphStyle('dxt_right_bold', parent=ss['Normal'], fontName='Helvetica-Bold', fontSize=6.7, leading=7.8, alignment=TA_RIGHT, textColor=TEXT),
    }


def _pdf_text(value: Any, default: str = '-') -> str:
    text = _clean(value)
    return escape(text if text else default)


def _pdf_par(value: Any, style: ParagraphStyle, default: str = '-') -> Paragraph:
    return Paragraph(_pdf_text(value, default), style)


def _pdf_static(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def _logo_unidad_path(detalle: dict[str, Any]) -> str | None:
    ruta = detalle.get('unidad_logo_ruta')
    if ruta:
        try:
            path = (Path(Config.DXT_CONTA_DATA_DIR) / str(ruta)).resolve()
            if path.exists() and path.is_file():
                return str(path)
        except Exception:
            pass

    # No usar el logo global de DXT-CONTA como reemplazo del logo de una
    # unidad de negocio. Un comprobante debe mostrar exclusivamente el logo
    # configurado para su propia unidad; si no existe, el espacio queda vacío.
    return None


def _img_logo_for_pdf(path: str | None, max_w: float = 32*mm, max_h: float = 15*mm):
    if not path:
        return ''
    try:
        img = ImageReader(path)
        w, h = img.getSize()
        ratio = min(max_w / float(w), max_h / float(h))
        return Image(path, width=w * ratio, height=h * ratio)
    except Exception:
        return ''


def _conceptos_detalle(detalle: dict[str, Any], tipo: str):
    conceptos = detalle.get('conceptos') or []
    ingresos = []
    egresos = []
    aportes = []
    for c in conceptos:
        monto = money(c.get('monto'))
        if monto <= 0:
            continue
        codigo = str(c.get('codigo_concepto') or '').upper()
        nombre = c.get('nombre_concepto') or codigo or 'Concepto'
        tipo_concepto = str(c.get('tipo_concepto') or '').upper()
        impacto = str(c.get('impacto_liquido') or '').upper()
        item = {'nombre': nombre, 'monto': monto, 'codigo': codigo, 'tipo': tipo_concepto, 'impacto': impacto}
        if tipo_concepto == 'APORTE_PATRONAL':
            aportes.append(item)
        elif tipo_concepto == 'INGRESO' or impacto == 'SUMA':
            ingresos.append(item)
        elif tipo_concepto in ('DESCUENTO', 'RETENCION') or impacto == 'RESTA':
            egresos.append(item)
    return ingresos, egresos, aportes


def _attach_conceptos_boleta(db: DatabaseManager, detalles: list[dict[str, Any]]):
    ids = [int(d['id']) for d in detalles if d.get('id')]
    if not ids:
        return detalles
    rows = db.execute_query(
        """
        SELECT planilla_detalle_id, codigo_concepto, nombre_concepto, tipo_concepto, impacto_liquido, monto
        FROM contabilidad.planilla_detalle_concepto
        WHERE planilla_detalle_id = ANY(%s)
        ORDER BY secuencia, id
        """,
        (ids,)
    )
    por = {}
    for r in rows:
        por.setdefault(int(r['planilla_detalle_id']), []).append(dict(r))
    for d in detalles:
        d['conceptos'] = por.get(int(d.get('id') or 0), [])
    return detalles


def _scaled_widths(total_width: float, weights: list[float]) -> list[float]:
    total_weight = sum(weights) or 1
    return [(total_width * weight) / total_weight for weight in weights]


def _boleta_page_layout(canvas, doc):
    """Dibuja las medias cartas ocupadas y una guía central de corte."""
    border_width = LETTER_WIDTH - (2 * BOLETA_SIDE_MARGIN)
    border_height = HALF_LETTER_HEIGHT - (2 * BOLETA_VERTICAL_MARGIN)
    page_number = canvas.getPageNumber()
    total_boletas = int(getattr(doc, 'total_boletas', 0) or 0)
    dibujar_inferior = (page_number * 2) <= total_boletas

    canvas.saveState()
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(0.9)
    canvas.rect(
        BOLETA_SIDE_MARGIN,
        HALF_LETTER_HEIGHT + BOLETA_VERTICAL_MARGIN,
        border_width,
        border_height,
        stroke=1,
        fill=0,
    )
    if dibujar_inferior:
        canvas.rect(
            BOLETA_SIDE_MARGIN,
            BOLETA_VERTICAL_MARGIN,
            border_width,
            border_height,
            stroke=1,
            fill=0,
        )

    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.setDash(3, 2)
    canvas.line(
        BOLETA_SIDE_MARGIN,
        HALF_LETTER_HEIGHT,
        LETTER_WIDTH - BOLETA_SIDE_MARGIN,
        HALF_LETTER_HEIGHT,
    )
    canvas.restoreState()


def _build_boletas_pdf(planilla: dict[str, Any], detalles: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=BOLETA_SIDE_MARGIN,
        rightMargin=BOLETA_SIDE_MARGIN,
        topMargin=0,
        bottomMargin=0,
    )
    doc.total_boletas = len(detalles)

    border_width = LETTER_WIDTH - (2 * BOLETA_SIDE_MARGIN)
    border_height = HALF_LETTER_HEIGHT - (2 * BOLETA_VERTICAL_MARGIN)
    frame_width = border_width - (2 * BOLETA_BORDER_PADDING)
    frame_height = border_height - (2 * BOLETA_BORDER_PADDING)
    frame_x = BOLETA_SIDE_MARGIN + BOLETA_BORDER_PADDING

    top_frame = Frame(
        frame_x,
        HALF_LETTER_HEIGHT + BOLETA_VERTICAL_MARGIN + BOLETA_BORDER_PADDING,
        frame_width,
        frame_height,
        id='boleta_superior',
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    bottom_frame = Frame(
        frame_x,
        BOLETA_VERTICAL_MARGIN + BOLETA_BORDER_PADDING,
        frame_width,
        frame_height,
        id='boleta_inferior',
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates([
        PageTemplate(
            id='carta_vertical_dos_boletas',
            frames=[top_frame, bottom_frame],
            onPage=_boleta_page_layout,
            pagesize=letter,
        )
    ])

    styles = _styles()
    content_width = frame_width
    story = []
    for idx, detalle in enumerate(detalles):
        if idx:
            story.append(FrameBreak())
        story.extend(_boleta_story(planilla, detalle, styles, content_width))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def _concept_row(nombre: Any, monto: Any, styles: dict[str, ParagraphStyle], total: bool = False):
    nombre_style = styles['bold'] if total else styles['small']
    monto_style = styles['right_bold'] if total else styles['right']
    nombre_text = f'<b>{_pdf_text(nombre, "")}</b>' if total else _pdf_text(nombre, '')
    monto_text = f'<b>{moneyfmt(monto)}</b>' if total else moneyfmt(monto)
    return [Paragraph(nombre_text, nombre_style), Paragraph(monto_text, monto_style)]


def _boleta_story(planilla: dict[str, Any], d: dict[str, Any], styles: dict[str, ParagraphStyle], content_width: float):
    tipo = planilla['tipo_planilla']
    es_planta = tipo == 'PLANTA'
    titulo = 'BOLETA DE PAGO' if es_planta else 'COMPROBANTE DE PAGO'
    periodo = f'{_mes_nombre(int(planilla["mes"]))} {planilla["gestion"]}'
    unidad_nombre = d.get('unidad_negocio_nombre') or 'Unidad de negocio'
    unidad_nit = d.get('unidad_nit') or ''
    logo = _img_logo_for_pdf(_logo_unidad_path(d), max_w=29*mm, max_h=13*mm)

    unidad_lineas = f'<b>{_pdf_text(unidad_nombre)}</b>'
    if unidad_nit:
        unidad_lineas += f'<br/><b>NIT:</b> {_pdf_text(unidad_nit)}'
    unidad_lineas += '<br/>Bolivia'
    header_left = Paragraph(unidad_lineas, ParagraphStyle('boleta_head_left', parent=styles['small'], fontName='Helvetica-Bold', fontSize=7.4, leading=8.3, textColor=NAVY))
    header_right = logo if logo else ''
    header = Table([[header_left, header_right]], colWidths=_scaled_widths(content_width, [145, 49]))
    header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LINEBELOW', (0,0), (-1,0), 0.6, BORDER),
    ]))

    titulo_tbl = Table([
        [Paragraph(f'<b>{titulo}</b>', ParagraphStyle('receipt_title', parent=styles['center'], fontName='Helvetica-Bold', fontSize=13, leading=14, textColor=NAVY))],
        [Paragraph('(Expresado en bolivianos)', ParagraphStyle('receipt_sub', parent=styles['center'], fontSize=6.7, leading=7.5, textColor=MUTED))]
    ], colWidths=[content_width])
    titulo_tbl.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))

    sueldo_base = d.get('haber_basico') if es_planta else d.get('monto_base')
    datos = [
        [_pdf_static('<b>NOMBRE</b>', styles['bold']), _pdf_par(d.get('nombre_completo'), styles['small']), _pdf_static('<b>SUELDO BASICO</b>' if es_planta else '<b>MONTO BASE</b>', styles['bold']), _pdf_static(moneyfmt(sueldo_base), styles['right'])],
        [_pdf_static('<b>C.I.</b>' if es_planta else '<b>CI/NIT</b>', styles['bold']), _pdf_par(d.get('ci_nit'), styles['small']), _pdf_static('<b>DIAS TRAB.</b>' if es_planta else '<b>RESPALDO</b>', styles['bold']), _pdf_par(str(d.get('dias_trabajados') or '-') if es_planta else str(d.get('tipo_respaldo') or '-'), styles['right'])],
        [_pdf_static('<b>CARGO</b>' if es_planta else '<b>SERVICIO</b>', styles['bold']), _pdf_par(d.get('cargo_referencia') or d.get('descripcion_servicio'), styles['small']), _pdf_static('<b>MES</b>', styles['bold']), _pdf_static(escape(periodo), styles['right'])],
        [_pdf_static('<b>F. INGRESO</b>', styles['bold']), _pdf_par(d.get('fecha_ingreso'), styles['small']), _pdf_static('<b>UNIDAD</b>', styles['bold']), _pdf_par(d.get('unidad_negocio_codigo'), styles['right'])],
    ]
    if not es_planta:
        datos.append([_pdf_static('<b>FACTURA</b>', styles['bold']), _pdf_par(d.get('numero_factura'), styles['small']), _pdf_static('<b>NIT FACTURA</b>', styles['bold']), _pdf_par(d.get('nit_factura'), styles['right'])])
    tbl_datos = Table(datos, colWidths=_scaled_widths(content_width, [28, 75, 37, 54]))
    tbl_datos.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.35, BORDER),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (0,-1), HEAD_FILL),
        ('BACKGROUND', (2,0), (2,-1), HEAD_FILL),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
    ]))

    conceptos_ing, conceptos_egr, conceptos_aportes = _conceptos_detalle(d, tipo)

    ingresos = []
    base = money(d.get('haber_basico') if es_planta else d.get('monto_base'))
    if base > 0:
        ingresos.append({'nombre': 'Haber basico' if es_planta else 'Honorario / servicio', 'monto': base})
    ingresos.extend({'nombre': c['nombre'], 'monto': c['monto']} for c in conceptos_ing)
    total_ingresos = money(d.get('total_ganado'))
    delta_ing = total_ingresos - sum((money(i['monto']) for i in ingresos), Decimal('0.00'))
    if delta_ing > Decimal('0.00'):
        ingresos.append({'nombre': 'Otros ingresos / ajuste', 'monto': delta_ing})

    egresos = [{'nombre': c['nombre'], 'monto': c['monto']} for c in conceptos_egr]
    total_egresos = money(d.get('descuentos_laborales')) + money(d.get('retenciones')) + money(d.get('otros_descuentos'))
    suma_egr = sum((money(e['monto']) for e in egresos), Decimal('0.00'))
    delta_egr = total_egresos - suma_egr
    if delta_egr > Decimal('0.00'):
        egresos.append({'nombre': 'Descuentos / retenciones', 'monto': delta_egr})

    aportes = [{'nombre': c['nombre'], 'monto': c['monto']} for c in conceptos_aportes]
    total_aportes = money(d.get('aportes_patronales'))
    suma_aportes = sum((money(a['monto']) for a in aportes), Decimal('0.00'))
    delta_aportes = total_aportes - suma_aportes
    if delta_aportes > Decimal('0.00'):
        aportes.append({'nombre': 'Aportes patronales', 'monto': delta_aportes})

    ie_rows = [[_pdf_static('<b>CONCEPTOS APLICADOS</b>', styles['section']), '', '', '']]
    row_styles = [
        ('SPAN', (0,0), (-1,0)),
        ('BACKGROUND', (0,0), (-1,0), HEAD_FILL),
        ('TEXTCOLOR', (0,0), (-1,0), TEXT),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
    ]
    current_row = 1

    ie_rows.append([
        _pdf_static('<b>INGRESOS</b>', styles['bold']), '',
        _pdf_static('<b>EGRESOS</b>', styles['bold']), ''
    ])
    row_styles.extend([
        ('SPAN', (0,current_row), (1,current_row)),
        ('SPAN', (2,current_row), (3,current_row)),
        ('BACKGROUND', (0,current_row), (-1,current_row), HEAD_FILL),
        ('TEXTCOLOR', (0,current_row), (-1,current_row), TEXT),
        ('ALIGN', (0,current_row), (1,current_row), 'CENTER'),
        ('ALIGN', (2,current_row), (3,current_row), 'CENTER'),
    ])
    current_row += 1

    def concept_cells(item: dict[str, Any] | None, empty_label: str = ''):
        if item:
            return [_pdf_par(item.get('nombre'), styles['small']), _pdf_static(moneyfmt(item.get('monto')), styles['right'])]
        if empty_label:
            return [_pdf_static(escape(empty_label), styles['small']), _pdf_static(moneyfmt(Decimal('0.00')), styles['right'])]
        return ['', '']

    max_ie_rows = max(len(ingresos), len(egresos), 1)
    for i in range(max_ie_rows):
        left_empty = 'Sin movimiento' if i == 0 and not ingresos else ''
        right_empty = 'Sin movimiento' if i == 0 and not egresos else ''
        left = concept_cells(ingresos[i] if i < len(ingresos) else None, left_empty)
        right = concept_cells(egresos[i] if i < len(egresos) else None, right_empty)
        ie_rows.append(left + right)
        current_row += 1

    ie_rows.append([
        _pdf_static('<b>TOTAL INGRESOS</b>', styles['bold']),
        _pdf_static(f'<b>{moneyfmt(total_ingresos)}</b>', styles['right_bold']),
        _pdf_static('<b>TOTAL EGRESOS</b>', styles['bold']),
        _pdf_static(f'<b>{moneyfmt(total_egresos)}</b>', styles['right_bold']),
    ])
    row_styles.append(('BACKGROUND', (0,current_row), (-1,current_row), ROW_ALT))
    current_row += 1

    if es_planta or total_aportes > 0:
        ie_rows.append([_pdf_static('<b>APORTES PATRONALES</b>', styles['bold']), '', '', ''])
        row_styles.extend([
            ('SPAN', (0,current_row), (-1,current_row)),
            ('BACKGROUND', (0,current_row), (-1,current_row), HEAD_FILL),
            ('TEXTCOLOR', (0,current_row), (-1,current_row), TEXT),
            ('ALIGN', (0,current_row), (-1,current_row), 'LEFT'),
        ])
        current_row += 1
        if aportes:
            for aporte in aportes:
                ie_rows.append([
                    _pdf_par(aporte.get('nombre'), styles['small']), '', '',
                    _pdf_static(moneyfmt(aporte.get('monto')), styles['right'])
                ])
                row_styles.append(('SPAN', (0,current_row), (2,current_row)))
                current_row += 1
        else:
            ie_rows.append([
                _pdf_static('Sin movimiento', styles['small']), '', '',
                _pdf_static(moneyfmt(Decimal('0.00')), styles['right'])
            ])
            row_styles.append(('SPAN', (0,current_row), (2,current_row)))
            current_row += 1
        ie_rows.append([
            _pdf_static('<b>TOTAL APORTES</b>', styles['bold']), '', '',
            _pdf_static(f'<b>{moneyfmt(total_aportes)}</b>', styles['right_bold'])
        ])
        row_styles.extend([
            ('SPAN', (0,current_row), (2,current_row)),
            ('BACKGROUND', (0,current_row), (-1,current_row), ROW_ALT),
        ])
        current_row += 1

    tbl_ie = Table(ie_rows, colWidths=_scaled_widths(content_width, [72, 25, 72, 25]), repeatRows=1, splitByRow=1)
    tbl_ie.setStyle(TableStyle(row_styles + [
        ('GRID', (0,0), (-1,-1), 0.35, BORDER),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('ALIGN', (3,0), (3,-1), 'RIGHT'),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 0.75),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0.75),
    ]))

    liquido = money(d.get('liquido_pagable'))
    pagado = money(d.get('pagado_real') if d.get('pagado_real') is not None else d.get('monto_pagado'))
    saldo_calculado = liquido - pagado
    if saldo_calculado < Decimal('0.00'):
        saldo_calculado = Decimal('0.00')
    saldo_raw = d.get('saldo_real') if d.get('saldo_real') is not None else d.get('saldo_pendiente')
    saldo = money(saldo_raw) if saldo_raw is not None else saldo_calculado
    if pagado >= liquido and liquido > 0:
        saldo = Decimal('0.00')

    estado = 'PENDIENTE DE PAGO'
    if pagado >= liquido and liquido > 0:
        estado = 'PAGADO'
    elif pagado > 0:
        estado = 'PAGO PARCIAL'
    saldo_label = 'SIN PENDIENTE' if saldo <= Decimal('0.00') else 'SALDO PENDIENTE'
    literal_liquido = monto_literal_bolivianos(liquido).upper()

    totales_tbl = Table([
        [_pdf_static('<b>LIQUIDO PAGABLE (I - E)</b>', styles['bold']), _pdf_static(f'<b>{moneyfmt(liquido)}</b>', styles['right_bold']), _pdf_static('<b>PAGADO</b>', styles['bold']), _pdf_static(f'<b>{moneyfmt(pagado)}</b>', styles['right_bold']), _pdf_static(f'<b>{escape(saldo_label)}</b>', styles['bold']), _pdf_static(f'<b>{moneyfmt(saldo)}</b>', styles['right_bold'])],
        [_pdf_static('<b>ESTADO</b>', styles['bold']), _pdf_static(f'<b>{escape(estado)}</b>', styles['right_bold']), _pdf_static('<b>FECHA</b>', styles['bold']), _pdf_static(date.today().strftime('%d/%m/%Y'), styles['right']), '', ''],
        [_pdf_static('<b>SON:</b>', styles['bold']), _pdf_static(escape(literal_liquido), styles['small']), '', '', '', ''],
    ], colWidths=_scaled_widths(content_width, [49, 32, 24, 30, 34, 25]))
    totales_tbl.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.35, BORDER),
        ('BACKGROUND', (0,0), (0,-1), HEAD_FILL),
        ('BACKGROUND', (2,0), (2,1), HEAD_FILL),
        ('BACKGROUND', (4,0), (4,0), HEAD_FILL),
        ('SPAN', (4,1), (5,1)),
        ('SPAN', (1,2), (5,2)),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
    ]))

    medio_entrega = d.get('medio_entrega')
    destino_text = ''
    if medio_entrega:
        if medio_entrega in ('TRANSFERENCIA', 'QR'):
            destino_text = f'{medio_entrega}: {d.get("banco_destino") or "-"} - {d.get("cuenta_destino") or "-"}'
        elif medio_entrega == 'CHEQUE':
            destino_text = f'CHEQUE Nro. {d.get("numero_cheque") or "-"}'
        else:
            destino_text = 'EFECTIVO'
        if d.get('referencia_destino'):
            destino_text += f' - Ref. {d.get("referencia_destino")}'

    firma_rows = []
    if destino_text:
        firma_rows.append([_pdf_static('<b>MEDIO DE ENTREGA</b>', styles['bold']), _pdf_par(destino_text, styles['small']), '', ''])
    firma_rows.extend([
        ['', '', '', ''],
        [_pdf_static('<b>RECIBI CONFORME</b>', styles['center']), '', _pdf_static('<b>ENTREGADO POR</b>', styles['center']), ''],
    ])
    firma = Table(firma_rows, colWidths=_scaled_widths(content_width, [56, 41, 56, 41]), rowHeights=([None] if destino_text else []) + [13, 9])
    firma_style = [
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]
    if destino_text:
        firma_style.extend([
            ('SPAN', (1,0), (-1,0)),
            ('GRID', (0,0), (-1,0), 0.35, BORDER),
            ('BACKGROUND', (0,0), (0,0), HEAD_FILL),
            ('LINEABOVE', (0,2), (1,2), 0.65, TEXT),
            ('LINEABOVE', (2,2), (3,2), 0.65, TEXT),
            ('SPAN', (0,2), (1,2)),
            ('SPAN', (2,2), (3,2)),
        ])
    else:
        firma_style.extend([
            ('LINEABOVE', (0,1), (1,1), 0.65, TEXT),
            ('LINEABOVE', (2,1), (3,1), 0.65, TEXT),
            ('SPAN', (0,1), (1,1)),
            ('SPAN', (2,1), (3,1)),
        ])
    firma.setStyle(TableStyle(firma_style))

    return [header, Spacer(1, 2), titulo_tbl, Spacer(1, 2), tbl_datos, Spacer(1, 3), tbl_ie, Spacer(1, 3), totales_tbl, Spacer(1, 7), firma]


# ============================================================
# Help / utilidades
# ============================================================
