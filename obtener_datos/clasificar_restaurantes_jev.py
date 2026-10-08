"""
Genera el EXCEL ÚNICO con todo lo que necesita la app, usando JEV (TypeSafe) para
clasificar cada reseña por TIPO DE COCINA y por SENTIMIENTO en la misma llamada.

Sustituye a extraer_resenas.py -> analizar_resenas.py -> unificar_excels.py en la parte
de análisis: este script lee directamente restaurantes_v1.xlsx (lista + imagen + precio +
rating) y restaurantes_v2.xlsx (localización + reseñas, generado con el scraper gratuito
de Playwright), y escribe excels/clasificacion_jev.xlsx listo para que la app lo use tal
cual. Ya no hace falta restaurantes_maestro.xlsx ni unificar_excels.py.

CÓMO FUNCIONA
  1. Lee restaurantes_v1.xlsx (Nombre, Puntuación, Nº Reseñas, Rango de precios, Tipo de
     cocina, Estado, Imagen URL) y le asigna un ID por posición (igual que hacía antes
     unificar_excels.py). Le añade Latitud/Longitud cruzando por nombre con
     restaurantes_v2.xlsx (esas coordenadas salen de la URL de la ficha de Google Maps, no
     hace falta ningún scraping aparte). No trae Dirección/Teléfono/Web -restaurantes_v2.xlsx
     no las captura-, pero no pasa nada: la app muestra "N/D" cuando faltan.
  2. Para CADA reseña (restaurantes_v2.xlsx, una fila por reseña), UNA sola llamada a
     Jev responde DOS preguntas a la vez:
       - "cocina": una de las categorías de CATEGORIAS.
       - "sentimiento": Buena / Mala / Neutra.
  3. Por restaurante: la cocina más votada entre las reseñas informativas (todas menos
     "no_se_sabe"; empate → la primera de CATEGORIAS), y el recuento de reseñas
     Buenas/Malas/Neutras.
  4. Los "platos destacados" NO los pregunta Jev (su API nunca da esa información, solo la
     categoría elegida, sus probabilidades y una confianza): se buscan en Python, mirando
     qué platos de ejemplo de CATEGORIAS (de cualquier categoría, no solo la elegida)
     aparecen literalmente en cada reseña. Por eso solo cubre los platos que aparecen en
     esas descripciones -son bastante más que antes, pero no genéricos como "pan" o
     "postre", que no ayudan a distinguir una cocina y por eso no están ahí.

Para cambiar las categorías de cocina o de sentimiento, edita SOLO CATEGORIAS y
CATEGORIAS_SENTIMIENTO más abajo.

REQUISITOS:
    pip install typesafe-sdk pandas openpyxl
    Una clave de API de TypeSafe en la variable de entorno TYPESAFE_API_KEY:
        Windows (PowerShell):  $env:TYPESAFE_API_KEY = "tu_clave"
        Mac/Linux:             export TYPESAFE_API_KEY="tu_clave"

USO (desde la carpeta obtener_datos/):
    python clasificar_restaurantes_jev.py --probar "cachopo y cecina espectacular"
    python clasificar_restaurantes_jev.py --limite 3      # prueba con 3 restaurantes
    python clasificar_restaurantes_jev.py                 # todos

SALIDA: excels/clasificacion_jev.xlsx, con las hojas:
    - Restaurantes: TODO lo que usa la app (ID, Nombre, Puntuación, Nº Reseñas, Rango de
      precios, Tipo de cocina (Google), Imagen URL, Estado, Latitud, Longitud,
      Categoría (Jev), Categoría 2ª (Jev), % votos, confianza, Reseñas
      buenas/malas/neutras, Platos mejor/peor valorados).
    - Reseñas: categoría, sentimiento, probabilidades y confianza de cada reseña.
    - Platos mencionados: una fila por cada plato de ejemplo detectado en una reseña
      (equivalente a lo que antes daba analizar_resenas.py con su diccionario; lo usa la
      app para la búsqueda de "¿Algún plato concreto?").
    - Configuración y Categorías.

CACHÉ: cada resultado se guarda en obtener_datos/.cache/cache_jev.jsonl en cuanto se
calcula. La clave incluye una huella de CATEGORIAS + CATEGORIAS_SENTIMIENTO + las dos
preguntas: si cambias cualquiera de las cuatro, se recalcula todo (y se paga otra vez).
Añade obtener_datos/.cache/ a tu .gitignore.

COSTE: Jev cobra por token de entrada (0,042 USD por millón, precio de lanzamiento que
puede cambiar); la salida es gratis. Al terminar se imprime una estimación con los tokens
reales consumidos.

NOTA: escrito según la documentación y el SDK oficial (typesafe-sdk 0.7.x) y probado a
fondo contra un servidor simulado con el formato de respuesta del SDK, incluida la
pregunta doble; la primera ejecución real conviene hacerla con --probar y --limite 3.
"""

import argparse
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from typesafe_sdk import (
    Choice,
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAuthenticationError,
    TypeSafeClient,
    TypeSafeError,
    TypeSafePermissionDeniedError,
)

# ----------------------- CONFIGURACIÓN ----------------------- #

BASE_DIR = Path(__file__).resolve().parent
EXCELS_DIR = BASE_DIR.parent / "excels"
CACHE_DIR = BASE_DIR / ".cache"            # resultados ya calculados (permite reanudar). No subir a GitHub.

RESTAURANTES_XLSX = EXCELS_DIR / "restaurantes_v1.xlsx"           # lista de restaurantes (de aquí salen ID, imagen, precio, rating)
RESENAS_XLSX = EXCELS_DIR / "restaurantes_v2.xlsx"                # localización (Latitud/Longitud) + reseñas, todo en una sola hoja
SALIDA_XLSX = EXCELS_DIR / "clasificacion_jev.xlsx"

MODELO_DEFECTO = "jev-1.13.0"     # versión fija (el alias "jev-latest" puede cambiar de modelo sin aviso)
HILOS_DEFECTO = 4                 # el límite es ~1.200 peticiones/min; 4 hilos quedan por debajo
PRECIO_USD_POR_MILLON_TOKENS = 0.042

MIN_CARACTERES_RESENA = 15        # reseñas más cortas se ignoran (no se llama al modelo)
MAX_CARACTERES_RESENA = 1500      # reseñas más largas se recortan
MAX_RESENAS_POR_RESTAURANTE = 30  # se leen las primeras N de cada restaurante
MIN_RESENAS_INFORMATIVAS = 2      # menos que esto => "sin_datos_suficientes"
TOP_PLATOS = 8                    # cuántos platos como máximo se listan en "Platos mejor/peor valorados"

