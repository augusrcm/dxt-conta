# ============================================================
# DXT CONTA - Reporte Especial
# Resultado mensual
# ============================================================

from __future__ import annotations

import io
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.sax.saxutils import escape

from flask import Response, render_template, request
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from database.db_manager import DatabaseManager
from modules.estado_resultados_mes import estado_resultados_mes_bp
from modules.reportes_rapidos.core.utils import logo_path, usuario_actual
from utils.decorators import login_required, roles_required

ROLES_LECTURA = [9, 10, 11]
CENTAVO = Decimal('0.01')
ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
GREEN = colors.HexColor('#107c41')
RED = colors.HexColor('#b42318')

ER_TIPO_INGRESO = 'INGRESO'
ER_TIPO_COSTO = 'COSTO'
ER_TIPO_GASTO = 'GASTO'
ER_ESTADO_CONFIRMADO = 'CONFIRMADO'
ER_MESES_ES = {
    1: 'Enero',
    2: 'Febrero',
    3: 'Marzo',
    4: 'Abril',
    5: 'Mayo',
    6: 'Junio',
    7: 'Julio',
    8: 'Agosto',
    9: 'Septiembre',
    10: 'Octubre',
    11: 'Noviembre',
    12: 'Diciembre',
}
ER_MODOS_PERIODO = {
    'GESTION': 'Gestión',
    'RANGO_MESES': 'Rango de meses',
}


def _clean(value) -> str:
    return str(value or '').strip()


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal('0.00')
    try:
        return Decimal(str(value)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _fmt_number(value) -> str:
    amount = _to_decimal(value)
    return f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _parse_optional_int(value, field_name):
    value = _clean(value)
    if not value:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} no es válido.') from exc
    if parsed <= 0:
        raise ValueError(f'{field_name} no es válido.')
    return parsed


def _safe_text(value) -> str:
    return escape(str(value if value is not None else ''))


class ReportCanvas(Canvas):
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

    def _draw_footer(self, total_pages: int):
        page_width, _ = self._pagesize
        user = self.report_context.get('emitted_by') or 'Sistema'
        self.saveState()
        self.setFont('Helvetica', 7.5)
        self.setFillColor(MUTED)
        self.drawString(18 * mm, 10 * mm, f'Generado por: {user}')
        self.drawRightString(page_width - 18 * mm, 10 * mm, f'Página {self._pageNumber} de {total_pages}')
        self.restoreState()


class BrandedDocTemplate(BaseDocTemplate):
    def __init__(self, *args, report_context=None, **kwargs):
        self.report_context = report_context or {}
        super().__init__(*args, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        template = PageTemplate(id='branded', frames=[frame], onPage=self._draw_header)
        self.addPageTemplates([template])

    def _draw_header(self, canvas, doc):
        title = self.report_context.get('title') or 'Reporte'
        subtitle = self.report_context.get('subtitle') or ''
        logo_file = self.report_context.get('logo_path')
        page_width, page_height = doc.pagesize
        x_left = doc.leftMargin
        x_right = page_width - doc.rightMargin
        header_top = page_height - 20 * mm

        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 18)
        canvas.drawString(x_left, header_top - 21, title)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(x_left, header_top - 38, subtitle)

        if logo_file:
            try:
                logo = ImageReader(logo_file)
                canvas.drawImage(
                    logo,
                    x_right - 38 * mm,
                    header_top - 42,
                    width=38 * mm,
                    height=12 * mm,
                    preserveAspectRatio=True,
                    mask='auto',
                    anchor='ne',
                )
            except Exception:
                pass

        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(1)
        canvas.line(x_left, header_top - 56, x_right, header_top - 56)
        canvas.restoreState()


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='DXTMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.2,
        leading=10.2,
        textColor=MUTED,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name='DXTBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.0,
        leading=8.3,
        textColor=TEXT,
        alignment=TA_LEFT,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTBodyCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.0,
        leading=8.3,
        textColor=TEXT,
        alignment=TA_CENTER,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTBodyRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.0,
        leading=8.3,
        textColor=TEXT,
        alignment=TA_RIGHT,
        wordWrap='CJK',
    ))
    return styles


