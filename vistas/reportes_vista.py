import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox, filedialog

from servicios import reportes_servicio
from servicios.aportes_servicio import NOMBRES_MESES
from utils.errores import ErrorDeNegocio
from utils.exportar import exportar_csv
from utils.validadores import formatear_guaranies

# Ancho y alineacion de cada tipo de columna
ESTILOS = {
    "texto": (240, "w"),
    "entero": (150, "center"),
    "monto": (160, "e"),
    "fecha": (110, "center"),
}


def _para_mostrar(valor, tipo):
    if valor is None:
        return "—"
    if tipo == "monto":
        return f"{formatear_guaranies(valor)} Gs"
    if tipo == "fecha":
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def _para_exportar(valor, tipo):
    if valor is None:
        return ""
    if tipo == "fecha":
        return valor.strftime("%d/%m/%Y")
    return valor  # los numeros se exportan como numeros, sin puntos ni "Gs"


class PestanaReporte(ttk.Frame):
    def __init__(self, master, nombre_archivo, generar, filtro_mes=False):
        super().__init__(master, padding=10)
        self.nombre_archivo = nombre_archivo
        self.generar = generar
        self.filtro_mes = filtro_mes
        self.reporte = None

        # --- Barra superior ---
        barra = ttk.Frame(self)
        barra.pack(fill="x", pady=(0, 8))
        if filtro_mes:
            ttk.Label(barra, text="Mes:").pack(side="left")
            self.var_mes = tk.StringVar(value=NOMBRES_MESES[date.today().month - 1])
            ttk.Combobox(barra, textvariable=self.var_mes, values=NOMBRES_MESES,
                         state="readonly", width=12).pack(side="left", padx=5)
            ttk.Label(barra, text="Año:").pack(side="left", padx=(10, 0))
            self.var_anio = tk.StringVar(value=str(date.today().year))
            ttk.Spinbox(barra, from_=2000, to=2100, textvariable=self.var_anio,
                        width=7).pack(side="left", padx=5)
            ttk.Button(barra, text="Generar", command=self.actualizar).pack(side="left", padx=10)
        else:
            ttk.Button(barra, text="Actualizar", command=self.actualizar).pack(side="left")
        ttk.Button(barra, text="Exportar a CSV", command=self.exportar).pack(side="right")

        # --- Tabla ---
        contenedor = ttk.Frame(self)
        contenedor.pack(fill="both", expand=True)
        self.tabla = ttk.Treeview(contenedor, show="headings", selectmode="browse")
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.lbl_resumen = ttk.Label(self, padding=(0, 8))
        self.lbl_resumen.pack(fill="x")

        self.actualizar()

    def actualizar(self):
        try:
            if self.filtro_mes:
                try:
                    anio = int(self.var_anio.get())
                except ValueError:
                    raise ErrorDeNegocio("El año no es válido.")
                mes = NOMBRES_MESES.index(self.var_mes.get()) + 1
                reporte = self.generar(anio, mes)
            else:
                reporte = self.generar()
        except ErrorDeNegocio as e:
            messagebox.showerror("Reportes", str(e), parent=self)
            return

        self.reporte = reporte
        columnas = reporte["columnas"]
        ids = [f"c{i}" for i in range(len(columnas))]
        self.tabla.configure(columns=ids)
        for cid, (titulo, tipo) in zip(ids, columnas):
            ancho, alineacion = ESTILOS[tipo]
            self.tabla.heading(cid, text=titulo)
            self.tabla.column(cid, width=ancho, anchor=alineacion)

        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        for fila in reporte["filas"]:
            valores = [_para_mostrar(v, tipo) for v, (_, tipo) in zip(fila, columnas)]
            self.tabla.insert("", "end", values=valores)

        self.lbl_resumen.config(text=reporte["resumen"])

    def exportar(self):
        if self.reporte is None:
            return
        sugerido = f"{self.nombre_archivo}_{date.today().strftime('%Y-%m-%d')}.csv"
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Guardar reporte", defaultextension=".csv",
            initialfile=sugerido, filetypes=[("Archivo CSV", "*.csv")])
        if not ruta:  # el usuario cancelo
            return

        columnas = self.reporte["columnas"]
        filas = [
            [_para_exportar(v, tipo) for v, (_, tipo) in zip(fila, columnas)]
            for fila in self.reporte["filas"]
        ]
        try:
            exportar_csv(ruta, [titulo for titulo, _ in columnas], filas)
            reportes_servicio.registrar_exportacion(self.reporte["titulo"])
        except (OSError, ErrorDeNegocio) as e:
            messagebox.showerror(
                "No se pudo guardar",
                f"No se pudo guardar el archivo. Si lo tenés abierto en Excel, cerralo e intentá de nuevo.\n\n{e}",
                parent=self)
            return
        messagebox.showinfo("Reporte exportado", f"Se guardó el archivo:\n{ruta}", parent=self)


class ReportesVentana(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Reportes")
        self.geometry("1040x580")
        self.transient(master)

        libro = ttk.Notebook(self)
        libro.pack(fill="both", expand=True, padx=10, pady=10)
        libro.add(
            PestanaReporte(libro, "resumen_general", reportes_servicio.resumen_general),
            text="Resumen general")
        libro.add(
            PestanaReporte(libro, "socios_morosos", reportes_servicio.socios_morosos),
            text="Socios morosos")
        libro.add(
            PestanaReporte(libro, "resumen_mensual", reportes_servicio.resumen_mensual, filtro_mes=True),
            text="Resumen mensual")

        ttk.Button(self, text="Cerrar", command=self.destroy).pack(pady=(0, 10))