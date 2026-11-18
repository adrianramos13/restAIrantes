-- Cuándo entró cada restaurante en tu lista (ficha: «En tu lista desde…»; lista: filtro por fecha).
-- Ejecútalo UNA vez en Supabase (SQL Editor -> pega todo -> Run). Solo añade una columna: no cambia nada de lo que hay.
-- Los que ya estaban se quedan sin fecha (no se sabe), salvo los que te gustaron en Food match, que la toman de ahí.
-- Al volver a sincronizar la lista de Google Maps, los que ya estaban conservan su fecha (datos.reemplazar_lista).

alter table lista_restaurantes add column if not exists anadido_en timestamptz;
alter table lista_restaurantes alter column anadido_en set default now();

do $$
begin
    if to_regclass('public.deslizados') is not null then
        update lista_restaurantes lr set anadido_en = d.creado_en
        from listas l, deslizados d
        where lr.anadido_en is null and l.id = lr.lista_id and d.usuario = l.usuario
          and d.restaurante_id = lr.restaurante_id and d.gusta;
    end if;
end $$;
