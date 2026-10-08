"""
App web (Streamlit) que convierte la encuesta + algoritmo de recomendación
en una página que se abre desde el navegador del móvil.

Reutiliza toda la lógica de encuesta.py (parseo de precios, scoring,
geocoding, tiempos en coche vía OSRM) pero con un formulario web en vez de
preguntas por terminal, y muestra el resultado en tarjetas + mapa.

ESTRUCTURA DE CARPETAS ESPERADA (este archivo vive en algoritmo/):
    proyecto/
      excels/
        clasificacion_jev.xlsx   <- lo genera obtener_datos/clasificar_restaurantes_jev.py
      algoritmo/
        app.py          <- este archivo
        encuesta.py

USO LOCAL (para probarlo antes de desplegar):
    pip install -r requirements.txt
    streamlit run algoritmo/app.py      (desde la raíz del proyecto)
    -- o --
    cd algoritmo && streamlit run app.py   (funciona igual, la ruta al
    excel se calcula a partir de dónde está este archivo, no de desde
    dónde se lanza el comando)

DESPLIEGUE (para tener una URL pública desde el móvil):
    1. Sube TODO el proyecto (carpetas excels/ y algoritmo/ incluidas,
       con requirements.txt en la raíz) a un repositorio de GitHub
       (puede ser privado).
    2. Ve a https://share.streamlit.io, entra con tu cuenta de GitHub.
    3. "New app" -> selecciona el repo, la rama, y como "Main file path"
       escribe: algoritmo/app.py   (con la ruta de la subcarpeta)
    4. Te da una URL tipo https://tuapp.streamlit.app -> ábrela en el
       móvil y guárdala en la pantalla de inicio como acceso directo.
"""

import re
import math
import base64
import time
import unicodedata
import urllib.parse
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from geopy.exc import GeocoderServiceError


# ----------------------- CONFIGURACIÓN ----------------------- #

# Ruta calculada a partir de la ubicación de ESTE archivo (no de desde
# dónde se ejecute el comando), para que funcione tanto si lanzas
# `streamlit run algoritmo/app.py` desde la raíz como si haces `cd
# algoritmo` primero.
BASE_DIR = Path(__file__).resolve().parent
MAESTRO_XLSX = BASE_DIR.parent / "excels" / "clasificacion_jev.xlsx"
IMAGENES_DIR = BASE_DIR.parent / "imagenes"

PESO_PRECIO = 0.15
PESO_COCINA = 0.30
PESO_PLATO = 0.20
PESO_CALIDAD = 0.30
PESO_NUM_RESENAS = 0.05

TOP_N = 5
TOP_N_MAX = 10

# Categoría de cocina calculada con Jev (columnas que trae clasificacion_jev.xlsx).
COL_CATEGORIA = "Categoría (Jev)"
COL_CATEGORIA_2 = "Categoría 2ª (Jev)"
COL_VOTOS_1 = "% votos categoría (Jev)"
COL_VOTOS_2 = "% votos 2ª (Jev)"
SCORE_COCINA_SECUNDARIA = 0.6    # el restaurante tiene la cocina elegida como segunda categoría
SCORE_COCINA_DESCONOCIDA = 0.3   # Jev no pudo clasificarlo (pocas reseñas informativas): ni sí ni no
VOTOS_MIN_SECUNDARIA = 0.25      # la segunda categoría solo cuenta si tiene al menos este % de los votos

OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
OSRM_BATCH_SIZE = 100
VELOCIDAD_RESPALDO_COCHE_KMH = 30

ORS_URL = "https://api.openrouteservice.org/v2/matrix/foot-walking"
ORS_BATCH_SIZE = 50
VELOCIDAD_RESPALDO_ANDANDO_KMH = 5

CAJA_MADRID = [(41.17, -4.58), (39.88, -3.05)]   # Comunidad de Madrid (esquinas NO y SE)

# --------------------------------------------------------------- #


@st.cache_data
def cargar_datos():
    maestro = pd.read_excel(MAESTRO_XLSX, sheet_name="Restaurantes")
    try:
        df_platos = pd.read_excel(MAESTRO_XLSX, sheet_name="Platos mencionados")
    except Exception:
        df_platos = pd.DataFrame(columns=["ID_Restaurante", "Plato", "Sentimiento"])
    return maestro, df_platos


def parsear_rango_precio(texto):
    if not isinstance(texto, str) or not texto.strip():
        return None, None
    numeros = [int(n) for n in re.findall(r"\d+", texto)]
    if len(numeros) >= 2:
        return min(numeros), max(numeros)
    if len(numeros) == 1:
        if "más" in texto.lower() or "+" in texto:
            return numeros[0], None
        return None, numeros[0]
    return None, None


def solapamiento(min1, max1, min2, max2):
    if min1 is None and max1 is None:
        return 0.5
    if min2 is None and max2 is None:
        return 0.5
    lo1 = min1 if min1 is not None else 0
    hi1 = max1 if max1 is not None else float("inf")
    lo2 = min2 if min2 is not None else 0
    hi2 = max2 if max2 is not None else float("inf")
    inicio_solape = max(lo1, lo2)
    fin_solape = min(hi1, hi2)
    solape = max(0, fin_solape - inicio_solape)
    ancho_union = max(hi1, hi2) - min(lo1, lo2)
    if ancho_union in (0, float("inf")):
        return 1.0 if solape > 0 else 0.0
    return min(1.0, solape / ancho_union)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def geocodificar_direccion(direccion):
    """Devuelve el Location de geopy (o None si no la encuentra). Solo busca dentro de la
    Comunidad de Madrid y añade "Madrid" al texto: sin eso, "Chueca" acababa en Toledo y
    "Calle Princesa 1" en Marbella. Si el servicio falla, la excepción sube (no es lo mismo
    que "no existe esa dirección")."""
    from geopy.geocoders import Nominatim

    consulta = direccion if "madrid" in direccion.lower() else f"{direccion}, Madrid"
    geolocalizador = Nominatim(user_agent="app_restaurantes_pareja")
    return geolocalizador.geocode(consulta, timeout=10, viewbox=CAJA_MADRID, bounded=True)


def obtener_minutos_coche(ubicacion_usuario, maestro):
    lat_u, lon_u = ubicacion_usuario
    minutos = [None] * len(maestro)

    indices_validos = [
        i for i in range(len(maestro))
        if pd.notna(maestro.iloc[i]["Latitud"]) and pd.notna(maestro.iloc[i]["Longitud"])
    ]

    for start in range(0, len(indices_validos), OSRM_BATCH_SIZE):
        lote_idx = indices_validos[start:start + OSRM_BATCH_SIZE]
        coords = [f"{lon_u},{lat_u}"] + [
            f"{maestro.iloc[i]['Longitud']},{maestro.iloc[i]['Latitud']}" for i in lote_idx
        ]
        url = OSRM_URL + ";".join(coords)
        try:
            resp = requests.get(url, params={"sources": "0", "annotations": "duration"}, timeout=30)
            resp.raise_for_status()
            duraciones = resp.json()["durations"][0]
            for j, idx in enumerate(lote_idx):
                dur_seg = duraciones[j + 1]
                if dur_seg is not None:
                    minutos[idx] = dur_seg / 60.0
        except Exception:
            for idx in lote_idx:
                fila = maestro.iloc[idx]
                dist_km = haversine_km(lat_u, lon_u, fila["Latitud"], fila["Longitud"])
                minutos[idx] = (dist_km / VELOCIDAD_RESPALDO_COCHE_KMH) * 60

        if start + OSRM_BATCH_SIZE < len(indices_validos):
            time.sleep(1)

    return minutos


