"""
App web (Streamlit), pensada para el móvil, que recomienda restaurantes de vuestra lista
de Google Maps según desde dónde salís, cuánto tiempo queréis tardar, cocina, presupuesto
y plato. Muestra los resultados en lista o mapa, con una ficha por restaurante.

ESTRUCTURA DE CARPETAS ESPERADA (este archivo vive en algoritmo/):
    proyecto/
      excels/
        clasificacion_jev.xlsx   <- lo genera obtener_datos/clasificar_restaurantes_jev.py
      imagenes/                  <- fotos, las descarga obtener_datos/extraer_html.py
      algoritmo/
        app.py          <- este archivo

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

import io
import re
import base64
import random
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st
from geopy.exc import GeocoderServiceError

from logica import (COL_CATEGORIA, COL_CATEGORIA_2, COL_VOTOS_2, ORDEN_CERCANOS, ORDEN_PUNTUACION,
                    VOTOS_MIN_SECUNDARIA, filtrar_y_puntuar, ordenar_resultados, tiene_categorias_jev)
from servicios import geocodificar_direccion, obtener_minutos_a_pie, obtener_minutos_coche


# ----------------------- CONFIGURACIÓN ----------------------- #

# Ruta calculada a partir de la ubicación de ESTE archivo (no de desde
# dónde se ejecute el comando), para que funcione tanto si lanzas
# `streamlit run algoritmo/app.py` desde la raíz como si haces `cd
# algoritmo` primero.
BASE_DIR = Path(__file__).resolve().parent
MAESTRO_XLSX = BASE_DIR.parent / "excels" / "clasificacion_jev.xlsx"
IMAGENES_DIR = BASE_DIR.parent / "imagenes"
COMPONENTES_DIR = BASE_DIR / "componentes"   # HTML/CSS/JS de los componentes propios y estilos


def recurso(nombre):
    return (COMPONENTES_DIR / nombre).read_text(encoding="utf-8")


TOP_N = 5
TOP_N_MAX = 10

PRESUPUESTO_SIN_LIMITE = 100   # el máximo del slider de presupuesto significa "sin tope"





# --------------------------------------------------------------- #


@st.cache_data
def cargar_datos():
    maestro = pd.read_excel(MAESTRO_XLSX, sheet_name="Restaurantes")
    try:
        df_platos = pd.read_excel(MAESTRO_XLSX, sheet_name="Platos mencionados")
    except Exception:
        df_platos = pd.DataFrame(columns=["ID_Restaurante", "Plato", "Sentimiento"])
    return maestro, df_platos






























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


@st.cache_data(show_spinner=False)
def _foto_base64(ruta):
    return "data:image/jpeg;base64," + base64.b64encode(Path(ruta).read_bytes()).decode()


def foto_restaurante(fila, ancho=160):
    """Foto para el navegador: la descargada en imagenes/ (en base64, porque los componentes
    no ven el disco) o, si no hay, la URL de Google (que puede haber caducado)."""
    imagen_local = IMAGENES_DIR / str(valor_o(fila, "Imagen archivo", ""))
    if imagen_local.is_file():
        return _foto_base64(str(imagen_local))
    url = fila.get("Imagen URL")
    if isinstance(url, str) and url.strip():
        return mejorar_resolucion_imagen(url, ancho=ancho, alto=ancho)
    return None


def estado_cerrado(fila):
    """'Cerrado temporalmente' / 'Cerrado permanentemente' o '' si está abierto."""
    estado = str(valor_o(fila, "Estado", ""))
    return estado if "cerrado" in estado.lower() else ""


def resumen_valoracion(fila):
    puntuacion = fila.get("Puntuación")
    if pd.isna(puntuacion):
        return "Sin nota"
    resenas = fila.get("Nº Reseñas")
    detalle = f" ({int(resenas)})" if pd.notna(resenas) else ""
    return f"⭐ {puntuacion:.1f}".replace(".", ",") + detalle


def icono_transporte(modo_transporte):
    return "🚗" if modo_transporte == "En coche" else "🚶"


def mostrar_ficha(fila, respuestas, df_platos):
    """Ficha completa en una ventana encima de los resultados (se abre al tocar una tarjeta
    o una foto del mapa). No tiene widgets: así ninguna recarga la vuelve a abrir sola."""

    @st.dialog(str(fila["Nombre"]), width="medium")
    def _ficha():
        imagen_local = IMAGENES_DIR / str(valor_o(fila, "Imagen archivo", ""))
        foto = str(imagen_local) if imagen_local.is_file() else foto_restaurante(fila, ancho=800)
        if foto:
            st.image(foto, width="stretch")

        cerrado = estado_cerrado(fila)
        if cerrado:
            st.badge(cerrado, icon=":material/schedule:", color="gray")

        minutos = f"{icono_transporte(respuestas['modo_transporte'])} {fila['Tiempo desplazamiento (min)']:.0f} min"
        direccion = valor_o(fila, "Dirección", "")
        st.markdown(
            f"**{etiqueta_cocina(fila)}**  \n"
            f"{valor_o(fila, 'Rango de precios', 'Precio ?')} · {resumen_valoracion(fila)} reseñas  \n"
            f"{minutos}" + (f" · {direccion}" if direccion else "")
        )

        if respuestas["plato_deseado"]:
            resumen = resumen_mencion_plato(fila["ID"], respuestas["plato_deseado"], df_platos)
            st.markdown(f"**Sobre «{respuestas['plato_deseado']}»:** {resumen}")

        platos = formatear_platos(fila.get("Platos mejor valorados"))
        if platos:
            st.markdown("**Lo que destacan**  \n" + " ".join(
                f":orange-badge[{p.strip()}]" for p in platos.split(",") if p.strip()))

        modo_ruta = "driving" if respuestas["modo_transporte"] == "En coche" else "walking"
        url_ruta = ("https://www.google.com/maps/dir/?api=1&destination="
                    f"{fila['Latitud']},{fila['Longitud']}&travelmode={modo_ruta}")
        st.link_button("Cómo llegar", url_ruta, type="primary", icon=":material/directions:", width="stretch")

        # Instagram/TikTok no tienen una búsqueda por palabra clave fiable sin iniciar
        # sesión, así que se usa el operador site: de Google (funciona sin cuenta).
        nombre = fila["Nombre"]
        buscar = lambda q: "https://www.google.com/search?q=" + urllib.parse.quote(q)
        with st.container(horizontal=True):
            st.link_button("Instagram", buscar(f'site:instagram.com "{nombre}" Madrid'), width="stretch")
            st.link_button("TikTok", buscar(f'site:tiktok.com "{nombre}" Madrid'), width="stretch")
        st.link_button("Buscar en Google", buscar(f"{nombre} Madrid"), type="tertiary",
                       icon=":material/search:", width="stretch")

    _ficha()


# ----------------------- LISTA DE RESULTADOS ----------------------- #
# Componente propio: tarjetas horizontales compactas (foto pequeña + 3 líneas de datos),
# caben 4-5 por pantalla en el móvil. st.columns no sirve aquí porque en pantallas
# estrechas apila la foto encima de los datos. Al tocar una tarjeta se avisa a Python
# para abrir su ficha.

_HTML_LISTA = recurso("lista.html")
_CSS_LISTA = recurso("lista.css")
_JS_LISTA = recurso("lista.js")

_LISTA_RESTAURANTES = st.components.v2.component(
    "lista_restaurantes",
    html=_HTML_LISTA, css=_CSS_LISTA, js=_JS_LISTA,
)


def _al_abrir_desde_lista():
    valor = st.session_state["lista_restaurantes"].abrir
    if valor is not None:
        st.session_state["restaurante_seleccionado"] = int(valor)
        st.session_state["ficha_abrir"] = int(valor)


def mostrar_lista(top, respuestas, seleccionado_id=None):
    icono = icono_transporte(respuestas["modo_transporte"])
    items = []
    for n, (_, fila) in enumerate(top.iterrows(), start=1):
        items.append({
            "id": int(fila["ID"]), "n": n, "nombre": str(fila["Nombre"]),
            "cocina": str(etiqueta_cocina(fila)), "foto": foto_restaurante(fila),
            "meta": (f"{valor_o(fila, 'Rango de precios', 'Precio ?')} · {resumen_valoracion(fila)} · "
                     f"{icono} {fila['Tiempo desplazamiento (min)']:.0f}'"),
            "cerrado": estado_cerrado(fila),
        })
    _LISTA_RESTAURANTES(
        data={"items": items, "seleccionado": seleccionado_id},
        key="lista_restaurantes", on_abrir_change=_al_abrir_desde_lista,
    )


# ----------------------- MAPA CON FOTOS REDONDAS ----------------------- #
# Componente propio (st.components.v2) con Leaflet: cada restaurante es su foto
# redonda con el número de posición (el mismo que en la lista). Al tocar una
# foto se avisa a Python para abrir su ficha. Leaflet y los mosaicos del
# mapa se cargan desde internet (jsDelivr y OpenFreeMap; OpenStreetMap de respaldo).

_HTML_MAPA = recurso("mapa.html")
_CSS_MAPA = recurso("mapa.css")
_JS_MAPA = recurso("mapa.js")

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
    if int(valor) != -1:
        st.session_state["ficha_abrir"] = int(valor)


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
            foto = foto_restaurante(fila)
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
        st.caption("🔵 Tú · Toca una foto para ver la ficha.")
    else:
        st.caption("🔵 Tú — comprueba que el mapa te sitúa donde esperabas.")


# ----------------------- BOTÓN "UBICACIÓN ACTUAL" ----------------------- #
# Componente propio (st.components.v2, sin paquetes externos). Al pulsarlo, el
# navegador pide permiso y devuelve las coordenadas a Python. Se ejecuta en la
# propia página (no en un iframe), así que usa el permiso normal del navegador.
# Requiere HTTPS (Streamlit Cloud lo es) o localhost.

_HTML_UBICACION = recurso("ubicacion.html")
_CSS_UBICACION = recurso("ubicacion.css")
_JS_UBICACION = recurso("ubicacion.js")

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

_HTML_DIRECCION = recurso("direccion.html")
_CSS_DIRECCION = recurso("direccion.css")
_JS_DIRECCION = recurso("direccion.js")

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
# Dos vistas en la misma página: "buscador" y "resultados". El formulario se dibuja
# SIEMPRE (en resultados solo se oculta con CSS): si no se dibujara, Streamlit borraría
# lo que habías escrito y "Cambiar" te devolvería un formulario vacío.

# Ajustes de estilo que el tema de config.toml no cubre. El botón Buscar se queda fijo
# abajo (al alcance del pulgar) con un fondo degradado para que no tape el texto de golpe.
# ponytail: el fondo del botón fijo sigue el modo claro/oscuro del sistema, no el que se
# elija en el menú de Streamlit; si se cambia a mano, el degradado puede no casar.
_CSS_GLOBAL = "\n<style>\n" + recurso("global.css") + "</style>\n"
_CSS_OCULTAR_BUSCADOR = "<style>.st-key-buscador { display: none; }</style>"

ETIQUETAS_TRANSPORTE = {"En coche": "🚗 Coche", "A pie": "🚶 A pie"}


def ir_a_buscador():
    st.session_state["vista"] = "buscador"


def fallar_busqueda(mensaje):
    """Vuelve al buscador y enseña el error allí (si la búsqueda se lanzó desde la vista de
    resultados, el formulario está oculto y un st.error ahí no se vería)."""
    st.session_state["vista"] = "buscador"
    st.session_state["error_busqueda"] = mensaje
    st.rerun()


def buscar_con(**cambios):
    """Botones rápidos del estado "sin resultados": cambian un filtro y repiten la búsqueda."""
    for clave, valor in cambios.items():
        st.session_state[clave] = valor
    st.session_state["buscar_ya"] = True


def texto_presupuesto(minimo, maximo):
    if maximo is None:
        return f"desde {minimo} €" if minimo else "cualquier precio"
    return f"{minimo}–{maximo} €"


def resumen_busqueda(r):
    lugar = (r.get("direccion_encontrada") or "Tu ubicación").split(",")
    partes = [", ".join(p.strip() for p in lugar[:2]),
              r["cocina"] or "Cualquier cocina",
              f"{icono_transporte(r['modo_transporte'])} ≤{r['tiempo_maximo_min']}'",
              texto_presupuesto(r["presupuesto_min"], r["presupuesto_max"])]
    return " · ".join(partes)


# ----------------------- PORTADA ----------------------- #
# Lo primero que se ve al entrar: una cinta de fotos de vuestros restaurantes que se desliza
# despacio (fotos distintas en cada visita). Sin saludos por hora: a veces se busca para
# otro día. Solo CSS: si el móvil pide "reducir movimiento", todo se queda quieto.

FOTOS_PORTADA = 14

_CSS_PORTADA = "\n<style>\n" + recurso("portada.css") + "</style>\n"

# Pantalla de entrada (una vez por visita): 3 fotos entran con rebote, aparece el título y
# todo sube como un telón (~2,5 s). Tapa también la carga inicial de la app. Es decorativa
# (aria-hidden): el contenido real está debajo. Con "reducir movimiento" no se muestra.
_CSS_INTRO = "\n<style>\n" + recurso("intro.css") + "</style>\n"


@st.cache_data(show_spinner=False)
def miniaturas_portada():
    """Todas las fotos de imagenes/ en miniatura (176 px, nítidas a 88 px en pantallas retina;
    ~10 KB): la portada manda 14 en base64 y con las originales sería ~1 MB en cada carga."""
    from PIL import Image
    miniaturas = []
    for ruta in sorted(IMAGENES_DIR.glob("*.jpg")):
        try:
            with Image.open(ruta) as img:
                img = img.convert("RGB")
                img.thumbnail((176, 176))
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=75)
            miniaturas.append("data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode())
        except OSError:
            continue   # foto dañada: simplemente no sale en la cinta
    return miniaturas


def fotos_portada():
    if "fotos_portada" not in st.session_state:   # fotos distintas en cada visita, fijas mientras dure
        todas = miniaturas_portada()
        st.session_state["fotos_portada"] = random.sample(todas, min(FOTOS_PORTADA, len(todas)))
    return st.session_state["fotos_portada"]


def mostrar_intro():
    """Pantalla de entrada, solo en la primera carga de cada visita. Devuelve si se ha mostrado."""
    if st.session_state.get("intro_vista"):
        return False
    st.session_state["intro_vista"] = True
    platos = "".join(f'<img src="{f}" alt="">' for f in fotos_portada()[:3])
    st.html(_CSS_INTRO + f"""
