-- ============================================================================
-- DXT-CONTA
-- Migración: 20260901_001_INTERCOMPANIA_BASE
-- Objetivo:
--   1) Crear registro persistente de migraciones de BD.
--   2) Crear modelo auditable para operaciones intercompañía.
--   3) Incorporar las 3 operaciones históricas ya regularizadas de
--      PRE-2026-0001 sin alterar sus importes, fechas ni asientos.
--
-- Ejecución prevista:
--   PRIMERO LOCAL. Solo después de validar el resultado, ejecutar el MISMO
--   archivo en PRODUCCIÓN.
--
-- Seguridad:
--   - Transaccional: cualquier desviación provoca ROLLBACK total.
--   - Idempotente: una segunda ejecución no duplica datos.
--   - No modifica los asientos 948 ni 953-958 ni recalcula planillas/préstamo.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

SELECT pg_advisory_xact_lock(
    hashtextextended('DXT-CONTA:20260901_001_INTERCOMPANIA_BASE', 0)
);

-- --------------------------------------------------------------------------
-- 1. Registro persistente de migraciones
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contabilidad.sistema_migracion (
    codigo          varchar(100) PRIMARY KEY,
    descripcion     varchar(500) NOT NULL,
    checksum        varchar(64) NOT NULL,
    aplicado_en     timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aplicado_por    varchar(100) NOT NULL,
    base_datos      varchar(100) NOT NULL,
    usuario_bd      varchar(100) NOT NULL,
    atributos       jsonb
);

COMMENT ON TABLE contabilidad.sistema_migracion IS
'Registro transaccional de migraciones estructurales aplicadas a DXT-Conta.';
COMMENT ON COLUMN contabilidad.sistema_migracion.checksum IS
'Checksum lógico de la definición de la migración; no depende de rutas locales.';

DO $validar_registro$
DECLARE
    v_faltantes integer;
BEGIN
    SELECT count(*)
      INTO v_faltantes
      FROM (VALUES
            ('codigo'), ('descripcion'), ('checksum'), ('aplicado_en'),
            ('aplicado_por'), ('base_datos'), ('usuario_bd'), ('atributos')
      ) AS e(columna)
     WHERE NOT EXISTS (
            SELECT 1
              FROM information_schema.columns c
             WHERE c.table_schema = 'contabilidad'
               AND c.table_name = 'sistema_migracion'
               AND c.column_name = e.columna
     );

    IF v_faltantes <> 0 THEN
        RAISE EXCEPTION
            'contabilidad.sistema_migracion existe pero no coincide con la estructura esperada (% columnas faltantes).',
            v_faltantes;
    END IF;
END
$validar_registro$;

-- --------------------------------------------------------------------------
-- 2. Precondiciones de esta migración
-- --------------------------------------------------------------------------
DO $precheck$
DECLARE
    v_ya_aplicada boolean;
    v_count integer;
    v_total numeric(18,2);
    v_asientos integer;
    v_asiento_deudora bigint;
    v_asiento_acreedora bigint;
    v_aux_deudora bigint;
    v_aux_acreedora bigint;
    v_aux_count integer;
    v_debe numeric(18,2);
    v_haber numeric(18,2);
    r record;
