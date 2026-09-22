"""
Extrae los datos de restaurantes desde el HTML de tu lista de Google Maps
(guardado en la carpeta origen/) y genera restaurantes_novia.xlsx.

CAMPOS EXTRAÍDOS:
    - Nombre
    - Puntuación
    - Nº Reseñas
    - Rango de precios
    - Tipo de cocina
    - Estado           (vacío normalmente; "Cerrado temporalmente" o
                         "Cerrado permanentemente" si Google Maps lo marca así)

CÓMO OBTENER EL HTML:
    1. Abre tu lista de Google Maps en el navegador.
    2. Haz scroll hasta cargar TODOS los restaurantes (Google Maps carga
       la lista poco a poco al hacer scroll).
    3. Clic derecho -> "Inspeccionar" -> en el árbol del DOM busca el
       contenedor de la lista y copia su HTML ("Copy outerHTML"), o guarda
       la página completa con Ctrl+S.
    4. Guarda ese HTML como origen/restaurantes.html

USO:
    python extraer_html.py
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill


# ----------------------- CONFIGURACIÓN ----------------------- #

BASE_DIR = Path(__file__).resolve().parent
INPUT_HTML = BASE_DIR.parent / "origen" / "restaurantes.html"
OUTPUT_XLSX = BASE_DIR.parent / "excels" / "restaurantes_v1.xlsx"

# --------------------------------------------------------------- #


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def extraer_restaurantes(soup):
    buttons = soup.find_all("button", class_="SMP2wb")
    print(f"Encontrados {len(buttons)} restaurantes en el HTML.")

    filas = []
    for b in buttons:
        # --- Nombre ---
        name_div = b.find("div", class_="fontHeadlineSmall")
        nombre = clean(name_div.get_text()) if name_div else ""

        # --- Puntuación y nº de reseñas (desde el aria-label) ---
        rating_span = b.find("span", class_="ZkP5Je")
        puntuacion, resenas = None, None
        if rating_span and rating_span.get("aria-label"):
            m = re.match(
                r"([\d,]+)\s+estrellas\s+([\d.,]+)\s+rese",
                rating_span["aria-label"],
            )
            if m:
                puntuacion = float(m.group(1).replace(",", "."))
                resenas = int(m.group(2).replace(".", ""))

        # --- Imagen (miniatura del restaurante) ---
        img_tag = b.find("img", class_="WkIe8")
        imagen_url = img_tag.get("src", "") if img_tag else ""

        # --- Segundo bloque IIrLbb: precio + cocina, o "Cerrado..." ---
        iirlbbs = b.find_all("div", class_="IIrLbb")
        precio, cocina, estado = "", "", ""

        if len(iirlbbs) >= 2:
            block = iirlbbs[1]
            texto_bloque = clean(block.get_text())

            if "cerrado" in texto_bloque.lower():
                # Caso: "Cerrado temporalmente" / "Cerrado permanentemente"
                estado = texto_bloque
            else:
                price_span = block.find("span", attrs={"role": "img"})
                if price_span:
                    precio = clean(price_span.get_text())

                spans = block.find_all("span", recursive=False)
                for sp in spans:
                    if sp.get("role") != "img":
                        text = clean(sp.get_text()).replace("·", "").strip()
                        if text:
                            cocina = text

        filas.append(
            {
                "Nombre": nombre,
                "Puntuación": puntuacion,
                "Nº Reseñas": resenas,
                "Rango de precios": precio,
                "Tipo de cocina": cocina,
                "Estado": estado,
                "Imagen URL": imagen_url,
            }
        )

    return filas


def guardar_excel(filas, ruta_salida):
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Restaurantes"

    headers = list(filas[0].keys()) if filas else [
        "Nombre", "Puntuación", "Nº Reseñas", "Rango de precios", "Tipo de cocina", "Estado", "Imagen URL"
    ]
    ws.append(headers)
    for fila in filas:
        ws.append([fila[h] for h in headers])

    header_font = Font(name="Arial", bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
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

    anchos = {"A": 45, "B": 12, "C": 12, "D": 18, "E": 20, "F": 25, "G": 50}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w

    wb.save(ruta_salida)
    print(f"\nGuardado: {ruta_salida}")
    print(f"  - {len(filas)} restaurantes")

    cerrados = [f for f in filas if f["Estado"]]
    if cerrados:
        print(f"  - [AVISO] {len(cerrados)} restaurantes aparecen como cerrados:")
        for f in cerrados:
            print(f"      · {f['Nombre']} — {f['Estado']}")


def main():
    if not INPUT_HTML.exists():
        raise SystemExit(
            f"ERROR: no encuentro '{INPUT_HTML}'. Guarda el HTML de tu "
            f"lista de Google Maps en esa ruta antes de ejecutar el script."
        )

    with open(INPUT_HTML, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    filas = extraer_restaurantes(soup)
    guardar_excel(filas, OUTPUT_XLSX)


if __name__ == "__main__":
    main()