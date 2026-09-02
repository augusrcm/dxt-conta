# ============================================================
# DXT CONTA - Dashboard Ejecutivo - Constructor principal
# ============================================================

from __future__ import annotations

from datetime import datetime

from modules.dashboard.services.alertas import build_alertas
from modules.dashboard.services.graficos import build_charts
from modules.dashboard.services.indicadores import build_cards
from modules.dashboard.services.utils import money_note, period_label, usuario_actual


def build_dashboard_payload(filters: dict) -> dict:
    return {
        'titulo': 'Dashboard Ejecutivo',
        'subtitulo': 'Situación financiera, alertas y vencimientos relevantes',
        'periodo': period_label(filters),
        'fecha_corte': filters['fecha_corte'].isoformat(),
        'fecha_desde': filters['fecha_desde'].isoformat(),
        'fecha_hasta': filters['fecha_hasta'].isoformat(),
        'rango': filters['rango'],
        'rango_label': filters['rango_label'],
        'unidad_negocio_id': filters['unidad_negocio_id'] or '',
        'moneda_codigo': 'BOB',
        'moneda_note': money_note('BOB'),
        'emitido_en': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'generado_por': usuario_actual(),
        'cards': build_cards(filters),
        'charts': build_charts(filters),
        'alertas': build_alertas(filters),
        'criterio': (
            'Lectura ejecutiva basada en compromisos pendientes, pagos/cobros confirmados en Bs, '
            'alertas críticas y vencimientos de publicidad. No reemplaza los reportes detallados.'
        ),
    }
