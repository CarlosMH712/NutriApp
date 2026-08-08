from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client


AUTH_STATE_KEYS = (
    "access_token",
    "refresh_token",
    "auth_user_id",
    "food_search_results",
    "food_search_notices",
)


class DatabaseConfigError(RuntimeError):
    """Raised when the public Supabase credentials are missing or incomplete."""


class AuthenticationError(RuntimeError):
    """Raised when the current Streamlit session is not authenticated."""


def _public_config() -> tuple[str, str]:
    try:
        cfg = st.secrets["supabase"]
        url = str(cfg["url"]).strip()
        key = str(cfg.get("publishable_key", cfg.get("anon_key", ""))).strip()
    except (KeyError, FileNotFoundError) as exc:
        raise DatabaseConfigError(
            "Faltan las credenciales públicas de Supabase. Configura "
            "[supabase].url y [supabase].publishable_key en Streamlit Secrets."
        ) from exc

    if not url or not key:
        raise DatabaseConfigError("Las credenciales públicas de Supabase están vacías.")
    if key.startswith("sb_secret_"):
        raise DatabaseConfigError(
            "La app multiusuario no debe usar una Secret key. Configura una "
            "Publishable key que empiece con sb_publishable_."
        )
    return url, key


def create_public_client() -> Client:
    url, key = _public_config()
    return create_client(url, key)


def _save_session(session: Any) -> None:
    if session is None:
        return
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    if getattr(session, "user", None) is not None:
        st.session_state["auth_user_id"] = str(session.user.id)


def clear_auth_session() -> None:
    for key in AUTH_STATE_KEYS:
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if str(key).startswith("goal_"):
            st.session_state.pop(key, None)


def sign_up(email: str, password: str, full_name: str) -> bool:
    """Register a patient. Returns True when email confirmation is pending."""
    client = create_public_client()
    response = client.auth.sign_up(
        {
            "email": email.strip().lower(),
            "password": password,
            "options": {"data": {"full_name": full_name.strip()}},
        }
    )
    if response.session is None:
        return True
    _save_session(response.session)
    return False


def sign_in(email: str, password: str) -> None:
    client = create_public_client()
    response = client.auth.sign_in_with_password(
        {"email": email.strip().lower(), "password": password}
    )
    if response.session is None:
        raise AuthenticationError("Supabase no devolvió una sesión válida.")
    _save_session(response.session)


def get_supabase() -> Client:
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")
    if not access_token or not refresh_token:
        raise AuthenticationError("Inicia sesión para continuar.")

    client = create_public_client()
    try:
        response = client.auth.set_session(access_token, refresh_token)
    except Exception as exc:
        clear_auth_session()
        raise AuthenticationError(
            "Tu sesión venció. Inicia sesión nuevamente."
        ) from exc

    _save_session(response.session)
    return client


def sign_out() -> None:
    try:
        get_supabase().auth.sign_out()
    finally:
        clear_auth_session()


def get_auth_context() -> dict[str, Any]:
    client = get_supabase()
    user_response = client.auth.get_user()
    user = user_response.user
    if user is None:
        clear_auth_session()
        raise AuthenticationError("No se encontró el usuario autenticado.")

    response = (
        client.table("profiles")
        .select("id,role,full_name,patient_id,invite_code")
        .eq("id", str(user.id))
        .single()
        .execute()
    )
    profile = dict(response.data)
    profile["email"] = str(user.email or "")
    return profile


def get_profile(patient_id: str) -> dict[str, Any]:
    response = (
        get_supabase()
        .table("patients")
        .select("id,name,age,sex,weight,height,activity_level")
        .eq("id", patient_id)
        .single()
        .execute()
    )
    return dict(response.data)


def update_profile(
    patient_id: str,
    name: str,
    age: int,
    sex: str,
    weight: float,
    height: float,
    activity_level: str = "Sedentaria",
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
                "activity_level": activity_level.strip(),
            }
        )
        .eq("id", patient_id)
        .execute()
    )