INSTRUCCION_COCINA = "¿Qué tipo de cocina sirve el restaurante, según lo que cuenta esta reseña?"
INSTRUCCION_SENTIMIENTO = ("¿Cuál es el sentimiento general del cliente hacia el restaurante, "
                           "según lo que cuenta en esta reseña?")

CATEGORIA_SIN_DATOS = "no_se_sabe"
CATEGORIA_INSUFICIENTE = "sin_datos_suficientes"

# Categorías de COCINA (clave -> descripción). BORRADOR: ajústala a tus restaurantes. El
# ORDEN importa solo para desempates (gana la primera). Deja "no_se_sabe" al final.
CATEGORIAS = {
    "espanola": "Cocina tradicional española de cualquier región: cochinillo, cordero asado, jamón, "
                "tortilla de patatas, cocido, fabada, cachopo, callos, migas, croquetas, salmorejo, torreznos.",
    "tapas_raciones": "Tapas, pinchos y raciones para compartir en barra o mesa baja: patatas bravas, "
                      "calamares, ensaladilla, tabla de jamón y queso, montaditos.",
    "arroces_mediterranea": "Arroces y cocina mediterránea: paella, arroz caldoso, fideuá, arroz negro, "
                            "pescados y verduras a la mediterránea.",
    "carnes_parrilla": "Carne a la brasa o a la parrilla como especialidad: chuletón, entrecot, solomillo, "
                       "costillar, picaña, asado, secreto ibérico.",
    "pescados_mariscos": "Pescado y marisco como especialidad: pulpo, gambas, langostinos, ostras, mejillones, "
                         "almejas, bacalao, pescado fresco, marisquería.",
    "italiana": "Cocina italiana: pasta, pizza, risotto, lasaña, carbonara, gnocchi, burrata, tiramisú.",
    "japonesa": "Cocina japonesa: sushi, sashimi, ramen, gyozas, tempura, udon, yakitori, izakaya.",
    "asiatica_otra": "Otras cocinas asiáticas distintas de la japonesa: tailandesa (pad thai, curry), china "
                     "(dim sum, wok), coreana (bibimbap, kimchi), vietnamita (pho), india (tikka masala, naan).",
    "mexicana": "Cocina mexicana y tex-mex: tacos, guacamole, nachos, burritos, quesadillas, enchiladas.",
    "latinoamericana": "Cocina latinoamericana distinta de la mexicana: peruana (ceviche, lomo saltado), "
                       "argentina (empanadas, provoleta), venezolana (arepas), colombiana, brasileña.",
    "oriente_medio": "Cocina de Oriente Medio y mediterránea oriental: libanesa, turca, griega, árabe; "
                     "hummus, falafel, shawarma, kebab, gyros, moussaka.",
    "americana": "Comida americana: hamburguesas, alitas, costillas BBQ, hot dogs, patatas fritas, sándwiches.",
    "europea_otra": "Otras cocinas europeas: francesa, portuguesa, alemana, británica, nórdica, georgiana.",
    "vegetariana_vegana": "Carta vegetariana o vegana como eje del restaurante: platos vegetales, bowls, opciones veganas.",
    "reposteria_cafeteria": "Pastelería, cafetería y brunch: tartas, bollería, croissants, café, tostadas, tortitas, helados.",
    "fusion_autor": "Cocina de autor, creativa o de fusión que mezcla tradiciones: menús degustación, platos "
                    "elaborados sin una cocina de origen clara.",
    CATEGORIA_SIN_DATOS: "La reseña no menciona comida ni platos que permitan saber el tipo de cocina "
                         "(solo habla de servicio, precio, ambiente o valoraciones genéricas).",
}

# Categorías de SENTIMIENTO. Los nombres ("Buena"/"Mala"/"Neutra") son los que ya usaba el
# análisis anterior con pysentimiento: se mantienen tal cual para que nada más en la app
# tenga que cambiar.
CATEGORIAS_SENTIMIENTO = {
    "Buena": "Reseña mayoritariamente positiva: el cliente está contento con la comida, el servicio o la "
             "experiencia en general, aunque mencione algún detalle menor negativo.",
    "Mala": "Reseña mayoritariamente negativa: el cliente se queja de la comida, el servicio, la limpieza, "
            "el precio o cualquier otro aspecto, aunque mencione algún detalle positivo menor.",
    "Neutra": "Reseña neutra, mixta o puramente descriptiva: no hay una valoración claramente positiva ni "
              "negativa, o lo bueno y lo malo pesan por igual.",
}


# Nombre legible de cada categoría de cocina, para lo que ve quien usa la app (el desplegable,
# las tarjetas). Si añades una categoría a CATEGORIAS y no la pones aquí, se muestra su clave
# con formato ("mi_categoria" -> "Mi categoria"), así que no rompe nada.
ETIQUETAS_CATEGORIA = {
    "espanola": "Española", "tapas_raciones": "Tapas y raciones", "arroces_mediterranea": "Arroces y mediterránea",
    "carnes_parrilla": "Carnes y parrilla", "pescados_mariscos": "Pescados y mariscos", "italiana": "Italiana",
    "japonesa": "Japonesa", "asiatica_otra": "Asiática (otras)", "mexicana": "Mexicana",
    "latinoamericana": "Latinoamericana", "oriente_medio": "Oriente Medio", "americana": "Americana",
    "europea_otra": "Europea (otras)", "vegetariana_vegana": "Vegetariana y vegana",
    "reposteria_cafeteria": "Repostería y cafetería", "fusion_autor": "Fusión y de autor",
}


def etiqueta_categoria(clave):
    """Clave interna de Jev -> texto legible. "sin_datos_suficientes"/"no_se_sabe" NO son una
    cocina real, así que devuelven None (y la app cae entonces al tipo de cocina de Google)."""
    if not isinstance(clave, str) or not clave.strip() or clave in (CATEGORIA_INSUFICIENTE, CATEGORIA_SIN_DATOS):
        return None
    return ETIQUETAS_CATEGORIA.get(clave, clave.replace("_", " ").capitalize())

# --------------------------------------------------------------- #

_ORDEN = {clave: i for i, clave in enumerate(CATEGORIAS)}


def huella_categorias():
    """Huella corta de las dos preguntas y las dos listas de categorías. Si cambia cualquiera
    de las cuatro, la caché deja de valer y se recalcula todo (incluida la ejecución
    anterior a este cambio, porque antes no existía la pregunta de sentimiento)."""
    contenido = json.dumps({
        "instruccion_cocina": INSTRUCCION_COCINA, "categorias_cocina": CATEGORIAS,
        "instruccion_sentimiento": INSTRUCCION_SENTIMIENTO, "categorias_sentimiento": CATEGORIAS_SENTIMIENTO,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:12]


HUELLA = huella_categorias()


# ----------------------- PLATOS DE EJEMPLO (calculados aquí, no por Jev) ----------------------- #

def _sin_tildes(texto):
    if not isinstance(texto, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))


