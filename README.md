# 🥗 Mi Nutrición — V0.8.1 registro inteligente con Gemini

Aplicación Streamlit multiusuario para registrar alimentos y seguir metas nutricionales. Usa Supabase Auth, PostgreSQL y Row Level Security (RLS) para aislar los datos de cada paciente.

## Funciones incluidas

- Registro e inicio de sesión con correo y contraseña.
- Autocompletado compatible con el administrador de contraseñas y biometría del dispositivo.
- Roles de paciente y nutriólogo.
- Expediente, metas y alimentos independientes por paciente.
- Vinculación mediante un código compartido por el nutriólogo.
- Panel profesional para revisar historial y ajustar metas.
- Catálogo privado creado o importado por cada nutriólogo.
- Búsqueda opcional en USDA FoodData Central.
- Cálculo automático de macros por gramos o porción casera.
- Porciones del SMAE expresadas como taza, pieza, cucharada, onza, envase u otra medida disponible.
- Registro de líquidos en mililitros y actualización automática de hidratación para agua potable.
- Calculadora editable de gasto en reposo y metas diarias para adultos.
- Registro histórico opcional de IMC, grasa, músculo, calorías basales, grasa visceral y edad metabólica.
- Evolución gráfica de peso, grasa, músculo, IMC y grasa visceral.
- Edición de alimentos registrados con recálculo proporcional por cantidad.
- Interpretación con IA de descripciones de comidas y desglose de platillos compuestos.
- Revisión obligatoria de cada coincidencia antes de registrar nutrientes.
- Platillos frecuentes del paciente y recetas compartidas por el nutriólogo.
- Corrección y eliminación confirmada de mediciones corporales.
- Registro manual disponible cuando el alimento no existe en el catálogo.
- Trazabilidad de la fuente e identificador de cada alimento registrado.

## 1. Actualizar la base de datos

### Proyecto que ya tiene V0.6

En Supabase **SQL Editor**, copia y ejecuta una sola vez:

```text
supabase_v07_ai_recipes_migration.sql
```

La migración crea `meal_templates` y `meal_template_items` con RLS. Conserva pacientes, mediciones, catálogo y registros existentes.

### Instalación nueva

Ejecuta en este orden:

1. `supabase_schema.sql`
2. `supabase_v04_catalog_migration.sql`
3. `supabase_v05_measurements_goals_migration.sql`
4. `supabase_v06_experience_tracking_migration.sql`
5. `supabase_v07_ai_recipes_migration.sql`

## 2. Configurar Supabase Auth

En Supabase abre **Authentication**:

1. Verifica que el proveedor **Email** esté habilitado.
2. Se recomienda conservar **Confirm email** habilitado.
3. En **URL Configuration**, usa la URL pública de Streamlit como `Site URL`.
4. Agrega `https://tu-app.streamlit.app/**` en **Redirect URLs**.

Para desarrollo local también puedes permitir `http://localhost:8501/**`.

## 3. Configurar Secrets

```toml
[supabase]
url = "https://TU-PROYECTO.supabase.co"
publishable_key = "sb_publishable_TU_CLAVE_PUBLICA"
```

Para habilitar la búsqueda de alimentos de USDA, solicita una API key en `https://fdc.nal.usda.gov/api-key-signup/` y agrega:

```toml
[food_data_central]
api_key = "TU_API_KEY"
```

Para habilitar la interpretación de platillos crea una clave en Google AI Studio y agrega:

```toml
[gemini]
api_key = "TU_GEMINI_API_KEY"
model = "gemini-3.5-flash-lite"
```

Pega esta configuración en:

- local: `.streamlit/secrets.toml`;
- Streamlit Community Cloud: **App settings > Secrets**.

`secrets.toml` está excluido por `.gitignore` y nunca debe subirse a GitHub.

La descripción de la comida se envía a la API sólo cuando el usuario presiona
**Interpretar platillo**. No se envía nombre, correo, identificador de usuario ni
expediente; la solicitud usa `store=False`. En el nivel gratuito, Google indica que
el contenido puede utilizarse para mejorar sus productos. Por eso la interfaz pide
no escribir nombres, diagnósticos ni otros datos personales.

## 4. Crear la cuenta del nutriólogo

Las cuentas nuevas se crean como pacientes. Después de registrar y confirmar el correo profesional, ejecuta en SQL Editor:

```sql
select public.promote_user_to_nutritionist('nutriologa@ejemplo.com');
```

El resultado es el código que el nutriólogo comparte con sus pacientes.

## 5. Administrar el catálogo

El nutriólogo encontrará **Catálogo** en la barra lateral. Puede:

- crear un alimento con valores por 100 g;
- definir una porción casera y sus gramos;
- importar hasta 2000 filas desde CSV;
- consultar y eliminar sus propios alimentos.

La pantalla de importación incluye una plantilla descargable. Columnas:

```text
name,brand,calories_per_100g,protein_per_100g,carbs_per_100g,
fat_per_100g,fiber_per_100g,water_per_100g,portion_name,
portion_grams,source,external_id
```

Los alimentos creados por un nutriólogo sólo son visibles para esa cuenta y sus pacientes vinculados.

## 6. Fuentes de datos

- **FoodData Central:** búsqueda externa opcional. Datos CC0/dominio público. La app conserva el `fdcId`.
- **INCMNSZ/CONABIO:** puede importarse desde CSV después de confirmar sus condiciones de reutilización y citación.
- **SMAE:** no se incluye ni redistribuye. Requiere autorización o licencia para copiar su base comercial.
- **Sistema Digital de Alimentos:** útil como referencia de equivalentes, pero el sitio indica “todos los derechos reservados”; no se integra por extracción automática sin autorización escrita.
- **Datos profesionales:** el nutriólogo puede cargar valores propios y queda identificado como fuente.

La aplicación no genera valores nutrimentales con IA. Calcula a partir de una fuente identificada y muestra el resultado antes de guardarlo.

## 7. Cálculo de metas y composición corporal

- El IMC se calcula como peso en kg dividido entre estatura en metros al cuadrado.
- Para adultos, la calculadora puede estimar el gasto energético en reposo con Mifflin-St Jeor.
- Si existe una medición Tanita/Omron con calorías basales, el nutriólogo puede usar ese valor como alternativa.
- El factor de actividad, ajuste calórico, distribución de macros y agua orientativa son editables.
- La fibra inicial se estima a razón de 14 g por cada 1000 kcal.
- Ninguna estimación se guarda hasta que el usuario autorizado la aplique y confirme.

Referencias técnicas:

- https://pubmed.ncbi.nlm.nih.gov/2305711/
- https://www.andeal.org/template.cfm?auth=1&key=621&template=guide_summary
- https://www.ncbi.nlm.nih.gov/mesh/68015992
- https://pubmed.ncbi.nlm.nih.gov/26514720/

Estas fórmulas son estimaciones para adultos y no sustituyen la evaluación profesional ni la calorimetría indirecta.

## 8. Flujo del paciente

1. Crear y confirmar su cuenta.
2. Vincularse con el código del nutriólogo.
3. Abrir **Registrar > Desde catálogo**.
4. Buscar y seleccionar el alimento.
5. Elegir gramos o una porción disponible.
6. Revisar el cálculo y confirmar.
7. Consultar avances en **Mi día** e **Historial**.
8. Usar el botón ✏️ para corregir un registro sin eliminarlo.
9. Registrar peso y composición corporal para construir las gráficas de evolución.
10. Opcionalmente describir un platillo, revisar sus componentes y confirmarlo.
11. Guardar la combinación confirmada como platillo frecuente.

## 9. Registro inteligente y recetas

- La IA extrae componentes, cantidades, preparación y preguntas pendientes.
- Nunca genera valores nutrimentales: cada componente debe vincularse a SMAE,
  CONABIO, USDA o al catálogo profesional.
- Si no existe una coincidencia, el componente no puede guardarse hasta que el
  usuario seleccione otra o lo excluya.
- Los platillos frecuentes conservan los valores y fuentes que el paciente confirmó.
- Las recetas del nutriólogo están disponibles para todos sus pacientes vinculados.
- Una receta puede registrarse en 0.25, 0.5, 1 o más porciones.

## 10. Ejecutar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m streamlit run app.py
```

## 11. Desplegar

Sube el código a GitHub sin `secrets.toml`. Streamlit Community Cloud actualizará la app desde el repositorio. Después verifica que **App settings > Secrets** incluya la configuración de Supabase, Gemini y, opcionalmente, FoodData Central.

## Pruebas recomendadas

1. Ejecuta la migración V0.4.
2. Crea un alimento desde la cuenta del nutriólogo.
3. Confirma que un paciente vinculado pueda encontrarlo.
4. Confirma que otro paciente no vinculado no pueda verlo.
5. Registra 150 g y verifica que los valores correspondan a 1.5 veces los valores por 100 g.
6. Configura FoodData Central y prueba una búsqueda externa.
7. Verifica que los registros manuales anteriores sigan visibles.

## Alcance y privacidad

RLS y Auth mejoran el aislamiento técnico, pero una aplicación que almacena datos personales o clínicos también requiere aviso de privacidad, consentimiento, control administrativo, respaldos y análisis legal acorde con el país donde opere.
