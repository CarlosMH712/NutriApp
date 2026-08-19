from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app_timezone import (
    TIMEZONE_LABELS,
    local_today,
    normalize_timezone,
    timezone_label,
)
from db import (
    AuthenticationError,
    DatabaseConfigError,
    add_catalog_portion,
    clear_auth_session,
    count_owned_catalog,
    create_catalog_food,
    delete_body_measurement,
    delete_catalog_food,
    delete_catalog_portion,
    delete_food,
    get_auth_context,
    get_body_measurements,
    get_day_log,
    get_goals,
    get_history,
    get_profile,
    import_catalog_foods,
    link_nutritionist,
    list_assigned_patients,
    list_owned_catalog,
    patient_has_nutritionist,
    save_food,
    save_body_measurement,
    search_catalog,
    set_catalog_food_liquid,
    sign_in,
    sign_out,
    sign_up,
    update_food,
    update_account_timezone,
    update_body_measurement,
    update_goals,
    update_patient_weight,
    update_profile,
)
from food_sources import (
    FoodSourceError,
    food_data_central_configured,
    search_food_data_central,
)
from food_measurements import (
    GRAMS,
    MILLILITERS,
    calculate_food_serving,
    effective_water_ml,
    food_portions,
    is_plain_water_name,
    measurement_options,
    volume_ml_from_quantity,
)
from nutrition_calculations import (
    ACTIVITY_FACTORS,
    calculate_bmi,
    calculate_nutrition_targets,
    mifflin_st_jeor,
)
from nutrition_charts import stable_line_chart
from meal_workflows import (
    render_ai_register,
    render_recipe_admin,
    render_saved_meals,
)
from activity_workflows import (
    render_activity_history,
    render_activity_register,
)


st.set_page_config(page_title="Mi Nutrición", page_icon="🥗", layout="wide")

SELF_TRACKING_LABEL = "👤 Mi propio seguimiento"


def auth_screen() -> dict:
    if st.session_state.get("access_token"):
        try:
            return get_auth_context()
        except AuthenticationError:
            pass
        except Exception as exc:
            clear_auth_session()
            st.warning("No se pudo restaurar tu sesión. Inicia sesión nuevamente.")
            with st.expander("Detalle técnico"):
                st.code(str(exc))

    st.title("🥗 Mi Nutrición")
    st.write("Registra tus alimentos y da seguimiento a tus metas nutricionales.")
    login_tab, register_tab = st.tabs(["Iniciar sesión", "Crear cuenta"])

    with login_tab:
        st.caption(
            "En un dispositivo personal, permite que el navegador guarde tus "
            "credenciales. Después podrá completarlas usando huella, Face ID o PIN."
        )
        with st.form("login_form"):
            email = st.text_input(
                "Correo electrónico",
                key="login_email",
                autocomplete="username",
            )
            password = st.text_input(
                "Contraseña",
                type="password",
                key="login_password",
                autocomplete="current-password",
            )
            login_submitted = st.form_submit_button(
                "Entrar", width="stretch"
            )
        if login_submitted:
            if not email.strip() or not password:
                st.error("Escribe tu correo y contraseña.")
            else:
                try:
                    sign_in(email, password)
                    st.rerun()
                except DatabaseConfigError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error("No fue posible iniciar sesión. Revisa tu correo y contraseña.")
                    with st.expander("Detalle técnico"):
                        st.code(str(exc))

    with register_tab:
        st.caption("Las cuentas nuevas se crean como pacientes.")
        with st.form("register_form"):
            full_name = st.text_input("Nombre completo")
            new_email = st.text_input(
                "Correo electrónico",
                key="register_email",
                autocomplete="email",
            )
            new_password = st.text_input(
                "Contraseña (mínimo 8 caracteres)",
                type="password",
                key="register_password",
                autocomplete="new-password",
            )
            confirm_password = st.text_input(
                "Confirmar contraseña", type="password",
                autocomplete="new-password",
            )
            register_submitted = st.form_submit_button(
                "Crear mi cuenta", width="stretch"
            )
        if register_submitted:
            if not full_name.strip() or not new_email.strip():
                st.error("Completa tu nombre y correo.")
            elif len(new_password) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
            elif new_password != confirm_password:
                st.error("Las contraseñas no coinciden.")
            else:
                try:
                    confirmation_pending = sign_up(
                        new_email, new_password, full_name
                    )
                    if confirmation_pending:
                        st.success(
                            "Cuenta creada. Revisa tu correo y confirma la cuenta antes de iniciar sesión."
                        )
                    else:
                        st.rerun()
                except DatabaseConfigError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error("No fue posible crear la cuenta.")
                    with st.expander("Detalle técnico"):
                        st.code(str(exc))

    st.stop()


def progress_value(consumed: float, goal: float) -> float:
    if goal <= 0:
        return 0.0
    return min(max(float(consumed) / float(goal), 0.0), 1.0)


def nutrient_progress(title: str, consumed: float, goal: float, unit: str) -> None:
    st.write(f"**{title}**")
    st.progress(progress_value(consumed, goal))
    remaining = max(float(goal) - float(consumed), 0.0)
    st.caption(
        f"{consumed:.1f} / {goal:.1f} {unit} · Restante: {remaining:.1f} {unit}"
    )


def totals_for_day(df: pd.DataFrame) -> dict[str, float]:
    keys = ["calories", "protein", "carbs", "fat", "fiber", "water"]
    if df.empty:
        return {key: 0.0 for key in keys}
    totals = {key: float(df[key].fillna(0).sum()) for key in keys}
    totals["water"] = float(
        df.apply(
            lambda row: effective_water_ml(
                row.get("food"),
                float(row.get("quantity") or 0),
                row.get("unit"),
                float(row.get("water") or 0),
            ),
            axis=1,
        ).sum()
    )
    return totals


def _scaled_food_values(row: pd.Series, quantity: float) -> dict[str, float]:
    original_quantity = float(row.get("quantity") or 0)
    factor = float(quantity) / original_quantity if original_quantity > 0 else 1.0
    return {
        field: float(row.get(field) or 0) * factor
        for field in ["calories", "protein", "carbs", "fat", "fiber", "water"]
    }


