from __future__ import annotations

import hmac
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from db import (
    DatabaseConfigError,
    delete_food,
    ensure_demo_patient,
    get_day_log,
    get_goals,
    get_history,
    get_profile,
    save_food,
    update_goals,
    update_profile,
)


st.set_page_config(
    page_title="Mi Nutrición",
    page_icon="🥗",
    layout="wide",
)


# ============================================================
# AUTENTICACIÓN MVP
# ============================================================


def get_app_pin() -> str:
    try:
        return str(st.secrets["app"]["pin"])
    except (KeyError, FileNotFoundError):
        return ""


def authenticate() -> bool:
    expected_pin = get_app_pin()

    if not expected_pin:
        st.error(
            "Falta configurar [app].pin en los Secrets de Streamlit. "
            "Consulta el README del proyecto."
        )
        return False

    if st.session_state.get("authenticated", False):
        return True

    st.title("🥗 Mi Nutrición")
    st.write("Acceso privado al MVP de seguimiento nutricional.")

    with st.form("login_form"):
        pin = st.text_input("PIN de acceso", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)

    if submitted:
        if hmac.compare_digest(pin, expected_pin):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("PIN incorrecto.")

    st.caption(
        "Este PIN es una protección básica para el MVP. "
        "La siguiente etapa debería incorporar autenticación individual."
    )
    return False


if not authenticate():
    st.stop()


# ============================================================
# INICIALIZACIÓN DE SUPABASE
# ============================================================

try:
    ensure_demo_patient()
    profile = get_profile()
    goals = get_goals()
except DatabaseConfigError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(
        "No fue posible conectar con Supabase. Verifica que ejecutaste "
        "supabase_schema.sql y que las credenciales de Streamlit Secrets sean correctas."
    )
    with st.expander("Detalle técnico"):
        st.code(str(exc))
    st.stop()


# ============================================================
# UTILIDADES DE UI
# ============================================================


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
    if df.empty:
        return {
            "calories": 0.0,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 0.0,
            "fiber": 0.0,
            "water": 0.0,
        }

    return {
        key: float(df[key].fillna(0).sum())
        for key in ["calories", "protein", "carbs", "fat", "fiber", "water"]
    }


def safe_action(action, success_message: str) -> None:
    try:
        action()
        st.success(success_message)
    except Exception as exc:
        st.error("No se pudo guardar el cambio en Supabase.")
        with st.expander("Detalle técnico"):
            st.code(str(exc))


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🥗 Mi Nutrición")
st.sidebar.caption("MVP con persistencia en Supabase")
st.sidebar.write(f"### {profile['name']}")

page = st.sidebar.radio(
    "Navegación",
    [
        "🏠 Mi día",
        "➕ Registrar",
        "📊 Historial",
        "👤 Perfil y metas",
    ],
)

st.sidebar.divider()
selected_date = st.sidebar.date_input("Fecha", value=date.today())

st.sidebar.divider()
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    st.session_state.clear()
    st.rerun()

st.sidebar.caption("Los datos se almacenan en Supabase/PostgreSQL.")


# ============================================================
# MI DÍA
# ============================================================

