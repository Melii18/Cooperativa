import calendar
from datetime import date

from database.conexion import obtener_conexion
from servicios import aportes_servicio, historial_servicio
from servicios.aportes_servicio import NOMBRES_MESES
from servicios.sesion import Sesion
from utils.errores import ErrorValidacion
from utils.validadores import formatear_guaranies

# Cada reporte devuelve un diccionario con esta forma:
#   titulo   -> nombre del reporte
#   columnas -> lista de (titulo, tipo) donde tipo es "texto", "entero", "monto" o "fecha"
#   filas    -> lista de listas con los valores sin formato (numeros y fechas reales)
#   resumen  -> frase que se muestra debajo de la tabla


def _contar_y_sumar(cursor, sql, parametros=()):
    """Ejecuta una consulta que devuelve las columnas n y total, y las entrega como enteros."""
    cursor.execute(sql, parametros)
    fila = cursor.fetchone()
    return int(fila["n"]), int(fila["total"])


def resumen_general():
    Sesion.exigir_permiso("reportes")
    hoy = date.today()

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)

        cursor.execute("SELECT COUNT(*) AS n FROM socios WHERE estado = 'activo'")
        socios = int(cursor.fetchone()["n"])

        aportes = _contar_y_sumar(
            cursor,
            "SELECT COUNT(*) AS n, COALESCE(SUM(monto), 0) AS total "
            "FROM aportes WHERE estado = 'vigente'")
        prestados = _contar_y_sumar(
            cursor,
            "SELECT COUNT(*) AS n, COALESCE(SUM(monto_prestado), 0) AS total "
            "FROM prestamos WHERE estado IN ('activo', 'cancelado')")
        pagos = _contar_y_sumar(
            cursor,
            "SELECT COUNT(DISTINCT nro_recibo) AS n, COALESCE(SUM(monto), 0) AS total "
            "FROM pagos WHERE estado = 'vigente'")
        por_cobrar = _contar_y_sumar(
            cursor,
            "SELECT COUNT(*) AS n, COALESCE(SUM(saldo_pendiente), 0) AS total "
            "FROM prestamos WHERE estado = 'activo'")
        vencido = _contar_y_sumar(
            cursor,
            "SELECT COUNT(*) AS n, COALESCE(SUM(c.monto_cuota - c.monto_pagado), 0) AS total "
            "FROM cuotas_prestamo c JOIN prestamos p ON p.id = c.prestamo_id "
            "WHERE p.estado = 'activo' AND c.estado = 'pendiente' AND c.fecha_vencimiento < %s",
            (hoy,))
    finally:
        conexion.close()

    return {
        "titulo": "Resumen general",
        "columnas": [("Concepto", "texto"), ("Cantidad", "entero"), ("Monto", "monto")],
        "filas": [
            ["Socios activos", socios, None],
            ["Aportes recibidos", aportes[0], aportes[1]],
            ["Préstamos otorgados (activos y cancelados)", prestados[0], prestados[1]],
            ["Pagos de préstamos recibidos (cantidad de recibos)", pagos[0], pagos[1]],
            ["Préstamos activos: saldo por cobrar", por_cobrar[0], por_cobrar[1]],
            ["Cuotas vencidas sin pagar", vencido[0], vencido[1]],
        ],
        "resumen": f"Datos al {hoy.strftime('%d/%m/%Y')}",
    }


