"""Panel con todos los pacientes de un nutriólogo.

Antes había que entrar expediente por expediente para saber cómo iba cada uno.
Esta pantalla resuelve la pregunta de trabajo real: a quién hay que buscar esta
semana.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from db import get_patient_summary


# Sin registrar durante estos días, el paciente aparece marcado.
INACTIVE_DAYS = 3

PERIOD_OPTIONS = {"Últimos 7 días": 7, "Últimos 14 días": 14, "Últimos 30 días": 30}


def _days_since(value: object, today: date) -> int | None:
    if value in (None, "") or pd.isna(value):
        return None
    try:
        last = pd.to_datetime(value).date()
    except (ValueError, TypeError):
        return None
    return max((today - last).days, 0)


def _has_no_records(value: object) -> bool:
    """True cuando el paciente nunca registró.

    pandas convierte los None en NaN al construir la columna, así que comparar
    contra None no basta: NaN no es None y cualquier comparación con NaN es
    falsa, lo que dejaba fuera de la alerta justo a quien nunca registró.
    """
    return value is None or pd.isna(value)


def _needs_followup(value: object) -> bool:
    return _has_no_records(value) or float(value) > INACTIVE_DAYS


def _status(days_since: object) -> str:
    if _has_no_records(days_since):
        return "⚪ Sin registros"
    days = int(days_since)
    if days == 0:
        return "🟢 Hoy"
    if days <= INACTIVE_DAYS:
        return f"🟢 Hace {days} d"
    if days <= 7:
        return f"🟡 Hace {days} d"
    return f"🔴 Hace {days} d"


def _adherence_pct(row: pd.Series) -> float | None:
    logged = float(row.get("days_logged") or 0)
    if logged <= 0:
        return None
    return round(float(row.get("days_on_target") or 0) / logged * 100, 1)


def render_patient_dashboard(today: date) -> None:
    st.title("👥 Panel de pacientes")

    period_label = st.selectbox("Periodo", list(PERIOD_OPTIONS), index=0)
    days = PERIOD_OPTIONS[period_label]

    try:
        summary = get_patient_summary(days)
    except Exception as exc:
        st.error(
            "No se pudo cargar el panel. Si acabas de actualizar, ejecuta la "
            "migración supabase_v10_search_dashboard_migration.sql."
        )
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        return

    if summary.empty:
        st.info("Aún no tienes pacientes vinculados.")
        return

    summary = summary.copy()
    summary["days_since"] = summary["last_log_date"].map(
        lambda value: _days_since(value, today)
    )
    summary["adherencia"] = summary.apply(_adherence_pct, axis=1)

    total = len(summary)
    inactive = int(summary["days_since"].map(_needs_followup).sum())
    mean_adherence = summary["adherencia"].dropna().mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Pacientes", f"{total}")
    col2.metric(
        f"Sin registrar +{INACTIVE_DAYS} días",
        f"{inactive}",
        delta=None if inactive == 0 else "requieren seguimiento",
        delta_color="inverse",
    )
    col3.metric(
        "Adherencia promedio",
        f"{mean_adherence:.0f}%" if pd.notna(mean_adherence) else "—",
    )

    st.caption(
        f"Adherencia es el porcentaje de días registrados en que las calorías "
        f"quedaron a ±10% de la meta. Se calcula sobre los días con registro, "
        f"no sobre los {days} del periodo, por eso se muestran ambas cifras."
    )

    table = pd.DataFrame(
        {
            "Paciente": summary["patient_name"],
            "Estado": summary["days_since"].map(_status),
            "Días con registro": summary["days_logged"].astype("Int64").astype(str)
            + f" / {days}",
            "Adherencia": summary["adherencia"].map(
                lambda value: "—" if pd.isna(value) else f"{value:.0f}%"
            ),
            "Kcal promedio": summary["avg_calories"].map(
                lambda value: "—" if pd.isna(value) or float(value) == 0
                else f"{float(value):.0f}"
            ),
            "Meta kcal": summary["goal_calories"].map(
                lambda value: "—" if pd.isna(value) else f"{float(value):.0f}"
            ),
            "Proteína promedio": summary["avg_protein"].map(
                lambda value: "—" if pd.isna(value) or float(value) == 0
                else f"{float(value):.0f} g"
            ),
            "Último peso": summary.apply(_weight_label, axis=1),
        }
    )
    st.dataframe(table, width="stretch", hide_index=True)

    pending = summary[summary["days_since"].map(_needs_followup)]
    if not pending.empty:
        st.subheader("🔔 Conviene contactar")
        for _, row in pending.iterrows():
            days_since = row["days_since"]
            detail = (
                "nunca ha registrado alimentos"
                if _has_no_records(days_since)
                else f"lleva {int(days_since)} días sin registrar"
            )
            st.write(f"- **{row['patient_name']}**: {detail}.")

    st.caption(
        "Para revisar un expediente a detalle, elígelo en el selector "
        "**Expediente** de la barra lateral."
    )


def _weight_label(row: pd.Series) -> str:
    weight = row.get("last_weight")
    if weight in (None, "") or pd.isna(weight):
        return "—"
    measured = row.get("last_weight_date")
    if measured in (None, "") or pd.isna(measured):
        return f"{float(weight):.1f} kg"
    return f"{float(weight):.1f} kg · {pd.to_datetime(measured).strftime('%d/%m')}"