BEGIN
    SELECT EXISTS (
        SELECT 1
          FROM contabilidad.sistema_migracion
         WHERE codigo = '20260901_001_INTERCOMPANIA_BASE'
    ) INTO v_ya_aplicada;

    IF v_ya_aplicada THEN
        IF to_regclass('contabilidad.operacion_intercompania') IS NULL THEN
            RAISE EXCEPTION
                'La migración figura como aplicada pero falta contabilidad.operacion_intercompania.';
        END IF;

        RAISE NOTICE
            '20260901_001_INTERCOMPANIA_BASE ya figura aplicada. Se validará el estado final sin duplicar datos.';
        RETURN;
    END IF;

    IF to_regclass('contabilidad.operacion_intercompania') IS NOT NULL THEN
        RAISE EXCEPTION
            'contabilidad.operacion_intercompania ya existe sin registro de esta migración. Se detiene para evitar asumir su origen.';
    END IF;

    -- La regularización previa debe existir completa antes de migrar su trazabilidad.
    SELECT count(*), COALESCE(sum(app.monto_aplicado), 0)
      INTO v_count, v_total
      FROM contabilidad.planilla_prestamo_aplicacion app
      JOIN contabilidad.planilla_prestamo p
        ON p.id = app.prestamo_id
     WHERE p.codigo = 'PRE-2026-0001'
       AND app.tipo_aplicacion = 'PLANILLA'
       AND app.atributos ->> 'regularizacion_origen' = 'PRE-2026-0001-INTERCOMPANIA';

    IF v_count <> 3 OR v_total <> 4000.00 THEN
        RAISE EXCEPTION
            'Base histórica inesperada para PRE-2026-0001: aplicaciones=%, total=%. Esperado: 3 y 4000.00.',
            v_count, v_total;
    END IF;

    FOR r IN
        SELECT
            app.id AS aplicacion_id,
            app.asiento_id AS asiento_aplicacion_id,
            app.fecha_aplicacion,
            app.monto_aplicado,
            app.moneda_codigo,
            app.tipo_cambio,
            app.planilla_periodo_id,
            app.planilla_detalle_id,
            app.atributos,
            p.id AS prestamo_id,
            p.codigo AS prestamo_codigo,
            p.auxiliar_id AS auxiliar_persona_id,
            c.id AS cuota_id,
            c.numero_cuota,
            ud.id AS unidad_deudora_id,
            ua.id AS unidad_acreedora_id
        FROM contabilidad.planilla_prestamo_aplicacion app
        JOIN contabilidad.planilla_prestamo p
          ON p.id = app.prestamo_id
        JOIN contabilidad.planilla_prestamo_cuota c
          ON c.id = app.cuota_id
        LEFT JOIN contabilidad.unidad_negocio ud
          ON ud.codigo = app.atributos ->> 'unidad_retenedora'
        LEFT JOIN contabilidad.unidad_negocio ua
          ON ua.codigo = app.atributos ->> 'unidad_acreedora'
        WHERE p.codigo = 'PRE-2026-0001'
          AND app.tipo_aplicacion = 'PLANILLA'
          AND app.atributos ->> 'regularizacion_origen' = 'PRE-2026-0001-INTERCOMPANIA'
        ORDER BY c.numero_cuota
    LOOP
        IF r.unidad_deudora_id IS NULL OR r.unidad_acreedora_id IS NULL THEN
            RAISE EXCEPTION
                'Aplicación %: no se pudo resolver unidad retenedora/acreedora desde atributos.',
                r.aplicacion_id;
        END IF;

        IF r.unidad_deudora_id = r.unidad_acreedora_id THEN
            RAISE EXCEPTION
                'Aplicación %: las unidades deudora y acreedora no pueden ser la misma.',
                r.aplicacion_id;
        END IF;

        SELECT count(*)
          INTO v_asientos
          FROM contabilidad.asiento a
         WHERE a.referencia LIKE r.prestamo_codigo || '/C' || r.numero_cuota::text || '/%'
           AND a.fecha = r.fecha_aplicacion
           AND a.estado::text = 'CONFIRMADO';

        IF v_asientos <> 2 THEN
            RAISE EXCEPTION
                'Aplicación %: se esperaban exactamente 2 asientos intercompañía CONFIRMADOS y existen %.',
                r.aplicacion_id, v_asientos;
        END IF;

        SELECT min(a.id), count(*)
          INTO v_asiento_deudora, v_count
          FROM contabilidad.asiento a
         WHERE a.referencia LIKE r.prestamo_codigo || '/C' || r.numero_cuota::text || '/%'
           AND a.fecha = r.fecha_aplicacion
           AND a.unidad_negocio_id = r.unidad_deudora_id
           AND a.estado::text = 'CONFIRMADO';

        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: se esperaba 1 asiento para la unidad deudora y existen %.',
                r.aplicacion_id, v_count;
        END IF;

        SELECT min(a.id), count(*)
          INTO v_asiento_acreedora, v_count
          FROM contabilidad.asiento a
         WHERE a.referencia LIKE r.prestamo_codigo || '/C' || r.numero_cuota::text || '/%'
           AND a.fecha = r.fecha_aplicacion
           AND a.unidad_negocio_id = r.unidad_acreedora_id
           AND a.estado::text = 'CONFIRMADO';

        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: se esperaba 1 asiento para la unidad acreedora y existen %.',
                r.aplicacion_id, v_count;
        END IF;

        IF r.asiento_aplicacion_id IS DISTINCT FROM v_asiento_acreedora THEN
            RAISE EXCEPTION
                'Aplicación %: asiento_id=% pero el asiento que reduce el préstamo en la unidad acreedora es %.',
                r.aplicacion_id, r.asiento_aplicacion_id, v_asiento_acreedora;
        END IF;

        -- Cada lado de la operación debe estar balanceado por sí mismo y por el monto aplicado.
        SELECT COALESCE(sum(ad.debe), 0), COALESCE(sum(ad.haber), 0)
          INTO v_debe, v_haber
          FROM contabilidad.asiento_detalle ad
         WHERE ad.asiento_id = v_asiento_deudora;

        IF v_debe <> r.monto_aplicado OR v_haber <> r.monto_aplicado THEN
            RAISE EXCEPTION
                'Aplicación %: asiento deudora % no cuadra con el monto %. Debe=%, Haber=%.',
                r.aplicacion_id, v_asiento_deudora, r.monto_aplicado, v_debe, v_haber;
        END IF;

        SELECT COALESCE(sum(ad.debe), 0), COALESCE(sum(ad.haber), 0)
          INTO v_debe, v_haber
          FROM contabilidad.asiento_detalle ad
         WHERE ad.asiento_id = v_asiento_acreedora;

        IF v_debe <> r.monto_aplicado OR v_haber <> r.monto_aplicado THEN
            RAISE EXCEPTION
                'Aplicación %: asiento acreedora % no cuadra con el monto %. Debe=%, Haber=%.',
                r.aplicacion_id, v_asiento_acreedora, r.monto_aplicado, v_debe, v_haber;
        END IF;

        -- Auxiliares canónicos de las empresas relacionadas.
        SELECT min(aux.id), count(*)
          INTO v_aux_acreedora, v_aux_count
          FROM contabilidad.auxiliar aux
         WHERE aux.origen_tabla = 'contabilidad.unidad_negocio'
           AND aux.ref_id = r.unidad_acreedora_id
           AND aux.activo = TRUE;

        IF v_aux_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: la unidad acreedora debe tener exactamente 1 auxiliar canónico activo; existen %.',
                r.aplicacion_id, v_aux_count;
        END IF;

        SELECT min(aux.id), count(*)
          INTO v_aux_deudora, v_aux_count
          FROM contabilidad.auxiliar aux
         WHERE aux.origen_tabla = 'contabilidad.unidad_negocio'
           AND aux.ref_id = r.unidad_deudora_id
           AND aux.activo = TRUE;

        IF v_aux_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: la unidad deudora debe tener exactamente 1 auxiliar canónico activo; existen %.',
                r.aplicacion_id, v_aux_count;
        END IF;

        IF NOT EXISTS (
            SELECT 1
              FROM contabilidad.auxiliar_cuenta ac
             WHERE ac.auxiliar_id = v_aux_acreedora
               AND ac.cuenta_codigo = '2.1.1.003'
        ) THEN
            RAISE EXCEPTION
                'Aplicación %: falta relación auxiliar acreedora -> 2.1.1.003.',
                r.aplicacion_id;
        END IF;

        IF NOT EXISTS (
            SELECT 1
              FROM contabilidad.auxiliar_cuenta ac
             WHERE ac.auxiliar_id = v_aux_deudora
               AND ac.cuenta_codigo = '1.1.2.004'
        ) THEN
            RAISE EXCEPTION
                'Aplicación %: falta relación auxiliar deudora -> 1.1.2.004.',
                r.aplicacion_id;
        END IF;

        -- MONDO/unidad retenedora: reduce obligación con la persona y reconoce CxP relacionada.
        SELECT count(*) INTO v_count
          FROM contabilidad.asiento_detalle ad
         WHERE ad.asiento_id = v_asiento_deudora
           AND ad.cuenta_codigo = '2.1.1.001'
           AND ad.auxiliar_id = r.auxiliar_persona_id
           AND ad.debe = r.monto_aplicado
           AND ad.haber = 0;
        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: asiento deudora no contiene exactamente la reducción esperada de 2.1.1.001.',
                r.aplicacion_id;
        END IF;

        SELECT count(*) INTO v_count
          FROM contabilidad.asiento_detalle ad
         WHERE ad.asiento_id = v_asiento_deudora
           AND ad.cuenta_codigo = '2.1.1.003'
           AND ad.auxiliar_id = v_aux_acreedora
           AND ad.debe = 0
           AND ad.haber = r.monto_aplicado;
        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: asiento deudora no contiene exactamente la CxP relacionada esperada en 2.1.1.003.',
                r.aplicacion_id;
        END IF;

        -- DXT/unidad acreedora: reconoce CxC relacionada y reduce préstamo personal.
        SELECT count(*) INTO v_count
          FROM contabilidad.asiento_detalle ad
         WHERE ad.asiento_id = v_asiento_acreedora
           AND ad.cuenta_codigo = '1.1.2.004'
           AND ad.auxiliar_id = v_aux_deudora
           AND ad.debe = r.monto_aplicado
           AND ad.haber = 0;
        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: asiento acreedora no contiene exactamente la CxC relacionada esperada en 1.1.2.004.',
                r.aplicacion_id;
        END IF;

        SELECT count(*) INTO v_count
          FROM contabilidad.asiento_detalle ad
         WHERE ad.asiento_id = v_asiento_acreedora
           AND ad.cuenta_codigo = '1.1.2.003'
           AND ad.auxiliar_id = r.auxiliar_persona_id
           AND ad.debe = 0
           AND ad.haber = r.monto_aplicado;
        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'Aplicación %: asiento acreedora no contiene exactamente la reducción esperada del préstamo en 1.1.2.003.',
                r.aplicacion_id;
        END IF;
    END LOOP;

    RAISE NOTICE
        'Precondiciones históricas verificadas: 3 aplicaciones intercompañía, Bs 4.000,00 y 6 asientos consistentes.';
