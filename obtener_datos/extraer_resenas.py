import asyncio
import re
import time
from urllib.parse import quote
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIGURACIÓN
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
EXCELS_DIR = BASE_DIR.parent / "excels"

INPUT_FILE = EXCELS_DIR / "restaurantes_v1.xlsx"
OUTPUT_FILE = EXCELS_DIR / "restaurantes_v2.xlsx"

# Si tus restaurantes son de Madrid, déjalo así.
# Puedes cambiarlo por "Madrid, España", "Barcelona, España", etc.
CIUDAD = "Madrid, España"

# Número máximo de reseñas que queremos por restaurante
MAX_REVIEWS = 30

# Tiempo entre restaurantes
WAIT_BETWEEN_RESTAURANTS = 2


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def normalizar_texto(texto):
    """Normaliza texto para facilitar comparaciones."""
    if pd.isna(texto):
        return ""

    texto = str(texto).lower().strip()

    # Eliminar espacios duplicados
    texto = re.sub(r"\s+", " ", texto)

    return texto


def extraer_numero(texto):
    """Extrae el primer número decimal/integer encontrado."""
    if not texto:
        return None

    texto = str(texto).replace(",", ".")

    match = re.search(r"\d+(?:\.\d+)?", texto)

    if match:
        try:
            return float(match.group())
        except ValueError:
            return None

    return None


def extraer_lat_lon(url):
    """
    Las URLs de fichas de Google Maps casi siempre llevan las coordenadas incrustadas,
    tipo ".../@40.4168,-3.7038,17z/...". Las sacamos de ahí con una regex: es gratis (no
    hace falta ningún scraping ni clic extra) y no depende de ningún selector de la página
    que Google pueda cambiar.
    """
    if not url:
        return None, None
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


async def aceptar_cookies(page):
    """
    Intenta aceptar cookies si aparece el diálogo.
    Google puede mostrar textos diferentes dependiendo
    de país/navegador.
    """

    posibles_botones = [
        "Aceptar todo",
        "Aceptar",
        "Accept all",
        "I agree",
        "Rechazar todo",
        "No aceptar",
    ]

    for texto in posibles_botones:
        try:
            boton = page.get_by_role("button", name=re.compile(texto, re.I))

            if await boton.count() > 0:
                await boton.first.click(timeout=2000)
                await page.wait_for_timeout(1000)
                return

        except Exception:
            pass


async def buscar_restaurante(page, nombre):
    """
    Busca el restaurante directamente en Google Maps.
    """

    query = f"{nombre}, {CIUDAD}"

    url = (
        "https://www.google.com/maps/search/?api=1&query="
        + quote(query)
    )

    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    await page.wait_for_timeout(3000)

    await aceptar_cookies(page)

    await page.wait_for_timeout(2000)

    return query


async def abrir_ficha_desde_resultados(page, nombre):
    """
    Si la búsqueda deja una lista de resultados en lugar de la ficha,
    abre el primer resultado (o el que mejor coincida con el nombre).
    """

    try:
        titulo = page.locator("h1").first
        if await titulo.count() > 0 and await titulo.is_visible():
            texto = (await titulo.inner_text()).strip()
            if texto:
                return True
    except Exception:
        pass

    nombre_norm = normalizar_texto(nombre)

    candidatos = [
        'a[href*="/maps/place/"]',
        'a.hfpxzc',
        'div[role="article"]',
    ]

    for selector in candidatos:
        try:
            loc = page.locator(selector)
            cantidad = await loc.count()

            if cantidad == 0:
                continue

            elegido = 0

            for i in range(min(cantidad, 8)):
                try:
                    texto = normalizar_texto(await loc.nth(i).inner_text())
                    if nombre_norm and nombre_norm in texto:
                        elegido = i
                        break
                except Exception:
                    continue

            await loc.nth(elegido).click()
            await page.wait_for_timeout(2500)
            return True

        except Exception:
            continue

    return False


