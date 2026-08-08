from __future__ import annotations

import hashlib
from typing import Literal

import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, Field


class MealAIConfigError(RuntimeError):
    """Raised when the OpenAI configuration is missing."""


class MealAIError(RuntimeError):
    """Raised when a meal description cannot be interpreted."""


class ParsedFood(BaseModel):
    name: str = Field(description="Nombre genérico del alimento en español")
    quantity: float = Field(gt=0, description="Cantidad expresada por el usuario o estimada")
    unit: str = Field(description="Unidad casera, por ejemplo pieza, taza o gramos")
    estimated_grams: float | None = Field(
        gt=0,
        description="Estimación de gramos sólo para facilitar la revisión",
    )
    preparation: str = Field(description="Preparación indicada, o cadena vacía")
    assumption: str = Field(
        description="Suposición realizada sobre cantidad o componente, o cadena vacía"
    )
    needs_clarification: bool
    clarification_question: str = Field(
        description="Pregunta breve para el usuario, o cadena vacía"
    )


class ParsedMeal(BaseModel):
    dish_name: str
    suggested_meal: Literal["Desayuno", "Comida", "Cena", "Snack"]
    items: list[ParsedFood] = Field(min_length=1, max_length=15)
    missing_details: list[str] = Field(max_length=8)


SYSTEM_PROMPT = """
Eres un extractor de alimentos para una aplicación mexicana de nutrición.
Convierte la descripción en componentes alimentarios concretos y revisables.

Reglas obligatorias:
- No calcules ni inventes calorías, macronutrientes ni valores nutrimentales.
- Descompón platillos compuestos en sus ingredientes estructurales habituales. Por
  ejemplo, una hamburguesa incluye al menos pan y carne; agrega lechuga, chile,
  queso, aderezos u otros componentes sólo cuando el usuario los mencione o cuando
  sean indispensables para el platillo.
- No asumas silenciosamente ingredientes opcionales con impacto calórico, como
  queso, mayonesa, aceite, crema, azúcar o bebidas. Agrégalos a missing_details como
  preguntas si pueden cambiar materialmente el resultado.
- Conserva cantidades y medidas caseras mencionadas por el usuario.
- Si falta una cantidad, propón una porción convencional prudente, indícala en
  assumption y marca needs_clarification=true.
- estimated_grams es sólo una estimación de porción para que el usuario la corrija;
  nunca representa una fuente nutrimental.
- Usa nombres genéricos fáciles de buscar en un catálogo mexicano. Distingue
  preparación cuando sea relevante, por ejemplo cocido, frito, asado o crudo.
- Si un término es ambiguo, formula una pregunta breve en clarification_question.
- Responde siempre en español y limita el resultado a 15 componentes.
""".strip()


def _config() -> tuple[str, str]:
    try:
        cfg = st.secrets["openai"]
        api_key = str(cfg["api_key"]).strip()
        model = str(cfg.get("model", "gpt-4o-mini")).strip()
    except (KeyError, FileNotFoundError) as exc:
        raise MealAIConfigError(
            "Falta configurar [openai].api_key en los Secrets de Streamlit."
        ) from exc
    if not api_key:
        raise MealAIConfigError("La clave de OpenAI está vacía.")
    return api_key, model or "gpt-4o-mini"


def openai_configured() -> bool:
    try:
        _config()
        return True
    except MealAIConfigError:
        return False


def privacy_safe_identifier(user_id: str) -> str:
    normalized = user_id.strip() or "anonymous"
    return "nutrition-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def interpret_meal(description: str, user_id: str) -> ParsedMeal:
    clean_description = description.strip()
    if len(clean_description) < 3:
        raise MealAIError("Describe con un poco más de detalle lo que comiste.")
    if len(clean_description) > 2000:
        raise MealAIError("La descripción debe tener máximo 2000 caracteres.")

    api_key, model = _config()
    try:
        response = OpenAI(api_key=api_key).responses.parse(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=clean_description,
            text_format=ParsedMeal,
            max_output_tokens=1400,
            store=False,
            safety_identifier=privacy_safe_identifier(user_id),
        )
    except Exception as exc:
        raise MealAIError(
            "No fue posible interpretar el platillo en este momento. Intenta nuevamente."
        ) from exc

    parsed = response.output_parsed
    if parsed is None or not parsed.items:
        raise MealAIError(
            "La IA no devolvió componentes revisables. Intenta describir los alimentos por separado."
        )
    return parsed