def get_goals(patient_id: str) -> dict[str, Any]:
    response = (
        get_supabase()
        .table("goals")
        .select(
            "patient_id,calories,protein,carbs,fat,fiber,water,"
            "calculation_method,resting_calories,activity_factor,"
            "calorie_adjustment_pct,protein_pct,carbs_pct,fat_pct,"
            "water_ml_per_kg"
        )
        .eq("patient_id", patient_id)
        .single()
        .execute()
    )
    return dict(response.data)


def update_goals(
    patient_id: str,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    fiber: float,
    water: float,
    calculation_method: str | None = None,
    resting_calories: float | None = None,
    activity_factor: float | None = None,
    calorie_adjustment_pct: float | None = None,
    protein_pct: float | None = None,
    carbs_pct: float | None = None,
    fat_pct: float | None = None,
    water_ml_per_kg: float | None = None,
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
                "calculation_method": calculation_method,
                "resting_calories": resting_calories,
                "activity_factor": activity_factor,
                "calorie_adjustment_pct": calorie_adjustment_pct,
                "protein_pct": protein_pct,
                "carbs_pct": carbs_pct,
                "fat_pct": fat_pct,
                "water_ml_per_kg": water_ml_per_kg,
            },
            on_conflict="patient_id",
        )
        .execute()
    )


BODY_MEASUREMENT_COLUMNS = [
    "id",
    "patient_id",
    "measured_on",
    "device",
    "bmi",
    "body_fat_pct",
    "muscle_pct",
    "basal_calories",
    "visceral_fat",
    "metabolic_age",
    "notes",
]


def get_body_measurements(patient_id: str, limit: int = 30) -> pd.DataFrame:
    response = (
        get_supabase()
        .table("body_measurements")
        .select(",".join(BODY_MEASUREMENT_COLUMNS))
        .eq("patient_id", patient_id)
        .order("measured_on", desc=True)
        .order("created_at", desc=True)
        .limit(min(max(int(limit), 1), 100))
        .execute()
    )
    return pd.DataFrame(response.data or [], columns=BODY_MEASUREMENT_COLUMNS)


def save_body_measurement(
    patient_id: str,
    measured_on: date,
    device: str,
    bmi: float | None = None,
    body_fat_pct: float | None = None,
    muscle_pct: float | None = None,
    basal_calories: float | None = None,
    visceral_fat: float | None = None,
    metabolic_age: int | None = None,
    notes: str = "",
) -> None:
    def optional_positive(value: float | int | None) -> float | int | None:
        if value is None or float(value) <= 0:
            return None
        return value

    (
        get_supabase()
        .table("body_measurements")
        .insert(
            {
                "patient_id": patient_id,
                "measured_on": measured_on.isoformat(),
                "device": device.strip() or None,
                "bmi": optional_positive(bmi),
                "body_fat_pct": optional_positive(body_fat_pct),
                "muscle_pct": optional_positive(muscle_pct),
                "basal_calories": optional_positive(basal_calories),
                "visceral_fat": optional_positive(visceral_fat),
                "metabolic_age": optional_positive(metabolic_age),
                "notes": notes.strip() or None,
            }
        )
        .execute()
    )


def get_day_log(selected_date: date, patient_id: str) -> pd.DataFrame:
    response = (
        get_supabase()
        .table("food_log")
        .select(
            "id,log_date,meal,food,quantity,unit,calories,protein,carbs,fat,fiber,water,source_name,source_id"
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
        "source_name",
        "source_id",
    ]
    return pd.DataFrame(response.data or [], columns=columns)


def save_food(
    patient_id: str,
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
    catalog_food_id: str | None = None,
    source_name: str | None = None,
    source_id: str | None = None,
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
                "catalog_food_id": catalog_food_id,
                "source_name": source_name,
                "source_id": source_id,
            }
        )
        .execute()
    )


