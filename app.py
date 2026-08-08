import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="Mi Nutrición",
    page_icon="🥗",
    layout="wide",
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = DATA_DIR / "nutrition.db"


# ============================================================
# BASE DE DATOS
# ============================================================

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            sex TEXT,
            weight REAL,
            height REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY,
            calories REAL,
            protein REAL,
            carbs REAL,
            fat REAL,
            fiber REAL,
            water REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS food_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT,
            meal TEXT,
            food TEXT,
            quantity REAL,
            unit TEXT,
            calories REAL,
            protein REAL,
            carbs REAL,
            fat REAL,
            fiber REAL,
            water REAL DEFAULT 0
        )
    """)

    cur.execute("SELECT COUNT(*) FROM profile")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO profile
            (id, name, age, sex, weight, height)
            VALUES (1, 'Paciente demo', 30, 'Femenino', 65, 165)
        """)

    cur.execute("SELECT COUNT(*) FROM goals")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO goals
            (id, calories, protein, carbs, fat, fiber, water)
            VALUES (1, 2000, 120, 220, 65, 30, 2500)
        """)

    conn.commit()
    conn.close()


def get_profile():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM profile WHERE id = 1", conn)
    conn.close()
    return df.iloc[0]


def get_goals():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM goals WHERE id = 1", conn)
    conn.close()
    return df.iloc[0]


def get_day_log(selected_date):
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT *
        FROM food_log
        WHERE log_date = ?
        ORDER BY id
        """,
        conn,
        params=(str(selected_date),),
    )
    conn.close()
    return df


def save_food(
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
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO food_log (
            log_date,
            meal,
            food,
            quantity,
            unit,
            calories,
            protein,
            carbs,
            fat,
            fiber,
            water
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(selected_date),
        meal,
        food.strip(),
        quantity,
        unit,
        calories,
        protein,
        carbs,
        fat,
        fiber,
        water,
    ))

    conn.commit()
    conn.close()


def delete_food(food_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM food_log WHERE id = ?", (food_id,))
    conn.commit()
    conn.close()


def update_profile(name, age, sex, weight, height):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE profile
        SET name = ?, age = ?, sex = ?, weight = ?, height = ?
        WHERE id = 1
    """, (name.strip(), age, sex, weight, height))

    conn.commit()
    conn.close()


def update_goals(calories, protein, carbs, fat, fiber, water):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE goals
        SET calories = ?, protein = ?, carbs = ?, fat = ?, fiber = ?, water = ?
        WHERE id = 1
    """, (calories, protein, carbs, fat, fiber, water))

    conn.commit()
    conn.close()


# ============================================================
# UTILIDADES
# ============================================================

def progress_value(consumed, goal):
    if goal <= 0:
        return 0.0
    return min(max(float(consumed) / float(goal), 0.0), 1.0)


def nutrient_progress(title, consumed, goal, unit):
    st.write(f"**{title}**")
    st.progress(progress_value(consumed, goal))

    remaining = max(float(goal) - float(consumed), 0.0)

    st.caption(
        f"{consumed:.1f} / {goal:.1f} {unit} · "
        f"Restante: {remaining:.1f} {unit}"
    )


def totals_for_day(df):
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
        "calories": float(df["calories"].sum()),
        "protein": float(df["protein"].sum()),
        "carbs": float(df["carbs"].sum()),
        "fat": float(df["fat"].sum()),
        "fiber": float(df["fiber"].sum()),
        "water": float(df["water"].sum()),
    }


# ============================================================
# INICIALIZAR
# ============================================================

init_db()

profile = get_profile()
goals = get_goals()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🥗 Mi Nutrición")
st.sidebar.caption("MVP de seguimiento nutricional")
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

selected_date = st.sidebar.date_input(
    "Fecha",
    value=date.today(),
)


# ============================================================
# MI DÍA
# ============================================================