class ResultadoNetoBarChart(Flowable):
    def __init__(self, monthly, width, height=58 * mm):
        super().__init__()
        self.monthly = monthly or []
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        self.width = min(self.width, availWidth)
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        x0 = 0
        y0 = 0
        width = self.width
        height = self.height
        pad_left = 8 * mm
        pad_right = 5 * mm
        pad_top = 5 * mm
        pad_bottom = 12 * mm
        plot_width = max(width - pad_left - pad_right, 20 * mm)
        plot_height = max(height - pad_top - pad_bottom, 25 * mm)
        zero_y = y0 + pad_bottom + (plot_height / 2)
        values = [_to_decimal(row.get('resultado_neto')) for row in self.monthly]
        max_abs = max((abs(value) for value in values), default=Decimal('0.00'))

        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.roundRect(x0, y0, width, height, 7, stroke=1, fill=0)
        canvas.setStrokeColor(colors.HexColor('#c8d3df'))
        canvas.setDash(2, 2)
        canvas.line(pad_left, zero_y, width - pad_right, zero_y)
        canvas.setDash()
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(pad_left, height - 4 * mm, 'Resultado neto')

        if not self.monthly or max_abs == 0:
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(MUTED)
            canvas.drawCentredString(width / 2, height / 2, 'Sin datos suficientes para graficar.')
            canvas.restoreState()
            return

        step = plot_width / len(self.monthly)
        bar_width = min(step * 0.52, 12 * mm)
        max_bar_height = (plot_height / 2) - 4

        for idx, row in enumerate(self.monthly):
            value = _to_decimal(row.get('resultado_neto'))
            center_x = pad_left + (step * idx) + (step / 2)
            x = center_x - (bar_width / 2)
            bar_height = float((abs(value) / max_abs) * Decimal(str(max_bar_height)))
            if value >= 0:
                y = zero_y
                fill = GREEN
            else:
                y = zero_y - bar_height
                fill = RED
            canvas.setFillColor(fill)
            canvas.roundRect(x, y, bar_width, max(bar_height, 1.2), 2, stroke=0, fill=1)

            canvas.setFillColor(TEXT)
            canvas.setFont('Helvetica', 5.7)
            label = str(row.get('mes_label') or '')[:3]
            canvas.drawCentredString(center_x, 4 * mm, label)

        canvas.restoreState()


