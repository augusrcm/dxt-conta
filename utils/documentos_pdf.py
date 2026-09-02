# ============================================================
# DXT CONTA - Motor PDF transversal para documentos operativos
# Base para pagos, cobros, comprobantes y caja/bancos.
# ============================================================

from __future__ import annotations

import io
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen.canvas import Canvas


ACCENT = colors.HexColor('#ea6f1b')
NAVY = colors.HexColor('#0f2340')
BLUE = colors.HexColor('#2563eb')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#64748b')
BORDER = colors.HexColor('#d9e1ea')
ROW_ALT = colors.HexColor('#f7f9fc')
HEAD_FILL = colors.HexColor('#eef3f8')
BOX_FILL = colors.HexColor('#f8fafc')
STATE_GREEN = colors.HexColor('#15803d')
STATE_AMBER = colors.HexColor('#b45309')
STATE_RED = colors.HexColor('#b91c1c')
STATE_GRAY = colors.HexColor('#475569')


def safe_text(value) -> str:
    return escape(str(value if value is not None else ''))


def format_date(value) -> str:
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    text = str(value)
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        return text


def format_money(value) -> str:
    try:
        number = Decimal(str(value if value is not None else '0')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        number = Decimal('0.00')
    return f'{number:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _state_color(state: str):
    state = (state or '').upper()
    if state == 'CONFIRMADO':
        return STATE_GREEN
    if state == 'BORRADOR':
        return STATE_AMBER
    if state == 'ANULADO':
        return STATE_RED
    return STATE_GRAY


class DocumentCanvas(Canvas):
    def __init__(self, *args, document_context=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.document_context = document_context or {}
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
        emitted_by = self.document_context.get('emitted_by') or 'Sistema'
        generated_at = self.document_context.get('generated_at') or datetime.now().strftime('%d/%m/%Y %H:%M')

        self.saveState()
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.5)
        self.line(18 * mm, 14 * mm, page_width - 18 * mm, 14 * mm)
        self.setFont('Helvetica', 7.5)
        self.setFillColor(MUTED)
        self.drawString(18 * mm, 9 * mm, f'Generado por: {emitted_by} - {generated_at}')
        self.drawRightString(page_width - 18 * mm, 9 * mm, f'Pagina {self._pageNumber} de {total_pages}')
        self.restoreState()


class BrandedDocumentTemplate(BaseDocTemplate):
    def __init__(self, *args, document_context=None, **kwargs):
        self.document_context = document_context or {}
        super().__init__(*args, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        template = PageTemplate(id='document', frames=[frame], onPage=self._draw_header)
        self.addPageTemplates([template])

    def _draw_header(self, canvas, doc):
        title = self.document_context.get('title') or 'Documento'
        subtitle = self.document_context.get('subtitle') or ''
        document_number = self.document_context.get('document_number') or ''
        state = self.document_context.get('state') or ''
        logo_file = self.document_context.get('logo_path')

        page_width, page_height = doc.pagesize
        x_left = doc.leftMargin
        x_right = page_width - doc.rightMargin
        header_top = page_height - 19 * mm

        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)

        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 18)
        canvas.drawString(x_left, header_top - 20, title)

        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 8.5)
        if subtitle:
            canvas.drawString(x_left, header_top - 36, subtitle)
        if document_number:
            canvas.drawString(x_left, header_top - 50, f'Documento: {document_number}')

        if logo_file and os.path.exists(logo_file):
            try:
                logo = ImageReader(logo_file)
                logo_w = 34 * mm
                logo_h = 11 * mm
                canvas.drawImage(
                    logo,
                    x_right - logo_w,
                    header_top - 48,
                    width=logo_w,
                    height=logo_h,
                    preserveAspectRatio=True,
                    mask='auto',
                    anchor='ne',
                )
            except Exception:
                pass

        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.8)
        canvas.line(x_left, header_top - 58, x_right, header_top - 58)
        canvas.restoreState()


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='DXTDocSection',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=9.2,
        leading=11.2,
        textColor=NAVY,
        spaceBefore=2,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name='DXTDocLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.8,
        leading=8.2,
        textColor=MUTED,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name='DXTDocValue',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.0,
        leading=9.4,
        textColor=TEXT,
        alignment=TA_LEFT,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTDocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=8.8,
        textColor=TEXT,
        alignment=TA_LEFT,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='DXTDocBodyCenter',
        parent=styles['DXTDocBody'],
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='DXTDocBodyRight',
        parent=styles['DXTDocBody'],
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        name='DXTDocNote',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.4,
        leading=9,
        textColor=MUTED,
        alignment=TA_LEFT,
        wordWrap='CJK',
    ))
    return styles


def _paragraph(value, style):
    return Paragraph(safe_text(value), style)


def _section_title(title, styles):
    return Paragraph(safe_text(title), styles['DXTDocSection'])


