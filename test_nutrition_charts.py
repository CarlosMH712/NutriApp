from __future__ import annotations

import unittest

import pandas as pd

from nutrition_charts import stable_line_chart


class NutritionChartTests(unittest.TestCase):
    def test_chart_keeps_tooltip_without_zoom_or_pan_selection(self) -> None:
        data = pd.DataFrame(
            {
                "log_date": ["2026-08-07", "2026-08-08"],
                "calories": [1800, 1950],
            }
        )
        spec = stable_line_chart(
            data,
            "log_date",
            {"calories": "Calorías"},
            "kcal",
            zero=True,
        ).to_dict()

        self.assertNotIn("params", spec)
        self.assertIn("tooltip", spec["encoding"])
        self.assertTrue(spec["encoding"]["y"]["scale"]["zero"])


if __name__ == "__main__":
    unittest.main()
