-- "De dónde eres" (Ajustes de usuario) para "Te recomendamos ir a cenar con" de Inicio: gente que vive cerca.
-- Ejecútalo UNA vez en Supabase: SQL Editor -> pega todo -> Run. Hasta entonces la app funciona igual, solo
-- que no se puede guardar la zona y las sugerencias son solo amigos de amigos.

alter table perfiles add column if not exists zona     text check (char_length(zona) <= 120);
alter table perfiles add column if not exists zona_lat double precision;
alter table perfiles add column if not exists zona_lon double precision;

create index if not exists perfiles_zona on perfiles (zona_lat, zona_lon) where zona_lat is not null;
