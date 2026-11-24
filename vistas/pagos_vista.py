import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox, simpledialog

from servicios import pagos_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorDeNegocio
from utils.validadores import formatear_guaranies


def gs(valor):
    return f"{formatear_guaranies(valor)} Gs"


class PagosVentana(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Pagos de préstamos")
        self.geometry("980x540")
        self.transient(master)

        # --- Barra superior ---
        barra = ttk.Frame(self, padding=10)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar socio:").pack(side="left")
        self.var_busqueda = tk.StringVar()
        ttk.Entry(barra, textvariable=self.var_busqueda, width=30).pack(side="left", padx=5)
        self.var_busqueda.trace_add("write", lambda *args: self.cargar())

        # --- Tabla ---
        contenedor = ttk.Frame(self)
        contenedor.pack(fill="both", expand=True, padx=10)
        columnas = ("socio", "saldo", "vencidas", "vencido", "proximo", "estado")
        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for columna, titulo, ancho, alineacion in (
            ("socio", "Socio", 240, "w"),
            ("saldo", "Saldo pendiente", 140, "e"),
            ("vencidas", "Cuotas vencidas", 110, "center"),
            ("vencido", "Monto vencido", 140, "e"),
            ("proximo", "Vence (próxima cuota)", 150, "center"),
            ("estado", "Estado", 100, "center"),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor=alineacion)
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("atrasado", foreground="#b00020")
        self.tabla.tag_configure("aldia", foreground="#1b7f3b")

        self.lbl_resumen = ttk.Label(self, padding=(10, 8))
        self.lbl_resumen.pack(fill="x")

        # --- Botones ---
        botones = ttk.Frame(self, padding=10)
        botones.pack(fill="x")
        self.btn_registrar = ttk.Button(botones, text="Registrar pago", command=self.registrar)
        self.btn_registrar.pack(side="left", padx=5)
        if not Sesion.tiene_permiso("pagos_registrar"):
            self.btn_registrar.state(["disabled"])
        ttk.Button(botones, text="Ver pagos del préstamo", command=self.ver_pagos).pack(side="left", padx=5)
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=5)

        self.cargar()

    def cargar(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)

        atrasados = total_saldo = total_vencido = 0
        for r in pagos_servicio.resumen_prestamos_activos(self.var_busqueda.get()):
            atrasado = r["cuotas_vencidas"] > 0
            if atrasado:
                atrasados += 1
            total_saldo += r["saldo"]
            total_vencido += r["monto_vencido"]
            proximo = r["proximo_vencimiento"].strftime("%d/%m/%Y") if r["proximo_vencimiento"] else "—"
            self.tabla.insert(
                "", "end", iid=str(r["id"]), tags=("atrasado" if atrasado else "aldia",),
                values=(r["nombre"], gs(r["saldo"]), r["cuotas_vencidas"], gs(r["monto_vencido"]),
                        proximo, "Atrasado" if atrasado else "Al día"),
            )

        self.lbl_resumen.config(
            text=f"Préstamos con atraso: {atrasados}   ·   Saldo total por cobrar: {gs(total_saldo)}"
                 f"   ·   Total vencido: {gs(total_vencido)}"
        )

    def _prestamo_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Pagos", "Seleccione un préstamo de la lista.", parent=self)
            return None
        return int(seleccion[0])

    def registrar(self):
        prestamo_id = self._prestamo_seleccionado()
        if prestamo_id is None:
            return
        try:
            datos = pagos_servicio.datos_para_pago(prestamo_id)
        except ErrorDeNegocio as e:
            messagebox.showerror("Pagos", str(e), parent=self)
            return
        PagoFormulario(self, prestamo_id, datos, self.cargar)

    def ver_pagos(self):
        prestamo_id = self._prestamo_seleccionado()
        if prestamo_id is None:
            return
        socio = self.tabla.item(str(prestamo_id), "values")[0]
        PagosPrestamoVentana(self, prestamo_id, socio, self.cargar)


