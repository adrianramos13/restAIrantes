-- Explorar: cualquier restaurante, bar o cafetería (datos abiertos de Overture Maps), aunque no esté en
-- ninguna lista. Ejecútalo UNA vez en Supabase: SQL Editor -> pega todo -> Run. Luego importa una zona:
--     python obtener_datos/importar_overture.py --zona madrid
--
-- "lugares" es el mapa ligero (solo columnas con tipo, sin jsonb): sirve para buscar y ver lo básico.
-- Cuando alguien pide analizarlo, el procesador saca de Google Maps nota, precio, foto y reseñas, lo
-- clasifica con Jev y lo guarda en "restaurantes" (el catálogo de siempre); restaurante_id los enlaza.

create extension if not exists pg_trgm;

create table if not exists lugares (
    id                text primary key,                 -- id de Overture
    nombre            text not null,
    nombre_busqueda   text not null,                    -- minúsculas, sin tildes (datos.texto_busqueda)
    categoria         text,                             -- ya en español (importar_overture.etiqueta_categoria)
    lat               double precision not null,
    lon               double precision not null,
    direccion         text,
    ciudad            text,
    pais              text,
    web               text,
    telefono          text,
    confianza         real,
    estado_analisis   text not null default 'sin_analizar'
                      check (estado_analisis in ('sin_analizar', 'pendiente', 'procesando', 'analizado', 'error')),
    mensaje           text,
    restaurante_id    bigint references restaurantes(id) on delete set null,
    actualizado_en    timestamptz not null default now()
);

-- Buscar por nombre ("ilike *texto*") y por zona (lat/lon entre dos valores).
create index if not exists lugares_nombre_trgm on lugares using gin (nombre_busqueda gin_trgm_ops);
create index if not exists lugares_lat_lon on lugares (lat, lon);
create index if not exists lugares_pendientes on lugares (estado_analisis) where estado_analisis = 'pendiente';

-- Quién ha pedido analizar cada sitio (el procesador empieza por los más pedidos).
create table if not exists solicitudes_analisis (
    lugar_id    text not null references lugares(id) on delete cascade,
    usuario     text not null,
    creado_en   timestamptz not null default now(),
    primary key (lugar_id, usuario)
);
create index if not exists solicitudes_analisis_usuario on solicitudes_analisis (usuario, creado_en desc);

alter table lugares enable row level security;
alter table solicitudes_analisis enable row level security;
