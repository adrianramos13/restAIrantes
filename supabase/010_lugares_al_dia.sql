-- Explorar al día: los sitios cerrados dejan de enseñarse y se apunta cuándo se comprobó cada uno en Google
-- Maps (obtener_datos/verificar_lugares.py, que lo hace solo en GitHub Actions). Ejecútalo UNA vez en Supabase
-- (SQL Editor -> pega todo -> Run), después de 009_lugares.sql.

alter table lugares drop constraint if exists lugares_estado_analisis_check;
alter table lugares add constraint lugares_estado_analisis_check
    check (estado_analisis in ('sin_analizar', 'pendiente', 'procesando', 'analizado', 'error', 'cerrado'));

alter table lugares add column if not exists verificado_en timestamptz;   -- última comprobación en Google Maps

create index if not exists lugares_por_verificar on lugares (verificado_en asc nulls first)
    where estado_analisis <> 'cerrado';
