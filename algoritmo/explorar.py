"""
Buscar -> "Descubrir" (solo con cuentas): cualquier restaurante, bar o cafetería, aunque no esté en ninguna
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
from logica import PRESUPUESTO_SIN_LIMITE, filtrar_lista
from servicios import geocodificar_direccion, haversine_km

# Sin texto: lo que hay alrededor, ampliando si hay pocos. En el centro de Madrid caben ~400 sitios en 250 m y
# más de 1.000 (el tope de una consulta) en 500 m: si se pasa del tope llegan unos cualesquiera, no los más cercanos.
RADIOS_CERCA_KM = (0.25, 0.5, 1.5, 4)
RADIO_TEXTO_KM = 40      # con texto y ubicación: por nombre, en tu zona
POR_PAGINA = 15
CANDIDATOS = 1000        # se piden de sobra y luego se ordenan por distancia: si no, se cuelan sitios lejanos
MAX_RESULTADOS = 200
MAX_EN_MAPA = 50         # pines con foto; con más, el mapa los agrupa en burbujas con un número
RADIO_ZONA_KM = 1.0      # una zona (barrio, calle, pueblo): todo lo que hay en ~1 km alrededor
MAX_EN_ZONA = 3000       # en el centro de Madrid hay ~2.800 sitios en ese cuadrado
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
    if bd.texto_busqueda(texto):
        return _cliente.buscar_lugares(texto, cerca, radio_km=RADIO_TEXTO_KM, limite=CANDIDATOS if cerca else MAX_RESULTADOS)
    for radio in RADIOS_CERCA_KM:   # de cerca a lejos, hasta que haya bastantes
        lugares = _cliente.buscar_lugares("", cerca, radio_km=radio, limite=CANDIDATOS)
        if len(lugares) >= MAX_EN_MAPA:
            break
    return lugares


@st.cache_data(ttl=600, show_spinner=False)
def _en_zona(_cliente, texto, zona):
    return _cliente.buscar_lugares(texto, zona, radio_km=RADIO_ZONA_KM, limite=MAX_EN_ZONA)


@st.cache_data(ttl=600, show_spinner=False)
def _analizados(_cliente):
    return _cliente.lugares_analizados()


@st.cache_data(ttl=3600, show_spinner=False)
def _geocodificar(texto):
    lugar = geocodificar_direccion(texto)
    return (lugar.latitude, lugar.longitude) if lugar else None


def _elegir_zona(caja_zona):
    """La caja de zona (la de direcciones de Comer hoy). La zona elegida queda en session_state["ex_zona_elegida"] =
    (lat, lon, texto) y solo se recalcula cuando cambia lo escrito (eligiendo una sugerencia o pulsando Intro)."""
    antes = st.session_state.get("_texto_ex_zona", "")
    texto, sugerencia = caja_zona(key="ex_zona", disabled=False, placeholder="Zona: barrio, calle o pueblo", etiqueta="")
    if texto == antes:
        return st.session_state.get("ex_zona_elegida")
    st.session_state.pop("ex_visibles", None)
    st.session_state.pop("ex_zona_elegida", None)
    if sugerencia:
        st.session_state["ex_zona_elegida"] = (sugerencia["lat"], sugerencia["lon"], texto)
    elif texto.strip():
        try:
            punto = _geocodificar(texto.strip())
        except Exception:   # el servicio de direcciones no responde: no es lo mismo que "no existe"
            st.warning("No se ha podido buscar esa zona ahora mismo. Prueba en un momento.")
            return None
        if punto:
            st.session_state["ex_zona_elegida"] = (*punto, texto)
        else:
            st.warning("No encontramos esa zona. Prueba a elegir una de las sugerencias.")
    return st.session_state.get("ex_zona_elegida")


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


# Icono de cada sitio en la lista y en el mapa (no hay foto hasta que se analiza), según su categoría.
ICONOS = {
    "Japonesa": "🍣", "Sushi": "🍣", "Pizzería": "🍕", "Italiana": "🍝", "China": "🥡", "Asiática": "🥢",
    "Coreana": "🥢", "Tailandesa": "🍜", "Vietnamita": "🍜", "India": "🍛", "Mexicana": "🌮", "Peruana": "🐟",
    "Marisquería": "🦐", "Tapas": "🍤", "Española": "🥘", "Mediterránea": "🫒", "Hamburguesas": "🍔",
    "Comida rápida": "🍟", "Pollos": "🍗", "Asador": "🥩", "Brasa": "🥩", "Argentina": "🥩", "Kebab": "🥙",
    "Turca": "🥙", "Libanesa": "🥙", "Griega": "🥗", "Vegana": "🥗", "Vegetariana": "🥗", "Cafetería": "☕",
    "Desayunos y brunch": "🥞", "Panadería": "🥐", "Heladería": "🍦", "Postres": "🍰", "Bocadillos": "🥪",
    "Bar": "🍺", "Pub": "🍺", "Cervecería": "🍺", "Bar restaurante": "🍺", "Gastrobar": "🍷", "Vinoteca": "🍷",
    "Coctelería": "🍸",
}
VISTAS = ["Lista", "Mapa"]
ORDENES = ["Más cerca", "Mejor nota"]


def _nota(lugar):
    if not lugar.get("nota_google"):
        return ""
    return "★ " + f"{float(lugar['nota_google']):g}".replace(".", ",")


def _foto(cliente, lugar):
    """La foto pequeña de su ficha rápida (supabase/012_ficha_rapida.sql), o None."""
    return cliente.url_foto(lugar["foto"]) if lugar.get("foto") else None


def _por_nota(lugares):
    """Mejor nota de Google primero (los que aún no tienen, al final); a igualdad, el orden que traían."""
    return sorted(lugares, key=lambda l: -(l.get("nota_google") or 0))


def _icono(lugar):
    return ICONOS.get(lugar.get("categoria"), "🍽️")


def _visibles(lugares):
    """Sin los que se acaban de avisar como cerrados en esta visita (la búsqueda está en caché)."""
    ocultos = st.session_state.get("lugares_ocultos", ())
    return [l for l in lugares if l["id"] not in ocultos]


def _cocina(lugar):
    return lugar.get("cocina_google") or lugar.get("categoria") or ""


@st.cache_data(ttl=600, show_spinner=False)
def _catalogo(_cliente, ids):
    return _cliente.restaurantes_por_ids(ids)


def filtrar_lugares(lugares, catalogo=None, cocinas=(), presupuesto=(0, PRESUPUESTO_SIN_LIMITE), nota_min=0.0, plato=""):
    """Los filtros de Mi lista sobre los sitios de Descubrir. La cocina es la que se ve en la tarjeta. Precio y
    platos solo se saben de los analizados (`catalogo` = (maestro, df_platos) de sus restaurantes): con esos
    filtros puestos, los demás no salen; la nota, de su restaurante o, si no está analizado, de su ficha rápida."""
    if cocinas:
        lugares = [l for l in lugares if _cocina(l) in cocinas]
    solo_analizados = tuple(presupuesto) != (0, PRESUPUESTO_SIN_LIMITE) or bool(plato.strip())
    if not (solo_analizados or nota_min):
        return lugares
    buenos = set()
    if catalogo is not None and not catalogo[0].empty:
        tope = None if presupuesto[1] == PRESUPUESTO_SIN_LIMITE else presupuesto[1]
        buenos = set(filtrar_lista(catalogo[0], catalogo[1], "", (), presupuesto[0], tope, nota_min, plato)["ID"])

    def pasa(lugar):
        if lugar.get("restaurante_id"):
            return int(lugar["restaurante_id"]) in buenos
        return not solo_analizados and (lugar.get("nota_google") or 0) >= nota_min

    return [l for l in lugares if pasa(l)]


def _filtros(cliente, lugares):
    """El desplegable "Filtros" (como en Mi lista) y los sitios que lo cumplen."""
    estado, otra = st.session_state, {"on_change": st.session_state.pop, "args": ("ex_visibles", None)}
    sin_tope = (0, PRESUPUESTO_SIN_LIMITE)
    activos = sum([bool(estado.get("ex_cocinas")), bool(estado.get("ex_nota")), bool(estado.get("ex_plato", "").strip()),
                   tuple(estado.get("ex_presupuesto", sin_tope)) != sin_tope])
    with st.expander(f"Filtros ({activos})" if activos else "Filtros", icon=":material/tune:"):
        # las elegidas siguen en la lista aunque aquí no haya ninguna (si no, Streamlit las borraría)
        opciones = sorted({_cocina(l) for l in lugares} - {""} | set(estado.get("ex_cocinas", ())))
        cocinas = st.multiselect("Cocina", opciones, key="ex_cocinas", placeholder="Cualquiera", **otra)
        presupuesto = st.slider("Presupuesto por persona", 0, PRESUPUESTO_SIN_LIMITE, sin_tope, step=5,
                                format="%d €", key="ex_presupuesto", **otra)
        nota_min = st.slider("Nota mínima en Google", 0.0, 5.0, 0.0, step=0.5, format="%.1f ⭐", key="ex_nota", **otra)
        plato = st.text_input("Plato que destaquen", placeholder="ej. croquetas", key="ex_plato", **otra)
        st.caption("El precio y los platos solo se saben de los analizados.")
    catalogo = None
    if tuple(presupuesto) != sin_tope or plato.strip() or nota_min:
        ids = tuple(sorted({int(l["restaurante_id"]) for l in lugares if l.get("restaurante_id")}))
        if ids:
            catalogo = _catalogo(cliente, ids)
    return filtrar_lugares(lugares, catalogo, cocinas, presupuesto, nota_min, plato)


def _al_tocar(key, campo):
    """Al tocar un sitio en la lista (`abrir`) o en el mapa (`seleccion`): se abre su ventana."""
    lugar = st.session_state.get("ex_por_id", {}).get(getattr(st.session_state[key], campo, None))
    if lugar is not None:
        st.session_state["lugar_abrir"] = lugar


def _lista(cliente, lugares, cerca, key, lista):
    """Tarjetas (las mismas de Comer hoy): icono de su cocina, categoría, ciudad, distancia y estado."""
    st.session_state.setdefault("ex_por_id", {}).update({l["id"]: l for l in lugares})
    items = [{"id": l["id"], "n": n, "nombre": l["nombre"], "cocina": _cocina(l),
              "meta": " · ".join(t for t in (_nota(l), l.get("ciudad"), _distancia(l, cerca)) if t),
              "foto": _foto(cliente, l),
              "icono": _icono(l), "estado": _estado(l), "estado_texto": ESTADOS[_estado(l)][0]}
             for n, l in enumerate(lugares, start=1)]
    lista(items, key=key, al_abrir=lambda: _al_tocar(key, "abrir"))


def _mapa(cliente, lugares, tu, mapa):
    """Todos los sitios: con pocos, pines con foto; con muchos, puntos agrupados (verdes los analizados).
    `tu`: tu ubicación (punto azul), o None."""
    st.session_state.setdefault("ex_por_id", {}).update({l["id"]: l for l in lugares})
    agrupar = len(lugares) > MAX_EN_MAPA
    puntos = [{"id": l["id"], "n": n, "nombre": l["nombre"], "lat": l["lat"], "lon": l["lon"],
               "foto": None if agrupar else _foto(cliente, l), "icono": _icono(l), "estado": _estado(l)}
              for n, l in enumerate(lugares, start=1)]
    mapa(puntos, tu, key="mapa_explorar", al_tocar=lambda: _al_tocar("mapa_explorar", "seleccion"), agrupar=agrupar)
    st.caption(("🔵 Tú · " if tu else "") + "Toca un sitio para ver su ficha. "
               + ("En verde, los analizados; acércate para separar los grupos." if agrupar
                  else "Con borde verde, los analizados."))


def seccion(cliente, usuario, *, ficha, boton_ubicacion, caja_zona, lista, mapa):
    """`ficha(fila, df_platos)`: la ficha completa de un restaurante del catálogo (la de siempre).
    `boton_ubicacion(key)`: el botón "Usar mi ubicación" (comparte la ubicación con "Comer hoy").
    `caja_zona(key, disabled, placeholder)`: la caja de direcciones con sugerencias de Comer hoy.
    `lista(items, key, al_abrir)` y `mapa(puntos, centro, key, al_tocar, agrupar)`: los componentes de Comer hoy."""
    if cliente is None:   # solo hay "Descubrir" con cuentas de usuario
        return
    if (lugar := st.session_state.pop("lugar_abrir", None)) is not None:
        _ficha_lugar(cliente, usuario, lugar, ficha)

    texto = st.text_input("Buscar un restaurante", placeholder="Cualquier restaurante, bar o cafetería",
                          key="ex_texto", label_visibility="collapsed", icon=":material/search:",
                          on_change=st.session_state.pop, args=("ex_visibles", None))   # otra búsqueda: desde arriba
    zona = _elegir_zona(caja_zona)
    lectura = boton_ubicacion(key="ubicacion_explorar")
    if lectura.ubicacion:
        st.session_state["ubicacion_actual"] = (lectura.ubicacion["lat"], lectura.ubicacion["lon"])
    tu = st.session_state.get("ubicacion_actual")
    cerca = tuple(zona[:2]) if zona else tu   # desde dónde se mide la distancia: la zona, si hay, o tú
    if zona:
        st.caption(f"✓ En {texto_seguro(zona[2])} (lo que hay en ~1 km)")
    elif tu:
        st.caption("✓ Cerca de tu ubicación" + ("" if bd.texto_busqueda(texto) else " (lo que hay alrededor)"))

    try:
        if zona:
            lugares = _en_zona(cliente, texto, cerca)
        elif bd.texto_busqueda(texto) or tu:
            lugares = _buscar(cliente, texto, tuple(tu) if tu else None)
        else:   # sin buscar nada: el mapa de los ya analizados
            lugares = _filtros(cliente, _visibles(_analizados(cliente)))
            st.caption("Escribe un nombre, una zona o usa tu ubicación para ver todos los sitios. En el mapa, los "
                       f"**{len(lugares)} ya analizados** (con ficha completa); los demás puedes pedir que se analicen.")
            if lugares:
                _mapa(cliente, lugares, None, mapa)
            return
    except bd.ErrorSupabase:
        st.warning(FALTA_TABLA)
        return
    lugares = _visibles(_ordenar(lugares, cerca))
    if not lugares:
        st.info("No hemos encontrado nada así" + (" por aquí." if cerca else ". Prueba con otro nombre o usa tu ubicación."))
        return
    lugares = _filtros(cliente, lugares)
    if not lugares:
        st.info("Ninguno cumple esos filtros.")
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        vista = st.segmented_control("Vista", VISTAS, default="Lista", key="ex_vista", label_visibility="collapsed")
        if st.toggle("Solo analizados", key="ex_solo_analizados", on_change=st.session_state.pop, args=("ex_visibles", None)):
            lugares = [l for l in lugares if _estado(l) == "analizado"]
        st.caption(f"{len(lugares)} sitio{'s' if len(lugares) != 1 else ''}")
    if not lugares:
        st.info("Aún no hay ninguno analizado por aquí.")
        return
    if any(l.get("nota_google") for l in lugares):   # con la ficha rápida se puede ordenar por la nota de Google
        orden = st.segmented_control("Orden", ORDENES, default=ORDENES[0], key="ex_orden", label_visibility="collapsed",
                                     on_change=st.session_state.pop, args=("ex_visibles", None))
        if orden == "Mejor nota" or not cerca:
            lugares = _por_nota(lugares)
    if vista == "Mapa":
        _mapa(cliente, lugares, tu, mapa)
        return
    lugares = lugares[:MAX_RESULTADOS]
    visibles = st.session_state.get("ex_visibles", POR_PAGINA)
    _lista(cliente, lugares[:visibles], cerca, "lista_explorar", lista)
    if len(lugares) > visibles:
        st.button("Ver más", key="ex_ver_mas", width="stretch",
                  on_click=st.session_state.update, args=({"ex_visibles": visibles + POR_PAGINA},))
