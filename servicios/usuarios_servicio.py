from database.conexion import obtener_conexion
from servicios import historial_servicio
from servicios.auth_servicio import ROLES, validar_password
from servicios.sesion import Sesion
from utils.errores import ErrorValidacion
from utils.seguridad import hashear_password


def listar_usuarios():
    Sesion.exigir_permiso("usuarios")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, nombre_usuario, nombre_completo, rol, activo, creado_en "
            "FROM usuarios ORDER BY nombre_usuario"
        )
        return cursor.fetchall()
    finally:
        conexion.close()


def _usuario_ajeno(cursor, usuario_id, mensaje_propio):
    """Carga y bloquea a otro usuario para modificarlo. Nadie puede modificarse a si mismo.

    Como quien modifica es siempre un administrador activo distinto del modificado,
    nunca es posible quedarse sin administradores.
    """
    if usuario_id == Sesion.id_usuario():
        raise ErrorValidacion(mensaje_propio)
    cursor.execute(
        "SELECT nombre_usuario, rol, activo FROM usuarios WHERE id = %s FOR UPDATE",
        (usuario_id,),
    )
    usuario = cursor.fetchone()
    if usuario is None:
        raise ErrorValidacion("El usuario no existe.")
    return usuario


def cambiar_rol(usuario_id, nuevo_rol):
    Sesion.exigir_permiso("usuarios")
    if nuevo_rol not in ROLES:
        raise ErrorValidacion("Rol no válido.")

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        usuario = _usuario_ajeno(cursor, usuario_id, "No puede cambiar su propio rol.")
        if usuario["rol"] == nuevo_rol:
            return

        cursor.execute("UPDATE usuarios SET rol = %s WHERE id = %s", (nuevo_rol, usuario_id))
        historial_servicio.registrar(
            Sesion.id_usuario(), "EDITAR_USUARIO", "usuarios", usuario_id,
            f"usuario={usuario['nombre_usuario']}, rol: {usuario['rol']} -> {nuevo_rol}",
            cursor=cursor,
        )
        conexion.commit()
    finally:
        conexion.close()


def cambiar_estado(usuario_id, activo):
    Sesion.exigir_permiso("usuarios")

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        usuario = _usuario_ajeno(cursor, usuario_id, "No puede desactivar su propio usuario.")
        if bool(usuario["activo"]) == bool(activo):
            return

        cursor.execute(
            "UPDATE usuarios SET activo = %s WHERE id = %s", (1 if activo else 0, usuario_id))
        accion = "REACTIVAR_USUARIO" if activo else "DESACTIVAR_USUARIO"
        historial_servicio.registrar(
            Sesion.id_usuario(), accion, "usuarios", usuario_id,
            f"usuario={usuario['nombre_usuario']}", cursor=cursor,
        )
        conexion.commit()
    finally:
        conexion.close()


def restablecer_password(usuario_id, nueva, repetida):
    Sesion.exigir_permiso("usuarios")
    if nueva != repetida:
        raise ErrorValidacion("La contraseña nueva y su repetición no coinciden.")
    validar_password(nueva)

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        usuario = _usuario_ajeno(
            cursor, usuario_id,
            'Para cambiar su propia contraseña use "Cambiar mi contraseña" en el menú principal.',
        )
        cursor.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id = %s",
            (hashear_password(nueva), usuario_id),
        )
        historial_servicio.registrar(
            Sesion.id_usuario(), "RESTABLECER_PASSWORD", "usuarios", usuario_id,
            f"usuario={usuario['nombre_usuario']}", cursor=cursor,
        )
        conexion.commit()
    finally:
        conexion.close()