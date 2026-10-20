-- Eatlist: los restaurantes a los que quieres ir, en tu orden de preferencia (1 = el que más). Se añade desde
-- la ficha de cada restaurante eligiendo el puesto. Ejecútalo una vez: Supabase -> SQL Editor -> pega -> Run.

create table if not exists eatlist (
    usuario         text not null,
    restaurante_id  bigint not null references restaurantes(id) on delete cascade,
    posicion        integer not null check (posicion >= 1),
    creado_en       timestamptz not null default now(),
    primary key (usuario, restaurante_id)
);
create index if not exists eatlist_usuario_posicion on eatlist (usuario, posicion);

-- Como las demás tablas: sin políticas, solo la clave de servicio (servidor) puede leer y escribir.
alter table eatlist enable row level security;
