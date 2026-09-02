# ============================================================
# DXT CONTA - Planilla de Honorarios - Colaboradores
# Generación mensual editable, con snapshot de personas y conceptos.
# ============================================================

from __future__ import annotations

import io
from xml.sax.saxutils import escape
from collections import OrderedDict
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import Response, jsonify, render_template, request, session, redirect, url_for
from psycopg2.extras import Json
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from database.db_manager import DatabaseManager
from modules.planilla_honorarios_colaboradores import planilla_honorarios_colaboradores_bp
from modules.reportes_rapidos.core.utils import logo_path, usuario_actual
from utils.decorators import login_required, roles_required
from utils.planillas_security import assert_gestion_abierta, mensaje_error_operacion


ROLES_LECTURA = [9, 10, 11]
ROLES_EDICION = [9, 10]
CUANTIA = Decimal('0.01')
TIPO_PLANILLA = 'COLABORADORES'
TIPO_PERSONA = 'COLABORADOR'
ESTADOS_PERIODO = {'BORRADOR', 'CONSOLIDADA', 'PAGADA'}
MESES = [
    (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
    (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
    (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
]

ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
GREEN = colors.HexColor('#107c41')
RED = colors.HexColor('#b42318')
OFICIO = (216 * mm, 330 * mm)


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
    else:
        if number <= 0:
            raise ValueError(f'El campo "{field_name}" debe ser mayor a cero.')
    return number.quantize(CUANTIA, rounding=ROUND_HALF_UP)


def _int_value(value: Any, field_name: str, required: bool = True) -> int | None:
    if value in (None, ''):
        if required:
            raise ValueError(f'El campo "{field_name}" es obligatorio.')
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'El campo "{field_name}" debe ser numérico.') from exc


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


def _limit_text(value: Any, field_name: str, max_len: int, required: bool = False) -> str | None:
    text = _clean(value)
    if required and not text:
        raise ValueError(f'El campo "{field_name}" es obligatorio.')
    if len(text) > max_len:
        raise ValueError(f'El campo "{field_name}" no puede exceder {max_len} caracteres.')
    return text or None


def _mes_nombre(mes: int) -> str:
    return dict(MESES).get(int(mes), str(mes))


def _codigo_planilla(db: DatabaseManager, gestion: int, mes: int) -> str:
    prefijo = f'PL-HO-{gestion}{mes:02d}'
    rows = db.execute_query(
        """
        SELECT codigo
        FROM contabilidad.planilla_periodo
        WHERE codigo LIKE %s
        ORDER BY codigo DESC
        LIMIT 1
        """,
        (f'{prefijo}-%',)
    )
    if not rows:
        return f'{prefijo}-001'
    try:
        ultimo = int(str(rows[0]['codigo']).split('-')[-1])
    except Exception:
        ultimo = 0
    return f'{prefijo}-{ultimo + 1:03d}'


def _assert_tables_ready(db: DatabaseManager):
    tablas = [
        'planilla_persona', 'planilla_concepto', 'planilla_parametro', 'planilla_periodo',
        'planilla_detalle', 'planilla_detalle_concepto'
    ]
    faltantes = []
    for tabla in tablas:
        existe = db.execute_query(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'contabilidad' AND table_name = %s
            ) AS ok
            """,
            (tabla,)
        )[0]['ok']
        if not existe:
            faltantes.append(f'contabilidad.{tabla}')
    if faltantes:
        raise RuntimeError('Faltan tablas de planillas: ' + ', '.join(faltantes))




def _parametros_gestion(db: DatabaseManager, gestion: int) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT *
        FROM contabilidad.planilla_parametro
        WHERE gestion = %s
          AND activo IS TRUE
        LIMIT 1
        """,
        (gestion,)
    )
    if not rows:
        raise ValueError(f'No existe Parámetros de Planilla activo para la gestión {gestion}.')
    return dict(rows[0])


def _anios_servicio(fecha_ingreso, gestion: int, mes: int) -> int:
    if not fecha_ingreso:
        return 0
    fecha_corte = date(gestion, mes, monthrange(gestion, mes)[1])
    years = fecha_corte.year - fecha_ingreso.year
    if (fecha_corte.month, fecha_corte.day) < (fecha_ingreso.month, fecha_ingreso.day):
        years -= 1
    return max(years, 0)


def _porcentaje_bono_antiguedad(anios: int) -> Decimal:
    if anios < 2:
        return Decimal('0')
    if anios <= 4:
        return Decimal('5')
    if anios <= 7:
        return Decimal('11')
    if anios <= 10:
        return Decimal('18')
    if anios <= 14:
        return Decimal('26')
    if anios <= 19:
        return Decimal('34')
    if anios <= 24:
        return Decimal('42')
    return Decimal('50')


def _horas_mes_referenciales(gestion: int, mes: int, jornada_semanal: Decimal) -> Decimal:
    dias = Decimal(str(monthrange(gestion, mes)[1]))
    return (dias * jornada_semanal / Decimal('7')).quantize(CUANTIA, rounding=ROUND_HALF_UP)

# ============================================================
# Catálogos y consultas
# ============================================================

def _stats(db: DatabaseManager) -> dict[str, Any]:
    row = db.execute_query(
        """
        SELECT
          COUNT(*) AS total,
          COALESCE(SUM(CASE WHEN estado = 'BORRADOR' THEN 1 ELSE 0 END),0) AS borradores,
          COALESCE(SUM(CASE WHEN estado = 'CONSOLIDADA' THEN 1 ELSE 0 END),0) AS consolidadas,
          COALESCE(SUM(CASE WHEN estado = 'PAGADA' THEN 1 ELSE 0 END),0) AS pagadas,
          COALESCE(SUM(total_liquido),0) AS liquido,
          COALESCE(SUM(saldo_pendiente),0) AS pendiente
        FROM contabilidad.planilla_periodo
        WHERE tipo_planilla = 'COLABORADORES'
        """
    )[0]
    return dict(row)


def _catalogos(db: DatabaseManager) -> dict[str, Any]:
    monedas = db.execute_query("SELECT codigo, nombre FROM contabilidad.moneda WHERE activo = TRUE ORDER BY codigo")
    conceptos = db.execute_query(
        """
        SELECT id, codigo, nombre, tipo_planilla, tipo_concepto, impacto_liquido,
               metodo_calculo, COALESCE(monto_referencial, 0) AS monto_referencial,
               porcentaje_referencial, cuenta_debe_codigo, cuenta_haber_codigo,
               requiere_justificativo, observacion
        FROM contabilidad.planilla_concepto
        WHERE activo = TRUE
          AND tipo_planilla IN ('COLABORADORES','AMBAS')
          AND codigo NOT IN ('HABER_BASICO','BONO_ANTIGUEDAD','AFP_LABORAL','ANTICIPO_SUELDO','TOTAL_GANADO','TOTAL_DESCUENTOS','LIQUIDO_PAGABLE','NETO_PAGABLE')
        ORDER BY
          CASE tipo_concepto
            WHEN 'INGRESO' THEN 1
            WHEN 'DESCUENTO' THEN 2
            WHEN 'RETENCION' THEN 3
            WHEN 'APORTE_PATRONAL' THEN 4
            ELSE 9
          END,
          nombre
        """
    )
    personas = db.execute_query(
        """
        SELECT pp.id, pp.ci_nit, pp.nombre_completo, pp.cargo_referencia, pp.regional_referencia, pp.auxiliar_id,
               pp.banco_referencia, pp.cuenta_bancaria_referencia, pp.unidad_negocio_id,
                       pp.fecha_ingreso_referencia, pp.fecha_nacimiento, pp.nacionalidad, pp.sexo, pp.ocupacion_referencia,
                       COALESCE(pp.monto_minimo_mensual_referencia, 0) AS monto_minimo_mensual_referencia,
               un.codigo AS unidad_negocio_codigo, un.nombre AS unidad_negocio_nombre
        FROM contabilidad.planilla_persona pp
        LEFT JOIN contabilidad.unidad_negocio un ON un.id = pp.unidad_negocio_id
        WHERE pp.tipo_persona = 'COLABORADOR' AND pp.estado = 'ACTIVO'
        ORDER BY un.codigo NULLS LAST, pp.nombre_completo
        """
    )
    return {
        'monedas': [dict(x) for x in monedas],
        'conceptos': [dict(x) for x in conceptos],
        'personas': [dict(x) for x in personas],
        'meses': [{'id': m, 'nombre': n} for m, n in MESES],
        'hoy': date.today().isoformat(),
    }


def _conceptos_predefinidos(db: DatabaseManager) -> list[int]:
    rows = db.execute_query(
        """
        SELECT DISTINCT ON (dc.secuencia) dc.concepto_id, dc.secuencia
        FROM contabilidad.planilla_periodo pp
        JOIN contabilidad.planilla_detalle_concepto dc ON dc.planilla_periodo_id = pp.id
        WHERE pp.tipo_planilla = 'COLABORADORES'
          AND dc.concepto_id IS NOT NULL
        ORDER BY dc.secuencia, pp.id DESC
        """
    )
    ids = [int(r['concepto_id']) for r in rows if r.get('concepto_id')]
    if ids:
        return ids
    defaults = db.execute_query(
        """
        SELECT id
        FROM contabilidad.planilla_concepto
        WHERE activo = TRUE
          AND tipo_planilla IN ('COLABORADORES','AMBAS')
          AND codigo IN ('SERVICIO_ADICIONAL','BONO_TAREA','OTROS_INGRESOS','RETENCION_HONORARIOS','DESCUENTO_COLABORADOR','OTROS_DESCUENTOS')
        ORDER BY
          CASE codigo
            WHEN 'SERVICIO_ADICIONAL' THEN 1
            WHEN 'BONO_TAREA' THEN 2
            WHEN 'OTROS_INGRESOS' THEN 3
            WHEN 'RETENCION_HONORARIOS' THEN 4
            WHEN 'DESCUENTO_COLABORADOR' THEN 5
            WHEN 'OTROS_DESCUENTOS' THEN 6
            ELSE 99
          END
        """
    )
    return [int(r['id']) for r in defaults]


def _obtener_planilla(db: DatabaseManager, planilla_id: int) -> dict[str, Any] | None:
    rows = db.execute_query(
        """
        SELECT pp.*, m.nombre AS moneda_nombre,
               COUNT(DISTINCT pd.unidad_negocio_id) FILTER (WHERE pd.estado <> 'EXCLUIDO') AS unidades_count
        FROM contabilidad.planilla_periodo pp
        JOIN contabilidad.moneda m ON m.codigo = pp.moneda_codigo
        LEFT JOIN contabilidad.planilla_detalle pd ON pd.planilla_periodo_id = pp.id
        WHERE pp.id = %s AND pp.tipo_planilla = 'COLABORADORES'
        GROUP BY pp.id, m.nombre
        """,
        (planilla_id,)
    )
    return dict(rows[0]) if rows else None


def _conceptos_planilla(db: DatabaseManager, planilla_id: int) -> list[dict[str, Any]]:
    rows = db.execute_query(
        """
        SELECT codigo_concepto, nombre_concepto, tipo_concepto, impacto_liquido,
               MIN(secuencia) AS secuencia,
               BOOL_OR(COALESCE((atributos->>'requiere_justificativo')::boolean, false)) AS requiere_justificativo
        FROM contabilidad.planilla_detalle_concepto
        WHERE planilla_periodo_id = %s
        GROUP BY codigo_concepto, nombre_concepto, tipo_concepto, impacto_liquido
        ORDER BY MIN(secuencia), nombre_concepto
        """,
        (planilla_id,)
    )
    return [dict(r) for r in rows]


def _detalle_planilla(db: DatabaseManager, planilla_id: int) -> list[dict[str, Any]]:
    detalles = db.execute_query(
        """
        SELECT *
        FROM contabilidad.planilla_detalle
        WHERE planilla_periodo_id = %s
        ORDER BY COALESCE(unidad_negocio_codigo, 'ZZZ'), secuencia, nombre_completo
        """,
        (planilla_id,)
    )
    conceptos = db.execute_query(
        """
        SELECT *
        FROM contabilidad.planilla_detalle_concepto
        WHERE planilla_periodo_id = %s
        ORDER BY planilla_detalle_id, secuencia
        """,
        (planilla_id,)
    )
    por_detalle: dict[int, list[dict[str, Any]]] = {}
    for concepto in conceptos:
        por_detalle.setdefault(int(concepto['planilla_detalle_id']), []).append(dict(concepto))
    resultado = []
    for detalle in detalles:
        item = dict(detalle)
        item['conceptos'] = por_detalle.get(int(detalle['id']), [])
        item['conceptos_map'] = {c['codigo_concepto']: c for c in item['conceptos']}
        resultado.append(item)
    return resultado


def _cuotas_prestamos_por_persona(db: DatabaseManager, gestion: int, mes: int, moneda_codigo: str) -> dict[int, list[dict[str, Any]]]:
    try:
        rows = db.execute_query(
            """
            SELECT pc.id AS cuota_id, pc.prestamo_id, pc.numero_cuota, pc.monto_programado,
                   pc.monto_aplicado, pc.saldo_pendiente, p.persona_id, p.codigo,
                   p.tipo_operacion, p.nombre_completo
            FROM contabilidad.planilla_prestamo_cuota pc
            JOIN contabilidad.planilla_prestamo p ON p.id = pc.prestamo_id
            WHERE p.tipo_persona = 'COLABORADOR'
              AND p.moneda_codigo = %s
              AND p.estado IN ('CONFIRMADO','PARCIAL')
              AND pc.gestion = %s
              AND pc.mes = %s
              AND pc.estado IN ('PENDIENTE','PARCIAL')
              AND pc.saldo_pendiente > 0
            ORDER BY p.persona_id, pc.numero_cuota
            """,
            (moneda_codigo, gestion, mes)
        )
    except Exception:
        return {}
    data: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        data.setdefault(int(row['persona_id']), []).append(dict(row))
    return data


def _concepto_anticipo(db: DatabaseManager) -> dict[str, Any] | None:
    rows = db.execute_query(
        """
        SELECT id, codigo, nombre, tipo_concepto, impacto_liquido, metodo_calculo,
               COALESCE(monto_referencial, 0) AS monto_referencial,
               porcentaje_referencial, cuenta_debe_codigo, cuenta_haber_codigo,
               requiere_justificativo, observacion
        FROM contabilidad.planilla_concepto
        WHERE activo = TRUE
          AND tipo_planilla IN ('COLABORADORES','AMBAS')
          AND codigo = 'ANTICIPO_SUELDO'
        LIMIT 1
        """
    )
    return dict(rows[0]) if rows else None


# ============================================================
# Recalculo
# ============================================================

def _recalcular_detalle(db: DatabaseManager, detalle_id: int):
    base_row = db.execute_query(
        """
        SELECT COALESCE(monto_base, 0) AS monto_base_honorario
        FROM contabilidad.planilla_detalle
        WHERE id = %s
        """,
        (detalle_id,)
    )[0]
    row = db.execute_query(
        """
        SELECT
          COALESCE(SUM(CASE WHEN impacto_liquido = 'SUMA' THEN monto ELSE 0 END),0) AS ingresos_adicionales,
          COALESCE(SUM(CASE WHEN tipo_concepto = 'DESCUENTO' THEN monto ELSE 0 END),0) AS descuentos,
          COALESCE(SUM(CASE WHEN tipo_concepto = 'RETENCION' THEN monto ELSE 0 END),0) AS retenciones,
          COALESCE(SUM(CASE WHEN tipo_concepto = 'APORTE_PATRONAL' THEN monto ELSE 0 END),0) AS aportes
        FROM contabilidad.planilla_detalle_concepto
        WHERE planilla_detalle_id = %s
        """,
        (detalle_id,)
    )[0]
    monto_base_honorario = Decimal(str(base_row['monto_base_honorario'] or 0)).quantize(CUANTIA)
    ingresos_adicionales = Decimal(str(row['ingresos_adicionales'] or 0)).quantize(CUANTIA)
    ingresos = monto_base_honorario + ingresos_adicionales
    descuentos = Decimal(str(row['descuentos'] or 0)).quantize(CUANTIA)
    retenciones = Decimal(str(row['retenciones'] or 0)).quantize(CUANTIA)
    aportes = Decimal(str(row['aportes'] or 0)).quantize(CUANTIA)
    liquido = ingresos - descuentos - retenciones
    if liquido < 0:
        raise ValueError('El líquido pagable no puede ser negativo. Revise descuentos y retenciones.')
    db.execute_update(
        """
        UPDATE contabilidad.planilla_detalle
        SET monto_base = %s,
            otros_ingresos = %s,
            total_ganado = %s,
            descuentos_laborales = %s,
            retenciones = %s,
            otros_descuentos = 0,
            aportes_patronales = %s,
            liquido_pagable = %s,
            saldo_pendiente = GREATEST(%s - monto_pagado, 0),
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (monto_base_honorario, ingresos_adicionales, ingresos, descuentos, retenciones, aportes, liquido, liquido, detalle_id)
    )


def _recalcular_planilla(db: DatabaseManager, planilla_id: int):
    rows = db.execute_query(
        """
        SELECT
          COALESCE(SUM(total_ganado),0) AS ingresos,
          COALESCE(SUM(descuentos_laborales),0) AS descuentos,
          COALESCE(SUM(retenciones),0) AS retenciones,
          COALESCE(SUM(aportes_patronales),0) AS aportes,
          COALESCE(SUM(liquido_pagable),0) AS liquido,
          COALESCE(SUM(monto_pagado),0) AS pagado,
          COALESCE(SUM(saldo_pendiente),0) AS pendiente
        FROM contabilidad.planilla_detalle
        WHERE planilla_periodo_id = %s
          AND estado <> 'EXCLUIDO'
        """,
        (planilla_id,)
    )[0]
    db.execute_update(
        """
        UPDATE contabilidad.planilla_periodo
        SET total_ingresos = %s,
            total_descuentos = %s,
            total_retenciones = %s,
            total_aportes_patronales = %s,
            total_liquido = %s,
            total_pagado = %s,
            saldo_pendiente = %s,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            row_decimal(rows, 'ingresos'), row_decimal(rows, 'descuentos'), row_decimal(rows, 'retenciones'),
            row_decimal(rows, 'aportes'), row_decimal(rows, 'liquido'), row_decimal(rows, 'pagado'),
            row_decimal(rows, 'pendiente'), planilla_id
        )
    )


