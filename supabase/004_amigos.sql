-- Amigos y "He ido". Ejecútalo una vez: Supabase -> SQL Editor -> pega el contenido -> Run.
-- (Necesita la tabla perfiles: 002_perfiles.sql o esquema.sql.)

-- Nombre de usuario público (@ana_g) para que los amigos te encuentren sin ver tu correo.
alter table perfiles add column if not exists alias text unique
    check (alias ~ '^[a-z0-9_.]{3,20}$');

-- Solicitudes de amistad: "pendiente" hasta que el destinatario la acepta; rechazar o quitar
-- un amigo borra la fila. Los usuarios son correos (como en listas y perfiles): nunca se enseñan.
create table if not exists amistades (
    solicitante   text not null,
    destinatario  text not null,
    estado        text not null default 'pendiente' check (estado in ('pendiente', 'aceptada')),
    creado_en     timestamptz not null default now(),
    primary key (solicitante, destinatario),
    check (solicitante <> destinatario)
);
create index if not exists amistades_destinatario on amistades (destinatario);

-- Botón "He ido" de la ficha: lo que ven tus amigos en su Inicio.
create table if not exists visitas (
    id              bigint generated always as identity primary key,
    usuario         text not null,
    restaurante_id  bigint not null references restaurantes(id) on delete cascade,
    nota            smallint check (nota between 1 and 5),
    creado_en       timestamptz not null default now()
);
create index if not exists visitas_usuario_fecha on visitas (usuario, creado_en desc);

-- Como las demás tablas: sin políticas, solo la clave de servicio (servidor) puede leer y escribir.
alter table amistades enable row level security;
alter table visitas enable row level security;