async def obtener_datos_ficha(page):
    """
    Obtiene los datos principales de la ficha actualmente abierta.
    """

    datos = {
        "nombre_google": "",
        "rating_google": None,
        "num_reviews_google": None,
        "direccion_google": "",
        "url_google": page.url,
    }

    try:
        # Nombre
        try:
            titulo = page.locator("h1").first

            if await titulo.count() > 0:
                datos["nombre_google"] = (
                    await titulo.inner_text()
                ).strip()
        except Exception:
            pass

        # Rating
        try:
            rating = page.locator(
                '[role="img"][aria-label*="estrella"]'
            ).first

            if await rating.count() > 0:
                aria = await rating.get_attribute("aria-label")
                datos["rating_google"] = extraer_numero(aria)

        except Exception:
            pass

        # Buscar número de reseñas en el texto de la página
        try:
            texto = await page.locator("body").inner_text()

            patrones = [
                r"([\d\.,]+)\s+reseñas",
                r"([\d\.,]+)\s+reviews",
            ]

            for patron in patrones:
                match = re.search(
                    patron,
                    texto,
                    flags=re.IGNORECASE
                )

                if match:
                    numero = (
                        match.group(1)
                        .replace(".", "")
                        .replace(",", "")
                    )

                    try:
                        datos["num_reviews_google"] = int(numero)
                    except ValueError:
                        pass

                    break

        except Exception:
            pass

        # Dirección: en la ficha de Google Maps suele ser un botón con
        # data-item-id="address" y un aria-label tipo "Dirección: Calle X, Madrid".
        # Probamos ese selector primero, y si Google no lo trae (puede cambiar),
        # cualquier botón cuyo aria-label empiece por "Dirección"/"Address".
        try:
            direccion = ""

            boton_direccion = page.locator('button[data-item-id="address"]').first
            if await boton_direccion.count() > 0:
                aria = await boton_direccion.get_attribute("aria-label")
                if aria:
                    direccion = re.sub(
                        r"^(Dirección|Address)\s*:\s*", "", aria.strip(),
                        flags=re.IGNORECASE,
                    ).strip()

            if not direccion:
                botones = page.locator("button[aria-label]")
                cantidad_botones = await botones.count()

                for i in range(min(cantidad_botones, 25)):
                    try:
                        aria = (
                            await botones.nth(i).get_attribute("aria-label")
                            or ""
                        ).strip()

                        if re.match(
                            r"^(Dirección|Address)\s*:", aria,
                            flags=re.IGNORECASE,
                        ):
                            direccion = re.sub(
                                r"^(Dirección|Address)\s*:\s*", "", aria,
                                flags=re.IGNORECASE,
                            ).strip()
                            break

                    except Exception:
                        continue

            datos["direccion_google"] = direccion

        except Exception:
            pass

    except Exception:
        pass

    return datos


async def _hay_tarjetas_resena(page):
    loc = page.locator("div[data-review-id], div.jftiEf")
    try:
        return await loc.count()
    except Exception:
        return 0


async def _info_contenedor_scroll(page):
    """(contenedor, scrollHeight, clientHeight) del panel de reseñas actual, o
    (None, 0, 0) si no se encuentra ninguno con el que medir."""
    contenedor = await obtener_contenedor_scroll(page)
    if not contenedor:
        return None, 0, 0
    try:
        alto_scroll = await contenedor.evaluate("(el) => el.scrollHeight")
        alto_visible = await contenedor.evaluate("(el) => el.clientHeight")
        return contenedor, alto_scroll, alto_visible
    except Exception:
        return contenedor, 0, 0


async def _panel_parece_real(page, margen=150):
    """
    Un panel de reseñas de verdad (con scroll infinito) tiene su contenedor con bastante
    más alto de scroll que de alto visible. La vista previa pequeña de la ficha, en cambio,
    apenas es desplazable -por eso el script se quedaba "atascado" en 3 reseñas: creía que
    había abierto el panel bueno solo porque YA había alguna tarjeta visible (la vista
    previa también las tiene, sin pinchar nada), y ese "ya hay tarjetas" no demuestra que
    estemos en el feed infinito real.
    """
    _, alto_scroll, alto_visible = await _info_contenedor_scroll(page)
    return (alto_scroll - alto_visible) > margen


