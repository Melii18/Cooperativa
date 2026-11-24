import re
from datetime import date, datetime

from mysql.connector import IntegrityError

from database.conexion import obtener_conexion
from servicios import historial_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorValidacion

COLUMNAS = "id, nombre, telefono, cedula, fecha_ingreso, estado"


def _validar(nombre, telefono, cedula, fecha_ingreso):
    """Limpia y valida los datos. Devuelve (nombre, telefono, cedula, fecha)."""
    nombre = " ".join(nombre.split())  # quita espacios sobrantes
    if len(nombre) < 3 or len(nombre) > 160:
        raise ErrorValidacion("El nombre debe tener entre 3 y 160 caracteres.")
    if any(c.isdigit() for c in nombre):
        raise ErrorValidacion("El nombre no puede contener números.")

    telefono = re.sub(r"[ \-()]", "", telefono)  # quita espacios, guiones y parentesis
    if not re.fullmatch(r"\+?\d{7,15}", telefono):
        raise ErrorValidacion("El teléfono no es válido. Use solo números (ej: 0981123456).")

    cedula = re.sub(r"[.\s]", "", cedula)  # quita puntos y espacios
    if cedula == "":
        cedula = None  # sin cedula: guardamos NULL, no texto vacio
    elif not re.fullmatch(r"\d{5,10}", cedula):
        raise ErrorValidacion("La cédula debe tener entre 5 y 10 números.")

    try:
        fecha = datetime.strptime(fecha_ingreso.strip(), "%d/%m/%Y").date()
    except ValueError:
        raise ErrorValidacion("La fecha de ingreso debe tener el formato DD/MM/AAAA.")
    if fecha > date.today():
        raise ErrorValidacion("La fecha de ingreso no puede ser futura.")

    return nombre, telefono, cedula, fecha


def _traducir_integridad(error):
    """Convierte el error de MySQL por duplicado en un mensaje claro."""
    texto = str(error)
    if "uq_socio_nombre_telefono" in texto:
        return ErrorValidacion("Ya existe un socio con ese nombre y teléfono.")
    if "cedula" in texto:
        return ErrorValidacion("Ya existe un socio con esa cédula.")
    return ErrorValidacion("No se pudo guardar: hay un dato duplicado.")


def listar(busqueda="", incluir_inactivos=False):
    Sesion.exigir_permiso("socios_ver")

    sql = f"SELECT {COLUMNAS} FROM socios WHERE 1 = 1"
    parametros = []
    if not incluir_inactivos:
        sql += " AND estado = 'activo'"
    busqueda = busqueda.strip()
    if busqueda:
        sql += " AND (nombre LIKE %s OR telefono LIKE %s OR cedula LIKE %s)"
        patron = f"%{busqueda}%"
        parametros += [patron, patron, patron]
    sql += " ORDER BY nombre"

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(sql, parametros)
        return cursor.fetchall()
    finally:
        conexion.close()


def obtener(socio_id):
    Sesion.exigir_permiso("socios_ver")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(f"SELECT {COLUMNAS} FROM socios WHERE id = %s", (socio_id,))
        socio = cursor.fetchone()
    finally:
        conexion.close()
    if socio is None:
        raise ErrorValidacion("El socio no existe.")
    return socio


def crear(nombre, telefono, cedula, fecha_ingreso):
    Sesion.exigir_permiso("socios_editar")
    nombre, telefono, cedula, fecha = _validar(nombre, telefono, cedula, fecha_ingreso)

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO socios (nombre, telefono, cedula, fecha_ingreso) VALUES (%s, %s, %s, %s)",
            (nombre, telefono, cedula, fecha),
        )
        nuevo_id = cursor.lastrowid
        historial_servicio.registrar(
            Sesion.id_usuario(), "CREAR_SOCIO", "socios", nuevo_id,
            f"nombre={nombre}, telefono={telefono}", cursor=cursor,
        )
        conexion.commit()
        return nuevo_id
    except IntegrityError as e:
        conexion.rollback()
        raise _traducir_integridad(e)
    finally:
        conexion.close()


def actualizar(socio_id, nombre, telefono, cedula, fecha_ingreso):
    Sesion.exigir_permiso("socios_editar")
    nombre, telefono, cedula, fecha = _validar(nombre, telefono, cedula, fecha_ingreso)

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT nombre, telefono, cedula, fecha_ingreso FROM socios WHERE id = %s",
            (socio_id,),
        )
        antes = cursor.fetchone()
        if antes is None:
            raise ErrorValidacion("El socio no existe.")

        nuevos = {"nombre": nombre, "telefono": telefono, "cedula": cedula, "fecha_ingreso": fecha}
        cambios = [
            f"{campo}: {antes[campo]} -> {valor}"
            for campo, valor in nuevos.items() if antes[campo] != valor
        ]
        if not cambios:
            return  # no se modifico nada, no hay que guardar ni registrar

        cursor.execute(
            "UPDATE socios SET nombre = %s, telefono = %s, cedula = %s, fecha_ingreso = %s "
            "WHERE id = %s",
            (nombre, telefono, cedula, fecha, socio_id),
        )
        historial_servicio.registrar(
            Sesion.id_usuario(), "EDITAR_SOCIO", "socios", socio_id,
            "; ".join(cambios), cursor=cursor,
        )
        conexion.commit()
    except IntegrityError as e:
        conexion.rollback()
        raise _traducir_integridad(e)
    finally:
        conexion.close()


def cambiar_estado(socio_id, nuevo_estado):
    Sesion.exigir_permiso("socios_editar")
    if nuevo_estado not in ("activo", "inactivo"):
        raise ErrorValidacion("Estado no válido.")

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT nombre, estado FROM socios WHERE id = %s", (socio_id,))
        socio = cursor.fetchone()
        if socio is None:
            raise ErrorValidacion("El socio no existe.")
        if socio["estado"] == nuevo_estado:
            return

        if nuevo_estado == "inactivo":
            cursor.execute(
                "SELECT COUNT(*) AS total FROM prestamos WHERE socio_id = %s AND estado = 'activo'",
                (socio_id,),
            )
            if cursor.fetchone()["total"] > 0:
                raise ErrorValidacion("No se puede dar de baja a un socio con un préstamo activo.")

        cursor.execute("UPDATE socios SET estado = %s WHERE id = %s", (nuevo_estado, socio_id))
        accion = "BAJA_SOCIO" if nuevo_estado == "inactivo" else "REACTIVAR_SOCIO"
        historial_servicio.registrar(
            Sesion.id_usuario(), accion, "socios", socio_id,
            f"nombre={socio['nombre']}", cursor=cursor,
        )
        conexion.commit()
    finally:
        conexion.close()