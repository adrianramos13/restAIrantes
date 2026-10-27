-- "He ido con...": al guardar tu visita puedes decir con qué amigos fuiste. A cada uno le llega una invitación
-- (invitaciones_visita) y no le sale nada en su perfil hasta que la acepta: entonces pone sus estrellas y su
-- comentario y se le guarda UNA visita suya, con anadido_por = quien le invitó. Si la rechaza, se borra.
-- Ejecútalo en Supabase (SQL Editor -> pega todo -> Run). Se puede volver a ejecutar sin problema.

alter table visitas add column if not exists anadido_por text;
create index if not exists visitas_anadido_por on visitas (anadido_por, restaurante_id) where anadido_por is not null;

create table if not exists invitaciones_visita (
    de              text not null,                    -- quien dice que fuisteis juntos
    para            text not null,                    -- el amigo que tiene que confirmarlo
    restaurante_id  bigint not null references restaurantes(id) on delete cascade,
    fecha           date not null,                    -- el día que fuisteis
    creado_en       timestamptz not null default now(),
    primary key (de, para, restaurante_id),
    check (de <> para)
);
create index if not exists invitaciones_visita_para on invitaciones_visita (para, creado_en desc);

alter table invitaciones_visita enable row level security;