def _build_pdf_bytes(*, title, subtitle, header_note, columns, rows, col_widths, pagesize=landscape(A4), chart_monthly=None):
    buffer = io.BytesIO()
    context = {
        'title': title,
        'subtitle': subtitle,
        'emitted_by': usuario_actual(),
        'logo_path': logo_path(),
    }
    doc = BrandedDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=48 * mm,
        bottomMargin=18 * mm,
        report_context=context,
    )
    styles = _pdf_styles()
    story = [Paragraph(_safe_text(header_note), styles['DXTMeta']), Spacer(1, 4 * mm)]
    if chart_monthly is not None:
        story.append(Paragraph('Gráfico del resultado neto', styles['DXTMeta']))
        story.append(Spacer(1, 2 * mm))
        story.append(ResultadoNetoBarChart(chart_monthly, doc.width, height=62 * mm))
        story.append(Spacer(1, 5 * mm))

    header = [Paragraph(_safe_text(col['label']), styles['DXTBodyCenter']) for col in columns]
    data = [header]
    for row in rows:
        rendered = []
        for idx, value in enumerate(row):
            align = columns[idx].get('align', 'left') if idx < len(columns) else 'left'
            style_name = 'DXTBodyRight' if align == 'right' else 'DXTBodyCenter' if align == 'center' else 'DXTBody'
            rendered.append(Paragraph(_safe_text(value), styles[style_name]))
        data.append(rendered)

    table = Table(data, colWidths=[w * mm for w in col_widths], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            table.setStyle(TableStyle([('BACKGROUND', (0, row_idx), (-1, row_idx), ROW_ALT)]))

    story.append(table)
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


def _er_parse_year(value):
    raw = _clean(value)
    today = date.today()
    if not raw:
        return today.year
    try:
        year = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('La gestión seleccionada no es válida.') from exc
    if year < 1900 or year > 2200:
        raise ValueError('La gestión seleccionada no es válida.')
    return year


def _er_parse_month(value, field_name):
    raw = _clean(value)
    if not raw:
        raise ValueError(f'{field_name} es obligatorio.')
    try:
        parsed = datetime.strptime(raw, '%Y-%m').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no tiene un mes válido.') from exc
    return date(parsed.year, parsed.month, 1)


def _er_month_label(month_date):
    return f"{ER_MESES_ES.get(month_date.month, month_date.strftime('%B'))} {month_date.year}"


def _er_month_key(month_date):
    return month_date.strftime('%Y-%m')


def _er_add_month(month_date):
    if month_date.month == 12:
        return date(month_date.year + 1, 1, 1)
    return date(month_date.year, month_date.month + 1, 1)


def _er_months_between(start_month, end_month):
    months = []
    current = date(start_month.year, start_month.month, 1)
    limit = date(end_month.year, end_month.month, 1)
    while current <= limit:
        months.append(current)
        current = _er_add_month(current)
    return months


def _er_month_to_last_day(month_date):
    return _er_add_month(month_date) - timedelta(days=1)


def _er_fetch_gestiones():
    sql = """
        SELECT DISTINCT EXTRACT(YEAR FROM a.fecha)::int AS gestion
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad
            ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c
            ON c.codigo = ad.cuenta_codigo
        WHERE a.estado = %s
          AND c.tipo::text IN (%s, %s, %s)
        ORDER BY gestion DESC
    """
    try:
        with DatabaseManager.get_cursor() as cursor:
            cursor.execute(sql, (ER_ESTADO_CONFIRMADO, ER_TIPO_INGRESO, ER_TIPO_COSTO, ER_TIPO_GASTO))
            rows = [dict(row) for row in cursor.fetchall()]
    except Exception:
        rows = []
    if not rows:
        return [date.today().year]
    return [row['gestion'] for row in rows if row.get('gestion')]


def _er_fetch_unidades():
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
            FROM contabilidad.unidad_negocio
            WHERE activo = TRUE
            ORDER BY nombre ASC, codigo ASC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _er_fetch_monedas():
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo, COALESCE(NULLIF(simbolo, ''), codigo) AS simbolo, COALESCE(nombre, codigo) AS nombre
            FROM contabilidad.moneda
            ORDER BY codigo ASC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _er_resolver_unidad(unidad_id):
    if not unidad_id:
        return None
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
            FROM contabilidad.unidad_negocio
            WHERE id = %s
            LIMIT 1
            """,
            (unidad_id,),
        )
        row = cursor.fetchone()
    return dict(row) if row else None


def _er_resolver_moneda(moneda_codigo):
    codigo = _clean(moneda_codigo)
    if not codigo:
        return None
    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo, COALESCE(NULLIF(simbolo, ''), codigo) AS simbolo, COALESCE(nombre, codigo) AS nombre
            FROM contabilidad.moneda
            WHERE codigo = %s
            LIMIT 1
            """,
            (codigo,),
        )
        row = cursor.fetchone()
    return dict(row) if row else None