if page == "🏠 Mi día":
    st.title("🥗 Mi día")
    st.caption(selected_date.strftime("%d/%m/%Y"))

    df = get_day_log(selected_date)
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
        f"Meta {goals['protein']:.0f} g",
    )

    col3.metric(
        "🍚 Carbohidratos",
        f"{totals['carbs']:.1f} g",
        f"Meta {goals['carbs']:.0f} g",
    )

    col4.metric(
        "🥑 Grasas",
        f"{totals['fat']:.1f} g",
        f"Meta {goals['fat']:.0f} g",
    )

    st.divider()

    left, right = st.columns(2)

    with left:
        nutrient_progress(
            "🔥 Energía",
            totals["calories"],
            float(goals["calories"]),
            "kcal",
        )
        nutrient_progress(
            "🥩 Proteína",
            totals["protein"],
            float(goals["protein"]),
            "g",
        )
        nutrient_progress(
            "🍚 Carbohidratos",
            totals["carbs"],
            float(goals["carbs"]),
            "g",
        )

    with right:
        nutrient_progress(
            "🥑 Grasas",
            totals["fat"],
            float(goals["fat"]),
            "g",
        )
        nutrient_progress(
            "🌾 Fibra",
            totals["fiber"],
            float(goals["fiber"]),
            "g",
        )
        nutrient_progress(
            "💧 Agua",
            totals["water"],
            float(goals["water"]),
            "ml",
        )

    st.divider()
    st.subheader("🍽️ Registro del día")

    if df.empty:
        st.info("Todavía no hay alimentos registrados.")
    else:
        meal_order = ["Desayuno", "Comida", "Cena", "Snack"]

        for meal in meal_order:
            meal_df = df[df["meal"] == meal]

            if meal_df.empty:
                continue

            calories = meal_df["calories"].sum()

            with st.expander(
                f"{meal} · {calories:.0f} kcal",
                expanded=True,
            ):
                for _, row in meal_df.iterrows():
                    col_food, col_kcal, col_delete = st.columns([5, 2, 1])

                    with col_food:
                        st.write(f"**{row['food']}**")
                        st.caption(
                            f"{row['quantity']} {row['unit']} · "
                            f"P {row['protein']:.1f} g · "
                            f"CHO {row['carbs']:.1f} g · "
                            f"G {row['fat']:.1f} g · "
                            f"Fibra {row['fiber']:.1f} g"
                        )

                    with col_kcal:
                        st.write(f"**{row['calories']:.0f} kcal**")

                    with col_delete:
                        if st.button(
                            "🗑️",
                            key=f"delete_{row['id']}",
                            help="Eliminar registro",
                        ):
                            delete_food(int(row["id"]))
                            st.rerun()


# ============================================================
# REGISTRAR
# ============================================================

elif page == "➕ Registrar":
    st.title("➕ Registrar alimento")
    st.write(
        "Introduce los valores nutricionales correspondientes "
        "a la cantidad realmente consumida."
    )

    with st.form("food_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            meal = st.selectbox(
                "Tiempo de comida",
                ["Desayuno", "Comida", "Cena", "Snack"],
            )

            food = st.text_input(
                "Alimento",
                placeholder="Ej. Huevo",
            )

            quantity = st.number_input(
                "Cantidad",
                min_value=0.0,
                value=1.0,
                step=0.5,
            )

            unit = st.selectbox(
                "Unidad",
                [
                    "pieza",
                    "g",
                    "ml",
                    "taza",
                    "cucharada",
                    "porción",
                ],
            )

        with col2:
            calories = st.number_input(
                "Calorías (kcal)",
                min_value=0.0,
                step=10.0,
            )

            protein = st.number_input(
                "Proteína (g)",
                min_value=0.0,
                step=1.0,
            )

            carbs = st.number_input(
                "Carbohidratos (g)",
                min_value=0.0,
                step=1.0,
            )

            fat = st.number_input(
                "Grasas (g)",
                min_value=0.0,
                step=1.0,
            )

            fiber = st.number_input(
                "Fibra (g)",
                min_value=0.0,
                step=1.0,
            )

            water = st.number_input(
                "Agua (ml)",
                min_value=0.0,
                step=50.0,
            )

        submitted = st.form_submit_button(
            "✅ Registrar alimento",
            use_container_width=True,
        )

        if submitted:
            if not food.strip():
                st.error("Escribe el nombre del alimento.")
            else:
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


