"""
Sube los datos actuales (excels/clasificacion_jev.xlsx + imagenes/) a Supabase como TU lista.
Se ejecuta una vez, al pasar al modo multiusuario. Repetirlo no duplica nada: actualiza.

USO:
    python obtener_datos/migrar_a_supabase.py --email tu_correo@gmail.com
    python obtener_datos/migrar_a_supabase.py --email tu_correo@gmail.com --url "https://maps.app.goo.gl/..."
        (--url guarda también el enlace de tu lista, para poder refrescarla con el procesador)
"""

import argparse

import pandas as pd

from conexion_supabase import RAIZ, cliente, datos

EXCEL = RAIZ / "excels" / "clasificacion_jev.xlsx"
IMAGENES_DIR = RAIZ / "imagenes"


def main():
    parser = argparse.ArgumentParser(description="Sube tu lista actual a Supabase.")
    parser.add_argument("--email", required=True, help="tu correo de Google (el que usarás para entrar en la app)")
    parser.add_argument("--url", help="enlace de tu lista de Google Maps (opcional)")
    args = parser.parse_args()
    usuario = args.email.strip().lower()
    if args.url and not datos.enlace_lista_valido(args.url):
        raise SystemExit("ERROR: --url no parece un enlace de una lista de Google Maps.")

    bd = cliente()
    df_rest = pd.read_excel(EXCEL, sheet_name="Restaurantes")
    try:
        df_platos = pd.read_excel(EXCEL, sheet_name="Platos mencionados")
    except ValueError:
        df_platos = pd.DataFrame(columns=datos.COLUMNAS_PLATOS)
    filas = datos.filas_catalogo_desde_excel(df_rest, df_platos)
    print(f"{len(df_rest)} filas en {EXCEL.name} -> {len(filas)} restaurantes (sin repetidos).")

    subidas, sin_archivo = 0, []
    for fila in filas:
        ruta = IMAGENES_DIR / (fila["imagen"] or "")
        if fila["imagen"] and ruta.is_file():
            bd.subir_foto(fila["imagen"], ruta.read_bytes())
            subidas += 1
        else:
            sin_archivo.append(fila["datos"].get("Nombre"))
            fila["imagen"] = None   # que la app no apunte a una foto que no está en el bucket
    print(f"Fotos subidas: {subidas}." + (f" Sin foto: {sin_archivo[:8]}" if sin_archivo else ""))

    ids = bd.guardar_restaurantes(filas)
    lista = bd.guardar_lista(usuario, enlace=args.url, estado="lista",
                             mensaje=f"{len(ids)} restaurantes (migrados desde el excel)")
    bd.reemplazar_lista(lista["id"], [ids[f["clave"]] for f in filas])
    print(f"Lista de {usuario}: {len(ids)} restaurantes. Ya puedes entrar en la app con esa cuenta.")


if __name__ == "__main__":
    main()