def obtener_minutos_a_pie(ubicacion_usuario, maestro):
    """
    Igual que obtener_minutos_coche pero vía OpenRouteService (perfil
    foot-walking). El modo a pie de la matriz de ORS falla a veces con un
    error 6099 ('Unable to compute a distance/duration matrix') en ciertas
    coordenadas -es un bug conocido de su lado, no nuestro-, así que ante
    cualquier fallo caemos también a una estimación por distancia en línea
    recta a velocidad media andando (5 km/h).
    """
    lat_u, lon_u = ubicacion_usuario
    minutos = [None] * len(maestro)

    indices_validos = [
        i for i in range(len(maestro))
        if pd.notna(maestro.iloc[i]["Latitud"]) and pd.notna(maestro.iloc[i]["Longitud"])
    ]

    def respaldo_haversine(idx):
        fila = maestro.iloc[idx]
        dist_km = haversine_km(lat_u, lon_u, fila["Latitud"], fila["Longitud"])
        return (dist_km / VELOCIDAD_RESPALDO_ANDANDO_KMH) * 60

    api_key = leer_secreto("ORS_API_KEY")
    if not api_key:
        st.warning("No hay configurada una clave de OpenRouteService (ORS_API_KEY) en los "
                   "secretos de la app: se está estimando el tiempo a pie por distancia en "
                   "línea recta, no por calles reales.")
        for idx in indices_validos:
            minutos[idx] = respaldo_haversine(idx)
        return minutos

    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    for start in range(0, len(indices_validos), ORS_BATCH_SIZE):
        lote_idx = indices_validos[start:start + ORS_BATCH_SIZE]
        locations = [[lon_u, lat_u]] + [
            [maestro.iloc[i]["Longitud"], maestro.iloc[i]["Latitud"]] for i in lote_idx
        ]
        body = {"locations": locations, "sources": [0], "metrics": ["duration"]}
        try:
            resp = requests.post(ORS_URL, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
            duraciones = resp.json()["durations"][0]
            for j, idx in enumerate(lote_idx):
                dur_seg = duraciones[j + 1]
                minutos[idx] = dur_seg / 60.0 if dur_seg is not None else respaldo_haversine(idx)
        except Exception:
            for idx in lote_idx:
                minutos[idx] = respaldo_haversine(idx)

        if start + ORS_BATCH_SIZE < len(indices_validos):
            time.sleep(2)

    return minutos


def puntuacion_plato(id_restaurante, plato_deseado, df_platos):
    if not plato_deseado:
        return 0.0
    if df_platos.empty or "ID_Restaurante" not in df_platos.columns:
        return 0.0
    menciones = df_platos[
        (df_platos["ID_Restaurante"] == id_restaurante) &
        (df_platos["Plato"].astype(str).str.contains(plato_deseado, case=False, na=False))
    ]
    if menciones.empty:
        return 0.0
    buenas = (menciones["Sentimiento"] == "Buena").sum()
    malas = (menciones["Sentimiento"] == "Mala").sum()
    total = len(menciones)
    ratio_positivo = buenas / total if total else 0
    bonus_volumen = min(0.2, 0.05 * total)
    return min(1.0, ratio_positivo + bonus_volumen) if buenas >= malas else max(0.0, ratio_positivo - 0.2)


def calcular_score_calidad(fila):
    score_estrellas = (fila["Puntuación"] or 0) / 5.0
    buenas = fila.get("Reseñas buenas", 0)
    malas = fila.get("Reseñas malas", 0)
    neutras = fila.get("Reseñas neutras", 0)
    buenas = 0 if pd.isna(buenas) else buenas
    malas = 0 if pd.isna(malas) else malas
    neutras = 0 if pd.isna(neutras) else neutras
    total_analizadas = buenas + malas + neutras
    if total_analizadas > 0:
        proporcion_buenas = buenas / total_analizadas
        return 0.6 * score_estrellas + 0.4 * proporcion_buenas
    return score_estrellas


def tiene_categorias_jev(maestro):
    """¿Trae el maestro la categoría de cocina de Jev? Si no (maestro antiguo), se usa la de Google."""
    return COL_CATEGORIA in maestro.columns and maestro[COL_CATEGORIA].notna().any()


def _sin_tildes(texto):
    if not isinstance(texto, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))


_STOPWORDS_COCINA = {"y", "de", "del", "la", "el", "las", "los", "otras", "otra"}
_RAIZ_MIN = 5   # comparamos por raíz de palabra: "arroces"/"arrocería" o "vegana"/"vegano"
                # no coinciden letra por letra, pero sus 5 primeras letras sí


def _palabras_significativas(texto):
    """Raíces de las palabras de 4+ letras de `texto`, sin tildes ni conectores ('y', 'de',
    'otras'...). Se usa para comparar una etiqueta de Jev tipo "Asiática (otras)" contra el
    texto libre de Google: comparar la frase completa casi nunca coincide, y comparar palabra
    a palabra tampoco (género/número distintos), así que se compara por raíz."""
    palabras = [p for p in re.findall(r"[a-z]+", _sin_tildes(texto)) if len(p) >= 4 and p not in _STOPWORDS_COCINA]
    return [p[:_RAIZ_MIN] for p in palabras]


def _coincide_con_google(etiqueta_elegida, texto_google):
    palabras = _palabras_significativas(etiqueta_elegida)
    if not palabras:
        return False
    texto_norm = _sin_tildes(texto_google)
    return any(p in texto_norm for p in palabras)


def puntuacion_cocina(fila, cocina_elegida, con_jev):
    """
    Encaje (0-1) entre la cocina elegida y la del restaurante.
    Con categorías de Jev: 1 si es su categoría principal (o hay empate con la segunda), 0.6 si es
    la segunda con peso suficiente, 0 si tiene otra cocina, y 0.3 si Jev no pudo clasificarlo
    (salvo que la etiqueta de Google contenga esa cocina, que cuenta como 1).
    Sin categorías de Jev (maestro antiguo): coincidencia de texto con el tipo de Google, como antes.
    """
    if not cocina_elegida:
        return 0.5
    if not con_jev:
        return 1.0 if cocina_elegida.lower() in str(fila["Tipo de cocina"]).lower() else 0.0

    principal = fila.get(COL_CATEGORIA)
    if isinstance(principal, str) and principal.strip():
        if principal == cocina_elegida:
            return 1.0
        if fila.get(COL_CATEGORIA_2) == cocina_elegida:
            v1, v2 = fila.get(COL_VOTOS_1), fila.get(COL_VOTOS_2)
            if pd.notna(v1) and pd.notna(v2) and v2 >= v1:
                return 1.0                     # empate: la "segunda" es tan buena como la principal
            if pd.notna(v2) and v2 >= VOTOS_MIN_SECUNDARIA:
                return SCORE_COCINA_SECUNDARIA
        return 0.0

    return 1.0 if _coincide_con_google(cocina_elegida, fila.get("Tipo de cocina")) else SCORE_COCINA_DESCONOCIDA


def etiqueta_cocina(fila):
    """Cocina que se muestra en la tarjeta: la de Jev (con la segunda si pesa lo suficiente, para
    explicar por qué sale al buscar esa cocina) o, si no hay, la de Google."""
    principal = fila.get(COL_CATEGORIA)
    if isinstance(principal, str) and principal.strip():
        segunda, v2 = fila.get(COL_CATEGORIA_2), fila.get(COL_VOTOS_2)
        if isinstance(segunda, str) and segunda.strip() and pd.notna(v2) and v2 >= VOTOS_MIN_SECUNDARIA:
            return f"{principal} · también {segunda}"
        return principal
    return valor_o(fila, "Tipo de cocina")


