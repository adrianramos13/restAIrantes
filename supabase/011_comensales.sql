-- "He ido" con amigos: al añadir a un amigo como comensal se le crea su propia visita a ese restaurante (sin nota,
-- para que la ponga él) con anadido_por = quien le añadió. Así le sale en su Diario y en su perfil. Si ya lo tenía
-- valorado, no se toca. Ejecútalo UNA vez en Supabase (SQL Editor -> pega todo -> Run).

alter table visitas add column if not exists anadido_por text;

create index if not exists visitas_anadido_por on visitas (anadido_por, restaurante_id) where anadido_por is not null;
