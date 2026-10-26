"""
Amigos: el bloque "Amigos" del Perfil (cifras, solicitudes, tus amigos en una fila de círculos con su
mini perfil, tu @usuario y el buscador) y los datos de "Tus amigos han ido a" de Inicio. Los correos de
los demás nunca se enseñan: solo nombre, @usuario y la foto de Google si la tienen.
"""

import html
import re
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

import datos as bd
from logica import cocina_favorita, compatibilidad, en_comun, hace_cuanto

_COMPONENTES = Path(__file__).resolve().parent / "componentes"
_BUSCADOR = {n: (_COMPONENTES / f"buscador_amigos.{n}").read_text(encoding="utf-8") for n in ("html", "css", "js")}
_LISTA = {n: (_COMPONENTES / f"lista_amigos.{n}").read_text(encoding="utf-8") for n in ("html", "css", "js")}

# Colores de los avatares sin foto (siempre el mismo para cada persona); todos con texto blanco legible.
PALETA = ["#C2410C", "#0F766E", "#7C3AED", "#BE185D", "#1D4ED8", "#15803D", "#B45309", "#475569"]
DIAS_ACTIVIDAD = 30              # "visitas de tus amigos en los últimos 30 días"
EN_MINI_PERFIL = 10              # tarjetas de cada carrusel del mini perfil de un amigo


