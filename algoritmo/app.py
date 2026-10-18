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

import html
import io
import re
import base64
import random
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from geopy.exc import GeocoderServiceError
from streamlit.errors import StreamlitAPIException

from logica import (COL_CATEGORIA, COL_CATEGORIA_2, COL_VOTOS_2, ORDEN_CERCANOS, ORDEN_NOMBRE, ORDEN_PUNTUACION,
                    ORDEN_RESENAS, VOTOS_MIN_SECUNDARIA, estadisticas_lista, filtrar_lista, filtrar_y_puntuar,
                    ordenar_resultados, sugerencia_plato, tiene_categorias_jev)
from servicios import geocodificar_direccion, obtener_minutos_a_pie, obtener_minutos_coche
import acceso
import amigos
import datos as bd
from cuentas import Cuentas
from logica import hace_cuanto
from sesion import config_multiusuario, datos_google, usuario_actual


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


# Modo multiusuario (login de Google + Supabase) si los secrets lo configuran; si no, modo local
# con los excels de siempre. Ver sesion.py.
CONFIG_MULTIUSUARIO = config_multiusuario()
BD = bd.Supabase(CONFIG_MULTIUSUARIO["url"], CONFIG_MULTIUSUARIO["clave_servicio"]) if CONFIG_MULTIUSUARIO else None
# Cuentas con correo y contraseña (Supabase Auth), además de Google. Ver cuentas.py y acceso.py.
CUENTAS = Cuentas(CONFIG_MULTIUSUARIO["url"], CONFIG_MULTIUSUARIO["clave_servicio"]) if CONFIG_MULTIUSUARIO else None


@st.cache_data
def cargar_datos():
    maestro = pd.read_excel(MAESTRO_XLSX, sheet_name="Restaurantes")
    try:
        df_platos = pd.read_excel(MAESTRO_XLSX, sheet_name="Platos mencionados")
    except Exception:
        df_platos = pd.DataFrame(columns=["ID_Restaurante", "Plato", "Sentimiento"])
    return maestro, df_platos


@st.cache_data(ttl=300, show_spinner=False)   # 5 min: lo que tarda en verse una lista recién procesada
def cargar_datos_usuario(usuario):
    """(maestro, df_platos, lista) del usuario en modo multiusuario."""
    return BD.restaurantes_de(usuario)






























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
    """Foto para el navegador: en multiusuario, la de Supabase Storage (URL pública); en local,
    la descargada en imagenes/ (en base64, porque los componentes no ven el disco). Si no hay,
    la URL de Google (que puede haber caducado)."""
    archivo = valor_o(fila, "Imagen archivo", "")
    if BD is not None and archivo:
        return BD.url_foto(archivo)
    imagen_local = IMAGENES_DIR / str(archivo)
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


def contenido_ficha(fila, df_platos, plato=None, modo_transporte=None):
    """Foto, datos, lo que destacan y enlaces de un restaurante. `modo_transporte` solo viene de una
    búsqueda (trae el tiempo de viaje); `plato`, de una búsqueda con plato o de la idea de Inicio."""
    if BD is not None and usuario:
        bloque_valoracion(fila)
    imagen_local = IMAGENES_DIR / str(valor_o(fila, "Imagen archivo", ""))
    foto = str(imagen_local) if BD is None and imagen_local.is_file() else foto_restaurante(fila, ancho=800)
    if foto:
        st.image(foto, width="stretch")

    cerrado = estado_cerrado(fila)
    if cerrado:
        st.badge(cerrado, icon=":material/schedule:", color="gray")

    lugar = [valor_o(fila, "Dirección", "")]
    if modo_transporte:
        lugar.insert(0, f"{icono_transporte(modo_transporte)} {fila['Tiempo desplazamiento (min)']:.0f} min")
    st.markdown(
        f"**{etiqueta_cocina(fila)}**  \n"
        f"{valor_o(fila, 'Rango de precios', 'Precio ?')} · {resumen_valoracion(fila)} reseñas  \n"
        + " · ".join(p for p in lugar if p)
    )

    if plato:
        st.markdown(f"**Sobre «{plato}»:** {resumen_mencion_plato(fila['ID'], plato, df_platos)}")

    platos = formatear_platos(fila.get("Platos mejor valorados"))
    if platos:
        st.markdown("**Lo que destacan**  \n" + " ".join(
            f":orange-badge[{p.strip()}]" for p in platos.split(",") if p.strip()))

    url_ruta = f"https://www.google.com/maps/dir/?api=1&destination={fila['Latitud']},{fila['Longitud']}"
    if modo_transporte:
        url_ruta += "&travelmode=" + ("driving" if modo_transporte == "En coche" else "walking")
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


# ----------------------- "HE IDO": NOTA EN MEDIAS ESTRELLAS Y COMENTARIO ----------------------- #

_ESTRELLAS = st.components.v2.component(
    "estrellas_nota", html=recurso("estrellas.html"), css=recurso("estrellas.css"), js=recurso("estrellas.js"),
)


def estrellas(key, guardada=None):
    """Nota de 0,5 a 5 (medias estrellas). La que se acaba de tocar manda sobre la guardada."""
    try:
        tocada = st.session_state[key].nota
    except (KeyError, AttributeError):
        tocada = None
    actual = tocada if tocada is not None else guardada
    _ESTRELLAS(key=key, data={"valor": actual}, on_nota_change=lambda: None)
    return actual


