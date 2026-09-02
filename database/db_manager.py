# ============================================================
# DXT CONTA - Gestor de Base de Datos
# ============================================================

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import current_app, g
from contextlib import contextmanager


class DatabaseManager:
    """
    Gestor centralizado de operaciones de base de datos
    """
    
    def __init__(self):
        """Inicializar conexión"""
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        """Context manager: entrada"""
        self.conn = psycopg2.connect(
            host=current_app.config['DB_HOST'],
            port=current_app.config['DB_PORT'],
            database=current_app.config['DB_NAME'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            options=f"-c search_path={current_app.config['DB_SCHEMA']},public"
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: salida"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
            self.conn.close()
        return False
    
    def execute_query(self, query, params=None):
        """
        Ejecutar una consulta SELECT
        
        Args:
            query (str): Consulta SQL
            params (tuple): Parámetros de la consulta
        
        Returns:
            list: Lista de diccionarios con los resultados
        """
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    def execute_insert(self, query, params=None, return_id=True):
        """
        Ejecutar un INSERT
        
        Args:
            query (str): Consulta INSERT
            params (tuple): Parámetros
            return_id (bool): Si True, devuelve el ID insertado
        
        Returns:
            int/None: ID del registro insertado o None
        """
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        self.cursor.execute(query, params)
        
        if return_id:
            self.cursor.execute('SELECT LASTVAL()')
            result = self.cursor.fetchone()
            return result['lastval'] if result else None
        return None
    
    def execute_update(self, query, params=None):
        """
        Ejecutar un UPDATE
        
        Args:
            query (str): Consulta UPDATE
            params (tuple): Parámetros
        
        Returns:
            int: Número de filas afectadas
        """
        self.cursor = self.conn.cursor()
        self.cursor.execute(query, params)
        return self.cursor.rowcount
    
    def execute_delete(self, query, params=None):
        """
        Ejecutar un DELETE
        
        Args:
            query (str): Consulta DELETE
            params (tuple): Parámetros
        
        Returns:
            int: Número de filas eliminadas
        """
        self.cursor = self.conn.cursor()
        self.cursor.execute(query, params)
        return self.cursor.rowcount
    
    @staticmethod
    def get_connection():
        """Obtener conexión a la base de datos desde el contexto de Flask"""
        if 'db' not in g:
            g.db = psycopg2.connect(
                host=current_app.config['DB_HOST'],
                port=current_app.config['DB_PORT'],
                database=current_app.config['DB_NAME'],
                user=current_app.config['DB_USER'],
                password=current_app.config['DB_PASSWORD'],
                options=f"-c search_path={current_app.config['DB_SCHEMA']},public"
            )
        return g.db
    
    @staticmethod
    @contextmanager
    def get_cursor(dict_cursor=True):
        """
        Context manager para obtener un cursor
        
        Args:
            dict_cursor (bool): Si True, devuelve RealDictCursor
        
        Yields:
            cursor: Cursor de PostgreSQL
        """
        conn = DatabaseManager.get_connection()
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    @staticmethod
    def table_exists(table_name):
        """
        Verificar si una tabla existe
        
        Args:
            table_name (str): Nombre de la tabla
        
        Returns:
            bool: True si existe, False si no
        """
        with DatabaseManager.get_cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = %s 
                    AND table_name = %s
                )
            """, (current_app.config['DB_SCHEMA'], table_name))
            result = cursor.fetchone()
            return result['exists'] if result else False
    
    @staticmethod
    def get_table_columns(table_name):
        """
        Obtener las columnas de una tabla
        
        Args:
            table_name (str): Nombre de la tabla
        
        Returns:
            list: Lista de nombres de columnas
        """
        with DatabaseManager.get_cursor() as cursor:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = %s 
                AND table_name = %s
                ORDER BY ordinal_position
            """, (current_app.config['DB_SCHEMA'], table_name))
            results = cursor.fetchall()
            return [row['column_name'] for row in results] if results else []
    
    @staticmethod
    def close_connection():
        """Cerrar la conexión de base de datos"""
        db = g.pop('db', None)
        if db is not None:
            db.close()