def _er_build_filters(args):
    today = date.today()
    modo_periodo = _clean(args.get('modo_periodo')).upper() or 'GESTION'
    if modo_periodo not in ER_MODOS_PERIODO:
        raise ValueError('El modo de período seleccionado no es válido.')

    gestion = _er_parse_year(args.get('gestion'))
    default_start_month = date(today.year, 1, 1)
    default_end_month = date(today.year, today.month, 1)

    if modo_periodo == 'GESTION':
        fecha_desde = date(gestion, 1, 1)
        fecha_hasta = date(gestion, 12, 31)
        mes_desde = date(gestion, 1, 1)
        mes_hasta = date(gestion, 12, 1)
        periodo_label = f'Gestión {gestion}'
    else:
        mes_desde = _er_parse_month(args.get('mes_desde') or _er_month_key(default_start_month), 'Mes desde')
        mes_hasta = _er_parse_month(args.get('mes_hasta') or _er_month_key(default_end_month), 'Mes hasta')
        if mes_hasta < mes_desde:
            raise ValueError('El mes hasta no puede ser menor al mes desde.')
        fecha_desde = mes_desde
        fecha_hasta = _er_month_to_last_day(mes_hasta)
        periodo_label = f'{_er_month_label(mes_desde)} al {_er_month_label(mes_hasta)}'

    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'La unidad de negocio')
    moneda_codigo = _clean(args.get('moneda_codigo')).upper() or None

    return {
        'modo_periodo': modo_periodo,
        'modo_periodo_label': ER_MODOS_PERIODO[modo_periodo],
        'gestion': gestion,
        'mes_desde': mes_desde,
        'mes_hasta': mes_hasta,
        'mes_desde_value': _er_month_key(mes_desde),
        'mes_hasta_value': _er_month_key(mes_hasta),
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'periodo_label': periodo_label,
        'unidad_negocio_id': unidad_negocio_id,
        'moneda_codigo': moneda_codigo,
    }


def _er_monto_resultado(tipo_cuenta, debe, haber):
    debe = _to_decimal(debe)
    haber = _to_decimal(haber)
    if tipo_cuenta == ER_TIPO_INGRESO:
        return haber - debe
    if tipo_cuenta in {ER_TIPO_COSTO, ER_TIPO_GASTO}:
        return debe - haber
    return Decimal('0.00')


def _er_empty_month(moneda_codigo, moneda_simbolo, month):
    return {
        'mes': _er_month_key(month),
        'mes_label': _er_month_label(month),
        'fecha_inicio': month,
        'moneda_codigo': moneda_codigo,
        'moneda_simbolo': moneda_simbolo,
        'ingresos': Decimal('0.00'),
        'costos': Decimal('0.00'),
        'gastos': Decimal('0.00'),
        'utilidad_bruta': Decimal('0.00'),
        'resultado_neto': Decimal('0.00'),
    }


