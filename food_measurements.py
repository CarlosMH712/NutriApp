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


DEFAULT_DENSITY_G_PER_ML = 1.0


def food_density(food: dict) -> float:
    """Gramos por mililitro del alimento; 1.0 si no se capturó."""
    density = _nonnegative_number(food.get("density_g_per_ml"))
    return density if density > 0 else DEFAULT_DENSITY_G_PER_ML


def food_portions(food: dict) -> list[dict]:
    """Devuelve las medidas caseras de un alimento como [{name, grams}].

    Acepta la lista de `food_catalog_portions` y también la porción única que
    guardaban las versiones anteriores, para que los alimentos importados y los
    resultados de USDA sigan funcionando sin volver a capturarse.
    """
    portions: list[dict] = []
    seen: set[str] = set()

    def add(name: object, grams: object) -> None:
        clean_name = str(name or "").strip()
        clean_grams = _nonnegative_number(grams)
        key = normalize_measurement_text(clean_name)
        if clean_name and clean_grams > 0 and key and key not in seen:
            seen.add(key)
            portions.append({"name": clean_name, "grams": clean_grams})

    for item in food.get("portions") or []:
        if isinstance(item, dict):
            add(
                item.get("portion_name") or item.get("name"),
                item.get("grams") if item.get("grams") is not None else item.get("portion_grams"),
            )
    add(food.get("portion_name"), food.get("portion_grams"))
    return portions


def is_liquid_food(food: dict, hinted_unit: object = "") -> bool:
    # La marca explícita del catálogo tiene prioridad: la detección por nombre
    # falla con líquidos que no se llaman agua, leche o jugo.
    if bool(food.get("is_liquid")):
        return True
    name_tokens = set(normalize_measurement_text(food.get("name")).split())
    hint = normalize_measurement_text(hinted_unit)
    if name_tokens.intersection(LIQUID_NAME_TERMS):
        return True
    for portion in food_portions(food):
        if normalize_measurement_text(portion["name"]) in LIQUID_PORTION_TERMS:
            return True
    return hint in LIQUID_PORTION_TERMS


def measurement_options(food: dict, hinted_unit: object = "") -> list[str]:
    options = [MILLILITERS, GRAMS] if is_liquid_food(food, hinted_unit) else [GRAMS]
    for portion in food_portions(food):
        if portion["name"] not in options:
            options.append(portion["name"])
    return options


def calculate_food_serving(food: dict, amount: float, unit_choice: str) -> dict:
    quantity = float(amount)
    if quantity <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")

    normalized_unit = normalize_measurement_text(unit_choice)
    if normalized_unit in {"g", "gramo", "gramos"}:
        grams = quantity
        saved_unit = "g"
    elif normalized_unit in {"ml", "mililitro", "mililitros"}:
        # La base nutrimental está expresada por 100 g, así que los mililitros
        # se convierten con la densidad del alimento. Sin densidad capturada se
        # asume 1 g/ml, que es correcto para agua pero desvía en aceite o miel.
        grams = quantity * food_density(food)
        saved_unit = "ml"
    else:
        matched = next(
            (
                portion
                for portion in food_portions(food)
                if normalize_measurement_text(portion["name"]) == normalized_unit
            ),
            None,
        )
        if matched is None:
            raise ValueError("La porción seleccionada no tiene equivalencia en gramos.")
        grams = quantity * matched["grams"]
        saved_unit = matched["name"]

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
