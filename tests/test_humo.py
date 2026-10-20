"""
Tests de humo de la app (AppTest): que carga, que busca y que las vistas funcionan, y que los
resultados de 3 búsquedas fijas no cambian (tests/referencia.json).

Los componentes propios (mapa, lista, caja de dirección, botón de ubicación) son JS y AppTest no
puede usarlos: la ubicación se simula con session_state["ubicacion_actual"].

Usan red de verdad (OSRM para los tiempos en coche). Si cambia algo a propósito en los datos o
en la puntuación, regenera la referencia con:  REGENERAR_REFERENCIA=1 pytest tests/test_humo.py
"""

import json
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parent.parent
APP = str(RAIZ / "algoritmo" / "app.py")
REFERENCIA = Path(__file__).resolve().parent / "referencia.json"
CHUECA = (40.4227, -3.6993)

BUSQUEDAS = {   # nombre -> filtros del formulario
    "europea_20min": {"cocina": "Europea (otras)"},
    "cualquiera_20min": {},
    "italiana_barata_30min": {"cocina": "Italiana", "presupuesto": (0, 20), "tiempo": 30},
}


def nueva_app(seccion="comer"):
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["ubicacion_actual"] = CHUECA
    at.session_state["seccion"] = seccion
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def buscar(at, cocina="Cualquiera", presupuesto=(0, 30), tiempo=20, plato=""):
    at.selectbox(key="cocina").select(cocina)
    at.slider(key="presupuesto").set_range(*presupuesto)
    at.slider(key="tiempo").set_value(tiempo)
    at.text_input(key="plato").input(plato)
    at.run()
    at.button(key="boton_buscar").click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at.session_state["resultado"]["df_puntuado"]


def huella_resultado(df):
    """Lo que tiene que mantenerse idéntico entre fases: qué restaurantes, en qué orden y con qué nota."""
    df = df.sort_values(["Score", "ID"], ascending=[False, True])
    return [[int(i), round(float(s), 4)] for i, s in zip(df["ID"], df["Score"])]


def test_carga_sin_errores():
    at = nueva_app()
    assert at.session_state["vista"] == "buscador"
    assert at.button(key="boton_buscar").label == "Buscar restaurantes"


@pytest.mark.parametrize("nombre", list(BUSQUEDAS))
def test_resultados_iguales_a_la_referencia(nombre):
    at = nueva_app()
    huella = huella_resultado(buscar(at, **BUSQUEDAS[nombre]))
    assert at.session_state["vista"] == "resultados"

    referencia = json.loads(REFERENCIA.read_text(encoding="utf-8")) if REFERENCIA.exists() else {}
    if os.environ.get("REGENERAR_REFERENCIA") or nombre not in referencia:
        referencia[nombre] = huella
        REFERENCIA.write_text(json.dumps(referencia, indent=1), encoding="utf-8")
        pytest.skip(f"referencia de '{nombre}' guardada")
    assert huella == referencia[nombre]


def test_filtro_cocina_estricto():
    at = nueva_app()
    df = buscar(at, cocina="Europea (otras)")
    assert list(df["Nombre"]) == ["K'era | Restaurante Georgiano Madrid"]
    assert any("Solo hay 1" in m.value for m in at.markdown)
    assert not [b for b in at.button if b.label.startswith("Ver ")]   # no rellena con otros


def test_sin_resultados_y_atajo():
    at = nueva_app()
    assert buscar(at, plato="xyzzy").empty
    assert "Nada por aquí" in [s.value for s in at.subheader]
    atajo = [b for b in at.button if b.label == "Sin plato concreto"]
    assert atajo
    atajo[0].click().run()
    assert not at.exception
    assert not at.session_state["resultado"]["df_puntuado"].empty
    assert at.session_state["plato"] == ""


