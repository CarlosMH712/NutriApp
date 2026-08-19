# Guía de actualización V0.10

Esta versión corrige la búsqueda que ignoraba los alimentos con acento, agrega
la recuperación de contraseña, el panel de pacientes, el resumen semanal, la
exportación del expediente, la densidad para líquidos y un límite de uso de la
IA.

## 1. Ejecutar en Supabase

Abre **Supabase > SQL Editor**, copia el contenido de
`supabase_v10_search_dashboard_migration.sql` y ejecútalo una sola vez.

Conserva pacientes, alimentos, metas, mediciones, actividad y registros.

La migración instala las extensiones `unaccent` y `pg_trgm`. Ambas vienen
disponibles en Supabase; si el proyecto las tiene restringidas, el editor
mostrará un error de permisos y hay que habilitarlas desde
**Database > Extensions**.

## 2. Verificar la columna de búsqueda

La columna `food_catalog.name_search` se calcula sola a partir del nombre. Para
comprobar que quedó bien:

```sql
select name, name_search
from public.food_catalog
where name ilike '%á%'
limit 5;
```

Debe verse el nombre original con acentos y su versión sin ellos.

## 3. Configurar el correo de recuperación

En **Supabase > Authentication > URL Configuration**, confirma que `Site URL`
sea la URL pública de Streamlit y que esté en **Redirect URLs**. Sin eso, el
enlace del correo de recuperación no regresa a la aplicación.

La plantilla del correo se ajusta en **Authentication > Emails > Reset password**.

## 4. Actualizar GitHub

Sube los archivos de la V0.10. No subas `.streamlit/secrets.toml`.

Esta versión agrega `.streamlit/config.toml` con el tema verde, que existía en
la carpeta de trabajo pero nunca se había subido: la aplicación desplegada
estaba usando el tema por omisión de Streamlit.

## 5. Qué probar

### Búsqueda sin acentos

1. En **Catálogo > Mis alimentos**, escribe `platano` sin acento.
2. Debe aparecer *Plátano* y sus variantes.
3. Prueba también `pina` y `azucar`.

### Recuperación de contraseña

1. Cierra sesión y abre la pestaña **Olvidé mi contraseña**.
2. Escribe un correo registrado y envía. Debe llegar el enlace.
3. Prueba con un correo inexistente: el mensaje debe ser **el mismo**, para no
   revelar qué cuentas existen.
4. Abre el enlace, entra y cambia la contraseña en **⚙️ Configuración**.

### Panel de pacientes

1. Entra como nutrióloga. La primera pantalla es **👥 Panel**.
2. Verifica el semáforo por paciente y la lista **Conviene contactar**.
3. Cambia el periodo a 14 y 30 días.

### Resumen semanal y exportación

1. Como paciente, abre **Historial > Resumen**.
2. Revisa adherencia y días registrados.
3. Presiona **Redactar resumen de la semana**.
4. Presiona **Preparar descarga** y baja el ZIP con los CSV.

### Densidad

1. En el catálogo, marca un aceite como líquido y captura densidad `0.92`.
2. Registra 100 ml y confirma que equivalga a 92 g, no a 100 g.

### Límite de la IA

1. El límite es de 30 interpretaciones por paciente y día.
2. A partir de la interpretación 26 aparece el aviso de cuántas quedan.

## 6. Base de datos

Esta actualización agrega:

- La extensión `unaccent`, la función `immutable_unaccent`, la columna generada
  `food_catalog.name_search` y su índice trigram.
- `food_catalog.density_g_per_ml` y la función `set_catalog_food_density`.
- La función `nutritionist_patient_summary`, que arma el panel en una sola
  consulta en vez de una por paciente.
- La tabla `ai_usage` y la función `register_ai_interpretation`.

## 7. Lo que quedó pendiente

- **Recordatorios automáticos.** Streamlit Cloud se apaga cuando nadie usa la
  aplicación, así que necesitan `pg_cron` más una Edge Function y una cuenta de
  envío de correo.
- **Aviso de privacidad y consentimiento.** Sigue siendo el punto con más
  riesgo para operar con pacientes reales.
- **Pruebas automatizadas de las políticas RLS.** Requieren un proyecto de
  Supabase de prueba con credenciales dedicadas.
