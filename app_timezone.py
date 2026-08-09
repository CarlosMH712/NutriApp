from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "America/Chihuahua"

TIMEZONE_LABELS = {
    "Chihuahua": "America/Chihuahua",
    "Ciudad Juárez": "America/Ciudad_Juarez",
    "Ciudad de México": "America/Mexico_City",
    "Hermosillo": "America/Hermosillo",
    "Mazatlán": "America/Mazatlan",
    "Tijuana": "America/Tijuana",
    "Cancún": "America/Cancun",
}


def normalize_timezone(value: object) -> str:
    candidate = str(value or "").strip()
    if candidate not in TIMEZONE_LABELS.values():
        return DEFAULT_TIMEZONE
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return DEFAULT_TIMEZONE
    return candidate


def timezone_label(timezone_name: object) -> str:
    normalized = normalize_timezone(timezone_name)
    return next(
        (label for label, value in TIMEZONE_LABELS.items() if value == normalized),
        "Chihuahua",
    )


def local_today(
    timezone_name: object,
    now_utc: datetime | None = None,
) -> date:
    zone = ZoneInfo(normalize_timezone(timezone_name))
    if now_utc is None:
        return datetime.now(zone).date()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(zone).date()
