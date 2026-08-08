from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from db import (
    AuthenticationError,
    DatabaseConfigError,
    clear_auth_session,
    delete_food,
    get_auth_context,
    get_day_log,
    get_goals,
    get_history,
    get_profile,
    link_nutritionist,
    list_assigned_patients,
    patient_has_nutritionist,
    save_food,
    sign_in,
    sign_out,
    sign_up,
    update_goals,
    update_profile,
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


def render_register(patient_id: str, selected_date: date) -> None:
    st.title("➕ Registrar alimento")
    st.write("Introduce los valores correspondientes a la cantidad realmente consumida.")
    with st.form("food_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            meal = st.selectbox("Tiempo de comida", ["Desayuno", "Comida", "Cena", "Snack"])
            food = st.text_input("Alimento", placeholder="Ej. Huevo")
            quantity = st.number_input("Cantidad", min_value=0.0, value=1.0, step=0.5)
            unit = st.selectbox("Unidad", ["pieza", "g", "ml", "taza", "cucharada", "porción"])
        with col2:
            calories = st.number_input("Calorías (kcal)", min_value=0.0, step=10.0)
            protein = st.number_input("Proteína (g)", min_value=0.0, step=1.0)
            carbs = st.number_input("Carbohidratos (g)", min_value=0.0, step=1.0)
            fat = st.number_input("Grasas (g)", min_value=0.0, step=1.0)
            fiber = st.number_input("Fibra (g)", min_value=0.0, step=1.0)
            water = st.number_input("Agua (ml)", min_value=0.0, step=50.0)
        submitted = st.form_submit_button("✅ Registrar alimento", use_container_width=True)

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
                )
                st.success(f"{food.strip()} registrado correctamente.")
            except Exception as exc:
                st.error("No se pudo registrar el alimento.")
                with st.expander("Detalle técnico"):
                    st.code(str(exc))


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
    pages = ["🏠 Resumen", "📊 Historial", "👤 Perfil y metas"]
    page = st.sidebar.radio("Navegación", pages)

selected_date = st.sidebar.date_input("Fecha", value=date.today())
st.sidebar.divider()
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    sign_out()
    st.rerun()

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