async def abrir_panel_resenas(page):
    """
    Abre la pestaña completa de reseñas, no el preview de la ficha (ese preview suele
    mostrar solo ~3-5 reseñas SIN scroll infinito real, y no carga más).

    Cada estrategia, tras pinchar, se valida con _panel_parece_real(): "hay alguna tarjeta
    visible" YA NO basta por sí solo para dar el panel por abierto.
    """

    # 1) Pestaña "Reseñas" / "Reviews" (la que abre el feed infinito).
    #    Sin anclas ^...$: el texto accesible real de la pestaña puede traer pegados la
    #    puntuación o el nº de reseñas junto a la palabra, y una coincidencia EXACTA la
    #    descartaría sin más (probablemente lo que estaba pasando).
    for patron in (r"reseñas", r"reviews"):
        try:
            tab = page.get_by_role("tab", name=re.compile(patron, re.I))

            if await tab.count() > 0 and await tab.first.is_visible():
                await tab.first.click()
                await page.wait_for_timeout(2000)

                if await _panel_parece_real(page):
                    print("  [panel] Abierto por la pestaña 'Reseñas'.")
                    return True

        except Exception:
            pass

    # 2) Pinchar directamente en la puntuación/nº de reseñas de la cabecera: en la ficha
    #    de Google Maps ese texto suele ser TAMBIÉN un botón que abre el panel completo.
    try:
        insignia = page.locator('[role="img"][aria-label*="estrella"]').first
        if await insignia.count() > 0:
            clicable = insignia.locator(
                "xpath=ancestor::button[1] | xpath=ancestor::*[@role='button'][1]"
            )
            if await clicable.count() > 0 and await clicable.first.is_visible():
                await clicable.first.click()
                await page.wait_for_timeout(2000)

                if await _panel_parece_real(page):
                    print("  [panel] Abierto pinchando en la puntuación de la cabecera.")
                    return True
    except Exception:
        pass

    # 3) Enlaces / botones de "ver todas"
    textos_todas = [
        "Más reseñas",
        "Ver todas las reseñas",
        "See all reviews",
        "More reviews",
    ]

    for texto in textos_todas:
        try:
            loc = page.get_by_text(re.compile(rf"^{re.escape(texto)}$", re.I))

            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click()
                await page.wait_for_timeout(2000)

                if await _panel_parece_real(page):
                    print(f"  [panel] Abierto por el enlace {texto!r}.")
                    return True

        except Exception:
            pass

    # 4) Botón con aria-label de reseñas (evitar "escribir una reseña")
    try:
        botones = page.locator(
            'button[aria-label*="reseña" i], '
            'button[aria-label*="review" i]'
        )

        for i in range(min(await botones.count(), 6)):
            try:
                boton = botones.nth(i)

                if not await boton.is_visible():
                    continue

                aria = (await boton.get_attribute("aria-label") or "").lower()

                if "escribir" in aria or "write a review" in aria:
                    continue

                await boton.click()
                await page.wait_for_timeout(2000)

                if await _panel_parece_real(page):
                    print("  [panel] Abierto por un botón con aria-label de reseñas.")
                    return True

            except Exception:
                continue

    except Exception:
        pass

    # 5) Fallback: botones visibles con "reseñas"
    posibles_selectores = [
        'button:has-text("reseñas")',
        'button:has-text("Reseñas")',
        'button:has-text("reviews")',
        '[role="button"]:has-text("reseñas")',
        '[role="button"]:has-text("Reviews")',
    ]

    for selector in posibles_selectores:
        try:
            elementos = page.locator(selector)
            cantidad = await elementos.count()

            if cantidad == 0:
                continue

            for i in range(min(cantidad, 3)):
                try:
                    elemento = elementos.nth(i)

                    if await elemento.is_visible():
                        await elemento.click()
                        await page.wait_for_timeout(2000)

                        if await _panel_parece_real(page):
                            print("  [panel] Abierto por un botón/texto genérico de reseñas.")
                            return True

                except Exception:
                    continue

        except Exception:
            continue

    # Ninguna estrategia ha podido CONFIRMAR el panel real. Antes, aquí se devolvía True
    # solo por existir alguna tarjeta (la vista previa siempre tiene alguna) -eso es
    # justo lo que causaba el atasco en 3 reseñas-, así que ahora se avisa con los
    # números reales del contenedor encontrado, y solo se acepta como último recurso con
    # un margen de scroll mucho más laxo (mejor intentarlo igualmente que devolver 0).
    _, alto_scroll, alto_visible = await _info_contenedor_scroll(page)
    cantidad_tarjetas = await _hay_tarjetas_resena(page)
    print(f"  [panel] AVISO: ninguna estrategia ha confirmado el panel completo. "
          f"Tarjetas visibles ahora: {cantidad_tarjetas} | contenedor detectado: "
          f"scrollHeight={alto_scroll} clientHeight={alto_visible} "
          f"(margen={alto_scroll - alto_visible}px; se exigían >150px arriba).")
    return cantidad_tarjetas > 0 and (alto_scroll - alto_visible) > 40


