-- Preferencias de búsqueda de cada usuario (Perfil -> Preferencias: transporte, tiempo y presupuesto
-- que vienen ya puestos en "Comer hoy"). Si ya ejecutaste esquema.sql o 002_perfiles.sql antes de
-- que existiera esta columna, ejecuta SOLO este archivo: Supabase -> SQL Editor -> pega -> Run.

alter table perfiles add column if not exists preferencias jsonb not null default '{}'::jsonb;
