from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest


APP_FILE = Path(__file__).resolve().parent / "app.py"


class AppSmokeTests(unittest.TestCase):
    @staticmethod
    def patient_context() -> tuple[dict, dict, dict]:
        auth = {
            "id": "user-1", "role": "patient", "full_name": "Paciente prueba",
            "patient_id": "patient-1", "invite_code": "CODE",
            "email": "patient@example.com",
        }
        profile = {
            "id": "patient-1", "name": "Paciente prueba", "age": 30,
            "sex": "Masculino", "weight": 80, "height": 175,
            "activity_level": "Sedentaria",
        }
        goals = {
            "patient_id": "patient-1", "calories": 2000, "protein": 120,
            "carbs": 220, "fat": 65, "fiber": 30, "water": 2500,
        }
        return auth, profile, goals

    def test_auth_screen_loads(self) -> None:
        app = AppTest.from_file(str(APP_FILE)).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], ["Iniciar sesión", "Crear cuenta"])

    def test_patient_can_save_timezone_and_uses_local_date(self) -> None:
        auth, profile, goals = self.patient_context()
        auth["timezone"] = "America/Chihuahua"
        empty_log = pd.DataFrame(
            columns=[
                "id", "log_date", "meal", "food", "quantity", "unit",
                "calories", "protein", "carbs", "fat", "fiber", "water",
                "source_name", "source_id",
            ]
        )
        with ExitStack() as stack:
            stack.enter_context(patch("db.get_auth_context", return_value=auth))
            stack.enter_context(patch("db.get_profile", return_value=profile))
            stack.enter_context(patch("db.get_goals", return_value=goals))
            stack.enter_context(patch("db.get_day_log", return_value=empty_log))
            stack.enter_context(
                patch("app_timezone.local_today", return_value=date(2026, 8, 8))
            )
            update_timezone = stack.enter_context(
                patch("db.update_account_timezone")
            )
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.run(timeout=20)

            selected_date = next(
                widget for widget in app.date_input if widget.label == "Fecha"
            )
            self.assertEqual(selected_date.value, date(2026, 8, 8))
            timezone_select = next(
                widget for widget in app.selectbox
                if widget.label == "Zona horaria"
            )
            timezone_select.set_value("Ciudad de México")
            next(
                button for button in app.button
                if button.label == "Guardar zona horaria"
            ).click().run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        update_timezone.assert_called_once_with(
            "user-1", "America/Mexico_City"
        )

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
            "activity_level": "Sedentaria",
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
            "portion_name": "pieza",
            "portion_grams": 50,
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

            default_energy = [metric for metric in app.metric if metric.label == "Energía"]
            self.assertEqual(default_energy[0].value, "200 kcal")
            household_unit = next(
                selectbox
                for selectbox in app.selectbox
                if "gramos" in selectbox.options and "pieza" in selectbox.options
            )
            household_unit.set_value("pieza").run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        energy_metrics = [metric for metric in app.metric if metric.label == "Energía"]
        self.assertEqual(energy_metrics[0].value, "100 kcal")

    def test_patient_can_edit_food_quantity_proportionally(self) -> None:
        auth, profile, goals = self.patient_context()
        log = pd.DataFrame(
            [{
                "id": 7, "log_date": "2026-08-08", "meal": "Desayuno",
                "food": "Huevo", "quantity": 1.0, "unit": "pieza",
                "calories": 100.0, "protein": 8.0, "carbs": 2.0,
                "fat": 6.0, "fiber": 0.0, "water": 30.0,
                "source_name": "SMAE 2014", "source_id": "SMAE:HUEVO",
            }]
        )
        with ExitStack() as stack:
            stack.enter_context(patch("db.get_auth_context", return_value=auth))
            stack.enter_context(patch("db.get_profile", return_value=profile))
            stack.enter_context(patch("db.get_goals", return_value=goals))
            stack.enter_context(patch("db.get_day_log", return_value=log))
            update_mock = stack.enter_context(patch("db.update_food"))
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.run(timeout=20)
            next(button for button in app.button if button.label == "✏️").click().run(timeout=20)
            quantity = next(
                widget for widget in app.number_input if widget.label == "Cantidad"
            )
            quantity.set_value(0.5)
            next(
                button for button in app.button if button.label == "Guardar cambios"
            ).click().run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        update_mock.assert_called_once()
        args = update_mock.call_args.args
        self.assertEqual(args[0:2], (7, "patient-1"))
        self.assertAlmostEqual(args[4], 0.5)
        self.assertAlmostEqual(args[6], 50.0)
        self.assertAlmostEqual(args[7], 4.0)

    def test_history_shows_body_progress(self) -> None:
        auth, profile, goals = self.patient_context()
        empty_history = pd.DataFrame(
            columns=["log_date", "calories", "protein", "carbs", "fat", "fiber", "water"]
        )
        measurements = pd.DataFrame(
            [
                {
                    "id": 1, "patient_id": "patient-1", "measured_on": "2026-07-01",
                    "device": "Tanita", "weight_kg": 80.0, "bmi": 26.1,
                    "body_fat_pct": 30.0, "muscle_pct": 34.0,
                    "basal_calories": 1600, "visceral_fat": 10,
                    "metabolic_age": 40, "notes": None,
                },
                {
                    "id": 2, "patient_id": "patient-1", "measured_on": "2026-08-01",
                    "device": "Tanita", "weight_kg": 78.0, "bmi": 25.5,
                    "body_fat_pct": 28.0, "muscle_pct": 35.0,
                    "basal_calories": 1590, "visceral_fat": 9,
                    "metabolic_age": 38, "notes": None,
                },
            ]
        )
        with ExitStack() as stack:
            stack.enter_context(patch("db.get_auth_context", return_value=auth))
            stack.enter_context(patch("db.get_profile", return_value=profile))
            stack.enter_context(patch("db.get_goals", return_value=goals))
            stack.enter_context(patch("db.get_history", return_value=empty_history))
            stack.enter_context(patch("db.get_body_measurements", return_value=measurements))
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.run(timeout=20)
            app.sidebar.radio[0].set_value("📊 Historial").run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        body_metric = next(metric for metric in app.metric if metric.label == "Peso actual")
        self.assertEqual(body_metric.value, "78.0 kg")

    def test_patient_can_delete_incorrect_body_measurement(self) -> None:
        auth, profile, goals = self.patient_context()
        measurement = pd.DataFrame(
            [{
                "id": 12, "patient_id": "patient-1", "measured_on": "2026-08-08",
                "device": "Tanita", "weight_kg": 180.0, "bmi": 58.8,
                "body_fat_pct": 70.0, "muscle_pct": 10.0,
                "basal_calories": 2000, "visceral_fat": 20,
                "metabolic_age": 80, "notes": "Captura incorrecta",
            }]
        )
        with ExitStack() as stack:
            stack.enter_context(patch("db.get_auth_context", return_value=auth))
            stack.enter_context(patch("db.get_profile", return_value=profile))
            stack.enter_context(patch("db.get_goals", return_value=goals))
            stack.enter_context(patch("db.get_body_measurements", return_value=measurement))
            stack.enter_context(patch("db.patient_has_nutritionist", return_value=False))
            delete_mock = stack.enter_context(patch("db.delete_body_measurement"))
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.run(timeout=20)
            app.sidebar.radio[0].set_value("👤 Perfil y metas").run(timeout=20)
            next(
                button for button in app.button if button.label == "🗑️ Eliminar"
            ).click().run(timeout=20)
            next(
                button for button in app.button
                if button.label == "Confirmar eliminación"
            ).click().run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        delete_mock.assert_called_once_with(12, "patient-1")

    def test_nutritionist_can_open_profile_calculator(self) -> None:
        empty_log = pd.DataFrame(
            columns=[
                "id", "log_date", "meal", "food", "quantity", "unit",
                "calories", "protein", "carbs", "fat", "fiber", "water",
                "source_name", "source_id",
            ]
        )
        auth = {
            "id": "nutritionist-1",
            "role": "nutritionist",
            "full_name": "Nutrióloga prueba",
            "patient_id": None,
            "invite_code": "NUTRI123",
            "email": "nutritionist@example.com",
        }
        patient = {
            "id": "patient-1", "name": "Paciente prueba", "age": 33,
            "sex": "Masculino", "weight": 84, "height": 170,
            "activity_level": "Moderada",
        }
        goals = {
            "patient_id": "patient-1", "calories": 2000, "protein": 120,
            "carbs": 220, "fat": 65, "fiber": 30, "water": 2500,
            "calculation_method": None, "resting_calories": None,
            "activity_factor": None, "calorie_adjustment_pct": None,
            "protein_pct": None, "carbs_pct": None, "fat_pct": None,
            "water_ml_per_kg": None,
        }
        with ExitStack() as stack:
            stack.enter_context(patch("db.get_auth_context", return_value=auth))
            stack.enter_context(patch("db.list_assigned_patients", return_value=[patient]))
            stack.enter_context(patch("db.get_goals", return_value=goals))
            stack.enter_context(patch("db.get_day_log", return_value=empty_log))
            stack.enter_context(patch("db.patient_has_nutritionist", return_value=True))
            stack.enter_context(patch("db.get_body_measurements", return_value=pd.DataFrame()))
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.run(timeout=20)
            app.sidebar.radio[0].set_value("👤 Perfil y metas").run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            [tab.label for tab in app.tabs],
            ["Perfil", "Metas nutricionales", "Composición corporal"],
        )
        self.assertIn("Gasto en reposo", [metric.label for metric in app.metric])

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

    def test_nutritionist_can_manage_recipes_without_patients(self) -> None:
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
            stack.enter_context(patch("db.list_owned_meal_templates", return_value=[]))
            app = AppTest.from_file(str(APP_FILE))
            app.session_state["access_token"] = "token"
            app.run(timeout=20)
            app.sidebar.radio[0].set_value("🍲 Recetas").run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        self.assertIn("🍲 Recetas del nutriólogo", [title.value for title in app.title])


if __name__ == "__main__":
    unittest.main()
