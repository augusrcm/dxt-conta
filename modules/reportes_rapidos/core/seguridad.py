# ============================================================
# DXT CONTA - Reportes Rápidos - Seguridad común
# ============================================================


def require_report(report_id, registry):
    report_id = (report_id or '').strip()
    report = registry.get(report_id)
    if report is None:
        raise ValueError('El reporte solicitado no está disponible.')
    return report
