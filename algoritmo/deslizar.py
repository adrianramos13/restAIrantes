"""
Comer hoy -> «Food match» (solo con cuentas y con supabase/014_deslizar.sql): restaurantes de uno en uno,
estilo Tinder. Derecha = te gusta (entra en tu lista); izquierda = no te gusta (no vuelve a salir).

Qué sale: los restaurantes del catálogo que no conoces (ni en tu lista, ni en tu eatlist, ni donde has ido, ni ya
deslizados), ordenados por lo que encajan con tus gustos (logica.perfil_de_gustos / ranking_por_gustos). Se
mezclan dos de tu zona («De dónde eres» del perfil o tu ubicación) por cada uno de Madrid ciudad; cuando se
acaban, se amplía la zona y al final se usa el catálogo entero. Cada REORDENAR_CADA decisiones se vuelve a
ordenar lo que queda con lo que has deslizado.

Cómo va: el ranking se calcula una vez y se guarda en session_state; al navegador se mandan tandas de POR_TANDA
cuando le quedan PEDIR_CON por ver. La pila vive en el navegador (componentes/deslizar.*) y cada decisión llega
por el trigger «decision»; solo se vuelve a ejecutar el fragmento, no la página.
"""

import random

import pandas as pd
import streamlit as st

import datos as bd
from logica import (PESO_GUSTO_DESLIZADO, PESO_NO_GUSTA, intercalar, motivo_gusto, perfil_de_gustos,
                    ranking_por_gustos)

ESTADO = "deslizar"              # session_state: el mazo de esta visita a la pantalla
DECISION = "deslizar_decision"   # session_state: la última decisión, aún sin guardar ({id, gusta})
POR_TANDA = 15
PEDIR_CON = 5                    # cuando en el navegador quedan estas, se le mandan POR_TANDA más
REORDENAR_CADA = 10
CENTRO_MADRID = (40.4169, -3.7035)   # Puerta del Sol
# (radio de tu zona, radio de Madrid) en km; None = el catálogo entero. Se pasa a la siguiente al acabarse.
FASES = ((3.0, 5.0), (12.0, 12.0), (None, None))
CLAVE_MAZO = "mazo_deslizar"     # key del componente (app.mazo_deslizar)
AVISO_SEGUNDOS = 3               # lo que dura «X añadido a tu lista»


def salir():
    st.session_state["vista"] = "buscador"   # el mazo se queda: al volver, sigue donde lo dejaste


def preparar(ctx):
    """El mazo «en la recámara»: se llama al final de Inicio y Comer hoy, con la página ya dibujada, para que al
    pulsar «Food match» la primera tanda ya esté lista (lo lento es bajarse los restaurantes de la zona)."""
    if ESTADO in st.session_state:
        return
    try:
        est = empezar(ctx)
        rellenar(est, ctx)
    except bd.ErrorSupabase:
        return   # ya se intentará al pulsar el botón, y allí sí se avisa
    st.session_state[ESTADO] = est


def pantalla(ctx):
    """`ctx`: bd, usuario, lista (fila de listas o None), zona ((lat, lon) o None), fuentes ([(DataFrame, peso)] de
    tus gustos), excluir (ids que ya conoces), cargar_zona(lat, lon, radio) y cargar_todo() -> maestro,
    tarjeta(fila) -> {foto, meta}, al_cambiar_lista() (borra la caché de tu lista) y mazo(tarjetas, al_decidir)
    (dibuja el componente: se registra en app.py, como los de explorar.py)."""
    st.button("Volver", icon=":material/arrow_back:", type="tertiary", on_click=salir, key="deslizar_volver")
    st.subheader("Food match")
    st.caption("Desliza a la derecha lo que te guste (se añade a tu lista) y a la izquierda lo que no. "
               + ("Salen sitios de tu zona y de Madrid." if ctx["zona"] else "Salen sitios de Madrid: "
                  "pon «De dónde eres» en tus ajustes para ver también los de tu zona."))
    if ESTADO not in st.session_state:
        try:
            with st.spinner("Buscando sitios que te puedan gustar..."):
                st.session_state[ESTADO] = empezar(ctx)
        except bd.ErrorSupabase:
            st.error("No se han podido cargar los restaurantes ahora mismo. Prueba en un momento.")
            return
    mazo(ctx)


def empezar(ctx):
    vistos = set(ctx["excluir"]) | set(ctx["bd"].deslizados_de(ctx["usuario"]))
    est = {"fase": 0, "pool": pd.DataFrame(columns=["ID"]), "cerca": pd.DataFrame(), "lejos": pd.DataFrame(),
           "orden_cerca": [], "orden_lejos": [], "pendientes": [], "vistos": vistos, "gustados": [],
           "descartados": [], "decisiones": 0, "fin": False, "lista": ctx["lista"], "azar": random.Random()}
    _cargar_fase(est, ctx)
    return est


def _cargar_fase(est, ctx):
    radio_zona, radio_madrid = FASES[est["fase"]]
    if radio_zona is None:
        est["cerca"], est["lejos"] = ctx["cargar_todo"](), pd.DataFrame()
    else:
        est["cerca"] = ctx["cargar_zona"](*(ctx["zona"] or CENTRO_MADRID), radio_zona)
        est["lejos"] = ctx["cargar_zona"](*CENTRO_MADRID, radio_madrid)
    nuevos = [df for df in (est["cerca"], est["lejos"]) if not df.empty]
    if nuevos:
        est["pool"] = pd.concat([est["pool"], *nuevos], ignore_index=True).drop_duplicates("ID")
    _ordenar(est, ctx)


