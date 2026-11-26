"""
Rutas «sociales» de la API: amigos (solicitudes, buscar gente, su perfil), «Te recomendamos ir a cenar con»,
notificaciones (un amigo dice que fuisteis juntos), con quién fuiste a un sitio, Diario, «Food match», editar tu
perfil y borrar tu cuenta. A los demás se les nombra por su @alias: su correo solo se usa aquí dentro y nunca sale.
"""

import threading
import time
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

import amigos
import datos
import deslizar
import tarjetas
from base import (Id, limite, mi_lista, obtener_bd, obtener_cuentas, olvidar_lista, olvidar_tokens_de, usuario_actual,
                  validado)
from logica import PESO_GUSTO_EATLIST, PESO_GUSTO_LISTA, cocina_favorita, compatibilidad, en_comun, motivo_gusto
from servicios import geocodificar_direccion

rutas = APIRouter()
Alias = Annotated[str, Path(pattern=r"^[a-z0-9_.]{3,20}$")]   # datos.ALIAS_VALIDO
MAX_PERSONAS = 30


# ----------------------- ayudas ----------------------- #

def persona(p):
    """Otra persona para la app: nombre, @alias y avatar (foto o inicial y color); nunca su correo."""
    return {"alias": p.get("alias"), "nombre": amigos._nombre(p), **amigos.datos_avatar(p)}


def _estado(relacion):
    if relacion is None:
        return "nuevo"
    if relacion["estado"] == "aceptada":
        return "amigo"
    return "enviada" if relacion["enviada"] else "recibida"


def _amigos(bd, correo):
    """{correo: relación} de tus amigos aceptados."""
    return {r["usuario"]: r for r in amigos.cargar_relaciones(bd, correo) if r["estado"] == "aceptada"}


def _por_alias(bd, correo, alias):
    """(correo, perfil con foto) de quien tiene ese @alias, o 404."""
    p = next((p for p in amigos.cargar_directorio(bd, correo) if p["alias"] == alias), None)
    if p is None:
        raise HTTPException(404, "No hay nadie con ese nombre de usuario.")
    return p["usuario"], {**p, **bd.perfiles_de({p["usuario"]}).get(p["usuario"], {})}


def correos_de_amigos(bd, correo, aliases):
    """@alias de tus amigos -> sus correos (para las consultas). 400 si alguno no es amigo tuyo."""
    if not aliases:
        return []
    por_alias = {r["alias"]: u for u, r in _amigos(bd, correo).items() if r.get("alias")}
    pedidos = list(dict.fromkeys(a.lstrip("@").lower() for a in aliases))
    if any(a not in por_alias for a in pedidos):
        raise HTTPException(400, "Solo puedes apuntar a tus amigos.")
    return [por_alias[a] for a in pedidos]


def quitar_de_eatlist(bd, correo, restaurante_id):
    ids = [f["restaurantes"]["id"] for f in bd.eatlist_de(correo) if f.get("restaurantes")]
    if restaurante_id in ids:
        bd.guardar_eatlist(correo, [i for i in ids if i != restaurante_id])


def invitaciones_de_amigos(bd, correo):
    """(invitaciones que esperan tu respuesta, solo de amigos aceptados; {correo: amigo})."""
    try:
        invitaciones = bd.invitaciones_para(correo)
    except datos.ErrorSupabase:   # p. ej. aún sin supabase/011_comensales.sql
        return [], {}
    amigos_ok = _amigos(bd, correo)
    return [i for i in invitaciones if i["de"] in amigos_ok and i.get("restaurantes")], amigos_ok


def _con_visita(df, bd):
    return [{**tarjetas.tarjeta(f, bd), "visita": tarjetas.visita(f)} for _, f in df.iterrows()] if not df.empty else []


def _mi_nombre(bd, u):
    return (bd.perfil_de(u["correo"]) or {}).get("nombre") or u.get("nombre") or u["correo"].split("@")[0]


def _cambiado():
    amigos.limpiar_cache()
    amigos.cargar_directorio.clear()


# ----------------------- amigos ----------------------- #

