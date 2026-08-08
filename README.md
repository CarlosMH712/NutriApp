# 🥗 Mi Nutrición — V0.2 con Supabase

Esta versión reemplaza SQLite por **Supabase/PostgreSQL**, por lo que los registros pueden persistir aunque Streamlit Community Cloud reinicie o vuelva a desplegar la app.

También incorpora un **PIN básico de acceso** almacenado en Streamlit Secrets. El PIN sirve únicamente para proteger el MVP de accesos casuales; no sustituye una autenticación individual para pacientes.

## Qué cambió respecto a V0.1

- Persistencia real en Supabase/PostgreSQL.
- SQLite eliminado del flujo de ejecución.
- Esquema SQL versionado en `supabase_schema.sql`.
- Credenciales leídas con `st.secrets`.
- PIN de acceso al MVP.
- Row Level Security habilitado sin políticas públicas.
- Uso de una Supabase **Secret key (`sb_secret_...`)** solamente desde el servidor de Streamlit; también se admite `service_role` legacy como fallback.
- Estructura preparada para añadir múltiples pacientes y autenticación en la siguiente fase.

## Estructura

```text
nutrition_streamlit_supabase/
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── app.py
├── db.py
├── supabase_schema.sql
├── requirements.txt
├── .gitignore
└── README.md
```

## 1. Crear un proyecto en Supabase

1. Crea un proyecto nuevo en Supabase.
2. Espera a que termine de inicializarse.
3. En el panel del proyecto abre **SQL Editor**.
4. Crea una consulta nueva.
5. Copia todo el contenido de `supabase_schema.sql`.
6. Ejecuta el script.

El script crea:

- `patients`
- `goals`
- `food_log`
- índice por paciente/fecha
- un paciente demo
- metas demo
- RLS en las tres tablas

## 2. Obtener las credenciales

En Supabase abre la configuración/API del proyecto y localiza:

- Project URL
- Secret key (`sb_secret_...`) recomendada por Supabase para backend

Si tu proyecto solo tiene claves legacy, también funciona con `service_role`, aunque Supabase está migrando a las Secret keys nuevas.

> **Importante:** la Secret key es una credencial privilegiada que bypassa RLS. Debe permanecer exclusivamente en Streamlit Secrets y nunca debe aparecer en GitHub, capturas, código frontend o archivos públicos.

## 3. Configuración local

Copia:

```text
.streamlit/secrets.toml.example
```

como:

```text
.streamlit/secrets.toml
```

Completa:

```toml
[app]
pin = "UN_PIN_PRIVADO"

[supabase]
url = "https://TU-PROYECTO.supabase.co"
secret_key = "sb_secret_TU_CLAVE_SECRETA"
```

`secrets.toml` está incluido en `.gitignore` y no debe subirse al repositorio.

## 4. Ejecutar localmente

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 5. Subir la nueva versión a GitHub

Si vas a reemplazar la versión anterior, copia estos archivos sobre tu repositorio y ejecuta:

```bash
git add .
git commit -m "Migrate nutrition app persistence to Supabase"
git push
```

Streamlit Community Cloud normalmente detectará el push y volverá a desplegar la app.

## 6. Configurar Secrets en Streamlit Community Cloud

En la configuración de la app desplegada abre **Secrets** y pega:

```toml
[app]
pin = "UN_PIN_PRIVADO"

[supabase]
url = "https://TU-PROYECTO.supabase.co"
secret_key = "sb_secret_TU_CLAVE_SECRETA"
```

Guarda los cambios y reinicia/redeploya la app si fuera necesario.

## 7. Prueba recomendada

1. Entra con el PIN.
2. Cambia el nombre o una meta nutricional.
3. Registra un alimento.
4. Cambia de fecha y vuelve.
5. Reinicia la app desde Streamlit Cloud.
6. Comprueba que los datos sigan presentes.
7. Revisa también las tablas desde Supabase > Table Editor.

## Seguridad del MVP

Esta versión mejora significativamente la persistencia, pero todavía **no debe considerarse un sistema clínico multiusuario**.

Actualmente:

- existe un solo paciente demo;
- todas las personas que conozcan el PIN acceden al mismo perfil;
- el servidor de Streamlit utiliza una Secret key privilegiada (o `service_role` legacy como fallback);
- RLS está habilitado y no hay políticas públicas, por lo que las tablas no quedan abiertas mediante una anon/publishable key.

Antes de utilizar expedientes reales de varios pacientes, la siguiente versión debe incorporar:

- Supabase Auth;
- usuarios individuales;
- roles `nutrióloga` / `paciente`;
- RLS por usuario;
- trazabilidad de quién puede leer/modificar cada expediente;
- política de privacidad y manejo adecuado de datos personales.

## Próxima etapa sugerida: V0.3

- Múltiples pacientes.
- Panel de la nutrióloga.
- Login real con Supabase Auth.
- Roles y permisos.
- Selección de paciente.
- Metas individuales.
- Resumen de adherencia de cada paciente.

Después de eso tiene mucho más sentido integrar catálogo de alimentos, equivalentes e IA.