def row_decimal(row: dict[str, Any], key: str) -> Decimal:
    return Decimal(str(row.get(key) or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP)




# ============================================================
# PDF helpers
# ============================================================

class PlanillaCanvas(Canvas):
    def __init__(self, *args, report_context=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_context = report_context or {}
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, total_pages):
        page_width, _ = self._pagesize
        user = self.report_context.get('emitted_by') or 'Sistema'
        self.saveState()
        self.setFont('Helvetica', 7.2)
        self.setFillColor(MUTED)
        self.drawString(14 * mm, 9 * mm, f'Generado por: {user}')
        self.drawRightString(page_width - 14 * mm, 9 * mm, f'Página {self._pageNumber} de {total_pages}')
        self.restoreState()


class PlanillaDocTemplate(BaseDocTemplate):
    def __init__(self, *args, report_context=None, **kwargs):
        self.report_context = report_context or {}
        super().__init__(*args, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        template = PageTemplate(id='planilla', frames=[frame], onPage=self._draw_header)
        self.addPageTemplates([template])

    def _draw_header(self, canvas, doc):
        title = self.report_context.get('title') or 'Planilla'
        subtitle = self.report_context.get('subtitle') or ''
        estado = self.report_context.get('estado') or ''
        logo_file = self.report_context.get('logo_path')
        page_width, page_height = doc.pagesize
        x_left = doc.leftMargin
        x_right = page_width - doc.rightMargin
        header_top = page_height - 14 * mm

        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawString(x_left, header_top - 18, title)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 8.2)
        canvas.drawString(x_left, header_top - 33, subtitle)
        if estado:
            stamp_text = 'BORRADOR - REVISIÓN' if estado == 'BORRADOR' else estado
            stamp_w = 62 * mm if estado == 'BORRADOR' else 42 * mm
            stamp_h = 10 * mm
            stamp_x = (x_left + x_right - stamp_w) / 2
            stamp_y = header_top - 46
            canvas.saveState()
            canvas.setDash(3, 2)
            canvas.setStrokeColor(RED if estado == 'BORRADOR' else GREEN)
            canvas.setLineWidth(0.9)
            canvas.roundRect(stamp_x, stamp_y, stamp_w, stamp_h, 4, stroke=1, fill=0)
            canvas.setDash()
            canvas.setFillColor(colors.black)
            canvas.setFont('Helvetica-Bold', 7.4)
            canvas.drawCentredString(stamp_x + stamp_w / 2, stamp_y + 3.4 * mm, stamp_text)
            canvas.restoreState()
        if logo_file:
            try:
                logo = ImageReader(logo_file)
                canvas.drawImage(
                    logo, x_right - 42 * mm, header_top - 42,
                    width=42 * mm, height=14 * mm,
                    preserveAspectRatio=True, mask='auto', anchor='ne'
                )
            except Exception:
                pass
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(1)
        canvas.line(x_left, header_top - 59, x_right, header_top - 59)
        canvas.restoreState()


def _safe_text(value: Any) -> str:
    return escape(str(value if value is not None else ''))


def _money_pdf(value: Any) -> str:
    try:
        return f'{Decimal(str(value or 0)).quantize(CUANTIA, rounding=ROUND_HALF_UP):,.2f}'
    except Exception:
        return '0.00'


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DXTMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=7.6, leading=9, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTBody', parent=styles['Normal'], fontName='Helvetica', fontSize=5.9, leading=7.0, textColor=TEXT, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTBodyCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=5.9, leading=7.0, textColor=TEXT, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTBodyRight', parent=styles['Normal'], fontName='Helvetica', fontSize=5.9, leading=7.0, textColor=TEXT, alignment=TA_RIGHT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=5.8, leading=6.8, textColor=NAVY, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=NAVY, spaceAfter=4))
    styles.add(ParagraphStyle(name='DXTNotice', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=RED, alignment=TA_CENTER))
    return styles