def _terminos_ejemplo(descripcion):
    """Saca los platos/términos de ejemplo del TEXTO de la descripción de una categoría (lo que
    hay después de los ':'). Son solo los ejemplos que yo escribí en CATEGORIAS: Jev no expone en
    ningún momento qué términos usa internamente -esto es una aproximación calculada aquí, en
    Python, buscando estas palabras literalmente en el texto de cada reseña.
    Algunas descripciones agrupan ejemplos entre paréntesis (ej. "peruana (ceviche, lomo
    saltado)") o usan ";" además de ",": se extraen por separado, si no "ceviche" quedaba pegado
    a "peruana (" y no coincidía nunca con el texto de una reseña real."""
    resto = (descripcion.split(":", 1)[1] if ":" in descripcion else descripcion).rstrip(".")
    de_parentesis = [t for grupo in re.findall(r"\(([^)]*)\)", resto) for t in re.split(r"[,;]", grupo)]
    resto_sin_parentesis = re.sub(r"\([^)]*\)", "", resto)
    fuera = re.split(r"[,;]", resto_sin_parentesis)
    return [t.strip().rstrip(".").strip() for t in (de_parentesis + fuera) if t.strip()]


TERMINOS_POR_CATEGORIA = {
    clave: _terminos_ejemplo(descripcion) for clave, descripcion in CATEGORIAS.items()
    if clave != CATEGORIA_SIN_DATOS
}

# Para "todos los platos, de cualquier categoría" (usado en la hoja "Platos mencionados" y en
# los platos destacados por restaurante). Si un término aparece en más de una categoría, se
# queda con la primera que lo trae.
_TERMINO_A_CATEGORIA = {}
for _cat, _terminos in TERMINOS_POR_CATEGORIA.items():
    for _t in _terminos:
        _TERMINO_A_CATEGORIA.setdefault(_sin_tildes(_t), (_t, _cat))


def terminos_encontrados(texto, categoria):
    """De los términos de ejemplo de `categoria`, cuáles aparecen literalmente en `texto`
    (sin distinguir mayúsculas ni tildes). Se usa para la columna "Platos de ejemplo
    encontrados en el texto" de la hoja Reseñas (solo de la categoría que Jev eligió, para
    entender por qué la eligió)."""
    terminos = TERMINOS_POR_CATEGORIA.get(categoria)
    if not terminos:
        return []
    texto_norm = _sin_tildes(texto)
    return [t for t in terminos if _sin_tildes(t) in texto_norm]


def todos_los_platos_en_texto(texto):
    """Qué platos de ejemplo, de CUALQUIER categoría, aparecen en `texto`. Devuelve una lista
    de (plato, categoria_a_la_que_pertenece_ese_plato). Se usa para "Platos mencionados" y
    para los platos destacados por restaurante -no depende de qué cocina eligió Jev para esa
    reseña en concreto."""
    texto_norm = _sin_tildes(texto)
    return [(plato, cat) for clave_norm, (plato, cat) in _TERMINO_A_CATEGORIA.items() if clave_norm in texto_norm]


# ----------------------- CARGA Y PREPARACIÓN ----------------------- #

def _clave_nombre(texto):
    """Clave de cruce por nombre: NFKC, espacios colapsados, minúsculas."""
    if not isinstance(texto, str):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", texto)).strip().lower()


def _clave_aproximada(texto):
    """Clave más laxa: sin tildes ni signos, solo letras y números. Solo se usa si el cruce exacto falla."""
    return re.sub(r"[^0-9a-z]+", "", _sin_tildes(_clave_nombre(texto)))


def _cruzar_por_nombre(nombres, rest):
    """ID de `rest` (restaurantes_v1.xlsx) para cada nombre de restaurantes_v2.xlsx: primero por
    la clave exacta y, si falla, por la aproximada cuando no es ambigua. Es el ÚNICO cruce por
    nombre: localización y reseñas usan el mismo, para que un restaurante no pueda quedarse
    con reseñas pero sin coordenadas. Devuelve (ids con None si no cruza, recuento por modo)."""
    exacto = dict(zip(rest["Nombre"].apply(_clave_nombre), rest["ID"]))
    por_aprox = {}
    for nombre, id_r in zip(rest["Nombre"], rest["ID"]):
        por_aprox.setdefault(_clave_aproximada(nombre), set()).add(id_r)
    aprox = {k: next(iter(v)) for k, v in por_aprox.items() if k and len(v) == 1}   # solo las no ambiguas

    ids, modo = [], Counter()
    for nombre in nombres:
        id_r = exacto.get(_clave_nombre(nombre))
        if id_r is not None:
            modo["exacto"] += 1
        else:
            id_r = aprox.get(_clave_aproximada(nombre))
            modo["aproximado" if id_r is not None else "sin_cruce"] += 1
        ids.append(id_r)
    return ids, modo


