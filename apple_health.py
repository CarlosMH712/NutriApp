"""Lectura del archivo de exportación de la app Salud de iPhone.

La app Salud exporta un ZIP que contiene `export.xml` con un registro por cada
muestra tomada por el iPhone y el Apple Watch. Aquí sólo se extrae el resumen
diario que interesa al seguimiento nutricional: pasos, calorías activas y
distancia, además de las sesiones de ejercicio.

Nota sobre el doble conteo: cuando el iPhone y el Apple Watch registran la misma
caminata, ambos guardan sus propias muestras. Sumarlas todas duplicaría los
pasos, así que se agrupa por dispositivo y se conserva, para cada día, el
dispositivo con el valor más alto.
"""

from __future__ import annotations

import zipfile
from collections import defaultdict
from datetime import date, datetime
from typing import Any, BinaryIO, Iterator
from xml.etree import ElementTree


STEP_TYPE = "HKQuantityTypeIdentifierStepCount"
ACTIVE_ENERGY_TYPE = "HKQuantityTypeIdentifierActiveEnergyBurned"
DISTANCE_TYPE = "HKQuantityTypeIdentifierDistanceWalkingRunning"
TRACKED_TYPES = {STEP_TYPE, ACTIVE_ENERGY_TYPE, DISTANCE_TYPE}

# Nombres legibles para los tipos de entrenamiento más comunes.
WORKOUT_NAMES = {
    "HKWorkoutActivityTypeRunning": "Correr",
    "HKWorkoutActivityTypeWalking": "Caminar",
    "HKWorkoutActivityTypeCycling": "Ciclismo",
    "HKWorkoutActivityTypeSwimming": "Natación",
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "Pesas",
    "HKWorkoutActivityTypeFunctionalStrengthTraining": "Fuerza funcional",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "HIIT",
    "HKWorkoutActivityTypeYoga": "Yoga",
    "HKWorkoutActivityTypeElliptical": "Elíptica",
    "HKWorkoutActivityTypeRowing": "Remo",
    "HKWorkoutActivityTypeDancing": "Baile",
    "HKWorkoutActivityTypeHiking": "Senderismo",
    "HKWorkoutActivityTypeCoreTraining": "Core",
    "HKWorkoutActivityTypeStairClimbing": "Escaleras",
}


class AppleHealthError(RuntimeError):
    """Raised when the Health export cannot be read."""


def workout_label(activity_type: object) -> str:
    raw = str(activity_type or "").strip()
    if raw in WORKOUT_NAMES:
        return WORKOUT_NAMES[raw]
    trimmed = raw.replace("HKWorkoutActivityType", "").strip()
    return trimmed or "Ejercicio"


def _parse_day(value: object) -> date | None:
    """Toma la fecha local del atributo startDate, ignorando la zona."""
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_float(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _open_export(file_obj: BinaryIO | str) -> Iterator[bytes]:
    """Entrega el contenido de export.xml, venga en ZIP o suelto."""
    if zipfile.is_zipfile(file_obj):
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with zipfile.ZipFile(file_obj) as bundle:
            names = [
                name for name in bundle.namelist()
                if name.endswith("export.xml") and not name.startswith("__MACOSX")
            ]
            if not names:
                raise AppleHealthError(
                    "El ZIP no contiene export.xml. Verifica que sea la "
                    "exportación completa de la app Salud."
                )
            with bundle.open(names[0]) as handle:
                yield from handle
        return
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
        yield from file_obj
        return
    with open(file_obj, "rb") as handle:
        yield from handle


def parse_health_export(
    file_obj: BinaryIO | str, max_days: int = 2000
) -> dict[str, Any]:
    """Devuelve {'days': [...], 'workouts': [...]} a partir de la exportación.

    Cada día trae log_date, steps, active_calories y distance_km. Cada
    entrenamiento trae log_date, exercise, duration_minutes y calories.
    """
    # (tipo, día, dispositivo) -> total, para descartar el doble conteo.
    by_source: dict[str, dict[date, dict[str, float]]] = {
        STEP_TYPE: defaultdict(lambda: defaultdict(float)),
        ACTIVE_ENERGY_TYPE: defaultdict(lambda: defaultdict(float)),
        DISTANCE_TYPE: defaultdict(lambda: defaultdict(float)),
    }
    workouts: list[dict[str, Any]] = []

    def stream() -> Iterator[bytes]:
        yield from _open_export(file_obj)

    try:
        parser = ElementTree.XMLPullParser(events=("end",))
        for chunk in stream():
            parser.feed(chunk)
            for _, element in parser.read_events():
                if element.tag == "Record":
                    record_type = element.get("type", "")
                    if record_type in TRACKED_TYPES:
                        day = _parse_day(element.get("startDate"))
                        value = _to_float(element.get("value"))
                        if day is not None and value is not None:
                            source = str(element.get("sourceName") or "desconocido")
                            by_source[record_type][day][source] += value
                    element.clear()
                elif element.tag == "Workout":
                    day = _parse_day(element.get("startDate"))
                    if day is not None:
                        workouts.append(
                            {
                                "log_date": day.isoformat(),
                                "exercise": workout_label(
                                    element.get("workoutActivityType")
                                ),
                                "duration_minutes": _to_float(element.get("duration")),
                                "calories": _to_float(
                                    element.get("totalEnergyBurned")
                                ),
                            }
                        )
                    element.clear()
    except AppleHealthError:
        raise
    except ElementTree.ParseError as exc:
        raise AppleHealthError(
            "No se pudo leer el XML de la exportación. Vuelve a generarla "
            "desde Salud > tu foto de perfil > Exportar todos los datos."
        ) from exc

    def best_per_day(record_type: str) -> dict[date, float]:
        return {
            day: max(sources.values())
            for day, sources in by_source[record_type].items()
            if sources
        }

    steps = best_per_day(STEP_TYPE)
    energy = best_per_day(ACTIVE_ENERGY_TYPE)
    distance = best_per_day(DISTANCE_TYPE)

    all_days = sorted(set(steps) | set(energy) | set(distance), reverse=True)
    if not all_days and not workouts:
        raise AppleHealthError(
            "La exportación no contiene pasos, calorías activas ni "
            "entrenamientos que se puedan importar."
        )

    days = [
        {
            "log_date": day.isoformat(),
            "steps": int(round(steps[day])) if day in steps else None,
            "active_calories": round(energy[day], 2) if day in energy else None,
            "distance_km": round(distance[day], 2) if day in distance else None,
        }
        for day in all_days[:max_days]
    ]
    workouts.sort(key=lambda item: str(item["log_date"]), reverse=True)
    return {"days": days, "workouts": workouts[:max_days]}
