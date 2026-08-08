# 🥗 Mi Nutrición — V0.3 multiusuario

Aplicación Streamlit para que cada paciente registre sus alimentos y dé seguimiento a sus macros. Usa Supabase Auth para cuentas individuales y PostgreSQL con Row Level Security (RLS) para aislar los datos.

## Funciones incluidas

- Registro e inicio de sesión con correo y contraseña.
- Expediente, metas y alimentos independientes por paciente.
- Vinculación mediante un código compartido por el nutriólogo.
- Panel del nutriólogo para consultar pacientes, revisar historial y ajustar metas.
- Los pacientes registran y eliminan únicamente sus propios alimentos.
- Un nutriólogo sólo puede consultar pacientes vinculados con su cuenta.
- Las operaciones normales usan una Publishable key y el JWT del usuario; no usan una Secret key que omita RLS.

## 1. Actualizar la base de datos

Antes de desplegar esta versión:

1. Abre tu proyecto en Supabase.
2. Entra a **SQL Editor**.
3. Crea una consulta nueva.
4. Copia todo `supabase_schema.sql`.
5. Pulsa **Run** una sola vez.

El script conserva las tablas y registros de V0.2, y añade:

- `profiles`;
- `nutritionist_patients`;
- creación automática del expediente al registrar una cuenta;
- roles `patient` y `nutritionist`;
- funciones de vinculación;
- políticas RLS para las cinco tablas.

## 2. Configurar Supabase Auth

En Supabase abre **Authentication**:

1. Verifica que el proveedor **Email** esté habilitado.
2. Se recomienda conservar **Confirm email** habilitado.
3. En **URL Configuration**, coloca la URL pública de tu app Streamlit como `Site URL`, por ejemplo `https://tu-app.streamlit.app`.

Si todavía trabajas sólo en local, puedes usar temporalmente `http://localhost:8501` como `Site URL`.

## 3. Cambiar los Secrets de Streamlit

V0.3 ya no utiliza el PIN compartido ni `sb_secret_...`. Usa la Project URL y una Publishable key desde Supabase **Connect** o **Settings > API Keys**:

```toml
[supabase]
url = "https://TU-PROYECTO.supabase.co"
publishable_key = "sb_publishable_TU_CLAVE_PUBLICA"
```

Pega lo mismo en:

- local: `.streamlit/secrets.toml`;
- Streamlit Community Cloud: **App settings > Secrets**.

`secrets.toml` está excluido por `.gitignore` y nunca debe subirse a GitHub.

## 4. Crear la cuenta del nutriólogo

Todas las cuentas nuevas nacen como pacientes para evitar que alguien se asigne privilegios profesionales.

1. Despliega o ejecuta la app.
2. En **Crear cuenta**, registra el correo que usará el nutriólogo.
3. Confirma el correo si Supabase lo solicita.
4. En Supabase **SQL Editor**, ejecuta sustituyendo el correo:

```sql
select public.promote_user_to_nutritionist('nutriologa@ejemplo.com');
```

El resultado es el código que el nutriólogo podrá compartir con sus pacientes. También aparecerá en la barra lateral de su app.

## 5. Flujo del paciente

1. El paciente abre la app y crea su cuenta.
2. Confirma su correo e inicia sesión.
3. Completa su perfil.
4. Abre **Mi nutriólogo** e introduce el código recibido.
5. Registra alimentos en **Registrar**.
6. Consulta sus avances en **Mi día** e **Historial**.

Cuando el paciente todavía no está vinculado, puede ajustar sus propias metas. Después de vincularse, las metas quedan a cargo del nutriólogo.

## 6. Conservar el paciente de prueba V0.2 (opcional)

El registro heredado `11111111-1111-1111-1111-111111111111` no pertenece automáticamente a una cuenta Auth. Para asociarlo a una cuenta de paciente ya creada, ejecuta en SQL Editor:

```sql
select public.attach_legacy_patient(
    'paciente@ejemplo.com',
    '11111111-1111-1111-1111-111111111111'
);
```

No ejecutes esto con la cuenta del nutriólogo.

## 7. Ejecutar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m streamlit run app.py
```

La app queda disponible en `http://localhost:8501`.

## 8. Desplegar

Sube el código a GitHub sin `secrets.toml`. Streamlit Community Cloud actualizará la app desde el repositorio. Después revisa **App settings > Secrets** y sustituye la configuración anterior por la Publishable key.

## Pruebas recomendadas

1. Crea una cuenta de nutriólogo y promuévela mediante SQL.
2. Crea dos cuentas de paciente con correos diferentes.
3. Vincula sólo una de ellas al nutriólogo.
4. Registra alimentos con ambas cuentas.
5. Confirma que cada paciente sólo vea sus propios registros.
6. Confirma que el nutriólogo sólo vea al paciente vinculado.
7. Ajusta las metas desde el panel profesional y verifica que el paciente las vea sin poder modificarlas.

## Alcance y privacidad

RLS y Auth mejoran el aislamiento técnico, pero una aplicación que almacena datos personales o clínicos también requiere aviso de privacidad, consentimiento, control de acceso administrativo, respaldos y un análisis legal acorde con el país donde opere.