def _er_fetch_estado_mensual(filtros):
    months = _er_months_between(filtros['mes_desde'], filtros['mes_hasta'])
    sql = """
        SELECT
            DATE_TRUNC('month', a.fecha)::date AS mes,
            c.tipo::text AS tipo,
            COALESCE(a.moneda_codigo, 'SIN_MONEDA') AS moneda_codigo,
            COALESCE(NULLIF(m.simbolo, ''), a.moneda_codigo, 'Sin moneda') AS moneda_simbolo,
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
          AND c.tipo::text IN (%s, %s, %s)
    """
    params = [
        ER_ESTADO_CONFIRMADO,
        filtros['fecha_desde'],
        filtros['fecha_hasta'],
        ER_TIPO_INGRESO,
        ER_TIPO_COSTO,
        ER_TIPO_GASTO,
    ]

    if filtros.get('unidad_negocio_id'):
        sql += "\n          AND a.unidad_negocio_id = %s"
        params.append(filtros['unidad_negocio_id'])

    if filtros.get('moneda_codigo'):
        sql += "\n          AND a.moneda_codigo = %s"
        params.append(filtros['moneda_codigo'])

    sql += """
        GROUP BY DATE_TRUNC('month', a.fecha)::date, c.tipo::text, a.moneda_codigo, m.simbolo
        ORDER BY mes ASC, moneda_codigo ASC, tipo ASC
    """

    with DatabaseManager.get_cursor() as cursor:
        cursor.execute(sql, tuple(params))
        rows = [dict(row) for row in cursor.fetchall()]

    currency_map = OrderedDict()
    for row in rows:
        codigo = row.get('moneda_codigo') or 'SIN_MONEDA'
        simbolo = row.get('moneda_simbolo') or codigo
        currency_map[codigo] = simbolo

    if filtros.get('moneda_codigo') and filtros['moneda_codigo'] not in currency_map:
        moneda = _er_resolver_moneda(filtros['moneda_codigo'])
        currency_map[filtros['moneda_codigo']] = (moneda or {}).get('simbolo') or filtros['moneda_codigo']

    data = OrderedDict()
    for codigo, simbolo in currency_map.items():
        for month in months:
            data[(_er_month_key(month), codigo)] = _er_empty_month(codigo, simbolo, month)

    for row in rows:
        month = row.get('mes')
        if isinstance(month, datetime):
            month = month.date()
        if not isinstance(month, date):
            continue
        month_date = date(month.year, month.month, 1)
        codigo = row.get('moneda_codigo') or 'SIN_MONEDA'
        key = (_er_month_key(month_date), codigo)
        if key not in data:
            data[key] = _er_empty_month(codigo, row.get('moneda_simbolo') or codigo, month_date)
        tipo = row.get('tipo')
        monto = _er_monto_resultado(tipo, row.get('debe_periodo'), row.get('haber_periodo'))
        if tipo == ER_TIPO_INGRESO:
            data[key]['ingresos'] += monto
        elif tipo == ER_TIPO_COSTO:
            data[key]['costos'] += monto
        elif tipo == ER_TIPO_GASTO:
            data[key]['gastos'] += monto

    monthly = []
    for item in data.values():
        item['utilidad_bruta'] = item['ingresos'] - item['costos']
        item['resultado_neto'] = item['utilidad_bruta'] - item['gastos']
        monthly.append(item)

    monthly.sort(key=lambda item: (item['fecha_inicio'], item['moneda_codigo']))
    return monthly


def _er_summary(monthly):
    totales = OrderedDict()
    for row in monthly:
        codigo = row.get('moneda_codigo') or 'SIN_MONEDA'
        if codigo not in totales:
            totales[codigo] = {
                'moneda_codigo': codigo,
                'moneda_simbolo': row.get('moneda_simbolo') or codigo,
                'ingresos': Decimal('0.00'),
                'costos': Decimal('0.00'),
                'gastos': Decimal('0.00'),
                'utilidad_bruta': Decimal('0.00'),
                'resultado_neto': Decimal('0.00'),
            }
        total = totales[codigo]
        total['ingresos'] += row['ingresos']
        total['costos'] += row['costos']
        total['gastos'] += row['gastos']

    for total in totales.values():
        total['utilidad_bruta'] = total['ingresos'] - total['costos']
        total['resultado_neto'] = total['utilidad_bruta'] - total['gastos']
        total['ingresos_label'] = _fmt_number(total['ingresos'])
        total['costos_label'] = _fmt_number(total['costos'])
        total['gastos_label'] = _fmt_number(total['gastos'])
        total['utilidad_bruta_label'] = _fmt_number(total['utilidad_bruta'])
        total['resultado_neto_label'] = _fmt_number(total['resultado_neto'])
        total['resultado_tipo'] = 'utilidad' if total['resultado_neto'] >= 0 else 'perdida'

    totales_lista = list(totales.values())
    moneda_unica = len(totales_lista) == 1
    principal = totales_lista[0] if moneda_unica else None
    meses_con_movimiento = sum(
        1
        for row in monthly
        if row['ingresos'] != 0 or row['costos'] != 0 or row['gastos'] != 0
    )
    return {
        'meses': len({row['mes'] for row in monthly}),
        'meses_con_movimiento': meses_con_movimiento,
        'moneda_unica': moneda_unica,
        'cantidad_monedas': len(totales_lista),
        'moneda_principal_simbolo': principal['moneda_simbolo'] if principal else '',
        'ingresos_label': _fmt_number(principal['ingresos']) if principal else 'Por moneda',
        'costos_label': _fmt_number(principal['costos']) if principal else 'Por moneda',
        'gastos_label': _fmt_number(principal['gastos']) if principal else 'Por moneda',
        'utilidad_bruta_label': _fmt_number(principal['utilidad_bruta']) if principal else 'Por moneda',
        'resultado_neto_label': _fmt_number(principal['resultado_neto']) if principal else 'Por moneda',
        'resultado_tipo': 'utilidad' if (principal and principal['resultado_neto'] >= 0) else 'perdida',
        'totales_por_moneda': totales_lista,
    }