def socios_morosos():
    Sesion.exigir_permiso("reportes")
    hoy = date.today()

    # Aportes: reutilizamos el calculo que ya hace el modulo de aportes
    socios = {s["id"]: s for s in aportes_servicio.resumen_por_socio()}

    # Prestamos: cuotas pendientes cuya fecha de vencimiento ya paso, por socio
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT p.socio_id, COUNT(*) AS cuotas, SUM(c.monto_cuota - c.monto_pagado) AS monto "
            "FROM prestamos p JOIN cuotas_prestamo c ON c.prestamo_id = p.id "
            "WHERE p.estado = 'activo' AND c.estado = 'pendiente' AND c.fecha_vencimiento < %s "
            "GROUP BY p.socio_id",
            (hoy,),
        )
        vencidos = {f["socio_id"]: (int(f["cuotas"]), int(f["monto"])) for f in cursor.fetchall()}
    finally:
        conexion.close()

    filas = []
    for socio_id, s in socios.items():
        cuotas, monto_prestamo = vencidos.get(socio_id, (0, 0))
        if s["meses_pendientes"] == 0 and cuotas == 0:
            continue  # al dia: no es moroso
        filas.append([
            s["nombre"], s["telefono"],
            s["meses_pendientes"], s["deuda"],
            cuotas, monto_prestamo,
            s["deuda"] + monto_prestamo,
        ])
    filas.sort(key=lambda f: f[6], reverse=True)  # los que mas deben, primero

    total = sum(f[6] for f in filas)
    if filas:
        resumen = (f"Socios con deudas: {len(filas)}   ·   "
                   f"Total adeudado: {formatear_guaranies(total)} Gs")
    else:
        resumen = "No hay socios con deudas. Todo al día."

    return {
        "titulo": "Socios morosos",
        "columnas": [
            ("Socio", "texto"), ("Teléfono", "texto"),
            ("Meses de aporte pendientes", "entero"), ("Deuda de aportes (mínima)", "monto"),
            ("Cuotas de préstamo vencidas", "entero"), ("Monto vencido del préstamo", "monto"),
            ("Total adeudado", "monto"),
        ],
        "filas": filas,
        "resumen": resumen,
    }


def resumen_mensual(anio, mes):
    Sesion.exigir_permiso("reportes")
    if not 1 <= mes <= 12 or not 2000 <= anio <= 2100:
        raise ErrorValidacion("El mes o el año no son válidos.")

    inicio = date(anio, mes, 1)
    fin = date(anio, mes, calendar.monthrange(anio, mes)[1])

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        aportes = _contar_y_sumar(
            cursor,
            "SELECT COUNT(*) AS n, COALESCE(SUM(monto), 0) AS total FROM aportes "
            "WHERE estado = 'vigente' AND fecha_pago BETWEEN %s AND %s",
            (inicio, fin))
        pagos = _contar_y_sumar(
            cursor,
            "SELECT COUNT(DISTINCT nro_recibo) AS n, COALESCE(SUM(monto), 0) AS total FROM pagos "
            "WHERE estado = 'vigente' AND fecha_pago BETWEEN %s AND %s",
            (inicio, fin))
        prestamos = _contar_y_sumar(
            cursor,
            "SELECT COUNT(*) AS n, COALESCE(SUM(monto_prestado), 0) AS total FROM prestamos "
            "WHERE estado <> 'anulado' AND fecha_desembolso BETWEEN %s AND %s",
            (inicio, fin))
    finally:
        conexion.close()

    ingresos = aportes[1] + pagos[1]
    return {
        "titulo": f"Resumen de {NOMBRES_MESES[mes - 1]} {anio}",
        "columnas": [("Concepto", "texto"), ("Cantidad", "entero"), ("Monto", "monto")],
        "filas": [
            ["Aportes recibidos", aportes[0], aportes[1]],
            ["Pagos de préstamos recibidos (recibos)", pagos[0], pagos[1]],
            ["Total de ingresos", None, ingresos],
            ["Préstamos otorgados", prestamos[0], prestamos[1]],
            ["Ingresos menos préstamos otorgados", None, ingresos - prestamos[1]],
        ],
        "resumen": "Aportes y pagos según su fecha de pago. Préstamos según su fecha de otorgamiento.",
    }


def registrar_exportacion(titulo):
    """Deja constancia en el historial de que alguien exporto un reporte."""
    Sesion.exigir_permiso("reportes")
    historial_servicio.registrar(
        Sesion.id_usuario(), "EXPORTAR_REPORTE", "reportes", None, f"reporte={titulo}")