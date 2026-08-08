from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client


DEMO_PATIENT_ID = "11111111-1111-1111-1111-111111111111"


class DatabaseConfigError(RuntimeError):
    """Raised when Supabase credentials are missing or incomplete."""


@st.cache_resource
def get_supabase() -> Client:
    try:
        cfg = st.secrets["supabase"]
        url = str(cfg["url"]).strip()
        # Supabase recomienda las nuevas Secret keys (sb_secret_...).
        # Se conserva fallback a service_role_key para proyectos legacy.
        key = str(cfg.get("secret_key", cfg.get("service_role_key", ""))).strip()
    except (KeyError, FileNotFoundError) as exc:
        raise DatabaseConfigError(
            "Faltan los secretos de Supabase. Configura [supabase].url y "
            "[supabase].secret_key en Streamlit Secrets."
        ) from exc

    if not url or not key:
        raise DatabaseConfigError("Las credenciales de Supabase están vacías.")

    return create_client(url, key)


def ensure_demo_patient(patient_id: str = DEMO_PATIENT_ID) -> None:
    """Create the single-patient MVP rows if they do not exist yet."""
    db = get_supabase()

    patient = (
        db.table("patients")
        .select("id")
        .eq("id", patient_id)
        .limit(1)
        .execute()
    )

    if not patient.data:
        db.table("patients").insert(
            {
                "id": patient_id,
                "name": "Paciente demo",
                "age": 30,
                "sex": "Femenino",
                "weight": 65.0,
                "height": 165.0,
            }
        ).execute()

    goals = (
        db.table("goals")
        .select("patient_id")
        .eq("patient_id", patient_id)
        .limit(1)
        .execute()
    )

    if not goals.data:
        db.table("goals").insert(
            {
                "patient_id": patient_id,
                "calories": 2000.0,
                "protein": 120.0,
                "carbs": 220.0,
                "fat": 65.0,
                "fiber": 30.0,
                "water": 2500.0,
            }
        ).execute()


def get_profile(patient_id: str = DEMO_PATIENT_ID) -> dict[str, Any]:
    response = (
        get_supabase()
        .table("patients")
        .select("id,name,age,sex,weight,height")
        .eq("id", patient_id)
        .single()
        .execute()
    )
    return dict(response.data)


def update_profile(
    name: str,
    age: int,
    sex: str,
    weight: float,
    height: float,
    patient_id: str = DEMO_PATIENT_ID,
) -> None:
    (
        get_supabase()
        .table("patients")
        .update(
            {
                "name": name.strip(),
                "age": int(age),
                "sex": sex,
                "weight": float(weight),
                "height": float(height),
            }
        )
        .eq("id", patient_id)
        .execute()
    )


def get_goals(patient_id: str = DEMO_PATIENT_ID) -> dict[str, Any]:
    response = (
        get_supabase()
        .table("goals")
        .select("patient_id,calories,protein,carbs,fat,fiber,water")
        .eq("patient_id", patient_id)
        .single()
        .execute()
    )
    return dict(response.data)


def update_goals(
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    fiber: float,
    water: float,
    patient_id: str = DEMO_PATIENT_ID,
) -> None:
    (
        get_supabase()
        .table("goals")
        .upsert(
            {
                "patient_id": patient_id,
                "calories": float(calories),
                "protein": float(protein),
                "carbs": float(carbs),
                "fat": float(fat),
                "fiber": float(fiber),
                "water": float(water),
            },
            on_conflict="patient_id",
        )
        .execute()
    )


def get_day_log(
    selected_date: date,
    patient_id: str = DEMO_PATIENT_ID,
) -> pd.DataFrame:
    response = (
        get_supabase()
        .table("food_log")
        .select(
            "id,log_date,meal,food,quantity,unit,calories,protein,carbs,fat,fiber,water"
        )
        .eq("patient_id", patient_id)
        .eq("log_date", selected_date.isoformat())
        .order("id")
        .execute()
    )

    columns = [
        "id",
        "log_date",
        "meal",
        "food",
        "quantity",
        "unit",
        "calories",
        "protein",
        "carbs",
        "fat",
        "fiber",
        "water",
    ]
    return pd.DataFrame(response.data or [], columns=columns)


def save_food(
    selected_date: date,
    meal: str,
    food: str,
    quantity: float,
    unit: str,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    fiber: float,
    water: float,
    patient_id: str = DEMO_PATIENT_ID,
) -> None:
    (
        get_supabase()
        .table("food_log")
        .insert(
            {
                "patient_id": patient_id,
                "log_date": selected_date.isoformat(),
                "meal": meal,
                "food": food.strip(),
                "quantity": float(quantity),
                "unit": unit,
                "calories": float(calories),
                "protein": float(protein),
                "carbs": float(carbs),
                "fat": float(fat),
                "fiber": float(fiber),
                "water": float(water),
            }
        )
        .execute()
    )


def delete_food(food_id: int, patient_id: str = DEMO_PATIENT_ID) -> None:
    (
        get_supabase()
        .table("food_log")
        .delete()
        .eq("id", int(food_id))
        .eq("patient_id", patient_id)
        .execute()
    )


def get_history(patient_id: str = DEMO_PATIENT_ID) -> pd.DataFrame:
    """Fetch raw rows with pagination; aggregation is performed in pandas."""
    db = get_supabase()
    page_size = 1000
    start = 0
    rows: list[dict[str, Any]] = []

    while True:
        response = (
            db.table("food_log")
            .select("log_date,calories,protein,carbs,fat,fiber,water")
            .eq("patient_id", patient_id)
            .order("log_date")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    columns = [
        "log_date",
        "calories",
        "protein",
        "carbs",
        "fat",
        "fiber",
        "water",
    ]
    return pd.DataFrame(rows, columns=columns)
