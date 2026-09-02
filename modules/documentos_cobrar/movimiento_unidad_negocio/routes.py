# ============================================================
# DXT CONTA - Reporte Especial
# Movimiento por Unidad
# ============================================================

from __future__ import annotations

import io
from datetime import date, datetime
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
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from database.db_manager import DatabaseManager
from modules.movimiento_unidad_negocio import movimiento_unidad_negocio_bp
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
SOFT_BLUE = colors.HexColor('#f4f7fb')

MESES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
    7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}


def _clean(value) -> str:
    return str(value or '').strip()


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _money(value) -> str:
    return f'{_to_decimal(value):,.2f}'


def _date_label(value) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    raw = _clean(value)
    if not raw:
        return ''
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return raw


def _safe_text(value) -> str:
    return escape(str(value if value is not None else ''))


def _currency_label(codigo, simbolo=None) -> str:
    codigo = _clean(codigo)
    simbolo = _clean(simbolo)
    if simbolo:
        return simbolo
    return codigo or '-'


def _parse_date(value, default_value: date, field_name: str) -> date:
    raw = _clean(value)
    if not raw:
        return default_value
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'{field_name} no es válida.') from exc


def _parse_optional_int(value, field_name: str):
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} no es válido.') from exc
    if parsed <= 0:
        raise ValueError(f'{field_name} no es válido.')
    return parsed


def _parse_optional_code(value, field_name: str):
    raw = _clean(value).upper()
    if not raw:
        return None
    if len(raw) > 10 or not raw.replace('_', '').replace('-', '').isalnum():
        raise ValueError(f'{field_name} no es válida.')
    return raw


def _db_rows(sql: str, params=()):
    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))
    return [dict(row) for row in rows]


def _default_dates():
    today = date.today()
    return date(today.year, 1, 1), today


def _build_filters(args):
    default_desde, default_hasta = _default_dates()
    fecha_desde = _parse_date(args.get('fecha_desde'), default_desde, 'La fecha desde')
    fecha_hasta = _parse_date(args.get('fecha_hasta'), default_hasta, 'La fecha hasta')
    if fecha_desde > fecha_hasta:
        raise ValueError('La fecha desde no puede ser mayor a la fecha hasta.')
    return {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_desde_label': _date_label(fecha_desde),
        'fecha_hasta_label': _date_label(fecha_hasta),
        'unidad_negocio_id': _parse_optional_int(args.get('unidad_negocio_id'), 'La unidad'),
        'moneda_codigo': _parse_optional_code(args.get('moneda_codigo'), 'La moneda'),
        'emitido': datetime.now(),
    }


def _empty_filters():
    return _build_filters({})