END
$precheck$;

-- --------------------------------------------------------------------------
-- 3. Modelo persistente de operación intercompañía
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contabilidad.operacion_intercompania (
    id                              bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    clave_origen                    varchar(180) NOT NULL,
    tipo_operacion                  varchar(60) NOT NULL,
    fecha_operacion                 date NOT NULL,
    unidad_deudora_id               bigint NOT NULL,
    unidad_acreedora_id             bigint NOT NULL,
    moneda_codigo                   varchar(10) NOT NULL,
    tipo_cambio                     numeric(18,6) NOT NULL DEFAULT 1,
    monto                           numeric(18,2) NOT NULL,
    modulo_origen                   varchar(50),
    tabla_origen                    varchar(100) NOT NULL,
    origen_id                       bigint NOT NULL,
    referencia                      varchar(150),
    asiento_unidad_deudora_id       bigint NOT NULL,
    asiento_unidad_acreedora_id     bigint NOT NULL,
    asiento_reversion_deudora_id    bigint,
    asiento_reversion_acreedora_id  bigint,
    estado                          varchar(20) NOT NULL DEFAULT 'CONFIRMADA',
    motivo_regularizacion           varchar(800),
    creado_por                      varchar(100),
    actualizado_por                 varchar(100),
    atributos                       jsonb,
    creado_en                       timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en                  timestamp(6),

    CONSTRAINT uq_operacion_intercompania_clave UNIQUE (clave_origen),
    CONSTRAINT ck_operacion_intercompania_monto CHECK (monto > 0),
    CONSTRAINT ck_operacion_intercompania_tc CHECK (tipo_cambio > 0),
    CONSTRAINT ck_operacion_intercompania_unidades CHECK (unidad_deudora_id <> unidad_acreedora_id),
    CONSTRAINT ck_operacion_intercompania_asientos CHECK (asiento_unidad_deudora_id <> asiento_unidad_acreedora_id),
    CONSTRAINT ck_operacion_intercompania_estado CHECK (
        estado IN ('BORRADOR', 'CONFIRMADA', 'REVERSADA', 'ANULADA')
    ),

    CONSTRAINT fk_oi_unidad_deudora FOREIGN KEY (unidad_deudora_id)
        REFERENCES contabilidad.unidad_negocio(id) ON DELETE RESTRICT,
    CONSTRAINT fk_oi_unidad_acreedora FOREIGN KEY (unidad_acreedora_id)
        REFERENCES contabilidad.unidad_negocio(id) ON DELETE RESTRICT,
    CONSTRAINT fk_oi_moneda FOREIGN KEY (moneda_codigo)
        REFERENCES contabilidad.moneda(codigo) ON DELETE RESTRICT,
    CONSTRAINT fk_oi_asiento_deudora FOREIGN KEY (asiento_unidad_deudora_id)
        REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT,
    CONSTRAINT fk_oi_asiento_acreedora FOREIGN KEY (asiento_unidad_acreedora_id)
        REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT,
    CONSTRAINT fk_oi_asiento_rev_deudora FOREIGN KEY (asiento_reversion_deudora_id)
        REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT,
    CONSTRAINT fk_oi_asiento_rev_acreedora FOREIGN KEY (asiento_reversion_acreedora_id)
        REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT
);

