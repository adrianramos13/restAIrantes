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
    - Imagen URL / Imagen archivo
                       las URLs de fotos de Google caducan en unas semanas, así que
                       cada foto se descarga UNA vez a imagenes/<nombre>.jpg (que se
                       sube al repo) y la app usa ese archivo. Los restaurantes que ya
                       tienen foto descargada no se vuelven a descargar: al añadir
                       restaurantes nuevos, solo se bajan las fotos de los nuevos.
                       Si la URL del HTML ya ha caducado, se busca el restaurante en
                       Google Maps con Playwright (sin coste) para sacar una URL nueva.

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

import asyncio
import re
import unicodedata
import urllib.parse
from pathlib import Path

import requests

from bs4 import BeautifulSoup
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill


# ----------------------- CONFIGURACIÓN ----------------------- #

BASE_DIR = Path(__file__).resolve().parent
INPUT_HTML = BASE_DIR.parent / "origen" / "restaurantes.html"
OUTPUT_XLSX = BASE_DIR.parent / "excels" / "restaurantes_v1.xlsx"
IMAGENES_DIR = BASE_DIR.parent / "imagenes"
TAMANO_IMAGEN = "=w450-h450"   # la miniatura del HTML es diminuta (=w80-h142); se pide más grande

# --------------------------------------------------------------- #


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def nombre_archivo_imagen(nombre):
    """'K'era | Restaurante Georgiano' -> 'kera-restaurante-georgiano.jpg'. Depende solo del
    nombre (no del ID, que cambia al añadir restaurantes), así la foto sigue siendo la suya."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", sin_tildes.replace("'", "")).strip("-")[:80]
    return f"{slug or 'sin-nombre'}.jpg"


def bajar_imagen(url, ruta):
    """Descarga `url` (pidiendo TAMANO_IMAGEN) a `ruta`. Lanza excepción si no es una imagen."""
    r = requests.get(re.sub(r"=w\d+-h\d+", TAMANO_IMAGEN, url), timeout=15)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/"):
        raise ValueError(f"no es una imagen ({r.headers.get('content-type')})")
    ruta.write_bytes(r.content)


async def _urls_frescas(nombres):
    """Abre la ficha de cada restaurante en Google Maps (con Playwright, como extraer_resenas.py)
    y devuelve {nombre: URL de su foto principal}, recién generada y por tanto aún válida."""
    from playwright.async_api import async_playwright
    from extraer_resenas import aceptar_cookies

    urls = {}
    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=True)
        page = await navegador.new_page(locale="es-ES")
        for i, nombre in enumerate(nombres, start=1):
            print(f"  [{i}/{len(nombres)}] {nombre}")
            consulta = urllib.parse.quote(f"{nombre}, Madrid, España")
            try:
                await page.goto(f"https://www.google.com/maps/search/?api=1&query={consulta}",
                                wait_until="domcontentloaded")
                await aceptar_cookies(page)
                foto = page.locator('button[jsaction*="heroHeaderImage"] img').first
                primer_resultado = page.locator("a.hfpxzc").first
                # La búsqueda abre directamente la ficha o, si hay varias coincidencias, una lista.
                await foto.or_(primer_resultado).wait_for(timeout=15000)
                if not await foto.count():
                    await primer_resultado.click()
                    await foto.wait_for(timeout=15000)
                urls[nombre] = await foto.get_attribute("src")
            except Exception as e:
                print(f"      sin foto: {type(e).__name__}")
        await navegador.close()
    return urls


def descargar_imagenes(filas):
    """Descarga a imagenes/ las fotos que aún no estén, y rellena 'Imagen archivo' en cada fila
    (vacío si no hay foto ni se ha podido bajar; la app entonces prueba con la URL).
    Si la URL del HTML ha caducado (HTML antiguo), busca el restaurante en Google Maps para
    sacar una URL nueva de su foto."""
    IMAGENES_DIR.mkdir(parents=True, exist_ok=True)
    nuevas, pendientes = 0, []
    for fila in filas:
        ruta = IMAGENES_DIR / nombre_archivo_imagen(fila["Nombre"])
        if not ruta.exists():
            try:
                bajar_imagen(fila["Imagen URL"], ruta)
                nuevas += 1
            except Exception:
                pendientes.append(fila)

    fallos = []
    if pendientes:
        print(f"{len(pendientes)} fotos con la URL del HTML caducada: buscándolas en Google Maps...")
        urls = asyncio.run(_urls_frescas([f["Nombre"] for f in pendientes]))
        for fila in pendientes:
            if not urls.get(fila["Nombre"]):
                fallos.append(f"{fila['Nombre']}: no encontrada en Google Maps")
                continue
            try:
                bajar_imagen(urls[fila["Nombre"]], IMAGENES_DIR / nombre_archivo_imagen(fila["Nombre"]))
                nuevas += 1
            except Exception as e:
                fallos.append(f"{fila['Nombre']}: {str(e).split(' for url')[0]}")

    for fila in filas:
        archivo = nombre_archivo_imagen(fila["Nombre"])
        fila["Imagen archivo"] = archivo if (IMAGENES_DIR / archivo).exists() else ""

    print(f"Imágenes: {nuevas} descargadas, {sum(1 for f in filas if f['Imagen archivo'])}/{len(filas)} con foto.")
    if fallos:
        print(f"  - [AVISO] {len(fallos)} no se han podido descargar:")
        for f in fallos:
            print(f"      · {f}")


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
        "Nombre", "Puntuación", "Nº Reseñas", "Rango de precios", "Tipo de cocina", "Estado", "Imagen URL",
        "Imagen archivo",
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

    anchos = {"A": 45, "B": 12, "C": 12, "D": 18, "E": 20, "F": 25, "G": 50, "H": 40}
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
    descargar_imagenes(filas)
    guardar_excel(filas, OUTPUT_XLSX)


if __name__ == "__main__":
    main()