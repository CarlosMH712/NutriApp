-- Mi Nutrición V0.8.2 - zona horaria configurable por cuenta.
-- Ejecutar una sola vez desde Supabase > SQL Editor con el rol postgres.

alter table public.profiles
    add column if not exists timezone text not null default 'America/Chihuahua';

comment on column public.profiles.timezone is
    'Zona horaria IANA usada para calcular la fecha local de la cuenta.';

grant update(timezone) on public.profiles to authenticated;

drop policy if exists "profiles_update_own_timezone" on public.profiles;
create policy "profiles_update_own_timezone"
on public.profiles for update to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);
