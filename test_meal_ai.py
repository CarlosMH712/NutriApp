from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from meal_ai import ParsedFood, ParsedMeal, interpret_meal, privacy_safe_identifier
from meal_workflows import calculate_component, rank_catalog_matches


class MealAITests(unittest.TestCase):
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

    def test_interpretation_uses_structured_output_and_private_identifier(self) -> None:
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
        parse_mock = MagicMock(return_value=SimpleNamespace(output_parsed=parsed))
        fake_client = SimpleNamespace(
            responses=SimpleNamespace(parse=parse_mock)
        )
        with patch("meal_ai._config", return_value=("test-key", "gpt-4o-mini")):
            with patch("meal_ai.OpenAI", return_value=fake_client):
                result = interpret_meal(
                    "Comí una hamburguesa", "patient-private-id"
                )

        self.assertEqual(result.dish_name, "Hamburguesa sencilla")
        kwargs = parse_mock.call_args.kwargs
        self.assertFalse(kwargs["store"])
        self.assertNotIn("patient-private-id", kwargs["safety_identifier"])
        self.assertEqual(
            kwargs["safety_identifier"],
            privacy_safe_identifier("patient-private-id"),
        )


if __name__ == "__main__":
    unittest.main()
