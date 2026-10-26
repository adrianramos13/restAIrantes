"""
Explorar (a la derecha de Inicio en la barra): cualquier restaurante, bar o cafetería, aunque no esté en ninguna
lista. Los sitios salen de la tabla lugares (datos abiertos de Overture Maps, ver
obtener_datos/importar_overture.py). Un sitio "analizado" ya está en el catálogo y se abre su ficha completa
(nota, lo que destacan, eatlist, He ido...); si no, se ve lo básico y se puede pedir que se analice: el
procesador (obtener_datos/procesar_solicitudes.py --vigilar, que corre solo en el ordenador del dueño) saca sus
reseñas de Google Maps y lo clasifica con Jev en unos minutos. Los que han cerrado no salen (estado "cerrado": lo comprueba solo
obtener_datos/verificar_lugares.py, o lo avisa cualquiera con "¿Ha cerrado?").
"""

import urllib.parse

import streamlit as st

import datos as bd
from amigos import texto_seguro
from servicios import haversine_km

RADIO_CERCA_KM = 1.5     # sin texto: lo que hay alrededor
RADIO_TEXTO_KM = 40      # con texto y ubicación: por nombre, en tu zona
POR_PAGINA = 15
ESTADOS = {   # estado_analisis -> (texto, color, icono)
    "analizado": ("Analizado", "green", ":material/verified:"),
    "pendiente": ("Análisis en camino", "orange", ":material/hourglass_top:"),
    "procesando": ("Análisis en camino", "orange", ":material/hourglass_top:"),
    "error": ("No se pudo analizar", "red", ":material/error:"),
    "sin_analizar": ("Datos básicos", "gray", ":material/info:"),
    "cerrado": ("Ha cerrado", "red", ":material/block:"),
}
SEGUNDOS_ENTRE_COMPROBACIONES = 5   # mientras se analiza, cada cuánto mira la ventana si ya está
FALTA_TABLA = "Explorar aún no está activado: falta ejecutar `supabase/009_lugares.sql` e importar una zona."


@st.cache_data(ttl=600, show_spinner=False)
def _buscar(_cliente, texto, cerca):
    radio = RADIO_TEXTO_KM if bd.texto_busqueda(texto) else RADIO_CERCA_KM
    return _cliente.buscar_lugares(texto, cerca, radio_km=radio)


@st.cache_data(ttl=600, show_spinner=False)
def _restaurante(_cliente, restaurante_id):
    return _cliente.restaurantes_por_ids([restaurante_id])


def _estado(lugar):
    """El de la base de datos, salvo que lo acabes de pedir en esta sesión (aún no se ha vuelto a leer)."""
    estado = lugar.get("estado_analisis") or "sin_analizar"
    if lugar["id"] in st.session_state.get("lugares_pedidos", ()) and estado in ("sin_analizar", "error"):
        return "pendiente"
    return estado


def _distancia(lugar, cerca):
    if not cerca:
        return ""
    km = haversine_km(cerca[0], cerca[1], lugar["lat"], lugar["lon"])
    return f"{km * 1000:.0f} m" if km < 1 else f"{km:.1f} km".replace(".", ",")


def _ordenar(lugares, cerca):
    return sorted(lugares, key=lambda l: haversine_km(cerca[0], cerca[1], l["lat"], l["lon"])) if cerca else lugares


def _url_segura(url):
    """Webs de Overture: solo http(s) (vienen de fuera, no se abre cualquier esquema)."""
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else None


def _pedir(cliente, usuario, lugar):
    try:
        cliente.pedir_analisis(usuario, lugar["id"])
    except bd.ErrorSupabase:
        st.toast("No se ha podido pedir ahora mismo. Inténtalo en un momento.", icon=":material/error:")
        return
    st.session_state.setdefault("lugares_pedidos", set()).add(lugar["id"])
    _buscar.clear()
    st.toast("¡Pedido! En un par de minutos tendrá su ficha completa.", icon=":material/hourglass_top:")


