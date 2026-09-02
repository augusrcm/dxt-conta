--
-- PostgreSQL database dump
--

\restrict HGlDnf5nJeGXoli622B7IeAaRTud8K8lVzS70mkdN3QrYwU5xZVROK03gN6r2ri

-- Dumped from database version 17.0
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY contabilidad.venta DROP CONSTRAINT IF EXISTS venta_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta DROP CONSTRAINT IF EXISTS venta_factura_electronica_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta_detalle DROP CONSTRAINT IF EXISTS venta_detalle_venta_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta_detalle DROP CONSTRAINT IF EXISTS venta_detalle_cuenta_ingreso_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta_detalle DROP CONSTRAINT IF EXISTS venta_detalle_centro_costo_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta DROP CONSTRAINT IF EXISTS venta_contra_cuenta_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta DROP CONSTRAINT IF EXISTS venta_cliente_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta DROP CONSTRAINT IF EXISTS venta_asiento_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_proveedor_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_cuenta_bancaria_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_contra_cuenta_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_caja_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_asiento_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_contra_cuenta_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_caja_origen_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_caja_destino_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_banco_origen_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_banco_destino_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_asiento_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.esquema_restauracion_log DROP CONSTRAINT IF EXISTS fk_restauracion_backup;
ALTER TABLE IF EXISTS ONLY contabilidad.pago_detalle DROP CONSTRAINT IF EXISTS fk_pago_detalle_pago;
ALTER TABLE IF EXISTS ONLY contabilidad.pago_detalle DROP CONSTRAINT IF EXISTS fk_pago_detalle_compromiso;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_regularizacion DROP CONSTRAINT IF EXISTS fk_factura_regularizacion_factura;
ALTER TABLE IF EXISTS ONLY contabilidad.cuenta DROP CONSTRAINT IF EXISTS fk_cuenta_padre;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro_detalle DROP CONSTRAINT IF EXISTS fk_cobro_detalle_compromiso;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro_detalle DROP CONSTRAINT IF EXISTS fk_cobro_detalle_cobro;
ALTER TABLE IF EXISTS ONLY contabilidad.arqueo_caja DROP CONSTRAINT IF EXISTS fk_arqueo_caja_caja;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_electronica DROP CONSTRAINT IF EXISTS factura_electronica_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_electronica DROP CONSTRAINT IF EXISTS factura_electronica_cliente_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_aplicacion DROP CONSTRAINT IF EXISTS factura_aplicacion_venta_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_aplicacion DROP CONSTRAINT IF EXISTS factura_aplicacion_factura_electronica_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_aplicacion DROP CONSTRAINT IF EXISTS factura_aplicacion_cobro_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.documento_asiento DROP CONSTRAINT IF EXISTS documento_asiento_asiento_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cuenta_bancaria DROP CONSTRAINT IF EXISTS cuenta_bancaria_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cuenta_bancaria DROP CONSTRAINT IF EXISTS cuenta_bancaria_cuenta_contable_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cuenta_bancaria DROP CONSTRAINT IF EXISTS cuenta_bancaria_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compromiso_detalle DROP CONSTRAINT IF EXISTS compromiso_detalle_compromiso_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra DROP CONSTRAINT IF EXISTS compra_proveedor_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra DROP CONSTRAINT IF EXISTS compra_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra_detalle DROP CONSTRAINT IF EXISTS compra_detalle_cuenta_gasto_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra_detalle DROP CONSTRAINT IF EXISTS compra_detalle_compra_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra_detalle DROP CONSTRAINT IF EXISTS compra_detalle_centro_costo_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra DROP CONSTRAINT IF EXISTS compra_contra_cuenta_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra DROP CONSTRAINT IF EXISTS compra_asiento_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_cuenta_bancaria_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_contra_cuenta_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_cliente_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_caja_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_asiento_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.caja DROP CONSTRAINT IF EXISTS caja_cuenta_contable_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.auxiliar_cuenta DROP CONSTRAINT IF EXISTS auxiliar_cuenta_cuenta_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.auxiliar_cuenta DROP CONSTRAINT IF EXISTS auxiliar_cuenta_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento DROP CONSTRAINT IF EXISTS asiento_moneda_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento_detalle DROP CONSTRAINT IF EXISTS asiento_detalle_cuenta_codigo_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento_detalle DROP CONSTRAINT IF EXISTS asiento_detalle_centro_costo_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento_detalle DROP CONSTRAINT IF EXISTS asiento_detalle_auxiliar_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento_detalle DROP CONSTRAINT IF EXISTS asiento_detalle_asiento_id_fkey;
ALTER TABLE IF EXISTS ONLY contabilidad._tipo_cambio DROP CONSTRAINT IF EXISTS _tipo_cambio_moneda_codigo_fkey;
DROP TRIGGER IF EXISTS trg_validar_cuenta_postable ON contabilidad.asiento_detalle;
DROP TRIGGER IF EXISTS trg_pago_estado_au ON contabilidad.pago;
DROP TRIGGER IF EXISTS trg_pago_detalle_biu ON contabilidad.pago_detalle;
DROP TRIGGER IF EXISTS trg_pago_detalle_aiud ON contabilidad.pago_detalle;
DROP TRIGGER IF EXISTS trg_gestion_control_actualizado_en ON contabilidad.gestion_control;
DROP TRIGGER IF EXISTS trg_gestion_configuracion_actualizado_en ON contabilidad.gestion_configuracion;
DROP TRIGGER IF EXISTS trg_cobro_estado_au ON contabilidad.cobro;
DROP TRIGGER IF EXISTS trg_cobro_detalle_biu ON contabilidad.cobro_detalle;
DROP TRIGGER IF EXISTS trg_cobro_detalle_aiud ON contabilidad.cobro_detalle;
DROP TRIGGER IF EXISTS trg_arqueo_caja_biu ON contabilidad.arqueo_caja;
DROP INDEX IF EXISTS contabilidad.uq_pago_detalle_compromiso_unico;
DROP INDEX IF EXISTS contabilidad.uq_gestion_configuracion_activa_unica;
DROP INDEX IF EXISTS contabilidad.uq_gbloqueo_activo_por_gestion;
DROP INDEX IF EXISTS contabilidad.uq_factura_regularizacion_cierre_manual_activo;
DROP INDEX IF EXISTS contabilidad.uq_factura_aplicacion_venta_factura;
DROP INDEX IF EXISTS contabilidad.uq_factura_aplicacion_cobro_factura;
DROP INDEX IF EXISTS contabilidad.uq_cobro_detalle_compromiso_unico;
DROP INDEX IF EXISTS contabilidad.uq_arqueo_caja_confirmado_fecha;
DROP INDEX IF EXISTS contabilidad.idx_venta_fecha;
DROP INDEX IF EXISTS contabilidad.idx_venta_factura_ext;
DROP INDEX IF EXISTS contabilidad.idx_venta_estado;
DROP INDEX IF EXISTS contabilidad.idx_venta_detalle_venta;
DROP INDEX IF EXISTS contabilidad.idx_venta_detalle_cuenta;
DROP INDEX IF EXISTS contabilidad.idx_venta_cliente_emp;
DROP INDEX IF EXISTS contabilidad.idx_venta_cliente_aux;
DROP INDEX IF EXISTS contabilidad.idx_restauracion_gestion;
DROP INDEX IF EXISTS contabilidad.idx_restauracion_backup;
DROP INDEX IF EXISTS contabilidad.idx_pago_proveedor;
DROP INDEX IF EXISTS contabilidad.idx_pago_origen_operacion;
DROP INDEX IF EXISTS contabilidad.idx_pago_fecha;
DROP INDEX IF EXISTS contabilidad.idx_pago_estado_fecha;
DROP INDEX IF EXISTS contabilidad.idx_pago_estado;
DROP INDEX IF EXISTS contabilidad.idx_pago_detalle_pago;
DROP INDEX IF EXISTS contabilidad.idx_pago_detalle_compromiso;
DROP INDEX IF EXISTS contabilidad.idx_mov_tesoreria_fecha;
DROP INDEX IF EXISTS contabilidad.idx_mov_tesoreria_estado;
DROP INDEX IF EXISTS contabilidad.idx_gpbitacora_tipo;
DROP INDEX IF EXISTS contabilidad.idx_gpbitacora_gestion_origen;
DROP INDEX IF EXISTS contabilidad.idx_gpbitacora_gestion_destino;
DROP INDEX IF EXISTS contabilidad.idx_gpbitacora_fecha;
DROP INDEX IF EXISTS contabilidad.idx_gpbitacora_estado;
DROP INDEX IF EXISTS contabilidad.idx_gestion_control_estado;
DROP INDEX IF EXISTS contabilidad.idx_gbloqueo_gestion_origen;
DROP INDEX IF EXISTS contabilidad.idx_gbloqueo_estado;
DROP INDEX IF EXISTS contabilidad.idx_factura_regularizacion_tipo_activa;
DROP INDEX IF EXISTS contabilidad.idx_factura_regularizacion_factura_activa;
DROP INDEX IF EXISTS contabilidad.idx_factura_regularizacion_factura;
DROP INDEX IF EXISTS contabilidad.idx_factura_electronica_numero;
DROP INDEX IF EXISTS contabilidad.idx_factura_electronica_estado;
DROP INDEX IF EXISTS contabilidad.idx_factura_electronica_cobranza_cliente;
DROP INDEX IF EXISTS contabilidad.idx_factura_electronica_cliente_emp;
DROP INDEX IF EXISTS contabilidad.idx_factura_electronica_cliente_aux;
DROP INDEX IF EXISTS contabilidad.idx_factura_aplicacion_venta;
DROP INDEX IF EXISTS contabilidad.idx_factura_aplicacion_factura;
DROP INDEX IF EXISTS contabilidad.idx_factura_aplicacion_cobro;
DROP INDEX IF EXISTS contabilidad.idx_documento_asiento_origen;
DROP INDEX IF EXISTS contabilidad.idx_cuenta_tipo;
DROP INDEX IF EXISTS contabilidad.idx_cuenta_postable;
DROP INDEX IF EXISTS contabilidad.idx_cuenta_padre;
DROP INDEX IF EXISTS contabilidad.idx_cuenta_bancaria_cuenta;
DROP INDEX IF EXISTS contabilidad.idx_cuenta_bancaria_aux;
DROP INDEX IF EXISTS contabilidad.idx_cuenta_activo;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_tipo;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_gestion;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_detalle_pendiente_venc;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_detalle_fecha;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_detalle_estado;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_detalle_compromiso;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_cuenta;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_auxiliar;
DROP INDEX IF EXISTS contabilidad.idx_compromiso_activo;
DROP INDEX IF EXISTS contabilidad.idx_compra_proveedor;
DROP INDEX IF EXISTS contabilidad.idx_compra_numero_factura;
DROP INDEX IF EXISTS contabilidad.idx_compra_fecha;
DROP INDEX IF EXISTS contabilidad.idx_compra_estado;
DROP INDEX IF EXISTS contabilidad.idx_compra_detalle_cuenta;
DROP INDEX IF EXISTS contabilidad.idx_compra_detalle_compra;
DROP INDEX IF EXISTS contabilidad.idx_cobro_origen_operacion;
DROP INDEX IF EXISTS contabilidad.idx_cobro_fecha;
DROP INDEX IF EXISTS contabilidad.idx_cobro_estado;
DROP INDEX IF EXISTS contabilidad.idx_cobro_detalle_compromiso;
DROP INDEX IF EXISTS contabilidad.idx_cobro_detalle_cobro;
DROP INDEX IF EXISTS contabilidad.idx_cobro_cliente;
DROP INDEX IF EXISTS contabilidad.idx_caja_cuenta;
DROP INDEX IF EXISTS contabilidad.idx_backup_catalogo_gestion;
DROP INDEX IF EXISTS contabilidad.idx_backup_catalogo_estado;
DROP INDEX IF EXISTS contabilidad.idx_auxiliar_tipo;
DROP INDEX IF EXISTS contabilidad.idx_auxiliar_ref;
DROP INDEX IF EXISTS contabilidad.idx_auxiliar_nombre;
DROP INDEX IF EXISTS contabilidad.idx_auxiliar_nit;
DROP INDEX IF EXISTS contabilidad.idx_auxiliar_cuenta_cuenta;
DROP INDEX IF EXISTS contabilidad.idx_auxiliar_cuenta_aux;
DROP INDEX IF EXISTS contabilidad.idx_auxiliar_activo;
DROP INDEX IF EXISTS contabilidad.idx_asiento_origen;
DROP INDEX IF EXISTS contabilidad.idx_asiento_fecha;
DROP INDEX IF EXISTS contabilidad.idx_asiento_estado;
DROP INDEX IF EXISTS contabilidad.idx_asiento_detalle_cuenta;
DROP INDEX IF EXISTS contabilidad.idx_asiento_detalle_auxiliar;
DROP INDEX IF EXISTS contabilidad.idx_asiento_detalle_asiento;
DROP INDEX IF EXISTS contabilidad.idx_arqueo_caja_fecha;
DROP INDEX IF EXISTS contabilidad.idx_arqueo_caja_estado;
DROP INDEX IF EXISTS contabilidad.idx_arqueo_caja_caja;
ALTER TABLE IF EXISTS ONLY contabilidad.venta DROP CONSTRAINT IF EXISTS venta_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta_detalle DROP CONSTRAINT IF EXISTS venta_detalle_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.venta DROP CONSTRAINT IF EXISTS venta_asiento_id_key;
ALTER TABLE IF EXISTS ONLY contabilidad.venta_detalle DROP CONSTRAINT IF EXISTS uq_venta_detalle_secuencia;
ALTER TABLE IF EXISTS ONLY contabilidad._tipo_cambio DROP CONSTRAINT IF EXISTS uq_tipo_cambio;
ALTER TABLE IF EXISTS ONLY contabilidad.pago_detalle DROP CONSTRAINT IF EXISTS uq_pago_detalle_secuencia;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_electronica DROP CONSTRAINT IF EXISTS uq_factura_electronica;
ALTER TABLE IF EXISTS ONLY contabilidad.documento_asiento DROP CONSTRAINT IF EXISTS uq_documento_asiento_asiento;
ALTER TABLE IF EXISTS ONLY contabilidad.documento_asiento DROP CONSTRAINT IF EXISTS uq_documento_asiento;
ALTER TABLE IF EXISTS ONLY contabilidad.cuenta_bancaria DROP CONSTRAINT IF EXISTS uq_cuenta_bancaria;
ALTER TABLE IF EXISTS ONLY contabilidad.compra_detalle DROP CONSTRAINT IF EXISTS uq_compra_detalle_secuencia;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro_detalle DROP CONSTRAINT IF EXISTS uq_cobro_detalle_secuencia;
ALTER TABLE IF EXISTS ONLY contabilidad.auxiliar_cuenta DROP CONSTRAINT IF EXISTS uq_auxiliar_cuenta;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento_detalle DROP CONSTRAINT IF EXISTS uq_asiento_detalle_secuencia;
ALTER TABLE IF EXISTS ONLY contabilidad.sistema_control_sesion DROP CONSTRAINT IF EXISTS sistema_control_sesion_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago_detalle DROP CONSTRAINT IF EXISTS pago_detalle_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.pago DROP CONSTRAINT IF EXISTS pago_asiento_id_key;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.movimiento_tesoreria DROP CONSTRAINT IF EXISTS movimiento_tesoreria_asiento_id_key;
ALTER TABLE IF EXISTS ONLY contabilidad.moneda DROP CONSTRAINT IF EXISTS moneda_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.gestion_proceso_bitacora DROP CONSTRAINT IF EXISTS gestion_proceso_bitacora_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.gestion_control DROP CONSTRAINT IF EXISTS gestion_control_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.gestion_configuracion DROP CONSTRAINT IF EXISTS gestion_configuracion_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.gestion_bloqueo_critico DROP CONSTRAINT IF EXISTS gestion_bloqueo_critico_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_regularizacion DROP CONSTRAINT IF EXISTS factura_regularizacion_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_electronica DROP CONSTRAINT IF EXISTS factura_electronica_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.factura_aplicacion DROP CONSTRAINT IF EXISTS factura_aplicacion_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.esquema_restauracion_log DROP CONSTRAINT IF EXISTS esquema_restauracion_log_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.esquema_backup_catalogo DROP CONSTRAINT IF EXISTS esquema_backup_catalogo_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.documento_asiento DROP CONSTRAINT IF EXISTS documento_asiento_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cuenta DROP CONSTRAINT IF EXISTS cuenta_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cuenta_bancaria DROP CONSTRAINT IF EXISTS cuenta_bancaria_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compromiso DROP CONSTRAINT IF EXISTS compromiso_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compromiso_detalle DROP CONSTRAINT IF EXISTS compromiso_detalle_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compromiso DROP CONSTRAINT IF EXISTS compromiso_codigo_key;
ALTER TABLE IF EXISTS ONLY contabilidad.compra DROP CONSTRAINT IF EXISTS compra_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra_detalle DROP CONSTRAINT IF EXISTS compra_detalle_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.compra DROP CONSTRAINT IF EXISTS compra_asiento_id_key;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro_detalle DROP CONSTRAINT IF EXISTS cobro_detalle_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.cobro DROP CONSTRAINT IF EXISTS cobro_asiento_id_key;
ALTER TABLE IF EXISTS ONLY contabilidad.centro_costo DROP CONSTRAINT IF EXISTS centro_costo_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.centro_costo DROP CONSTRAINT IF EXISTS centro_costo_codigo_key;
ALTER TABLE IF EXISTS ONLY contabilidad.caja DROP CONSTRAINT IF EXISTS caja_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.caja DROP CONSTRAINT IF EXISTS caja_codigo_key;
ALTER TABLE IF EXISTS ONLY contabilidad.auxiliar DROP CONSTRAINT IF EXISTS auxiliar_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.auxiliar_cuenta DROP CONSTRAINT IF EXISTS auxiliar_cuenta_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento DROP CONSTRAINT IF EXISTS asiento_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.asiento_detalle DROP CONSTRAINT IF EXISTS asiento_detalle_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad.arqueo_caja DROP CONSTRAINT IF EXISTS arqueo_caja_pkey;
ALTER TABLE IF EXISTS ONLY contabilidad._tipo_cambio DROP CONSTRAINT IF EXISTS _tipo_cambio_pkey;
ALTER TABLE IF EXISTS contabilidad.venta_detalle ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.venta ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.pago_detalle ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.pago ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.movimiento_tesoreria ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.factura_regularizacion ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.factura_electronica ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.factura_aplicacion ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.documento_asiento ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.cuenta_bancaria ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.compromiso_detalle ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.compromiso ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.compra_detalle ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.compra ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.cobro_detalle ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.cobro ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.centro_costo ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.caja ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.auxiliar_cuenta ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.auxiliar ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.asiento_detalle ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.asiento ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad.arqueo_caja ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS contabilidad._tipo_cambio ALTER COLUMN id DROP DEFAULT;
DROP VIEW IF EXISTS contabilidad.vw_saldo_factura_electronica;
DROP SEQUENCE IF EXISTS contabilidad.venta_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.venta_detalle_id_seq;
DROP TABLE IF EXISTS contabilidad.venta_detalle;
DROP TABLE IF EXISTS contabilidad.venta;
DROP TABLE IF EXISTS contabilidad.tipo_cambio;
DROP TABLE IF EXISTS contabilidad.sistema_control_sesion;
DROP SEQUENCE IF EXISTS contabilidad.pago_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.pago_detalle_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.movimiento_tesoreria_id_seq;
DROP TABLE IF EXISTS contabilidad.movimiento_tesoreria;
DROP TABLE IF EXISTS contabilidad.moneda;
DROP SEQUENCE IF EXISTS contabilidad.gestion_proceso_bitacora_id_seq;
DROP TABLE IF EXISTS contabilidad.gestion_proceso_bitacora;
DROP TABLE IF EXISTS contabilidad.gestion_control;
DROP SEQUENCE IF EXISTS contabilidad.gestion_configuracion_id_seq;
DROP TABLE IF EXISTS contabilidad.gestion_configuracion;
DROP SEQUENCE IF EXISTS contabilidad.gestion_bloqueo_critico_id_seq;
DROP TABLE IF EXISTS contabilidad.gestion_bloqueo_critico;
DROP SEQUENCE IF EXISTS contabilidad.factura_regularizacion_id_seq;
DROP TABLE IF EXISTS contabilidad.factura_regularizacion;
DROP SEQUENCE IF EXISTS contabilidad.factura_electronica_id_seq;
DROP TABLE IF EXISTS contabilidad.factura_electronica;
DROP SEQUENCE IF EXISTS contabilidad.factura_aplicacion_id_seq;
DROP TABLE IF EXISTS contabilidad.factura_aplicacion;
DROP SEQUENCE IF EXISTS contabilidad.esquema_restauracion_log_id_seq;
DROP TABLE IF EXISTS contabilidad.esquema_restauracion_log;
DROP SEQUENCE IF EXISTS contabilidad.esquema_backup_catalogo_id_seq;
DROP TABLE IF EXISTS contabilidad.esquema_backup_catalogo;
DROP SEQUENCE IF EXISTS contabilidad.documento_asiento_id_seq;
DROP TABLE IF EXISTS contabilidad.documento_asiento;
DROP SEQUENCE IF EXISTS contabilidad.cuenta_bancaria_id_seq;
DROP TABLE IF EXISTS contabilidad.cuenta_bancaria;
DROP TABLE IF EXISTS contabilidad.cuenta;
DROP SEQUENCE IF EXISTS contabilidad.compromiso_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.compromiso_detalle_id_seq;
DROP TABLE IF EXISTS contabilidad.compromiso_detalle;
DROP SEQUENCE IF EXISTS contabilidad.compromiso_codigo_seq;
DROP VIEW IF EXISTS contabilidad.compromiso_aplicacion;
DROP TABLE IF EXISTS contabilidad.pago_detalle;
DROP TABLE IF EXISTS contabilidad.pago;
DROP TABLE IF EXISTS contabilidad.compromiso;
DROP SEQUENCE IF EXISTS contabilidad.compra_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.compra_detalle_id_seq;
DROP TABLE IF EXISTS contabilidad.compra_detalle;
DROP TABLE IF EXISTS contabilidad.compra;
DROP SEQUENCE IF EXISTS contabilidad.cobro_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.cobro_detalle_id_seq;
DROP TABLE IF EXISTS contabilidad.cobro_detalle;
DROP TABLE IF EXISTS contabilidad.cobro;
DROP SEQUENCE IF EXISTS contabilidad.centro_costo_id_seq;
DROP TABLE IF EXISTS contabilidad.centro_costo;
DROP SEQUENCE IF EXISTS contabilidad.caja_id_seq;
DROP TABLE IF EXISTS contabilidad.caja;
DROP SEQUENCE IF EXISTS contabilidad.auxiliar_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.auxiliar_cuenta_id_seq;
DROP TABLE IF EXISTS contabilidad.auxiliar_cuenta;
DROP TABLE IF EXISTS contabilidad.auxiliar;
DROP SEQUENCE IF EXISTS contabilidad.asiento_id_seq;
DROP SEQUENCE IF EXISTS contabilidad.asiento_detalle_id_seq;
DROP TABLE IF EXISTS contabilidad.asiento_detalle;
DROP TABLE IF EXISTS contabilidad.asiento;
DROP SEQUENCE IF EXISTS contabilidad.arqueo_caja_id_seq;
DROP TABLE IF EXISTS contabilidad.arqueo_caja;
DROP SEQUENCE IF EXISTS contabilidad._tipo_cambio_id_seq;
DROP TABLE IF EXISTS contabilidad._tipo_cambio;
DROP FUNCTION IF EXISTS contabilidad.fn_validar_cuenta_postable();
DROP FUNCTION IF EXISTS contabilidad.fn_validar_asiento_balanceado(p_asiento_id bigint);
DROP FUNCTION IF EXISTS contabilidad.fn_set_actualizado_en();
DROP FUNCTION IF EXISTS contabilidad.fn_recalcular_pago_total(p_pago_id bigint);
DROP FUNCTION IF EXISTS contabilidad.fn_recalcular_compromiso_detalle(p_compromiso_detalle_id bigint);
DROP FUNCTION IF EXISTS contabilidad.fn_recalcular_cobro_total(p_cobro_id bigint);
DROP FUNCTION IF EXISTS contabilidad.fn_pago_estado_au();
DROP FUNCTION IF EXISTS contabilidad.fn_pago_detalle_biu();
DROP FUNCTION IF EXISTS contabilidad.fn_pago_detalle_aiud();
DROP FUNCTION IF EXISTS contabilidad.fn_cobro_estado_au();
DROP FUNCTION IF EXISTS contabilidad.fn_cobro_detalle_biu();
DROP FUNCTION IF EXISTS contabilidad.fn_cobro_detalle_aiud();
DROP FUNCTION IF EXISTS contabilidad.fn_arqueo_caja_biu();
DROP TYPE IF EXISTS contabilidad.tipo_venta_enum;
DROP TYPE IF EXISTS contabilidad.tipo_proceso_gestion_enum;
DROP TYPE IF EXISTS contabilidad.tipo_proceso_critico_enum;
DROP TYPE IF EXISTS contabilidad.tipo_mov_tesoreria_enum;
DROP TYPE IF EXISTS contabilidad.tipo_linea_tesoreria_enum;
DROP TYPE IF EXISTS contabilidad.tipo_cuenta_enum;
DROP TYPE IF EXISTS contabilidad.tipo_compra_enum;
DROP TYPE IF EXISTS contabilidad.tipo_auxiliar_enum;
DROP TYPE IF EXISTS contabilidad.origen_tesoreria_enum;
DROP TYPE IF EXISTS contabilidad.origen_documento_enum;
DROP TYPE IF EXISTS contabilidad.naturaleza_enum;
DROP TYPE IF EXISTS contabilidad.medio_tesoreria_enum;
DROP TYPE IF EXISTS contabilidad.medio_pago_enum;
DROP TYPE IF EXISTS contabilidad.estado_restauracion_esquema_enum;
DROP TYPE IF EXISTS contabilidad.estado_proceso_gestion_enum;
DROP TYPE IF EXISTS contabilidad.estado_gestion_enum;
DROP TYPE IF EXISTS contabilidad.estado_generico_enum;
DROP TYPE IF EXISTS contabilidad.estado_factura_ext_enum;
DROP TYPE IF EXISTS contabilidad.estado_compromiso_enum;
DROP TYPE IF EXISTS contabilidad.estado_bloqueo_critico_enum;
DROP TYPE IF EXISTS contabilidad.estado_backup_esquema_enum;
DROP SCHEMA IF EXISTS contabilidad;
--
-- Name: contabilidad; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA contabilidad;


--
-- Name: estado_backup_esquema_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_backup_esquema_enum AS ENUM (
    'GENERADO',
    'FALLIDO',
    'RESTAURADO',
    'OBSOLETO'
);


--
-- Name: estado_bloqueo_critico_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_bloqueo_critico_enum AS ENUM (
    'EN_PROCESO',
    'FINALIZADO',
    'FALLIDO',
    'LIBERADO'
);