async def obtener_contenedor_scroll(page):
    """
    Localiza el panel que realmente hace infinite-scroll de reseñas.
    Prioriza el ancestro con overflow de una tarjeta de reseña,
    no cualquier div.m6QErb de la página.
    """

    try:
        handle = await page.evaluate_handle(
            """
            () => {
                const review = document.querySelector(
                    'div[data-review-id], div.jftiEf'
                );

                if (review) {
                    let el = review.parentElement;

                    while (el && el !== document.body) {
                        const estilo = window.getComputedStyle(el);
                        const overflowY = estilo.overflowY;
                        const puedeScroll =
                            overflowY === 'auto' ||
                            overflowY === 'scroll' ||
                            overflowY === 'overlay';

                        if (
                            puedeScroll &&
                            el.scrollHeight > el.clientHeight + 20
                        ) {
                            return el;
                        }

                        el = el.parentElement;
                    }
                }

                const feeds = [...document.querySelectorAll('[role="feed"]')];

                for (const feed of feeds) {
                    if (feed.querySelector('div[data-review-id], div.jftiEf')) {
                        return feed;
                    }
                }

                return feeds[0] || null;
            }
            """
        )

        element = handle.as_element()

        if element:
            return element

    except Exception:
        pass

    candidatos = [
        'div[role="feed"]',
        'div.m6QErb.DxyBCb.kA9KIf.dS8AEf',
        'div.m6QErb.DxyBCb',
        'div.m6QErb',
    ]

    for selector in candidatos:
        try:
            loc = page.locator(selector)

            for i in range(await loc.count()):
                elemento = loc.nth(i)

                if await elemento.is_visible():
                    return elemento

        except Exception:
            pass

    return None