def filtrar_y_puntuar(maestro, df_platos, r):
    df = maestro.copy()
    if r["modo_transporte"] == "A pie":
        df["Tiempo desplazamiento (min)"] = obtener_minutos_a_pie(r["ubicacion_usuario"], df)
    else:
        df["Tiempo desplazamiento (min)"] = obtener_minutos_coche(r["ubicacion_usuario"], df)

    df = df[df["Tiempo desplazamiento (min)"].notna() & (df["Tiempo desplazamiento (min)"] <= r["tiempo_maximo_min"])]
    if df.empty:
        return df

    # Filtros estrictos: solo pasan los que cumplen lo pedido; si no hay, no se rellena con otros.
    con_jev_filtro = tiene_categorias_jev(maestro)
    if r["cocina"]:
        # Exige cocina principal o segunda con peso; descarta los de otra cocina y los no clasificados.
        df = df[df.apply(lambda f: puntuacion_cocina(f, r["cocina"], con_jev_filtro) >= SCORE_COCINA_SECUNDARIA, axis=1)]

    def encaja_precio(texto):
        min_r, max_r = parsear_rango_precio(texto)
        # ponytail: sin precio conocido no se puede descartar, se deja pasar
        return (min_r is None and max_r is None) or solapamiento(min_r, max_r, r["presupuesto_min"], r["presupuesto_max"]) > 0
    df = df[df["Rango de precios"].apply(encaja_precio)]

    if r["plato_deseado"]:
        df = df[df["ID"].apply(lambda i: puntuacion_plato(i, r["plato_deseado"], df_platos) > 0)]
    if df.empty:
        return df

    max_resenas = maestro["Nº Reseñas"].max() or 1
    con_jev = tiene_categorias_jev(maestro)

    # Sin plato concreto, puntuacion_plato() da 0.0 a todos por igual (no discrimina nada), así
    # que ese 20% de PESO_PLATO se perdería sin más. En ese caso lo pasamos a la cocina, que pasa
    # de 0.30 a 0.50; los pesos siguen sumando 1.0 en los dos casos.
    if r["plato_deseado"]:
        peso_cocina_efectivo, peso_plato_efectivo = PESO_COCINA, PESO_PLATO
    else:
        peso_cocina_efectivo, peso_plato_efectivo = PESO_COCINA + PESO_PLATO, 0.0

    def puntuar_fila(fila):
        min_r, max_r = parsear_rango_precio(fila["Rango de precios"])
        score_precio = solapamiento(min_r, max_r, r["presupuesto_min"], r["presupuesto_max"])

        score_cocina = puntuacion_cocina(fila, r["cocina"], con_jev)

        score_plato = puntuacion_plato(fila["ID"], r["plato_deseado"], df_platos)
        score_calidad = calcular_score_calidad(fila)
        num_resenas = fila["Nº Reseñas"] if not pd.isna(fila["Nº Reseñas"]) else 0
        score_resenas = min(1.0, num_resenas / max_resenas)

        return (
            PESO_PRECIO * score_precio + peso_cocina_efectivo * score_cocina + peso_plato_efectivo * score_plato +
            PESO_CALIDAD * score_calidad + PESO_NUM_RESENAS * score_resenas
        )

    df["Score"] = df.apply(puntuar_fila, axis=1)
    if r["orden"] == "Más cercanos":
        return df.sort_values(["Tiempo desplazamiento (min)", "Score"], ascending=[True, False])
    return df.sort_values("Score", ascending=False)


def leer_secreto(nombre, defecto=""):
    """Lee un secreto de Streamlit sin romper si no existe (st.secrets.get lanza
    StreamlitSecretNotFoundError cuando no hay ningún archivo secrets.toml)."""
    try:
        return st.secrets.get(nombre, defecto)
    except Exception:
        return defecto


def configuracion_mapa_base():
    """Mapa base: OpenFreeMap "Positron" (vectorial, gris claro, sin clave ni límites), para que
    las fotos destaquen. Si el navegador no puede dibujarlo (sin WebGL, sin acceso a
    OpenFreeMap...), el componente cae automáticamente a OpenStreetMap (raster, sin clave)."""
    return {
        "vectorial": {
            "style": "https://tiles.openfreemap.org/styles/positron",
            "atribucion": '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> '
                          '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">&copy; OpenMapTiles</a> '
                          'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
        },
        "respaldo": {
            "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "subdominios": "abc", "maxZoom": 19,
            "atribucion": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        },
    }


def formatear_platos(texto):
    if not isinstance(texto, str):
        return ""
    return re.sub(r"\s*\(\d+\)", "", texto).strip()


def valor_o(fila, campo, defecto="N/D"):
    """Como fila.get(campo, defecto), pero también cae al valor por defecto
    cuando la columna existe pero el valor es NaN o una cadena vacía
    (fila.get() por sí solo NO cubre el caso NaN: solo usa el defecto si
    la columna no existe, así que un hueco de datos real se acababa
    mostrando como el texto "nan")."""
    valor = fila.get(campo)
    if pd.isna(valor):
        return defecto
    if isinstance(valor, str) and not valor.strip():
        return defecto
    return valor


def mejorar_resolucion_imagen(url, ancho=600, alto=400):
    """
    Las URLs de imágenes de Google (googleusercontent.com) incluyen el
    tamaño deseado al final (ej. '=w80-h142-k-no', el tamaño diminuto de
    la miniatura del listado de Maps). Pedimos la misma foto pero a mayor
    resolución cambiando esos números, en vez de estirar la miniatura
    pequeña y verse pixelada.
    """
    if not isinstance(url, str) or not url.strip():
        return url
    return re.sub(r"=w\d+-h\d+", f"=w{ancho}-h{alto}", url)


def resumen_mencion_plato(id_restaurante, plato_deseado, df_platos):
    if df_platos.empty or "ID_Restaurante" not in df_platos.columns:
        return "(sin datos de reseñas analizadas)"
    menciones = df_platos[
        (df_platos["ID_Restaurante"] == id_restaurante) &
        (df_platos["Plato"].astype(str).str.contains(plato_deseado, case=False, na=False))
    ]
    if menciones.empty:
        return "no se menciona explícitamente en las reseñas analizadas"
    buenas = (menciones["Sentimiento"] == "Buena").sum()
    malas = (menciones["Sentimiento"] == "Mala").sum()
    neutras = (menciones["Sentimiento"] == "Neutra").sum()
    partes = []
    if buenas:
        partes.append(f"{buenas} bien")
    if malas:
        partes.append(f"{malas} mal")
    if neutras:
        partes.append(f"{neutras} neutra")
    return f"mencionado {len(menciones)} veces en reseñas ({', '.join(partes)})"