def mis_visitas():
    """{id del restaurante: tu valoración} ({} en modo local o si no se puede leer)."""
    if BD is None or not usuario:
        return {}
    try:
        df = amigos.cargar_mis_visitas(BD, usuario)
    except bd.ErrorSupabase:
        return {}
    return {int(f["ID"]): f for _, f in df.iterrows()}


def _o_none(valor):
    return None if valor is None or (not isinstance(valor, str) and pd.isna(valor)) else valor


def bloque_valoracion(fila):
    """Arriba de la ficha: tu nota, lo que más te gustó y "He ido" (lo ven tus amigos en su Inicio). En
    verde si ya has ido. La ficha es una ventana (st.dialog): tocar aquí solo recarga la ventana."""
    id_restaurante = int(fila["ID"])
    visita = mis_visitas().get(id_restaurante)
    clave = f"{'visitado' if visita is not None else 'valoracion'}_{id_restaurante}"
    with st.container(border=True, key=clave):
        if visita is not None:
            st.markdown(f"**✓ Has ido** · {hace_cuanto(visita['Fecha visita'], datetime.now(timezone.utc))}")
        else:
            st.markdown("**¿Has ido?** Puntúalo: tus amigos lo verán en su Inicio.")
        nota = estrellas(f"nota_visita_{id_restaurante}",
                         _o_none(visita["Nota visita"]) if visita is not None else None)
        comentario = st.text_area(
            "Lo que más te gustó", value=(_o_none(visita["Comentario visita"]) or "") if visita is not None else "",
            max_chars=bd.LARGO_MAX_COMENTARIO, key=f"comentario_visita_{id_restaurante}", height=80,
            placeholder="ej. Las croquetas y el trato")
        with st.container(horizontal=True):
            guardar = st.button("Guardar" if visita is not None else "He ido", type="primary",
                                icon=":material/check_circle:", width="stretch", key=f"he_ido_{id_restaurante}")
            quitar = visita is not None and st.button("Quitar", type="tertiary", key=f"quitar_visita_{id_restaurante}")
    if not (guardar or quitar):
        return
    try:
        if quitar:
            BD.quitar_visita(usuario, id_restaurante)
        else:
            BD.registrar_visita(usuario, id_restaurante, nota, comentario)
    except ValueError as e:
        st.error(str(e))
        return
    except bd.ErrorSupabase:
        st.error("No se ha podido guardar ahora mismo (¿falta ejecutar supabase/005_valoraciones.sql?).")
        return
    amigos.limpiar_cache()
    try:
        st.rerun(scope="fragment")   # la ventana se vuelve a dibujar ya en verde (o sin verde, si lo has quitado)
    except StreamlitAPIException:    # no venía de la ventana (p. ej. en AppTest, que recarga todo): recarga entera
        st.rerun()


def mostrar_ficha(fila, df_platos, plato=None, modo_transporte=None):
    """Ficha completa en una ventana encima de la lista (se abre al tocar una tarjeta o una foto
    del mapa). No tiene widgets: así ninguna recarga la vuelve a abrir sola."""

    @st.dialog(str(fila["Nombre"]), width="medium")
    def _ficha():
        contenido_ficha(fila, df_platos, plato, modo_transporte)

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


def _al_abrir_desde_lista(key):
    valor = st.session_state[key].abrir
    if valor is not None:
        st.session_state["restaurante_seleccionado"] = int(valor)
        st.session_state["ficha_abrir"] = int(valor)


