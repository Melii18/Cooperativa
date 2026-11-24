import calendar
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from mysql.connector import IntegrityError, errorcode

from database.conexion import obtener_conexion
from servicios import configuracion_servicio, historial_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorValidacion
from utils.validadores import formatear_guaranies, parsear_fecha, parsear_monto


def _sumar_meses(fecha, meses):
    """Suma meses a una fecha. Si el dia no existe (ej: 31 de febrero), usa el ultimo dia."""
    indice = fecha.month - 1 + meses
    anio = fecha.year + indice // 12
    mes = indice % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def calcular_plan(monto, cantidad_cuotas, porcentaje, fecha_desembolso):
    """Calcula el plan de pagos. No toca la base de datos.

    Cada cuota mensual de capital (monto / cuotas) lleva un recargo del porcentaje
    indicado. El total a pagar es entonces monto + porcentaje % del monto.
    """
    porcentaje = Decimal(porcentaje)
    total = int(
        (Decimal(monto) * (Decimal(100) + porcentaje) / Decimal(100))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    cuota_base = total // cantidad_cuotas
    resto = total - cuota_base * cantidad_cuotas  # guaranies que sobran de la division

    cuotas = []
    for numero in range(1, cantidad_cuotas + 1):
        valor = cuota_base + (resto if numero == cantidad_cuotas else 0)
        cuotas.append({
            "numero": numero,
            "vencimiento": _sumar_meses(fecha_desembolso, numero),
            "monto": valor,
        })
    return {
        "monto": monto,
        "porcentaje": porcentaje,
        "interes": total - monto,
        "total": total,
        "cuotas": cuotas,
    }


def _validar_solicitud(monto_texto, cuotas_texto, fecha_texto):
    monto = parsear_monto(monto_texto)
    maximo = configuracion_servicio.obtener_monto_maximo_prestamo()
    if monto > maximo:
        raise ErrorValidacion(
            f"El monto máximo por préstamo es de {formatear_guaranies(maximo)} Gs."
        )

    max_cuotas = configuracion_servicio.obtener_max_cuotas()
    cuotas_texto = cuotas_texto.strip()
    if not re.fullmatch(r"\d{1,3}", cuotas_texto) or not 1 <= int(cuotas_texto) <= max_cuotas:
        raise ErrorValidacion(f"La cantidad de cuotas debe ser un número entre 1 y {max_cuotas}.")
    cantidad = int(cuotas_texto)

    if monto < cantidad:
        raise ErrorValidacion("El monto es demasiado pequeño para esa cantidad de cuotas.")

    fecha = parsear_fecha(fecha_texto, "La fecha del préstamo")
    return monto, cantidad, fecha


def simular(monto_texto, cuotas_texto, fecha_texto):
    """Valida los datos y devuelve el plan de pagos sin guardar nada."""
    Sesion.exigir_permiso("prestamos_crear")
    monto, cantidad, fecha = _validar_solicitud(monto_texto, cuotas_texto, fecha_texto)
    porcentaje = configuracion_servicio.obtener_interes_porcentaje()
    return calcular_plan(monto, cantidad, porcentaje, fecha)


def socios_elegibles():
    """Socios activos que no tienen un prestamo activo."""
    Sesion.exigir_permiso("prestamos_crear")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT s.id, s.nombre, s.telefono FROM socios s "
            "WHERE s.estado = 'activo' AND NOT EXISTS ("
            "  SELECT 1 FROM prestamos p WHERE p.socio_id = s.id AND p.estado = 'activo'"
            ") ORDER BY s.nombre"
        )
        return cursor.fetchall()
    finally:
        conexion.close()


