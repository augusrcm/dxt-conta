# ============================================================
# DXT CONTA - Reportes Rapidos - Exportacion PDF generica
# ============================================================

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader

from modules.reportes_rapidos.core.utils import logo_path, usuario_actual


ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')


def _safe_text(value) -> str:
    return escape(str(value if value is not None else ''))


def _money_note_display(value: str | None) -> str:
    note = str(value or '').strip()
    if not note:
        return ''
    if not note.endswith('.'):
        note += '.'
    if note.startswith('(') and note.endswith(')'):
        return note
    return f'({note})'


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
        self.drawRightString(page_width - 18 * mm, 10 * mm, f'Pagina {self._pageNumber} de {total_pages}')
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
        subtitle = self.report_context.get('subtitle') or datetime.now().strftime('%d/%m/%Y %H:%M')
        money_note = _money_note_display(self.report_context.get('money_note'))
        logo_file = self.report_context.get('logo_path')

        page_width, page_height = doc.pagesize
        x_left = doc.leftMargin
        x_right = page_width - doc.rightMargin
        header_top = page_height - 22 * mm

        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)

        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 20)
        canvas.drawString(x_left, header_top - 22, title)

        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 9.5)
        canvas.drawString(x_left, header_top - 40, subtitle)

        line_y = header_top - 58
        if money_note:
            canvas.setFillColor(colors.black)
            canvas.setFont('Helvetica-Bold', 8.6)
            canvas.drawString(x_left, header_top - 53, money_note)
            line_y = header_top - 66

        if logo_file and os.path.exists(logo_file):
            try:
                logo = ImageReader(logo_file)
                logo_w = 38 * mm
                logo_h = 12 * mm
                canvas.drawImage(
                    logo,
                    x_right - logo_w,
                    header_top - 45,
                    width=logo_w,
                    height=logo_h,
                    preserveAspectRatio=True,
                    mask='auto',
                    anchor='ne',
                )
            except Exception:
                pass

        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(1)
        canvas.line(x_left, line_y, x_right, line_y)
        canvas.restoreState()


def _styles():
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
        fontSize=7.1,
        leading=8.5,
        textColor=TEXT,
        alignment=TA_LEFT,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTBodyCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.1,
        leading=8.5,
        textColor=TEXT,
        alignment=TA_CENTER,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTBodyRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.1,
        leading=8.5,
        textColor=TEXT,
        alignment=TA_RIGHT,
        wordWrap='CJK',
    ))
    return styles


def _build_table_report_pdf(*, title: str, subtitle: str, columns: Sequence[dict], rows: Iterable[Sequence],
                            orientation: str = 'portrait', emitted_by: str = 'Sistema',
                            logo_file: str | None = None, header_note: str | None = None,
                            money_note: str | None = None) -> bytes:
    pagesize = portrait(A4) if orientation != 'landscape' else landscape(A4)
    buffer = io.BytesIO()
    top_margin = 56 * mm if money_note else 50 * mm

    context = {
        'title': title,
        'subtitle': subtitle,
        'emitted_by': emitted_by,
        'logo_path': logo_file,
        'money_note': money_note,
    }

    doc = BrandedDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=top_margin,
        bottomMargin=18 * mm,
        report_context=context,
    )

    styles = _styles()
    story = []
    if header_note:
        story.append(Paragraph(_safe_text(header_note), styles['DXTMeta']))
        story.append(Spacer(1, 4 * mm))

    header_row = [Paragraph(_safe_text(col.get('label', '')), styles['DXTBodyCenter']) for col in columns]
    data = [header_row]
    for row in rows:
        rendered = []
        for idx, cell in enumerate(row):
            align = columns[idx].get('align', 'left') if idx < len(columns) else 'left'
            style_name = 'DXTBody'
            if align == 'center':
                style_name = 'DXTBodyCenter'
            elif align == 'right':
                style_name = 'DXTBodyRight'
            rendered.append(Paragraph(_safe_text(cell), styles[style_name]))
        data.append(rendered)

    col_widths = [col.get('width', 20) * mm for col in columns]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.1),
        ('LEADING', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, row_idx), (-1, row_idx), ROW_ALT),
            ]))

    story.append(table)
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


def build_pdf(report, payload):
    summary = payload.get('summary') or {}
    moneda_note = summary.get('moneda_display_note') or ''
    header_note = report.pdf_header_note(payload)
    criterio = str(payload.get('criterio_reporte') or '').strip()
    fuente = str(payload.get('fuente_datos') or '').strip()
    if criterio:
        criterio_line = f"Criterio: {criterio}"
        if fuente:
            criterio_line = f"{criterio_line} Fuente: {fuente}"
        header_note = f"{header_note} {criterio_line}" if header_note else criterio_line

    return _build_table_report_pdf(
        title=payload.get('titulo', getattr(report, 'TITLE', 'Reporte')),
        subtitle=f"DXT Conta · {payload.get('emitido_en', '')}",
        columns=report.pdf_columns(),
        rows=report.pdf_rows(payload),
        orientation=getattr(report, 'PDF_ORIENTATION', 'landscape'),
        emitted_by=usuario_actual(),
        logo_file=logo_path(),
        header_note=header_note,
        money_note=moneda_note,
    )