def test_ver_mas_orden_y_volver():
    at = nueva_app()
    df = buscar(at)
    assert len(df) > 10
    [b for b in at.button if b.label == "Ver 5 más"][0].click().run()
    assert at.session_state["num_mostrados"] == 10
    assert not [b for b in at.button if b.label.startswith("Ver ")]

    at.session_state["orden"] = "Más cerca"
    at.run()
    assert not at.exception

    [b for b in at.button if b.label == "Cambiar"][0].click().run()
    assert at.session_state["vista"] == "buscador"
    assert at.session_state["tiempo"] == 20   # el formulario conserva lo escrito


# ---------------------------------------------------------------- barra de secciones

def test_inicio_propone_un_plato_y_lleva_a_buscarlo():
    at = nueva_app(seccion="inicio")
    plato, id_restaurante, _ = at.session_state["sugerencia"]
    assert any(f"¿Te apetece {plato}?" in h.value for h in at.subheader)
    at.button(key="otra_idea").click().run()
    assert not at.exception and at.session_state["sugerencia"][0] != plato   # otro plato
    plato = at.session_state["sugerencia"][0]
    at.button(key="buscar_plato").click().run()
    assert not at.exception
    assert at.session_state["seccion"] == "comer" and at.text_input(key="plato").value == plato


def test_mi_lista_filtra():
    at = nueva_app(seccion="mi_lista")
    total = at.caption[0].value
    assert total.endswith("restaurantes")
    at.text_input(key="ml_texto").input("zzzz no existe").run()
    assert any("Ninguno cumple" in i.value for i in at.info)
    at.text_input(key="ml_texto").input("").run()
    at.multiselect(key="ml_cocinas").select("Italiana").run()
    assert not at.exception and at.caption[0].value != total


def test_cambiar_de_seccion_conserva_el_formulario():
    at = nueva_app()
    at.slider(key="tiempo").set_value(45).run()
    at.session_state["seccion"] = "perfil"
    at.run()
    assert not at.exception and any(h.value == "Tus datos" for h in at.subheader)
    at.session_state["seccion"] = "comer"
    at.run()
    assert at.slider(key="tiempo").value == 45
    assert not at.warning, [w.value for w in at.warning]   # ni el aviso de "default + Session State"


def test_los_css_no_llevan_menor_que():
    """st.html limpia el HTML con DOMPurify, que tira un <style> ENTERO si su texto lleva algo que parezca
    una etiqueta (p. ej. un comentario con "<id>"): todo ese CSS dejaría de aplicarse sin dar ningún error."""
    for css in (RAIZ / "algoritmo" / "componentes").glob("*.css"):
        assert "<" not in css.read_text(encoding="utf-8"), css.name


def test_mi_lista_dice_cuantos_filtros_hay_puestos():
    at = nueva_app(seccion="mi_lista")
    at.session_state["ml_cocinas"] = ["Italiana"]            # lo que hace tocar "Italiana" en la gráfica del Perfil
    at.run()
    assert at.status[0].label == "Filtros (1)"
    at.slider(key="ml_nota").set_value(4.0).run()
    assert at.status[0].label == "Filtros (2)"



def test_tocar_mi_lista_en_la_barra_quita_todos_los_filtros():
    at = nueva_app(seccion="mi_lista")
    at.text_input(key="ml_texto").input("sushi").run()
    at.multiselect(key="ml_cocinas").select("Japonesa").run()
    at.slider(key="ml_nota").set_value(4.5).run()
    at.toggle(key="ml_cerrados").set_value(True).run()
    assert at.status[0].label == "Filtros (3)"
    at.session_state["seccion"] = "perfil"
    at.run()
    at.session_state["seccion"] = "mi_lista"
    at.session_state["limpiar_mi_lista"] = True                         # lo que hace tocar "Mi lista" en la barra
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.text_input(key="ml_texto").value == "" and at.multiselect(key="ml_cocinas").value == []
    assert at.slider(key="ml_nota").value == 0.0 and at.toggle(key="ml_cerrados").value is False
    assert at.status[0].label == "Filtros"
