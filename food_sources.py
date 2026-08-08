from __future__ import annotations

import re
import unicodedata
from typing import Any

import requests
import streamlit as st


FDC_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

SPANISH_FDC_TERMS = {
    "aguacate": "avocado",
    "agua": "water",
    "arroz": "rice",
    "avena": "oats",
    "carne": "beef",
    "cebolla": "onion",
    "cerdo": "pork",
    "frijol": "beans",
    "frijoles": "beans",
    "huevo": "egg",
    "huevos": "eggs",
    "leche": "milk",
    "lenteja": "lentils",
    "lentejas": "lentils",
    "manzana": "apple",
    "naranja": "orange",
    "papa": "potato",
    "papas": "potatoes",
    "pechuga de pollo": "chicken breast",
    "pescado": "fish",
    "platano": "banana",
    "pollo": "chicken",
    "queso": "cheese",
    "tortilla": "corn tortilla",
    "tortillas": "corn tortillas",
    "tomate": "tomato",
    "yogur": "yogurt",
    "yogurt": "yogurt",
}

NUTRIENT_IDS = {
    1008: "calories_per_100g",
    2047: "calories_per_100g",
    2048: "calories_per_100g",
    1003: "protein_per_100g",
    1005: "carbs_per_100g",
    1004: "fat_per_100g",
    1079: "fiber_per_100g",
    1051: "water_per_100g",
}


class FoodSourceError(RuntimeError):
    """Raised when an external food source cannot be queried."""


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _translate_query(query: str) -> str:
    normalized = _normalize_text(query)
    if normalized in SPANISH_FDC_TERMS:
        return SPANISH_FDC_TERMS[normalized]

    words = re.findall(r"[a-z0-9]+", normalized)
    translated = [SPANISH_FDC_TERMS.get(word, word) for word in words]
    return " ".join(translated) or query


def food_data_central_configured() -> bool:
    try:
        return bool(str(st.secrets["food_data_central"]["api_key"]).strip())
    except (KeyError, FileNotFoundError):
        return False


def _fdc_api_key() -> str:
    try:
        key = str(st.secrets["food_data_central"]["api_key"]).strip()
    except (KeyError, FileNotFoundError) as exc:
        raise FoodSourceError(
            "FoodData Central no está configurado. Agrega [food_data_central].api_key."
        ) from exc
    if not key:
        raise FoodSourceError("La API key de FoodData Central está vacía.")
    return key


def _nutrient_values(food: dict[str, Any]) -> dict[str, float]:
    values = {field: 0.0 for field in NUTRIENT_IDS.values()}
    for nutrient in food.get("foodNutrients") or []:
        try:
            nutrient_id = int(nutrient.get("nutrientId"))
        except (TypeError, ValueError):
            continue
        field = NUTRIENT_IDS.get(nutrient_id)
        if field and values[field] == 0:
            try:
                values[field] = max(
                    float(nutrient.get("value") or nutrient.get("amount") or 0),
                    0.0,
                )
            except (TypeError, ValueError):
                pass
    return values


@st.cache_data(ttl=60 * 60, show_spinner=False)
def search_food_data_central(query: str, limit: int = 12) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    api_key = _fdc_api_key()
    translated_query = _translate_query(query)
    try:
        response = requests.post(
            FDC_SEARCH_URL,
            params={"api_key": api_key},
            json={
                "query": translated_query,
                "pageSize": min(max(int(limit), 1), 25),
                "dataType": ["Foundation", "SR Legacy"],
                "sortBy": "dataType.keyword",
                "sortOrder": "asc",
            },
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise FoodSourceError(
            "No fue posible consultar FoodData Central en este momento."
        ) from exc
    except ValueError as exc:
        raise FoodSourceError("FoodData Central devolvió una respuesta inválida.") from exc

    results: list[dict[str, Any]] = []
    for food in payload.get("foods") or []:
        fdc_id = food.get("fdcId")
        description = str(food.get("description") or "").strip()
        if not fdc_id or not description:
            continue
        nutrients = _nutrient_values(food)
        results.append(
            {
                "result_key": f"fdc:{fdc_id}",
                "catalog_food_id": None,
                "name": description.capitalize(),
                "brand": str(food.get("brandOwner") or "").strip() or None,
                "source": "USDA FoodData Central",
                "source_id": str(fdc_id),
                "verified": True,
                "portion_name": None,
                "portion_grams": None,
                **nutrients,
            }
        )
    return results
