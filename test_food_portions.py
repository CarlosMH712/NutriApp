from __future__ import annotations

import unittest

from food_measurements import (
    GRAMS,
    MILLILITERS,
    calculate_food_serving,
    food_portions,
    is_liquid_food,
    measurement_options,
)


def build_food(**overrides) -> dict:
    food = {
        "name": "Arroz cocido",
        "calories_per_100g": 130,
        "protein_per_100g": 2.7,
        "carbs_per_100g": 28.0,
        "fat_per_100g": 0.3,
        "fiber_per_100g": 0.4,
        "water_per_100g": 68.0,
    }
    food.update(overrides)
    return food


class FoodPortionsTests(unittest.TestCase):
    def test_reads_the_portions_table(self):
        food = build_food(
            portions=[
                {"portion_name": "taza", "grams": 158},
                {"portion_name": "cucharada", "grams": 12},
            ]
        )
        names = [portion["name"] for portion in food_portions(food)]
        self.assertEqual(names, ["taza", "cucharada"])

    def test_keeps_the_single_portion_of_older_versions(self):
        """Los alimentos importados y los de USDA no tienen tabla de porciones."""
        food = build_food(portion_name="pieza", portion_grams=120)
        self.assertEqual(
            food_portions(food), [{"name": "pieza", "grams": 120.0}]
        )

    def test_does_not_duplicate_the_same_measure(self):
        food = build_food(
            portions=[{"portion_name": "Taza", "grams": 158}],
            portion_name="taza",
            portion_grams=158,
        )
        self.assertEqual(len(food_portions(food)), 1)

    def test_ignores_portions_without_grams(self):
        food = build_food(portions=[{"portion_name": "taza", "grams": 0}])
        self.assertEqual(food_portions(food), [])


class MeasurementOptionsTests(unittest.TestCase):
    def test_offers_every_portion_defined(self):
        food = build_food(
            portions=[
                {"portion_name": "taza", "grams": 158},
                {"portion_name": "pieza", "grams": 90},
            ]
        )
        options = measurement_options(food)
        self.assertEqual(options, [GRAMS, "taza", "pieza"])

    def test_explicit_liquid_flag_enables_milliliters(self):
        """Antes sólo se ofrecían ml si el nombre incluía agua, leche o jugo."""
        food = build_food(name="Caldo tlalpeño", is_liquid=True)
        self.assertIn(MILLILITERS, measurement_options(food))

    def test_liquid_detection_by_name_still_works(self):
        self.assertTrue(is_liquid_food(build_food(name="Leche entera")))

    def test_solid_food_does_not_offer_milliliters(self):
        self.assertNotIn(MILLILITERS, measurement_options(build_food()))


class CalculateServingTests(unittest.TestCase):
    def test_uses_the_selected_portion(self):
        food = build_food(
            portions=[
                {"portion_name": "taza", "grams": 158},
                {"portion_name": "cucharada", "grams": 12},
            ]
        )
        result = calculate_food_serving(food, 2, "taza")
        self.assertAlmostEqual(result["grams"], 316.0)
        self.assertAlmostEqual(result["calories"], 130 * 3.16, places=2)
        self.assertEqual(result["unit"], "taza")

    def test_picks_the_right_portion_when_there_are_several(self):
        food = build_food(
            portions=[
                {"portion_name": "taza", "grams": 158},
                {"portion_name": "cucharada", "grams": 12},
            ]
        )
        result = calculate_food_serving(food, 3, "cucharada")
        self.assertAlmostEqual(result["grams"], 36.0)

    def test_matches_the_portion_ignoring_accents(self):
        food = build_food(portions=[{"portion_name": "Cucharadita", "grams": 5}])
        self.assertAlmostEqual(
            calculate_food_serving(food, 2, "cucharadita")["grams"], 10.0
        )

    def test_grams_still_work(self):
        result = calculate_food_serving(build_food(), 150, GRAMS)
        self.assertAlmostEqual(result["grams"], 150.0)
        self.assertEqual(result["unit"], "g")

    def test_unknown_portion_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_food_serving(build_food(), 1, "rebanada")

    def test_zero_amount_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_food_serving(build_food(), 0, GRAMS)


class DensityTests(unittest.TestCase):
    def test_without_density_assumes_water(self):
        food = build_food(name="Agua natural", is_liquid=True)
        result = calculate_food_serving(food, 250, MILLILITERS)
        self.assertAlmostEqual(result["grams"], 250.0)

    def test_oil_weighs_less_than_its_volume(self):
        """1 ml de aceite pesa 0.92 g; antes se contaba como 1 g."""
        food = build_food(
            name="Aceite de oliva", is_liquid=True, density_g_per_ml=0.92,
            calories_per_100g=884,
        )
        result = calculate_food_serving(food, 100, MILLILITERS)
        self.assertAlmostEqual(result["grams"], 92.0)
        self.assertAlmostEqual(result["calories"], 884 * 0.92, places=2)

    def test_honey_weighs_more_than_its_volume(self):
        food = build_food(name="Miel", is_liquid=True, density_g_per_ml=1.4)
        self.assertAlmostEqual(
            calculate_food_serving(food, 100, MILLILITERS)["grams"], 140.0
        )

    def test_invalid_density_falls_back_to_one(self):
        food = build_food(name="Leche", is_liquid=True, density_g_per_ml=0)
        self.assertAlmostEqual(
            calculate_food_serving(food, 200, MILLILITERS)["grams"], 200.0
        )

    def test_density_does_not_affect_grams(self):
        food = build_food(name="Aceite", is_liquid=True, density_g_per_ml=0.92)
        self.assertAlmostEqual(
            calculate_food_serving(food, 50, GRAMS)["grams"], 50.0
        )


if __name__ == "__main__":
    unittest.main()
