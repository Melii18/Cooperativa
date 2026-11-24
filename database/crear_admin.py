import getpass

from database.conexion import obtener_conexion
from servicios.auth_servicio import crear_usuario
from utils.errores import ErrorDeNegocio


def main():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'administrador'")
    (cantidad,) = cursor.fetchone()
    conexion.close()

    if cantidad > 0:
        print("Ya existe un administrador. Los demás usuarios se crean desde el sistema.")
        return

    print("Creación del primer administrador")
    usuario = input("Nombre de usuario: ")
    nombre = input("Nombre completo: ")
    password = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
    repetir = getpass.getpass("Repetir contraseña: ")

    if password != repetir:
        print("Las contraseñas no coinciden.")
        return

    try:
        crear_usuario(usuario, nombre, password, "administrador", verificar_permiso=False)
        print("Administrador creado correctamente.")
    except ErrorDeNegocio as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()