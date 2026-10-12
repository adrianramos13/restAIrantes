-- Esquema de la base de datos (Supabase / Postgres) para el modo multiusuario.
-- Ejecútalo UNA vez en Supabase: panel del proyecto -> SQL Editor -> pega todo -> Run.
--
-- Seguridad: las tablas tienen Row Level Security activado y NINGUNA política, así que la
-- clave pública ("anon") no puede leer ni escribir nada. La app y el procesador usan la clave
-- de servicio desde el servidor / tu ordenador (nunca llega al navegador) y filtran por
-- usuario en el código.

-- Catálogo COMPARTIDO de restaurantes: si dos usuarios tienen el mismo restaurante, sus datos,
-- reseñas y clasificación de Jev se calculan una sola vez.
create table if not exists restaurantes (
    id              bigint generated always as identity primary key,
    clave           text not null unique,             -- nombre normalizado (datos.clave_restaurante)
    datos           jsonb not null,                   -- las mismas columnas que clasificacion_jev.xlsx
    platos          jsonb not null default '[]',      -- [{"Plato": "...", "Sentimiento": "Buena"}, ...]
    imagen          text,                             -- archivo dentro del bucket "fotos"
    actualizado_en  timestamptz not null default now()
);

-- Una lista por usuario (su correo de Google) y su estado de procesado.
create table if not exists listas (
    id              bigint generated always as identity primary key,
    usuario         text not null unique,
    enlace          text,
    estado          text not null default 'sin_lista'
                    check (estado in ('sin_lista', 'pendiente', 'procesando', 'lista', 'error')),
    mensaje         text,
    actualizado_en  timestamptz not null default now()
);

-- Qué restaurantes tiene cada lista, en el orden de Google Maps.
create table if not exists lista_restaurantes (
    lista_id        bigint not null references listas(id) on delete cascade,
    restaurante_id  bigint not null references restaurantes(id) on delete cascade,
    posicion        integer not null,
    primary key (lista_id, restaurante_id)
);

alter table restaurantes enable row level security;
alter table listas enable row level security;
alter table lista_restaurantes enable row level security;

-- Datos personales (menú de usuario -> "Datos personales"). También en 002_perfiles.sql, para
-- quien ya hubiera ejecutado este archivo antes de que existiera la tabla.
create table if not exists perfiles (
    usuario         text primary key,
    nombre          text not null check (char_length(nombre) between 1 and 40),
    actualizado_en  timestamptz not null default now()
);
alter table perfiles enable row level security;

-- Fotos de los restaurantes: bucket público (son las fotos públicas de Google Maps).
insert into storage.buckets (id, name, public)
values ('fotos', 'fotos', true)
on conflict (id) do nothing;
