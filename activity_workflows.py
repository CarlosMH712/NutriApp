"""Registro y seguimiento de actividad física.

El resumen del día (pasos, calorías activas, distancia) admite un solo renglón
por fecha y puede llenarse a mano o importarse de la app Salud. Las sesiones de
ejercicio son varias por día y siempre se capturan manualmente.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from apple_health import AppleHealthError, parse_health_export
from db import (
    delete_activity_day,
    delete_exercise,
    get_activity_day,
    get_activity_days,
    get_exercise_log,
    import_activity_days,
    save_activity_day,
    save_exercise,
)
from nutrition_charts import stable_line_chart


INTENSITIES = ["Ligera", "Moderada", "Alta"]

COMMON_EXERCISES = [
    "Caminar", "Correr", "Ciclismo", "Natación", "Pesas",
    "Fuerza funcional", "HIIT", "Yoga", "Elíptica", "Baile", "Otro",
]


def _optional_number(value: float, enabled: bool) -> float | None:
    return float(value) if enabled and value > 0 else None


def render_activity_register(
    patient_id: str, selected_date: date, can_edit: bool = True
) -> None:
    st.subheader("🏃 Actividad del día")
    st.caption(selected_date.strftime("%d/%m/%Y"))

    if notice := st.session_state.pop("activity_notice", None):
        st.success(str(notice))

    try:
        current = get_activity_day(patient_id, selected_date)
    except Exception as exc:
        st.error("No se pudo cargar la actividad del día.")
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        return

    summary_tab, exercise_tab, import_tab = st.tabs(
        ["Resumen del día", "Ejercicios", "Importar de Salud"]
    )

    with summary_tab:
        st.caption(
            "Estos valores vienen de tu reloj o teléfono. Son una referencia de "
            "actividad, no una medición clínica."
        )
        with st.form("activity_day_form"):
            col1, col2 = st.columns(2)
            with col1:
                steps = st.number_input(
                    "Pasos", min_value=0, max_value=200000, step=500,
                    value=int(current.get("steps") or 0),
                )
                distance_km = st.number_input(
                    "Distancia (km)", min_value=0.0, max_value=500.0, step=0.1,
                    value=float(current.get("distance_km") or 0),
                )
            with col2:
                active_calories = st.number_input(
                    "Calorías activas (kcal)", min_value=0.0, max_value=20000.0,
                    step=10.0, value=float(current.get("active_calories") or 0),
                )
                resting_calories = st.number_input(
                    "Calorías en reposo (kcal)", min_value=0.0, max_value=20000.0,
                    step=10.0, value=float(current.get("resting_calories") or 0),
                )
            notes = st.text_input(
                "Nota (opcional)", value=str(current.get("notes") or "")
            )
            saved = st.form_submit_button(
                "Guardar actividad", width="stretch", disabled=not can_edit
            )

        if saved:
            try:
                save_activity_day(
                    patient_id,
                    selected_date,
                    steps=int(steps) if steps > 0 else None,
                    active_calories=_optional_number(active_calories, True),
                    resting_calories=_optional_number(resting_calories, True),
                    distance_km=_optional_number(distance_km, True),
                    notes=notes,
                )
                st.session_state["activity_notice"] = "Actividad guardada."
                st.rerun()
            except Exception as exc:
                st.error("No se pudo guardar la actividad.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))

        if current and can_edit:
            source_label = (
                "importado de Salud"
                if current.get("source") == "apple_health"
                else "capturado a mano"
            )
            st.caption(f"Registro {source_label}.")
            if st.button("🗑️ Borrar la actividad de este día"):
                try:
                    delete_activity_day(patient_id, selected_date)
                    st.session_state["activity_notice"] = "Actividad eliminada."
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo eliminar.")
                    st.code(str(exc))

    with exercise_tab:
        with st.form("exercise_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                choice = st.selectbox("Ejercicio", COMMON_EXERCISES)
                custom = st.text_input(
                    "Nombre (si elegiste Otro)", placeholder="Ej. Escalada"
                )
            with col2:
                duration = st.number_input(
                    "Duración (minutos)", min_value=0.0, max_value=1440.0, step=5.0
                )
                intensity = st.selectbox("Intensidad", INTENSITIES, index=1)
            calories = st.number_input(
                "Calorías quemadas (opcional)", min_value=0.0, max_value=20000.0, step=10.0
            )
            exercise_notes = st.text_input("Nota (opcional)")
            added = st.form_submit_button(
                "Agregar ejercicio", width="stretch", disabled=not can_edit
            )

        if added:
            name = custom.strip() if choice == "Otro" else choice
            try:
                save_exercise(
                    patient_id,
                    selected_date,
                    name,
                    duration_minutes=duration if duration > 0 else None,
                    intensity=intensity,
                    calories=calories if calories > 0 else None,
                    notes=exercise_notes,
                )
                st.session_state["activity_notice"] = "Ejercicio registrado."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error("No se pudo registrar el ejercicio.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))

        try:
            day_exercises = get_exercise_log(patient_id, selected_date)
        except Exception as exc:
            st.error("No se pudo cargar la lista de ejercicios.")
            st.code(str(exc))
            return

        if day_exercises.empty:
            st.info("Todavía no hay ejercicios registrados este día.")
        else:
            for _, row in day_exercises.iterrows():
                col_name, col_detail, col_delete = st.columns([4, 4, 1])
                with col_name:
                    st.write(f"**{row['exercise']}**")
                with col_detail:
                    parts = []
                    if pd.notna(row.get("duration_minutes")) and row.get("duration_minutes"):
                        parts.append(f"{float(row['duration_minutes']):.0f} min")
                    if pd.notna(row.get("intensity")) and row.get("intensity"):
                        parts.append(str(row["intensity"]))
                    if pd.notna(row.get("calories")) and row.get("calories"):
                        parts.append(f"{float(row['calories']):.0f} kcal")
                    st.caption(" · ".join(parts) or "Sin detalle")
                with col_delete:
                    if can_edit and st.button("🗑️", key=f"delete_exercise_{row['id']}"):
                        try:
                            delete_exercise(int(row["id"]), patient_id)
                            st.rerun()
                        except Exception as exc:
                            st.error("No se pudo eliminar.")
                            st.code(str(exc))

    with import_tab:
        render_health_import(patient_id, can_edit)


def render_health_import(patient_id: str, can_edit: bool = True) -> None:
    st.write(
        "En el iPhone abre **Salud > tu foto de perfil > Exportar todos los "
        "datos**. Se genera un archivo ZIP que puedes subir aquí."
    )
    st.caption(
        "Se leen únicamente pasos, calorías activas, distancia y entrenamientos. "
        "El archivo se procesa en el momento y no se almacena."
    )
    if not can_edit:
        st.info("Sólo el propio paciente puede importar su archivo de Salud.")
        return

    uploaded = st.file_uploader(
        "Exportación de Salud", type=["zip", "xml"], key="health_export_file"
    )
    if uploaded is None:
        return

    try:
        with st.spinner("Leyendo la exportación..."):
            parsed = parse_health_export(uploaded)
    except AppleHealthError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error("No se pudo procesar el archivo.")
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        return

    days = parsed["days"]
    workouts = parsed["workouts"]
    st.success(
        f"Se encontraron {len(days)} días con actividad y {len(workouts)} entrenamientos."
    )
    preview = pd.DataFrame(days[:30])
    if not preview.empty:
        st.dataframe(preview, width="stretch", hide_index=True)

    st.warning(
        "Importar reemplaza el resumen que ya tengas guardado en esas fechas. "
        "Los ejercicios capturados a mano no se modifican."
    )
    if st.button("Importar actividad", width="stretch"):
        try:
            imported = import_activity_days(patient_id, days)
            st.session_state["activity_notice"] = (
                f"Se importaron {imported} días de actividad."
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("No se pudo importar la actividad.")
            with st.expander("Detalle técnico"):
                st.code(str(exc))


def render_activity_history(patient_id: str, energy_by_day: pd.DataFrame | None = None) -> None:
    """Gráficas de actividad y, si hay datos, balance contra lo consumido."""
    st.subheader("🏃 Actividad física")
    try:
        activity = get_activity_days(patient_id)
        exercises = get_exercise_log(patient_id)
    except Exception as exc:
        st.error("No se pudo cargar el historial de actividad.")
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        return

    if activity.empty and exercises.empty:
        st.info(
            "Todavía no hay actividad registrada. Captúrala en Registrar > "
            "Actividad o importa tu archivo de Salud."
        )
        return

    if not activity.empty:
        activity = activity.copy()
        activity["log_date"] = pd.to_datetime(activity["log_date"])
        for column in ["steps", "active_calories", "distance_km"]:
            activity[column] = pd.to_numeric(activity[column], errors="coerce")

        recent = activity.tail(30)
        col1, col2, col3 = st.columns(3)
        col1.metric("Días con registro", f"{len(activity)}")
        mean_steps = recent["steps"].mean()
        col2.metric(
            "Pasos promedio (30 días)",
            f"{mean_steps:,.0f}" if pd.notna(mean_steps) else "—",
        )
        mean_calories = recent["active_calories"].mean()
        col3.metric(
            "Calorías activas promedio",
            f"{mean_calories:,.0f} kcal" if pd.notna(mean_calories) else "—",
        )

        if recent["steps"].notna().any():
            st.altair_chart(
                stable_line_chart(
                    recent, "log_date", {"steps": "Pasos"}, "Pasos", zero=True
                ),
                width="stretch",
                on_select="ignore",
            )
        if recent["active_calories"].notna().any():
            st.altair_chart(
                stable_line_chart(
                    recent,
                    "log_date",
                    {"active_calories": "Calorías activas"},
                    "kcal",
                    zero=True,
                ),
                width="stretch",
                on_select="ignore",
            )

        if energy_by_day is not None and not energy_by_day.empty:
            _render_energy_balance(activity, energy_by_day)

    if not exercises.empty:
        st.subheader("🏋️ Ejercicios registrados")
        exercises = exercises.copy()
        exercises["duration_minutes"] = pd.to_numeric(
            exercises["duration_minutes"], errors="coerce"
        )
        by_exercise = (
            exercises.groupby("exercise")
            .agg(
                sesiones=("exercise", "size"),
                minutos=("duration_minutes", "sum"),
            )
            .sort_values("sesiones", ascending=False)
            .reset_index()
        )
        by_exercise.columns = ["Ejercicio", "Sesiones", "Minutos"]
        st.dataframe(by_exercise, width="stretch", hide_index=True)


def _render_energy_balance(activity: pd.DataFrame, energy_by_day: pd.DataFrame) -> None:
    """Compara lo consumido contra las calorías activas del mismo día."""
    consumed = energy_by_day.copy()
    consumed["log_date"] = pd.to_datetime(consumed["log_date"])
    merged = consumed.merge(
        activity[["log_date", "active_calories"]], on="log_date", how="inner"
    ).dropna(subset=["active_calories"])
    if merged.empty:
        return

    st.subheader("⚖️ Consumo contra gasto por actividad")
    st.caption(
        "Sólo compara las calorías consumidas con las calorías activas del "
        "mismo día. No incluye el gasto en reposo, así que no representa el "
        "balance energético total."
    )
    st.altair_chart(
        stable_line_chart(
            merged.tail(30),
            "log_date",
            {"calories": "Consumidas", "active_calories": "Quemadas en actividad"},
            "kcal",
            zero=True,
        ),
        width="stretch",
        on_select="ignore",
    )
