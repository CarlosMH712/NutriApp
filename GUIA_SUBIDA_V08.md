# Guía de actualización V0.8

La V0.8 cambia el proveedor de interpretación de platillos de OpenAI a Gemini.
Conserva el catálogo, platillos frecuentes, recetas, registros y mediciones de V0.7.

## 1. Supabase

Esta actualización no crea tablas nuevas. Si ya ejecutaste
`supabase_v07_ai_recipes_migration.sql`, no ejecutes ningún SQL adicional.

## 2. Crear la clave gratuita de Gemini

1. Abre `https://aistudio.google.com/apikey` e inicia sesión con Google.
2. Pulsa **Create API key**.
3. Copia la nueva clave y guárdala como contraseña.
4. No la pegues en GitHub, `app.py`, documentos ni archivos CSV.

## 3. Actualizar los Secrets de Streamlit

En **Streamlit Community Cloud > App settings > Secrets**, elimina el bloque
`[openai]` anterior y agrega:

```toml
[gemini]
api_key = "TU_GEMINI_API_KEY"
model = "gemini-3.5-flash-lite"
```

Conserva sin cambios los bloques `[supabase]` y `[food_data_central]` que ya tengas.

## 4. Subir el código

Actualiza en GitHub:

- `app.py`
- `db.py`
- `food_sources.py`
- `meal_ai.py`
- `meal_workflows.py`
- `nutrition_calculations.py`
- `requirements.txt`
- `README.md`

No subas `.streamlit/secrets.toml`.

## 5. Probar Gemini

1. Espera a que Streamlit termine de instalar `google-genai` y reinicie la app.
2. Entra como paciente y abre **Registrar > Describir comida**.
3. Escribe: `Comí una hamburguesa con lechuga y chile verde, sin queso`.
4. Pulsa **Interpretar platillo**.
5. Confirma que aparezcan componentes revisables y coincidencias del catálogo.
6. Corrige cantidades o equivalencias antes de registrar.

La IA nunca aporta calorías ni macronutrientes. Esos valores continúan saliendo
del catálogo y requieren confirmación del usuario.

## 6. Privacidad y límites gratuitos

Sólo se envía a Gemini la descripción escrita al pulsar **Interpretar platillo**;
no se envían el correo, el nombre, el expediente ni el identificador de la cuenta.
El usuario debe evitar incluir diagnósticos u otros datos personales.

El nivel gratuito tiene límites de solicitudes y Google indica que su contenido
puede utilizarse para mejorar productos. Si se agota la cuota, el registro manual,
las recetas y los platillos frecuentes continúan funcionando normalmente.
