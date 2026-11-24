import csv


def exportar_csv(ruta, encabezados, filas):
    """Guarda una tabla en un archivo CSV que Excel abre correctamente."""
    with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(encabezados)
        escritor.writerows(filas)