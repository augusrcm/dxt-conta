-- ============================================================
-- TABLA: tipo_cambio
-- Descripción: Tipo de cambio diario USD paralelo y UFV
-- Un registro por día
-- ============================================================

DROP TABLE IF EXISTS tipo_cambio;

CREATE TABLE tipo_cambio (
    fecha DATE NOT NULL PRIMARY KEY,
    usd_paralelo DECIMAL(10, 4) NOT NULL CHECK (usd_paralelo > 0),
    ufv DECIMAL(12, 6) NOT NULL CHECK (ufv > 0),
    registrado_por VARCHAR(20) NOT NULL,
    registrado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_por VARCHAR(20),
    actualizado_en DATETIME
);

-- Índice para búsquedas rápidas
CREATE INDEX idx_tipo_cambio_fecha ON tipo_cambio(fecha DESC);

-- Comentarios (SQLite no soporta COMMENT, pero los dejamos como documentación)
-- fecha: Fecha del tipo de cambio (PK)
-- usd_paralelo: Tipo de cambio USD mercado paralelo (Bs por 1 USD)
-- ufv: Unidad de Fomento a la Vivienda BCB (valor en Bs)
-- registrado_por: Usuario que registró el valor
-- registrado_en: Fecha/hora de registro
-- actualizado_por: Usuario que actualizó el valor
-- actualizado_en: Fecha/hora de última actualización

-- ============================================================
-- DATOS INICIALES (OPCIONAL)
-- ============================================================
INSERT OR IGNORE INTO tipo_cambio (fecha, usd_paralelo, ufv, registrado_por) 
VALUES (DATE('now'), 6.9600, 2.445000, 'admin');
