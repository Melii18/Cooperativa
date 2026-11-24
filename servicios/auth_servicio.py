import re
from mysql.connector import IntegrityError

from database.conexion import obtener_conexion
from servicios import historial_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorAutenticacion, ErrorValidacion
from utils.seguridad import hashear_password, verificar_password

ROLES = ("administrador", "consulta")
PATRON_USUARIO = re.compile(r"[A-Za-z0-9_]{4,30}")


def validar_password(password):
    """Reglas de la contrasena. Para endurecerlas, se agregan aca."""
    if len(password) < 8:
        raise ErrorValidacion("La contraseña debe tener al menos 8 caracteres.")
    if len(password.encode("utf-8")) > 72:
        raise ErrorValidacion("La contraseña es demasiado larga (máximo 72 bytes).")


def iniciar_sesion(nombre_usuario, password):
    nombre_usuario = nombre_usuario.strip()
    if not nombre_usuario or not password:
        raise ErrorAutenticacion("Ingrese su usuario y contraseña.")

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, nombre_usuario, nombre_completo, password_hash, rol, activo "
            "FROM usuarios WHERE nombre_usuario = %s",
            (nombre_usuario,),
        )
        fila = cursor.fetchone()
    finally:
        conexion.close()

    usuario_id = fila["id"] if fila else None

    # Mismo mensaje si el usuario no existe, esta inactivo o la clave es incorrecta
    if fila is None or not fila["activo"] or not verificar_password(password, fila["password_hash"]):
        historial_servicio.registrar(
            usuario_id, "LOGIN_FALLIDO", "usuarios", usuario_id, f"usuario={nombre_usuario}"
        )
        raise ErrorAutenticacion("Usuario o contraseña incorrectos.")

    Sesion.iniciar(fila)
    historial_servicio.registrar(usuario_id, "LOGIN", "usuarios", usuario_id)


def cerrar_sesion():
    historial_servicio.registrar(Sesion.id_usuario(), "LOGOUT", "usuarios", Sesion.id_usuario())
    Sesion.cerrar()


def crear_usuario(nombre_usuario, nombre_completo, password, rol,
                  verificar_permiso=True, repetir=None):
    if verificar_permiso:
        Sesion.exigir_permiso("usuarios")

    nombre_usuario = nombre_usuario.strip()
    nombre_completo = " ".join(nombre_completo.split())

    if not PATRON_USUARIO.fullmatch(nombre_usuario):
        raise ErrorValidacion(
            "El usuario debe tener entre 4 y 30 caracteres: letras, números o guion bajo."
        )
    if not nombre_completo:
        raise ErrorValidacion("El nombre completo es obligatorio.")
    if repetir is not None and password != repetir:
        raise ErrorValidacion("Las contraseñas no coinciden.")
    validar_password(password)
    if rol not in ROLES:
        raise ErrorValidacion("Rol no válido.")

    hash_guardado = hashear_password(password)

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO usuarios (nombre_usuario, nombre_completo, password_hash, rol) "
            "VALUES (%s, %s, %s, %s)",
            (nombre_usuario, nombre_completo, hash_guardado, rol),
        )
        conexion.commit()
        nuevo_id = cursor.lastrowid
    except IntegrityError:
        raise ErrorValidacion("Ya existe un usuario con ese nombre.")
    finally:
        conexion.close()

    historial_servicio.registrar(
        Sesion.id_usuario(), "CREAR_USUARIO", "usuarios", nuevo_id,
        f"usuario={nombre_usuario}, rol={rol}",
    )
    return nuevo_id


def cambiar_password_propia(actual, nueva, repetida):
    usuario_id = Sesion.id_usuario()
    if usuario_id is None:
        raise ErrorAutenticacion("No hay una sesión iniciada.")
    if nueva != repetida:
        raise ErrorValidacion("La contraseña nueva y su repetición no coinciden.")
    validar_password(nueva)

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT password_hash FROM usuarios WHERE id = %s", (usuario_id,))
        fila = cursor.fetchone()

        if fila is None or not verificar_password(actual, fila["password_hash"]):
            historial_servicio.registrar(
                usuario_id, "CAMBIAR_PASSWORD_FALLIDO", "usuarios", usuario_id)
            raise ErrorAutenticacion("La contraseña actual es incorrecta.")
        if verificar_password(nueva, fila["password_hash"]):
            raise ErrorValidacion("La contraseña nueva debe ser distinta de la actual.")

        cursor.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id = %s",
            (hashear_password(nueva), usuario_id),
        )
        # En el historial queda SOLO el hecho del cambio, nunca la contrasena
        historial_servicio.registrar(
            usuario_id, "CAMBIAR_PASSWORD", "usuarios", usuario_id, cursor=cursor)
        conexion.commit()
    finally:
        conexion.close()