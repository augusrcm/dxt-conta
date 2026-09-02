# ============================================================
# DXT CONTA - Dashboard Ejecutivo - PDF ejecutivo
# ============================================================

from __future__ import annotations

import io
import os
from pathlib import Path
from xml.sax.saxutils import escape

from config import Config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle


NAVY = colors.HexColor('#0f2340')
TEXT = colors.HexColor('#243447')
MUTED = colors.HexColor('#5f6f83')
BORDER = colors.HexColor('#d9e1ea')
HEAD_FILL = colors.HexColor('#eef3f8')
ROW_ALT = colors.HexColor('#f7f9fc')


def _safe(value) -> str:
    return escape(str(value if value is not None else ''))


def _logo_path() -> str:
    folder = Path(getattr(Config, 'LOGO_FOLDER', '') or '')
    for filename in ('dxt_logo.jpg', getattr(Config, 'SIDEBAR_LOGO_FILENAME', ''), getattr(Config, 'LOGIN_LOGO_FILENAME', '')):
        if not filename:
            continue
        candidate = folder / filename
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return ''


class DashboardCanvas(Canvas):
    def __init__(self, *args, context=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.context = context or {}
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_header_footer(self, total_pages):
        width, height = self._pagesize
        self.saveState()
        self.setFillColor(NAVY)
        self.setFont('Helvetica-Bold', 16)
        self.drawString(18 * mm, height - 18 * mm, self.context.get('title', 'Dashboard Ejecutivo'))
        self.setFillColor(MUTED)
        self.setFont('Helvetica', 8.5)
        self.drawString(18 * mm, height - 25 * mm, f"DXT Conta · {self.context.get('emitido_en', '')}")
        self.setFillColor(colors.black)
        self.setFont('Helvetica-Bold', 8.5)
        self.drawString(18 * mm, height - 31 * mm, f"({self.context.get('moneda_note', 'Expresado en Bs.')})")

        logo_file = self.context.get('logo_path')
        if logo_file and os.path.exists(logo_file):
            try:
                logo = ImageReader(logo_file)
                self.drawImage(logo, width - 56 * mm, height - 31 * mm, width=38 * mm, height=12 * mm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        self.setStrokeColor(BORDER)
        self.setLineWidth(1)
        self.line(18 * mm, height - 37 * mm, width - 18 * mm, height - 37 * mm)
        self.setFillColor(MUTED)
        self.setFont('Helvetica', 7.5)
        self.drawString(18 * mm, 10 * mm, f"Generado por: {self.context.get('generado_por', 'Usuario del sistema')}")
        self.drawRightString(width - 18 * mm, 10 * mm, f"Página {self._pageNumber} de {total_pages}")
        self.restoreState()


class DashboardDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        self.context = kwargs.pop('context', {})
        super().__init__(filename, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        self.addPageTemplates([PageTemplate(id='principal', frames=[frame])])


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DXTMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=8.2, leading=10, textColor=MUTED))
    styles.add(ParagraphStyle(name='DXTBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7.6, leading=9.2, textColor=TEXT, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTBodyCenter', parent=styles['DXTBody'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='DXTBodyRight', parent=styles['DXTBody'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='DXTSection', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=NAVY))
    return styles


def _cards_table(payload, styles):
    cards = payload.get('cards', [])
    data = []
    for start in range(0, len(cards), 4):
        row = []
        for card in cards[start:start + 4]:
            text = f"<b>{_safe(card.get('titulo'))}</b><br/><font size='11'>{_safe(card.get('valor'))}</font><br/><font color='#5f6f83'>{_safe(card.get('detalle'))}</font>"
            row.append(Paragraph(text, styles['DXTBodyCenter']))
        while len(row) < 4:
            row.append('')
        data.append(row)
    table = Table(data, colWidths=[64 * mm, 64 * mm, 64 * mm, 64 * mm])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return table


def _alerts_table(payload, styles):
    header = ['Prioridad', 'Fecha', 'Tipo', 'Descripción', 'Monto', 'Acción']
    data = [[Paragraph(_safe(item), styles['DXTBodyCenter']) for item in header]]
    for item in payload.get('alertas', []):
        data.append([
            Paragraph(_safe(item.get('prioridad')), styles['DXTBodyCenter']),
            Paragraph(_safe(item.get('fecha_label')), styles['DXTBodyCenter']),
            Paragraph(_safe(item.get('tipo')), styles['DXTBody']),
            Paragraph(_safe(item.get('descripcion')), styles['DXTBody']),
            Paragraph(_safe(item.get('monto_label')), styles['DXTBodyRight']),
            Paragraph(_safe(item.get('accion')), styles['DXTBody']),
        ])
    if len(data) == 1:
        data.append(['', '', '', Paragraph('Sin alertas prioritarias para los filtros seleccionados.', styles['DXTBody']), '', ''])
    table = Table(data, colWidths=[22 * mm, 20 * mm, 35 * mm, 75 * mm, 25 * mm, 70 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    for idx in range(1, len(data)):
        if idx % 2 == 0:
            table.setStyle(TableStyle([('BACKGROUND', (0, idx), (-1, idx), ROW_ALT)]))
    return table


def build_pdf(payload: dict) -> bytes:
    buffer = io.BytesIO()
    context = {
        'title': 'Dashboard Ejecutivo',
        'emitido_en': payload.get('emitido_en', ''),
        'moneda_note': payload.get('moneda_note', 'Expresado en Bs.'),
        'generado_por': payload.get('generado_por', 'Usuario del sistema'),
        'logo_path': _logo_path(),
    }
    doc = DashboardDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=45 * mm,
        bottomMargin=18 * mm,
        context=context,
    )
    styles = _styles()
    story = [
        Paragraph(_safe(payload.get('subtitulo', '')), styles['DXTMeta']),
        Paragraph(_safe(f"Periodo: {payload.get('periodo', '')}"), styles['DXTMeta']),
        Paragraph(_safe(payload.get('criterio', '')), styles['DXTMeta']),
        Spacer(1, 5 * mm),
        Paragraph('Indicadores principales', styles['DXTSection']),
        Spacer(1, 2 * mm),
        _cards_table(payload, styles),
        Spacer(1, 6 * mm),
        Paragraph('Atención prioritaria', styles['DXTSection']),
        Spacer(1, 2 * mm),
        _alerts_table(payload, styles),
    ]
    doc.build(story, canvasmaker=lambda *args, **kwargs: DashboardCanvas(*args, context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()
