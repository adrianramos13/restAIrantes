-- Foto de perfil propia (Perfil -> Datos personales): además de la de Google, la que sube cada uno, guardada
-- en el almacenamiento de Supabase (bucket "fotos", carpeta perfiles/). Ejecútalo una vez, después de
-- 006_fotos_perfil.sql: Supabase -> SQL Editor -> pega el contenido -> Run.

alter table perfiles drop constraint if exists perfiles_foto_check;
alter table perfiles add constraint perfiles_foto_check check (
    char_length(foto) <= 500 and (
        foto ~ '^https://[a-z0-9.-]+[.]googleusercontent[.]com/'
        or foto ~ '^https://[a-z0-9-]+[.]supabase[.]co/storage/v1/object/public/fotos/perfiles/[0-9a-f]{32}[.]jpg$'
    )
);
