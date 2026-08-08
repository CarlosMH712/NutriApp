from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher
import re
import unicodedata

import streamlit as st

from db import (
    create_meal_template,
    delete_meal_template,
    list_available_meal_templates,
    list_owned_meal_templates,
    save_food_entries,
    search_catalog,
)
from food_sources import (
    FoodSourceError,
    food_data_central_configured,
    search_food_data_central,
)
from meal_ai import MealAIConfigError, MealAIError, interpret_meal, openai_configured


MEALS = ["Desayuno", "Comida", "Cena", "Snack"]
NUTRIENT_FIELDS = ["calories", "protein", "carbs", "fat", "fiber", "water"]


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _match_score(query: str, candidate: str) -> float:
    left = _normalize(query)
    right = _normalize(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        containment = min(len(left), len(right)) / max(len(left), len(right))
        return 0.88 + 0.1 * containment
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence = SequenceMatcher(None, left, right).ratio()
    return 0.55 * sequence + 0.45 * overlap


def rank_catalog_matches(
    query: str, candidates: list[dict], limit: int = 8
) -> list[dict]:
    unique: dict[str, dict] = {}
    for candidate in candidates:
        key = str(candidate.get("result_key") or candidate.get("catalog_food_id") or "")
        if key:
            unique[key] = candidate
    ranked = [
        {
            **item,
            "match_score": _match_score(query, str(item.get("name") or "")),
        }
        for item in unique.values()
    ]
    return sorted(
        ranked,
        key=lambda item: float(item.get("match_score") or 0),
        reverse=True,
    )[:limit]


def _catalog_candidates(query: str) -> list[dict]:
    candidates: list[dict] = []
    search_terms = [query]
    ignored = {"con", "sin", "para", "tipo", "de", "del", "la", "el"}
    search_terms.extend(
        token for token in _normalize(query).split()
        if len(token) >= 4 and token not in ignored
    )
    seen_terms: set[str] = set()
    for term in search_terms[:5]:
        normalized = _normalize(term)
        if not normalized or normalized in seen_terms:
            continue
        seen_terms.add(normalized)
        try:
            candidates.extend(search_catalog(term, limit=15))
        except Exception:
            continue

    if not candidates and food_data_central_configured():
        try:
            candidates.extend(search_food_data_central(query, limit=8))
        except FoodSourceError:
            pass
    return rank_catalog_matches(query, candidates)


def _food_label(food: dict) -> str:
    brand = f" · {food['brand']}" if food.get("brand") else ""
    source = str(food.get("source") or "Catálogo")
    score = food.get("match_score")
    confidence = f" · coincidencia {float(score) * 100:.0f}%" if score is not None else ""
    return f"{food.get('name', 'Alimento')}{brand} — {source}{confidence}"


def _portion_matches(parsed_unit: str, portion_name: str) -> bool:
    parsed = _normalize(parsed_unit).rstrip("s")
    portion = _normalize(portion_name).rstrip("s")
    return bool(parsed and portion and (parsed == portion or parsed in portion or portion in parsed))


def calculate_component(food: dict, amount: float, unit_choice: str) -> dict:
    portion_name = str(food.get("portion_name") or "").strip()
    portion_grams = float(food.get("portion_grams") or 0)
    grams = (
        float(amount)
        if unit_choice == "gramos"
        else float(amount) * portion_grams
    )
    factor = grams / 100.0
    values = {
        field: float(food.get(f"{field}_per_100g") or 0) * factor
        for field in NUTRIENT_FIELDS
    }
    values.update(
        {
            "food_name": str(food.get("name") or "Alimento"),
            "quantity": float(amount),
            "unit": "g" if unit_choice == "gramos" else portion_name,
            "grams": grams,
            "catalog_food_id": food.get("catalog_food_id"),
            "source_name": str(food.get("source") or "Catálogo"),
            "source_id": str(food.get("source_id") or "") or None,
        }
    )
    return values


def _scaled_template_items(items: list[dict], multiplier: float) -> list[dict]:
    scaled: list[dict] = []
    for item in items:
        row = dict(item)
        row["quantity"] = float(item.get("quantity") or 0) * multiplier
        for field in NUTRIENT_FIELDS:
            row[field] = float(item.get(field) or 0) * multiplier
        scaled.append(row)
    return scaled


def _total(entries: list[dict], field: str) -> float:
    return sum(float(entry.get(field) or 0) for entry in entries)


def _show_totals(entries: list[dict]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Energía", f"{_total(entries, 'calories'):.0f} kcal")
    col2.metric("Proteína", f"{_total(entries, 'protein'):.1f} g")
    col3.metric("Carbohidratos", f"{_total(entries, 'carbs'):.1f} g")
    col4.metric("Grasas", f"{_total(entries, 'fat'):.1f} g")


def _clear_ai_result() -> None:
    st.session_state.pop("ai_meal_result", None)
    st.session_state.pop("ai_meal_description", None)


def render_ai_register(patient_id: str, selected_date: date) -> None:
    st.write(
        "Describe el platillo como lo dirías normalmente. La IA propondrá los "
        "componentes, pero los nutrientes siempre se obtienen del catálogo."
    )
    st.caption(
        "Al presionar Interpretar, se envía únicamente esta descripción a OpenAI. "
        "Evita escribir nombres, diagnósticos u otros datos personales."
    )
    if notice := st.session_state.pop("ai_saved_notice", None):
        st.success(str(notice))
    if not openai_configured():
        st.info(
            "Para activar esta función agrega la clave de OpenAI en los Secrets. "
            "Mientras tanto puedes seguir usando el catálogo y el registro manual."
        )

    with st.form("ai_meal_description_form"):
        description = st.text_area(
            "¿Qué comiste?",
            value=str(st.session_state.get("ai_meal_description") or ""),
            placeholder=(
                "Ej. Comí una hamburguesa con lechuga y un chile verde, sin queso"
            ),
            max_chars=2000,
        )
        interpret_submitted = st.form_submit_button(
            "✨ Interpretar platillo", use_container_width=True
        )

    if interpret_submitted:
        try:
            with st.spinner("Separando ingredientes y buscando equivalencias..."):
                parsed = interpret_meal(
                    description,
                    str(st.session_state.get("auth_user_id") or patient_id),
                )
                parsed_data = parsed.model_dump()
                for item in parsed_data["items"]:
                    item["matches"] = _catalog_candidates(item["name"])
                parsed_data["run_id"] = int(
                    st.session_state.get("ai_meal_run_id", 0)
                ) + 1
                st.session_state["ai_meal_run_id"] = parsed_data["run_id"]
                st.session_state["ai_meal_description"] = description
                st.session_state["ai_meal_result"] = parsed_data
                st.rerun()
        except (MealAIConfigError, MealAIError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("No se pudo preparar la revisión del platillo.")
            with st.expander("Detalle técnico"):
                st.code(str(exc))

    result = st.session_state.get("ai_meal_result")
    if not result:
        return

    st.subheader(f"Revisar: {result.get('dish_name') or 'Platillo'}")
    for detail in result.get("missing_details") or []:
        st.warning(str(detail))

    run_id = int(result.get("run_id") or 0)
    confirmed_items: list[dict] = []
    unresolved_items: list[str] = []
    for index, item in enumerate(result.get("items") or []):
        with st.expander(
            f"{index + 1}. {item.get('name', 'Alimento')}", expanded=True
        ):
            include = st.checkbox(
                "Incluir este componente", value=True,
                key=f"ai_include_{run_id}_{index}",
            )
            if item.get("assumption"):
                st.caption(f"Suposición de la IA: {item['assumption']}")
            if item.get("clarification_question"):
                st.warning(str(item["clarification_question"]))

            matches = item.get("matches") or []
            if not matches:
                st.error("No se encontró una coincidencia en el catálogo.")
                replacement_query = st.text_input(
                    "Buscar otra forma",
                    value=str(item.get("name") or ""),
                    key=f"ai_replacement_{run_id}_{index}",
                )
                if st.button(
                    "Buscar coincidencias",
                    key=f"ai_search_replacement_{run_id}_{index}",
                ):
                    item["matches"] = _catalog_candidates(replacement_query)
                    st.session_state["ai_meal_result"] = result
                    st.rerun()
                if include:
                    unresolved_items.append(str(item.get("name") or "Alimento"))
                continue

            selected_food = st.selectbox(
                "Coincidencia del catálogo",
                matches,
                format_func=_food_label,
                key=f"ai_match_{run_id}_{index}",
            )
            portion_name = str(selected_food.get("portion_name") or "").strip()
            portion_grams = float(selected_food.get("portion_grams") or 0)
            units = ["gramos"]
            if portion_name and portion_grams > 0:
                units.append(portion_name)
            default_unit_index = (
                1 if len(units) > 1 and _portion_matches(
                    str(item.get("unit") or ""), portion_name
                ) else 0
            )
            match_key = str(selected_food.get("result_key") or index).replace(":", "_")
            unit_choice = st.selectbox(
                "Unidad", units, index=default_unit_index,
                key=f"ai_unit_{run_id}_{index}_{match_key}",
            )
            if unit_choice == "gramos":
                default_amount = float(item.get("estimated_grams") or 100)
                step = 1.0
            else:
                default_amount = float(item.get("quantity") or 1)
                step = 0.25
            amount = st.number_input(
                f"Cantidad ({unit_choice})",
                min_value=0.01,
                value=max(default_amount, 0.01),
                step=step,
                key=f"ai_amount_{run_id}_{index}_{match_key}_{unit_choice}",
            )
            component = calculate_component(selected_food, amount, unit_choice)
            st.caption(
                f"Equivale a {component['grams']:.1f} g · "
                f"{component['calories']:.0f} kcal · "
                f"P {component['protein']:.1f} g · "
                f"CHO {component['carbs']:.1f} g · G {component['fat']:.1f} g"
            )
            if include:
                confirmed_items.append(component)

    st.markdown("##### ¿Falta algún componente?")
    extra_component = st.text_input(
        "Agregar otro alimento",
        placeholder="Ej. mayonesa, queso o aguacate",
        key=f"ai_extra_component_{run_id}",
    )
    if st.button("Agregar a la revisión", key=f"ai_add_component_{run_id}"):
        if extra_component.strip():
            result.setdefault("items", []).append(
                {
                    "name": extra_component.strip(),
                    "quantity": 1.0,
                    "unit": "porción",
                    "estimated_grams": 100.0,
                    "preparation": "",
                    "assumption": "Componente agregado por el usuario; revisa su cantidad.",
                    "needs_clarification": False,
                    "clarification_question": "",
                    "matches": _catalog_candidates(extra_component),
                }
            )
            st.session_state["ai_meal_result"] = result
            st.rerun()

    if confirmed_items:
        st.subheader("Total propuesto")
        _show_totals(confirmed_items)
    if unresolved_items:
        st.error(
            "Falta resolver: " + ", ".join(unresolved_items)
            + ". Busca una coincidencia o excluye ese componente."
        )

    suggested_meal = str(result.get("suggested_meal") or "Comida")
    meal_index = MEALS.index(suggested_meal) if suggested_meal in MEALS else 1
    meal = st.selectbox(
        "Tiempo de comida", MEALS, index=meal_index,
        key=f"ai_meal_{run_id}",
    )
    save_favorite = st.checkbox(
        "Guardar también como platillo frecuente",
        key=f"ai_save_favorite_{run_id}",
    )
    favorite_name = ""
    if save_favorite:
        favorite_name = st.text_input(
            "Nombre del platillo frecuente",
            value=str(result.get("dish_name") or "Mi platillo"),
            key=f"ai_favorite_name_{run_id}",
        )

    register_disabled = not confirmed_items or bool(unresolved_items)
    if st.button(
        "✅ Confirmar y registrar componentes",
        use_container_width=True,
        disabled=register_disabled,
        key=f"ai_confirm_{run_id}",
    ):
        try:
            saved = save_food_entries(patient_id, selected_date, meal, confirmed_items)
            favorite_warning = ""
            if save_favorite:
                try:
                    create_meal_template(
                        favorite_name or str(
                            result.get("dish_name") or "Mi platillo"
                        ),
                        "patient_favorite",
                        patient_id,
                        meal,
                        confirmed_items,
                    )
                except Exception:
                    favorite_warning = (
                        " No se pudo guardar como frecuente; revisa que la "
                        "migración V0.7 esté instalada."
                    )
            _clear_ai_result()
            st.session_state["ai_saved_notice"] = (
                f"Platillo registrado con {saved} componentes.{favorite_warning}"
            )
            st.rerun()
        except Exception as exc:
            st.error("No se pudo guardar el platillo.")
            st.code(str(exc))

def render_saved_meals(patient_id: str, selected_date: date) -> None:
    st.write(
        "Registra nuevamente un platillo frecuente o una receta compartida por tu nutriólogo."
    )
    try:
        templates = list_available_meal_templates(patient_id)
    except Exception as exc:
        st.warning(
            "Los platillos guardados estarán disponibles después de ejecutar la migración V0.7."
        )
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        return
    if not templates:
        st.info(
            "Todavía no hay platillos guardados. Puedes crear uno al confirmar una "
            "interpretación con IA."
        )
        return

    current_user_id = str(st.session_state.get("auth_user_id") or "")
    for template in templates:
        kind = (
            "Platillo frecuente"
            if template.get("template_type") == "patient_favorite"
            else "Receta del nutriólogo"
        )
        items = template.get("items") or []
        with st.expander(f"{template['name']} · {kind}", expanded=False):
            for item in items:
                st.caption(
                    f"• {item['food_name']}: {float(item['quantity']):g} "
                    f"{item['unit']} · {float(item['calories']):.0f} kcal"
                )
            multiplier = st.number_input(
                "Porciones", min_value=0.25, value=1.0, step=0.25,
                key=f"template_multiplier_{template['id']}",
            )
            scaled_items = _scaled_template_items(items, float(multiplier))
            _show_totals(scaled_items)
            default_meal = str(template.get("default_meal") or "Comida")
            meal_index = MEALS.index(default_meal) if default_meal in MEALS else 1
            meal = st.selectbox(
                "Tiempo de comida", MEALS, index=meal_index,
                key=f"template_meal_{template['id']}",
            )
            if st.button(
                "Registrar platillo", key=f"register_template_{template['id']}",
                use_container_width=True,
            ):
                try:
                    save_food_entries(patient_id, selected_date, meal, scaled_items)
                    st.success("Platillo registrado.")
                except Exception as exc:
                    st.error("No se pudo registrar el platillo.")
                    st.code(str(exc))
            if str(template.get("created_by") or "") == current_user_id:
                if st.button(
                    "Eliminar de mis frecuentes",
                    key=f"delete_template_{template['id']}",
                ):
                    try:
                        delete_meal_template(str(template["id"]))
                        st.rerun()
                    except Exception as exc:
                        st.error("No se pudo eliminar el platillo.")
                        st.code(str(exc))


def render_recipe_admin() -> None:
    st.title("🍲 Recetas del nutriólogo")
    st.write(
        "Construye recetas con alimentos del catálogo. Estarán disponibles para "
        "todos tus pacientes vinculados."
    )
    draft: list[dict] = st.session_state.setdefault("recipe_draft_items", [])

    with st.form("recipe_catalog_search"):
        query = st.text_input(
            "Buscar componente", placeholder="Ej. pan de hamburguesa"
        )
        search_submitted = st.form_submit_button("Buscar")
    if search_submitted:
        st.session_state["recipe_search_results"] = _catalog_candidates(query)

    results = st.session_state.get("recipe_search_results") or []
    if results:
        selected_food = st.selectbox(
            "Alimento", results, format_func=_food_label,
            key="recipe_selected_food",
        )
        portion_name = str(selected_food.get("portion_name") or "").strip()
        portion_grams = float(selected_food.get("portion_grams") or 0)
        units = ["gramos"] + (
            [portion_name] if portion_name and portion_grams > 0 else []
        )
        unit_choice = st.selectbox("Unidad", units, key="recipe_component_unit")
        amount = st.number_input(
            "Cantidad", min_value=0.01,
            value=100.0 if unit_choice == "gramos" else 1.0,
            step=1.0 if unit_choice == "gramos" else 0.25,
            key=f"recipe_component_amount_{unit_choice}",
        )
        preview = calculate_component(selected_food, amount, unit_choice)
        st.caption(
            f"{preview['grams']:.1f} g · {preview['calories']:.0f} kcal"
        )
        if st.button("Agregar componente", use_container_width=True):
            draft.append(preview)
            st.session_state["recipe_draft_items"] = draft
            st.rerun()

    st.subheader("Componentes de la receta")
    if not draft:
        st.info("Busca y agrega al menos un alimento.")
    else:
        for index, item in enumerate(draft):
            col1, col2 = st.columns([8, 1])
            col1.write(
                f"{index + 1}. **{item['food_name']}** · "
                f"{item['quantity']:g} {item['unit']} · "
                f"{item['calories']:.0f} kcal"
            )
            if col2.button("🗑️", key=f"remove_recipe_item_{index}"):
                draft.pop(index)
                st.session_state["recipe_draft_items"] = draft
                st.rerun()
        _show_totals(draft)

    with st.form("save_nutritionist_recipe"):
        recipe_name = st.text_input("Nombre de la receta")
        default_meal = st.selectbox("Tiempo de comida sugerido", MEALS, index=1)
        save_recipe = st.form_submit_button(
            "Guardar receta para mis pacientes", use_container_width=True,
            disabled=not draft,
        )
    if save_recipe:
        try:
            create_meal_template(
                recipe_name,
                "nutritionist_recipe",
                None,
                default_meal,
                draft,
            )
            st.session_state["recipe_draft_items"] = []
            st.session_state.pop("recipe_search_results", None)
            st.success("Receta guardada y compartida con tus pacientes.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo guardar la receta.")
            st.code(str(exc))

    st.subheader("Mis recetas")
    try:
        owned = [
            template for template in list_owned_meal_templates()
            if template.get("template_type") == "nutritionist_recipe"
        ]
    except Exception as exc:
        st.warning("Ejecuta la migración V0.7 para administrar recetas.")
        st.code(str(exc))
        return
    if not owned:
        st.info("Todavía no has guardado recetas.")
    for template in owned:
        columns = st.columns([7, 2, 1])
        columns[0].write(f"**{template['name']}**")
        columns[1].caption(f"{len(template.get('items') or [])} componentes")
        if columns[2].button("🗑️", key=f"delete_owned_recipe_{template['id']}"):
            try:
                delete_meal_template(str(template["id"]))
                st.rerun()
            except Exception as exc:
                st.error("No se pudo eliminar la receta.")
                st.code(str(exc))
