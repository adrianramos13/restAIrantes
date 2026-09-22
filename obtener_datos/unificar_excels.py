"""
Unifica los 3 excels que hemos ido generando (restaurantes_v1.xlsx,
restaurantes_con_resenas.xlsx, analisis_resenas.xlsx) en un único archivo
`restaurantes_maestro.xlsx`, asignando un ID numérico fijo a cada
restaurante.

Esta es la ÚLTIMA vez que hace falta cruzar por nombre normalizado: a
partir de este momento, todos los scripts futuros (encuesta, futuras
re-ejecuciones del análisis de reseñas, etc.) pueden referenciar cada
restaurante por su ID en vez de por su nombre, evitando por completo los
problemas de cruce que veníamos arrastrando.

ESTRUCTURA DEL MAESTRO:
  - Hoja "Restaurantes": ID, Nombre, Puntuación, Nº Reseñas, Rango de
    precios, Tipo de cocina, Dirección, Latitud, Longitud, Teléfono, Web,
    Reseñas buenas, Reseñas malas, Reseñas neutras, Platos mejor
    valorados, Platos peor valorados.
  - Hoja "Reseñas": ID_Restaurante, Autor, Puntuación, Fecha, Texto,
    Sentimiento (si se pudo cruzar con el análisis).
  - Hoja "Platos mencionados": ID_Restaurante, Plato, Sentimiento,
    Fragmento, Autor.

USO:
    python unificar_excels.py
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill


# ----------------------- CONFIGURACIÓN ----------------------- #

EXCELS_DIR = Path(__file__).resolve().parent.parent / "excels"

RESTAURANTES_XLSX = EXCELS_DIR / "restaurantes_v1.xlsx"
RESENAS_XLSX = EXCELS_DIR / "restaurantes_con_resenas.xlsx"
ANALISIS_XLSX = EXCELS_DIR / "analisis_resenas.xlsx"   # cambia a analisis_resenas_llm.xlsx si aplica

OUTPUT_MAESTRO = EXCELS_DIR / "restaurantes_maestro.xlsx"

# --------------------------------------------------------------- #


def normalizar_nombre_clave(texto):
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKC", texto)
    texto = re.sub(r"\s+", " ", texto).strip().lower()
    return texto


def cargar_base_con_id():
    df = pd.read_excel(RESTAURANTES_XLSX)
    df["ID"] = range(1, len(df) + 1)
    df["_clave"] = df["Nombre"].apply(normalizar_nombre_clave)
    return df


def construir_mapa_id(df_base):
    """dict: nombre normalizado -> ID, para cruzar los demás excels."""
    return dict(zip(df_base["_clave"], df_base["ID"]))


def construir_hoja_restaurantes(df_base, mapa_id):
    columnas = ["ID", "Nombre", "Puntuación", "Nº Reseñas",
                "Rango de precios", "Tipo de cocina"]
    # Columnas opcionales: solo si vienen en restaurantes_v1.xlsx (por si
    # se generó con una versión más antigua de extraer_html.py)
    for col_opcional in ["Imagen URL", "Estado"]:
        if col_opcional in df_base.columns:
            columnas.append(col_opcional)
        else:
            print(f"[AVISO] '{col_opcional}' no está en restaurantes_v1.xlsx; "
                  f"vuelve a ejecutar extraer_html.py si la necesitas.")

    resultado = df_base[columnas].copy()

    # --- Localización (restaurantes_con_resenas.xlsx, hoja Restaurantes) ---
    try:
        df_loc = pd.read_excel(RESENAS_XLSX, sheet_name="Restaurantes")
        df_loc = df_loc.rename(columns={"Nombre (excel original)": "Nombre"})
        df_loc["_clave"] = df_loc["Nombre"].apply(normalizar_nombre_clave)
        df_loc["ID"] = df_loc["_clave"].map(mapa_id)
        no_cruzados = df_loc["ID"].isna().sum()
        if no_cruzados:
            print(f"[AVISO] {no_cruzados} filas de localización no se pudieron cruzar con ningún ID.")
        df_loc = df_loc.dropna(subset=["ID"])
        df_loc = df_loc[["ID", "Dirección", "Latitud", "Longitud", "Teléfono", "Web"]]
        resultado = resultado.merge(df_loc, on="ID", how="left")
    except Exception as e:
        print(f"[AVISO] No se pudo leer localización de '{RESENAS_XLSX}': {e}")

    # --- Resumen de reseñas (analisis_resenas.xlsx, hoja Resumen por restaurante) ---
    try:
        df_resumen = pd.read_excel(ANALISIS_XLSX, sheet_name="Resumen por restaurante")
        df_resumen = df_resumen.rename(columns={"Restaurante": "Nombre"})
        df_resumen["_clave"] = df_resumen["Nombre"].apply(normalizar_nombre_clave)
        df_resumen["ID"] = df_resumen["_clave"].map(mapa_id)
        no_cruzados = df_resumen["ID"].isna().sum()
        if no_cruzados:
            print(f"[AVISO] {no_cruzados} filas de resumen de reseñas no se pudieron cruzar con ningún ID.")
        df_resumen = df_resumen.dropna(subset=["ID"])
        df_resumen = df_resumen[["ID", "Reseñas buenas", "Reseñas malas", "Reseñas neutras",
                                  "Platos mejor valorados", "Platos peor valorados"]]
        resultado = resultado.merge(df_resumen, on="ID", how="left")
    except Exception as e:
        print(f"[AVISO] No se pudo leer resumen de reseñas de '{ANALISIS_XLSX}': {e}")

    return resultado


def construir_hoja_resenas(mapa_id):
    """
    Cruza restaurantes_con_resenas.xlsx (hoja Reseñas, texto crudo) con
    analisis_resenas.xlsx (hoja 'Reseñas analizadas', que tiene el
    sentimiento) usando restaurante+autor+texto como clave compuesta,
    ya que no había un ID de reseña individual hasta ahora.
    """
    try:
        df_resenas = pd.read_excel(RESENAS_XLSX, sheet_name="Reseñas")
    except Exception as e:
        print(f"[AVISO] No se pudo leer la hoja 'Reseñas' de '{RESENAS_XLSX}': {e}")
        return pd.DataFrame(columns=["ID_Restaurante", "Autor", "Puntuación", "Fecha", "Texto", "Sentimiento"])

    df_resenas["_clave"] = df_resenas["Restaurante"].apply(normalizar_nombre_clave)
    df_resenas["ID_Restaurante"] = df_resenas["_clave"].map(mapa_id)
    df_resenas["_clave_texto"] = df_resenas["_clave"] + "||" + df_resenas["Autor"].astype(str) + "||" + df_resenas["Texto"].astype(str)

    try:
        df_analizadas = pd.read_excel(ANALISIS_XLSX, sheet_name="Reseñas analizadas")
        df_analizadas["_clave"] = df_analizadas["Restaurante"].apply(normalizar_nombre_clave)
        df_analizadas["_clave_texto"] = df_analizadas["_clave"] + "||" + df_analizadas["Autor"].astype(str) + "||" + df_analizadas["Texto"].astype(str)
        mapa_sentimiento = dict(zip(df_analizadas["_clave_texto"], df_analizadas["Sentimiento reseña"]))
        df_resenas["Sentimiento"] = df_resenas["_clave_texto"].map(mapa_sentimiento)
        sin_sentimiento = df_resenas["Sentimiento"].isna().sum()
        if sin_sentimiento:
            print(f"[AVISO] {sin_sentimiento}/{len(df_resenas)} reseñas no encontraron su sentimiento "
                  f"correspondiente (puede pasar si el análisis se hizo solo sobre una parte de las reseñas).")
    except Exception as e:
        print(f"[AVISO] No se pudo cruzar el sentimiento de reseñas: {e}")
        df_resenas["Sentimiento"] = None

    return df_resenas[["ID_Restaurante", "Autor", "Puntuación", "Fecha", "Texto", "Sentimiento"]]


def construir_hoja_platos(mapa_id):
    try:
        df_platos = pd.read_excel(ANALISIS_XLSX, sheet_name="Platos mencionados")
    except Exception as e:
        print(f"[AVISO] No se pudo leer 'Platos mencionados' de '{ANALISIS_XLSX}': {e}")
        return pd.DataFrame(columns=["ID_Restaurante", "Plato", "Sentimiento", "Fragmento", "Autor"])

    df_platos = df_platos.rename(columns={"Restaurante": "Nombre", "Autor reseña": "Autor"})
    df_platos["_clave"] = df_platos["Nombre"].apply(normalizar_nombre_clave)
    df_platos["ID_Restaurante"] = df_platos["_clave"].map(mapa_id)
    no_cruzados = df_platos["ID_Restaurante"].isna().sum()
    if no_cruzados:
        print(f"[AVISO] {no_cruzados} menciones de platos no se pudieron cruzar con ningún ID.")

    columna_fragmento = "Fragmento" if "Fragmento" in df_platos.columns else "Reseña completa"
    df_platos = df_platos.rename(columns={columna_fragmento: "Fragmento"})

    return df_platos[["ID_Restaurante", "Plato", "Sentimiento", "Fragmento", "Autor"]]


def guardar_maestro(hoja_restaurantes, hoja_resenas, hoja_platos, ruta_salida):
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "Restaurantes"
    ws1.append(list(hoja_restaurantes.columns))
    for fila in hoja_restaurantes.itertuples(index=False):
        ws1.append(list(fila))

    ws2 = wb.create_sheet("Reseñas")
    ws2.append(list(hoja_resenas.columns))
    for fila in hoja_resenas.itertuples(index=False):
        ws2.append(list(fila))

    ws3 = wb.create_sheet("Platos mencionados")
    ws3.append(list(hoja_platos.columns))
    for fila in hoja_platos.itertuples(index=False):
        ws3.append(list(fila))

    header_font = Font(name="Arial", bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    for ws in [ws1, ws2, ws3]:
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.font = Font(name="Arial")
        ws.freeze_panes = "A2"
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions

    anchos = {
        ws1: {"A": 6, "B": 30, "C": 12, "D": 12, "E": 18, "F": 20, "G": 40,
              "H": 12, "I": 12, "J": 15, "K": 25, "L": 12, "M": 12, "N": 12, "O": 40, "P": 40},
        ws2: {"A": 12, "B": 20, "C": 12, "D": 16, "E": 60, "F": 14},
        ws3: {"A": 12, "B": 18, "C": 14, "D": 60, "E": 20},
    }
    for ws, widths in anchos.items():
        for col, w in widths.items():
            ws.column_dimensions[col].width = w

    wb.save(ruta_salida)
    print(f"\nGuardado: {ruta_salida}")
    print(f"  - {len(hoja_restaurantes)} restaurantes")
    print(f"  - {len(hoja_resenas)} reseñas")
    print(f"  - {len(hoja_platos)} menciones de platos")


def main():
    df_base = cargar_base_con_id()
    print(f"Base cargada: {len(df_base)} restaurantes, IDs asignados del 1 al {len(df_base)}.")

    mapa_id = construir_mapa_id(df_base)

    hoja_restaurantes = construir_hoja_restaurantes(df_base, mapa_id)
    hoja_resenas = construir_hoja_resenas(mapa_id)
    hoja_platos = construir_hoja_platos(mapa_id)

    guardar_maestro(hoja_restaurantes, hoja_resenas, hoja_platos, OUTPUT_MAESTRO)


if __name__ == "__main__":
    main()