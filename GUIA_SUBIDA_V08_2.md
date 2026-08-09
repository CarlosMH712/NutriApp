# Guía de actualización V0.8.2

Esta versión corrige la fecha local y evita que las gráficas pierdan su escala
cuando se usa la rueda del mouse o una pantalla táctil.

## 1. Ejecutar en Supabase

Antes de actualizar la aplicación, abre **Supabase > SQL Editor**, copia el
contenido de `supabase_v08_2_timezone_migration.sql` y ejecútalo una sola vez.

La migración conserva todos los usuarios, alimentos, metas y mediciones.

## 2. Actualizar GitHub

Sube los archivos de la V0.8.2. No subas `.streamlit/secrets.toml` y no cambies
los Secrets existentes de Supabase o Gemini.

## 3. Qué probar

1. Inicia sesión y abre **Configuración** en la barra lateral.
2. Confirma que la zona seleccionada sea **Chihuahua**.
3. Guarda la zona horaria y verifica que la fecha local sea correcta.
4. Registra una cena y confirma que se guarde en el día seleccionado.
5. Abre **Historial** y pasa el cursor sobre las gráficas para ver los valores.
6. Usa la rueda del mouse o desplázate con el dedo: la gráfica no debe cambiar
   de escala ni moverse fuera de su posición.

## Base de datos

Esta actualización sólo agrega `profiles.timezone` y una política RLS para que
cada usuario pueda actualizar exclusivamente la zona horaria de su propia cuenta.
