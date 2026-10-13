"""
Lógica de recomendación, sin Streamlit ni red: filtros estrictos, puntuación y orden.
Se puede importar y probar sola (tests/test_logica.py).
"""

import re
import unicodedata
from datetime import datetime

import pandas as pd

PESO_PRECIO = 0.15
PESO_COCINA = 0.30
PESO_PLATO = 0.20
PESO_CALIDAD = 0.30
PESO_NUM_RESENAS = 0.05
ORDEN_PUNTUACION = "Mejor valorados"
ORDEN_CERCANOS = "Más cerca"
ORDEN_RESENAS = "Más reseñas"   # solo en "Mi lista"
ORDEN_NOMBRE = "Nombre"
# Categoría de cocina calculada con Jev (columnas que trae clasificacion_jev.xlsx).
COL_CATEGORIA = "Categoría (Jev)"
COL_CATEGORIA_2 = "Categoría 2ª (Jev)"
COL_VOTOS_1 = "% votos categoría (Jev)"
COL_VOTOS_2 = "% votos 2ª (Jev)"
SCORE_COCINA_SECUNDARIA = 0.6    # el restaurante tiene la cocina elegida como segunda categoría
SCORE_COCINA_DESCONOCIDA = 0.3   # Jev no pudo clasificarlo (pocas reseñas informativas): ni sí ni no
VOTOS_MIN_SECUNDARIA = 0.25      # la segunda categoría solo cuenta si tiene al menos este % de los votos


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


def tiene_categorias_jev(maestro):
    """¿Trae el maestro la categoría de cocina de Jev? Si no (maestro antiguo), se usa la de Google."""
    return COL_CATEGORIA in maestro.columns and maestro[COL_CATEGORIA].notna().any()


def _sin_tildes(texto):
    if not isinstance(texto, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))
_STOPWORDS_COCINA = {"y", "de", "del", "la", "el", "las", "los", "otras", "otra"}
_RAIZ_MIN = 5   # comparamos por raíz de palabra: "arroces"/"arrocería" o "vegana"/"vegano"
                # no coinciden letra por letra, pero sus 5 primeras letras sí


def _palabras_significativas(texto):
    """Raíces de las palabras de 4+ letras de `texto`, sin tildes ni conectores ('y', 'de',
    'otras'...). Se usa para comparar una etiqueta de Jev tipo "Asiática (otras)" contra el
    texto libre de Google: comparar la frase completa casi nunca coincide, y comparar palabra
    a palabra tampoco (género/número distintos), así que se compara por raíz."""
    palabras = [p for p in re.findall(r"[a-z]+", _sin_tildes(texto)) if len(p) >= 4 and p not in _STOPWORDS_COCINA]
    return [p[:_RAIZ_MIN] for p in palabras]


def _coincide_con_google(etiqueta_elegida, texto_google):
    palabras = _palabras_significativas(etiqueta_elegida)
    if not palabras:
        return False
    texto_norm = _sin_tildes(texto_google)
    return any(p in texto_norm for p in palabras)


def puntuacion_cocina(fila, cocina_elegida, con_jev):
    """
    Encaje (0-1) entre la cocina elegida y la del restaurante.
    Con categorías de Jev: 1 si es su categoría principal (o hay empate con la segunda), 0.6 si es
    la segunda con peso suficiente, 0 si tiene otra cocina, y 0.3 si Jev no pudo clasificarlo
    (salvo que la etiqueta de Google contenga esa cocina, que cuenta como 1).
    Sin categorías de Jev (maestro antiguo): coincidencia de texto con el tipo de Google, como antes.
    """
    if not cocina_elegida:
        return 0.5
    if not con_jev:
        return 1.0 if cocina_elegida.lower() in str(fila["Tipo de cocina"]).lower() else 0.0

    principal = fila.get(COL_CATEGORIA)
    if isinstance(principal, str) and principal.strip():
        if principal == cocina_elegida:
            return 1.0
        if fila.get(COL_CATEGORIA_2) == cocina_elegida:
            v1, v2 = fila.get(COL_VOTOS_1), fila.get(COL_VOTOS_2)
            if pd.notna(v1) and pd.notna(v2) and v2 >= v1:
                return 1.0                     # empate: la "segunda" es tan buena como la principal
            if pd.notna(v2) and v2 >= VOTOS_MIN_SECUNDARIA:
                return SCORE_COCINA_SECUNDARIA
        return 0.0

    return 1.0 if _coincide_con_google(cocina_elegida, fila.get("Tipo de cocina")) else SCORE_COCINA_DESCONOCIDA


