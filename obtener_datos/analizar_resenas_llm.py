"""
Analiza el sentimiento de las reseñas y extrae los platos mencionados
(y si se valoran bien o mal) usando un MODELO DE LENGUAJE LOCAL vía Ollama.

A diferencia de la versión con diccionario fijo (analizar_resenas.py), aquí
el modelo entiende lenguaje libre: detecta cualquier plato mencionado,
aunque no lo hayamos anticipado en ninguna lista, y con más matiz de
sentimiento (negaciones, comparaciones, sarcasmo, etc.).

REQUISITOS PREVIOS (una sola vez):
    1. Instala Ollama: https://ollama.com/download
    2. Descarga un modelo:  ollama pull qwen2.5:7b-instruct
       (si tu ordenador va lento, prueba un modelo más ligero:
        ollama pull llama3.2:3b  y cambia OLLAMA_MODEL más abajo)

USO:
    1. Instala dependencias:
         pip install ollama pandas openpyxl

    2. Asegúrate de que Ollama está corriendo (se inicia solo tras
       instalarlo; puedes comprobarlo con `ollama list` en una terminal).

    3. Ejecuta:
         python analizar_resenas_llm.py

NOTA: no he podido probar este script contra un servidor Ollama real
(mi entorno no tiene uno disponible), así que está construido siguiendo
la documentación oficial del paquete `ollama` pero conviene probarlo
primero con pocas reseñas (ver LIMITE_RESENAS más abajo).
"""

import json
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
import ollama


# ----------------------- CONFIGURACIÓN ----------------------- #

EXCELS_DIR = Path(__file__).resolve().parent.parent / "excels"

INPUT_XLSX = EXCELS_DIR / "restaurantes_con_resenas.xlsx"     # salida de extraer_resenas.py
INPUT_SHEET = "Reseñas"
OUTPUT_XLSX = EXCELS_DIR / "analisis_resenas_llm.xlsx"

OLLAMA_MODEL = "qwen2.5:7b-instruct"   # cambia a "llama3.2:3b" si va muy lento

LIMITE_RESENAS = 20   # PRUEBA con pocas primero. Pon None para procesar todas.

MAX_REINTENTOS = 2    # reintentos si el modelo no devuelve JSON válido

# --------------------------------------------------------------- #


PROMPT_SISTEMA = """Eres un asistente que analiza reseñas de restaurantes en español.

Para cada reseña que te pase el usuario, responde ÚNICAMENTE con un JSON
(sin explicaciones, sin texto adicional, sin markdown) con este formato exacto:

{
  "sentimiento": "Buena" | "Mala" | "Neutra",
  "platos": [
    {"nombre": "nombre del plato o comida", "valoracion": "Buena" | "Mala" | "Neutra"}
  ]
}

Reglas:
- "sentimiento" es la valoración GENERAL de toda la reseña.
- "platos" es una lista de platos, comidas o bebidas concretas que se mencionen
  explícitamente en la reseña, cada uno con su propia valoración según lo que
  diga el texto sobre ese plato en particular (no la valoración general).
- Si no se menciona ningún plato concreto, devuelve "platos": [].
- Usa el nombre del plato tal como aparece o se sobreentiende en el texto,
  en minúsculas, sin artículos (ej. "sushi", no "el sushi").
- No inventes platos que no estén mencionados.
"""


def cargar_resenas(ruta, hoja):
    df = pd.read_excel(ruta, sheet_name=hoja)
    columnas_necesarias = {"Restaurante", "Texto"}
    if not columnas_necesarias.issubset(df.columns):
        raise ValueError(f"Faltan columnas {columnas_necesarias} en la hoja '{hoja}'")
    df = df.dropna(subset=["Texto"])
    df["Texto"] = df["Texto"].astype(str)
    if LIMITE_RESENAS:
        df = df.head(LIMITE_RESENAS)
    return df