@rutas.get("/amigos")
def mis_amigos(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    relaciones = sorted((r for r in amigos.cargar_relaciones(bd, u["correo"]) if r.get("alias")),
                        key=lambda r: r["alias"])   # sin @alias no se les puede nombrar ni buscar
    return {cual: [persona(r) for r in relaciones if _estado(r) == estado]
            for cual, estado in (("amigos", "amigo"), ("recibidas", "recibida"), ("enviadas", "enviada"))}


@rutas.get("/amigos/visitas")
def visitas_de_amigos(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Inicio: «Tus amigos han ido a» (las dos últimas semanas)."""
    df = amigos.cargar_visitas_amigos(bd, u["correo"])
    return {"tiene_amigos": df is not None, "restaurantes": [] if df is None else _con_visita(df, bd)}


@rutas.get("/personas")
def buscar_personas(q: str = Query("", max_length=40), u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Gente con @alias cuyo nombre o @alias contiene lo escrito (con tu relación con cada uno)."""
    texto = datos.texto_busqueda(q.lstrip("@"))
    if len(texto) < 2:
        return {"personas": []}
    relaciones = {r["usuario"]: r for r in amigos.cargar_relaciones(bd, u["correo"])}
    encontradas = [p for p in amigos.cargar_directorio(bd, u["correo"])
                   if texto in datos.texto_busqueda(f"{p['alias']} {p.get('nombre') or ''}")]
    return {"personas": [{**persona(p), "estado": _estado(relaciones.get(p["usuario"]))}
                         for p in encontradas[:MAX_PERSONAS]]}


@rutas.get("/personas/{alias}")
def perfil_de_persona(alias: Alias, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Su perfil (también el de un enlace compartido). Lo de dentro (valoraciones, en común...), solo si sois amigos."""
    correo_otro, p = _por_alias(bd, u["correo"], alias)
    relacion = next((r for r in amigos.cargar_relaciones(bd, u["correo"]) if r["usuario"] == correo_otro), None)
    resultado = {**persona(p), "estado": _estado(relacion)}
    if resultado["estado"] != "amigo":
        return resultado
    su_lista = amigos.cargar_lista_de(bd, correo_otro)
    mia = mi_lista(bd, u["correo"])[0]
    suyas = amigos.cargar_valoraciones_de(bd, correo_otro, amigos._nombre(p))
    mias = amigos.cargar_mis_visitas(bd, u["correo"])
    sus_notas = amigos._notas(suyas)
    comunes = en_comun(mia, su_lista)
    afinidad = compatibilidad(mia, su_lista, amigos._notas(mias), sus_notas)
    return {**resultado,
            "afinidad": None if afinidad is None else int(afinidad),
            "nota_media": sum(sus_notas.values()) / len(sus_notas) if sus_notas else None,
            "ha_ido": len(suyas), "cocina_favorita": cocina_favorita(su_lista),
            "valoraciones": _con_visita(suyas.head(amigos.EN_MINI_PERFIL), bd),
            "en_comun_total": len(comunes), "idos_los_dos": len(amigos._ids(mias) & amigos._ids(suyas)),
            "en_comun": tarjetas.tarjetas(mia[mia["ID"].isin(comunes)].head(amigos.EN_MINI_PERFIL), bd) if comunes else []}


@rutas.post("/personas/{alias}/amistad", dependencies=[Depends(limite("amistad", 30, 3600))])
def pedir_amistad(alias: Alias, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Envía una solicitud (si esa persona ya te la había enviado, sois amigos directamente)."""
    correo_otro, _ = _por_alias(bd, u["correo"], alias)
    estado = validado(bd.solicitar_amistad, u["correo"], correo_otro)
    _cambiado()
    return {"estado": "amigo" if estado == "aceptada" else "enviada"}


@rutas.post("/personas/{alias}/aceptar")
def aceptar_amistad(alias: Alias, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    correo_otro, _ = _por_alias(bd, u["correo"], alias)
    bd.responder_solicitud(u["correo"], correo_otro, True)
    _cambiado()
    return {"estado": "amigo"}


@rutas.delete("/personas/{alias}/amistad")
def quitar_amistad(alias: Alias, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Rechazar una solicitud, cancelar la que enviaste o dejar de ser amigos."""
    correo_otro, _ = _por_alias(bd, u["correo"], alias)
    bd.quitar_amistad(u["correo"], correo_otro)
    _cambiado()
    return {"estado": "nuevo"}


@rutas.get("/cenar-con")
def cenar_con(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """«Te recomendamos ir a cenar con»: amigos de tus amigos y gente de tu zona (sin decir dónde vive)."""
    perfil = bd.perfil_de(u["correo"]) or {}
    zona = (perfil.get("zona_lat"), perfil.get("zona_lon"))
    zona = None if None in zona else zona
    sugeridas = amigos.cargar_sugerencias(bd, u["correo"], zona)
    return {"tiene_zona": zona is not None,
            "personas": [{**persona(s), "motivo": s["motivo"]} for s in sugeridas if s.get("alias")]}


# ----------------------- notificaciones: «X dice que fuisteis juntos» ----------------------- #

@rutas.get("/notificaciones")
def notificaciones(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    invitaciones, amigos_ok = invitaciones_de_amigos(bd, u["correo"])
    return {"notificaciones": [
        {"de": persona(amigos_ok[i["de"]]), "restaurante_id": int(i["restaurante_id"]),
         "restaurante": (i["restaurantes"].get("datos") or {}).get("Nombre") or "un restaurante",
         "fecha": str(i["fecha"])} for i in invitaciones if amigos_ok[i["de"]].get("alias")]}


def _invitacion(bd, correo, alias, restaurante_id):
    invitaciones, amigos_ok = invitaciones_de_amigos(bd, correo)
    encontrada = next((i for i in invitaciones if int(i["restaurante_id"]) == restaurante_id
                       and amigos_ok[i["de"]].get("alias") == alias), None)
    if encontrada is None:
        raise HTTPException(404, "Esa notificación ya no está.")
    return encontrada


class Valoracion(BaseModel):
    nota: float | None = Field(None, ge=0.5, le=5)
    comentario: str | None = Field(None, max_length=1000)


@rutas.post("/notificaciones/{alias}/{restaurante_id}")
def aceptar_invitacion(alias: Alias, restaurante_id: Id, v: Valoracion, u=Depends(usuario_actual),
                       bd=Depends(obtener_bd)):
    """«Sí, fui»: tu visita, con tus estrellas y tu comentario y el día que puso quien te invitó."""
    inv = _invitacion(bd, u["correo"], alias, restaurante_id)
    validado(bd.aceptar_invitacion, u["correo"], inv["de"], restaurante_id, v.nota, v.comentario,
             fecha=date.fromisoformat(str(inv["fecha"])))
    quitar_de_eatlist(bd, u["correo"], restaurante_id)
    amigos.limpiar_cache()
    return {"ok": True}


@rutas.delete("/notificaciones/{alias}/{restaurante_id}")
def rechazar_invitacion(alias: Alias, restaurante_id: Id, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    inv = _invitacion(bd, u["correo"], alias, restaurante_id)
    bd.borrar_invitacion(inv["de"], u["correo"], restaurante_id)
    return {"ok": True}


# ----------------------- con quién fuiste ----------------------- #

@rutas.get("/visitas/{restaurante_id}/comensales")
def comensales(restaurante_id: Id, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Los que confirmaron que fueron contigo, los que aún no y los amigos que puedes apuntar."""
    amigos_ok = {c: r for c, r in _amigos(bd, u["correo"]).items() if r.get("alias")}
    try:
        con = [c for c in bd.comensales_de(u["correo"], restaurante_id) if c in amigos_ok]
        pendientes = [c for c in bd.invitados_de(u["correo"], restaurante_id) if c in amigos_ok and c not in con]
        te_anadio = bd.anadido_por(u["correo"], restaurante_id)
    except datos.ErrorSupabase:   # p. ej. aún sin supabase/011_comensales.sql
        con, pendientes, te_anadio = [], [], None
    opciones = sorted((c for c in amigos_ok if c not in con and c not in pendientes and c != te_anadio),
                      key=lambda c: amigos_ok[c]["alias"])
    return {"con": [persona(amigos_ok[c]) for c in con], "pendientes": [persona(amigos_ok[c]) for c in pendientes],
            "te_anadio": persona(amigos_ok[te_anadio]) if te_anadio in amigos_ok else None,
            "opciones": [persona(amigos_ok[c]) for c in opciones]}


@rutas.delete("/visitas/{restaurante_id}/comensales/{alias}")
def quitar_comensal(restaurante_id: Id, alias: Alias, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Quita una invitación que aún no ha contestado."""
    bd.borrar_invitacion(u["correo"], correos_de_amigos(bd, u["correo"], [alias])[0], restaurante_id)
    return {"ok": True}


# ----------------------- Diario ----------------------- #

@rutas.get("/diario")
def diario(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Los sitios a los que has ido, del más reciente al más antiguo, con tu nota y tu comentario."""
    return {"restaurantes": _con_visita(amigos.cargar_mis_visitas(bd, u["correo"]), bd)}


# ----------------------- tu perfil ----------------------- #

class Nombre(BaseModel):
    nombre: str = Field(max_length=100)


class NuevoAlias(BaseModel):
    alias: str = Field(max_length=30)


class Preferencias(BaseModel):
    transporte: Literal["En coche", "A pie"]
    tiempo: int
    presupuesto: tuple[int, int]


class Zona(BaseModel):
    zona: str = Field(min_length=2, max_length=120)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class Foto(BaseModel):
    imagen: str = Field(max_length=datos.MAX_BYTES_FOTO * 4 // 3 + 100)   # data:image/...;base64,...


@rutas.put("/yo/nombre")
def cambiar_nombre(n: Nombre, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    bd.guardar_perfil(u["correo"], validado(datos.validar_nombre, n.nombre))
    _cambiado()
    return {"ok": True}


@rutas.put("/yo/alias")
def cambiar_alias(a: NuevoAlias, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    alias = validado(datos.validar_alias, a.alias)
    validado(bd.guardar_alias, u["correo"], _mi_nombre(bd, u), alias)
    _cambiado()
    return {"alias": alias}


@rutas.put("/yo/preferencias")
def cambiar_preferencias(p: Preferencias, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Lo que viene puesto en Comer hoy. Valores no válidos (no múltiplos de 5...) vuelven a los de siempre."""
    guardadas = bd.guardar_perfil(u["correo"], _mi_nombre(bd, u),
                                  {"transporte": p.transporte, "tiempo": p.tiempo, "presupuesto": list(p.presupuesto)})
    return {"preferencias": datos.preferencias_validas(guardadas.get("preferencias"))}


@rutas.put("/yo/zona", dependencies=[Depends(limite("zona", 20, 3600))])
def cambiar_zona(z: Zona, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """«De dónde eres»: solo para proponerte gente de tu zona; nadie la ve."""
    zona = " ".join(z.zona.split())
    punto = (z.lat, z.lon)
    if None in punto:   # escrita a mano, sin elegir una sugerencia
        encontrada = geocodificar_direccion(zona)
        if encontrada is None:
            raise HTTPException(404, "No encontramos esa zona. Prueba a elegir una de las sugerencias.")
        punto = (encontrada.latitude, encontrada.longitude)
    bd.guardar_zona(u["correo"], _mi_nombre(bd, u), zona, *punto)
    amigos.limpiar_cache()
    return {"zona": zona}


@rutas.delete("/yo/zona")
def quitar_zona(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    bd.guardar_zona(u["correo"], _mi_nombre(bd, u), None, None, None)
    amigos.limpiar_cache()
    return {"ok": True}


def _foto_propia(bd, correo):
    foto = (bd.perfil_de(correo) or {}).get("foto")
    return foto if datos.es_foto_propia(foto) else None


@rutas.put("/yo/foto", dependencies=[Depends(limite("foto", 10, 3600))])
def cambiar_foto(f: Foto, u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Foto propia (la ven tus amigos): se recorta cuadrada y pequeña y se le quitan los metadatos (GPS...)."""
    contenido = validado(datos.foto_desde_data_url, f.imagen)
    url = validado(bd.subir_foto_perfil, u["correo"], _mi_nombre(bd, u), contenido,
                   anterior=_foto_propia(bd, u["correo"]))
    _cambiado()
    return {"foto": url}


@rutas.delete("/yo/foto")
def quitar_foto(u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    bd.quitar_foto_perfil(u["correo"], _mi_nombre(bd, u), anterior=_foto_propia(bd, u["correo"]))
    _cambiado()
    return {"ok": True}


class Borrado(BaseModel):
    confirmacion: Literal["BORRAR"]


@rutas.post("/yo/borrar", dependencies=[Depends(limite("borrar", 3, 3600))])
def borrar_cuenta(b: Borrado, u=Depends(usuario_actual), bd=Depends(obtener_bd), cuentas=Depends(obtener_cuentas)):
    """Borra tu cuenta y todos tus datos (lo pide Apple). Primero los datos: si algo falla, se puede repetir."""
    bd.borrar_usuario(u["correo"])
    cuentas.borrar_usuario(u.get("id"))
    olvidar_lista(u["correo"])
    olvidar_tokens_de(u["correo"])
    _mazos.pop(u["correo"], None)
    _cambiado()
    return {"ok": True}


# ----------------------- «Food match» ----------------------- #
# El mazo de cada usuario vive aquí, en memoria (como en Streamlit en session_state), y se olvida a la media hora
# sin usarlo. ponytail: con varios procesos de la API, cada uno tendría el suyo; entonces, guardarlo fuera.

SEG_MAZO = 1800
_mazos = {}   # correo -> {"est", "ctx", "cerrojo", "hasta"}


def _contexto(bd, correo, zona):
    """Lo que necesita deslizar.py: tus gustos (lista, eatlist y visitas) y cómo cargar restaurantes."""
    mia, _, lista = mi_lista(bd, correo)
    eatlist = datos.eatlist_a_dataframe(bd.eatlist_de(correo))
    visitas = amigos.cargar_mis_visitas(bd, correo)

    def cargar_zona(lat, lon, radio_km):
        if bd.con_ficha_rapida():
            return bd.restaurantes_cerca(round(lat, 3), round(lon, 3), radio_km)[0]
        return bd.todos_los_restaurantes()[0]   # sin 012 no hay lat/lon en el catálogo

    return {"bd": bd, "usuario": correo, "lista": lista, "zona": zona,
            "amigos": list(_amigos(bd, correo).values()),
            "fuentes": [(mia, PESO_GUSTO_LISTA), (eatlist, PESO_GUSTO_EATLIST), (visitas, None)],
            "excluir": {int(i) for df in (mia, eatlist, visitas) for i in df.get("ID", [])},
            "cargar_zona": cargar_zona, "cargar_todo": lambda: bd.todos_los_restaurantes()[0],
            "al_cambiar_lista": lambda: olvidar_lista(correo)}


def _cartas(mazo):
    est, ctx = mazo["est"], mazo["ctx"]
    deslizar.rellenar(est, ctx)
    if not est["pendientes"]:
        return {"tarjetas": [], "fin": True, "con_zona": ctx["zona"] is not None}
    pool = est["pool"].set_index("ID", drop=False)
    ciudades, fotos, gustos = deslizar._ciudades(est, ctx, pool), deslizar._fotos(est, ctx), deslizar._gustos(est, ctx)
    return {"fin": False, "con_zona": ctx["zona"] is not None, "tarjetas": [
        {**tarjetas.tarjeta(pool.loc[i], ctx["bd"]), "localidad": ciudades.get(i) or None,
         "fotos": fotos.get(int(i)) or [], "gusto": gustos.get(int(i)), "motivo": motivo_gusto(pool.loc[i], est["perfil"])}
        for i in est["pendientes"] if i in pool.index]}


@rutas.get("/deslizar")
def empezar_deslizar(lat: float | None = Query(None, ge=-90, le=90), lon: float | None = Query(None, ge=-180, le=180),
                     u=Depends(usuario_actual), bd=Depends(obtener_bd)):
    """Las tarjetas que quedan por deslizar (si ya habías empezado hace poco, sigue donde lo dejaste). Tu zona es
    la de «De dónde eres» o, si no la tienes, la ubicación que mande la app."""
    if not bd.con_deslizar():
        raise HTTPException(404, "«Food match» todavía no está disponible.")
    ahora = time.monotonic()
    for correo in [c for c, m in _mazos.items() if m["hasta"] < ahora]:
        _mazos.pop(correo, None)
    mazo = _mazos.get(u["correo"])
    if mazo is None:
        perfil = bd.perfil_de(u["correo"]) or {}
        zona = (perfil.get("zona_lat"), perfil.get("zona_lon"))
        zona = zona if None not in zona else ((lat, lon) if lat is not None and lon is not None else None)
        ctx = _contexto(bd, u["correo"], zona)
        mazo = {"est": deslizar.empezar(ctx), "ctx": ctx, "cerrojo": threading.Lock()}
        _mazos[u["correo"]] = mazo
    mazo["hasta"] = ahora + SEG_MAZO
    with mazo["cerrojo"]:
        return _cartas(mazo)


class Decision(BaseModel):
    id: int = Field(ge=1)
    gusta: bool


@rutas.post("/deslizar", dependencies=[Depends(limite("deslizar", 120, 60))])
def decidir(d: Decision, u=Depends(usuario_actual)):
    """Derecha (gusta: a tu lista) o izquierda. Devuelve las que quedan (con las nuevas si hacían falta)."""
    mazo = _mazos.get(u["correo"])
    if mazo is None:
        raise HTTPException(409, "Ha pasado mucho rato: vuelve a abrir «Food match».")
    mazo["hasta"] = time.monotonic() + SEG_MAZO
    with mazo["cerrojo"]:
        deslizar.decidir(mazo["est"], mazo["ctx"], d.id, d.gusta)
        return _cartas(mazo)