COMMENT ON TABLE contabilidad.operacion_intercompania IS
'Par auditable de asientos que representa una obligación/acreencia entre unidades jurídicas por una operación realizada por cuenta de otra.';
COMMENT ON COLUMN contabilidad.operacion_intercompania.unidad_deudora_id IS
'Unidad que reconoce la cuenta por pagar intercompañía.';
COMMENT ON COLUMN contabilidad.operacion_intercompania.unidad_acreedora_id IS
'Unidad que reconoce la cuenta por cobrar intercompañía.';
COMMENT ON COLUMN contabilidad.operacion_intercompania.clave_origen IS
'Clave de negocio idempotente de la operación intercompañía.';
COMMENT ON COLUMN contabilidad.operacion_intercompania.fecha_operacion IS
'Fecha soberana de la operación económica; los asientos del par deben respetarla.';

CREATE INDEX IF NOT EXISTS ix_oi_fecha
    ON contabilidad.operacion_intercompania (fecha_operacion);
CREATE INDEX IF NOT EXISTS ix_oi_deudora_fecha
    ON contabilidad.operacion_intercompania (unidad_deudora_id, fecha_operacion);
CREATE INDEX IF NOT EXISTS ix_oi_acreedora_fecha
    ON contabilidad.operacion_intercompania (unidad_acreedora_id, fecha_operacion);