def extraer_json(texto_respuesta):
    """
    Intenta parsear el JSON devuelto por el modelo. Si viene envuelto en
    texto o markdown (a veces pasa aunque se le pida JSON puro), intenta
    recortar el primer bloque {...} como fallback.
    """
    try:
        return json.loads(texto_respuesta)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", texto_respuesta, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def analizar_una_resena(texto):
    """
    Llama al modelo local vía Ollama para una reseña, con reintentos si
    la respuesta no es JSON válido.
    """
    for intento in range(MAX_REINTENTOS + 1):
        respuesta = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": texto},
            ],
            format="json",
            options={"temperature": 0},
        )
        contenido = respuesta["message"]["content"]
        datos = extraer_json(contenido)

        if datos and "sentimiento" in datos:
            # Normalizamos por si el modelo devuelve variantes raras
            sentimiento = str(datos.get("sentimiento", "Neutra")).strip().capitalize()
            if sentimiento not in ("Buena", "Mala", "Neutra"):
                sentimiento = "Neutra"

            platos = []
            for p in datos.get("platos", []) or []:
                if not isinstance(p, dict):
                    continue
                nombre = str(p.get("nombre", "")).strip().lower()
                valoracion = str(p.get("valoracion", "Neutra")).strip().capitalize()
                if valoracion not in ("Buena", "Mala", "Neutra"):
                    valoracion = "Neutra"
                if nombre:
                    platos.append({"nombre": nombre, "valoracion": valoracion})

            return sentimiento, platos

        # JSON inválido -> reintentar
        if intento < MAX_REINTENTOS:
            time.sleep(0.5)

    # Si tras los reintentos sigue sin funcionar, devolvemos neutro vacío
    # y lo dejamos constar para que se pueda revisar a mano.
    return "Neutra", []


def analizar_resenas(df):
    filas_resenas = []
    filas_platos = []
    fallos = []

    total = len(df)
    t0 = time.time()

    for idx, fila in enumerate(df.itertuples(index=False), start=1):
        texto = fila.Texto
        restaurante = fila.Restaurante
        autor = getattr(fila, "Autor", "")

        try:
            sentimiento, platos = analizar_una_resena(texto)
        except Exception as e:
            print(f"    [ERROR] Fallo en reseña {idx} ({restaurante}): {e}")
            fallos.append({"Restaurante": restaurante, "Autor": autor, "Texto": texto, "Error": str(e)})
            sentimiento, platos = "Neutra", []

        filas_resenas.append({
            "Restaurante": restaurante,
            "Autor": autor,
            "Texto": texto,
            "Sentimiento reseña": sentimiento,
        })

        for p in platos:
            filas_platos.append({
                "Restaurante": restaurante,
                "Plato": p["nombre"],
                "Sentimiento": p["valoracion"],
                "Reseña completa": texto,
                "Autor reseña": autor,
            })

        if idx % 10 == 0 or idx == total:
            transcurrido = time.time() - t0
            print(f"  Procesadas {idx}/{total} reseñas ({transcurrido:.0f}s)...")

    return filas_resenas, filas_platos, fallos


def construir_resumen(filas_resenas, filas_platos):
    resumen = defaultdict(lambda: {
        "buenas": 0, "malas": 0, "neutras": 0,
        "platos_buenos": defaultdict(int), "platos_malos": defaultdict(int),
    })

    for fila in filas_resenas:
        r = resumen[fila["Restaurante"]]
        if fila["Sentimiento reseña"] == "Buena":
            r["buenas"] += 1
        elif fila["Sentimiento reseña"] == "Mala":
            r["malas"] += 1
        else:
            r["neutras"] += 1

    for fila in filas_platos:
        r = resumen[fila["Restaurante"]]
        if fila["Sentimiento"] == "Buena":
            r["platos_buenos"][fila["Plato"]] += 1
        elif fila["Sentimiento"] == "Mala":
            r["platos_malos"][fila["Plato"]] += 1

    filas_resumen = []
    for restaurante, datos in resumen.items():
        top_buenos = sorted(datos["platos_buenos"].items(), key=lambda x: -x[1])[:5]
        top_malos = sorted(datos["platos_malos"].items(), key=lambda x: -x[1])[:5]
        filas_resumen.append({
            "Restaurante": restaurante,
            "Reseñas buenas": datos["buenas"],
            "Reseñas malas": datos["malas"],
            "Reseñas neutras": datos["neutras"],
            "Platos mejor valorados": ", ".join(f"{p} ({n})" for p, n in top_buenos),
            "Platos peor valorados": ", ".join(f"{p} ({n})" for p, n in top_malos),
        })

    filas_resumen.sort(key=lambda f: f["Restaurante"])
    return filas_resumen


