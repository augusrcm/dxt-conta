"""
Script para hashear las contraseñas existentes en la base de datos
"""
from werkzeug.security import generate_password_hash
import psycopg2
from config import Config

def hash_existing_passwords():
    """Hashear todas las contraseñas en texto plano"""
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        cursor = conn.cursor()
        
        # Obtener todos los usuarios
        cursor.execute("SELECT id, password FROM usuarios.usuarios")
        usuarios = cursor.fetchall()
        
        for user_id, password in usuarios:
            if password and not password.startswith('pbkdf2:'):
                # Hashear la contraseña
                hashed = generate_password_hash(password)
                cursor.execute(
                    "UPDATE usuarios.usuarios SET password = %s WHERE id = %s",
                    (hashed, user_id)
                )
                print(f"✅ Usuario ID {user_id}: Contraseña hasheada")
        
        conn.commit()
        print("\n✅ Todas las contraseñas han sido hasheadas")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    hash_existing_passwords()
