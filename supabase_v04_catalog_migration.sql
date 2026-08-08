-- Mi Nutrición V0.4 - catálogo de alimentos con trazabilidad.
-- Requiere haber ejecutado primero supabase_schema.sql (V0.3).
-- Ejecutar una sola vez desde Supabase > SQL Editor.

create table if not exists public.food_catalog (
    id uuid primary key default gen_random_uuid(),
    name text not null check (length(trim(name)) > 0),
    brand text,
    source text not null default 'nutritionist',
    external_id text,
    created_by uuid references public.profiles(id) on delete cascade,
    is_public boolean not null default false,
    verified boolean not null default false,
    calories_per_100g numeric(10,2) not null default 0 check (calories_per_100g >= 0),
    protein_per_100g numeric(10,2) not null default 0 check (protein_per_100g >= 0),
    carbs_per_100g numeric(10,2) not null default 0 check (carbs_per_100g >= 0),
    fat_per_100g numeric(10,2) not null default 0 check (fat_per_100g >= 0),
    fiber_per_100g numeric(10,2) not null default 0 check (fiber_per_100g >= 0),
    water_per_100g numeric(10,2) not null default 0 check (water_per_100g >= 0),
    portion_name text,
    portion_grams numeric(10,2) check (portion_grams is null or portion_grams > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_food_catalog_name
    on public.food_catalog(lower(name));
create index if not exists idx_food_catalog_created_by
    on public.food_catalog(created_by);

alter table public.food_log
    add column if not exists catalog_food_id uuid
        references public.food_catalog(id) on delete set null;
alter table public.food_log
    add column if not exists source_name text;
alter table public.food_log
    add column if not exists source_id text;

alter table public.food_catalog enable row level security;

grant select on public.food_catalog to authenticated;

drop policy if exists "catalog_select_allowed" on public.food_catalog;
create policy "catalog_select_allowed"
on public.food_catalog for select to authenticated
using (
    is_public
    or created_by = (select auth.uid())
    or exists (
        select 1
        from public.nutritionist_patients np
        where np.nutritionist_id = food_catalog.created_by
          and np.patient_id = (select private.current_patient_id())
    )
);

-- Sólo un nutriólogo puede crear alimentos compartidos con sus pacientes.
create or replace function public.create_catalog_food(
    p_name text,
    p_brand text,
    p_source text,
    p_external_id text,
    p_calories_per_100g numeric,
    p_protein_per_100g numeric,
    p_carbs_per_100g numeric,
    p_fat_per_100g numeric,
    p_fiber_per_100g numeric,
    p_water_per_100g numeric,
    p_portion_name text,
    p_portion_grams numeric
)
returns uuid
language plpgsql
security definer set search_path = ''
as $$
declare
    new_food_id uuid;
begin
    if not (select private.is_nutritionist()) then
        raise exception 'Sólo un nutriólogo puede crear alimentos del catálogo';
    end if;
    if nullif(trim(p_name), '') is null then
        raise exception 'El nombre del alimento es obligatorio';
    end if;

    insert into public.food_catalog (
        name, brand, source, external_id, created_by, is_public, verified,
        calories_per_100g, protein_per_100g, carbs_per_100g,
        fat_per_100g, fiber_per_100g, water_per_100g,
        portion_name, portion_grams
    )
    values (
        trim(p_name), nullif(trim(p_brand), ''),
        coalesce(nullif(trim(p_source), ''), 'nutritionist'),
        nullif(trim(p_external_id), ''), (select auth.uid()), false, true,
        greatest(coalesce(p_calories_per_100g, 0), 0),
        greatest(coalesce(p_protein_per_100g, 0), 0),
        greatest(coalesce(p_carbs_per_100g, 0), 0),
        greatest(coalesce(p_fat_per_100g, 0), 0),
        greatest(coalesce(p_fiber_per_100g, 0), 0),
        greatest(coalesce(p_water_per_100g, 0), 0),
        nullif(trim(p_portion_name), ''),
        case when p_portion_grams > 0 then p_portion_grams else null end
    )
    returning id into new_food_id;

    return new_food_id;
end;
$$;

create or replace function public.delete_catalog_food(p_food_id uuid)
returns void
language plpgsql
security definer set search_path = ''
as $$
begin
    if not (select private.is_nutritionist()) then
        raise exception 'Sólo un nutriólogo puede eliminar alimentos del catálogo';
    end if;

    delete from public.food_catalog
    where id = p_food_id
      and created_by = (select auth.uid())
      and not is_public;

    if not found then
        raise exception 'No se encontró un alimento propio con ese identificador';
    end if;
end;
$$;

create or replace function public.import_catalog_foods(p_foods jsonb)
returns integer
language plpgsql
security definer set search_path = ''
as $$
declare
    item jsonb;
    imported_count integer := 0;
begin
    if not (select private.is_nutritionist()) then
        raise exception 'Sólo un nutriólogo puede importar alimentos';
    end if;
    if jsonb_typeof(p_foods) <> 'array' then
        raise exception 'La importación debe ser una lista JSON';
    end if;
    if jsonb_array_length(p_foods) > 2000 then
        raise exception 'Importa un máximo de 2000 alimentos por archivo';
    end if;

    for item in select value from jsonb_array_elements(p_foods) loop
        if nullif(trim(item ->> 'name'), '') is null then
            continue;
        end if;

        insert into public.food_catalog (
            name, brand, source, external_id, created_by, is_public, verified,
            calories_per_100g, protein_per_100g, carbs_per_100g,
            fat_per_100g, fiber_per_100g, water_per_100g,
            portion_name, portion_grams
        )
        values (
            trim(item ->> 'name'),
            nullif(trim(coalesce(item ->> 'brand', '')), ''),
            coalesce(nullif(trim(item ->> 'source'), ''), 'nutritionist_import'),
            nullif(trim(coalesce(item ->> 'external_id', '')), ''),
            (select auth.uid()), false, true,
            greatest(coalesce(nullif(item ->> 'calories_per_100g', '')::numeric, 0), 0),
            greatest(coalesce(nullif(item ->> 'protein_per_100g', '')::numeric, 0), 0),
            greatest(coalesce(nullif(item ->> 'carbs_per_100g', '')::numeric, 0), 0),
            greatest(coalesce(nullif(item ->> 'fat_per_100g', '')::numeric, 0), 0),
            greatest(coalesce(nullif(item ->> 'fiber_per_100g', '')::numeric, 0), 0),
            greatest(coalesce(nullif(item ->> 'water_per_100g', '')::numeric, 0), 0),
            nullif(trim(coalesce(item ->> 'portion_name', '')), ''),
            case
                when coalesce(nullif(item ->> 'portion_grams', '')::numeric, 0) > 0
                then (item ->> 'portion_grams')::numeric
                else null
            end
        );
        imported_count := imported_count + 1;
    end loop;

    return imported_count;
end;
$$;

revoke all on function public.create_catalog_food(
    text, text, text, text, numeric, numeric, numeric, numeric,
    numeric, numeric, text, numeric
) from public;
grant execute on function public.create_catalog_food(
    text, text, text, text, numeric, numeric, numeric, numeric,
    numeric, numeric, text, numeric
) to authenticated;

revoke all on function public.delete_catalog_food(uuid) from public;
grant execute on function public.delete_catalog_food(uuid) to authenticated;

revoke all on function public.import_catalog_foods(jsonb) from public;
grant execute on function public.import_catalog_foods(jsonb) to authenticated;
