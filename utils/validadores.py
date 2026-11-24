import re
from datetime import date, datetime

from utils.errores import ErrorValidacion


def parsear_fecha(texto, nombre_campo="La fecha", permitir_futura=False):
    """Convierte 'DD/MM/AAAA' en un objeto date, o lanza ErrorValidacion."""
    try:
        fecha = datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        raise ErrorValidacion(f"{nombre_campo} debe tener el formato DD/MM/AAAA.")
    if fecha > date.today() and not permitir_futura:
        raise ErrorValidacion(f"{nombre_campo} no puede ser futura.")
    return fecha


def parsear_monto(texto):
    """Convierte '50.000' o '50000' en el entero 50000, o lanza ErrorValidacion."""
    limpio = re.sub(r"[.\s]", "", texto)  # quita puntos y espacios
    if not re.fullmatch(r"\d{1,12}", limpio):
        raise ErrorValidacion("El monto debe contener solo números (ej: 50000 o 50.000).")
    monto = int(limpio)
    if monto <= 0:
        raise ErrorValidacion("El monto debe ser mayor a cero.")
    return monto


def formatear_guaranies(valor):
    """50000 -> '50.000'"""
    return f"{int(valor):,}".replace(",", ".")