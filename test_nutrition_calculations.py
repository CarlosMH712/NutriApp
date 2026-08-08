from __future__ import annotations

import unittest

from nutrition_calculations import (
    calculate_bmi,
    calculate_nutrition_targets,
    mifflin_st_jeor,
)


class NutritionCalculationTests(unittest.TestCase):
    def test_bmi_uses_metric_formula(self) -> None:
        self.assertEqual(calculate_bmi(84, 170), 29.07)

    def test_mifflin_st_jeor_male(self) -> None:
        self.assertEqual(mifflin_st_jeor(84, 170, 33, "Masculino"), 1742.5)

    def test_mifflin_st_jeor_female(self) -> None:
        self.assertEqual(mifflin_st_jeor(60, 165, 30, "Femenino"), 1320.2)

    def test_targets_preserve_macro_energy_distribution(self) -> None:
        targets = calculate_nutrition_targets(
            resting_calories=1600,
            weight_kg=70,
            activity_factor=1.5,
            calorie_adjustment_pct=-10,
            protein_pct=25,
            carbs_pct=45,
            fat_pct=30,
            water_ml_per_kg=35,
        )
        self.assertEqual(targets["calories"], 2160.0)
        macro_calories = (
            targets["protein"] * 4
            + targets["carbs"] * 4
            + targets["fat"] * 9
        )
        self.assertAlmostEqual(macro_calories, targets["calories"], delta=1)
        self.assertEqual(targets["fiber"], 30.2)
        self.assertEqual(targets["water"], 2450)

    def test_rejects_invalid_macro_percentages(self) -> None:
        with self.assertRaises(ValueError):
            calculate_nutrition_targets(1600, 70, 1.2, 0, 20, 40, 30)


if __name__ == "__main__":
    unittest.main()
