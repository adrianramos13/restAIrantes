"""
Amigos: el bloque "Amigos" del Perfil (tu @usuario, buscar gente, solicitudes y amigos) y los datos de
"Tus amigos han ido a" de Inicio. Los correos de los demás nunca se enseñan: solo nombre y @usuario.
"""

import re

import streamlit as st

import datos as bd


def texto_seguro(texto):
    """Nombre de otra persona dentro de st.markdown: sin que pueda meter enlaces, imágenes ni formato."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|~<>])", r"\\\1", str(texto or ""))


def quien(relacion):
    nombre = texto_seguro(relacion.get("nombre") or relacion.get("alias") or "Alguien")
    return f"**{nombre}** · @{relacion['alias']}" if relacion.get("alias") else f"**{nombre}**"


@st.cache_data(ttl=60, show_spinner=False)
def cargar_relaciones(_bd, usuario):
    return _bd.relaciones_de(usuario)


@st.cache_data(ttl=60, show_spinner=False)
def cargar_visitas_amigos(_bd, usuario, limite=10):
    """Últimas visitas de los amigos (DataFrame como el maestro, ver datos.visitas_a_dataframe), o None
    si todavía no tiene amigos."""
    amigos = [r for r in cargar_relaciones(_bd, usuario) if r["estado"] == "aceptada"]
    if not amigos:
        return None
    nombres = {a["usuario"]: a["nombre"] or a["alias"] or "Un amigo" for a in amigos}
    return bd.visitas_a_dataframe(_bd.visitas_de(list(nombres), limite), nombres)


@st.cache_data(ttl=60, show_spinner=False)
def cargar_directorio(_bd, usuario):
    return _bd.directorio(excepto=usuario)


def limpiar_cache():
    cargar_relaciones.clear()
    cargar_visitas_amigos.clear()


def _accion(funcion, *args, **kwargs):
    """Callback de los botones de amigos: hace el cambio y refresca la caché; si falla, lo apunta."""
    try:
        funcion(*args, **kwargs)
    except (bd.ErrorSupabase, ValueError):
        st.session_state["error_amigos"] = "No se ha podido hacer ahora mismo. Inténtalo en un momento."
    limpiar_cache()


def bloque_amigos(cliente, usuario, nombre, perfil, al_guardar_alias):
    st.subheader("Amigos")
    alias = (perfil or {}).get("alias")
    if not alias:
        _elegir_alias(cliente, usuario, nombre, al_guardar_alias)
        return
    st.caption(f"Tu nombre de usuario es **@{alias}**: dáselo a tus amigos para que te encuentren.")
    if st.session_state.get("error_amigos"):
        st.error(st.session_state.pop("error_amigos"))
    try:
        relaciones = cargar_relaciones(cliente, usuario)
    except bd.ErrorSupabase:
        st.error("No se pueden cargar tus amigos ahora mismo (¿falta ejecutar supabase/004_amigos.sql?).")
        return

    for r in [r for r in relaciones if r["estado"] == "pendiente" and not r["enviada"]]:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"{quien(r)} quiere ser tu amigo")
            st.button("Aceptar", type="primary", key=f"aceptar_{r['alias'] or r['usuario']}",
                      on_click=_accion, args=(cliente.responder_solicitud, usuario, r["usuario"], True))
            st.button("Rechazar", key=f"rechazar_{r['alias'] or r['usuario']}",
                      on_click=_accion, args=(cliente.responder_solicitud, usuario, r["usuario"], False))

    amigos = [r for r in relaciones if r["estado"] == "aceptada"]
    if amigos:
        st.markdown(f"**Tus amigos ({len(amigos)})**")
        for r in amigos:
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(quien(r))
                st.button("Quitar", type="tertiary", key=f"quitar_{r['alias'] or r['usuario']}",
                          on_click=_accion, args=(cliente.quitar_amistad, usuario, r["usuario"]))
    for r in [r for r in relaciones if r["estado"] == "pendiente" and r["enviada"]]:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(f"Solicitud enviada a {quien(r)}")
            st.button("Cancelar", type="tertiary", key=f"cancelar_{r['alias'] or r['usuario']}",
                      on_click=_accion, args=(cliente.quitar_amistad, usuario, r["usuario"]))

    _buscar_amigos(cliente, usuario, {r["usuario"]: r for r in relaciones})


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


def _buscar_amigos(cliente, usuario, conocidos):
    """Desplegable con buscador: al escribir, va sugiriendo gente de la base de datos por nombre o @usuario
    (lo filtra el navegador, sin esperar al servidor). Las opciones son texto plano: ni correos ni formato."""
    try:
        personas = {p["alias"]: p for p in cargar_directorio(cliente, usuario)}
    except bd.ErrorSupabase:
        st.error("No se puede buscar ahora mismo. Inténtalo en un momento.")
        return
    if not personas:
        st.caption("Todavía no hay nadie más con nombre de usuario para añadir.")
        return
    alias = st.selectbox("Buscar amigos", list(personas), index=None, key="buscar_amigos",
                         format_func=lambda a: f"{personas[a]['nombre'] or a} · @{a}",
                         placeholder="Escribe un nombre o @usuario")
    if alias is None:
        return
    p = personas[alias]
    relacion = conocidos.get(p["usuario"])
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(quien(p))
        if relacion is None:
            st.button("Añadir", icon=":material/person_add:", key=f"anadir_{alias}",
                      on_click=_accion, args=(cliente.solicitar_amistad, usuario, p["usuario"]))
        else:
            st.caption("Amigos ✓" if relacion["estado"] == "aceptada" else "Solicitud pendiente")