def cargar_restaurantes_base():
    """
    Lee restaurantes_v1.xlsx y le asigna un ID por posición (1..N, igual que hacía antes
    unificar_excels.py). Le añade Latitud/Longitud cruzando por nombre con
    restaurantes_v2.xlsx (si existe).

    restaurantes_v2.xlsx es UNA sola hoja con una fila por reseña (el nombre, la URL de
    Google Maps y las coordenadas se repiten en cada fila de un mismo restaurante), tal
    como la genera extraer_resenas.py con Playwright. No incluye Dirección/Teléfono/Web
    -no pasa nada: la app ya muestra "N/D" cuando faltan-, pero SÍ necesita Latitud/Longitud
    para poder calcular tiempos de desplazamiento; sin ellas, ese restaurante no puede
    aparecer en ningún resultado.
    """
    try:
        rest = pd.read_excel(RESTAURANTES_XLSX)
    except Exception as e:
        raise SystemExit(f"ERROR: no puedo leer {RESTAURANTES_XLSX}: {e}")
    if "Nombre" not in rest.columns:
        raise SystemExit(f"ERROR: {RESTAURANTES_XLSX.name} no tiene una columna 'Nombre'.")

    rest = rest.reset_index(drop=True)
    rest["ID"] = range(1, len(rest) + 1)

    repetidos = rest["Nombre"].apply(_clave_nombre)
    repetidos = repetidos[repetidos.duplicated(keep=False) & (repetidos != "")]
    if len(repetidos):
        nombres_rep = sorted(rest.loc[repetidos.index, "Nombre"].unique())
        print(f"[AVISO] {len(repetidos)} filas de {RESTAURANTES_XLSX.name} tienen un nombre repetido "
              f"({len(nombres_rep)} nombres): {nombres_rep[:8]}{'...' if len(nombres_rep) > 8 else ''}. "
              f"Las reseñas de cada nombre repetido se cruzan TODAS con el mismo ID (el último de ese "
              f"nombre), así que el/los otros ID del mismo restaurante se quedan sin categoría. Revisa y "
              f"quita el duplicado en {RESTAURANTES_XLSX.name} (probablemente hay que volver a ejecutar "
              f"extraer_html.py) y regenera este excel.")

    try:
        v2 = pd.read_excel(RESENAS_XLSX)
    except Exception as e:
        print(f"[AVISO] No se pudo leer {RESENAS_XLSX.name} ({e}); el resultado se genera sin Latitud/Longitud.")
        return rest

    faltan = {"Restaurante", "Latitud", "Longitud"} - set(v2.columns)
    if faltan:
        print(f"[AVISO] A {RESENAS_XLSX.name} le faltan las columnas {sorted(faltan)}; el resultado "
              f"se genera sin Latitud/Longitud.")
        return rest

    ids, _ = _cruzar_por_nombre(v2["Restaurante"], rest)
    v2 = v2.copy()
    v2["ID"] = pd.to_numeric(pd.Series(ids, index=v2.index, dtype="object"), errors="coerce")

    sin_cruzar = sorted(v2.loc[v2["ID"].isna(), "Restaurante"].dropna().unique())
    if sin_cruzar:
        print(f"[AVISO] {len(sin_cruzar)} restaurantes de {RESENAS_XLSX.name} no se pudieron cruzar "
              f"por nombre con {RESTAURANTES_XLSX.name}: {sin_cruzar[:8]}{'...' if len(sin_cruzar) > 8 else ''}.")

    # Localización: una fila por restaurante (la primera que tenga coordenadas válidas).
    # No hace falta avisar aparte de "repetidos" aquí: tener varias filas por restaurante
    # es NORMAL en este archivo (una por reseña), a diferencia del excel de localización
    # de Outscraper (el paso 2 de antes), donde sí era una señal de duplicado real.
    con_coords = v2.dropna(subset=["ID", "Latitud", "Longitud"])
    loc = con_coords.drop_duplicates(subset="ID", keep="first")[["ID", "Latitud", "Longitud"]]

    rest = rest.merge(loc, on="ID", how="left")
    sin_coords = int(rest["Latitud"].isna().sum())
    if sin_coords:
        print(f"[AVISO] {sin_coords} de {len(rest)} restaurantes se han quedado sin Latitud/Longitud "
              f"(no se cruzó el nombre, no se consiguieron reseñas de ese restaurante, o no se pudieron "
              f"sacar coordenadas de su URL de Google Maps). La app no podrá calcular tiempos de "
              f"desplazamiento para ellos, así que no aparecerán en ningún resultado.")
    return rest


def cargar_datos(limite_restaurantes=None):
    """
    Devuelve (restaurantes, reseñas, diagnóstico). `restaurantes` ya trae ID y localización
    (cargar_restaurantes_base). Cada reseña queda asociada a un restaurante por nombre:
    primero cruce exacto y, si falla, cruce aproximado (sin tildes ni signos) cuando no es
    ambiguo. `restaurantes` y `reseñas` se recortan al límite pedido.
    """
    rest = cargar_restaurantes_base()
    try:
        res = pd.read_excel(RESENAS_XLSX)
    except Exception as e:
        raise SystemExit(f"ERROR: no puedo leer {RESENAS_XLSX}: {e}")
    if "Restaurante" not in res.columns or "Texto" not in res.columns:
        raise SystemExit(f"ERROR: a {RESENAS_XLSX.name} le faltan las columnas "
                         f"'Restaurante' y/o 'Texto'.")

    ids, modo = _cruzar_por_nombre(res["Restaurante"], rest)
    res = res.assign(ID_Restaurante=pd.array(ids, dtype="object"))

    sin_cruce = res[res["ID_Restaurante"].isna()]
    con_texto = res["Texto"].apply(lambda t: isinstance(t, str) and len(t.strip()) >= MIN_CARACTERES_RESENA)
    diagnostico = {
        "restaurantes": len(rest), "filas_resenas": len(res), "con_texto_util": int(con_texto.sum()),
        "nombres_distintos": int(res["Restaurante"].nunique()),
        "cruzadas_exacto": modo["exacto"], "cruzadas_aproximado": modo["aproximado"], "sin_cruce": modo["sin_cruce"],
        "nombres_sin_cruce": sorted(sin_cruce["Restaurante"].dropna().astype(str).unique()),
        "ejemplos_resenas": [str(x) for x in res["Restaurante"].dropna().unique()[:5]],
        "ejemplos_v1": [str(x) for x in rest["Nombre"].head(5)],
    }

    res = res[res["ID_Restaurante"].notna()].copy()
    res["ID_Restaurante"] = res["ID_Restaurante"].astype(int)
    if limite_restaurantes:
        rest = rest.head(limite_restaurantes)
    res = res[res["ID_Restaurante"].isin(rest["ID"])]
    return rest, res, diagnostico


def explicar_sin_resenas(d, limite):
    """Mensaje claro cuando no hay ninguna reseña que clasificar (en vez de guardar un excel vacío)."""
    lineas = [
        "ERROR: no hay ninguna reseña que clasificar; no se ha guardado ningún excel.",
        f"  Diagnóstico ({RESENAS_XLSX.name} + {RESTAURANTES_XLSX.name}):",
        f"    - {d['restaurantes']} restaurantes en {RESTAURANTES_XLSX.name}",
        f"    - {d['filas_resenas']} filas en {RESENAS_XLSX.name} ({d['nombres_distintos']} nombres de restaurante distintos)",
        f"    - {d['con_texto_util']} con texto de al menos {MIN_CARACTERES_RESENA} caracteres",
        f"    - {d['cruzadas_exacto'] + d['cruzadas_aproximado']} asociadas a un restaurante por nombre "
        f"({d['cruzadas_exacto']} exactas, {d['cruzadas_aproximado']} aproximadas) · {d['sin_cruce']} sin asociar",
        "  Causa probable:",
    ]
    if d["filas_resenas"] == 0:
        lineas.append(f"    {RESENAS_XLSX.name} está vacío. Comprueba ese archivo.")
    elif d["con_texto_util"] == 0:
        lineas.append("    Hay filas pero ninguna con texto en la columna 'Texto'. Revisa esa columna.")
    elif d["cruzadas_exacto"] + d["cruzadas_aproximado"] == 0:
        lineas.append("    Ningún nombre de las reseñas coincide con los de la lista de restaurantes. Compara los nombres:")
        lineas.append(f"      en las reseñas:        {d['ejemplos_resenas']}")
        lineas.append(f"      en {RESTAURANTES_XLSX.name}: {d['ejemplos_v1']}")
        lineas.append("    Suele pasar si restaurantes_v1.xlsx se regeneró después de descargar las reseñas, con nombres distintos.")
    elif limite:
        lineas.append(f"    Los primeros {limite} restaurantes no tienen reseñas utilizables. Prueba sin --limite.")
    else:
        lineas.append("    Ninguna reseña supera los filtros (texto suficiente y pertenecer a un restaurante).")
    return "\n".join(lineas)