CREATE INDEX IF NOT EXISTS ix_oi_origen
    ON contabilidad.operacion_intercompania (tabla_origen, origen_id);
CREATE INDEX IF NOT EXISTS ix_oi_estado
    ON contabilidad.operacion_intercompania (estado);

-- --------------------------------------------------------------------------
-- 4. Incorporación de las 3 operaciones históricas ya regularizadas
--    No se crean ni se modifican asientos; solo se registra el par existente.
-- --------------------------------------------------------------------------
INSERT INTO contabilidad.operacion_intercompania (
    clave_origen,
    tipo_operacion,
    fecha_operacion,
    unidad_deudora_id,
    unidad_acreedora_id,
    moneda_codigo,
    tipo_cambio,
    monto,
    modulo_origen,
    tabla_origen,
    origen_id,
    referencia,
    asiento_unidad_deudora_id,
    asiento_unidad_acreedora_id,
    estado,
    motivo_regularizacion,
    creado_por,
    atributos
)
SELECT
    app.atributos ->> 'regularizacion_clave' AS clave_origen,
    'PRESTAMO_PLANILLA' AS tipo_operacion,
    app.fecha_aplicacion,
    ud.id AS unidad_deudora_id,
    ua.id AS unidad_acreedora_id,
    app.moneda_codigo,
    app.tipo_cambio,
    app.monto_aplicado,
    'PLANILLAS' AS modulo_origen,
    'contabilidad.planilla_prestamo_aplicacion' AS tabla_origen,
    app.id AS origen_id,
    app.referencia,
    ad.id AS asiento_unidad_deudora_id,
    aa.id AS asiento_unidad_acreedora_id,
    'CONFIRMADA' AS estado,
    'Trazabilidad incorporada por 20260901_001_INTERCOMPANIA_BASE sobre regularización histórica previamente validada.' AS motivo_regularizacion,
    COALESCE(NULLIF(app.creado_por, ''), current_user) AS creado_por,
    jsonb_build_object(
        'migracion_codigo', '20260901_001_INTERCOMPANIA_BASE',
        'regularizacion_origen', app.atributos ->> 'regularizacion_origen',
        'prestamo_id', p.id,
        'prestamo_codigo', p.codigo,
        'cuota_id', c.id,
        'cuota_numero', c.numero_cuota,
        'planilla_periodo_id', app.planilla_periodo_id,
        'planilla_detalle_id', app.planilla_detalle_id,
        'aplicacion_id', app.id
    ) AS atributos
