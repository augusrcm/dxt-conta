# ============================================================
# DXT CONTA - Reporte Especial
# Estado de Cuentas por Pagar
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
from modules.estado_cuentas_pagar import estado_cuentas_pagar_bp
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
CARD_FILL = colors.HexColor('#f8fafc')
RED = colors.HexColor('#b42318')

ESTADOS_REPORTE = {
    'pendiente': 'Pendientes',
    'parcial': 'Parciales',
    'pagado': 'Pagados',
    'todos': 'Todos',
}

MONEDA_OPERATIVA = 'Bs'


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


def _parse_date(value, default=None):
    raw = _clean(value)
    if not raw:
        return default or date.today()
    try:
        return datetime.strptime(raw[:10], '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError('La fecha de corte no es válida.') from exc


def _parse_optional_int(value, field_name):
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} no es válido.') from exc
    if parsed < 0:
        raise ValueError(f'{field_name} no es válido.')
    return parsed


def _db_rows(sql: str, params=()):
    with DatabaseManager() as db:
        rows = db.execute_query(sql, tuple(params))
    return [dict(row) for row in rows]


def _fetch_unidades():
    return _db_rows(
        """
        SELECT id, COALESCE(codigo, '') AS codigo, COALESCE(nombre, '') AS nombre
        FROM contabilidad.unidad_negocio
        WHERE activo = TRUE
        ORDER BY nombre ASC, codigo ASC
        """
    )


def _fetch_auxiliares_pagar():
    return _db_rows(
        """
        SELECT DISTINCT
            a.id,
            COALESCE(a.nombre, '') AS nombre,
            COALESCE(a.razon_social, '') AS razon_social,
            COALESCE(a.nit_ci, '') AS nit_ci,
            COALESCE(NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), '') AS orden_nombre
        FROM contabilidad.compromiso c
        INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
        INNER JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
        WHERE c.tipo = 'PAGAR'
          AND c.activo = TRUE
        ORDER BY orden_nombre ASC, nombre ASC, razon_social ASC
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


def _resolve_auxiliar(auxiliar_id):
    if auxiliar_id in (None, ''):
        return None
    if int(auxiliar_id) == 0:
        return {'id': 0, 'nombre': 'Sin auxiliar asignado', 'razon_social': '', 'nit_ci': ''}
    rows = _db_rows(
        """
        SELECT id, COALESCE(nombre, '') AS nombre, COALESCE(razon_social, '') AS razon_social, COALESCE(nit_ci, '') AS nit_ci
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (auxiliar_id,),
    )
    return rows[0] if rows else None


def _build_filters(args):
    fecha_corte = _parse_date(args.get('fecha_corte'), date.today())
    unidad_negocio_id = _parse_optional_int(args.get('unidad_negocio_id'), 'La unidad de negocio')
    auxiliar_id = _parse_optional_int(args.get('auxiliar_id'), 'El proveedor/auxiliar')
    estado = _clean(args.get('estado')) or 'pendiente'
    if estado not in ESTADOS_REPORTE:
        estado = 'pendiente'
    texto = _clean(args.get('texto'))

    return {
        'fecha_corte': fecha_corte,
        'fecha_corte_label': _date_label(fecha_corte),
        'unidad_negocio_id': unidad_negocio_id,
        'auxiliar_id': auxiliar_id,
        'estado': estado,
        'estado_label': ESTADOS_REPORTE[estado],
        'texto': texto,
        'moneda_label': MONEDA_OPERATIVA,
        'emitido': datetime.now(),
    }


def _query_args(filtros, include_auxiliar=True):
    data = {
        'fecha_corte': filtros['fecha_corte'].isoformat(),
        'estado': filtros.get('estado') or 'pendiente',
    }
    if filtros.get('unidad_negocio_id'):
        data['unidad_negocio_id'] = filtros['unidad_negocio_id']
    if include_auxiliar and filtros.get('auxiliar_id') is not None:
        data['auxiliar_id'] = filtros['auxiliar_id']
    if filtros.get('texto'):
        data['texto'] = filtros['texto']
    return data


def _periodo_label(filtros):
    return f"Corte al {filtros['fecha_corte_label']}"


