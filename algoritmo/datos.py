"""
Base de datos del modo multiusuario (Supabase), sin Streamlit: la usan la app (algoritmo/app.py),
el procesador de listas (obtener_datos/procesar_solicitudes.py) y la migración inicial.

Habla con la API REST de Supabase (PostgREST y Storage) con `requests` y la clave de servicio:
SOLO desde el servidor de Streamlit o tu ordenador, nunca en el navegador. Las tablas están en
supabase/esquema.sql.
"""

import base64
import io
import math
import re
import unicodedata
import urllib.parse
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

BUCKET_FOTOS = "fotos"
TIMEOUT_S = 30
FILAS_POR_PETICION = 100   # al guardar o buscar por clave, para no hacer URLs/peticiones enormes
COLUMNAS_PLATOS = ["ID_Restaurante", "Plato", "Sentimiento"]


class ErrorSupabase(Exception):
    pass


def clave_restaurante(nombre):
    """Clave del catálogo compartido: el nombre de Google normalizado (NFKC, espacios colapsados,
    minúsculas). Es la misma normalización que el cruce exacto del clasificador."""
    if not isinstance(nombre, str):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", nombre)).strip().lower()


def valor_para_json(valor):
    """JSON no admite NaN ni tipos de numpy/pandas: NaN -> None y numpy -> Python."""
    if valor is None:
        return None
    if isinstance(valor, np.bool_):
        return bool(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        return None if math.isnan(valor) else float(valor)
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):   # listas, dicts...: pd.isna no da un único booleano
        pass
    return valor


def fila_para_json(fila):
    return {str(k): valor_para_json(v) for k, v in dict(fila).items()}


def filas_a_dataframes(filas):
    """Filas de lista_restaurantes (con su restaurante embebido) -> (maestro, df_platos), con las
    mismas columnas que las hojas "Restaurantes" y "Platos mencionados" de clasificacion_jev.xlsx.
    El ID de cada restaurante es su id del catálogo, que no cambia aunque cambie la lista."""
    registros, platos = [], []
    for f in sorted(filas, key=lambda f: f["posicion"]):
        r = f["restaurantes"]
        registros.append({**(r.get("datos") or {}), "ID": r["id"], "Imagen archivo": r.get("imagen")})
        for p in r.get("platos") or []:
            platos.append({"ID_Restaurante": r["id"], "Plato": p.get("Plato"), "Sentimiento": p.get("Sentimiento")})
    return pd.DataFrame(registros), pd.DataFrame(platos, columns=COLUMNAS_PLATOS)


# Solo enlaces de listas de Google Maps: el procesador abre el enlace en TU Chrome, con TU sesión
# de Google iniciada, así que no puede aceptar cualquier web que pegue un usuario.
_PATRON_ENLACE_LISTA = re.compile(
    r"^https://(maps\.app\.goo\.gl/[A-Za-z0-9_-]+|goo\.gl/maps/[A-Za-z0-9_-]+|(www\.)?google\.(com|es)/maps/\S+)$")


LARGO_MAX_NOMBRE = 40   # el mismo límite que la tabla perfiles


PREFERENCIAS_DEFECTO = {"transporte": "En coche", "tiempo": 20, "presupuesto": [0, 30]}


def _es_paso_de_5(valor, minimo, maximo):
    return isinstance(valor, int) and not isinstance(valor, bool) and minimo <= valor <= maximo and valor % 5 == 0


def preferencias_validas(guardadas):
    """Preferencias de búsqueda (Perfil) listas para usar como valores iniciales del buscador: lo que
    falte o no valga (vienen de la base de datos) se queda con el valor por defecto."""
    guardadas = guardadas if isinstance(guardadas, dict) else {}
    p = dict(PREFERENCIAS_DEFECTO)
    if guardadas.get("transporte") in ("En coche", "A pie"):
        p["transporte"] = guardadas["transporte"]
    if _es_paso_de_5(guardadas.get("tiempo"), 5, 60):
        p["tiempo"] = guardadas["tiempo"]
    presupuesto = guardadas.get("presupuesto")
    if (isinstance(presupuesto, (list, tuple)) and len(presupuesto) == 2
            and all(_es_paso_de_5(x, 0, 100) for x in presupuesto) and presupuesto[0] <= presupuesto[1]):
        p["presupuesto"] = list(presupuesto)
    return p


def validar_nombre(nombre):
    """Nombre visible del usuario, limpio. Lanza ValueError con un mensaje para el usuario si no vale."""
    nombre = re.sub(r"\s+", " ", nombre or "").strip()
    if not nombre:
        raise ValueError("Escribe un nombre.")
    if len(nombre) > LARGO_MAX_NOMBRE:
        raise ValueError(f"El nombre puede tener como mucho {LARGO_MAX_NOMBRE} caracteres.")
    if any(c in nombre for c in "<>"):   # se muestra en la portada: nada de etiquetas HTML
        raise ValueError("El nombre no puede llevar los caracteres < ni >.")
    return nombre


def enlace_lista_valido(enlace):
    return isinstance(enlace, str) and bool(_PATRON_ENLACE_LISTA.match(enlace.strip()))


def filas_catalogo_desde_excel(df_rest, df_platos):
    """Hojas "Restaurantes" y "Platos mencionados" (las de clasificacion_jev.xlsx) -> filas del
    catálogo {clave, datos, platos, imagen}, en el orden de df_rest. Un restaurante repetido
    (misma clave) se guarda una vez: Postgres no deja actualizar la misma fila dos veces en una
    misma petición."""
    platos_por_id = {}
    for p in df_platos.to_dict("records") if not df_platos.empty else []:
        platos_por_id.setdefault(p["ID_Restaurante"], []).append(
            {"Plato": valor_para_json(p["Plato"]), "Sentimiento": valor_para_json(p["Sentimiento"])})
    filas, vistas = [], set()
    for fila in df_rest.to_dict("records"):
        clave = clave_restaurante(fila.get("Nombre"))
        if not clave or clave in vistas:
            continue
        vistas.add(clave)
        imagen = valor_para_json(fila.get("Imagen archivo"))
        datos = fila_para_json({k: v for k, v in fila.items() if k not in ("ID", "Imagen archivo")})
        filas.append({"clave": clave, "datos": datos, "platos": platos_por_id.get(fila.get("ID"), []),
                      "imagen": imagen or None})
    return filas