def mostrar_lista(top, modo_transporte=None, seleccionado_id=None, key="lista_restaurantes", extra=None,
                  carrusel=False, estatica=False):
    """Tarjetas de `top`. Con `modo_transporte` (resultados de una búsqueda) enseñan el tiempo de viaje;
    `extra(fila)` añade datos a la tarjeta (amigo, cuando, nota, cita: ver componentes/lista.js). Las de
    sitios a los que ya has ido llevan "✓ Has ido"."""
    visitados = set(mis_visitas())
    items = []
    for n, (_, fila) in enumerate(top.iterrows(), start=1):
        meta = f"{valor_o(fila, 'Rango de precios', 'Precio ?')} · {resumen_valoracion(fila)}"
        if modo_transporte:
            meta += f" · {icono_transporte(modo_transporte)} {fila['Tiempo desplazamiento (min)']:.0f}'"
        items.append({
            "id": int(fila["ID"]), "n": n, "nombre": str(fila["Nombre"]),
            "cocina": str(etiqueta_cocina(fila)), "foto": foto_restaurante(fila), "meta": meta,
            "cerrado": estado_cerrado(fila), "visitado": int(fila["ID"]) in visitados,
            **(extra(fila) if extra else {}),
        })
    _LISTA_RESTAURANTES(
        # carrusel: fila que se desliza; estatica: solo para mirar (no abre la ficha)
        data={"items": items, "seleccionado": seleccionado_id, "carrusel": carrusel, "estatica": estatica},
        key=key, on_abrir_change=lambda: _al_abrir_desde_lista(key),
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


def fotos_portada(maestro=None):
    """Fotos de la cinta: distintas en cada visita y fijas mientras dura. En multiusuario son las
    de los restaurantes del usuario (URLs de Supabase); en local, miniaturas de imagenes/."""
    if "fotos_portada" not in st.session_state:
        if BD is not None:
            archivos = [] if maestro is None or maestro.empty else maestro["Imagen archivo"].dropna().tolist()
            todas = [BD.url_foto(a) for a in archivos]
        else:
            todas = miniaturas_portada()
        if not todas:   # sin fotos todavía (p. ej. antes de entrar): no se fija, se reintenta luego
            return []
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


def mostrar_portada(num_restaurantes, tras_intro=False, maestro=None,
                    momento=None, subtitulo="Decid desde dónde salís y qué os apetece, y os digo cuál."):
    fotos = fotos_portada(maestro)
    # La lista va dos veces seguidas: al desplazarse la mitad, vuelve al principio sin salto.
    cinta = "".join(f'<img src="{f}" alt="">' for f in fotos * 2)
    momento = momento or f"🍽️ Vuestra lista · {num_restaurantes} sitios"

    st.html(_CSS_PORTADA + f"""
<div class="portada{' tras-intro' if tras_intro else ''}">
  {f'<div class="cinta" aria-hidden="true"><div class="pista">{cinta}</div></div>' if fotos else ''}
  <p class="momento">{momento}</p>
  <h1>¿Dónde comemos?</h1>
  <p class="sub">{subtitulo}</p>
</div>
""")


# ----------------------- BARRA DE SECCIONES ----------------------- #
# Componente propio fijo abajo: Inicio, Comer hoy (el buscador), Mi lista y Perfil (con la foto de
# Google del usuario como icono). Solo se dibuja la sección elegida; lo escrito en las demás se
# conserva con conservar_formularios().

SECCIONES = ("inicio", "comer", "mi_lista", "perfil")
_BARRA = st.components.v2.component(
    "barra_secciones", html=recurso("barra.html"), css=recurso("barra.css"), js=recurso("barra.js"),
)

# Widgets de cada sección cuyo valor tiene que sobrevivir mientras se está en otra.
CLAVES_FORMULARIOS = {
    "comer": ("fuente", "transporte", "tiempo", "cocina", "presupuesto", "plato", "modo_vista", "orden"),
    "mi_lista": ("ml_texto", "ml_cocinas", "ml_presupuesto", "ml_nota", "ml_plato", "ml_cerrados", "ml_orden"),
}


def ir_a(seccion):
    st.session_state["seccion"] = seccion


def _al_cambiar_seccion():
    seccion = st.session_state["barra_secciones"].seccion
    if seccion in SECCIONES:
        ir_a(seccion)


def barra_secciones(seccion, foto=None, avisos=0):
    """`avisos`: solicitudes de amistad pendientes (globito sobre el icono de Perfil)."""
    _BARRA(key="barra_secciones", data={"activa": seccion, "foto": foto, "avisos": avisos},
           on_seccion_change=_al_cambiar_seccion)


def conservar_formularios(seccion):
    """Streamlit borra el valor de un widget que no se dibuja; volver a guardarlo a mano lo conserva
    (truco documentado: "widget state across pages"). Así, al volver a una sección, sigue lo escrito."""
    for otra, claves in CLAVES_FORMULARIOS.items():
        if otra != seccion:
            for clave in claves:
                if clave in st.session_state:
                    st.session_state[clave] = st.session_state[clave]


def cocinas_disponibles(maestro):
    if tiene_categorias_jev(maestro):
        return sorted(maestro[COL_CATEGORIA].dropna().unique())
    return sorted(maestro["Tipo de cocina"].dropna().unique().tolist())   # sin categorías de Jev: la de Google


# ----------------------- INICIO ----------------------- #
# Una idea para hoy: un plato que las reseñas de tu lista elogian y el sitio donde más lo elogian.

def otra_sugerencia():
    anterior = st.session_state.pop("sugerencia", None)
    st.session_state["sugerencia_evitar"] = anterior and anterior[0]


def buscar_sitios_con(plato):
    """De la idea de Inicio a "Comer hoy" con el plato ya puesto."""
    st.session_state["plato"] = plato
    st.session_state["vista"] = "buscador"
    ir_a("comer")


_CSS_INICIO = "<style>\n" + recurso("inicio.css") + "</style>\n"


def seccion_inicio(maestro, df_platos, tras_intro, momento, nombre=None):
    abrir = st.session_state.pop("ficha_abrir", None)   # la ficha a abrir, de la idea o de los amigos
    idea_del_dia(maestro, df_platos, tras_intro, momento, nombre, abrir)
    if BD is not None:
        visitas_de_amigos(abrir)


def idea_del_dia(maestro, df_platos, tras_intro, momento, nombre, abrir):
    saludo = f"Hola, {html.escape(nombre)}. " if nombre else ""
    mostrar_portada(len(maestro), tras_intro=tras_intro, maestro=maestro, momento=momento,
                    subtitulo=f"{saludo}Una idea para hoy:")
    sugerencia = st.session_state.get("sugerencia")
    if sugerencia is None or sugerencia[1] not in set(maestro.get("ID", [])):
        sugerencia = sugerencia_plato(maestro, df_platos, random.Random(),
                                      evitar=st.session_state.pop("sugerencia_evitar", None))
        st.session_state["sugerencia"] = sugerencia
    if sugerencia is None:
        if maestro.empty and CONFIG_MULTIUSUARIO:
            st.info("Todavía no tienes restaurantes en tu lista. Añádela en tu **Perfil** y aquí te propondré "
                    "qué comer y dónde.")
            st.button("Añadir tu lista", on_click=ir_a, args=("perfil",), icon=":material/add_location_alt:")
        else:
            st.info("Cuando las reseñas de tu lista estén analizadas, aquí te propondré qué comer y dónde.")
        return

    plato, id_restaurante, menciones = sugerencia
    fila = maestro[maestro["ID"] == id_restaurante].iloc[0]
    with st.container(border=True):   # compacta: cabe entera en la pantalla del móvil sin deslizar
        st.subheader(f"¿Te apetece {plato}?")
        foto = foto_restaurante(fila, ancho=600)
        datos = [str(etiqueta_cocina(fila)), f"{valor_o(fila, 'Rango de precios', 'Precio ?')} · {resumen_valoracion(fila)}"]
        if estado_cerrado(fila):
            datos.append(estado_cerrado(fila))
        st.html(_CSS_INICIO + '<div class="sugerida">'
                + (f'<img src="{html.escape(foto)}" alt="" referrerpolicy="no-referrer">' if foto else "")
                + f'<p>Te gustará <b>{html.escape(str(fila["Nombre"]))}</b>: {menciones} reseñas hablan bien de '
                  f'su {html.escape(plato)}.</p><p class="datos">{html.escape(" · ".join(datos))}</p></div>')
        with st.container(horizontal=True):
            st.link_button("Cómo llegar", f"https://www.google.com/maps/dir/?api=1&destination="
                           f"{fila['Latitud']},{fila['Longitud']}", type="primary", icon=":material/directions:",
                           width="stretch")
            st.button("Ver ficha", on_click=lambda: st.session_state.update(ficha_abrir=id_restaurante),
                      icon=":material/info:", width="stretch", key="ver_ficha_sugerida")
    if abrir == id_restaurante:
        mostrar_ficha(fila, df_platos, plato)
    with st.container(horizontal=True, wrap=True):
        st.button("Otra idea", on_click=otra_sugerencia, icon=":material/casino:", key="otra_idea")
        st.button(f"Más sitios con {plato}", on_click=buscar_sitios_con, args=(plato,),
                  icon=":material/search:", key="buscar_plato")


def visitas_de_amigos(abrir):
    """Inicio: los últimos sitios a los que han ido tus amigos (botón "He ido" de la ficha)."""
    st.subheader("Tus amigos han ido a")
    try:
        df = amigos.cargar_visitas_amigos(BD, usuario)
    except bd.ErrorSupabase:
        st.caption("No se puede ver ahora mismo.")
        return
    if df is None:
        st.caption("Añade amigos desde tu **Perfil** y aquí verás los últimos sitios a los que han ido.")
        st.button("Buscar amigos", on_click=ir_a, args=("perfil",), icon=":material/person_add:", key="ir_a_amigos")
        return
    if df.empty:
        st.caption(f"Tus amigos no han marcado ningún sitio con «He ido» en las últimas "
                   f"{amigos.DIAS_VISITAS_AMIGOS // 7} semanas.")
        return
    ahora = datetime.now(timezone.utc)
    mostrar_lista(df, key="lista_amigos", carrusel=True, extra=lambda f: {
        "amigo": str(f["Amigo"]), "cuando": hace_cuanto(f["Fecha visita"], ahora),
        "nota": _o_none(f["Nota visita"]), "cita": _o_none(f["Comentario visita"])})
    # Si ese sitio es también la idea del día, ya se ha abierto su ficha arriba.
    coincide = df[df["ID"] == abrir]
    if abrir is not None and not coincide.empty and abrir != (st.session_state.get("sugerencia") or (0, None))[1]:
        mostrar_ficha(coincide.iloc[0], pd.DataFrame(columns=bd.COLUMNAS_PLATOS))


# ----------------------- MI LISTA ----------------------- #
# Todos los restaurantes de la lista del usuario, con buscador por nombre y filtros.

MI_LISTA_POR_PAGINA = 20


def seccion_mi_lista(maestro, df_platos):
    st.header("Mi lista")
    if maestro.empty:
        st.info("Todavía no tienes restaurantes en tu lista. Añádela en tu **Perfil**.")
        st.button("Añadir tu lista", on_click=ir_a, args=("perfil",), icon=":material/add_location_alt:")
        return

    texto = st.text_input("Buscar por nombre", placeholder="Buscar por nombre", key="ml_texto",
                          label_visibility="collapsed", icon=":material/search:")
    # Cuántos filtros hay puestos, para que se vea aunque el desplegable esté cerrado (p. ej. al llegar
    # desde la gráfica de cocinas del Perfil con una cocina ya elegida).
    estado = st.session_state
    activos = sum([bool(estado.get("ml_cocinas")), bool(estado.get("ml_nota")), bool(estado.get("ml_plato", "").strip()),
                   bool(estado.get("ml_cerrados")),
                   tuple(estado.get("ml_presupuesto", (0, PRESUPUESTO_SIN_LIMITE))) != (0, PRESUPUESTO_SIN_LIMITE)])
    with st.expander(f"Filtros ({activos})" if activos else "Filtros", icon=":material/tune:"):
        cocinas = st.multiselect("Cocina", cocinas_disponibles(maestro), key="ml_cocinas", placeholder="Cualquiera")
        presupuesto_min, presupuesto_max = st.slider(
            "Presupuesto por persona", 0, PRESUPUESTO_SIN_LIMITE, (0, PRESUPUESTO_SIN_LIMITE), step=5,
            format="%d €", key="ml_presupuesto")
        nota_min = st.slider("Nota mínima en Google", 0.0, 5.0, 0.0, step=0.5, format="%.1f ⭐", key="ml_nota")
        plato = st.text_input("Plato que destaquen", placeholder="ej. croquetas", key="ml_plato")
        ocultar_cerrados = st.toggle("Ocultar los cerrados", key="ml_cerrados")
    orden = st.segmented_control("Ordenar", [ORDEN_PUNTUACION, ORDEN_RESENAS, ORDEN_NOMBRE], default=ORDEN_PUNTUACION,
                                 key="ml_orden", label_visibility="collapsed") or ORDEN_PUNTUACION

    df = filtrar_lista(maestro, df_platos, texto, cocinas, presupuesto_min,
                       None if presupuesto_max == PRESUPUESTO_SIN_LIMITE else presupuesto_max,
                       nota_min, plato, ocultar_cerrados, orden)
    st.caption(f"{len(df)} de {len(maestro)} restaurantes")
    if df.empty:
        st.info("Ninguno cumple esos filtros.")
        return

    # Se pintan de 20 en 20: cada tarjeta lleva su foto.
    filtros = (texto, tuple(cocinas), presupuesto_min, presupuesto_max, nota_min, plato, ocultar_cerrados, orden)
    if st.session_state.get("ml_filtros") != filtros:
        st.session_state["ml_filtros"], st.session_state["ml_mostrados"] = filtros, MI_LISTA_POR_PAGINA
    top = df.head(st.session_state["ml_mostrados"])
    mostrar_lista(top, key="lista_mi_lista")
    if len(df) > len(top):
        if st.button(f"Ver más ({len(df) - len(top)} restantes)", width="stretch", key="ml_ver_mas"):
            st.session_state["ml_mostrados"] += MI_LISTA_POR_PAGINA
            st.rerun()

    abrir = st.session_state.pop("ficha_abrir", None)
    if abrir in set(top["ID"]):
        mostrar_ficha(top[top["ID"] == abrir].iloc[0], df_platos, plato.strip() or None)


# ----------------------- PERFIL ----------------------- #

ESTADOS_LISTA = {
    "sin_lista": "Todavía no has añadido tu lista.",
    "pendiente": "⏳ Pendiente de sincronizar. Las listas nuevas se procesan cuando el procesador del "
                 "administrador está en marcha; si alguien ya tenía esta misma lista, se copia al momento.",
    "procesando": "⚙️ Procesando tu lista ahora mismo…",
    "lista": "✓ Tu lista está al día.",
    "error": "⚠️ No se pudo procesar tu lista.",
}

FUENTE_MI_LISTA, FUENTE_TODOS = "Mi lista", "Todos los restaurantes"


@st.cache_data(ttl=600, show_spinner=False)
def cargar_catalogo():
    """Todos los restaurantes de la base de datos (de todas las listas), para "Buscar en: Todos"."""
    return BD.todos_los_restaurantes()


@st.cache_data(ttl=300, show_spinner=False)
def cargar_perfil(usuario):
    return BD.perfil_de(usuario)


def nombre_visible(usuario, perfil, google):
    """El que haya elegido en "Datos personales"; si no, el de Google; si no, lo de antes de la @."""
    return (perfil or {}).get("nombre") or google.get("nombre") or usuario.split("@")[0]


def bloque_datos_personales(usuario, nombre):
    st.subheader("Datos personales")
    nuevo = st.text_input("Nombre", value=nombre, max_chars=bd.LARGO_MAX_NOMBRE, key="perfil_nombre",
                          help="Es el nombre con el que te saluda la app.")
    st.caption("El correo identifica tu cuenta y tu lista: no se cambia aquí.")
    if st.button("Guardar nombre", width="stretch", key="guardar_perfil"):
        try:
            BD.guardar_perfil(usuario, bd.validar_nombre(nuevo))
        except ValueError as e:
            st.error(str(e))
            return
        except bd.ErrorSupabase:
            st.error("No se han podido guardar los cambios ahora mismo. Inténtalo en un momento.")
            return
        cargar_perfil.clear()
        st.rerun()   # todo saluda ya con el nombre nuevo


def pedir_sincronizar_lista(usuario, enlace):
    """Devuelve un mensaje de error para el usuario, o None si se ha pedido bien."""
    enlace = (enlace or "").strip()
    if not bd.enlace_lista_valido(enlace):
        return ("Ese enlace no parece de una lista de Google Maps. En Google Maps: abre tu lista → "
                "Compartir → copiar enlace (empieza por https://maps.app.goo.gl/).")
    try:
        BD.pedir_actualizacion(usuario, enlace)
    except bd.ErrorSupabase:
        return "No se ha podido guardar ahora mismo. Inténtalo en un momento."
    cargar_datos_usuario.clear()
    return None


def bloque_tus_listas(usuario, lista):
    """Estado de la sincronización y enlace de la lista de Google Maps."""
    st.subheader("Tus listas")
    estado = lista["estado"] if lista else "sin_lista"
    st.markdown(ESTADOS_LISTA.get(estado, estado))
    if lista and lista.get("actualizado_en"):
        st.caption(f"Última sincronización: {lista['actualizado_en'][:16].replace('T', ' ')} (UTC)")
    if lista and lista.get("mensaje"):
        st.caption(lista["mensaje"])
    enlace = st.text_input("Enlace de tu lista", value=(lista or {}).get("enlace") or "", key="enlace_lista",
                           placeholder="https://maps.app.goo.gl/...",
                           help="En Google Maps: abre tu lista → Compartir → copiar enlace.")
    if st.button("Guardar y sincronizar", type="primary", width="stretch", key="sincronizar_lista",
                 disabled=estado == "procesando"):
        error = pedir_sincronizar_lista(usuario, enlace)
        if error:
            st.error(error)
        else:
            st.rerun()   # si la lista ya existía en otra cuenta, aparece al momento
    st.caption("Sincronizar vuelve a leer tu lista de Google Maps: añade los sitios nuevos y quita los "
               "que hayas borrado.")


def bloque_estadisticas(maestro):
    st.subheader("Tus estadísticas")
    e = estadisticas_lista(maestro)
    if e is None:
        st.caption("Aparecerán cuando tengas restaurantes en tu lista.")
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        # el nº de restaurantes lleva a "Mi lista" (estilo de cifra grande en global.css, .st-key-ver_mi_lista)
        st.button(f"**{e['total']}** Restaurantes", type="tertiary", icon=":material/chevron_right:",
                  icon_position="right", key="ver_mi_lista", on_click=ver_en_mi_lista, help="Verlos en Mi lista")
        st.metric("Nota media", "–" if e["nota_media"] is None else f"{e['nota_media']:.1f} ⭐".replace(".", ","))
        st.metric("Precio medio", "–" if e["precio_medio"] is None else f"{e['precio_medio']:.0f} €")
    if not e["cocinas"].empty:
        st.markdown("**Las cocinas que más se repiten**")
        st.caption("Toca una para ver esos restaurantes en Mi lista.")
        datos_grafica = e["cocinas"].rename_axis("Cocina").reset_index(name="Restaurantes")
        tocada = alt.selection_point(name="cocina", fields=["Cocina"], on="click")
        # naranja intermedio entre el acento claro (#C2410C) y el oscuro (#FB923C): se ve bien en los dos
        grafica = alt.Chart(datos_grafica).mark_bar(color="#EA580C", cornerRadiusEnd=4, cursor="pointer").encode(
            x=alt.X("Restaurantes:Q", title=None, axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("Cocina:N", sort="-x", title=None),
            tooltip=["Cocina", "Restaurantes"],
        ).add_params(tocada).properties(height=220)
        st.altair_chart(grafica, on_select=_al_tocar_cocina, key="grafica_cocinas", width="stretch")


def ver_en_mi_lista(cocina=None):
    """A "Mi lista": con solo esa cocina filtrada, o sin filtro de cocina."""
    st.session_state["ml_cocinas"] = [cocina] if cocina else []
    ir_a("mi_lista")


def _al_tocar_cocina():
    puntos = st.session_state["grafica_cocinas"].selection.get("cocina") or []
    if puntos and puntos[0].get("Cocina"):
        ver_en_mi_lista(puntos[0]["Cocina"])


def bloque_preferencias(usuario, nombre, preferencias):
    st.subheader("Preferencias")
    st.caption("Lo que viene ya puesto al buscar en **Comer hoy**.")
    transporte = st.segmented_control(
        "¿Cómo soléis ir?", list(ETIQUETAS_TRANSPORTE), format_func=ETIQUETAS_TRANSPORTE.get,
        default=preferencias["transporte"], key="pref_transporte", width="stretch") or "En coche"
    tiempo = st.slider("Tiempo máximo", 5, 60, preferencias["tiempo"], step=5, format="%d min", key="pref_tiempo")
    presupuesto = st.slider("Presupuesto por persona", 0, PRESUPUESTO_SIN_LIMITE, tuple(preferencias["presupuesto"]),
                            step=5, format="%d €", key="pref_presupuesto")
    if st.button("Guardar preferencias", width="stretch", key="guardar_preferencias"):
        try:
            BD.guardar_perfil(usuario, nombre, {"transporte": transporte, "tiempo": tiempo,
                                                "presupuesto": list(presupuesto)})
        except bd.ErrorSupabase:
            st.error("No se han podido guardar las preferencias ahora mismo (¿falta ejecutar "
                     "supabase/003_preferencias.sql?). Inténtalo en un momento.")
            return
        cargar_perfil.clear()
        for clave in ("transporte", "tiempo", "presupuesto"):   # el buscador arranca con las nuevas
            st.session_state.pop(clave, None)
        st.toast("Preferencias guardadas", icon=":material/check:")


MIS_VISITAS_EN_PERFIL = 10   # las más recientes, en el carrusel; el resto con "Ver lista completa"


def bloque_mis_visitas():
    """Perfil: los sitios que has marcado con "He ido", del más reciente al más antiguo."""
    st.subheader("Los restaurantes a los que has ido")
    try:
        df = amigos.cargar_mis_visitas(BD, usuario)
    except bd.ErrorSupabase:
        st.caption("No se pueden ver ahora mismo.")
        return
    abrir = st.session_state.pop("ficha_abrir", None)
    if df.empty:
        st.caption("Cuando marques «He ido» en la ficha de un restaurante, aparecerá aquí.")
        return
    ahora = datetime.now(timezone.utc)
    st.caption(f"{len(df)} restaurante{'s' if len(df) != 1 else ''}")
    # Las más recientes en carrusel (como "Tus amigos han ido a"); con "Ver lista completa", todas en lista.
    completa = st.session_state.get("mis_visitas_completa", False)
    mostrar_lista(df if completa else df.head(MIS_VISITAS_EN_PERFIL), key="lista_mis_visitas",
                  carrusel=not completa, extra=lambda f: {
                      "cuando": "Fuiste " + hace_cuanto(f["Fecha visita"], ahora), "visitado": False,
                      "nota": _o_none(f["Nota visita"]), "cita": _o_none(f["Comentario visita"])})
    if len(df) > MIS_VISITAS_EN_PERFIL:
        st.button("Ver menos" if completa else f"Ver lista completa ({len(df)})", width="stretch",
                  key="ver_mis_visitas", icon=":material/expand_less:" if completa else ":material/expand_more:",
                  on_click=lambda: st.session_state.update(mis_visitas_completa=not completa))
    coincide = df[df["ID"] == abrir]
    if abrir is not None and not coincide.empty:
        mostrar_ficha(coincide.iloc[0], pd.DataFrame(columns=bd.COLUMNAS_PLATOS))


def seccion_perfil(maestro, usuario=None, nombre=None, google=None, lista=None, preferencias=None, perfil=None):
    if not CONFIG_MULTIUSUARIO:   # modo local: no hay cuenta, solo las estadísticas de la lista
        st.header("Perfil")
        bloque_estadisticas(maestro)
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        if google.get("foto"):
            st.image(google["foto"], width=72)
        alias = (perfil or {}).get("alias")
        st.markdown(f"### {nombre}\n" + (f"**@{alias}**  \n" if alias else "") + usuario)
    with st.container(border=True):
        bloque_estadisticas(maestro)
    with st.container(border=True):
        bloque_mis_visitas()
    with st.container(border=True):
        amigos.bloque_amigos(BD, usuario, nombre, perfil, al_guardar_alias=cargar_perfil.clear,
                             mi_lista=maestro, mostrar_lista=mostrar_lista)
    with st.container(border=True):
        bloque_tus_listas(usuario, lista)
    with st.container(border=True):
        bloque_preferencias(usuario, nombre, preferencias)
    with st.container(border=True):
        bloque_datos_personales(usuario, nombre)
    st.button("Cerrar sesión", on_click=acceso.cerrar_sesion, args=(CUENTAS,), icon=":material/logout:",
              width="stretch", key="cerrar_sesion")


def pantalla_entrar(tras_intro):
    mostrar_portada(0, tras_intro=tras_intro, momento="🍽️ Tus sitios de Google Maps",
                    subtitulo="Entra para ver los restaurantes de tu lista.")
    st.button("Entrar con Google", type="primary", icon=":material/login:", width="stretch",
              on_click=st.login, args=("google",))
    if not confirmacion_de_correo_activa():
        st.caption("Las cuentas con correo y contraseña están desactivadas hasta que el administrador active "
                   "«Confirm email» en Supabase.")
        return
    st.markdown("<p style='text-align:center;opacity:.7;margin:.5rem 0'>o con tu correo</p>", unsafe_allow_html=True)
    acceso.formulario_cuentas(CUENTAS)


@st.cache_data(ttl=600, show_spinner=False)
def confirmacion_de_correo_activa():
    return CUENTAS.confirmacion_obligatoria()


def guardar_foto_de_google(usuario, nombre, perfil, google):
    """Guarda (una vez por visita) la foto de Google del usuario en su perfil, para que la vean sus amigos."""
    foto = bd.foto_valida(google.get("foto"))
    if not foto or (perfil or {}).get("foto") == foto or st.session_state.get("foto_guardada"):
        return
    st.session_state["foto_guardada"] = True
    try:
        BD.guardar_foto(usuario, nombre, foto)
        cargar_perfil.clear()
    except (bd.ErrorSupabase, ValueError):   # p. ej. aún no existe la columna (006_fotos_perfil.sql)
        pass


def pantalla_sin_permiso(usuario):
    st.warning(f"La cuenta {usuario} no tiene acceso a esta app. Pide al administrador que te añada.")
    st.button("Salir", on_click=st.logout)


st.set_page_config(page_title="¿Dónde comemos?", page_icon="🍽️", layout="centered")
st.html(_CSS_GLOBAL)
hay_intro = mostrar_intro()

usuario, mi_lista, cuenta = None, None, None
if CONFIG_MULTIUSUARIO:
    usuario = usuario_actual()
    if usuario is None:   # sin Google: ¿sesión con correo y contraseña (o guardada en la cookie)?
        cuenta = acceso.usuario_con_contrasena(CUENTAS)
        usuario = cuenta and cuenta["correo"]
    acceso.sincronizar_cookie()
    if usuario is None:
        pantalla_entrar(hay_intro)
        st.stop()
    if CONFIG_MULTIUSUARIO["permitidos"] and usuario not in CONFIG_MULTIUSUARIO["permitidos"]:
        pantalla_sin_permiso(usuario)
        st.stop()
    try:
        maestro, df_platos, mi_lista = cargar_datos_usuario(usuario)
    except bd.ErrorSupabase:
        st.error("No se ha podido cargar tu lista ahora mismo. Prueba a recargar la página en un momento.")
        st.stop()
else:
    maestro, df_platos = cargar_datos()

seccion = st.session_state.setdefault("seccion", "inicio")
conservar_formularios(seccion)

momento_portada = nombre_usuario = None
google, perfil = {}, None
if CONFIG_MULTIUSUARIO:
    google = datos_google() if cuenta is None else {"nombre": cuenta.get("nombre"), "foto": None}
    try:
        perfil = cargar_perfil(usuario)
    except bd.ErrorSupabase:   # p. ej. aún no se ha creado la tabla perfiles: se usa el nombre de Google
        perfil = None
    nombre_usuario = nombre_visible(usuario, perfil, google)
    guardar_foto_de_google(usuario, nombre_usuario, perfil, google)
    dueno = f"@{perfil['alias']}" if (perfil or {}).get("alias") else nombre_usuario   # sin @usuario aún: el nombre
    momento_portada = f"🍽️ Los restaurantes de {html.escape(dueno)} · {len(maestro)} sitios"
preferencias = bd.preferencias_validas((perfil or {}).get("preferencias"))
barra_secciones(seccion, google.get("foto"), amigos.solicitudes_pendientes(BD, usuario) if BD is not None else 0)

# Inicio, Mi lista y Perfil trabajan siempre con la lista del usuario; "Comer hoy" es lo de debajo.
if seccion == "inicio":
    seccion_inicio(maestro, df_platos, hay_intro, momento_portada, nombre_usuario)
    st.stop()
if seccion == "mi_lista":
    seccion_mi_lista(maestro, df_platos)
    st.stop()
if seccion == "perfil":
    seccion_perfil(maestro, usuario, nombre_usuario, google, mi_lista, preferencias, perfil)
    st.stop()

# ----------------------- COMER HOY: EL BUSCADOR ----------------------- #
if CONFIG_MULTIUSUARIO:
    if st.session_state.get("fuente") == FUENTE_TODOS:   # "Buscar en: Todos los restaurantes"
        try:
            maestro, df_platos = cargar_catalogo()
        except bd.ErrorSupabase:
            st.error("No se han podido cargar todos los restaurantes ahora mismo. Prueba en un momento.")
            st.stop()
        momento_portada = f"🍽️ Todos los restaurantes · {len(maestro)} sitios"

vista = st.session_state.setdefault("vista", "buscador")
if vista == "resultados" and st.session_state.get("resultado") is not None:
    st.html(_CSS_OCULTAR_BUSCADOR)

# ----------------------- VISTA: BUSCADOR ----------------------- #
with st.container(key="buscador"):
    mostrar_portada(len(maestro), tras_intro=hay_intro, maestro=maestro, momento=momento_portada)
    if CONFIG_MULTIUSUARIO:
        st.segmented_control("Buscar en", [FUENTE_MI_LISTA, FUENTE_TODOS], default=FUENTE_MI_LISTA,
                             key="fuente", width="stretch")
        if maestro.empty:
            st.info("Todavía no tienes restaurantes en tu lista. Añádela en tu **Perfil** (abajo a la derecha) "
                    "o busca en **Todos los restaurantes**.")
            st.button("Añadir tu lista", on_click=ir_a, args=("perfil",), icon=":material/add_location_alt:")
            st.stop()

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
        default=preferencias["transporte"], key="transporte", width="stretch",
    ) or "En coche"   # si se desmarca la opción elegida, vuelve a coche
    tiempo_maximo_min = st.slider("Tiempo máximo", 5, 60, preferencias["tiempo"], step=5, format="%d min",
                                  key="tiempo")

    cocina = st.selectbox("Cocina", ["Cualquiera"] + cocinas_disponibles(maestro), key="cocina")

    presupuesto_min, presupuesto_max = st.slider(
        "Presupuesto por persona", 0, PRESUPUESTO_SIN_LIMITE, tuple(preferencias["presupuesto"]), step=5,
        format="%d €", key="presupuesto",
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
    mostrar_lista(top, respuestas["modo_transporte"], seleccionado)

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
        mostrar_ficha(top.iloc[ids_top.index(abrir)], df_platos, respuestas["plato_deseado"],
                      respuestas["modo_transporte"])