def encaja_precio(texto, presupuesto_min, presupuesto_max):
    min_r, max_r = parsear_rango_precio(texto)
    # ponytail: sin precio conocido no se puede descartar, se deja pasar
    return (min_r is None and max_r is None) or solapamiento(min_r, max_r, presupuesto_min, presupuesto_max) > 0


def cerrados(df):
    """Máscara de los restaurantes que Google da por cerrados (temporal o permanentemente)."""
    if "Estado" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Estado"].fillna("").astype(str).str.contains("cerrado", case=False)


def filtrar_lista(maestro, df_platos, texto="", cocinas=(), presupuesto_min=0, presupuesto_max=None,
                  nota_min=0.0, plato="", ocultar_cerrados=False, orden=ORDEN_PUNTUACION):
    """Pestaña "Mi lista": los restaurantes de la lista que cumplen los filtros (los mismos criterios
    estrictos que el buscador, sin tiempos de viaje), ordenados."""
    df = maestro
    if df.empty:
        return df
    if texto.strip():
        df = df[df["Nombre"].map(_sin_tildes).str.contains(re.escape(_sin_tildes(texto.strip())))]
    if cocinas and not df.empty:
        con_jev = tiene_categorias_jev(maestro)
        df = df[df.apply(lambda f: any(puntuacion_cocina(f, c, con_jev) >= SCORE_COCINA_SECUNDARIA for c in cocinas),
                         axis=1).astype(bool)]
    df = df[df["Rango de precios"].apply(encaja_precio, args=(presupuesto_min, presupuesto_max)).astype(bool)]
    if nota_min:
        df = df[df["Puntuación"].fillna(0) >= nota_min]
    if plato.strip():
        df = df[df["ID"].apply(lambda i: puntuacion_plato(i, plato.strip(), df_platos) > 0).astype(bool)]
    if ocultar_cerrados:
        df = df[~cerrados(df)]
    if orden == ORDEN_NOMBRE:
        return df.sort_values("Nombre", key=lambda s: s.map(_sin_tildes))
    if orden == ORDEN_RESENAS:
        return df.sort_values(["Nº Reseñas", "Puntuación"], ascending=False)
    return df.sort_values(["Puntuación", "Nº Reseñas"], ascending=False)


# Jev a veces apunta como "plato" el tipo de cocina ("india", "peruana"...): en Inicio quedaría
# "¿Te apetece india?". ponytail: lista a mano; si salen otros, añadirlos aquí.
NO_SON_PLATOS = {"argentina", "china", "coreana", "española", "francesa", "georgiana", "griega", "india",
                 "italiana", "izakaya", "japonesa", "libanesa", "marisquería", "mexicana", "peruana",
                 "tailandesa", "turca", "vietnamita"}


def sugerencia_plato(maestro, df_platos, rng, evitar=None, minimo=2):
    """Inicio: un plato al azar entre los que las reseñas elogian (al menos `minimo` menciones
    buenas en un mismo sitio abierto) y el sitio donde más lo elogian. Devuelve
    (plato, ID del restaurante, nº de menciones buenas) o None si no hay ninguno."""
    if maestro.empty or df_platos.empty or "ID_Restaurante" not in df_platos.columns:
        return None
    abiertos = maestro[~cerrados(maestro)]
    buenas = df_platos[(df_platos["Sentimiento"] == "Buena") & df_platos["ID_Restaurante"].isin(abiertos["ID"])]
    conteo = buenas.dropna(subset=["Plato"]).groupby(["Plato", "ID_Restaurante"]).size().reset_index(name="n")
    conteo = conteo[(conteo["n"] >= minimo) & ~conteo["Plato"].str.lower().isin(NO_SON_PLATOS)]
    platos = sorted(set(conteo["Plato"]) - {evitar}) or sorted(set(conteo["Plato"]))
    if not platos:
        return None
    plato = rng.choice(platos)
    candidatos = conteo[conteo["Plato"] == plato].merge(
        abiertos[["ID", "Puntuación"]], left_on="ID_Restaurante", right_on="ID")
    mejor = candidatos.sort_values(["n", "Puntuación"], ascending=False).iloc[0]
    return plato, int(mejor["ID"]), int(mejor["n"])