def render_food_editor(row: pd.Series, patient_id: str) -> None:
    food_id = int(row["id"])
    st.markdown("##### Editar registro")
    mode = st.radio(
        "Tipo de corrección",
        ["Cantidad o tiempo de comida", "Todos los valores manualmente"],
        horizontal=True,
        key=f"edit_mode_{food_id}",
    )
    meal_options = ["Desayuno", "Comida", "Cena", "Snack"]
    current_meal = str(row.get("meal") or "Desayuno")
    meal_index = meal_options.index(current_meal) if current_meal in meal_options else 0

    with st.form(f"edit_food_form_{food_id}"):
        edit_col1, edit_col2 = st.columns(2)
        with edit_col1:
            edited_meal = st.selectbox(
                "Tiempo de comida", meal_options, index=meal_index,
                key=f"edit_meal_{food_id}",
            )
            edited_food = st.text_input(
                "Alimento", value=str(row.get("food") or ""),
                key=f"edit_name_{food_id}",
                disabled=mode != "Todos los valores manualmente",
            )
        with edit_col2:
            edited_quantity = st.number_input(
                "Cantidad", min_value=0.01, value=float(row.get("quantity") or 1),
                step=0.25, key=f"edit_quantity_{food_id}",
            )
            edited_unit = st.text_input(
                "Unidad", value=str(row.get("unit") or "porción"),
                key=f"edit_unit_{food_id}",
            )

        if mode == "Todos los valores manualmente":
            st.caption("Corrige los valores correspondientes a la cantidad total indicada.")
            nutrient_col1, nutrient_col2, nutrient_col3 = st.columns(3)
            with nutrient_col1:
                edited_calories = st.number_input(
                    "Calorías (kcal)", min_value=0.0,
                    value=float(row.get("calories") or 0), step=1.0,
                    key=f"edit_calories_{food_id}",
                )
                edited_protein = st.number_input(
                    "Proteína (g)", min_value=0.0,
                    value=float(row.get("protein") or 0), step=0.1,
                    key=f"edit_protein_{food_id}",
                )
            with nutrient_col2:
                edited_carbs = st.number_input(
                    "Carbohidratos (g)", min_value=0.0,
                    value=float(row.get("carbs") or 0), step=0.1,
                    key=f"edit_carbs_{food_id}",
                )
                edited_fat = st.number_input(
                    "Grasas (g)", min_value=0.0,
                    value=float(row.get("fat") or 0), step=0.1,
                    key=f"edit_fat_{food_id}",
                )
            with nutrient_col3:
                edited_fiber = st.number_input(
                    "Fibra (g)", min_value=0.0,
                    value=float(row.get("fiber") or 0), step=0.1,
                    key=f"edit_fiber_{food_id}",
                )
                edited_water = st.number_input(
                    "Agua (ml)", min_value=0.0,
                    value=float(row.get("water") or 0), step=1.0,
                    key=f"edit_water_{food_id}",
                )
            nutrient_values = {
                "calories": edited_calories,
                "protein": edited_protein,
                "carbs": edited_carbs,
                "fat": edited_fat,
                "fiber": edited_fiber,
                "water": edited_water,
            }
        else:
            nutrient_values = _scaled_food_values(row, edited_quantity)
            st.caption(
                "Al guardar, calorías y macros se ajustarán proporcionalmente "
                "a la nueva cantidad."
            )

        save_edit = st.form_submit_button(
            "Guardar cambios", width="stretch"
        )

    if save_edit:
        try:
            update_food(
                food_id,
                patient_id,
                edited_meal,
                edited_food,
                edited_quantity,
                edited_unit,
                nutrient_values["calories"],
                nutrient_values["protein"],
                nutrient_values["carbs"],
                nutrient_values["fat"],
                nutrient_values["fiber"],
                nutrient_values["water"],
                manual_override=mode == "Todos los valores manualmente",
            )
            st.session_state.pop("editing_food_id", None)
            st.session_state["food_update_notice"] = "Registro actualizado correctamente."
            st.rerun()
        except Exception as exc:
            st.error("No se pudo actualizar el registro.")
            st.code(str(exc))

    if st.button("Cancelar edición", key=f"cancel_edit_{food_id}"):
        st.session_state.pop("editing_food_id", None)
        st.rerun()


def render_day(
    patient_id: str,
    goals: dict,
    selected_date: date,
    can_edit: bool,
    can_delete: bool,
    account_today: date | None = None,
) -> None:
    st.title("🥗 Mi día" if can_delete else "🥗 Resumen del paciente")
    if account_today is not None:
        selected_date = render_log_date_controls(account_today)
    else:
        st.caption(selected_date.strftime("%d/%m/%Y"))
    if notice := st.session_state.pop("food_update_notice", None):
        st.success(str(notice))
    try:
        df = get_day_log(selected_date, patient_id)
    except Exception as exc:
        st.error("No se pudo cargar el registro del día.")
        st.code(str(exc))
        return

    totals = totals_for_day(df)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "🔥 Energía",
        f"{totals['calories']:.0f} kcal",
        f"{float(goals['calories']) - totals['calories']:.0f} restantes",
    )
    col2.metric(
        "🥩 Proteína",
        f"{totals['protein']:.1f} g",
        f"Meta {float(goals['protein']):.0f} g",
    )
    col3.metric(
        "🍚 Carbohidratos",
        f"{totals['carbs']:.1f} g",
        f"Meta {float(goals['carbs']):.0f} g",
    )
    col4.metric(
        "🥑 Grasas",
        f"{totals['fat']:.1f} g",
        f"Meta {float(goals['fat']):.0f} g",
    )

    st.divider()
    left, right = st.columns(2)
    with left:
        nutrient_progress("🔥 Energía", totals["calories"], float(goals["calories"]), "kcal")
        nutrient_progress("🥩 Proteína", totals["protein"], float(goals["protein"]), "g")
        nutrient_progress("🍚 Carbohidratos", totals["carbs"], float(goals["carbs"]), "g")
    with right:
        nutrient_progress("🥑 Grasas", totals["fat"], float(goals["fat"]), "g")
        nutrient_progress("🌾 Fibra", totals["fiber"], float(goals["fiber"]), "g")
        nutrient_progress("💧 Agua", totals["water"], float(goals["water"]), "ml")

    st.divider()
    st.subheader("🍽️ Registro del día")
    if df.empty:
        st.info("Todavía no hay alimentos registrados.")
        return

    for meal in ["Desayuno", "Comida", "Cena", "Snack"]:
        meal_df = df[df["meal"] == meal]
        if meal_df.empty:
            continue
        meal_calories = meal_df["calories"].fillna(0).sum()
        with st.expander(f"{meal} · {meal_calories:.0f} kcal", expanded=True):
            for _, row in meal_df.iterrows():
                action_count = int(can_edit) + int(can_delete)
                widths = [5, 2] + ([1] * action_count)
                columns = st.columns(widths)
                with columns[0]:
                    st.write(f"**{row['food']}**")
                    row_water = effective_water_ml(
                        row.get("food"), row.get("quantity", 0),
                        row.get("unit"), row.get("water", 0),
                    )
                    water_detail = (
                        f" · Agua {row_water:.0f} ml"
                        if row_water > 0 and (
                            is_plain_water_name(row.get("food"))
                            or str(row.get("unit") or "").lower() == "ml"
                        )
                        else ""
                    )
                    st.caption(
                        f"{row['quantity']} {row['unit']} · "
                        f"P {float(row['protein']):.1f} g · "
                        f"CHO {float(row['carbs']):.1f} g · "
                        f"G {float(row['fat']):.1f} g · "
                        f"Fibra {float(row['fiber']):.1f} g"
                        f"{water_detail}"
                    )
                    if pd.notna(row.get("source_name")) and row.get("source_name"):
                        st.caption(f"Fuente: {row['source_name']}")
                with columns[1]:
                    st.write(f"**{float(row['calories']):.0f} kcal**")
                action_index = 2
                if can_edit:
                    with columns[action_index]:
                        if st.button(
                            "✏️", key=f"edit_{row['id']}", help="Editar registro"
                        ):
                            st.session_state["editing_food_id"] = int(row["id"])
                            st.rerun()
                    action_index += 1
                if can_delete:
                    with columns[action_index]:
                        if st.button("🗑️", key=f"delete_{row['id']}", help="Eliminar registro"):
                            try:
                                delete_food(int(row["id"]), patient_id)
                                st.rerun()
                            except Exception as exc:
                                st.error("No se pudo eliminar el alimento.")
                                st.code(str(exc))
                if st.session_state.get("editing_food_id") == int(row["id"]):
                    render_food_editor(row, patient_id)


def _catalog_label(food: dict) -> str:
    brand = f" · {food['brand']}" if food.get("brand") else ""
    source = str(food.get("source") or "Catálogo")
    return f"{food['name']}{brand} — {source}"