def preparar_resenas(res):
    """Lista de reseñas a clasificar: textos válidos, recortados, con un máximo por restaurante."""
    preparadas, por_restaurante = [], Counter()
    for id_r, texto in zip(res["ID_Restaurante"], res["Texto"]):
        if not isinstance(texto, str):
            continue
        texto = re.sub(r"\s+", " ", texto).strip()
        if len(texto) < MIN_CARACTERES_RESENA:
            continue
        if por_restaurante[id_r] >= MAX_RESENAS_POR_RESTAURANTE:
            continue
        por_restaurante[id_r] += 1
        preparadas.append({"id": int(id_r), "texto": texto[:MAX_CARACTERES_RESENA]})
    return preparadas


def cargar_y_preparar(limite):
    """Carga los datos y prepara las reseñas. Se para con un diagnóstico si no hay ninguna."""
    rest, res, diagnostico = cargar_datos(limite)
    resenas = preparar_resenas(res)
    if not resenas:
        raise SystemExit(explicar_sin_resenas(diagnostico, limite))
    if diagnostico["cruzadas_aproximado"]:
        print(f"  - [AVISO] {diagnostico['cruzadas_aproximado']} reseñas se asociaron a su restaurante por nombre "
              f"APROXIMADO (sin tildes ni signos); el resto, por nombre exacto.")
    if diagnostico["sin_cruce"]:
        ejemplos = ", ".join(repr(n) for n in diagnostico["nombres_sin_cruce"][:5])
        print(f"  - [AVISO] {diagnostico['sin_cruce']} reseñas ({len(diagnostico['nombres_sin_cruce'])} nombres) NO se "
              f"pudieron asociar a ningún restaurante de {RESTAURANTES_XLSX.name} y se ignoran. Ejemplos: {ejemplos}")
    return rest, resenas


# ----------------------- CACHÉ (para poder reanudar) ----------------------- #

class Cache:
    """Guarda cada resultado en un .jsonl en cuanto se calcula: si se corta la ejecución,
    al relanzar no se vuelve a pagar por lo ya hecho. La clave incluye el modelo y la huella
    de las categorías (cocina + sentimiento), así que si cambias cualquiera se recalcula."""

    def __init__(self, ruta, reiniciar=False):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.datos = {}
        if reiniciar and self.ruta.exists():
            self.ruta.unlink()
        if self.ruta.exists():
            with open(self.ruta, encoding="utf-8") as f:
                for linea in f:
                    try:
                        registro = json.loads(linea)
                        self.datos[registro["k"]] = registro["r"]
                    except (json.JSONDecodeError, KeyError):
                        continue

    def get(self, clave):
        return self.datos.get(clave)

    def put(self, clave, resultado):
        with self._lock:
            self.datos[clave] = resultado
            with open(self.ruta, "a", encoding="utf-8") as f:
                f.write(json.dumps({"k": clave, "r": resultado}, ensure_ascii=False) + "\n")


def _clave(modelo, id_r, texto):
    return hashlib.sha1(f"{modelo}|{HUELLA}|{id_r}|{texto}".encode("utf-8")).hexdigest()


# ----------------------- LLAMADA A JEV ----------------------- #

_local = threading.local()
_clientes = []
_lock = threading.Lock()
_tokens_entrada = 0
_modelo = MODELO_DEFECTO


def _cliente():
    """Un cliente por hilo (así no dependemos de que el cliente sea seguro entre hilos)."""
    if not hasattr(_local, "cliente"):
        cliente = TypeSafeClient(model=_modelo, retry=RetryPolicy(max_retries=5), timeout=30.0)
        _local.cliente = cliente
        with _lock:
            _clientes.append(cliente)
    return _local.cliente


def clasificar(texto):
    """Una reseña -> cocina + sentimiento, cada uno con sus probabilidades y confianza. Una
    sola llamada a Jev con las dos preguntas a la vez."""
    global _tokens_entrada
    respuesta = _cliente().system_one(
        state=texto,
        questions={
            "cocina": Choice(instructions=INSTRUCCION_COCINA, criteria=dict(CATEGORIAS)),
            "sentimiento": Choice(instructions=INSTRUCCION_SENTIMIENTO, criteria=dict(CATEGORIAS_SENTIMIENTO)),
        },
    )
    rc, rs = respuesta.choices["cocina"], respuesta.choices["sentimiento"]
    with _lock:
        _tokens_entrada += respuesta.usage.input_tokens or 0
    return {
        "categoria": rc.choice, "categoria_probs": {k: float(v) for k, v in rc.probabilities.items()},
        "categoria_confianza": float(rc.confidence),
        "sentimiento": rs.choice, "sentimiento_probs": {k: float(v) for k, v in rs.probabilities.items()},
        "sentimiento_confianza": float(rs.confidence),
    }


def _comprobar_conexion():
    """Una llamada de prueba para fallar rápido y con un mensaje claro (clave mala, sin red...)."""
    try:
        salida = clasificar("Probamos la paella y el jamón, todo buenísimo.")
    except TypeSafeAuthenticationError:
        raise SystemExit("ERROR: TypeSafe rechaza la clave (TYPESAFE_API_KEY). Revísala: copia completa, sin comillas de más.")
    except TypeSafePermissionDeniedError as e:
        raise SystemExit(f"ERROR: tu cuenta de TypeSafe no tiene permiso para este modelo: {e}")
    except TypeSafeAPIConnectionError as e:
        raise SystemExit(f"ERROR: no consigo conectar con la API de TypeSafe (¿conexión a internet?): {e}")
    except TypeSafeError as e:
        raise SystemExit(f"ERROR de TypeSafe en la llamada de prueba: {e}")
    print(f"  - Conexión OK (prueba: cocina='{salida['categoria']}' ({salida['categoria_confianza']:.2f}), "
          f"sentimiento='{salida['sentimiento']}' ({salida['sentimiento_confianza']:.2f}))")


def _cerrar_clientes():
    for c in _clientes:
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass


# ----------------------- CLASIFICACIÓN DE TODAS LAS RESEÑAS ----------------------- #