def delete_food(food_id: int, patient_id: str) -> None:
    (
        get_supabase()
        .table("food_log")
        .delete()
        .eq("id", int(food_id))
        .eq("patient_id", patient_id)
        .execute()
    )


def get_history(patient_id: str) -> pd.DataFrame:
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


def list_assigned_patients() -> list[dict[str, Any]]:
    db = get_supabase()
    links = db.table("nutritionist_patients").select("patient_id").execute().data or []
    patient_ids = [str(row["patient_id"]) for row in links]
    if not patient_ids:
        return []
    response = (
        db.table("patients")
        .select("id,name,age,sex,weight,height,activity_level")
        .in_("id", patient_ids)
        .order("name")
        .execute()
    )
    return [dict(row) for row in (response.data or [])]


def patient_has_nutritionist(patient_id: str) -> bool:
    response = (
        get_supabase()
        .table("nutritionist_patients")
        .select("nutritionist_id")
        .eq("patient_id", patient_id)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def link_nutritionist(invite_code: str) -> None:
    get_supabase().rpc(
        "link_my_nutritionist", {"p_invite_code": invite_code.strip().upper()}
    ).execute()


CATALOG_COLUMNS = (
    "id,name,brand,source,external_id,created_by,verified,"
    "calories_per_100g,protein_per_100g,carbs_per_100g,"
    "fat_per_100g,fiber_per_100g,water_per_100g,"
    "portion_name,portion_grams"
)


def _catalog_result(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["result_key"] = f"catalog:{row['id']}"
    result["catalog_food_id"] = str(row["id"])
    result["source_id"] = row.get("external_id") or str(row["id"])
    return result


def search_catalog(query: str, limit: int = 25) -> list[dict[str, Any]]:
    clean_query = query.strip().replace("%", "").replace("_", "")
    if not clean_query:
        return []
    response = (
        get_supabase()
        .table("food_catalog")
        .select(CATALOG_COLUMNS)
        .ilike("name", f"%{clean_query}%")
        .order("name")
        .limit(min(max(int(limit), 1), 50))
        .execute()
    )
    return [_catalog_result(dict(row)) for row in (response.data or [])]


def list_owned_catalog() -> list[dict[str, Any]]:
    user_id = str(st.session_state.get("auth_user_id") or "")
    if not user_id:
        raise AuthenticationError("No se encontró el usuario autenticado.")
    response = (
        get_supabase()
        .table("food_catalog")
        .select(CATALOG_COLUMNS)
        .eq("created_by", user_id)
        .order("name")
        .execute()
    )
    return [_catalog_result(dict(row)) for row in (response.data or [])]


def create_catalog_food(
    name: str,
    brand: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    fiber_per_100g: float,
    water_per_100g: float,
    portion_name: str = "",
    portion_grams: float | None = None,
    source: str = "nutritionist",
    external_id: str = "",
) -> str:
    response = (
        get_supabase()
        .rpc(
            "create_catalog_food",
            {
                "p_name": name.strip(),
                "p_brand": brand.strip(),
                "p_source": source.strip(),
                "p_external_id": external_id.strip(),
                "p_calories_per_100g": float(calories_per_100g),
                "p_protein_per_100g": float(protein_per_100g),
                "p_carbs_per_100g": float(carbs_per_100g),
                "p_fat_per_100g": float(fat_per_100g),
                "p_fiber_per_100g": float(fiber_per_100g),
                "p_water_per_100g": float(water_per_100g),
                "p_portion_name": portion_name.strip(),
                "p_portion_grams": (
                    float(portion_grams) if portion_grams and portion_grams > 0 else None
                ),
            },
        )
        .execute()
    )
    return str(response.data)


def delete_catalog_food(food_id: str) -> None:
    get_supabase().rpc("delete_catalog_food", {"p_food_id": food_id}).execute()


def import_catalog_foods(rows: list[dict[str, Any]]) -> int:
    response = (
        get_supabase().rpc("import_catalog_foods", {"p_foods": rows}).execute()
    )
    return int(response.data or 0)
