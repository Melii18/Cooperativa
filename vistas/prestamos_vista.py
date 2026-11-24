import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox, simpledialog

from servicios import configuracion_servicio, prestamos_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorDeNegocio
from utils.validadores import formatear_guaranies


def gs(valor):
    return f"{formatear_guaranies(valor)} Gs"


class PrestamosVentana(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Préstamos")
        self.geometry("980x540")
        self.transient(master)

        # --- Barra superior ---
        barra = ttk.Frame(self, padding=10)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar socio:").pack(side="left")
        self.var_busqueda = tk.StringVar()
        ttk.Entry(barra, textvariable=self.var_busqueda, width=28).pack(side="left", padx=5)
        self.var_busqueda.trace_add("write", lambda *args: self.cargar())
        self.var_cerrados = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="Mostrar cancelados y anulados",
                        variable=self.var_cerrados, command=self.cargar).pack(side="left", padx=10)

        maximo = configuracion_servicio.obtener_monto_maximo_prestamo()
        interes = float(configuracion_servicio.obtener_interes_porcentaje())
        ttk.Label(barra, text=f"Máximo: {gs(maximo)}  ·  Interés: {interes:g} %",
                  font=("Segoe UI", 10, "bold")).pack(side="right")

        # --- Tabla ---
        contenedor = ttk.Frame(self)
        contenedor.pack(fill="both", expand=True, padx=10)
        columnas = ("socio", "fecha", "monto", "total", "saldo", "cuotas", "estado")
        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for columna, titulo, ancho, alineacion in (
            ("socio", "Socio", 220, "w"),
            ("fecha", "Fecha", 90, "center"),
            ("monto", "Monto prestado", 130, "e"),
            ("total", "Total a pagar", 130, "e"),
            ("saldo", "Saldo pendiente", 130, "e"),
            ("cuotas", "Cuotas pagadas", 100, "center"),
            ("estado", "Estado", 90, "center"),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor=alineacion)
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("cancelado", foreground="#1b7f3b")
        self.tabla.tag_configure("anulado", foreground="gray")

        # --- Botones ---
        botones = ttk.Frame(self, padding=10)
        botones.pack(fill="x")
        self.btn_nuevo = ttk.Button(botones, text="Nuevo préstamo", command=self.nuevo)
        self.btn_nuevo.pack(side="left", padx=5)
        if not Sesion.tiene_permiso("prestamos_crear"):
            self.btn_nuevo.state(["disabled"])
        ttk.Button(botones, text="Ver plan de cuotas", command=self.ver_plan).pack(side="left", padx=5)
        self.btn_anular = ttk.Button(botones, text="Anular préstamo", command=self.anular)
        self.btn_anular.pack(side="left", padx=5)
        if not Sesion.tiene_permiso("anular"):
            self.btn_anular.state(["disabled"])
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=5)

        self.cargar()

    def cargar(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        prestamos = prestamos_servicio.listar_prestamos(self.var_busqueda.get(), self.var_cerrados.get())
        for p in prestamos:
            etiquetas = (p["estado"],) if p["estado"] in ("cancelado", "anulado") else ()
            self.tabla.insert(
                "", "end", iid=str(p["id"]), tags=etiquetas,
                values=(p["nombre"], p["fecha_desembolso"].strftime("%d/%m/%Y"),
                        gs(p["monto_prestado"]), gs(p["total_a_pagar"]), gs(p["saldo_pendiente"]),
                        f"{p['cuotas_pagadas']}/{p['cantidad_cuotas']}", p["estado"].capitalize()),
            )

    def _prestamo_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Préstamos", "Seleccione un préstamo de la lista.", parent=self)
            return None
        return int(seleccion[0])

    def nuevo(self):
        try:
            socios = prestamos_servicio.socios_elegibles()
        except ErrorDeNegocio as e:
            messagebox.showerror("Préstamos", str(e), parent=self)
            return
        if not socios:
            messagebox.showinfo(
                "Préstamos",
                "No hay socios disponibles: todos tienen un préstamo activo o no hay socios activos.",
                parent=self)
            return
        PrestamoFormulario(self, socios, self.cargar)

    def ver_plan(self):
        prestamo_id = self._prestamo_seleccionado()
        if prestamo_id is None:
            return
        socio = self.tabla.item(str(prestamo_id), "values")[0]
        PlanCuotasVentana(self, prestamo_id, socio)

    def anular(self):
        prestamo_id = self._prestamo_seleccionado()
        if prestamo_id is None:
            return
        motivo = simpledialog.askstring("Anular préstamo", "Motivo de la anulación:", parent=self)
        if motivo is None:
            return
        try:
            prestamos_servicio.anular_prestamo(prestamo_id, motivo)
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo anular", str(e), parent=self)
            return
        self.cargar()


class PrestamoFormulario(tk.Toplevel):
    def __init__(self, master, socios, al_guardar):
        super().__init__(master)
        self.socios = socios
        self.al_guardar = al_guardar
        self.title("Nuevo préstamo")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack()

        ttk.Label(cuerpo, text="Socio:").grid(row=0, column=0, sticky="e", padx=5, pady=6)
        etiquetas = [f"{s['nombre']} — {s['telefono']}" for s in socios]
        self.combo = ttk.Combobox(cuerpo, values=etiquetas, state="readonly", width=38)
        self.combo.grid(row=0, column=1, columnspan=2, pady=6, sticky="w")

        ttk.Label(cuerpo, text="Monto (Gs):").grid(row=1, column=0, sticky="e", padx=5, pady=6)
        self.var_monto = tk.StringVar()
        ttk.Entry(cuerpo, textvariable=self.var_monto, width=20).grid(row=1, column=1, pady=6, sticky="w")

        max_cuotas = configuracion_servicio.obtener_max_cuotas()
        ttk.Label(cuerpo, text="Cantidad de cuotas:").grid(row=2, column=0, sticky="e", padx=5, pady=6)
        self.var_cuotas = tk.StringVar(value="1")
        ttk.Spinbox(cuerpo, from_=1, to=max_cuotas, textvariable=self.var_cuotas,
                    width=8).grid(row=2, column=1, pady=6, sticky="w")

        ttk.Label(cuerpo, text="Fecha del préstamo:").grid(row=3, column=0, sticky="e", padx=5, pady=6)
        self.var_fecha = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ttk.Entry(cuerpo, textvariable=self.var_fecha, width=20).grid(row=3, column=1, pady=6, sticky="w")

        maximo = configuracion_servicio.obtener_monto_maximo_prestamo()
        ttk.Label(cuerpo, text=f"Máximo: {gs(maximo)}  ·  Fecha en formato DD/MM/AAAA",
                  foreground="gray").grid(row=4, column=0, columnspan=3, pady=(2, 8))

        ttk.Button(cuerpo, text="Calcular plan de pagos", command=self.calcular).grid(
            row=5, column=0, columnspan=3, pady=(0, 8))

        self.lbl_resultado = ttk.Label(cuerpo, text="", justify="left")
        self.lbl_resultado.grid(row=6, column=0, columnspan=3, sticky="w")

        marco = ttk.Frame(cuerpo)
        marco.grid(row=7, column=0, columnspan=3, pady=8)
        self.tabla = ttk.Treeview(marco, columns=("n", "venc", "monto"), show="headings", height=7)
        for columna, titulo, ancho in (("n", "Cuota", 60), ("venc", "Vencimiento", 130), ("monto", "Monto", 160)):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="center")
        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left")
        scroll.pack(side="right", fill="y")

        botones = ttk.Frame(cuerpo)
        botones.grid(row=8, column=0, columnspan=3, pady=(8, 0))
        self.btn_guardar = ttk.Button(botones, text="Guardar préstamo", command=self.guardar)
        self.btn_guardar.pack(side="left", padx=5)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)

    def calcular(self):
        """Muestra el plan de pagos. Devuelve el plan, o None si los datos no son validos."""
        try:
            plan = prestamos_servicio.simular(
                self.var_monto.get(), self.var_cuotas.get(), self.var_fecha.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("Datos no válidos", str(e), parent=self)
            return None

        self.lbl_resultado.config(
            text=f"Capital: {gs(plan['monto'])}\n"
                 f"Interés ({float(plan['porcentaje']):g} %): {gs(plan['interes'])}\n"
                 f"Total a pagar: {gs(plan['total'])}")
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        for c in plan["cuotas"]:
            self.tabla.insert("", "end", values=(
                c["numero"], c["vencimiento"].strftime("%d/%m/%Y"), gs(c["monto"])))
        return plan

    def guardar(self):
        indice = self.combo.current()
        if indice < 0:
            messagebox.showinfo("Nuevo préstamo", "Seleccione un socio.", parent=self)
            return
        plan = self.calcular()  # recalcula con lo que hay escrito ahora mismo
        if plan is None:
            return

        socio = self.socios[indice]
        confirmar = messagebox.askyesno(
            "Confirmar préstamo",
            f"Socio: {socio['nombre']}\n"
            f"Monto: {gs(plan['monto'])}\n"
            f"Cuotas: {len(plan['cuotas'])}\n"
            f"Total a pagar: {gs(plan['total'])}\n\n"
            "¿Desea registrar el préstamo?",
            parent=self)
        if not confirmar:
            return

        self.btn_guardar.state(["disabled"])  # evita registrar dos veces con doble clic
        try:
            prestamos_servicio.crear_prestamo(
                socio["id"], self.var_monto.get(), self.var_cuotas.get(), self.var_fecha.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo registrar", str(e), parent=self)
            self.btn_guardar.state(["!disabled"])
            return
        messagebox.showinfo("Préstamo registrado", "El préstamo se registró correctamente.", parent=self)
        self.al_guardar()
        self.destroy()


class PlanCuotasVentana(tk.Toplevel):
    def __init__(self, master, prestamo_id, socio):
        super().__init__(master)
        self.title(f"Plan de cuotas — {socio}")
        self.geometry("640x420")
        self.transient(master)

        contenedor = ttk.Frame(self, padding=10)
        contenedor.pack(fill="both", expand=True)
        columnas = ("n", "venc", "monto", "pagado", "estado")
        tabla = ttk.Treeview(contenedor, columns=columnas, show="headings")
        for columna, titulo, ancho in (
            ("n", "Cuota", 60), ("venc", "Vencimiento", 120), ("monto", "Monto", 130),
            ("pagado", "Pagado", 130), ("estado", "Estado", 100),
        ):
            tabla.heading(columna, text=titulo)
            tabla.column(columna, width=ancho, anchor="center")
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        tabla.tag_configure("pagada", foreground="#1b7f3b")
        tabla.tag_configure("vencida", foreground="#b00020")

        for c in prestamos_servicio.obtener_cuotas(prestamo_id):
            if c["estado"] == "pagada":
                estado, etiqueta = "Pagada", "pagada"
            elif c["vencida"]:
                estado, etiqueta = "Vencida", "vencida"
            else:
                estado, etiqueta = "Pendiente", ""
            tabla.insert("", "end", tags=(etiqueta,), values=(
                c["numero_cuota"], c["fecha_vencimiento"].strftime("%d/%m/%Y"),
                gs(c["monto_cuota"]), gs(c["monto_pagado"]), estado))

        ttk.Button(self, text="Cerrar", command=self.destroy).pack(pady=(0, 10))