<div class="intro" aria-hidden="true">
  <div class="platos">{platos}</div>
  <div class="titulo">¿Dónde comemos?</div>
  <div class="linea"></div>
</div>
""")
    return True


def mostrar_portada(num_restaurantes, tras_intro=False):
    fotos = fotos_portada()
    # La lista va dos veces seguidas: al desplazarse la mitad, vuelve al principio sin salto.
    cinta = "".join(f'<img src="{f}" alt="">' for f in fotos * 2)

    st.html(_CSS_PORTADA + f"""
<div class="portada{' tras-intro' if tras_intro else ''}">
  {f'<div class="cinta" aria-hidden="true"><div class="pista">{cinta}</div></div>' if fotos else ''}
  <p class="momento">🍽️ Vuestra lista · {num_restaurantes} sitios</p>
  <h1>¿Dónde comemos?</h1>
  <p class="sub">Decid desde dónde salís y qué os apetece, y os digo cuál.</p>
</div>
""")


st.set_page_config(page_title="¿Dónde comemos?", page_icon="🍽️", layout="centered")
st.html(_CSS_GLOBAL)
hay_intro = mostrar_intro()

maestro, df_platos = cargar_datos()
vista = st.session_state.setdefault("vista", "buscador")
if vista == "resultados" and st.session_state.get("resultado") is not None:
    st.html(_CSS_OCULTAR_BUSCADOR)

# ----------------------- VISTA: BUSCADOR ----------------------- #
with st.container(key="buscador"):
    mostrar_portada(len(maestro), tras_intro=hay_intro)

    # Caja de dirección y, justo debajo, el botón "Usar mi ubicación". Reservamos primero
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
            precision = st.session_state.get("precision_ubicacion")
            with st.container(horizontal=True, vertical_alignment="center"):
                detalle = f" · ±{precision:.0f} m" if precision else ""
                st.caption(f"✓ Tu ubicación{detalle}")
                st.button("Quitar", on_click=quitar_ubicacion_actual, type="tertiary")
            if precision and precision > 1000:
                st.caption("⚠️ Es poco precisa (habitual en ordenador). Si no cuadra, quítala y escribe la dirección.")
        elif st.session_state.get("error_ubicacion"):
            clave = st.session_state["error_ubicacion"]
            st.warning(MENSAJES_ERROR_UBICACION.get(clave, MENSAJES_ERROR_UBICACION["2"]))

    ubicacion_actual = st.session_state.get("ubicacion_actual")
    usar_ubicacion_actual = ubicacion_actual is not None

    with caja_direccion:
        direccion, sugerencia_elegida = caja_direccion_con_sugerencias(
            key="caja_direccion",
            disabled=usar_ubicacion_actual,
            placeholder=("Usando tu ubicación" if usar_ubicacion_actual else "Calle, barrio o sitio"),
        )

    modo_transporte = st.segmented_control(
        "¿Cómo vais?", list(ETIQUETAS_TRANSPORTE), format_func=ETIQUETAS_TRANSPORTE.get,
        default="En coche", key="transporte", width="stretch",
    ) or "En coche"   # si se desmarca la opción elegida, vuelve a coche
    tiempo_maximo_min = st.slider("Tiempo máximo", 5, 60, 20, step=5, format="%d min", key="tiempo")

    if tiene_categorias_jev(maestro):
        cocinas_disponibles = sorted(maestro[COL_CATEGORIA].dropna().unique())
    else:   # maestro sin categorías de Jev: se usa el tipo de Google
        cocinas_disponibles = sorted(maestro["Tipo de cocina"].dropna().unique().tolist())
    cocina = st.selectbox("Cocina", ["Cualquiera"] + cocinas_disponibles, key="cocina")

    presupuesto_min, presupuesto_max = st.slider(
        "Presupuesto por persona", 0, PRESUPUESTO_SIN_LIMITE, (0, 30), step=5, format="%d €", key="presupuesto",
        help=f"Arrastra el máximo hasta {PRESUPUESTO_SIN_LIMITE} € para no poner tope.",
    )
    if presupuesto_max == PRESUPUESTO_SIN_LIMITE:
        presupuesto_max = None   # solapamiento() trata None como "sin tope"

    with st.expander("Más opciones"):
        plato_deseado = st.text_input("¿Algún plato concreto?", placeholder="ej. sushi", key="plato")

    enviado = st.button("Buscar restaurantes", type="primary", icon=":material/search:",
                        width="stretch", key="boton_buscar")
    enviado = enviado or st.session_state.pop("buscar_ya", False)
    if st.session_state.get("error_busqueda") and not enviado:
        st.error(st.session_state.pop("error_busqueda"))

    if enviado:
        direccion_encontrada = None
        if usar_ubicacion_actual and ubicacion_actual:
            ubicacion_usuario = ubicacion_actual
        elif sugerencia_elegida:   # ya trae coordenadas: no hace falta geocodificar
            ubicacion_usuario = (sugerencia_elegida["lat"], sugerencia_elegida["lon"])
            direccion_encontrada = sugerencia_elegida["texto"]
        else:
            if not direccion.strip():
                fallar_busqueda("Dinos desde dónde salís (o usa tu ubicación).")

            try:
                with st.spinner("Localizando tu dirección..."):
                    encontrada = geocodificar_direccion(direccion)
            except GeocoderServiceError as e:
                fallar_busqueda(f"El servicio de mapas no responde ahora mismo ({type(e).__name__}). "
                                f"Prueba en un rato o usa tu ubicación.")

            if encontrada is None:
                fallar_busqueda("No he encontrado esa dirección en Madrid. Prueba con calle y número o un barrio.")
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
        }

        texto_spinner = ("Calculando tiempos en coche..." if modo_transporte == "En coche"
                         else "Calculando tiempos andando...")
        aviso_tiempos = None
        with st.spinner(texto_spinner):
            if modo_transporte == "A pie":
                clave_ors = leer_secreto("ORS_API_KEY")
                minutos = obtener_minutos_a_pie(ubicacion_usuario, maestro, clave_ors)
                if not clave_ors:
                    aviso_tiempos = ("No hay configurada una clave de OpenRouteService (ORS_API_KEY) en los "
                                     "secretos de la app: el tiempo a pie se estima por distancia en línea "
                                     "recta, no por calles reales.")
            else:
                minutos = obtener_minutos_coche(ubicacion_usuario, maestro)
            df_puntuado = filtrar_y_puntuar(maestro, df_platos, respuestas, minutos)
        respuestas["aviso_tiempos"] = aviso_tiempos

        # El resultado se guarda en la sesión: cambiar el orden, la vista o pulsar
        # "Ver más" vuelve a dibujar la página sin repetir toda la búsqueda.
        st.session_state["resultado"] = {"df_puntuado": df_puntuado, "respuestas": respuestas}
        st.session_state["num_mostrados"] = TOP_N
        st.session_state["restaurante_seleccionado"] = None
        st.session_state["vista"] = "resultados"
        st.rerun()

# ----------------------- VISTA: RESULTADOS ----------------------- #
resultado = st.session_state.get("resultado")
if vista == "resultados" and resultado is not None:
    respuestas = resultado["respuestas"]
    ubicacion_usuario = respuestas["ubicacion_usuario"]

    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("Cambiar", icon=":material/arrow_back:", type="tertiary", on_click=ir_a_buscador)
        modo_vista = st.segmented_control(
            "Vista", ["Lista", "Mapa"], default="Lista", key="modo_vista", label_visibility="collapsed",
        ) or "Lista"
    st.caption(resumen_busqueda(respuestas))
    if respuestas.get("aviso_tiempos"):
        st.warning(respuestas["aviso_tiempos"])

    df_puntuado = resultado["df_puntuado"]
    if df_puntuado.empty:
        with st.container(border=True):
            st.subheader("Nada por aquí")
            etiqueta_modo = "en coche" if respuestas["modo_transporte"] == "En coche" else "andando"
            st.write(f"No hay ningún restaurante a menos de {respuestas['tiempo_maximo_min']} min "
                     f"{etiqueta_modo} que cumpla lo que habéis pedido.")
            with st.container(horizontal=True, wrap=True):
                if respuestas["tiempo_maximo_min"] < 60:
                    nuevo_tiempo = min(60, respuestas["tiempo_maximo_min"] + 10)
                    st.button(f"Ampliar a {nuevo_tiempo} min", on_click=buscar_con, kwargs={"tiempo": nuevo_tiempo})
                if respuestas["cocina"]:
                    st.button("Cualquier cocina", on_click=buscar_con, kwargs={"cocina": "Cualquiera"})
                if respuestas["plato_deseado"]:
                    st.button("Sin plato concreto", on_click=buscar_con, kwargs={"plato": ""})
        mostrar_mapa(*ubicacion_usuario)
        st.stop()

    orden = st.segmented_control(
        "Ordenar", [ORDEN_PUNTUACION, ORDEN_CERCANOS], default=ORDEN_PUNTUACION, key="orden",
        label_visibility="collapsed",
    ) or ORDEN_PUNTUACION
    df_puntuado = ordenar_resultados(df_puntuado, orden)

    num_mostrados = min(st.session_state.get("num_mostrados", TOP_N), TOP_N_MAX, len(df_puntuado))
    top = df_puntuado.head(num_mostrados)
    ids_top = [int(x) for x in top["ID"].tolist()]
    seleccionado = st.session_state.get("restaurante_seleccionado")
    if seleccionado not in ids_top:
        seleccionado = None

    if len(df_puntuado) == 1:
        st.markdown("**Solo hay 1 sitio que encaja**")
    elif len(df_puntuado) < TOP_N:
        st.markdown(f"**Solo hay {len(df_puntuado)} que encajan**")

    if modo_vista == "Mapa":
        mostrar_mapa(*ubicacion_usuario, top, seleccionado)
    mostrar_lista(top, respuestas, seleccionado)

    # "Ver más": de 5 en 5 hasta 10, y solo si quedan restaurantes que encajen.
    quedan = min(TOP_N_MAX, len(df_puntuado)) - num_mostrados
    if quedan > 0:
        if st.button(f"Ver {min(5, quedan)} más", width="stretch"):
            st.session_state["num_mostrados"] = num_mostrados + min(5, quedan)
            st.rerun()

    # Ficha: se abre solo en la recarga justo después de tocar una tarjeta o una foto del
    # mapa (pop), así que al cerrarla con ✕ no vuelve a aparecer sola.
    abrir = st.session_state.pop("ficha_abrir", None)
    if abrir in ids_top:
        mostrar_ficha(top.iloc[ids_top.index(abrir)], respuestas, df_platos)
