# ============================================================
# DXT CONTA - Motor PDF transversal para reportes
# ============================================================

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Iterable, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader


ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#6f7c8a')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')


class NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, total_pages: int):
        self.saveState()
        self.setFont('Helvetica', 8)
        self.setFillColor(MUTED)
        self.drawRightString(self._pagesize[0] - 18 * mm, 10 * mm, f'Página {self._pageNumber} de {total_pages}')
        self.restoreState()


class BrandedDocTemplate(BaseDocTemplate):
    def __init__(self, *args, report_context=None, **kwargs):
        self.report_context = report_context or {}
        super().__init__(*args, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        template = PageTemplate(id='branded', frames=[frame], onPage=self._draw_header_footer)
        self.addPageTemplates([template])

    def _draw_header_footer(self, canvas, doc):
        draw_report_header(canvas, doc, self.report_context)
        draw_report_footer(canvas, doc, self.report_context)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='DXTTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=NAVY,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name='DXTMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name='DXTSection',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=NAVY,
        spaceBefore=4,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name='DXTBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=8.6,
        textColor=TEXT,
        alignment=TA_LEFT,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTBodyCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=8.6,
        textColor=TEXT,
        alignment=TA_CENTER,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTBodyRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=8.6,
        textColor=TEXT,
        alignment=TA_RIGHT,
        wordWrap='CJK',
    ))
    return styles


def draw_report_header(canvas, doc, context):
    title = context.get('title', 'Reporte')
    subtitle = context.get('subtitle') or datetime.now().strftime('%d/%m/%Y %H:%M')
    logo_path = context.get('logo_path')

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
    canvas.setFont('Helvetica', 10)
    canvas.drawString(x_left, header_top - 40, subtitle)

    if logo_path and os.path.exists(logo_path):
        try:
            logo = ImageReader(logo_path)
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
    canvas.line(x_left, header_top - 52, x_right, header_top - 52)
    canvas.restoreState()


def draw_report_footer(canvas, doc, context):
    emitted_by = context.get('emitted_by') or 'Sistema'
    organization = context.get('organization') or 'DXT Conta'
    page_width, _ = doc.pagesize
    y = 16 * mm
    center = page_width / 2.0

    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(1)
    canvas.line(center - 45 * mm, y + 8 * mm, center + 45 * mm, y + 8 * mm)
    canvas.setFillColor(NAVY)
    canvas.setFont('Helvetica-Bold', 11)
    text_width = stringWidth(emitted_by, 'Helvetica-Bold', 11)
    canvas.drawString(center - text_width / 2.0, y - 2 * mm, emitted_by)
    canvas.setFont('Helvetica-Bold', 10)
    org_width = stringWidth(organization, 'Helvetica-Bold', 10)
    canvas.drawString(center - org_width / 2.0, y - 10 * mm, organization)
    canvas.restoreState()


def build_table_report_pdf(*, title: str, subtitle: str, columns: Sequence[dict], rows: Iterable[Sequence],
                           orientation: str = 'portrait', emitted_by: str = 'Sistema',
                           organization: str = 'DXT Conta', logo_path: str | None = None,
                           header_note: str | None = None) -> bytes:
    pagesize = portrait(A4) if orientation != 'landscape' else landscape(A4)
    buffer = io.BytesIO()
    doc = BrandedDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=48 * mm,
        bottomMargin=30 * mm,
        report_context={
            'title': title,
            'subtitle': subtitle,
            'emitted_by': emitted_by,
            'organization': organization,
            'logo_path': logo_path,
        },
    )

    styles = _styles()
    story = []
    if header_note:
        story.append(Paragraph(header_note, styles['DXTMeta']))
        story.append(Spacer(1, 4 * mm))

    header_row = [Paragraph(str(col['label']), styles['DXTBodyCenter']) for col in columns]
    data = [header_row]
    for row in rows:
        rendered = []
        for idx, cell in enumerate(row):
            align = columns[idx].get('align', 'left')
            style_name = 'DXTBody'
            if align == 'center':
                style_name = 'DXTBodyCenter'
            elif align == 'right':
                style_name = 'DXTBodyRight'
            rendered.append(Paragraph(str(cell if cell is not None else ''), styles[style_name]))
        data.append(rendered)

    col_widths = [col['width'] * mm for col in columns]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.2),
        ('LEADING', (0, 0), (-1, -1), 8.6),
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
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()