def _er_format_monthly(monthly):
    formatted = []
    for row in monthly:
        formatted.append({
            **row,
            'ingresos_label': _fmt_number(row['ingresos']),
            'costos_label': _fmt_number(row['costos']),
            'gastos_label': _fmt_number(row['gastos']),
            'utilidad_bruta_label': _fmt_number(row['utilidad_bruta']),
            'resultado_neto_label': _fmt_number(row['resultado_neto']),
            'resultado_tipo': 'utilidad' if row['resultado_neto'] >= 0 else 'perdida',
        })
    return formatted


def _er_chart_view(monthly, resumen):
    if not resumen.get('moneda_unica'):
        return {
            'enabled': False,
            'reason': 'Seleccione una moneda para graficar.',
            'width': 1000,
            'height': 320,
            'zero_y': 160,
            'pad_left': 48,
            'pad_right': 24,
            'series': [],
            'has_data': False,
            'max_abs_label': '0,00',
        }

    values = [_to_decimal(row.get('resultado_neto')) for row in monthly]
    max_abs = max((abs(value) for value in values), default=Decimal('0.00'))
    chart_width = 1000
    chart_height = 320
    pad_left = 48
    pad_right = 24
    pad_top = 34
    pad_bottom = 62
    plot_width = chart_width - pad_left - pad_right
    plot_height = chart_height - pad_top - pad_bottom
    zero_y = pad_top + (plot_height / 2)
    step = plot_width / max(len(monthly), 1)
    bar_width = min(46, step * 0.56)
    max_bar_height = (plot_height / 2) - 10
    series = []

    for idx, row in enumerate(monthly):
        value = _to_decimal(row.get('resultado_neto'))
        center_x = pad_left + (step * idx) + (step / 2)
        height = 0
        if max_abs:
            height = float((abs(value) / max_abs) * Decimal(str(max_bar_height)))
        height = max(height, 1 if value else 0)
        if value >= 0:
            bar_y = zero_y - height
            value_y = max(bar_y - 8, 12)
        else:
            bar_y = zero_y
            value_y = min(zero_y + height + 16, chart_height - 10)
        label = str(row.get('mes_label') or '')
        series.append({
            'mes': row.get('mes'),
            'label': label,
            'label_short': label[:3],
            'value': float(value),
            'value_label': _fmt_number(value),
            'tipo': 'utilidad' if value >= 0 else 'perdida',
            'x': round(center_x - (bar_width / 2), 2),
            'center_x': round(center_x, 2),
            'bar_y': round(bar_y, 2),
            'bar_width': round(bar_width, 2),
            'bar_height': round(height, 2),
            'value_y': round(value_y, 2),
        })

    return {
        'enabled': True,
        'reason': '',
        'width': chart_width,
        'height': chart_height,
        'zero_y': round(zero_y, 2),
        'pad_left': pad_left,
        'pad_right': pad_right,
        'series': series,
        'has_data': bool(monthly) and max_abs != 0,
        'max_abs_label': _fmt_number(max_abs),
    }