async def hacer_scroll_reseñas(page, espera_maxima_ms=8000, intervalo_ms=400):
    """
    Hace scroll dentro del panel de reseñas para forzar la carga perezosa, y ESPERA
    ACTIVAMENTE a que aparezcan más tarjetas (comprobando cada `intervalo_ms`, hasta
    `espera_maxima_ms` como mucho) en vez de dormir un tiempo fijo y mirar una sola vez.

    Google Maps tarda un tiempo VARIABLE en traer el siguiente lote -a veces medio
    segundo, a veces bastantes segundos, según el momento-, y una espera fija corta se
    queda corta a veces: el script se rendía pensando que ya no había más reseñas cuando
    en realidad solo iban con retraso (de ahí que unas veces saliera bien del todo y
    otras se quedara atascado a las pocas reseñas, sin ningún patrón aparente). Ahora, si
    las tarjetas aparecen rápido, se sale enseguida; si tardan, se espera más antes de
    rendirse.

    Devuelve True si aparecen más tarjetas o el contenedor crece de verdad.
    """

    cantidad_antes = await _hay_tarjetas_resena(page)

    # Traer la última reseña visible al viewport: Maps carga el
    # siguiente lote al llegar al final del feed.
    try:
        tarjetas = page.locator("div[data-review-id], div.jftiEf")

        if await tarjetas.count() > 0:
            await tarjetas.last.scroll_into_view_if_needed()
    except Exception:
        pass

    contenedor = await obtener_contenedor_scroll(page)

    altura_antes = 0
    top_antes = 0

    if contenedor:
        try:
            altura_antes = await contenedor.evaluate("(el) => el.scrollHeight")
            top_antes = await contenedor.evaluate("(el) => el.scrollTop")

            await contenedor.evaluate(
                """
                (el) => {
                    el.scrollTop = el.scrollHeight;
                }
                """
            )
        except Exception:
            pass

    try:
        feed = page.locator('div[role="feed"]').last

        if await feed.count() > 0:
            await feed.hover()
            await page.mouse.wheel(0, 2400)
    except Exception:
        pass

    # ------------------------------------------------------------
    # ESPERA ACTIVA: comprobamos cada poco en vez de dormir un tiempo
    # fijo, para adaptarnos a que Google tarde más o menos según el
    # momento (en vez de rendirnos siempre igual de rápido).
    # ------------------------------------------------------------
    transcurrido_ms = 0

    while transcurrido_ms < espera_maxima_ms:
        await page.wait_for_timeout(intervalo_ms)
        transcurrido_ms += intervalo_ms

        cantidad_despues = await _hay_tarjetas_resena(page)

        if cantidad_despues > cantidad_antes:
            return True

        if contenedor:
            try:
                altura_despues = await contenedor.evaluate(
                    "(el) => el.scrollHeight"
                )
                top_despues = await contenedor.evaluate("(el) => el.scrollTop")

                if altura_despues > altura_antes or top_despues > top_antes:
                    return True

            except Exception:
                pass

    return False


