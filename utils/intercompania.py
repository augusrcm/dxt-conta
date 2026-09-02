from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

CUENTA_CXC_RELACIONADA = '1.1.2.004'
CUENTA_CXP_RELACIONADA = '2.1.1.003'
MIGRACION_BASE = '20260901_001_INTERCOMPANIA_BASE'
MIGRACION_AUXILIARES = '20260902_002_INTERCOMPANIA_AUXILIARES'
Q2 = Decimal('0.01')


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def validar_intercompania_lista(db) -> None:
    rows = db.execute_query(
        """
        SELECT codigo
        FROM contabilidad.sistema_migracion
        WHERE codigo IN (%s, %s)
        """,
        (MIGRACION_BASE, MIGRACION_AUXILIARES),
    )
    codigos = {str(r['codigo']) for r in rows}
    faltantes = [c for c in (MIGRACION_BASE, MIGRACION_AUXILIARES) if c not in codigos]
    if faltantes:
        raise ValueError(
            'La base de datos no tiene completa la configuración intercompañía. '
            'Ejecute primero la(s) migración(es): ' + ', '.join(faltantes) + '.'
        )


def obtener_unidad(db, unidad_id: int, *, activa: bool = True) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT id, codigo, nombre, nit, activo
        FROM contabilidad.unidad_negocio
        WHERE id = %s
        LIMIT 1
        """,
        (unidad_id,),
    )
    if not rows:
        raise ValueError(f'La unidad de negocio {unidad_id} no existe.')
    unidad = dict(rows[0])
    if activa and not bool(unidad.get('activo')):
        raise ValueError(f'La unidad de negocio {unidad.get("codigo") or unidad_id} está inactiva.')
    return unidad


def obtener_banco(db, banco_id: int, *, moneda_codigo: str | None = None) -> dict[str, Any]:
    rows = db.execute_query(
        """
        SELECT cb.id, cb.unidad_negocio_id, cb.auxiliar_id, cb.nombre_banco,
               cb.numero_cuenta, cb.moneda_codigo, cb.cuenta_contable_codigo,
               cb.titular, cb.activo
        FROM contabilidad.cuenta_bancaria cb
        WHERE cb.id = %s
        LIMIT 1
        """,
        (banco_id,),
    )
    if not rows:
        raise ValueError('La cuenta bancaria seleccionada no existe.')
    banco = dict(rows[0])
    if not bool(banco.get('activo')):
        raise ValueError('La cuenta bancaria seleccionada está inactiva.')
    if not banco.get('unidad_negocio_id'):
        raise ValueError('La cuenta bancaria no tiene unidad de negocio propietaria configurada.')
    if not banco.get('auxiliar_id'):
        raise ValueError('La cuenta bancaria no tiene auxiliar BANCO configurado.')
    if not banco.get('cuenta_contable_codigo'):
        raise ValueError('La cuenta bancaria no tiene cuenta contable configurada.')
    if moneda_codigo and str(banco.get('moneda_codigo') or '').upper() != str(moneda_codigo).upper():
        raise ValueError('La moneda de la cuenta bancaria no coincide con la moneda de la operación.')
    aux = db.execute_query(
        """
        SELECT id, tipo::text AS tipo, activo
        FROM contabilidad.auxiliar
        WHERE id = %s
        LIMIT 1
        """,
        (banco['auxiliar_id'],),
    )
    if not aux or str(aux[0].get('tipo') or '').upper() != 'BANCO' or not bool(aux[0].get('activo')):
        raise ValueError('El auxiliar vinculado a la cuenta bancaria no es un auxiliar BANCO activo.')
    obtener_unidad(db, int(banco['unidad_negocio_id']))
    return banco


def auxiliar_canonico_unidad(db, unidad_id: int) -> int:
    validar_intercompania_lista(db)
    obtener_unidad(db, unidad_id)
    rows = db.execute_query(
        """
        SELECT id
        FROM contabilidad.auxiliar
        WHERE origen_tabla = 'contabilidad.unidad_negocio'
          AND ref_id = %s
          AND activo IS TRUE
        ORDER BY id
        """,
        (unidad_id,),
    )
    if len(rows) != 1:
        raise ValueError(
            f'La unidad de negocio {unidad_id} debe tener exactamente un auxiliar canónico intercompañía activo; '
            f'se encontraron {len(rows)}.'
        )
    auxiliar_id = int(rows[0]['id'])
    relaciones = db.execute_query(
        """
        SELECT cuenta_codigo
        FROM contabilidad.auxiliar_cuenta
        WHERE auxiliar_id = %s
          AND activo IS TRUE
          AND cuenta_codigo IN (%s, %s)
        """,
        (auxiliar_id, CUENTA_CXC_RELACIONADA, CUENTA_CXP_RELACIONADA),
    )
    cuentas = {str(r['cuenta_codigo']) for r in relaciones}
    faltan = {CUENTA_CXC_RELACIONADA, CUENTA_CXP_RELACIONADA} - cuentas
    if faltan:
        raise ValueError(
            f'El auxiliar intercompañía de la unidad {unidad_id} no está relacionado con: '
            + ', '.join(sorted(faltan)) + '.'
        )
    return auxiliar_id


def _validar_lineas(lineas: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], Decimal]:
    normalizadas: list[dict[str, Any]] = []
    debe = Decimal('0.00')
    haber = Decimal('0.00')
    for linea in lineas:
        cuenta = str(linea.get('cuenta') or '').strip()
        if not cuenta:
            raise ValueError('Una línea contable no tiene cuenta.')
        d = money(linea.get('debe'))
        h = money(linea.get('haber'))
        if d < 0 or h < 0 or (d > 0 and h > 0):
            raise ValueError(f'Línea inválida para la cuenta {cuenta}.')
        if d == 0 and h == 0:
            continue
        normalizadas.append({**linea, 'cuenta': cuenta, 'debe': d, 'haber': h})
        debe += d
        haber += h
    debe = money(debe)
    haber = money(haber)
    if debe <= 0 or debe != haber:
        raise ValueError(f'El asiento intercompañía no cuadra. Debe {debe} / Haber {haber}.')
    return normalizadas, debe


def crear_asiento(
    db,
    *,
    fecha: date,
    unidad_id: int,
    moneda_codigo: str,
    tipo_cambio: Any,
    glosa: str,
    referencia: str,
    modulo_origen: str,
    tabla_origen: str,
    origen_id: int,
    accion: str,
    lineas: Iterable[dict[str, Any]],
    atributos: dict[str, Any] | None = None,
    cliente_nit_ci_ref: str | None = None,
    cliente_nombre_ref: str | None = None,
) -> int:
    obtener_unidad(db, unidad_id)
    lineas_ok, _ = _validar_lineas(lineas)
    attrs = {'origen': 'intercompania', 'accion': accion}
    attrs.update(atributos or {})
    asiento_id = db.execute_insert(
        """
        INSERT INTO contabilidad.asiento (
            fecha, unidad_negocio_id, moneda_codigo, tipo_cambio, glosa, referencia,
            modulo_origen, tabla_origen, origen_id, estado, cliente_nit_ci_ref,
            cliente_nombre_ref, atributos, actualizado_en
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'CONFIRMADO', %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
        """,
        (
            fecha, unidad_id, moneda_codigo, tipo_cambio, str(glosa)[:500], str(referencia)[:150],
            str(modulo_origen)[:50], str(tabla_origen)[:100], int(origen_id), cliente_nit_ci_ref,
            cliente_nombre_ref, _json(attrs),
        ),
    )
    for sec, linea in enumerate(lineas_ok, start=1):
        db.execute_insert(
            """
            INSERT INTO contabilidad.asiento_detalle (
                asiento_id, secuencia, cuenta_codigo, auxiliar_id, centro_costo_id,
                glosa, debe, haber, monto_moneda, referencia, atributos
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                asiento_id, sec, linea['cuenta'], linea.get('auxiliar_id'), linea.get('centro_costo_id'),
                str(linea.get('glosa') or glosa)[:300], linea['debe'], linea['haber'],
                max(linea['debe'], linea['haber']), str(referencia)[:150], _json(linea.get('atributos')),
            ),
            return_id=False,
        )
    return int(asiento_id)


