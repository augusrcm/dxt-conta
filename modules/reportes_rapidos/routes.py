# ============================================================
# DXT CONTA - Reportes Rápidos - Rutas principales
# ============================================================

from __future__ import annotations

from datetime import date, datetime

from flask import Response, render_template, request, url_for

from modules.reportes_rapidos import reportes_rapidos_bp
from modules.reportes_rapidos.core.catalogos import obtener_unidades_negocio
from modules.reportes_rapidos.core.config import MAX_ROWS_EXPORT, MAX_ROWS_SCREEN, ROLES_LECTURA
from modules.reportes_rapidos.core.export_excel import build_excel
from modules.reportes_rapidos.core.export_pdf import build_pdf
from modules.reportes_rapidos.core.confiabilidad import apply_quality_context
from modules.reportes_rapidos.core.responses import json_error, json_ok
from modules.reportes_rapidos.core.seguridad import require_report
from modules.reportes_rapidos.registry import REPORTE_INICIAL, REPORTES, list_reports
from utils.decorators import login_required, roles_required


def _initial_report():
    return require_report(REPORTE_INICIAL, REPORTES)


def _frontend_reports():
    reports = []
    for item in list_reports():
        report_id = item['id']
        enriched = dict(item)
        enriched['urls'] = {
            'data': url_for('reportes_rapidos.report_data', report_id=report_id),
            'excel': url_for('reportes_rapidos.report_excel', report_id=report_id),
            'pdf': url_for('reportes_rapidos.report_pdf', report_id=report_id),
        }
        reports.append(enriched)
    return reports


@reportes_rapidos_bp.route('/')
@login_required
@roles_required(ROLES_LECTURA)
def index():
    hoy = date.today()
    return render_template(
        'reportes_rapidos_index.html',
        fecha_hoy=hoy.isoformat(),
        unidades_negocio=obtener_unidades_negocio(),
        reportes=_frontend_reports(),
        reporte_inicial=_initial_report().REPORT_ID,
    )


@reportes_rapidos_bp.route('/api/<report_id>')
@login_required
@roles_required(ROLES_LECTURA)
def report_data(report_id):
    try:
        report = require_report(report_id, REPORTES)
        filtros = report.validate_filters(request.args)
        payload = report.build_payload(filtros, limit_rows=MAX_ROWS_SCREEN)
        payload = apply_quality_context(report, payload)
        return json_ok(**payload)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:  # pragma: no cover - defensa operativa
        return json_error(f'No se pudo generar el reporte. {exc}', 500)


@reportes_rapidos_bp.route('/excel/<report_id>')
@login_required
@roles_required(ROLES_LECTURA)
def report_excel(report_id):
    try:
        report = require_report(report_id, REPORTES)
        filtros = report.validate_filters(request.args)
        payload = report.build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        payload = apply_quality_context(report, payload)
        excel_bytes = build_excel(report, payload)
        nombre = f"{report.FILE_SLUG}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={nombre}'},
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:  # pragma: no cover - defensa operativa
        return json_error(f'No se pudo generar el Excel del reporte. {exc}', 500)


@reportes_rapidos_bp.route('/pdf/<report_id>')
@login_required
@roles_required(ROLES_LECTURA)
def report_pdf(report_id):
    try:
        report = require_report(report_id, REPORTES)
        filtros = report.validate_filters(request.args)
        payload = report.build_payload(filtros, limit_rows=MAX_ROWS_EXPORT)
        payload = apply_quality_context(report, payload)
        pdf_bytes = build_pdf(report, payload)
        nombre = f"{report.FILE_SLUG}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename={nombre}'},
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:  # pragma: no cover - defensa operativa
        return json_error(f'No se pudo generar el PDF del reporte. {exc}', 500)


@reportes_rapidos_bp.route('/help')
@login_required
@roles_required(ROLES_LECTURA)
def help():
    reportes = _frontend_reports()
    reporte_id = (request.args.get('reporte') or REPORTE_INICIAL).strip()
    reporte_actual = next((item for item in reportes if item['id'] == reporte_id), None)
    if reporte_actual is None and reportes:
        reporte_actual = reportes[0]
    return render_template(
        'reportes_rapidos_help.html',
        reportes=reportes,
        reporte_actual=reporte_actual,
    )