def mostrar_tarjeta(fila, respuestas, df_platos, numero=None):
    """Dibuja la tarjeta de un restaurante (foto a la izquierda, datos a la
    derecha). Se usa tanto en la lista de resultados como en la ficha que
    aparece al pinchar un punto del mapa."""
    col_img, col_info = st.columns([1, 3], vertical_alignment="center")

    with col_img:
        imagen_url = fila.get("Imagen URL")
        imagen_local = IMAGENES_DIR / str(valor_o(fila, "Imagen archivo", ""))
        if imagen_local.is_file():   # descargada por extraer_html.py; las URLs de Google caducan
            st.image(str(imagen_local), width="stretch")
        elif isinstance(imagen_url, str) and imagen_url.strip():
            # Pedimos bastante más resolución de la que se va a mostrar (la
            # columna es estrecha) para que se vea nítida en pantallas retina.
            st.image(mejorar_resolucion_imagen(imagen_url, ancho=450, alto=450),
                     width="stretch")

    with col_info:
        consulta_busqueda = urllib.parse.quote(f"{fila['Nombre']} Madrid")
        url_busqueda = f"https://www.google.com/search?q={consulta_busqueda}"
        prefijo = f"{numero}. " if numero is not None else ""
        st.markdown(f"### {prefijo}[{fila['Nombre']}]({url_busqueda})")

        st.write(f"**Cocina:** {etiqueta_cocina(fila)}  |  **Precio:** {fila['Rango de precios']}  |  "
                 f"**Rating:** {fila['Puntuación']} ({fila['Nº Reseñas']} reseñas)")
        etiqueta_modo_tarjeta = "En coche" if respuestas["modo_transporte"] == "En coche" else "Andando"
        st.write(f"**{etiqueta_modo_tarjeta}:** {fila['Tiempo desplazamiento (min)']:.0f} min  |  "
                 f"**Dirección:** {valor_o(fila, 'Dirección')}")

        if respuestas["plato_deseado"]:
            resumen = resumen_mencion_plato(fila["ID"], respuestas["plato_deseado"], df_platos)
            st.write(f"**Sobre '{respuestas['plato_deseado']}':** {resumen}")

        valor = fila.get("Platos mejor valorados")
        if isinstance(valor, str) and valor.strip():
            st.write(f"**Otros platos destacados:** {formatear_platos(valor)}")

        # Instagram/TikTok no tienen una búsqueda por palabra clave fiable
        # sin iniciar sesión (Instagram redirige a login), así que usamos el
        # operador site: de Google, que sí funciona sin cuenta y solo
        # devuelve contenido público. Los logos vienen de Simple Icons
        # (cdn.simpleicons.org), gratuito y sin login.
        consulta_ig = urllib.parse.quote(f'site:instagram.com "{fila["Nombre"]}" Madrid')
        consulta_tt = urllib.parse.quote(f'site:tiktok.com "{fila["Nombre"]}" Madrid')
        url_ig = f"https://www.google.com/search?q={consulta_ig}"
        url_tt = f"https://www.google.com/search?q={consulta_tt}"
        logo_ig = "https://cdn.simpleicons.org/instagram/E4405F"
        logo_tt = "https://cdn.simpleicons.org/tiktok/000000"
        st.markdown(
            f'<a href="{url_ig}" target="_blank" style="margin-right:16px; text-decoration:none;">'
            f'<img src="{logo_ig}" width="16" style="vertical-align:middle; margin-right:4px;">'
            f'<span style="vertical-align:middle;">Instagram</span></a>'
            f'<a href="{url_tt}" target="_blank" style="text-decoration:none;">'
            f'<img src="{logo_tt}" width="16" style="vertical-align:middle; margin-right:4px;">'
            f'<span style="vertical-align:middle;">TikTok</span></a>',
            unsafe_allow_html=True,
        )


# ----------------------- MAPA CON FOTOS REDONDAS ----------------------- #
# Componente propio (st.components.v2) con Leaflet: cada restaurante es su foto
# redonda con el número de posición (el mismo que en la lista). Al pinchar una
# foto se avisa a Python para mostrar su ficha debajo. Leaflet y los mosaicos del
# mapa se cargan desde internet (jsDelivr y OpenFreeMap; OpenStreetMap de respaldo).

_HTML_MAPA = """
<div class="fm-mapa"></div>
"""

_CSS_MAPA = """
.fm-mapa {
  height: 420px; width: 100%; position: relative; z-index: 0; overflow: hidden;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
  border-radius: var(--st-base-radius, 0.5rem);
  font-family: var(--st-font, sans-serif);
}
.fm-icono { background: transparent; border: none; }
.fm-pin { position: relative; width: 46px; height: 56px; transform-origin: 50% 100%; transition: transform 0.12s ease-out; cursor: pointer; }
.fm-pin.fm-sel { transform: scale(1.22); }
.fm-foto {
  position: absolute; left: 0; top: 0; width: 40px; height: 40px;
  border: 3px solid #fff; border-radius: 50%; overflow: hidden; background: #e6e6ea;
  box-shadow: 0 1px 5px rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center; font-size: 20px;
}
.fm-foto img { width: 100%; height: 100%; object-fit: cover; display: block; }
.fm-sel .fm-foto { border-color: var(--st-primary-color, #ff4b4b); }
.fm-punta {
  position: absolute; left: 50%; bottom: 0; transform: translateX(-50%);
  width: 0; height: 0; border-left: 8px solid transparent; border-right: 8px solid transparent;
  border-top: 12px solid #fff; filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.3));
}
.fm-sel .fm-punta { border-top-color: var(--st-primary-color, #ff4b4b); }
.fm-num {
  position: absolute; right: -7px; top: -7px; min-width: 20px; height: 20px; padding: 0 4px; box-sizing: border-box;
  border-radius: 10px; background: var(--st-primary-color, #ff4b4b); color: #fff;
  font: 700 12px/20px var(--st-font, sans-serif); text-align: center; box-shadow: 0 0 0 2px #fff;
}
.fm-top .fm-num { background: #f5b301; color: #3b2a00; }
.fm-yo { position: relative; width: 22px; height: 22px; }
.fm-yo-pulso { position: absolute; inset: 0; border-radius: 50%; background: #1a73e8; animation: fm-pulso 2s ease-out infinite; }
.fm-yo-punto { position: absolute; left: 2px; top: 2px; width: 12px; height: 12px; border: 3px solid #fff; border-radius: 50%; background: #1a73e8; box-shadow: 0 0 3px rgba(0, 0, 0, 0.45); }
@keyframes fm-pulso { 0% { transform: scale(0.6); opacity: 0.55; } 100% { transform: scale(2.3); opacity: 0; } }
.fm-mensaje { padding: 1rem; color: var(--st-text-color); }
"""