def url_foto(url_supabase, archivo):
    if not archivo:
        return None
    return f"{url_supabase.rstrip('/')}/storage/v1/object/public/{BUCKET_FOTOS}/{urllib.parse.quote(archivo)}"


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _filtro_in(valores):
    """Valores para el filtro in.(...) de PostgREST, entre comillas (los nombres llevan comas, paréntesis...)."""
    return "(" + ",".join('"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"' for v in valores) + ")"


def _par(a, b):
    """Filtro or/and de PostgREST para la amistad entre a y b, en cualquiera de los dos sentidos."""
    return (f"(and(solicitante.eq.{_comillas(a)},destinatario.eq.{_comillas(b)}),"
            f"and(solicitante.eq.{_comillas(b)},destinatario.eq.{_comillas(a)}))")


def _comillas(valor):
    return '"' + str(valor).replace("\\", "\\\\").replace('"', '\\"') + '"'


def texto_busqueda(texto):
    """Nombre para buscar: minúsculas, sin tildes y solo letras, números y espacios. Es lo que se guarda en
    lugares.nombre_busqueda y lo que se hace con lo que escribe el usuario (que así no puede colar comodines
    ni filtros de PostgREST)."""
    if not isinstance(texto, str):
        return ""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]|_", " ", sin_tildes.lower())).strip()


def caja_alrededor(lat, lon, radio_km):
    """(lat_min, lat_max, lon_min, lon_max) de un cuadrado de `radio_km` alrededor del punto."""
    dlat = radio_km / 111.32
    dlon = radio_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


COLUMNAS_LUGAR = "id,nombre,categoria,lat,lon,direccion,ciudad,pais,web,telefono,estado_analisis,restaurante_id"
COLUMNAS_FICHA = "nota_google,cocina_google,foto"   # la ficha rápida (supabase/012_ficha_rapida.sql)
DIAS_ENTRE_VERIFICACIONES = 30   # cada cuánto se vuelve a comprobar en Google Maps si un sitio sigue abierto


# Fotos de perfil: la de la cuenta de Google o una propia subida a nuestro almacenamiento (perfiles/<hex>.jpg).
# Se enseñan a los amigos como <img>, así que no vale cualquier URL (lo mismo exige 007_foto_propia.sql).
_FOTO_GOOGLE = re.compile(r"^https://[a-z0-9.-]+\.googleusercontent\.com/[^\s\"'<>]*$")
_FOTO_PROPIA = re.compile(r"^https://[a-z0-9-]+\.supabase\.co/storage/v1/object/public/fotos/perfiles/[0-9a-f]{32}\.jpg$")
LADO_FOTO_PERFIL = 256                  # px: se guarda cuadrada y pequeña
MAX_BYTES_FOTO = 5 * 1024 * 1024        # lo más grande que se acepta al subirla
MAX_PIXELES_FOTO = 40_000_000           # imágenes enormes (o "bombas" de descompresión): fuera


def foto_valida(url):
    """La URL de la foto si es una foto de Google o una propia de nuestro almacenamiento; si no, None."""
    if not isinstance(url, str) or len(url) > 500:
        return None
    return url if _FOTO_GOOGLE.match(url) or _FOTO_PROPIA.match(url) else None


_DATA_URL_FOTO = re.compile(r"^data:image/(?:jpeg|png|webp);base64,([A-Za-z0-9+/]+={0,2})$")


def foto_desde_data_url(texto):
    """La foto que manda el navegador ("data:image/jpeg;base64,...") -> sus bytes. ValueError si no vale."""
    if not isinstance(texto, str) or len(texto) > MAX_BYTES_FOTO * 4 // 3 + 100:
        raise ValueError(f"La foto tiene que ocupar menos de {MAX_BYTES_FOTO // (1024 * 1024)} MB.")
    encontrada = _DATA_URL_FOTO.match(texto)
    if not encontrada:
        raise ValueError("No parece una foto: usa una imagen JPG, PNG o WEBP.")
    return base64.b64decode(encontrada.group(1))


def es_foto_propia(url):
    return isinstance(url, str) and bool(_FOTO_PROPIA.match(url))


