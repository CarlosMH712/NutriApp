-- Mi Nutrición V0.10 - búsqueda sin acentos, densidad, panel y control de uso de IA.
-- Requiere supabase_schema.sql, v04, v05, v06, v07, v08_2 y v09.
-- Ejecutar una sola vez desde Supabase > SQL Editor con el rol postgres.
--
-- Conserva pacientes, alimentos, metas, mediciones, actividad y registros.


-- ---------------------------------------------------------------------------
-- 1. Búsqueda que ignora acentos
-- ---------------------------------------------------------------------------
--
-- ILIKE distingue acentos, así que buscar "platano" nunca encontraba "Plátano".
-- En los catálogos importados esto dejaba fuera cerca del 18% de los alimentos,
-- y en el teléfono casi nadie escribe los acentos.

create extension if not exists unaccent with schema extensions;
create extension if not exists pg_trgm with schema extensions;

-- unaccent() es STABLE porque depende del diccionario que se le pase. Fijando
-- el diccionario queda determinista y puede usarse en columnas generadas.
create or replace function public.immutable_unaccent(p_text text)
returns text
language sql
immutable
strict
parallel safe
set search_path = ''
as $$
    select extensions.unaccent('extensions.unaccent'::regdictionary, p_text)
$$;

comment on function public.immutable_unaccent(text) is
    'unaccent con diccionario fijo, apto para índices y columnas generadas.';

alter table public.food_catalog
    add column if not exists name_search text
    generated always as (lower(public.immutable_unaccent(name))) stored;

-- El índice trigram acelera las búsquedas por subcadena (%texto%).
create index if not exists idx_food_catalog_name_search
    on public.food_catalog using gin (name_search extensions.gin_trgm_ops);

comment on column public.food_catalog.name_search is
    'Nombre en minúsculas y sin acentos. Lo mantiene la base; no se captura.';


-- ---------------------------------------------------------------------------
-- 2. Densidad para la conversión de mililitros
-- ---------------------------------------------------------------------------
--
-- La app aproximaba 1 ml = 1 g para todos los líquidos. Es correcto para agua,
-- pero desvía en aceite (0.92) y miel (1.4). Sin densidad se conserva el 1:1.

alter table public.food_catalog
    add column if not exists density_g_per_ml numeric(6,3)
        check (density_g_per_ml is null or (density_g_per_ml > 0 and density_g_per_ml <= 5));

comment on column public.food_catalog.density_g_per_ml is
    'Gramos por mililitro. Si está vacío se asume 1.0, como agua.';


create or replace function public.set_catalog_food_density(
    p_food_id uuid,
    p_density numeric
)
returns void
language plpgsql
security definer set search_path = ''
as $$
begin
    update public.food_catalog
    set density_g_per_ml = case
            when p_density is null or p_density <= 0 then null
            else p_density
        end,
        updated_at = now()
    where id = p_food_id and created_by = (select auth.uid());
end;
$$;


-- ---------------------------------------------------------------------------
-- 3. Resumen para el panel del nutriólogo
-- ---------------------------------------------------------------------------
--
-- Sin esto, armar el panel exigía una consulta por paciente. Con veinte
-- pacientes eran veinte viajes a la base cada vez que se abría la pantalla.