def _base_where_sql(filtros, apply_auxiliar=True):
    clauses = [
        "c.tipo = 'PAGAR'",
        'c.activo = TRUE',
        'd.fecha_vencimiento <= %s',
    ]
    params = [filtros['fecha_corte']]

    if filtros.get('unidad_negocio_id'):
        clauses.append('c.unidad_negocio_id = %s')
        params.append(filtros['unidad_negocio_id'])

    if apply_auxiliar and filtros.get('auxiliar_id') is not None:
        if int(filtros['auxiliar_id']) == 0:
            clauses.append('c.auxiliar_id IS NULL')
        else:
            clauses.append('c.auxiliar_id = %s')
            params.append(filtros['auxiliar_id'])

    texto = filtros.get('texto')
    if texto:
        like = f'%{texto}%'
        clauses.append(
            """
            (
                c.codigo ILIKE %s
                OR c.nombre ILIKE %s
                OR COALESCE(c.descripcion, '') ILIKE %s
                OR COALESCE(d.observacion, '') ILIKE %s
                OR COALESCE(a.nombre, '') ILIKE %s
                OR COALESCE(a.razon_social, '') ILIKE %s
                OR COALESCE(a.nit_ci, '') ILIKE %s
                OR COALESCE(un.nombre, '') ILIKE %s
                OR COALESCE(un.codigo, '') ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like, like, like, like, like])

    return ' AND '.join(clauses), params


def _estado_where_sql(filtros):
    estado = filtros.get('estado') or 'pendiente'
    if estado == 'pendiente':
        return 'saldo_corte > 0'
    if estado == 'parcial':
        return 'pagado_corte_topado > 0 AND saldo_corte > 0'
    if estado == 'pagado':
        return 'saldo_corte <= 0'
    return 'TRUE'


def _base_cte_sql(where_sql):
    return f"""
        WITH pagos_detalle AS (
            SELECT
                pd.compromiso_detalle_id,
                COALESCE(SUM(pd.subtotal), 0) AS pagado_corte,
                MAX(p.fecha) AS ultimo_pago
            FROM contabilidad.pago_detalle pd
            INNER JOIN contabilidad.pago p ON p.id = pd.pago_id
            WHERE pd.tipo_linea::text = 'COMPROMISO'
              AND p.estado::text = 'CONFIRMADO'
              AND p.fecha <= %s
            GROUP BY pd.compromiso_detalle_id
        ),
        base AS (
            SELECT
                d.id AS detalle_id,
                c.id AS compromiso_id,
                COALESCE(c.auxiliar_id, 0) AS auxiliar_id,
                CASE
                    WHEN c.auxiliar_id IS NULL THEN 'Sin auxiliar asignado'
                    ELSE COALESCE(NULLIF(a.nombre, ''), NULLIF(a.razon_social, ''), 'Sin nombre')
                END AS auxiliar,
                COALESCE(a.nit_ci, '') AS documento_identidad,
                c.codigo,
                c.nombre,
                COALESCE(c.descripcion, '') AS descripcion,
                d.fecha_vencimiento,
                COALESCE(d.observacion, '') AS observacion,
                COALESCE(un.codigo, '') AS unidad_codigo,
                COALESCE(un.nombre, '') AS unidad_nombre,
                COALESCE(c.cuenta_contable, '') AS cuenta_contable,
                COALESCE(cta.nombre, '') AS cuenta_nombre,
                COALESCE(d.monto_programado, 0) AS monto_programado,
                LEAST(COALESCE(pg.pagado_corte, 0), COALESCE(d.monto_programado, 0)) AS pagado_corte_topado,
                GREATEST(COALESCE(d.monto_programado, 0) - COALESCE(pg.pagado_corte, 0), 0) AS saldo_corte,
                pg.ultimo_pago
            FROM contabilidad.compromiso c
            INNER JOIN contabilidad.compromiso_detalle d ON d.compromiso_id = c.id
            LEFT JOIN contabilidad.auxiliar a ON a.id = c.auxiliar_id
            LEFT JOIN contabilidad.unidad_negocio un ON un.id = c.unidad_negocio_id
            LEFT JOIN contabilidad.cuenta cta ON cta.codigo = c.cuenta_contable
            LEFT JOIN pagos_detalle pg ON pg.compromiso_detalle_id = d.id
            WHERE {where_sql}
        )
    """


def _fetch_general(filtros):
    where_sql, params = _base_where_sql(filtros, apply_auxiliar=True)
    estado_where = _estado_where_sql(filtros)
    sql = f"""
        {_base_cte_sql(where_sql)}
        SELECT
            auxiliar_id,
            auxiliar,
            documento_identidad AS documento,
            COUNT(DISTINCT compromiso_id) AS cantidad_documentos,
            COUNT(detalle_id) AS cantidad_vencimientos,
            COUNT(*) FILTER (WHERE pagado_corte_topado > 0 AND saldo_corte > 0) AS cantidad_parciales,
            COALESCE(SUM(monto_programado), 0) AS total_registrado,
            COALESCE(SUM(pagado_corte_topado), 0) AS total_pagado,
            COALESCE(SUM(saldo_corte), 0) AS saldo_pendiente,
            MIN(CASE WHEN saldo_corte > 0 THEN fecha_vencimiento END) AS primer_vencimiento_pendiente,
            MAX(ultimo_pago) AS ultimo_pago
        FROM base
        WHERE {estado_where}
        GROUP BY auxiliar_id, auxiliar, documento_identidad
        ORDER BY saldo_pendiente DESC, auxiliar ASC
    """
    rows = _db_rows(sql, [filtros['fecha_corte']] + params)
    total_registrado = Decimal('0.00')
    total_pagado = Decimal('0.00')
    total_saldo = Decimal('0.00')
    total_documentos = 0
    total_vencimientos = 0
    total_parciales = 0

    for row in rows:
        registrado = _to_decimal(row.get('total_registrado'))
        pagado = _to_decimal(row.get('total_pagado'))
        saldo = _to_decimal(row.get('saldo_pendiente'))
        parciales = int(row.get('cantidad_parciales') or 0)
        vencimientos = int(row.get('cantidad_vencimientos') or 0)
        documentos = int(row.get('cantidad_documentos') or 0)
        row['total_registrado'] = registrado
        row['total_pagado'] = pagado
        row['saldo_pendiente'] = saldo
        row['total_registrado_label'] = _money(registrado)
        row['total_pagado_label'] = _money(pagado)
        row['saldo_pendiente_label'] = _money(saldo)
        row['primer_vencimiento_pendiente_label'] = _date_label(row.get('primer_vencimiento_pendiente'))
        row['ultimo_pago_label'] = _date_label(row.get('ultimo_pago'))
        row['cantidad_documentos'] = documentos
        row['cantidad_vencimientos'] = vencimientos
        row['cantidad_parciales'] = parciales
        row['estado_label'] = 'Pagado' if saldo <= 0 else 'Parcial' if pagado > 0 else 'Pendiente'
        row['estado_badge'] = 'success' if saldo <= 0 else 'warning' if pagado > 0 else 'danger'
        total_registrado += registrado
        total_pagado += pagado
        total_saldo += saldo
        total_documentos += documentos
        total_vencimientos += vencimientos
        total_parciales += parciales

    resumen = {
        'total_registrado': total_registrado,
        'total_pagado': total_pagado,
        'saldo_pendiente': total_saldo,
        'cantidad_auxiliares': len(rows),
        'cantidad_documentos': total_documentos,
        'cantidad_vencimientos': total_vencimientos,
        'cantidad_parciales': total_parciales,
        'total_registrado_label': _money(total_registrado),
        'total_pagado_label': _money(total_pagado),
        'saldo_pendiente_label': _money(total_saldo),
        'moneda_label': MONEDA_OPERATIVA,
    }
    return rows, resumen


def _fetch_detalle(filtros):
    where_sql, params = _base_where_sql(filtros, apply_auxiliar=True)
    estado_where = _estado_where_sql(filtros)
    sql = f"""
        {_base_cte_sql(where_sql)}
        SELECT
            detalle_id,
            compromiso_id,
            codigo,
            nombre,
            descripcion,
            fecha_vencimiento,
            observacion,
            unidad_codigo,
            unidad_nombre,
            cuenta_contable,
            cuenta_nombre,
            monto_programado AS haber,
            pagado_corte_topado AS debe,
            saldo_corte AS saldo,
            ultimo_pago
        FROM base
        WHERE {estado_where}
        ORDER BY fecha_vencimiento ASC, codigo ASC, detalle_id ASC
    """
    rows = _db_rows(sql, [filtros['fecha_corte']] + params)
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')
    total_saldo = Decimal('0.00')
    for row in rows:
        debe = _to_decimal(row.get('debe'))
        haber = _to_decimal(row.get('haber'))
        saldo = _to_decimal(row.get('saldo'))
        row['documento'] = f"{row.get('codigo') or ''} · {row.get('nombre') or ''}".strip(' ·')
        row['fecha_label'] = _date_label(row.get('fecha_vencimiento'))
        row['ultimo_pago_label'] = _date_label(row.get('ultimo_pago'))
        row['glosa'] = row.get('observacion') or row.get('descripcion') or row.get('nombre') or ''
        row['unidad_label'] = f"{row.get('unidad_codigo') or ''} · {row.get('unidad_nombre') or ''}".strip(' ·')
        row['cuenta_label'] = f"{row.get('cuenta_contable') or ''} · {row.get('cuenta_nombre') or ''}".strip(' ·')
        row['debe'] = debe
        row['haber'] = haber
        row['saldo'] = saldo
        row['debe_label'] = _money(debe)
        row['haber_label'] = _money(haber)
        row['saldo_label'] = _money(saldo)
        row['estado_visual'] = 'PAGADO' if saldo <= 0 else 'PARCIAL' if debe > 0 else 'PENDIENTE'
        row['estado_badge'] = 'success' if saldo <= 0 else 'warning' if debe > 0 else 'danger'
        total_debe += debe
        total_haber += haber
        total_saldo += saldo
    resumen = {
        'total_debe': total_debe,
        'total_haber': total_haber,
        'total_saldo': total_saldo,
        'total_debe_label': _money(total_debe),
        'total_haber_label': _money(total_haber),
        'total_saldo_label': _money(total_saldo),
        'cantidad': len(rows),
        'moneda_label': MONEDA_OPERATIVA,
    }
    return rows, resumen


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
        self.drawString(15 * mm, 10 * mm, f'Generado por: {user}')
        self.drawRightString(page_width - 15 * mm, 10 * mm, f'Página {self._pageNumber} de {total_pages}')
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
        header_top = page_height - 17 * mm

        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2)
        canvas.line(x_left, header_top, x_right, header_top)
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 17)
        canvas.drawString(x_left, header_top - 19, title)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(x_left, header_top - 36, subtitle)
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
        canvas.line(x_left, header_top - 53, x_right, header_top - 53)
        canvas.restoreState()


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DXTMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=8.1, leading=10, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTSection', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=NAVY, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_CENTER, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTRight', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=8.4, textColor=TEXT, alignment=TA_RIGHT, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DXTCardLabel', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='DXTCardValue', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=13, textColor=NAVY, alignment=TA_LEFT))
    return styles


def _paragraph(value, style):
    return Paragraph(_safe_text(value), style)


def _make_table(columns, rows, widths, styles):
    header = [_paragraph(col.get('label', ''), styles['DXTCenter']) for col in columns]
    data = [header]
    for row in rows:
        rendered = []
        for idx, value in enumerate(row):
            align = columns[idx].get('align', 'left') if idx < len(columns) else 'left'
            style = styles['DXTRight'] if align == 'right' else styles['DXTCenter'] if align == 'center' else styles['DXTBody']
            rendered.append(_paragraph(value, style))
        data.append(rendered)
    table = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('BOX', (0, 0), (-1, -1), 0.75, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.5),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            table.setStyle(TableStyle([('BACKGROUND', (0, row_idx), (-1, row_idx), ROW_ALT)]))
    return table


def _build_pdf_general(filtros, rows, resumen, unidad):
    buffer = io.BytesIO()
    unidad_label = f"{unidad['codigo']} · {unidad['nombre']}" if unidad else 'Todas las unidades'
    context = {
        'title': 'Estado de cuentas por pagar',
        'subtitle': f"Corte {filtros['fecha_corte_label']} · {unidad_label} · {filtros['estado_label']}",
        'emitted_by': usuario_actual(),
        'logo_path': logo_path(),
    }
    doc = BrandedDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=47 * mm,
        bottomMargin=17 * mm,
        report_context=context,
    )
    styles = _pdf_styles()
    story = []

    cards = [
        ('Registrado', resumen['total_registrado_label']),
        ('Pagado', resumen['total_pagado_label']),
        ('Pendiente', resumen['saldo_pendiente_label']),
        ('Proveedores', str(resumen['cantidad_auxiliares'])),
        ('Parciales', str(resumen['cantidad_parciales'])),
    ]
    card_rows = [[[_paragraph(label, styles['DXTCardLabel']), _paragraph(value, styles['DXTCardValue'])] for label, value in cards]]
    card_table = Table(card_rows, colWidths=[doc.width / len(cards)] * len(cards))
    card_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_FILL),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.45, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(card_table)
    story.append(Spacer(1, 5 * mm))

    table_rows = []
    for row in rows:
        table_rows.append([
            row.get('estado_label') or '',
            row.get('auxiliar') or '',
            row.get('documento') or '',
            str(row.get('cantidad_documentos') or 0),
            str(row.get('cantidad_vencimientos') or 0),
            row.get('total_registrado_label') or '0.00',
            row.get('total_pagado_label') or '0.00',
            row.get('saldo_pendiente_label') or '0.00',
            row.get('primer_vencimiento_pendiente_label') or '',
        ])
    if not table_rows:
        table_rows = [['Sin datos', '', '', '0', '0', '0.00', '0.00', '0.00', '']]
    story.append(_make_table(
        [
            {'label': 'Estado', 'align': 'center'},
            {'label': 'Proveedor'},
            {'label': 'Doc.'},
            {'label': 'Comp.', 'align': 'center'},
            {'label': 'Venc.', 'align': 'center'},
            {'label': 'Registrado', 'align': 'right'},
            {'label': 'Pagado', 'align': 'right'},
            {'label': 'Pendiente', 'align': 'right'},
            {'label': 'Primer venc.', 'align': 'center'},
        ],
        table_rows,
        [21, 54, 23, 15, 15, 28, 28, 28, 28],
        styles,
    ))

    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


def _build_pdf_detalle(filtros, detalle, resumen, unidad, auxiliar):
    buffer = io.BytesIO()
    unidad_label = f"{unidad['codigo']} · {unidad['nombre']}" if unidad else 'Todas las unidades'
    auxiliar_label = auxiliar['nombre'] if auxiliar else 'Proveedor / auxiliar'
    context = {
        'title': 'Detalle de cuentas por pagar',
        'subtitle': f"{auxiliar_label} · Corte {filtros['fecha_corte_label']} · {unidad_label}",
        'emitted_by': usuario_actual(),
        'logo_path': logo_path(),
    }
    doc = BrandedDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=47 * mm,
        bottomMargin=17 * mm,
        report_context=context,
    )
    styles = _pdf_styles()
    story = [
        _paragraph(f"Registros {resumen['cantidad']} · Registrado {resumen['total_haber_label']} · Pagado {resumen['total_debe_label']} · Pendiente {resumen['total_saldo_label']}", styles['DXTSection']),
        Spacer(1, 3 * mm),
    ]
    table_rows = []
    for row in detalle:
        table_rows.append([
            row.get('estado_visual') or '',
            row.get('documento') or '',
            row.get('fecha_label') or '',
            row.get('glosa') or '',
            row.get('unidad_label') or '',
            row.get('haber_label') or '0.00',
            row.get('debe_label') or '0.00',
            row.get('saldo_label') or '0.00',
        ])
    if not table_rows:
        table_rows = [['Sin datos', '', '', '', '', '0.00', '0.00', '0.00']]
    story.append(_make_table(
        [
            {'label': 'Estado', 'align': 'center'},
            {'label': 'Documento'},
            {'label': 'Fecha', 'align': 'center'},
            {'label': 'Glosa'},
            {'label': 'Unidad'},
            {'label': 'Registrado', 'align': 'right'},
            {'label': 'Pagado', 'align': 'right'},
            {'label': 'Pendiente', 'align': 'right'},
        ],
        table_rows,
        [20, 43, 20, 62, 34, 24, 24, 24],
        styles,
    ))
    doc.build(story, canvasmaker=lambda *args, **kwargs: ReportCanvas(*args, report_context=context, **kwargs))
    buffer.seek(0)
    return buffer.getvalue()


@estado_cuentas_pagar_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    error = ''
    try:
        filtros = _build_filters(request.args)
        rows, resumen = _fetch_general(filtros)
    except ValueError as exc:
        filtros = _build_filters({})
        rows, resumen = _fetch_general(filtros)
        error = str(exc)
    except Exception as exc:
        filtros = _build_filters({})
        rows = []
        resumen = {
            'total_registrado_label': '0.00',
            'total_pagado_label': '0.00',
            'saldo_pendiente_label': '0.00',
            'cantidad_auxiliares': 0,
            'cantidad_documentos': 0,
            'cantidad_vencimientos': 0,
            'cantidad_parciales': 0,
            'moneda_label': MONEDA_OPERATIVA,
        }
        error = f'No se pudo cargar el estado de cuentas por pagar. {exc}'

    query_args = _query_args(filtros)
    return render_template(
        'estado_cuentas_pagar_index.html',
        filtros=filtros,
        periodo_label=_periodo_label(filtros),
        unidades=_fetch_unidades(),
        auxiliares=_fetch_auxiliares_pagar(),
        estados=ESTADOS_REPORTE,
        rows=rows,
        resumen=resumen,
        error=error,
        query_args=query_args,
    )


@estado_cuentas_pagar_bp.route('/detalle')
@login_required
@roles_required(ROLES_LECTURA)
def detalle():
    error = ''
    try:
        filtros = _build_filters(request.args)
        if filtros.get('auxiliar_id') is None:
            filtros['auxiliar_id'] = 0
        detalle_rows, resumen = _fetch_detalle(filtros)
    except Exception as exc:
        filtros = _build_filters({})
        detalle_rows = []
        resumen = {'total_debe_label': '0.00', 'total_haber_label': '0.00', 'total_saldo_label': '0.00', 'cantidad': 0, 'moneda_label': MONEDA_OPERATIVA}
        error = f'No se pudo cargar el detalle de cuentas por pagar. {exc}'

    unidad = _resolve_unidad(filtros.get('unidad_negocio_id'))
    auxiliar = _resolve_auxiliar(filtros.get('auxiliar_id'))
    query_args = _query_args(filtros)
    back_args = _query_args(filtros, include_auxiliar=True)
    return render_template(
        'estado_cuentas_pagar_detalle.html',
        filtros=filtros,
        periodo_label=_periodo_label(filtros),
        unidad=unidad,
        auxiliar=auxiliar,
        detalle=detalle_rows,
        resumen=resumen,
        error=error,
        query_args=query_args,
        back_args=back_args,
    )


@estado_cuentas_pagar_bp.route('/pdf')
@login_required
@roles_required(ROLES_LECTURA)
def pdf():
    try:
        filtros = _build_filters(request.args)
        rows, resumen = _fetch_general(filtros)
        unidad = _resolve_unidad(filtros.get('unidad_negocio_id'))
        pdf_bytes = _build_pdf_general(filtros, rows, resumen, unidad)
        filename = f"estado_cuentas_pagar_{filtros['fecha_corte'].strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF de cuentas por pagar. {exc}', status=500, mimetype='text/plain')


@estado_cuentas_pagar_bp.route('/pdf-auxiliar')
@login_required
@roles_required(ROLES_LECTURA)
def pdf_auxiliar():
    try:
        filtros = _build_filters(request.args)
        if filtros.get('auxiliar_id') is None:
            filtros['auxiliar_id'] = 0
        detalle_rows, resumen = _fetch_detalle(filtros)
        unidad = _resolve_unidad(filtros.get('unidad_negocio_id'))
        auxiliar = _resolve_auxiliar(filtros.get('auxiliar_id'))
        pdf_bytes = _build_pdf_detalle(filtros, detalle_rows, resumen, unidad, auxiliar)
        aux = filtros.get('auxiliar_id') if filtros.get('auxiliar_id') is not None else 0
        filename = f"estado_cuentas_pagar_auxiliar_{aux}_{filtros['fecha_corte'].strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.pdf"
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename={filename}'})
    except Exception as exc:
        return Response(f'No se pudo generar el PDF por proveedor. {exc}', status=500, mimetype='text/plain')


@estado_cuentas_pagar_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    return render_template('estado_cuentas_pagar_help.html')
