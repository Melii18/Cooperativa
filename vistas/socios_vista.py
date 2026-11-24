import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox

from servicios import socios_servicio
from servicios.sesion import Sesion
from utils.errores import ErrorDeNegocio


class SociosVentana(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Socios")
        self.geometry("780x500")
        self.transient(master)

        # --- Barra de busqueda ---
        barra = ttk.Frame(self, padding=10)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar:").pack(side="left")
        self.var_busqueda = tk.StringVar()
        ttk.Entry(barra, textvariable=self.var_busqueda, width=30).pack(side="left", padx=5)
        self.var_busqueda.trace_add("write", lambda *args: self.cargar())
        self.var_inactivos = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="Mostrar inactivos",
                        variable=self.var_inactivos, command=self.cargar).pack(side="left", padx=10)

        # --- Tabla ---
        contenedor = ttk.Frame(self)
        contenedor.pack(fill="both", expand=True, padx=10)
        columnas = ("nombre", "telefono", "cedula", "ingreso", "estado")
        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for columna, titulo, ancho in (
            ("nombre", "Nombre y apellido", 260),
            ("telefono", "Teléfono", 130),
            ("cedula", "Cédula", 110),
            ("ingreso", "Ingreso", 100),
            ("estado", "Estado", 80),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho)
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("inactivo", foreground="gray")
        self.tabla.bind("<Double-1>", lambda evento: self.editar())

        # --- Botones ---
        botones = ttk.Frame(self, padding=10)
        botones.pack(fill="x")
        acciones = [
            ("Nuevo socio", self.nuevo),
            ("Editar", self.editar),
            ("Dar de baja / Reactivar", self.cambiar_estado),
        ]
        for texto, comando in acciones:
            boton = ttk.Button(botones, text=texto, command=comando)
            boton.pack(side="left", padx=5)
            if not Sesion.tiene_permiso("socios_editar"):
                boton.state(["disabled"])
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=5)

        self.cargar()

    def cargar(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        socios = socios_servicio.listar(self.var_busqueda.get(), self.var_inactivos.get())
        for s in socios:
            etiquetas = ("inactivo",) if s["estado"] == "inactivo" else ()
            self.tabla.insert(
                "", "end", iid=str(s["id"]), tags=etiquetas,
                values=(s["nombre"], s["telefono"], s["cedula"] or "—",
                        s["fecha_ingreso"].strftime("%d/%m/%Y"), s["estado"].capitalize()),
            )

    def _socio_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Socios", "Seleccione un socio de la lista.", parent=self)
            return None
        return int(seleccion[0])

    def nuevo(self):
        SocioFormulario(self, None, self.cargar)

    def editar(self):
        if not Sesion.tiene_permiso("socios_editar"):
            return
        socio_id = self._socio_seleccionado()
        if socio_id is not None:
            SocioFormulario(self, socio_id, self.cargar)

    def cambiar_estado(self):
        socio_id = self._socio_seleccionado()
        if socio_id is None:
            return
        socio = socios_servicio.obtener(socio_id)
        nuevo_estado = "inactivo" if socio["estado"] == "activo" else "activo"
        accion = "dar de baja a" if nuevo_estado == "inactivo" else "reactivar a"
        if not messagebox.askyesno("Confirmar", f"¿Desea {accion} {socio['nombre']}?", parent=self):
            return
        try:
            socios_servicio.cambiar_estado(socio_id, nuevo_estado)
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo completar", str(e), parent=self)
            return
        self.cargar()


class SocioFormulario(tk.Toplevel):
    def __init__(self, master, socio_id, al_guardar):
        super().__init__(master)
        self.socio_id = socio_id
        self.al_guardar = al_guardar
        self.title("Nuevo socio" if socio_id is None else "Editar socio")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()  # ventana modal: bloquea la de atras hasta cerrar esta

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack()

        self.var_nombre = tk.StringVar()
        self.var_telefono = tk.StringVar()
        self.var_cedula = tk.StringVar()
        self.var_ingreso = tk.StringVar()

        campos = [
            ("Nombre y apellido *", self.var_nombre),
            ("Teléfono *", self.var_telefono),
            ("Cédula (opcional)", self.var_cedula),
            ("Fecha de ingreso *", self.var_ingreso),
        ]
        primera_entrada = None
        for i, (etiqueta, variable) in enumerate(campos):
            ttk.Label(cuerpo, text=etiqueta).grid(row=i, column=0, sticky="e", padx=5, pady=6)
            entrada = ttk.Entry(cuerpo, textvariable=variable, width=32)
            entrada.grid(row=i, column=1, pady=6)
            if primera_entrada is None:
                primera_entrada = entrada

        ttk.Label(cuerpo, text="* obligatorio · Fecha en formato DD/MM/AAAA",
                  foreground="gray").grid(row=4, column=0, columnspan=2, pady=(5, 10))

        botones = ttk.Frame(cuerpo)
        botones.grid(row=5, column=0, columnspan=2)
        ttk.Button(botones, text="Guardar", command=self.guardar).pack(side="left", padx=5)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)

        if socio_id is None:
            self.var_ingreso.set(date.today().strftime("%d/%m/%Y"))
        else:
            socio = socios_servicio.obtener(socio_id)
            self.var_nombre.set(socio["nombre"])
            self.var_telefono.set(socio["telefono"])
            self.var_cedula.set(socio["cedula"] or "")
            self.var_ingreso.set(socio["fecha_ingreso"].strftime("%d/%m/%Y"))

        primera_entrada.focus()

    def guardar(self):
        datos = (self.var_nombre.get(), self.var_telefono.get(),
                 self.var_cedula.get(), self.var_ingreso.get())
        try:
            if self.socio_id is None:
                socios_servicio.crear(*datos)
            else:
                socios_servicio.actualizar(self.socio_id, *datos)
        except ErrorDeNegocio as e:
            messagebox.showerror("Datos no válidos", str(e), parent=self)
            return
        self.al_guardar()
        self.destroy()