def preparar_foto_perfil(contenido):
    """Foto subida por el usuario -> JPEG cuadrado de 256 px (recortada al centro, girada según el móvil y
    sin metadatos: ni GPS ni nada). ValueError con un mensaje para el usuario si no vale."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not contenido or len(contenido) > MAX_BYTES_FOTO:
        raise ValueError(f"La foto tiene que ocupar menos de {MAX_BYTES_FOTO // (1024 * 1024)} MB.")
    try:
        with Image.open(io.BytesIO(contenido)) as img:
            if img.width * img.height > MAX_PIXELES_FOTO:
                raise ValueError("La foto es demasiado grande.")
            img = ImageOps.exif_transpose(img).convert("RGB")
            img = ImageOps.fit(img, (LADO_FOTO_PERFIL, LADO_FOTO_PERFIL), method=Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ValueError("No parece una foto: usa una imagen JPG, PNG o WEBP.") from e
    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=85)
    return salida.getvalue()


ALIAS_VALIDO = re.compile(r"^[a-z0-9_.]{3,20}$")   # el mismo check que la tabla perfiles


def validar_alias(alias):
    """@usuario elegido por el usuario -> el que se guarda (sin @, en minúsculas). ValueError si no vale."""
    alias = (alias or "").strip().lstrip("@").lower()
    if not ALIAS_VALIDO.match(alias):
        raise ValueError("El nombre de usuario debe tener de 3 a 20 caracteres: letras sin tildes, números, "
                         "'_' o '.'.")
    return alias


LARGO_MAX_COMENTARIO = 280   # el mismo límite que la tabla visitas


def validar_nota(nota):
    """Nota de "He ido": None, o de 0,5 a 5 en pasos de media estrella. ValueError si no vale."""
    if nota is None:
        return None
    if isinstance(nota, bool) or not isinstance(nota, (int, float)) or not 0.5 <= nota <= 5 or (nota * 2) % 1:
        raise ValueError("La nota tiene que ir de 0,5 a 5 estrellas, en medias estrellas.")
    return float(nota)


def validar_comentario(comentario):
    comentario = re.sub(r"\s+", " ", comentario or "").strip()
    if len(comentario) > LARGO_MAX_COMENTARIO:
        raise ValueError(f"El comentario puede tener como mucho {LARGO_MAX_COMENTARIO} caracteres.")
    return comentario or None


def momento_visita(fecha=None):
    """creado_en de una visita (es la fecha que se ve en el Diario y en el Inicio de los amigos): ahora si fue
    hoy (o no se dice) y, si fue otro día, ese día a las 14:00 de Madrid. Nunca en el futuro."""
    try:
        from zoneinfo import ZoneInfo
        zona = ZoneInfo("Europe/Madrid")
    except Exception:   # sistema sin base de zonas horarias
        zona = timezone.utc
    hoy = datetime.now(zona).date()
    if fecha is None or fecha == hoy:
        return _ahora()
    if fecha > hoy:
        raise ValueError("La fecha no puede ser de un día que aún no ha llegado.")
    return datetime(fecha.year, fecha.month, fecha.day, 14, tzinfo=zona).isoformat()


def visitas_a_dataframe(visitas, nombres):
    """Visitas de amigos (con su restaurante embebido) -> DataFrame como el maestro, más las columnas
    "Amigo" (su nombre, de `nombres`: {usuario: nombre}), "Nota visita" y "Fecha visita"."""
    filas = []
    for v in visitas:
        r = v.get("restaurantes")
        if not r:
            continue
        filas.append({**(r.get("datos") or {}), "ID": r["id"], "Imagen archivo": r.get("imagen"),
                      "Amigo": nombres.get(v["usuario"], "Un amigo"), "Nota visita": v.get("nota"),
                      "Comentario visita": v.get("comentario"), "Fecha visita": v["creado_en"]})
    return pd.DataFrame(filas)


def eatlist_a_dataframe(filas):
    """Filas de la eatlist (con su restaurante embebido, ya en orden) -> DataFrame como el maestro, más
    "Posición" (1 = el que más te apetece)."""
    registros = [{**(f["restaurantes"].get("datos") or {}), "ID": f["restaurantes"]["id"],
                  "Imagen archivo": f["restaurantes"].get("imagen"), "Posición": f["posicion"]}
                 for f in filas if f.get("restaurantes")]
    return pd.DataFrame(registros)


def _lotes(elementos, tamano=FILAS_POR_PETICION):
    for i in range(0, len(elementos), tamano):
        yield elementos[i:i + tamano]


class Supabase:
    def __init__(self, url, clave_servicio):
        self.url = url.rstrip("/")
        self._cabeceras = {"apikey": clave_servicio}
        # Las claves antiguas (service_role, "eyJ...") son JWT y van también como Bearer; las nuevas
        # (sb_secret_...) no son JWT y Supabase solo las acepta en la cabecera apikey.
        if not clave_servicio.startswith("sb_"):
            self._cabeceras["Authorization"] = f"Bearer {clave_servicio}"

    def _rest(self, metodo, tabla, *, params=None, json=None, prefer=None):
        cabeceras = dict(self._cabeceras)
        if prefer:
            cabeceras["Prefer"] = prefer
        try:
            r = requests.request(metodo, f"{self.url}/rest/v1/{tabla}", params=params, json=json,
                                 headers=cabeceras, timeout=TIMEOUT_S)
        except requests.RequestException as e:   # sin red, tiempo agotado...: la app ya sabe manejar ErrorSupabase
            raise ErrorSupabase(f"{metodo} {tabla}: sin respuesta de Supabase ({type(e).__name__})") from e
        if not r.ok:
            raise ErrorSupabase(f"{metodo} {tabla}: {r.status_code} {r.text[:300]}")
        return r.json() if r.content else None

    # ---------------- listas (una por usuario) ----------------

    def lista_de(self, usuario):
        filas = self._rest("GET", "listas", params={"usuario": f"eq.{usuario}", "select": "*"})
        return filas[0] if filas else None

    def guardar_lista(self, usuario, *, enlace=None, estado, mensaje=None):
        """Crea o actualiza la lista del usuario. Devuelve la fila guardada."""
        fila = {"usuario": usuario, "estado": estado, "mensaje": mensaje, "actualizado_en": _ahora()}
        if enlace is not None:
            fila["enlace"] = enlace
        filas = self._rest("POST", "listas", params={"on_conflict": "usuario"}, json=fila,
                           prefer="resolution=merge-duplicates,return=representation")
        return filas[0]

    def pedir_actualizacion(self, usuario, enlace):
        """El usuario pega (o vuelve a pedir) su lista. Si otra persona ya tiene ESA MISMA lista
        procesada, se copia al momento (estado "lista"); si no, queda pendiente para el procesador."""
        lista = self.guardar_lista(usuario, enlace=enlace, estado="pendiente")
        igual = self.lista_procesada_con_enlace(enlace, excepto_usuario=usuario)
        ids = self.ids_de_lista(igual["id"]) if igual else []
        if not ids:
            return lista
        self.reemplazar_lista(lista["id"], ids)
        self.marcar(lista["id"], "lista", f"{len(ids)} restaurantes (copiada de una lista ya procesada)")
        return {**lista, "estado": "lista"}

    def lista_procesada_con_enlace(self, enlace, excepto_usuario):
        filas = self._rest("GET", "listas", params={"enlace": f"eq.{enlace}", "estado": "eq.lista",
                                                    "usuario": f"neq.{excepto_usuario}", "select": "*", "limit": 1})
        return filas[0] if filas else None

    def ids_de_lista(self, lista_id):
        filas = self._rest("GET", "lista_restaurantes", params={
            "lista_id": f"eq.{lista_id}", "select": "restaurante_id,posicion", "order": "posicion.asc"})
        return [f["restaurante_id"] for f in filas]

    def listas_pendientes(self):
        return self._rest("GET", "listas", params={"estado": "eq.pendiente", "select": "*",
                                                   "order": "actualizado_en.asc"})

    def listas_con_enlace(self):
        return self._rest("GET", "listas", params={"enlace": "not.is.null", "select": "*",
                                                   "order": "actualizado_en.asc"})

    def marcar(self, lista_id, estado, mensaje=None):
        self._rest("PATCH", "listas", params={"id": f"eq.{lista_id}"},
                   json={"estado": estado, "mensaje": mensaje, "actualizado_en": _ahora()})

    def restaurantes_de(self, usuario):
        """(maestro, df_platos, lista) del usuario; DataFrames vacíos si aún no tiene restaurantes."""
        lista = self.lista_de(usuario)
        if not lista:
            return pd.DataFrame(), pd.DataFrame(columns=COLUMNAS_PLATOS), None
        filas = self._rest("GET", "lista_restaurantes", params={
            "lista_id": f"eq.{lista['id']}", "select": "posicion,restaurantes(id,datos,platos,imagen)"})
        maestro, df_platos = filas_a_dataframes(filas)
        return maestro, df_platos, lista

    def reemplazar_lista(self, lista_id, ids_en_orden):
        """La lista del usuario pasa a tener exactamente estos restaurantes, en este orden."""
        vistos, filas = set(), []
        for posicion, id_r in enumerate(ids_en_orden, start=1):
            if id_r in vistos:   # mismo restaurante dos veces en la lista de Google
                continue
            vistos.add(id_r)
            filas.append({"lista_id": lista_id, "restaurante_id": id_r, "posicion": posicion})
        self._rest("DELETE", "lista_restaurantes", params={"lista_id": f"eq.{lista_id}"})
        for lote in _lotes(filas):
            self._rest("POST", "lista_restaurantes", json=lote)

    def quitar_de_lista(self, lista_id, restaurante_id):
        """Quita un restaurante de UNA lista (solo esa relación lista-restaurante). El restaurante sigue en el
        catálogo, con sus datos y reseñas, en las listas de los demás y en las valoraciones de quien haya ido."""
        self._rest("DELETE", "lista_restaurantes", params={"lista_id": f"eq.{int(lista_id)}",
                                                           "restaurante_id": f"eq.{int(restaurante_id)}"})

    # ---------------- perfil (datos personales) ----------------

    def perfil_de(self, usuario):
        filas = self._rest("GET", "perfiles", params={"usuario": f"eq.{usuario}", "select": "*"})
        return filas[0] if filas else None

    def guardar_perfil(self, usuario, nombre, preferencias=None):
        fila = {"usuario": usuario, "nombre": nombre, "actualizado_en": _ahora()}
        if preferencias is not None:
            fila["preferencias"] = preferencias_validas(preferencias)
        filas = self._rest("POST", "perfiles", params={"on_conflict": "usuario"}, json=fila,
                           prefer="resolution=merge-duplicates,return=representation")
        return filas[0]

    # ---------------- amigos y "He ido" ----------------
    # Los usuarios son correos: se usan en las consultas, pero a la app solo le llegan nombre y @alias.

    def guardar_alias(self, usuario, nombre, alias):
        """Guarda el @usuario (ya validado con validar_alias). ValueError si ya lo tiene otra persona."""
        try:
            self._rest("POST", "perfiles", params={"on_conflict": "usuario"},
                       json={"usuario": usuario, "nombre": nombre, "alias": alias, "actualizado_en": _ahora()},
                       prefer="resolution=merge-duplicates")
        except ErrorSupabase as e:
            if ": 409 " in str(e):   # unique (alias) de la tabla perfiles
                raise ValueError(f"El nombre de usuario @{alias} ya lo tiene otra persona.") from e
            raise

    def directorio(self, excepto, limite=1000):
        """Toda la gente con @alias menos `excepto`: [{usuario, nombre, alias}], para el buscador de amigos
        (filtra el navegador mientras se escribe). ponytail: con más de `limite` usuarios, buscar en el servidor."""
        return self._rest("GET", "perfiles", params={
            "alias": "not.is.null", "usuario": f"neq.{excepto}", "select": "usuario,nombre,alias",
            "order": "alias.asc", "limit": limite})

    def perfiles_de(self, usuarios):
        """{usuario: {nombre, alias, foto...}} de esos usuarios. Con "*" para no fallar si aún no existe la
        columna foto (006_fotos_perfil.sql): son datos del servidor, a la app solo le llegan nombre, alias y foto."""
        if not usuarios:
            return {}
        filas = self._rest("GET", "perfiles", params={"usuario": f"in.{_filtro_in(sorted(usuarios))}", "select": "*"})
        return {f["usuario"]: f for f in filas}

    def guardar_foto(self, usuario, nombre, foto):
        """Foto de perfil del usuario (la ven sus amigos): la de Google o una propia (subir_foto_perfil)."""
        if foto_valida(foto) is None:
            raise ValueError("Solo se guardan fotos de Google o subidas a la app.")
        self._rest("POST", "perfiles", params={"on_conflict": "usuario"}, prefer="resolution=merge-duplicates",
                   json={"usuario": usuario, "nombre": nombre, "foto": foto, "actualizado_en": _ahora()})

    def amistades_de(self, usuario):
        """Filas de amistades donde participa el usuario (enviadas, recibidas y aceptadas)."""
        u = _comillas(usuario)
        return self._rest("GET", "amistades", params={"or": f"(solicitante.eq.{u},destinatario.eq.{u})",
                                                      "select": "*", "order": "creado_en.desc"})

    def relaciones_de(self, usuario):
        """Amigos y solicitudes del usuario: [{usuario, nombre, alias, estado, enviada}], donde `usuario`
        es el otro (su correo, solo para las consultas) y `enviada` dice si la pidió el usuario."""
        filas = self.amistades_de(usuario)
        otros = [f["destinatario"] if f["solicitante"] == usuario else f["solicitante"] for f in filas]
        perfiles = self.perfiles_de(set(otros))
        return [{"usuario": otro, "nombre": perfiles.get(otro, {}).get("nombre"),
                 "alias": perfiles.get(otro, {}).get("alias"), "foto": foto_valida(perfiles.get(otro, {}).get("foto")),
                 "estado": f["estado"], "enviada": f["solicitante"] == usuario} for otro, f in zip(otros, filas)]

    def solicitar_amistad(self, de, a):
        """Envía una solicitud de `de` a `a`. Si `a` ya se la había enviado a `de`, se aceptan las
        dos. Devuelve el estado final: "pendiente" o "aceptada"."""
        if de == a:
            raise ValueError("No puedes añadirte a ti mismo.")
        existentes = self._rest("GET", "amistades", params={"or": _par(de, a), "select": "*"})
        for fila in existentes:
            if fila["estado"] == "pendiente" and fila["solicitante"] == a:
                self.responder_solicitud(de, a, aceptar=True)
                return "aceptada"
            return fila["estado"]
        self._rest("POST", "amistades", json={"solicitante": de, "destinatario": a})
        return "pendiente"

    def responder_solicitud(self, usuario, de, aceptar):
        """El usuario acepta o rechaza (borra) la solicitud que le envió `de`."""
        filtro = {"solicitante": f"eq.{de}", "destinatario": f"eq.{usuario}", "estado": "eq.pendiente"}
        if aceptar:
            self._rest("PATCH", "amistades", params=filtro, json={"estado": "aceptada"})
        else:
            self._rest("DELETE", "amistades", params=filtro)

    def quitar_amistad(self, usuario, otro):
        """Deja de ser amigo (o cancela una solicitud enviada), en cualquiera de los dos sentidos."""
        self._rest("DELETE", "amistades", params={"or": _par(usuario, otro)})

    def registrar_visita(self, usuario, restaurante_id, nota=None, comentario=None, fecha=None, anadido_por=None):
        """"He ido": una valoración por persona y restaurante; si ya existía, se actualiza. `fecha`: el día que
        fue (por defecto hoy; ver momento_visita). `anadido_por`: quién le invitó, al aceptar una invitación."""
        fila = {"usuario": usuario, "restaurante_id": int(restaurante_id), "nota": validar_nota(nota),
                "comentario": validar_comentario(comentario), "creado_en": momento_visita(fecha)}
        if anadido_por:   # solo entonces (la columna es de supabase/011_comensales.sql)
            fila["anadido_por"] = anadido_por
        self._rest("POST", "visitas", params={"on_conflict": "usuario,restaurante_id"},
                   prefer="resolution=merge-duplicates", json=fila)

    # ---------------- "He ido con..." (invitaciones; supabase/011_comensales.sql) ----------------

    def invitar_comensales(self, usuario, restaurante_id, amigos, fecha=None):
        """Pregunta a esos amigos si fueron con el usuario: hasta que no lo aceptan, no les sale nada en su perfil.
        Quien llama comprueba que son amigos suyos."""
        amigos = sorted(set(amigos) - {usuario})
        if amigos:
            dia = (fecha or datetime.now(timezone.utc).date()).isoformat()
            self._rest("POST", "invitaciones_visita", params={"on_conflict": "de,para,restaurante_id"},
                       prefer="resolution=merge-duplicates",
                       json=[{"de": usuario, "para": a, "restaurante_id": int(restaurante_id), "fecha": dia}
                             for a in amigos])

    def invitados_de(self, usuario, restaurante_id):
        """A quién ha invitado el usuario en ese restaurante y aún no ha contestado (correos)."""
        return [f["para"] for f in self._rest("GET", "invitaciones_visita", params={
            "de": f"eq.{usuario}", "restaurante_id": f"eq.{int(restaurante_id)}", "select": "para"})]

    def invitaciones_para(self, usuario):
        """Las que tiene que contestar el usuario, con el restaurante embebido (las últimas primero)."""
        return self._rest("GET", "invitaciones_visita", params={
            "para": f"eq.{usuario}", "order": "creado_en.desc",
            "select": "de,restaurante_id,fecha,restaurantes(id,datos)"})

    def borrar_invitacion(self, de, para, restaurante_id):
        self._rest("DELETE", "invitaciones_visita", params={"de": f"eq.{de}", "para": f"eq.{para}",
                                                            "restaurante_id": f"eq.{int(restaurante_id)}"})

    def aceptar_invitacion(self, usuario, de, restaurante_id, nota=None, comentario=None, fecha=None):
        """Sí, fue con `de`: se le guarda su visita (con su nota y su comentario; si ya la tenía, se actualiza esa
        misma: una sola entrada) y la invitación desaparece."""
        self.registrar_visita(usuario, restaurante_id, nota, comentario, fecha=fecha, anadido_por=de)
        self.borrar_invitacion(de, usuario, restaurante_id)

    def comensales_de(self, usuario, restaurante_id):
        """Los amigos (correos) que aceptaron que fueron con el usuario a ese restaurante."""
        return [f["usuario"] for f in self._rest("GET", "visitas", params={
            "anadido_por": f"eq.{usuario}", "restaurante_id": f"eq.{int(restaurante_id)}", "select": "usuario"})]

    def anadido_por(self, usuario, restaurante_id):
        """Con quién fue el usuario a ese restaurante, si aceptó una invitación suya (correo), o None."""
        filas = self._rest("GET", "visitas", params={"usuario": f"eq.{usuario}", "restaurante_id": f"eq.{int(restaurante_id)}",
                                                     "anadido_por": "not.is.null", "select": "anadido_por"})
        return filas[0]["anadido_por"] if filas else None

    def quitar_visita(self, usuario, restaurante_id):
        self._rest("DELETE", "visitas", params={"usuario": f"eq.{usuario}",
                                                "restaurante_id": f"eq.{int(restaurante_id)}"})

    def visitas_de(self, usuarios, limite=10, desde=None):
        """Últimas visitas de esos usuarios (solo las de `desde` en adelante, si se da: un datetime con zona
        horaria), con su restaurante del catálogo embebido."""
        if not usuarios:
            return []
        params = {"usuario": f"in.{_filtro_in(sorted(usuarios))}", "order": "creado_en.desc", "limit": limite,
                  "select": "usuario,nota,comentario,creado_en,restaurantes(id,datos,imagen)"}
        if desde is not None:
            params["creado_en"] = f"gte.{desde.isoformat()}"
        return self._rest("GET", "visitas", params=params)

    # ---------------- eatlist (los que quieres probar, en orden) ----------------

    def eatlist_de(self, usuario):
        return self._rest("GET", "eatlist", params={"usuario": f"eq.{usuario}", "order": "posicion.asc",
                                                    "select": "posicion,restaurantes(id,datos,imagen)"})

    def guardar_eatlist(self, usuario, ids):
        """Deja la eatlist del usuario con esos restaurantes y en ese orden (el primero, el nº 1)."""
        ids = list(dict.fromkeys(int(i) for i in ids))
        if ids:
            self._rest("POST", "eatlist", params={"on_conflict": "usuario,restaurante_id"},
                       prefer="resolution=merge-duplicates",
                       json=[{"usuario": usuario, "restaurante_id": i, "posicion": n} for n, i in enumerate(ids, 1)])
        sobran = {"usuario": f"eq.{usuario}"}
        if ids:
            sobran["restaurante_id"] = f"not.in.({','.join(map(str, ids))})"
        self._rest("DELETE", "eatlist", params=sobran)

    # ---------------- catálogo compartido ----------------

    def todos_los_restaurantes(self):
        """(maestro, df_platos) con TODO el catálogo compartido (opción "Todos los restaurantes")."""
        filas, desde = [], 0
        while True:   # PostgREST devuelve como mucho 1000 filas por petición
            lote = self._rest("GET", "restaurantes", params={
                "select": "id,datos,platos,imagen", "order": "id.asc", "limit": 1000, "offset": desde})
            filas += lote
            if len(lote) < 1000:
                break
            desde += 1000
        return filas_a_dataframes([{"posicion": i, "restaurantes": f} for i, f in enumerate(filas)])

    def restaurantes_por_clave(self, claves):
        """{clave: fila del catálogo} para las claves que ya existen."""
        encontrados = {}
        for lote in _lotes(sorted({c for c in claves if c})):
            for fila in self._rest("GET", "restaurantes", params={
                    "clave": f"in.{_filtro_in(lote)}", "select": "id,clave,datos,platos,imagen"}):
                encontrados[fila["clave"]] = fila
        return encontrados

    def guardar_restaurantes(self, filas):
        """Crea o actualiza restaurantes del catálogo (por clave). Cada fila: {clave, datos,
        platos, imagen}. Devuelve {clave: id}."""
        ids = {}
        for lote in _lotes([{**f, "actualizado_en": _ahora()} for f in filas]):
            guardadas = self._rest("POST", "restaurantes", params={"on_conflict": "clave"}, json=lote,
                                   prefer="resolution=merge-duplicates,return=representation")
            ids.update({g["clave"]: g["id"] for g in guardadas})
        return ids

    def restaurantes_por_ids(self, ids):
        """(maestro, df_platos) de esos restaurantes del catálogo."""
        filas = []
        for lote in _lotes(sorted({int(i) for i in ids})):
            filas += self._rest("GET", "restaurantes", params={"id": f"in.({','.join(map(str, lote))})",
                                                               "select": "id,datos,platos,imagen"})
        return filas_a_dataframes([{"posicion": i, "restaurantes": f} for i, f in enumerate(filas)])

    # ---------------- explorar: lugares de Overture (supabase/009_lugares.sql) ----------------

    def con_ficha_rapida(self):
        """¿Está ya supabase/012_ficha_rapida.sql? (se mira una vez): sin ella, todo funciona como antes."""
        if getattr(self, "_con_ficha", None) is None:
            try:
                self._rest("GET", "lugares", params={"select": "ficha_en", "limit": 1})
                self._con_ficha = True
            except ErrorSupabase:
                self._con_ficha = False
        return self._con_ficha

    def _columnas_lugar(self):
        return COLUMNAS_LUGAR + ("," + COLUMNAS_FICHA if self.con_ficha_rapida() else "")

    def buscar_lugares(self, texto="", cerca=None, radio_km=2.0, limite=200):
        """Lugares cuyo nombre lleva las palabras de `texto` (en ese orden) y/o dentro del cuadrado de
        `radio_km` alrededor de `cerca` (lat, lon). Sin ordenar por distancia: eso lo hace quien llama."""
        palabras = texto_busqueda(texto).split()
        if not palabras and not cerca:
            return []
        params = {"select": self._columnas_lugar(), "limit": limite, "order": "confianza.desc.nullslast",
                  "estado_analisis": "neq.cerrado"}
        if palabras:
            params["nombre_busqueda"] = "ilike.*" + "*".join(palabras) + "*"
        if cerca:
            a, b, c, d = caja_alrededor(cerca[0], cerca[1], radio_km)
            params["and"] = f"(lat.gte.{a:.6f},lat.lte.{b:.6f},lon.gte.{c:.6f},lon.lte.{d:.6f})"
        return self._rest("GET", "lugares", params=params)

    def guardar_lugares(self, filas, tamano=1000):
        """Crea o actualiza lugares por id. Todas las filas de una llamada con las mismas columnas."""
        for lote in _lotes(filas, tamano):
            self._rest("POST", "lugares", params={"on_conflict": "id"}, json=lote,
                       prefer="resolution=merge-duplicates")

    def pedir_analisis(self, usuario, lugar_id):
        """Apunta que el usuario quiere ese sitio analizado y lo deja en la cola (si no estaba ya en ella o hecho)."""
        self._rest("POST", "solicitudes_analisis", params={"on_conflict": "lugar_id,usuario"},
                   prefer="resolution=ignore-duplicates", json={"lugar_id": lugar_id, "usuario": usuario})
        self._rest("PATCH", "lugares", params={"id": f"eq.{lugar_id}", "estado_analisis": "in.(sin_analizar,error)"},
                   json={"estado_analisis": "pendiente", "mensaje": None, "actualizado_en": _ahora()})

    def solicitudes_de(self, usuario, limite=20):
        """Los sitios que ha pedido analizar el usuario (los últimos primero), con su lugar embebido."""
        return self._rest("GET", "solicitudes_analisis", params={
            "usuario": f"eq.{usuario}", "order": "creado_en.desc", "limit": limite,
            "select": f"creado_en,lugares({COLUMNAS_LUGAR})"})

    def lugares_pendientes(self, limite=50):
        """Los que hay que analizar: primero los que más gente ha pedido y, a igualdad, los más antiguos."""
        lugares = self._rest("GET", "lugares", params={"estado_analisis": "eq.pendiente", "select": COLUMNAS_LUGAR,
                                                       "order": "actualizado_en.asc", "limit": limite})
        if not lugares:
            return []
        pedidas = self._rest("GET", "solicitudes_analisis", params={
            "lugar_id": f"in.{_filtro_in([l['id'] for l in lugares])}", "select": "lugar_id"})
        cuantos = Counter(p["lugar_id"] for p in pedidas)
        return sorted(lugares, key=lambda l: -cuantos[l["id"]])

    # ---------------- Explorar al día (supabase/010_lugares_al_dia.sql) ----------------

    def lugares_a_verificar(self, limite=60, dias=DIAS_ENTRE_VERIFICACIONES):
        """Los que toca mirar en Google Maps: los que aún no tienen ficha rápida y los comprobados hace más de
        `dias`; primero los más viejos."""
        hace = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        if self.con_ficha_rapida():
            filtro, orden = f"(ficha_en.is.null,verificado_en.lt.{hace})", "ficha_en.asc.nullsfirst"
        else:
            filtro, orden = f"(verificado_en.is.null,verificado_en.lt.{hace})", "verificado_en.asc.nullsfirst"
        return self._rest("GET", "lugares", params={"select": "id,nombre,lat,lon", "estado_analisis": "neq.cerrado",
                                                    "limit": limite, "or": filtro, "order": orden})

    def quedan_sin_ficha(self):
        """¿Queda algún sitio abierto sin ficha rápida? (para encadenar la carga inicial en GitHub Actions)"""
        return self.con_ficha_rapida() and bool(self._rest("GET", "lugares", params={
            "select": "id", "ficha_en": "is.null", "estado_analisis": "neq.cerrado", "limit": 1}))

    def marcar_verificado(self, lugar_id, cerrado=False, ficha=None):
        """Apunta que se ha mirado en Google Maps; si ha cerrado, lo oculta. `ficha`: {nota_google, cocina_google,
        foto} leídos de su ficha (solo si es el mismo sitio)."""
        cambios = {"verificado_en": _ahora()}
        if self.con_ficha_rapida():
            cambios["ficha_en"] = cambios["verificado_en"]
            cambios.update(ficha or {})
        if cerrado:
            cambios.update(estado_analisis="cerrado", mensaje="Cerrado permanentemente según Google Maps")
        self._rest("PATCH", "lugares", params={"id": f"eq.{lugar_id}"}, json=cambios)

    def lugares_para_analizar(self, limite=1):
        """Los siguientes a analizar por adelantado: sin analizar y con ficha rápida, los mejor valorados primero."""
        return self._rest("GET", "lugares", params={
            "select": COLUMNAS_LUGAR, "estado_analisis": "eq.sin_analizar", "restaurante_id": "is.null",
            "nota_google": "not.is.null", "order": "nota_google.desc", "limit": limite})

    # ---------------- "Todos los restaurantes" por zona y espacio (supabase/012_ficha_rapida.sql) ----------------

    def restaurantes_cerca(self, lat, lon, radio_km, limite=3000):
        """(maestro, df_platos) de los restaurantes del catálogo dentro del cuadrado de `radio_km` alrededor."""
        a, b, c, d = caja_alrededor(lat, lon, radio_km)
        filas = self._rest("GET", "restaurantes", params={
            "select": "id,datos,platos,imagen", "limit": limite,
            "and": f"(lat.gte.{a:.6f},lat.lte.{b:.6f},lon.gte.{c:.6f},lon.lte.{d:.6f})"})
        return filas_a_dataframes([{"posicion": i, "restaurantes": f} for i, f in enumerate(filas)])

    def cocinas_del_catalogo(self):
        """(cocinas distintas, nº de restaurantes) de todo el catálogo, sin bajarse sus datos."""
        cocinas, total, desde = set(), 0, 0
        while True:   # PostgREST devuelve como mucho 1000 filas por petición
            lote = self._rest("GET", "restaurantes", params={"select": "cocina", "order": "id.asc",
                                                             "limit": 1000, "offset": desde})
            cocinas.update(f["cocina"] for f in lote if f.get("cocina"))
            total += len(lote)
            if len(lote) < 1000:
                return sorted(cocinas), total
            desde += 1000

    def tamano(self):
        """{qué: bytes} de la base de datos, cada tabla y las fotos."""
        r = requests.post(f"{self.url}/rest/v1/rpc/tamano_bd", headers=self._cabeceras, json={}, timeout=TIMEOUT_S)
        if not r.ok:
            raise ErrorSupabase(f"tamano_bd: {r.status_code} {r.text[:200]}")
        return {f["que"]: f["bytes"] for f in r.json()}

    def avisar_cerrado(self, lugar_id):
        """Un usuario avisa de que ha cerrado: deja de salir en Explorar para todos."""
        self._rest("PATCH", "lugares", params={"id": f"eq.{lugar_id}"},
                   json={"estado_analisis": "cerrado", "mensaje": "Avisado por un usuario", "actualizado_en": _ahora()})

    def cerrar_lugares(self, ids, mensaje):
        """Marca como cerrados esos lugares (los que existan); para el importador."""
        for lote in _lotes(sorted(ids)):
            self._rest("PATCH", "lugares", params={"id": f"in.{_filtro_in(lote)}"},
                       json={"estado_analisis": "cerrado", "mensaje": mensaje, "actualizado_en": _ahora()})

    def estados_de_lugares_en(self, caja):
        """{id: estado_analisis} de todos los lugares dentro de la caja (oeste, sur, este, norte)."""
        oeste, sur, este, norte = caja
        estados, desde = {}, 0
        while True:   # PostgREST devuelve como mucho 1000 filas por petición
            lote = self._rest("GET", "lugares", params={
                "select": "id,estado_analisis", "order": "id.asc", "limit": 1000, "offset": desde,
                "and": f"(lat.gte.{sur},lat.lte.{norte},lon.gte.{oeste},lon.lte.{este})"})
            estados.update({f["id"]: f["estado_analisis"] for f in lote})
            if len(lote) < 1000:
                return estados
            desde += 1000

    def lugar_por_id(self, lugar_id):
        filas = self._rest("GET", "lugares", params={"id": f"eq.{lugar_id}", "select": COLUMNAS_LUGAR})
        return filas[0] if filas else None

    def rescatar_interrumpidos(self):
        """Vuelve a "pendiente" lo que se quedó en "procesando" (el ordenador se apagó a medias). Devuelve cuántos."""
        cambios = {"mensaje": "interrumpido; se volverá a intentar", "actualizado_en": _ahora()}
        listas = self._rest("PATCH", "listas", params={"estado": "eq.procesando"}, json={"estado": "pendiente", **cambios},
                            prefer="return=representation")
        lugares = self._rest("PATCH", "lugares", params={"estado_analisis": "eq.procesando"},
                             json={"estado_analisis": "pendiente", **cambios}, prefer="return=representation")
        return len(listas or []) + len(lugares or [])

    def marcar_lugar(self, lugar_id, estado, restaurante_id=None, mensaje=None):
        cambios = {"estado_analisis": estado, "mensaje": mensaje, "actualizado_en": _ahora()}
        if restaurante_id is not None:
            cambios["restaurante_id"] = int(restaurante_id)
        self._rest("PATCH", "lugares", params={"id": f"eq.{lugar_id}"}, json=cambios)

    # ---------------- fotos ----------------

    def subir_foto(self, archivo, contenido):
        r = requests.post(f"{self.url}/storage/v1/object/{BUCKET_FOTOS}/{urllib.parse.quote(archivo)}",
                          data=contenido, timeout=TIMEOUT_S,
                          headers={**self._cabeceras, "Content-Type": "image/jpeg", "x-upsert": "true"})
        if not r.ok:
            raise ErrorSupabase(f"subir foto {archivo}: {r.status_code} {r.text[:200]}")

    def subir_foto_perfil(self, usuario, nombre, contenido, anterior=None):
        """Sube una foto propia (ya preparada aquí: cuadrada, pequeña y sin metadatos) y la pone en el perfil.
        El nombre del archivo es aleatorio; si había otra propia, se borra. Devuelve la URL."""
        archivo = f"perfiles/{uuid.uuid4().hex}.jpg"
        self.subir_foto(archivo, preparar_foto_perfil(contenido))
        url = self.url_foto(archivo)
        self.guardar_foto(usuario, nombre, url)
        self._borrar_foto_propia(anterior)
        return url

    def quitar_foto_perfil(self, usuario, nombre, anterior=None):
        """Sin foto propia: se ve la de Google (si entra con Google) o la inicial."""
        self._rest("POST", "perfiles", params={"on_conflict": "usuario"}, prefer="resolution=merge-duplicates",
                   json={"usuario": usuario, "nombre": nombre, "foto": None, "actualizado_en": _ahora()})
        self._borrar_foto_propia(anterior)

    def _borrar_foto_propia(self, url):
        if not es_foto_propia(url):
            return
        archivo = url.split(f"/public/{BUCKET_FOTOS}/", 1)[1]
        try:
            requests.delete(f"{self.url}/storage/v1/object/{BUCKET_FOTOS}/{archivo}", headers=self._cabeceras,
                            timeout=TIMEOUT_S)
        except requests.RequestException:
            pass   # solo queda un archivo sin usar en el almacenamiento: no merece fallar por eso

    def url_foto(self, archivo):
        return url_foto(self.url, archivo)
