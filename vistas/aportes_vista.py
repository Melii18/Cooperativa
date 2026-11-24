import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox, simpledialog

from servicios import aportes_servicio, configuracion_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorDeNegocio
from utils.validadores import formatear_guaranies


class AportesVentana(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Aportes mensuales")
        self.geometry("920x540")
        self.transient(master)

        # --- Barra superior ---
        barra = ttk.Frame(self, padding=10)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar:").pack(side="left")
        self.var_busqueda = tk.StringVar()
        ttk.Entry(barra, textvariable=self.var_busqueda, width=30).pack(side="left", padx=5)
        self.var_busqueda.trace_add("write", lambda *args: self.cargar())
        self.lbl_minimo = ttk.Label(barra, font=("Segoe UI", 10, "bold"))
        self.lbl_minimo.pack(side="right")

        # --- Tabla ---
        contenedor = ttk.Frame(self)
        contenedor.pack(fill="both", expand=True, padx=10)
        columnas = ("nombre", "telefono", "pendientes", "deuda", "total", "estado")
        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for columna, titulo, ancho, alineacion in (
            ("nombre", "Nombre y apellido", 230, "w"),
            ("telefono", "Teléfono", 110, "w"),
            ("pendientes", "Meses pendientes", 115, "center"),
            ("deuda", "Deuda mínima", 125, "e"),
            ("total", "Total aportado", 135, "e"),
            ("estado", "Estado", 110, "center"),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor=alineacion)
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("pendiente", foreground="#b00020")
        self.tabla.tag_configure("aldia", foreground="#1b7f3b")

        # --- Resumen ---
        self.lbl_resumen = ttk.Label(self, padding=(10, 8))
        self.lbl_resumen.pack(fill="x")

        # --- Botones ---
        botones = ttk.Frame(self, padding=10)
        botones.pack(fill="x")
        self.btn_registrar = ttk.Button(botones, text="Registrar aporte", command=self.registrar)
        self.btn_registrar.pack(side="left", padx=5)
        if not Sesion.tiene_permiso("aportes_registrar"):
            self.btn_registrar.state(["disabled"])
        ttk.Button(botones, text="Ver aportes del socio", command=self.ver_detalle).pack(side="left", padx=5)
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=5)

        self.cargar()

    def cargar(self):
        minimo = configuracion_servicio.obtener_aporte_minimo()
        self.lbl_minimo.config(text=f"Aporte mínimo: {formatear_guaranies(minimo)} Gs")

        for fila in self.tabla.get_children():
            self.tabla.delete(fila)

        al_dia = con_pendientes = deuda_total = 0
        for r in aportes_servicio.resumen_por_socio(self.var_busqueda.get()):
            if r["meses_pendientes"] == 0:
                estado, etiqueta = "Al día", "aldia"
                al_dia += 1
            else:
                estado, etiqueta = "Con pendientes", "pendiente"
                con_pendientes += 1
            deuda_total += r["deuda"]
            self.tabla.insert(
                "", "end", iid=str(r["id"]), tags=(etiqueta,),
                values=(r["nombre"], r["telefono"], r["meses_pendientes"],
                        f"{formatear_guaranies(r['deuda'])} Gs",
                        f"{formatear_guaranies(r['total_aportado'])} Gs", estado),
            )

        self.lbl_resumen.config(
            text=f"Al día: {al_dia}   ·   Con pendientes: {con_pendientes}   ·   "
                 f"Deuda mínima total: {formatear_guaranies(deuda_total)} Gs"
        )

    def _socio_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Aportes", "Seleccione un socio de la lista.", parent=self)
            return None
        return int(seleccion[0])

    def registrar(self):
        socio_id = self._socio_seleccionado()
        if socio_id is None:
            return
        try:
            disponibles = aportes_servicio.meses_disponibles(socio_id)
        except ErrorDeNegocio as e:
            messagebox.showerror("Aportes", str(e), parent=self)
            return
        if not disponibles:
            messagebox.showinfo("Aportes", "No hay meses disponibles para registrar.", parent=self)
            return
        nombre = self.tabla.item(str(socio_id), "values")[0]
        AporteFormulario(self, socio_id, nombre, disponibles, self.cargar)

    def ver_detalle(self):
        socio_id = self._socio_seleccionado()
        if socio_id is None:
            return
        nombre = self.tabla.item(str(socio_id), "values")[0]
        DetalleAportesVentana(self, socio_id, nombre, self.cargar)


