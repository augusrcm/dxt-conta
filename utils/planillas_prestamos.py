from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

Q2 = Decimal('0.01')


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def sincronizar_prestamos_borrador(
    db,
    *,
    planilla: dict[str, Any],
    tipo_persona: str,
    recalcular_detalle: Callable[[Any, int], None],
    recalcular_planilla: Callable[[Any, int], None],
) -> int:
    """Sincroniza solamente el concepto automático ANTICIPO_PRESTAMO de una planilla BORRADOR."""
    if str(planilla.get('estado')) != 'BORRADOR':
        raise ValueError('La sincronización de préstamos solo puede ejecutarse sobre una planilla BORRADOR.')
    planilla_id = int(planilla['id'])
    detalles = db.execute_query(
        """
        SELECT id, persona_id
        FROM contabilidad.planilla_detalle
        WHERE planilla_periodo_id = %s
          AND estado <> 'EXCLUIDO'
        ORDER BY id
        """,
        (planilla_id,),
    )
    cambios = 0
    for detalle in detalles:
        detalle_id = int(detalle['id'])
        persona_id = int(detalle['persona_id'])
        cuotas = db.execute_query(
            """
            SELECT pc.id AS cuota_id, pc.prestamo_id, pc.numero_cuota, pc.saldo_pendiente,
                   p.codigo, p.unidad_negocio_id AS unidad_acreedora_id
            FROM contabilidad.planilla_prestamo_cuota pc
            JOIN contabilidad.planilla_prestamo p ON p.id = pc.prestamo_id
            WHERE p.tipo_persona = %s
              AND p.persona_id = %s
              AND p.moneda_codigo = %s
              AND p.estado IN ('CONFIRMADO','PARCIAL')
              AND pc.gestion = %s
              AND pc.mes = %s
              AND pc.estado IN ('PENDIENTE','PARCIAL')
              AND pc.saldo_pendiente > 0
            ORDER BY p.id, pc.numero_cuota
            """,
            (tipo_persona, persona_id, planilla['moneda_codigo'], int(planilla['gestion']), int(planilla['mes'])),
        )
        existentes = db.execute_query(
            """
            SELECT id
            FROM contabilidad.planilla_detalle_concepto
            WHERE planilla_detalle_id = %s
              AND codigo_concepto = 'ANTICIPO_PRESTAMO'
              AND COALESCE(atributos->>'origen','') = 'ANTICIPO_PRESTAMO_PROGRAMADO'
            ORDER BY id
            """,
            (detalle_id,),
        )
        if len(existentes) > 1:
            raise ValueError(f'La fila {detalle_id} tiene más de un concepto automático ANTICIPO_PRESTAMO.')
        total = sum((money(c.get('saldo_pendiente')) for c in cuotas), Decimal('0.00')).quantize(Q2)
        if total > 0:
            attrs = {
                'origen': 'ANTICIPO_PRESTAMO_PROGRAMADO',
                'sincronizado_al_consolidar': True,
                'prestamo_cuotas': [
                    {
                        'cuota_id': int(c['cuota_id']),
                        'prestamo_id': int(c['prestamo_id']),
                        'codigo': c['codigo'],
                        'numero_cuota': int(c['numero_cuota']),
                        'monto': str(money(c['saldo_pendiente'])),
                        'unidad_acreedora_id': int(c['unidad_acreedora_id']),
                    }
                    for c in cuotas
                ],
            }
            if existentes:
                db.execute_update(
                    """
                    UPDATE contabilidad.planilla_detalle_concepto
                    SET monto = %s,
                        justificativo = %s,
                        atributos = %s::jsonb,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (total, 'Descuento automático sincronizado al consolidar la planilla.', _json(attrs), int(existentes[0]['id'])),
                )
            else:
                sec = db.execute_query(
                    "SELECT COALESCE(MAX(secuencia),0) + 1 AS sec FROM contabilidad.planilla_detalle_concepto WHERE planilla_detalle_id = %s",
                    (detalle_id,),
                )[0]['sec']
                db.execute_insert(
                    """
                    INSERT INTO contabilidad.planilla_detalle_concepto (
                        planilla_periodo_id, planilla_detalle_id, concepto_id, secuencia,
                        codigo_concepto, nombre_concepto, tipo_concepto, impacto_liquido,
                        monto, porcentaje_aplicado, cuenta_debe_codigo, cuenta_haber_codigo,
                        justificativo, observacion, atributos, creado_en
                    ) VALUES (%s, %s, NULL, %s, 'ANTICIPO_PRESTAMO', 'Anticipos / préstamos programados',
                              'DESCUENTO', 'RESTA', %s, NULL, NULL, NULL, %s, NULL, %s::jsonb, CURRENT_TIMESTAMP)
                    """,
                    (planilla_id, detalle_id, int(sec), total, 'Descuento automático sincronizado al consolidar la planilla.', _json(attrs)),
                    return_id=False,
                )
            cambios += 1
        elif existentes:
            db.execute_delete(
                "DELETE FROM contabilidad.planilla_detalle_concepto WHERE id = %s",
                (int(existentes[0]['id']),),
            )
            cambios += 1
        if total > 0 or existentes:
            recalcular_detalle(db, detalle_id)
    if cambios:
        recalcular_planilla(db, planilla_id)
    return cambios


def aplicar_cuotas_planilla(
    db,
    *,
    planilla: dict[str, Any],
    fecha_operacion: date,
    usuario: str,
) -> list[int]:
    planilla_id = int(planilla['id'])
    conceptos = db.execute_query(
        """
        SELECT dc.id, dc.planilla_detalle_id, dc.monto, dc.atributos,
               pd.persona_id, pd.unidad_negocio_id AS unidad_retenedora_id
        FROM contabilidad.planilla_detalle_concepto dc
        JOIN contabilidad.planilla_detalle pd ON pd.id = dc.planilla_detalle_id
        WHERE dc.planilla_periodo_id = %s
          AND pd.estado <> 'EXCLUIDO'
          AND dc.codigo_concepto = 'ANTICIPO_PRESTAMO'
          AND dc.monto > 0
          AND COALESCE(dc.atributos->>'origen','') = 'ANTICIPO_PRESTAMO_PROGRAMADO'
        ORDER BY dc.id
        """,
        (planilla_id,),
    )
    aplicaciones_ids: list[int] = []
    for concepto in conceptos:
        monto_disponible = money(concepto['monto'])
        attrs = concepto.get('atributos') or {}
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        cuotas = attrs.get('prestamo_cuotas') or []
        for cuota_ref in cuotas:
            if monto_disponible <= 0:
                break
            cuota_id = int(cuota_ref['cuota_id'])
            cuota_rows = db.execute_query(
                """
                SELECT pc.*, p.moneda_codigo, p.tipo_cambio, p.persona_id,
                       p.unidad_negocio_id AS unidad_acreedora_id
                FROM contabilidad.planilla_prestamo_cuota pc
                JOIN contabilidad.planilla_prestamo p ON p.id = pc.prestamo_id
                WHERE pc.id = %s
                  AND p.persona_id = %s
                  AND pc.gestion = %s
                  AND pc.mes = %s
                  AND pc.estado IN ('PENDIENTE','PARCIAL')
                FOR UPDATE
                """,
                (cuota_id, int(concepto['persona_id']), int(planilla['gestion']), int(planilla['mes'])),
            )
            if not cuota_rows:
                continue
            cuota = dict(cuota_rows[0])
            if db.execute_query(
                """
                SELECT 1 FROM contabilidad.planilla_prestamo_aplicacion
                WHERE cuota_id = %s AND planilla_periodo_id = %s AND tipo_aplicacion = 'PLANILLA'
                LIMIT 1
                """,
                (cuota_id, planilla_id),
            ):
                raise ValueError(f'La cuota {cuota_id} ya tiene una aplicación de esta planilla.')
            saldo = money(cuota['saldo_pendiente'])
            aplicar = min(saldo, monto_disponible).quantize(Q2)
            if aplicar <= 0:
                continue
            nuevo_aplicado = money(cuota['monto_aplicado']) + aplicar
            nuevo_saldo = money(saldo - aplicar)
            estado = 'APLICADA' if nuevo_saldo <= 0 else 'PARCIAL'
            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo_cuota
                SET monto_aplicado = %s, saldo_pendiente = %s, estado = %s,
                    planilla_periodo_id = %s, planilla_detalle_id = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (nuevo_aplicado, nuevo_saldo, estado, planilla_id, int(concepto['planilla_detalle_id']), cuota_id),
            )
            app_attrs = {
                'origen': 'ANTICIPO_PRESTAMO_PROGRAMADO',
                'fecha_operacion': fecha_operacion.isoformat(),
                'unidad_retenedora_id': int(concepto['unidad_retenedora_id']),
                'unidad_acreedora_id': int(cuota['unidad_acreedora_id']),
            }
            app_id = db.execute_insert(
                """
                INSERT INTO contabilidad.planilla_prestamo_aplicacion (
                    prestamo_id, cuota_id, tipo_aplicacion, fecha_aplicacion, monto_aplicado,
                    moneda_codigo, tipo_cambio, planilla_periodo_id, planilla_detalle_id,
                    referencia, justificativo, creado_por, atributos, creado_en
                ) VALUES (%s, %s, 'PLANILLA', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                """,
                (
                    int(cuota['prestamo_id']), cuota_id, fecha_operacion, aplicar,
                    cuota['moneda_codigo'], cuota['tipo_cambio'], planilla_id, int(concepto['planilla_detalle_id']),
                    planilla['codigo'], f'Descuento aplicado por planilla {planilla["codigo"]}', usuario, _json(app_attrs),
                ),
            )
            aplicaciones_ids.append(int(app_id))
            resumen = db.execute_query(
                """
                SELECT COALESCE(SUM(monto_aplicado),0) AS aplicado,
                       COALESCE(SUM(saldo_pendiente),0) AS saldo
                FROM contabilidad.planilla_prestamo_cuota
                WHERE prestamo_id = %s AND estado <> 'ANULADA'
                """,
                (int(cuota['prestamo_id']),),
            )[0]
            saldo_p = money(resumen['saldo'])
            aplicado_p = money(resumen['aplicado'])
            estado_p = 'PAGADO' if saldo_p <= 0 else ('PARCIAL' if aplicado_p > 0 else 'CONFIRMADO')
            db.execute_update(
                """
                UPDATE contabilidad.planilla_prestamo
                SET monto_recuperado = %s, saldo_pendiente = %s, estado = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (aplicado_p, saldo_p, estado_p, int(cuota['prestamo_id'])),
            )
            monto_disponible = money(monto_disponible - aplicar)
        if monto_disponible != 0:
            raise ValueError(
                f'El concepto automático de préstamos de la fila {concepto["planilla_detalle_id"]} '
                f'no pudo aplicarse completamente. Diferencia: {monto_disponible}.'
            )
    return aplicaciones_ids


def recuperos_planilla_por_unidad(db, planilla_id: int, unidad_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute_query(
        """
        SELECT pa.id AS aplicacion_id, pa.monto_aplicado, pa.fecha_aplicacion,
               pa.moneda_codigo, pa.tipo_cambio, pa.prestamo_id, pa.cuota_id,
               p.codigo AS prestamo_codigo, p.cuenta_cobrar_codigo, p.auxiliar_id,
               p.nombre_completo, p.unidad_negocio_id AS unidad_acreedora_id,
               pd.unidad_negocio_id AS unidad_retenedora_id
        FROM contabilidad.planilla_prestamo_aplicacion pa
        JOIN contabilidad.planilla_prestamo p ON p.id = pa.prestamo_id
        JOIN contabilidad.planilla_detalle pd ON pd.id = pa.planilla_detalle_id
        WHERE pa.planilla_periodo_id = %s
          AND pd.unidad_negocio_id = %s
          AND pa.tipo_aplicacion = 'PLANILLA'
        ORDER BY pa.id
        """,
        (int(planilla_id), int(unidad_id)),
    )]


def vincular_aplicacion_asiento(db, aplicacion_id: int, asiento_id: int) -> None:
    db.execute_update(
        """
        UPDATE contabilidad.planilla_prestamo_aplicacion
        SET asiento_id = %s
        WHERE id = %s
        """,
        (int(asiento_id), int(aplicacion_id)),
    )
