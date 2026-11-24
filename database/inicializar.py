from pathlib import Path
import mysql.connector
from config import DB_CONFIG


def crear_base_de_datos():
    # Nos conectamos SIN indicar la base, porque todavia no existe
    config = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    conexion = mysql.connector.connect(**config)
    cursor = conexion.cursor()

    # Leemos schema.sql y quitamos las lineas de comentarios
    ruta = Path(__file__).parent / "schema.sql"
    lineas = [
        linea for linea in ruta.read_text(encoding="utf-8").splitlines()
        if not linea.strip().startswith("--")
    ]

    # Separamos por ";" y ejecutamos cada sentencia
    for sentencia in "\n".join(lineas).split(";"):
        if sentencia.strip():
            cursor.execute(sentencia)

    conexion.commit()
    cursor.close()
    conexion.close()
    print("Base de datos creada correctamente.")


if __name__ == "__main__":
    crear_base_de_datos()