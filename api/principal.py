"""
API de «¿Dónde comemos?» para la app móvil (movil/). La app nunca ve la clave de servicio de Supabase ni
correos de otros usuarios: entra con su token de Supabase Auth y la API hace el resto con datos.py y logica.py
(los mismos que la app de Streamlit, que sigue funcionando igual).

Configuración: variables de entorno SUPABASE_URL, SUPABASE_CLAVE_SERVICIO, R2_URL_PUBLICA, ORS_API_KEY o, si
faltan, .streamlit/secrets.toml (en local).

USO (desde la raíz del proyecto):
    uvicorn api.principal:app --host 0.0.0.0 --port 8787 --reload
    (el móvil, en la misma wifi, la llama en http://<IP del PC>:8787)
"""

import logging
import random
import sys
from datetime import date
from pathlib import Path as Ruta
from typing import Annotated, Literal

sys.path.insert(0, str(Ruta(__file__).resolve().parent))
import streamlit  # noqa: E402,F401  (primero: configura su registro al cargarse y luego se le baja el volumen)

# Las cachés de Streamlit (amigos.cargar_*) funcionan sin Streamlit, pero avisan al crearse y en cada llamada
logging.getLogger("streamlit.runtime.caching.cache_data_api").setLevel(logging.ERROR)
from base import (ID_MAX, NO_SE_PUEDE, Id, _listas, _tokens, configuracion, limite, mi_lista,  # noqa: E402,F401
                  obtener_bd, obtener_cuentas, olvidar_lista, usuario_actual)
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import amigos  # noqa: E402
import datos  # noqa: E402
import explorar  # noqa: E402
import social  # noqa: E402
import tarjetas  # noqa: E402
from cuentas import ErrorCuenta  # noqa: E402
from logica import (COL_ANADIDO, COL_CATEGORIA, ORDEN_NOMBRE, ORDEN_PUNTUACION, ORDEN_RECIENTES,  # noqa: E402
                    ORDEN_RESENAS, PRESUPUESTO_SIN_LIMITE, estadisticas_lista, filtrar_lista,
                    filtrar_y_puntuar, ordenar_resultados, radio_busqueda_km, resumen_mencion_plato, sugerencia_plato,
                    tiene_categorias_jev)
from servicios import geocodificar_direccion, obtener_minutos_a_pie, obtener_minutos_coche  # noqa: E402

MAX_RESULTADOS = 50        # de una búsqueda: la app enseña 5 y «Ver más» hasta 10, en el orden que elija
ORDENES = {"nota": ORDEN_PUNTUACION, "nombre": ORDEN_NOMBRE, "recientes": ORDEN_RECIENTES, "resenas": ORDEN_RESENAS}
LIMITE_CUENTAS = Depends(limite("auth", 10, 60))   # por IP: frena a quien pruebe contraseñas

app = FastAPI(title="¿Dónde comemos?")
app.include_router(social.rutas)


@app.exception_handler(datos.ErrorSupabase)
def _sin_supabase(request: Request, error: datos.ErrorSupabase):
    logging.getLogger("api").warning("Supabase: %s %s: %s", request.method, request.url.path, str(error)[:300])
    return JSONResponse(status_code=503, content={"detail": NO_SE_PUEDE})


@app.exception_handler(ErrorCuenta)
def _error_cuenta(request: Request, error: ErrorCuenta):
    return JSONResponse(status_code=400, content={"detail": str(error)})


# ----------------------- cuentas ----------------------- #

class Entrar(BaseModel):
    correo: str = Field(max_length=254)
    contrasena: str = Field(max_length=200)


class Registro(Entrar):
    nombre: str = Field(max_length=datos.LARGO_MAX_NOMBRE)


class Renovar(BaseModel):
    renovacion: str = Field(max_length=500)


class Recuperar(BaseModel):
    correo: str = Field(max_length=254)


class NuevaContrasena(Recuperar):
    codigo: str = Field(max_length=10)
    contrasena: str = Field(max_length=200)