async def extraer_reseñas(page):
    """
    Extrae hasta MAX_REVIEWS reseñas visibles/cargadas.

    Antes de extraer el texto de cada reseña:
    - Busca el botón "Más"
    - Lo pulsa si existe
    - Espera a que se expanda
    - Extrae entonces el texto completo
    """

    reseñas = []

    # Selectores habituales de Google Maps para reseñas
    posibles_selectores = [
        'div[data-review-id]',
        'div.jftiEf',
    ]

    elementos = None

    for selector in posibles_selectores:

        try:
            loc = page.locator(selector)

            if await loc.count() > 0:
                elementos = loc
                break

        except Exception:
            continue

    if elementos is None:
        return reseñas

    cantidad = await elementos.count()

    for i in range(cantidad):

        if len(reseñas) >= MAX_REVIEWS:
            break

        try:

            review = elementos.nth(i)

            # =================================================
            # 1. EXPANDIR LA RESEÑA COMPLETA
            # =================================================

            posibles_botones_mas = [
                'button:has-text("Más")',
                'button:has-text("más")',
                'button:has-text("More")',
                'button:has-text("more")',
                '[role="button"]:has-text("Más")',
                '[role="button"]:has-text("More")',
            ]

            for selector_mas in posibles_botones_mas:

                try:

                    botones = review.locator(
                        selector_mas
                    )

                    cantidad_botones = await botones.count()

                    if cantidad_botones == 0:
                        continue

                    for j in range(cantidad_botones):

                        try:

                            boton = botones.nth(j)

                            if await boton.is_visible():

                                # Comprobamos que realmente es
                                # un botón de expansión.
                                texto_boton = (
                                    await boton.inner_text()
                                ).strip().lower()

                                if texto_boton in [
                                    "más",
                                    "more",
                                ]:

                                    await boton.click(
                                        timeout=2000
                                    )

                                    # Esperamos a que Google
                                    # expanda el contenido.
                                    await page.wait_for_timeout(
                                        300
                                    )

                                    break

                        except Exception:
                            continue

                    # Si hemos encontrado el selector correcto,
                    # dejamos de probar los demás.
                    break

                except Exception:
                    continue

            # =================================================
            # 2. AUTOR
            # =================================================

            autor = ""

            try:

                autor_element = review.locator(
                    'div[class*="d4r55"]'
                )

                if await autor_element.count() > 0:

                    autor = (
                        await autor_element.first.inner_text()
                    ).strip()

            except Exception:
                pass

            # =================================================
            # 3. TEXTO COMPLETO DE LA RESEÑA
            # =================================================

            texto = ""

            posibles_textos = [
                'span.wiI7pd',
                'span[class*="wiI7pd"]',
            ]

            for selector in posibles_textos:

                try:

                    texto_element = review.locator(
                        selector
                    )

                    if await texto_element.count() > 0:

                        # IMPORTANTE:
                        # inner_text() se ejecuta DESPUÉS
                        # de pulsar "Más".
                        texto = (
                            await texto_element.first.inner_text()
                        ).strip()

                        if texto:
                            break

                except Exception:
                    continue

            # -------------------------------------------------
            # Si no encontramos el span habitual, utilizamos
            # el texto completo de la tarjeta como fallback.
            # -------------------------------------------------

            if not texto:

                try:

                    texto_completo = (
                        await review.inner_text()
                    ).strip()

                    # Intentamos eliminar información que
                    # claramente no pertenece a la reseña.
                    if texto_completo:
                        texto = texto_completo

                except Exception:
                    pass

            # =================================================
            # 4. PUNTUACIÓN
            # =================================================

            puntuacion = None

            try:

                estrellas = review.locator(
                    '[role="img"][aria-label*="estrella"]'
                )

                if await estrellas.count() > 0:

                    aria = await estrellas.first.get_attribute(
                        "aria-label"
                    )

                    puntuacion = extraer_numero(
                        aria
                    )

            except Exception:
                pass

            # =================================================
            # 5. FECHA
            # =================================================

            fecha = ""

            try:

                texto_review = await review.inner_text()

                patrones_fecha = [
                    r"hace\s+[^\n]+",
                    r"\d+\s+(?:days?|weeks?|months?|years?)\s+ago",
                ]

                for patron in patrones_fecha:

                    match = re.search(
                        patron,
                        texto_review,
                        flags=re.IGNORECASE
                    )

                    if match:

                        fecha = (
                            match.group()
                            .strip()
                        )

                        break

            except Exception:
                pass

            # =================================================
            # 6. EVITAR DUPLICADOS
            # =================================================

            clave = (
                normalizar_texto(autor),
                normalizar_texto(texto),
                puntuacion,
            )

            duplicada = any(
                (
                    normalizar_texto(r["Autor"]),
                    normalizar_texto(r["Texto"]),
                    r["Puntuación"],
                ) == clave
                for r in reseñas
            )

            if duplicada:
                continue

            # =================================================
            # 7. GUARDAR RESEÑA
            # =================================================

            if autor or texto:

                reseñas.append({
                    "Autor": autor,
                    "Puntuación": puntuacion,
                    "Fecha": fecha,
                    "Texto": texto,
                })

        except Exception as e:

            # Si una reseña concreta da problemas,
            # continuamos con la siguiente.
            print(
                f"  Aviso: error leyendo reseña "
                f"{i + 1}: {e}"
            )

            continue

    return reseñas[:MAX_REVIEWS]

# ============================================================
# PROCESAR UN RESTAURANTE
# ============================================================