def clasificar_todas(resenas, cache, hilos=1, max_errores_seguidos=8):
    """
    Clasifica cada reseña (en paralelo, usando la caché). Devuelve una lista de resultados en el
    mismo orden que `resenas`; cada uno trae "categoria", "sentimiento" y sus probabilidades y
    confianza, más "estado" ("ok" o "error"). Las reseñas que fallan no se guardan en caché
    (se reintentan al relanzar).
    """
    resultados = [None] * len(resenas)
    pendientes = []
    for i, r in enumerate(resenas):
        guardado = cache.get(_clave(_modelo, r["id"], r["texto"]))
        if guardado is not None:
            resultados[i] = {**guardado, "estado": "ok"}
        else:
            pendientes.append(i)

    print(f"  - {len(resenas)} reseñas a clasificar: {len(resenas) - len(pendientes)} ya en caché, "
          f"{len(pendientes)} por calcular (hilos: {hilos})")
    if not pendientes:
        return resultados

    t0, hechas, errores_seguidos, ultimo_error = time.time(), 0, 0, ""

    def trabajo(i):
        salida = clasificar(resenas[i]["texto"])
        if salida.get("categoria") not in CATEGORIAS:
            raise ValueError(f"categoría de cocina inválida: {salida.get('categoria')!r}")
        if salida.get("sentimiento") not in CATEGORIAS_SENTIMIENTO:
            raise ValueError(f"categoría de sentimiento inválida: {salida.get('sentimiento')!r}")
        return i, salida

    with ThreadPoolExecutor(max_workers=max(1, hilos)) as pool:
        futuros = {pool.submit(trabajo, i): i for i in pendientes}
        try:
            for futuro in as_completed(futuros):
                i = futuros[futuro]
                hechas += 1
                try:
                    _, resultado = futuro.result()
                    cache.put(_clave(_modelo, resenas[i]["id"], resenas[i]["texto"]), resultado)
                    resultados[i] = {**resultado, "estado": "ok"}
                    errores_seguidos = 0
                except Exception as e:  # noqa: BLE001 - queremos seguir con el resto
                    resultados[i] = {"categoria": None, "sentimiento": None, "categoria_probs": None,
                                     "sentimiento_probs": None, "categoria_confianza": None,
                                     "sentimiento_confianza": None, "estado": "error", "error": str(e)[:200]}
                    errores_seguidos += 1
                    ultimo_error = str(e)[:300]
                    if errores_seguidos >= max_errores_seguidos:
                        raise SystemExit(f"\nABORTO: {errores_seguidos} errores seguidos. Último error: {ultimo_error}\n"
                                         f"Lo ya calculado está guardado en caché; corrige el problema y vuelve a lanzar.")
                if hechas % 25 == 0 or hechas == len(pendientes):
                    ritmo = hechas / max(time.time() - t0, 1e-9)
                    faltan = (len(pendientes) - hechas) / max(ritmo, 1e-9)
                    print(f"    {hechas}/{len(pendientes)} ({ritmo:.1f}/s, quedan ~{faltan / 60:.1f} min)")
        except BaseException:
            # Salida limpia, Ctrl+C o demasiados errores: cancelamos lo que queda en cola.
            for f in futuros:
                f.cancel()
            raise
    return resultados


# ----------------------- AGRUPAR POR RESTAURANTE ----------------------- #

def agregar_restaurante(resultados):
    """
    Cocina: entre las reseñas informativas (todas menos "no_se_sabe") gana la categoría con
    más votos; en empate, la primera de CATEGORIAS. Menos de MIN_RESENAS_INFORMATIVAS =>
    "sin_datos_suficientes". Sentimiento: recuento simple de Buena/Mala/Neutra entre TODAS
    las reseñas correctamente clasificadas (el sentimiento no depende de si la reseña habla
    de comida o no).
    """
    ok = [r for r in resultados if r["estado"] == "ok"]
    informativas = [r for r in ok if r["categoria"] != CATEGORIA_SIN_DATOS]
    votos = Counter(r["categoria"] for r in informativas)
    sentimientos = Counter(r["sentimiento"] for r in ok)
    confianzas_sent = [r["sentimiento_confianza"] for r in ok if r.get("sentimiento_confianza") is not None]

    base = {
        "Reseñas leídas": len(ok), "Reseñas informativas (cocina)": len(informativas),
        "Reseñas con error": len(resultados) - len(ok),
        "Reseñas buenas": sentimientos.get("Buena", 0), "Reseñas malas": sentimientos.get("Mala", 0),
        "Reseñas neutras": sentimientos.get("Neutra", 0),
        "Confianza sentimiento (Jev)": round(sum(confianzas_sent) / len(confianzas_sent), 3) if confianzas_sent else None,
    }

    # Nota: "Votos" y "Margen" se calculan siempre sobre las CLAVES internas de Jev (para que
    # los porcentajes tengan sentido); solo "Categoría (Jev)" y "Categoría 2ª (Jev)" -lo que ve
    # la persona que usa la app- pasan por etiqueta_categoria() para mostrarse en bonito.
    if len(informativas) < MIN_RESENAS_INFORMATIVAS:
        base.update({"Categoría (Jev)": None, "% votos categoría (Jev)": None, "Categoría 2ª (Jev)": None,
                     "% votos 2ª (Jev)": None, "Margen": None, "Empate": "", "Votos": "",
                     "Confianza categoría (Jev)": None})
        return base

    orden = sorted(votos.items(), key=lambda kv: (-kv[1], _ORDEN[kv[0]]))
    n = len(informativas)
    (cat1, v1) = orden[0]
    (cat2, v2) = orden[1] if len(orden) > 1 else ("", 0)
    confianzas_cat = [r["categoria_confianza"] for r in informativas if r.get("categoria_confianza") is not None]
    base.update({
        "Categoría (Jev)": etiqueta_categoria(cat1), "% votos categoría (Jev)": round(v1 / n, 3),
        "Categoría 2ª (Jev)": etiqueta_categoria(cat2), "% votos 2ª (Jev)": round(v2 / n, 3) if v2 else None,
        "Margen": round((v1 - v2) / n, 3), "Empate": "sí" if v2 == v1 else "",
        "Votos": ", ".join(f"{c}: {v}" for c, v in orden),
        "Confianza categoría (Jev)": round(sum(confianzas_cat) / len(confianzas_cat), 3) if confianzas_cat else None,
    })
    return base


def agregar_platos(pares_ok):
    """`pares_ok`: lista de (texto, resultado) de reseñas "ok" de un restaurante. Cuenta, entre
    TODAS las categorías (no solo la ganadora), qué platos aparecen en reseñas Buenas y cuáles
    en reseñas Malas. Es el equivalente a "Platos mejor/peor valorados" de la versión anterior,
    pero calculado con los platos de ejemplo de Jev en vez del diccionario."""
    mejor, peor = Counter(), Counter()
    for texto, res in pares_ok:
        if res["sentimiento"] not in ("Buena", "Mala"):
            continue
        destino = mejor if res["sentimiento"] == "Buena" else peor
        for plato, _cat in todos_los_platos_en_texto(texto):
            destino[plato] += 1
    formatear = lambda c: ", ".join(f"{p} ({n})" for p, n in c.most_common(TOP_PLATOS))  # noqa: E731
    return formatear(mejor), formatear(peor)


