import re
from datetime import date

from mysql.connector import IntegrityError, errorcode

from database.conexion import obtener_conexion
from servicios import historial_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorValidacion
from utils.validadores import formatear_guaranies, parsear_fecha, parsear_monto


def _tipo_cuota(vencimiento, hoy):
    if vencimiento < hoy:
        return "Vencida"
    if vencimiento > hoy:
        return "Adelantada"
    return "Vence hoy"


def distribuir_pago(cuotas, monto, hoy):
    """Reparte un monto entre las cuotas pendientes, de la mas antigua a la mas nueva.

    `cuotas` es una lista ordenada de diccionarios con id, numero, vencimiento y pendiente.
    No toca la base de datos.
    """
    restante = monto
    reparto = []
    for c in cuotas:
        if restante <= 0:
            break
        aplicado = min(restante, c["pendiente"])
        reparto.append({
            "cuota_id": c["id"],
            "numero": c["numero"],
            "vencimiento": c["vencimiento"],
            "pendiente_antes": c["pendiente"],
            "aplicado": aplicado,
            "pendiente_despues": c["pendiente"] - aplicado,
            "tipo": _tipo_cuota(c["vencimiento"], hoy),
        })
        restante -= aplicado
    return reparto


def _normalizar_recibo(texto):
    recibo = (texto or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-/]{0,29}", recibo):
        raise ErrorValidacion(
            "Ingrese el número de recibo (letras, números, guion o barra; máximo 30 caracteres)."
        )
    return recibo


def _cuotas_pendientes(cursor, prestamo_id, bloquear=False):
    sql = (
        "SELECT id, numero_cuota, fecha_vencimiento, monto_cuota, monto_pagado "
        "FROM cuotas_prestamo WHERE prestamo_id = %s AND estado = 'pendiente' "
        "ORDER BY numero_cuota"
    )
    if bloquear:
        sql += " FOR UPDATE"
    cursor.execute(sql, (prestamo_id,))
    return [
        {
            "id": f["id"],
            "numero": f["numero_cuota"],
            "vencimiento": f["fecha_vencimiento"],
            "monto_cuota": int(f["monto_cuota"]),
            "pagado": int(f["monto_pagado"]),
            "pendiente": int(f["monto_cuota"] - f["monto_pagado"]),
        }
        for f in cursor.fetchall()
    ]


def resumen_prestamos_activos(busqueda=""):
    """Para cada prestamo activo: saldo, cuotas vencidas y monto vencido."""
    Sesion.exigir_permiso("pagos_ver")
    hoy = date.today()
    sql = (
        "SELECT p.id, s.nombre, p.saldo_pendiente, "
        "COALESCE(SUM(CASE WHEN c.estado = 'pendiente' AND c.fecha_vencimiento < %s "
        "  THEN c.monto_cuota - c.monto_pagado ELSE 0 END), 0) AS monto_vencido, "
        "COALESCE(SUM(CASE WHEN c.estado = 'pendiente' AND c.fecha_vencimiento < %s "
        "  THEN 1 ELSE 0 END), 0) AS cuotas_vencidas, "
        "MIN(CASE WHEN c.estado = 'pendiente' THEN c.fecha_vencimiento END) AS proximo_vencimiento "
        "FROM prestamos p JOIN socios s ON s.id = p.socio_id "
        "JOIN cuotas_prestamo c ON c.prestamo_id = p.id "
        "WHERE p.estado = 'activo'"
    )
    parametros = [hoy, hoy]
    busqueda = busqueda.strip()
    if busqueda:
        sql += " AND s.nombre LIKE %s"
        parametros.append(f"%{busqueda}%")
    sql += " GROUP BY p.id, s.nombre, p.saldo_pendiente ORDER BY s.nombre"

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(sql, parametros)
        filas = cursor.fetchall()
    finally:
        conexion.close()

    for f in filas:
        f["saldo"] = int(f.pop("saldo_pendiente"))
        f["monto_vencido"] = int(f["monto_vencido"])
        f["cuotas_vencidas"] = int(f["cuotas_vencidas"])
    return filas


def datos_para_pago(prestamo_id):
    """Datos que muestra el formulario de pago: saldo, vencido y proxima cuota."""
    Sesion.exigir_permiso("pagos_registrar")
    hoy = date.today()
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT p.estado, p.saldo_pendiente, s.nombre FROM prestamos p "
            "JOIN socios s ON s.id = p.socio_id WHERE p.id = %s",
            (prestamo_id,),
        )
        prestamo = cursor.fetchone()
        if prestamo is None:
            raise ErrorValidacion("El préstamo no existe.")
        if prestamo["estado"] != "activo":
            raise ErrorValidacion("El préstamo no está activo.")
        cuotas = _cuotas_pendientes(cursor, prestamo_id)
    finally:
        conexion.close()

    vencidas = [c for c in cuotas if c["vencimiento"] < hoy]
    return {
        "socio": prestamo["nombre"],
        "saldo": int(prestamo["saldo_pendiente"]),
        "cuotas_vencidas": len(vencidas),
        "monto_vencido": sum(c["pendiente"] for c in vencidas),
        "proxima_cuota": cuotas[0]["pendiente"] if cuotas else 0,
    }


