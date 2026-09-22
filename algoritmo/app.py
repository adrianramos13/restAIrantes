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

PESO_PRECIO = 0.20
PESO_COCINA = 0.20
PESO_PLATO = 0.30
PESO_CALIDAD = 0.25
PESO_NUM_RESENAS = 0.05

TOP_N = 5

OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
OSRM_BATCH_SIZE = 100
VELOCIDAD_RESPALDO_KMH = 30

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
                minutos[idx] = (dist_km / VELOCIDAD_RESPALDO_KMH) * 60

        if start + OSRM_BATCH_SIZE < len(indices_validos):
            time.sleep(1)

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
    df["Tiempo en coche (min)"] = obtener_minutos_coche(r["ubicacion_usuario"], df)

    df = df[df["Tiempo en coche (min)"].notna() & (df["Tiempo en coche (min)"] <= r["tiempo_maximo_min"])]
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
    tiempo_maximo_min = st.slider("Máximo en coche (minutos)", 5, 60, 20)
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
        "tiempo_maximo_min": tiempo_maximo_min,
        "plato_deseado": plato_deseado.strip(),
    }

    with st.spinner("Calculando tiempos en coche a los restaurantes..."):
        df_puntuado = filtrar_y_puntuar(maestro, df_platos, respuestas)

    if df_puntuado.empty:
        st.warning(f"No hay ningún restaurante a menos de {tiempo_maximo_min} min en coche. "
                   f"Prueba a ampliar el tiempo.")
        st.stop()

    top = df_puntuado.head(TOP_N)

    # --- Mapa ---
    lat_u, lon_u = ubicacion_usuario
    capa_restaurantes = pdk.Layer(
        "ScatterplotLayer",
        data=top.rename(columns={"Latitud": "lat", "Longitud": "lon"}),
        get_position="[lon, lat]",
        get_color="[200, 30, 0, 180]",
        get_radius=120,
        pickable=True,
    )
    capa_usuario = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": lat_u, "lon": lon_u}]),
        get_position="[lon, lat]",
        get_color="[0, 110, 220, 220]",
        get_radius=160,
    )
    vista = pdk.ViewState(latitude=lat_u, longitude=lon_u, zoom=12)
    st.pydeck_chart(pdk.Deck(
        layers=[capa_restaurantes, capa_usuario],
        initial_view_state=vista,
        tooltip={"text": "{Nombre}"},
    ))
    st.caption("🔵 Tu ubicación · 🔴 Restaurantes recomendados")

    # --- Tarjetas de resultados ---
    st.subheader(f"Top {len(top)} para vosotros")
    for i, (_, fila) in enumerate(top.iterrows(), start=1):
        with st.container(border=True):
            imagen_url = fila.get("Imagen URL")
            if isinstance(imagen_url, str) and imagen_url.strip():
                st.image(imagen_url, use_container_width=True)

            st.markdown(f"### {i}. {fila['Nombre']}")
            st.write(f"**Cocina:** {fila['Tipo de cocina']}  |  **Precio:** {fila['Rango de precios']}  |  "
                     f"**Rating:** {fila['Puntuación']} ({fila['Nº Reseñas']} reseñas)")
            st.write(f"**En coche:** {fila['Tiempo en coche (min)']:.0f} min  |  "
                     f"**Dirección:** {fila.get('Dirección', 'N/D')}")

            if respuestas["plato_deseado"]:
                resumen = resumen_mencion_plato(fila["ID"], respuestas["plato_deseado"], df_platos)
                st.write(f"**Sobre '{respuestas['plato_deseado']}':** {resumen}")

            valor = fila.get("Platos mejor valorados")
            if isinstance(valor, str) and valor.strip():
                st.write(f"**Otros platos destacados:** {formatear_platos(valor)}")