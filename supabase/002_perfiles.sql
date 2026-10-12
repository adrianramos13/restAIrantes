-- Datos personales de cada usuario (menú de usuario -> "Datos personales").
-- Si ya ejecutaste esquema.sql antes de que existiera esta tabla, ejecuta SOLO este archivo:
-- Supabase -> SQL Editor -> pega el contenido -> Run.

create table if not exists perfiles (
    usuario         text primary key,                 -- correo de Google (no se puede cambiar)
    nombre          text not null check (char_length(nombre) between 1 and 40),
    actualizado_en  timestamptz not null default now()
);

-- Como las demás tablas: sin políticas, solo la clave de servicio (servidor) puede leer y escribir.
alter table perfiles enable row level security;