def _avisar_cerrado(cliente, lugar):
    try:
        cliente.avisar_cerrado(lugar["id"])
    except bd.ErrorSupabase:
        st.toast("No se ha podido guardar ahora mismo. Inténtalo en un momento.", icon=":material/error:")
        return
    st.session_state.setdefault("lugares_ocultos", set()).add(lugar["id"])
    _buscar.clear()
    st.toast("Gracias: ya no saldrá en Explorar.", icon=":material/check:")


@st.fragment(run_every=SEGUNDOS_ENTRE_COMPROBACIONES)
def _esperar_analisis(cliente, lugar):
    """Mientras se analiza: mira si ya está y, en cuanto lo está, vuelve a abrir la ventana con el resultado
    (la ficha completa, o por qué no se ha podido). Así no hay que cerrarla y volver más tarde."""
    try:
        ahora = cliente.lugar_por_id(lugar["id"])
    except bd.ErrorSupabase:
        ahora = None
    if ahora and ahora.get("estado_analisis") not in ("pendiente", "procesando"):
        st.session_state.get("lugares_pedidos", set()).discard(lugar["id"])
        _buscar.clear()
        st.session_state["lugar_abrir"] = ahora
        st.rerun()
    st.info("Analizando (nota, precio, foto y lo que dicen sus reseñas). Suele tardar uno o dos minutos: "
            "esta ventana se actualiza sola.", icon=":material/hourglass_top:")


def _ficha_lugar(cliente, usuario, lugar, ficha):
    """Ventana de un sitio: su ficha completa si está analizado; si no, lo básico y "Analizar"."""

    @st.dialog(str(lugar["nombre"]), width="medium")
    def _ventana():
        if lugar.get("restaurante_id"):
            try:
                maestro, platos = _restaurante(cliente, int(lugar["restaurante_id"]))
            except bd.ErrorSupabase:
                maestro = None
            if maestro is not None and not maestro.empty:
                ficha(maestro.iloc[0], platos)
                return
        estado = _estado(lugar)
        texto, color, icono = ESTADOS.get(estado, ESTADOS["sin_analizar"])
        st.badge(texto, icon=icono, color=color)
        st.markdown("  \n".join(texto_seguro(t) for t in (lugar.get("categoria"), lugar.get("direccion"),
                                                          lugar.get("ciudad")) if t))
        with st.container(horizontal=True):
            consulta = urllib.parse.quote(f"{lugar['nombre']} {lugar['lat']},{lugar['lon']}")
            st.link_button("Google Maps", f"https://www.google.com/maps/search/?api=1&query={consulta}",
                           icon=":material/map:")
            if _url_segura(lugar.get("web")):
                st.link_button("Web", lugar["web"], icon=":material/language:")
        if lugar.get("telefono"):
            st.caption(f"Teléfono: {texto_seguro(lugar['telefono'])}")
        if lugar["id"] in st.session_state.get("lugares_ocultos", ()):
            st.success("Gracias por avisar: ya no sale en Explorar.")
            return
        if estado == "cerrado":
            st.warning("Según Google Maps ha cerrado, así que ya no sale en Explorar.")
            return
        if estado in ("pendiente", "procesando"):
            _esperar_analisis(cliente, lugar)
        else:
            st.caption("Aún no sabemos qué dicen sus reseñas. Al analizarlo tendrá su ficha completa (nota, precio, "
                       "lo que destacan) y podrás añadirlo a tu eatlist o marcar «He ido».")
            st.button("Analizar este restaurante", type="primary", icon=":material/auto_awesome:", width="stretch",
                      key="analizar_lugar", on_click=_pedir, args=(cliente, usuario, lugar))
        st.button("¿Ha cerrado? Avísanos", type="tertiary", icon=":material/storefront:", key="avisar_cerrado",
                  help="Deja de salir en Explorar para todos", on_click=_avisar_cerrado, args=(cliente, lugar))

    _ventana()


