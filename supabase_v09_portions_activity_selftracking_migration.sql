-- Mi Nutrición V0.9 - porciones múltiples, actividad física y autoseguimiento del nutriólogo.
-- Requiere supabase_schema.sql, v04, v05, v06, v07 y v08_2.
-- Ejecutar una sola vez desde Supabase > SQL Editor con el rol postgres.
--
-- Esta migración conserva pacientes, alimentos, metas, mediciones y registros
-- existentes. Las porciones ya capturadas se copian a la nueva tabla.


-- ---------------------------------------------------------------------------
-- 1. Porciones múltiples por alimento
-- ---------------------------------------------------------------------------

-- Marca explícita de líquido. Sustituye la detección por palabras en el nombre,
-- que fallaba con líquidos cuyo nombre no incluía "agua", "leche" o "jugo".
alter table public.food_catalog
    add column if not exists is_liquid boolean not null default false;

create table if not exists public.food_catalog_portions (
    id uuid primary key default gen_random_uuid(),
    food_id uuid not null references public.food_catalog(id) on delete cascade,
    portion_name text not null check (length(trim(portion_name)) > 0),
    grams numeric(10,2) not null check (grams > 0),
    position integer not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists idx_food_catalog_portions_food
    on public.food_catalog_portions(food_id, position);

-- Evita duplicar la misma medida en un alimento, sin distinguir acentos ni mayúsculas.
create unique index if not exists idx_food_catalog_portions_unique
    on public.food_catalog_portions(food_id, lower(trim(portion_name)));

comment on table public.food_catalog_portions is
    'Medidas caseras equivalentes de un alimento. Un alimento puede tener taza, pieza, cucharada y las que requiera.';

-- Copia la porción única que existía en food_catalog hacia la nueva tabla.
insert into public.food_catalog_portions (food_id, portion_name, grams, position)
select fc.id, trim(fc.portion_name), fc.portion_grams, 0
from public.food_catalog fc
where nullif(trim(coalesce(fc.portion_name, '')), '') is not null
  and fc.portion_grams is not null
  and fc.portion_grams > 0
on conflict do nothing;

alter table public.food_catalog_portions enable row level security;

grant select on public.food_catalog_portions to authenticated;

-- La visibilidad de una porción sigue exactamente la del alimento que la contiene.
drop policy if exists "catalog_portions_select_allowed" on public.food_catalog_portions;
create policy "catalog_portions_select_allowed"
on public.food_catalog_portions for select to authenticated
using (
    exists (
        select 1
        from public.food_catalog fc
        where fc.id = food_catalog_portions.food_id
          and (
              fc.is_public
              or fc.created_by = (select auth.uid())
              or exists (
                  select 1
                  from public.nutritionist_patients np
                  where np.nutritionist_id = fc.created_by
                    and np.patient_id = (select private.current_patient_id())
              )
          )
    )
);


create or replace function public.add_catalog_portion(
    p_food_id uuid,
    p_portion_name text,
    p_grams numeric
)
returns uuid
language plpgsql
security definer set search_path = ''
as $$
declare
    new_portion_id uuid;
    next_position integer;
begin
    if not exists (
        select 1 from public.food_catalog fc
        where fc.id = p_food_id and fc.created_by = (select auth.uid())
    ) then
        raise exception 'Sólo puedes agregar medidas a los alimentos que creaste';
    end if;
    if nullif(trim(p_portion_name), '') is null then
        raise exception 'El nombre de la medida es obligatorio';
    end if;
    if p_grams is null or p_grams <= 0 then
        raise exception 'Los gramos equivalentes deben ser mayores que cero';
    end if;

    select coalesce(max(position), -1) + 1 into next_position
    from public.food_catalog_portions
    where food_id = p_food_id;

    insert into public.food_catalog_portions (food_id, portion_name, grams, position)
    values (p_food_id, trim(p_portion_name), p_grams, next_position)
    on conflict (food_id, lower(trim(portion_name))) do update
        set grams = excluded.grams
    returning id into new_portion_id;

    return new_portion_id;
end;
$$;


create or replace function public.delete_catalog_portion(p_portion_id uuid)
returns void
language plpgsql
security definer set search_path = ''
as $$
begin
    delete from public.food_catalog_portions p
    using public.food_catalog fc
    where p.id = p_portion_id
      and p.food_id = fc.id
      and fc.created_by = (select auth.uid());
end;
$$;


create or replace function public.set_catalog_food_liquid(
    p_food_id uuid,
    p_is_liquid boolean
)
returns void
language plpgsql
security definer set search_path = ''
as $$
begin
    update public.food_catalog
    set is_liquid = coalesce(p_is_liquid, false), updated_at = now()
    where id = p_food_id and created_by = (select auth.uid());
end;
$$;


-- ---------------------------------------------------------------------------
-- 2. Actividad física
-- ---------------------------------------------------------------------------

-- Resumen diario: un renglón por paciente y fecha. Es el destino de la
-- importación de la app Salud y de la captura manual de pasos y calorías.
create table if not exists public.activity_days (
    id bigint generated by default as identity primary key,
    patient_id uuid not null references public.patients(id) on delete cascade,
    log_date date not null,
    steps integer check (steps is null or (steps >= 0 and steps <= 200000)),
    active_calories numeric(10,2)
        check (active_calories is null or (active_calories >= 0 and active_calories <= 20000)),
    resting_calories numeric(10,2)
        check (resting_calories is null or (resting_calories >= 0 and resting_calories <= 20000)),
    distance_km numeric(10,2)
        check (distance_km is null or (distance_km >= 0 and distance_km <= 500)),
    source text not null default 'manual'
        check (source in ('manual', 'apple_health')),
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (patient_id, log_date)
);

create index if not exists idx_activity_days_patient_date
    on public.activity_days(patient_id, log_date desc);

comment on table public.activity_days is
    'Resumen diario de actividad. Los valores provienen del dispositivo del paciente o de captura manual; no son una medición clínica.';

-- Sesiones de ejercicio: varias por día.
create table if not exists public.exercise_log (
    id bigint generated by default as identity primary key,
    patient_id uuid not null references public.patients(id) on delete cascade,
    log_date date not null,
    exercise text not null check (length(trim(exercise)) > 0),
    duration_minutes numeric(10,2)
        check (duration_minutes is null or (duration_minutes > 0 and duration_minutes <= 1440)),
    intensity text check (intensity is null or intensity in ('Ligera', 'Moderada', 'Alta')),
    calories numeric(10,2)
        check (calories is null or (calories >= 0 and calories <= 20000)),
    notes text,
    source text not null default 'manual'
        check (source in ('manual', 'apple_health')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_exercise_log_patient_date
    on public.exercise_log(patient_id, log_date desc);

alter table public.activity_days enable row level security;
alter table public.exercise_log enable row level security;

grant select, insert, update, delete on public.activity_days to authenticated;
grant select, insert, update, delete on public.exercise_log to authenticated;
grant usage, select on sequence public.activity_days_id_seq to authenticated;
grant usage, select on sequence public.exercise_log_id_seq to authenticated;

drop policy if exists "activity_days_select_allowed" on public.activity_days;
create policy "activity_days_select_allowed"
on public.activity_days for select to authenticated
using ((select private.can_access_patient(patient_id)));

drop policy if exists "activity_days_insert_allowed" on public.activity_days;
create policy "activity_days_insert_allowed"
on public.activity_days for insert to authenticated
with check ((select private.can_access_patient(patient_id)));

drop policy if exists "activity_days_update_allowed" on public.activity_days;
create policy "activity_days_update_allowed"
on public.activity_days for update to authenticated
using ((select private.can_access_patient(patient_id)))
with check ((select private.can_access_patient(patient_id)));

drop policy if exists "activity_days_delete_allowed" on public.activity_days;
create policy "activity_days_delete_allowed"
on public.activity_days for delete to authenticated
using ((select private.can_access_patient(patient_id)));

drop policy if exists "exercise_log_select_allowed" on public.exercise_log;
create policy "exercise_log_select_allowed"
on public.exercise_log for select to authenticated
using ((select private.can_access_patient(patient_id)));

drop policy if exists "exercise_log_insert_allowed" on public.exercise_log;
create policy "exercise_log_insert_allowed"
on public.exercise_log for insert to authenticated
with check ((select private.can_access_patient(patient_id)));

drop policy if exists "exercise_log_update_allowed" on public.exercise_log;
create policy "exercise_log_update_allowed"
on public.exercise_log for update to authenticated
using ((select private.can_access_patient(patient_id)))
with check ((select private.can_access_patient(patient_id)));

drop policy if exists "exercise_log_delete_allowed" on public.exercise_log;
create policy "exercise_log_delete_allowed"
on public.exercise_log for delete to authenticated
using ((select private.can_access_patient(patient_id)));


-- ---------------------------------------------------------------------------
-- 3. Autoseguimiento del nutriólogo
-- ---------------------------------------------------------------------------

-- Antes, promover a nutriólogo hacía patient_id = null. Como las políticas de
-- food_log exigen patient_id = current_patient_id(), el nutriólogo quedaba sin
-- posibilidad de registrar su propia comida y tenía que abrir una segunda cuenta.
-- El expediente en public.patients siempre siguió existiendo: sólo se dejó de
-- apuntar. Esta versión conserva el vínculo.
create or replace function public.promote_user_to_nutritionist(p_email text)
returns text
language plpgsql
security definer set search_path = ''
as $$
declare
    selected_user uuid;
    selected_code text;
    selected_name text;
begin
    select u.id into selected_user
    from auth.users u
    where lower(u.email) = lower(trim(p_email));

    if selected_user is null then
        raise exception 'No existe un usuario Auth con ese correo';
    end if;

    select coalesce(nullif(trim(p.full_name), ''), 'Nutriólogo') into selected_name
    from public.profiles p
    where p.id = selected_user;

    -- Garantiza el expediente propio incluso si la cuenta se promovió antes.
    insert into public.patients (id, name)
    values (selected_user, coalesce(selected_name, 'Nutriólogo'))
    on conflict (id) do nothing;

    update public.profiles
    set role = 'nutritionist', patient_id = selected_user
    where id = selected_user
    returning invite_code into selected_code;

    return selected_code;
end;
$$;


-- Repara las cuentas que ya se promovieron con la versión anterior.
-- Devuelve cuántas cuentas recuperaron su expediente propio.
create or replace function public.repair_nutritionist_self_tracking()
returns integer
language plpgsql
security definer set search_path = ''
as $$
declare
    repaired integer;
begin
    insert into public.patients (id, name)
    select p.id, coalesce(nullif(trim(p.full_name), ''), 'Nutriólogo')
    from public.profiles p
    where p.role = 'nutritionist' and p.patient_id is null
    on conflict (id) do nothing;

    with fixed as (
        update public.profiles p
        set patient_id = p.id
        where p.role = 'nutritionist' and p.patient_id is null
        returning 1
    )
    select count(*) into repaired from fixed;

    return coalesce(repaired, 0);
end;
$$;


-- Mueve el historial de una cuenta hacia otra. Pensado para la nutrióloga que
-- llevaba su propio seguimiento en una cuenta adicional.
-- Ejemplo:
--   select public.merge_patient_records('cuenta.extra@ejemplo.com',
--                                       'nutriologa@ejemplo.com');
create or replace function public.merge_patient_records(
    p_source_email text,
    p_target_email text
)
returns text
language plpgsql
security definer set search_path = ''
as $$
declare
    source_id uuid;
    target_id uuid;
    moved_food integer := 0;
    moved_measurements integer := 0;
    moved_activity integer := 0;
    moved_exercise integer := 0;
begin
    select u.id into source_id from auth.users u
    where lower(u.email) = lower(trim(p_source_email));
    select u.id into target_id from auth.users u
    where lower(u.email) = lower(trim(p_target_email));

    if source_id is null then
        raise exception 'No existe un usuario Auth con el correo origen %', p_source_email;
    end if;
    if target_id is null then
        raise exception 'No existe un usuario Auth con el correo destino %', p_target_email;
    end if;
    if source_id = target_id then
        raise exception 'El correo origen y el destino son el mismo';
    end if;

    -- El destino necesita expediente propio para recibir los registros.
    insert into public.patients (id, name)
    select target_id, coalesce(nullif(trim(p.full_name), ''), 'Paciente')
    from public.profiles p where p.id = target_id
    on conflict (id) do nothing;

    with moved as (
        update public.food_log set patient_id = target_id
        where patient_id = source_id returning 1
    )
    select count(*) into moved_food from moved;

    with moved as (
        update public.body_measurements set patient_id = target_id
        where patient_id = source_id returning 1
    )
    select count(*) into moved_measurements from moved;

    -- activity_days es único por paciente y fecha: si ambas cuentas tienen el
    -- mismo día, se conserva el del destino y se descarta el duplicado.
    delete from public.activity_days source_row
    where source_row.patient_id = source_id
      and exists (
          select 1 from public.activity_days target_row
          where target_row.patient_id = target_id
            and target_row.log_date = source_row.log_date
      );

    with moved as (
        update public.activity_days set patient_id = target_id
        where patient_id = source_id returning 1
    )
    select count(*) into moved_activity from moved;

    with moved as (
        update public.exercise_log set patient_id = target_id
        where patient_id = source_id returning 1
    )
    select count(*) into moved_exercise from moved;

    return format(
        'Movidos a %s: %s alimentos, %s mediciones, %s días de actividad, %s ejercicios.',
        p_target_email, moved_food, moved_measurements, moved_activity, moved_exercise
    );
end;
$$;


-- ---------------------------------------------------------------------------
-- 4. Permisos
-- ---------------------------------------------------------------------------

revoke all on function public.repair_nutritionist_self_tracking() from public, anon, authenticated;
revoke all on function public.merge_patient_records(text, text) from public, anon, authenticated;
revoke all on function public.promote_user_to_nutritionist(text) from public, anon, authenticated;

grant execute on function public.add_catalog_portion(uuid, text, numeric) to authenticated;
grant execute on function public.delete_catalog_portion(uuid) to authenticated;
grant execute on function public.set_catalog_food_liquid(uuid, boolean) to authenticated;


-- ---------------------------------------------------------------------------
-- 5. Después de ejecutar este archivo
-- ---------------------------------------------------------------------------
--
--   select public.repair_nutritionist_self_tracking();
--
-- Y, para unir la cuenta adicional de la nutrióloga con la principal:
--
--   select public.merge_patient_records('cuenta.extra@ejemplo.com',
--                                       'nutriologa@ejemplo.com');
