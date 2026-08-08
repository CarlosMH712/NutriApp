# Guía de actualización V0.6

Esta versión incorpora acceso más rápido con el administrador de contraseñas del dispositivo, edición de alimentos y evolución corporal.

## 1. Respaldar

Antes de aplicar cambios, crea un respaldo del proyecto Supabase.

## 2. Ejecutar la migración

En **Supabase > SQL Editor**, ejecuta una vez:

```text
supabase_v06_experience_tracking_migration.sql
```

Requiere que la migración V0.5 ya esté instalada. Agrega `weight_kg` a las mediciones corporales sin borrar registros anteriores.

## 3. Subir el código

Actualiza en GitHub:

- `app.py`
- `db.py`
- `README.md`
- `supabase_v06_experience_tracking_migration.sql`

No subas `.streamlit/secrets.toml`, contraseñas ni claves de Supabase.

## 4. Verificar

1. Abre el inicio de sesión en un dispositivo personal y permite que el navegador guarde las credenciales.
2. Cierra y abre la página; confirma que el administrador de contraseñas ofrezca huella, Face ID o PIN si el dispositivo lo admite.
3. Registra un alimento, abre **Mi día** y presiona ✏️.
4. Cambia la cantidad y confirma que los macros se recalculen proporcionalmente.
5. Guarda dos mediciones corporales en fechas distintas incluyendo peso y grasa.
6. Abre **Historial > Evolución corporal** y revisa las gráficas.

## 5. Seguridad

La app no almacena la contraseña ni los datos biométricos. El acceso rápido depende del administrador de contraseñas de Safari, Chrome, iCloud Keychain, Google Password Manager u otro servicio configurado en el dispositivo.
