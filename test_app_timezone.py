from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from app_timezone import (
    DEFAULT_TIMEZONE,
    local_today,
    normalize_timezone,
    timezone_label,
)


class AppTimezoneTests(unittest.TestCase):
    def test_chihuahua_uses_previous_local_day_when_utc_is_after_midnight(self) -> None:
        now_utc = datetime(2026, 8, 9, 2, 30, tzinfo=timezone.utc)
        self.assertEqual(
            local_today("America/Chihuahua", now_utc),
            date(2026, 8, 8),
        )

    def test_unknown_timezone_falls_back_to_chihuahua(self) -> None:
        self.assertEqual(normalize_timezone("Zona inventada"), DEFAULT_TIMEZONE)
        self.assertEqual(timezone_label("Zona inventada"), "Chihuahua")


if __name__ == "__main__":
    unittest.main()