def simular_pago(prestamo_id, monto_texto):
    """Valida el monto y muestra como se repartiria, sin guardar nada."""
    Sesion.exigir_permiso("pagos_registrar")
    monto = parsear_monto(monto_texto)
    hoy = date.today()

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT estado FROM prestamos WHERE id = %s", (prestamo_id,))
        prestamo = cursor.fetchone()
        if prestamo is None:
            raise ErrorValidacion("El préstamo no existe.")
        if prestamo["estado"] != "activo":
            raise ErrorValidacion("El préstamo no está activo.")
        cuotas = _cuotas_pendientes(cursor, prestamo_id)
    finally:
        conexion.close()

    saldo = sum(c["pendiente"] for c in cuotas)
    if monto > saldo:
        raise ErrorValidacion(
            f"El monto supera el saldo pendiente del préstamo ({formatear_guaranies(saldo)} Gs)."
        )
    return {
        "monto": monto,
        "saldo": saldo,
        "saldo_final": saldo - monto,
        "cancela": monto == saldo,
        "reparto": distribuir_pago(cuotas, monto, hoy),
    }


def registrar_pago(prestamo_id, monto_texto, recibo_texto, fecha_texto):
    Sesion.exigir_permiso("pagos_registrar")

    monto = parsear_monto(monto_texto)
    recibo = _normalizar_recibo(recibo_texto)
    fecha_pago = parsear_fecha(fecha_texto, "La fecha de pago")
    hoy = date.today()

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)

        # Bloquea el prestamo: si dos personas pagan a la vez, la segunda espera a la primera
        cursor.execute(
            "SELECT p.estado, p.saldo_pendiente, p.fecha_desembolso, s.nombre "
            "FROM prestamos p JOIN socios s ON s.id = p.socio_id "
            "WHERE p.id = %s FOR UPDATE OF p",
            (prestamo_id,),
        )
        prestamo = cursor.fetchone()
        if prestamo is None:
            raise ErrorValidacion("El préstamo no existe.")
        if prestamo["estado"] != "activo":
            raise ErrorValidacion("El préstamo no está activo.")
        if fecha_pago < prestamo["fecha_desembolso"]:
            raise ErrorValidacion("La fecha de pago no puede ser anterior a la fecha del préstamo.")

        cursor.execute(
            "SELECT COUNT(*) AS total FROM pagos WHERE nro_recibo = %s AND estado = 'vigente'",
            (recibo,),
        )
        if cursor.fetchone()["total"] > 0:
            raise ErrorValidacion(f"El recibo N° {recibo} ya fue registrado.")

        cuotas = _cuotas_pendientes(cursor, prestamo_id, bloquear=True)
        saldo = sum(c["pendiente"] for c in cuotas)
        if saldo != int(prestamo["saldo_pendiente"]):
            raise ErrorValidacion(
                "El saldo del préstamo no coincide con sus cuotas. Avise al administrador."
            )
        if monto > saldo:
            raise ErrorValidacion(
                f"El monto supera el saldo pendiente del préstamo ({formatear_guaranies(saldo)} Gs)."
            )

        reparto = distribuir_pago(cuotas, monto, hoy)
        por_cuota = {c["id"]: c for c in cuotas}
        primer_pago_id = None
        for r in reparto:
            cursor.execute(
                "INSERT INTO pagos (cuota_id, monto, fecha_pago, nro_recibo, registrado_por) "
                "VALUES (%s, %s, %s, %s, %s)",
                (r["cuota_id"], r["aplicado"], fecha_pago, recibo, Sesion.id_usuario()),
            )
            if primer_pago_id is None:
                primer_pago_id = cursor.lastrowid

            cuota = por_cuota[r["cuota_id"]]
            nuevo_pagado = cuota["pagado"] + r["aplicado"]
            nuevo_estado = "pagada" if nuevo_pagado == cuota["monto_cuota"] else "pendiente"
            cursor.execute(
                "UPDATE cuotas_prestamo SET monto_pagado = %s, estado = %s WHERE id = %s",
                (nuevo_pagado, nuevo_estado, r["cuota_id"]),
            )

        nuevo_saldo = saldo - monto
        estado_prestamo = "cancelado" if nuevo_saldo == 0 else "activo"
        cursor.execute(
            "UPDATE prestamos SET saldo_pendiente = %s, estado = %s WHERE id = %s",
            (nuevo_saldo, estado_prestamo, prestamo_id),
        )

        numeros = ", ".join(str(r["numero"]) for r in reparto)
        adelantadas = sum(1 for r in reparto if r["tipo"] == "Adelantada")
        historial_servicio.registrar(
            Sesion.id_usuario(), "REGISTRAR_PAGO", "pagos", primer_pago_id,
            f"recibo={recibo}, socio={prestamo['nombre']}, prestamo={prestamo_id}, monto={monto}, "
            f"cuotas={numeros}, adelantadas={adelantadas}, saldo={nuevo_saldo}",
            cursor=cursor,
        )
        conexion.commit()
        return {"nuevo_saldo": nuevo_saldo, "cancelado": nuevo_saldo == 0}
    except IntegrityError as e:
        conexion.rollback()
        if e.errno == errorcode.ER_DUP_ENTRY:
            raise ErrorValidacion(f"El recibo N° {recibo} ya fue registrado para esas cuotas.")
        raise
    finally:
        conexion.close()


