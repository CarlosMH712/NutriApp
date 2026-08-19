from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from meal_ai import MealAIError
from weekly_summary import build_context, generate_weekly_summary


GOALS = {"calories": 2000, "protein": 120}
CURRENT = {
    "days_logged": 5, "days_on_target": 4,
    "adherence_pct": 80.0, "avg_calories": 1950.0,
}
PREVIOUS = {
    "days_logged": 7, "days_on_target": 3,
    "adherence_pct": 42.9, "avg_calories": 2150.0,
}


class BuildContextTests(unittest.TestCase):
    def context(self, **kwargs) -> str:
        params = {
            "week_end": date(2026, 8, 21), "goals": GOALS, "current": CURRENT,
            "previous": PREVIOUS, "calorie_delta": -200.0, "logging_rate": 71.4,
        }
        params.update(kwargs)
        return build_context(**params)

    def test_includes_the_computed_figures(self):
        text = self.context()
        self.assertIn("2000 kcal", text)
        self.assertIn("5 de 7", text)
        self.assertIn("80 %", text.replace("80%", "80 %"))

    def test_shows_the_sign_of_the_change(self):
        self.assertIn("-200 kcal", self.context())
        self.assertIn("+150 kcal", self.context(calorie_delta=150.0))

    def test_optional_metrics_are_omitted_when_absent(self):
        text = self.context()
        self.assertNotIn("Cambio de peso", text)
        self.assertNotIn("Pasos promedio", text)

    def test_optional_metrics_appear_when_given(self):
        text = self.context(weight_change=-0.5, avg_steps=8200)
        self.assertIn("Cambio de peso: -0.5 kg", text)
        self.assertIn("Pasos promedio: 8200", text)

    def test_carries_no_personal_identifiers(self):
        """Sólo se envían cifras agregadas al modelo."""
        text = self.context().lower()
        for forbidden in ("nombre", "correo", "@", "paciente_id", "uuid"):
            self.assertNotIn(forbidden, text)


class GenerateWeeklySummaryTests(unittest.TestCase):
    def test_returns_the_model_text(self):
        client = MagicMock()
        client.interactions.create.return_value = MagicMock(
            output_text="Registraste cinco de siete días."
        )
        with patch("weekly_summary.gemini_client_config", return_value=("key", "modelo")), \
             patch("weekly_summary.genai.Client", return_value=client):
            result = generate_weekly_summary("Semana de prueba")
        self.assertEqual(result, "Registraste cinco de siete días.")

    def test_sends_the_context_as_data(self):
        client = MagicMock()
        client.interactions.create.return_value = MagicMock(output_text="ok")
        with patch("weekly_summary.gemini_client_config", return_value=("key", "modelo")), \
             patch("weekly_summary.genai.Client", return_value=client):
            generate_weekly_summary("Meta de calorías: 2000 kcal")
        prompt = client.interactions.create.call_args.kwargs["input"]
        self.assertIn("<ficha>", prompt)
        self.assertIn("Meta de calorías: 2000 kcal", prompt)
        self.assertFalse(client.interactions.create.call_args.kwargs["store"])

    def test_empty_context_is_rejected_without_calling_the_model(self):
        with patch("weekly_summary.genai.Client") as client:
            with self.assertRaises(MealAIError):
                generate_weekly_summary("   ")
            client.assert_not_called()

    def test_empty_answer_raises(self):
        client = MagicMock()
        client.interactions.create.return_value = MagicMock(output_text="")
        with patch("weekly_summary.gemini_client_config", return_value=("key", "modelo")), \
             patch("weekly_summary.genai.Client", return_value=client):
            with self.assertRaises(MealAIError):
                generate_weekly_summary("Semana de prueba")

    def test_api_failure_becomes_a_readable_error(self):
        with patch("weekly_summary.gemini_client_config", return_value=("key", "modelo")), \
             patch("weekly_summary.genai.Client", side_effect=RuntimeError("cuota")):
            with self.assertRaises(MealAIError):
                generate_weekly_summary("Semana de prueba")


if __name__ == "__main__":
    unittest.main()
