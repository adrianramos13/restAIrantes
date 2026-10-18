-- Foto de perfil (la de la cuenta de Google) para que tus amigos la vean en su sección de Amigos.
-- La app la guarda sola al entrar con Google. Ejecútalo una vez: Supabase -> SQL Editor -> pega -> Run.

alter table perfiles add column if not exists foto text
    check (foto ~ '^https://[a-z0-9.-]+[.]googleusercontent[.]com/' and char_length(foto) <= 500);