@estado_resultados_mes_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    error = ''
    try:
        filtros = _er_build_filters(request.args)
        monthly_raw = _er_fetch_estado_mensual(filtros)
        resumen = _er_summary(monthly_raw)
        monthly = _er_format_monthly(monthly_raw)
        chart_view = _er_chart_view(monthly_raw, resumen)
    except ValueError as exc:
        filtros = _er_build_filters({})
        monthly_raw = []
        monthly = []
        resumen = _er_summary([])
        chart_view = _er_chart_view([], resumen)
        error = str(exc)
    except Exception as exc:
        filtros = _er_build_filters({})
        monthly_raw = []
        monthly = []
        resumen = _er_summary([])
        chart_view = _er_chart_view([], resumen)
        error = f'No se pudo cargar el reporte mensual. {exc}'

    unidades = _er_fetch_unidades()
    gestiones = _er_fetch_gestiones()
    monedas = _er_fetch_monedas()
    unidad = _er_resolver_unidad(filtros.get('unidad_negocio_id'))
    moneda = _er_resolver_moneda(filtros.get('moneda_codigo'))
    return render_template(
        'estado_resultados_mes_index.html',
        filtros=filtros,
        modos_periodo=ER_MODOS_PERIODO,
        gestiones=gestiones,
        unidades=unidades,
        monedas=monedas,
        unidad=unidad,
        moneda=moneda,
        monthly=monthly,
        resumen=resumen,
        chart_view=chart_view,
        error=error,
        query_args=request.args.to_dict(flat=True),
    )


@estado_resultados_mes_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _er_build_filters(request.args)
        monthly_raw = _er_fetch_estado_mensual(filtros)
        resumen = _er_summary(monthly_raw)
        monthly = _er_format_monthly(monthly_raw)
        unidad = _er_resolver_unidad(filtros.get('unidad_negocio_id'))
        moneda = _er_resolver_moneda(filtros.get('moneda_codigo'))
        unidad_label = f"{unidad['codigo']} · {unidad['nombre']}" if unidad else 'Todas las unidades'
        moneda_label = (moneda or {}).get('simbolo') or 'Todas las monedas'

        rows = []
        for row in monthly:
            rows.append([
                row['mes_label'],
                row['moneda_simbolo'],
                row['ingresos_label'],
                row['costos_label'],
                row['utilidad_bruta_label'],
                row['gastos_label'],
                row['resultado_neto_label'],
            ])
        if resumen['totales_por_moneda']:
            rows.append(['', '', '', '', '', '', ''])
            for total in resumen['totales_por_moneda']:
                rows.append([
                    'TOTAL',
                    total['moneda_simbolo'],
                    total['ingresos_label'],
                    total['costos_label'],
                    total['utilidad_bruta_label'],
                    total['gastos_label'],
                    total['resultado_neto_label'],
                ])

        chart_monthly = monthly_raw if resumen.get('moneda_unica') else None
        pdf_bytes = _build_pdf_bytes(
            title='Resultado mensual',
            subtitle=f"{filtros['periodo_label']} · {unidad_label} · {moneda_label}",
            header_note='Asientos confirmados. Importes expresados según columna Moneda.',
            columns=[
                {'label': 'Mes'},
                {'label': 'Moneda', 'align': 'center'},
                {'label': 'Ingresos', 'align': 'right'},
                {'label': 'Costos', 'align': 'right'},
                {'label': 'Utilidad bruta', 'align': 'right'},
                {'label': 'Gastos', 'align': 'right'},
                {'label': 'Resultado neto', 'align': 'right'},
            ],
            rows=rows,
            col_widths=[34, 18, 31, 31, 35, 31, 35],
            pagesize=landscape(A4),
            chart_monthly=chart_monthly,
        )
        filename = f"resultado_mensual_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF del resultado mensual. {exc}', status=500, mimetype='text/plain')


@estado_resultados_mes_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('estado_resultados_mes_help.html')
