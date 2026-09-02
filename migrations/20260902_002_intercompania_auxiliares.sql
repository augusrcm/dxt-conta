-- ============================================================================
-- DXT-CONTA
-- Migración: 20260902_002_INTERCOMPANIA_AUXILIARES
-- Objetivo:
--   1) Garantizar un auxiliar canónico activo por unidad de negocio activa.
--   2) Relacionar ese auxiliar con CxC/CxP entre empresas relacionadas.
--   3) Automatizar la misma configuración para nuevas unidades de negocio.
--
-- Requiere: 20260901_001_INTERCOMPANIA_BASE
-- Ejecución: LOCAL primero; después, el MISMO archivo en PRODUCCIÓN.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

SELECT pg_advisory_xact_lock(
    hashtextextended('DXT-CONTA:20260902_002_INTERCOMPANIA_AUXILIARES', 0)
);

DO $precheck$
DECLARE
    v_checksum constant varchar(64) := '32e1f45ea350b61e0086bb69a6f3da0a411667d81f993331261862739ca7ec2b';
    v_existente varchar(64);
    v_count integer;
BEGIN
    IF to_regclass('contabilidad.sistema_migracion') IS NULL
       OR to_regclass('contabilidad.operacion_intercompania') IS NULL THEN
        RAISE EXCEPTION 'Falta 20260901_001_INTERCOMPANIA_BASE. Ejecute primero la migración base intercompañía.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM contabilidad.sistema_migracion
        WHERE codigo = '20260901_001_INTERCOMPANIA_BASE'
    ) THEN
        RAISE EXCEPTION '20260901_001_INTERCOMPANIA_BASE no figura aplicada.';
    END IF;

    SELECT checksum INTO v_existente
    FROM contabilidad.sistema_migracion
    WHERE codigo = '20260902_002_INTERCOMPANIA_AUXILIARES';

    IF v_existente IS NOT NULL AND v_existente <> v_checksum THEN
        RAISE EXCEPTION 'La migración 002 ya figura aplicada con checksum distinto: %', v_existente;
    END IF;

    SELECT count(*) INTO v_count
    FROM (VALUES ('1.1.2.004'), ('2.1.1.003')) AS x(codigo)
    LEFT JOIN contabilidad.cuenta c ON c.codigo = x.codigo
    WHERE c.codigo IS NULL
       OR c.activo IS NOT TRUE
       OR c.es_postable IS NOT TRUE
       OR c.requiere_auxiliar IS NOT TRUE;

    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Las cuentas 1.1.2.004 y 2.1.1.003 deben existir, estar activas, ser postables y requerir auxiliar.';
    END IF;

    SELECT count(*) INTO v_count
    FROM (
        SELECT ref_id
        FROM contabilidad.auxiliar
        WHERE origen_tabla = 'contabilidad.unidad_negocio'
          AND ref_id IS NOT NULL
          AND activo IS TRUE
        GROUP BY ref_id
        HAVING count(*) > 1
    ) d;

    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Existen unidades con más de un auxiliar canónico activo. Se detiene para no elegir uno arbitrariamente.';
    END IF;
END
$precheck$;

-- Un auxiliar canónico activo por unidad. El índice se crea solo después del precheck.
CREATE UNIQUE INDEX IF NOT EXISTS uq_auxiliar_unidad_negocio_canonico_activo
    ON contabilidad.auxiliar (origen_tabla, ref_id)
    WHERE origen_tabla = 'contabilidad.unidad_negocio'
      AND ref_id IS NOT NULL
      AND activo IS TRUE;

-- Crear auxiliar canónico para unidades activas que aún no tengan uno.
INSERT INTO contabilidad.auxiliar (
    tipo, origen_tabla, ref_id, codigo_externo, nit_ci, nombre, razon_social,
    es_ocasional, activo, creado_en, actualizado_en, observaciones
)
SELECT
    'OTRO'::contabilidad.tipo_auxiliar_enum,
    'contabilidad.unidad_negocio',
    un.id,
    un.codigo,
    un.nit,
    un.nombre,
    un.nombre,
    FALSE,
    TRUE,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    'Auxiliar canónico automático para operaciones intercompañía.'
