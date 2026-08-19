# Guía de actualización V0.9

Esta versión corrige el catálogo que sólo mostraba los alimentos con A, permite
varias medidas caseras por alimento, agrega el registro de actividad física y
habilita que el nutriólogo lleve su propio seguimiento sin una segunda cuenta.

## 1. Ejecutar en Supabase

Antes de actualizar la aplicación, abre **Supabase > SQL Editor**, copia el
contenido de `supabase_v09_portions_activity_selftracking_migration.sql` y
ejecútalo una sola vez.

La migración conserva pacientes, alimentos, metas, mediciones y registros. Las
porciones que ya tenías capturadas se copian solas a la nueva tabla.

### 1.1 Recuperar el expediente del nutriólogo

Las cuentas promovidas con la versión anterior perdieron el vínculo con su
expediente. En el mismo SQL Editor ejecuta:

```sql
select public.repair_nutritionist_self_tracking();
```

Devuelve cuántas cuentas quedaron reparadas. El expediente nunca se borró, sólo
se había dejado de apuntar, así que no se pierde nada.

### 1.2 Unir la cuenta adicional de la nutrióloga

Si llevaba su propio seguimiento en otra cuenta, mueve ese historial a su cuenta
principal:

```sql
select public.merge_patient_records('cuenta.extra@ejemplo.com',
                                    'nutriologa@ejemplo.com');
```

Devuelve un resumen de cuántos alimentos, mediciones, días de actividad y
ejercicios se movieron. Si ambas cuentas tienen actividad el mismo día, se
conserva la del destino.

Después de verificar que todo aparezca en la cuenta principal, puedes eliminar la
cuenta extra desde **Authentication > Users**.

## 2. Actualizar GitHub

Sube los archivos de la V0.9. No subas `.streamlit/secrets.toml` y no cambies los
Secrets existentes de Supabase, Gemini o FoodData Central.

Esta versión sube el mínimo de Streamlit a 1.50 porque reemplaza
`use_container_width`, que Streamlit retiró después del 31 de diciembre de 2025.

## 3. Qué probar

### Catálogo completo

1. Entra como nutriólogo y abre **Catálogo > Mis alimentos**.
2. Confirma que el contador muestre el total real, no 1000.
3. Escribe "zanahoria" en el buscador y verifica que aparezca.
4. Avanza a la última página y confirma que se vean alimentos con Z.

### Varias medidas por alimento

1. Abre un alimento en **Mis alimentos**.
2. Agrega la medida `taza` con sus gramos equivalentes.
3. Agrega también `pieza` con sus gramos.
4. Como paciente, registra ese alimento y confirma que el selector de unidad
   ofrezca gramos, taza y pieza.
5. Registra 2 tazas y verifica que los gramos correspondan al doble.

### Líquidos

1. En un alimento líquido cuyo nombre no diga agua, leche ni jugo, marca
   **Es un líquido**.
2. Confirma que al registrarlo aparezca la opción de mililitros.

### Días pasados

1. Como paciente, abre **Registrar**.
2. Confirma que la fecha y los botones Hoy y Ayer se vean en la página, sin
   abrir la barra lateral.
3. Presiona **Ayer**, registra un alimento y verifica en **Mi día** que quedó
   guardado en la fecha correcta.

### Actividad física

1. En **Registrar > Actividad**, captura pasos y calorías activas.
2. Agrega un ejercicio con duración e intensidad.
3. Abre **Historial > Actividad** y confirma que aparezcan las gráficas.
4. Opcional: en el iPhone, **Salud > foto de perfil > Exportar todos los datos**
   y sube el ZIP en la pestaña **Importar de Salud**.

### Autoseguimiento del nutriólogo

1. Entra con la cuenta de la nutrióloga.
2. En la barra lateral, el selector **Expediente** debe ofrecer
   **👤 Mi propio seguimiento**.
3. Al elegirlo, debe aparecer la pantalla **➕ Registrar**.
4. Registra un alimento y confirma que se guarde en su propio expediente y no en
   el de ningún paciente.
5. Cambia a un paciente y confirma que **Registrar** desaparece: el registro de
   alimentos lo hace el paciente.

### Interpretación de platillos

1. En **Registrar > Describir comida**, escribe "una hamburguesa".
2. Confirma que aparezcan pan y carne como componentes.
3. Verifica que la carne ofrezca coincidencias de res y no sólo de cerdo.

## Base de datos

Esta actualización agrega:

- `food_catalog.is_liquid` y la tabla `food_catalog_portions`.
- Las tablas `activity_days` y `exercise_log`, con sus políticas RLS.
- Las funciones `add_catalog_portion`, `delete_catalog_portion`,
  `set_catalog_food_liquid`, `repair_nutritionist_self_tracking` y
  `merge_patient_records`.
- Una corrección a `promote_user_to_nutritionist` para que conserve el
  expediente propio de la cuenta.

## Privacidad

El archivo de exportación de Salud se procesa en el momento de subirlo y no se
almacena. Sólo se leen pasos, calorías activas, distancia y entrenamientos; el
resto del archivo se ignora. Los datos de actividad quedan protegidos por las
mismas políticas RLS que el resto del expediente: cada paciente ve únicamente
los suyos y su nutriólogo vinculado.
