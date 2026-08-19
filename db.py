from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from app_timezone import DEFAULT_TIMEZONE, normalize_timezone
from food_matching import rank_by_relevance


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

    profile_fields = "id,role,full_name,patient_id,invite_code"
    try:
        response = (
            client.table("profiles")
            .select(f"{profile_fields},timezone")
            .eq("id", str(user.id))
            .single()
            .execute()
        )
    except Exception:
        # Mantiene el acceso mientras se ejecuta la migración V0.8.2.
        response = (
            client.table("profiles")
            .select(profile_fields)
            .eq("id", str(user.id))
            .single()
            .execute()
        )
    profile = dict(response.data)
    profile["timezone"] = normalize_timezone(
        profile.get("timezone", DEFAULT_TIMEZONE)
    )
    profile["email"] = str(user.email or "")
    return profile


def update_account_timezone(user_id: str, timezone_name: str) -> None:
    (
        get_supabase()
        .table("profiles")
        .update({"timezone": normalize_timezone(timezone_name)})
        .eq("id", user_id)
        .execute()
    )


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
    "weight_kg",
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
    weight_kg: float | None = None,
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
                "weight_kg": optional_positive(weight_kg),
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


def update_body_measurement(
    measurement_id: int,
    patient_id: str,
    measured_on: date,
    device: str,
    weight_kg: float | None = None,
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
        .update(
            {
                "measured_on": measured_on.isoformat(),
                "device": device.strip() or None,
                "weight_kg": optional_positive(weight_kg),
                "bmi": optional_positive(bmi),
                "body_fat_pct": optional_positive(body_fat_pct),
                "muscle_pct": optional_positive(muscle_pct),
                "basal_calories": optional_positive(basal_calories),
                "visceral_fat": optional_positive(visceral_fat),
                "metabolic_age": optional_positive(metabolic_age),
                "notes": notes.strip() or None,
            }
        )
        .eq("id", int(measurement_id))
        .eq("patient_id", patient_id)
        .execute()
    )


def delete_body_measurement(measurement_id: int, patient_id: str) -> None:
    (
        get_supabase()
        .table("body_measurements")
        .delete()
        .eq("id", int(measurement_id))
        .eq("patient_id", patient_id)
        .execute()
    )


