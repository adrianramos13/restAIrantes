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


def mostrar_tarjeta(fila, respuestas, df_platos, numero=None):
    """Dibuja la tarjeta de un restaurante (foto a la izquierda, datos a la
    derecha). Se usa tanto en la lista de resultados como en la ficha que
    aparece al pinchar un punto del mapa."""
    col_img, col_info = st.columns([1, 3], vertical_alignment="center")

    with col_img:
        imagen_url = fila.get("Imagen URL")
        if isinstance(imagen_url, str) and imagen_url.strip():
            # Pedimos bastante más resolución de la que se va a mostrar (la
            # columna es estrecha) para que se vea nítida en pantallas retina.
            st.image(mejorar_resolucion_imagen(imagen_url, ancho=450, alto=450),
                     width="stretch")

    with col_info:
        consulta_busqueda = urllib.parse.quote(f"{fila['Nombre']} Madrid")
        url_busqueda = f"https://www.google.com/search?q={consulta_busqueda}"
        prefijo = f"{numero}. " if numero is not None else ""
        st.markdown(f"### {prefijo}[{fila['Nombre']}]({url_busqueda})")

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
# mapa se cargan desde internet (jsDelivr y CARTO/OpenStreetMap).

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

function cargarLeaflet() {
  if (window.L && window.L.map) return Promise.resolve(window.L);
  if (!window.__fmLeaflet) {
    const css = new Promise((ok, fallo) => {
      const l = document.createElement('link');
      l.rel = 'stylesheet'; l.href = LEAFLET_CSS; l.onload = ok; l.onerror = fallo;
      document.head.appendChild(l);
    });
    const js = new Promise((ok, fallo) => {
      const sc = document.createElement('script');
      sc.src = LEAFLET_JS; sc.onload = ok; sc.onerror = fallo;
      document.head.appendChild(sc);
    });
    window.__fmLeaflet = Promise.all([css, js]).then(() => window.L).catch((e) => { window.__fmLeaflet = null; throw e; });
  }
  return window.__fmLeaflet;
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

function pintar(L, estado) {
  const { usuario, restaurantes, seleccionado } = estado.datos;

  if (!estado.mapa) {
    estado.mapa = L.map(estado.contenedor, { scrollWheelZoom: false });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd', maxZoom: 20,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(estado.mapa);
    estado.capa = L.layerGroup().addTo(estado.mapa);
    // La rueda del ratón solo hace zoom tras pinchar dentro del mapa (así no secuestra el scroll de la página).
    estado.mapa.on('mousedown', () => estado.mapa.scrollWheelZoom.enable());
    estado.contenedor.addEventListener('mouseleave', () => estado.mapa.scrollWheelZoom.disable());
    // Pinchar en un hueco del mapa quita la selección.
    estado.mapa.on('click', () => { if (estado.seleccionado != null) estado.setTrigger('seleccion', -1); });
  }

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
            foto = mejorar_resolucion_imagen(url, ancho=160, alto=160) if isinstance(url, str) and url.strip() else None
            lista.append({
                "id": int(fila["ID"]), "n": n, "nombre": str(fila["Nombre"]),
                "lat": float(fila["Latitud"]), "lon": float(fila["Longitud"]), "foto": foto,
            })

    _MAPA_FOTOS(
        data={"usuario": {"lat": float(lat_u), "lon": float(lon_u)}, "restaurantes": lista,
              "seleccionado": seleccionado_id},
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


def quitar_ubicacion_actual():
    for clave in ("ubicacion_actual", "precision_ubicacion", "error_ubicacion"):
        st.session_state.pop(clave, None)


# ----------------------- INTERFAZ ----------------------- #

st.set_page_config(page_title="¿Dónde comemos?", page_icon="🍽️", layout="centered")
st.title("🍽️ ¿Dónde comemos hoy?")

maestro, df_platos = cargar_datos()

col1, col2 = st.columns(2)
with col1:
    presupuesto_min = st.number_input("Presupuesto mín. (€/persona)", min_value=0, value=10, step=5)
with col2:
    presupuesto_max = st.number_input("Presupuesto máx. (€/persona)", min_value=0, value=30, step=5)

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
    direccion = st.text_input(
        "¿Desde dónde salís?",
        placeholder=("Usando tu ubicación actual" if usar_ubicacion_actual else "ej. Sol, Madrid"),
        disabled=usar_ubicacion_actual,
    )

modo_transporte = st.radio("¿Cómo vais a ir?", ["En coche", "A pie"], horizontal=True)
etiqueta_tiempo = "Máximo en coche (minutos)" if modo_transporte == "En coche" else "Máximo andando (minutos)"
tiempo_maximo_min = st.number_input(
    etiqueta_tiempo, min_value=5, max_value=60, value=20, step=1
)
plato_deseado = st.text_input("¿Algún plato concreto?", placeholder="ej. sushi (opcional)")

enviado = st.button("🔍 Buscar restaurantes", width="stretch")

if enviado:
    if usar_ubicacion_actual and ubicacion_actual:
        ubicacion_usuario = ubicacion_actual
    else:
        if not direccion.strip():
            st.error("Necesito una dirección o zona desde donde salís (o usa tu ubicación actual).")
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
    st.session_state["restaurante_seleccionado"] = None

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
    st.subheader(f"Top {len(top)} para vosotros")
    for i, (_, fila) in enumerate(top.iterrows(), start=1):
        with st.container(border=True):
            mostrar_tarjeta(fila, respuestas, df_platos, numero=i)

    # --- Botón "Mostrar más" (hasta un máximo de 10, siempre por score) ---
    if num_mostrados < min(TOP_N_MAX, len(df_puntuado)):
        if st.button("Mostrar más", width="stretch"):
            st.session_state["num_mostrados"] = min(num_mostrados + 5, TOP_N_MAX, len(df_puntuado))
            st.rerun() 