async def procesar_restaurante(page, nombre, indice, total):
    print("\n" + "=" * 70)
    print(f"[{indice}/{total}] {nombre}")
    print("=" * 70)

    resultado_base = {
        "Restaurante": nombre,
        "URL Google Maps": "",
        "Nombre Google": "",
        "Latitud": None,
        "Longitud": None,
        "Dirección": "",
        "Rating Google": None,
        "Nº reseñas Google": None,
        "Autor": "",
        "Puntuación": None,
        "Fecha": "",
        "Texto": "",
        "Estado": "OK",
        "Error": "",
    }

    try:
        # ---------------------------------------------------------
        # 1. BUSCAR RESTAURANTE
        # ---------------------------------------------------------
        encontrado = await buscar_restaurante(page, nombre)

        if not encontrado:
            print("No se encontró el restaurante.")

            resultado_base["Estado"] = "NO ENCONTRADO"
            resultado_base["Error"] = "No se encontró en Google Maps"

            return [resultado_base]

        await abrir_ficha_desde_resultados(page, nombre)

        print(f"Ficha encontrada: {nombre}")

        # ---------------------------------------------------------
        # 2. OBTENER DATOS DE LA FICHA
        # ---------------------------------------------------------
        datos_ficha = await obtener_datos_ficha(page)

        resultado_base.update({
            "URL Google Maps": datos_ficha.get("url_google", ""),
            "Nombre Google": datos_ficha.get("nombre_google", ""),
            "Rating Google": datos_ficha.get("rating_google"),
            "Nº reseñas Google": datos_ficha.get("num_reviews_google"),
            "Dirección": datos_ficha.get("direccion_google", ""),
        })

        lat, lon = extraer_lat_lon(datos_ficha.get("url_google", ""))
        resultado_base["Latitud"] = lat
        resultado_base["Longitud"] = lon
        if lat is None:
            print(
                f"  Aviso: no se han podido sacar coordenadas de la URL "
                f'de este sitio: {datos_ficha.get("url_google", "")!r}'
            )
        if not resultado_base["Dirección"]:
            print("  Aviso: no se ha podido leer la dirección de este sitio.")

        # ---------------------------------------------------------
        # 3. ABRIR PANEL DE RESEÑAS
        # ---------------------------------------------------------
        abierto = await abrir_panel_resenas(page)

        if not abierto:
            print("No se pudo abrir el panel de reseñas.")

            resultado_base["Estado"] = "ERROR"
            resultado_base["Error"] = "No se pudo abrir el panel de reseñas"

            return [resultado_base]

        print(f"Panel de reseñas abierto. (Google indica "
              f"{datos_ficha.get('num_reviews_google')} reseñas en total para este sitio)")

        try:
            await page.locator(
                "div[data-review-id], div.jftiEf"
            ).first.wait_for(state="visible", timeout=10000)
        except Exception:
            pass

# Pequeña espera para que Google Maps termine de cargar
        await page.wait_for_timeout(1500)

        # ---------------------------------------------------------
        # 4. EXTRAER RESEÑAS
        # ---------------------------------------------------------
        reseñas = []

        intentos_sin_nuevas = 0
        ultimo_numero = 0

        # Máximo de 30 iteraciones para evitar bucles infinitos
        for intento in range(30):

            # Buscar las reseñas que actualmente están cargadas
            nuevas = await extraer_reseñas(page)

            # -----------------------------------------------------
            # ELIMINAR DUPLICADOS
            # -----------------------------------------------------
            existentes = {
                (
                    r.get("Autor", ""),
                    r.get("Texto", ""),
                    r.get("Fecha", "")
                )
                for r in reseñas
            }

            for r in nuevas:

                clave = (
                    r.get("Autor", ""),
                    r.get("Texto", ""),
                    r.get("Fecha", "")
                )

                if clave not in existentes:
                    reseñas.append(r)
                    existentes.add(clave)

            # Limitar a 30
            if len(reseñas) > MAX_REVIEWS:
                reseñas = reseñas[:MAX_REVIEWS]

            print(
                f"Reseñas cargadas: "
                f"{len(reseñas)}/{MAX_REVIEWS}"
            )

            # -----------------------------------------------------
            # ¿YA TENEMOS 30?
            # -----------------------------------------------------
            if len(reseñas) >= MAX_REVIEWS:
                print("Se han conseguido las 30 reseñas.")
                break

            # -----------------------------------------------------
            # COMPROBAR SI HAN APARECIDO NUEVAS
            # -----------------------------------------------------
            if len(reseñas) == ultimo_numero:
                intentos_sin_nuevas += 1
            else:
                intentos_sin_nuevas = 0

            ultimo_numero = len(reseñas)

            # -----------------------------------------------------
            # HACER SCROLL
            # -----------------------------------------------------
            avanzado = await hacer_scroll_reseñas(page)

            if not avanzado:
                intentos_sin_nuevas += 1

            # -----------------------------------------------------
            # SI LLEVAMOS VARIOS INTENTOS SIN NUEVAS RESEÑAS
            # -----------------------------------------------------
            if intentos_sin_nuevas >= 6:

                print(
                    "No aparecen nuevas reseñas después de varios "
                    "intentos. Se detiene la extracción."
                )

                break

            # Esperar a que Google Maps cargue las nuevas reseñas
            await page.wait_for_timeout(1000)

        # ---------------------------------------------------------
        # 5. COMPROBAR RESULTADO
        # ---------------------------------------------------------
        if not reseñas:

            print("No se pudo extraer ninguna reseña.")

            resultado_base["Estado"] = "SIN RESEÑAS"
            resultado_base["Error"] = (
                "No se pudieron extraer reseñas de Google Maps"
            )

            return [resultado_base]

        # ---------------------------------------------------------
        # 6. CREAR UNA FILA POR CADA RESEÑA
        # ---------------------------------------------------------
        resultados = []

        for reseña in reseñas:

            fila = resultado_base.copy()

            fila.update({
                "Autor": reseña.get("Autor", ""),
                "Puntuación": reseña.get("Puntuación"),
                "Fecha": reseña.get("Fecha", ""),
                "Texto": reseña.get("Texto", ""),
            })

            resultados.append(fila)

        print(
            f"Extracción terminada: "
            f"{len(resultados)} reseñas."
        )

        # ---------------------------------------------------------
        # 7. ESPERA ENTRE RESTAURANTES
        # ---------------------------------------------------------
        await page.wait_for_timeout(
            WAIT_BETWEEN_RESTAURANTS * 1000
        )

        return resultados

    # -------------------------------------------------------------
    # CONTROL DE ERRORES
    # -------------------------------------------------------------
    except Exception as e:

        print(f"ERROR procesando {nombre}: {e}")

        resultado_base["Estado"] = "ERROR"
        resultado_base["Error"] = str(e)

        return [resultado_base]

