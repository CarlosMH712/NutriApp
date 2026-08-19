"""Normalización y puntuación de nombres de alimentos.

La búsqueda del catálogo y el emparejamiento de los componentes que devuelve la
IA necesitan el mismo criterio. Tenerlo en un solo lugar evita que una búsqueda
encuentre un alimento y la otra no.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


# Palabras que no aportan a la búsqueda. Se listan explícitamente porque el
# filtro por longitud descartaba términos cortos pero decisivos como "res".
STOPWORDS = {
    "con", "sin", "para", "tipo", "de", "del", "la", "el", "los", "las",
    "un", "una", "uno", "y", "o", "al", "en", "por", "que", "su",
}

# Longitud mínima de un término de búsqueda. Tres caracteres permiten "res",
# "soya" y "ajo", que antes se perdían.
MIN_TERM_LENGTH = 3


def fold_accents(value: object) -> str:
    """Minúsculas sin acentos, conservando espacios y puntuación.

    Debe coincidir con la columna `food_catalog.name_search`, que la base
    calcula como `lower(unaccent(name))`. Si las dos normalizaciones difieren,
    la búsqueda deja de encontrar alimentos.
    """
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def normalize(value: object) -> str:
    """Minúsculas sin acentos ni puntuación, para comparar nombres."""
    return re.sub(r"[^a-z0-9]+", " ", fold_accents(value)).strip()


def match_score(query: str, candidate: str) -> float:
    """Qué tanto se parece un nombre del catálogo a lo que se busca, de 0 a 1."""
    left = normalize(query)
    right = normalize(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        containment = min(len(left), len(right)) / max(len(left), len(right))
        return 0.88 + 0.1 * containment

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    significant = {token for token in left_tokens if token not in STOPWORDS}
    overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence = SequenceMatcher(None, left, right).ratio()
    score = 0.55 * sequence + 0.45 * overlap

    # "Carne de res" contra "Res, carne molida" comparte todas sus palabras
    # significativas aunque el orden y el relleno cambien. Sin este empujón,
    # el resultado correcto quedaba por debajo de coincidencias alfabéticas.
    if significant and significant.issubset(right_tokens):
        score = max(score, 0.80 + 0.05 * (len(significant) / max(len(right_tokens), 1)))
    return min(score, 1.0)


def search_terms(query: str, limit: int = 5) -> list[str]:
    """Términos con los que vale la pena consultar el catálogo.

    Devuelve la frase completa primero y después sus palabras significativas,
    de la más larga a la más corta, porque las largas son más discriminantes.
    """
    normalized = normalize(query)
    if not normalized:
        return []
    tokens = [
        token
        for token in dict.fromkeys(normalized.split())
        if len(token) >= MIN_TERM_LENGTH and token not in STOPWORDS
    ]
    tokens.sort(key=len, reverse=True)
    terms = [normalized, *tokens]
    return list(dict.fromkeys(terms))[:limit]


def rank_by_relevance(
    query: str, rows: list[dict], limit: int, name_key: str = "name"
) -> list[dict]:
    """Ordena por parecido real al término buscado, no alfabéticamente."""
    scored = [
        {**row, "match_score": match_score(query, str(row.get(name_key) or ""))}
        for row in rows
    ]
    scored.sort(key=lambda row: float(row.get("match_score") or 0), reverse=True)
    return scored[: max(int(limit), 1)]