@app.post("/auth/entrar", dependencies=[LIMITE_CUENTAS])
def entrar(e: Entrar, cuentas=Depends(obtener_cuentas)):
    return cuentas.entrar(e.correo, e.contrasena)


@app.post("/auth/renovar")
def renovar(e: Renovar, cuentas=Depends(obtener_cuentas)):
    return cuentas.renovar(e.renovacion)


@app.post("/auth/registrar", dependencies=[LIMITE_CUENTAS])
def registrar(e: Registro, cuentas=Depends(obtener_cuentas)):
    # Solo es seguro si Supabase obliga a confirmar el correo (si no, cualquiera entraría con el correo de otro)
    if not cuentas.confirmacion_obligatoria():
        raise HTTPException(503, "Ahora mismo no se pueden crear cuentas con contraseña.")
    cuentas.registrar(e.correo, e.contrasena, e.nombre)
    return {"ok": True, "mensaje": "Te hemos enviado un correo: ábrelo para confirmar tu cuenta y luego entra."}


@app.post("/auth/recuperar", dependencies=[LIMITE_CUENTAS])
def recuperar(e: Recuperar, cuentas=Depends(obtener_cuentas)):
    cuentas.pedir_codigo_recuperacion(e.correo)
    return {"ok": True}


@app.post("/auth/nueva-contrasena", dependencies=[LIMITE_CUENTAS])
def nueva_contrasena(e: NuevaContrasena, cuentas=Depends(obtener_cuentas)):
    return cuentas.cambiar_contrasena_con_codigo(e.correo, e.codigo, e.contrasena)


# ----------------------- tú ----------------------- #