create or replace function public.nutritionist_patient_summary(
    p_days integer default 7
)
returns table (
    patient_id uuid,
    patient_name text,
    goal_calories numeric,
    last_log_date date,
    days_logged integer,
    avg_calories numeric,
    avg_protein numeric,
    days_on_target integer,
    last_weight numeric,
    last_weight_date date
)
language sql
stable
security invoker
set search_path = ''
as $$
    with window_bounds as (
        select current_date - greatest(coalesce(p_days, 7), 1) + 1 as start_date
    ),
    mine as (
        select np.patient_id
        from public.nutritionist_patients np
        where np.nutritionist_id = (select auth.uid())
    ),
    daily as (
        select
            fl.patient_id,
            fl.log_date,
            sum(fl.calories) as calories,
            sum(fl.protein) as protein
        from public.food_log fl
        join mine on mine.patient_id = fl.patient_id
        cross join window_bounds wb
        where fl.log_date >= wb.start_date
        group by fl.patient_id, fl.log_date
    )
    select
        p.id,
        p.name,
        g.calories,
        (select max(fl.log_date) from public.food_log fl where fl.patient_id = p.id),
        coalesce(count(daily.log_date), 0)::integer,
        round(coalesce(avg(daily.calories), 0), 1),
        round(coalesce(avg(daily.protein), 0), 1),
        -- Dentro de meta es quedar a ±10% de las calorías objetivo.
        coalesce(
            count(daily.log_date) filter (
                where g.calories > 0
                  and abs(daily.calories - g.calories) <= g.calories * 0.10
            ),
            0
        )::integer,
        (select bm.weight_kg from public.body_measurements bm
          where bm.patient_id = p.id and bm.weight_kg is not null
          order by bm.measured_on desc limit 1),
        (select bm.measured_on from public.body_measurements bm
          where bm.patient_id = p.id and bm.weight_kg is not null
          order by bm.measured_on desc limit 1)
    from public.patients p
    join mine on mine.patient_id = p.id
    left join public.goals g on g.patient_id = p.id
    left join daily on daily.patient_id = p.id
    group by p.id, p.name, g.calories
    order by p.name;
$$;

comment on function public.nutritionist_patient_summary(integer) is
    'Resumen por paciente para el panel. Usa security invoker: cada quien ve sólo a sus pacientes según las políticas RLS.';


-- ---------------------------------------------------------------------------
-- 4. Control de uso de la IA
-- ---------------------------------------------------------------------------
--
-- Nada impedía presionar Interpretar platillo decenas de veces y agotar la
-- cuota gratuita de Gemini, que es de la cuenta y no del usuario.

create table if not exists public.ai_usage (
    id bigint generated by default as identity primary key,
    patient_id uuid not null references public.patients(id) on delete cascade,
    used_on date not null default current_date,
    interpretations integer not null default 0 check (interpretations >= 0),
    updated_at timestamptz not null default now(),
    unique (patient_id, used_on)
);

create index if not exists idx_ai_usage_patient_date
    on public.ai_usage(patient_id, used_on desc);

alter table public.ai_usage enable row level security;

grant select on public.ai_usage to authenticated;

drop policy if exists "ai_usage_select_own" on public.ai_usage;
create policy "ai_usage_select_own"
on public.ai_usage for select to authenticated
using ((select private.can_access_patient(patient_id)));


-- Registra un uso y devuelve cuántos quedan. Se ejecuta como definer para que
-- el propio usuario no pueda alterar su contador.
create or replace function public.register_ai_interpretation(
    p_daily_limit integer default 30
)
returns integer
language plpgsql
security definer set search_path = ''
as $$
declare
    current_patient uuid;
    used integer;
    daily_limit integer := greatest(coalesce(p_daily_limit, 30), 1);
begin
    current_patient := (select private.current_patient_id());
    if current_patient is null then
        raise exception 'La cuenta no tiene un expediente asociado';
    end if;

    insert into public.ai_usage (patient_id, used_on, interpretations)
    values (current_patient, current_date, 1)
    on conflict (patient_id, used_on) do update
        set interpretations = public.ai_usage.interpretations + 1,
            updated_at = now()
    returning interpretations into used;

    if used > daily_limit then
        raise exception 'Alcanzaste el límite de % interpretaciones por día', daily_limit
            using errcode = 'check_violation';
    end if;

    return daily_limit - used;
end;
$$;


-- ---------------------------------------------------------------------------
-- 5. Permisos
-- ---------------------------------------------------------------------------

grant execute on function public.immutable_unaccent(text) to authenticated;
grant execute on function public.set_catalog_food_density(uuid, numeric) to authenticated;
grant execute on function public.nutritionist_patient_summary(integer) to authenticated;
grant execute on function public.register_ai_interpretation(integer) to authenticated;