# ============================================================
# MAIN
# ============================================================

async def main():

    print()
    print("==============================================")
    print(" EXTRACTOR DE RESEÑAS DE GOOGLE MAPS")
    print("==============================================")
    print()

    # --------------------------------------------------------
    # Leer Excel
    # --------------------------------------------------------

    try:

        df = pd.read_excel(INPUT_FILE)

    except Exception as e:

        print(
            f"No se pudo abrir {INPUT_FILE}: {e}"
        )

        return

    # --------------------------------------------------------
    # Comprobar columna Nombre
    # --------------------------------------------------------

    if "Nombre" not in df.columns:

        print(
            "ERROR: El Excel debe contener una columna "
            "'Nombre'."
        )

        print(
            "Columnas encontradas:",
            list(df.columns)
        )

        return

    print(
        f"Restaurantes encontrados: {len(df)}"
    )

    print(
        f"Objetivo máximo: "
        f"{len(df) * MAX_REVIEWS:,} reseñas"
    )

    resultados_totales = []

    async with async_playwright() as p:

        # ----------------------------------------------------
        # Abrir navegador
        # ----------------------------------------------------

        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled"
            ]
        )

        context = await browser.new_context(
            locale="es-ES",
            viewport={
                "width": 1440,
                "height": 900,
            }
        )

        page = await context.new_page()

        # ----------------------------------------------------
        # Procesar restaurantes
        # ----------------------------------------------------

        total = len(df)

        for indice, (_, fila) in enumerate(
            df.iterrows(),
            start=1
        ):

            nombre = str(fila["Nombre"]).strip()

            resultados = await procesar_restaurante(
                page,
                nombre,
                indice,
                total
            )

            resultados_totales.extend(
                resultados
            )

            # Guardado incremental
            # Así no perdemos todo si el script se interrumpe.
            if resultados_totales:

                df_resultados = pd.DataFrame(
                    resultados_totales
                )

                df_resultados.to_excel(
                    OUTPUT_FILE,
                    index=False
                )

            await page.wait_for_timeout(
                WAIT_BETWEEN_RESTAURANTS * 1000
            )

        await browser.close()

    # --------------------------------------------------------
    # Resultado final
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("PROCESO TERMINADO")
    print("=" * 70)

    print(
        f"Restaurantes procesados: {len(df)}"
    )

    print(
        f"Reseñas obtenidas: "
        f"{len(resultados_totales)}"
    )

    print(
        f"Archivo: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    asyncio.run(main())