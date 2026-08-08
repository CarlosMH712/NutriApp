# 🥗 Mi Nutrición — Streamlit MVP

Primera versión de una app de seguimiento nutricional desarrollada con Streamlit.

## Funciones incluidas

- Perfil básico del paciente.
- Metas nutricionales editables por la nutrióloga.
- Registro de desayuno, comida, cena y snacks.
- Seguimiento de:
  - kcal
  - proteína
  - carbohidratos
  - grasas
  - fibra
  - agua
- Dashboard diario.
- Historial y resumen de los últimos 7 días.
- Persistencia local mediante SQLite.
- Estructura sencilla para seguir incorporando:
  - múltiples pacientes
  - base de alimentos
  - equivalentes
  - recetas
  - IA
  - Supabase/PostgreSQL

## Estructura

```text
nutrition_streamlit_mvp/
├── .streamlit/
│   └── config.toml
├── app.py
├── requirements.txt
├── .gitignore
└── README.md
```

La carpeta `data/` se crea automáticamente al ejecutar la app y no se sube a GitHub.

## Ejecutar localmente

### 1. Crear entorno virtual

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Ejecutar

```bash
streamlit run app.py
```

## Subir a GitHub

Desde esta carpeta:

```bash
git init
git add .
git commit -m "Initial nutrition Streamlit MVP"
git branch -M main
git remote add origin URL_DE_TU_REPOSITORIO
git push -u origin main
```

También puedes copiar directamente esta carpeta dentro de un repositorio que ya tengas.

## Desplegar en Streamlit Community Cloud

1. Sube el repositorio a GitHub.
2. Entra a Streamlit Community Cloud.
3. Selecciona **Create app**.
4. Conecta el repositorio.
5. Selecciona:
   - Branch: `main`
   - Main file path: `app.py`
6. Despliega la aplicación.

## ⚠️ Persistencia en Streamlit Community Cloud

Esta primera versión usa SQLite para que sea muy fácil probarla localmente.

En Streamlit Community Cloud, el sistema de archivos de la instancia no debe considerarse una base de datos persistente. Los datos pueden perderse cuando la aplicación se reinicia, se actualiza o se vuelve a desplegar.

Por ello:

- Esta versión es adecuada como **MVP y demostración**.
- No debe usarse todavía para almacenar expedientes reales de pacientes.
- La siguiente versión debería migrar la persistencia a **Supabase/PostgreSQL** antes de utilizarse con pacientes.

## Privacidad

No subas a GitHub:

- archivos `.db`
- información identificable de pacientes
- API keys
- contraseñas
- `secrets.toml`

El `.gitignore` incluido ya bloquea las ubicaciones más comunes.

## Próximos pasos sugeridos

### V0.2
- Catálogo de alimentos.
- Alimentos frecuentes.
- Recetas.
- Edición de registros.
- Mejor dashboard semanal.

### V0.3
- Múltiples pacientes.
- Login.
- Panel de nutrióloga.
- Plan vs. consumo real.
- Sistema de equivalentes.

### V0.4
- Supabase/PostgreSQL.
- Roles y autenticación.
- Persistencia real en la nube.

### V0.5
- IA para interpretar lenguaje natural.
- Confirmación antes de registrar.
- Integración con una fuente nutricional verificable.

---

**Importante:** esta aplicación es una herramienta de seguimiento y no sustituye la valoración ni el criterio profesional de una nutrióloga.
