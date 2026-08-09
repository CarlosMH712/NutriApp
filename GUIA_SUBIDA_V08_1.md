# Guía de actualización V0.8.1

Esta corrección agrega mililitros para líquidos y asegura que el agua potable
actualice la meta diaria de hidratación, incluso cuando el catálogo tenga
`water_per_100g` en cero.

## Supabase

No ejecutes ningún SQL. La corrección utiliza el campo `water` que ya existe.

## Archivos para actualizar en GitHub

- `app.py`
- `db.py`
- `food_measurements.py` (nuevo)
- `meal_workflows.py`
- `meal_ai.py`
- `requirements.txt`
- `README.md`

Conserva los demás archivos y los Secrets sin cambios.

## Qué probar

1. Abre **Registrar > Describir comida**.
2. Escribe `Tomé 500 ml de agua`.
3. Confirma que la unidad propuesta sea **mililitros** y la cantidad sea `500`.
4. Registra el componente y abre **Mi día**.
5. La barra **Agua** debe aumentar `500 ml`.
6. Prueba también `dos tazas de agua`; deben equivaler a `480 ml`.

La versión también recupera en la vista diaria registros anteriores de agua que
tengan hidratación en cero y unidades reconocibles como ml, gramos, taza, vaso o
litro. Para otros líquidos, conserva el contenido de agua informado por el catálogo.

Para calcular nutrientes de líquidos por 100 g sin una densidad específica, la app
indica y utiliza la aproximación revisable `1 ml = 1 g`.