--
-- Name: estado_compromiso_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_compromiso_enum AS ENUM (
    'PENDIENTE',
    'PARCIAL',
    'CUMPLIDO',
    'INCUMPLIDO',
    'ANULADO'
);


--
-- Name: estado_factura_ext_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_factura_ext_enum AS ENUM (
    'RECIBIDA',
    'DISPONIBLE',
    'REGISTRADA',
    'COBRADA_PARCIAL',
    'COBRADA_TOTAL',
    'ANULADA'
);


--
-- Name: estado_generico_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_generico_enum AS ENUM (
    'BORRADOR',
    'CONFIRMADO',
    'ANULADO'
);


--
-- Name: estado_gestion_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_gestion_enum AS ENUM (
    'ABIERTA',
    'CERRADA'
);


--
-- Name: estado_proceso_gestion_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_proceso_gestion_enum AS ENUM (
    'PENDIENTE',
    'EN_PROCESO',
    'EJECUTADO',
    'ANULADO',
    'FALLIDO',
    'BLOQUEADO'
);


--
-- Name: estado_restauracion_esquema_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.estado_restauracion_esquema_enum AS ENUM (
    'EJECUTADA',
    'FALLIDA',
    'PARCIAL'
);


--
-- Name: medio_pago_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.medio_pago_enum AS ENUM (
    'CAJA',
    'BANCO',
    'MIXTO',
    'OTRO'
);


--
-- Name: medio_tesoreria_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.medio_tesoreria_enum AS ENUM (
    'CAJA',
    'BANCO'
);


--
-- Name: naturaleza_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.naturaleza_enum AS ENUM (
    'DEUDORA',
    'ACREEDORA'
);


--
-- Name: origen_documento_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.origen_documento_enum AS ENUM (
    'MANUAL',
    'FACTURA_EXTERNA',
    'IMPORTADO',
    'AJUSTE'
);


--
-- Name: origen_tesoreria_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.origen_tesoreria_enum AS ENUM (
    'COMPROMISO',
    'DIRECTO'
);


--
-- Name: TYPE origen_tesoreria_enum; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON TYPE contabilidad.origen_tesoreria_enum IS 'Indica si el documento de tesorería se originó por compromiso o por concepto directo.';


--
-- Name: tipo_auxiliar_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_auxiliar_enum AS ENUM (
    'CLIENTE',
    'PROVEEDOR',
    'FUNCIONARIO',
    'BANCO',
    'OTRO'
);


--
-- Name: tipo_compra_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_compra_enum AS ENUM (
    'CONTADO',
    'CREDITO'
);


--
-- Name: tipo_cuenta_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_cuenta_enum AS ENUM (
    'ACTIVO',
    'PASIVO',
    'PATRIMONIO',
    'INGRESO',
    'GASTO',
    'COSTO',
    'ORDEN'
);


--
-- Name: tipo_linea_tesoreria_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_linea_tesoreria_enum AS ENUM (
    'COMPROMISO',
    'DIRECTO'
);


--
-- Name: TYPE tipo_linea_tesoreria_enum; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON TYPE contabilidad.tipo_linea_tesoreria_enum IS 'Indica si una línea del detalle corresponde a compromiso o a concepto directo.';


--
-- Name: tipo_mov_tesoreria_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_mov_tesoreria_enum AS ENUM (
    'INGRESO',
    'EGRESO',
    'TRANSFERENCIA'
);


--
-- Name: tipo_proceso_critico_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_proceso_critico_enum AS ENUM (
    'CIERRE',
    'APERTURA',
    'REAPERTURA',
    'RESTAURACION'
);


--
-- Name: tipo_proceso_gestion_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_proceso_gestion_enum AS ENUM (
    'VALIDACION_CIERRE',
    'CIERRE',
    'VALIDACION_APERTURA',
    'APERTURA',
    'REAPERTURA',
    'BACKUP_PRE_CIERRE',
    'RESTAURACION_BACKUP',
    'LIBERACION_BLOQUEO'
);


--
-- Name: tipo_venta_enum; Type: TYPE; Schema: contabilidad; Owner: -
--

CREATE TYPE contabilidad.tipo_venta_enum AS ENUM (
    'CONTADO',
    'CREDITO'
);