def registrar_operacion(
    db,
    *,
    clave_origen: str,
    tipo_operacion: str,
    fecha_operacion: date,
    unidad_deudora_id: int,
    unidad_acreedora_id: int,
    moneda_codigo: str,
    tipo_cambio: Any,
    monto: Any,
    modulo_origen: str,
    tabla_origen: str,
    origen_id: int,
    referencia: str,
    asiento_deudora_id: int,
    asiento_acreedora_id: int,
    usuario: str,
    atributos: dict[str, Any] | None = None,
) -> int:
    validar_intercompania_lista(db)
    if int(unidad_deudora_id) == int(unidad_acreedora_id):
        raise ValueError('Una operación intercompañía requiere dos unidades jurídicas distintas.')
    monto_q = money(monto)
    if monto_q <= 0:
        raise ValueError('El monto intercompañía debe ser mayor a cero.')
    existentes = db.execute_query(
        """
        SELECT *
        FROM contabilidad.operacion_intercompania
        WHERE clave_origen = %s
        LIMIT 1
        """,
        (str(clave_origen)[:180],),
    )
    if existentes:
        row = dict(existentes[0])
        esperados = {
            'unidad_deudora_id': int(unidad_deudora_id),
            'unidad_acreedora_id': int(unidad_acreedora_id),
            'asiento_unidad_deudora_id': int(asiento_deudora_id),
            'asiento_unidad_acreedora_id': int(asiento_acreedora_id),
        }
        for campo, esperado in esperados.items():
            if int(row.get(campo) or 0) != esperado:
                raise ValueError(f'La clave intercompañía {clave_origen} ya existe con datos distintos ({campo}).')
        if money(row.get('monto')) != monto_q or str(row.get('estado')) not in ('CONFIRMADA', 'REVERSADA'):
            raise ValueError(f'La clave intercompañía {clave_origen} ya existe con monto/estado incompatible.')
        return int(row['id'])

    asientos = db.execute_query(
        """
        SELECT id, fecha, unidad_negocio_id, estado::text AS estado
        FROM contabilidad.asiento
        WHERE id = ANY(%s)
        ORDER BY id
        """,
        ([int(asiento_deudora_id), int(asiento_acreedora_id)],),
    )
    por_id = {int(r['id']): r for r in asientos}
    for aid, uid in ((int(asiento_deudora_id), int(unidad_deudora_id)), (int(asiento_acreedora_id), int(unidad_acreedora_id))):
        a = por_id.get(aid)
        if not a or int(a.get('unidad_negocio_id') or 0) != uid or str(a.get('estado')) != 'CONFIRMADO':
            raise ValueError(f'El asiento {aid} no corresponde a la unidad/estado esperado para la operación intercompañía.')
        if a.get('fecha') != fecha_operacion:
            raise ValueError(f'El asiento {aid} no respeta la fecha soberana {fecha_operacion}.')

    return int(db.execute_insert(
        """
        INSERT INTO contabilidad.operacion_intercompania (
            clave_origen, tipo_operacion, fecha_operacion,
            unidad_deudora_id, unidad_acreedora_id, moneda_codigo, tipo_cambio, monto,
            modulo_origen, tabla_origen, origen_id, referencia,
            asiento_unidad_deudora_id, asiento_unidad_acreedora_id,
            estado, creado_por, atributos
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  'CONFIRMADA', %s, %s::jsonb)
        """,
        (
            str(clave_origen)[:180], str(tipo_operacion)[:60], fecha_operacion,
            int(unidad_deudora_id), int(unidad_acreedora_id), moneda_codigo, tipo_cambio, monto_q,
            str(modulo_origen)[:50], str(tabla_origen)[:100], int(origen_id), str(referencia)[:150],
            int(asiento_deudora_id), int(asiento_acreedora_id), str(usuario)[:100], _json(atributos),
        ),
    ))