_JS_MAPA = r"""
const LEAFLET_CSS = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css';
const LEAFLET_JS = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js';
const MAPLIBRE_CSS = 'https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css';
const MAPLIBRE_JS = 'https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js';
const PLUGIN_JS = 'https://cdn.jsdelivr.net/npm/@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js';
const TIEMPO_MAX_VECTORIAL_MS = 12000;

function cargarCss(href) {
  return new Promise((ok, fallo) => {
    const l = document.createElement('link');
    l.rel = 'stylesheet'; l.href = href; l.onload = ok; l.onerror = fallo;
    document.head.appendChild(l);
  });
}

function cargarScript(src) {
  return new Promise((ok, fallo) => {
    const sc = document.createElement('script');
    sc.src = src; sc.onload = ok; sc.onerror = fallo;
    document.head.appendChild(sc);
  });
}

function cargarLeaflet() {
  if (window.L && window.L.map) return Promise.resolve(window.L);
  if (!window.__fmLeaflet) {
    window.__fmLeaflet = Promise.all([cargarCss(LEAFLET_CSS), cargarScript(LEAFLET_JS)])
      .then(() => window.L)
      .catch((e) => { window.__fmLeaflet = null; throw e; });
  }
  return window.__fmLeaflet;
}

// MapLibre GL + su plugin para Leaflet (mapa vectorial). Se cargan solo si hacen falta.
function cargarMapLibre() {
  if (window.L && window.L.maplibreGL) return Promise.resolve();
  if (!window.__fmMapLibre) {
    window.__fmMapLibre = Promise.all([
      cargarCss(MAPLIBRE_CSS),
      cargarScript(MAPLIBRE_JS).then(() => cargarScript(PLUGIN_JS)),
    ]).then(() => undefined).catch((e) => { window.__fmMapLibre = null; throw e; });
  }
  return window.__fmMapLibre;
}

function crearPin(r, seleccionado) {
  const pin = document.createElement('div');
  pin.className = 'fm-pin' + (seleccionado ? ' fm-sel' : '') + (r.n === 1 ? ' fm-top' : '');
  const foto = document.createElement('div');
  foto.className = 'fm-foto';
  const sinFoto = () => { foto.textContent = '🍽️'; };
  if (r.foto) {
    const img = document.createElement('img');
    img.alt = ''; img.referrerPolicy = 'no-referrer';
    img.onerror = () => { img.remove(); sinFoto(); };
    img.src = r.foto;
    foto.appendChild(img);
  } else {
    sinFoto();
  }
  const num = document.createElement('span');
  num.className = 'fm-num'; num.textContent = String(r.n);
  const punta = document.createElement('span');
  punta.className = 'fm-punta';
  pin.append(foto, num, punta);
  return pin;
}

function crearPuntoUsuario() {
  const yo = document.createElement('div');
  yo.className = 'fm-yo';
  const pulso = document.createElement('span'); pulso.className = 'fm-yo-pulso';
  const punto = document.createElement('span'); punto.className = 'fm-yo-punto';
  yo.append(pulso, punto);
  return yo;
}

function quitarBase(estado) {
  if (estado.temporizador) { clearTimeout(estado.temporizador); estado.temporizador = null; }
  if (estado.capaBase) { try { estado.capaBase.remove(); } catch (e) { /* ya no estaba */ } estado.capaBase = null; }
  // Restos de una capa vectorial que no llegó a montarse del todo (p. ej. sin WebGL).
  estado.contenedor.querySelectorAll('.leaflet-gl-layer').forEach((el) => el.remove());
}

function ponerRespaldo(L, estado) {
  const r = estado.datos.base.respaldo;
  quitarBase(estado);
  estado.capaBase = L.tileLayer(r.url, { subdomains: r.subdominios, maxZoom: r.maxZoom, attribution: r.atribucion }).addTo(estado.mapa);
  estado.baseClave = 'respaldo';
}

// Mapa vectorial (OpenFreeMap). Si algo falla (sin WebGL, sin red, tarda demasiado) se usa el respaldo.
function ponerVectorial(L, estado) {
  const v = estado.datos.base.vectorial;
  const clave = 'vectorial:' + v.style;
  if (estado.baseClave === clave || estado.baseClave === 'respaldo') return;
  quitarBase(estado);
  estado.baseClave = clave;

  cargarMapLibre().then(() => {
    if (estado.baseClave !== clave || !estado.mapa) return;
    const capa = L.maplibreGL({ style: v.style, attributionControl: { customAttribution: v.atribucion } });
    estado.capaBase = capa;   // antes de añadirla: si addTo falla (p. ej. sin WebGL), quitarBase() puede limpiarla
    capa.addTo(estado.mapa);
    let cargado = false;
    capa.getMaplibreMap().on('styledata', () => { cargado = true; });
    estado.temporizador = setTimeout(() => {
      if (!cargado && estado.baseClave === clave) ponerRespaldo(L, estado);
    }, TIEMPO_MAX_VECTORIAL_MS);
  }).catch(() => {
    if (estado.baseClave === clave) ponerRespaldo(L, estado);
  });
}

function aplicarBase(L, estado) {
  // Limpia capas de mosaicos que no sean las nuestras (p. ej. de una versión anterior con la página abierta).
  estado.mapa.eachLayer((capa) => {
    if (capa instanceof L.TileLayer && capa !== estado.capaBase) capa.remove();
  });
  ponerVectorial(L, estado);
}

function pintar(L, estado) {
  const { usuario, restaurantes, seleccionado } = estado.datos;

  if (!estado.mapa) {
    estado.mapa = L.map(estado.contenedor, { scrollWheelZoom: false });
    estado.capa = L.layerGroup().addTo(estado.mapa);
    // La rueda del ratón solo hace zoom tras pinchar dentro del mapa (así no secuestra el scroll de la página).
    estado.mapa.on('mousedown', () => estado.mapa.scrollWheelZoom.enable());
    estado.contenedor.addEventListener('mouseleave', () => estado.mapa.scrollWheelZoom.disable());
    // Pinchar en un hueco del mapa quita la selección.
    estado.mapa.on('click', () => { if (estado.seleccionado != null) estado.setTrigger('seleccion', -1); });
  }

  aplicarBase(L, estado);

  estado.seleccionado = seleccionado;
  estado.capa.clearLayers();

  L.marker([usuario.lat, usuario.lon], {
    icon: L.divIcon({ className: 'fm-icono', html: crearPuntoUsuario(), iconSize: [22, 22], iconAnchor: [11, 11] }),
    interactive: false, keyboard: false, zIndexOffset: -1000,
  }).addTo(estado.capa);

  restaurantes.forEach((r) => {
    const marcador = L.marker([r.lat, r.lon], {
      icon: L.divIcon({ className: 'fm-icono', html: crearPin(r, r.id === seleccionado), iconSize: [46, 56], iconAnchor: [23, 56] }),
      zIndexOffset: r.id === seleccionado ? 1000 : 100 - r.n,
    });
    const nombre = document.createElement('span');
    nombre.textContent = r.nombre;
    marcador.bindTooltip(nombre, { direction: 'top', offset: [0, -50], opacity: 0.95 });
    marcador.on('click', () => estado.setTrigger('seleccion', r.id));
    marcador.addTo(estado.capa);
  });

  // Encuadre: solo cuando cambia el conjunto de restaurantes (no al seleccionar uno),
  // para no perder el zoom/posición que haya puesto la persona.
  const clave = usuario.lat + ',' + usuario.lon + '|' + restaurantes.map((r) => r.id).join(',');
  if (clave !== estado.clave) {
    estado.clave = clave;
    if (restaurantes.length) {
      const puntos = restaurantes.map((r) => [r.lat, r.lon]).concat([[usuario.lat, usuario.lon]]);
      estado.mapa.fitBounds(L.latLngBounds(puntos), { paddingTopLeft: [40, 75], paddingBottomRight: [40, 35], maxZoom: 16 });
    } else {
      estado.mapa.setView([usuario.lat, usuario.lon], 15);
    }
  }
  estado.mapa.invalidateSize();
}

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const contenedor = parentElement.querySelector('.fm-mapa');
  if (!contenedor) return;

  // El estado vive en el propio elemento: así sobrevive a las recargas de Streamlit
  // (el JS se vuelve a ejecutar con datos nuevos) sin recrear el mapa ni perder el zoom.
  let estado = contenedor.__fmEstado;
  if (!estado) {
    estado = { contenedor, mapa: null, capa: null, clave: null, seleccionado: null };
    contenedor.__fmEstado = estado;
  }
  estado.setTrigger = setTriggerValue;
  estado.datos = data;

  cargarLeaflet()
    .then((L) => pintar(L, estado))
    .catch(() => {
      contenedor.textContent = '';
      const aviso = document.createElement('div');
      aviso.className = 'fm-mensaje';
      aviso.textContent = 'No se ha podido cargar el mapa. Comprueba tu conexión y recarga la página.';
      contenedor.appendChild(aviso);
    });

  return () => {
    // Solo destruimos el mapa si el elemento ya no está en la página (no en cada recarga).
    setTimeout(() => {
      if (!parentElement.isConnected && estado.mapa) {
        estado.mapa.remove(); estado.mapa = null; contenedor.__fmEstado = null;
      }
    }, 0);
  };
}
"""

