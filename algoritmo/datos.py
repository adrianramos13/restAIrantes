"""
Base de datos del modo multiusuario (Supabase), sin Streamlit: la usan la app (algoritmo/app.py),
el procesador de listas (obtener_datos/procesar_solicitudes.py) y la migración inicial.

Habla con la API REST de Supabase (PostgREST y Storage) con `requests` y la clave de servicio:
SOLO desde el servidor de Streamlit o tu ordenador, nunca en el navegador. Las tablas están en
supabase/esquema.sql.
"""

import math
import re
import unicodedata
import urllib.parse
from datetime import datetime, timezone

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


ALIAS_VALIDO = re.compile(r"^[a-z0-9_.]{3,20}$")   # el mismo check que la tabla perfiles


def validar_alias(alias):
    """@usuario elegido por el usuario -> el que se guarda (sin @, en minúsculas). ValueError si no vale."""
    alias = (alias or "").strip().lstrip("@").lower()
    if not ALIAS_VALIDO.match(alias):
        raise ValueError("El nombre de usuario debe tener de 3 a 20 caracteres: letras sin tildes, números, "
                         "'_' o '.'.")
    return alias


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
                      "Fecha visita": v["creado_en"]})
    return pd.DataFrame(filas)


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

    def buscar_usuarios(self, texto, excepto, limite=10):
        """Usuarios con @alias cuyo alias o nombre contiene `texto`: [{usuario, nombre, alias}]."""
        texto = re.sub(r"[^\w .]", "", (texto or "").lstrip("@")).strip()   # nada de comas, comillas o paréntesis
        if len(texto) < 2:
            return []
        patron = _comillas(f"*{texto}*")
        return self._rest("GET", "perfiles", params={
            "or": f"(alias.ilike.{patron},nombre.ilike.{patron})", "alias": "not.is.null",
            "usuario": f"neq.{excepto}", "select": "usuario,nombre,alias", "order": "alias.asc", "limit": limite})

    def perfiles_de(self, usuarios):
        """{usuario: {nombre, alias}} de esos usuarios."""
        if not usuarios:
            return {}
        filas = self._rest("GET", "perfiles", params={"usuario": f"in.{_filtro_in(sorted(usuarios))}",
                                                      "select": "usuario,nombre,alias"})
        return {f["usuario"]: f for f in filas}

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
                 "alias": perfiles.get(otro, {}).get("alias"), "estado": f["estado"],
                 "enviada": f["solicitante"] == usuario} for otro, f in zip(otros, filas)]

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

    def registrar_visita(self, usuario, restaurante_id, nota=None):
        if nota is not None and not (isinstance(nota, int) and 1 <= nota <= 5):
            raise ValueError("La nota tiene que ir de 1 a 5.")
        self._rest("POST", "visitas", json={"usuario": usuario, "restaurante_id": int(restaurante_id), "nota": nota})

    def visitas_de(self, usuarios, limite=10):
        """Últimas visitas de esos usuarios, con su restaurante del catálogo embebido."""
        if not usuarios:
            return []
        return self._rest("GET", "visitas", params={
            "usuario": f"in.{_filtro_in(sorted(usuarios))}", "order": "creado_en.desc", "limit": limite,
            "select": "usuario,nota,creado_en,restaurantes(id,datos,imagen)"})

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

    # ---------------- fotos ----------------

    def subir_foto(self, archivo, contenido):
        r = requests.post(f"{self.url}/storage/v1/object/{BUCKET_FOTOS}/{urllib.parse.quote(archivo)}",
                          data=contenido, timeout=TIMEOUT_S,
                          headers={**self._cabeceras, "Content-Type": "image/jpeg", "x-upsert": "true"})
        if not r.ok:
            raise ErrorSupabase(f"subir foto {archivo}: {r.status_code} {r.text[:200]}")

    def url_foto(self, archivo):
        return url_foto(self.url, archivo)
