from __future__ import annotations

import unittest

from food_matching import (
    fold_accents,
    match_score,
    normalize,
    rank_by_relevance,
    search_terms,
)


class SearchTermsTests(unittest.TestCase):
    def test_keeps_short_but_meaningful_words(self):
        """El filtro anterior exigía 4 caracteres y descartaba "res"."""
        terms = search_terms("carne de res")
        self.assertIn("res", terms)
        self.assertEqual(terms[0], "carne de res")

    def test_drops_stopwords(self):
        terms = search_terms("pechuga de pollo con piel")
        self.assertNotIn("de", terms)
        self.assertNotIn("con", terms)
        self.assertIn("pechuga", terms)
        self.assertIn("pollo", terms)

    def test_longer_words_come_first(self):
        terms = search_terms("sopa de fideo")[1:]
        self.assertEqual(terms, sorted(terms, key=len, reverse=True))

    def test_ignores_accents_and_punctuation(self):
        self.assertEqual(normalize("Plátano, maduro"), "platano maduro")

    def test_empty_query_returns_nothing(self):
        self.assertEqual(search_terms("   "), [])


class MatchScoreTests(unittest.TestCase):
    def test_exact_name_scores_one(self):
        self.assertEqual(match_score("Tortilla de maíz", "tortilla de maiz"), 1.0)

    def test_reordered_name_beats_unrelated_food(self):
        """Buscar "carne de res" debe preferir la de res sobre la de cerdo."""
        good = match_score("carne de res", "Res, carne molida")
        bad = match_score("carne de res", "Carne de cerdo, lomo")
        self.assertGreater(good, bad)

    def test_unrelated_food_scores_low(self):
        self.assertLess(match_score("carne de res", "Manzana"), 0.4)


class RankByRelevanceTests(unittest.TestCase):
    def test_orders_by_similarity_not_alphabetically(self):
        # Ordenar por nombre dejaba arriba las carnes de cerdo y la de res
        # quedaba fuera del corte.
        rows = [
            {"name": "Carne de cerdo, chuleta"},
            {"name": "Carne de cerdo, lomo"},
            {"name": "Res, carne molida"},
        ]
        ranked = rank_by_relevance("carne de res", rows, limit=3)
        self.assertEqual(ranked[0]["name"], "Res, carne molida")
        self.assertIn("match_score", ranked[0])

    def test_respects_the_limit(self):
        rows = [{"name": f"Alimento {index}"} for index in range(10)]
        self.assertEqual(len(rank_by_relevance("alimento", rows, limit=4)), 4)


class FoldAccentsTests(unittest.TestCase):
    """La búsqueda del catálogo depende de que esto coincida con la base.

    `food_catalog.name_search` se calcula como `lower(unaccent(name))`. Si la
    normalización de Python difiere, escribir "platano" deja de encontrar
    "Plátano", que era el bug original: cerca del 18% de los alimentos
    importados tienen acento o ñ.
    """

    def test_removes_accents(self):
        self.assertEqual(fold_accents("Plátano"), "platano")

    def test_handles_enye(self):
        self.assertEqual(fold_accents("Piña Garapiñada"), "pina garapinada")

    def test_keeps_punctuation_and_spaces(self):
        # A diferencia de normalize(), aquí la puntuación se conserva porque
        # lower(unaccent(...)) de Postgres tampoco la quita.
        self.assertEqual(fold_accents("Zarzamora, Pulpa Con Azúcar"),
                         "zarzamora, pulpa con azucar")

    def test_lowercases(self):
        self.assertEqual(fold_accents("ACELGA"), "acelga")

    def test_empty_value(self):
        self.assertEqual(fold_accents(None), "")

    def test_a_query_without_accents_matches_the_stored_name(self):
        stored = fold_accents("Alga spirulina máxima")
        self.assertIn(fold_accents("maxima"), stored)


if __name__ == "__main__":
    unittest.main()
