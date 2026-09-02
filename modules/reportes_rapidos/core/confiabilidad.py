# ============================================================
# DXT CONTA - Reportes Rapidos - Confiabilidad e interpretacion
# ============================================================

from __future__ import annotations


DEFAULT_CRITERIO = {
    'fuente_datos': 'Consulta directa a tablas operativas del sistema DXT.',
    'criterio_reporte': 'Se aplican los filtros visibles de la pantalla y se respeta el estado operativo registrado en la fuente.',
    'advertencia': 'Revise el help del reporte si necesita conocer el alcance exacto de la informacion mostrada.',
}

REPORT_CRITERIA = {
    'atencion_inmediata': {
        'fuente_datos': 'Compromisos pendientes, pagos/cobros en borrador, facturas con saldo, arqueos, procesos criticos y vigencias de publicidad.',
        'criterio_reporte': 'Muestra alertas vencidas o de atencion diaria; no reemplaza los reportes legales ni los estados financieros.',
        'advertencia': 'Las alertas son operativas y priorizan riesgo/urgencia para facilitar seguimiento diario.',
    },
    'agenda_financiera_hoy': {
        'fuente_datos': 'Compromisos, documentos por cobrar y facturas electrónicas pendientes.',
        'criterio_reporte': 'Muestra pendientes por vencimiento; la opción Sin vencimiento lista cobrables sin fecha definida.',
        'advertencia': 'El neto se calcula por moneda como pendientes por cobrar menos pendientes por pagar.',
    },
    'cuentas_por_pagar_pendientes': {
        'fuente_datos': 'contabilidad.compromiso y contabilidad.compromiso_detalle.',
        'criterio_reporte': 'Incluye compromisos tipo PAGAR con estado PENDIENTE, PARCIAL o INCUMPLIDO y saldo pendiente mayor a cero.',
        'advertencia': 'No incluye compromisos cancelados o sin saldo pendiente.',
    },
    'cuentas_por_pagar_por_proveedor': {
        'fuente_datos': 'contabilidad.compromiso y contabilidad.compromiso_detalle agrupados por auxiliar proveedor.',
        'criterio_reporte': 'Agrupa compromisos tipo PAGAR con saldo pendiente por proveedor y moneda; el estado operativo se calcula por importe pagado y fecha base.',
        'advertencia': 'Un proveedor sin auxiliar asociado puede mostrarse como Sin proveedor para control de datos incompletos.',
    },
    'cuentas_por_pagar_por_unidad_rubro': {
        'fuente_datos': 'Compromisos por pagar, unidad de negocio y rubro/cuenta contable disponible.',
        'criterio_reporte': 'Agrupa obligaciones pendientes por unidad y rubro operativo; si no existe rubro, usa la cuenta contable como referencia.',
        'advertencia': 'La calidad del agrupado depende de que cada compromiso tenga unidad y rubro correctamente registrados.',
    },
    'cuentas_por_cobrar_pendientes': {
        'fuente_datos': 'Compromisos por cobrar, documentos por cobrar y facturas electrónicas contabilizadas con saldo pendiente.',
        'criterio_reporte': 'Consolida toda la cartera pendiente de cobro, separando saldos por moneda y filtrando por vencimiento, origen y unidad.',
        'advertencia': 'Los pendientes sin vencimiento no se tratan como vencidos; no representan dinero en caja o banco hasta confirmar el cobro.',
    },
    'cuentas_por_cobrar_por_cliente': {
        'fuente_datos': 'Compromisos por cobrar, documentos por cobrar y facturas electrónicas contabilizadas con saldo pendiente.',
        'criterio_reporte': 'Agrupa la cartera pendiente por cliente y moneda; no mezcla saldos de monedas distintas.',
        'advertencia': 'Los pendientes sin vencimiento no se tratan como vencidos y aparecen agrupados por cliente para gestión de cobranza.',
    },
    'cuentas_por_cobrar_por_unidad_rubro': {
        'fuente_datos': 'Compromisos por cobrar, unidad de negocio y rubro/cuenta contable disponible.',
        'criterio_reporte': 'Agrupa cuentas por cobrar pendientes por unidad y rubro operativo; si no existe rubro, usa la cuenta contable como referencia.',
        'advertencia': 'La calidad del agrupado depende de que cada compromiso tenga unidad y rubro correctamente registrados.',
    },
    'pagos_realizados': {
        'fuente_datos': 'contabilidad.pago y tablas relacionadas de auxiliar, caja/banco, unidad y rubro.',
        'criterio_reporte': 'Muestra pagos registrados en el periodo filtrado segun fecha de pago y estado seleccionado.',
        'advertencia': 'Si el estado es Todos, el reporte puede incluir borradores o anulados segun el filtro elegido por el usuario.',
    },
    'pagos_por_proveedor': {
        'fuente_datos': 'contabilidad.pago cruzado con auxiliares proveedores.',
        'criterio_reporte': 'Lista pagos por proveedor segun fecha, estado y unidad de negocio.',
        'advertencia': 'Use el estado Confirmado cuando requiera un reporte operativo de pagos efectivos.',
    },
    'pagos_por_referencia_publicitaria': {
        'fuente_datos': 'contabilidad.pago con campos de referencia publicitaria.',
        'criterio_reporte': 'Lista pagos vinculados a codigo o elemento publicitario registrado en el pago.',
        'advertencia': 'No infiere referencias publicitarias si el pago fue registrado sin esos campos.',
    },
    'cobros_realizados': {
        'fuente_datos': 'contabilidad.cobro y tablas relacionadas de auxiliar, caja/banco, unidad y rubro.',
        'criterio_reporte': 'Muestra cobros registrados en el periodo filtrado segun fecha de cobro y estado seleccionado.',
        'advertencia': 'Use el estado Confirmado cuando requiera un reporte operativo de cobros efectivos.',
    },
    'cobros_por_cliente': {
        'fuente_datos': 'contabilidad.cobro cruzado con auxiliares clientes.',
        'criterio_reporte': 'Lista cobros por cliente segun fecha, estado y unidad de negocio.',
        'advertencia': 'Los datos dependen de que el cobro tenga cliente correctamente asociado.',
    },
    'cobros_por_referencia_publicitaria': {
        'fuente_datos': 'contabilidad.cobro con campos de referencia publicitaria.',
        'criterio_reporte': 'Lista cobros vinculados a codigo o elemento publicitario registrado en el cobro.',
        'advertencia': 'No infiere referencias publicitarias si el cobro fue registrado sin esos campos.',
    },
    'clientes_registrados_contabilidad': {
        'fuente_datos': 'contabilidad.auxiliar con tipo CLIENTE.',
        'criterio_reporte': 'Lista clientes contables registrados y filtra segun estado/condicion seleccionada.',
        'advertencia': 'No equivale necesariamente al cliente comercial de publicidad si no existe sincronizacion entre esquemas.',
    },
    'proveedores_registrados': {
        'fuente_datos': 'contabilidad.auxiliar con tipo PROVEEDOR.',
        'criterio_reporte': 'Lista proveedores contables registrados y filtra segun estado/condicion seleccionada.',
        'advertencia': 'Los proveedores sin datos basicos deben revisarse en el reporte de datos incompletos.',
    },
    'clientes_comerciales_publicidad': {
        'fuente_datos': 'publicidad.cliente.',
        'criterio_reporte': 'Lista clientes comerciales del subsistema de publicidad segun estado y filtros disponibles.',
        'advertencia': 'Este reporte no reemplaza el registro de clientes contables del esquema contabilidad.',
    },
    'facturas_saldo_pendiente': {
        'fuente_datos': 'contabilidad.factura_electronica, documento_asiento, factura_aplicacion y factura_regularizacion.',
        'criterio_reporte': 'Lista facturas electrónicas por fecha de emisión. Debe es el importe facturado, Haber son cobros o cierres aplicados y Saldo es lo pendiente.',
        'advertencia': 'El reporte es operativo de cobranza; no reemplaza libros tributarios ni reportes fiscales.',
    },
    'facturas_por_estado': {
        'fuente_datos': 'contabilidad.factura_electronica, documento_asiento, factura_aplicacion y factura_regularizacion.',
        'criterio_reporte': 'Clasifica facturas en con saldo, recibidas, cerradas o todas usando estado operativo, contabilización y aplicaciones registradas.',
        'advertencia': 'La fecha filtrada siempre es la fecha de emisión de la factura.',
    },
    'publicidad_licencias_vigentes': {
        'fuente_datos': 'publicidad.licencia y datos del elemento/estructura publicitaria.',
        'criterio_reporte': 'Incluye licencias habilitadas cuya vigencia cubre la fecha o rango seleccionado.',
        'advertencia': 'La vigencia depende de las fechas desde/hasta registradas en publicidad.',
    },
    'publicidad_licencias_por_vencer': {
        'fuente_datos': 'publicidad.licencia y datos del elemento/estructura publicitaria.',
        'criterio_reporte': 'Lista licencias habilitadas que vencen dentro del horizonte seleccionado.',
        'advertencia': 'Revise renovaciones oportunamente para evitar vencimientos operativos.',
    },
    'publicidad_licencias_vencidas': {
        'fuente_datos': 'publicidad.licencia y datos del elemento/estructura publicitaria.',
        'criterio_reporte': 'Lista licencias habilitadas o registradas cuya fecha hasta ya vencio respecto al corte seleccionado.',
        'advertencia': 'Una licencia vencida no implica necesariamente baja del elemento; requiere revision administrativa.',
    },
    'publicidad_contratos_vigentes': {
        'fuente_datos': 'publicidad.contrato y datos de cliente/elemento asociados.',
        'criterio_reporte': 'Incluye contratos vigentes segun fecha de corte y estado operativo.',
        'advertencia': 'La vigencia depende de las fechas contractuales registradas.',
    },
    'publicidad_contratos_por_vencer': {
        'fuente_datos': 'publicidad.contrato y datos de cliente/elemento asociados.',
        'criterio_reporte': 'Lista contratos que vencen dentro del horizonte seleccionado.',
        'advertencia': 'El reporte sirve para seguimiento comercial y no modifica estados contractuales.',
    },
    'publicidad_cotizaciones_comerciales': {
        'fuente_datos': 'publicidad.cotizacion y datos comerciales asociados.',
        'criterio_reporte': 'Lista cotizaciones segun fecha, estado y cliente comercial.',
        'advertencia': 'Una cotizacion no representa ingreso contable hasta su aprobacion y registro correspondiente.',
    },
    'publicidad_elementos_activos': {
        'fuente_datos': 'publicidad.elemento_publicitario y vistas de ubicacion/estructura.',
        'criterio_reporte': 'Lista elementos publicitarios activos o habilitados segun el estado seleccionado.',
        'advertencia': 'La disponibilidad comercial depende de contratos/licencias vigentes, no solo del estado del elemento.',
    },
    'publicidad_mantenimientos_elementos': {
        'fuente_datos': 'publicidad.mantenimiento_elemento y datos del elemento publicitario.',
        'criterio_reporte': 'Lista mantenimientos segun fecha, estado y unidad de negocio.',
        'advertencia': 'El costo mostrado corresponde al registro de mantenimiento, no necesariamente a pago contable confirmado.',
    },
    'publicidad_pagos_fum': {
        'fuente_datos': 'contabilidad.asiento complementado con publicidad.pago_fum_documento si existe PDF asociado.',
        'criterio_reporte': 'Parte de asientos contables relacionados con FUM, canon o patente; el PDF se muestra como respaldo documental opcional.',
        'advertencia': 'Puede mostrar pagos sin PDF cargado; la columna PDF indica si existe respaldo documental en publicidad.',
    },
    'operaciones_en_borrador': {
        'fuente_datos': 'Pagos, cobros, comprobantes y documentos operativos en estado BORRADOR.',
        'criterio_reporte': 'Lista operaciones no confirmadas que requieren revision o finalizacion.',
        'advertencia': 'Los borradores normalmente no deben tomarse como movimiento definitivo.',
    },
    'operaciones_anuladas': {
        'fuente_datos': 'Pagos, cobros, comprobantes y documentos operativos en estado ANULADO.',
        'criterio_reporte': 'Lista operaciones anuladas para control y trazabilidad.',
        'advertencia': 'Una operacion anulada no debe sumarse como movimiento efectivo.',
    },
    'movimientos_sin_asiento': {
        'fuente_datos': 'Pagos, cobros, compras y ventas con referencia a asiento contable.',
        'criterio_reporte': 'Identifica operaciones sin asiento, con asiento pendiente o con asiento anulado segun la relacion disponible.',
        'advertencia': 'Use este reporte para depuracion antes de cierres o revisiones contables.',
    },
    'datos_incompletos': {
        'fuente_datos': 'Auxiliares, clientes, proveedores, documentos y objetos operativos revisados por campos minimos.',
        'criterio_reporte': 'Identifica registros con datos basicos faltantes o inconsistentes para correccion operativa.',
        'advertencia': 'Un dato incompleto no siempre bloquea la operacion, pero reduce la confiabilidad de reportes y documentos.',
    },
}


def get_quality_context(report_id: str) -> dict:
    data = REPORT_CRITERIA.get(str(report_id or '').strip(), DEFAULT_CRITERIO)
    merged = dict(DEFAULT_CRITERIO)
    merged.update(data)
    return merged


def apply_quality_context(report, payload: dict) -> dict:
    report_id = getattr(report, 'REPORT_ID', '')
    data = get_quality_context(report_id)
    payload['fuente_datos'] = data.get('fuente_datos', '')
    payload['criterio_reporte'] = data.get('criterio_reporte', '')
    payload['advertencia_reporte'] = data.get('advertencia', '')

    summary = payload.setdefault('summary', {})
    summary['fuente_datos'] = payload['fuente_datos']
    summary['criterio_reporte'] = payload['criterio_reporte']
    summary['advertencia_reporte'] = payload['advertencia_reporte']
    return payload
