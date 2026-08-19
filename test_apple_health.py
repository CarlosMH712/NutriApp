from __future__ import annotations

import io
import unittest
import zipfile

from apple_health import AppleHealthError, parse_health_export, workout_label


EXPORT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="es_MX">
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Apple Watch"
   startDate="2026-08-17 08:00:00 -0600" value="4000" unit="count"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Apple Watch"
   startDate="2026-08-17 18:00:00 -0600" value="2500" unit="count"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone"
   startDate="2026-08-17 08:00:00 -0600" value="3800" unit="count"/>
 <Record type="HKQuantityTypeIdentifierActiveEnergyBurned" sourceName="Apple Watch"
   startDate="2026-08-17 08:00:00 -0600" value="180.5" unit="kcal"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="Apple Watch"
   startDate="2026-08-17 08:00:00 -0600" value="3.2" unit="km"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Apple Watch"
   startDate="2026-08-18 09:00:00 -0600" value="7100" unit="count"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch"
   startDate="2026-08-18 09:00:00 -0600" value="78" unit="count/min"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="32.5"
   durationUnit="min" totalEnergyBurned="280" startDate="2026-08-17 07:00:00 -0600"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeYoga" duration="45"
   durationUnit="min" startDate="2026-08-18 20:00:00 -0600"/>
</HealthData>
"""


def as_zip(xml: str = EXPORT_XML) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("apple_health_export/export.xml", xml)
    buffer.seek(0)
    return buffer


class ParseHealthExportTests(unittest.TestCase):
    def test_reads_days_from_a_zip(self):
        result = parse_health_export(as_zip())
        days = {day["log_date"]: day for day in result["days"]}
        self.assertEqual(set(days), {"2026-08-17", "2026-08-18"})

    def test_avoids_double_counting_between_devices(self):
        """El reloj y el teléfono registran la misma caminata.

        Sumar ambas fuentes daría 10300 pasos. Se conserva el dispositivo con
        el total más alto, que aquí es el reloj con 6500.
        """
        result = parse_health_export(as_zip())
        day = next(d for d in result["days"] if d["log_date"] == "2026-08-17")
        self.assertEqual(day["steps"], 6500)

    def test_reads_energy_and_distance(self):
        result = parse_health_export(as_zip())
        day = next(d for d in result["days"] if d["log_date"] == "2026-08-17")
        self.assertAlmostEqual(day["active_calories"], 180.5)
        self.assertAlmostEqual(day["distance_km"], 3.2)

    def test_missing_values_stay_empty(self):
        result = parse_health_export(as_zip())
        day = next(d for d in result["days"] if d["log_date"] == "2026-08-18")
        self.assertEqual(day["steps"], 7100)
        self.assertIsNone(day["active_calories"])

    def test_ignores_untracked_record_types(self):
        # La frecuencia cardiaca del XML no debe convertirse en un día extra.
        result = parse_health_export(as_zip())
        self.assertEqual(len(result["days"]), 2)

    def test_reads_workouts_with_readable_names(self):
        result = parse_health_export(as_zip())
        names = {workout["exercise"] for workout in result["workouts"]}
        self.assertEqual(names, {"Correr", "Yoga"})

    def test_workout_duration_and_calories(self):
        result = parse_health_export(as_zip())
        running = next(w for w in result["workouts"] if w["exercise"] == "Correr")
        self.assertAlmostEqual(running["duration_minutes"], 32.5)
        self.assertAlmostEqual(running["calories"], 280.0)

    def test_accepts_a_plain_xml_file(self):
        result = parse_health_export(io.BytesIO(EXPORT_XML.encode("utf-8")))
        self.assertEqual(len(result["days"]), 2)

    def test_zip_without_export_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("otra_cosa.txt", "contenido")
        buffer.seek(0)
        with self.assertRaises(AppleHealthError):
            parse_health_export(buffer)

    def test_export_without_activity_is_rejected(self):
        empty = '<?xml version="1.0" encoding="UTF-8"?>\n<HealthData locale="es_MX"/>\n'
        with self.assertRaises(AppleHealthError):
            parse_health_export(as_zip(empty))

    def test_unknown_workout_keeps_a_readable_label(self):
        self.assertEqual(workout_label("HKWorkoutActivityTypePilates"), "Pilates")
        self.assertEqual(workout_label(""), "Ejercicio")


if __name__ == "__main__":
    unittest.main()