def _p(value: Any, style):
    return Paragraph(_safe_text(value), style)


def _meta_table(meta, styles):
    data = []
    for label, value in meta:
        data.append([Paragraph(f'<b>{_safe_text(label)}</b>', styles['DXTMeta']), _p(value, styles['DXTMeta'])])
    table = Table(data, colWidths=[35 * mm, 82 * mm, 35 * mm, 82 * mm]) if len(data) and len(data[0]) == 4 else Table(data, colWidths=[35 * mm, 115 * mm])
    table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('BACKGROUND', (0, 0), (0, -1), HEAD_FILL),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return table


def _pdf_table(data, col_widths, repeat_header=True, header_rows=1):
    table = Table(data, colWidths=col_widths, repeatRows=header_rows if repeat_header else 0)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, header_rows - 1), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), NAVY),
        ('FONTNAME', (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, header_rows - 1), 5.8),
        ('GRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2.2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2.2),
        ('TOPPADDING', (0, 0), (-1, -1), 2.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
    ])
    for idx in range(header_rows, len(data)):
        row_marker = data[idx][0]
        if isinstance(row_marker, Paragraph) and 'UNIDAD:' in getattr(row_marker, 'text', ''):
            style.add('SPAN', (0, idx), (-1, idx))
            style.add('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#eef6ff'))
            style.add('FONTNAME', (0, idx), (-1, idx), 'Helvetica-Bold')
            style.add('TEXTCOLOR', (0, idx), (-1, idx), NAVY)
        elif idx % 2 == 0:
            style.add('BACKGROUND', (0, idx), (-1, idx), ROW_ALT)
    table.setStyle(style)
    return table


def _pdf_response(story, filename, title, subtitle='', estado=''):
    buffer = io.BytesIO()
    context = {
        'title': title,
        'subtitle': subtitle,
        'estado': estado,
        'logo_path': logo_path(),
        'emitted_by': usuario_actual(),
    }
    doc = PlanillaDocTemplate(
        buffer,
        pagesize=landscape(OFICIO),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=34 * mm,
        bottomMargin=15 * mm,
        report_context=context,
    )
    doc.build(story, canvasmaker=lambda *args, **kwargs: PlanillaCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{filename}"'},
    )


def _build_planilla_pdf_story(planilla: dict[str, Any], conceptos: list[dict[str, Any]], detalles: list[dict[str, Any]]):
    styles = _pdf_styles()
    story = []
    if planilla.get('estado') == 'BORRADOR':
        story.append(Paragraph('DOCUMENTO EN BORRADOR - NO VÁLIDO PARA PAGO NI CONTABILIDAD DEFINITIVA', styles['DXTNotice']))
        story.append(Spacer(1, 4 * mm))
    meta = [
        ('Código', planilla.get('codigo')),
        ('Periodo', f'{_mes_nombre(planilla.get("mes"))} {planilla.get("gestion")}'),
        ('Fecha', planilla.get('fecha_planilla')),
        ('Estado', planilla.get('estado')),
        ('Moneda', planilla.get('moneda_codigo')),
        ('Unidades', planilla.get('unidades_count') or 0),
        ('Glosa', planilla.get('glosa') or ''),
        ('Asiento', planilla.get('asiento_devengamiento_id') or 'Pendiente'),
    ]
    # two-column meta table
    rows = []
    for i in range(0, len(meta), 2):
        left = meta[i]
        right = meta[i + 1] if i + 1 < len(meta) else ('', '')
        rows.append([_p(f'<b>{left[0]}</b>', styles['DXTMeta']), _p(left[1], styles['DXTMeta']), _p(f'<b>{right[0]}</b>', styles['DXTMeta']), _p(right[1], styles['DXTMeta'])])
    table = Table(rows, colWidths=[24 * mm, 100 * mm, 24 * mm, 100 * mm])
    table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, BORDER),
        ('BACKGROUND', (0, 0), (0, -1), HEAD_FILL),
        ('BACKGROUND', (2, 0), (2, -1), HEAD_FILL),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    headers = ['#', 'CI/NIT', 'Colaborador', 'Servicio', 'Resp.', 'Factura', 'Monto base']
    for c in conceptos:
        headers.append(c.get('nombre_concepto') or c.get('codigo_concepto'))
    headers += ['Total ganado', 'Desc.', 'Ret.', 'Líquido']
    data = [[_p(h, styles['DXTHeader']) for h in headers]]

    unidad_actual = None
    n = 0
    total_ganado = Decimal('0.00')
    total_desc = Decimal('0.00')
    total_ret = Decimal('0.00')
    total_liq = Decimal('0.00')
    totales_unidad: dict[str, dict[str, Decimal]] = {}

    for d in detalles:
        if d.get('estado') == 'EXCLUIDO':
            continue
        unidad_label = f"{d.get('unidad_negocio_codigo') or 'S/U'} · {d.get('unidad_negocio_nombre') or 'Sin unidad'}"
        if unidad_label != unidad_actual:
            unidad_actual = unidad_label
            data.append([_p(f'UNIDAD: {unidad_label}', styles['DXTBody'])] + [''] * (len(headers) - 1))
        n += 1
        row = [
            _p(n, styles['DXTBodyCenter']),
            _p(d.get('ci_nit') or '', styles['DXTBody']),
            _p(d.get('nombre_completo') or '', styles['DXTBody']),
            _p(d.get('descripcion_servicio') or d.get('ocupacion_referencia') or d.get('cargo_referencia') or '', styles['DXTBody']),
            _p(d.get('tipo_respaldo') or '', styles['DXTBodyCenter']),
            _p(d.get('numero_factura') or '-', styles['DXTBody']),
            _p(_money_pdf(d.get('monto_base')), styles['DXTBodyRight']),
        ]
        for c in conceptos:
            item = (d.get('conceptos_map') or {}).get(c.get('codigo_concepto'))
            row.append(_p(_money_pdf(item.get('monto') if item else 0), styles['DXTBodyRight']))
        row += [
            _p(_money_pdf(d.get('total_ganado')), styles['DXTBodyRight']),
            _p(_money_pdf(d.get('descuentos_laborales')), styles['DXTBodyRight']),
            _p(_money_pdf(d.get('retenciones')), styles['DXTBodyRight']),
            _p(_money_pdf(d.get('liquido_pagable')), styles['DXTBodyRight']),
        ]
        data.append(row)
        total_ganado += Decimal(str(d.get('total_ganado') or 0)).quantize(CUANTIA)
        total_desc += Decimal(str(d.get('descuentos_laborales') or 0)).quantize(CUANTIA)
        total_ret += Decimal(str(d.get('retenciones') or 0)).quantize(CUANTIA)
        total_liq += Decimal(str(d.get('liquido_pagable') or 0)).quantize(CUANTIA)
        t = totales_unidad.setdefault(unidad_label, {'ganado': Decimal('0.00'), 'desc': Decimal('0.00'), 'ret': Decimal('0.00'), 'liq': Decimal('0.00')})
        t['ganado'] += Decimal(str(d.get('total_ganado') or 0)).quantize(CUANTIA)
        t['desc'] += Decimal(str(d.get('descuentos_laborales') or 0)).quantize(CUANTIA)
        t['ret'] += Decimal(str(d.get('retenciones') or 0)).quantize(CUANTIA)
        t['liq'] += Decimal(str(d.get('liquido_pagable') or 0)).quantize(CUANTIA)

    col_count = len(headers)
    fixed_widths = [8 * mm, 17 * mm, 37 * mm, 28 * mm, 11 * mm, 12 * mm, 18 * mm]
    end_widths = [20 * mm, 16 * mm, 16 * mm, 20 * mm]
    available = 306 * mm - sum(fixed_widths) - sum(end_widths)
    concept_width = min(23 * mm, available / max(len(conceptos), 1)) if conceptos else 0
    col_widths = fixed_widths + [concept_width] * len(conceptos) + end_widths
    story.append(_pdf_table(data, col_widths, repeat_header=True))
    story.append(Spacer(1, 4 * mm))

    summary_data = [[_p('Unidad', styles['DXTHeader']), _p('Total ganado', styles['DXTHeader']), _p('Descuentos', styles['DXTHeader']), _p('Retenciones', styles['DXTHeader']), _p('Líquido', styles['DXTHeader'])]]
    for unidad, vals in totales_unidad.items():
        summary_data.append([_p(unidad, styles['DXTBody']), _p(_money_pdf(vals['ganado']), styles['DXTBodyRight']), _p(_money_pdf(vals['desc']), styles['DXTBodyRight']), _p(_money_pdf(vals['ret']), styles['DXTBodyRight']), _p(_money_pdf(vals['liq']), styles['DXTBodyRight'])])
    summary_data.append([_p('TOTAL GENERAL', styles['DXTBody']), _p(_money_pdf(total_ganado), styles['DXTBodyRight']), _p(_money_pdf(total_desc), styles['DXTBodyRight']), _p(_money_pdf(total_ret), styles['DXTBodyRight']), _p(_money_pdf(total_liq), styles['DXTBodyRight'])])
    summary = _pdf_table(summary_data, [82 * mm, 28 * mm, 28 * mm, 28 * mm, 30 * mm])
    story.append(KeepTogether([Paragraph('Resumen por unidad de negocio', styles['DXTSection']), summary]))
    story.append(Spacer(1, 8 * mm))
    firmas = Table([
        ['Elaborado por', 'Revisado por', 'Aprobado por'],
        ['', '', ''],
        ['Nombre / Firma', 'Nombre / Firma', 'Nombre / Firma'],
    ], colWidths=[65 * mm, 65 * mm, 65 * mm])
    firmas.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, 2), (-1, 2), 0.5, TEXT),
        ('TOPPADDING', (0, 1), (-1, 1), 22),
    ]))
    story.append(firmas)
    return story


