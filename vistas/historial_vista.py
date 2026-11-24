import tkinter as tk
from tkinter import ttk, messagebox

from servicios import historial_servicio
from utils.errores import ErrorDeNegocio
from utils.validadores import parsear_fecha

TODOS = "(todos)"  # tiene parentesis para que no se confunda con un nombre de usuario real
ACCIONES_ALERTA = {
    "LOGIN_FALLIDO", "BAJA_SOCIO", "CAMBIAR_PASSWORD_FALLIDO",
    "DESACTIVAR_USUARIO", "RESTABLECER_PASSWORD",
}


class HistorialVentana(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Historial de movimientos")
        self.geometry("1120x640")
        self.transient(master)
        self.filas = {}

        # --- Filtros ---
        filtros = ttk.LabelFrame(self, text="Filtros", padding=10)
        filtros.pack(fill="x", padx=10, pady=(10, 0))

        self.usuarios = {u["nombre_usuario"]: u["id"] for u in historial_servicio.listar_usuarios()}
        self.acciones = {etiqueta: codigo for codigo, etiqueta in historial_servicio.listar_acciones()}

        ttk.Label(filtros, text="Usuario:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.var_usuario = tk.StringVar(value=TODOS)
        ttk.Combobox(filtros, textvariable=self.var_usuario, state="readonly", width=20,
                     values=[TODOS] + sorted(self.usuarios)).grid(row=0, column=1, padx=4)

        ttk.Label(filtros, text="Acción:").grid(row=0, column=2, sticky="e", padx=4)
        self.var_accion = tk.StringVar(value=TODOS)
        ttk.Combobox(filtros, textvariable=self.var_accion, state="readonly", width=26,
                     values=[TODOS] + sorted(self.acciones)).grid(row=0, column=3, padx=4)

        ttk.Label(filtros, text="Buscar en el detalle:").grid(row=0, column=4, sticky="e", padx=4)
        self.var_texto = tk.StringVar()
        entrada_texto = ttk.Entry(filtros, textvariable=self.var_texto, width=26)
        entrada_texto.grid(row=0, column=5, padx=4)
        entrada_texto.bind("<Return>", lambda evento: self.buscar())

        ttk.Label(filtros, text="Desde:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.var_desde = tk.StringVar()
        ttk.Entry(filtros, textvariable=self.var_desde, width=14).grid(row=1, column=1, sticky="w", padx=4)

        ttk.Label(filtros, text="Hasta:").grid(row=1, column=2, sticky="e", padx=4)
        self.var_hasta = tk.StringVar()
        ttk.Entry(filtros, textvariable=self.var_hasta, width=14).grid(row=1, column=3, sticky="w", padx=4)

        ttk.Label(filtros, text="Fechas en formato DD/MM/AAAA (opcionales)",
                  foreground="gray").grid(row=1, column=4, sticky="e", padx=4)

        botones = ttk.Frame(filtros)
        botones.grid(row=1, column=5, sticky="w", padx=4)
        ttk.Button(botones, text="Buscar", command=self.buscar).pack(side="left", padx=(0, 6))
        ttk.Button(botones, text="Limpiar", command=self.limpiar).pack(side="left")

        # --- Tabla ---
        contenedor = ttk.Frame(self)
        contenedor.pack(fill="both", expand=True, padx=10, pady=10)
        columnas = ("fecha", "usuario", "accion", "detalle")
        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for columna, titulo, ancho in (
            ("fecha", "Fecha y hora", 150), ("usuario", "Usuario", 120),
            ("accion", "Acción", 190), ("detalle", "Detalle", 600),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="w")
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("alerta", foreground="#b00020")
        self.tabla.bind("<<TreeviewSelect>>", self.mostrar_detalle)

        # --- Detalle del movimiento seleccionado ---
        marco = ttk.LabelFrame(self, text="Detalle del movimiento", padding=8)
        marco.pack(fill="x", padx=10)
        self.texto_detalle = tk.Text(marco, height=5, wrap="word", state="disabled", relief="flat")
        self.texto_detalle.pack(fill="x")

        self.lbl_resumen = ttk.Label(self, padding=(10, 8))
        self.lbl_resumen.pack(fill="x")
        ttk.Button(self, text="Cerrar", command=self.destroy).pack(pady=(0, 10))

        self.buscar()

    @staticmethod
    def _fecha(texto, nombre):
        texto = texto.strip()
        return parsear_fecha(texto, nombre) if texto else None

    def buscar(self):
        try:
            desde = self._fecha(self.var_desde.get(), "La fecha 'desde'")
            hasta = self._fecha(self.var_hasta.get(), "La fecha 'hasta'")
            resultado = historial_servicio.consultar(
                usuario_id=self.usuarios.get(self.var_usuario.get()),
                accion=self.acciones.get(self.var_accion.get()),
                desde=desde, hasta=hasta, texto=self.var_texto.get(),
            )
        except ErrorDeNegocio as e:
            messagebox.showerror("Historial", str(e), parent=self)
            return

        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        self.filas = {}
        self._escribir_detalle("")

        for r in resultado["filas"]:
            iid = str(r["id"])
            self.filas[iid] = r
            alerta = r["accion"].startswith("ANULAR") or r["accion"] in ACCIONES_ALERTA
            self.tabla.insert(
                "", "end", iid=iid, tags=("alerta",) if alerta else (),
                values=(r["fecha_hora"].strftime("%d/%m/%Y %H:%M:%S"), r["usuario"],
                        r["accion_texto"], r["detalle"] or ""),
            )

        cantidad = len(resultado["filas"])
        if resultado["hay_mas"]:
            self.lbl_resumen.config(
                text=f"Mostrando los últimos {cantidad} movimientos. Hay más: use los filtros para acotar la búsqueda.")
        elif cantidad == 0:
            self.lbl_resumen.config(text="No se encontraron movimientos con esos filtros.")
        else:
            self.lbl_resumen.config(text=f"{cantidad} movimientos encontrados.")

    def limpiar(self):
        self.var_usuario.set(TODOS)
        self.var_accion.set(TODOS)
        self.var_texto.set("")
        self.var_desde.set("")
        self.var_hasta.set("")
        self.buscar()

    def _escribir_detalle(self, texto):
        self.texto_detalle.config(state="normal")
        self.texto_detalle.delete("1.0", "end")
        self.texto_detalle.insert("1.0", texto)
        self.texto_detalle.config(state="disabled")

    def mostrar_detalle(self, evento=None):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        r = self.filas[seleccion[0]]
        registro = r["registro_id"] if r["registro_id"] is not None else "—"
        self._escribir_detalle(
            f"{r['accion_texto']}  ·  {r['fecha_hora'].strftime('%d/%m/%Y %H:%M:%S')}  ·  Usuario: {r['usuario']}\n"
            f"Tabla: {r['tabla_afectada']}  ·  Registro N° {registro}\n\n"
            f"{r['detalle'] or '(sin detalle)'}"
        )