def construir_top_platos_global(filas_platos):
    conteo = defaultdict(lambda: {"bien": 0, "mal": 0, "neutro": 0})

    for fila in filas_platos:
        plato = fila["Plato"]
        if fila["Sentimiento"] == "Buena":
            conteo[plato]["bien"] += 1
        elif fila["Sentimiento"] == "Mala":
            conteo[plato]["mal"] += 1
        else:
            conteo[plato]["neutro"] += 1

    filas = []
    for plato, datos in conteo.items():
        total = datos["bien"] + datos["mal"] + datos["neutro"]
        filas.append({
            "Plato": plato,
            "Veces valorado bien": datos["bien"],
            "Veces valorado mal": datos["mal"],
            "Menciones totales": total,
        })

    filas.sort(key=lambda f: -f["Menciones totales"])
    return filas


def guardar_excel(filas_resenas, filas_platos, filas_resumen, filas_top_platos, fallos, ruta_salida):
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "Reseñas analizadas"
    if filas_resenas:
        headers = list(filas_resenas[0].keys())
        ws1.append(headers)
        for fila in filas_resenas:
            ws1.append([fila[h] for h in headers])

    ws2 = wb.create_sheet("Platos mencionados")
    if filas_platos:
        headers = list(filas_platos[0].keys())
        ws2.append(headers)
        for fila in filas_platos:
            ws2.append([fila[h] for h in headers])

    ws3 = wb.create_sheet("Resumen por restaurante")
    if filas_resumen:
        headers = list(filas_resumen[0].keys())
        ws3.append(headers)
        for fila in filas_resumen:
            ws3.append([fila[h] for h in headers])

    ws4 = wb.create_sheet("Top platos general")
    if filas_top_platos:
        headers = list(filas_top_platos[0].keys())
        ws4.append(headers)
        for fila in filas_top_platos:
            ws4.append([fila[h] for h in headers])

    hojas = [ws1, ws2, ws3, ws4]

    if fallos:
        ws5 = wb.create_sheet("Fallos (revisar)")
        headers = list(fallos[0].keys())
        ws5.append(headers)
        for fila in fallos:
            ws5.append([fila[h] for h in headers])
        hojas.append(ws5)

    header_font = Font(name="Arial", bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    for ws in hojas:
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
        ws1: {"A": 30, "B": 20, "C": 60, "D": 16},
        ws2: {"A": 30, "B": 18, "C": 14, "D": 60, "E": 20},
        ws3: {"A": 30, "B": 14, "C": 14, "D": 14, "E": 45, "F": 45},
        ws4: {"A": 20, "B": 18, "C": 18, "D": 18},
    }
    for ws, widths in anchos.items():
        for col, w in widths.items():
            ws.column_dimensions[col].width = w

    wb.save(ruta_salida)
    print(f"\nGuardado: {ruta_salida}")
    print(f"  - {len(filas_resenas)} reseñas analizadas")
    print(f"  - {len(filas_platos)} menciones de platos detectadas")
    print(f"  - {len(filas_resumen)} restaurantes resumidos")
    print(f"  - {len(filas_top_platos)} platos distintos en el ranking global")
    if fallos:
        print(f"  - [AVISO] {len(fallos)} reseñas fallaron y quedaron como 'Neutra' sin platos "
              f"(revisa la hoja 'Fallos (revisar)')")


def main():
    df = cargar_resenas(INPUT_XLSX, INPUT_SHEET)
    print(f"Leídas {len(df)} reseñas de '{INPUT_XLSX}' (hoja '{INPUT_SHEET}').")
    print(f"Modelo local: {OLLAMA_MODEL} (asegúrate de que Ollama está corriendo).")

    try:
        ollama.list()
    except Exception as e:
        sys.exit(
            f"ERROR: no puedo conectar con Ollama en localhost. "
            f"¿Está instalado y corriendo? Detalle: {e}"
        )

    filas_resenas, filas_platos, fallos = analizar_resenas(df)
    filas_resumen = construir_resumen(filas_resenas, filas_platos)
    filas_top_platos = construir_top_platos_global(filas_platos)

    guardar_excel(filas_resenas, filas_platos, filas_resumen, filas_top_platos, fallos, OUTPUT_XLSX)


if __name__ == "__main__":
    main()