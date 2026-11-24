import tkinter as tk
from tkinter import ttk, messagebox

from servicios import auth_servicio, usuarios_servicio
from servicios.auth_servicio import ROLES
from servicios.sesion import Sesion
from utils.errores import ErrorDeNegocio


class UsuariosVentana(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Usuarios")
        self.geometry("820x480")
        self.transient(master)
        self.usuarios = {}

        # --- Tabla ---
        contenedor = ttk.Frame(self, padding=10)
        contenedor.pack(fill="both", expand=True)
        columnas = ("usuario", "nombre", "rol", "estado", "creado")
        self.tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for columna, titulo, ancho in (
            ("usuario", "Usuario", 160), ("nombre", "Nombre completo", 250),
            ("rol", "Rol", 120), ("estado", "Estado", 90), ("creado", "Creado", 100),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor="w")
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tabla.tag_configure("inactivo", foreground="gray")

        # --- Botones ---
        botones = ttk.Frame(self, padding=10)
        botones.pack(fill="x")
        for texto, comando in (
            ("Nuevo usuario", self.nuevo),
            ("Cambiar rol", self.cambiar_rol),
            ("Activar / Desactivar", self.cambiar_estado),
            ("Restablecer contraseña", self.restablecer),
        ):
            ttk.Button(botones, text=texto, command=comando).pack(side="left", padx=5)
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="right", padx=5)

        self.cargar()

    def cargar(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        self.usuarios = {}
        for u in usuarios_servicio.listar_usuarios():
            iid = str(u["id"])
            self.usuarios[iid] = u
            nombre = u["nombre_usuario"] + ("  (usted)" if u["id"] == Sesion.id_usuario() else "")
            self.tabla.insert(
                "", "end", iid=iid, tags=() if u["activo"] else ("inactivo",),
                values=(nombre, u["nombre_completo"], u["rol"].capitalize(),
                        "Activo" if u["activo"] else "Inactivo",
                        u["creado_en"].strftime("%d/%m/%Y")),
            )

    def _seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showinfo("Usuarios", "Seleccione un usuario de la lista.", parent=self)
            return None
        return self.usuarios[seleccion[0]]

    def nuevo(self):
        NuevoUsuarioFormulario(self, self.cargar)

    def cambiar_rol(self):
        usuario = self._seleccionado()
        if usuario is not None:
            RolFormulario(self, usuario, self.cargar)

    def cambiar_estado(self):
        usuario = self._seleccionado()
        if usuario is None:
            return
        activar = not usuario["activo"]
        accion = "activar" if activar else "desactivar"
        if not messagebox.askyesno(
                "Confirmar", f"¿Desea {accion} al usuario {usuario['nombre_usuario']}?", parent=self):
            return
        try:
            usuarios_servicio.cambiar_estado(usuario["id"], activar)
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo completar", str(e), parent=self)
            return
        self.cargar()

    def restablecer(self):
        usuario = self._seleccionado()
        if usuario is None:
            return
        DialogoPassword(
            self, f"Restablecer contraseña de {usuario['nombre_usuario']}",
            "Defina una contraseña nueva. Avísele a la persona para que la cambie al ingresar.",
            False,
            lambda nueva, repetida: usuarios_servicio.restablecer_password(
                usuario["id"], nueva, repetida),
        )


class NuevoUsuarioFormulario(tk.Toplevel):
    def __init__(self, master, al_guardar):
        super().__init__(master)
        self.al_guardar = al_guardar
        self.title("Nuevo usuario")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack()

        self.var_usuario = tk.StringVar()
        self.var_nombre = tk.StringVar()
        self.var_rol = tk.StringVar(value="consulta")  # el rol de menor poder, por defecto
        self.var_password = tk.StringVar()
        self.var_repetir = tk.StringVar()

        primera = None
        filas = [
            ("Usuario *", self.var_usuario, None),
            ("Nombre completo *", self.var_nombre, None),
            ("Rol *", self.var_rol, "combo"),
            ("Contraseña *", self.var_password, "clave"),
            ("Repetir contraseña *", self.var_repetir, "clave"),
        ]
        for i, (etiqueta, variable, tipo) in enumerate(filas):
            ttk.Label(cuerpo, text=etiqueta).grid(row=i, column=0, sticky="e", padx=5, pady=6)
            if tipo == "combo":
                ttk.Combobox(cuerpo, textvariable=variable, values=ROLES,
                             state="readonly", width=29).grid(row=i, column=1, pady=6)
            else:
                entrada = ttk.Entry(cuerpo, textvariable=variable, width=32,
                                    show="•" if tipo == "clave" else "")
                entrada.grid(row=i, column=1, pady=6)
                if primera is None:
                    primera = entrada

        ttk.Label(
            cuerpo, foreground="gray", justify="center",
            text="Usuario: 4 a 30 caracteres (letras, números o guion bajo).\nContraseña: mínimo 8 caracteres.",
        ).grid(row=5, column=0, columnspan=2, pady=(5, 10))

        botones = ttk.Frame(cuerpo)
        botones.grid(row=6, column=0, columnspan=2)
        self.btn_guardar = ttk.Button(botones, text="Crear usuario", command=self.guardar)
        self.btn_guardar.pack(side="left", padx=5)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)

        primera.focus()

    def guardar(self):
        self.btn_guardar.state(["disabled"])
        try:
            auth_servicio.crear_usuario(
                self.var_usuario.get(), self.var_nombre.get(), self.var_password.get(),
                self.var_rol.get(), repetir=self.var_repetir.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo crear", str(e), parent=self)
            self.btn_guardar.state(["!disabled"])
            return
        messagebox.showinfo("Usuario creado", "El usuario se creó correctamente.", parent=self)
        self.al_guardar()
        self.destroy()


class RolFormulario(tk.Toplevel):
    def __init__(self, master, usuario, al_guardar):
        super().__init__(master)
        self.usuario = usuario
        self.al_guardar = al_guardar
        self.title("Cambiar rol")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack()
        ttk.Label(cuerpo, text=usuario["nombre_usuario"],
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 10))
        ttk.Label(cuerpo, text="Rol:").grid(row=1, column=0, sticky="e", padx=5, pady=6)
        self.var_rol = tk.StringVar(value=usuario["rol"])
        ttk.Combobox(cuerpo, textvariable=self.var_rol, values=ROLES,
                     state="readonly", width=22).grid(row=1, column=1, pady=6)

        botones = ttk.Frame(cuerpo)
        botones.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(botones, text="Guardar", command=self.guardar).pack(side="left", padx=5)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)

    def guardar(self):
        try:
            usuarios_servicio.cambiar_rol(self.usuario["id"], self.var_rol.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo cambiar", str(e), parent=self)
            return
        self.al_guardar()
        self.destroy()


class DialogoPassword(tk.Toplevel):
    """Ventana para definir una contraseña nueva.

    Si pedir_actual es True pide tambien la contraseña actual y llama a
    accion(actual, nueva, repetida). Si es False llama a accion(nueva, repetida).
    """

    def __init__(self, master, titulo, indicacion, pedir_actual, accion):
        super().__init__(master)
        self.pedir_actual = pedir_actual
        self.accion = accion
        self.title(titulo)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cuerpo = ttk.Frame(self, padding=20)
        cuerpo.pack()
        ttk.Label(cuerpo, text=indicacion, wraplength=340, justify="center").grid(
            row=0, column=0, columnspan=2, pady=(0, 12))

        self.var_actual = tk.StringVar()
        self.var_nueva = tk.StringVar()
        self.var_repetir = tk.StringVar()

        campos = []
        if pedir_actual:
            campos.append(("Contraseña actual:", self.var_actual))
        campos.append(("Contraseña nueva:", self.var_nueva))
        campos.append(("Repetir contraseña nueva:", self.var_repetir))

        primera = None
        for i, (etiqueta, variable) in enumerate(campos, start=1):
            ttk.Label(cuerpo, text=etiqueta).grid(row=i, column=0, sticky="e", padx=5, pady=6)
            entrada = ttk.Entry(cuerpo, textvariable=variable, show="•", width=28)
            entrada.grid(row=i, column=1, pady=6)
            entrada.bind("<Return>", lambda evento: self.aceptar())
            if primera is None:
                primera = entrada

        ttk.Label(cuerpo, text="Mínimo 8 caracteres.", foreground="gray").grid(
            row=len(campos) + 1, column=0, columnspan=2, pady=(2, 10))

        botones = ttk.Frame(cuerpo)
        botones.grid(row=len(campos) + 2, column=0, columnspan=2)
        ttk.Button(botones, text="Aceptar", command=self.aceptar).pack(side="left", padx=5)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)

        primera.focus()

    def aceptar(self):
        try:
            if self.pedir_actual:
                self.accion(self.var_actual.get(), self.var_nueva.get(), self.var_repetir.get())
            else:
                self.accion(self.var_nueva.get(), self.var_repetir.get())
        except ErrorDeNegocio as e:
            messagebox.showerror("No se pudo cambiar la contraseña", str(e), parent=self)
            for variable in (self.var_actual, self.var_nueva, self.var_repetir):
                variable.set("")  # no dejamos contraseñas escritas en pantalla
            return
        messagebox.showinfo("Contraseña actualizada", "La contraseña se cambió correctamente.", parent=self)
        self.destroy()