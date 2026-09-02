# ============================================================
# DXT-CONTA - Gestión de Tipo de Cambio
# ============================================================
# Funciones reutilizables para verificar y registrar tipo de cambio

from datetime import date
from .db import execute_query_one, execute_query

def verificar_tipo_cambio_fecha(fecha):
    """
    Verifica si existe tipo de cambio para una fecha específica.
    
    Args:
        fecha (date): Fecha a verificar
        
    Returns:
        bool: True si existe, False si no existe
        
    Example:
        from datetime import date
        existe = verificar_tipo_cambio_fecha(date.today())
    """
    query = """
        SELECT COUNT(*) as count 
        FROM contabilidad.tipo_cambio 
        WHERE fecha = %s
    """
    result = execute_query_one(query, (fecha,))
    return result['count'] > 0 if result else False

def obtener_tipo_cambio(fecha):
    """
    Obtiene el tipo de cambio para una fecha específica.
    
    Args:
        fecha (date): Fecha a consultar
        
    Returns:
        dict: {'usd_paralelo': float, 'ufv': float} o None si no existe
        
    Example:
        tc = obtener_tipo_cambio(date.today())
        if tc:
            print(f"USD: {tc['usd_paralelo']}, UFV: {tc['ufv']}")
    """
    query = """
        SELECT usd_paralelo, ufv, fecha
        FROM contabilidad.tipo_cambio 
        WHERE fecha = %s
    """
    return execute_query_one(query, (fecha,))

def registrar_tipo_cambio(fecha, usd_paralelo, ufv, usuario_ci):
    """
    Registra o actualiza el tipo de cambio para una fecha.
    
    Args:
        fecha (date): Fecha del tipo de cambio
        usd_paralelo (float): Tipo de cambio USD paralelo
        ufv (float): Valor UFV
        usuario_ci (str): CI del usuario que registra
        
    Returns:
        bool: True si se registró correctamente, False si hubo error
        
    Example:
        exito = registrar_tipo_cambio(
            date.today(), 
            6.96, 
            2.45678, 
            '12345678'
        )
    """
    try:
        # Verificar si ya existe
        existe = verificar_tipo_cambio_fecha(fecha)
        
        if existe:
            # Actualizar
            query = """
                UPDATE contabilidad.tipo_cambio 
                SET usd_paralelo = %s, 
                    ufv = %s,
                    actualizado_por = %s,
                    actualizado_en = NOW()
                WHERE fecha = %s
            """
            params = (usd_paralelo, ufv, usuario_ci, fecha)
        else:
            # Insertar
            query = """
                INSERT INTO contabilidad.tipo_cambio 
                (fecha, usd_paralelo, ufv, registrado_por)
                VALUES (%s, %s, %s, %s)
            """
            params = (fecha, usd_paralelo, ufv, usuario_ci)
        
        execute_query(query, params, fetch=False)
        return True
        
    except Exception as e:
        print(f"❌ Error registrando tipo de cambio: {e}")
        return False

def obtener_ultimo_tipo_cambio():
    """
    Obtiene el último tipo de cambio registrado.
    Útil para pre-llenar el formulario con valores recientes.
    
    Returns:
        dict: Último tipo de cambio o None
    """
    query = """
        SELECT usd_paralelo, ufv, fecha
        FROM contabilidad.tipo_cambio 
        ORDER BY fecha DESC 
        LIMIT 1
    """
    return execute_query_one(query)
