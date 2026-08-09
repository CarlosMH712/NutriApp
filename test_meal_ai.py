from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from meal_ai import ParsedFood, ParsedMeal, interpret_meal
from food_measurements import (
    MILLILITERS,
    calculate_food_serving,
    effective_water_ml,
    measurement_options,
)
from meal_workflows import calculate_component, rank_catalog_matches


class MealAITests(unittest.TestCase):
    def test_plain_water_offers_ml_and_updates_hydration_without_catalog_water(self) -> None:
        water = {
            "name": "Agua purificada",
            "portion_name": "taza",
            "portion_grams": 240,
            "calories_per_100g": 0,
            "protein_per_100g": 0,
            "carbs_per_100g": 0,
            "fat_per_100g": 0,
            "fiber_per_100g": 0,
            "water_per_100g": 0,
        }
        self.assertIn(MILLILITERS, measurement_options(water))
        result = calculate_food_serving(water, 500, MILLILITERS)
        self.assertEqual(result["unit"], "ml")
        self.assertEqual(result["grams"], 500)
        self.assertEqual(result["water"], 500)

    def test_existing_plain_water_cup_is_recovered_for_daily_total(self) -> None:
        self.assertEqual(effective_water_ml("Agua", 2, "taza", 0), 480)

    def test_solid_food_does_not_offer_ml(self) -> None:
        apple = {
            "name": "Manzana",
            "portion_name": "pieza",
            "portion_grams": 150,
        }
        self.assertNotIn(MILLILITERS, measurement_options(apple))

    def test_catalog_ranking_prefers_semantic_name_match(self) -> None:
        candidates = [
            {"result_key": "1", "name": "Pan de hamburguesa"},
            {"result_key": "2", "name": "Carne de hamburguesa de res"},
            {"result_key": "3", "name": "Carne de cerdo"},
        ]
        ranked = rank_catalog_matches("carne para hamburguesa", candidates)
        self.assertEqual(ranked[0]["result_key"], "2")

    def test_component_uses_catalog_values_and_household_measure(self) -> None:
        food = {
            "name": "Pan de hamburguesa",
            "portion_name": "pieza",
            "portion_grams": 50,
            "calories_per_100g": 260,
            "protein_per_100g": 8,
            "carbs_per_100g": 50,
            "fat_per_100g": 3,
            "fiber_per_100g": 2,
            "water_per_100g": 30,
            "catalog_food_id": "food-1",
            "source": "SMAE 2014",
            "source_id": "SMAE:PAN",
        }
        result = calculate_component(food, 1, "pieza")
        self.assertEqual(result["grams"], 50)
        self.assertEqual(result["calories"], 130)
        self.assertEqual(result["carbs"], 25)

    def test_interpretation_uses_gemini_structured_output_without_identity(self) -> None:
        parsed = ParsedMeal(
            dish_name="Hamburguesa sencilla",
            suggested_meal="Comida",
            items=[
                ParsedFood(
                    name="Pan de hamburguesa",
                    quantity=1,
                    unit="pieza",
                    estimated_grams=50,
                    preparation="",
                    assumption="",
                    needs_clarification=False,
                    clarification_question="",
                )
            ],
            missing_details=["¿La hamburguesa tenía queso o aderezo?"],
        )
        create_mock = MagicMock(
            return_value=SimpleNamespace(output_text=parsed.model_dump_json())
        )
        fake_client = SimpleNamespace(
            interactions=SimpleNamespace(create=create_mock)
        )
        with patch(
            "meal_ai._config",
            return_value=("test-key", "gemini-3.5-flash-lite"),
        ):
            with patch("meal_ai.genai.Client", return_value=fake_client):
                result = interpret_meal("Comí una hamburguesa")

        self.assertEqual(result.dish_name, "Hamburguesa sencilla")
        kwargs = create_mock.call_args.kwargs
        self.assertFalse(kwargs["store"])
        self.assertEqual(kwargs["model"], "gemini-3.5-flash-lite")
        self.assertEqual(
            kwargs["response_format"]["mime_type"], "application/json"
        )
        self.assertNotIn("patient-private-id", kwargs["input"])


if __name__ == "__main__":
    unittest.main()