--
-- Name: fn_arqueo_caja_biu(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_arqueo_caja_biu() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.monto_contado IS NULL THEN
    NEW.diferencia := NULL;
  ELSE
    NEW.diferencia := ROUND((NEW.monto_contado - NEW.saldo_teorico)::numeric, 2);
  END IF;

  NEW.actualizado_en := CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$;


--
-- Name: fn_cobro_detalle_aiud(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_cobro_detalle_aiud() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_old_cobro_id BIGINT;
    v_new_cobro_id BIGINT;
    v_old_compromiso_id BIGINT;
    v_new_compromiso_id BIGINT;
BEGIN
    v_old_cobro_id := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN OLD.cobro_id ELSE NULL END;
    v_new_cobro_id := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN NEW.cobro_id ELSE NULL END;

    v_old_compromiso_id := CASE
        WHEN TG_OP IN ('UPDATE', 'DELETE') AND OLD.tipo_linea = 'COMPROMISO' THEN OLD.compromiso_detalle_id
        ELSE NULL
    END;

    v_new_compromiso_id := CASE
        WHEN TG_OP IN ('INSERT', 'UPDATE') AND NEW.tipo_linea = 'COMPROMISO' THEN NEW.compromiso_detalle_id
        ELSE NULL
    END;

    IF v_old_cobro_id IS NOT NULL THEN
        PERFORM contabilidad.fn_recalcular_cobro_total(v_old_cobro_id);
    END IF;

    IF v_new_cobro_id IS NOT NULL AND v_new_cobro_id IS DISTINCT FROM v_old_cobro_id THEN
        PERFORM contabilidad.fn_recalcular_cobro_total(v_new_cobro_id);
    END IF;

    IF v_old_compromiso_id IS NOT NULL THEN
        PERFORM contabilidad.fn_recalcular_compromiso_detalle(v_old_compromiso_id);
    END IF;

    IF v_new_compromiso_id IS NOT NULL AND v_new_compromiso_id IS DISTINCT FROM v_old_compromiso_id THEN
        PERFORM contabilidad.fn_recalcular_compromiso_detalle(v_new_compromiso_id);
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$;


--
-- Name: fn_cobro_detalle_biu(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_cobro_detalle_biu() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_tipo_compromiso VARCHAR(10);
    v_codigo VARCHAR(20);
    v_nombre VARCHAR(150);
    v_fecha DATE;
    v_monto NUMERIC(18,2);
BEGIN
    IF NEW.secuencia IS NULL OR NEW.secuencia < 1 THEN
        RAISE EXCEPTION 'La secuencia del detalle de cobro es obligatoria y debe ser mayor a cero.';
    END IF;

    IF NEW.tipo_linea = 'COMPROMISO' THEN
        IF NEW.compromiso_detalle_id IS NULL THEN
            RAISE EXCEPTION 'La línea de cobro tipo COMPROMISO requiere compromiso_detalle_id.';
        END IF;

        SELECT
            c.tipo,
            c.codigo,
            c.nombre,
            d.fecha_vencimiento,
            d.monto_programado
        INTO
            v_tipo_compromiso,
            v_codigo,
            v_nombre,
            v_fecha,
            v_monto
        FROM contabilidad.compromiso_detalle d
        INNER JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        WHERE d.id = NEW.compromiso_detalle_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'El compromiso_detalle_id % no existe.', NEW.compromiso_detalle_id;
        END IF;

        IF v_tipo_compromiso <> 'COBRAR' THEN
            RAISE EXCEPTION 'El detalle % no corresponde a un compromiso de tipo COBRAR.', NEW.compromiso_detalle_id;
        END IF;

        NEW.cantidad := 1;
        NEW.precio_unitario := v_monto;
        NEW.subtotal := v_monto;

        IF BTRIM(COALESCE(NEW.descripcion, '')) = '' THEN
            NEW.descripcion := FORMAT(
                'Compromiso %s - %s - %s',
                v_codigo,
                v_nombre,
                TO_CHAR(v_fecha, 'DD/MM/YYYY')
            );
        END IF;
    ELSE
        NEW.compromiso_detalle_id := NULL;

        IF NEW.cantidad IS NULL OR NEW.cantidad <= 0 THEN
            RAISE EXCEPTION 'La cantidad en detalle directo de cobro debe ser mayor a cero.';
        END IF;

        IF NEW.precio_unitario IS NULL OR NEW.precio_unitario < 0 THEN
            RAISE EXCEPTION 'El precio unitario en detalle directo de cobro no puede ser negativo.';
        END IF;

        IF BTRIM(COALESCE(NEW.descripcion, '')) = '' THEN
            RAISE EXCEPTION 'La descripción es obligatoria en detalle directo de cobro.';
        END IF;

        NEW.subtotal := ROUND((NEW.cantidad * NEW.precio_unitario)::numeric, 2);
    END IF;

    NEW.actualizado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: fn_cobro_estado_au(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_cobro_estado_au() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    r RECORD;
BEGIN
    IF NEW.estado IS DISTINCT FROM OLD.estado THEN
        FOR r IN
            SELECT DISTINCT compromiso_detalle_id
            FROM contabilidad.cobro_detalle
            WHERE cobro_id = NEW.id
              AND tipo_linea = 'COMPROMISO'
              AND compromiso_detalle_id IS NOT NULL
        LOOP
            PERFORM contabilidad.fn_recalcular_compromiso_detalle(r.compromiso_detalle_id);
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: fn_pago_detalle_aiud(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_pago_detalle_aiud() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_old_pago_id BIGINT;
    v_new_pago_id BIGINT;
    v_old_compromiso_id BIGINT;
    v_new_compromiso_id BIGINT;
BEGIN
    v_old_pago_id := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN OLD.pago_id ELSE NULL END;
    v_new_pago_id := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN NEW.pago_id ELSE NULL END;

    v_old_compromiso_id := CASE
        WHEN TG_OP IN ('UPDATE', 'DELETE') AND OLD.tipo_linea = 'COMPROMISO' THEN OLD.compromiso_detalle_id
        ELSE NULL
    END;

    v_new_compromiso_id := CASE
        WHEN TG_OP IN ('INSERT', 'UPDATE') AND NEW.tipo_linea = 'COMPROMISO' THEN NEW.compromiso_detalle_id
        ELSE NULL
    END;

    IF v_old_pago_id IS NOT NULL THEN
        PERFORM contabilidad.fn_recalcular_pago_total(v_old_pago_id);
    END IF;

    IF v_new_pago_id IS NOT NULL AND v_new_pago_id IS DISTINCT FROM v_old_pago_id THEN
        PERFORM contabilidad.fn_recalcular_pago_total(v_new_pago_id);
    END IF;

    IF v_old_compromiso_id IS NOT NULL THEN
        PERFORM contabilidad.fn_recalcular_compromiso_detalle(v_old_compromiso_id);
    END IF;

    IF v_new_compromiso_id IS NOT NULL AND v_new_compromiso_id IS DISTINCT FROM v_old_compromiso_id THEN
        PERFORM contabilidad.fn_recalcular_compromiso_detalle(v_new_compromiso_id);
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$;


--
-- Name: fn_pago_detalle_biu(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_pago_detalle_biu() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_tipo_compromiso VARCHAR(10);
    v_codigo VARCHAR(20);
    v_nombre VARCHAR(150);
    v_fecha DATE;
    v_monto NUMERIC(18,2);
BEGIN
    IF NEW.secuencia IS NULL OR NEW.secuencia < 1 THEN
        RAISE EXCEPTION 'La secuencia del detalle de pago es obligatoria y debe ser mayor a cero.';
    END IF;

    IF NEW.tipo_linea = 'COMPROMISO' THEN
        IF NEW.compromiso_detalle_id IS NULL THEN
            RAISE EXCEPTION 'La línea de pago tipo COMPROMISO requiere compromiso_detalle_id.';
        END IF;

        SELECT
            c.tipo,
            c.codigo,
            c.nombre,
            d.fecha_vencimiento,
            d.monto_programado
        INTO
            v_tipo_compromiso,
            v_codigo,
            v_nombre,
            v_fecha,
            v_monto
        FROM contabilidad.compromiso_detalle d
        INNER JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
        WHERE d.id = NEW.compromiso_detalle_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'El compromiso_detalle_id % no existe.', NEW.compromiso_detalle_id;
        END IF;

        IF v_tipo_compromiso <> 'PAGAR' THEN
            RAISE EXCEPTION 'El detalle % no corresponde a un compromiso de tipo PAGAR.', NEW.compromiso_detalle_id;
        END IF;

        NEW.cantidad := 1;
        NEW.precio_unitario := v_monto;
        NEW.subtotal := v_monto;

        IF BTRIM(COALESCE(NEW.descripcion, '')) = '' THEN
            NEW.descripcion := FORMAT(
                'Compromiso %s - %s - %s',
                v_codigo,
                v_nombre,
                TO_CHAR(v_fecha, 'DD/MM/YYYY')
            );
        END IF;
    ELSE
        NEW.compromiso_detalle_id := NULL;

        IF NEW.cantidad IS NULL OR NEW.cantidad <= 0 THEN
            RAISE EXCEPTION 'La cantidad en detalle directo de pago debe ser mayor a cero.';
        END IF;

        IF NEW.precio_unitario IS NULL OR NEW.precio_unitario < 0 THEN
            RAISE EXCEPTION 'El precio unitario en detalle directo de pago no puede ser negativo.';
        END IF;

        IF BTRIM(COALESCE(NEW.descripcion, '')) = '' THEN
            RAISE EXCEPTION 'La descripción es obligatoria en detalle directo de pago.';
        END IF;

        NEW.subtotal := ROUND((NEW.cantidad * NEW.precio_unitario)::numeric, 2);
    END IF;

    NEW.actualizado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: fn_pago_estado_au(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_pago_estado_au() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    r RECORD;
BEGIN
    IF NEW.estado IS DISTINCT FROM OLD.estado THEN
        FOR r IN
            SELECT DISTINCT compromiso_detalle_id
            FROM contabilidad.pago_detalle
            WHERE pago_id = NEW.id
              AND tipo_linea = 'COMPROMISO'
              AND compromiso_detalle_id IS NOT NULL
        LOOP
            PERFORM contabilidad.fn_recalcular_compromiso_detalle(r.compromiso_detalle_id);
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: fn_recalcular_cobro_total(bigint); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_recalcular_cobro_total(p_cobro_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_total NUMERIC(18,2) := 0;
    v_tiene_compromiso BOOLEAN := FALSE;
BEGIN
    SELECT
        COALESCE(ROUND(SUM(subtotal)::numeric, 2), 0),
        COALESCE(BOOL_OR(tipo_linea = 'COMPROMISO'), FALSE)
    INTO v_total, v_tiene_compromiso
    FROM contabilidad.cobro_detalle
    WHERE cobro_id = p_cobro_id;

    UPDATE contabilidad.cobro
    SET monto_total = v_total,
        origen_operacion = CASE
            WHEN v_tiene_compromiso
                THEN 'COMPROMISO'::contabilidad.origen_tesoreria_enum
            ELSE
                'DIRECTO'::contabilidad.origen_tesoreria_enum
        END,
        actualizado_en = CURRENT_TIMESTAMP
    WHERE id = p_cobro_id;
END;
$$;


--
-- Name: fn_recalcular_compromiso_detalle(bigint); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_recalcular_compromiso_detalle(p_compromiso_detalle_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_tipo VARCHAR(10);
    v_total NUMERIC(18,2) := 0;
    v_estado VARCHAR(10) := 'PENDIENTE';
BEGIN
    SELECT c.tipo
    INTO v_tipo
    FROM contabilidad.compromiso_detalle d
    INNER JOIN contabilidad.compromiso c ON c.id = d.compromiso_id
    WHERE d.id = p_compromiso_detalle_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT
        COALESCE((
            SELECT SUM(pd.subtotal)
            FROM contabilidad.pago_detalle pd
            INNER JOIN contabilidad.pago p ON p.id = pd.pago_id
            WHERE pd.tipo_linea = 'COMPROMISO'
              AND pd.compromiso_detalle_id = p_compromiso_detalle_id
              AND p.estado = 'CONFIRMADO'
        ), 0)
        +
        COALESCE((
            SELECT SUM(cd.subtotal)
            FROM contabilidad.cobro_detalle cd
            INNER JOIN contabilidad.cobro c2 ON c2.id = cd.cobro_id
            WHERE cd.tipo_linea = 'COMPROMISO'
              AND cd.compromiso_detalle_id = p_compromiso_detalle_id
              AND c2.estado = 'CONFIRMADO'
        ), 0)
    INTO v_total;

    IF v_total > 0 THEN
        v_estado := CASE
            WHEN v_tipo = 'PAGAR' THEN 'PAGADO'
            WHEN v_tipo = 'COBRAR' THEN 'COBRADO'
            ELSE 'PENDIENTE'
        END;
    END IF;

    UPDATE contabilidad.compromiso_detalle
    SET monto_registrado = v_total,
        estado = v_estado,
        actualizado_en = CURRENT_TIMESTAMP
    WHERE id = p_compromiso_detalle_id;
END;
$$;


--
-- Name: fn_recalcular_pago_total(bigint); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_recalcular_pago_total(p_pago_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_total NUMERIC(18,2) := 0;
    v_tiene_compromiso BOOLEAN := FALSE;
BEGIN
    SELECT
        COALESCE(ROUND(SUM(subtotal)::numeric, 2), 0),
        COALESCE(BOOL_OR(tipo_linea = 'COMPROMISO'), FALSE)
    INTO v_total, v_tiene_compromiso
    FROM contabilidad.pago_detalle
    WHERE pago_id = p_pago_id;

    UPDATE contabilidad.pago
    SET monto_total = v_total,
        origen_operacion = CASE
            WHEN v_tiene_compromiso
                THEN 'COMPROMISO'::contabilidad.origen_tesoreria_enum
            ELSE
                'DIRECTO'::contabilidad.origen_tesoreria_enum
        END,
        actualizado_en = CURRENT_TIMESTAMP
    WHERE id = p_pago_id;
END;
$$;


--
-- Name: fn_set_actualizado_en(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_set_actualizado_en() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.actualizado_en = now();
    RETURN NEW;
END;
$$;


--
-- Name: fn_validar_asiento_balanceado(bigint); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_validar_asiento_balanceado(p_asiento_id bigint) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_debe  NUMERIC(18,2);
    v_haber NUMERIC(18,2);
BEGIN
    SELECT COALESCE(SUM(debe), 0), COALESCE(SUM(haber), 0)
      INTO v_debe, v_haber
      FROM contabilidad.asiento_detalle
     WHERE asiento_id = p_asiento_id;

    RETURN v_debe = v_haber;
END;
$$;


--
-- Name: fn_validar_cuenta_postable(); Type: FUNCTION; Schema: contabilidad; Owner: -
--

CREATE FUNCTION contabilidad.fn_validar_cuenta_postable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_postable BOOLEAN;
    v_requiere_aux BOOLEAN;
BEGIN
    SELECT es_postable, requiere_auxiliar
      INTO v_postable, v_requiere_aux
      FROM contabilidad.cuenta
     WHERE codigo = NEW.cuenta_codigo;

    IF v_postable IS NULL THEN
        RAISE EXCEPTION 'La cuenta % no existe.', NEW.cuenta_codigo;
    END IF;

    IF v_postable = FALSE THEN
        RAISE EXCEPTION 'La cuenta % no es postable.', NEW.cuenta_codigo;
    END IF;

    IF v_requiere_aux AND NEW.auxiliar_id IS NULL THEN
        RAISE EXCEPTION 'La cuenta % requiere auxiliar.', NEW.cuenta_codigo;
    END IF;

    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _tipo_cambio; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad._tipo_cambio (
    id bigint NOT NULL,
    fecha date NOT NULL,
    moneda_codigo character varying(10) NOT NULL,
    compra numeric(18,6) NOT NULL,
    venta numeric(18,6) NOT NULL,
    observado text,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT _tipo_cambio_compra_check CHECK ((compra > (0)::numeric)),
    CONSTRAINT _tipo_cambio_venta_check CHECK ((venta > (0)::numeric))
);


--
-- Name: _tipo_cambio_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad._tipo_cambio_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: _tipo_cambio_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad._tipo_cambio_id_seq OWNED BY contabilidad._tipo_cambio.id;


--
-- Name: arqueo_caja; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.arqueo_caja (
    id bigint NOT NULL,
    caja_id bigint NOT NULL,
    fecha_arqueo date NOT NULL,
    saldo_anterior numeric(18,2) DEFAULT 0 NOT NULL,
    ingresos_dia numeric(18,2) DEFAULT 0 NOT NULL,
    egresos_dia numeric(18,2) DEFAULT 0 NOT NULL,
    saldo_teorico numeric(18,2) DEFAULT 0 NOT NULL,
    monto_contado numeric(18,2),
    diferencia numeric(18,2),
    observacion character varying(500),
    estado contabilidad.estado_generico_enum DEFAULT 'BORRADOR'::contabilidad.estado_generico_enum NOT NULL,
    usuario_nombre character varying(150) NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT ck_arqueo_caja_confirmado_contado CHECK (((estado <> 'CONFIRMADO'::contabilidad.estado_generico_enum) OR (monto_contado IS NOT NULL))),
    CONSTRAINT ck_arqueo_caja_confirmado_observacion CHECK (((estado <> 'CONFIRMADO'::contabilidad.estado_generico_enum) OR (diferencia IS NULL) OR (diferencia = (0)::numeric) OR ((observacion IS NOT NULL) AND (btrim((observacion)::text) <> ''::text)))),
    CONSTRAINT ck_arqueo_caja_egresos_dia CHECK ((egresos_dia >= (0)::numeric)),
    CONSTRAINT ck_arqueo_caja_ingresos_dia CHECK ((ingresos_dia >= (0)::numeric)),
    CONSTRAINT ck_arqueo_caja_monto_contado CHECK (((monto_contado IS NULL) OR (monto_contado >= (0)::numeric))),
    CONSTRAINT ck_arqueo_caja_usuario_nombre CHECK ((btrim((usuario_nombre)::text) <> ''::text))
);


--
-- Name: TABLE arqueo_caja; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON TABLE contabilidad.arqueo_caja IS 'Arqueo general de caja. Guarda el snapshot del saldo teórico y el conteo físico para una caja y fecha determinada.';


--
-- Name: COLUMN arqueo_caja.saldo_anterior; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.arqueo_caja.saldo_anterior IS 'Saldo acumulado de la caja hasta el día anterior al arqueo.';


--
-- Name: COLUMN arqueo_caja.ingresos_dia; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.arqueo_caja.ingresos_dia IS 'Suma de cobros y movimientos confirmados de entrada del día del arqueo.';


--
-- Name: COLUMN arqueo_caja.egresos_dia; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.arqueo_caja.egresos_dia IS 'Suma de pagos y movimientos confirmados de salida del día del arqueo.';


--
-- Name: COLUMN arqueo_caja.saldo_teorico; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.arqueo_caja.saldo_teorico IS 'Saldo que el sistema espera en caja para la fecha del arqueo.';


--
-- Name: COLUMN arqueo_caja.monto_contado; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.arqueo_caja.monto_contado IS 'Monto contado físicamente por el usuario al realizar el arqueo.';


--
-- Name: COLUMN arqueo_caja.diferencia; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.arqueo_caja.diferencia IS 'Diferencia entre monto contado y saldo teórico.';


--
-- Name: arqueo_caja_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.arqueo_caja_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: arqueo_caja_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.arqueo_caja_id_seq OWNED BY contabilidad.arqueo_caja.id;


--
-- Name: asiento; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.asiento (
    id bigint NOT NULL,
    fecha date NOT NULL,
    moneda_codigo character varying(10) NOT NULL,
    tipo_cambio numeric(18,6) DEFAULT 1 NOT NULL,
    glosa character varying(500) NOT NULL,
    referencia character varying(150),
    modulo_origen character varying(50),
    tabla_origen character varying(100),
    origen_id bigint,
    estado contabilidad.estado_generico_enum DEFAULT 'BORRADOR'::contabilidad.estado_generico_enum NOT NULL,
    atributos jsonb,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT asiento_tipo_cambio_check CHECK ((tipo_cambio > (0)::numeric))
);


--
-- Name: asiento_detalle; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.asiento_detalle (
    id bigint NOT NULL,
    asiento_id bigint NOT NULL,
    secuencia integer NOT NULL,
    cuenta_codigo character varying(30) NOT NULL,
    auxiliar_id bigint,
    centro_costo_id bigint,
    glosa character varying(300),
    debe numeric(18,2) DEFAULT 0 NOT NULL,
    haber numeric(18,2) DEFAULT 0 NOT NULL,
    monto_moneda numeric(18,2),
    referencia character varying(150),
    atributos jsonb,
    CONSTRAINT asiento_detalle_debe_check CHECK ((debe >= (0)::numeric)),
    CONSTRAINT asiento_detalle_haber_check CHECK ((haber >= (0)::numeric)),
    CONSTRAINT ck_asiento_detalle_debe_haber CHECK ((((debe > (0)::numeric) AND (haber = (0)::numeric)) OR ((haber > (0)::numeric) AND (debe = (0)::numeric))))
);


--
-- Name: asiento_detalle_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.asiento_detalle_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: asiento_detalle_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.asiento_detalle_id_seq OWNED BY contabilidad.asiento_detalle.id;


--
-- Name: asiento_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.asiento_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: asiento_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.asiento_id_seq OWNED BY contabilidad.asiento.id;


--
-- Name: auxiliar; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.auxiliar (
    id bigint NOT NULL,
    tipo contabilidad.tipo_auxiliar_enum NOT NULL,
    origen_tabla character varying(100),
    ref_id bigint,
    codigo_externo character varying(100),
    nit_ci character varying(50),
    nombre character varying(200) NOT NULL,
    razon_social character varying(200),
    telefono character varying(50),
    email character varying(120),
    direccion character varying(250),
    es_ocasional boolean DEFAULT false NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    observaciones text
);


--
-- Name: auxiliar_cuenta; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.auxiliar_cuenta (
    id bigint NOT NULL,
    auxiliar_id bigint NOT NULL,
    cuenta_codigo character varying(30) NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: auxiliar_cuenta_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.auxiliar_cuenta_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auxiliar_cuenta_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.auxiliar_cuenta_id_seq OWNED BY contabilidad.auxiliar_cuenta.id;


--
-- Name: auxiliar_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.auxiliar_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auxiliar_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.auxiliar_id_seq OWNED BY contabilidad.auxiliar.id;


--
-- Name: caja; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.caja (
    id bigint NOT NULL,
    codigo character varying(30) NOT NULL,
    nombre character varying(150) NOT NULL,
    cuenta_contable_codigo character varying(30) NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone
);


--
-- Name: caja_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.caja_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: caja_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.caja_id_seq OWNED BY contabilidad.caja.id;


--
-- Name: centro_costo; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.centro_costo (
    id bigint NOT NULL,
    codigo character varying(30) NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion text,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone
);


--
-- Name: centro_costo_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.centro_costo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: centro_costo_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.centro_costo_id_seq OWNED BY contabilidad.centro_costo.id;


--
-- Name: cobro; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.cobro (
    id bigint NOT NULL,
    fecha date NOT NULL,
    cliente_auxiliar_id bigint,
    medio_pago contabilidad.medio_pago_enum NOT NULL,
    contra_cuenta_codigo character varying(30) NOT NULL,
    caja_id bigint,
    cuenta_bancaria_id bigint,
    moneda_codigo character varying(10) NOT NULL,
    tipo_cambio numeric(18,6) DEFAULT 1 NOT NULL,
    monto_total numeric(18,2) NOT NULL,
    referencia character varying(150),
    glosa character varying(500) NOT NULL,
    estado contabilidad.estado_generico_enum DEFAULT 'BORRADOR'::contabilidad.estado_generico_enum NOT NULL,
    asiento_id bigint,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    origen_operacion contabilidad.origen_tesoreria_enum DEFAULT 'DIRECTO'::contabilidad.origen_tesoreria_enum NOT NULL,
    CONSTRAINT ck_cobro_medio CHECK ((((medio_pago = 'CAJA'::contabilidad.medio_pago_enum) AND (caja_id IS NOT NULL)) OR ((medio_pago = 'BANCO'::contabilidad.medio_pago_enum) AND (cuenta_bancaria_id IS NOT NULL)) OR (medio_pago = ANY (ARRAY['MIXTO'::contabilidad.medio_pago_enum, 'OTRO'::contabilidad.medio_pago_enum])))),
    CONSTRAINT cobro_monto_total_check CHECK ((monto_total >= (0)::numeric)),
    CONSTRAINT cobro_tipo_cambio_check CHECK ((tipo_cambio > (0)::numeric))
);


--
-- Name: COLUMN cobro.origen_operacion; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.cobro.origen_operacion IS 'COMPROMISO = cobro generado desde cuota programada; DIRECTO = cobro por concepto libre.';


--
-- Name: cobro_detalle; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.cobro_detalle (
    id bigint NOT NULL,
    cobro_id bigint NOT NULL,
    secuencia integer NOT NULL,
    tipo_linea contabilidad.tipo_linea_tesoreria_enum DEFAULT 'DIRECTO'::contabilidad.tipo_linea_tesoreria_enum NOT NULL,
    compromiso_detalle_id bigint,
    descripcion character varying(300) NOT NULL,
    cantidad numeric(18,4) DEFAULT 1 NOT NULL,
    precio_unitario numeric(18,2) DEFAULT 0 NOT NULL,
    subtotal numeric(18,2) DEFAULT 0 NOT NULL,
    observacion character varying(300),
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT ck_cobro_detalle_cantidad CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT ck_cobro_detalle_precio_unitario CHECK ((precio_unitario >= (0)::numeric)),
    CONSTRAINT ck_cobro_detalle_subtotal CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT ck_cobro_detalle_tipo_compromiso CHECK ((((tipo_linea = 'COMPROMISO'::contabilidad.tipo_linea_tesoreria_enum) AND (compromiso_detalle_id IS NOT NULL)) OR ((tipo_linea = 'DIRECTO'::contabilidad.tipo_linea_tesoreria_enum) AND (compromiso_detalle_id IS NULL))))
);


--
-- Name: TABLE cobro_detalle; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON TABLE contabilidad.cobro_detalle IS 'Detalle único del cobro. Soporta líneas por compromiso o por concepto directo.';


--
-- Name: COLUMN cobro_detalle.tipo_linea; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.cobro_detalle.tipo_linea IS 'COMPROMISO = línea ligada a una cuota programada; DIRECTO = línea libre.';


--
-- Name: COLUMN cobro_detalle.compromiso_detalle_id; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.cobro_detalle.compromiso_detalle_id IS 'Se llena únicamente cuando la línea proviene de una cuota de compromiso.';


--
-- Name: cobro_detalle_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.cobro_detalle_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cobro_detalle_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.cobro_detalle_id_seq OWNED BY contabilidad.cobro_detalle.id;


--
-- Name: cobro_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.cobro_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cobro_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.cobro_id_seq OWNED BY contabilidad.cobro.id;


--
-- Name: compra; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.compra (
    id bigint NOT NULL,
    fecha date NOT NULL,
    proveedor_auxiliar_id bigint,
    proveedor_nit character varying(50),
    proveedor_nombre character varying(200) NOT NULL,
    numero_factura character varying(100),
    fecha_factura date,
    tipo_compra contabilidad.tipo_compra_enum NOT NULL,
    glosa character varying(500) NOT NULL,
    moneda_codigo character varying(10) NOT NULL,
    tipo_cambio numeric(18,6) DEFAULT 1 NOT NULL,
    subtotal numeric(18,2) DEFAULT 0 NOT NULL,
    impuestos numeric(18,2) DEFAULT 0 NOT NULL,
    total numeric(18,2) NOT NULL,
    contra_cuenta_codigo character varying(30) NOT NULL,
    estado contabilidad.estado_generico_enum DEFAULT 'BORRADOR'::contabilidad.estado_generico_enum NOT NULL,
    asiento_id bigint,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT compra_impuestos_check CHECK ((impuestos >= (0)::numeric)),
    CONSTRAINT compra_subtotal_check CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT compra_tipo_cambio_check CHECK ((tipo_cambio > (0)::numeric)),
    CONSTRAINT compra_total_check CHECK ((total >= (0)::numeric))
);


--
-- Name: compra_detalle; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.compra_detalle (
    id bigint NOT NULL,
    compra_id bigint NOT NULL,
    secuencia integer NOT NULL,
    descripcion character varying(300) NOT NULL,
    cantidad numeric(18,4) DEFAULT 1 NOT NULL,
    precio_unitario numeric(18,2) DEFAULT 0 NOT NULL,
    subtotal numeric(18,2) NOT NULL,
    cuenta_gasto_codigo character varying(30) NOT NULL,
    centro_costo_id bigint,
    CONSTRAINT compra_detalle_cantidad_check CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT compra_detalle_precio_unitario_check CHECK ((precio_unitario >= (0)::numeric)),
    CONSTRAINT compra_detalle_subtotal_check CHECK ((subtotal >= (0)::numeric))
);


--
-- Name: compra_detalle_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.compra_detalle_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: compra_detalle_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.compra_detalle_id_seq OWNED BY contabilidad.compra_detalle.id;


--
-- Name: compra_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.compra_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: compra_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.compra_id_seq OWNED BY contabilidad.compra.id;


--
-- Name: compromiso; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.compromiso (
    id bigint NOT NULL,
    codigo character varying(5) NOT NULL,
    tipo character varying(10) NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion text,
    auxiliar_id bigint,
    cuenta_contable character varying(30),
    gestion integer NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT compromiso_gestion_check CHECK ((gestion >= 2000)),
    CONSTRAINT compromiso_tipo_check CHECK (((tipo)::text = ANY (ARRAY[('PAGAR'::character varying)::text, ('COBRAR'::character varying)::text])))
);


--
-- Name: pago; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.pago (
    id bigint NOT NULL,
    fecha date NOT NULL,
    proveedor_auxiliar_id bigint,
    medio_pago contabilidad.medio_pago_enum NOT NULL,
    contra_cuenta_codigo character varying(30) NOT NULL,
    caja_id bigint,
    cuenta_bancaria_id bigint,
    moneda_codigo character varying(10) NOT NULL,
    tipo_cambio numeric(18,6) DEFAULT 1 NOT NULL,
    monto_total numeric(18,2) NOT NULL,
    referencia character varying(150),
    glosa character varying(500) NOT NULL,
    estado contabilidad.estado_generico_enum DEFAULT 'BORRADOR'::contabilidad.estado_generico_enum NOT NULL,
    asiento_id bigint,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    origen_operacion contabilidad.origen_tesoreria_enum DEFAULT 'DIRECTO'::contabilidad.origen_tesoreria_enum NOT NULL,
    CONSTRAINT ck_pago_medio CHECK ((((medio_pago = 'CAJA'::contabilidad.medio_pago_enum) AND (caja_id IS NOT NULL)) OR ((medio_pago = 'BANCO'::contabilidad.medio_pago_enum) AND (cuenta_bancaria_id IS NOT NULL)) OR (medio_pago = ANY (ARRAY['MIXTO'::contabilidad.medio_pago_enum, 'OTRO'::contabilidad.medio_pago_enum])))),
    CONSTRAINT pago_monto_total_check CHECK ((monto_total >= (0)::numeric)),
    CONSTRAINT pago_tipo_cambio_check CHECK ((tipo_cambio > (0)::numeric))
);


--
-- Name: COLUMN pago.origen_operacion; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.pago.origen_operacion IS 'COMPROMISO = pago generado desde cuota programada; DIRECTO = pago por concepto libre.';


--
-- Name: pago_detalle; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.pago_detalle (
    id bigint NOT NULL,
    pago_id bigint NOT NULL,
    secuencia integer NOT NULL,
    tipo_linea contabilidad.tipo_linea_tesoreria_enum DEFAULT 'DIRECTO'::contabilidad.tipo_linea_tesoreria_enum NOT NULL,
    compromiso_detalle_id bigint,
    descripcion character varying(300) NOT NULL,
    cantidad numeric(18,4) DEFAULT 1 NOT NULL,
    precio_unitario numeric(18,2) DEFAULT 0 NOT NULL,
    subtotal numeric(18,2) DEFAULT 0 NOT NULL,
    observacion character varying(300),
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT ck_pago_detalle_cantidad CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT ck_pago_detalle_precio_unitario CHECK ((precio_unitario >= (0)::numeric)),
    CONSTRAINT ck_pago_detalle_subtotal CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT ck_pago_detalle_tipo_compromiso CHECK ((((tipo_linea = 'COMPROMISO'::contabilidad.tipo_linea_tesoreria_enum) AND (compromiso_detalle_id IS NOT NULL)) OR ((tipo_linea = 'DIRECTO'::contabilidad.tipo_linea_tesoreria_enum) AND (compromiso_detalle_id IS NULL))))
);


--
-- Name: TABLE pago_detalle; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON TABLE contabilidad.pago_detalle IS 'Detalle único del pago. Soporta líneas por compromiso o por concepto directo.';


--
-- Name: COLUMN pago_detalle.tipo_linea; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.pago_detalle.tipo_linea IS 'COMPROMISO = línea ligada a una cuota programada; DIRECTO = línea libre.';


--
-- Name: COLUMN pago_detalle.compromiso_detalle_id; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.pago_detalle.compromiso_detalle_id IS 'Se llena únicamente cuando la línea proviene de una cuota de compromiso.';


--
-- Name: compromiso_aplicacion; Type: VIEW; Schema: contabilidad; Owner: -
--

CREATE VIEW contabilidad.compromiso_aplicacion AS
 SELECT pd.id,
    pd.compromiso_detalle_id,
    pd.pago_id,
    NULL::bigint AS cobro_id,
    NULL::bigint AS movimiento_tesoreria_id,
    pd.subtotal AS monto_aplicado,
    p.fecha AS fecha_aplicacion,
    COALESCE(pd.observacion, pd.descripcion) AS observacion
   FROM (contabilidad.pago_detalle pd
     JOIN contabilidad.pago p ON ((p.id = pd.pago_id)))
  WHERE ((pd.tipo_linea = 'COMPROMISO'::contabilidad.tipo_linea_tesoreria_enum) AND (p.estado = 'CONFIRMADO'::contabilidad.estado_generico_enum))
UNION ALL
 SELECT (- cd.id) AS id,
    cd.compromiso_detalle_id,
    NULL::bigint AS pago_id,
    cd.cobro_id,
    NULL::bigint AS movimiento_tesoreria_id,
    cd.subtotal AS monto_aplicado,
    c.fecha AS fecha_aplicacion,
    COALESCE(cd.observacion, cd.descripcion) AS observacion
   FROM (contabilidad.cobro_detalle cd
     JOIN contabilidad.cobro c ON ((c.id = cd.cobro_id)))
  WHERE ((cd.tipo_linea = 'COMPROMISO'::contabilidad.tipo_linea_tesoreria_enum) AND (c.estado = 'CONFIRMADO'::contabilidad.estado_generico_enum));


--
-- Name: compromiso_codigo_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.compromiso_codigo_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: compromiso_detalle; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.compromiso_detalle (
    id bigint NOT NULL,
    compromiso_id bigint NOT NULL,
    fecha_vencimiento date NOT NULL,
    monto_programado numeric(18,2) NOT NULL,
    monto_registrado numeric(18,2) DEFAULT 0 NOT NULL,
    estado character varying(10) NOT NULL,
    observacion character varying(300),
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT compromiso_detalle_estado_check CHECK (((estado)::text = ANY (ARRAY[('PENDIENTE'::character varying)::text, ('PAGADO'::character varying)::text, ('COBRADO'::character varying)::text]))),
    CONSTRAINT compromiso_detalle_monto_programado_check CHECK ((monto_programado > (0)::numeric)),
    CONSTRAINT compromiso_detalle_monto_registrado_check CHECK ((monto_registrado >= (0)::numeric))
);


--
-- Name: compromiso_detalle_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.compromiso_detalle_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: compromiso_detalle_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.compromiso_detalle_id_seq OWNED BY contabilidad.compromiso_detalle.id;


--
-- Name: compromiso_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.compromiso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: compromiso_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.compromiso_id_seq OWNED BY contabilidad.compromiso.id;


--
-- Name: cuenta; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.cuenta (
    codigo character varying(30) NOT NULL,
    nombre character varying(250) NOT NULL,
    nivel integer NOT NULL,
    tipo contabilidad.tipo_cuenta_enum NOT NULL,
    naturaleza contabilidad.naturaleza_enum NOT NULL,
    es_postable boolean DEFAULT false NOT NULL,
    requiere_auxiliar boolean DEFAULT false NOT NULL,
    requiere_cc boolean DEFAULT false NOT NULL,
    codigo_padre character varying(30),
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT cuenta_nivel_check CHECK ((nivel >= 1))
);


--
-- Name: cuenta_bancaria; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.cuenta_bancaria (
    id bigint NOT NULL,
    auxiliar_id bigint,
    nombre_banco character varying(150) NOT NULL,
    numero_cuenta character varying(100) NOT NULL,
    moneda_codigo character varying(10) NOT NULL,
    cuenta_contable_codigo character varying(30) NOT NULL,
    titular character varying(200),
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone
);


--
-- Name: cuenta_bancaria_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.cuenta_bancaria_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cuenta_bancaria_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.cuenta_bancaria_id_seq OWNED BY contabilidad.cuenta_bancaria.id;


--
-- Name: documento_asiento; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.documento_asiento (
    id bigint NOT NULL,
    modulo character varying(50) NOT NULL,
    tabla_origen character varying(100) NOT NULL,
    origen_id bigint NOT NULL,
    asiento_id bigint NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: documento_asiento_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.documento_asiento_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: documento_asiento_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.documento_asiento_id_seq OWNED BY contabilidad.documento_asiento.id;


--
-- Name: esquema_backup_catalogo; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.esquema_backup_catalogo (
    id bigint NOT NULL,
    gestion_origen integer NOT NULL,
    gestion_destino integer,
    tipo_respaldo character varying(50) DEFAULT 'PRE_CIERRE'::character varying NOT NULL,
    estado contabilidad.estado_backup_esquema_enum DEFAULT 'GENERADO'::contabilidad.estado_backup_esquema_enum NOT NULL,
    nombre_archivo character varying(255) NOT NULL,
    ruta_archivo character varying(1000) NOT NULL,
    hash_archivo character varying(255),
    tamanio_bytes bigint,
    usuario_id integer,
    usuario_nombre character varying(200),
    fecha_generacion timestamp(6) without time zone DEFAULT now() NOT NULL,
    observacion text,
    detalle_json jsonb,
    creado_en timestamp(6) without time zone DEFAULT now() NOT NULL
);


--
-- Name: esquema_backup_catalogo_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.esquema_backup_catalogo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: esquema_backup_catalogo_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.esquema_backup_catalogo_id_seq OWNED BY contabilidad.esquema_backup_catalogo.id;


--
-- Name: esquema_backup_catalogo_id_seq1; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

ALTER TABLE contabilidad.esquema_backup_catalogo ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME contabilidad.esquema_backup_catalogo_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: esquema_restauracion_log; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.esquema_restauracion_log (
    id bigint NOT NULL,
    backup_id bigint NOT NULL,
    estado contabilidad.estado_restauracion_esquema_enum NOT NULL,
    gestion_origen integer NOT NULL,
    gestion_destino integer,
    usuario_id integer,
    usuario_nombre character varying(200),
    motivo text NOT NULL,
    detalle_json jsonb,
    fecha_hora_inicio timestamp(6) without time zone DEFAULT now() NOT NULL,
    fecha_hora_fin timestamp(6) without time zone,
    creado_en timestamp(6) without time zone DEFAULT now() NOT NULL
);


--
-- Name: esquema_restauracion_log_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.esquema_restauracion_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: esquema_restauracion_log_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.esquema_restauracion_log_id_seq OWNED BY contabilidad.esquema_restauracion_log.id;


--
-- Name: esquema_restauracion_log_id_seq1; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

ALTER TABLE contabilidad.esquema_restauracion_log ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME contabilidad.esquema_restauracion_log_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: factura_aplicacion; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.factura_aplicacion (
    id bigint NOT NULL,
    factura_electronica_id bigint NOT NULL,
    venta_id bigint,
    cobro_id bigint,
    monto_aplicado numeric(18,2) NOT NULL,
    estado_resultante contabilidad.estado_factura_ext_enum,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_factura_aplicacion_origen CHECK (((
CASE
    WHEN (venta_id IS NOT NULL) THEN 1
    ELSE 0
END +
CASE
    WHEN (cobro_id IS NOT NULL) THEN 1
    ELSE 0
END) = 1)),
    CONSTRAINT factura_aplicacion_monto_aplicado_check CHECK ((monto_aplicado > (0)::numeric))
);


--
-- Name: factura_aplicacion_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.factura_aplicacion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: factura_aplicacion_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.factura_aplicacion_id_seq OWNED BY contabilidad.factura_aplicacion.id;


--
-- Name: factura_electronica; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.factura_electronica (
    id bigint NOT NULL,
    origen character varying(50) DEFAULT 'EXTERNO'::character varying NOT NULL,
    codigo_externo character varying(100),
    cliente_auxiliar_id bigint,
    cliente_empresa_id bigint,
    nit_cliente character varying(50),
    nombre_cliente character varying(200),
    numero_factura character varying(100) NOT NULL,
    cuf character varying(255),
    fecha_emision date NOT NULL,
    moneda_codigo character varying(10) NOT NULL,
    subtotal numeric(18,2) DEFAULT 0 NOT NULL,
    descuento numeric(18,2) DEFAULT 0 NOT NULL,
    importe_total numeric(18,2) NOT NULL,
    saldo_pendiente numeric(18,2) NOT NULL,
    estado contabilidad.estado_factura_ext_enum DEFAULT 'RECIBIDA'::contabilidad.estado_factura_ext_enum NOT NULL,
    payload jsonb,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT factura_electronica_descuento_check CHECK ((descuento >= (0)::numeric)),
    CONSTRAINT factura_electronica_importe_total_check CHECK ((importe_total >= (0)::numeric)),
    CONSTRAINT factura_electronica_saldo_pendiente_check CHECK ((saldo_pendiente >= (0)::numeric)),
    CONSTRAINT factura_electronica_subtotal_check CHECK ((subtotal >= (0)::numeric))
);


--
-- Name: factura_electronica_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.factura_electronica_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: factura_electronica_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.factura_electronica_id_seq OWNED BY contabilidad.factura_electronica.id;


--
-- Name: factura_regularizacion; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.factura_regularizacion (
    id bigint NOT NULL,
    factura_electronica_id bigint NOT NULL,
    tipo_regularizacion character varying(20) NOT NULL,
    monto numeric(18,2) NOT NULL,
    motivo character varying(200) NOT NULL,
    observacion character varying(500),
    activo boolean DEFAULT true NOT NULL,
    creado_por character varying(120),
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    anulado_por character varying(120),
    anulado_en timestamp(6) without time zone,
    CONSTRAINT ck_factura_regularizacion_monto CHECK ((monto > (0)::numeric)),
    CONSTRAINT ck_factura_regularizacion_tipo CHECK (((tipo_regularizacion)::text = ANY (ARRAY[('AJUSTE'::character varying)::text, ('CIERRE_MANUAL'::character varying)::text])))
);


--
-- Name: factura_regularizacion_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.factura_regularizacion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: factura_regularizacion_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.factura_regularizacion_id_seq OWNED BY contabilidad.factura_regularizacion.id;


--
-- Name: gestion_bloqueo_critico; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.gestion_bloqueo_critico (
    id bigint NOT NULL,
    tipo_proceso contabilidad.tipo_proceso_critico_enum NOT NULL,
    estado contabilidad.estado_bloqueo_critico_enum DEFAULT 'EN_PROCESO'::contabilidad.estado_bloqueo_critico_enum NOT NULL,
    gestion_origen integer NOT NULL,
    gestion_destino integer,
    usuario_id integer,
    usuario_nombre character varying(200),
    motivo text,
    fecha_hora_inicio timestamp(6) without time zone DEFAULT now() NOT NULL,
    fecha_hora_fin timestamp(6) without time zone,
    token_proceso uuid DEFAULT gen_random_uuid() NOT NULL,
    creado_en timestamp(6) without time zone DEFAULT now() NOT NULL
);


--
-- Name: gestion_bloqueo_critico_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.gestion_bloqueo_critico_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gestion_bloqueo_critico_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.gestion_bloqueo_critico_id_seq OWNED BY contabilidad.gestion_bloqueo_critico.id;


--
-- Name: gestion_bloqueo_critico_id_seq1; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

ALTER TABLE contabilidad.gestion_bloqueo_critico ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME contabilidad.gestion_bloqueo_critico_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: gestion_configuracion; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.gestion_configuracion (
    id integer NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    cuenta_resultado_ejercicio_codigo character varying(50) NOT NULL,
    glosa_cierre character varying(250) DEFAULT 'CIERRE DE GESTIÓN'::character varying NOT NULL,
    glosa_apertura character varying(250) DEFAULT 'APERTURA DE GESTIÓN'::character varying NOT NULL,
    generar_backup_pre_cierre boolean DEFAULT true NOT NULL,
    permitir_reapertura boolean DEFAULT true NOT NULL,
    bloquear_si_hay_borradores boolean DEFAULT true NOT NULL,
    bloquear_si_hay_movimientos_destino boolean DEFAULT true NOT NULL,
    ruta_backup_base character varying(500),
    comando_backup text,
    comando_restauracion text,
    creado_en timestamp(6) without time zone DEFAULT now() NOT NULL,
    actualizado_en timestamp(6) without time zone DEFAULT now() NOT NULL
);


--
-- Name: gestion_configuracion_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.gestion_configuracion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


--
-- Name: gestion_configuracion_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.gestion_configuracion_id_seq OWNED BY contabilidad.gestion_configuracion.id;


--
-- Name: gestion_configuracion_id_seq1; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

ALTER TABLE contabilidad.gestion_configuracion ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME contabilidad.gestion_configuracion_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: gestion_control; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.gestion_control (
    gestion integer NOT NULL,
    estado contabilidad.estado_gestion_enum DEFAULT 'ABIERTA'::contabilidad.estado_gestion_enum NOT NULL,
    comprobante_cierre_id integer,
    fecha_cierre timestamp(6) without time zone,
    usuario_cierre_id integer,
    observacion_cierre text,
    comprobante_apertura_id integer,
    fecha_apertura timestamp(6) without time zone,
    usuario_apertura_id integer,
    observacion_apertura text,
    fecha_ultima_reapertura timestamp(6) without time zone,
    usuario_ultima_reapertura_id integer,
    observacion_ultima_reapertura text,
    creado_en timestamp(6) without time zone DEFAULT now() NOT NULL,
    actualizado_en timestamp(6) without time zone DEFAULT now() NOT NULL
);


--
-- Name: gestion_proceso_bitacora; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.gestion_proceso_bitacora (
    id bigint NOT NULL,
    tipo_proceso contabilidad.tipo_proceso_gestion_enum NOT NULL,
    estado contabilidad.estado_proceso_gestion_enum DEFAULT 'PENDIENTE'::contabilidad.estado_proceso_gestion_enum NOT NULL,
    gestion_origen integer NOT NULL,
    gestion_destino integer,
    comprobante_id integer,
    backup_id bigint,
    restauracion_id bigint,
    usuario_id integer,
    usuario_nombre character varying(200),
    observacion text,
    detalle_json jsonb,
    fecha_hora_inicio timestamp(6) without time zone DEFAULT now() NOT NULL,
    fecha_hora_fin timestamp(6) without time zone,
    creado_en timestamp(6) without time zone DEFAULT now() NOT NULL
);


--
-- Name: gestion_proceso_bitacora_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.gestion_proceso_bitacora_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gestion_proceso_bitacora_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.gestion_proceso_bitacora_id_seq OWNED BY contabilidad.gestion_proceso_bitacora.id;


--
-- Name: gestion_proceso_bitacora_id_seq1; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

ALTER TABLE contabilidad.gestion_proceso_bitacora ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME contabilidad.gestion_proceso_bitacora_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: moneda; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.moneda (
    codigo character varying(10) NOT NULL,
    nombre character varying(50) NOT NULL,
    simbolo character varying(10),
    activo boolean DEFAULT true NOT NULL
);


--
-- Name: movimiento_tesoreria; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.movimiento_tesoreria (
    id bigint NOT NULL,
    fecha date NOT NULL,
    tipo_movimiento contabilidad.tipo_mov_tesoreria_enum NOT NULL,
    medio_origen contabilidad.medio_tesoreria_enum,
    caja_origen_id bigint,
    banco_origen_id bigint,
    medio_destino contabilidad.medio_tesoreria_enum,
    caja_destino_id bigint,
    banco_destino_id bigint,
    auxiliar_id bigint,
    contra_cuenta_codigo character varying(30),
    moneda_codigo character varying(10) NOT NULL,
    tipo_cambio numeric(18,6) DEFAULT 1 NOT NULL,
    monto numeric(18,2) NOT NULL,
    referencia character varying(150),
    glosa character varying(500) NOT NULL,
    estado contabilidad.estado_generico_enum DEFAULT 'BORRADOR'::contabilidad.estado_generico_enum NOT NULL,
    asiento_id bigint,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT movimiento_tesoreria_monto_check CHECK ((monto > (0)::numeric)),
    CONSTRAINT movimiento_tesoreria_tipo_cambio_check CHECK ((tipo_cambio > (0)::numeric))
);


--
-- Name: movimiento_tesoreria_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.movimiento_tesoreria_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: movimiento_tesoreria_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.movimiento_tesoreria_id_seq OWNED BY contabilidad.movimiento_tesoreria.id;


--
-- Name: pago_detalle_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.pago_detalle_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pago_detalle_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.pago_detalle_id_seq OWNED BY contabilidad.pago_detalle.id;


--
-- Name: pago_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.pago_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pago_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.pago_id_seq OWNED BY contabilidad.pago.id;


--
-- Name: sistema_control_sesion; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.sistema_control_sesion (
    id smallint DEFAULT 1 NOT NULL,
    forzar_relogin_desde timestamp(6) without time zone,
    actualizado_en timestamp(6) without time zone DEFAULT now() NOT NULL,
    actualizado_por character varying(150)
);


--
-- Name: tipo_cambio; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.tipo_cambio (
    fecha date NOT NULL,
    usd_paralelo numeric(10,4) NOT NULL,
    ufv numeric(12,6) NOT NULL,
    registrado_por character varying(120) NOT NULL,
    registrado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_por character varying(120),
    actualizado_en timestamp(6) without time zone
);


--
-- Name: TABLE tipo_cambio; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON TABLE contabilidad.tipo_cambio IS 'Tipo de cambio diario USD paralelo y UFV';


--
-- Name: COLUMN tipo_cambio.fecha; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.tipo_cambio.fecha IS 'Fecha del tipo de cambio';


--
-- Name: COLUMN tipo_cambio.usd_paralelo; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.tipo_cambio.usd_paralelo IS 'Tipo de cambio USD mercado paralelo (Bs por 1 USD)';


--
-- Name: COLUMN tipo_cambio.ufv; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.tipo_cambio.ufv IS 'Unidad de Fomento a la Vivienda BCB (valor en Bs)';


--
-- Name: COLUMN tipo_cambio.registrado_por; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.tipo_cambio.registrado_por IS 'Usuario que registró el valor';


--
-- Name: COLUMN tipo_cambio.registrado_en; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.tipo_cambio.registrado_en IS 'Fecha/hora de registro';


--
-- Name: COLUMN tipo_cambio.actualizado_por; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.tipo_cambio.actualizado_por IS 'Usuario que actualizó el valor';


--
-- Name: COLUMN tipo_cambio.actualizado_en; Type: COMMENT; Schema: contabilidad; Owner: -
--

COMMENT ON COLUMN contabilidad.tipo_cambio.actualizado_en IS 'Fecha/hora de última actualización';


--
-- Name: venta; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.venta (
    id bigint NOT NULL,
    fecha date NOT NULL,
    cliente_auxiliar_id bigint,
    cliente_empresa_id bigint,
    tipo_venta contabilidad.tipo_venta_enum NOT NULL,
    origen_documento contabilidad.origen_documento_enum DEFAULT 'MANUAL'::contabilidad.origen_documento_enum NOT NULL,
    factura_electronica_id bigint,
    numero_factura_ext character varying(100),
    nit_cliente character varying(50),
    nombre_cliente character varying(200),
    glosa character varying(500) NOT NULL,
    moneda_codigo character varying(10) NOT NULL,
    tipo_cambio numeric(18,6) DEFAULT 1 NOT NULL,
    subtotal numeric(18,2) DEFAULT 0 NOT NULL,
    impuestos numeric(18,2) DEFAULT 0 NOT NULL,
    total numeric(18,2) NOT NULL,
    contra_cuenta_codigo character varying(30) NOT NULL,
    estado contabilidad.estado_generico_enum DEFAULT 'BORRADOR'::contabilidad.estado_generico_enum NOT NULL,
    asiento_id bigint,
    creado_en timestamp(6) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actualizado_en timestamp(6) without time zone,
    CONSTRAINT venta_impuestos_check CHECK ((impuestos >= (0)::numeric)),
    CONSTRAINT venta_subtotal_check CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT venta_tipo_cambio_check CHECK ((tipo_cambio > (0)::numeric)),
    CONSTRAINT venta_total_check CHECK ((total >= (0)::numeric))
);


--
-- Name: venta_detalle; Type: TABLE; Schema: contabilidad; Owner: -
--

CREATE TABLE contabilidad.venta_detalle (
    id bigint NOT NULL,
    venta_id bigint NOT NULL,
    secuencia integer NOT NULL,
    descripcion character varying(300) NOT NULL,
    cantidad numeric(18,4) DEFAULT 1 NOT NULL,
    precio_unitario numeric(18,2) DEFAULT 0 NOT NULL,
    subtotal numeric(18,2) NOT NULL,
    cuenta_ingreso_codigo character varying(30) NOT NULL,
    centro_costo_id bigint,
    CONSTRAINT venta_detalle_cantidad_check CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT venta_detalle_precio_unitario_check CHECK ((precio_unitario >= (0)::numeric)),
    CONSTRAINT venta_detalle_subtotal_check CHECK ((subtotal >= (0)::numeric))
);


--
-- Name: venta_detalle_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.venta_detalle_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: venta_detalle_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.venta_detalle_id_seq OWNED BY contabilidad.venta_detalle.id;


--
-- Name: venta_id_seq; Type: SEQUENCE; Schema: contabilidad; Owner: -
--

CREATE SEQUENCE contabilidad.venta_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: venta_id_seq; Type: SEQUENCE OWNED BY; Schema: contabilidad; Owner: -
--

ALTER SEQUENCE contabilidad.venta_id_seq OWNED BY contabilidad.venta.id;


--
-- Name: vw_saldo_factura_electronica; Type: VIEW; Schema: contabilidad; Owner: -
--

CREATE VIEW contabilidad.vw_saldo_factura_electronica AS
 SELECT id,
    origen,
    codigo_externo,
    cliente_auxiliar_id,
    cliente_empresa_id,
    nit_cliente,
    nombre_cliente,
    numero_factura,
    fecha_emision,
    importe_total,
    saldo_pendiente,
    estado
   FROM contabilidad.factura_electronica f;


--
-- Name: _tipo_cambio id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad._tipo_cambio ALTER COLUMN id SET DEFAULT nextval('contabilidad._tipo_cambio_id_seq'::regclass);


--
-- Name: arqueo_caja id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.arqueo_caja ALTER COLUMN id SET DEFAULT nextval('contabilidad.arqueo_caja_id_seq'::regclass);


--
-- Name: asiento id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento ALTER COLUMN id SET DEFAULT nextval('contabilidad.asiento_id_seq'::regclass);


--
-- Name: asiento_detalle id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento_detalle ALTER COLUMN id SET DEFAULT nextval('contabilidad.asiento_detalle_id_seq'::regclass);


--
-- Name: auxiliar id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.auxiliar ALTER COLUMN id SET DEFAULT nextval('contabilidad.auxiliar_id_seq'::regclass);


--
-- Name: auxiliar_cuenta id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.auxiliar_cuenta ALTER COLUMN id SET DEFAULT nextval('contabilidad.auxiliar_cuenta_id_seq'::regclass);


--
-- Name: caja id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.caja ALTER COLUMN id SET DEFAULT nextval('contabilidad.caja_id_seq'::regclass);


--
-- Name: centro_costo id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.centro_costo ALTER COLUMN id SET DEFAULT nextval('contabilidad.centro_costo_id_seq'::regclass);


--
-- Name: cobro id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro ALTER COLUMN id SET DEFAULT nextval('contabilidad.cobro_id_seq'::regclass);


--
-- Name: cobro_detalle id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro_detalle ALTER COLUMN id SET DEFAULT nextval('contabilidad.cobro_detalle_id_seq'::regclass);


--
-- Name: compra id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra ALTER COLUMN id SET DEFAULT nextval('contabilidad.compra_id_seq'::regclass);


--
-- Name: compra_detalle id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra_detalle ALTER COLUMN id SET DEFAULT nextval('contabilidad.compra_detalle_id_seq'::regclass);


--
-- Name: compromiso id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compromiso ALTER COLUMN id SET DEFAULT nextval('contabilidad.compromiso_id_seq'::regclass);


--
-- Name: compromiso_detalle id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compromiso_detalle ALTER COLUMN id SET DEFAULT nextval('contabilidad.compromiso_detalle_id_seq'::regclass);


--
-- Name: cuenta_bancaria id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta_bancaria ALTER COLUMN id SET DEFAULT nextval('contabilidad.cuenta_bancaria_id_seq'::regclass);


--
-- Name: documento_asiento id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.documento_asiento ALTER COLUMN id SET DEFAULT nextval('contabilidad.documento_asiento_id_seq'::regclass);


--
-- Name: factura_aplicacion id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_aplicacion ALTER COLUMN id SET DEFAULT nextval('contabilidad.factura_aplicacion_id_seq'::regclass);


--
-- Name: factura_electronica id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_electronica ALTER COLUMN id SET DEFAULT nextval('contabilidad.factura_electronica_id_seq'::regclass);


--
-- Name: factura_regularizacion id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_regularizacion ALTER COLUMN id SET DEFAULT nextval('contabilidad.factura_regularizacion_id_seq'::regclass);


--
-- Name: movimiento_tesoreria id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria ALTER COLUMN id SET DEFAULT nextval('contabilidad.movimiento_tesoreria_id_seq'::regclass);


--
-- Name: pago id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago ALTER COLUMN id SET DEFAULT nextval('contabilidad.pago_id_seq'::regclass);


--
-- Name: pago_detalle id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago_detalle ALTER COLUMN id SET DEFAULT nextval('contabilidad.pago_detalle_id_seq'::regclass);


--
-- Name: venta id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta ALTER COLUMN id SET DEFAULT nextval('contabilidad.venta_id_seq'::regclass);


--
-- Name: venta_detalle id; Type: DEFAULT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta_detalle ALTER COLUMN id SET DEFAULT nextval('contabilidad.venta_detalle_id_seq'::regclass);


--
-- Data for Name: _tipo_cambio; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad._tipo_cambio (id, fecha, moneda_codigo, compra, venta, observado, activo, creado_en, actualizado_en) FROM stdin;
\.


--
-- Data for Name: arqueo_caja; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.arqueo_caja (id, caja_id, fecha_arqueo, saldo_anterior, ingresos_dia, egresos_dia, saldo_teorico, monto_contado, diferencia, observacion, estado, usuario_nombre, creado_en, actualizado_en) FROM stdin;
2	2	2026-03-19	-500.00	0.00	0.00	-500.00	50.00	550.00	error de operador	BORRADOR	AUGUSTO CAMACHO MENESES	2026-03-19 04:01:13.357165	2026-03-19 04:01:13.357165
\.


--
-- Data for Name: asiento; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.asiento (id, fecha, moneda_codigo, tipo_cambio, glosa, referencia, modulo_origen, tabla_origen, origen_id, estado, atributos, creado_en, actualizado_en) FROM stdin;
1	2026-03-17	BOB	1.000000	Pago del compromiso con el banco	None	TESORERIA	contabilidad.pago	1	CONFIRMADO	{"origen": "tesoreria_pagos"}	2026-03-17 02:17:39.692519	2026-03-17 02:17:39.692519
2	2026-03-17	BOB	1.000000	alquiler de quiosco feb/2026	00001	TESORERIA	contabilidad.pago	2	CONFIRMADO	{"origen": "tesoreria_pagos", "version": "v3"}	2026-03-17 21:03:45.571664	2026-03-17 21:03:45.571664
3	2026-03-17	BOB	1.000000	ALQUILER DE OFICINA FEB/2026	5342	TESORERIA	contabilidad.pago	3	CONFIRMADO	{"origen": "tesoreria_pagos", "version": "v3"}	2026-03-17 21:16:12.318642	2026-03-17 21:16:12.318642
4	2026-03-18	BOB	1.000000	CLIENTE ALFA COBRO	00002	TESORERIA	contabilidad.cobro	1	CONFIRMADO	{"origen": "tesoreria_cobros", "version": "v3"}	2026-03-18 01:20:34.128705	2026-03-18 01:20:34.128705
5	2026-03-24	BOB	1.000000	alquiler	None	TESORERIA	contabilidad.cobro	6	CONFIRMADO	{"origen": "tesoreria_cobros", "version": "v3"}	2026-03-24 00:32:43.836144	2026-03-24 00:32:43.836144
6	2026-03-24	BOB	1.000000	ALQUILERS	\N	TESORERIA	contabilidad.cobro	7	CONFIRMADO	{"origen": "tesoreria_cobros", "version": "v3"}	2026-03-24 00:33:40.77899	2026-03-24 00:33:40.77899
7	2026-03-24	BOB	1.000000	Cobro directo simple	\N	TESORERIA	contabilidad.cobro	8	CONFIRMADO	{"origen": "tesoreria_cobros", "version": "v3"}	2026-03-24 16:27:54.467671	2026-03-24 16:27:54.467671
\.


--
-- Data for Name: asiento_detalle; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.asiento_detalle (id, asiento_id, secuencia, cuenta_codigo, auxiliar_id, centro_costo_id, glosa, debe, haber, monto_moneda, referencia, atributos) FROM stdin;
1	1	1	6.1.1.008	1	\N	Pago del compromiso con el banco	3500.00	0.00	3500.00	None	\N
2	1	2	1.1.1.001	\N	\N	Pago del compromiso con el banco	0.00	3500.00	3500.00	None	\N
3	2	1	6.1.1.008	22	\N	alquiler de quiosco feb/2026	500.00	0.00	500.00	00001	{"tipo": "debe_pago_simple"}
4	2	2	1.1.1.001	\N	\N	Salida por CAJA - CAJA CHICA	0.00	500.00	500.00	00001	{"tipo": "haber_pago"}
5	3	1	6.1.1.008	1	\N	Compromiso 00001 - PRUEBA TES - ALQUILER OFICINA CENTRAL - 10/01/2026	3500.00	0.00	3500.00	5342	{"tipo": "debe_pago"}
6	3	2	1.1.1.002	\N	\N	Salida por BANCO - BANCO BISA · 2000000001	0.00	3500.00	3500.00	5342	{"tipo": "haber_pago"}
7	4	1	1.1.2.001	22	\N	Compromiso 99001 - Compromiso de cobro Cliente Alfa - 15/04/2026	0.00	3500.00	3500.00	00002	{"tipo": "haber_cobro"}
8	4	2	1.1.1.001	\N	\N	Ingreso por CAJA - CAJA CHICA	3500.00	0.00	3500.00	00002	{"tipo": "debe_ingreso_cobro"}
9	5	1	6.1.1.008	5	\N	alquiler	0.00	100.00	100.00	None	{"tipo": "haber_cobro_simple"}
10	5	2	1.1.1.001	\N	\N	Ingreso por CAJA - CAJA CHICA	100.00	0.00	100.00	None	{"tipo": "debe_ingreso_cobro"}
11	6	1	6.1.1.008	4	\N	ALQUILERS	0.00	5000.00	5000.00	\N	{"tipo": "haber_cobro_simple"}
12	6	2	1.1.1.001	\N	\N	Ingreso por CAJA - CAJA CHICA	5000.00	0.00	5000.00	\N	{"tipo": "debe_ingreso_cobro"}
13	7	1	6.1.1.008	4	\N	Cobro directo simple	0.00	1860.00	1860.00	\N	{"tipo": "haber_cobro_simple"}
14	7	2	1.1.1.001	\N	\N	Ingreso por CAJA - CAJA CHICA	1860.00	0.00	1860.00	\N	{"tipo": "debe_ingreso_cobro"}
\.


--
-- Data for Name: auxiliar; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.auxiliar (id, tipo, origen_tabla, ref_id, codigo_externo, nit_ci, nombre, razon_social, telefono, email, direccion, es_ocasional, activo, creado_en, actualizado_en, observaciones) FROM stdin;
1	PROVEEDOR	\N	\N	\N	900100201	PRUEBA TES - INMOBILIARIA CENTRAL	INMOBILIARIA CENTRAL S.R.L.	76543210	pruebas.alquiler@dxtsys.local	Av. Oficina Central Nro. 101	f	t	2026-03-16 19:05:13.418787	\N	Auxiliar de prueba para Tesorería Pagos
2	PROVEEDOR	\N	\N	\N	900100202	PRUEBA TES - SOPORTE TECNICO PLATAFORMA	SOPORTE TECNICO PLATAFORMA S.R.L.	76543211	pruebas.soporte@dxtsys.local	Calle Sistemas Nro. 202	f	t	2026-03-16 19:05:13.418787	\N	Auxiliar de prueba para Tesorería Pagos
3	PROVEEDOR	\N	\N	\N	900100203	PRUEBA TES - LICENCIAS Y CLOUD	LICENCIAS Y CLOUD BOLIVIA S.A.	76543212	pruebas.cloud@dxtsys.local	Zona Empresarial Nro. 303	f	t	2026-03-16 19:05:13.418787	\N	Auxiliar de prueba para Tesorería Pagos
4	BANCO	\N	\N	00001	\N	BANCO UNION	BANCO UNION S.A.	\N	\N	\N	f	t	2026-03-17 01:38:44.293316	\N	Registro de prueba para cuentas bancarias
5	BANCO	\N	\N	00002	\N	BANCO BISA	BANCO BISA S.A.	\N	\N	\N	f	t	2026-03-17 01:38:44.293316	\N	Registro de prueba para cuentas bancarias
6	BANCO	\N	\N	00003	\N	BANCO MERCANTIL SANTA CRUZ	BANCO MERCANTIL SANTA CRUZ S.A.	\N	\N	\N	f	t	2026-03-17 01:38:44.293316	\N	Registro de prueba para cuentas bancarias
22	CLIENTE	\N	\N	CLI-0001	10000001	PRUEBA COBRO - CLIENTE ALFA	CLIENTE ALFA S.R.L.	70000001	cliente.alfa@test.local	Zona Central #101	f	t	2026-03-17 04:07:26.952537	\N	Cliente de prueba para compromisos de cobro
23	CLIENTE	\N	\N	CLI-0002	10000002	PRUEBA COBRO - CLIENTE BETA	CLIENTE BETA S.A.	70000002	cliente.beta@test.local	Av. Principal #202	f	t	2026-03-17 04:07:26.952537	\N	Cliente de prueba para compromisos de cobro
24	CLIENTE	\N	\N	CLI-0003	10000003	PRUEBA COBRO - CLIENTE GAMMA	CLIENTE GAMMA LTDA.	70000003	cliente.gamma@test.local	Calle Secundaria #303	f	t	2026-03-17 04:07:26.952537	\N	Cliente de prueba para compromisos de cobro
25	CLIENTE	clientes.empresas	1	1007017028	1007017028	LA BOLIVIANA	LA BOLIVIANA CIACRUZ DE SEGUROS Y REASEGUROS S.A.	800102727	jhimmy.mendoza@lbc.bo	AV. BALLIVIÁN #1213, ESQUINA CALLE 19 DE CALACOTO	f	t	2026-03-19 03:12:59.897691	2026-03-19 03:13:47.955047	CLIENTE DE DXT MAGAZINE
26	CLIENTE	\N	\N	\N	1000854026	ENTEL	EMPRESA NACIONAL DE TELECOMINICACIONES	\N	\N	C. Federico Zuazo N° 1771	t	t	2026-03-30 14:14:15.817918	2026-03-30 14:14:15.817918	SERVICIO DE TELEFONÍA E INTERNET
\.


--
-- Data for Name: auxiliar_cuenta; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.auxiliar_cuenta (id, auxiliar_id, cuenta_codigo, activo, creado_en) FROM stdin;
1	4	2.1.2.001	t	2026-03-20 22:06:26.783658
2	6	1.1.2.002	t	2026-03-20 22:07:43.199973
\.


--
-- Data for Name: caja; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.caja (id, codigo, nombre, cuenta_contable_codigo, activo, creado_en, actualizado_en) FROM stdin;
1	00001	CAJA GENERAL	1.1.1.001	t	2026-03-16 23:12:46.992405	\N
2	00002	CAJA CHICA	1.1.1.001	t	2026-03-16 23:12:46.992405	\N
3	00003	CAJA SUCURSAL 1	1.1.1.001	t	2026-03-16 23:12:46.992405	\N
4	00004	CAJA SUCURSAL 2	1.1.1.001	t	2026-03-16 23:12:46.992405	\N
\.


--
-- Data for Name: centro_costo; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.centro_costo (id, codigo, nombre, descripcion, activo, creado_en, actualizado_en) FROM stdin;
2	FIN	Finanzas	Centro de costo para operaciones financieras y contables	t	2026-03-18 16:47:34.675202	\N
3	TES	Tesorería	Centro de costo para gestión de caja, bancos y pagos	t	2026-03-18 16:47:34.675202	\N
5	VEN	Ventas	Centro de costo para actividades comerciales e ingresos	t	2026-03-18 16:47:34.675202	\N
6	SIS	Sistemas	Centro de costo para soporte tecnológico e infraestructura	t	2026-03-18 16:47:34.675202	\N
1	ADM	Administración	Centro de costo para gastos administrativos generales	t	2026-03-18 16:47:34.675202	2026-03-18 16:49:44.550698
4	COM	Compras	Centro de costo para adquisiciones y abastecimiento	t	2026-03-18 16:47:34.675202	2026-03-18 16:49:49.937012
\.


--
-- Data for Name: cobro; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.cobro (id, fecha, cliente_auxiliar_id, medio_pago, contra_cuenta_codigo, caja_id, cuenta_bancaria_id, moneda_codigo, tipo_cambio, monto_total, referencia, glosa, estado, asiento_id, creado_en, actualizado_en, origen_operacion) FROM stdin;
1	2026-03-18	22	CAJA	1.1.2.001	2	\N	BOB	1.000000	3500.00	00002	CLIENTE ALFA COBRO	CONFIRMADO	4	2026-03-18 01:20:16.373985	2026-03-18 01:20:34.128705	COMPROMISO
6	2026-03-24	5	CAJA	6.1.1.008	2	\N	BOB	1.000000	100.00	None	alquiler	CONFIRMADO	5	2026-03-24 00:31:53.968165	2026-03-24 00:32:43.836144	DIRECTO
7	2026-03-24	4	CAJA	6.1.1.008	2	\N	BOB	1.000000	5000.00	\N	ALQUILERS	CONFIRMADO	6	2026-03-24 00:33:40.604551	2026-03-24 00:33:40.77899	DIRECTO
8	2026-03-24	4	CAJA	6.1.1.008	2	\N	BOB	1.000000	1860.00	\N	Cobro directo simple	CONFIRMADO	7	2026-03-24 16:27:54.386624	2026-03-24 16:27:54.467671	DIRECTO
\.


--
-- Data for Name: cobro_detalle; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.cobro_detalle (id, cobro_id, secuencia, tipo_linea, compromiso_detalle_id, descripcion, cantidad, precio_unitario, subtotal, observacion, creado_en, actualizado_en) FROM stdin;
2	1	1	COMPROMISO	22	Compromiso 99001 - Compromiso de cobro Cliente Alfa - 15/04/2026	1.0000	3500.00	3500.00	Cuota 1 de 3	2026-03-18 01:20:34.070869	2026-03-18 01:20:34.070869
\.


--
-- Data for Name: compra; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.compra (id, fecha, proveedor_auxiliar_id, proveedor_nit, proveedor_nombre, numero_factura, fecha_factura, tipo_compra, glosa, moneda_codigo, tipo_cambio, subtotal, impuestos, total, contra_cuenta_codigo, estado, asiento_id, creado_en, actualizado_en) FROM stdin;
\.


--
-- Data for Name: compra_detalle; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.compra_detalle (id, compra_id, secuencia, descripcion, cantidad, precio_unitario, subtotal, cuenta_gasto_codigo, centro_costo_id) FROM stdin;
\.


--
-- Data for Name: compromiso; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.compromiso (id, codigo, tipo, nombre, descripcion, auxiliar_id, cuenta_contable, gestion, activo, creado_en, actualizado_en) FROM stdin;
3	00002	PAGAR	PRUEBA TES - MANTENIMIENTO PLATAFORMA DXTSYS	Compromiso de prueba para Tesorería. Servicio periódico de mantenimiento y soporte.	2	6.1.1.014	2026	t	2026-03-16 19:05:13.418787	2026-03-16 21:28:47.133358
4	00003	PAGAR	PRUEBA TES - LICENCIAS Y SERVICIOS CLOUD	Compromiso de prueba para Tesorería. Licencias operativas y servicios cloud.	3	6.1.1.017	2026	t	2026-03-16 19:05:13.418787	2026-03-16 21:29:14.936454
2	00001	PAGAR	PRUEBA TES - ALQUILER OFICINA CENTRAL	Compromiso de prueba para Tesorería. Alquiler mensual de oficina central.	1	6.1.1.008	2026	t	2026-03-16 19:05:13.418787	2026-03-16 23:51:03.829886
6	99001	COBRAR	Compromiso de cobro Cliente Alfa	Compromiso programado de cobro en tres cuotas para Cliente Alfa	22	1.1.2.001	2026	t	2026-03-17 04:07:26.952537	\N
7	99002	COBRAR	Compromiso de cobro Cliente Beta	Compromiso programado de cobro en dos cuotas para Cliente Beta	23	1.1.2.001	2026	t	2026-03-17 04:07:26.952537	\N
8	99003	COBRAR	Compromiso único de cobro Cliente Gamma	Compromiso único de cobro para Cliente Gamma	24	1.1.2.001	2026	t	2026-03-17 04:07:26.952537	2026-03-18 01:42:27.019617
9	99004	PAGAR	INTERNET	PAGO MENSUAL DE SERVICIO DE INTERNET	26	6.1.1.010	2026	t	2026-03-30 16:59:30.095978	\N
\.


--
-- Data for Name: compromiso_detalle; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.compromiso_detalle (id, compromiso_id, fecha_vencimiento, monto_programado, monto_registrado, estado, observacion, creado_en, actualizado_en) FROM stdin;
11	3	2026-02-15	1800.00	0.00	PENDIENTE	Servicio 1 de 5	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
12	3	2026-04-15	1800.00	0.00	PENDIENTE	Servicio 2 de 5	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
13	3	2026-06-15	1800.00	0.00	PENDIENTE	Servicio 3 de 5	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
14	3	2026-08-15	1800.00	0.00	PENDIENTE	Servicio 4 de 5	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
15	3	2026-10-15	1800.00	0.00	PENDIENTE	Servicio 5 de 5	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
16	4	2026-01-20	950.00	0.00	PENDIENTE	Licencia 1 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
17	4	2026-03-20	950.00	0.00	PENDIENTE	Licencia 2 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
18	4	2026-05-20	950.00	0.00	PENDIENTE	Licencia 3 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
19	4	2026-07-20	950.00	0.00	PENDIENTE	Licencia 4 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
20	4	2026-09-20	950.00	0.00	PENDIENTE	Licencia 5 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
21	4	2026-11-20	950.00	0.00	PENDIENTE	Licencia 6 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
7	2	2026-03-10	3500.00	0.00	PENDIENTE	Cuota 3 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
8	2	2026-04-10	3500.00	0.00	PENDIENTE	Cuota 4 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
9	2	2026-05-10	3500.00	0.00	PENDIENTE	Cuota 5 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
10	2	2026-06-10	3500.00	0.00	PENDIENTE	Cuota 6 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
23	6	2026-05-15	3500.00	0.00	PENDIENTE	Cuota 2 de 3	2026-03-17 04:07:26.952537	2026-03-17 19:26:20.199605
24	6	2026-06-15	3500.00	0.00	PENDIENTE	Cuota 3 de 3	2026-03-17 04:07:26.952537	2026-03-17 19:26:20.199605
25	7	2026-04-20	5000.00	0.00	PENDIENTE	Cuota 1 de 2	2026-03-17 04:07:26.952537	2026-03-17 19:26:20.199605
26	7	2026-05-20	5000.00	0.00	PENDIENTE	Cuota 2 de 2	2026-03-17 04:07:26.952537	2026-03-17 19:26:20.199605
6	2	2026-02-10	3500.00	3500.00	PAGADO	Cuota 2 de 6	2026-03-16 19:05:13.418787	2026-03-17 19:26:20.199605
5	2	2026-01-10	3500.00	3500.00	PAGADO	Cuota 1 de 6	2026-03-16 19:05:13.418787	2026-03-17 21:16:12.318642
22	6	2026-04-15	3500.00	3500.00	COBRADO	Cuota 1 de 3	2026-03-17 04:07:26.952537	2026-03-18 01:20:34.128705
27	8	2026-04-25	7800.00	0.00	PENDIENTE	Cobro único	2026-03-17 04:07:26.952537	2026-03-18 01:42:27.019617
28	9	2026-04-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
29	9	2026-05-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
30	9	2026-06-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
31	9	2026-07-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
32	9	2026-08-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
33	9	2026-09-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
34	9	2026-10-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
35	9	2026-11-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
36	9	2026-12-09	235.00	0.00	PENDIENTE	\N	2026-03-30 16:59:30.095978	\N
\.


--
-- Data for Name: cuenta; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.cuenta (codigo, nombre, nivel, tipo, naturaleza, es_postable, requiere_auxiliar, requiere_cc, codigo_padre, activo, creado_en, actualizado_en) FROM stdin;
1	ACTIVO	1	ACTIVO	DEUDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
1.1	ACTIVO CORRIENTE	2	ACTIVO	DEUDORA	f	f	f	1	t	2026-03-11 19:54:30.965984	\N
1.1.1	EFECTIVO Y EQUIVALENTES DE EFECTIVO	3	ACTIVO	DEUDORA	f	f	f	1.1	t	2026-03-11 19:54:30.965984	\N
1.1.1.001	CAJA	4	ACTIVO	DEUDORA	t	f	f	1.1.1	t	2026-03-11 19:54:30.965984	\N
1.1.1.002	BANCOS	4	ACTIVO	DEUDORA	t	f	f	1.1.1	t	2026-03-11 19:54:30.965984	\N
1.1.1.003	INVERSIONES AL VALOR RAZONABLE	4	ACTIVO	DEUDORA	t	f	f	1.1.1	t	2026-03-11 19:54:30.965984	\N
1.1.1.004	INVERSIONES DISPONIBLES PARA LA VENTA	4	ACTIVO	DEUDORA	t	f	f	1.1.1	t	2026-03-11 19:54:30.965984	\N
1.1.1.005	INVERSIONES EN CRIPTOACTIVOS	4	ACTIVO	DEUDORA	t	f	f	1.1.1	t	2026-03-11 19:54:30.965984	\N
1.1.2	EXIGIBLE DE CORTO PLAZO	3	ACTIVO	DEUDORA	f	f	f	1.1	t	2026-03-11 19:54:30.965984	\N
1.1.2.001	CUENTAS POR COBRAR	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.002	DOCUMENTOS POR COBRAR	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.003	PRESTAMOS POR COBRAR	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.004	CUENTAS POR COBRAR A EMPRESAS RELACIONADAS	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.005	CUENTAS POR COBRAR AL PERSONAL, SOCIOS Y DIRECTORES	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.006	INTERESES COMERCIALES POR COBRAR	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.007	INTERESES FINANCIEROS POR COBRAR	4	ACTIVO	DEUDORA	t	f	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.008	DIVIDENDOS POR COBRAR	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.009	COMISIONES POR COBRAR	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.010	ALQUILERES POR COBRAR	4	ACTIVO	DEUDORA	t	f	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.011	ANTICIPOS POR COBRAR	4	ACTIVO	DEUDORA	t	t	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.012	RECLAMOS AL SEGURO	4	ACTIVO	DEUDORA	t	f	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.013	FONDOS A RENDIR	4	ACTIVO	DEUDORA	t	f	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.015	DEPOSITOS EN GARANTIA POR COBRAR	4	ACTIVO	DEUDORA	t	f	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.016	COBRANZA DUDOSA	4	ACTIVO	DEUDORA	t	f	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.2.019	OTRAS CUENTAS POR COBRAR	4	ACTIVO	DEUDORA	t	f	f	1.1.2	t	2026-03-11 19:54:30.965984	\N
1.1.3	REALIZABLE DE CORTO PLAZO	3	ACTIVO	DEUDORA	f	f	f	1.1	t	2026-03-11 19:54:30.965984	\N
1.1.3.001	EXISTENCIA DE MERCANCIAS	4	ACTIVO	DEUDORA	t	f	f	1.1.3	t	2026-03-11 19:54:30.965984	\N
1.1.3.002	EXISTENCIA DE MERCANCIAS EN CONSIGNACION	4	ACTIVO	DEUDORA	t	f	f	1.1.3	t	2026-03-11 19:54:30.965984	\N
1.1.3.003	EXISTENCIA DE MATERIALES, REPUESTOS Y ACCESORIOS	4	ACTIVO	DEUDORA	t	f	f	1.1.3	t	2026-03-11 19:54:30.965984	\N
1.1.3.004	EXISTENCIA DE ENVASES Y EMBALAJES	4	ACTIVO	DEUDORA	t	f	f	1.1.3	t	2026-03-11 19:54:30.965984	\N
1.1.3.006	MERCADERIA EN TRANSITO	4	ACTIVO	DEUDORA	t	f	f	1.1.3	t	2026-03-11 19:54:30.965984	\N
1.1.3.009	EXISTENCIA DE PRODUCTOS AVERIADOS	4	ACTIVO	DEUDORA	t	f	f	1.1.3	t	2026-03-11 19:54:30.965984	\N
1.1.3.011	BIENES INMUEBLES PARA LA VENTA	4	ACTIVO	DEUDORA	t	f	f	1.1.3	t	2026-03-11 19:54:30.965984	\N
1.1.5	ACTIVOS DIFERIDOS A CORTO PLAZO	3	ACTIVO	DEUDORA	f	f	f	1.1	t	2026-03-11 19:54:30.965984	\N
1.1.5.001	GASTOS PAGADOS POR ANTICIPADO	4	ACTIVO	DEUDORA	t	f	f	1.1.5	t	2026-03-11 19:54:30.965984	\N
1.1.5.005	OTROS CARGOS DIFERIDOS	4	ACTIVO	DEUDORA	t	f	f	1.1.5	t	2026-03-11 19:54:30.965984	\N
1.1.6	CUENTAS FISCALES	3	ACTIVO	DEUDORA	f	f	f	1.1	t	2026-03-11 19:54:30.965984	\N
1.1.6.001	IVA CREDITO FISCAL	4	ACTIVO	DEUDORA	t	f	f	1.1.6	t	2026-03-11 19:54:30.965984	\N
1.1.6.002	IVA CREDITO FISCAL COMPROMETIDO	4	ACTIVO	DEUDORA	t	f	f	1.1.6	t	2026-03-11 19:54:30.965984	\N
1.1.6.004	VALORES FISCALES NEGOCIABLES	4	ACTIVO	DEUDORA	t	f	f	1.1.6	t	2026-03-11 19:54:30.965984	\N
1.1.6.005	IT PAGADO POR ANTICIPADO	4	ACTIVO	DEUDORA	t	f	f	1.1.6	t	2026-03-11 19:54:30.965984	\N
1.1.6.006	IUE POR COMPENSAR	4	ACTIVO	DEUDORA	t	f	f	1.1.6	t	2026-03-11 19:54:30.965984	\N
1.1.6.007	IMPUESTOS DIFERIDOS	4	ACTIVO	DEUDORA	t	f	f	1.1.6	t	2026-03-11 19:54:30.965984	\N
1.2	ACTIVO NO CORRIENTE	2	ACTIVO	DEUDORA	f	f	f	1	t	2026-03-11 19:54:30.965984	\N
1.2.1	EXIGIBLE A LARGO PLAZO	3	ACTIVO	DEUDORA	f	f	f	1.2	t	2026-03-11 19:54:30.965984	\N
1.2.1.001	CUENTAS POR COBRAR LP	4	ACTIVO	DEUDORA	t	t	f	1.2.1	t	2026-03-11 19:54:30.965984	\N
1.2.1.002	DOCUMENTOS POR COBRAR LP	4	ACTIVO	DEUDORA	t	t	f	1.2.1	t	2026-03-11 19:54:30.965984	\N
1.2.1.003	PRESTAMOS POR COBRAR LP	4	ACTIVO	DEUDORA	t	t	f	1.2.1	t	2026-03-11 19:54:30.965984	\N
1.2.1.004	CUENTAS POR COBRAR A EMPRESAS RELACIONADAS LP	4	ACTIVO	DEUDORA	t	t	f	1.2.1	t	2026-03-11 19:54:30.965984	\N
1.2.1.005	DEPOSITOS EN GARANTIA POR COBRAR LP	4	ACTIVO	DEUDORA	t	f	f	1.2.1	t	2026-03-11 19:54:30.965984	\N
1.2.1.009	OTRAS CUENTAS POR COBRAR LP	4	ACTIVO	DEUDORA	t	f	f	1.2.1	t	2026-03-11 19:54:30.965984	\N
1.2.2	REALIZABLE A LARGO PLAZO	3	ACTIVO	DEUDORA	f	f	f	1.2	t	2026-03-11 19:54:30.965984	\N
1.2.2.001	EXISTENCIA DE MERCANCIAS LP	4	ACTIVO	DEUDORA	t	f	f	1.2.2	t	2026-03-11 19:54:30.965984	\N
1.2.2.009	OTRAS EXISTENCIAS LP	4	ACTIVO	DEUDORA	t	f	f	1.2.2	t	2026-03-11 19:54:30.965984	\N
1.2.3	INVERSIONES PERMANENTES	3	ACTIVO	DEUDORA	f	f	f	1.2	t	2026-03-11 19:54:30.965984	\N
1.2.3.001	INVERSIONES EN ACCIONES	4	ACTIVO	DEUDORA	t	f	f	1.2.3	t	2026-03-11 19:54:30.965984	\N
1.2.3.002	INVERSIONES EN CUOTAS DE CAPITAL	4	ACTIVO	DEUDORA	t	f	f	1.2.3	t	2026-03-11 19:54:30.965984	\N
1.2.3.003	INVERSIONES EN BONOS	4	ACTIVO	DEUDORA	t	f	f	1.2.3	t	2026-03-11 19:54:30.965984	\N
1.2.3.004	INVERSIONES EN TITULOS VALORES	4	ACTIVO	DEUDORA	t	f	f	1.2.3	t	2026-03-11 19:54:30.965984	\N
1.2.3.005	INVERSIONES EN BIENES INMUEBLES	4	ACTIVO	DEUDORA	t	f	f	1.2.3	t	2026-03-11 19:54:30.965984	\N
1.2.3.009	OTRAS INVERSIONES PERMANENTES	4	ACTIVO	DEUDORA	t	f	f	1.2.3	t	2026-03-11 19:54:30.965984	\N
1.2.4	ACTIVOS FIJOS	3	ACTIVO	DEUDORA	f	f	f	1.2	t	2026-03-11 19:54:30.965984	\N
1.2.4.001	TERRENOS	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.002	EDIFICIOS Y CONSTRUCCIONES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.003	MAQUINARIA Y EQUIPO	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.004	MUEBLES Y ENSERES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.005	EQUIPOS DE COMPUTACION	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.006	VEHICULOS	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.007	EQUIPOS DE COMUNICACION	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.008	INSTALACIONES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.009	HERRAMIENTAS Y UTILES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.010	OBRAS EN PROCESO	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.011	ACTIVOS EN ARRENDAMIENTO FINANCIERO	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.012	ACTIVOS POR DERECHO DE USO	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.019	OTROS ACTIVOS FIJOS	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.021	DEPRECIACION ACUM. EDIFICIOS Y CONSTRUCCIONES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.022	DEPRECIACION ACUM. MAQUINARIA Y EQUIPO	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.023	DEPRECIACION ACUM. MUEBLES Y ENSERES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.024	DEPRECIACION ACUM. EQUIPOS DE COMPUTACION	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.025	DEPRECIACION ACUM. VEHICULOS	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.026	DEPRECIACION ACUM. EQUIPOS DE COMUNICACION	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.027	DEPRECIACION ACUM. INSTALACIONES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.028	DEPRECIACION ACUM. HERRAMIENTAS Y UTILES	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.029	DEPRECIACION ACUM. ACTIVOS EN ARRENDAMIENTO	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.030	DEPRECIACION ACUM. ACTIVOS POR DERECHO DE USO	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.4.039	DEPRECIACION ACUM. OTROS ACTIVOS FIJOS	4	ACTIVO	DEUDORA	t	f	f	1.2.4	t	2026-03-11 19:54:30.965984	\N
1.2.5	ACTIVOS INTANGIBLES	3	ACTIVO	DEUDORA	f	f	f	1.2	t	2026-03-11 19:54:30.965984	\N
1.2.5.001	MARCAS Y PATENTES	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.002	LICENCIAS Y FRANQUICIAS	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.003	PROGRAMAS DE COMPUTACION (SOFTWARE)	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.004	DERECHOS DE AUTOR	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.005	PLUSVALIA (GOODWILL)	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.009	OTROS ACTIVOS INTANGIBLES	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.021	AMORTIZACION ACUM. MARCAS Y PATENTES	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.022	AMORTIZACION ACUM. LICENCIAS Y FRANQUICIAS	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.023	AMORTIZACION ACUM. PROGRAMAS DE COMPUTACION	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.024	AMORTIZACION ACUM. DERECHOS DE AUTOR	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.5.029	AMORTIZACION ACUM. OTROS ACTIVOS INTANGIBLES	4	ACTIVO	DEUDORA	t	f	f	1.2.5	t	2026-03-11 19:54:30.965984	\N
1.2.6	ACTIVOS DIFERIDOS A LARGO PLAZO	3	ACTIVO	DEUDORA	f	f	f	1.2	t	2026-03-11 19:54:30.965984	\N
1.2.6.001	GASTOS DE CONSTITUCION Y ORGANIZACION	4	ACTIVO	DEUDORA	t	f	f	1.2.6	t	2026-03-11 19:54:30.965984	\N
1.2.6.002	GASTOS DE INVESTIGACION Y DESARROLLO	4	ACTIVO	DEUDORA	t	f	f	1.2.6	t	2026-03-11 19:54:30.965984	\N
1.2.6.009	OTROS ACTIVOS DIFERIDOS	4	ACTIVO	DEUDORA	t	f	f	1.2.6	t	2026-03-11 19:54:30.965984	\N
2	PASIVO	1	PASIVO	ACREEDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
2.1	PASIVO CORRIENTE	2	PASIVO	ACREEDORA	f	f	f	2	t	2026-03-11 19:54:30.965984	\N
2.1.1	OBLIGACIONES COMERCIALES	3	PASIVO	ACREEDORA	f	f	f	2.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.001	CUENTAS POR PAGAR	4	PASIVO	ACREEDORA	t	t	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.002	DOCUMENTOS POR PAGAR	4	PASIVO	ACREEDORA	t	t	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.003	CUENTAS POR PAGAR A EMPRESAS RELACIONADAS	4	PASIVO	ACREEDORA	t	t	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.004	ANTICIPOS RECIBIDOS DE CLIENTES	4	PASIVO	ACREEDORA	t	t	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.005	COMISIONES POR PAGAR	4	PASIVO	ACREEDORA	t	t	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.006	INTERESES COMERCIALES POR PAGAR	4	PASIVO	ACREEDORA	t	t	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.007	ALQUILERES POR PAGAR	4	PASIVO	ACREEDORA	t	t	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.1.009	OTRAS CUENTAS POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.1	t	2026-03-11 19:54:30.965984	\N
2.1.2	OBLIGACIONES FINANCIERAS	3	PASIVO	ACREEDORA	f	f	f	2.1	t	2026-03-11 19:54:30.965984	\N
2.1.2.001	PRESTAMOS BANCARIOS	4	PASIVO	ACREEDORA	t	t	f	2.1.2	t	2026-03-11 19:54:30.965984	\N
2.1.2.002	PRESTAMOS DE OTRAS ENTIDADES FINANCIERAS	4	PASIVO	ACREEDORA	t	t	f	2.1.2	t	2026-03-11 19:54:30.965984	\N
2.1.2.003	PRESTAMOS DE EMPRESAS RELACIONADAS	4	PASIVO	ACREEDORA	t	t	f	2.1.2	t	2026-03-11 19:54:30.965984	\N
2.1.2.004	INTERESES FINANCIEROS POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.2	t	2026-03-11 19:54:30.965984	\N
2.1.2.005	OBLIGACIONES POR ARRENDAMIENTO FINANCIERO	4	PASIVO	ACREEDORA	t	f	f	2.1.2	t	2026-03-11 19:54:30.965984	\N
2.1.2.006	OBLIGACIONES POR ARRENDAMIENTO - PASIVO CORRIENTE	4	PASIVO	ACREEDORA	t	f	f	2.1.2	t	2026-03-11 19:54:30.965984	\N
2.1.2.009	OTRAS OBLIGACIONES FINANCIERAS	4	PASIVO	ACREEDORA	t	f	f	2.1.2	t	2026-03-11 19:54:30.965984	\N
2.1.3	OBLIGACIONES FISCALES	3	PASIVO	ACREEDORA	f	f	f	2.1	t	2026-03-11 19:54:30.965984	\N
2.1.3.001	IVA DEBITO FISCAL	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.3.002	IT POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.3.003	IUE POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.3.004	IEHD POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.3.005	ICE POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.3.006	IPBI POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.3.007	TASAS Y PATENTES MUNICIPALES POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.3.009	OTROS IMPUESTOS POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.3	t	2026-03-11 19:54:30.965984	\N
2.1.4	OBLIGACIONES LABORALES Y SOCIALES	3	PASIVO	ACREEDORA	f	f	f	2.1	t	2026-03-11 19:54:30.965984	\N
2.1.4.001	SUELDOS Y SALARIOS POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.002	AGUINALDO POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.003	VACACIONES POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.004	INDEMNIZACIONES POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.005	APORTES AFP POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.006	APORTES CNS POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.007	APORTES PRO-VIVIENDA POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.008	RC-IVA RETENIDO POR PAGAR	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.4.009	OTRAS OBLIGACIONES LABORALES	4	PASIVO	ACREEDORA	t	f	f	2.1.4	t	2026-03-11 19:54:30.965984	\N
2.1.5	OTRAS OBLIGACIONES A CORTO PLAZO	3	PASIVO	ACREEDORA	f	f	f	2.1	t	2026-03-11 19:54:30.965984	\N
2.1.5.001	DIVIDENDOS POR PAGAR	4	PASIVO	ACREEDORA	t	t	f	2.1.5	t	2026-03-11 19:54:30.965984	\N
2.1.5.002	DEPOSITOS EN GARANTIA RECIBIDOS	4	PASIVO	ACREEDORA	t	f	f	2.1.5	t	2026-03-11 19:54:30.965984	\N
2.1.5.003	INGRESOS DIFERIDOS	4	PASIVO	ACREEDORA	t	f	f	2.1.5	t	2026-03-11 19:54:30.965984	\N
2.1.5.009	OTRAS OBLIGACIONES	4	PASIVO	ACREEDORA	t	f	f	2.1.5	t	2026-03-11 19:54:30.965984	\N
2.2	PASIVO NO CORRIENTE	2	PASIVO	ACREEDORA	f	f	f	2	t	2026-03-11 19:54:30.965984	\N
2.2.1	OBLIGACIONES FINANCIERAS A LARGO PLAZO	3	PASIVO	ACREEDORA	f	f	f	2.2	t	2026-03-11 19:54:30.965984	\N
2.2.1.001	PRESTAMOS BANCARIOS A LARGO PLAZO	4	PASIVO	ACREEDORA	t	t	f	2.2.1	t	2026-03-11 19:54:30.965984	\N
2.2.1.002	PRESTAMOS DE OTRAS ENTIDADES FINANCIERAS LP	4	PASIVO	ACREEDORA	t	t	f	2.2.1	t	2026-03-11 19:54:30.965984	\N
2.2.1.003	PRESTAMOS DE EMPRESAS RELACIONADAS LP	4	PASIVO	ACREEDORA	t	t	f	2.2.1	t	2026-03-11 19:54:30.965984	\N
2.2.1.004	OBLIGACIONES POR ARRENDAMIENTO FINANCIERO LP	4	PASIVO	ACREEDORA	t	f	f	2.2.1	t	2026-03-11 19:54:30.965984	\N
2.2.1.005	OBLIGACIONES POR ARRENDAMIENTO - PASIVO NO CORRIENTE	4	PASIVO	ACREEDORA	t	f	f	2.2.1	t	2026-03-11 19:54:30.965984	\N
2.2.1.009	OTRAS OBLIGACIONES FINANCIERAS LP	4	PASIVO	ACREEDORA	t	f	f	2.2.1	t	2026-03-11 19:54:30.965984	\N
2.2.2	OBLIGACIONES COMERCIALES A LARGO PLAZO	3	PASIVO	ACREEDORA	f	f	f	2.2	t	2026-03-11 19:54:30.965984	\N
2.2.2.001	CUENTAS POR PAGAR LP	4	PASIVO	ACREEDORA	t	t	f	2.2.2	t	2026-03-11 19:54:30.965984	\N
2.2.2.009	OTRAS CUENTAS POR PAGAR LP	4	PASIVO	ACREEDORA	t	f	f	2.2.2	t	2026-03-11 19:54:30.965984	\N
2.2.3	OTRAS OBLIGACIONES A LARGO PLAZO	3	PASIVO	ACREEDORA	f	f	f	2.2	t	2026-03-11 19:54:30.965984	\N
2.2.3.001	DEPOSITOS EN GARANTIA RECIBIDOS LP	4	PASIVO	ACREEDORA	t	f	f	2.2.3	t	2026-03-11 19:54:30.965984	\N
2.2.3.002	INGRESOS DIFERIDOS LP	4	PASIVO	ACREEDORA	t	f	f	2.2.3	t	2026-03-11 19:54:30.965984	\N
2.2.3.009	OTRAS OBLIGACIONES LP	4	PASIVO	ACREEDORA	t	f	f	2.2.3	t	2026-03-11 19:54:30.965984	\N
3	PATRIMONIO	1	PATRIMONIO	ACREEDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
3.1	CAPITAL	2	PATRIMONIO	ACREEDORA	f	f	f	3	t	2026-03-11 19:54:30.965984	\N
3.1.1	CAPITAL SOCIAL	3	PATRIMONIO	ACREEDORA	f	f	f	3.1	t	2026-03-11 19:54:30.965984	\N
3.1.1.001	CAPITAL PAGADO	4	PATRIMONIO	ACREEDORA	t	f	f	3.1.1	t	2026-03-11 19:54:30.965984	\N
3.1.1.002	CAPITAL SUSCRITO POR PAGAR	4	PATRIMONIO	ACREEDORA	t	f	f	3.1.1	t	2026-03-11 19:54:30.965984	\N
3.1.2	APORTES NO CAPITALIZADOS	3	PATRIMONIO	ACREEDORA	f	f	f	3.1	t	2026-03-11 19:54:30.965984	\N
3.1.2.001	APORTES PARA FUTUROS AUMENTOS DE CAPITAL	4	PATRIMONIO	ACREEDORA	t	f	f	3.1.2	t	2026-03-11 19:54:30.965984	\N
3.1.2.002	PRIMAS DE EMISION	4	PATRIMONIO	ACREEDORA	t	f	f	3.1.2	t	2026-03-11 19:54:30.965984	\N
3.2	RESERVAS	2	PATRIMONIO	ACREEDORA	f	f	f	3	t	2026-03-11 19:54:30.965984	\N
3.2.1	RESERVAS LEGALES Y ESTATUTARIAS	3	PATRIMONIO	ACREEDORA	f	f	f	3.2	t	2026-03-11 19:54:30.965984	\N
3.2.1.001	RESERVA LEGAL	4	PATRIMONIO	ACREEDORA	t	f	f	3.2.1	t	2026-03-11 19:54:30.965984	\N
3.2.1.002	RESERVA ESTATUTARIA	4	PATRIMONIO	ACREEDORA	t	f	f	3.2.1	t	2026-03-11 19:54:30.965984	\N
3.2.1.003	RESERVA VOLUNTARIA	4	PATRIMONIO	ACREEDORA	t	f	f	3.2.1	t	2026-03-11 19:54:30.965984	\N
3.2.2	AJUSTES AL PATRIMONIO	3	PATRIMONIO	ACREEDORA	f	f	f	3.2	t	2026-03-11 19:54:30.965984	\N
3.2.2.001	AJUSTE POR MANTENIMIENTO DE VALOR	4	PATRIMONIO	ACREEDORA	t	f	f	3.2.2	t	2026-03-11 19:54:30.965984	\N
3.2.2.002	AJUSTE POR REVALORIZACION DE ACTIVOS	4	PATRIMONIO	ACREEDORA	t	f	f	3.2.2	t	2026-03-11 19:54:30.965984	\N
3.2.2.003	DIFERENCIA EN CONVERSION DE MONEDA EXTRANJERA	4	PATRIMONIO	ACREEDORA	t	f	f	3.2.2	t	2026-03-11 19:54:30.965984	\N
3.3	RESULTADOS	2	PATRIMONIO	ACREEDORA	f	f	f	3	t	2026-03-11 19:54:30.965984	\N
3.3.1	RESULTADOS ACUMULADOS	3	PATRIMONIO	ACREEDORA	f	f	f	3.3	t	2026-03-11 19:54:30.965984	\N
3.3.1.001	UTILIDADES ACUMULADAS	4	PATRIMONIO	ACREEDORA	t	f	f	3.3.1	t	2026-03-11 19:54:30.965984	\N
3.3.1.002	PERDIDAS ACUMULADAS	4	PATRIMONIO	ACREEDORA	t	f	f	3.3.1	t	2026-03-11 19:54:30.965984	\N
3.3.2	RESULTADO DE LA GESTION	3	PATRIMONIO	ACREEDORA	f	f	f	3.3	t	2026-03-11 19:54:30.965984	\N
3.3.2.001	UTILIDAD DE LA GESTION	4	PATRIMONIO	ACREEDORA	t	f	f	3.3.2	t	2026-03-11 19:54:30.965984	\N
3.3.2.002	PERDIDA DE LA GESTION	4	PATRIMONIO	ACREEDORA	t	f	f	3.3.2	t	2026-03-11 19:54:30.965984	\N
4	INGRESOS	1	INGRESO	ACREEDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
4.1	INGRESOS OPERATIVOS	2	INGRESO	ACREEDORA	f	f	f	4	t	2026-03-11 19:54:30.965984	\N
4.1.1	VENTAS	3	INGRESO	ACREEDORA	f	f	f	4.1	t	2026-03-11 19:54:30.965984	\N
4.1.1.001	VENTAS DE MERCANCIAS	4	INGRESO	ACREEDORA	t	f	f	4.1.1	t	2026-03-11 19:54:30.965984	\N
4.1.1.002	VENTAS DE SERVICIOS	4	INGRESO	ACREEDORA	t	f	f	4.1.1	t	2026-03-11 19:54:30.965984	\N
4.1.1.003	VENTAS DE PRODUCTOS ELABORADOS	4	INGRESO	ACREEDORA	t	f	f	4.1.1	t	2026-03-11 19:54:30.965984	\N
4.1.1.004	VENTAS DE BIENES INMUEBLES	4	INGRESO	ACREEDORA	t	f	f	4.1.1	t	2026-03-11 19:54:30.965984	\N
4.1.1.009	OTRAS VENTAS	4	INGRESO	ACREEDORA	t	f	f	4.1.1	t	2026-03-11 19:54:30.965984	\N
4.1.2	DEVOLUCIONES Y DESCUENTOS EN VENTAS	3	INGRESO	ACREEDORA	f	f	f	4.1	t	2026-03-11 19:54:30.965984	\N
4.1.2.001	DEVOLUCIONES EN VENTAS	4	INGRESO	ACREEDORA	t	f	f	4.1.2	t	2026-03-11 19:54:30.965984	\N
4.1.2.002	DESCUENTOS EN VENTAS	4	INGRESO	ACREEDORA	t	f	f	4.1.2	t	2026-03-11 19:54:30.965984	\N
4.1.2.003	REBAJAS EN VENTAS	4	INGRESO	ACREEDORA	t	f	f	4.1.2	t	2026-03-11 19:54:30.965984	\N
4.2	INGRESOS NO OPERATIVOS	2	INGRESO	ACREEDORA	f	f	f	4	t	2026-03-11 19:54:30.965984	\N
4.2.1	INGRESOS FINANCIEROS	3	INGRESO	ACREEDORA	f	f	f	4.2	t	2026-03-11 19:54:30.965984	\N
4.2.1.001	INTERESES GANADOS	4	INGRESO	ACREEDORA	t	f	f	4.2.1	t	2026-03-11 19:54:30.965984	\N
4.2.1.002	DIVIDENDOS GANADOS	4	INGRESO	ACREEDORA	t	f	f	4.2.1	t	2026-03-11 19:54:30.965984	\N
4.2.1.003	DIFERENCIA DE CAMBIO FAVORABLE	4	INGRESO	ACREEDORA	t	f	f	4.2.1	t	2026-03-11 19:54:30.965984	\N
4.2.1.004	MANTENIMIENTO DE VALOR FAVORABLE	4	INGRESO	ACREEDORA	t	f	f	4.2.1	t	2026-03-11 19:54:30.965984	\N
4.2.1.009	OTROS INGRESOS FINANCIEROS	4	INGRESO	ACREEDORA	t	f	f	4.2.1	t	2026-03-11 19:54:30.965984	\N
4.2.2	OTROS INGRESOS	3	INGRESO	ACREEDORA	f	f	f	4.2	t	2026-03-11 19:54:30.965984	\N
4.2.2.001	ALQUILERES GANADOS	4	INGRESO	ACREEDORA	t	f	f	4.2.2	t	2026-03-11 19:54:30.965984	\N
4.2.2.002	COMISIONES GANADAS	4	INGRESO	ACREEDORA	t	f	f	4.2.2	t	2026-03-11 19:54:30.965984	\N
4.2.2.003	UTILIDAD EN VENTA DE ACTIVOS FIJOS	4	INGRESO	ACREEDORA	t	f	f	4.2.2	t	2026-03-11 19:54:30.965984	\N
4.2.2.004	UTILIDAD EN VENTA DE INVERSIONES	4	INGRESO	ACREEDORA	t	f	f	4.2.2	t	2026-03-11 19:54:30.965984	\N
4.2.2.005	RECUPERACION DE CUENTAS INCOBRABLES	4	INGRESO	ACREEDORA	t	f	f	4.2.2	t	2026-03-11 19:54:30.965984	\N
4.2.2.006	INGRESOS POR SUBVENCIONES	4	INGRESO	ACREEDORA	t	f	f	4.2.2	t	2026-03-11 19:54:30.965984	\N
4.2.2.009	OTROS INGRESOS DIVERSOS	4	INGRESO	ACREEDORA	t	f	f	4.2.2	t	2026-03-11 19:54:30.965984	\N
5	COSTOS	1	COSTO	DEUDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
5.1	COSTO DE VENTAS	2	COSTO	DEUDORA	f	f	f	5	t	2026-03-11 19:54:30.965984	\N
5.1.1	COSTO DE MERCANCIAS VENDIDAS	3	COSTO	DEUDORA	f	f	f	5.1	t	2026-03-11 19:54:30.965984	\N
5.1.1.001	COSTO DE MERCANCIAS VENDIDAS	4	COSTO	DEUDORA	t	f	f	5.1.1	t	2026-03-11 19:54:30.965984	\N
5.1.1.002	COSTO DE SERVICIOS PRESTADOS	4	COSTO	DEUDORA	t	f	f	5.1.1	t	2026-03-11 19:54:30.965984	\N
5.1.1.003	COSTO DE PRODUCTOS ELABORADOS VENDIDOS	4	COSTO	DEUDORA	t	f	f	5.1.1	t	2026-03-11 19:54:30.965984	\N
5.1.1.004	COSTO DE BIENES INMUEBLES VENDIDOS	4	COSTO	DEUDORA	t	f	f	5.1.1	t	2026-03-11 19:54:30.965984	\N
5.1.2	COMPRAS	3	COSTO	DEUDORA	f	f	f	5.1	t	2026-03-11 19:54:30.965984	\N
5.1.2.001	COMPRAS DE MERCANCIAS	4	COSTO	DEUDORA	t	t	f	5.1.2	t	2026-03-11 19:54:30.965984	\N
5.1.2.002	FLETES Y ACARREOS EN COMPRAS	4	COSTO	DEUDORA	t	f	f	5.1.2	t	2026-03-11 19:54:30.965984	\N
5.1.2.003	SEGUROS EN COMPRAS	4	COSTO	DEUDORA	t	f	f	5.1.2	t	2026-03-11 19:54:30.965984	\N
5.1.2.004	DEVOLUCIONES EN COMPRAS	4	COSTO	DEUDORA	t	f	f	5.1.2	t	2026-03-11 19:54:30.965984	\N
5.1.2.005	DESCUENTOS EN COMPRAS	4	COSTO	DEUDORA	t	f	f	5.1.2	t	2026-03-11 19:54:30.965984	\N
6	GASTOS	1	GASTO	DEUDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
6.1	GASTOS OPERATIVOS	2	GASTO	DEUDORA	f	f	f	6	t	2026-03-11 19:54:30.965984	\N
6.1.1	GASTOS DE ADMINISTRACION	3	GASTO	DEUDORA	f	f	f	6.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.001	SUELDOS Y SALARIOS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.002	AGUINALDO	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.003	VACACIONES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.004	INDEMNIZACIONES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.005	APORTES PATRONALES AFP	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.006	APORTES PATRONALES CNS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.007	APORTES PRO-VIVIENDA	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.008	ALQUILERES	4	GASTO	DEUDORA	t	t	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.009	SERVICIOS BASICOS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.010	COMUNICACIONES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.011	MATERIALES DE OFICINA Y ESCRITORIO	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.012	MATERIALES DE LIMPIEZA	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.013	SEGUROS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.014	MANTENIMIENTO Y REPARACIONES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.015	DEPRECIACION DE ACTIVOS FIJOS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.016	AMORTIZACION DE ACTIVOS INTANGIBLES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.017	HONORARIOS PROFESIONALES	4	GASTO	DEUDORA	t	t	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.018	GASTOS DE REPRESENTACION	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.019	GASTOS DE VIAJE	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.020	CAPACITACION Y FORMACION	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.021	PUBLICIDAD Y PROPAGANDA	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.022	GASTOS LEGALES Y NOTARIALES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.023	IMPUESTOS Y TASAS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.024	MULTAS Y SANCIONES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.025	PROVISIONES PARA CUENTAS INCOBRABLES	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.026	PERDIDA EN BAJA DE ACTIVOS FIJOS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.027	PERDIDA EN VENTA DE ACTIVOS FIJOS	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.028	GASTOS DE CONSTITUCION Y ORGANIZACION	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.1.029	OTROS GASTOS DE ADMINISTRACION	4	GASTO	DEUDORA	t	f	t	6.1.1	t	2026-03-11 19:54:30.965984	\N
6.1.2	GASTOS DE COMERCIALIZACION	3	GASTO	DEUDORA	f	f	f	6.1	t	2026-03-11 19:54:30.965984	\N
6.1.2.001	SUELDOS Y SALARIOS - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.002	AGUINALDO - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.003	VACACIONES - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.004	INDEMNIZACIONES - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.005	APORTES PATRONALES AFP - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.006	APORTES PATRONALES CNS - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.007	APORTES PRO-VIVIENDA - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.008	COMISIONES SOBRE VENTAS	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.009	PUBLICIDAD Y PROPAGANDA - VENTAS	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.010	TRANSPORTE Y DISTRIBUCION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.011	EMBALAJES Y MATERIALES DE VENTA	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.012	SERVICIOS BASICOS - COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.013	MANTENIMIENTO Y REPARACIONES - VENTAS	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.014	DEPRECIACION DE ACTIVOS - VENTAS	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.015	HONORARIOS PROFESIONALES - VENTAS	4	GASTO	DEUDORA	t	t	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.016	GASTOS DE REPRESENTACION - VENTAS	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.017	GASTOS DE VIAJE - VENTAS	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.018	CAPACITACION - VENTAS	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.2.019	OTROS GASTOS DE COMERCIALIZACION	4	GASTO	DEUDORA	t	f	t	6.1.2	t	2026-03-11 19:54:30.965984	\N
6.1.3	GASTOS DE PRODUCCION	3	GASTO	DEUDORA	f	f	f	6.1	t	2026-03-11 19:54:30.965984	\N
6.1.3.001	SUELDOS Y SALARIOS - PRODUCCION	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.002	AGUINALDO - PRODUCCION	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.003	APORTES PATRONALES AFP - PRODUCCION	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.004	APORTES PATRONALES CNS - PRODUCCION	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.005	MATERIAS PRIMAS UTILIZADAS	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.006	MATERIALES DIRECTOS	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.007	ENERGIA ELECTRICA - PRODUCCION	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.008	DEPRECIACION DE ACTIVOS - PRODUCCION	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.009	MANTENIMIENTO DE MAQUINARIA	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.1.3.019	OTROS GASTOS DE PRODUCCION	4	GASTO	DEUDORA	t	f	t	6.1.3	t	2026-03-11 19:54:30.965984	\N
6.2	GASTOS NO OPERATIVOS	2	GASTO	DEUDORA	f	f	f	6	t	2026-03-11 19:54:30.965984	\N
6.2.1	GASTOS FINANCIEROS	3	GASTO	DEUDORA	f	f	f	6.2	t	2026-03-11 19:54:30.965984	\N
6.2.1.001	INTERESES PAGADOS	4	GASTO	DEUDORA	t	t	f	6.2.1	t	2026-03-11 19:54:30.965984	\N
6.2.1.002	COMISIONES BANCARIAS	4	GASTO	DEUDORA	t	f	f	6.2.1	t	2026-03-11 19:54:30.965984	\N
6.2.1.003	DIFERENCIA DE CAMBIO DESFAVORABLE	4	GASTO	DEUDORA	t	f	f	6.2.1	t	2026-03-11 19:54:30.965984	\N
6.2.1.004	MANTENIMIENTO DE VALOR DESFAVORABLE	4	GASTO	DEUDORA	t	f	f	6.2.1	t	2026-03-11 19:54:30.965984	\N
6.2.1.005	GASTOS DE EMISION Y MANTENIMIENTO DE DEUDA	4	GASTO	DEUDORA	t	f	f	6.2.1	t	2026-03-11 19:54:30.965984	\N
6.2.1.006	CARGOS POR ARRENDAMIENTO FINANCIERO	4	GASTO	DEUDORA	t	f	f	6.2.1	t	2026-03-11 19:54:30.965984	\N
6.2.1.009	OTROS GASTOS FINANCIEROS	4	GASTO	DEUDORA	t	f	f	6.2.1	t	2026-03-11 19:54:30.965984	\N
6.2.2	OTROS GASTOS NO OPERATIVOS	3	GASTO	DEUDORA	f	f	f	6.2	t	2026-03-11 19:54:30.965984	\N
6.2.2.001	MULTAS Y SANCIONES FISCALES	4	GASTO	DEUDORA	t	f	f	6.2.2	t	2026-03-11 19:54:30.965984	\N
6.2.2.002	PERDIDAS DIVERSAS	4	GASTO	DEUDORA	t	f	f	6.2.2	t	2026-03-11 19:54:30.965984	\N
6.2.2.003	PERDIDA EN VENTA DE INVERSIONES	4	GASTO	DEUDORA	t	f	f	6.2.2	t	2026-03-11 19:54:30.965984	\N
6.2.2.004	PERDIDA POR SINIESTROS	4	GASTO	DEUDORA	t	f	f	6.2.2	t	2026-03-11 19:54:30.965984	\N
6.2.2.005	DONACIONES Y LIBERALIDADES	4	GASTO	DEUDORA	t	f	f	6.2.2	t	2026-03-11 19:54:30.965984	\N
6.2.2.009	OTROS GASTOS DIVERSOS	4	GASTO	DEUDORA	t	f	f	6.2.2	t	2026-03-11 19:54:30.965984	\N
7	CUENTAS DE ORDEN DEUDORAS	1	ACTIVO	DEUDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
7.1	GARANTIAS OTORGADAS	2	ACTIVO	DEUDORA	f	f	f	7	t	2026-03-11 19:54:30.965984	\N
7.1.1	GARANTIAS OTORGADAS	3	ACTIVO	DEUDORA	f	f	f	7.1	t	2026-03-11 19:54:30.965984	\N
7.1.1.001	GARANTIAS EN VALORES	4	ACTIVO	DEUDORA	t	f	f	7.1.1	t	2026-03-11 19:54:30.965984	\N
7.1.1.002	GARANTIAS EN BIENES	4	ACTIVO	DEUDORA	t	f	f	7.1.1	t	2026-03-11 19:54:30.965984	\N
7.1.1.009	OTRAS GARANTIAS OTORGADAS	4	ACTIVO	DEUDORA	t	f	f	7.1.1	t	2026-03-11 19:54:30.965984	\N
8	CUENTAS DE ORDEN ACREEDORAS	1	PASIVO	ACREEDORA	f	f	f	\N	t	2026-03-11 19:54:30.965984	\N
8.1	GARANTIAS RECIBIDAS	2	PASIVO	ACREEDORA	f	f	f	8	t	2026-03-11 19:54:30.965984	\N
8.1.1	GARANTIAS RECIBIDAS	3	PASIVO	ACREEDORA	f	f	f	8.1	t	2026-03-11 19:54:30.965984	\N
8.1.1.001	GARANTIAS RECIBIDAS EN VALORES	4	PASIVO	ACREEDORA	t	f	f	8.1.1	t	2026-03-11 19:54:30.965984	\N
8.1.1.002	GARANTIAS RECIBIDAS EN BIENES	4	PASIVO	ACREEDORA	t	f	f	8.1.1	t	2026-03-11 19:54:30.965984	\N
8.1.1.009	OTRAS GARANTIAS RECIBIDAS	4	PASIVO	ACREEDORA	t	f	f	8.1.1	t	2026-03-11 19:54:30.965984	\N
\.


--
-- Data for Name: cuenta_bancaria; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.cuenta_bancaria (id, auxiliar_id, nombre_banco, numero_cuenta, moneda_codigo, cuenta_contable_codigo, titular, activo, creado_en, actualizado_en) FROM stdin;
1	4	BANCO UNION	1000000001	BOB	1.1.1.002	EMPRESA DEMO S.R.L.	t	2026-03-17 01:39:37.890536	\N
2	4	BANCO UNION	1000000002	USD	1.1.1.002	EMPRESA DEMO S.R.L.	t	2026-03-17 01:39:37.890536	\N
3	5	BANCO BISA	2000000001	BOB	1.1.1.002	EMPRESA DEMO S.R.L.	t	2026-03-17 01:39:37.890536	\N
4	5	BANCO BISA	2000000002	USD	1.1.1.002	EMPRESA DEMO S.R.L.	t	2026-03-17 01:39:37.890536	\N
5	6	BANCO MERCANTIL SANTA CRUZ	3000000001	BOB	1.1.1.002	EMPRESA DEMO S.R.L.	t	2026-03-17 01:39:37.890536	\N
6	6	BANCO MERCANTIL SANTA CRUZ	3000000002	USD	1.1.1.002	EMPRESA DEMO S.R.L.	t	2026-03-17 01:39:37.890536	\N
\.


--
-- Data for Name: documento_asiento; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.documento_asiento (id, modulo, tabla_origen, origen_id, asiento_id, creado_en) FROM stdin;
1	TESORERIA	contabilidad.pago	1	1	2026-03-17 02:17:39.692519
2	TESORERIA	contabilidad.pago	2	2	2026-03-17 21:03:45.571664
3	TESORERIA	contabilidad.pago	3	3	2026-03-17 21:16:12.318642
4	TESORERIA	contabilidad.cobro	1	4	2026-03-18 01:20:34.128705
5	TESORERIA	contabilidad.cobro	6	5	2026-03-24 00:32:43.836144
6	TESORERIA	contabilidad.cobro	7	6	2026-03-24 00:33:40.77899
7	TESORERIA	contabilidad.cobro	8	7	2026-03-24 16:27:54.467671
\.


--
-- Data for Name: esquema_backup_catalogo; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.esquema_backup_catalogo (id, gestion_origen, gestion_destino, tipo_respaldo, estado, nombre_archivo, ruta_archivo, hash_archivo, tamanio_bytes, usuario_id, usuario_nombre, fecha_generacion, observacion, detalle_json, creado_en) FROM stdin;
5	2027	\N	MANUAL	GENERADO	contabilidad_20260331_013923.sql	F:\\laragon\\www\\dxt-conta\\var\\backups_contabilidad\\contabilidad_20260331_013923.sql	\N	\N	36	AUGUSTO CAMACHO MENESES	2026-03-31 01:39:26.883281	\N	{"origen": "UI", "alcance": "schema_contabilidad"}	2026-03-31 01:39:26.883281
6	2027	\N	MANUAL	GENERADO	contabilidad_20260331_021223.sql	F:\\laragon\\www\\dxt-conta\\var\\backups_contabilidad\\contabilidad_20260331_021223.sql	\N	\N	36	AUGUSTO CAMACHO MENESES	2026-03-31 02:12:25.557997	\N	{"origen": "UI", "alcance": "schema_contabilidad"}	2026-03-31 02:12:25.557997
\.


--
-- Data for Name: esquema_restauracion_log; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.esquema_restauracion_log (id, backup_id, estado, gestion_origen, gestion_destino, usuario_id, usuario_nombre, motivo, detalle_json, fecha_hora_inicio, fecha_hora_fin, creado_en) FROM stdin;
\.


--
-- Data for Name: factura_aplicacion; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.factura_aplicacion (id, factura_electronica_id, venta_id, cobro_id, monto_aplicado, estado_resultante, creado_en) FROM stdin;
2	7	\N	6	100.00	\N	2026-03-24 00:32:43.778017
3	7	\N	7	5000.00	\N	2026-03-24 00:33:40.604551
4	7	\N	8	1860.00	\N	2026-03-24 16:27:54.386624
\.


--
-- Data for Name: factura_electronica; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.factura_electronica (id, origen, codigo_externo, cliente_auxiliar_id, cliente_empresa_id, nit_cliente, nombre_cliente, numero_factura, cuf, fecha_emision, moneda_codigo, subtotal, descuento, importe_total, saldo_pendiente, estado, payload, creado_en, actualizado_en) FROM stdin;
1	EXTERNO	EE8C97E25CD6C75D18774B1F83F09A5F9A4FE92072621E9BDCC8AF74	\N	\N	1020505029	BOLSA BOLIVIANA DE VALORES S.A.	80	EE8C97E25CD6C75D18774B1F83F09A5F9A4FE92072621E9BDCC8AF74	2026-02-06	BOB	2800.00	0.00	2800.00	2800.00	RECIBIDA	{"raw": {"columna_1": "1", "columna_2": "Casa Matriz Dxt Mag SRL", "columna_3": "06/02/2026", "columna_4": "80", "columna_5": "EE8C97E25CD6C75D18774B1F83F09A5F9A4FE92072621E9BDCC8AF74", "columna_6": "Recepcionada", "columna_7": "1020505029", "columna_8": "BOLSA BOLIVIANA DE VALORES S.A.", "columna_9": "", "columna_10": "2800", "columna_11": "0.00", "columna_12": "0.00", "columna_13": "0.00", "columna_14": "2800", "columna_15": "0.00", "columna_16": "2,800.00", "columna_17": "364.00", "columna_18": "En Linea", "columna_19": "EFECTIVO", "columna_20": "ANA CRISTINA VICENTE MARTINEZ"}, "usuario": "ANA CRISTINA VICENTE MARTINEZ", "sucursal": "Casa Matriz Dxt Mag SRL", "file_name": "facturas_emitidas.xls", "fila_origen": 2, "metodo_pago": "EFECTIVO", "punto_venta": null, "importado_en": "2026-03-20T02:13:28.025505", "tipo_emision": "En Linea", "debito_fiscal": "364.00", "importado_por": "", "estado_archivo": "Recepcionada", "importe_base_debito": "2800.00"}	2026-03-20 02:13:28.007754	\N
5	EXTERNO	EE8C97E25CD6EF7C771F4B3C405F8587DE304AC88870BA594DF8AF74	\N	\N	99001	SAMSUNG ELECTRONICS CO LTD.	84	EE8C97E25CD6EF7C771F4B3C405F8587DE304AC88870BA594DF8AF74	2026-02-19	BOB	42339.98	0.00	42339.98	42339.98	RECIBIDA	{"raw": {"columna_1": "5", "columna_2": "Casa Matriz Dxt Mag SRL", "columna_3": "19/02/2026", "columna_4": "84", "columna_5": "EE8C97E25CD6EF7C771F4B3C405F8587DE304AC88870BA594DF8AF74", "columna_6": "Recepcionada", "columna_7": "99001", "columna_8": "SAMSUNG ELECTRONICS CO LTD.", "columna_9": "", "columna_10": "42339.98", "columna_11": "0.00", "columna_12": "0.00", "columna_13": "0.00", "columna_14": "42339.98", "columna_15": "0.00", "columna_16": "42,339.98", "columna_17": "5,504.20", "columna_18": "En Linea", "columna_19": "EFECTIVO", "columna_20": "ANA CRISTINA VICENTE MARTINEZ"}, "usuario": "ANA CRISTINA VICENTE MARTINEZ", "sucursal": "Casa Matriz Dxt Mag SRL", "file_name": "facturas_emitidas.xls", "fila_origen": 6, "metodo_pago": "EFECTIVO", "punto_venta": null, "importado_en": "2026-03-20T02:13:28.037793", "tipo_emision": "En Linea", "debito_fiscal": "5504.20", "importado_por": "", "estado_archivo": "Recepcionada", "importe_base_debito": "42339.98"}	2026-03-20 02:13:28.007754	\N
6	EXTERNO	EE8C97E25CD6EF7C86E49B7C0D19FDD6010063321870BA594DF8AF74	\N	\N	99001	SAMSUNG ELECTRONICS CO LTD.	85	EE8C97E25CD6EF7C86E49B7C0D19FDD6010063321870BA594DF8AF74	2026-02-19	BOB	10309.99	0.00	10309.99	10309.99	RECIBIDA	{"raw": {"columna_1": "6", "columna_2": "Casa Matriz Dxt Mag SRL", "columna_3": "19/02/2026", "columna_4": "85", "columna_5": "EE8C97E25CD6EF7C86E49B7C0D19FDD6010063321870BA594DF8AF74", "columna_6": "Recepcionada", "columna_7": "99001", "columna_8": "SAMSUNG ELECTRONICS CO LTD.", "columna_9": "", "columna_10": "10309.99", "columna_11": "0.00", "columna_12": "0.00", "columna_13": "0.00", "columna_14": "10309.99", "columna_15": "0.00", "columna_16": "10,309.99", "columna_17": "1,340.30", "columna_18": "En Linea", "columna_19": "EFECTIVO", "columna_20": "ANA CRISTINA VICENTE MARTINEZ"}, "usuario": "ANA CRISTINA VICENTE MARTINEZ", "sucursal": "Casa Matriz Dxt Mag SRL", "file_name": "facturas_emitidas.xls", "fila_origen": 7, "metodo_pago": "EFECTIVO", "punto_venta": null, "importado_en": "2026-03-20T02:13:28.038537", "tipo_emision": "En Linea", "debito_fiscal": "1340.30", "importado_por": "", "estado_archivo": "Recepcionada", "importe_base_debito": "10309.99"}	2026-03-20 02:13:28.007754	\N
2	EXTERNO	EE8C97E25CD6D6DA3FCFC5F614AAFB804390018A27249BFB7FD8AF74	\N	\N	1023103028	OVANDO S.A.	81	EE8C97E25CD6D6DA3FCFC5F614AAFB804390018A27249BFB7FD8AF74	2026-02-11	BOB	5568.00	0.00	5568.00	0.00	ANULADA	{"raw": {"columna_1": "2", "columna_2": "Casa Matriz Dxt Mag SRL", "columna_3": "11/02/2026", "columna_4": "81", "columna_5": "EE8C97E25CD6D6DA3FCFC5F614AAFB804390018A27249BFB7FD8AF74", "columna_6": "Anulada", "columna_7": "1023103028", "columna_8": "OVANDO S.A.", "columna_9": "", "columna_10": "5568", "columna_11": "0.00", "columna_12": "0.00", "columna_13": "0.00", "columna_14": "5568", "columna_15": "0.00", "columna_16": "5,568.00", "columna_17": "723.84", "columna_18": "En Linea", "columna_19": "EFECTIVO", "columna_20": "ANA CRISTINA VICENTE MARTINEZ"}, "usuario": "ANA CRISTINA VICENTE MARTINEZ", "sucursal": "Casa Matriz Dxt Mag SRL", "file_name": "facturas_emitidas - copia.xls", "fila_origen": 3, "metodo_pago": "EFECTIVO", "punto_venta": null, "importado_en": "2026-03-20T02:30:23.797690", "tipo_emision": "En Linea", "debito_fiscal": "723.84", "importado_por": "", "estado_archivo": "Anulada", "importe_base_debito": "5568.00"}	2026-03-20 02:13:28.007754	2026-03-20 02:30:23.792884
3	EXTERNO	EE8C97E25CD6D6DA516571FD9C02156553C019F467249BFB7FD8AF74	\N	\N	1023103028	OVANDO S.A.	82	EE8C97E25CD6D6DA516571FD9C02156553C019F467249BFB7FD8AF74	2026-02-11	BOB	5568.00	0.00	5568.00	0.00	ANULADA	{"raw": {"columna_1": "3", "columna_2": "Casa Matriz Dxt Mag SRL", "columna_3": "11/02/2026", "columna_4": "82", "columna_5": "EE8C97E25CD6D6DA516571FD9C02156553C019F467249BFB7FD8AF74", "columna_6": "Anulada", "columna_7": "1023103028", "columna_8": "OVANDO S.A.", "columna_9": "", "columna_10": "5568", "columna_11": "0.00", "columna_12": "0.00", "columna_13": "0.00", "columna_14": "5568", "columna_15": "0.00", "columna_16": "5,568.00", "columna_17": "723.84", "columna_18": "En Linea", "columna_19": "EFECTIVO", "columna_20": "ANA CRISTINA VICENTE MARTINEZ"}, "usuario": "ANA CRISTINA VICENTE MARTINEZ", "sucursal": "Casa Matriz Dxt Mag SRL", "file_name": "facturas_emitidas - copia.xls", "fila_origen": 4, "metodo_pago": "EFECTIVO", "punto_venta": null, "importado_en": "2026-03-20T02:30:23.808543", "tipo_emision": "En Linea", "debito_fiscal": "723.84", "importado_por": "", "estado_archivo": "Anulada", "importe_base_debito": "5568.00"}	2026-03-20 02:13:28.007754	2026-03-20 02:30:23.792884
4	EXTERNO	EE8C97E25CD6D6DA60B69771477A02177420325E67249BFB7FD8AF74	\N	\N	1023103028	OVANDO S.A.	83	EE8C97E25CD6D6DA60B69771477A02177420325E67249BFB7FD8AF74	2026-02-11	BOB	5568.00	0.00	5568.00	0.00	ANULADA	{"raw": {"columna_1": "4", "columna_2": "Casa Matriz Dxt Mag SRL", "columna_3": "11/02/2026", "columna_4": "83", "columna_5": "EE8C97E25CD6D6DA60B69771477A02177420325E67249BFB7FD8AF74", "columna_6": "Anulada", "columna_7": "1023103028", "columna_8": "OVANDO S.A.", "columna_9": "", "columna_10": "5568", "columna_11": "0.00", "columna_12": "0.00", "columna_13": "0.00", "columna_14": "5568", "columna_15": "0.00", "columna_16": "5,568.00", "columna_17": "723.84", "columna_18": "En Linea", "columna_19": "EFECTIVO", "columna_20": "ANA CRISTINA VICENTE MARTINEZ"}, "usuario": "ANA CRISTINA VICENTE MARTINEZ", "sucursal": "Casa Matriz Dxt Mag SRL", "file_name": "facturas_emitidas - copia.xls", "fila_origen": 5, "metodo_pago": "EFECTIVO", "punto_venta": null, "importado_en": "2026-03-20T02:30:23.809311", "tipo_emision": "En Linea", "debito_fiscal": "723.84", "importado_por": "", "estado_archivo": "Anulada", "importe_base_debito": "5568.00"}	2026-03-20 02:13:28.007754	2026-03-20 02:30:23.792884
7	EXTERNO	EE8C97E25CD6FBDE30FB70AC8C133EFEDA107B9C4752ED003C09AF74	\N	\N	1026969024	Rodaria Ltda.	86	EE8C97E25CD6FBDE30FB70AC8C133EFEDA107B9C4752ED003C09AF74	2026-02-23	BOB	6960.00	0.00	6960.00	0.00	COBRADA_TOTAL	{"raw": {"columna_1": "7", "columna_2": "Casa Matriz Dxt Mag SRL", "columna_3": "23/02/2026", "columna_4": "86", "columna_5": "EE8C97E25CD6FBDE30FB70AC8C133EFEDA107B9C4752ED003C09AF74", "columna_6": "Recepcionada", "columna_7": "1026969024", "columna_8": "Rodaria Ltda.", "columna_9": "", "columna_10": "6960", "columna_11": "0.00", "columna_12": "0.00", "columna_13": "0.00", "columna_14": "6960", "columna_15": "0.00", "columna_16": "6,960.00", "columna_17": "904.80", "columna_18": "En Linea", "columna_19": "EFECTIVO", "columna_20": "ANA CRISTINA VICENTE MARTINEZ"}, "usuario": "ANA CRISTINA VICENTE MARTINEZ", "sucursal": "Casa Matriz Dxt Mag SRL", "file_name": "facturas_emitidas.xls", "fila_origen": 8, "metodo_pago": "EFECTIVO", "punto_venta": null, "importado_en": "2026-03-20T02:13:28.039284", "tipo_emision": "En Linea", "debito_fiscal": "904.80", "importado_por": "", "estado_archivo": "Recepcionada", "importe_base_debito": "6960.00"}	2026-03-20 02:13:28.007754	2026-03-24 16:27:54.467671
\.


--
-- Data for Name: factura_regularizacion; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.factura_regularizacion (id, factura_electronica_id, tipo_regularizacion, monto, motivo, observacion, activo, creado_por, creado_en, actualizado_en, anulado_por, anulado_en) FROM stdin;
\.


--
-- Data for Name: gestion_bloqueo_critico; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.gestion_bloqueo_critico (id, tipo_proceso, estado, gestion_origen, gestion_destino, usuario_id, usuario_nombre, motivo, fecha_hora_inicio, fecha_hora_fin, token_proceso, creado_en) FROM stdin;
\.


--
-- Data for Name: gestion_configuracion; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.gestion_configuracion (id, activo, cuenta_resultado_ejercicio_codigo, glosa_cierre, glosa_apertura, generar_backup_pre_cierre, permitir_reapertura, bloquear_si_hay_borradores, bloquear_si_hay_movimientos_destino, ruta_backup_base, comando_backup, comando_restauracion, creado_en, actualizado_en) FROM stdin;
1	t	3.3.2.001	CIERRE DE GESTIÓN	APERTURA DE GESTIÓN	t	t	t	t	\N	\N	\N	2026-03-28 23:19:59.698803	2026-03-30 23:11:24.206321
\.


--
-- Data for Name: gestion_control; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.gestion_control (gestion, estado, comprobante_cierre_id, fecha_cierre, usuario_cierre_id, observacion_cierre, comprobante_apertura_id, fecha_apertura, usuario_apertura_id, observacion_apertura, fecha_ultima_reapertura, usuario_ultima_reapertura_id, observacion_ultima_reapertura, creado_en, actualizado_en) FROM stdin;
2026	ABIERTA	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-03-30 23:11:24.206321	2026-03-30 23:11:24.206321
2027	ABIERTA	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2026-03-30 23:36:37.091596	2026-03-30 23:36:37.091596
\.


--
-- Data for Name: gestion_proceso_bitacora; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.gestion_proceso_bitacora (id, tipo_proceso, estado, gestion_origen, gestion_destino, comprobante_id, backup_id, restauracion_id, usuario_id, usuario_nombre, observacion, detalle_json, fecha_hora_inicio, fecha_hora_fin, creado_en) FROM stdin;
\.


--
-- Data for Name: moneda; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.moneda (codigo, nombre, simbolo, activo) FROM stdin;
USD	Dólar estadounidense	$	t
UFV	Unidad del Fondo a la Vivienda	UFV	t
BOB	Bolivianos	Bs	t
\.


--
-- Data for Name: movimiento_tesoreria; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.movimiento_tesoreria (id, fecha, tipo_movimiento, medio_origen, caja_origen_id, banco_origen_id, medio_destino, caja_destino_id, banco_destino_id, auxiliar_id, contra_cuenta_codigo, moneda_codigo, tipo_cambio, monto, referencia, glosa, estado, asiento_id, creado_en, actualizado_en) FROM stdin;
\.


--
-- Data for Name: pago; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.pago (id, fecha, proveedor_auxiliar_id, medio_pago, contra_cuenta_codigo, caja_id, cuenta_bancaria_id, moneda_codigo, tipo_cambio, monto_total, referencia, glosa, estado, asiento_id, creado_en, actualizado_en, origen_operacion) FROM stdin;
1	2026-03-17	1	CAJA	6.1.1.008	2	\N	BOB	1.000000	3500.00	None	Pago del compromiso con el banco	CONFIRMADO	1	2026-03-17 00:22:58.149358	2026-03-17 18:51:30.787103	COMPROMISO
2	2026-03-17	22	CAJA	6.1.1.008	2	\N	BOB	1.000000	500.00	00001	alquiler de quiosco feb/2026	CONFIRMADO	2	2026-03-17 21:03:18.214286	2026-03-17 21:03:45.571664	DIRECTO
3	2026-03-17	1	BANCO	6.1.1.008	\N	3	BOB	1.000000	3500.00	5342	ALQUILER DE OFICINA FEB/2026	CONFIRMADO	3	2026-03-17 21:15:42.208437	2026-03-17 21:16:12.318642	COMPROMISO
\.


--
-- Data for Name: pago_detalle; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.pago_detalle (id, pago_id, secuencia, tipo_linea, compromiso_detalle_id, descripcion, cantidad, precio_unitario, subtotal, observacion, creado_en, actualizado_en) FROM stdin;
1	1	1	COMPROMISO	6	Compromiso 00001 - PRUEBA TES - ALQUILER OFICINA CENTRAL - 10/02/2026	1.0000	3500.00	3500.00	Compromiso 00001 · PRUEBA TES - ALQUILER OFICINA CENTRAL	2026-03-17 18:51:30.787103	2026-03-17 18:51:30.787103
3	3	1	COMPROMISO	5	Compromiso 00001 - PRUEBA TES - ALQUILER OFICINA CENTRAL - 10/01/2026	1.0000	3500.00	3500.00	Cuota 1 de 6	2026-03-17 21:16:12.25966	2026-03-17 21:16:12.25966
\.


--
-- Data for Name: sistema_control_sesion; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.sistema_control_sesion (id, forzar_relogin_desde, actualizado_en, actualizado_por) FROM stdin;
1	\N	2026-03-31 00:32:02.481234	\N
\.


--
-- Data for Name: tipo_cambio; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.tipo_cambio (fecha, usd_paralelo, ufv, registrado_por, registrado_en, actualizado_por, actualizado_en) FROM stdin;
2026-03-11	6.9600	4.235568	AUGUSTO CAMACHO MENESES	2026-03-11 17:06:33.680215	\N	\N
2026-03-13	6.9600	2.458750	AUGUSTO CAMACHO MENESES	2026-03-13 16:14:49.170367	\N	\N
2026-03-16	6.9600	2.456840	AUGUSTO CAMACHO MENESES	2026-03-16 18:49:02.987142	\N	\N
2026-03-17	6.9700	2.458400	AUGUSTO CAMACHO MENESES	2026-03-17 00:19:44.977388	\N	\N
2026-03-31	5.9600	2.568940	AUGUSTO CAMACHO MENESES	2026-03-18 00:46:12.645703	AUGUSTO CAMACHO MENESES	2026-03-18 00:46:21.097997
2026-03-18	6.9600	2.568847	AUGUSTO CAMACHO MENESES	2026-03-18 02:58:40.829356	\N	\N
2026-03-19	6.9600	2.567410	AUGUSTO CAMACHO MENESES	2026-03-19 00:04:37.120895	\N	\N
2026-03-20	5.9600	2.568400	AUGUSTO CAMACHO MENESES	2026-03-20 01:26:30.668284	\N	\N
2026-03-23	6.9600	2.587400	AUGUSTO CAMACHO MENESES	2026-03-23 15:24:31.450272	\N	\N
2026-03-24	6.9600	2.123450	AUGUSTO CAMACHO MENESES	2026-03-24 00:00:36.105323	\N	\N
2026-03-25	6.9600	2.458740	AUGUSTO CAMACHO MENESES	2026-03-25 22:45:34.437112	\N	\N
2026-03-26	6.9600	2.598400	AUGUSTO CAMACHO MENESES	2026-03-26 00:40:33.384265	\N	\N
2026-03-28	6.9600	2.452550	AUGUSTO CAMACHO MENESES	2026-03-28 18:02:12.606792	\N	\N
2026-03-29	6.9600	2.456780	AUGUSTO CAMACHO MENESES	2026-03-29 22:36:17.369644	\N	\N
2026-03-27	2.9600	2.564740	AUGUSTO CAMACHO MENESES	2026-03-30 16:53:54.333129	\N	\N
2026-03-30	6.9600	2.456210	AUGUSTO CAMACHO MENESES	2026-03-30 23:11:41.561011	\N	\N
\.


--
-- Data for Name: venta; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.venta (id, fecha, cliente_auxiliar_id, cliente_empresa_id, tipo_venta, origen_documento, factura_electronica_id, numero_factura_ext, nit_cliente, nombre_cliente, glosa, moneda_codigo, tipo_cambio, subtotal, impuestos, total, contra_cuenta_codigo, estado, asiento_id, creado_en, actualizado_en) FROM stdin;
\.


--
-- Data for Name: venta_detalle; Type: TABLE DATA; Schema: contabilidad; Owner: -
--

COPY contabilidad.venta_detalle (id, venta_id, secuencia, descripcion, cantidad, precio_unitario, subtotal, cuenta_ingreso_codigo, centro_costo_id) FROM stdin;
\.


--
-- Name: _tipo_cambio_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad._tipo_cambio_id_seq', 1, false);


--
-- Name: arqueo_caja_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.arqueo_caja_id_seq', 2, true);


--
-- Name: asiento_detalle_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.asiento_detalle_id_seq', 14, true);


--
-- Name: asiento_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.asiento_id_seq', 7, true);


--
-- Name: auxiliar_cuenta_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.auxiliar_cuenta_id_seq', 2, true);


--
-- Name: auxiliar_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.auxiliar_id_seq', 26, true);


--
-- Name: caja_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.caja_id_seq', 4, true);


--
-- Name: centro_costo_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.centro_costo_id_seq', 6, true);


--
-- Name: cobro_detalle_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.cobro_detalle_id_seq', 2, true);


--
-- Name: cobro_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.cobro_id_seq', 8, true);


--
-- Name: compra_detalle_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.compra_detalle_id_seq', 1, false);


--
-- Name: compra_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.compra_id_seq', 1, false);


--
-- Name: compromiso_codigo_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.compromiso_codigo_seq', 2, true);


--
-- Name: compromiso_detalle_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.compromiso_detalle_id_seq', 36, true);


--
-- Name: compromiso_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.compromiso_id_seq', 9, true);


--
-- Name: cuenta_bancaria_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.cuenta_bancaria_id_seq', 6, true);


--
-- Name: documento_asiento_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.documento_asiento_id_seq', 7, true);


--
-- Name: esquema_backup_catalogo_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.esquema_backup_catalogo_id_seq', 1, false);


--
-- Name: esquema_backup_catalogo_id_seq1; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.esquema_backup_catalogo_id_seq1', 6, true);


--
-- Name: esquema_restauracion_log_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.esquema_restauracion_log_id_seq', 1, false);


--
-- Name: esquema_restauracion_log_id_seq1; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.esquema_restauracion_log_id_seq1', 1, false);


--
-- Name: factura_aplicacion_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.factura_aplicacion_id_seq', 4, true);


--
-- Name: factura_electronica_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.factura_electronica_id_seq', 7, true);


--
-- Name: factura_regularizacion_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.factura_regularizacion_id_seq', 1, false);


--
-- Name: gestion_bloqueo_critico_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.gestion_bloqueo_critico_id_seq', 1, false);


--
-- Name: gestion_bloqueo_critico_id_seq1; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.gestion_bloqueo_critico_id_seq1', 1, false);


--
-- Name: gestion_configuracion_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.gestion_configuracion_id_seq', 1, true);


--
-- Name: gestion_configuracion_id_seq1; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.gestion_configuracion_id_seq1', 1, false);


--
-- Name: gestion_proceso_bitacora_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.gestion_proceso_bitacora_id_seq', 1, false);


--
-- Name: gestion_proceso_bitacora_id_seq1; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.gestion_proceso_bitacora_id_seq1', 1, false);


--
-- Name: movimiento_tesoreria_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.movimiento_tesoreria_id_seq', 1, false);


--
-- Name: pago_detalle_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.pago_detalle_id_seq', 3, true);


--
-- Name: pago_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.pago_id_seq', 3, true);


--
-- Name: venta_detalle_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.venta_detalle_id_seq', 1, false);


--
-- Name: venta_id_seq; Type: SEQUENCE SET; Schema: contabilidad; Owner: -
--

SELECT pg_catalog.setval('contabilidad.venta_id_seq', 1, false);


--
-- Name: _tipo_cambio _tipo_cambio_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad._tipo_cambio
    ADD CONSTRAINT _tipo_cambio_pkey PRIMARY KEY (id);


--
-- Name: arqueo_caja arqueo_caja_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.arqueo_caja
    ADD CONSTRAINT arqueo_caja_pkey PRIMARY KEY (id);


--
-- Name: asiento_detalle asiento_detalle_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento_detalle
    ADD CONSTRAINT asiento_detalle_pkey PRIMARY KEY (id);


--
-- Name: asiento asiento_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento
    ADD CONSTRAINT asiento_pkey PRIMARY KEY (id);


--
-- Name: auxiliar_cuenta auxiliar_cuenta_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.auxiliar_cuenta
    ADD CONSTRAINT auxiliar_cuenta_pkey PRIMARY KEY (id);


--
-- Name: auxiliar auxiliar_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.auxiliar
    ADD CONSTRAINT auxiliar_pkey PRIMARY KEY (id);


--
-- Name: caja caja_codigo_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.caja
    ADD CONSTRAINT caja_codigo_key UNIQUE (codigo);


--
-- Name: caja caja_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.caja
    ADD CONSTRAINT caja_pkey PRIMARY KEY (id);


--
-- Name: centro_costo centro_costo_codigo_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.centro_costo
    ADD CONSTRAINT centro_costo_codigo_key UNIQUE (codigo);


--
-- Name: centro_costo centro_costo_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.centro_costo
    ADD CONSTRAINT centro_costo_pkey PRIMARY KEY (id);


--
-- Name: cobro cobro_asiento_id_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_asiento_id_key UNIQUE (asiento_id);


--
-- Name: cobro_detalle cobro_detalle_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro_detalle
    ADD CONSTRAINT cobro_detalle_pkey PRIMARY KEY (id);


--
-- Name: cobro cobro_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_pkey PRIMARY KEY (id);


--
-- Name: compra compra_asiento_id_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra
    ADD CONSTRAINT compra_asiento_id_key UNIQUE (asiento_id);


--
-- Name: compra_detalle compra_detalle_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra_detalle
    ADD CONSTRAINT compra_detalle_pkey PRIMARY KEY (id);


--
-- Name: compra compra_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra
    ADD CONSTRAINT compra_pkey PRIMARY KEY (id);


--
-- Name: compromiso compromiso_codigo_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compromiso
    ADD CONSTRAINT compromiso_codigo_key UNIQUE (codigo);


--
-- Name: compromiso_detalle compromiso_detalle_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compromiso_detalle
    ADD CONSTRAINT compromiso_detalle_pkey PRIMARY KEY (id);


--
-- Name: compromiso compromiso_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compromiso
    ADD CONSTRAINT compromiso_pkey PRIMARY KEY (id);


--
-- Name: cuenta_bancaria cuenta_bancaria_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta_bancaria
    ADD CONSTRAINT cuenta_bancaria_pkey PRIMARY KEY (id);


--
-- Name: cuenta cuenta_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta
    ADD CONSTRAINT cuenta_pkey PRIMARY KEY (codigo);


--
-- Name: documento_asiento documento_asiento_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.documento_asiento
    ADD CONSTRAINT documento_asiento_pkey PRIMARY KEY (id);


--
-- Name: esquema_backup_catalogo esquema_backup_catalogo_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.esquema_backup_catalogo
    ADD CONSTRAINT esquema_backup_catalogo_pkey PRIMARY KEY (id);


--
-- Name: esquema_restauracion_log esquema_restauracion_log_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.esquema_restauracion_log
    ADD CONSTRAINT esquema_restauracion_log_pkey PRIMARY KEY (id);


--
-- Name: factura_aplicacion factura_aplicacion_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_aplicacion
    ADD CONSTRAINT factura_aplicacion_pkey PRIMARY KEY (id);


--
-- Name: factura_electronica factura_electronica_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_electronica
    ADD CONSTRAINT factura_electronica_pkey PRIMARY KEY (id);


--
-- Name: factura_regularizacion factura_regularizacion_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_regularizacion
    ADD CONSTRAINT factura_regularizacion_pkey PRIMARY KEY (id);


--
-- Name: gestion_bloqueo_critico gestion_bloqueo_critico_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.gestion_bloqueo_critico
    ADD CONSTRAINT gestion_bloqueo_critico_pkey PRIMARY KEY (id);


--
-- Name: gestion_configuracion gestion_configuracion_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.gestion_configuracion
    ADD CONSTRAINT gestion_configuracion_pkey PRIMARY KEY (id);


--
-- Name: gestion_control gestion_control_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.gestion_control
    ADD CONSTRAINT gestion_control_pkey PRIMARY KEY (gestion);


--
-- Name: gestion_proceso_bitacora gestion_proceso_bitacora_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.gestion_proceso_bitacora
    ADD CONSTRAINT gestion_proceso_bitacora_pkey PRIMARY KEY (id);


--
-- Name: moneda moneda_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.moneda
    ADD CONSTRAINT moneda_pkey PRIMARY KEY (codigo);


--
-- Name: movimiento_tesoreria movimiento_tesoreria_asiento_id_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_asiento_id_key UNIQUE (asiento_id);


--
-- Name: movimiento_tesoreria movimiento_tesoreria_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_pkey PRIMARY KEY (id);


--
-- Name: pago pago_asiento_id_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_asiento_id_key UNIQUE (asiento_id);


--
-- Name: pago_detalle pago_detalle_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago_detalle
    ADD CONSTRAINT pago_detalle_pkey PRIMARY KEY (id);


--
-- Name: pago pago_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_pkey PRIMARY KEY (id);


--
-- Name: sistema_control_sesion sistema_control_sesion_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.sistema_control_sesion
    ADD CONSTRAINT sistema_control_sesion_pkey PRIMARY KEY (id);


--
-- Name: asiento_detalle uq_asiento_detalle_secuencia; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento_detalle
    ADD CONSTRAINT uq_asiento_detalle_secuencia UNIQUE (asiento_id, secuencia);


--
-- Name: auxiliar_cuenta uq_auxiliar_cuenta; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.auxiliar_cuenta
    ADD CONSTRAINT uq_auxiliar_cuenta UNIQUE (auxiliar_id, cuenta_codigo);


--
-- Name: cobro_detalle uq_cobro_detalle_secuencia; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro_detalle
    ADD CONSTRAINT uq_cobro_detalle_secuencia UNIQUE (cobro_id, secuencia);


--
-- Name: compra_detalle uq_compra_detalle_secuencia; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra_detalle
    ADD CONSTRAINT uq_compra_detalle_secuencia UNIQUE (compra_id, secuencia);


--
-- Name: cuenta_bancaria uq_cuenta_bancaria; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta_bancaria
    ADD CONSTRAINT uq_cuenta_bancaria UNIQUE (numero_cuenta);


--
-- Name: documento_asiento uq_documento_asiento; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.documento_asiento
    ADD CONSTRAINT uq_documento_asiento UNIQUE (tabla_origen, origen_id);


--
-- Name: documento_asiento uq_documento_asiento_asiento; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.documento_asiento
    ADD CONSTRAINT uq_documento_asiento_asiento UNIQUE (asiento_id);


--
-- Name: factura_electronica uq_factura_electronica; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_electronica
    ADD CONSTRAINT uq_factura_electronica UNIQUE (origen, numero_factura, fecha_emision);


--
-- Name: pago_detalle uq_pago_detalle_secuencia; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago_detalle
    ADD CONSTRAINT uq_pago_detalle_secuencia UNIQUE (pago_id, secuencia);


--
-- Name: _tipo_cambio uq_tipo_cambio; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad._tipo_cambio
    ADD CONSTRAINT uq_tipo_cambio UNIQUE (fecha, moneda_codigo);


--
-- Name: venta_detalle uq_venta_detalle_secuencia; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta_detalle
    ADD CONSTRAINT uq_venta_detalle_secuencia UNIQUE (venta_id, secuencia);


--
-- Name: venta venta_asiento_id_key; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta
    ADD CONSTRAINT venta_asiento_id_key UNIQUE (asiento_id);


--
-- Name: venta_detalle venta_detalle_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta_detalle
    ADD CONSTRAINT venta_detalle_pkey PRIMARY KEY (id);


--
-- Name: venta venta_pkey; Type: CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta
    ADD CONSTRAINT venta_pkey PRIMARY KEY (id);


--
-- Name: idx_arqueo_caja_caja; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_arqueo_caja_caja ON contabilidad.arqueo_caja USING btree (caja_id);


--
-- Name: idx_arqueo_caja_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_arqueo_caja_estado ON contabilidad.arqueo_caja USING btree (estado);


--
-- Name: idx_arqueo_caja_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_arqueo_caja_fecha ON contabilidad.arqueo_caja USING btree (fecha_arqueo DESC);


--
-- Name: idx_asiento_detalle_asiento; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_asiento_detalle_asiento ON contabilidad.asiento_detalle USING btree (asiento_id);


--
-- Name: idx_asiento_detalle_auxiliar; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_asiento_detalle_auxiliar ON contabilidad.asiento_detalle USING btree (auxiliar_id);


--
-- Name: idx_asiento_detalle_cuenta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_asiento_detalle_cuenta ON contabilidad.asiento_detalle USING btree (cuenta_codigo);


--
-- Name: idx_asiento_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_asiento_estado ON contabilidad.asiento USING btree (estado);


--
-- Name: idx_asiento_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_asiento_fecha ON contabilidad.asiento USING btree (fecha);


--
-- Name: idx_asiento_origen; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_asiento_origen ON contabilidad.asiento USING btree (modulo_origen, tabla_origen, origen_id);


--
-- Name: idx_auxiliar_activo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_auxiliar_activo ON contabilidad.auxiliar USING btree (activo);


--
-- Name: idx_auxiliar_cuenta_aux; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_auxiliar_cuenta_aux ON contabilidad.auxiliar_cuenta USING btree (auxiliar_id);


--
-- Name: idx_auxiliar_cuenta_cuenta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_auxiliar_cuenta_cuenta ON contabilidad.auxiliar_cuenta USING btree (cuenta_codigo);


--
-- Name: idx_auxiliar_nit; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_auxiliar_nit ON contabilidad.auxiliar USING btree (nit_ci);


--
-- Name: idx_auxiliar_nombre; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_auxiliar_nombre ON contabilidad.auxiliar USING btree (nombre);


--
-- Name: idx_auxiliar_ref; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_auxiliar_ref ON contabilidad.auxiliar USING btree (origen_tabla, ref_id);


--
-- Name: idx_auxiliar_tipo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_auxiliar_tipo ON contabilidad.auxiliar USING btree (tipo);


--
-- Name: idx_backup_catalogo_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_backup_catalogo_estado ON contabilidad.esquema_backup_catalogo USING btree (estado);


--
-- Name: idx_backup_catalogo_gestion; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_backup_catalogo_gestion ON contabilidad.esquema_backup_catalogo USING btree (gestion_origen, fecha_generacion DESC);


--
-- Name: idx_caja_cuenta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_caja_cuenta ON contabilidad.caja USING btree (cuenta_contable_codigo);


--
-- Name: idx_cobro_cliente; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cobro_cliente ON contabilidad.cobro USING btree (cliente_auxiliar_id);


--
-- Name: idx_cobro_detalle_cobro; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cobro_detalle_cobro ON contabilidad.cobro_detalle USING btree (cobro_id);


--
-- Name: idx_cobro_detalle_compromiso; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cobro_detalle_compromiso ON contabilidad.cobro_detalle USING btree (compromiso_detalle_id);


--
-- Name: idx_cobro_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cobro_estado ON contabilidad.cobro USING btree (estado);


--
-- Name: idx_cobro_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cobro_fecha ON contabilidad.cobro USING btree (fecha);


--
-- Name: idx_cobro_origen_operacion; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cobro_origen_operacion ON contabilidad.cobro USING btree (origen_operacion);


--
-- Name: idx_compra_detalle_compra; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compra_detalle_compra ON contabilidad.compra_detalle USING btree (compra_id);


--
-- Name: idx_compra_detalle_cuenta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compra_detalle_cuenta ON contabilidad.compra_detalle USING btree (cuenta_gasto_codigo);


--
-- Name: idx_compra_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compra_estado ON contabilidad.compra USING btree (estado);


--
-- Name: idx_compra_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compra_fecha ON contabilidad.compra USING btree (fecha);


--
-- Name: idx_compra_numero_factura; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compra_numero_factura ON contabilidad.compra USING btree (numero_factura);


--
-- Name: idx_compra_proveedor; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compra_proveedor ON contabilidad.compra USING btree (proveedor_auxiliar_id);


--
-- Name: idx_compromiso_activo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_activo ON contabilidad.compromiso USING btree (activo);


--
-- Name: idx_compromiso_auxiliar; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_auxiliar ON contabilidad.compromiso USING btree (auxiliar_id);


--
-- Name: idx_compromiso_cuenta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_cuenta ON contabilidad.compromiso USING btree (cuenta_contable);


--
-- Name: idx_compromiso_detalle_compromiso; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_detalle_compromiso ON contabilidad.compromiso_detalle USING btree (compromiso_id);


--
-- Name: idx_compromiso_detalle_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_detalle_estado ON contabilidad.compromiso_detalle USING btree (estado);


--
-- Name: idx_compromiso_detalle_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_detalle_fecha ON contabilidad.compromiso_detalle USING btree (fecha_vencimiento);


--
-- Name: idx_compromiso_detalle_pendiente_venc; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_detalle_pendiente_venc ON contabilidad.compromiso_detalle USING btree (estado, fecha_vencimiento);


--
-- Name: idx_compromiso_gestion; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_gestion ON contabilidad.compromiso USING btree (gestion);


--
-- Name: idx_compromiso_tipo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_compromiso_tipo ON contabilidad.compromiso USING btree (tipo);


--
-- Name: idx_cuenta_activo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cuenta_activo ON contabilidad.cuenta USING btree (activo);


--
-- Name: idx_cuenta_bancaria_aux; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cuenta_bancaria_aux ON contabilidad.cuenta_bancaria USING btree (auxiliar_id);


--
-- Name: idx_cuenta_bancaria_cuenta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cuenta_bancaria_cuenta ON contabilidad.cuenta_bancaria USING btree (cuenta_contable_codigo);


--
-- Name: idx_cuenta_padre; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cuenta_padre ON contabilidad.cuenta USING btree (codigo_padre);


--
-- Name: idx_cuenta_postable; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cuenta_postable ON contabilidad.cuenta USING btree (es_postable);


--
-- Name: idx_cuenta_tipo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_cuenta_tipo ON contabilidad.cuenta USING btree (tipo);


--
-- Name: idx_documento_asiento_origen; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_documento_asiento_origen ON contabilidad.documento_asiento USING btree (tabla_origen, origen_id);


--
-- Name: idx_factura_aplicacion_cobro; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_aplicacion_cobro ON contabilidad.factura_aplicacion USING btree (cobro_id);


--
-- Name: idx_factura_aplicacion_factura; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_aplicacion_factura ON contabilidad.factura_aplicacion USING btree (factura_electronica_id);


--
-- Name: idx_factura_aplicacion_venta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_aplicacion_venta ON contabilidad.factura_aplicacion USING btree (venta_id);


--
-- Name: idx_factura_electronica_cliente_aux; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_electronica_cliente_aux ON contabilidad.factura_electronica USING btree (cliente_auxiliar_id);


--
-- Name: idx_factura_electronica_cliente_emp; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_electronica_cliente_emp ON contabilidad.factura_electronica USING btree (cliente_empresa_id);


--
-- Name: idx_factura_electronica_cobranza_cliente; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_electronica_cobranza_cliente ON contabilidad.factura_electronica USING btree (cliente_auxiliar_id, fecha_emision DESC, id DESC) WHERE ((cliente_auxiliar_id IS NOT NULL) AND (saldo_pendiente > (0)::numeric) AND (estado = ANY (ARRAY['DISPONIBLE'::contabilidad.estado_factura_ext_enum, 'COBRADA_PARCIAL'::contabilidad.estado_factura_ext_enum])));


--
-- Name: idx_factura_electronica_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_electronica_estado ON contabilidad.factura_electronica USING btree (estado);


--
-- Name: idx_factura_electronica_numero; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_electronica_numero ON contabilidad.factura_electronica USING btree (numero_factura);


--
-- Name: idx_factura_regularizacion_factura; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_regularizacion_factura ON contabilidad.factura_regularizacion USING btree (factura_electronica_id);


--
-- Name: idx_factura_regularizacion_factura_activa; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_regularizacion_factura_activa ON contabilidad.factura_regularizacion USING btree (factura_electronica_id, activo);


--
-- Name: idx_factura_regularizacion_tipo_activa; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_factura_regularizacion_tipo_activa ON contabilidad.factura_regularizacion USING btree (tipo_regularizacion, activo);


--
-- Name: idx_gbloqueo_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gbloqueo_estado ON contabilidad.gestion_bloqueo_critico USING btree (estado);


--
-- Name: idx_gbloqueo_gestion_origen; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gbloqueo_gestion_origen ON contabilidad.gestion_bloqueo_critico USING btree (gestion_origen);


--
-- Name: idx_gestion_control_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gestion_control_estado ON contabilidad.gestion_control USING btree (estado);


--
-- Name: idx_gpbitacora_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gpbitacora_estado ON contabilidad.gestion_proceso_bitacora USING btree (estado);


--
-- Name: idx_gpbitacora_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gpbitacora_fecha ON contabilidad.gestion_proceso_bitacora USING btree (fecha_hora_inicio DESC);


--
-- Name: idx_gpbitacora_gestion_destino; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gpbitacora_gestion_destino ON contabilidad.gestion_proceso_bitacora USING btree (gestion_destino);


--
-- Name: idx_gpbitacora_gestion_origen; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gpbitacora_gestion_origen ON contabilidad.gestion_proceso_bitacora USING btree (gestion_origen);


--
-- Name: idx_gpbitacora_tipo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_gpbitacora_tipo ON contabilidad.gestion_proceso_bitacora USING btree (tipo_proceso);


--
-- Name: idx_mov_tesoreria_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_mov_tesoreria_estado ON contabilidad.movimiento_tesoreria USING btree (estado);


--
-- Name: idx_mov_tesoreria_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_mov_tesoreria_fecha ON contabilidad.movimiento_tesoreria USING btree (fecha);


--
-- Name: idx_pago_detalle_compromiso; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_pago_detalle_compromiso ON contabilidad.pago_detalle USING btree (compromiso_detalle_id);


--
-- Name: idx_pago_detalle_pago; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_pago_detalle_pago ON contabilidad.pago_detalle USING btree (pago_id);


--
-- Name: idx_pago_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_pago_estado ON contabilidad.pago USING btree (estado);


--
-- Name: idx_pago_estado_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_pago_estado_fecha ON contabilidad.pago USING btree (estado, fecha);


--
-- Name: idx_pago_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_pago_fecha ON contabilidad.pago USING btree (fecha);


--
-- Name: idx_pago_origen_operacion; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_pago_origen_operacion ON contabilidad.pago USING btree (origen_operacion);


--
-- Name: idx_pago_proveedor; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_pago_proveedor ON contabilidad.pago USING btree (proveedor_auxiliar_id);


--
-- Name: idx_restauracion_backup; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_restauracion_backup ON contabilidad.esquema_restauracion_log USING btree (backup_id);


--
-- Name: idx_restauracion_gestion; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_restauracion_gestion ON contabilidad.esquema_restauracion_log USING btree (gestion_origen, fecha_hora_inicio DESC);


--
-- Name: idx_venta_cliente_aux; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_venta_cliente_aux ON contabilidad.venta USING btree (cliente_auxiliar_id);


--
-- Name: idx_venta_cliente_emp; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_venta_cliente_emp ON contabilidad.venta USING btree (cliente_empresa_id);


--
-- Name: idx_venta_detalle_cuenta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_venta_detalle_cuenta ON contabilidad.venta_detalle USING btree (cuenta_ingreso_codigo);


--
-- Name: idx_venta_detalle_venta; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_venta_detalle_venta ON contabilidad.venta_detalle USING btree (venta_id);


--
-- Name: idx_venta_estado; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_venta_estado ON contabilidad.venta USING btree (estado);


--
-- Name: idx_venta_factura_ext; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_venta_factura_ext ON contabilidad.venta USING btree (factura_electronica_id);


--
-- Name: idx_venta_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE INDEX idx_venta_fecha ON contabilidad.venta USING btree (fecha);


--
-- Name: uq_arqueo_caja_confirmado_fecha; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_arqueo_caja_confirmado_fecha ON contabilidad.arqueo_caja USING btree (caja_id, fecha_arqueo) WHERE (estado = 'CONFIRMADO'::contabilidad.estado_generico_enum);


--
-- Name: uq_cobro_detalle_compromiso_unico; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_cobro_detalle_compromiso_unico ON contabilidad.cobro_detalle USING btree (compromiso_detalle_id) WHERE (tipo_linea = 'COMPROMISO'::contabilidad.tipo_linea_tesoreria_enum);


--
-- Name: uq_factura_aplicacion_cobro_factura; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_factura_aplicacion_cobro_factura ON contabilidad.factura_aplicacion USING btree (cobro_id, factura_electronica_id) WHERE (cobro_id IS NOT NULL);


--
-- Name: uq_factura_aplicacion_venta_factura; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_factura_aplicacion_venta_factura ON contabilidad.factura_aplicacion USING btree (venta_id, factura_electronica_id) WHERE (venta_id IS NOT NULL);


--
-- Name: uq_factura_regularizacion_cierre_manual_activo; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_factura_regularizacion_cierre_manual_activo ON contabilidad.factura_regularizacion USING btree (factura_electronica_id) WHERE ((activo = true) AND ((tipo_regularizacion)::text = 'CIERRE_MANUAL'::text));


--
-- Name: uq_gbloqueo_activo_por_gestion; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_gbloqueo_activo_por_gestion ON contabilidad.gestion_bloqueo_critico USING btree (gestion_origen) WHERE (estado = 'EN_PROCESO'::contabilidad.estado_bloqueo_critico_enum);


--
-- Name: uq_gestion_configuracion_activa_unica; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_gestion_configuracion_activa_unica ON contabilidad.gestion_configuracion USING btree (activo) WHERE (activo = true);


--
-- Name: uq_pago_detalle_compromiso_unico; Type: INDEX; Schema: contabilidad; Owner: -
--

CREATE UNIQUE INDEX uq_pago_detalle_compromiso_unico ON contabilidad.pago_detalle USING btree (compromiso_detalle_id) WHERE (tipo_linea = 'COMPROMISO'::contabilidad.tipo_linea_tesoreria_enum);


--
-- Name: arqueo_caja trg_arqueo_caja_biu; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_arqueo_caja_biu BEFORE INSERT OR UPDATE ON contabilidad.arqueo_caja FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_arqueo_caja_biu();


--
-- Name: cobro_detalle trg_cobro_detalle_aiud; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_cobro_detalle_aiud AFTER INSERT OR DELETE OR UPDATE ON contabilidad.cobro_detalle FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_cobro_detalle_aiud();


--
-- Name: cobro_detalle trg_cobro_detalle_biu; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_cobro_detalle_biu BEFORE INSERT OR UPDATE ON contabilidad.cobro_detalle FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_cobro_detalle_biu();


--
-- Name: cobro trg_cobro_estado_au; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_cobro_estado_au AFTER UPDATE OF estado ON contabilidad.cobro FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_cobro_estado_au();


--
-- Name: gestion_configuracion trg_gestion_configuracion_actualizado_en; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_gestion_configuracion_actualizado_en BEFORE UPDATE ON contabilidad.gestion_configuracion FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_set_actualizado_en();


--
-- Name: gestion_control trg_gestion_control_actualizado_en; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_gestion_control_actualizado_en BEFORE UPDATE ON contabilidad.gestion_control FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_set_actualizado_en();


--
-- Name: pago_detalle trg_pago_detalle_aiud; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_pago_detalle_aiud AFTER INSERT OR DELETE OR UPDATE ON contabilidad.pago_detalle FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_pago_detalle_aiud();


--
-- Name: pago_detalle trg_pago_detalle_biu; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_pago_detalle_biu BEFORE INSERT OR UPDATE ON contabilidad.pago_detalle FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_pago_detalle_biu();


--
-- Name: pago trg_pago_estado_au; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_pago_estado_au AFTER UPDATE OF estado ON contabilidad.pago FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_pago_estado_au();


--
-- Name: asiento_detalle trg_validar_cuenta_postable; Type: TRIGGER; Schema: contabilidad; Owner: -
--

CREATE TRIGGER trg_validar_cuenta_postable BEFORE INSERT OR UPDATE ON contabilidad.asiento_detalle FOR EACH ROW EXECUTE FUNCTION contabilidad.fn_validar_cuenta_postable();


--
-- Name: _tipo_cambio _tipo_cambio_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad._tipo_cambio
    ADD CONSTRAINT _tipo_cambio_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: asiento_detalle asiento_detalle_asiento_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento_detalle
    ADD CONSTRAINT asiento_detalle_asiento_id_fkey FOREIGN KEY (asiento_id) REFERENCES contabilidad.asiento(id) ON DELETE CASCADE;


--
-- Name: asiento_detalle asiento_detalle_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento_detalle
    ADD CONSTRAINT asiento_detalle_auxiliar_id_fkey FOREIGN KEY (auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: asiento_detalle asiento_detalle_centro_costo_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento_detalle
    ADD CONSTRAINT asiento_detalle_centro_costo_id_fkey FOREIGN KEY (centro_costo_id) REFERENCES contabilidad.centro_costo(id) ON DELETE RESTRICT;


--
-- Name: asiento_detalle asiento_detalle_cuenta_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento_detalle
    ADD CONSTRAINT asiento_detalle_cuenta_codigo_fkey FOREIGN KEY (cuenta_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: asiento asiento_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.asiento
    ADD CONSTRAINT asiento_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: auxiliar_cuenta auxiliar_cuenta_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.auxiliar_cuenta
    ADD CONSTRAINT auxiliar_cuenta_auxiliar_id_fkey FOREIGN KEY (auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE CASCADE;


--
-- Name: auxiliar_cuenta auxiliar_cuenta_cuenta_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.auxiliar_cuenta
    ADD CONSTRAINT auxiliar_cuenta_cuenta_codigo_fkey FOREIGN KEY (cuenta_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: caja caja_cuenta_contable_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.caja
    ADD CONSTRAINT caja_cuenta_contable_codigo_fkey FOREIGN KEY (cuenta_contable_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: cobro cobro_asiento_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_asiento_id_fkey FOREIGN KEY (asiento_id) REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT;


--
-- Name: cobro cobro_caja_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_caja_id_fkey FOREIGN KEY (caja_id) REFERENCES contabilidad.caja(id) ON DELETE RESTRICT;


--
-- Name: cobro cobro_cliente_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_cliente_auxiliar_id_fkey FOREIGN KEY (cliente_auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: cobro cobro_contra_cuenta_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_contra_cuenta_codigo_fkey FOREIGN KEY (contra_cuenta_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: cobro cobro_cuenta_bancaria_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_cuenta_bancaria_id_fkey FOREIGN KEY (cuenta_bancaria_id) REFERENCES contabilidad.cuenta_bancaria(id) ON DELETE RESTRICT;


--
-- Name: cobro cobro_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro
    ADD CONSTRAINT cobro_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: compra compra_asiento_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra
    ADD CONSTRAINT compra_asiento_id_fkey FOREIGN KEY (asiento_id) REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT;


--
-- Name: compra compra_contra_cuenta_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra
    ADD CONSTRAINT compra_contra_cuenta_codigo_fkey FOREIGN KEY (contra_cuenta_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: compra_detalle compra_detalle_centro_costo_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra_detalle
    ADD CONSTRAINT compra_detalle_centro_costo_id_fkey FOREIGN KEY (centro_costo_id) REFERENCES contabilidad.centro_costo(id) ON DELETE RESTRICT;


--
-- Name: compra_detalle compra_detalle_compra_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra_detalle
    ADD CONSTRAINT compra_detalle_compra_id_fkey FOREIGN KEY (compra_id) REFERENCES contabilidad.compra(id) ON DELETE CASCADE;


--
-- Name: compra_detalle compra_detalle_cuenta_gasto_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra_detalle
    ADD CONSTRAINT compra_detalle_cuenta_gasto_codigo_fkey FOREIGN KEY (cuenta_gasto_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: compra compra_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra
    ADD CONSTRAINT compra_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: compra compra_proveedor_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compra
    ADD CONSTRAINT compra_proveedor_auxiliar_id_fkey FOREIGN KEY (proveedor_auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: compromiso_detalle compromiso_detalle_compromiso_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.compromiso_detalle
    ADD CONSTRAINT compromiso_detalle_compromiso_id_fkey FOREIGN KEY (compromiso_id) REFERENCES contabilidad.compromiso(id) ON DELETE CASCADE;


--
-- Name: cuenta_bancaria cuenta_bancaria_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta_bancaria
    ADD CONSTRAINT cuenta_bancaria_auxiliar_id_fkey FOREIGN KEY (auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: cuenta_bancaria cuenta_bancaria_cuenta_contable_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta_bancaria
    ADD CONSTRAINT cuenta_bancaria_cuenta_contable_codigo_fkey FOREIGN KEY (cuenta_contable_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: cuenta_bancaria cuenta_bancaria_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta_bancaria
    ADD CONSTRAINT cuenta_bancaria_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: documento_asiento documento_asiento_asiento_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.documento_asiento
    ADD CONSTRAINT documento_asiento_asiento_id_fkey FOREIGN KEY (asiento_id) REFERENCES contabilidad.asiento(id) ON DELETE CASCADE;


--
-- Name: factura_aplicacion factura_aplicacion_cobro_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_aplicacion
    ADD CONSTRAINT factura_aplicacion_cobro_id_fkey FOREIGN KEY (cobro_id) REFERENCES contabilidad.cobro(id) ON DELETE RESTRICT;


--
-- Name: factura_aplicacion factura_aplicacion_factura_electronica_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_aplicacion
    ADD CONSTRAINT factura_aplicacion_factura_electronica_id_fkey FOREIGN KEY (factura_electronica_id) REFERENCES contabilidad.factura_electronica(id) ON DELETE CASCADE;


--
-- Name: factura_aplicacion factura_aplicacion_venta_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_aplicacion
    ADD CONSTRAINT factura_aplicacion_venta_id_fkey FOREIGN KEY (venta_id) REFERENCES contabilidad.venta(id) ON DELETE RESTRICT;


--
-- Name: factura_electronica factura_electronica_cliente_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_electronica
    ADD CONSTRAINT factura_electronica_cliente_auxiliar_id_fkey FOREIGN KEY (cliente_auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: factura_electronica factura_electronica_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_electronica
    ADD CONSTRAINT factura_electronica_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: arqueo_caja fk_arqueo_caja_caja; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.arqueo_caja
    ADD CONSTRAINT fk_arqueo_caja_caja FOREIGN KEY (caja_id) REFERENCES contabilidad.caja(id) ON DELETE RESTRICT;


--
-- Name: cobro_detalle fk_cobro_detalle_cobro; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro_detalle
    ADD CONSTRAINT fk_cobro_detalle_cobro FOREIGN KEY (cobro_id) REFERENCES contabilidad.cobro(id) ON DELETE CASCADE;


--
-- Name: cobro_detalle fk_cobro_detalle_compromiso; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cobro_detalle
    ADD CONSTRAINT fk_cobro_detalle_compromiso FOREIGN KEY (compromiso_detalle_id) REFERENCES contabilidad.compromiso_detalle(id) ON DELETE RESTRICT;


--
-- Name: cuenta fk_cuenta_padre; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.cuenta
    ADD CONSTRAINT fk_cuenta_padre FOREIGN KEY (codigo_padre) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: factura_regularizacion fk_factura_regularizacion_factura; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.factura_regularizacion
    ADD CONSTRAINT fk_factura_regularizacion_factura FOREIGN KEY (factura_electronica_id) REFERENCES contabilidad.factura_electronica(id);


--
-- Name: pago_detalle fk_pago_detalle_compromiso; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago_detalle
    ADD CONSTRAINT fk_pago_detalle_compromiso FOREIGN KEY (compromiso_detalle_id) REFERENCES contabilidad.compromiso_detalle(id) ON DELETE RESTRICT;


--
-- Name: pago_detalle fk_pago_detalle_pago; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago_detalle
    ADD CONSTRAINT fk_pago_detalle_pago FOREIGN KEY (pago_id) REFERENCES contabilidad.pago(id) ON DELETE CASCADE;


--
-- Name: esquema_restauracion_log fk_restauracion_backup; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.esquema_restauracion_log
    ADD CONSTRAINT fk_restauracion_backup FOREIGN KEY (backup_id) REFERENCES contabilidad.esquema_backup_catalogo(id);


--
-- Name: movimiento_tesoreria movimiento_tesoreria_asiento_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_asiento_id_fkey FOREIGN KEY (asiento_id) REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT;


--
-- Name: movimiento_tesoreria movimiento_tesoreria_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_auxiliar_id_fkey FOREIGN KEY (auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: movimiento_tesoreria movimiento_tesoreria_banco_destino_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_banco_destino_id_fkey FOREIGN KEY (banco_destino_id) REFERENCES contabilidad.cuenta_bancaria(id) ON DELETE RESTRICT;


--
-- Name: movimiento_tesoreria movimiento_tesoreria_banco_origen_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_banco_origen_id_fkey FOREIGN KEY (banco_origen_id) REFERENCES contabilidad.cuenta_bancaria(id) ON DELETE RESTRICT;


--
-- Name: movimiento_tesoreria movimiento_tesoreria_caja_destino_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_caja_destino_id_fkey FOREIGN KEY (caja_destino_id) REFERENCES contabilidad.caja(id) ON DELETE RESTRICT;


--
-- Name: movimiento_tesoreria movimiento_tesoreria_caja_origen_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_caja_origen_id_fkey FOREIGN KEY (caja_origen_id) REFERENCES contabilidad.caja(id) ON DELETE RESTRICT;


--
-- Name: movimiento_tesoreria movimiento_tesoreria_contra_cuenta_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_contra_cuenta_codigo_fkey FOREIGN KEY (contra_cuenta_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: movimiento_tesoreria movimiento_tesoreria_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.movimiento_tesoreria
    ADD CONSTRAINT movimiento_tesoreria_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: pago pago_asiento_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_asiento_id_fkey FOREIGN KEY (asiento_id) REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT;


--
-- Name: pago pago_caja_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_caja_id_fkey FOREIGN KEY (caja_id) REFERENCES contabilidad.caja(id) ON DELETE RESTRICT;


--
-- Name: pago pago_contra_cuenta_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_contra_cuenta_codigo_fkey FOREIGN KEY (contra_cuenta_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: pago pago_cuenta_bancaria_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_cuenta_bancaria_id_fkey FOREIGN KEY (cuenta_bancaria_id) REFERENCES contabilidad.cuenta_bancaria(id) ON DELETE RESTRICT;


--
-- Name: pago pago_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- Name: pago pago_proveedor_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.pago
    ADD CONSTRAINT pago_proveedor_auxiliar_id_fkey FOREIGN KEY (proveedor_auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: venta venta_asiento_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta
    ADD CONSTRAINT venta_asiento_id_fkey FOREIGN KEY (asiento_id) REFERENCES contabilidad.asiento(id) ON DELETE RESTRICT;


--
-- Name: venta venta_cliente_auxiliar_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta
    ADD CONSTRAINT venta_cliente_auxiliar_id_fkey FOREIGN KEY (cliente_auxiliar_id) REFERENCES contabilidad.auxiliar(id) ON DELETE RESTRICT;


--
-- Name: venta venta_contra_cuenta_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta
    ADD CONSTRAINT venta_contra_cuenta_codigo_fkey FOREIGN KEY (contra_cuenta_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: venta_detalle venta_detalle_centro_costo_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta_detalle
    ADD CONSTRAINT venta_detalle_centro_costo_id_fkey FOREIGN KEY (centro_costo_id) REFERENCES contabilidad.centro_costo(id) ON DELETE RESTRICT;


--
-- Name: venta_detalle venta_detalle_cuenta_ingreso_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta_detalle
    ADD CONSTRAINT venta_detalle_cuenta_ingreso_codigo_fkey FOREIGN KEY (cuenta_ingreso_codigo) REFERENCES contabilidad.cuenta(codigo) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: venta_detalle venta_detalle_venta_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta_detalle
    ADD CONSTRAINT venta_detalle_venta_id_fkey FOREIGN KEY (venta_id) REFERENCES contabilidad.venta(id) ON DELETE CASCADE;


--
-- Name: venta venta_factura_electronica_id_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta
    ADD CONSTRAINT venta_factura_electronica_id_fkey FOREIGN KEY (factura_electronica_id) REFERENCES contabilidad.factura_electronica(id) ON DELETE RESTRICT;


--
-- Name: venta venta_moneda_codigo_fkey; Type: FK CONSTRAINT; Schema: contabilidad; Owner: -
--

ALTER TABLE ONLY contabilidad.venta
    ADD CONSTRAINT venta_moneda_codigo_fkey FOREIGN KEY (moneda_codigo) REFERENCES contabilidad.moneda(codigo);


--
-- PostgreSQL database dump complete
--

\unrestrict HGlDnf5nJeGXoli622B7IeAaRTud8K8lVzS70mkdN3QrYwU5xZVROK03gN6r2ri