# ============================================================
# HISTORIAL
# ============================================================

elif page == "📊 Historial":
    st.title("📊 Historial")

    conn = get_connection()

    df_history = pd.read_sql_query(
        """
        SELECT
            log_date,
            SUM(calories) AS calories,
            SUM(protein) AS protein,
            SUM(carbs) AS carbs,
            SUM(fat) AS fat,
            SUM(fiber) AS fiber,
            SUM(water) AS water
        FROM food_log
        GROUP BY log_date
        ORDER BY log_date
        """,
        conn,
    )

    conn.close()

    if df_history.empty:
        st.info("Todavía no hay datos suficientes para mostrar historial.")
    else:
        df_history["log_date"] = pd.to_datetime(df_history["log_date"])

        start_date = pd.Timestamp(date.today() - timedelta(days=6))
        week_df = df_history[df_history["log_date"] >= start_date]

        st.subheader("Últimos 7 días")

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Promedio energético",
            f"{week_df['calories'].mean():.0f} kcal/día",
        )

        c2.metric(
            "Proteína promedio",
            f"{week_df['protein'].mean():.1f} g/día",
        )

        c3.metric(
            "Días registrados",
            f"{len(week_df)} / 7",
        )

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

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# PERFIL Y METAS
# ============================================================

elif page == "👤 Perfil y metas":
    st.title("👤 Perfil y metas")

    tab1, tab2 = st.tabs(["Perfil", "Metas nutricionales"])

    with tab1:
        st.subheader("Datos del paciente")

        with st.form("profile_form"):
            name = st.text_input(
                "Nombre",
                value=str(profile["name"]),
            )

            age = st.number_input(
                "Edad",
                min_value=1,
                max_value=120,
                value=int(profile["age"]),
            )

            sex_options = [
                "Femenino",
                "Masculino",
                "Otro / no especificado",
            ]

            try:
                sex_index = sex_options.index(str(profile["sex"]))
            except ValueError:
                sex_index = 0

            sex = st.selectbox(
                "Sexo",
                sex_options,
                index=sex_index,
            )

            weight = st.number_input(
                "Peso (kg)",
                min_value=1.0,
                value=float(profile["weight"]),
                step=0.1,
            )

            height = st.number_input(
                "Estatura (cm)",
                min_value=50.0,
                value=float(profile["height"]),
                step=0.5,
            )

            save_profile = st.form_submit_button(
                "Guardar perfil",
                use_container_width=True,
            )

            if save_profile:
                update_profile(name, age, sex, weight, height)
                st.success("Perfil actualizado.")
                st.rerun()

    with tab2:
        st.subheader("Metas establecidas por la nutrióloga")

        st.caption(
            "Estas metas son editables manualmente. "
            "La aplicación no sustituye el criterio profesional."
        )

        with st.form("goals_form"):
            goal_calories = st.number_input(
                "Energía (kcal/día)",
                min_value=0.0,
                value=float(goals["calories"]),
                step=50.0,
            )

            goal_protein = st.number_input(
                "Proteína (g/día)",
                min_value=0.0,
                value=float(goals["protein"]),
                step=5.0,
            )

            goal_carbs = st.number_input(
                "Carbohidratos (g/día)",
                min_value=0.0,
                value=float(goals["carbs"]),
                step=5.0,
            )

            goal_fat = st.number_input(
                "Grasas (g/día)",
                min_value=0.0,
                value=float(goals["fat"]),
                step=5.0,
            )

            goal_fiber = st.number_input(
                "Fibra (g/día)",
                min_value=0.0,
                value=float(goals["fiber"]),
                step=1.0,
            )

            goal_water = st.number_input(
                "Agua (ml/día)",
                min_value=0.0,
                value=float(goals["water"]),
                step=100.0,
            )

            save_goals = st.form_submit_button(
                "Guardar metas",
                use_container_width=True,
            )

            if save_goals:
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


# ============================================================
# AVISO
# ============================================================

st.sidebar.divider()
st.sidebar.caption(
    "Versión MVP. Los datos se almacenan localmente en SQLite."
)
