import tkinter as tk

from vistas.login_vista import LoginFrame
from vistas.principal_vista import PrincipalFrame


class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Cooperativa")
        self.frame_actual = None
        self.mostrar_login()

    def _cambiar_frame(self, frame):
        if self.frame_actual is not None:
            self.frame_actual.destroy()
        self.frame_actual = frame
        self.frame_actual.pack(fill="both", expand=True)

    def mostrar_login(self):
        self.geometry("380x300")
        self._cambiar_frame(LoginFrame(self, self.mostrar_principal))

    def mostrar_principal(self):
        self.geometry("560x420")
        self._cambiar_frame(PrincipalFrame(self, self.mostrar_login))


if __name__ == "__main__":
    Aplicacion().mainloop()