FROM contabilidad.unidad_negocio un
WHERE un.activo IS TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM contabilidad.auxiliar a
      WHERE a.origen_tabla = 'contabilidad.unidad_negocio'
        AND a.ref_id = un.id
        AND a.activo IS TRUE
  );

-- Sincronizar metadatos del auxiliar canónico sin alterar su identidad histórica.
UPDATE contabilidad.auxiliar a
SET codigo_externo = un.codigo,
    nit_ci = un.nit,
    nombre = un.nombre,
    razon_social = un.nombre,
    actualizado_en = CURRENT_TIMESTAMP
FROM contabilidad.unidad_negocio un
WHERE a.origen_tabla = 'contabilidad.unidad_negocio'
  AND a.ref_id = un.id
  AND a.activo IS TRUE
  AND un.activo IS TRUE;

-- Cada auxiliar canónico puede representar a la unidad tanto como CxC como CxP relacionada.
INSERT INTO contabilidad.auxiliar_cuenta (auxiliar_id, cuenta_codigo, activo, creado_en)
SELECT a.id, c.codigo, TRUE, CURRENT_TIMESTAMP
FROM contabilidad.auxiliar a
CROSS JOIN (VALUES ('1.1.2.004'), ('2.1.1.003')) AS c(codigo)
WHERE a.origen_tabla = 'contabilidad.unidad_negocio'
  AND a.ref_id IS NOT NULL
  AND a.activo IS TRUE
ON CONFLICT (auxiliar_id, cuenta_codigo)
DO UPDATE SET activo = TRUE;

-- La misma regla se aplica automáticamente al crear/editar futuras unidades.
CREATE OR REPLACE FUNCTION contabilidad.fn_unidad_negocio_intercompania_aux()
RETURNS trigger
LANGUAGE plpgsql
AS $BODY$
DECLARE
    v_auxiliar_id bigint;
    v_count integer;
BEGIN
    IF NEW.activo IS NOT TRUE THEN
        RETURN NEW;
    END IF;

    SELECT min(a.id), count(*)
      INTO v_auxiliar_id, v_count
      FROM contabilidad.auxiliar a
     WHERE a.origen_tabla = 'contabilidad.unidad_negocio'
       AND a.ref_id = NEW.id
       AND a.activo IS TRUE;

    IF v_count > 1 THEN
        RAISE EXCEPTION 'Unidad % tiene % auxiliares canónicos activos.', NEW.codigo, v_count;
    END IF;

    IF v_count = 0 THEN
        INSERT INTO contabilidad.auxiliar (
            tipo, origen_tabla, ref_id, codigo_externo, nit_ci, nombre, razon_social,
            es_ocasional, activo, creado_en, actualizado_en, observaciones
        ) VALUES (
            'OTRO'::contabilidad.tipo_auxiliar_enum,
            'contabilidad.unidad_negocio', NEW.id, NEW.codigo, NEW.nit, NEW.nombre, NEW.nombre,
            FALSE, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
            'Auxiliar canónico automático para operaciones intercompañía.'
        ) RETURNING id INTO v_auxiliar_id;
    ELSE
        UPDATE contabilidad.auxiliar
           SET codigo_externo = NEW.codigo,
               nit_ci = NEW.nit,
               nombre = NEW.nombre,
               razon_social = NEW.nombre,
               actualizado_en = CURRENT_TIMESTAMP
         WHERE id = v_auxiliar_id;
    END IF;

    INSERT INTO contabilidad.auxiliar_cuenta (auxiliar_id, cuenta_codigo, activo, creado_en)
    VALUES
        (v_auxiliar_id, '1.1.2.004', TRUE, CURRENT_TIMESTAMP),
        (v_auxiliar_id, '2.1.1.003', TRUE, CURRENT_TIMESTAMP)
    ON CONFLICT (auxiliar_id, cuenta_codigo)
    DO UPDATE SET activo = TRUE;

    RETURN NEW;