_MAPA_FOTOS = st.components.v2.component(
    "mapa_fotos_restaurantes",
    html=_HTML_MAPA, css=_CSS_MAPA, js=_JS_MAPA, isolate_styles=False,
)


def _al_seleccionar_en_mapa():
    """Callback del mapa: se ejecuta ANTES de la recarga del script, así que la
    selección ya está actualizada cuando se vuelve a dibujar la página."""
    valor = st.session_state["mapa_fotos"].seleccion
    if valor is None:
        return
    st.session_state["restaurante_seleccionado"] = None if int(valor) == -1 else int(valor)


def mostrar_mapa(lat_u, lon_u, restaurantes=None, seleccionado_id=None):
    """Dibuja el mapa con tu ubicación (punto azul) y cada restaurante recomendado como
    su foto redonda con el número de posición. Sin restaurantes (búsqueda sin
    resultados) solo se ve tu ubicación, para comprobar que la app te sitúa donde
    esperabas (por si la dirección se ha ido a un sitio equivocado)."""
    lista = []
    if restaurantes is not None and not restaurantes.empty:
        for n, (_, fila) in enumerate(restaurantes.iterrows(), start=1):
            if pd.isna(fila["Latitud"]) or pd.isna(fila["Longitud"]):
                continue
            url = fila.get("Imagen URL")
            imagen_local = IMAGENES_DIR / str(valor_o(fila, "Imagen archivo", ""))
            if imagen_local.is_file():   # el componente JS no ve el disco: se la pasamos en base64
                foto = "data:image/jpeg;base64," + base64.b64encode(imagen_local.read_bytes()).decode()
            elif isinstance(url, str) and url.strip():
                foto = mejorar_resolucion_imagen(url, ancho=160, alto=160)
            else:
                foto = None
            lista.append({
                "id": int(fila["ID"]), "n": n, "nombre": str(fila["Nombre"]),
                "lat": float(fila["Latitud"]), "lon": float(fila["Longitud"]), "foto": foto,
            })

    _MAPA_FOTOS(
        data={"usuario": {"lat": float(lat_u), "lon": float(lon_u)}, "restaurantes": lista,
              "seleccionado": seleccionado_id, "base": configuracion_mapa_base()},
        key="mapa_fotos",
        on_seleccion_change=_al_seleccionar_en_mapa,
    )
    if lista:
        st.caption("🔵 Tu ubicación · Pincha la foto de un restaurante para ver su ficha.")
    else:
        st.caption("🔵 Tu ubicación — comprueba que el mapa te sitúa donde esperabas.")


# ----------------------- BOTÓN "UBICACIÓN ACTUAL" ----------------------- #
# Componente propio (st.components.v2, sin paquetes externos). Al pulsarlo, el
# navegador pide permiso y devuelve las coordenadas a Python. Se ejecuta en la
# propia página (no en un iframe), así que usa el permiso normal del navegador.
# Requiere HTTPS (Streamlit Cloud lo es) o localhost.

_HTML_UBICACION = """
<button type="button" id="boton">
  <span class="icono">📍</span><span class="etiqueta">Ubicación actual</span>
</button>
"""

_CSS_UBICACION = """
button {
  display: inline-flex; align-items: center; gap: 0.4rem;
  font-family: var(--st-font, inherit); font-size: calc(var(--st-base-font-size, 16px) * 0.875);
  font-weight: 400; line-height: 1.6;
  color: var(--st-text-color); background: var(--st-background-color);
  border: 1px solid var(--st-border-color);
  border-radius: var(--st-button-radius, 0.5rem);
  padding: 0.25rem 0.75rem; min-height: 2.5rem; cursor: pointer;
}
button:hover { border-color: var(--st-primary-color); color: var(--st-primary-color); }
button:disabled { opacity: 0.6; cursor: progress; }
"""

_JS_UBICACION = """
export default function (component) {
  const { parentElement, setTriggerValue } = component;
  const boton = parentElement.querySelector('#boton');
  const etiqueta = boton.querySelector('.etiqueta');
  const textoNormal = 'Ubicación actual';

  boton.onclick = () => {
    if (!navigator.geolocation) { setTriggerValue('error', 'no_soportado'); return; }
    boton.disabled = true;
    etiqueta.textContent = 'Buscando tu ubicación…';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        boton.disabled = false; etiqueta.textContent = textoNormal;
        setTriggerValue('ubicacion', {
          lat: pos.coords.latitude, lon: pos.coords.longitude, precision: pos.coords.accuracy,
        });
      },
      (err) => {
        boton.disabled = false; etiqueta.textContent = textoNormal;
        setTriggerValue('error', String(err.code));  // 1 denegado, 2 no disponible, 3 tiempo agotado
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
  };
}
"""

_BOTON_UBICACION = st.components.v2.component(
    "boton_ubicacion_actual",
    html=_HTML_UBICACION, css=_CSS_UBICACION, js=_JS_UBICACION,
)

MENSAJES_ERROR_UBICACION = {
    "1": "No has dado permiso al navegador para ver tu ubicación. Actívalo (icono del candado "
         "junto a la dirección web) o escribe la dirección.",
    "2": "No he podido determinar tu ubicación. Prueba otra vez o escribe la dirección.",
    "3": "Se ha agotado el tiempo esperando tu ubicación. Prueba otra vez o escribe la dirección.",
    "no_soportado": "Tu navegador no permite obtener la ubicación. Escribe la dirección.",
}


def boton_ubicacion_actual(key):
    """Muestra el botón y devuelve el resultado del clic (atributos .ubicacion o .error,
    que solo tienen valor en la ejecución inmediatamente posterior al clic)."""
    return _BOTON_UBICACION(key=key, on_ubicacion_change=lambda: None, on_error_change=lambda: None)


# ----------------------- CAJA DE DIRECCIÓN CON SUGERENCIAS ----------------------- #
# Componente propio: mientras escribes, el navegador pide sugerencias a Photon
# (photon.komoot.io, gratis, pensado para autocompletar; Nominatim lo prohíbe) dentro de
# la Comunidad de Madrid. Al elegir una, se devuelven sus coordenadas y no hace falta
# geocodificar; si escribes sin elegir, el texto se geocodifica con Nominatim al buscar.
# Solo se avisa a Python al elegir, al pulsar Enter o al salir de la caja (no en cada
# tecla), para no relanzar la app a cada letra.

_HTML_DIRECCION = """
<label for="dir">¿Desde dónde salís?</label>
<div class="caja">
  <input id="dir" type="text" autocomplete="off" role="combobox" aria-autocomplete="list"
         aria-expanded="false" aria-controls="sugerencias">
  <ul id="sugerencias" role="listbox" hidden></ul>
</div>
"""

