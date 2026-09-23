"""
App web (Streamlit) que convierte la encuesta + algoritmo de recomendación
en una página que se abre desde el navegador del móvil.

Reutiliza toda la lógica de encuesta.py (parseo de precios, scoring,
geocoding, tiempos en coche vía OSRM) pero con un formulario web en vez de
preguntas por terminal, y muestra el resultado en tarjetas + mapa.

ESTRUCTURA DE CARPETAS ESPERADA (este archivo vive en algoritmo/):
    proyecto/
      excels/
        restaurantes_maestro.xlsx
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
import time
import urllib.parse
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import pydeck as pdk


# ----------------------- CONFIGURACIÓN ----------------------- #

# Ruta calculada a partir de la ubicación de ESTE archivo (no de desde
# dónde se ejecute el comando), para que funcione tanto si lanzas
# `streamlit run algoritmo/app.py` desde la raíz como si haces `cd
# algoritmo` primero.
BASE_DIR = Path(__file__).resolve().parent
MAESTRO_XLSX = BASE_DIR.parent / "excels" / "restaurantes_maestro.xlsx"

PESO_PRECIO = 0.15
PESO_COCINA = 0.30
PESO_PLATO = 0.20
PESO_CALIDAD = 0.30
PESO_NUM_RESENAS = 0.05

TOP_N = 5
TOP_N_MAX = 10

OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
OSRM_BATCH_SIZE = 100
VELOCIDAD_RESPALDO_COCHE_KMH = 30

ORS_URL = "https://api.openrouteservice.org/v2/matrix/foot-walking"
ORS_BATCH_SIZE = 50
VELOCIDAD_RESPALDO_ANDANDO_KMH = 5

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
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError, GeocoderTimedOut

    geolocalizador = Nominatim(user_agent="app_restaurantes_pareja")
    try:
        ubicacion = geolocalizador.geocode(direccion, timeout=10)
    except (GeocoderServiceError, GeocoderTimedOut):
        return None
    if ubicacion is None:
        return None
    return ubicacion.latitude, ubicacion.longitude


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

    api_key = st.secrets.get("ORS_API_KEY", "")
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


def filtrar_y_puntuar(maestro, df_platos, r):
    df = maestro.copy()
    if r["modo_transporte"] == "A pie":
        df["Tiempo desplazamiento (min)"] = obtener_minutos_a_pie(r["ubicacion_usuario"], df)
    else:
        df["Tiempo desplazamiento (min)"] = obtener_minutos_coche(r["ubicacion_usuario"], df)

    df = df[df["Tiempo desplazamiento (min)"].notna() & (df["Tiempo desplazamiento (min)"] <= r["tiempo_maximo_min"])]
    if df.empty:
        return df

    max_resenas = maestro["Nº Reseñas"].max() or 1

    def puntuar_fila(fila):
        min_r, max_r = parsear_rango_precio(fila["Rango de precios"])
        score_precio = solapamiento(min_r, max_r, r["presupuesto_min"], r["presupuesto_max"])

        if r["cocina"]:
            score_cocina = 1.0 if r["cocina"].lower() in str(fila["Tipo de cocina"]).lower() else 0.0
        else:
            score_cocina = 0.5

        score_plato = puntuacion_plato(fila["ID"], r["plato_deseado"], df_platos)
        score_calidad = calcular_score_calidad(fila)
        num_resenas = fila["Nº Reseñas"] if not pd.isna(fila["Nº Reseñas"]) else 0
        score_resenas = min(1.0, num_resenas / max_resenas)

        return (
            PESO_PRECIO * score_precio + PESO_COCINA * score_cocina + PESO_PLATO * score_plato +
            PESO_CALIDAD * score_calidad + PESO_NUM_RESENAS * score_resenas
        )

    df["Score"] = df.apply(puntuar_fila, axis=1)
    return df.sort_values("Score", ascending=False)


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


def mostrar_mapa(lat_u, lon_u, restaurantes=None):
    """Pinta el mapa con la ubicación del usuario y, si hay, los restaurantes
    recomendados. Se usa tanto en resultados normales como para que el
    usuario pueda comprobar visualmente dónde se ha geocodificado su
    dirección cuando no sale ningún restaurante (por si se ha ido a un
    sitio equivocado, ej. un homónimo lejos de Madrid)."""
    capas = []
    if restaurantes is not None and not restaurantes.empty:
        capas.append(pdk.Layer(
            "ScatterplotLayer",
            data=restaurantes.rename(columns={"Latitud": "lat", "Longitud": "lon"}),
            get_position="[lon, lat]",
            get_color="[200, 30, 0, 180]",
            get_radius=120,
            pickable=True,
        ))
    capas.append(pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": lat_u, "lon": lon_u}]),
        get_position="[lon, lat]",
        get_color="[0, 110, 220, 220]",
        get_radius=160,
    ))
    vista = pdk.ViewState(latitude=lat_u, longitude=lon_u, zoom=12)
    st.pydeck_chart(pdk.Deck(
        layers=capas,
        initial_view_state=vista,
        tooltip={"text": "{Nombre}"},
    ))
    if restaurantes is not None and not restaurantes.empty:
        st.caption("🔵 Tu ubicación · 🔴 Restaurantes recomendados")
    else:
        st.caption("🔵 Tu ubicación — comprueba que el mapa te sitúa donde esperabas.")


# ----------------------- INTERFAZ ----------------------- #

st.set_page_config(page_title="¿Dónde comemos?", page_icon="🍽️", layout="centered")
st.title("🍽️ ¿Dónde comemos hoy?")

maestro, df_platos = cargar_datos()

with st.form("encuesta"):
    col1, col2 = st.columns(2)
    with col1:
        presupuesto_min = st.number_input("Presupuesto mín. (€/persona)", min_value=0, value=10, step=5)
    with col2:
        presupuesto_max = st.number_input("Presupuesto máx. (€/persona)", min_value=0, value=30, step=5)

    cocinas_disponibles = sorted(maestro["Tipo de cocina"].dropna().unique().tolist())
    cocina = st.selectbox("Tipo de cocina", ["Cualquiera"] + cocinas_disponibles)

    direccion = st.text_input("¿Desde dónde salís?", placeholder="ej. Sol, Madrid")

    modo_transporte = st.radio("¿Cómo vais a ir?", ["En coche", "A pie"], horizontal=True)
    etiqueta_tiempo = "Máximo en coche (minutos)" if modo_transporte == "En coche" else "Máximo andando (minutos)"
    tiempo_maximo_min = st.number_input(
        etiqueta_tiempo, min_value=5, max_value=60, value=20, step=1
    )
    plato_deseado = st.text_input("¿Algún plato concreto?", placeholder="ej. sushi (opcional)")

    enviado = st.form_submit_button("🔍 Buscar restaurantes", use_container_width=True)

if enviado:
    if not direccion.strip():
        st.error("Necesito una dirección o zona desde donde salís.")
        st.stop()

    with st.spinner("Localizando tu dirección..."):
        ubicacion_usuario = geocodificar_direccion(direccion)

    if ubicacion_usuario is None:
        st.error("No he podido localizar esa dirección. Prueba a ser más específico (calle + ciudad).")
        st.stop()

    respuestas = {
        "presupuesto_min": presupuesto_min,
        "presupuesto_max": presupuesto_max,
        "cocina": "" if cocina == "Cualquiera" else cocina,
        "ubicacion_usuario": ubicacion_usuario,
        "modo_transporte": modo_transporte,
        "tiempo_maximo_min": tiempo_maximo_min,
        "plato_deseado": plato_deseado.strip(),
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

resultado = st.session_state.get("resultado")
if resultado is not None:
    df_puntuado = resultado["df_puntuado"]
    respuestas = resultado["respuestas"]
    ubicacion_usuario = respuestas["ubicacion_usuario"]
    modo_transporte_resultado = respuestas["modo_transporte"]
    tiempo_maximo_resultado = respuestas["tiempo_maximo_min"]

    if df_puntuado.empty:
        etiqueta_modo = "en coche" if modo_transporte_resultado == "En coche" else "andando"
        st.warning(f"No hay ningún restaurante a menos de {tiempo_maximo_resultado} min {etiqueta_modo}. "
                   f"Prueba a ampliar el tiempo.")
        mostrar_mapa(*ubicacion_usuario)
        st.stop()

    num_mostrados = min(st.session_state.get("num_mostrados", TOP_N), TOP_N_MAX, len(df_puntuado))
    top = df_puntuado.head(num_mostrados)

    # --- Mapa ---
    lat_u, lon_u = ubicacion_usuario
    mostrar_mapa(lat_u, lon_u, top)

    # --- Tarjetas de resultados ---
    st.subheader(f"Top {len(top)} para vosotros")
    for i, (_, fila) in enumerate(top.iterrows(), start=1):
        with st.container(border=True):
            col_img, col_info = st.columns([1, 3], vertical_alignment="center")

            with col_img:
                imagen_url = fila.get("Imagen URL")
                if isinstance(imagen_url, str) and imagen_url.strip():
                    # Pedimos bastante más resolución de la que se va a
                    # mostrar (la columna es estrecha) para que se vea
                    # nítida incluso en pantallas retina/alta densidad.
                    st.image(mejorar_resolucion_imagen(imagen_url, ancho=450, alto=450),
                             use_container_width=True)

            with col_info:
                consulta_busqueda = urllib.parse.quote(f"{fila['Nombre']} Madrid")
                url_busqueda = f"https://www.google.com/search?q={consulta_busqueda}"
                st.markdown(f"### {i}. [{fila['Nombre']}]({url_busqueda})")
                st.write(f"**Cocina:** {fila['Tipo de cocina']}  |  **Precio:** {fila['Rango de precios']}  |  "
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

    # --- Botón "Mostrar más" (hasta un máximo de 10, siempre por score) ---
    if num_mostrados < min(TOP_N_MAX, len(df_puntuado)):
        if st.button("Mostrar más", use_container_width=True):
            st.session_state["num_mostrados"] = min(num_mostrados + 5, TOP_N_MAX, len(df_puntuado))
            st.rerun()