FROM contabilidad.planilla_prestamo_aplicacion app
JOIN contabilidad.planilla_prestamo p
  ON p.id = app.prestamo_id
JOIN contabilidad.planilla_prestamo_cuota c
  ON c.id = app.cuota_id
JOIN contabilidad.unidad_negocio ud
  ON ud.codigo = app.atributos ->> 'unidad_retenedora'
JOIN contabilidad.unidad_negocio ua
  ON ua.codigo = app.atributos ->> 'unidad_acreedora'
JOIN contabilidad.asiento ad
  ON ad.referencia LIKE p.codigo || '/C' || c.numero_cuota::text || '/%'
 AND ad.fecha = app.fecha_aplicacion
 AND ad.unidad_negocio_id = ud.id
 AND ad.estado::text = 'CONFIRMADO'
JOIN contabilidad.asiento aa
  ON aa.id = app.asiento_id
 AND aa.referencia LIKE p.codigo || '/C' || c.numero_cuota::text || '/%'
 AND aa.fecha = app.fecha_aplicacion
 AND aa.unidad_negocio_id = ua.id
 AND aa.estado::text = 'CONFIRMADO'
WHERE p.codigo = 'PRE-2026-0001'
  AND app.tipo_aplicacion = 'PLANILLA'
  AND app.atributos ->> 'regularizacion_origen' = 'PRE-2026-0001-INTERCOMPANIA'
  AND NOT EXISTS (
      SELECT 1
      FROM contabilidad.sistema_migracion sm
      WHERE sm.codigo = '20260901_001_INTERCOMPANIA_BASE'
  )
ON CONFLICT (clave_origen) DO NOTHING;

-- --------------------------------------------------------------------------
-- 5. Postcondiciones antes de registrar la migración
-- --------------------------------------------------------------------------
DO $postcheck$
DECLARE
    v_count integer;
    v_total numeric(18,2);
    v_invalid integer;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM contabilidad.sistema_migracion
        WHERE codigo = '20260901_001_INTERCOMPANIA_BASE'
    ) THEN
        RAISE NOTICE 'Migración ya aplicada previamente: se omite el postcheck histórico inmutable.';
        RETURN;
    END IF;

    SELECT count(*), COALESCE(sum(oi.monto), 0)
      INTO v_count, v_total
      FROM contabilidad.operacion_intercompania oi
     WHERE oi.atributos ->> 'migracion_codigo' = '20260901_001_INTERCOMPANIA_BASE';

    IF v_count <> 3 OR v_total <> 4000.00 THEN
        RAISE EXCEPTION
            'Postcheck intercompañía inválido: filas=%, total=%. Esperado: 3 y 4000.00.',
            v_count, v_total;
    END IF;

    SELECT count(*)
      INTO v_invalid
      FROM contabilidad.operacion_intercompania oi
      JOIN contabilidad.asiento ad ON ad.id = oi.asiento_unidad_deudora_id
      JOIN contabilidad.asiento aa ON aa.id = oi.asiento_unidad_acreedora_id
     WHERE oi.atributos ->> 'migracion_codigo' = '20260901_001_INTERCOMPANIA_BASE'
       AND (
            oi.estado <> 'CONFIRMADA'
         OR ad.estado::text <> 'CONFIRMADO'
         OR aa.estado::text <> 'CONFIRMADO'
         OR ad.unidad_negocio_id <> oi.unidad_deudora_id
         OR aa.unidad_negocio_id <> oi.unidad_acreedora_id
         OR ad.fecha <> oi.fecha_operacion
         OR aa.fecha <> oi.fecha_operacion
       );

    IF v_invalid <> 0 THEN
        RAISE EXCEPTION
            'Postcheck intercompañía: % fila(s) tienen estado, unidad o fecha inconsistente con sus asientos.',
            v_invalid;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM contabilidad.operacion_intercompania oi
         WHERE oi.atributos ->> 'migracion_codigo' = '20260901_001_INTERCOMPANIA_BASE'
           AND oi.unidad_deudora_id = oi.unidad_acreedora_id
    ) THEN
        RAISE EXCEPTION 'Postcheck intercompañía: se detectó una operación con la misma unidad en ambos lados.';
    END IF;