def render_catalog_register(patient_id: str, selected_date: date) -> None:
    st.write("Busca un alimento y la app calculará los macros según la cantidad consumida.")
    with st.form("catalog_search_form"):
        query = st.text_input(
            "Buscar alimento",
            placeholder="Ej. huevo, arroz, tortilla o aguacate",
        )
        search_submitted = st.form_submit_button(
            "🔎 Buscar", width="stretch"
        )

    if search_submitted:
        if len(query.strip()) < 2:
            st.warning("Escribe al menos dos caracteres.")
        else:
            results: list[dict] = []
            notices: list[str] = []
            try:
                results.extend(search_catalog(query))
            except Exception as exc:
                notices.append(f"No se pudo consultar el catálogo local: {exc}")

            if food_data_central_configured():
                try:
                    results.extend(search_food_data_central(query))
                except FoodSourceError as exc:
                    notices.append(str(exc))
            else:
                notices.append(
                    "FoodData Central aún no está configurado; se muestran sólo alimentos del catálogo del nutriólogo."
                )

            unique_results: dict[str, dict] = {}
            for result in results:
                unique_results[str(result["result_key"])] = result
            st.session_state["food_search_results"] = list(unique_results.values())
            st.session_state["food_search_notices"] = notices

    for notice in st.session_state.get("food_search_notices", []):
        st.caption(notice)

    results = st.session_state.get("food_search_results", [])
    if not results:
        st.info("Busca un alimento para comenzar.")
        return

    selected_food = st.selectbox(
        "Selecciona el alimento",
        results,
        format_func=_catalog_label,
    )
    st.caption(
        "Valores de referencia por 100 g · "
        f"{float(selected_food['calories_per_100g']):.0f} kcal · "
        f"P {float(selected_food['protein_per_100g']):.1f} g · "
        f"CHO {float(selected_food['carbs_per_100g']):.1f} g · "
        f"G {float(selected_food['fat_per_100g']):.1f} g"
    )

    unit_options = measurement_options(selected_food)
    available_portions = food_portions(selected_food)
    if available_portions:
        st.caption(
            "Medidas caseras disponibles: "
            + " · ".join(
                f"1 {portion['name']} = {portion['grams']:.1f} g"
                for portion in available_portions
            )
        )
    if MILLILITERS in unit_options:
        st.caption("Para líquidos, la conversión nutrimental aproxima 1 ml = 1 g.")

    selection_key = str(selected_food["result_key"]).replace(":", "_")
    unit_choice = st.selectbox(
        "Unidad",
        unit_options,
        key=f"catalog_unit_{selection_key}",
    )
    default_quantity = 250.0 if unit_choice == MILLILITERS else (
        100.0 if unit_choice == GRAMS else 1.0
    )
    amount = st.number_input(
        f"Cantidad consumida ({unit_choice})",
        min_value=0.01,
        value=default_quantity,
        step=1.0 if unit_choice in {GRAMS, MILLILITERS} else 0.25,
        key=f"catalog_amount_{selection_key}_{unit_choice}",
    )
    calculated = calculate_food_serving(selected_food, amount, unit_choice)
    grams = float(calculated["grams"])

    st.write(f"**Cálculo para {grams:.1f} g**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Energía", f"{calculated['calories']:.0f} kcal")
    c2.metric("Proteína", f"{calculated['protein']:.1f} g")
    c3.metric("Carbohidratos", f"{calculated['carbs']:.1f} g")
    c4.metric("Grasas", f"{calculated['fat']:.1f} g")

    meal = st.selectbox(
        "Tiempo de comida",
        ["Desayuno", "Comida", "Cena", "Snack"],
        key="catalog_meal",
    )
    if st.button("✅ Confirmar y registrar", width="stretch"):
        try:
            save_food(
                patient_id,
                selected_date,
                meal,
                str(selected_food["name"]),
                float(amount),
                calculated["unit"],
                calculated["calories"],
                calculated["protein"],
                calculated["carbs"],
                calculated["fat"],
                calculated["fiber"],
                calculated["water"],
                catalog_food_id=selected_food.get("catalog_food_id"),
                source_name=str(selected_food.get("source") or "Catálogo"),
                source_id=str(selected_food.get("source_id") or "") or None,
            )
            st.success(f"{selected_food['name']} registrado correctamente.")
        except Exception as exc:
            st.error("No se pudo registrar el alimento calculado.")
            with st.expander("Detalle técnico"):
                st.code(str(exc))


