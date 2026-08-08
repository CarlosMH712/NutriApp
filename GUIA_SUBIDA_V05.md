# Guía de actualización V0.5

Esta actualización incorpora medidas caseras del SMAE, cálculo editable de metas y composición corporal opcional.

## 1. Respaldar

Antes de aplicar cambios, crea un respaldo del proyecto Supabase y conserva los CSV originales fuera de GitHub.

## 2. Actualizar Supabase

En **Supabase > SQL Editor**, ejecuta una vez:

```text
supabase_v05_measurements_goals_migration.sql
```

El script conserva la información existente y agrega:

- `patients.activity_level`;
- parámetros de cálculo en `goals`;
- tabla `body_measurements`;
- permisos y políticas RLS para paciente y nutriólogo vinculado.

## 3. Subir el código a GitHub

Sube estos archivos actualizados:

- `app.py`
- `db.py`
- `nutrition_calculations.py`
- `supabase_v05_measurements_goals_migration.sql`
- `README.md`
- `tests/test_nutrition_calculations.py`

No subas `.streamlit/secrets.toml`, contraseñas, claves de Supabase ni datos identificables de pacientes.

## 4. Actualizar Streamlit

Si Streamlit Community Cloud está conectado al repositorio, desplegará el cambio después de actualizar GitHub. Confirma que los Secrets sigan configurados.

## 5. Importar el catálogo

Desde la cuenta de nutriólogo abre **Catálogo > Importar CSV**.

1. Importa `Catalogo_CONABIO_importable.csv` si todavía no está cargado.
2. Importa `Catalogo_SMAE_importable_parte_1.csv`.
3. Importa `Catalogo_SMAE_importable_parte_2.csv`.

La app admite hasta 2000 alimentos por archivo. El SMAE ya fue dividido en dos partes.

Los alimentos del SMAE incluyen una medida casera cuando la fuente proporciona una equivalencia confiable. En la app, el paciente podrá seleccionar gramos o la unidad disponible y capturar cantidades como 1, 0.5 o 0.25.

Antes de cargar o redistribuir SMAE, confirma que el uso está cubierto por la licencia o autorización correspondiente. No extraigas en bloque datos de https://sistemadigitaldealimentos.org/ sin permiso escrito; el sitio indica “todos los derechos reservados”.

## 6. Verificación funcional

1. Busca un alimento como huevo, pan o fruta.
2. Confirma que aparezca una medida como pieza, taza o cucharada cuando esté disponible.
3. Registra 0.5 unidades y verifica que los gramos y macros sean la mitad de una unidad.
4. Abre **Perfil y metas > Composición corporal** y guarda una medición de prueba.
5. Abre **Metas nutricionales**, revisa el cálculo automático y aplícalo.
6. Edita manualmente una meta y confirma que el nutriólogo conserva el control final.

## 7. Alcance clínico

La calculadora usa Mifflin-St Jeor sólo para adultos con sexo femenino o masculino seleccionado. Es una estimación; la medición profesional, la calorimetría indirecta y el criterio clínico tienen prioridad.