_CSS_DIRECCION = """
label { display: block; font-family: var(--st-font, inherit); font-size: calc(var(--st-base-font-size, 16px) * 0.875);
        color: var(--st-text-color); margin-bottom: 0.25rem; }
.caja { position: relative; }
input {
  box-sizing: border-box; width: 100%; min-height: 2.5rem; padding: 0.5rem 0.75rem;
  font-family: var(--st-font, inherit); font-size: var(--st-base-font-size, 16px);
  color: var(--st-text-color); background: var(--st-secondary-background-color);
  border: 1px solid transparent; border-radius: var(--st-base-radius, 0.5rem); outline: none;
}
input:focus { border-color: var(--st-primary-color); }
input:disabled { opacity: 0.6; cursor: not-allowed; }
ul {
  position: absolute; z-index: 1000; left: 0; right: 0; top: calc(100% + 4px); margin: 0; padding: 0.25rem 0;
  list-style: none; background: var(--st-background-color); border: 1px solid var(--st-border-color);
  border-radius: var(--st-base-radius, 0.5rem); box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  max-height: 18rem; overflow-y: auto;
}
li { padding: 0.45rem 0.75rem; cursor: pointer; font-family: var(--st-font, inherit); color: var(--st-text-color); }
li[aria-selected="true"], li:hover { background: var(--st-secondary-background-color); }
li .principal { display: block; font-size: calc(var(--st-base-font-size, 16px) * 0.95); }
li .detalle { display: block; font-size: calc(var(--st-base-font-size, 16px) * 0.8); opacity: 0.7; }
"""

_JS_DIRECCION = """
const PHOTON = 'https://photon.komoot.io/api/';
const CAJA_MADRID = '-4.58,39.88,-3.05,41.17';   // lon/lat mín,máx: Comunidad de Madrid

function etiquetas(p) {
  const calle = [p.street, p.housenumber].filter(Boolean).join(' ');
  const principal = p.name || calle || p.district || p.city || '';
  const detalle = [p.name ? calle : null, p.district, p.city].filter((x) => x && x !== principal);
  return { principal, detalle: [...new Set(detalle)].join(', ') };
}

export default function (component) {
  const { parentElement, data, setStateValue } = component;
  const input = parentElement.querySelector('#dir');
  const lista = parentElement.querySelector('#sugerencias');
  let opciones = [], activa = -1, temporizador = null, peticion = 0;

  input.disabled = !!data.disabled;
  input.placeholder = data.placeholder || '';
  if (!input.value && data.texto) input.value = data.texto;   // si la caja se ha vuelto a montar vacía

  const cerrar = () => { lista.hidden = true; input.setAttribute('aria-expanded', 'false'); activa = -1; };
  const enviarTexto = () => { if (input.value !== (data.texto || '')) setStateValue('texto', input.value); };

  const elegir = (i) => {
    const o = opciones[i];
    input.value = o.texto;
    cerrar();
    setStateValue('seleccion', { lat: o.lat, lon: o.lon, texto: o.texto });
    setStateValue('texto', o.texto);
  };

  const pintar = () => {
    lista.innerHTML = '';
    opciones.forEach((o, i) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', String(i === activa));
      const a = document.createElement('span'); a.className = 'principal'; a.textContent = o.principal;
      const b = document.createElement('span'); b.className = 'detalle'; b.textContent = o.detalle;
      li.append(a, b);
      li.onmousedown = (e) => { e.preventDefault(); elegir(i); };   // mousedown: antes del blur
      lista.appendChild(li);
    });
    lista.hidden = opciones.length === 0;
    input.setAttribute('aria-expanded', String(!lista.hidden));
  };

  input.oninput = () => {
    clearTimeout(temporizador);
    const q = input.value.trim();
    if (q.length < 3) { opciones = []; cerrar(); return; }
    temporizador = setTimeout(async () => {
      const id = ++peticion;
      try {
        const url = `${PHOTON}?q=${encodeURIComponent(q)}&limit=6&lat=40.4168&lon=-3.7038&bbox=${CAJA_MADRID}`;
        const res = await (await fetch(url)).json();
        if (id !== peticion) return;   // ya hay una petición más reciente
        const vistos = new Set();
        opciones = res.features.map((f) => {
          const { principal, detalle } = etiquetas(f.properties);
          const [lon, lat] = f.geometry.coordinates;
          return { principal, detalle, lat, lon, texto: [principal, detalle].filter(Boolean).join(', ') };
        }).filter((o) => o.principal && !vistos.has(o.texto) && vistos.add(o.texto));
        activa = -1;
        pintar();
      } catch (e) { opciones = []; cerrar(); }   // sin sugerencias: se puede seguir escribiendo a mano
    }, 300);
  };

  input.onkeydown = (e) => {
    if (e.key === 'ArrowDown' && opciones.length) { activa = (activa + 1) % opciones.length; pintar(); e.preventDefault(); }
    else if (e.key === 'ArrowUp' && opciones.length) { activa = (activa - 1 + opciones.length) % opciones.length; pintar(); e.preventDefault(); }
    else if (e.key === 'Enter') { if (activa >= 0 && !lista.hidden) elegir(activa); else { cerrar(); enviarTexto(); } }
    else if (e.key === 'Escape') cerrar();
  };
  input.onblur = () => { cerrar(); enviarTexto(); };
}
"""

_CAJA_DIRECCION = st.components.v2.component(
    "caja_direccion_sugerencias",
    html=_HTML_DIRECCION, css=_CSS_DIRECCION, js=_JS_DIRECCION,
)


def caja_direccion_con_sugerencias(key, disabled, placeholder):
    """Devuelve (texto escrito, sugerencia elegida o None). La sugerencia solo vale si el
    texto no se ha cambiado después de elegirla."""
    res = _CAJA_DIRECCION(
        key=key, data={"disabled": disabled, "placeholder": placeholder,
                       "texto": st.session_state.get("_texto_" + key, "")},
        default={"texto": "", "seleccion": None},
        on_texto_change=lambda: None, on_seleccion_change=lambda: None,
    )
    texto, seleccion = res.texto or "", res.seleccion
    st.session_state["_texto_" + key] = texto
    if seleccion and seleccion.get("texto") != texto:
        seleccion = None
    return texto, seleccion


def quitar_ubicacion_actual():
    for clave in ("ubicacion_actual", "precision_ubicacion", "error_ubicacion"):
        st.session_state.pop(clave, None)


# ----------------------- INTERFAZ ----------------------- #

st.set_page_config(page_title="¿Dónde comemos?", page_icon="🍽️", layout="centered")
st.title("🍽️ ¿Dónde comemos hoy?")

maestro, df_platos = cargar_datos()

col1, col2 = st.columns(2)
with col1:
    presupuesto_min = st.number_input("Presupuesto mín. (€/persona)", min_value=0, value=0, step=5)
with col2:
    presupuesto_max = st.number_input("Presupuesto máx. (€/persona)", min_value=0, value=30, step=5)

if tiene_categorias_jev(maestro):
    cocinas_jev = sorted(maestro[COL_CATEGORIA].dropna().unique())
    cocina = st.selectbox("Tipo de cocina", ["Cualquiera"] + cocinas_jev)
else:   # maestro sin categorías de Jev: se usa el tipo de Google
    cocinas_disponibles = sorted(maestro["Tipo de cocina"].dropna().unique().tolist())
    cocina = st.selectbox("Tipo de cocina", ["Cualquiera"] + cocinas_disponibles)

# Caja de dirección y, justo debajo, el botón "Ubicación actual". Reservamos primero
# el hueco de la caja y lo rellenamos después de procesar el clic del botón: así la
# caja ya refleja (desactivada) que se está usando la ubicación en ese mismo ciclo.
caja_direccion = st.container()
zona_ubicacion = st.container()