def crear_prestamo(socio_id, monto_texto, cuotas_texto, fecha_texto):
    Sesion.exigir_permiso("prestamos_crear")
    monto, cantidad, fecha = _validar_solicitud(monto_texto, cuotas_texto, fecha_texto)
    porcentaje = configuracion_servicio.obtener_interes_porcentaje()
    plan = calcular_plan(monto, cantidad, porcentaje, fecha)

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT nombre, estado, fecha_ingreso FROM socios WHERE id = %s", (socio_id,)
        )
        socio = cursor.fetchone()
        if socio is None:
            raise ErrorValidacion("El socio no existe.")
        if socio["estado"] != "activo":
            raise ErrorValidacion("El socio está inactivo.")
        if fecha < socio["fecha_ingreso"]:
            raise ErrorValidacion("El préstamo no puede ser anterior a la fecha de ingreso del socio.")

        cursor.execute(
            "SELECT COUNT(*) AS total FROM prestamos WHERE socio_id = %s AND estado = 'activo'",
            (socio_id,),
        )
        if cursor.fetchone()["total"] > 0:
            raise ErrorValidacion("El socio ya tiene un préstamo activo.")

        cursor.execute(
            "INSERT INTO prestamos (socio_id, monto_prestado, interes_porcentaje, cantidad_cuotas, "
            "total_a_pagar, saldo_pendiente, fecha_desembolso, registrado_por) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (socio_id, monto, porcentaje, cantidad, plan["total"], plan["total"],
             fecha, Sesion.id_usuario()),
        )
        prestamo_id = cursor.lastrowid

        cursor.executemany(
            "INSERT INTO cuotas_prestamo (prestamo_id, numero_cuota, fecha_vencimiento, monto_cuota) "
            "VALUES (%s, %s, %s, %s)",
            [(prestamo_id, c["numero"], c["vencimiento"], c["monto"]) for c in plan["cuotas"]],
        )

        historial_servicio.registrar(
            Sesion.id_usuario(), "CREAR_PRESTAMO", "prestamos", prestamo_id,
            f"socio={socio['nombre']}, monto={monto}, cuotas={cantidad}, "
            f"interes={porcentaje}%, total={plan['total']}",
            cursor=cursor,
        )
        conexion.commit()
        return prestamo_id
    except IntegrityError as e:
        conexion.rollback()
        if e.errno == errorcode.ER_DUP_ENTRY:  # la clave UNIQUE de "un prestamo activo por socio"
            raise ErrorValidacion("El socio ya tiene un préstamo activo.")
        raise
    finally:
        conexion.close()


def listar_prestamos(busqueda="", incluir_cerrados=False):
    Sesion.exigir_permiso("prestamos_ver")
    sql = (
        "SELECT p.id, s.nombre, p.fecha_desembolso, p.monto_prestado, p.total_a_pagar, "
        "p.saldo_pendiente, p.cantidad_cuotas, p.estado, "
        "(SELECT COUNT(*) FROM cuotas_prestamo c "
        " WHERE c.prestamo_id = p.id AND c.estado = 'pagada') AS cuotas_pagadas "
        "FROM prestamos p JOIN socios s ON s.id = p.socio_id WHERE 1 = 1"
    )
    parametros = []
    if not incluir_cerrados:
        sql += " AND p.estado = 'activo'"
    busqueda = busqueda.strip()
    if busqueda:
        sql += " AND s.nombre LIKE %s"
        parametros.append(f"%{busqueda}%")
    sql += " ORDER BY p.fecha_desembolso DESC, p.id DESC"

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(sql, parametros)
        return cursor.fetchall()
    finally:
        conexion.close()


def obtener_cuotas(prestamo_id):
    Sesion.exigir_permiso("prestamos_ver")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT numero_cuota, fecha_vencimiento, monto_cuota, monto_pagado, estado "
            "FROM cuotas_prestamo WHERE prestamo_id = %s ORDER BY numero_cuota",
            (prestamo_id,),
        )
        cuotas = cursor.fetchall()
    finally:
        conexion.close()

    hoy = date.today()
    for c in cuotas:
        c["vencida"] = c["estado"] == "pendiente" and c["fecha_vencimiento"] < hoy
    return cuotas


def anular_prestamo(prestamo_id, motivo):
    Sesion.exigir_permiso("anular")
    motivo = " ".join((motivo or "").split())
    if len(motivo) < 5:
        raise ErrorValidacion("Indique el motivo de la anulación (mínimo 5 caracteres).")

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT p.estado, p.monto_prestado, s.nombre FROM prestamos p "
            "JOIN socios s ON s.id = p.socio_id WHERE p.id = %s",
            (prestamo_id,),
        )
        prestamo = cursor.fetchone()
        if prestamo is None:
            raise ErrorValidacion("El préstamo no existe.")
        if prestamo["estado"] != "activo":
            raise ErrorValidacion("Solo se puede anular un préstamo activo.")

        cursor.execute(
            "SELECT COALESCE(SUM(monto_pagado), 0) AS pagado FROM cuotas_prestamo WHERE prestamo_id = %s",
            (prestamo_id,),
        )
        if cursor.fetchone()["pagado"] > 0:
            raise ErrorValidacion("No se puede anular: el préstamo ya tiene pagos registrados.")

        cursor.execute(
            "UPDATE prestamos SET estado = 'anulado' WHERE id = %s AND estado = 'activo'",
            (prestamo_id,),
        )
        if cursor.rowcount == 0:
            raise ErrorValidacion("Este préstamo ya fue modificado por otro usuario.")

        historial_servicio.registrar(
            Sesion.id_usuario(), "ANULAR_PRESTAMO", "prestamos", prestamo_id,
            f"socio={prestamo['nombre']}, monto={int(prestamo['monto_prestado'])}, motivo={motivo}",
            cursor=cursor,
        )
        conexion.commit()
    finally:
        conexion.close()