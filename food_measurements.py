from __future__ import annotations

import math
import re
import unicodedata


GRAMS = "gramos"
MILLILITERS = "mililitros"

LIQUID_NAME_TERMS = {
    "agua", "water", "leche", "milk", "jugo", "juice", "bebida", "drink",
    "refresco", "soda", "cafe", "coffee", "te", "tea", "caldo", "broth",
    "sopa", "soup", "licuado", "smoothie", "atole", "cerveza", "beer",
    "vino", "wine",
}
LIQUID_PORTION_TERMS = {
    "ml", "mililitro", "mililitros", "l", "litro", "litros", "vaso",
    "vasos", "botella", "botellas", "lata", "latas", "fl oz",
    "onza liquida", "onzas liquidas",
}
PLAIN_WATER_EXCLUSIONS = {
    "coco", "jamaica", "horchata", "fruta", "frutas", "fresca", "frescas",
    "sabor", "saborizada", "saborizadas", "tonica", "limon", "naranja",
    "melon",
}
VOLUME_ML_FACTORS = {
    "ml": 1.0,
    "mililitro": 1.0,
    "mililitros": 1.0,
    "l": 1000.0,
    "litro": 1000.0,
    "litros": 1000.0,
    "taza": 240.0,
    "tazas": 240.0,
    "vaso": 240.0,
    "vasos": 240.0,
    "cucharada": 15.0,
    "cucharadas": 15.0,
    "cucharadita": 5.0,
    "cucharaditas": 5.0,
    "onza liquida": 29.5735,
    "onzas liquidas": 29.5735,
    "fl oz": 29.5735,
}


def normalize_measurement_text(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _nonnegative_number(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(number, 0.0) if math.isfinite(number) else 0.0


def is_plain_water_name(name: object) -> bool:
    normalized = normalize_measurement_text(name)
    tokens = set(normalized.split())
    is_water = "agua" in tokens or normalized == "water" or normalized.startswith("water ")
    return bool(is_water and not tokens.intersection(PLAIN_WATER_EXCLUSIONS))


def volume_ml_from_quantity(quantity: float, unit: object) -> float | None:
    normalized_unit = normalize_measurement_text(unit)
    factor = VOLUME_ML_FACTORS.get(normalized_unit)
    if factor is None:
        return None
    return _nonnegative_number(quantity) * factor


def effective_water_ml(
    food_name: object,
    quantity: float,
    unit: object,
    stored_water: float,
) -> float:
    stored = _nonnegative_number(stored_water)
    if stored > 0 or not is_plain_water_name(food_name):
        return stored
    inferred = volume_ml_from_quantity(quantity, unit)
    if inferred is not None:
        return inferred
    normalized_unit = normalize_measurement_text(unit)
    if normalized_unit in {"g", "gramo", "gramos"}:
        return _nonnegative_number(quantity)
    return stored


def is_liquid_food(food: dict, hinted_unit: object = "") -> bool:
    name_tokens = set(normalize_measurement_text(food.get("name")).split())
    portion_name = normalize_measurement_text(food.get("portion_name"))
    hint = normalize_measurement_text(hinted_unit)
    if name_tokens.intersection(LIQUID_NAME_TERMS):
        return True
    if portion_name in LIQUID_PORTION_TERMS:
        return True
    return hint in LIQUID_PORTION_TERMS


def measurement_options(food: dict, hinted_unit: object = "") -> list[str]:
    options = [MILLILITERS, GRAMS] if is_liquid_food(food, hinted_unit) else [GRAMS]
    portion_name = str(food.get("portion_name") or "").strip()
    portion_grams = float(food.get("portion_grams") or 0)
    if portion_name and portion_grams > 0 and portion_name not in options:
        options.append(portion_name)
    return options


def calculate_food_serving(food: dict, amount: float, unit_choice: str) -> dict:
    quantity = float(amount)
    if quantity <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")

    portion_name = str(food.get("portion_name") or "").strip()
    portion_grams = float(food.get("portion_grams") or 0)
    normalized_unit = normalize_measurement_text(unit_choice)
    if normalized_unit in {"g", "gramo", "gramos"}:
        grams = quantity
        saved_unit = "g"
    elif normalized_unit in {"ml", "mililitro", "mililitros"}:
        # La base nutrimental está expresada por 100 g. Sin densidad específica,
        # los líquidos se aproximan como 1 ml = 1 g y se muestran para revisión.
        grams = quantity
        saved_unit = "ml"
    elif portion_name and portion_grams > 0:
        grams = quantity * portion_grams
        saved_unit = portion_name
    else:
        raise ValueError("La porción seleccionada no tiene equivalencia en gramos.")

    factor = grams / 100.0
    values = {
        field: max(float(food.get(f"{field}_per_100g") or 0), 0.0) * factor
        for field in ["calories", "protein", "carbs", "fat", "fiber", "water"]
    }
    if is_plain_water_name(food.get("name")):
        values["water"] = grams
    values.update(
        {
            "food_name": str(food.get("name") or "Alimento"),
            "quantity": quantity,
            "unit": saved_unit,
            "grams": grams,
            "catalog_food_id": food.get("catalog_food_id"),
            "source_name": str(food.get("source") or "Catálogo"),
            "source_id": str(food.get("source_id") or "") or None,
        }
    )
    return values