def _perfil(est, ctx):
    pool = est["pool"]
    return perfil_de_gustos(ctx["fuentes"] + [(pool[pool["ID"].isin(est["gustados"])], PESO_GUSTO_DESLIZADO),
                                              (pool[pool["ID"].isin(est["descartados"])], PESO_NO_GUSTA)])


def _ordenar(est, ctx):
    est["perfil"] = _perfil(est, ctx)
    est["orden_cerca"] = ranking_por_gustos(est["cerca"], est["perfil"], est["azar"], est["vistos"])
    est["orden_lejos"] = ranking_por_gustos(est["lejos"], est["perfil"], est["azar"], est["vistos"])


def rellenar(est, ctx):
    """Si quedan PEDIR_CON o menos por ver, añade la siguiente tanda (pasando de fase si se acaba la actual)."""
    while len(est["pendientes"]) <= PEDIR_CON and not est["fin"]:
        nuevos = intercalar(est["orden_cerca"], est["orden_lejos"], est["vistos"], POR_TANDA)
        est["vistos"].update(nuevos)
        est["pendientes"] += nuevos
        if len(nuevos) < POR_TANDA:   # esta fase se ha acabado
            if est["fase"] + 1 < len(FASES):
                est["fase"] += 1
                _cargar_fase(est, ctx)
            else:
                est["fin"] = True


def decidir(est, ctx, restaurante_id, gusta):
    """Guarda una decisión: en deslizados y, si te gusta, en tu lista. Devuelve el aviso para el usuario."""
    if restaurante_id not in est["pendientes"]:   # repetida (doble toque) o de otra visita a la pantalla
        return None
    est["pendientes"].remove(restaurante_id)
    (est["gustados"] if gusta else est["descartados"]).append(restaurante_id)
    est["decisiones"] += 1
    if est["decisiones"] % REORDENAR_CADA == 0:   # con lo que llevas deslizado, lo que queda se reordena
        _ordenar(est, ctx)
    ctx["bd"].guardar_deslizado(ctx["usuario"], restaurante_id, gusta)
    if not gusta:
        return None
    if est["lista"] is None:   # aún no tenía lista: se le crea una sin enlace de Google Maps
        est["lista"] = ctx["bd"].crear_lista_vacia(ctx["usuario"])
    ctx["bd"].anadir_a_lista(est["lista"]["id"], restaurante_id)
    ctx["al_cambiar_lista"]()
    nombre = est["pool"].loc[est["pool"]["ID"] == restaurante_id, "Nombre"]
    return f"«{nombre.iloc[0]}» añadido a tu lista" if not nombre.empty else "Añadido a tu lista"


def _al_decidir():
    valor = st.session_state[CLAVE_MAZO].decision
    if valor:
        st.session_state[DECISION] = valor


@st.fragment
def mazo(ctx):
    est = st.session_state[ESTADO]
    decision = st.session_state.pop(DECISION, None)
    try:
        if decision:
            aviso = decidir(est, ctx, int(decision["id"]), bool(decision["gusta"]))
            if aviso:
                st.toast(aviso, icon=":material/favorite:", duration=AVISO_SEGUNDOS)
        rellenar(est, ctx)
    except bd.ErrorSupabase:
        st.toast("No se ha podido guardar ahora mismo. Prueba en un momento.", icon=":material/error:")
    if not est["pendientes"]:
        st.info("¡Has visto todos los restaurantes que tenemos! Cada día se analizan sitios nuevos: vuelve en unos días.")
        return
    pool = est["pool"].set_index("ID", drop=False)
    ciudades = _ciudades(est, ctx, pool)
    tarjetas = [{"id": int(i), "nombre": str(pool.at[i, "Nombre"]), "localidad": ciudades.get(i) or "",
                 **ctx["tarjeta"](pool.loc[i]), "motivo": motivo_gusto(pool.loc[i], est["perfil"])}
                for i in est["pendientes"] if i in pool.index]
    ctx["mazo"](tarjetas, _al_decidir)


def _ciudades(est, ctx, pool):
    """Localidad de cada tarjeta (por su posición: datos.localidades): se pide una vez por tanda nueva y se guarda
    en el mazo. Sin coordenadas, sin localidad."""
    ciudades = est.setdefault("ciudades", {})
    faltan = [i for i in est["pendientes"] if i not in ciudades and i in pool.index]
    puntos = [(i, float(pool.at[i, "Latitud"]), float(pool.at[i, "Longitud"])) for i in faltan
              if pd.notna(pool.at[i, "Latitud"]) and pd.notna(pool.at[i, "Longitud"])]
    if faltan:
        try:
            ciudades.update(dict.fromkeys(faltan) | (ctx["bd"].localidades(puntos) if puntos else {}))
        except bd.ErrorSupabase:
            pass   # solo es un dato de la tarjeta: sin él sale igual, y se vuelve a pedir con la siguiente decisión
    return ciudades
