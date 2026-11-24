import tkinter as tk
from tkinter import ttk, messagebox

from servicios import auth_servicio
from utils.errores import ErrorDeNegocio

MAX_INTENTOS = 5


class LoginFrame(ttk.Frame):
    def __init__(self, master, al_iniciar_sesion):
        super().__init__(master, padding=30)
        self.al_iniciar_sesion = al_iniciar_sesion
        self.intentos = 0

        ttk.Label(self, text="Sistema de Cooperativa",
                  font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(self, text="Usuario:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.var_usuario = tk.StringVar()
        entrada_usuario = ttk.Entry(self, textvariable=self.var_usuario, width=28)
        entrada_usuario.grid(row=1, column=1, pady=5)

        ttk.Label(self, text="Contraseña:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.var_password = tk.StringVar()
        entrada_password = ttk.Entry(self, textvariable=self.var_password, show="•", width=28)
        entrada_password.grid(row=2, column=1, pady=5)

        ttk.Button(self, text="Ingresar", command=self.intentar_login).grid(
            row=3, column=0, columnspan=2, pady=20)

        # Enter en cualquiera de los dos campos equivale a pulsar "Ingresar"
        entrada_usuario.bind("<Return>", lambda evento: self.intentar_login())
        entrada_password.bind("<Return>", lambda evento: self.intentar_login())
        entrada_usuario.focus()

    def intentar_login(self):
        try:
            auth_servicio.iniciar_sesion(self.var_usuario.get(), self.var_password.get())
        except ErrorDeNegocio as e:
            self.intentos += 1
            self.var_password.set("")
            messagebox.showerror("Acceso denegado", str(e))
            if self.intentos >= MAX_INTENTOS:
                messagebox.showwarning("Bloqueado", "Demasiados intentos fallidos. Se cerrará el sistema.")
                self.winfo_toplevel().destroy()
            return
        except RuntimeError as e:  # lo lanza obtener_conexion si MySQL no responde
            messagebox.showerror("Error de conexión", str(e))
            return

        self.al_iniciar_sesion()