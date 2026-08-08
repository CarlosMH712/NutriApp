-- Mi Nutrición V0.6 - edición de registros y evolución corporal.
-- Requiere haber ejecutado supabase_v05_measurements_goals_migration.sql.
-- Ejecutar una sola vez desde Supabase > SQL Editor con el rol postgres.

alter table public.body_measurements
    add column if not exists weight_kg numeric(7,2);

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'body_measurements_weight_kg_check'
          and conrelid = 'public.body_measurements'::regclass
    ) then
        alter table public.body_measurements
            add constraint body_measurements_weight_kg_check
            check (weight_kg is null or (weight_kg > 0 and weight_kg <= 500));
    end if;
end;
$$;

comment on column public.body_measurements.weight_kg is
    'Peso medido en kg en la fecha del registro; se conserva para mostrar su evolución.';

-- El paciente y su nutriólogo vinculado pueden corregir un registro.
-- La eliminación continúa reservada al paciente propietario.
drop policy if exists "food_log_update_own" on public.food_log;
drop policy if exists "food_log_update_allowed" on public.food_log;
create policy "food_log_update_allowed"
on public.food_log for update to authenticated
using ((select private.can_access_patient(patient_id)))
with check ((select private.can_access_patient(patient_id)));