class AporteFormulario(tk.Toplevel):
    def __init__(self, master, socio_id, nombre, disponibles, al_guardar):
        super().__init__(master)
        self.socio_id = socio_id
        self.disponibles = disponibles
        self.al_guardar = al_guardar
        self.title("Registrar aporte")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack()
        ttk.Label(cuerpo, text=nombre, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 12))

        # Mes: primero los pendientes, despues los adelantados
        etiquetas = []
        for anio, mes, adelantado in disponibles:
            sufijo = "adelantado" if adelantado else "pendiente"
            etiquetas.append(f"{aportes_servicio.etiqueta_mes(anio, mes)} ({sufijo})")

        ttk.Label(cuerpo, text="Mes a pagar:").grid(row=1, column=0, sticky="e", padx=5, pady=6)
        self.var_mes = tk.StringVar(value=etiquetas[0])
        self.combo = ttk.Combobox(cuerpo, textvariable=self.var_mes, values=etiquetas,
                                  state="readonly", width=30)
        self.combo.grid(row=1, column=1, pady=6)

        ttk.Label(cuerpo, text="Monto (Gs):").grid(row=2, column=0, sticky="e", padx=5, pady=6)
        self.var_monto = tk.StringVar()  # vacio: lo escribe quien registra
        entrada_monto = ttk.Entry(cuerpo, textvariable=self.var_monto, width=32)
        entrada_monto.grid(row=2, column=1, pady=6)

        ttk.Label(cuerpo, text="Fecha de pago:").grid(row=3, column=0, sticky="e", padx=5, pady=6)
        self.var_fecha = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ttk.Entry(cuerpo, textvariable=self.var_fecha, width=32).grid(row=3, column=1, pady=6)

        minimo = configuracion_servicio.obtener_aporte_minimo()
        ttk.Label(
            cuerpo,
            text=f"Aporte mínimo: {formatear_guaranies(minimo)} Gs  ·  Fecha en formato DD/MM/AAAA",
            foreground="gray",
        ).grid(row=4, column=0, columnspan=2, pady=(5, 10))

        botones = ttk.Frame(cuerpo)
        botones.grid(row=5, column=0, columnspan=2)
        self.btn_guardar = ttk.Button(botones, text="Guardar", command=self.guardar)
        self.btn_guardar.pack(side="left", padx=5)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)

        entrada_monto.focus()

    def guardar(self):
        anio, mes, _ = self.disponibles[self.combo.current()]
        self.btn_guardar.state(["disabled"])  # evita guardar dos veces con doble clic
        try:
            aportes_servicio.registrar_aporte(
                self.socio_id, anio, mes, self.var_monto.get(), self.var_fecha.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo registrar", str(e), parent=self)
            self.btn_guardar.state(["!disabled"])
            return
        messagebox.showinfo("Aporte registrado", "El aporte se registró correctamente.", parent=self)
        self.al_guardar()
        self.destroy()


class DetalleAportesVentana(tk.Toplevel):
    def __init__(self, master, socio_id, nombre, al_cambiar):
        super().__init__(master)
        self.socio_id = socio_id
        self.al_cambiar = al_cambiar
        self.title(f"Aportes de {nombre}")
        self.geometry("560x400")
        self.transient(master)

        contenedor = ttk.Frame(self, padding=10)
        contenedor.pack(fill="both", expand=True)
        columnas = ("periodo", "monto", "fecha", "estado")
        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for columna, titulo, ancho in (
            ("periodo", "Período", 160), ("monto", "Monto", 120),
            ("fecha", "Fecha de pago", 120), ("estado", "Estado", 90),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho)
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("anulado", foreground="gray")

        botones = ttk.Frame(self, padding=10)
        botones.pack(fill="x")
        self.btn_anular = ttk.Button(botones, text="Anular aporte", command=self.anular)
        self.btn_anular.pack(side="left", padx=5)
        if not Sesion.tiene_permiso("anular"):
            self.btn_anular.state(["disabled"])
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=5)

        self.cargar()

    def cargar(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        for a in aportes_servicio.listar_aportes_socio(self.socio_id):
            etiquetas = ("anulado",) if a["estado"] == "anulado" else ()
            self.tabla.insert(
                "", "end", iid=str(a["id"]), tags=etiquetas,
                values=(aportes_servicio.etiqueta_mes(a["anio"], a["mes"]),
                        f"{formatear_guaranies(a['monto'])} Gs",
                        a["fecha_pago"].strftime("%d/%m/%Y"),
                        a["estado"].capitalize()),
            )

    def anular(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Aportes", "Seleccione el aporte a anular.", parent=self)
            return
        motivo = simpledialog.askstring("Anular aporte", "Motivo de la anulación:", parent=self)
        if motivo is None:  # el usuario cancelo
            return
        try:
            aportes_servicio.anular_aporte(int(seleccion[0]), motivo)
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo anular", str(e), parent=self)
            return
        self.cargar()
        self.al_cambiar()