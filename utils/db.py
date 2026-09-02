# ============================================================
# DXT CONTA - Utilidad de Base de Datos PostgreSQL
# ============================================================

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config

def get_db_connection():
    """
    Crea y retorna una conexión a PostgreSQL.
    
    Returns:
        connection: Objeto de conexión psycopg2
    """
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        return conn
    except psycopg2.Error as e:
        print(f"❌ Error al conectar a PostgreSQL: {e}")
        raise

def execute_query(query, params=None, fetch=False):
    """
    Ejecuta una consulta SQL que retorna múltiples resultados.
    
    Args:
        query (str): Consulta SQL
        params (tuple): Parámetros de la consulta
        fetch (bool): Si debe retornar resultados (SELECT)
        
    Returns:
        list: Lista de diccionarios con los resultados
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(query, params or ())
        
        if fetch:
            results = cursor.fetchall()
            return [dict(row) for row in results]
        else:
            conn.commit()
            return cursor.rowcount
            
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        print(f"❌ Error en consulta SQL: {e}")
        raise
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def execute_query_one(query, params=None):
    """
    Ejecuta una consulta SQL que retorna un solo resultado.
    
    Args:
        query (str): Consulta SQL
        params (tuple): Parámetros de la consulta
        
    Returns:
        dict/None: Diccionario con el resultado o None
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(query, params or ())
        result = cursor.fetchone()
        
        return dict(result) if result else None
            
    except psycopg2.Error as e:
        print(f"❌ Error en consulta SQL: {e}")
        raise
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def test_connection():
    """
    Prueba la conexión a la base de datos.
    
    Returns:
        bool: True si la conexión es exitosa
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ Conexión exitosa a PostgreSQL")
        print(f"   Versión: {version[0]}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False

def execute_query(query, params=None, fetch=False, fetchall=False):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params or ())
        
        if fetch or fetchall:          # ← acepta ambos
            results = cursor.fetchall()
            return [dict(row) for row in results]
        else:
            conn.commit()
            return cursor.rowcount
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        print(f"❌ Error en consulta SQL: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

