-- "He ido" con medias estrellas y comentario, y UNA valoración por persona y restaurante (volver a
-- guardarla la actualiza). Ejecútalo una vez: Supabase -> SQL Editor -> pega el contenido -> Run.
-- (Necesita 004_amigos.sql.)

-- Si alguien marcó el mismo sitio varias veces, se queda la última.
delete from visitas a using visitas b
where a.usuario = b.usuario and a.restaurante_id = b.restaurante_id and a.id < b.id;

alter table visitas drop constraint if exists visitas_unica;
alter table visitas add constraint visitas_unica unique (usuario, restaurante_id);

-- Nota de 0,5 a 5 en pasos de media estrella.
alter table visitas drop constraint if exists visitas_nota_check;
alter table visitas alter column nota type numeric(2, 1);
alter table visitas add constraint visitas_nota_check check (nota between 0.5 and 5 and nota * 2 = round(nota * 2));

-- Lo que más te gustó (opcional).
alter table visitas add column if not exists comentario text check (char_length(comentario) <= 280);