# ----------------------- EXCEL DE SALIDA ----------------------- #

def _limpiar(valor):
    return ILLEGAL_CHARACTERS_RE.sub("", valor) if isinstance(valor, str) else valor


def _largo_tipico(serie):
    """Largo de texto típico (percentil 90) de una columna. Robusto a columnas vacías (en
    pandas 3, una columna entera vacía da NaN en vez de una lista con la que calcular)."""
    largos = [len(str(v)) for v in serie if v is not None and not pd.isna(v)]
    return int(pd.Series(largos).quantile(0.9)) if largos else 0


def _estilo(ws, df):
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="2F5496")
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, col in enumerate(df.columns, start=1):
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(12, _largo_tipico(df[col]) + 2, len(str(col)) + 2))
    ws.freeze_panes = "A2"


def guardar_excel(ruta, *, rest, resenas, resultados, por_restaurante, extra_config):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nombres = dict(zip(rest["ID"], rest["Nombre"]))

    # --- Restaurantes: todas las columnas de rest (ID, Nombre, Puntuación, precio, Google,
    #     imagen, localización...) + lo agregado (cocina, sentimiento, platos) ---
    df_rest = rest.reset_index(drop=True).copy()
    df_agg = pd.DataFrame(por_restaurante)
    df_rest = pd.concat([df_rest, df_agg], axis=1)

    # Sin categoría de Jev (pocas o ninguna reseña informativa): se usa el tipo de cocina de
    # Google tal cual, en vez de dejarlo vacío. OJO: ese campo de Google a veces no es una
    # cocina (puede ser "Restaurante", "Bar de tapas"...), así que puede que no encaje del todo
    # con las demás categorías, pero es mejor que no tener nada.
    if "Tipo de cocina" in df_rest.columns:
        sin_categoria = df_rest["Categoría (Jev)"].isna()
        google_valido = df_rest["Tipo de cocina"].apply(lambda v: isinstance(v, str) and v.strip() != "")
        usar_google = sin_categoria & google_valido
        if usar_google.any():
            df_rest.loc[usar_google, "Categoría (Jev)"] = df_rest.loc[usar_google, "Tipo de cocina"]
            nombres_rellenados = ", ".join(df_rest.loc[usar_google, "Nombre"].astype(str))
            print(f"[AVISO] {int(usar_google.sum())} restaurantes sin categoría de Jev: se ha usado su "
                  f"'Tipo de cocina' de Google en su lugar ({nombres_rellenados}).")

    # --- Reseñas ---
    filas_r = []
    for r, res in zip(resenas, resultados):
        cprobs, sprobs = res.get("categoria_probs") or {}, res.get("sentimiento_probs") or {}
        top3 = sorted(cprobs.items(), key=lambda kv: -kv[1])[:3]
        encontrados = terminos_encontrados(r["texto"], res["categoria"]) if res["categoria"] else []
        filas_r.append({
            "ID": r["id"], "Restaurante": nombres.get(r["id"]), "Texto": r["texto"],
            "Categoría": res["categoria"] or "",
            "Estado": res["estado"] if res["estado"] == "ok" else f"error: {res.get('error', '')}",
            "Probabilidad cocina elegida": round(cprobs.get(res["categoria"], 0), 3) if res["categoria"] else None,
            "Confianza cocina": res.get("categoria_confianza"),
            "Top 3 probabilidades cocina": ", ".join(f"{c}: {p:.2f}" for c, p in top3),
            "Platos de ejemplo encontrados en el texto": ", ".join(encontrados),
            "Sentimiento": res["sentimiento"] or "",
            "Probabilidad sentimiento elegido": round(sprobs.get(res["sentimiento"], 0), 3) if res["sentimiento"] else None,
            "Confianza sentimiento": res.get("sentimiento_confianza"),
        })
    df_resenas = pd.DataFrame(filas_r)

    # --- Platos mencionados (equivalente al de analizar_resenas.py; lo usa la app para la
    #     búsqueda de "¿Algún plato concreto?") ---
    filas_p = []
    for r, res in zip(resenas, resultados):
        if res["estado"] != "ok":
            continue
        for plato, cat in todos_los_platos_en_texto(r["texto"]):
            filas_p.append({"ID_Restaurante": r["id"], "Restaurante": nombres.get(r["id"]), "Plato": plato,
                            "Categoría del plato": cat, "Sentimiento": res["sentimiento"], "Fragmento": r["texto"]})
    df_platos = pd.DataFrame(filas_p, columns=["ID_Restaurante", "Restaurante", "Plato", "Categoría del plato",
                                               "Sentimiento", "Fragmento"])

    # --- Configuración ---
    config = [
        ("Modelo", "Jev"), ("Identificador del modelo", _modelo), ("Fecha", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("HUELLA de categorías", HUELLA), ("Pregunta cocina", INSTRUCCION_COCINA),
        ("Pregunta sentimiento", INSTRUCCION_SENTIMIENTO),
        ("Reseñas mín./máx. caracteres", f"{MIN_CARACTERES_RESENA} / {MAX_CARACTERES_RESENA}"),
        ("Reseñas máx. por restaurante", MAX_RESENAS_POR_RESTAURANTE),
        ("Reseñas informativas mínimas", MIN_RESENAS_INFORMATIVAS), *extra_config,
    ]
    df_conf = pd.DataFrame(config, columns=["Parámetro", "Valor"])

    # --- Categorías (cocina + sentimiento en una sola hoja, con una columna 'Tipo') ---
    df_cats = pd.DataFrame(
        [(k, v, "cocina") for k, v in CATEGORIAS.items()] +
        [(k, v, "sentimiento") for k, v in CATEGORIAS_SENTIMIENTO.items()],
        columns=["Clave", "Descripción", "Tipo"],
    )

    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        for nombre, df in [("Restaurantes", df_rest), ("Reseñas", df_resenas), ("Platos mencionados", df_platos),
                           ("Configuración", df_conf), ("Categorías", df_cats)]:
            df = df.map(_limpiar) if hasattr(df, "map") else df.applymap(_limpiar)
            df.to_excel(w, sheet_name=nombre, index=False)
            _estilo(w.sheets[nombre], df)


# ----------------------- LÍNEA DE COMANDOS Y EJECUCIÓN ----------------------- #

def parsear_argumentos():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limite", type=int, default=None, metavar="N",
                   help="clasificar solo los primeros N restaurantes (para probar barato/rápido)")
    p.add_argument("--modelo", default=MODELO_DEFECTO, help=f"modelo a usar (por defecto: {MODELO_DEFECTO})")
    p.add_argument("--hilos", type=int, default=HILOS_DEFECTO, help=f"peticiones en paralelo (por defecto: {HILOS_DEFECTO})")
    p.add_argument("--reiniciar", action="store_true", help="ignorar y borrar la caché")
    p.add_argument("--verbose", action="store_true",
                   help="imprime por pantalla, restaurante a restaurante, la clasificación de cada una de sus "
                       "reseñas (cocina, sentimiento, confianza) y el resultado final agregado. Solo IMPRIME: "
                       "no cambia ningún cálculo ni lo que se guarda en el excel.")
    p.add_argument("--probar", metavar="TEXTO", default=None,
                   help='clasifica solo este texto y lo imprime, sin tocar ningún excel. Ej.: --probar "cachopo y cecina espectacular"')
    return p.parse_args()


