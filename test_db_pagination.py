from __future__ import annotations

import unittest
from types import SimpleNamespace

import db


class FakeQuery:
    """Imita el corte de 1000 filas que aplica PostgREST."""

    def __init__(self, rows: list[dict], calls: list[tuple[int, int]]):
        self._rows = rows
        self._calls = calls
        self._start = 0
        self._end = 0

    def range(self, start: int, end: int) -> "FakeQuery":
        self._start, self._end = start, end
        self._calls.append((start, end))
        return self

    def execute(self) -> SimpleNamespace:
        window = self._rows[self._start : self._end + 1]
        # PostgREST nunca devuelve más de PAGE_SIZE filas por consulta.
        return SimpleNamespace(data=window[: db.PAGE_SIZE])


class FetchAllTests(unittest.TestCase):
    def build(self, total: int) -> tuple[list[dict], list[tuple[int, int]]]:
        rows = [{"id": index, "name": f"Alimento {index:05d}"} for index in range(total)]
        calls: list[tuple[int, int]] = []
        return rows, calls

    def test_reads_past_the_thousand_row_cap(self):
        """El catálogo de CONABIO tiene 1872 alimentos y se cortaba en 1000.

        Al pedir una sola página y ordenar por nombre, sólo se alcanzaban a ver
        los primeros alfabéticamente.
        """
        rows, calls = self.build(1872)
        fetched = db._fetch_all(lambda: FakeQuery(rows, calls))
        self.assertEqual(len(fetched), 1872)
        self.assertEqual(fetched[-1]["name"], "Alimento 01871")

    def test_requests_consecutive_pages(self):
        rows, calls = self.build(1872)
        db._fetch_all(lambda: FakeQuery(rows, calls))
        self.assertEqual(calls, [(0, 999), (1000, 1999)])

    def test_stops_on_a_short_page(self):
        rows, calls = self.build(120)
        fetched = db._fetch_all(lambda: FakeQuery(rows, calls))
        self.assertEqual(len(fetched), 120)
        self.assertEqual(len(calls), 1)

    def test_exact_multiple_needs_one_extra_page(self):
        rows, calls = self.build(db.PAGE_SIZE)
        fetched = db._fetch_all(lambda: FakeQuery(rows, calls))
        self.assertEqual(len(fetched), db.PAGE_SIZE)
        self.assertEqual(len(calls), 2)

    def test_empty_table_returns_nothing(self):
        rows, calls = self.build(0)
        self.assertEqual(db._fetch_all(lambda: FakeQuery(rows, calls)), [])


if __name__ == "__main__":
    unittest.main()
