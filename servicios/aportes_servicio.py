from datetime import date

from mysql.connector import IntegrityError, errorcode

from database.conexion import obtener_conexion
from servicios import configuracion_servicio, historial_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorValidacion
from utils.validadores import formatear_guaranies, parsear_fecha, parsear_monto

MESES_ADELANTO_MAX = 12  # cuantos meses futuros se pueden pagar por adelantado

NOMBRES_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def etiqueta_mes(anio, mes):
    return f"{NOMBRES_MESES[mes - 1]} {anio}"


def _siguiente_mes(anio, mes):
    if mes == 12:
        return anio + 1, 1
    return anio, mes + 1


def _meses_desde(fecha_ingreso, hoy):
    """Lista de (anio, mes) desde el mes de ingreso hasta el mes actual, inclusive."""
    anio, mes = fecha_ingreso.year, fecha_ingreso.month
    meses = []
    while (anio, mes) <= (hoy.year, hoy.month):
        meses.append((anio, mes))
        anio, mes = _siguiente_mes(anio, mes)
    return meses


def _limite_adelanto(hoy):
    """Ultimo (anio, mes) que se puede pagar por adelantado."""
    anio, mes = hoy.year, hoy.month
    for _ in range(MESES_ADELANTO_MAX):
        anio, mes = _siguiente_mes(anio, mes)
    return anio, mes


def _ingreso_y_pagados(socio_id):
    """Devuelve la fecha de ingreso del socio y el conjunto de meses que ya tiene pagados."""
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT fecha_ingreso FROM socios WHERE id = %s", (socio_id,))
        socio = cursor.fetchone()
        if socio is None:
            raise ErrorValidacion("El socio no existe.")
        cursor.execute(
            "SELECT anio, mes FROM aportes WHERE socio_id = %s AND estado = 'vigente'",
            (socio_id,),
        )
        pagados = {(f["anio"], f["mes"]) for f in cursor.fetchall()}
    finally:
        conexion.close()
    return socio["fecha_ingreso"], pagados


def resumen_por_socio(busqueda=""):
    """Para cada socio activo: meses pendientes, deuda minima y total aportado."""
    Sesion.exigir_permiso("aportes_ver")
    minimo = configuracion_servicio.obtener_aporte_minimo()
    hoy = date.today()

    sql = "SELECT id, nombre, telefono, fecha_ingreso FROM socios WHERE estado = 'activo'"
    parametros = []
    busqueda = busqueda.strip()
    if busqueda:
        sql += " AND (nombre LIKE %s OR telefono LIKE %s)"
        parametros = [f"%{busqueda}%", f"%{busqueda}%"]
    sql += " ORDER BY nombre"

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(sql, parametros)
        socios = cursor.fetchall()

        cursor.execute("SELECT socio_id, anio, mes, monto FROM aportes WHERE estado = 'vigente'")
        pagados = {}
        totales = {}
        for fila in cursor.fetchall():
            sid = fila["socio_id"]
            pagados.setdefault(sid, set()).add((fila["anio"], fila["mes"]))
            totales[sid] = totales.get(sid, 0) + int(fila["monto"])
    finally:
        conexion.close()

    resumen = []
    for s in socios:
        ya_pagados = pagados.get(s["id"], set())
        pendientes = [m for m in _meses_desde(s["fecha_ingreso"], hoy) if m not in ya_pagados]
        resumen.append({
            "id": s["id"],
            "nombre": s["nombre"],
            "telefono": s["telefono"],
            "meses_pendientes": len(pendientes),
            "deuda": len(pendientes) * minimo,
            "total_aportado": totales.get(s["id"], 0),
        })
    return resumen


def meses_disponibles(socio_id):
    """Meses que se pueden pagar: primero los pendientes y despues los adelantados.

    Devuelve una lista de (anio, mes, es_adelantado).
    """
    Sesion.exigir_permiso("aportes_ver")
    hoy = date.today()
    fecha_ingreso, pagados = _ingreso_y_pagados(socio_id)

    disponibles = [
        (a, m, False) for a, m in _meses_desde(fecha_ingreso, hoy) if (a, m) not in pagados
    ]

    anio, mes = hoy.year, hoy.month
    for _ in range(MESES_ADELANTO_MAX):
        anio, mes = _siguiente_mes(anio, mes)
        if (anio, mes) not in pagados:
            disponibles.append((anio, mes, True))
    return disponibles


