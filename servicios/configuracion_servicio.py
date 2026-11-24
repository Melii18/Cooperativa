from decimal import Decimal

from database.conexion import obtener_conexion
from utils.errores import ErrorValidacion


def obtener_valor(clave):
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT valor FROM configuracion WHERE clave = %s", (clave,))
        fila = cursor.fetchone()
    finally:
        conexion.close()
    if fila is None:
        raise ErrorValidacion(f"Falta el valor de configuración '{clave}'.")
    return fila[0]


def obtener_aporte_minimo():
    return int(obtener_valor("aporte_minimo"))


def obtener_interes_porcentaje():
    return Decimal(obtener_valor("interes_porcentaje"))


def obtener_monto_maximo_prestamo():
    return int(obtener_valor("monto_maximo_prestamo"))


def obtener_max_cuotas():
    return int(obtener_valor("max_cuotas"))