def operaciones_por_origen(db, tabla_origen: str, origen_ids: Iterable[int]) -> list[dict[str, Any]]:
    ids = sorted({int(x) for x in origen_ids if x is not None})
    if not ids:
        return []
    return [dict(r) for r in db.execute_query(
        """
        SELECT *
        FROM contabilidad.operacion_intercompania
        WHERE tabla_origen = %s
          AND origen_id = ANY(%s)
        ORDER BY id
        """,
        (tabla_origen, ids),
    )]


def crear_reverso_asiento(
    db,
    asiento_id: int,
    *,
    fecha_reversion: date | None = None,
    justificativo: str,
    modulo_origen: str = 'INTERCOMPANIA',
    tabla_origen: str = 'contabilidad.asiento',
    origen_id: int | None = None,
    accion: str = 'reversion_intercompania',
) -> int:
    rows = db.execute_query(
        """
        SELECT *
        FROM contabilidad.asiento
        WHERE id = %s
        LIMIT 1
        """,
        (int(asiento_id),),
    )
    if not rows:
        raise ValueError(f'No existe el asiento {asiento_id} que debe revertirse.')
    asiento = dict(rows[0])
    if str(asiento.get('estado')) != 'CONFIRMADO':
        raise ValueError(f'El asiento {asiento_id} no está CONFIRMADO.')
    detalles = db.execute_query(
        """
        SELECT *
        FROM contabilidad.asiento_detalle
        WHERE asiento_id = %s
        ORDER BY secuencia
        """,
        (int(asiento_id),),
    )
    if not detalles:
        raise ValueError(f'El asiento {asiento_id} no tiene detalle.')
    fecha = fecha_reversion or asiento['fecha']
    lineas = [
        {
            'cuenta': d['cuenta_codigo'],
            'auxiliar_id': d.get('auxiliar_id'),
            'centro_costo_id': d.get('centro_costo_id'),
            'debe': money(d.get('haber')),
            'haber': money(d.get('debe')),
            'glosa': f'Reverso {d.get("glosa") or asiento.get("referencia") or asiento_id}',
            'atributos': {'tipo': accion, 'asiento_original_id': int(asiento_id)},
        }
        for d in detalles
    ]
    return crear_asiento(
        db,
        fecha=fecha,
        unidad_id=int(asiento['unidad_negocio_id']),
        moneda_codigo=asiento['moneda_codigo'],
        tipo_cambio=asiento['tipo_cambio'],
        glosa=f'Reverso {asiento.get("referencia") or asiento_id}: {justificativo}',
        referencia=f'REV-{asiento.get("referencia") or asiento_id}',
        modulo_origen=modulo_origen,
        tabla_origen=tabla_origen,
        origen_id=int(origen_id or asiento_id),
        accion=accion,
        lineas=lineas,
        atributos={'asiento_original_id': int(asiento_id), 'justificativo': justificativo},
        cliente_nit_ci_ref=asiento.get('cliente_nit_ci_ref'),
        cliente_nombre_ref=asiento.get('cliente_nombre_ref'),
    )


