"""
Gestión de conexión a PostgreSQL
"""

import psycopg2
import psycopg2.extras
from flask import g
import os

# Configuración de la base de datos PostgreSQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'dxtsys'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'tu_password'),
    'options': '-c search_path=contabilidad,public'  # Schema contabilidad
}


def get_db():
    """
    Obtiene la conexión a PostgreSQL.
    Si no existe en el contexto de Flask (g), la crea.
    """
    if 'db' not in g:
        g.db = psycopg2.connect(**DB_CONFIG)
        g.db.autocommit = False  # Manejo manual de transacciones
    
    return g.db


def close_db(e=None):
    """
    Cierra la conexión a la base de datos al finalizar la petición.
    """
    db = g.pop('db', None)
    
    if db is not None:
        db.close()


def init_db():
    """
    Inicializa la base de datos ejecutando el schema.
    """
    db = get_db()
    cursor = db.cursor()
    
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    
    if os.path.exists(schema_path):
        with open(schema_path, 'r', encoding='utf-8') as f:
            cursor.execute(f.read())
        db.commit()
        print("✅ Base de datos inicializada correctamente")
    else:
        print("⚠️ No se encontró schema.sql")
    
    cursor.close()
