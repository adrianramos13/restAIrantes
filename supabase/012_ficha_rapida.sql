-- Ficha rápida para todos los sitios de Descubrir, "Todos los restaurantes" por zona y medir el espacio.
-- Ejecútalo UNA vez en Supabase (SQL Editor -> pega todo -> Run), después de 011_comensales.sql.

-- 1) Lo que se ve sin sesión en la ficha de Google Maps, que verificar_lugares.py guarda de cada sitio:
--    nota, tipo de cocina y una foto pequeña (en el almacenamiento: fotos/lugares/<id>.jpg).
alter table lugares add column if not exists nota_google real;
alter table lugares add column if not exists cocina_google text;
alter table lugares add column if not exists foto text;
alter table lugares add column if not exists ficha_en timestamptz;   -- última vez que se leyó su ficha
create index if not exists lugares_por_ficha on lugares (ficha_en asc nulls first) where estado_analisis <> 'cerrado';
-- los que se analizan por adelantado: primero los mejor valorados
create index if not exists lugares_para_analizar on lugares (nota_google desc)
    where estado_analisis = 'sin_analizar' and restaurante_id is null;

-- 2) Coordenadas y cocina de cada restaurante analizado como columnas (salen solas de `datos`): así "Comer hoy ->
--    Todos los restaurantes" pide solo los de tu zona en vez de descargar el catálogo entero.
alter table restaurantes add column if not exists lat double precision
    generated always as (nullif(datos->>'Latitud', '')::double precision) stored;
alter table restaurantes add column if not exists lon double precision
    generated always as (nullif(datos->>'Longitud', '')::double precision) stored;
alter table restaurantes add column if not exists cocina text
    generated always as (datos->>'Categoría (Jev)') stored;
create index if not exists restaurantes_lat_lon on restaurantes (lat, lon);

-- 3) Cuánto ocupa cada cosa (obtener_datos/espacio.py). Solo para la clave de servicio.
create or replace function tamano_bd() returns table (que text, bytes bigint)
language sql security definer set search_path = public, storage as $$
    select 'base de datos', pg_database_size(current_database())
    union all
    select 'tabla ' || relname, pg_total_relation_size(relid) from pg_catalog.pg_statio_user_tables
    where schemaname = 'public'
    union all
    select 'fotos', coalesce(sum((metadata->>'size')::bigint), 0) from storage.objects where bucket_id = 'fotos'
$$;
revoke execute on function tamano_bd() from public, anon, authenticated;
grant execute on function tamano_bd() to service_role;
