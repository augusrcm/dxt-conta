# ============================================================
# DXT CONTA - Reportes Rápidos - Registro de reportes
# ============================================================

from modules.reportes_rapidos.core.confiabilidad import get_quality_context
from modules.reportes_rapidos.reports import (
    agenda_financiera_hoy,
    atencion_inmediata,
    cuentas_por_pagar_pendientes,
    cuentas_por_pagar_por_proveedor,
    cuentas_por_cobrar_pendientes,
    cuentas_por_cobrar_por_cliente,
    cuentas_por_cobrar_por_unidad_rubro,
    pagos_realizados,
    pagos_por_proveedor,
    cobros_realizados,
    cobros_por_cliente,
    operaciones_en_borrador,
    operaciones_anuladas,
    movimientos_sin_asiento,
    datos_incompletos,
)


REPORTES = {
    atencion_inmediata.REPORT_ID: atencion_inmediata,
    agenda_financiera_hoy.REPORT_ID: agenda_financiera_hoy,
    cuentas_por_cobrar_pendientes.REPORT_ID: cuentas_por_cobrar_pendientes,
    cuentas_por_cobrar_por_cliente.REPORT_ID: cuentas_por_cobrar_por_cliente,
    cuentas_por_cobrar_por_unidad_rubro.REPORT_ID: cuentas_por_cobrar_por_unidad_rubro,
    cuentas_por_pagar_pendientes.REPORT_ID: cuentas_por_pagar_pendientes,
    cuentas_por_pagar_por_proveedor.REPORT_ID: cuentas_por_pagar_por_proveedor,
    cobros_realizados.REPORT_ID: cobros_realizados,
    cobros_por_cliente.REPORT_ID: cobros_por_cliente,
    pagos_realizados.REPORT_ID: pagos_realizados,
    pagos_por_proveedor.REPORT_ID: pagos_por_proveedor,
    operaciones_en_borrador.REPORT_ID: operaciones_en_borrador,
    operaciones_anuladas.REPORT_ID: operaciones_anuladas,
    movimientos_sin_asiento.REPORT_ID: movimientos_sin_asiento,
    datos_incompletos.REPORT_ID: datos_incompletos,
}


REPORTE_INICIAL = atencion_inmediata.REPORT_ID


def get_report(report_id):
    return REPORTES.get(report_id)


def list_reports():
    return [
        {
            'id': report.REPORT_ID,
            'titulo': report.TITLE,
            'descripcion': getattr(report, 'DESCRIPTION', ''),
            'icono': getattr(report, 'ICON', 'fas fa-file-lines'),
            'alcances': [{'id': key, 'label': value} for key, value in report.ALCANCES.items()],
            'grupos': [{'id': key, 'label': value} for key, value in report.GRUPOS.items()],
            'alcance_default': getattr(report, 'DEFAULT_ALCANCE', 'hoy'),
            'grupo_default': getattr(report, 'DEFAULT_GRUPO', ''),
            'alcance_label': getattr(report, 'FILTER_ALCANCE_LABEL', 'Alcance'),
            'grupo_label': getattr(report, 'FILTER_GROUP_LABEL', 'Grupo'),
            'fecha_label': getattr(report, 'FILTER_DATE_LABEL', 'Fecha de atención'),
            'help_title': getattr(report, 'HELP_TITLE', getattr(report, 'TITLE', 'Reporte')),
            'help_intro': getattr(report, 'HELP_INTRO', getattr(report, 'DESCRIPTION', '')),
            'help_items': list(getattr(report, 'HELP_ITEMS', [])),
            'show_unidad_filter': bool(getattr(report, 'FILTER_UNIDAD_VISIBLE', True)),
            'hide_fecha_base_filter': bool(getattr(report, 'HIDE_FECHA_BASE_FILTER', False)),
            'hide_hoy_button': bool(getattr(report, 'HIDE_HOY_BUTTON', False)),
            'calidad': get_quality_context(report.REPORT_ID),
        }
        for report in REPORTES.values()
    ]
