from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from adherence import (
    calorie_adherence,
    daily_totals,
    days_since_last_log,
    logging_rate,
    weekly_comparison,
    window,
)


def history(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Construye un registro crudo: (fecha, calorías, proteína)."""
    return pd.DataFrame(
        [
            {
                "log_date": day, "calories": calories, "protein": protein,
                "carbs": 0, "fat": 0, "fiber": 0, "water": 0,
            }
            for day, calories, protein in rows
        ]
    )


class DailyTotalsTests(unittest.TestCase):
    def test_sums_several_entries_of_the_same_day(self):
        totals = daily_totals(
            history([("2026-08-17", 500, 20), ("2026-08-17", 700, 30)])
        )
        self.assertEqual(len(totals), 1)
        self.assertAlmostEqual(float(totals.iloc[0]["calories"]), 1200.0)
        self.assertAlmostEqual(float(totals.iloc[0]["protein"]), 50.0)

    def test_empty_history_gives_empty_totals(self):
        self.assertTrue(daily_totals(pd.DataFrame()).empty)

    def test_non_numeric_values_do_not_break_the_sum(self):
        raw = history([("2026-08-17", 500, 20)])
        raw["calories"] = raw["calories"].astype(object)
        raw.loc[0, "calories"] = "no es número"
        totals = daily_totals(raw)
        self.assertAlmostEqual(float(totals.iloc[0]["calories"]), 0.0)


class CalorieAdherenceTests(unittest.TestCase):
    def test_counts_only_days_inside_the_range(self):
        # Meta 2000: 1900 y 2100 entran en ±10%; 1500 no.
        totals = daily_totals(
            history([("2026-08-15", 1900, 0), ("2026-08-16", 2100, 0), ("2026-08-17", 1500, 0)])
        )
        stats = calorie_adherence(totals, 2000)
        self.assertEqual(stats["days_logged"], 3)
        self.assertEqual(stats["days_on_target"], 2)
        self.assertAlmostEqual(stats["adherence_pct"], 66.7)

    def test_boundaries_count_as_inside(self):
        totals = daily_totals(
            history([("2026-08-15", 1800, 0), ("2026-08-16", 2200, 0)])
        )
        self.assertEqual(calorie_adherence(totals, 2000)["days_on_target"], 2)

    def test_is_measured_over_logged_days_not_the_period(self):
        """Tres días perfectos de siete dan 100% de adherencia, no 43%.

        Por eso la interfaz muestra también los días registrados: la cifra
        sola se puede leer mal.
        """
        totals = daily_totals(
            history([("2026-08-15", 2000, 0), ("2026-08-16", 2000, 0), ("2026-08-17", 2000, 0)])
        )
        stats = calorie_adherence(totals, 2000)
        self.assertAlmostEqual(stats["adherence_pct"], 100.0)
        self.assertEqual(stats["days_logged"], 3)

    def test_without_records_returns_zeros(self):
        stats = calorie_adherence(daily_totals(pd.DataFrame()), 2000)
        self.assertEqual(stats["days_logged"], 0)
        self.assertAlmostEqual(stats["adherence_pct"], 0.0)

    def test_goal_of_zero_does_not_divide_by_zero(self):
        totals = daily_totals(history([("2026-08-15", 1800, 0)]))
        self.assertAlmostEqual(calorie_adherence(totals, 0)["adherence_pct"], 0.0)


class WindowTests(unittest.TestCase):
    def test_keeps_only_the_requested_days(self):
        totals = daily_totals(
            history([(f"2026-08-{day:02d}", 2000, 0) for day in range(10, 21)])
        )
        recent = window(totals, date(2026, 8, 20), 7)
        self.assertEqual(len(recent), 7)
        self.assertEqual(
            pd.to_datetime(recent["log_date"]).min().date(), date(2026, 8, 14)
        )

    def test_logging_rate_is_capped_at_one_hundred(self):
        totals = daily_totals(
            history([(f"2026-08-{day:02d}", 2000, 0) for day in range(10, 21)])
        )
        self.assertAlmostEqual(logging_rate(totals, 7), 100.0)


class WeeklyComparisonTests(unittest.TestCase):
    def test_compares_against_the_previous_week(self):
        rows = [(f"2026-08-{day:02d}", 2000, 0) for day in range(8, 15)]
        rows += [(f"2026-08-{day:02d}", 1800, 0) for day in range(15, 22)]
        totals = daily_totals(history(rows))
        result = weekly_comparison(totals, date(2026, 8, 21), 2000)
        self.assertAlmostEqual(result["current"]["avg_calories"], 1800.0)
        self.assertAlmostEqual(result["previous"]["avg_calories"], 2000.0)
        self.assertAlmostEqual(result["calorie_delta"], -200.0)

    def test_days_since_last_log(self):
        totals = daily_totals(history([("2026-08-17", 2000, 0)]))
        self.assertEqual(days_since_last_log(totals, date(2026, 8, 20)), 3)

    def test_days_since_last_log_without_records(self):
        self.assertIsNone(days_since_last_log(daily_totals(pd.DataFrame()), date(2026, 8, 20)))


if __name__ == "__main__":
    unittest.main()