def listar_pagos_prestamo(prestamo_id):
    """Pagos de un prestamo, agrupados por recibo (un recibo puede cubrir varias cuotas)."""
    Sesion.exigir_permiso("pagos_ver")
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(
            "SELECT pg.id, pg.nro_recibo, pg.fecha_pago, pg.estado, pg.monto, c.numero_cuota "
            "FROM pagos pg JOIN cuotas_prestamo c ON c.id = pg.cuota_id "
            "WHERE c.prestamo_id = %s ORDER BY pg.id DESC",
            (prestamo_id,),
        )
        filas = cursor.fetchall()
    finally:
        conexion.close()

    grupos = {}
    for f in filas:
        clave = (f["nro_recibo"], f["fecha_pago"], f["estado"])
        g = grupos.setdefault(clave, {
            "nro_recibo": f["nro_recibo"], "fecha_pago": f["fecha_pago"],
            "estado": f["estado"], "monto": 0, "numeros": [],
        })
        g["monto"] += int(f["monto"])
        g["numeros"].append(f["numero_cuota"])

    resultado = []
    for g in grupos.values():
        g["cuotas"] = ", ".join(str(n) for n in sorted(g.pop("numeros")))
        resultado.append(g)
    return resultado


def anular_pago(prestamo_id, recibo, motivo):
    Sesion.exigir_permiso("anular")
    motivo = " ".join((motivo or "").split())
    if len(motivo) < 5:
        raise ErrorValidacion("Indique el motivo de la anulación (mínimo 5 caracteres).")

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT p.estado, p.saldo_pendiente, s.nombre FROM prestamos p "
            "JOIN socios s ON s.id = p.socio_id WHERE p.id = %s FOR UPDATE OF p",
            (prestamo_id,),
        )
        prestamo = cursor.fetchone()
        if prestamo is None:
            raise ErrorValidacion("El préstamo no existe.")
        if prestamo["estado"] == "anulado":
            raise ErrorValidacion("El préstamo está anulado.")

        cursor.execute(
            "SELECT pg.id, pg.cuota_id, pg.monto FROM pagos pg "
            "JOIN cuotas_prestamo c ON c.id = pg.cuota_id "
            "WHERE c.prestamo_id = %s AND pg.nro_recibo = %s AND pg.estado = 'vigente' "
            "FOR UPDATE OF pg",
            (prestamo_id, recibo),
        )
        pagos = cursor.fetchall()
        if not pagos:
            raise ErrorValidacion("No hay un pago vigente con ese recibo en este préstamo.")

        total = 0
        for pg in pagos:
            monto = int(pg["monto"])
            total += monto
            cursor.execute("UPDATE pagos SET estado = 'anulado' WHERE id = %s", (pg["id"],))
            cursor.execute(
                "UPDATE cuotas_prestamo SET monto_pagado = monto_pagado - %s, estado = 'pendiente' "
                "WHERE id = %s",
                (monto, pg["cuota_id"]),
            )

        nuevo_saldo = int(prestamo["saldo_pendiente"]) + total
        cursor.execute(
            "UPDATE prestamos SET saldo_pendiente = %s, estado = 'activo' WHERE id = %s",
            (nuevo_saldo, prestamo_id),
        )

        historial_servicio.registrar(
            Sesion.id_usuario(), "ANULAR_PAGO", "pagos", pagos[0]["id"],
            f"recibo={recibo}, socio={prestamo['nombre']}, prestamo={prestamo_id}, monto={total}, "
            f"saldo={nuevo_saldo}, motivo={motivo}",
            cursor=cursor,
        )
        conexion.commit()
    except IntegrityError as e:
        conexion.rollback()
        if e.errno == errorcode.ER_DUP_ENTRY:
            raise ErrorValidacion(
                "No se puede anular este pago: el socio ya tiene otro préstamo activo."
            )
        raise
    finally:
        conexion.close()