class PagoFormulario(tk.Toplevel):
    def __init__(self, master, prestamo_id, datos, al_guardar):
        super().__init__(master)
        self.prestamo_id = prestamo_id
        self.datos = datos
        self.al_guardar = al_guardar
        self.title("Registrar pago")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack()

        ttk.Label(cuerpo, text=datos["socio"], font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 4))
        ttk.Label(
            cuerpo,
            text=f"Saldo pendiente: {gs(datos['saldo'])}   ·   "
                 f"Vencido: {gs(datos['monto_vencido'])} ({datos['cuotas_vencidas']} cuotas)",
        ).grid(row=1, column=0, columnspan=2, pady=(0, 12))

        ttk.Label(cuerpo, text="Monto entregado (Gs):").grid(row=2, column=0, sticky="e", padx=5, pady=6)
        self.var_monto = tk.StringVar()
        entrada_monto = ttk.Entry(cuerpo, textvariable=self.var_monto, width=22)
        entrada_monto.grid(row=2, column=1, sticky="w", pady=6)

        atajos = ttk.Frame(cuerpo)
        atajos.grid(row=3, column=1, sticky="w")
        ttk.Button(atajos, text="Próxima cuota",
                   command=lambda: self.llenar(datos["proxima_cuota"])).pack(side="left", padx=(0, 4))
        btn_vencido = ttk.Button(atajos, text="Monto vencido",
                                 command=lambda: self.llenar(datos["monto_vencido"]))
        btn_vencido.pack(side="left", padx=4)
        if datos["monto_vencido"] == 0:
            btn_vencido.state(["disabled"])
        ttk.Button(atajos, text="Saldo total",
                   command=lambda: self.llenar(datos["saldo"])).pack(side="left", padx=4)

        ttk.Label(cuerpo, text="N° de recibo:").grid(row=4, column=0, sticky="e", padx=5, pady=6)
        self.var_recibo = tk.StringVar()
        ttk.Entry(cuerpo, textvariable=self.var_recibo, width=22).grid(row=4, column=1, sticky="w", pady=6)

        ttk.Label(cuerpo, text="Fecha de pago:").grid(row=5, column=0, sticky="e", padx=5, pady=6)
        self.var_fecha = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ttk.Entry(cuerpo, textvariable=self.var_fecha, width=22).grid(row=5, column=1, sticky="w", pady=6)

        ttk.Label(cuerpo, text="Fecha en formato DD/MM/AAAA. El pago se aplica a las cuotas más antiguas primero.",
                  foreground="gray").grid(row=6, column=0, columnspan=2, pady=(2, 8))

        ttk.Button(cuerpo, text="Ver cómo se aplica el pago", command=self.calcular).grid(
            row=7, column=0, columnspan=2, pady=(0, 8))

        marco = ttk.Frame(cuerpo)
        marco.grid(row=8, column=0, columnspan=2)
        self.tabla = ttk.Treeview(
            marco, columns=("n", "venc", "antes", "aplica", "queda", "tipo"), show="headings", height=6)
        for columna, titulo, ancho in (
            ("n", "Cuota", 55), ("venc", "Vencimiento", 100), ("antes", "Pendiente", 110),
            ("aplica", "Se paga", 110), ("queda", "Queda", 110), ("tipo", "Tipo", 90),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="center")
        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left")
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("vencida", foreground="#b00020")
        self.tabla.tag_configure("adelantada", foreground="#1a5fb4")

        self.lbl_resultado = ttk.Label(cuerpo, text="")
        self.lbl_resultado.grid(row=9, column=0, columnspan=2, pady=8)

        botones = ttk.Frame(cuerpo)
        botones.grid(row=10, column=0, columnspan=2)
        self.btn_guardar = ttk.Button(botones, text="Guardar pago", command=self.guardar)
        self.btn_guardar.pack(side="left", padx=5)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)

        entrada_monto.focus()

    def llenar(self, valor):
        self.var_monto.set(formatear_guaranies(valor))

    def calcular(self):
        """Muestra la distribucion. Devuelve la simulacion, o None si el monto no es valido."""
        try:
            sim = pagos_servicio.simular_pago(self.prestamo_id, self.var_monto.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("Datos no válidos", str(e), parent=self)
            return None

        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        for r in sim["reparto"]:
            self.tabla.insert(
                "", "end", tags=(r["tipo"].lower(),),
                values=(r["numero"], r["vencimiento"].strftime("%d/%m/%Y"),
                        gs(r["pendiente_antes"]), gs(r["aplicado"]),
                        gs(r["pendiente_despues"]), r["tipo"]))

        texto = f"Saldo después del pago: {gs(sim['saldo_final'])}"
        if sim["cancela"]:
            texto += "   ·   El préstamo quedará CANCELADO"
        self.lbl_resultado.config(text=texto)
        return sim

    def guardar(self):
        sim = self.calcular()  # recalcula con lo que esta escrito ahora mismo
        if sim is None:
            return

        confirmar = messagebox.askyesno(
            "Confirmar pago",
            f"Socio: {self.datos['socio']}\n"
            f"Monto: {gs(sim['monto'])}\n"
            f"Cuotas afectadas: {len(sim['reparto'])}\n"
            f"Saldo después del pago: {gs(sim['saldo_final'])}\n\n"
            "¿Desea registrar el pago?",
            parent=self)
        if not confirmar:
            return

        self.btn_guardar.state(["disabled"])  # evita registrar dos veces con doble clic
        try:
            resultado = pagos_servicio.registrar_pago(
                self.prestamo_id, self.var_monto.get(), self.var_recibo.get(), self.var_fecha.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo registrar", str(e), parent=self)
            self.btn_guardar.state(["!disabled"])
            return

        if resultado["cancelado"]:
            mensaje = "Pago registrado. El préstamo quedó CANCELADO."
        else:
            mensaje = f"Pago registrado. Saldo pendiente: {gs(resultado['nuevo_saldo'])}"
        messagebox.showinfo("Pago registrado", mensaje, parent=self)
        self.al_guardar()
        self.destroy()


class PagosPrestamoVentana(tk.Toplevel):
    def __init__(self, master, prestamo_id, socio, al_cambiar):
        super().__init__(master)
        self.prestamo_id = prestamo_id
        self.al_cambiar = al_cambiar
        self.filas = {}
        self.title(f"Pagos de {socio}")
        self.geometry("620x400")
        self.transient(master)

        contenedor = ttk.Frame(self, padding=10)
        contenedor.pack(fill="both", expand=True)
        self.tabla = ttk.Treeview(
            contenedor, columns=("recibo", "fecha", "cuotas", "monto", "estado"),
            show="headings", selectmode="browse")
        for columna, titulo, ancho in (
            ("recibo", "Recibo", 110), ("fecha", "Fecha", 100), ("cuotas", "Cuotas", 120),
            ("monto", "Monto", 130), ("estado", "Estado", 90),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="center")
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("anulado", foreground="gray")

        botones = ttk.Frame(self, padding=10)
        botones.pack(fill="x")
        self.btn_anular = ttk.Button(botones, text="Anular pago", command=self.anular)
        self.btn_anular.pack(side="left", padx=5)
        if not Sesion.tiene_permiso("anular"):
            self.btn_anular.state(["disabled"])
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=5)

        self.cargar()

    def cargar(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        self.filas = {}
        for i, p in enumerate(pagos_servicio.listar_pagos_prestamo(self.prestamo_id)):
            iid = str(i)
            self.filas[iid] = p
            etiquetas = ("anulado",) if p["estado"] == "anulado" else ()
            self.tabla.insert(
                "", "end", iid=iid, tags=etiquetas,
                values=(p["nro_recibo"], p["fecha_pago"].strftime("%d/%m/%Y"), p["cuotas"],
                        gs(p["monto"]), p["estado"].capitalize()))

    def anular(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Pagos", "Seleccione el pago a anular.", parent=self)
            return
        pago = self.filas[seleccion[0]]
        if pago["estado"] == "anulado":
            messagebox.showinfo("Pagos", "Este pago ya está anulado.", parent=self)
            return
        motivo = simpledialog.askstring(
            "Anular pago", f"Motivo de la anulación del recibo {pago['nro_recibo']}:", parent=self)
        if motivo is None:
            return
        try:
            pagos_servicio.anular_pago(self.prestamo_id, pago["nro_recibo"], motivo)
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo anular", str(e), parent=self)
            return
        self.cargar()
        self.al_cambiar()