@app.get("/yo")
def yo(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    perfil = bd.perfil_de(u["correo"]) or {}
    maestro, _, lista = mi_lista(bd, u["correo"])
    return {
        "correo": u["correo"],   # el suyo: solo lo ve él
        "nombre": perfil.get("nombre") or u.get("nombre") or u["correo"].split("@")[0],
        "alias": perfil.get("alias"), "foto": datos.foto_valida(perfil.get("foto")),
        "preferencias": datos.preferencias_validas(perfil.get("preferencias")),
        "foto_propia": datos.es_foto_propia(perfil.get("foto")),   # «Quitar foto» solo para la subida
        "lista": {"estado": (lista or {}).get("estado"), "mensaje": (lista or {}).get("mensaje"),
                  "total": len(maestro), "enlace": (lista or {}).get("enlace"),
                  "actualizado_en": (lista or {}).get("actualizado_en")},
        "zona": perfil.get("zona"),   # «De dónde eres»: solo la ve él
        "solicitudes": amigos.solicitudes_pendientes(bd, u["correo"]),
        "notificaciones": len(social.invitaciones_de_amigos(bd, u["correo"])[0]),
        "food_match": bd.con_deslizar(),
        "presupuesto_sin_limite": PRESUPUESTO_SIN_LIMITE,
    }


# ----------------------- Comer hoy ----------------------- #

def cocinas_disponibles(maestro):
    """app.cocinas_disponibles: las categorías de Jev o, si la lista no las tiene, la cocina de Google."""
    if maestro.empty:
        return []
    if tiene_categorias_jev(maestro):
        return sorted(str(c) for c in maestro[COL_CATEGORIA].dropna().unique())
    return sorted(str(c) for c in maestro["Tipo de cocina"].dropna().unique()) if "Tipo de cocina" in maestro else []


@app.get("/cocinas")
def cocinas(fuente: Literal["lista", "todos"] = "lista", u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Las cocinas para el desplegable y cuántos sitios hay (la portada: «… · N sitios»)."""
    if fuente == "todos":
        cocinas_todos, total = bd.cocinas_del_catalogo()
        return {"cocinas": cocinas_todos, "total": total}
    maestro = mi_lista(bd, u["correo"])[0]
    if maestro.empty:
        return {"cocinas": [], "total": 0}
    return {"cocinas": cocinas_disponibles(maestro), "total": len(maestro)}


@app.get("/geocodificar", dependencies=[Depends(limite("geocodificar", 30, 60))])
def geocodificar(q: str = Query(max_length=200), u=Depends(usuario_actual)):
    encontrada = geocodificar_direccion(q)
    if encontrada is None:
        raise HTTPException(404, "No he encontrado esa dirección en Madrid. Prueba con calle y número o un barrio.")
    return {"lat": encontrada.latitude, "lon": encontrada.longitude, "direccion": encontrada.address}


class Busqueda(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    transporte: Literal["En coche", "A pie"] = "En coche"
    minutos: int = Field(20, ge=5, le=60)
    cocina: str = Field("", max_length=60)
    presupuesto_min: int = Field(0, ge=0, le=PRESUPUESTO_SIN_LIMITE)
    presupuesto_max: int = Field(PRESUPUESTO_SIN_LIMITE, ge=0, le=PRESUPUESTO_SIN_LIMITE)
    plato: str = Field("", max_length=60)
    fuente: Literal["lista", "todos"] = "lista"


@app.post("/buscar", dependencies=[Depends(limite("buscar", 20, 60))])
def buscar(b: Busqueda, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Comer hoy: los que cumplen TODO lo pedido (nunca se rellena con otros), del mejor al peor."""
    if b.fuente == "todos":
        maestro, df_platos = bd.restaurantes_cerca(round(b.lat, 3), round(b.lon, 3),
                                                   radio_busqueda_km(b.transporte, b.minutos))
    else:
        maestro, df_platos, _ = mi_lista(bd, u["correo"])
    if maestro.empty:
        return {"resultados": [], "aviso": None, "vacio": True}
    aviso = None
    if b.transporte == "A pie":
        clave_ors = configuracion()["ors"]
        minutos = obtener_minutos_a_pie((b.lat, b.lon), maestro, clave_ors)
        if not clave_ors:
            aviso = "El tiempo a pie se estima en línea recta, no por calles reales."
    else:
        minutos = obtener_minutos_coche((b.lat, b.lon), maestro)
    r = {"presupuesto_min": b.presupuesto_min,
         "presupuesto_max": None if b.presupuesto_max >= PRESUPUESTO_SIN_LIMITE else b.presupuesto_max,
         "cocina": b.cocina.strip(), "tiempo_maximo_min": b.minutos, "plato_deseado": b.plato.strip()}
    df = filtrar_y_puntuar(maestro, df_platos, r, minutos)
    if df.empty:   # sin ninguno que cumpla, filtrar_y_puntuar no añade la columna Score
        return {"resultados": [], "aviso": aviso, "vacio": False}
    df = ordenar_resultados(df, ORDEN_PUNTUACION).head(MAX_RESULTADOS)
    return {"resultados": [{**tarjetas.tarjeta(f, bd), "minutos": round(float(f["Tiempo desplazamiento (min)"])),
                            "puntuacion": round(float(f["Score"]), 4)} for _, f in df.iterrows()],
            "aviso": aviso, "vacio": False}


# ----------------------- tu lista ----------------------- #

@app.get("/lista")
def lista(texto: str = Query("", max_length=60), cocina: list[str] = Query([], max_length=10),
          presupuesto_min: int = 0, presupuesto_max: int = PRESUPUESTO_SIN_LIMITE, nota_min: float = 0.0,
          plato: str = Query("", max_length=60), ocultar_cerrados: bool = False,
          orden: Literal["nota", "nombre", "recientes", "resenas"] = "nota",
          de: Literal["lista", "idos"] = "lista", desde: date | None = None, hasta: date | None = None,
          u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """app.lista_filtrable: tu lista o, con de=idos, los restaurantes a los que has ido (app.restaurantes_a_los_que_has_ido).
    `desde`/`hasta`: «Añadidos a tu lista entre». `cocinas`: las opciones del filtro (app.cocinas_disponibles)."""
    maestro, df_platos, _ = mi_lista(bd, u["correo"])
    if de == "idos":
        visitas = amigos.cargar_mis_visitas(bd, u["correo"])
        maestro = visitas.drop(columns=["Amigo", "Nota visita", "Comentario visita", "Fecha visita"],
                               errors="ignore").drop_duplicates("ID") if not visitas.empty else visitas
    anadido_entre = tuple(d for d in (desde, hasta) if d) if desde else ()
    df = filtrar_lista(maestro, df_platos, texto, tuple(c[:60] for c in cocina), presupuesto_min,
                       None if presupuesto_max >= PRESUPUESTO_SIN_LIMITE else presupuesto_max, nota_min,
                       plato, ocultar_cerrados, ORDENES[orden], anadido_entre) if not maestro.empty else maestro
    resumen = estadisticas_lista(maestro)
    if resumen:
        resumen = {**resumen, "cocinas": {str(k): int(v) for k, v in resumen["cocinas"].items()}}
    return {"restaurantes": tarjetas.tarjetas(df, bd), "total": len(maestro), "resumen": resumen,
            "cocinas": cocinas_disponibles(maestro)}


class Enlace(BaseModel):
    enlace: str = Field(max_length=500)


@app.post("/lista/enlace", dependencies=[Depends(limite("enlace", 5, 3600))])
def sincronizar_lista(e: Enlace, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Pega (o vuelve a pedir) tu lista de Google Maps: la procesa el procesador del PC."""
    enlace = e.enlace.strip()
    if not datos.enlace_lista_valido(enlace):
        raise HTTPException(400, "Ese enlace no parece de una lista de Google Maps. En Google Maps: abre tu lista → "
                                 "Compartir → copiar enlace (empieza por https://maps.app.goo.gl/).")
    estado = bd.pedir_actualizacion(u["correo"], enlace)["estado"]
    olvidar_lista(u["correo"])
    return {"estado": estado}


@app.delete("/lista/{restaurante_id}")
def quitar_de_mi_lista(restaurante_id: Id, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Deja de estar en TU lista (no se borra de la app: sigue para los demás y en tus valoraciones)."""
    lista_actual = mi_lista(bd, u["correo"])[2]
    if not lista_actual:
        raise HTTPException(404, "No tienes lista.")
    bd.quitar_de_lista(lista_actual["id"], restaurante_id)
    if bd.con_deslizar():   # si lo añadiste deslizando, que no vuelva al sincronizar tu lista de Google Maps
        bd.no_me_gusta_ya(u["correo"], restaurante_id)
    olvidar_lista(u["correo"])
    return {"ok": True}


# ----------------------- ficha de un restaurante ----------------------- #

def _mis_visitas(bd, correo):
    df = amigos.cargar_mis_visitas(bd, correo)
    return {} if df.empty else {int(f["ID"]): tarjetas.visita(f) for _, f in df.iterrows()}


@app.get("/restaurantes/{restaurante_id}")
def ficha(restaurante_id: Id, plato: str = Query("", max_length=60),
          u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    maestro, df_platos = bd.restaurantes_por_ids([restaurante_id])
    if maestro.empty:
        raise HTTPException(404, "Ese restaurante no existe.")
    mio = mi_lista(bd, u["correo"])[0]
    en_mia = mio[mio["ID"] == restaurante_id] if not mio.empty else mio
    eatlist = {f["restaurantes"]["id"] for f in bd.eatlist_de(u["correo"]) if f.get("restaurantes")}
    return {
        **tarjetas.ficha(maestro.iloc[0], bd),
        # la fecha en que lo añadiste sale de TU lista (el catálogo no la tiene)
        "anadido_en": tarjetas.texto(en_mia.iloc[0].get(COL_ANADIDO)) if not en_mia.empty else None,
        "fotos": [bd.url_foto(a) for a in bd.fotos_de(restaurante_id)],
        "en_mi_lista": not en_mia.empty, "en_eatlist": restaurante_id in eatlist,
        "mi_visita": _mis_visitas(bd, u["correo"]).get(restaurante_id),
        "num_resenas": len(amigos.cargar_resenas(bd, restaurante_id)),
        "sobre_plato": resumen_mencion_plato(restaurante_id, plato.strip(), df_platos) if plato.strip() else None,
    }


@app.get("/restaurantes/{restaurante_id}/resenas")
def resenas(restaurante_id: Id, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    return {"resenas": amigos.cargar_resenas(bd, restaurante_id)}   # nombre y @alias, nunca correos


# ----------------------- «Ya he ido» ----------------------- #

class Visita(BaseModel):
    nota: float | None = Field(None, ge=0.5, le=5)
    comentario: str | None = Field(None, max_length=1000)
    fecha: date | None = None
    con: list[Annotated[str, Field(max_length=30)]] = Field([], max_length=20)   # @alias de amigos: se les invita


@app.get("/visitas")
def mis_visitas(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    return {"visitas": list(_mis_visitas(bd, u["correo"]).values())}


@app.put("/visitas/{restaurante_id}")
def guardar_visita(restaurante_id: Id, v: Visita, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    # los acompañantes, antes de guardar: si alguno no es tu amigo, no se guarda nada
    invitados = social.correos_de_amigos(bd, u["correo"], v.con)
    try:
        bd.registrar_visita(u["correo"], restaurante_id, v.nota, v.comentario, fecha=v.fecha)
    except ValueError as e:   # validaciones de datos.py (nota, comentario, fecha futura): mensajes para el usuario
        raise HTTPException(400, str(e)) from e
    social.quitar_de_eatlist(bd, u["correo"], restaurante_id)   # ya has ido: deja de estar «por probar»
    if invitados:   # cada uno lo confirma en sus notificaciones; hasta entonces no le sale nada
        bd.invitar_comensales(u["correo"], restaurante_id, invitados, fecha=v.fecha)
    amigos.limpiar_cache()
    return {"ok": True, "invitados": len(invitados)}


@app.delete("/visitas/{restaurante_id}")
def quitar_visita(restaurante_id: Id, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    bd.quitar_visita(u["correo"], restaurante_id)
    amigos.limpiar_cache()
    return {"ok": True}


# ----------------------- eatlist ----------------------- #

class Orden(BaseModel):
    ids: list[Annotated[int, Field(ge=1, le=ID_MAX)]] = Field(max_length=500)


@app.get("/eatlist")
def eatlist(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    return {"restaurantes": tarjetas.tarjetas(datos.eatlist_a_dataframe(bd.eatlist_de(u["correo"])), bd)}


@app.put("/eatlist")
def guardar_eatlist(o: Orden, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """La eatlist entera, en orden (el primero, el que más te apetece)."""
    bd.guardar_eatlist(u["correo"], o.ids)
    return {"ok": True}


# ----------------------- Descubrir ----------------------- #

@app.get("/lugares")
def lugares(q: str = Query("", max_length=100), lat: float | None = Query(None, ge=-90, le=90), lon: float | None = Query(None, ge=-180, le=180),
            zona: bool = False,
            cocinas: Annotated[list[str] | None, Query(max_length=30)] = None,
            pmin: int = Query(0, ge=0, le=PRESUPUESTO_SIN_LIMITE), pmax: int = Query(PRESUPUESTO_SIN_LIMITE, ge=0, le=PRESUPUESTO_SIN_LIMITE),
            nota: float = Query(0.0, ge=0, le=5), plato: str = Query("", max_length=60),
            u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Descubrir (explorar.seccion): por nombre, cerca de ti o, con `zona`, todo lo que hay a ~1 km de ese punto; con
    los filtros de «Filtros» (explorar.filtrar_lugares). `cocinas` = las opciones del filtro, de lo encontrado."""
    cerca = (lat, lon) if lat is not None and lon is not None else None
    if not cerca and (zona or not datos.texto_busqueda(q)):
        return {"lugares": [], "cocinas": [], "total": 0}
    encontrados = explorar._en_zona(bd, q, cerca) if zona else explorar._buscar(bd, q, cerca)
    encontrados = explorar._ordenar(encontrados, cerca)
    opciones = sorted({explorar._cocina(l) for l in encontrados} - {""} | set(cocinas or ()))
    presupuesto = (pmin, max(pmin, pmax))
    catalogo = None
    if presupuesto != (0, PRESUPUESTO_SIN_LIMITE) or plato.strip() or nota:
        ids = tuple(sorted({int(l["restaurante_id"]) for l in encontrados if l.get("restaurante_id")}))
        catalogo = explorar._catalogo(bd, ids) if ids else None
    filtrados = explorar.filtrar_lugares(encontrados, catalogo, cocinas or (), presupuesto, nota, plato)
    # ponytail: como mucho MAX_RESULTADOS (200) también en el mapa; la web enseña hasta 3000 agrupados en burbujas
    return {"lugares": [{**tarjetas.lugar(l, bd), "icono": explorar._icono(l)} for l in filtrados[:explorar.MAX_RESULTADOS]],
            "cocinas": opciones, "total": len(encontrados)}


@app.get("/lugares/{lugar_id}")
def lugar(lugar_id: str = Path(min_length=1, max_length=100, pattern=r"^[\w.:-]+$"), u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    encontrado = bd.lugar_por_id(lugar_id)
    if not encontrado:
        raise HTTPException(404, "Ese sitio no existe.")
    return tarjetas.lugar(encontrado, bd)


@app.post("/lugares/{lugar_id}/analizar", dependencies=[Depends(limite("analizar", 20, 3600))])
def analizar(lugar_id: str = Path(min_length=1, max_length=100, pattern=r"^[\w.:-]+$"), u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Lo pone en la cola del procesador; la app pregunta por /lugares/{id} hasta que esté analizado."""
    if not bd.lugar_por_id(lugar_id):
        raise HTTPException(404, "Ese sitio no existe.")
    bd.pedir_analisis(u["correo"], lugar_id)
    return {"ok": True}


@app.post("/lugares/{lugar_id}/cerrado", dependencies=[Depends(limite("cerrado", 10, 3600))])
def avisar_cerrado(lugar_id: str = Path(min_length=1, max_length=100, pattern=r"^[\w.:-]+$"), u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """«¿Ha cerrado? Avísanos» (explorar._avisar_cerrado): deja de salir en Descubrir para todos."""
    if not bd.lugar_por_id(lugar_id):
        raise HTTPException(404, "Ese sitio no existe.")
    bd.avisar_cerrado(lugar_id)
    explorar._buscar.clear()
    return {"ok": True}


FOTOS_PORTADA = 14   # como app.FOTOS_PORTADA


@app.get("/inicio")
def inicio(evitar: Annotated[str | None, Query(max_length=80)] = None,
           u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Inicio de Streamlit: fotos de la cinta (de tu lista, al azar) y «Una idea para hoy» (app.idea_del_dia)."""
    maestro, df_platos, _ = mi_lista(bd, u["correo"])
    archivos = maestro["Imagen archivo"].dropna().tolist() if "Imagen archivo" in maestro else []
    portada = [bd.url_foto(a) for a in random.sample(archivos, min(FOTOS_PORTADA, len(archivos)))]
    sugerida = sugerencia_plato(maestro, df_platos, random.Random(), evitar=evitar)
    idea = None
    if sugerida:
        plato, rid, menciones = sugerida
        idea = {"plato": plato, "menciones": int(menciones),
                "restaurante": tarjetas.tarjeta(maestro[maestro["ID"] == rid].iloc[0], bd)}
    return {"portada": portada, "idea": idea}


@app.get("/destacados")
def destacados(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """«Lo mejor de la semana»: las mejores visitas de todos (nombre, nunca correo)."""
    df, de_la_semana = amigos.cargar_destacados(bd)
    return {"de_la_semana": de_la_semana,
            "restaurantes": [{**tarjetas.tarjeta(f, bd), "visita": tarjetas.visita(f)} for _, f in df.iterrows()]}


@app.get("/salud")
def salud():
    return {"ok": True}
