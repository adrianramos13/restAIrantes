-- Más fotos por restaurante (carrusel de la ficha): la principal a 800 px + 3 de «Comida y bebida» + 1 de
-- «Ambiente» de su galería de Google Maps, en Cloudflare R2 (restaurantes/<id>/1.jpg ... 5.jpg). Las saca el
-- procesador con la sesión de Google (sin sesión, Google solo enseña una foto), a la vez que analiza.
-- Ejecútalo UNA vez en Supabase (SQL Editor -> pega todo -> Run). Solo añade columnas: no cambia nada de lo que hay.
-- Hasta entonces el procesador no busca fotos y la ficha enseña solo la foto de siempre.

alter table restaurantes add column if not exists fotos jsonb;            -- ["restaurantes/7/1.jpg", ...]
alter table restaurantes add column if not exists fotos_en timestamptz;   -- cuándo se buscaron (aunque no hubiera)
create index if not exists restaurantes_sin_fotos on restaurantes (id) where fotos_en is null;