def render_manual_register(patient_id: str, selected_date: date) -> None:
    st.caption("Usa esta opción cuando el alimento todavía no exista en el catálogo.")
    with st.form("manual_food_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            meal = st.selectbox("Tiempo de comida", ["Desayuno", "Comida", "Cena", "Snack"], key="manual_meal")
            food = st.text_input("Alimento", placeholder="Ej. Huevo", key="manual_food")
            quantity = st.number_input("Cantidad", min_value=0.0, value=1.0, step=0.5, key="manual_quantity")
            unit = st.selectbox(
                "Unidad",
                ["pieza", "g", "ml", "litro", "taza", "vaso", "cucharada", "porción"],
                key="manual_unit",
            )
        with col2:
            calories = st.number_input("Calorías (kcal)", min_value=0.0, step=10.0, key="manual_calories")
            protein = st.number_input("Proteína (g)", min_value=0.0, step=1.0, key="manual_protein")
            carbs = st.number_input("Carbohidratos (g)", min_value=0.0, step=1.0, key="manual_carbs")
            fat = st.number_input("Grasas (g)", min_value=0.0, step=1.0, key="manual_fat")
            fiber = st.number_input("Fibra (g)", min_value=0.0, step=1.0, key="manual_fiber")
            water = st.number_input("Agua (ml)", min_value=0.0, step=50.0, key="manual_water")
        submitted = st.form_submit_button("✅ Registrar manualmente", width="stretch")

    if submitted:
        if not food.strip():
            st.error("Escribe el nombre del alimento.")
        else:
            try:
                effective_water = float(water)
                if effective_water == 0 and is_plain_water_name(food):
                    inferred_water = volume_ml_from_quantity(quantity, unit)
                    if inferred_water is not None:
                        effective_water = inferred_water
                    elif unit == "g":
                        effective_water = float(quantity)
                save_food(
                    patient_id,
                    selected_date,
                    meal,
                    food,
                    quantity,
                    unit,
                    calories,
                    protein,
                    carbs,
                    fat,
                    fiber,
                    effective_water,
                    source_name="Registro manual",
                )
                st.success(f"{food.strip()} registrado correctamente.")
            except Exception as exc:
                st.error("No se pudo registrar el alimento.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))


def render_log_date_controls(account_today: date) -> date:
    """Selector de fecha visible dentro de la página.

    Antes vivía sólo en la barra lateral, que Streamlit colapsa en el teléfono.
    Como ahí es donde el paciente registra, la opción de corregir un día
    olvidado quedaba fuera de la vista.
    """
    stored = st.session_state.get("selected_log_date")
    if not isinstance(stored, date):
        st.session_state["selected_log_date"] = account_today

    col_today, col_yesterday, col_picker = st.columns([1, 1, 2])
    if col_today.button("Hoy", width="stretch"):
        st.session_state["selected_log_date"] = account_today
        st.rerun()
    if col_yesterday.button("Ayer", width="stretch"):
        st.session_state["selected_log_date"] = account_today - timedelta(days=1)
        st.rerun()
    with col_picker:
        chosen = st.date_input(
            "Fecha",
            key="selected_log_date",
            max_value=account_today,
            format="DD/MM/YYYY",
        )

    if chosen != account_today:
        st.info(
            f"Estás trabajando en el {chosen.strftime('%d/%m/%Y')}, "
            "no en el día de hoy."
        )
    return chosen


def render_register(patient_id: str, selected_date: date, account_today: date) -> date:
    st.title("➕ Registrar")
    selected_date = render_log_date_controls(account_today)
    ai_tab, catalog_tab, saved_tab, manual_tab, activity_tab = st.tabs(
        [
            "✨ Describir comida",
            "🔎 Desde catálogo",
            "⭐ Platillos guardados",
            "✍️ Registro manual",
            "🏃 Actividad",
        ]
    )
    with ai_tab:
        render_ai_register(patient_id, selected_date)
    with catalog_tab:
        render_catalog_register(patient_id, selected_date)
    with saved_tab:
        render_saved_meals(patient_id, selected_date)
    with manual_tab:
        render_manual_register(patient_id, selected_date)
    with activity_tab:
        render_activity_register(patient_id, selected_date)
    return selected_date


def render_history(patient_id: str, current_date: date) -> None:
    st.title("📊 Historial")
    nutrition_tab, activity_tab, body_tab = st.tabs(
        ["🍽️ Alimentación", "🏃 Actividad", "⚖️ Evolución corporal"]
    )
    # El balance contra la actividad necesita el consumo diario, que se calcula
    # en la pestaña de alimentación.
    energy_by_day = pd.DataFrame()

    with nutrition_tab:
        try:
            raw_history = get_history(patient_id)
        except Exception as exc:
            st.error("No se pudo cargar el historial de alimentación.")
            st.code(str(exc))
            raw_history = pd.DataFrame()

        if raw_history.empty:
            st.info("Todavía no hay alimentos registrados.")
        else:
            raw_history["log_date"] = pd.to_datetime(raw_history["log_date"])
            numeric_cols = ["calories", "protein", "carbs", "fat", "fiber", "water"]
            for col in numeric_cols:
                raw_history[col] = pd.to_numeric(
                    raw_history[col], errors="coerce"
                ).fillna(0)
            raw_history["water"] = raw_history.apply(
                lambda row: effective_water_ml(
                    row.get("food"), row.get("quantity", 0), row.get("unit"), row["water"]
                ),
                axis=1,
            )
            df_history = (
                raw_history.groupby("log_date", as_index=False)[numeric_cols]
                .sum()
                .sort_values("log_date")
            )
            energy_by_day = df_history[["log_date", "calories"]].copy()
            start_date = pd.Timestamp(current_date - timedelta(days=6))
            week_df = df_history[df_history["log_date"] >= start_date]

            st.subheader("Últimos 7 días")
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Promedio energético",
                f"{week_df['calories'].mean():.0f} kcal/día"
                if not week_df.empty else "0 kcal/día",
            )
            c2.metric(
                "Proteína promedio",
                f"{week_df['protein'].mean():.1f} g/día"
                if not week_df.empty else "0 g/día",
            )
            c3.metric("Días registrados", f"{len(week_df)} / 7")
            st.subheader("🔥 Energía")
            st.altair_chart(
                stable_line_chart(
                    week_df,
                    "log_date",
                    {"calories": "Calorías"},
                    "kcal",
                    zero=True,
                ),
                width="stretch",
                on_select="ignore",
            )
            st.subheader("🥩 Macronutrientes")
            st.altair_chart(
                stable_line_chart(
                    week_df,
                    "log_date",
                    {
                        "protein": "Proteína",
                        "carbs": "Carbohidratos",
                        "fat": "Grasas",
                    },
                    "Gramos",
                    zero=True,
                ),
                width="stretch",
                on_select="ignore",
            )
            st.subheader("Datos")
            display_df = df_history.copy()
            display_df["log_date"] = display_df["log_date"].dt.strftime("%d/%m/%Y")
            display_df = display_df.rename(
                columns={
                    "log_date": "Fecha", "calories": "kcal",
                    "protein": "Proteína (g)", "carbs": "CHO (g)",
                    "fat": "Grasas (g)", "fiber": "Fibra (g)",
                    "water": "Agua (ml)",
                }
            )
            st.dataframe(display_df, width="stretch", hide_index=True)

    with activity_tab:
        render_activity_history(patient_id, energy_by_day)

    with body_tab:
        try:
            measurements = get_body_measurements(patient_id, limit=100)
        except Exception as exc:
            st.error("No se pudo cargar el progreso corporal.")
            st.code(str(exc))
            measurements = pd.DataFrame()

        if measurements.empty:
            st.info(
                "Todavía no hay mediciones. Agrégalas desde "
                "Perfil y metas → Composición corporal."
            )
        else:
            progress_df = measurements.copy()
            progress_df["measured_on"] = pd.to_datetime(progress_df["measured_on"])
            progress_columns = [
                "weight_kg", "bmi", "body_fat_pct", "muscle_pct",
                "visceral_fat", "basal_calories", "metabolic_age",
            ]
            for column in progress_columns:
                if column not in progress_df:
                    progress_df[column] = pd.NA
                progress_df[column] = pd.to_numeric(
                    progress_df[column], errors="coerce"
                )
            progress_df = progress_df.sort_values("measured_on")
            latest = progress_df.iloc[-1]

            metric1, metric2, metric3 = st.columns(3)
            metric1.metric(
                "Peso actual",
                f"{latest['weight_kg']:.1f} kg"
                if pd.notna(latest["weight_kg"]) else "Sin dato",
            )
            metric2.metric(
                "Grasa corporal",
                f"{latest['body_fat_pct']:.1f}%"
                if pd.notna(latest["body_fat_pct"]) else "Sin dato",
            )
            metric3.metric(
                "Músculo",
                f"{latest['muscle_pct']:.1f}%"
                if pd.notna(latest["muscle_pct"]) else "Sin dato",
            )

            weight_chart = progress_df.dropna(subset=["weight_kg"])
            if not weight_chart.empty:
                st.subheader("⚖️ Peso")
                st.altair_chart(
                    stable_line_chart(
                        weight_chart,
                        "measured_on",
                        {"weight_kg": "Peso"},
                        "kg",
                    ),
                    width="stretch",
                    on_select="ignore",
                )

            composition_columns = [
                column for column in ["body_fat_pct", "muscle_pct"]
                if progress_df[column].notna().any()
            ]
            if composition_columns:
                st.subheader("📉 Composición corporal (%)")
                st.altair_chart(
                    stable_line_chart(
                        progress_df,
                        "measured_on",
                        {
                            "body_fat_pct": "Grasa corporal",
                            "muscle_pct": "Músculo",
                        },
                        "Porcentaje",
                    ),
                    width="stretch",
                    on_select="ignore",
                )

            indicators = [
                column for column in ["bmi", "visceral_fat"]
                if progress_df[column].notna().any()
            ]
            if indicators:
                st.subheader("Indicadores")
                st.altair_chart(
                    stable_line_chart(
                        progress_df,
                        "measured_on",
                        {"bmi": "IMC", "visceral_fat": "Grasa visceral"},
                        "Valor",
                    ),
                    width="stretch",
                    on_select="ignore",
                )


def _measurement_number(row: pd.Series, field: str) -> float:
    value = row.get(field)
    return float(value) if pd.notna(value) and value is not None else 0.0


def render_body_measurement_editor(
    row: pd.Series,
    patient_id: str,
    can_update_current_weight: bool,
) -> None:
    measurement_id = int(row["id"])
    measured_date = pd.to_datetime(row.get("measured_on")).date()
    device_options = ["Tanita", "Omron", "Otro", "Sin especificar"]
    current_device = str(row.get("device") or "Sin especificar")
    if current_device not in device_options:
        device_options.insert(0, current_device)

    st.markdown("##### Corregir medición")
    with st.form(f"edit_measurement_form_{measurement_id}"):
        edited_date = st.date_input("Fecha", value=measured_date)
        edited_device = st.selectbox(
            "Equipo", device_options, index=device_options.index(current_device)
        )
        col1, col2 = st.columns(2)
        with col1:
            edited_weight = st.number_input(
                "Peso (kg)", min_value=0.0,
                value=_measurement_number(row, "weight_kg"), step=0.1,
            )
            edited_bmi = st.number_input(
                "IMC", min_value=0.0,
                value=_measurement_number(row, "bmi"), step=0.1,
            )
            edited_fat = st.number_input(
                "Grasa corporal (%)", min_value=0.0, max_value=100.0,
                value=_measurement_number(row, "body_fat_pct"), step=0.1,
            )
            edited_muscle = st.number_input(
                "Músculo (%)", min_value=0.0, max_value=100.0,
                value=_measurement_number(row, "muscle_pct"), step=0.1,
            )
        with col2:
            edited_basal = st.number_input(
                "Calorías basales", min_value=0.0,
                value=_measurement_number(row, "basal_calories"), step=10.0,
            )
            edited_visceral = st.number_input(
                "Grasa visceral", min_value=0.0,
                value=_measurement_number(row, "visceral_fat"), step=0.5,
            )
            edited_metabolic_age = st.number_input(
                "Edad metabólica", min_value=0, max_value=150,
                value=int(_measurement_number(row, "metabolic_age")), step=1,
            )
        edited_notes = st.text_area(
            "Notas", value=str(row.get("notes") or "")
        )
        update_current_weight = st.checkbox(
            "Actualizar también el peso actual del perfil",
            value=False,
            disabled=not can_update_current_weight,
        )
        save_changes = st.form_submit_button(
            "Guardar corrección", width="stretch"
        )
    if save_changes:
        try:
            update_body_measurement(
                measurement_id=measurement_id,
                patient_id=patient_id,
                measured_on=edited_date,
                device=edited_device,
                weight_kg=edited_weight,
                bmi=edited_bmi,
                body_fat_pct=edited_fat,
                muscle_pct=edited_muscle,
                basal_calories=edited_basal,
                visceral_fat=edited_visceral,
                metabolic_age=edited_metabolic_age,
                notes=edited_notes,
            )
            if update_current_weight and edited_weight > 0:
                update_patient_weight(patient_id, edited_weight)
            st.session_state.pop("editing_measurement_id", None)
            st.session_state["measurement_notice"] = "Medición corregida."
            st.rerun()
        except Exception as exc:
            st.error("No se pudo corregir la medición.")
            st.code(str(exc))

    if st.button(
        "Cancelar corrección", key=f"cancel_measurement_edit_{measurement_id}"
    ):
        st.session_state.pop("editing_measurement_id", None)
        st.rerun()


def render_profile_and_goals(
    patient_id: str,
    profile: dict,
    goals: dict,
    can_edit_profile: bool,
    can_edit_goals: bool,
    current_date: date,
) -> None:
    st.title("👤 Perfil y metas")
    try:
        measurements = get_body_measurements(patient_id)
        measurements_error: Exception | None = None
    except Exception as exc:
        measurements = pd.DataFrame()
        measurements_error = exc

    tab1, tab2, tab3 = st.tabs(
        ["Perfil", "Metas nutricionales", "Composición corporal"]
    )
    with tab1:
        st.subheader("Datos del paciente")
        if not can_edit_profile:
            st.json(profile)
        else:
            with st.form("profile_form"):
                name = st.text_input("Nombre", value=str(profile.get("name") or ""))
                age = st.number_input("Edad", min_value=1, max_value=120, value=int(profile.get("age") or 18))
                sex_options = ["Femenino", "Masculino", "Otro / no especificado"]
                current_sex = str(profile.get("sex") or "Otro / no especificado")
                sex_index = sex_options.index(current_sex) if current_sex in sex_options else 2
                sex = st.selectbox("Sexo", sex_options, index=sex_index)
                weight = st.number_input("Peso (kg)", min_value=1.0, value=float(profile.get("weight") or 70), step=0.1)
                height = st.number_input("Estatura (cm)", min_value=50.0, value=float(profile.get("height") or 165), step=0.5)
                activity_options = list(ACTIVITY_FACTORS)
                current_activity = str(profile.get("activity_level") or "Sedentaria")
                activity_index = activity_options.index(current_activity) if current_activity in activity_options else 0
                activity_level = st.selectbox(
                    "Nivel de actividad habitual", activity_options, index=activity_index
                )
                save_profile = st.form_submit_button("Guardar perfil", width="stretch")
            if save_profile:
                try:
                    update_profile(
                        patient_id, name, age, sex, weight, height, activity_level
                    )
                    st.success("Perfil actualizado.")
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo actualizar el perfil.")
                    st.code(str(exc))

    with tab2:
        st.subheader("Metas nutricionales")
        if not can_edit_goals:
            st.info("Estas metas fueron establecidas por tu nutriólogo.")

        def saved_number(field: str, default: float) -> float:
            value = goals.get(field)
            return float(default) if value is None else float(value)

        latest_basal = None
        if not measurements.empty and "basal_calories" in measurements:
            basal_values = pd.to_numeric(
                measurements["basal_calories"], errors="coerce"
            ).dropna()
            if not basal_values.empty:
                latest_basal = float(basal_values.iloc[0])

        with st.expander("🧮 Calculadora automática", expanded=True):
            st.caption(
                "Estimación inicial para adultos. El resultado siempre queda editable "
                "y debe ser validado por el profesional de nutrición."
            )
            method_options = ["Mifflin-St Jeor"]
            if latest_basal and latest_basal > 0:
                method_options.append("Calorías basales del equipo")
            saved_method = str(goals.get("calculation_method") or method_options[0])
            method_index = method_options.index(saved_method) if saved_method in method_options else 0
            calculation_method = st.selectbox(
                "Método para gasto en reposo", method_options, index=method_index,
                disabled=not can_edit_goals,
            )

            calc_col1, calc_col2, calc_col3 = st.columns(3)
            default_activity = saved_number(
                "activity_factor",
                ACTIVITY_FACTORS.get(
                    str(profile.get("activity_level") or "Sedentaria"), 1.2
                ),
            )
            with calc_col1:
                activity_factor = st.number_input(
                    "Factor de actividad", min_value=1.0, max_value=2.5,
                    value=default_activity, step=0.025, disabled=not can_edit_goals,
                )
            with calc_col2:
                calorie_adjustment = st.number_input(
                    "Ajuste sobre mantenimiento (%)", min_value=-50.0, max_value=50.0,
                    value=saved_number("calorie_adjustment_pct", 0), step=5.0,
                    disabled=not can_edit_goals,
                )
            with calc_col3:
                water_ml_per_kg = st.number_input(
                    "Agua orientativa (ml/kg)", min_value=0.0, max_value=100.0,
                    value=saved_number("water_ml_per_kg", 35), step=1.0,
                    disabled=not can_edit_goals,
                )

            macro_col1, macro_col2, macro_col3 = st.columns(3)
            with macro_col1:
                protein_pct = st.number_input(
                    "Proteína (%)", min_value=0.0, max_value=100.0,
                    value=saved_number("protein_pct", 25), step=1.0,
                    disabled=not can_edit_goals,
                )
            with macro_col2:
                carbs_pct = st.number_input(
                    "Carbohidratos (%)", min_value=0.0, max_value=100.0,
                    value=saved_number("carbs_pct", 45), step=1.0,
                    disabled=not can_edit_goals,
                )
            with macro_col3:
                fat_pct = st.number_input(
                    "Grasas (%)", min_value=0.0, max_value=100.0,
                    value=saved_number("fat_pct", 30), step=1.0,
                    disabled=not can_edit_goals,
                )

            calculation_error = None
            calculated_targets = None
            try:
                if calculation_method == "Calorías basales del equipo":
                    resting_calories = float(latest_basal or 0)
                else:
                    resting_calories = mifflin_st_jeor(
                        float(profile.get("weight") or 0),
                        float(profile.get("height") or 0),
                        int(profile.get("age") or 0),
                        str(profile.get("sex") or ""),
                    )
                calculated_targets = calculate_nutrition_targets(
                    resting_calories=resting_calories,
                    weight_kg=float(profile.get("weight") or 0),
                    activity_factor=activity_factor,
                    calorie_adjustment_pct=calorie_adjustment,
                    protein_pct=protein_pct,
                    carbs_pct=carbs_pct,
                    fat_pct=fat_pct,
                    water_ml_per_kg=water_ml_per_kg,
                )
            except ValueError as exc:
                calculation_error = str(exc)

            if calculation_error:
                st.warning(calculation_error)
            elif calculated_targets:
                metric1, metric2, metric3 = st.columns(3)
                metric1.metric("Gasto en reposo", f"{calculated_targets['resting_calories']:.0f} kcal")
                metric2.metric("Mantenimiento estimado", f"{calculated_targets['maintenance_calories']:.0f} kcal")
                metric3.metric("Meta calculada", f"{calculated_targets['calories']:.0f} kcal")

            apply_calculation = st.button(
                "Aplicar cálculo a las metas",
                width="stretch",
                disabled=not can_edit_goals or calculated_targets is None,
            )
            if apply_calculation and calculated_targets:
                goal_prefix = f"goal_{patient_id}"
                for field in ["calories", "protein", "carbs", "fat", "fiber", "water"]:
                    st.session_state[f"{goal_prefix}_{field}"] = float(calculated_targets[field])
                st.session_state[f"{goal_prefix}_calculation"] = {
                    "calculation_method": calculation_method,
                    "resting_calories": resting_calories,
                    "activity_factor": activity_factor,
                    "calorie_adjustment_pct": calorie_adjustment,
                    "protein_pct": protein_pct,
                    "carbs_pct": carbs_pct,
                    "fat_pct": fat_pct,
                    "water_ml_per_kg": water_ml_per_kg,
                }
                st.rerun()

        goal_prefix = f"goal_{patient_id}"
        for field in ["calories", "protein", "carbs", "fat", "fiber", "water"]:
            st.session_state.setdefault(f"{goal_prefix}_{field}", float(goals[field]))
        with st.form("goals_form"):
            goal_calories = st.number_input("Energía (kcal/día)", min_value=0.0, step=50.0, disabled=not can_edit_goals, key=f"{goal_prefix}_calories")
            goal_protein = st.number_input("Proteína (g/día)", min_value=0.0, step=5.0, disabled=not can_edit_goals, key=f"{goal_prefix}_protein")
            goal_carbs = st.number_input("Carbohidratos (g/día)", min_value=0.0, step=5.0, disabled=not can_edit_goals, key=f"{goal_prefix}_carbs")
            goal_fat = st.number_input("Grasas (g/día)", min_value=0.0, step=5.0, disabled=not can_edit_goals, key=f"{goal_prefix}_fat")
            goal_fiber = st.number_input("Fibra (g/día)", min_value=0.0, step=1.0, disabled=not can_edit_goals, key=f"{goal_prefix}_fiber")
            goal_water = st.number_input("Agua (ml/día)", min_value=0.0, step=100.0, disabled=not can_edit_goals, key=f"{goal_prefix}_water")
            save_goals = st.form_submit_button("Guardar metas", width="stretch", disabled=not can_edit_goals)
        if save_goals:
            try:
                calculation_metadata = st.session_state.get(
                    f"{goal_prefix}_calculation",
                    {
                        "calculation_method": goals.get("calculation_method"),
                        "resting_calories": goals.get("resting_calories"),
                        "activity_factor": goals.get("activity_factor"),
                        "calorie_adjustment_pct": goals.get("calorie_adjustment_pct"),
                        "protein_pct": goals.get("protein_pct"),
                        "carbs_pct": goals.get("carbs_pct"),
                        "fat_pct": goals.get("fat_pct"),
                        "water_ml_per_kg": goals.get("water_ml_per_kg"),
                    },
                )
                update_goals(
                    patient_id, goal_calories, goal_protein, goal_carbs,
                    goal_fat, goal_fiber, goal_water, **calculation_metadata,
                )
                st.success("Metas actualizadas.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudieron actualizar las metas.")
                st.code(str(exc))

    with tab3:
        st.subheader("Mediciones de composición corporal")
        if notice := st.session_state.pop("measurement_notice", None):
            st.success(str(notice))
        try:
            calculated_bmi = calculate_bmi(
                float(profile.get("weight") or 0),
                float(profile.get("height") or 0),
            )
            st.metric("IMC calculado con peso y estatura", f"{calculated_bmi:.2f} kg/m²")
        except ValueError:
            calculated_bmi = 0.0

        st.caption(
            "Los valores de Tanita, Omron u otro equipo son opcionales y dependen "
            "del dispositivo y sus condiciones de medición."
        )
        if measurements_error:
            st.warning(
                "La tabla de composición corporal aún no está disponible. "
                "Ejecuta las migraciones V0.5 y V0.6 en Supabase."
            )
            with st.expander("Detalle técnico"):
                st.code(str(measurements_error))
        else:
            with st.form("body_measurement_form", clear_on_submit=True):
                measured_on = st.date_input("Fecha de medición", value=current_date)
                device = st.selectbox("Equipo", ["Tanita", "Omron", "Otro", "Sin especificar"])
                measure_col1, measure_col2 = st.columns(2)
                with measure_col1:
                    measured_weight = st.number_input(
                        "Peso (kg)", min_value=0.0,
                        value=float(profile.get("weight") or 0), step=0.1,
                    )
                    measured_bmi = st.number_input("IMC del equipo (opcional)", min_value=0.0, value=float(calculated_bmi), step=0.1)
                    body_fat_pct = st.number_input("Grasa corporal (%)", min_value=0.0, max_value=100.0, step=0.1)
                    muscle_pct = st.number_input("Músculo (%)", min_value=0.0, max_value=100.0, step=0.1)
                with measure_col2:
                    basal_calories = st.number_input("Calorías basales del equipo", min_value=0.0, step=10.0)
                    visceral_fat = st.number_input("Grasa visceral (nivel)", min_value=0.0, step=0.5)
                    metabolic_age = st.number_input("Edad metabólica", min_value=0, max_value=150, step=1)
                update_current_weight = st.checkbox(
                    "Actualizar también el peso actual del perfil",
                    value=True,
                    disabled=not can_edit_profile,
                )
                measurement_notes = st.text_area("Notas (opcional)")
                save_measurement = st.form_submit_button("Guardar medición", width="stretch")
            if save_measurement:
                try:
                    save_body_measurement(
                        patient_id=patient_id,
                        measured_on=measured_on,
                        device=device,
                        weight_kg=measured_weight,
                        bmi=measured_bmi,
                        body_fat_pct=body_fat_pct,
                        muscle_pct=muscle_pct,
                        basal_calories=basal_calories,
                        visceral_fat=visceral_fat,
                        metabolic_age=metabolic_age,
                        notes=measurement_notes,
                    )
                    if update_current_weight and measured_weight > 0:
                        update_patient_weight(patient_id, measured_weight)
                    st.success("Medición guardada.")
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo guardar la medición.")
                    st.code(str(exc))

            if measurements.empty:
                st.info("Todavía no hay mediciones registradas.")
            else:
                display_measurements = measurements.copy()
                display_measurements = display_measurements.rename(
                    columns={
                        "measured_on": "Fecha", "device": "Equipo",
                        "weight_kg": "Peso (kg)", "bmi": "IMC",
                        "body_fat_pct": "Grasa (%)", "muscle_pct": "Músculo (%)",
                        "basal_calories": "Calorías basales", "visceral_fat": "Grasa visceral",
                        "metabolic_age": "Edad metabólica", "notes": "Notas",
                    }
                )
                visible_columns = [
                    "Fecha", "Equipo", "Peso (kg)", "IMC", "Grasa (%)", "Músculo (%)",
                    "Calorías basales", "Grasa visceral", "Edad metabólica", "Notas",
                ]
                st.dataframe(
                    display_measurements[visible_columns],
                    width="stretch",
                    hide_index=True,
                )
                st.markdown("#### Corregir o eliminar mediciones")
                for _, measurement in measurements.iterrows():
                    measurement_id = int(measurement["id"])
                    summary_date = pd.to_datetime(
                        measurement.get("measured_on")
                    ).strftime("%d/%m/%Y")
                    weight_text = (
                        f" · {_measurement_number(measurement, 'weight_kg'):.1f} kg"
                        if _measurement_number(measurement, "weight_kg") > 0 else ""
                    )
                    with st.expander(
                        f"{summary_date}{weight_text} · "
                        f"{measurement.get('device') or 'Sin equipo'}"
                    ):
                        action1, action2 = st.columns(2)
                        if action1.button(
                            "✏️ Corregir",
                            key=f"edit_measurement_{measurement_id}",
                            width="stretch",
                        ):
                            st.session_state["editing_measurement_id"] = measurement_id
                            st.session_state.pop("deleting_measurement_id", None)
                            st.rerun()
                        if action2.button(
                            "🗑️ Eliminar",
                            key=f"delete_measurement_{measurement_id}",
                            width="stretch",
                        ):
                            st.session_state["deleting_measurement_id"] = measurement_id
                            st.session_state.pop("editing_measurement_id", None)
                            st.rerun()

                        if st.session_state.get("editing_measurement_id") == measurement_id:
                            render_body_measurement_editor(
                                measurement,
                                patient_id,
                                can_update_current_weight=can_edit_profile,
                            )

                        if st.session_state.get("deleting_measurement_id") == measurement_id:
                            st.warning(
                                "Esta medición se eliminará definitivamente. "
                                "El peso actual del perfil no cambiará."
                            )
                            confirm_col, cancel_col = st.columns(2)
                            if confirm_col.button(
                                "Confirmar eliminación",
                                key=f"confirm_delete_measurement_{measurement_id}",
                                width="stretch",
                            ):
                                try:
                                    delete_body_measurement(measurement_id, patient_id)
                                    st.session_state.pop(
                                        "deleting_measurement_id", None
                                    )
                                    st.session_state["measurement_notice"] = (
                                        "Medición eliminada."
                                    )
                                    st.rerun()
                                except Exception as exc:
                                    st.error("No se pudo eliminar la medición.")
                                    st.code(str(exc))
                            if cancel_col.button(
                                "Cancelar",
                                key=f"cancel_delete_measurement_{measurement_id}",
                                width="stretch",
                            ):
                                st.session_state.pop("deleting_measurement_id", None)
                                st.rerun()


CATALOG_IMPORT_COLUMNS = [
    "name",
    "brand",
    "calories_per_100g",
    "protein_per_100g",
    "carbs_per_100g",
    "fat_per_100g",
    "fiber_per_100g",
    "water_per_100g",
    "portion_name",
    "portion_grams",
    "source",
    "external_id",
]

CATALOG_CSV_TEMPLATE = ",".join(CATALOG_IMPORT_COLUMNS) + "\n"


def render_catalog_admin() -> None:
    st.title("🍎 Catálogo de alimentos")
    st.write(
        "Los alimentos creados aquí estarán disponibles para tus pacientes vinculados. "
        "Los valores nutrimentales deben capturarse por cada 100 g."
    )
    create_tab, import_tab, list_tab = st.tabs(
        ["Crear alimento", "Importar CSV", "Mis alimentos"]
    )

    with create_tab:
        with st.form("create_catalog_food_form", clear_on_submit=True):
            name = st.text_input("Nombre del alimento")
            brand = st.text_input("Marca (opcional)")
            col1, col2 = st.columns(2)
            with col1:
                calories = st.number_input("Calorías por 100 g", min_value=0.0, step=10.0)
                protein = st.number_input("Proteína por 100 g", min_value=0.0, step=1.0)
                carbs = st.number_input("Carbohidratos por 100 g", min_value=0.0, step=1.0)
            with col2:
                fat = st.number_input("Grasas por 100 g", min_value=0.0, step=1.0)
                fiber = st.number_input("Fibra por 100 g", min_value=0.0, step=1.0)
                water = st.number_input("Agua por 100 g", min_value=0.0, step=1.0)
            is_liquid = st.checkbox(
                "Es un líquido (habilita mililitros)",
                help=(
                    "Marca esta casilla para que el alimento pueda registrarse en "
                    "mililitros además de gramos."
                ),
            )
            st.caption(
                "Porción casera opcional. Después podrás agregar todas las que "
                "necesites desde Mis alimentos."
            )
            portion_col1, portion_col2 = st.columns(2)
            with portion_col1:
                portion_name = st.text_input("Nombre de la porción", placeholder="Ej. pieza mediana")
            with portion_col2:
                portion_grams = st.number_input("Gramos por porción", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Guardar en catálogo", width="stretch")

        if submitted:
            if not name.strip():
                st.error("Escribe el nombre del alimento.")
            elif bool(portion_name.strip()) != bool(portion_grams > 0):
                st.error("Completa tanto el nombre como los gramos de la porción.")
            else:
                try:
                    new_food_id = create_catalog_food(
                        name,
                        brand,
                        calories,
                        protein,
                        carbs,
                        fat,
                        fiber,
                        water,
                        portion_name,
                        portion_grams if portion_grams > 0 else None,
                    )
                    if portion_name.strip() and portion_grams > 0:
                        add_catalog_portion(new_food_id, portion_name, portion_grams)
                    if is_liquid:
                        set_catalog_food_liquid(new_food_id, True)
                    st.success("Alimento agregado al catálogo.")
                except Exception as exc:
                    st.error("No se pudo crear el alimento.")
                    with st.expander("Detalle técnico"):
                        st.code(str(exc))

    with import_tab:
        st.write(
            "Puedes importar una tabla autorizada o datos propios. Conserva el nombre "
            "de la fuente y su identificador para mantener trazabilidad."
        )
        st.download_button(
            "Descargar plantilla CSV",
            data=CATALOG_CSV_TEMPLATE,
            file_name="plantilla_catalogo_alimentos.csv",
            mime="text/csv",
        )
        uploaded_file = st.file_uploader("Selecciona el CSV", type=["csv"])
        if uploaded_file is not None:
            try:
                import_df = pd.read_csv(uploaded_file)
                if "name" not in import_df.columns:
                    st.error("El archivo debe contener la columna name.")
                elif len(import_df) > 2000:
                    st.error("Importa un máximo de 2000 alimentos por archivo.")
                else:
                    for column in CATALOG_IMPORT_COLUMNS:
                        if column not in import_df.columns:
                            import_df[column] = ""
                    numeric_columns = [
                        "calories_per_100g",
                        "protein_per_100g",
                        "carbs_per_100g",
                        "fat_per_100g",
                        "fiber_per_100g",
                        "water_per_100g",
                        "portion_grams",
                    ]
                    for column in numeric_columns:
                        import_df[column] = pd.to_numeric(
                            import_df[column], errors="coerce"
                        ).fillna(0)
                    import_df = import_df[CATALOG_IMPORT_COLUMNS].fillna("")
                    st.dataframe(import_df.head(25), width="stretch", hide_index=True)
                    if st.button("Importar alimentos", width="stretch"):
                        imported = import_catalog_foods(import_df.to_dict(orient="records"))
                        st.success(f"Se importaron {imported} alimentos.")
            except Exception as exc:
                st.error("No se pudo procesar o importar el archivo.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))

        st.warning(
            "No importes el SMAE u otra base comercial sin contar con autorización de reutilización."
        )

    with list_tab:
        render_owned_catalog_list()


CATALOG_PAGE_SIZE = 50


def render_owned_catalog_list() -> None:
    """Catálogo propio con búsqueda y páginas.

    Antes se pedía la tabla completa sin paginar y se recortaba a 200 renglones.
    Con un catálogo importado de casi 1900 alimentos, sólo se alcanzaban a ver
    los que empiezan con A.
    """
    if notice := st.session_state.pop("catalog_notice", None):
        st.success(str(notice))

    search = st.text_input(
        "Buscar en mi catálogo",
        key="catalog_admin_search",
        placeholder="Ej. tortilla, res, leche",
    )

    try:
        total = count_owned_catalog(search)
    except Exception as exc:
        st.error("No se pudo cargar el catálogo.")
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        return

    if not total:
        if search.strip():
            st.info("Ningún alimento de tu catálogo coincide con esa búsqueda.")
        else:
            st.info("Todavía no has creado alimentos.")
        return

    page_count = max((total + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE, 1)
    page = 1
    if page_count > 1:
        page = st.number_input(
            f"Página (de {page_count})",
            min_value=1,
            max_value=page_count,
            step=1,
            value=1,
            key="catalog_admin_page",
        )
    start = (int(page) - 1) * CATALOG_PAGE_SIZE

    # Se pide sólo la página visible: traer los casi 1900 alimentos y sus
    # medidas en cada recarga haría lenta la pantalla.
    try:
        visible = list_owned_catalog(search, limit=CATALOG_PAGE_SIZE, offset=start)
    except Exception as exc:
        st.error("No se pudo cargar el catálogo.")
        with st.expander("Detalle técnico"):
            st.code(str(exc))
        return

    st.caption(
        f"{total} alimentos · mostrando {start + 1}–{start + len(visible)}"
    )

    for food in visible:
        portions = food.get("portions") or []
        measures = ", ".join(
            f"{portion['portion_name']} = {float(portion['grams']):.0f} g"
            for portion in portions
        )
        header = f"{food['name']}"
        if food.get("brand"):
            header += f" · {food['brand']}"
        with st.expander(header):
            st.caption(
                f"100 g: {float(food['calories_per_100g']):.0f} kcal · "
                f"P {float(food['protein_per_100g']):.1f} · "
                f"CHO {float(food['carbs_per_100g']):.1f} · "
                f"G {float(food['fat_per_100g']):.1f} · "
                f"Fuente: {food.get('source') or 'Catálogo'}"
            )
            st.write(f"**Medidas disponibles:** {measures or 'sólo gramos'}")

            liquid = st.checkbox(
                "Es un líquido (habilita mililitros)",
                value=bool(food.get("is_liquid")),
                key=f"catalog_liquid_{food['id']}",
            )
            if liquid != bool(food.get("is_liquid")):
                try:
                    set_catalog_food_liquid(str(food["id"]), liquid)
                    st.session_state["catalog_notice"] = "Se actualizó el tipo de alimento."
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo actualizar el alimento.")
                    st.code(str(exc))

            for portion in portions:
                col_portion, col_remove = st.columns([6, 1])
                with col_portion:
                    st.caption(
                        f"1 {portion['portion_name']} = {float(portion['grams']):.1f} g"
                    )
                with col_remove:
                    if st.button("🗑️", key=f"delete_portion_{portion['id']}"):
                        try:
                            delete_catalog_portion(str(portion["id"]))
                            st.session_state["catalog_notice"] = "Medida eliminada."
                            st.rerun()
                        except Exception as exc:
                            st.error("No se pudo eliminar la medida.")
                            st.code(str(exc))

            with st.form(f"add_portion_{food['id']}", clear_on_submit=True):
                col_name, col_grams = st.columns(2)
                with col_name:
                    new_portion = st.text_input(
                        "Nueva medida", placeholder="Ej. taza, pieza, cucharada"
                    )
                with col_grams:
                    new_grams = st.number_input(
                        "Equivale a (g)", min_value=0.0, step=1.0
                    )
                if st.form_submit_button("Agregar medida", width="stretch"):
                    if not new_portion.strip() or new_grams <= 0:
                        st.error("Escribe el nombre de la medida y sus gramos.")
                    else:
                        try:
                            add_catalog_portion(
                                str(food["id"]), new_portion, new_grams
                            )
                            st.session_state["catalog_notice"] = "Medida agregada."
                            st.rerun()
                        except Exception as exc:
                            st.error("No se pudo agregar la medida.")
                            st.code(str(exc))

            if st.button("🗑️ Eliminar alimento", key=f"delete_catalog_{food['id']}"):
                try:
                    delete_catalog_food(str(food["id"]))
                    st.session_state["catalog_notice"] = "Alimento eliminado."
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo eliminar.")
                    st.code(str(exc))


def render_link_nutritionist(patient_id: str) -> None:
    st.title("🔗 Mi nutriólogo")
    if patient_has_nutritionist(patient_id):
        st.success("Tu cuenta ya está vinculada con un nutriólogo.")
        st.caption("Para cambiar la vinculación, contacta al administrador de la app.")
        return
    st.write("Solicita a tu nutriólogo su código de vinculación e introdúcelo aquí.")
    with st.form("link_nutritionist_form"):
        code = st.text_input("Código de vinculación").upper()
        submitted = st.form_submit_button("Vincular", width="stretch")
    if submitted:
        if not code.strip():
            st.error("Escribe el código.")
        else:
            try:
                link_nutritionist(code)
                st.success("Nutriólogo vinculado correctamente.")
                st.rerun()
            except Exception as exc:
                st.error("El código no es válido o no se pudo realizar la vinculación.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))


try:
    auth = auth_screen()
except DatabaseConfigError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error("No fue posible cargar tu cuenta.")
    with st.expander("Detalle técnico"):
        st.code(str(exc))
    st.stop()

role = str(auth.get("role") or "patient")
account_timezone = normalize_timezone(auth.get("timezone"))
account_today = local_today(account_timezone)
st.sidebar.title("🥗 Mi Nutrición")
st.sidebar.caption("Paciente" if role == "patient" else "Panel del nutriólogo")
st.sidebar.write(f"### {auth.get('full_name') or auth.get('email')}")

patient_id: str | None = None
patient_profile: dict | None = None
if role == "patient":
    patient_id = str(auth.get("patient_id") or "")
    if not patient_id:
        st.error("Tu cuenta no tiene un expediente de paciente asociado.")
        st.stop()
    patient_profile = get_profile(patient_id)
    pages = ["🏠 Mi día", "➕ Registrar", "📊 Historial", "👤 Perfil y metas", "🔗 Mi nutriólogo"]
    page = st.sidebar.radio("Navegación", pages)
else:
    assigned_patients = list_assigned_patients()
    st.sidebar.info(f"Código para tus pacientes: {auth.get('invite_code')}")

    # El nutriólogo también lleva su propio seguimiento. Su expediente existe
    # desde que creó la cuenta; la versión anterior sólo dejaba de apuntarlo al
    # promoverlo, y por eso hacía falta abrir una segunda cuenta.
    own_patient_id = str(auth.get("patient_id") or "")
    patient_by_label: dict[str, dict] = {}
    if own_patient_id:
        patient_by_label[SELF_TRACKING_LABEL] = {"id": own_patient_id}
    patient_by_label.update(
        {
            f"{row['name']} · {str(row['id'])[:8]}": row for row in assigned_patients
        }
    )

    if patient_by_label:
        selected_label = st.sidebar.selectbox("Expediente", list(patient_by_label))
        selected_record = patient_by_label[selected_label]
        patient_id = str(selected_record["id"])
        # list_assigned_patients ya trae el expediente completo; sólo el propio
        # entra a la lista con el identificador solo.
        patient_profile = (
            selected_record if "name" in selected_record else get_profile(patient_id)
        )
    viewing_self = bool(own_patient_id) and patient_id == own_patient_id

    pages = ["🏠 Resumen", "📊 Historial", "👤 Perfil y metas"]
    if viewing_self:
        pages.insert(1, "➕ Registrar")
    pages += ["🍎 Catálogo", "🍲 Recetas"]
    page = st.sidebar.radio("Navegación", pages)

with st.sidebar.expander("⚙️ Configuración"):
    timezone_labels = list(TIMEZONE_LABELS)
    current_timezone_label = timezone_label(account_timezone)
    selected_timezone_label = st.selectbox(
        "Zona horaria",
        timezone_labels,
        index=timezone_labels.index(current_timezone_label),
        key="account_timezone",
    )
    st.caption(f"Fecha local actual: {account_today.strftime('%d/%m/%Y')}")
    if st.button("Guardar zona horaria", width="stretch"):
        try:
            update_account_timezone(
                str(auth.get("id") or ""),
                TIMEZONE_LABELS[selected_timezone_label],
            )
            st.session_state.pop("selected_log_date", None)
            st.session_state["timezone_notice"] = "Zona horaria actualizada."
            st.rerun()
        except Exception as exc:
            st.error(
                "No se pudo guardar. Ejecuta primero la migración "
                "supabase_v08_2_timezone_migration.sql."
            )
            st.code(str(exc))

if timezone_notice := st.session_state.pop("timezone_notice", None):
    st.sidebar.success(str(timezone_notice))

selected_date = st.session_state.get("selected_log_date")
if not isinstance(selected_date, date):
    selected_date = account_today
st.sidebar.divider()
if st.sidebar.button("Cerrar sesión", width="stretch"):
    sign_out()
    st.rerun()

if role == "nutritionist" and page == "🍎 Catálogo":
    render_catalog_admin()
    st.stop()

if role == "nutritionist" and page == "🍲 Recetas":
    render_recipe_admin()
    st.stop()

if role == "nutritionist" and not patient_id:
    st.title("👥 Pacientes")
    st.info("Aún no tienes pacientes vinculados ni expediente propio.")
    st.write("Comparte este código con tus pacientes:")
    st.code(str(auth.get("invite_code") or ""))
    st.caption(
        "Para llevar además tu propio seguimiento, ejecuta en Supabase "
        "`select public.repair_nutritionist_self_tracking();` de la migración V0.9."
    )
    st.stop()

assert patient_id is not None and patient_profile is not None
try:
    goals = get_goals(patient_id)
except Exception as exc:
    st.error("No fue posible cargar las metas del paciente.")
    st.code(str(exc))
    st.stop()

owns_record = role == "patient" or patient_id == str(auth.get("patient_id") or "")

if page in ("🏠 Mi día", "🏠 Resumen"):
    render_day(
        patient_id,
        goals,
        selected_date,
        can_edit=True,
        can_delete=owns_record,
        account_today=account_today,
    )
elif page == "➕ Registrar":
    selected_date = render_register(patient_id, selected_date, account_today)
elif page == "📊 Historial":
    render_history(patient_id, account_today)
elif page == "👤 Perfil y metas":
    patient_linked = patient_has_nutritionist(patient_id)
    render_profile_and_goals(
        patient_id,
        patient_profile,
        goals,
        can_edit_profile=True,
        can_edit_goals=role == "nutritionist" or not patient_linked,
        current_date=account_today,
    )
elif page == "🔗 Mi nutriólogo":
    render_link_nutritionist(patient_id)