def registrar_aporte(socio_id, anio, mes, monto_texto, fecha_pago_texto):
    Sesion.exigir_permiso("aportes_registrar")

    monto = parsear_monto(monto_texto)
    fecha_pago = parsear_fecha(fecha_pago_texto, "La fecha de pago")

    minimo = configuracion_servicio.obtener_aporte_minimo()
    if monto < minimo:
        raise ErrorValidacion(f"El aporte mínimo es de {formatear_guaranies(minimo)} Gs.")

    hoy = date.today()
    if not 1 <= mes <= 12:
        raise ErrorValidacion("Mes no válido.")
    if (anio, mes) > _limite_adelanto(hoy):
        raise ErrorValidacion(
            f"Solo se pueden registrar aportes hasta {MESES_ADELANTO_MAX} meses por adelantado."
        )

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
        ingreso = socio["fecha_ingreso"]
        if (anio, mes) < (ingreso.year, ingreso.month):
            raise ErrorValidacion(
                "No se puede registrar un aporte anterior al mes de ingreso del socio."
            )

        cursor.execute(
            "INSERT INTO aportes (socio_id, anio, mes, monto, fecha_pago, registrado_por) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (socio_id, anio, mes, monto, fecha_pago, Sesion.id_usuario()),
        )
        nuevo_id = cursor.lastrowid

        adelantado = " (adelantado)" if (anio, mes) > (hoy.year, hoy.month) else ""
        historial_servicio.registrar(
            Sesion.id_usuario(), "REGISTRAR_APORTE", "aportes", nuevo_id,
            f"socio={socio['nombre']}, periodo={anio}-{mes:02d}{adelantado}, monto={monto}",
            cursor=cursor,
        )
        conexion.commit()
        return nuevo_id
    except IntegrityError as e:
        conexion.rollback()
        if e.errno == errorcode.ER_DUP_ENTRY:  # error 1062: la clave UNIQUE ya existe
            raise ErrorValidacion(
                f"Ya existe un aporte vigente de este socio para {etiqueta_mes(anio, mes)}."
            )
        raise
    finally:
        conexion.close()


def listar_aportes_socio(socio_id):
    Sesion.exigir_permiso("aportes_ver")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, anio, mes, monto, fecha_pago, estado FROM aportes "
            "WHERE socio_id = %s ORDER BY anio DESC, mes DESC, id DESC",
            (socio_id,),
        )
        return cursor.fetchall()
    finally:
        conexion.close()


def anular_aporte(aporte_id, motivo):
    Sesion.exigir_permiso("anular")
    motivo = " ".join((motivo or "").split())
    if len(motivo) < 5:
        raise ErrorValidacion("Indique el motivo de la anulación (mínimo 5 caracteres).")

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT a.anio, a.mes, a.monto, a.estado, s.nombre "
            "FROM aportes a JOIN socios s ON s.id = a.socio_id WHERE a.id = %s",
            (aporte_id,),
        )
        aporte = cursor.fetchone()
        if aporte is None:
            raise ErrorValidacion("El aporte no existe.")
        if aporte["estado"] == "anulado":
            raise ErrorValidacion("Este aporte ya está anulado.")

        cursor.execute(
            "UPDATE aportes SET estado = 'anulado' WHERE id = %s AND estado = 'vigente'",
            (aporte_id,),
        )
        if cursor.rowcount == 0:
            raise ErrorValidacion("Este aporte ya fue anulado.")

        historial_servicio.registrar(
            Sesion.id_usuario(), "ANULAR_APORTE", "aportes", aporte_id,
            f"socio={aporte['nombre']}, periodo={aporte['anio']}-{aporte['mes']:02d}, "
            f"monto={int(aporte['monto'])}, motivo={motivo}",
            cursor=cursor,
        )
        conexion.commit()
    finally:
        conexion.close()