END
$BODY$;

DROP TRIGGER IF EXISTS trg_unidad_negocio_intercompania_aux ON contabilidad.unidad_negocio;
CREATE TRIGGER trg_unidad_negocio_intercompania_aux
AFTER INSERT OR UPDATE OF codigo, nombre, nit, activo
ON contabilidad.unidad_negocio
FOR EACH ROW
EXECUTE FUNCTION contabilidad.fn_unidad_negocio_intercompania_aux();

-- Verificación posterior: exactamente un auxiliar activo por cada unidad activa y ambas relaciones.
DO $postcheck$
DECLARE
    v_count integer;
BEGIN
    SELECT count(*) INTO v_count
    FROM contabilidad.unidad_negocio un
    WHERE un.activo IS TRUE
      AND 1 <> (
          SELECT count(*)
          FROM contabilidad.auxiliar a
          WHERE a.origen_tabla = 'contabilidad.unidad_negocio'
            AND a.ref_id = un.id
            AND a.activo IS TRUE
      );
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Postcheck: % unidad(es) activa(s) no tienen exactamente un auxiliar canónico activo.', v_count;
    END IF;

    SELECT count(*) INTO v_count
    FROM contabilidad.unidad_negocio un
    JOIN contabilidad.auxiliar a
      ON a.origen_tabla = 'contabilidad.unidad_negocio'
     AND a.ref_id = un.id
     AND a.activo IS TRUE
    CROSS JOIN (VALUES ('1.1.2.004'), ('2.1.1.003')) AS c(codigo)
    WHERE un.activo IS TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM contabilidad.auxiliar_cuenta ac
          WHERE ac.auxiliar_id = a.id
            AND ac.cuenta_codigo = c.codigo
            AND ac.activo IS TRUE
      );
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Postcheck: faltan % relación(es) auxiliar-cuenta intercompañía.', v_count;
    END IF;
END
$postcheck$;

INSERT INTO contabilidad.sistema_migracion (
    codigo, descripcion, checksum, aplicado_por, base_datos, usuario_bd, atributos
)
VALUES (
    '20260902_002_INTERCOMPANIA_AUXILIARES',
    'Auxiliares canónicos genéricos de unidades y relaciones CxC/CxP intercompañía, con automatización para nuevas unidades.',
    '32e1f45ea350b61e0086bb69a6f3da0a411667d81f993331261862739ca7ec2b',
    current_user, current_database(), current_user,
    jsonb_build_object('cuenta_cxc', '1.1.2.004', 'cuenta_cxp', '2.1.1.003', 'auto_nuevas_unidades', true)
)
ON CONFLICT (codigo) DO NOTHING;

-- Salida de validación visible en Navicat.
SELECT
    un.id AS unidad_id,
    un.codigo,
    un.nombre,
    a.id AS auxiliar_canonico_id,
    bool_and(ac.activo) AS relaciones_activas,
    string_agg(ac.cuenta_codigo, ', ' ORDER BY ac.cuenta_codigo) AS cuentas_intercompania
FROM contabilidad.unidad_negocio un
JOIN contabilidad.auxiliar a
  ON a.origen_tabla = 'contabilidad.unidad_negocio'
 AND a.ref_id = un.id
 AND a.activo IS TRUE
JOIN contabilidad.auxiliar_cuenta ac
  ON ac.auxiliar_id = a.id
 AND ac.cuenta_codigo IN ('1.1.2.004', '2.1.1.003')
WHERE un.activo IS TRUE
GROUP BY un.id, un.codigo, un.nombre, a.id
ORDER BY un.codigo;

COMMIT;
