from __future__ import annotations

from typing import Final


ACTIVITY_FACTORS: Final[dict[str, float]] = {
    "Sedentaria": 1.20,
    "Ligera": 1.375,
    "Moderada": 1.55,
    "Alta": 1.725,
    "Muy alta": 1.90,
}


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """Calculate adult BMI in kg/m² from metric measurements."""
    if weight_kg <= 0 or height_cm <= 0:
        raise ValueError("Peso y estatura deben ser mayores que cero.")
    height_m = height_cm / 100
    return round(weight_kg / (height_m**2), 2)


def mifflin_st_jeor(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    sex: str,
) -> float:
    """Estimate resting energy expenditure (kcal/day) for an adult."""
    if weight_kg <= 0 or height_cm <= 0 or age_years <= 0:
        raise ValueError("Peso, estatura y edad deben ser mayores que cero.")
    if age_years < 19:
        raise ValueError(
            "La calculadora Mifflin-St Jeor de esta versión es sólo para adultos."
        )

    normalized_sex = sex.strip().lower()
    if normalized_sex == "masculino":
        sex_constant = 5
    elif normalized_sex == "femenino":
        sex_constant = -161
    else:
        raise ValueError(
            "Mifflin-St Jeor requiere seleccionar sexo femenino o masculino."
        )

    return round(
        10 * float(weight_kg)
        + 6.25 * float(height_cm)
        - 5 * int(age_years)
        + sex_constant,
        1,
    )


def calculate_nutrition_targets(
    resting_calories: float,
    weight_kg: float,
    activity_factor: float,
    calorie_adjustment_pct: float,
    protein_pct: float,
    carbs_pct: float,
    fat_pct: float,
    water_ml_per_kg: float = 35,
) -> dict[str, float]:
    """Calculate editable daily targets from resting expenditure and percentages."""
    if resting_calories <= 0 or weight_kg <= 0 or activity_factor <= 0:
        raise ValueError("Gasto en reposo, peso y factor de actividad deben ser positivos.")
    if not -50 <= calorie_adjustment_pct <= 50:
        raise ValueError("El ajuste calórico debe estar entre -50% y 50%.")
    if any(value < 0 for value in (protein_pct, carbs_pct, fat_pct)):
        raise ValueError("Los porcentajes de macronutrientes no pueden ser negativos.")
    if abs(protein_pct + carbs_pct + fat_pct - 100) > 0.01:
        raise ValueError("Proteína, carbohidratos y grasa deben sumar 100%.")
    if water_ml_per_kg < 0:
        raise ValueError("Los mililitros de agua por kg no pueden ser negativos.")

    maintenance = resting_calories * activity_factor
    calories = max(maintenance * (1 + calorie_adjustment_pct / 100), 0)
    return {
        "resting_calories": round(resting_calories, 1),
        "maintenance_calories": round(maintenance, 1),
        "calories": round(calories, 1),
        "protein": round(calories * protein_pct / 100 / 4, 1),
        "carbs": round(calories * carbs_pct / 100 / 4, 1),
        "fat": round(calories * fat_pct / 100 / 9, 1),
        "fiber": round(calories / 1000 * 14, 1),
        "water": round(weight_kg * water_ml_per_kg, 0),
    }
