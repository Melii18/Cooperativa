import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG


def obtener_conexion():
    """Devuelve una conexion nueva a la base de datos."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        raise RuntimeError(f"No se pudo conectar a la base de datos: {e}")