with zona_ubicacion:
    lectura = boton_ubicacion_actual(key="boton_ubicacion")
    if lectura.ubicacion:
        st.session_state["ubicacion_actual"] = (lectura.ubicacion["lat"], lectura.ubicacion["lon"])
        st.session_state["precision_ubicacion"] = lectura.ubicacion.get("precision")
        st.session_state.pop("error_ubicacion", None)
    elif lectura.error is not None:
        st.session_state["error_ubicacion"] = str(lectura.error)

    if st.session_state.get("ubicacion_actual"):
        col_estado, col_quitar = st.columns([3, 1], vertical_alignment="center")
        with col_estado:
            precision = st.session_state.get("precision_ubicacion")
            detalle = f" (precisión ≈ {precision:.0f} m)" if precision else ""
            st.caption(f"✅ Usando tu ubicación actual{detalle}")
            if precision and precision > 1000:
                st.caption("⚠️ Es poco precisa (habitual en ordenador). Si no cuadra, quítala y escribe la dirección.")
        with col_quitar:
            st.button("✖ Quitar", on_click=quitar_ubicacion_actual, width="stretch")
    elif st.session_state.get("error_ubicacion"):
        clave = st.session_state["error_ubicacion"]
        st.warning(MENSAJES_ERROR_UBICACION.get(clave, MENSAJES_ERROR_UBICACION["2"]))

ubicacion_actual = st.session_state.get("ubicacion_actual")
usar_ubicacion_actual = ubicacion_actual is not None

with caja_direccion:
    direccion, sugerencia_elegida = caja_direccion_con_sugerencias(
        key="caja_direccion",
        disabled=usar_ubicacion_actual,
        placeholder=("Usando tu ubicación actual" if usar_ubicacion_actual else "ej. Sol, Madrid"),
    )

modo_transporte = st.radio("¿Cómo vais a ir?", ["En coche", "A pie"], horizontal=True)
etiqueta_tiempo = "Máximo en coche (minutos)" if modo_transporte == "En coche" else "Máximo andando (minutos)"
tiempo_maximo_min = st.number_input(
    etiqueta_tiempo, min_value=5, max_value=60, value=20, step=1
)
plato_deseado = st.text_input("¿Algún plato concreto?", placeholder="ej. sushi (opcional)")
orden = st.radio("Ordenar por", ["Mejor puntuación", "Más cercanos"], horizontal=True)

enviado = st.button("🔍 Buscar restaurantes", width="stretch")

if enviado:
    direccion_encontrada = None
    if usar_ubicacion_actual and ubicacion_actual:
        ubicacion_usuario = ubicacion_actual
    elif sugerencia_elegida:   # ya trae coordenadas: no hace falta geocodificar
        ubicacion_usuario = (sugerencia_elegida["lat"], sugerencia_elegida["lon"])
        direccion_encontrada = sugerencia_elegida["texto"]
    else:
        if not direccion.strip():
            st.error("Necesito una dirección o zona desde donde salís (o usa tu ubicación actual).")
            st.stop()

        try:
            with st.spinner("Localizando tu dirección..."):
                encontrada = geocodificar_direccion(direccion)
        except GeocoderServiceError as e:
            st.error(f"El servicio de mapas no responde ahora mismo ({type(e).__name__}). "
                     f"Prueba en un rato o usa tu ubicación actual.")
            st.stop()

        if encontrada is None:
            st.error("No he encontrado esa dirección en Madrid. Prueba con calle y número o un barrio.")
            st.stop()
        ubicacion_usuario = (encontrada.latitude, encontrada.longitude)
        direccion_encontrada = encontrada.address

    respuestas = {
        "presupuesto_min": presupuesto_min,
        "presupuesto_max": presupuesto_max,
        "cocina": "" if cocina == "Cualquiera" else cocina,
        "ubicacion_usuario": ubicacion_usuario,
        "direccion_encontrada": direccion_encontrada,
        "modo_transporte": modo_transporte,
        "tiempo_maximo_min": tiempo_maximo_min,
        "plato_deseado": plato_deseado.strip(),
        "orden": orden,
    }

    texto_spinner = ("Calculando tiempos en coche a los restaurantes..." if modo_transporte == "En coche"
                      else "Calculando tiempos andando a los restaurantes...")
    with st.spinner(texto_spinner):
        df_puntuado = filtrar_y_puntuar(maestro, df_platos, respuestas)

    # Guardamos el resultado de esta búsqueda en la sesión: así el botón
    # "Mostrar más" (que no está dentro del formulario) puede hacer que la
    # página se vuelva a dibujar sin tener que repetir toda la búsqueda.
    st.session_state["resultado"] = {"df_puntuado": df_puntuado, "respuestas": respuestas}
    st.session_state["num_mostrados"] = TOP_N
    st.session_state["restaurante_seleccionado"] = None

resultado = st.session_state.get("resultado")
if resultado is not None:
    df_puntuado = resultado["df_puntuado"]
    respuestas = resultado["respuestas"]
    ubicacion_usuario = respuestas["ubicacion_usuario"]
    modo_transporte_resultado = respuestas["modo_transporte"]
    tiempo_maximo_resultado = respuestas["tiempo_maximo_min"]
    if respuestas.get("direccion_encontrada"):
        st.caption(f"📍 Te he situado en: {respuestas['direccion_encontrada']}")

    if df_puntuado.empty:
        etiqueta_modo = "en coche" if modo_transporte_resultado == "En coche" else "andando"
        st.warning(f"No hay ningún restaurante a menos de {tiempo_maximo_resultado} min {etiqueta_modo} "
                   f"que cumpla lo que has pedido. Prueba a ampliar el tiempo o relajar cocina, presupuesto o plato.")
        mostrar_mapa(*ubicacion_usuario)
        st.stop()

    num_mostrados = min(st.session_state.get("num_mostrados", TOP_N), TOP_N_MAX, len(df_puntuado))
    top = df_puntuado.head(num_mostrados)

    # --- Mapa (al pinchar una foto, aparece su ficha debajo) ---
    lat_u, lon_u = ubicacion_usuario
    ids_top = [int(x) for x in top["ID"].tolist()]
    seleccionado = st.session_state.get("restaurante_seleccionado")
    if seleccionado not in ids_top:
        seleccionado = None
    mostrar_mapa(lat_u, lon_u, top, seleccionado)

    if seleccionado is not None:
        posicion = ids_top.index(seleccionado)
        st.markdown("#### 📍 Restaurante seleccionado")
        with st.container(border=True):
            mostrar_tarjeta(top.iloc[posicion], respuestas, df_platos, numero=posicion + 1)

    # --- Tarjetas de resultados ---
    if respuestas.get("orden") == "Más cercanos":
        st.subheader(f"Los {len(top)} más cercanos")
    else:
        st.subheader(f"Top {len(top)} para vosotros")
    for i, (_, fila) in enumerate(top.iterrows(), start=1):
        with st.container(border=True):
            mostrar_tarjeta(fila, respuestas, df_platos, numero=i)

    # --- Botón "Mostrar más" (hasta un máximo de 10, siempre por score) ---
    if num_mostrados < min(TOP_N_MAX, len(df_puntuado)):
        if st.button("Mostrar más", width="stretch"):
            st.session_state["num_mostrados"] = min(num_mostrados + 5, TOP_N_MAX, len(df_puntuado))
            st.rerun()