def _build_key_value_section(title: str, items: Sequence[dict], styles, page_width_mm: float = 174.0):
    story = [_section_title(title, styles)]
    data = []
    row = []
    for item in items:
        label = item.get('label') or ''
        value = item.get('value') if item.get('value') not in (None, '') else '-'
        colspan = int(item.get('span') or 1)
        cell = [
            Paragraph(safe_text(label).upper(), styles['DXTDocLabel']),
            Spacer(1, 1.2 * mm),
            Paragraph(safe_text(value), styles['DXTDocValue']),
        ]
        row.append(cell)
        if len(row) >= 3 or colspan >= 3:
            while len(row) < 3:
                row.append('')
            data.append(row[:3])
            row = []
    if row:
        while len(row) < 3:
            row.append('')
        data.append(row[:3])

    table = Table(data, colWidths=[page_width_mm / 3 * mm] * 3, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BOX_FILL),
        ('BOX', (0, 0), (-1, -1), 0.7, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    return story


def _build_text_box(title: str, text: str, styles):
    story = [_section_title(title, styles)]
    table = Table([[Paragraph(safe_text(text or '-'), styles['DXTDocBody'])]], colWidths=[174 * mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.7, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    return story


def _build_table(title: str, columns: Sequence[dict], rows: Iterable[Sequence], styles, empty_message: str = 'Sin registros.'):
    story = [_section_title(title, styles)]
    header = [Paragraph(safe_text(col.get('label', '')), styles['DXTDocBodyCenter']) for col in columns]
    data = [header]
    row_count = 0
    for row in rows or []:
        row_count += 1
        rendered = []
        for idx, cell in enumerate(row):
            align = columns[idx].get('align', 'left') if idx < len(columns) else 'left'
            style_name = 'DXTDocBody'
            if align == 'center':
                style_name = 'DXTDocBodyCenter'
            elif align == 'right':
                style_name = 'DXTDocBodyRight'
            rendered.append(Paragraph(safe_text(cell), styles[style_name]))
        data.append(rendered)

    if row_count == 0:
        data.append([Paragraph(safe_text(empty_message), styles['DXTDocBodyCenter'])] + [''] * (len(columns) - 1))

    col_widths = [col.get('width', 20) * mm for col in columns]
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    commands = [
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.7, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if row_count == 0:
        commands.append(('SPAN', (0, 1), (-1, 1)))
    else:
        for idx in range(1, row_count + 1):
            if idx % 2 == 0:
                commands.append(('BACKGROUND', (0, idx), (-1, idx), ROW_ALT))
    table.setStyle(TableStyle(commands))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    return story


def _build_totals_table(totals: Sequence[dict], styles):
    rows = []
    for item in totals or []:
        rows.append([
            Paragraph(safe_text(item.get('label') or ''), styles['DXTDocBodyRight']),
            Paragraph(safe_text(item.get('value') or ''), styles['DXTDocBodyRight']),
        ])
    if not rows:
        return []
    table = Table(rows, colWidths=[35 * mm, 35 * mm], hAlign='RIGHT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BOX_FILL),
        ('BOX', (0, 0), (-1, -1), 0.7, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return [table, Spacer(1, 4 * mm)]


def _build_signatures(styles):
    data = [[
        Paragraph('Elaborado por', styles['DXTDocBodyCenter']),
        Paragraph('Revisado por', styles['DXTDocBodyCenter']),
        Paragraph('Autorizado / Recibido', styles['DXTDocBodyCenter']),
    ]]
    table = Table(data, colWidths=[58 * mm, 58 * mm, 58 * mm], rowHeights=[21 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LINEABOVE', (0, 0), (-1, 0), 0.7, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return [_section_title('Firmas de respaldo', styles), table]


def build_accounting_document_pdf(*, title: str, subtitle: str, document_number: str, state: str,
                                  sections: Sequence[dict], detail_columns: Sequence[dict], detail_rows: Iterable[Sequence],
                                  totals: Sequence[dict] | None = None,
                                  additional_tables: Sequence[dict] | None = None,
                                  accounting_columns: Sequence[dict] | None = None,
                                  accounting_rows: Iterable[Sequence] | None = None,
                                  notes: Sequence[dict] | None = None,
                                  emitted_by: str = 'Sistema', logo_file: str | None = None,
                                  generated_at: str | None = None) -> bytes:
    buffer = io.BytesIO()
    context = {
        'title': title,
        'subtitle': subtitle,
        'document_number': document_number,
        'state': state,
        'emitted_by': emitted_by,
        'logo_path': logo_file,
        'generated_at': generated_at or datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
    doc = BrandedDocumentTemplate(
        buffer,
        pagesize=portrait(A4),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=45 * mm,
        bottomMargin=20 * mm,
        document_context=context,
    )
    styles = _styles()
    story = []

    for section in sections or []:
        story.extend(_build_key_value_section(section.get('title') or 'Datos', section.get('items') or [], styles))

    for note in notes or []:
        story.extend(_build_text_box(note.get('title') or 'Observacion', note.get('text') or '', styles))

    story.extend(_build_table('Detalle del documento', detail_columns, detail_rows, styles))
    story.extend(_build_totals_table(totals or [], styles))

    for extra_table in additional_tables or []:
        story.extend(_build_table(
            extra_table.get('title') or 'Detalle adicional',
            extra_table.get('columns') or [],
            extra_table.get('rows') or [],
            styles,
            empty_message=extra_table.get('empty_message') or 'Sin registros.',
        ))

    if accounting_columns:
        story.extend(_build_table('Asiento contable asociado', accounting_columns, accounting_rows or [], styles, empty_message='Este documento no tiene asiento contable asociado.'))

    doc.build(story, canvasmaker=lambda *args, **kwargs: DocumentCanvas(*args, document_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()
