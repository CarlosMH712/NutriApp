"""Métricas de adherencia al plan nutricional.

Se separan del acceso a datos y de la interfaz para poder verificarlas: son las
cifras que la nutrióloga va a leer en consulta y no deben depender de cómo se
dibuje la pantalla.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


# Un día cuenta como dentro de meta si queda a ±10% de las calorías objetivo.
DEFAULT_TOLERANCE = 0.10


def _tolerance_bounds(goal: float, tolerance: float) -> tuple[float, float]:
    margin = abs(goal) * tolerance
    return goal - margin, goal + margin


def daily_totals(history: pd.DataFrame) -> pd.DataFrame:
    """Suma por día el registro crudo de alimentos."""
    columns = ["calories", "protein", "carbs", "fat", "fiber", "water"]
    if history.empty:
        return pd.DataFrame(columns=["log_date", *columns])
    data = history.copy()
    data["log_date"] = pd.to_datetime(data["log_date"])
    for column in columns:
        if column not in data:
            data[column] = 0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    return (
        data.groupby("log_date", as_index=False)[columns].sum().sort_values("log_date")
    )


def calorie_adherence(
    totals: pd.DataFrame,
    goal_calories: float,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, float]:
    """Qué tan seguido el consumo quedó dentro del rango objetivo.

    `adherence_pct` se calcula sobre los días registrados, no sobre los días
    del periodo: un paciente que registró tres días y acertó los tres tuvo 100%
    de adherencia con 3 días de registro. Ambas cifras se devuelven para que la
    interfaz muestre las dos y no se lea una sola fuera de contexto.
    """
    logged = int(len(totals))
    if logged == 0 or goal_calories <= 0:
        return {
            "days_logged": logged,
            "days_on_target": 0,
            "adherence_pct": 0.0,
            "avg_calories": 0.0,
        }

    low, high = _tolerance_bounds(float(goal_calories), tolerance)
    calories = pd.to_numeric(totals["calories"], errors="coerce").fillna(0)
    on_target = int(((calories >= low) & (calories <= high)).sum())
    return {
        "days_logged": logged,
        "days_on_target": on_target,
        "adherence_pct": round(on_target / logged * 100, 1),
        "avg_calories": round(float(calories.mean()), 1),
    }


def logging_rate(totals: pd.DataFrame, period_days: int) -> float:
    """Porcentaje de días del periodo con al menos un alimento registrado."""
    if period_days <= 0:
        return 0.0
    return round(min(len(totals) / period_days, 1.0) * 100, 1)


def window(totals: pd.DataFrame, end: date, days: int) -> pd.DataFrame:
    """Recorta los totales al periodo que termina en `end`."""
    if totals.empty:
        return totals
    start = pd.Timestamp(end - timedelta(days=max(days, 1) - 1))
    return totals[
        (totals["log_date"] >= start) & (totals["log_date"] <= pd.Timestamp(end))
    ]


def weekly_comparison(
    totals: pd.DataFrame, end: date, goal_calories: float
) -> dict[str, object]:
    """Compara la semana que termina en `end` contra la anterior."""
    current = window(totals, end, 7)
    previous = window(totals, end - timedelta(days=7), 7)

    current_stats = calorie_adherence(current, goal_calories)
    previous_stats = calorie_adherence(previous, goal_calories)
    delta = current_stats["avg_calories"] - previous_stats["avg_calories"]
    return {
        "current": current_stats,
        "previous": previous_stats,
        "calorie_delta": round(delta, 1),
        "logging_rate": logging_rate(current, 7),
    }


def days_since_last_log(totals: pd.DataFrame, today: date) -> int | None:
    """Días transcurridos desde el último registro; None si nunca registró."""
    if totals.empty:
        return None
    last = pd.to_datetime(totals["log_date"]).max().date()
    return max((today - last).days, 0)