def imprimir_prueba(salida):
    print(f"\nCocina:       {salida['categoria']}  (confianza {salida['categoria_confianza']:.3f})")
    if salida.get("categoria_probs"):
        for cat, p in sorted(salida["categoria_probs"].items(), key=lambda kv: -kv[1])[:6]:
            print(f"   {cat:22s} {p:.3f}")
    print(f"Sentimiento:  {salida['sentimiento']}  (confianza {salida['sentimiento_confianza']:.3f})")
    if salida.get("sentimiento_probs"):
        for cat, p in sorted(salida["sentimiento_probs"].items(), key=lambda kv: -kv[1]):
            print(f"   {cat:22s} {p:.3f}")


def imprimir_detalle_restaurante(nombre, id_r, pares, fila):
    """Solo IMPRIME. Recibe exactamente los mismos `pares` (texto, resultado) y la misma `fila`
    ya agregada que usa ejecutar() para construir el excel -no repite ni recalcula nada-, así que
    lo que se ve aquí es siempre igual a lo que acaba en la hoja Restaurantes."""
    print(f"\n{'─' * 70}\n[{id_r}] {nombre}  ({len(pares)} reseñas leídas)")
    for texto, res in pares:
        extracto = (texto[:70] + "…") if len(texto) > 70 else texto
        if res["estado"] != "ok":
            print(f"  ERROR: {res.get('error', '')}  | {extracto!r}")
            continue
        print(f"  cocina={res['categoria']:22s} (conf. {res['categoria_confianza']:.2f})  "
              f"sentimiento={res['sentimiento']:6s} (conf. {res['sentimiento_confianza']:.2f})  | {extracto!r}")
    print(f"  -> RESULTADO AGREGADO: Categoría (Jev) = {fila.get('Categoría (Jev)')!r} "
          f"(% votos {fila.get('% votos categoría (Jev)')}, empate={fila.get('Empate') or 'no'}) "
          f"| Votos: {fila.get('Votos')} "
          f"| Reseñas buenas/malas/neutras: {fila.get('Reseñas buenas')}/{fila.get('Reseñas malas')}/{fila.get('Reseñas neutras')}")


def ejecutar(args, rest, resenas):
    """Flujo completo: clasificar cada reseña -> agrupar por restaurante -> guardar excel."""
    print(f"\n=== Clasificación con Jev ({_modelo}) · huella de categorías: {HUELLA} ===")
    print(f"  - {len(rest)} restaurantes, {len(resenas)} reseñas válidas "
          f"(≥{MIN_CARACTERES_RESENA} caracteres, máx. {MAX_RESENAS_POR_RESTAURANTE} por restaurante)")
    cache = Cache(CACHE_DIR / "cache_jev.jsonl", reiniciar=args.reiniciar)

    resultados = clasificar_todas(resenas, cache, hilos=args.hilos)

    por_id = {i: [] for i in rest["ID"]}
    for r, res_ in zip(resenas, resultados):
        por_id[r["id"]].append((r["texto"], res_))

    por_restaurante = []
    nombres_por_id = dict(zip(rest["ID"], rest["Nombre"]))
    for id_r in rest["ID"]:
        pares = por_id[id_r]
        fila = agregar_restaurante([res for _, res in pares])
        fila["Platos mejor valorados"], fila["Platos peor valorados"] = agregar_platos(
            [(t, res) for t, res in pares if res["estado"] == "ok"])
        por_restaurante.append(fila)
        if args.verbose:
            imprimir_detalle_restaurante(nombres_por_id[id_r], id_r, pares, fila)

    coste = _tokens_entrada / 1_000_000 * PRECIO_USD_POR_MILLON_TOKENS
    print(f"  - Tokens de entrada consumidos en esta ejecución: {_tokens_entrada:,} "
          f"(≈ {coste:.4f} USD a {PRECIO_USD_POR_MILLON_TOKENS} USD/millón)")
    extra = [("Tokens de entrada (esta ejecución)", _tokens_entrada), ("Coste estimado USD (esta ejecución)", round(coste, 5)),
             ("Precio supuesto USD por millón de tokens", PRECIO_USD_POR_MILLON_TOKENS),
             ("Origen de las reseñas y la localización", RESENAS_XLSX.name), ("Origen de los restaurantes", RESTAURANTES_XLSX.name)]
    guardar_excel(SALIDA_XLSX, rest=rest, resenas=resenas, resultados=resultados,
                  por_restaurante=por_restaurante, extra_config=extra)

    cats = Counter(f["Categoría (Jev)"] for f in por_restaurante)
    sent = Counter()
    for f in por_restaurante:
        sent["Buena"] += f["Reseñas buenas"]; sent["Mala"] += f["Reseñas malas"]; sent["Neutra"] += f["Reseñas neutras"]
    errores = sum(1 for r in resultados if r["estado"] != "ok")
    print(f"\nGuardado: {SALIDA_XLSX}")
    print("  - Cocina por restaurante: " + ", ".join(f"{c}: {n}" for c, n in cats.most_common()))
    print(f"  - Sentimiento por reseña: Buena {sent['Buena']}, Mala {sent['Mala']}, Neutra {sent['Neutra']}")
    if errores:
        print(f"  - [AVISO] {errores} reseñas con error (no se han guardado en caché: se reintentarán al relanzar)")


def main():
    global _modelo
    args = parsear_argumentos()
    _modelo = args.modelo

    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit(
            "ERROR: no encuentro la variable de entorno TYPESAFE_API_KEY.\n"
            '  Windows (PowerShell):  $env:TYPESAFE_API_KEY = "tu_clave"\n'
            '  Mac/Linux:             export TYPESAFE_API_KEY="tu_clave"\n'
            "  (Defínela en la MISMA ventana de terminal donde ejecutas el script.)")

    if args.probar:
        _comprobar_conexion()
        imprimir_prueba(clasificar(args.probar))
    else:
        rest, resenas = cargar_y_preparar(args.limite)   # falla antes de gastar nada si no hay reseñas
        _comprobar_conexion()
        ejecutar(args, rest, resenas)
    _cerrar_clientes()


if __name__ == "__main__":
    main()