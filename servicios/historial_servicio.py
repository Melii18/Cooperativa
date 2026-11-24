from datetime import datetime, timedelta

from database.conexion import obtener_conexion
from servicios.sesion import Sesion
from utils.errores import ErrorValidacion

SQL_HISTORIAL = (
    "INSERT INTO historial (usuario_id, accion, tabla_afectada, registro_id, detalle) "
    "VALUES (%s, %s, %s, %s, %s)"
)

# Nombre legible de cada accion. Si aparece una accion que no esta aca, se muestra su codigo.
ETIQUETAS_ACCION = {
    "LOGIN": "Inicio de sesión",
    "LOGIN_FALLIDO": "Intento de acceso fallido",
    "LOGOUT": "Cierre de sesión",
    "CREAR_USUARIO": "Usuario creado",
    "CREAR_SOCIO": "Socio registrado",
    "EDITAR_SOCIO": "Socio editado",
    "BAJA_SOCIO": "Socio dado de baja",
    "REACTIVAR_SOCIO": "Socio reactivado",
    "REGISTRAR_APORTE": "Aporte registrado",
    "ANULAR_APORTE": "Aporte anulado",
    "CREAR_PRESTAMO": "Préstamo registrado",
    "ANULAR_PRESTAMO": "Préstamo anulado",
    "REGISTRAR_PAGO": "Pago registrado",
    "ANULAR_PAGO": "Pago anulado",
    "EXPORTAR_REPORTE": "Reporte exportado",
        "EDITAR_USUARIO": "Usuario editado",
    "DESACTIVAR_USUARIO": "Usuario desactivado",
    "REACTIVAR_USUARIO": "Usuario reactivado",
    "RESTABLECER_PASSWORD": "Contraseña restablecida",
    "CAMBIAR_PASSWORD": "Contraseña cambiada",
    "CAMBIAR_PASSWORD_FALLIDO": "Cambio de contraseña fallido",
}


def registrar(usuario_id, accion, tabla, registro_id=None, detalle=None, cursor=None):
    valores = (usuario_id, accion, tabla, registro_id, detalle)

    # Si nos pasan un cursor, usamos la transaccion del que nos llama:
    # el commit lo hace él, y todo se guarda junto o no se guarda nada.
    if cursor is not None:
        cursor.execute(SQL_HISTORIAL, valores)
        return

    conexion = obtener_conexion()
    try:
        cur = conexion.cursor()
        cur.execute(SQL_HISTORIAL, valores)
        conexion.commit()
    finally:
        conexion.close()


def etiqueta_accion(codigo):
    return ETIQUETAS_ACCION.get(codigo, codigo)


def listar_usuarios():
    """Usuarios del sistema, para el filtro por usuario."""
    Sesion.exigir_permiso("historial_ver")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id, nombre_usuario FROM usuarios ORDER BY nombre_usuario")
        return cursor.fetchall()
    finally:
        conexion.close()


def listar_acciones():
    """Acciones que existen en el historial, como lista de (codigo, etiqueta)."""
    Sesion.exigir_permiso("historial_ver")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT DISTINCT accion FROM historial")
        codigos = [fila[0] for fila in cursor.fetchall()]
    finally:
        conexion.close()
    return sorted(((c, etiqueta_accion(c)) for c in codigos), key=lambda par: par[1])


def consultar(usuario_id=None, accion=None, desde=None, hasta=None, texto="", limite=500):
    """Devuelve {"filas": [...], "hay_mas": bool}, del movimiento mas reciente al mas antiguo."""
    Sesion.exigir_permiso("historial_ver")
    if desde and hasta and desde > hasta:
        raise ErrorValidacion("La fecha 'desde' no puede ser posterior a la fecha 'hasta'.")

    sql = (
        "SELECT h.id, h.fecha_hora, COALESCE(u.nombre_usuario, '(sin usuario)') AS usuario, "
        "h.accion, h.tabla_afectada, h.registro_id, h.detalle "
        "FROM historial h LEFT JOIN usuarios u ON u.id = h.usuario_id WHERE 1 = 1"
    )
    parametros = []
    if usuario_id is not None:
        sql += " AND h.usuario_id = %s"
        parametros.append(usuario_id)
    if accion:
        sql += " AND h.accion = %s"
        parametros.append(accion)
    if desde:
        sql += " AND h.fecha_hora >= %s"
        parametros.append(datetime.combine(desde, datetime.min.time()))
    if hasta:
        # "menor que el dia siguiente" incluye todo el dia 'hasta', hasta las 23:59:59
        sql += " AND h.fecha_hora < %s"
        parametros.append(datetime.combine(hasta + timedelta(days=1), datetime.min.time()))
    texto = texto.strip()
    if texto:
        sql += " AND h.detalle LIKE %s"
        parametros.append(f"%{texto}%")
    sql += " ORDER BY h.id DESC LIMIT %s"
    parametros.append(limite + 1)  # pedimos uno de mas para saber si hay mas resultados

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(sql, parametros)
        filas = cursor.fetchall()
    finally:
        conexion.close()

    hay_mas = len(filas) > limite
    filas = filas[:limite]
    for f in filas:
        f["accion_texto"] = etiqueta_accion(f["accion"])
    return {"filas": filas, "hay_mas": hay_mas}