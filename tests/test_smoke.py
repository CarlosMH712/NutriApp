from __future__ import annotations

import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


class AppSmokeTests(unittest.TestCase):
    def test_auth_screen_loads(self) -> None:
        app = AppTest.from_file(str(APP_FILE)).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], ["Iniciar sesión", "Crear cuenta"])

    def test_patient_catalog_calculates_default_100g(self) -> None:
        empty_log = pd.DataFrame(
            columns=[
                "id",
                "log_date",
                "meal",
                "food",
                "quantity",
                "unit",
                "calories",
                "protein",
                "carbs",
                "fat",
                "fiber",
                "water",
                "source_name",
                "source_id",
            ]
        )
        auth = {
            "id": "user-1",
            "role": "patient",
            "full_name": "Paciente prueba",
            "patient_id": "patient-1",
            "invite_code": "CODE",
            "email": "patient@example.com",
        }
        profile = {
            "id": "patient-1",
            "name": "Paciente prueba",
            "age": 30,
            "sex": "Otro / no especificado",
            "weight": 70,
            "height": 170,
        }
        goals = {
            "patient_id": "patient-1",
            "calories": 2000,
            "protein": 120,
            "carbs": 220,
            "fat": 65,
            "fiber": 30,
            "water": 2500,
        }
        catalog_result = {
            "result_key": "catalog:food-1",
            "catalog_food_id": "food-1",
            "name": "Alimento prueba",
            "brand": None,
            "source": "Nutriólogo",
            "source_id": "food-1",
            "verified": True,
            "portion_name": None,
            "portion_grams": None,
            "calories_per_100g": 200,
            "protein_per_100g": 10,
            "carbs_per_100g": 20,
            "fat_per_100g": 5,
            "fiber_per_100g": 2,
            "water_per_100g": 50,
        }

        with ExitStack() as stack:
            stack.enter_context(patch("db.get_auth_context", return_value=auth))
            stack.enter_context(patch("db.get_profile", return_value=profile))
            stack.enter_context(patch("db.get_goals", return_value=goals))
            stack.enter_context(patch("db.get_day_log", return_value=empty_log))
            stack.enter_context(patch("db.patient_has_nutritionist", return_value=False))
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.session_state["food_search_results"] = [catalog_result]
            app.run(timeout=20)
            app.sidebar.radio[0].set_value("➕ Registrar").run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        energy_metrics = [metric for metric in app.metric if metric.label == "Energía"]
        self.assertEqual(energy_metrics[0].value, "200 kcal")

    def test_nutritionist_can_open_catalog_without_patients(self) -> None:
        auth = {
            "id": "nutritionist-1",
            "role": "nutritionist",
            "full_name": "Nutrióloga prueba",
            "patient_id": None,
            "invite_code": "NUTRI123",
            "email": "nutritionist@example.com",
        }
        with ExitStack() as stack:
            stack.enter_context(patch("db.get_auth_context", return_value=auth))
            stack.enter_context(patch("db.list_assigned_patients", return_value=[]))
            stack.enter_context(patch("db.list_owned_catalog", return_value=[]))
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.run(timeout=20)
            app.sidebar.radio[0].set_value("🍎 Catálogo").run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        self.assertIn("🍎 Catálogo de alimentos", [title.value for title in app.title])


if __name__ == "__main__":
    unittest.main()