def _fetch_unidades():
    return _db_rows(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
        """
    )


def _fetch_monedas():
    return _db_rows(
        """
        SELECT codigo, COALESCE(nombre, '') AS nombre, COALESCE(simbolo, codigo) AS simbolo
        FROM contabilidad.moneda
        WHERE activo = TRUE
        ORDER BY CASE WHEN codigo = 'BOB' THEN 0 ELSE 1 END, codigo ASC
        """
    )


def _resolve_unidad(unidad_id):
    if not unidad_id:
        return None
    rows = _db_rows(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_id,),
    )
    return rows[0] if rows else None


def _resultado_por_tipo(tipo, debe, haber):
    debe = _to_decimal(debe)
    haber = _to_decimal(haber)
    if tipo == 'INGRESO':
        return haber - debe
    if tipo in {'COSTO', 'GASTO'}:
        return debe - haber
    return Decimal('0.00')


def _base_where(filtros):
    where = [
        "a.estado::text = 'CONFIRMADO'",
        "a.fecha BETWEEN %s AND %s",
        "c.es_postable = TRUE",
        "c.tipo::text IN ('INGRESO', 'COSTO', 'GASTO')",
    ]
    params = [filtros['fecha_desde'], filtros['fecha_hasta']]
    if filtros.get('unidad_negocio_id'):
        where.append('a.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])
    if filtros.get('moneda_codigo'):
        where.append('a.moneda_codigo = %s')
        params.append(filtros['moneda_codigo'])
    return ' AND '.join(where), params


def _new_currency_total(codigo, label):
    return {
        'moneda_codigo': codigo,
        'moneda_label': label,
        'ingresos': Decimal('0.00'),
        'costos': Decimal('0.00'),
        'gastos': Decimal('0.00'),
        'egresos': Decimal('0.00'),
        'resultado_neto': Decimal('0.00'),
        'comprobantes': 0,
    }


def _metric_summary(monedas, key, default_note='Sin datos'):
    if not monedas:
        return {'value': '0.00', 'note': default_note, 'css': 'neutral'}
    if len(monedas) == 1:
        item = monedas[0]
        css = 'positive' if key == 'resultado_neto' and item[key] >= 0 else 'negative' if key == 'resultado_neto' else 'neutral'
        return {'value': item[f'{key}_label'], 'note': item['moneda_label'], 'css': css}
    note = ' · '.join(f"{m['moneda_label']} {m[f'{key}_label']}" for m in monedas)
    return {'value': 'Por moneda', 'note': note, 'css': 'neutral'}


def _margin_summary(monedas):
    if not monedas:
        return {'value': '0.00%', 'note': 'Sin datos', 'css': 'neutral'}
    if len(monedas) == 1:
        item = monedas[0]
        return {'value': item['margen_label'], 'note': item['moneda_label'], 'css': 'neutral'}
    note = ' · '.join(f"{m['moneda_label']} {m['margen_label']}" for m in monedas)
    return {'value': 'Por moneda', 'note': note, 'css': 'neutral'}


def _finalize_totales(totales_por_moneda):
    monedas = []
    comprobantes = 0
    for codigo in sorted(totales_por_moneda):
        item = totales_por_moneda[codigo]
        item['egresos'] = item['costos'] + item['gastos']
        item['resultado_neto'] = item['ingresos'] - item['egresos']
        item['margen'] = Decimal('0.00')
        if item['ingresos'] != 0:
            item['margen'] = ((item['resultado_neto'] / item['ingresos']) * Decimal('100')).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        for key in ['ingresos', 'costos', 'gastos', 'egresos', 'resultado_neto']:
            item[f'{key}_label'] = _money(item[key])
        item['margen_label'] = f"{item['margen']:,.2f}%"
        item['resultado_tipo'] = 'positivo' if item['resultado_neto'] >= 0 else 'negativo'
        monedas.append(item)
        comprobantes += int(item.get('comprobantes') or 0)
    return {
        'monedas': monedas,
        'comprobantes': comprobantes,
        'monedas_count': len(monedas),
        'ingresos': _metric_summary(monedas, 'ingresos'),
        'costos': _metric_summary(monedas, 'costos'),
        'gastos': _metric_summary(monedas, 'gastos'),
        'egresos': _metric_summary(monedas, 'egresos'),
        'resultado_neto': _metric_summary(monedas, 'resultado_neto'),
        'margen': _margin_summary(monedas),
    }


def _fetch_resumen(filtros):
    where, params = _base_where(filtros)
    sql = f"""
        SELECT
            un.id AS unidad_id,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, 'Sin unidad') AS unidad_nombre,
            a.moneda_codigo,
            COALESCE(m.simbolo, a.moneda_codigo) AS moneda_label,
            COALESCE(SUM(CASE WHEN c.tipo::text = 'INGRESO' THEN ad.haber - ad.debe ELSE 0 END), 0) AS ingresos,
            COALESCE(SUM(CASE WHEN c.tipo::text = 'COSTO' THEN ad.debe - ad.haber ELSE 0 END), 0) AS costos,
            COALESCE(SUM(CASE WHEN c.tipo::text = 'GASTO' THEN ad.debe - ad.haber ELSE 0 END), 0) AS gastos,
            COUNT(DISTINCT a.id) AS comprobantes
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        INNER JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        LEFT JOIN contabilidad.moneda m ON m.codigo = a.moneda_codigo
        WHERE {where}
        GROUP BY un.id, un.codigo, un.nombre, a.moneda_codigo, m.simbolo
        ORDER BY un.nombre ASC, un.codigo ASC, a.moneda_codigo ASC
    """
    rows = _db_rows(sql, params)
    resumen = []
    totales_por_moneda = {}
    for row in rows:
        moneda_codigo = _clean(row.get('moneda_codigo')) or '-'
        moneda_label = _currency_label(moneda_codigo, row.get('moneda_label'))
        ingresos = _to_decimal(row.get('ingresos'))
        costos = _to_decimal(row.get('costos'))
        gastos = _to_decimal(row.get('gastos'))
        egresos = costos + gastos
        resultado = ingresos - egresos
        margen = Decimal('0.00')
        if ingresos != 0:
            margen = ((resultado / ingresos) * Decimal('100')).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        item = {
            **row,
            'moneda_codigo': moneda_codigo,
            'moneda_label': moneda_label,
            'ingresos': ingresos,
            'costos': costos,
            'gastos': gastos,
            'egresos': egresos,
            'resultado_neto': resultado,
            'margen': margen,
            'ingresos_label': _money(ingresos),
            'costos_label': _money(costos),
            'gastos_label': _money(gastos),
            'egresos_label': _money(egresos),
            'resultado_neto_label': _money(resultado),
            'margen_label': f'{margen:,.2f}%',
            'resultado_tipo': 'positivo' if resultado >= 0 else 'negativo',
        }
        resumen.append(item)
        total = totales_por_moneda.setdefault(moneda_codigo, _new_currency_total(moneda_codigo, moneda_label))
        total['ingresos'] += ingresos
        total['costos'] += costos
        total['gastos'] += gastos
        total['comprobantes'] += int(row.get('comprobantes') or 0)
    return resumen, _finalize_totales(totales_por_moneda)


def _fetch_detalle_por_unidad(filtros, unidad_id):
    filtros = dict(filtros)
    filtros['unidad_negocio_id'] = unidad_id
    where, params = _base_where(filtros)
    sql = f"""
        SELECT
            c.codigo AS cuenta_codigo,
            COALESCE(c.nombre, '') AS cuenta_nombre,
            c.tipo::text AS tipo,
            a.moneda_codigo,
            COALESCE(m.simbolo, a.moneda_codigo) AS moneda_label,
            COALESCE(SUM(ad.debe), 0) AS debe,
            COALESCE(SUM(ad.haber), 0) AS haber,
            COUNT(DISTINCT a.id) AS comprobantes
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        LEFT JOIN contabilidad.moneda m ON m.codigo = a.moneda_codigo
        WHERE {where}
        GROUP BY c.codigo, c.nombre, c.tipo::text, a.moneda_codigo, m.simbolo
        ORDER BY a.moneda_codigo ASC, c.tipo::text ASC, c.codigo ASC
    """
    rows = _db_rows(sql, params)
    detalle = []
    totales_por_moneda = {}
    for row in rows:
        moneda_codigo = _clean(row.get('moneda_codigo')) or '-'
        moneda_label = _currency_label(moneda_codigo, row.get('moneda_label'))
        debe = _to_decimal(row.get('debe'))
        haber = _to_decimal(row.get('haber'))
        tipo = row.get('tipo') or ''
        saldo = _resultado_por_tipo(tipo, debe, haber)
        resultado = saldo if tipo == 'INGRESO' else -saldo
        total = totales_por_moneda.setdefault(moneda_codigo, _new_currency_total(moneda_codigo, moneda_label))
        if tipo == 'INGRESO':
            total['ingresos'] += saldo
        elif tipo == 'COSTO':
            total['costos'] += saldo
        elif tipo == 'GASTO':
            total['gastos'] += saldo
        total['comprobantes'] += int(row.get('comprobantes') or 0)
        detalle.append({
            **row,
            'moneda_codigo': moneda_codigo,
            'moneda_label': moneda_label,
            'debe': debe,
            'haber': haber,
            'saldo': saldo,
            'resultado': resultado,
            'debe_label': _money(debe),
            'haber_label': _money(haber),
            'saldo_label': _money(saldo),
            'resultado_label': _money(resultado),
            'resultado_tipo': 'positivo' if resultado >= 0 else 'negativo',
        })
    return detalle, _finalize_totales(totales_por_moneda)


def _fetch_mensual(filtros):
    where, params = _base_where(filtros)
    sql = f"""
        SELECT
            un.id AS unidad_id,
            COALESCE(un.codigo, '') AS unidad_codigo,
            COALESCE(un.nombre, 'Sin unidad') AS unidad_nombre,
            a.moneda_codigo,
            COALESCE(m.simbolo, a.moneda_codigo) AS moneda_label,
            EXTRACT(MONTH FROM a.fecha)::int AS mes,
            COALESCE(SUM(CASE WHEN c.tipo::text = 'INGRESO' THEN ad.haber - ad.debe ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN c.tipo::text IN ('COSTO','GASTO') THEN ad.debe - ad.haber ELSE 0 END), 0) AS resultado
        FROM contabilidad.asiento a
        INNER JOIN contabilidad.asiento_detalle ad ON ad.asiento_id = a.id
        INNER JOIN contabilidad.cuenta c ON c.codigo = ad.cuenta_codigo
        INNER JOIN contabilidad.unidad_negocio un ON un.id = a.unidad_negocio_id
        LEFT JOIN contabilidad.moneda m ON m.codigo = a.moneda_codigo
        WHERE {where}
        GROUP BY un.id, un.codigo, un.nombre, a.moneda_codigo, m.simbolo, EXTRACT(MONTH FROM a.fecha)::int
        ORDER BY un.nombre ASC, un.codigo ASC, a.moneda_codigo ASC, mes ASC
    """
    rows = _db_rows(sql, params)
    data = {}
    for row in rows:
        uid = row['unidad_id']
        moneda_codigo = _clean(row.get('moneda_codigo')) or '-'
        key = (uid, moneda_codigo)
        if key not in data:
            data[key] = {
                'unidad_id': uid,
                'unidad_codigo': row.get('unidad_codigo') or '',
                'unidad_nombre': row.get('unidad_nombre') or '',
                'moneda_codigo': moneda_codigo,
                'moneda_label': _currency_label(moneda_codigo, row.get('moneda_label')),
                'meses': {m: Decimal('0.00') for m in range(1, 13)},
                'total': Decimal('0.00'),
            }
        mes = int(row.get('mes') or 0)
        if 1 <= mes <= 12:
            val = _to_decimal(row.get('resultado'))
            data[key]['meses'][mes] += val
            data[key]['total'] += val
    result = []
    for item in data.values():
        item['meses_label'] = {m: _money(v) for m, v in item['meses'].items()}
        item['total_label'] = _money(item['total'])
        item['resultado_tipo'] = 'positivo' if item['total'] >= 0 else 'negativo'
        result.append(item)
    return result


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
        self.drawString(16 * mm, 10 * mm, f'Generado por: {user}')
        self.drawRightString(page_width - 16 * mm, 10 * mm, f'Página {self._pageNumber} de {total_pages}')
        self.restoreState()


class BrandedDocTemplate(BaseDocTemplate):
    def __init__(self, *args, report_context=None, **kwargs):
        self.report_context = report_context or {}
        super().__init__(*args, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        self.addPageTemplates([PageTemplate(id='branded', frames=[frame], onPage=self._draw_header)])

    def _draw_header(self, canvas, doc):
        title = self.report_context.get('title') or 'Reporte'
        subtitle = self.report_context.get('subtitle') or ''
        logo_file = self.report_context.get('logo_path')
        page_width, page_height = doc.pagesize
        x_left = doc.leftMargin
        x_right = page_width - doc.rightMargin
        header_top = page_height - 18 * mm
        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 18)
        canvas.drawString(x_left, header_top - 20, title)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(x_left, header_top - 37, subtitle)
        if logo_file:
            try:
                logo = ImageReader(logo_file)
                canvas.drawImage(logo, x_right - 38 * mm, header_top - 42, width=38 * mm, height=12 * mm, preserveAspectRatio=True, mask='auto', anchor='ne')
            except Exception:
                pass
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(1)
        canvas.line(x_left, header_top - 54, x_right, header_top - 54)
        canvas.restoreState()


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DXTBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTRight', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_RIGHT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTCardLabel', parent=styles['Normal'], fontName='Helvetica', fontSize=6.8, leading=8, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTCardValue', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.4, leading=11, textColor=NAVY, alignment=TA_LEFT))
    return styles


def _paragraph(value, style):
    return Paragraph(_safe_text(value), style)


def _make_table(columns, rows, widths, styles):
    data = [[_paragraph(col.get('label', ''), styles['DXTCenter']) for col in columns]]
    for row in rows:
        rendered = []
        for idx, value in enumerate(row):
            align = columns[idx].get('align', 'left') if idx < len(columns) else 'left'
            style = styles['DXTRight'] if align == 'right' else styles['DXTCenter'] if align == 'center' else styles['DXTBody']
            rendered.append(_paragraph(value, style))
        data.append(rendered)
    table = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL), ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.75, BORDER), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            table.setStyle(TableStyle([('BACKGROUND', (0, row_idx), (-1, row_idx), ROW_ALT)]))
    return table


def _metric_pdf_label(totales, key):
    metric = totales.get(key) or {}
    if metric.get('value') == 'Por moneda':
        return f"Por moneda: {metric.get('note') or ''}"
    note = metric.get('note') or ''
    return f"{metric.get('value') or '0.00'} {note}".strip()


def _build_pdf_general(filtros, resumen, totales):
    buffer = io.BytesIO()
    moneda_label = filtros.get('moneda_codigo') or 'Todas las monedas'
    context = {
        'title': 'Movimiento por Unidad',
        'subtitle': f"Periodo {filtros['fecha_desde_label']} al {filtros['fecha_hasta_label']} · {moneda_label}",
        'emitted_by': usuario_actual(),
        'logo_path': logo_path(),
    }
    doc = BrandedDocTemplate(buffer, pagesize=landscape(A4), leftMargin=16 * mm, rightMargin=16 * mm, topMargin=48 * mm, bottomMargin=18 * mm, report_context=context)
    styles = _pdf_styles()
    story = []
    cards = [
        ('Ingresos', _metric_pdf_label(totales, 'ingresos')),
        ('Costos', _metric_pdf_label(totales, 'costos')),
        ('Gastos', _metric_pdf_label(totales, 'gastos')),
        ('Resultado', _metric_pdf_label(totales, 'resultado_neto')),
        ('Margen', _metric_pdf_label(totales, 'margen')),
    ]
    card_table = Table([[[_paragraph(l, styles['DXTCardLabel']), _paragraph(v, styles['DXTCardValue'])] for l, v in cards]], colWidths=[doc.width / 5] * 5)
    card_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), SOFT_BLUE), ('BOX', (0, 0), (-1, -1), 0.8, BORDER), ('INNERGRID', (0, 0), (-1, -1), 0.45, BORDER), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story.append(card_table)
    story.append(Spacer(1, 5 * mm))
    rows = [[r['unidad_codigo'], r['unidad_nombre'], r['moneda_label'], r['ingresos_label'], r['costos_label'], r['gastos_label'], r['resultado_neto_label'], r['margen_label']] for r in resumen]
    if not rows:
        rows = [['-', 'Sin movimientos en el periodo', '-', '0.00', '0.00', '0.00', '0.00', '0.00%']]
    story.append(_make_table(
        [{'label': 'Código'}, {'label': 'Unidad'}, {'label': 'Moneda', 'align': 'center'}, {'label': 'Ingresos', 'align': 'right'}, {'label': 'Costos', 'align': 'right'}, {'label': 'Gastos', 'align': 'right'}, {'label': 'Resultado', 'align': 'right'}, {'label': 'Margen', 'align': 'right'}],
        rows, [18, 60, 18, 28, 28, 28, 32, 24], styles
    ))
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


def _build_pdf_detalle(filtros, unidad, detalle, totales):
    buffer = io.BytesIO()
    unidad_label = f"{unidad['codigo']} · {unidad['nombre']}" if unidad else 'Unidad no encontrada'
    moneda_label = filtros.get('moneda_codigo') or 'Todas las monedas'
    context = {
        'title': 'Detalle Movimiento por Unidad',
        'subtitle': f"{unidad_label} · {filtros['fecha_desde_label']} al {filtros['fecha_hasta_label']} · {moneda_label}",
        'emitted_by': usuario_actual(),
        'logo_path': logo_path(),
    }
    doc = BrandedDocTemplate(buffer, pagesize=landscape(A4), leftMargin=16 * mm, rightMargin=16 * mm, topMargin=48 * mm, bottomMargin=18 * mm, report_context=context)
    styles = _pdf_styles()
    story = []
    cards = [
        ('Ingresos', _metric_pdf_label(totales, 'ingresos')),
        ('Costos', _metric_pdf_label(totales, 'costos')),
        ('Gastos', _metric_pdf_label(totales, 'gastos')),
        ('Resultado', _metric_pdf_label(totales, 'resultado_neto')),
    ]
    card_table = Table([[[_paragraph(l, styles['DXTCardLabel']), _paragraph(v, styles['DXTCardValue'])] for l, v in cards]], colWidths=[doc.width / 4] * 4)
    card_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), SOFT_BLUE), ('BOX', (0, 0), (-1, -1), 0.8, BORDER), ('INNERGRID', (0, 0), (-1, -1), 0.45, BORDER), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story.append(card_table)
    story.append(Spacer(1, 5 * mm))
    rows = [[r['cuenta_codigo'], r['cuenta_nombre'], r['tipo'], r['moneda_label'], r['debe_label'], r['haber_label'], r['saldo_label'], r['resultado_label']] for r in detalle]
    if not rows:
        rows = [['-', 'Sin movimientos en el periodo', '-', '-', '0.00', '0.00', '0.00', '0.00']]
    story.append(_make_table(
        [{'label': 'Cuenta'}, {'label': 'Nombre'}, {'label': 'Tipo', 'align': 'center'}, {'label': 'Moneda', 'align': 'center'}, {'label': 'Debe', 'align': 'right'}, {'label': 'Haber', 'align': 'right'}, {'label': 'Saldo', 'align': 'right'}, {'label': 'Resultado', 'align': 'right'}],
        rows, [23, 66, 20, 17, 27, 27, 27, 30], styles
    ))
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


def _empty_totales():
    return _finalize_totales({})


@movimiento_unidad_negocio_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    error = ''
    try:
        filtros = _build_filters(request.args)
        resumen, totales = _fetch_resumen(filtros)
        mensual = _fetch_mensual(filtros)
    except ValueError as exc:
        filtros = _empty_filters()
        resumen, totales = _fetch_resumen(filtros)
        mensual = _fetch_mensual(filtros)
        error = str(exc)
    except Exception as exc:
        filtros = _empty_filters()
        resumen, mensual = [], []
        totales = _empty_totales()
        error = f'No se pudo cargar el movimiento por unidad. {exc}'
    return render_template(
        'movimiento_unidad_negocio_index.html',
        filtros=filtros,
        unidades=_fetch_unidades(),
        monedas=_fetch_monedas(),
        resumen=resumen,
        mensual=mensual,
        totales=totales,
        meses=MESES_ES,
        error=error,
        query_args=request.args.to_dict(flat=True),
    )


@movimiento_unidad_negocio_bp.route('/detalle/<int:unidad_id>')
@login_required
@roles_required(ROLES_LECTURA)
def detalle(unidad_id):
    error = ''
    try:
        filtros = _build_filters(request.args)
    except ValueError as exc:
        filtros = _empty_filters()
        error = str(exc)
    unidad = _resolve_unidad(unidad_id)
    if not unidad:
        error = 'No se encontró la unidad seleccionada.'
    try:
        detalle_rows, totales = _fetch_detalle_por_unidad(filtros, unidad_id)
    except Exception as exc:
        detalle_rows, totales = [], _empty_totales()
        error = f'No se pudo cargar el detalle de la unidad. {exc}'
    return render_template(
        'movimiento_unidad_negocio_detalle.html',
        filtros=filtros,
        unidad=unidad,
        detalle=detalle_rows,
        totales=totales,
        error=error,
        query_args=request.args.to_dict(flat=True),
    )


@movimiento_unidad_negocio_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('movimiento_unidad_negocio_help.html')


@movimiento_unidad_negocio_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _build_filters(request.args)
        resumen, totales = _fetch_resumen(filtros)
        pdf_bytes = _build_pdf_general(filtros, resumen, totales)
        filename = f"movimiento_unidad_{filtros['fecha_desde']}_{filtros['fecha_hasta']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF del movimiento por unidad. {exc}', status=500, mimetype='text/plain')


@movimiento_unidad_negocio_bp.route('/detalle/<int:unidad_id>/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_detalle(unidad_id):
    try:
        filtros = _build_filters(request.args)
        unidad = _resolve_unidad(unidad_id)
        detalle_rows, totales = _fetch_detalle_por_unidad(filtros, unidad_id)
        pdf_bytes = _build_pdf_detalle(filtros, unidad, detalle_rows, totales)
        filename = f"movimiento_unidad_detalle_{unidad_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF del detalle por unidad. {exc}', status=500, mimetype='text/plain')