# ============================================================
# Rutas
# ============================================================

@planilla_honorarios_colaboradores_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    error = None
    stats = {'total': 0, 'borradores': 0, 'consolidadas': 0, 'pagadas': 0, 'liquido': 0, 'pendiente': 0}
    try:
        with DatabaseManager() as db:
            _assert_tables_ready(db)
            stats = _stats(db)
    except Exception as exc:
        error = 'No se pudo cargar la pantalla de planillas. Revise la configuración operativa del módulo.'
    return render_template(
        'planilla_honorarios_colaboradores_index.html',
        stats=stats,
        error=error,
        puede_editar=_puede_editar(),
        meses=MESES,
    )


@planilla_honorarios_colaboradores_bp.route('/ayuda')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('planilla_honorarios_colaboradores_help.html')


@planilla_honorarios_colaboradores_bp.route('/opciones')
@login_required
@roles_required(ROLES_LECTURA)
def opciones():
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        catalogos = _catalogos(db)
        catalogos['conceptos_predefinidos'] = _conceptos_predefinidos(db)
    return _json_ok(**catalogos)


@planilla_honorarios_colaboradores_bp.route('/listar')
@login_required
@roles_required(ROLES_LECTURA)
def listar():
    estado = _upper(request.args.get('estado'))
    gestion = _int_value(request.args.get('gestion'), 'Gestión', required=False)
    mes = _int_value(request.args.get('mes'), 'Mes', required=False)
    q = _clean(request.args.get('q'))
    filtros = ["pp.tipo_planilla = 'COLABORADORES'"]
    params: list[Any] = []
    if estado in ESTADOS_PERIODO:
        filtros.append('pp.estado = %s')
        params.append(estado)
    if gestion:
        filtros.append('pp.gestion = %s')
        params.append(gestion)
    if mes:
        filtros.append('pp.mes = %s')
        params.append(mes)
    if q:
        filtros.append(
            "(pp.codigo ILIKE %s OR COALESCE(pp.glosa,'') ILIKE %s OR EXISTS ("
            "SELECT 1 FROM contabilidad.planilla_detalle pd2 "
            "WHERE pd2.planilla_periodo_id = pp.id "
            "AND (COALESCE(pd2.unidad_negocio_codigo,'') ILIKE %s OR COALESCE(pd2.unidad_negocio_nombre,'') ILIKE %s)))"
        )
        like = f'%{q}%'
        params.extend([like, like, like, like])
    where = ' AND '.join(filtros)
    with DatabaseManager() as db:
        rows = db.execute_query(
            f"""
            SELECT pp.id, pp.codigo, pp.gestion, pp.mes, pp.fecha_planilla, pp.estado,
                   pp.moneda_codigo, pp.total_ingresos, pp.total_descuentos,
                   pp.total_retenciones, pp.total_aportes_patronales, pp.total_liquido,
                   pp.saldo_pendiente, pp.glosa, pp.creado_en, pp.asiento_devengamiento_id, pp.asiento_anulacion_id,
                   COUNT(pd.id) AS personas,
                   COUNT(DISTINCT pd.unidad_negocio_id) FILTER (WHERE pd.estado <> 'EXCLUIDO') AS unidades_count,
                   STRING_AGG(DISTINCT COALESCE(pd.unidad_negocio_codigo, 'S/U'), ', ' ORDER BY COALESCE(pd.unidad_negocio_codigo, 'S/U')) AS unidades_resumen
            FROM contabilidad.planilla_periodo pp
            LEFT JOIN contabilidad.planilla_detalle pd ON pd.planilla_periodo_id = pp.id AND pd.estado <> 'EXCLUIDO'
            WHERE {where}
            GROUP BY pp.id
            ORDER BY pp.gestion DESC, pp.mes DESC, pp.id DESC
            LIMIT 300
            """,
            tuple(params)
        )
    return _json_ok(planillas=[dict(r) for r in rows])


