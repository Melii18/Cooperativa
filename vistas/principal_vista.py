from tkinter import ttk, messagebox

from servicios import auth_servicio
from servicios.sesion import Sesion
from vistas.aportes_vista import AportesVentana
from vistas.historial_vista import HistorialVentana
from vistas.pagos_vista import PagosVentana
from vistas.prestamos_vista import PrestamosVentana
from vistas.reportes_vista import ReportesVentana
from vistas.socios_vista import SociosVentana
from vistas.usuarios_vista import DialogoPassword, UsuariosVentana

MODULOS = [
    ("Socios", "socios_ver"),
    ("Aportes", "aportes_ver"),
    ("Préstamos", "prestamos_ver"),
    ("Pagos", "pagos_ver"),
    ("Reportes", "reportes"),
    ("Historial", "historial_ver"),
    ("Usuarios", "usuarios"),
]

VENTANAS = {
    "Socios": SociosVentana,
    "Aportes": AportesVentana,
    "Préstamos": PrestamosVentana,
    "Pagos": PagosVentana,
    "Reportes": ReportesVentana,
    "Historial": HistorialVentana,
    "Usuarios": UsuariosVentana,
}


class PrincipalFrame(ttk.Frame):
    def __init__(self, master, al_cerrar_sesion):
        super().__init__(master, padding=20)
        self.al_cerrar_sesion = al_cerrar_sesion
        usuario = Sesion.usuario

        ttk.Label(self, text=f"Bienvenido/a, {usuario['nombre_completo']}",
                  font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 5))
        ttk.Label(self, text=f"Rol: {usuario['rol']}").grid(row=1, column=0, columnspan=2, pady=(0, 20))

        for i, (texto, permiso) in enumerate(MODULOS):
            boton = ttk.Button(self, text=texto, width=22,
                               command=lambda t=texto: self.abrir_modulo(t))
            boton.grid(row=2 + i // 2, column=i % 2, padx=8, pady=8)
            if not Sesion.tiene_permiso(permiso):
                boton.state(["disabled"])

        pie = ttk.Frame(self)
        pie.grid(row=10, column=0, columnspan=2, pady=(25, 0))
        ttk.Button(pie, text="Cambiar mi contraseña", command=self.cambiar_password).pack(side="left", padx=6)
        ttk.Button(pie, text="Cerrar sesión", command=self.cerrar_sesion).pack(side="left", padx=6)

    def abrir_modulo(self, nombre):
        ventana = VENTANAS.get(nombre)
        if ventana is None:
            messagebox.showinfo(nombre, "Este módulo se construirá en una próxima fase.")
        else:
            ventana(self)

    def cambiar_password(self):
        DialogoPassword(
            self, "Cambiar mi contraseña",
            "Ingrese su contraseña actual y defina la nueva.",
            True, auth_servicio.cambiar_password_propia)

    def cerrar_sesion(self):
        auth_servicio.cerrar_sesion()
        self.al_cerrar_sesion()