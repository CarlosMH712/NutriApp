from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from db import (
    AuthenticationError,
    DatabaseConfigError,
    clear_auth_session,
    create_catalog_food,
    delete_catalog_food,
    delete_food,
    get_auth_context,
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
    search_catalog,
    sign_in,
    sign_out,
    sign_up,
    update_goals,
    update_profile,
)
from food_sources import (
    FoodSourceError,
    food_data_central_configured,
    search_food_data_central,
)


st.set_page_config(page_title="Mi Nutrición", page_icon="🥗", layout="wide")


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
        with st.form("login_form"):
            email = st.text_input("Correo electrónico", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_password")
            login_submitted = st.form_submit_button(
                "Entrar", use_container_width=True
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
            new_email = st.text_input("Correo electrónico", key="register_email")
            new_password = st.text_input(
                "Contraseña (mínimo 8 caracteres)",
                type="password",
                key="register_password",
            )
            confirm_password = st.text_input(
                "Confirmar contraseña", type="password"
            )
            register_submitted = st.form_submit_button(
                "Crear mi cuenta", use_container_width=True
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
    return {key: float(df[key].fillna(0).sum()) for key in keys}


def render_day(patient_id: str, goals: dict, selected_date: date, can_delete: bool) -> None:
    st.title("🥗 Mi día" if can_delete else "🥗 Resumen del paciente")
    st.caption(selected_date.strftime("%d/%m/%Y"))
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
                widths = [5, 2, 1] if can_delete else [5, 2]
                columns = st.columns(widths)
                with columns[0]:
                    st.write(f"**{row['food']}**")
                    st.caption(
                        f"{row['quantity']} {row['unit']} · "
                        f"P {float(row['protein']):.1f} g · "
                        f"CHO {float(row['carbs']):.1f} g · "
                        f"G {float(row['fat']):.1f} g · "
                        f"Fibra {float(row['fiber']):.1f} g"
                    )
                    if pd.notna(row.get("source_name")) and row.get("source_name"):
                        st.caption(f"Fuente: {row['source_name']}")
                with columns[1]:
                    st.write(f"**{float(row['calories']):.0f} kcal**")
                if can_delete:
                    with columns[2]:
                        if st.button("🗑️", key=f"delete_{row['id']}", help="Eliminar registro"):
                            try:
                                delete_food(int(row["id"]), patient_id)
                                st.rerun()
                            except Exception as exc:
                                st.error("No se pudo eliminar el alimento.")
                                st.code(str(exc))


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
            "🔎 Buscar", use_container_width=True
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

    unit_options = ["gramos"]
    portion_name = str(selected_food.get("portion_name") or "").strip()
    portion_grams = float(selected_food.get("portion_grams") or 0)
    if portion_name and portion_grams > 0:
        unit_options.append(portion_name)

    selection_key = str(selected_food["result_key"]).replace(":", "_")
    unit_choice = st.selectbox(
        "Unidad",
        unit_options,
        key=f"catalog_unit_{selection_key}",
    )
    default_quantity = 100.0 if unit_choice == "gramos" else 1.0
    amount = st.number_input(
        "Cantidad consumida",
        min_value=0.01,
        value=default_quantity,
        step=1.0 if unit_choice == "gramos" else 0.5,
        key=f"catalog_amount_{selection_key}_{unit_choice}",
    )
    grams = float(amount) if unit_choice == "gramos" else float(amount) * portion_grams
    factor = grams / 100.0
    calculated = {
        "calories": float(selected_food["calories_per_100g"]) * factor,
        "protein": float(selected_food["protein_per_100g"]) * factor,
        "carbs": float(selected_food["carbs_per_100g"]) * factor,
        "fat": float(selected_food["fat_per_100g"]) * factor,
        "fiber": float(selected_food["fiber_per_100g"]) * factor,
        "water": float(selected_food["water_per_100g"]) * factor,
    }

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
    if st.button("✅ Confirmar y registrar", use_container_width=True):
        try:
            save_food(
                patient_id,
                selected_date,
                meal,
                str(selected_food["name"]),
                float(amount),
                "g" if unit_choice == "gramos" else unit_choice,
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
            unit = st.selectbox("Unidad", ["pieza", "g", "ml", "taza", "cucharada", "porción"], key="manual_unit")
        with col2:
            calories = st.number_input("Calorías (kcal)", min_value=0.0, step=10.0, key="manual_calories")
            protein = st.number_input("Proteína (g)", min_value=0.0, step=1.0, key="manual_protein")
            carbs = st.number_input("Carbohidratos (g)", min_value=0.0, step=1.0, key="manual_carbs")
            fat = st.number_input("Grasas (g)", min_value=0.0, step=1.0, key="manual_fat")
            fiber = st.number_input("Fibra (g)", min_value=0.0, step=1.0, key="manual_fiber")
            water = st.number_input("Agua (ml)", min_value=0.0, step=50.0, key="manual_water")
        submitted = st.form_submit_button("✅ Registrar manualmente", use_container_width=True)

    if submitted:
        if not food.strip():
            st.error("Escribe el nombre del alimento.")
        else:
            try:
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
                    water,
                    source_name="Registro manual",
                )
                st.success(f"{food.strip()} registrado correctamente.")
            except Exception as exc:
                st.error("No se pudo registrar el alimento.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))


def render_register(patient_id: str, selected_date: date) -> None:
    st.title("➕ Registrar alimento")
    catalog_tab, manual_tab = st.tabs(["🔎 Desde catálogo", "✍️ Registro manual"])
    with catalog_tab:
        render_catalog_register(patient_id, selected_date)
    with manual_tab:
        render_manual_register(patient_id, selected_date)


def render_history(patient_id: str) -> None:
    st.title("📊 Historial")
    try:
        raw_history = get_history(patient_id)
    except Exception as exc:
        st.error("No se pudo cargar el historial.")
        st.code(str(exc))
        return

    if raw_history.empty:
        st.info("Todavía no hay datos suficientes para mostrar historial.")
        return

    raw_history["log_date"] = pd.to_datetime(raw_history["log_date"])
    numeric_cols = ["calories", "protein", "carbs", "fat", "fiber", "water"]
    for col in numeric_cols:
        raw_history[col] = pd.to_numeric(raw_history[col], errors="coerce").fillna(0)
    df_history = (
        raw_history.groupby("log_date", as_index=False)[numeric_cols]
        .sum()
        .sort_values("log_date")
    )
    start_date = pd.Timestamp(date.today() - timedelta(days=6))
    week_df = df_history[df_history["log_date"] >= start_date]

    st.subheader("Últimos 7 días")
    c1, c2, c3 = st.columns(3)
    c1.metric("Promedio energético", f"{week_df['calories'].mean():.0f} kcal/día" if not week_df.empty else "0 kcal/día")
    c2.metric("Proteína promedio", f"{week_df['protein'].mean():.1f} g/día" if not week_df.empty else "0 g/día")
    c3.metric("Días registrados", f"{len(week_df)} / 7")
    st.subheader("🔥 Energía")
    st.line_chart(week_df.set_index("log_date")[["calories"]])
    st.subheader("🥩 Proteína")
    st.line_chart(week_df.set_index("log_date")[["protein"]])
    st.subheader("Datos")
    display_df = df_history.copy()
    display_df["log_date"] = display_df["log_date"].dt.strftime("%d/%m/%Y")
    display_df = display_df.rename(
        columns={
            "log_date": "Fecha",
            "calories": "kcal",
            "protein": "Proteína (g)",
            "carbs": "CHO (g)",
            "fat": "Grasas (g)",
            "fiber": "Fibra (g)",
            "water": "Agua (ml)",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_profile_and_goals(
    patient_id: str,
    profile: dict,
    goals: dict,
    can_edit_profile: bool,
    can_edit_goals: bool,
) -> None:
    st.title("👤 Perfil y metas")
    tab1, tab2 = st.tabs(["Perfil", "Metas nutricionales"])
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
                save_profile = st.form_submit_button("Guardar perfil", use_container_width=True)
            if save_profile:
                try:
                    update_profile(patient_id, name, age, sex, weight, height)
                    st.success("Perfil actualizado.")
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo actualizar el perfil.")
                    st.code(str(exc))

    with tab2:
        st.subheader("Metas nutricionales")
        if not can_edit_goals:
            st.info("Estas metas fueron establecidas por tu nutriólogo.")
        with st.form("goals_form"):
            goal_calories = st.number_input("Energía (kcal/día)", min_value=0.0, value=float(goals["calories"]), step=50.0, disabled=not can_edit_goals)
            goal_protein = st.number_input("Proteína (g/día)", min_value=0.0, value=float(goals["protein"]), step=5.0, disabled=not can_edit_goals)
            goal_carbs = st.number_input("Carbohidratos (g/día)", min_value=0.0, value=float(goals["carbs"]), step=5.0, disabled=not can_edit_goals)
            goal_fat = st.number_input("Grasas (g/día)", min_value=0.0, value=float(goals["fat"]), step=5.0, disabled=not can_edit_goals)
            goal_fiber = st.number_input("Fibra (g/día)", min_value=0.0, value=float(goals["fiber"]), step=1.0, disabled=not can_edit_goals)
            goal_water = st.number_input("Agua (ml/día)", min_value=0.0, value=float(goals["water"]), step=100.0, disabled=not can_edit_goals)
            save_goals = st.form_submit_button("Guardar metas", use_container_width=True, disabled=not can_edit_goals)
        if save_goals:
            try:
                update_goals(patient_id, goal_calories, goal_protein, goal_carbs, goal_fat, goal_fiber, goal_water)
                st.success("Metas actualizadas.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudieron actualizar las metas.")
                st.code(str(exc))


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
            st.caption("Porción casera opcional")
            portion_col1, portion_col2 = st.columns(2)
            with portion_col1:
                portion_name = st.text_input("Nombre de la porción", placeholder="Ej. pieza mediana")
            with portion_col2:
                portion_grams = st.number_input("Gramos por porción", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Guardar en catálogo", use_container_width=True)

        if submitted:
            if not name.strip():
                st.error("Escribe el nombre del alimento.")
            elif bool(portion_name.strip()) != bool(portion_grams > 0):
                st.error("Completa tanto el nombre como los gramos de la porción.")
            else:
                try:
                    create_catalog_food(
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
                    st.dataframe(import_df.head(25), use_container_width=True, hide_index=True)
                    if st.button("Importar alimentos", use_container_width=True):
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
        try:
            owned_foods = list_owned_catalog()
        except Exception as exc:
            st.error("No se pudo cargar el catálogo.")
            st.code(str(exc))
            owned_foods = []
        if not owned_foods:
            st.info("Todavía no has creado alimentos.")
        else:
            st.caption(f"{len(owned_foods)} alimentos")
            for food in owned_foods[:200]:
                col_name, col_values, col_delete = st.columns([4, 4, 1])
                with col_name:
                    st.write(f"**{food['name']}**")
                    st.caption(str(food.get("brand") or food.get("source") or ""))
                with col_values:
                    st.caption(
                        f"100 g: {float(food['calories_per_100g']):.0f} kcal · "
                        f"P {float(food['protein_per_100g']):.1f} · "
                        f"CHO {float(food['carbs_per_100g']):.1f} · "
                        f"G {float(food['fat_per_100g']):.1f}"
                    )
                with col_delete:
                    if st.button("🗑️", key=f"delete_catalog_{food['id']}"):
                        try:
                            delete_catalog_food(str(food["id"]))
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
        submitted = st.form_submit_button("Vincular", use_container_width=True)
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
    if assigned_patients:
        patient_by_label = {
            f"{row['name']} · {str(row['id'])[:8]}": row for row in assigned_patients
        }
        selected_label = st.sidebar.selectbox("Paciente", list(patient_by_label))
        patient_profile = patient_by_label[selected_label]
        patient_id = str(patient_profile["id"])
    pages = ["🏠 Resumen", "📊 Historial", "👤 Perfil y metas", "🍎 Catálogo"]
    page = st.sidebar.radio("Navegación", pages)

selected_date = st.sidebar.date_input("Fecha", value=date.today())
st.sidebar.divider()
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    sign_out()
    st.rerun()

if role == "nutritionist" and page == "🍎 Catálogo":
    render_catalog_admin()
    st.stop()

if role == "nutritionist" and not patient_id:
    st.title("👥 Pacientes")
    st.info("Aún no tienes pacientes vinculados.")
    st.write("Comparte este código con tus pacientes:")
    st.code(str(auth.get("invite_code") or ""))
    st.stop()

assert patient_id is not None and patient_profile is not None
try:
    goals = get_goals(patient_id)
except Exception as exc:
    st.error("No fue posible cargar las metas del paciente.")
    st.code(str(exc))
    st.stop()

if page in ("🏠 Mi día", "🏠 Resumen"):
    render_day(patient_id, goals, selected_date, can_delete=role == "patient")
elif page == "➕ Registrar":
    render_register(patient_id, selected_date)
elif page == "📊 Historial":
    render_history(patient_id)
elif page == "👤 Perfil y metas":
    patient_linked = patient_has_nutritionist(patient_id)
    render_profile_and_goals(
        patient_id,
        patient_profile,
        goals,
        can_edit_profile=True,
        can_edit_goals=role == "nutritionist" or not patient_linked,
    )
elif page == "🔗 Mi nutriólogo":
    render_link_nutritionist(patient_id)
