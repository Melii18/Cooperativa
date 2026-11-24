from utils.errores import ErrorPermiso

PERMISOS = {
    "administrador": {
        "usuarios", "socios_ver", "socios_editar", "aportes_ver", "aportes_registrar",
        "prestamos_ver", "prestamos_crear", "pagos_ver", "pagos_registrar", "anular",
        "historial_ver", "reportes",
    },
    "consulta": {"socios_ver", "aportes_ver", "prestamos_ver", "pagos_ver", "reportes"},
}


class Sesion:
    usuario = None  # diccionario con los datos del usuario logueado

    @classmethod
    def iniciar(cls, datos):
        # Guardamos solo lo necesario: NUNCA el hash de la contraseña
        cls.usuario = {
            "id": datos["id"],
            "nombre_usuario": datos["nombre_usuario"],
            "nombre_completo": datos["nombre_completo"],
            "rol": datos["rol"],
        }

    @classmethod
    def cerrar(cls):
        cls.usuario = None

    @classmethod
    def id_usuario(cls):
        return cls.usuario["id"] if cls.usuario else None

    @classmethod
    def tiene_permiso(cls, permiso):
        if cls.usuario is None:
            return False
        return permiso in PERMISOS.get(cls.usuario["rol"], set())

    @classmethod
    def exigir_permiso(cls, permiso):
        if not cls.tiene_permiso(permiso):
            raise ErrorPermiso("No tiene permiso para realizar esta acción.")