-- «Food match» (Comer hoy): restaurantes que se deslizan, a la derecha (te gusta: entra en tu lista) o a la
-- izquierda (no te gusta: no vuelve a salir). Una fila por restaurante deslizado; sirve para no repetir tarjetas
-- y para que lo que añadiste deslizando no se pierda al volver a sincronizar tu lista de Google Maps.
-- Ejecútalo UNA vez en Supabase: SQL Editor -> pega todo -> Run. Hasta entonces el botón no aparece.

create table if not exists deslizados (
    usuario         text not null,
    restaurante_id  bigint not null references restaurantes(id) on delete cascade,
    gusta           boolean not null,
    creado_en       timestamptz not null default now(),
    primary key (usuario, restaurante_id)
);

-- Como las demás tablas: sin políticas, solo la clave de servicio (servidor) puede leer y escribir.
alter table deslizados enable row level security;