if page == "🏠 Mi día":
    st.title("🥗 Mi día")
    st.caption(selected_date.strftime("%d/%m/%Y"))

    try:
        df = get_day_log(selected_date)
    except Exception as exc:
        st.error("No se pudo cargar el registro del día.")
        st.code(str(exc))
        st.stop()

    totals = totals_for_day(df)

    col1, col2, col3, col4 = st.columns(4)

    remaining_calories = float(goals["calories"]) - totals["calories"]
    col1.metric(
        "🔥 Energía",
        f"{totals['calories']:.0f} kcal",
        f"{remaining_calories:.0f} restantes",
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
    else:
        for meal in ["Desayuno", "Comida", "Cena", "Snack"]:
            meal_df = df[df["meal"] == meal]
            if meal_df.empty:
                continue

            meal_calories = meal_df["calories"].fillna(0).sum()
            with st.expander(f"{meal} · {meal_calories:.0f} kcal", expanded=True):
                for _, row in meal_df.iterrows():
                    col_food, col_kcal, col_delete = st.columns([5, 2, 1])

                    with col_food:
                        st.write(f"**{row['food']}**")
                        st.caption(
                            f"{row['quantity']} {row['unit']} · "
                            f"P {float(row['protein']):.1f} g · "
                            f"CHO {float(row['carbs']):.1f} g · "
                            f"G {float(row['fat']):.1f} g · "
                            f"Fibra {float(row['fiber']):.1f} g"
                        )

                    with col_kcal:
                        st.write(f"**{float(row['calories']):.0f} kcal**")

                    with col_delete:
                        if st.button(
                            "🗑️",
                            key=f"delete_{row['id']}",
                            help="Eliminar registro",
                        ):
                            try:
                                delete_food(int(row["id"]))
                                st.rerun()
                            except Exception as exc:
                                st.error("No se pudo eliminar el alimento.")
                                st.code(str(exc))


# ============================================================
# REGISTRAR
# ============================================================

elif page == "➕ Registrar":
    st.title("➕ Registrar alimento")
    st.write(
        "Introduce los valores nutricionales correspondientes a la cantidad realmente consumida."
    )

    with st.form("food_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            meal = st.selectbox(
                "Tiempo de comida", ["Desayuno", "Comida", "Cena", "Snack"]
            )
            food = st.text_input("Alimento", placeholder="Ej. Huevo")
            quantity = st.number_input(
                "Cantidad", min_value=0.0, value=1.0, step=0.5
            )
            unit = st.selectbox(
                "Unidad",
                ["pieza", "g", "ml", "taza", "cucharada", "porción"],
            )

        with col2:
            calories = st.number_input("Calorías (kcal)", min_value=0.0, step=10.0)
            protein = st.number_input("Proteína (g)", min_value=0.0, step=1.0)
            carbs = st.number_input("Carbohidratos (g)", min_value=0.0, step=1.0)
            fat = st.number_input("Grasas (g)", min_value=0.0, step=1.0)
            fiber = st.number_input("Fibra (g)", min_value=0.0, step=1.0)
            water = st.number_input("Agua (ml)", min_value=0.0, step=50.0)

        submitted = st.form_submit_button(
            "✅ Registrar alimento", use_container_width=True
        )

    if submitted:
        if not food.strip():
            st.error("Escribe el nombre del alimento.")
        else:
            try:
                save_food(
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
                )
                st.success(f"{food.strip()} registrado correctamente.")
            except Exception as exc:
                st.error("No se pudo registrar el alimento en Supabase.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))


# ============================================================
# HISTORIAL
# ============================================================

elif page == "📊 Historial":
    st.title("📊 Historial")

    try:
        raw_history = get_history()
    except Exception as exc:
        st.error("No se pudo cargar el historial.")
        st.code(str(exc))
        st.stop()

    if raw_history.empty:
        st.info("Todavía no hay datos suficientes para mostrar historial.")
    else:
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

        c1.metric(
            "Promedio energético",
            f"{week_df['calories'].mean():.0f} kcal/día" if not week_df.empty else "0 kcal/día",
        )
        c2.metric(
            "Proteína promedio",
            f"{week_df['protein'].mean():.1f} g/día" if not week_df.empty else "0 g/día",
        )
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


# ============================================================
# PERFIL Y METAS
# ============================================================

elif page == "👤 Perfil y metas":
    st.title("👤 Perfil y metas")
    tab1, tab2 = st.tabs(["Perfil", "Metas nutricionales"])

    with tab1:
        st.subheader("Datos del paciente")

        with st.form("profile_form"):
            name = st.text_input("Nombre", value=str(profile["name"]))
            age = st.number_input(
                "Edad", min_value=1, max_value=120, value=int(profile["age"])
            )

            sex_options = ["Femenino", "Masculino", "Otro / no especificado"]
            try:
                sex_index = sex_options.index(str(profile["sex"]))
            except ValueError:
                sex_index = 0

            sex = st.selectbox("Sexo", sex_options, index=sex_index)
            weight = st.number_input(
                "Peso (kg)", min_value=1.0, value=float(profile["weight"]), step=0.1
            )
            height = st.number_input(
                "Estatura (cm)", min_value=50.0, value=float(profile["height"]), step=0.5
            )
            save_profile = st.form_submit_button(
                "Guardar perfil", use_container_width=True
            )

        if save_profile:
            try:
                update_profile(name, age, sex, weight, height)
                st.success("Perfil actualizado.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo actualizar el perfil.")
                st.code(str(exc))

    with tab2:
        st.subheader("Metas establecidas por la nutrióloga")
        st.caption(
            "Estas metas son editables manualmente. La aplicación no sustituye el criterio profesional."
        )

        with st.form("goals_form"):
            goal_calories = st.number_input(
                "Energía (kcal/día)",
                min_value=0.0,
                value=float(goals["calories"]),
                step=50.0,
            )
            goal_protein = st.number_input(
                "Proteína (g/día)", min_value=0.0, value=float(goals["protein"]), step=5.0
            )
            goal_carbs = st.number_input(
                "Carbohidratos (g/día)", min_value=0.0, value=float(goals["carbs"]), step=5.0
            )
            goal_fat = st.number_input(
                "Grasas (g/día)", min_value=0.0, value=float(goals["fat"]), step=5.0
            )
            goal_fiber = st.number_input(
                "Fibra (g/día)", min_value=0.0, value=float(goals["fiber"]), step=1.0
            )
            goal_water = st.number_input(
                "Agua (ml/día)", min_value=0.0, value=float(goals["water"]), step=100.0
            )
            save_goals = st.form_submit_button(
                "Guardar metas", use_container_width=True
            )

        if save_goals:
            try:
                update_goals(
                    goal_calories,
                    goal_protein,
                    goal_carbs,
                    goal_fat,
                    goal_fiber,
                    goal_water,
                )
                st.success("Metas actualizadas.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudieron actualizar las metas.")
                st.code(str(exc))