def update_patient_weight(patient_id: str, weight_kg: float) -> None:
    if float(weight_kg) <= 0:
        raise ValueError("El peso debe ser mayor que cero.")
    (
        get_supabase()
        .table("patients")
        .update({"weight": float(weight_kg)})
        .eq("id", patient_id)
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


def save_food_entries(
    patient_id: str,
    selected_date: date,
    meal: str,
    entries: list[dict[str, Any]],
) -> int:
    if not entries:
        raise ValueError("No hay componentes para registrar.")
    if len(entries) > 30:
        raise ValueError("Registra un máximo de 30 componentes por platillo.")
    rows: list[dict[str, Any]] = []
    for entry in entries:
        food_name = str(entry.get("food_name") or "").strip()
        quantity = float(entry.get("quantity") or 0)
        if not food_name or quantity <= 0:
            raise ValueError("Cada componente requiere nombre y cantidad positiva.")
        rows.append(
            {
                "patient_id": patient_id,
                "log_date": selected_date.isoformat(),
                "meal": meal,
                "food": food_name,
                "quantity": quantity,
                "unit": str(entry.get("unit") or "porción").strip(),
                "calories": max(float(entry.get("calories") or 0), 0),
                "protein": max(float(entry.get("protein") or 0), 0),
                "carbs": max(float(entry.get("carbs") or 0), 0),
                "fat": max(float(entry.get("fat") or 0), 0),
                "fiber": max(float(entry.get("fiber") or 0), 0),
                "water": max(float(entry.get("water") or 0), 0),
                "catalog_food_id": entry.get("catalog_food_id"),
                "source_name": entry.get("source_name"),
                "source_id": entry.get("source_id"),
            }
        )
    get_supabase().table("food_log").insert(rows).execute()
    return len(rows)


def delete_food(food_id: int, patient_id: str) -> None:
    (
        get_supabase()
        .table("food_log")
        .delete()
        .eq("id", int(food_id))
        .eq("patient_id", patient_id)
        .execute()
    )


def update_food(
    food_id: int,
    patient_id: str,
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
    manual_override: bool = False,
) -> None:
    if not food.strip():
        raise ValueError("El nombre del alimento es obligatorio.")
    if float(quantity) < 0:
        raise ValueError("La cantidad no puede ser negativa.")
    nutrient_values = [calories, protein, carbs, fat, fiber, water]
    if any(float(value) < 0 for value in nutrient_values):
        raise ValueError("Los valores nutrimentales no pueden ser negativos.")
    payload = {
        "meal": meal,
        "food": food.strip(),
        "quantity": float(quantity),
        "unit": unit.strip(),
        "calories": float(calories),
        "protein": float(protein),
        "carbs": float(carbs),
        "fat": float(fat),
        "fiber": float(fiber),
        "water": float(water),
    }
    if manual_override:
        payload.update(
            {
                "catalog_food_id": None,
                "source_name": "Registro editado manualmente",
                "source_id": None,
            }
        )
    (
        get_supabase()
        .table("food_log")
        .update(payload)
        .eq("id", int(food_id))
        .eq("patient_id", patient_id)
        .execute()
    )


def get_history(patient_id: str) -> pd.DataFrame:
    """Fetch raw rows with pagination; aggregation is performed in pandas."""
    rows = _fetch_all(
        lambda: get_supabase()
        .table("food_log")
        .select("log_date,food,quantity,unit,calories,protein,carbs,fat,fiber,water")
        .eq("patient_id", patient_id)
        .order("log_date")
    )

    columns = [
        "log_date",
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
    "id,name,brand,source,external_id,created_by,verified,is_liquid,"
    "calories_per_100g,protein_per_100g,carbs_per_100g,"
    "fat_per_100g,fiber_per_100g,water_per_100g,"
    "portion_name,portion_grams"
)

# PostgREST devuelve como máximo 1000 filas por consulta. Cualquier lectura que
# pueda superar ese número debe pedir páginas hasta agotar el resultado.
PAGE_SIZE = 1000


def _fetch_all(build_query: Any) -> list[dict[str, Any]]:
    """Recorre todas las páginas de una consulta hasta agotarla."""
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        response = build_query().range(start, start + PAGE_SIZE - 1).execute()
        batch = response.data or []
        rows.extend(dict(row) for row in batch)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def _catalog_result(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["result_key"] = f"catalog:{row['id']}"
    result["catalog_food_id"] = str(row["id"])
    result["source_id"] = row.get("external_id") or str(row["id"])
    return result


def _attach_portions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrega a cada alimento sus medidas caseras en una sola consulta."""
    food_ids = [str(row["id"]) for row in rows if row.get("id")]
    if not food_ids:
        return rows
    portions_by_food: dict[str, list[dict[str, Any]]] = {}
    try:
        for chunk_start in range(0, len(food_ids), 200):
            chunk = food_ids[chunk_start : chunk_start + 200]
            response = (
                get_supabase()
                .table("food_catalog_portions")
                .select("id,food_id,portion_name,grams,position")
                .in_("food_id", chunk)
                .order("position")
                .execute()
            )
            for portion in response.data or []:
                portions_by_food.setdefault(str(portion["food_id"]), []).append(
                    dict(portion)
                )
    except Exception:
        # Si la migración V0.9 aún no se ejecuta, el alimento conserva la
        # porción única de la versión anterior y la app sigue funcionando.
        return rows
    for row in rows:
        row["portions"] = portions_by_food.get(str(row.get("id")), [])
    return rows


def search_catalog(query: str, limit: int = 25) -> list[dict[str, Any]]:
    clean_query = query.strip().replace("%", "").replace("_", "")
    if not clean_query:
        return []
    # Se traen más candidatos de los que se muestran y se ordenan por parecido.
    # Ordenar por nombre y cortar devolvía sólo los primeros alfabéticamente:
    # buscar "carne" se llenaba de "carne de cerdo" y nunca llegaba a la de res.
    pool = min(max(int(limit) * 12, 120), 400)
    response = (
        get_supabase()
        .table("food_catalog")
        .select(CATALOG_COLUMNS)
        .ilike("name", f"%{clean_query}%")
        .order("name")
        .limit(pool)
        .execute()
    )
    ranked = rank_by_relevance(
        clean_query, [dict(row) for row in (response.data or [])], limit
    )
    return [_catalog_result(row) for row in _attach_portions(ranked)]


def list_owned_catalog(
    query: str = "", limit: int | None = None, offset: int = 0
) -> list[dict[str, Any]]:
    """Catálogo propio del nutriólogo, filtrado y por páginas.

    Con `limit` se pide una sola página; sin él se recorre la tabla completa.
    Sin paginar, PostgREST cortaba en 1000 filas y con un catálogo importado de
    casi 1900 alimentos sólo se alcanzaban a ver los primeros alfabéticamente.
    """
    user_id = str(st.session_state.get("auth_user_id") or "")
    if not user_id:
        raise AuthenticationError("No se encontró el usuario autenticado.")
    clean_query = query.strip().replace("%", "").replace("_", "")

    def build_query() -> Any:
        request = (
            get_supabase()
            .table("food_catalog")
            .select(CATALOG_COLUMNS)
            .eq("created_by", user_id)
        )
        if clean_query:
            request = request.ilike("name", f"%{clean_query}%")
        return request.order("name")

    if limit is None:
        rows = _fetch_all(build_query)
    else:
        start = max(int(offset), 0)
        response = (
            build_query().range(start, start + max(int(limit), 1) - 1).execute()
        )
        rows = [dict(row) for row in (response.data or [])]
    return [_catalog_result(row) for row in _attach_portions(rows)]


def count_owned_catalog(query: str = "") -> int:
    """Total real de alimentos propios, sin traerlos todos."""
    user_id = str(st.session_state.get("auth_user_id") or "")
    if not user_id:
        raise AuthenticationError("No se encontró el usuario autenticado.")
    clean_query = query.strip().replace("%", "").replace("_", "")
    request = (
        get_supabase()
        .table("food_catalog")
        .select("id", count="exact")
        .eq("created_by", user_id)
    )
    if clean_query:
        request = request.ilike("name", f"%{clean_query}%")
    response = request.limit(1).execute()
    return int(response.count or 0)


def add_catalog_portion(food_id: str, portion_name: str, grams: float) -> str:
    response = (
        get_supabase()
        .rpc(
            "add_catalog_portion",
            {
                "p_food_id": food_id,
                "p_portion_name": portion_name.strip(),
                "p_grams": float(grams),
            },
        )
        .execute()
    )
    return str(response.data)


def delete_catalog_portion(portion_id: str) -> None:
    get_supabase().rpc(
        "delete_catalog_portion", {"p_portion_id": portion_id}
    ).execute()


def set_catalog_food_liquid(food_id: str, is_liquid: bool) -> None:
    get_supabase().rpc(
        "set_catalog_food_liquid",
        {"p_food_id": food_id, "p_is_liquid": bool(is_liquid)},
    ).execute()


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


MEAL_TEMPLATE_COLUMNS = (
    "id,name,template_type,patient_id,created_by,default_meal,created_at"
)
MEAL_TEMPLATE_ITEM_COLUMNS = (
    "id,template_id,position,food_name,quantity,unit,calories,protein,"
    "carbs,fat,fiber,water,catalog_food_id,source_name,source_id"
)


def create_meal_template(
    name: str,
    template_type: str,
    patient_id: str | None,
    default_meal: str,
    items: list[dict[str, Any]],
) -> str:
    response = (
        get_supabase()
        .rpc(
            "create_meal_template",
            {
                "p_name": name.strip(),
                "p_template_type": template_type,
                "p_patient_id": patient_id,
                "p_default_meal": default_meal,
                "p_items": items,
            },
        )
        .execute()
    )
    return str(response.data)


def _attach_template_items(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not templates:
        return []
    template_ids = [str(template["id"]) for template in templates]
    response = (
        get_supabase()
        .table("meal_template_items")
        .select(MEAL_TEMPLATE_ITEM_COLUMNS)
        .in_("template_id", template_ids)
        .order("position")
        .execute()
    )
    items_by_template: dict[str, list[dict[str, Any]]] = {
        template_id: [] for template_id in template_ids
    }
    for row in response.data or []:
        items_by_template.setdefault(str(row["template_id"]), []).append(dict(row))
    result: list[dict[str, Any]] = []
    for template in templates:
        item = dict(template)
        item["items"] = items_by_template.get(str(template["id"]), [])
        result.append(item)
    return result


def list_available_meal_templates(patient_id: str) -> list[dict[str, Any]]:
    response = (
        get_supabase()
        .table("meal_templates")
        .select(MEAL_TEMPLATE_COLUMNS)
        .or_(f"patient_id.eq.{patient_id},template_type.eq.nutritionist_recipe")
        .order("name")
        .execute()
    )
    return _attach_template_items([dict(row) for row in (response.data or [])])


def list_owned_meal_templates() -> list[dict[str, Any]]:
    user_id = str(st.session_state.get("auth_user_id") or "")
    if not user_id:
        raise AuthenticationError("No se encontró el usuario autenticado.")
    response = (
        get_supabase()
        .table("meal_templates")
        .select(MEAL_TEMPLATE_COLUMNS)
        .eq("created_by", user_id)
        .order("name")
        .execute()
    )
    return _attach_template_items([dict(row) for row in (response.data or [])])


def delete_meal_template(template_id: str) -> None:
    get_supabase().rpc(
        "delete_meal_template", {"p_template_id": template_id}
    ).execute()


# ---------------------------------------------------------------------------
# Actividad física
# ---------------------------------------------------------------------------

ACTIVITY_DAY_COLUMNS = (
    "id,log_date,steps,active_calories,resting_calories,distance_km,source,notes"
)
EXERCISE_COLUMNS = (
    "id,log_date,exercise,duration_minutes,intensity,calories,source,notes"
)


def get_activity_days(patient_id: str) -> pd.DataFrame:
    """Resumen diario de actividad, completo y ordenado por fecha."""
    rows = _fetch_all(
        lambda: get_supabase()
        .table("activity_days")
        .select(ACTIVITY_DAY_COLUMNS)
        .eq("patient_id", patient_id)
        .order("log_date")
    )
    columns = [
        "id", "log_date", "steps", "active_calories",
        "resting_calories", "distance_km", "source", "notes",
    ]
    return pd.DataFrame(rows, columns=columns)


def get_activity_day(patient_id: str, selected_date: date) -> dict[str, Any]:
    response = (
        get_supabase()
        .table("activity_days")
        .select(ACTIVITY_DAY_COLUMNS)
        .eq("patient_id", patient_id)
        .eq("log_date", selected_date.isoformat())
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return dict(rows[0]) if rows else {}


def save_activity_day(
    patient_id: str,
    selected_date: date,
    steps: int | None = None,
    active_calories: float | None = None,
    resting_calories: float | None = None,
    distance_km: float | None = None,
    notes: str = "",
    source: str = "manual",
) -> None:
    """Crea o reemplaza el resumen del día. Hay uno solo por paciente y fecha."""
    payload = {
        "patient_id": patient_id,
        "log_date": selected_date.isoformat(),
        "steps": int(steps) if steps is not None else None,
        "active_calories": float(active_calories) if active_calories is not None else None,
        "resting_calories": (
            float(resting_calories) if resting_calories is not None else None
        ),
        "distance_km": float(distance_km) if distance_km is not None else None,
        "notes": notes.strip() or None,
        "source": source,
        "updated_at": "now()",
    }
    (
        get_supabase()
        .table("activity_days")
        .upsert(payload, on_conflict="patient_id,log_date")
        .execute()
    )


def import_activity_days(patient_id: str, rows: list[dict[str, Any]]) -> int:
    """Alta masiva del resumen diario, usada por la importación de Salud."""
    if not rows:
        return 0
    if len(rows) > 2000:
        raise ValueError("Importa un máximo de 2000 días por archivo.")
    payload = [
        {
            "patient_id": patient_id,
            "log_date": str(row["log_date"]),
            "steps": int(row["steps"]) if row.get("steps") is not None else None,
            "active_calories": (
                float(row["active_calories"])
                if row.get("active_calories") is not None
                else None
            ),
            "distance_km": (
                float(row["distance_km"]) if row.get("distance_km") is not None else None
            ),
            "source": "apple_health",
            "updated_at": "now()",
        }
        for row in rows
    ]
    for chunk_start in range(0, len(payload), 500):
        (
            get_supabase()
            .table("activity_days")
            .upsert(
                payload[chunk_start : chunk_start + 500],
                on_conflict="patient_id,log_date",
            )
            .execute()
        )
    return len(payload)


def delete_activity_day(patient_id: str, selected_date: date) -> None:
    (
        get_supabase()
        .table("activity_days")
        .delete()
        .eq("patient_id", patient_id)
        .eq("log_date", selected_date.isoformat())
        .execute()
    )


def get_exercise_log(
    patient_id: str, selected_date: date | None = None
) -> pd.DataFrame:
    def build_query() -> Any:
        request = (
            get_supabase()
            .table("exercise_log")
            .select(EXERCISE_COLUMNS)
            .eq("patient_id", patient_id)
        )
        if selected_date is not None:
            request = request.eq("log_date", selected_date.isoformat())
        return request.order("log_date")

    rows = _fetch_all(build_query)
    columns = [
        "id", "log_date", "exercise", "duration_minutes",
        "intensity", "calories", "source", "notes",
    ]
    return pd.DataFrame(rows, columns=columns)


def save_exercise(
    patient_id: str,
    selected_date: date,
    exercise: str,
    duration_minutes: float | None = None,
    intensity: str | None = None,
    calories: float | None = None,
    notes: str = "",
) -> None:
    clean_exercise = exercise.strip()
    if not clean_exercise:
        raise ValueError("Escribe el nombre del ejercicio.")
    (
        get_supabase()
        .table("exercise_log")
        .insert(
            {
                "patient_id": patient_id,
                "log_date": selected_date.isoformat(),
                "exercise": clean_exercise,
                "duration_minutes": (
                    float(duration_minutes) if duration_minutes else None
                ),
                "intensity": intensity or None,
                "calories": float(calories) if calories else None,
                "notes": notes.strip() or None,
            }
        )
        .execute()
    )


def delete_exercise(exercise_id: int, patient_id: str) -> None:
    (
        get_supabase()
        .table("exercise_log")
        .delete()
        .eq("id", int(exercise_id))
        .eq("patient_id", patient_id)
        .execute()
    )
