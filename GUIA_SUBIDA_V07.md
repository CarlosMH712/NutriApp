# Guía de actualización V0.7

La V0.7 incorpora interpretación de platillos con IA, platillos frecuentes, recetas del nutriólogo y administración de mediciones corporales.

## 1. Respaldar

Crea un respaldo del proyecto Supabase antes de aplicar la migración.

## 2. Actualizar Supabase

En **Supabase > SQL Editor**, ejecuta una vez:

```text
supabase_v07_ai_recipes_migration.sql
```

Requiere que las migraciones V0.3 a V0.6 ya estén instaladas.

## 3. Configurar OpenAI

En la plataforma de OpenAI crea una clave de proyecto. En **Streamlit Community Cloud > App settings > Secrets** agrega:

```toml
[openai]
api_key = "TU_OPENAI_API_KEY"
model = "gpt-4o-mini"
```

No pegues la clave en `app.py`, GitHub ni ningún CSV. Configura alertas y límites de gasto en el proyecto de OpenAI.

## 4. Subir el código

Actualiza en GitHub:

- `app.py`
- `db.py`
- `meal_ai.py`
- `meal_workflows.py`
- `requirements.txt`
- `README.md`
- `supabase_v07_ai_recipes_migration.sql`

No subas `.streamlit/secrets.toml`.

## 5. Probar interpretación

1. Entra como paciente y abre **Registrar > Describir comida**.
2. Escribe: `Comí una hamburguesa con lechuga y un chile verde, sin queso`.
3. Confirma que aparezcan pan, carne, lechuga y chile como componentes revisables.
4. Revisa la coincidencia, cantidad, fuente y macros de cada componente.
5. Guarda el platillo y marca **Guardar también como platillo frecuente**.
6. Regístralo nuevamente desde **Platillos guardados**.

## 6. Probar recetas del nutriólogo

1. Entra como nutriólogo y abre **Recetas**.
2. Agrega componentes del catálogo y guarda la receta.
3. Entra como paciente vinculado y verifica que aparezca en **Platillos guardados**.

## 7. Probar mediciones

1. Abre **Perfil y metas > Composición corporal**.
2. Usa **Corregir** para modificar peso o datos Tanita.
3. Usa **Eliminar** y confirma la advertencia.
4. Verifica las gráficas en **Historial > Evolución corporal**.