def estadisticas_lista(maestro, num_cocinas=6):
    """Perfil: resumen de la lista (nº de sitios, nota media, precio medio y cocinas más repetidas)."""
    if maestro.empty:
        return None
    columna = COL_CATEGORIA if tiene_categorias_jev(maestro) else "Tipo de cocina"
    rangos = [parsear_rango_precio(t) for t in maestro["Rango de precios"]]
    medios = [(lo + hi) / 2 for lo, hi in rangos if lo is not None and hi is not None]
    nota = maestro["Puntuación"].mean()
    return {
        "total": len(maestro),
        "nota_media": None if pd.isna(nota) else float(nota),
        "precio_medio": sum(medios) / len(medios) if medios else None,
        "cocinas": maestro[columna].dropna().value_counts().head(num_cocinas),
    }


def filtrar_y_puntuar(maestro, df_platos, r, minutos):
    """`minutos`: tiempo hasta cada restaurante (misma posición que `maestro`, None si no se
    sabe), calculado por servicios.obtener_minutos_*. Devuelve solo los que cumplen todo lo
    pedido, con su columna Score; sin ordenar (eso lo hace ordenar_resultados)."""
    df = maestro.copy()
    df["Tiempo desplazamiento (min)"] = minutos

    df = df[df["Tiempo desplazamiento (min)"].notna() & (df["Tiempo desplazamiento (min)"] <= r["tiempo_maximo_min"])]
    if df.empty:
        return df

    # Filtros estrictos: solo pasan los que cumplen lo pedido; si no hay, no se rellena con otros.
    con_jev_filtro = tiene_categorias_jev(maestro)
    if r["cocina"]:
        # Exige cocina principal o segunda con peso; descarta los de otra cocina y los no clasificados.
        df = df[df.apply(lambda f: puntuacion_cocina(f, r["cocina"], con_jev_filtro) >= SCORE_COCINA_SECUNDARIA, axis=1)]

    df = df[df["Rango de precios"].apply(encaja_precio, args=(r["presupuesto_min"], r["presupuesto_max"]))]

    if r["plato_deseado"]:
        df = df[df["ID"].apply(lambda i: puntuacion_plato(i, r["plato_deseado"], df_platos) > 0)]
    if df.empty:
        return df

    max_resenas = maestro["Nº Reseñas"].max() or 1
    con_jev = tiene_categorias_jev(maestro)

    # Sin plato concreto, puntuacion_plato() da 0.0 a todos por igual (no discrimina nada), así
    # que ese 20% de PESO_PLATO se perdería sin más. En ese caso lo pasamos a la cocina, que pasa
    # de 0.30 a 0.50; los pesos siguen sumando 1.0 en los dos casos.
    if r["plato_deseado"]:
        peso_cocina_efectivo, peso_plato_efectivo = PESO_COCINA, PESO_PLATO
    else:
        peso_cocina_efectivo, peso_plato_efectivo = PESO_COCINA + PESO_PLATO, 0.0

    def puntuar_fila(fila):
        min_r, max_r = parsear_rango_precio(fila["Rango de precios"])
        score_precio = solapamiento(min_r, max_r, r["presupuesto_min"], r["presupuesto_max"])

        score_cocina = puntuacion_cocina(fila, r["cocina"], con_jev)

        score_plato = puntuacion_plato(fila["ID"], r["plato_deseado"], df_platos)
        score_calidad = calcular_score_calidad(fila)
        num_resenas = fila["Nº Reseñas"] if not pd.isna(fila["Nº Reseñas"]) else 0
        score_resenas = min(1.0, num_resenas / max_resenas)

        return (
            PESO_PRECIO * score_precio + peso_cocina_efectivo * score_cocina + peso_plato_efectivo * score_plato +
            PESO_CALIDAD * score_calidad + PESO_NUM_RESENAS * score_resenas
        )

    df["Score"] = df.apply(puntuar_fila, axis=1)
    return df


def ordenar_resultados(df, orden):
    """El orden se elige ya en la vista de resultados: cambiarlo no repite la búsqueda."""
    if orden == ORDEN_CERCANOS:
        return df.sort_values(["Tiempo desplazamiento (min)", "Score"], ascending=[True, False])
    return df.sort_values("Score", ascending=False)



def hace_cuanto(fecha_iso, ahora):
    """"hoy", "ayer", "hace 3 días" o la fecha (12/10) si hace más de una semana. `ahora` con zona horaria."""
    dias = (ahora.date() - datetime.fromisoformat(fecha_iso).astimezone(ahora.tzinfo).date()).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    if dias < 7:
        return f"hace {dias} días"
    return datetime.fromisoformat(fecha_iso).astimezone(ahora.tzinfo).strftime("%d/%m")
