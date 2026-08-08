# 🥗 Mi Nutrición — V0.4 catálogo de alimentos

Aplicación Streamlit multiusuario para registrar alimentos y seguir metas nutricionales. Usa Supabase Auth, PostgreSQL y Row Level Security (RLS) para aislar los datos de cada paciente.

## Funciones incluidas

- Registro e inicio de sesión con correo y contraseña.
- Roles de paciente y nutriólogo.
- Expediente, metas y alimentos independientes por paciente.
- Vinculación mediante un código compartido por el nutriólogo.
- Panel profesional para revisar historial y ajustar metas.
- Catálogo privado creado o importado por cada nutriólogo.
- Búsqueda opcional en USDA FoodData Central.
- Cálculo automático de macros por gramos o porción casera.
- Registro manual disponible cuando el alimento no existe en el catálogo.
- Trazabilidad de la fuente e identificador de cada alimento registrado.

## 1. Actualizar la base de datos

### Proyecto que ya tiene V0.3

En Supabase **SQL Editor**, copia y ejecuta una sola vez:

```text
supabase_v04_catalog_migration.sql
```

La migración crea `food_catalog`, agrega trazabilidad a `food_log` y configura funciones/RLS. Conserva los pacientes y registros existentes.

### Instalación nueva

Ejecuta en este orden:

1. `supabase_schema.sql`
2. `supabase_v04_catalog_migration.sql`

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

Pega esta configuración en:

- local: `.streamlit/secrets.toml`;
- Streamlit Community Cloud: **App settings > Secrets**.

`secrets.toml` está excluido por `.gitignore` y nunca debe subirse a GitHub.

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
- **Datos profesionales:** el nutriólogo puede cargar valores propios y queda identificado como fuente.

La aplicación no genera valores nutrimentales con IA. Calcula a partir de una fuente identificada y muestra el resultado antes de guardarlo.

## 7. Flujo del paciente

1. Crear y confirmar su cuenta.
2. Vincularse con el código del nutriólogo.
3. Abrir **Registrar > Desde catálogo**.
4. Buscar y seleccionar el alimento.
5. Elegir gramos o una porción disponible.
6. Revisar el cálculo y confirmar.
7. Consultar avances en **Mi día** e **Historial**.

## 8. Ejecutar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m streamlit run app.py
```

## 9. Desplegar

Sube el código a GitHub sin `secrets.toml`. Streamlit Community Cloud actualizará la app desde el repositorio. Después verifica que **App settings > Secrets** incluya la configuración de Supabase y, opcionalmente, FoodData Central.

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