def revertir_operacion(
    db,
    operacion: dict[str, Any] | int,
    *,
    justificativo: str,
    usuario: str,
    reversos_existentes: dict[int, int] | None = None,
) -> tuple[int, int]:
    if isinstance(operacion, int):
        rows = db.execute_query(
            "SELECT * FROM contabilidad.operacion_intercompania WHERE id = %s LIMIT 1",
            (operacion,),
        )
        if not rows:
            raise ValueError(f'No existe la operación intercompañía {operacion}.')
        oi = dict(rows[0])
    else:
        oi = dict(operacion)
    if str(oi.get('estado')) == 'REVERSADA':
        if not oi.get('asiento_reversion_deudora_id') or not oi.get('asiento_reversion_acreedora_id'):
            raise ValueError(f'La operación intercompañía {oi.get("id")} figura REVERSADA pero no tiene ambos asientos de reversión.')
        return int(oi['asiento_reversion_deudora_id']), int(oi['asiento_reversion_acreedora_id'])
    if str(oi.get('estado')) != 'CONFIRMADA':
        raise ValueError(f'La operación intercompañía {oi.get("id")} no está CONFIRMADA.')
    existentes = reversos_existentes or {}
    original_deudora = int(oi['asiento_unidad_deudora_id'])
    original_acreedora = int(oi['asiento_unidad_acreedora_id'])
    rev_deudora = existentes.get(original_deudora)
    rev_acreedora = existentes.get(original_acreedora)
    if not rev_deudora:
        rev_deudora = crear_reverso_asiento(
            db, original_deudora,
            fecha_reversion=oi['fecha_operacion'], justificativo=justificativo,
            modulo_origen='INTERCOMPANIA', tabla_origen='contabilidad.operacion_intercompania',
            origen_id=int(oi['id']), accion='reverso_intercompania_deudora',
        )
    if not rev_acreedora:
        rev_acreedora = crear_reverso_asiento(
            db, original_acreedora,
            fecha_reversion=oi['fecha_operacion'], justificativo=justificativo,
            modulo_origen='INTERCOMPANIA', tabla_origen='contabilidad.operacion_intercompania',
            origen_id=int(oi['id']), accion='reverso_intercompania_acreedora',
        )
    db.execute_update(
        """
        UPDATE contabilidad.operacion_intercompania
        SET estado = 'REVERSADA',
            asiento_reversion_deudora_id = %s,
            asiento_reversion_acreedora_id = %s,
            actualizado_por = %s,
            motivo_regularizacion = CASE
                WHEN COALESCE(motivo_regularizacion,'') = '' THEN %s
                ELSE motivo_regularizacion || E'\n' || %s
            END,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = %s AND estado = 'CONFIRMADA'
        """,
        (rev_deudora, rev_acreedora, str(usuario)[:100], f'Reversión: {justificativo}'[:800], f'Reversión: {justificativo}'[:800], int(oi['id'])),
    )
    return int(rev_deudora), int(rev_acreedora)