@planilla_honorarios_colaboradores_bp.route('/generar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def generar():
    data = request.get_json(silent=True) or {}
    try:
        gestion = _int_value(data.get('gestion'), 'Gestión')
        mes = _int_value(data.get('mes'), 'Mes')
        if mes < 1 or mes > 12:
            raise ValueError('El mes no es válido.')
        moneda = _upper(data.get('moneda_codigo') or 'BOB')
        tipo_cambio = _decimal(data.get('tipo_cambio') or 1, 'Tipo de cambio', allow_zero=False)
        fecha_planilla = _parse_date(data.get('fecha_planilla'), 'Fecha planilla')
        tipo_respaldo_default = _upper(data.get('tipo_respaldo_default') or 'SIN_FACTURA')
        if tipo_respaldo_default not in ('FACTURA', 'SIN_FACTURA'):
            raise ValueError('El respaldo predeterminado no es válido.')
        glosa = _limit_text(data.get('glosa') or f'Planilla de honorarios colaboradores - {_mes_nombre(mes)} {gestion}', 'Glosa', 500, required=True)
        observacion = _limit_text(data.get('observacion'), 'Observación', 800)
        concepto_ids = data.get('conceptos') or []
        if not isinstance(concepto_ids, list):
            raise ValueError('La selección de conceptos no es válida.')
        concepto_ids = [int(x) for x in concepto_ids if str(x).isdigit()]
        if len(concepto_ids) != len(set(concepto_ids)):
            raise ValueError('La selección de conceptos contiene duplicados.')

        with DatabaseManager() as db:
            _assert_tables_ready(db)
            assert_gestion_abierta(db, gestion, 'generar la planilla')
            existentes = db.execute_query(
                """
                SELECT id, codigo
                FROM contabilidad.planilla_periodo
                WHERE tipo_planilla = 'COLABORADORES'
                  AND gestion = %s
                  AND mes = %s
                  AND estado <> 'ANULADA'
                LIMIT 1
                """,
                (gestion, mes)
            )
            if existentes:
                return _json_error(f'Ya existe una planilla de honorarios para ese mes: {existentes[0]["codigo"]}.')

            sin_unidad = db.execute_query(
                """
                SELECT nombre_completo, ci_nit
                FROM contabilidad.planilla_persona
                WHERE tipo_persona = 'COLABORADOR'
                  AND estado = 'ACTIVO'
                  AND unidad_negocio_id IS NULL
                ORDER BY nombre_completo
                LIMIT 8
                """
            )
            if sin_unidad:
                nombres = ', '.join([f"{r['nombre_completo']} ({r['ci_nit']})" for r in sin_unidad])
                return _json_error('Existen colaboradores activos sin unidad de negocio asignada: ' + nombres)

            sin_minimo = db.execute_query(
                """
                SELECT nombre_completo, ci_nit
                FROM contabilidad.planilla_persona
                WHERE tipo_persona = 'COLABORADOR'
                  AND estado = 'ACTIVO'
                  AND COALESCE(monto_minimo_mensual_referencia, 0) <= 0
                ORDER BY nombre_completo
                LIMIT 8
                """
            )
            if sin_minimo:
                nombres = ', '.join([f"{r['nombre_completo']} ({r['ci_nit']})" for r in sin_minimo])
                return _json_error('Existen colaboradores activos sin mínimo mensual referencial: ' + nombres)

            personas = db.execute_query(
                """
                SELECT pp.id, pp.ci_nit, pp.nit_referencia, pp.nombre_completo, pp.cargo_referencia, pp.regional_referencia, pp.auxiliar_id,
                       pp.banco_referencia, pp.cuenta_bancaria_referencia, pp.unidad_negocio_id,
                       pp.ocupacion_referencia, COALESCE(pp.monto_minimo_mensual_referencia, 0) AS monto_minimo_mensual_referencia,
                       un.codigo AS unidad_negocio_codigo, un.nombre AS unidad_negocio_nombre
                FROM contabilidad.planilla_persona pp
                JOIN contabilidad.unidad_negocio un ON un.id = pp.unidad_negocio_id
                WHERE pp.tipo_persona = 'COLABORADOR' AND pp.estado = 'ACTIVO'
                ORDER BY un.codigo, pp.nombre_completo
                """
            )
            if not personas:
                return _json_error('No existen colaboradores activos para generar la planilla.')

            conceptos_ordenados = []
            if concepto_ids:
                placeholders = ','.join(['%s'] * len(concepto_ids))
                conceptos = db.execute_query(
                    f"""
                    SELECT *
                    FROM contabilidad.planilla_concepto
                    WHERE id IN ({placeholders})
                      AND activo = TRUE
                      AND tipo_planilla IN ('COLABORADORES','AMBAS')
                      AND codigo NOT IN ('HABER_BASICO','BONO_ANTIGUEDAD','AFP_LABORAL','ANTICIPO_SUELDO','ANTICIPO_PRESTAMO','TOTAL_GANADO','TOTAL_DESCUENTOS','LIQUIDO_PAGABLE','NETO_PAGABLE')
                    """,
                    tuple(concepto_ids)
                )
                conceptos_by_id = {int(c['id']): dict(c) for c in conceptos}
                for cid in concepto_ids:
                    if cid not in conceptos_by_id:
                        raise ValueError('Uno de los conceptos seleccionados no está activo o no aplica a colaboradores.')
                    conceptos_ordenados.append(conceptos_by_id[cid])

            _parametros_gestion(db, gestion)
            cuotas_por_persona = _cuotas_prestamos_por_persona(db, gestion, mes, moneda)

            codigo = _codigo_planilla(db, gestion, mes)
            planilla_id = db.execute_insert(
                """
                INSERT INTO contabilidad.planilla_periodo (
                    codigo, tipo_planilla, gestion, mes, unidad_negocio_id, moneda_codigo,
                    tipo_cambio, fecha_planilla, estado, glosa, observacion, creado_por, creado_en
                ) VALUES (%s, 'COLABORADORES', %s, %s, NULL, %s, %s, %s, 'BORRADOR', %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (codigo, gestion, mes, moneda, tipo_cambio, fecha_planilla, glosa, observacion, _usuario_actual())
            )

            for idx, persona in enumerate(personas, start=1):
                monto_base = Decimal(str(persona.get('monto_minimo_mensual_referencia') or 0)).quantize(CUANTIA)
                atributos = {
                    'banco_referencia': persona.get('banco_referencia'),
                    'cuenta_bancaria_referencia': persona.get('cuenta_bancaria_referencia'),
                    'nit_referencia': persona.get('nit_referencia'),
                }
                detalle_id = db.execute_insert(
                    """
                    INSERT INTO contabilidad.planilla_detalle (
                        planilla_periodo_id, persona_id, secuencia, tipo_persona, ci_nit,
                        nombre_completo, cargo_referencia, regional_referencia, auxiliar_id,
                        unidad_negocio_id, unidad_negocio_codigo, unidad_negocio_nombre,
                        ocupacion_referencia, tipo_respaldo, cantidad, precio_unitario, dias_trabajados, monto_base,
                        descripcion_servicio, nit_factura, estado, observacion, atributos, creado_en
                    ) VALUES (%s, %s, %s, 'COLABORADOR', %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, 1, %s, NULL, %s,
                              %s, %s, 'PENDIENTE', NULL, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    (
                        planilla_id, persona['id'], idx, persona['ci_nit'], persona['nombre_completo'],
                        persona.get('cargo_referencia'), persona.get('regional_referencia'), persona.get('auxiliar_id'),
                        persona.get('unidad_negocio_id'), persona.get('unidad_negocio_codigo'), persona.get('unidad_negocio_nombre'),
                        persona.get('ocupacion_referencia') or persona.get('cargo_referencia'), tipo_respaldo_default,
                        monto_base, monto_base, persona.get('ocupacion_referencia') or persona.get('cargo_referencia') or 'Honorarios / servicios',
                        persona.get('nit_referencia'), Json(atributos)
                    )
                )

                cuotas = cuotas_por_persona.get(int(persona['id']), [])
                monto_cuotas = sum((Decimal(str(c['saldo_pendiente'] or 0)) for c in cuotas), Decimal('0.00')).quantize(CUANTIA, rounding=ROUND_HALF_UP)
                secuencia_actual = 1
                if monto_cuotas > 0:
                    db.execute_insert(
                        """
                        INSERT INTO contabilidad.planilla_detalle_concepto (
                            planilla_periodo_id, planilla_detalle_id, concepto_id, secuencia,
                            codigo_concepto, nombre_concepto, tipo_concepto, impacto_liquido,
                            monto, porcentaje_aplicado, cuenta_debe_codigo, cuenta_haber_codigo,
                            justificativo, observacion, atributos, creado_en
                        ) VALUES (%s, %s, NULL, %s, 'ANTICIPO_PRESTAMO', 'Anticipos / préstamos programados', 'DESCUENTO', 'RESTA', %s, NULL, NULL, NULL, %s, NULL, %s, CURRENT_TIMESTAMP)
                        """,
                        (
                            planilla_id, detalle_id, secuencia_actual, monto_cuotas,
                            'Descuento automático por anticipos/préstamos programados para la planilla.',
                            Json({'origen': 'ANTICIPO_PRESTAMO_PROGRAMADO', 'prestamo_cuotas': [
                                {'cuota_id': int(c['cuota_id']), 'prestamo_id': int(c['prestamo_id']), 'codigo': c['codigo'], 'numero_cuota': int(c['numero_cuota']), 'monto': str(Decimal(str(c['saldo_pendiente'] or 0)).quantize(CUANTIA))} for c in cuotas
                            ]})
                        ),
                        return_id=True,
                    )
                    secuencia_actual += 1

                for sec, concepto in enumerate(conceptos_ordenados, start=secuencia_actual):
                    monto = Decimal('0.00')
                    if concepto.get('metodo_calculo') == 'FIJO' and concepto.get('monto_referencial') is not None:
                        monto = Decimal(str(concepto.get('monto_referencial') or 0)).quantize(CUANTIA)
                    db.execute_insert(
                        """
                        INSERT INTO contabilidad.planilla_detalle_concepto (
                            planilla_periodo_id, planilla_detalle_id, concepto_id, secuencia,
                            codigo_concepto, nombre_concepto, tipo_concepto, impacto_liquido,
                            monto, porcentaje_aplicado, cuenta_debe_codigo, cuenta_haber_codigo,
                            justificativo, observacion, atributos, creado_en
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, CURRENT_TIMESTAMP)
                        """,
                        (
                            planilla_id, detalle_id, concepto.get('id'), sec, concepto.get('codigo'), concepto.get('nombre'),
                            concepto.get('tipo_concepto'), concepto.get('impacto_liquido'), monto,
                            concepto.get('porcentaje_referencial'), concepto.get('cuenta_debe_codigo'), concepto.get('cuenta_haber_codigo'),
                            concepto.get('observacion'), Json({'requiere_justificativo': bool(concepto.get('requiere_justificativo')), 'metodo_calculo': concepto.get('metodo_calculo'), 'origen': 'CONCEPTO_BASE'})
                        ),
                        return_id=False
                    )
                _recalcular_detalle(db, detalle_id)

            _recalcular_planilla(db, planilla_id)
        return _json_ok('Planilla de honorarios generada en borrador.', redirect=url_for('planilla_honorarios_colaboradores.detalle', planilla_id=planilla_id))
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(mensaje_error_operacion('generar la planilla'), 500)


@planilla_honorarios_colaboradores_bp.route('/<int:planilla_id>')
@login_required
@roles_required(ROLES_LECTURA)
def detalle(planilla_id: int):
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        planilla = _obtener_planilla(db, planilla_id)
        if not planilla:
            return redirect(url_for('planilla_honorarios_colaboradores.index'))
        conceptos = _conceptos_planilla(db, planilla_id)
        detalles = _detalle_planilla(db, planilla_id)
    return render_template(
        'planilla_honorarios_colaboradores_detalle.html',
        planilla=planilla,
        conceptos=conceptos,
        detalles=detalles,
        meses=dict(MESES),
        puede_editar=_puede_editar(),
    )




@planilla_honorarios_colaboradores_bp.route('/<int:planilla_id>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_planilla(planilla_id: int):
    with DatabaseManager() as db:
        _assert_tables_ready(db)
        planilla = _obtener_planilla(db, planilla_id)
        if not planilla:
            return redirect(url_for('planilla_honorarios_colaboradores.index'))
        conceptos = _conceptos_planilla(db, planilla_id)
        detalles = _detalle_planilla(db, planilla_id)
    title = 'Planilla de Honorarios - Colaboradores'
    subtitle = f'{planilla.get("codigo")} · {_mes_nombre(planilla.get("mes"))} {planilla.get("gestion")} · {planilla.get("moneda_codigo")}'
    filename = f'planilla_honorarios_colaboradores_{planilla.get("codigo")}.pdf'.replace(' ', '_')
    story = _build_planilla_pdf_story(planilla, conceptos, detalles)
    return _pdf_response(story, filename, title, subtitle, planilla.get('estado'))


@planilla_honorarios_colaboradores_bp.route('/api/<int:planilla_id>/fila/<int:detalle_id>', methods=['GET'])
@login_required
@roles_required(ROLES_LECTURA)
def fila(planilla_id: int, detalle_id: int):
    with DatabaseManager() as db:
        detalle_rows = db.execute_query(
            """
            SELECT pd.*, pp.estado AS planilla_estado
            FROM contabilidad.planilla_detalle pd
            JOIN contabilidad.planilla_periodo pp ON pp.id = pd.planilla_periodo_id
            WHERE pd.id = %s AND pd.planilla_periodo_id = %s AND pp.tipo_planilla = 'COLABORADORES'
            """,
            (detalle_id, planilla_id)
        )
        if not detalle_rows:
            return _json_error('La fila de planilla no existe.', 404)
        conceptos = db.execute_query(
            """
            SELECT id, codigo_concepto, nombre_concepto, tipo_concepto, impacto_liquido,
                   monto, justificativo, observacion, atributos, secuencia
            FROM contabilidad.planilla_detalle_concepto
            WHERE planilla_detalle_id = %s
            ORDER BY secuencia
            """,
            (detalle_id,)
        )
    return _json_ok(detalle=dict(detalle_rows[0]), conceptos=[dict(c) for c in conceptos])


@planilla_honorarios_colaboradores_bp.route('/api/<int:planilla_id>/fila/<int:detalle_id>', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def guardar_fila(planilla_id: int, detalle_id: int):
    data = request.get_json(silent=True) or {}
    try:
        conceptos_payload = data.get('conceptos') or []
        monto_base = _decimal(data.get('monto_base'), 'Monto base', allow_zero=True)
        cantidad = _decimal(data.get('cantidad') or 1, 'Cantidad', allow_zero=False)
        tipo_respaldo = _upper(data.get('tipo_respaldo') or 'SIN_FACTURA')
        if tipo_respaldo not in ('FACTURA', 'SIN_FACTURA'):
            raise ValueError('El tipo de respaldo no es válido.')
        numero_factura = _limit_text(data.get('numero_factura'), 'Número de factura', 80)
        nit_factura = _limit_text(data.get('nit_factura'), 'NIT factura', 50)
        fecha_factura = _parse_date(data.get('fecha_factura'), 'Fecha factura', required=False)
        descripcion_servicio = _limit_text(data.get('descripcion_servicio'), 'Servicio / tarea', 500)
        observacion = _limit_text(data.get('observacion'), 'Observación', 800)
        if not isinstance(conceptos_payload, list):
            raise ValueError('Los conceptos de la fila no son válidos.')
        if tipo_respaldo == 'FACTURA' and not numero_factura:
            raise ValueError('Ingrese el número de factura o cambie el respaldo a SIN FACTURA.')
        with DatabaseManager() as db:
            rows = db.execute_query(
                """
                SELECT pd.id, pp.estado AS planilla_estado
                FROM contabilidad.planilla_detalle pd
                JOIN contabilidad.planilla_periodo pp ON pp.id = pd.planilla_periodo_id
                WHERE pd.id = %s AND pd.planilla_periodo_id = %s AND pp.tipo_planilla = 'COLABORADORES'
                """,
                (detalle_id, planilla_id)
            )
            if not rows:
                return _json_error('La fila de planilla no existe.', 404)
            if rows[0]['planilla_estado'] != 'BORRADOR':
                return _json_error('Solo se puede editar una planilla en BORRADOR.')
            for item in conceptos_payload:
                concepto_id = _int_value(item.get('id'), 'Concepto')
                monto = _decimal(item.get('monto'), 'Monto', allow_zero=True)
                justificativo = _limit_text(item.get('justificativo'), 'Justificativo', 800)
                db.execute_update(
                    """
                    UPDATE contabilidad.planilla_detalle_concepto
                    SET monto = %s,
                        justificativo = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s AND planilla_detalle_id = %s
                    """,
                    (monto, justificativo, concepto_id, detalle_id)
                )
            db.execute_update(
                """
                UPDATE contabilidad.planilla_detalle
                SET tipo_respaldo = %s,
                    numero_factura = %s,
                    nit_factura = %s,
                    fecha_factura = %s,
                    descripcion_servicio = %s,
                    cantidad = %s,
                    precio_unitario = %s,
                    monto_base = %s,
                    haber_basico = 0,
                    observacion = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (tipo_respaldo, numero_factura, nit_factura, fecha_factura, descripcion_servicio, cantidad, monto_base, monto_base, observacion, detalle_id)
            )
            _recalcular_detalle(db, detalle_id)
            _recalcular_planilla(db, planilla_id)
        return _json_ok('Fila actualizada correctamente.')
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(mensaje_error_operacion('guardar la fila'), 500)


@planilla_honorarios_colaboradores_bp.route('/api/<int:planilla_id>/fila/<int:detalle_id>/excluir', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def excluir_fila(planilla_id: int, detalle_id: int):
    try:
        with DatabaseManager() as db:
            rows = db.execute_query(
                """
                SELECT pp.estado
                FROM contabilidad.planilla_detalle pd
                JOIN contabilidad.planilla_periodo pp ON pp.id = pd.planilla_periodo_id
                WHERE pd.id = %s AND pd.planilla_periodo_id = %s AND pp.tipo_planilla = 'COLABORADORES'
                """,
                (detalle_id, planilla_id)
            )
            if not rows:
                return _json_error('La fila de planilla no existe.', 404)
            if rows[0]['estado'] != 'BORRADOR':
                return _json_error('Solo se puede excluir una fila en planilla BORRADOR.')
            db.execute_update(
                """
                UPDATE contabilidad.planilla_detalle
                SET estado = 'EXCLUIDO', actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (detalle_id,)
            )
            _recalcular_planilla(db, planilla_id)
        return _json_ok('Fila excluida de la planilla.')
    except Exception as exc:
        return _json_error(mensaje_error_operacion('excluir la fila'), 500)


@planilla_honorarios_colaboradores_bp.route('/api/<int:planilla_id>/consolidar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def consolidar(planilla_id: int):
    data = request.get_json(silent=True) or {}
    try:
        justificativo = _limit_text(data.get('justificativo'), 'Justificativo', 800, required=True)
        with DatabaseManager() as db:
            planilla = _obtener_planilla(db, planilla_id)
            if not planilla:
                return _json_error('La planilla no existe.', 404)
            assert_gestion_abierta(db, int(planilla['gestion']), 'consolidar la planilla')
            if planilla['estado'] != 'BORRADOR':
                return _json_error('Solo se puede consolidar una planilla en BORRADOR.')
            detalles = db.execute_query(
                """
                SELECT id, nombre_completo, liquido_pagable
                FROM contabilidad.planilla_detalle
                WHERE planilla_periodo_id = %s AND estado <> 'EXCLUIDO'
                """,
                (planilla_id,)
            )
            if not detalles:
                return _json_error('La planilla no tiene filas activas.')
            for d in detalles:
                if Decimal(str(d['liquido_pagable'] or 0)) < 0:
                    return _json_error(f'La fila de {d["nombre_completo"]} tiene líquido negativo.')

            parametros = _parametros_gestion(db, int(planilla['gestion']))
            _validar_parametros_contables(db, planilla_id, parametros)
            _aplicar_cuotas_prestamo_planilla(db, planilla_id, planilla)
            asientos = _crear_asientos_devengamiento(db, planilla_id, planilla, parametros, justificativo)
            asiento_principal = asientos[0] if asientos else None
            db.execute_update(
                """
                UPDATE contabilidad.planilla_periodo
                SET estado = 'CONSOLIDADA',
                    fecha_consolidacion = CURRENT_DATE,
                    fecha_contabilizacion = CURRENT_DATE,
                    consolidado_por = %s,
                    contabilizado_por = %s,
                    asiento_devengamiento_id = %s,
                    observacion = COALESCE(observacion || E'\n', '') || %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (_usuario_actual(), _usuario_actual(), asiento_principal, f'Consolidación/devengamiento: {justificativo}', planilla_id)
            )
        return _json_ok('Planilla consolidada y devengada contablemente.')
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(mensaje_error_operacion('consolidar la planilla'), 500)


@planilla_honorarios_colaboradores_bp.route('/api/<int:planilla_id>/revertir', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def revertir(planilla_id: int):
    data = request.get_json(silent=True) or {}
    try:
        justificativo = _limit_text(data.get('justificativo'), 'Justificativo', 800, required=True)
        with DatabaseManager() as db:
            planilla = _obtener_planilla(db, planilla_id)
            if not planilla:
                return _json_error('La planilla no existe.', 404)
            assert_gestion_abierta(db, int(planilla['gestion']), 'revertir la planilla')
            if planilla['estado'] != 'CONSOLIDADA':
                return _json_error('Solo se puede revertir una planilla CONSOLIDADA.')
            if _planilla_tiene_pagos(db, planilla_id):
                return _json_error('No se puede revertir una planilla con pagos registrados.')
            _crear_asientos_reversion(db, planilla_id, planilla, justificativo)
            _revertir_cuotas_prestamo_planilla(db, planilla_id)
            db.execute_update(
                """
                UPDATE contabilidad.planilla_periodo
                SET estado = 'BORRADOR',
                    fecha_consolidacion = NULL,
                    fecha_contabilizacion = NULL,
                    consolidado_por = NULL,
                    contabilizado_por = NULL,
                    asiento_devengamiento_id = NULL,
                    observacion = COALESCE(observacion || E'\n', '') || %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (f'Reversión a BORRADOR: {justificativo}', planilla_id)
            )
        return _json_ok('Planilla revertida a BORRADOR. El asiento de devengamiento fue reversado si correspondía.')
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(mensaje_error_operacion('revertir la planilla'), 500)


@planilla_honorarios_colaboradores_bp.route('/api/<int:planilla_id>/eliminar', methods=['POST'])
@login_required
@roles_required(ROLES_EDICION)
def eliminar(planilla_id: int):
    data = request.get_json(silent=True) or {}
    try:
        justificativo = _limit_text(data.get('justificativo'), 'Justificativo', 800, required=True)
        with DatabaseManager() as db:
            planilla = _obtener_planilla(db, planilla_id)
            if not planilla:
                return _json_error('La planilla no existe.', 404)
            assert_gestion_abierta(db, int(planilla['gestion']), 'eliminar la planilla')
            if planilla['estado'] != 'BORRADOR':
                return _json_error('Solo se puede eliminar una planilla en BORRADOR.')
            if _planilla_tiene_pagos(db, planilla_id):
                return _json_error('No se puede eliminar una planilla con pagos registrados.')
            if _planilla_tiene_aplicaciones_prestamo(db, planilla_id):
                return _json_error('La planilla tiene aplicaciones de anticipos/préstamos. No corresponde eliminarla directamente.')
            eliminados = db.execute_delete("DELETE FROM contabilidad.planilla_periodo WHERE id = %s AND tipo_planilla = 'COLABORADORES'", (planilla_id,))
            if eliminados != 1:
                return _json_error('La planilla no pudo ser eliminada porque no cumple las condiciones operativas.', 409)
        return _json_ok('Planilla eliminada correctamente.', redirect=url_for('planilla_honorarios_colaboradores.index'))
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(mensaje_error_operacion('eliminar la planilla'), 500)


def _aplicar_cuotas_prestamo_planilla(db: DatabaseManager, planilla_id: int, planilla: dict[str, Any]):
    conceptos = db.execute_query(
        """
        SELECT dc.id, dc.planilla_detalle_id, dc.monto, dc.atributos, pd.persona_id
        FROM contabilidad.planilla_detalle_concepto dc
        JOIN contabilidad.planilla_detalle pd ON pd.id = dc.planilla_detalle_id
        WHERE dc.planilla_periodo_id = %s
          AND dc.codigo_concepto = 'ANTICIPO_PRESTAMO'
          AND dc.monto > 0
          AND COALESCE(dc.atributos->>'origen','') = 'ANTICIPO_PRESTAMO_PROGRAMADO'
        """,
        (planilla_id,)
    )
    for concepto in conceptos:
        monto_disponible = Decimal(str(concepto['monto'] or 0)).quantize(CUANTIA)
        atributos = concepto.get('atributos') or {}
        cuotas = atributos.get('prestamo_cuotas') or []
        for cuota in cuotas:
            if monto_disponible <= 0:
                break
            cuota_id = int(cuota['cuota_id'])
            cuota_rows = db.execute_query(
                """
                SELECT pc.*, p.moneda_codigo, p.tipo_cambio
                FROM contabilidad.planilla_prestamo_cuota pc
                JOIN contabilidad.planilla_prestamo p ON p.id = pc.prestamo_id
                WHERE pc.id = %s AND pc.estado IN ('PENDIENTE','PARCIAL')
                """,
                (cuota_id,)
            )
            if not cuota_rows:
                continue
            cuota_db = cuota_rows[0]
            saldo_cuota = Decimal(str(cuota_db['saldo_pendiente'] or 0)).quantize(CUANTIA)
            aplicar = min(saldo_cuota, monto_disponible)
            if aplicar <= 0:
                continue
            nuevo_aplicado = Decimal(str(cuota_db['monto_aplicado'] or 0)).quantize(CUANTIA) + aplicar
            nuevo_saldo = saldo_cuota - aplicar
            estado_cuota = 'APLICADA' if nuevo_saldo <= 0 else 'PARCIAL'
            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo_cuota
                SET monto_aplicado = %s,
                    saldo_pendiente = %s,
                    estado = %s,
                    planilla_periodo_id = %s,
                    planilla_detalle_id = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (nuevo_aplicado, nuevo_saldo, estado_cuota, planilla_id, concepto['planilla_detalle_id'], cuota_id)
            )
            db.execute_insert(
                """
                INSERT INTO contabilidad.planilla_prestamo_aplicacion (
                    prestamo_id, cuota_id, tipo_aplicacion, fecha_aplicacion, monto_aplicado,
                    moneda_codigo, tipo_cambio, planilla_periodo_id, planilla_detalle_id,
                    referencia, justificativo, creado_por, creado_en
                ) VALUES (%s, %s, 'PLANILLA', CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    cuota_db['prestamo_id'], cuota_id, aplicar, cuota_db['moneda_codigo'], cuota_db['tipo_cambio'],
                    planilla_id, concepto['planilla_detalle_id'], planilla['codigo'],
                    f'Descuento aplicado por planilla {planilla["codigo"]}', _usuario_actual()
                ),
                return_id=False
            )
            resumen = db.execute_query(
                """
                SELECT COALESCE(SUM(monto_aplicado),0) AS aplicado, COALESCE(SUM(saldo_pendiente),0) AS saldo
                FROM contabilidad.planilla_prestamo_cuota
                WHERE prestamo_id = %s AND estado <> 'ANULADA'
                """,
                (cuota_db['prestamo_id'],)
            )[0]
            estado_prestamo = 'PAGADO' if Decimal(str(resumen['saldo'] or 0)) <= 0 else 'PARCIAL'
            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo
                SET monto_recuperado = %s,
                    saldo_pendiente = %s,
                    estado = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (row_decimal(resumen, 'aplicado'), row_decimal(resumen, 'saldo'), estado_prestamo, cuota_db['prestamo_id'])
            )
            monto_disponible -= aplicar

# ============================================================
# Devengamiento, reversión y eliminación segura
# ============================================================

def _planilla_tiene_pagos(db: DatabaseManager, planilla_id: int) -> bool:
    rows = db.execute_query(
        """
        SELECT 1
        FROM contabilidad.planilla_pago_aplicacion ppa
        JOIN contabilidad.pago p ON p.id = ppa.pago_id
        WHERE ppa.planilla_periodo_id = %s
          AND ppa.estado = 'VIGENTE'
          AND p.estado = 'CONFIRMADO'
        LIMIT 1
        """,
        (planilla_id,)
    )
    return bool(rows)


def _planilla_tiene_historial_contable(db: DatabaseManager, planilla_id: int) -> bool:
    rows = db.execute_query(
        """
        SELECT 1
        FROM contabilidad.documento_asiento
        WHERE tabla_origen = 'contabilidad.planilla_periodo'
          AND origen_id = %s
        LIMIT 1
        """,
        (planilla_id,)
    )
    return bool(rows)


def _planilla_tiene_aplicaciones_prestamo(db: DatabaseManager, planilla_id: int) -> bool:
    try:
        rows = db.execute_query(
            "SELECT 1 FROM contabilidad.planilla_prestamo_aplicacion WHERE planilla_periodo_id = %s LIMIT 1",
            (planilla_id,)
        )
        return bool(rows)
    except Exception:
        return False


def _requiere_cuenta(parametros: dict[str, Any], key: str, label: str) -> str:
    cuenta = _clean(parametros.get(key))
    if not cuenta:
        raise ValueError(f'Debe configurar la cuenta "{label}" en Parámetros de Planilla para esta gestión.')
    return cuenta


def _validar_parametros_contables(db: DatabaseManager, planilla_id: int, parametros: dict[str, Any]):
    _requiere_cuenta(parametros, 'cuenta_gasto_honorarios_codigo', 'Gasto honorarios / salarios')
    _requiere_cuenta(parametros, 'cuenta_honorarios_por_pagar_codigo', 'Honorarios por pagar')
    rows = db.execute_query(
        """
        SELECT codigo_concepto, nombre_concepto, tipo_concepto, COALESCE(cuenta_haber_codigo,'') AS cuenta_haber_codigo,
               COALESCE(SUM(monto),0) AS monto
        FROM contabilidad.planilla_detalle_concepto dc
        JOIN contabilidad.planilla_detalle pd ON pd.id = dc.planilla_detalle_id
        WHERE dc.planilla_periodo_id = %s
          AND pd.estado <> 'EXCLUIDO'
          AND dc.monto > 0
        GROUP BY codigo_concepto, nombre_concepto, tipo_concepto, cuenta_haber_codigo
        """,
        (planilla_id,)
    )
    for row in rows:
        monto = Decimal(str(row['monto'] or 0))
        if monto <= 0:
            continue
        codigo = _upper(row['codigo_concepto'])
        tipo = _upper(row['tipo_concepto'])
        if codigo == 'AFP_LABORAL':
            _requiere_cuenta(parametros, 'cuenta_afp_por_pagar_codigo', 'AFP/Gestora por pagar')
        elif codigo in ('RC_IVA', 'RCIVA', 'RC-IVA'):
            _requiere_cuenta(parametros, 'cuenta_rc_iva_por_pagar_codigo', 'RC-IVA por pagar')
        elif codigo == 'ANTICIPO_PRESTAMO':
            continue
        elif tipo in ('DESCUENTO', 'RETENCION') and not row.get('cuenta_haber_codigo'):
            _requiere_cuenta(parametros, 'cuenta_descuentos_por_pagar_codigo', 'Descuentos por pagar / compensar')
        elif tipo == 'APORTE_PATRONAL':
            _requiere_cuenta(parametros, 'cuenta_gasto_aportes_patronales_codigo', 'Gasto aportes patronales')
            if not row.get('cuenta_haber_codigo'):
                _requiere_cuenta(parametros, 'cuenta_aportes_patronales_por_pagar_codigo', 'Aportes patronales por pagar')


def _insertar_asiento(db: DatabaseManager, fecha: date, unidad_id: int, moneda: str, tipo_cambio: Decimal,
                      glosa: str, referencia: str, accion: str, planilla_id: int, lineas: list[dict[str, Any]],
                      vincular_documento: bool = True) -> int:
    total_debe = sum((Decimal(str(x.get('debe') or 0)) for x in lineas), Decimal('0.00')).quantize(CUANTIA)
    total_haber = sum((Decimal(str(x.get('haber') or 0)) for x in lineas), Decimal('0.00')).quantize(CUANTIA)
    if total_debe != total_haber:
        raise ValueError(f'El asiento de planilla no cuadra. Debe {total_debe} / Haber {total_haber}.')
    if total_debe <= 0:
        raise ValueError('El asiento de planilla no tiene importe.')
    asiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha, unidad_negocio_id, moneda_codigo, tipo_cambio, glosa, referencia,
            modulo_origen, tabla_origen, origen_id, estado, atributos, actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, 'PLANILLAS', 'contabilidad.planilla_periodo', %s, 'CONFIRMADO', %s::jsonb, CURRENT_TIMESTAMP)
        """,
        (fecha, unidad_id, moneda, tipo_cambio, glosa[:500], referencia[:150], planilla_id, Json({'origen': 'planilla_honorarios_colaboradores', 'accion': accion, 'planilla_id': planilla_id}))
    )
    sec = 1
    for linea in lineas:
        debe = Decimal(str(linea.get('debe') or 0)).quantize(CUANTIA)
        haber = Decimal(str(linea.get('haber') or 0)).quantize(CUANTIA)
        if debe == 0 and haber == 0:
            continue
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, glosa, debe, haber,
                monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (asiento_id, sec, linea['cuenta'], linea.get('auxiliar_id'), linea.get('glosa', glosa)[:300], debe, haber, max(debe, haber), referencia[:150], Json(linea.get('atributos') or {})),
            return_id=False
        )
        sec += 1
    if vincular_documento:
        db.execute_insert(
            """
            INSERT INTO contabilidad.documento_asiento (modulo, tabla_origen, origen_id, asiento_id)
            VALUES ('PLANILLAS', 'contabilidad.planilla_periodo', %s, %s)
            ON CONFLICT (tabla_origen, origen_id)
            DO UPDATE SET
                modulo = EXCLUDED.modulo,
                asiento_id = EXCLUDED.asiento_id
            """,
            (planilla_id, asiento_id),
            return_id=False
        )
    return asiento_id


def _agregar_linea(lineas: list[dict[str, Any]], cuenta: str, debe: Decimal = Decimal('0.00'), haber: Decimal = Decimal('0.00'),
                   glosa: str | None = None, auxiliar_id: int | None = None, atributos: dict[str, Any] | None = None):
    debe = Decimal(str(debe or 0)).quantize(CUANTIA)
    haber = Decimal(str(haber or 0)).quantize(CUANTIA)
    if debe <= 0 and haber <= 0:
        return
    lineas.append({'cuenta': cuenta, 'debe': debe, 'haber': haber, 'glosa': glosa, 'auxiliar_id': auxiliar_id, 'atributos': atributos or {}})


def _crear_asientos_devengamiento(db: DatabaseManager, planilla_id: int, planilla: dict[str, Any], parametros: dict[str, Any], justificativo: str) -> list[int]:
    unidades = db.execute_query(
        """
        SELECT unidad_negocio_id, COALESCE(unidad_negocio_codigo,'S/U') AS unidad_codigo,
               COALESCE(unidad_negocio_nombre,'Sin unidad') AS unidad_nombre,
               COALESCE(SUM(total_ganado),0) AS total_ganado,
               COALESCE(SUM(descuentos_laborales),0) AS total_descuentos,
               COALESCE(SUM(retenciones),0) AS retenciones,
               COALESCE(SUM(aportes_patronales),0) AS aportes,
               COALESCE(SUM(liquido_pagable),0) AS liquido
        FROM contabilidad.planilla_detalle
        WHERE planilla_periodo_id = %s
          AND estado <> 'EXCLUIDO'
        GROUP BY unidad_negocio_id, unidad_negocio_codigo, unidad_negocio_nombre
        ORDER BY unidad_codigo
        """,
        (planilla_id,)
    )
    asientos: list[int] = []
    for u in unidades:
        unidad_id = int(u['unidad_negocio_id'])
        glosa = f'Devengamiento honorarios {planilla["codigo"]} - {u["unidad_codigo"]}'
        referencia = planilla['codigo']
        lineas: list[dict[str, Any]] = []
        aportes = row_decimal(u, 'aportes')
        liquido = row_decimal(u, 'liquido')

        # Honorarios profesionales (6.1.1.017) requiere auxiliar en el plan de cuentas actual.
        # Por tanto el gasto no puede registrarse como una linea consolidada por unidad;
        # se desglosa por colaborador usando el auxiliar copiado en el detalle de planilla.
        honorarios_persona = db.execute_query(
            """
            SELECT id, nombre_completo, auxiliar_id, COALESCE(total_ganado,0) AS total_ganado
            FROM contabilidad.planilla_detalle
            WHERE planilla_periodo_id = %s
              AND unidad_negocio_id = %s
              AND estado <> 'EXCLUIDO'
              AND COALESCE(total_ganado,0) > 0
            ORDER BY secuencia, nombre_completo
            """,
            (planilla_id, unidad_id)
        )
        for hp in honorarios_persona:
            monto_honorario = row_decimal(hp, 'total_ganado')
            if monto_honorario <= 0:
                continue
            if not hp.get('auxiliar_id'):
                raise ValueError(f'El colaborador {hp["nombre_completo"]} no tiene auxiliar contable vinculado.')
            _agregar_linea(
                lineas,
                parametros['cuenta_gasto_honorarios_codigo'],
                debe=monto_honorario,
                auxiliar_id=hp.get('auxiliar_id'),
                glosa=f'{glosa} - {hp["nombre_completo"]}',
                atributos={'tipo': 'debe_total_ganado', 'detalle_id': hp.get('id')}
            )
        if aportes > 0:
            _agregar_linea(lineas, _requiere_cuenta(parametros, 'cuenta_gasto_aportes_patronales_codigo', 'Gasto aportes patronales'), debe=aportes, glosa=glosa, atributos={'tipo': 'debe_aportes_patronales'})
        # La cuenta por pagar 2.1.1.001 requiere auxiliar en el plan de cuentas actual.
        # Por tanto, la obligación no puede registrarse como una sola línea consolidada por unidad;
        # debe desglosarse por colaborador, usando el auxiliar copiado en el detalle de planilla.
        obligaciones_persona = db.execute_query(
            """
            SELECT id, nombre_completo, auxiliar_id, COALESCE(liquido_pagable,0) AS liquido_pagable
            FROM contabilidad.planilla_detalle
            WHERE planilla_periodo_id = %s
              AND unidad_negocio_id = %s
              AND estado <> 'EXCLUIDO'
              AND COALESCE(liquido_pagable,0) > 0
            ORDER BY secuencia, nombre_completo
            """,
            (planilla_id, unidad_id)
        )
        for op in obligaciones_persona:
            monto_liquido = row_decimal(op, 'liquido_pagable')
            if monto_liquido <= 0:
                continue
            if not op.get('auxiliar_id'):
                raise ValueError(f'El colaborador {op["nombre_completo"]} no tiene auxiliar contable vinculado.')
            _agregar_linea(
                lineas,
                parametros['cuenta_honorarios_por_pagar_codigo'],
                haber=monto_liquido,
                auxiliar_id=op.get('auxiliar_id'),
                glosa=f'{glosa} - obligación por pagar {op["nombre_completo"]}',
                atributos={'tipo': 'haber_liquido_pagable', 'detalle_id': op.get('id')}
            )

        conceptos = db.execute_query(
            """
            SELECT dc.codigo_concepto, dc.nombre_concepto, dc.tipo_concepto, COALESCE(dc.cuenta_haber_codigo,'') AS cuenta_haber_codigo,
                   COALESCE(SUM(dc.monto),0) AS monto
            FROM contabilidad.planilla_detalle_concepto dc
            JOIN contabilidad.planilla_detalle pd ON pd.id = dc.planilla_detalle_id
            WHERE dc.planilla_periodo_id = %s
              AND pd.unidad_negocio_id = %s
              AND pd.estado <> 'EXCLUIDO'
              AND dc.monto > 0
            GROUP BY dc.codigo_concepto, dc.nombre_concepto, dc.tipo_concepto, dc.cuenta_haber_codigo
            """,
            (planilla_id, unidad_id)
        )
        for c in conceptos:
            codigo = _upper(c['codigo_concepto'])
            tipo = _upper(c['tipo_concepto'])
            monto = row_decimal(c, 'monto')
            if monto <= 0 or codigo == 'ANTICIPO_PRESTAMO':
                continue
            if codigo == 'AFP_LABORAL':
                cuenta = _requiere_cuenta(parametros, 'cuenta_afp_por_pagar_codigo', 'AFP/Gestora por pagar')
            elif codigo in ('RC_IVA', 'RCIVA', 'RC-IVA'):
                cuenta = _requiere_cuenta(parametros, 'cuenta_rc_iva_por_pagar_codigo', 'RC-IVA por pagar')
            elif tipo == 'APORTE_PATRONAL':
                cuenta = c.get('cuenta_haber_codigo') or _requiere_cuenta(parametros, 'cuenta_aportes_patronales_por_pagar_codigo', 'Aportes patronales por pagar')
            elif tipo in ('DESCUENTO', 'RETENCION'):
                cuenta = c.get('cuenta_haber_codigo') or _requiere_cuenta(parametros, 'cuenta_descuentos_por_pagar_codigo', 'Descuentos por pagar / compensar')
            else:
                continue
            _agregar_linea(lineas, cuenta, haber=monto, glosa=f'{glosa} - {c["nombre_concepto"]}', atributos={'tipo': 'haber_concepto', 'codigo_concepto': codigo})

        prestamos = db.execute_query(
            """
            SELECT p.cuenta_cobrar_codigo, p.auxiliar_id, p.nombre_completo,
                   COALESCE(SUM(pa.monto_aplicado),0) AS monto
            FROM contabilidad.planilla_prestamo_aplicacion pa
            JOIN contabilidad.planilla_prestamo p ON p.id = pa.prestamo_id
            JOIN contabilidad.planilla_detalle pd ON pd.id = pa.planilla_detalle_id
            WHERE pa.planilla_periodo_id = %s
              AND pd.unidad_negocio_id = %s
              AND pa.tipo_aplicacion = 'PLANILLA'
            GROUP BY p.cuenta_cobrar_codigo, p.auxiliar_id, p.nombre_completo
            """,
            (planilla_id, unidad_id)
        )
        for pr in prestamos:
            monto = row_decimal(pr, 'monto')
            _agregar_linea(lineas, pr['cuenta_cobrar_codigo'], haber=monto, auxiliar_id=pr.get('auxiliar_id'), glosa=f'{glosa} - recupero anticipo/préstamo {pr["nombre_completo"]}', atributos={'tipo': 'haber_recupero_prestamo'})
        asiento_id = _insertar_asiento(
            db, planilla['fecha_planilla'], unidad_id, planilla['moneda_codigo'], planilla['tipo_cambio'],
            glosa, referencia, 'devengamiento_planilla_honorarios', planilla_id, lineas,
            vincular_documento=(len(asientos) == 0)
        )
        asientos.append(asiento_id)
    return asientos


def _crear_asientos_reversion(db: DatabaseManager, planilla_id: int, planilla: dict[str, Any], justificativo: str) -> list[int]:
    rows = db.execute_query(
        """
        SELECT DISTINCT a.*
        FROM contabilidad.asiento a
        LEFT JOIN contabilidad.documento_asiento da ON da.asiento_id = a.id
        WHERE a.estado = 'CONFIRMADO'
          AND a.tabla_origen = 'contabilidad.planilla_periodo'
          AND a.origen_id = %s
          AND COALESCE(a.atributos->>'accion','') = 'devengamiento_planilla_honorarios'
        UNION
        SELECT DISTINCT a.*
        FROM contabilidad.asiento a
        JOIN contabilidad.documento_asiento da ON da.asiento_id = a.id
        WHERE a.estado = 'CONFIRMADO'
          AND da.tabla_origen = 'contabilidad.planilla_periodo'
          AND da.origen_id = %s
          AND COALESCE(a.atributos->>'accion','') = 'devengamiento_planilla_honorarios'
        ORDER BY id
        """,
        (planilla_id, planilla_id)
    )
    reversos: list[int] = []
    for asiento in rows:
        detalles = db.execute_query(
            """
            SELECT *
            FROM contabilidad.asiento_detalle
            WHERE asiento_id = %s
            ORDER BY secuencia
            """,
            (asiento['id'],)
        )
        lineas = []
        for d in detalles:
            lineas.append({
                'cuenta': d['cuenta_codigo'],
                'auxiliar_id': d.get('auxiliar_id'),
                'glosa': f'Reverso {asiento["referencia"]}',
                'debe': Decimal(str(d.get('haber') or 0)).quantize(CUANTIA),
                'haber': Decimal(str(d.get('debe') or 0)).quantize(CUANTIA),
                'atributos': {'tipo': 'reverso_devengamiento', 'asiento_original_id': int(asiento['id'])}
            })
        reverso_id = _insertar_asiento(
            db, date.today(), int(asiento['unidad_negocio_id']), asiento['moneda_codigo'], asiento['tipo_cambio'],
            f'Reverso devengamiento {planilla["codigo"]}: {justificativo}', f'REV-{asiento["referencia"]}',
            'reverso_devengamiento_planilla_honorarios', planilla_id, lineas,
            vincular_documento=False
        )
        reversos.append(reverso_id)
    if reversos:
        db.execute_update(
            """
            UPDATE contabilidad.planilla_periodo
            SET asiento_anulacion_id = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (reversos[0], planilla_id)
        )
    return reversos


def _revertir_cuotas_prestamo_planilla(db: DatabaseManager, planilla_id: int):
    try:
        aplicaciones = db.execute_query(
            """
            SELECT *
            FROM contabilidad.planilla_prestamo_aplicacion
            WHERE planilla_periodo_id = %s
              AND tipo_aplicacion = 'PLANILLA'
            ORDER BY id DESC
            """,
            (planilla_id,)
        )
    except Exception:
        return
    prestamos_afectados: set[int] = set()
    for app in aplicaciones:
        monto = Decimal(str(app['monto_aplicado'] or 0)).quantize(CUANTIA)
        cuota_id = app.get('cuota_id')
        prestamo_id = int(app['prestamo_id'])
        prestamos_afectados.add(prestamo_id)
        if cuota_id:
            cuota_rows = db.execute_query("SELECT * FROM contabilidad.planilla_prestamo_cuota WHERE id = %s", (cuota_id,))
            if cuota_rows:
                cuota = cuota_rows[0]
                aplicado = max(Decimal(str(cuota['monto_aplicado'] or 0)).quantize(CUANTIA) - monto, Decimal('0.00'))
                programado = Decimal(str(cuota['monto_programado'] or 0)).quantize(CUANTIA)
                saldo = (programado - aplicado).quantize(CUANTIA)
                estado = 'PENDIENTE' if aplicado <= 0 else ('APLICADA' if saldo <= 0 else 'PARCIAL')
                db.execute_update(
                    """
                    UPDATE contabilidad.planilla_prestamo_cuota
                    SET monto_aplicado = %s,
                        saldo_pendiente = %s,
                        estado = %s,
                        planilla_periodo_id = NULL,
                        planilla_detalle_id = NULL,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (aplicado, saldo, estado, cuota_id)
                )
        db.execute_update("DELETE FROM contabilidad.planilla_prestamo_aplicacion WHERE id = %s", (app['id'],))
    for prestamo_id in prestamos_afectados:
        resumen = db.execute_query(
            """
            SELECT COALESCE(SUM(monto_aplicado),0) AS aplicado, COALESCE(SUM(saldo_pendiente),0) AS saldo
            FROM contabilidad.planilla_prestamo_cuota
            WHERE prestamo_id = %s AND estado <> 'ANULADA'
            """,
            (prestamo_id,)
        )[0]
        saldo = row_decimal(resumen, 'saldo')
        aplicado = row_decimal(resumen, 'aplicado')
        estado = 'PAGADO' if saldo <= 0 else ('PARCIAL' if aplicado > 0 else 'CONFIRMADO')
        db.execute_update(
            """
            UPDATE contabilidad.planilla_prestamo
            SET monto_recuperado = %s,
                saldo_pendiente = %s,
                estado = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (aplicado, saldo, estado, prestamo_id)
        )