def texto_seguro(texto):
    """Nombre de otra persona dentro de st.markdown: sin que pueda meter enlaces, imágenes ni formato."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|~<>])", r"\\\1", str(texto or ""))


def quien(relacion):
    nombre = texto_seguro(relacion.get("nombre") or relacion.get("alias") or "Alguien")
    return f"**{nombre}** · @{relacion['alias']}" if relacion.get("alias") else f"**{nombre}**"


def etiqueta_amigo(relacion):
    """Texto plano (para un desplegable): "Nombre · @usuario"."""
    nombre = relacion.get("nombre") or relacion.get("alias") or "Alguien"
    return f"{nombre} · @{relacion['alias']}" if relacion.get("alias") else nombre


def _nombre(p):
    return p.get("nombre") or p.get("alias") or "Alguien"


def _color(p):
    return PALETA[zlib.crc32(str(p.get("alias") or p.get("usuario") or "").encode()) % len(PALETA)]


def datos_avatar(p):
    """Lo que necesita un avatar en el navegador: inicial, color y foto (si es válida)."""
    return {"inicial": _nombre(p)[:1].upper(), "color": _color(p), "foto": bd.foto_valida(p.get("foto"))}


def avatar_html(p, tam=48):
    """Círculo con la foto de Google de la persona o, si no tiene, su inicial sobre su color."""
    foto = bd.foto_valida(p.get("foto"))
    dentro = html.escape(_nombre(p)[:1].upper())
    if foto:
        dentro += f'<img src="{html.escape(foto)}" alt="" referrerpolicy="no-referrer">'
    return (f'<span class="avatar-amigo" aria-hidden="true" style="width:{tam}px;height:{tam}px;'
            f'font-size:{round(tam * 0.42)}px;background:{_color(p)}">{dentro}</span>')


# ---------------------------------------------------------------- datos (con caché)

@st.cache_data(ttl=60, show_spinner=False)
def cargar_relaciones(_bd, usuario):
    return _bd.relaciones_de(usuario)


DIAS_VISITAS_AMIGOS = 14   # Inicio enseña lo que han hecho tus amigos en las dos últimas semanas


@st.cache_data(ttl=60, show_spinner=False)
def cargar_visitas_amigos(_bd, usuario, limite=50):
    """Visitas de los amigos de las dos últimas semanas (DataFrame como el maestro, ver
    datos.visitas_a_dataframe), o None si todavía no tiene amigos."""
    amigos = [r for r in cargar_relaciones(_bd, usuario) if r["estado"] == "aceptada"]
    if not amigos:
        return None
    nombres = {a["usuario"]: a["nombre"] or a["alias"] or "Un amigo" for a in amigos}
    desde = datetime.now(timezone.utc) - timedelta(days=DIAS_VISITAS_AMIGOS)
    return bd.visitas_a_dataframe(_bd.visitas_de(list(nombres), limite, desde=desde), nombres)


@st.cache_data(ttl=60, show_spinner=False)
def cargar_directorio(_bd, usuario):
    return _bd.directorio(excepto=usuario)


@st.cache_data(ttl=300, show_spinner=False)
def cargar_mis_visitas(_bd, usuario):
    """Tus valoraciones de "He ido" (DataFrame como el maestro, ver datos.visitas_a_dataframe)."""
    return bd.visitas_a_dataframe(_bd.visitas_de([usuario], limite=1000), {usuario: "Tú"})


@st.cache_data(ttl=300, show_spinner=False)
def cargar_lista_de(_bd, usuario):
    """La lista de restaurantes de otra persona (solo se usa para comparar: en común, cocina favorita...)."""
    return _bd.restaurantes_de(usuario)[0]


@st.cache_data(ttl=300, show_spinner=False)
def cargar_valoraciones_de(_bd, usuario, nombre):
    return bd.visitas_a_dataframe(_bd.visitas_de([usuario], limite=1000), {usuario: nombre})


@st.cache_data(ttl=300, show_spinner=False)
def cargar_actividad(_bd, usuarios):
    """Nº de visitas de esos usuarios en los últimos DIAS_ACTIVIDAD días."""
    desde = datetime.now(timezone.utc) - timedelta(days=DIAS_ACTIVIDAD)
    return len(_bd.visitas_de(list(usuarios), limite=1000, desde=desde))


def limpiar_cache():
    for funcion in (cargar_relaciones, cargar_visitas_amigos, cargar_mis_visitas, cargar_valoraciones_de,
                    cargar_actividad):
        funcion.clear()


def _ids(df):
    return set(df["ID"]) if not df.empty else set()


def _notas(df):
    """{id del restaurante: nota} de las valoraciones con nota."""
    if df.empty:
        return {}
    return {int(f["ID"]): float(f["Nota visita"]) for _, f in df.iterrows() if pd.notna(f["Nota visita"])}


def _accion(funcion, *args, **kwargs):
    """Callback de los botones de amigos: hace el cambio y refresca la caché; si falla, lo apunta."""
    try:
        funcion(*args, **kwargs)
    except (bd.ErrorSupabase, ValueError):
        st.session_state["error_amigos"] = "No se ha podido hacer ahora mismo. Inténtalo en un momento."
    limpiar_cache()


def solicitudes_pendientes(cliente, usuario):
    """Nº de solicitudes de amistad que esperan respuesta (para el globito de la barra de abajo)."""
    try:
        return sum(1 for r in cargar_relaciones(cliente, usuario) if r["estado"] == "pendiente" and not r["enviada"])
    except bd.ErrorSupabase:
        return 0


# ---------------------------------------------------------------- el bloque del Perfil

def bloque_amigos(cliente, usuario, nombre, perfil, al_guardar_alias, mi_lista, mostrar_lista):
    """La página de tus amigos (al tocar "amigos" en la cabecera del Perfil): solicitudes, cifras y el listado; al
    tocar uno, su mini perfil. `mi_lista`: tu lista (DataFrame), para comparar. `mostrar_lista`: la función de
    app.py que dibuja tarjetas de restaurantes (en el mini perfil). Buscar gente está en Buscar -> Personas."""
    st.subheader("Amigos")
    alias = (perfil or {}).get("alias")
    if not alias:
        _elegir_alias(cliente, usuario, nombre, al_guardar_alias)
        return
    if st.session_state.get("error_amigos"):
        st.error(st.session_state.pop("error_amigos"))
    try:
        relaciones = cargar_relaciones(cliente, usuario)
    except bd.ErrorSupabase:
        st.error("No se pueden cargar tus amigos ahora mismo (¿falta ejecutar supabase/004_amigos.sql?).")
        return
    amigos = [r for r in relaciones if r["estado"] == "aceptada"]

    _solicitudes(cliente, usuario, [r for r in relaciones if r["estado"] == "pendiente" and not r["enviada"]])
    listas, mis_valoraciones = {}, pd.DataFrame()
    try:
        listas = {a["usuario"]: cargar_lista_de(cliente, a["usuario"]) for a in amigos}
        mis_valoraciones = cargar_mis_visitas(cliente, usuario)
        _lista_de_amigos(amigos)
        _cifras(cliente, amigos, mi_lista, listas)
    except bd.ErrorSupabase:
        st.caption("No se pueden ver los datos de tus amigos ahora mismo.")

    for r in [r for r in relaciones if r["estado"] == "pendiente" and r["enviada"]]:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(f"Solicitud enviada a {quien(r)}")
            st.button("Cancelar", type="tertiary", key=f"cancelar_{r['alias'] or r['usuario']}",
                      on_click=_accion, args=(cliente.quitar_amistad, usuario, r["usuario"]))

    st.caption(f"Tu nombre de usuario es **@{alias}**: dáselo a tus amigos para que te encuentren. Para añadir "
               "a alguien, búscalo en **Buscar → Personas**.")

    abierto = st.session_state.pop("amigo_abierto", None)
    elegido = next((a for a in amigos if (a["alias"] or a["usuario"]) == abierto), None)
    if elegido is not None and elegido["usuario"] in listas:
        _mini_perfil(cliente, usuario, elegido, mi_lista, listas[elegido["usuario"]], mis_valoraciones, mostrar_lista)


def _solicitudes(cliente, usuario, recibidas):
    """Solicitudes recibidas, destacadas arriba en una tarjeta de color con avatar y botones grandes."""
    for r in recibidas:
        clave = r["alias"] or r["usuario"]
        with st.container(border=True, key=f"solicitud_{re.sub(r'[^a-z0-9_]', '_', clave.lower())}"):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.html(avatar_html(r, 48), width="content")
                st.markdown(f"{quien(r)}  \nquiere ser tu amigo")
            with st.container(horizontal=True):
                st.button("Aceptar", type="primary", icon=":material/check:", width="stretch", key=f"aceptar_{clave}",
                          on_click=_accion, args=(cliente.responder_solicitud, usuario, r["usuario"], True))
                st.button("Rechazar", icon=":material/close:", width="stretch", key=f"rechazar_{clave}",
                          on_click=_accion, args=(cliente.responder_solicitud, usuario, r["usuario"], False))


def _cifras(cliente, amigos, mi_lista, listas):
    """Visitas de tus amigos en los últimos 30 días · sitios de tu lista que también tiene algún amigo."""
    comunes = set().union(*(en_comun(mi_lista, lista) for lista in listas.values()))
    visitas = cargar_actividad(cliente, tuple(sorted(a["usuario"] for a in amigos))) if amigos else 0
    if amigos:   # el nº de amigos ya está arriba, en la cabecera del Perfil
        st.caption(f"Tus amigos han ido a {visitas} sitio{'s' if visitas != 1 else ''} en los últimos {DIAS_ACTIVIDAD} "
                   f"días · {len(comunes)} sitio{'s' if len(comunes) != 1 else ''} de tu lista los tiene también algún amigo")


def _al_tocar_amigo():
    clave = st.session_state["lista_amigos"].abrir
    if clave:
        st.session_state["amigo_abierto"] = clave


def _lista_de_amigos(amigos):
    """Tus amigos como la lista de seguidores de Instagram: buscador arriba y una fila por amigo (foto, @usuario
    y nombre); toda la fila se toca para abrir su mini perfil. Al navegador no le llegan correos."""
    if not amigos:
        st.caption("Todavía no tienes amigos: búscalos en **Buscar → Personas** por su nombre o @usuario.")
        return
    personas = [{"clave": a["alias"] or a["usuario"], "alias": a.get("alias"), "nombre": _nombre(a), **datos_avatar(a)}
                for a in sorted(amigos, key=lambda a: (a.get("alias") or _nombre(a)).lower())]
    st.components.v2.component("lista_amigos", **_LISTA)(
        key="lista_amigos", data={"personas": personas}, on_abrir_change=_al_tocar_amigo)


def _mini_perfil(cliente, usuario, amigo, mi_lista, su_lista, mis_valoraciones, mostrar_lista):
    """Ventana con lo que hace un amigo: compatibilidad, cifras, sus últimas valoraciones y lo que tenéis en común."""
    nombre = _nombre(amigo)

    @st.dialog(nombre, width="medium")
    def _ventana():
        valoraciones = cargar_valoraciones_de(cliente, amigo["usuario"], nombre)
        sus_notas = _notas(valoraciones)
        afinidad = compatibilidad(mi_lista, su_lista, _notas(mis_valoraciones), sus_notas)
        with st.container(horizontal=True, vertical_alignment="center"):
            st.html(avatar_html(amigo, 72), width="content")
            st.markdown((f"@{amigo['alias']}  \n" if amigo.get("alias") else "")
                        + (f"**🤝 {afinidad} % de gustos en común**" if afinidad is not None else ""))

        with st.container(horizontal=True):
            st.metric("Nota media", f"{sum(sus_notas.values()) / len(sus_notas):.1f} ★".replace(".", ",")
                      if sus_notas else "–")
            st.metric("Ha ido a", len(valoraciones))
        favorita = cocina_favorita(su_lista)
        if favorita:   # como texto: con st.metric, un nombre largo ("Tapas y raciones") sale enorme
            st.markdown(f"🍽️ Cocina favorita: **{texto_seguro(favorita)}**")

        ahora = datetime.now(timezone.utc)
        st.markdown("**Sus últimas valoraciones**")
        if valoraciones.empty:
            st.caption("Todavía no ha marcado ningún sitio con «He ido».")
        else:
            mostrar_lista(valoraciones.head(EN_MINI_PERFIL), key="lista_amigo_valoraciones",
                          carrusel=True, estatica=True, extra=lambda f: {
                              "cuando": hace_cuanto(f["Fecha visita"], ahora), "visitado": False,
                              "nota": None if pd.isna(f["Nota visita"]) else float(f["Nota visita"]),
                              "cita": None if pd.isna(f["Comentario visita"]) else f["Comentario visita"]})

        comunes = en_comun(mi_lista, su_lista)
        idos_los_dos = _ids(mis_valoraciones) & _ids(valoraciones)
        st.markdown(f"**En común** · {len(comunes)} restaurante{'s' if len(comunes) != 1 else ''} en vuestras listas"
                    + (f" · habéis ido los dos a {len(idos_los_dos)}" if idos_los_dos else ""))
        if comunes:
            mostrar_lista(mi_lista[mi_lista["ID"].isin(comunes)].head(EN_MINI_PERFIL),
                          key="lista_amigo_comunes", carrusel=True, estatica=True)

        if st.button("Quitar de amigos", type="tertiary", icon=":material/person_remove:", key="quitar_amigo"):
            _accion(cliente.quitar_amistad, usuario, amigo["usuario"])
            st.rerun()   # cierra la ventana

    _ventana()


def _elegir_alias(cliente, usuario, nombre, al_guardar_alias):
    st.caption("Elige un nombre de usuario para que tus amigos te encuentren. Tu correo no lo ve nadie.")
    nuevo = st.text_input("Nombre de usuario", placeholder="ej. ana_g", max_chars=21, key="alias_nuevo")
    if st.button("Guardar nombre de usuario", width="stretch", key="guardar_alias"):
        try:
            cliente.guardar_alias(usuario, nombre, bd.validar_alias(nuevo))
        except ValueError as e:
            st.error(str(e))
            return
        except bd.ErrorSupabase:
            st.error("No se ha podido guardar ahora mismo (¿falta ejecutar supabase/004_amigos.sql?).")
            return
        al_guardar_alias()
        st.rerun()


def buscador_de_personas(cliente, usuario, nombre, perfil, al_guardar_alias):
    """Buscar -> Personas: buscar gente registrada por su nombre o @usuario y añadirla. Si aún no tienes @usuario,
    se pide aquí también (sin él no te pueden encontrar)."""
    if not (perfil or {}).get("alias"):
        _elegir_alias(cliente, usuario, nombre, al_guardar_alias)
        st.divider()
    if st.session_state.get("error_amigos"):
        st.error(st.session_state.pop("error_amigos"))
    try:
        relaciones = cargar_relaciones(cliente, usuario)
    except bd.ErrorSupabase:
        st.error("No se puede buscar ahora mismo (¿falta ejecutar supabase/004_amigos.sql?).")
        return
    _buscar_amigos(cliente, usuario, {r["usuario"]: r for r in relaciones})


def _buscar_amigos(cliente, usuario, conocidos):
    """Buscador propio: al escribir, salen las personas de la base de datos cuyo nombre o @usuario coincide (lo
    filtra el navegador, al momento). Al navegador solo le llegan nombre y @usuario; "Añadir" devuelve el
    @usuario y aquí se busca a quién corresponde."""
    try:
        directorio = cargar_directorio(cliente, usuario)
    except bd.ErrorSupabase:
        st.error("No se puede buscar ahora mismo. Inténtalo en un momento.")
        return
    if not directorio:
        st.caption("Todavía no hay nadie más con nombre de usuario para añadir.")
        return
    por_alias = {p["alias"]: p for p in directorio}
    personas = []
    for p in directorio:
        relacion = conocidos.get(p["usuario"])
        estado = "nuevo" if relacion is None else ("amigo" if relacion["estado"] == "aceptada" else "pendiente")
        personas.append({"alias": p["alias"], "nombre": _nombre(p), "inicial": _nombre(p)[:1].upper(),
                         "color": _color(p), "estado": estado})
    st.components.v2.component("buscador_amigos", **_BUSCADOR)(
        key="buscador_amigos", data={"personas": personas},
        on_anadir_change=lambda: solicitar_por_alias(cliente, usuario, st.session_state["buscador_amigos"].anadir,
                                                     por_alias))


def solicitar_por_alias(cliente, usuario, alias, por_alias):
    """"Añadir" del buscador: el navegador solo manda un @usuario; si no es de nadie del directorio, no se hace nada."""
    persona = por_alias.get(alias) if alias else None
    if persona is not None:
        _accion(cliente.solicitar_amistad, usuario, persona["usuario"])