END
$postcheck$;

INSERT INTO contabilidad.sistema_migracion (
    codigo,
    descripcion,
    checksum,
    aplicado_por,
    base_datos,
    usuario_bd,
    atributos
)
VALUES (
    '20260901_001_INTERCOMPANIA_BASE',
    'Base estructural de operaciones intercompañía e incorporación de PRE-2026-0001 regularizado.',
    'e281e795cfbfbf2535469b0871f974670051d2c34729a4781293302d8760b494',
    current_user,
    current_database(),
    current_user,
    jsonb_build_object(
        'proyecto', 'DXT-CONTA',
        'version', 1,
        'fuente_historica', 'PRE-2026-0001-INTERCOMPANIA',
        'operaciones_migradas', 3,
        'monto_historico', 4000.00
    )
)
ON CONFLICT (codigo) DO NOTHING;

-- --------------------------------------------------------------------------
-- 6. Salida de verificación para copiar y devolver al análisis
-- --------------------------------------------------------------------------
SELECT
    current_database() AS base_datos,
    current_user AS usuario_bd,
    current_schema() AS schema_actual,
    now() AS ejecutado_en;

SELECT
    codigo,
    descripcion,
    checksum,
    aplicado_en,
    aplicado_por,
    base_datos,
    usuario_bd,
    atributos
FROM contabilidad.sistema_migracion
WHERE codigo = '20260901_001_INTERCOMPANIA_BASE';

SELECT
    oi.id,
    oi.clave_origen,
    oi.tipo_operacion,
    oi.fecha_operacion,
    ud.codigo AS unidad_deudora,
    ua.codigo AS unidad_acreedora,
    oi.moneda_codigo,
    oi.tipo_cambio,
    oi.monto,
    oi.estado,
    oi.tabla_origen,
    oi.origen_id,
    oi.asiento_unidad_deudora_id,
    oi.asiento_unidad_acreedora_id,
    oi.asiento_reversion_deudora_id,
    oi.asiento_reversion_acreedora_id
FROM contabilidad.operacion_intercompania oi
JOIN contabilidad.unidad_negocio ud ON ud.id = oi.unidad_deudora_id
JOIN contabilidad.unidad_negocio ua ON ua.id = oi.unidad_acreedora_id
WHERE oi.atributos ->> 'migracion_codigo' = '20260901_001_INTERCOMPANIA_BASE'
ORDER BY oi.fecha_operacion, oi.id;

SELECT
    count(*) AS operaciones,
    sum(monto) AS monto_total,
    count(*) FILTER (WHERE estado = 'CONFIRMADA') AS confirmadas,
    count(*) FILTER (WHERE asiento_reversion_deudora_id IS NOT NULL
                      OR asiento_reversion_acreedora_id IS NOT NULL) AS con_reversion
FROM contabilidad.operacion_intercompania
WHERE atributos ->> 'migracion_codigo' = '20260901_001_INTERCOMPANIA_BASE';

SELECT
    oi.clave_origen,
    oi.fecha_operacion,
    ad.id AS asiento_deudora,
    ad.fecha AS fecha_asiento_deudora,
    ad.estado AS estado_asiento_deudora,
    aa.id AS asiento_acreedora,
    aa.fecha AS fecha_asiento_acreedora,
    aa.estado AS estado_asiento_acreedora,
    (
        SELECT COALESCE(sum(x.debe), 0) - COALESCE(sum(x.haber), 0)
        FROM contabilidad.asiento_detalle x
        WHERE x.asiento_id = ad.id
    ) AS diferencia_deudora,
    (
        SELECT COALESCE(sum(x.debe), 0) - COALESCE(sum(x.haber), 0)
        FROM contabilidad.asiento_detalle x
        WHERE x.asiento_id = aa.id
    ) AS diferencia_acreedora
FROM contabilidad.operacion_intercompania oi
JOIN contabilidad.asiento ad ON ad.id = oi.asiento_unidad_deudora_id
JOIN contabilidad.asiento aa ON aa.id = oi.asiento_unidad_acreedora_id
WHERE oi.atributos ->> 'migracion_codigo' = '20260901_001_INTERCOMPANIA_BASE'
ORDER BY oi.fecha_operacion, oi.id;

COMMIT;