def _tarjetas(lugares, cerca, prefijo):
    ocultos = st.session_state.get("lugares_ocultos", ())   # avisados como cerrados en esta visita
    for i, lugar in enumerate(l for l in lugares if l["id"] not in ocultos):
        texto, color, _ = ESTADOS.get(_estado(lugar), ESTADOS["sin_analizar"])
        detalle = " · ".join(t for t in (lugar.get("categoria"), lugar.get("ciudad"), _distancia(lugar, cerca)) if t)
        with st.container(border=True, horizontal=True, vertical_alignment="center", key=f"{prefijo}_{i}"):
            st.markdown(f"**{texto_seguro(lugar['nombre'])}**  \n{texto_seguro(detalle)}  \n:{color}-badge[{texto}]")
            st.button("Ver", key=f"{prefijo}_ver_{i}", type="tertiary", icon=":material/chevron_right:",
                      on_click=st.session_state.update, args=({"lugar_abrir": lugar},))


def _tus_peticiones(cliente, usuario, cerca):
    try:
        pedidas = cliente.solicitudes_de(usuario)
    except bd.ErrorSupabase:
        return
    lugares = [p["lugares"] for p in pedidas if p.get("lugares")]
    if lugares:
        st.subheader("Has pedido analizar")
        _tarjetas(lugares, cerca, "pedido")


def seccion(cliente, usuario, *, ficha, boton_ubicacion):
    """`ficha(fila, df_platos)`: la ficha completa de un restaurante del catálogo (la de siempre).
    `boton_ubicacion(key)`: el botón "Usar mi ubicación" (comparte la ubicación con "Comer hoy")."""
    st.header("Explorar")
    if cliente is None:
        st.info("Explorar está disponible en el modo con cuentas de usuario.")
        return
    if (lugar := st.session_state.pop("lugar_abrir", None)) is not None:
        _ficha_lugar(cliente, usuario, lugar, ficha)

    texto = st.text_input("Buscar un restaurante", placeholder="Cualquier restaurante, bar o cafetería",
                          key="ex_texto", label_visibility="collapsed", icon=":material/search:",
                          on_change=st.session_state.pop, args=("ex_visibles", None))   # otra búsqueda: desde arriba
    lectura = boton_ubicacion(key="ubicacion_explorar")
    if lectura.ubicacion:
        st.session_state["ubicacion_actual"] = (lectura.ubicacion["lat"], lectura.ubicacion["lon"])
    cerca = st.session_state.get("ubicacion_actual")
    if cerca:
        st.caption("✓ Cerca de tu ubicación" + ("" if bd.texto_busqueda(texto) else " (lo que hay alrededor)"))

    if not bd.texto_busqueda(texto) and not cerca:
        st.caption("Escribe un nombre o usa tu ubicación para ver lo que hay cerca. Los sitios **analizados** "
                   "tienen ficha completa; los demás puedes pedir que se analicen.")
        _tus_peticiones(cliente, usuario, cerca)
        return
    try:
        lugares = _ordenar(_buscar(cliente, texto, tuple(cerca) if cerca else None), cerca)
    except bd.ErrorSupabase:
        st.warning(FALTA_TABLA)
        return
    if not lugares:
        st.info("No hemos encontrado nada así" + (" por aquí." if cerca else ". Prueba con otro nombre o usa tu ubicación."))
        return
    visibles = st.session_state.get("ex_visibles", POR_PAGINA)
    st.caption(f"{len(lugares)}{'+' if len(lugares) >= 200 else ''} sitio{'s' if len(lugares) != 1 else ''}")
    _tarjetas(lugares[:visibles], cerca, "lugar")
    if len(lugares) > visibles:
        st.button("Ver más", key="ex_ver_mas", width="stretch",
                  on_click=st.session_state.update, args=({"ex_visibles": visibles + POR_PAGINA},))
