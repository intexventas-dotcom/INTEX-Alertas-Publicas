# INTEX Alertas Públicas V2

Aplicación Streamlit para filtrar oportunidades de contratación pública en Honduras relacionadas con textiles, uniformes y confección.

## Funciones V2
- Puntaje de relevancia de 0 a 100.
- Prioridades MUY ALTA, ALTA, MEDIA y BAJA.
- Filtros por institución, prioridad, texto y vencimiento.
- Fecha límite, días restantes y razón de coincidencia.
- Descarga de resultados CSV.
- Envío manual de oportunidades nuevas por correo.
- `alert_job.py` para ejecutar el envío mediante un programador externo.

## Ejecutar en local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Actualizar el repositorio GitHub / Streamlit
1. Descargue y extraiga el ZIP.
2. En el repositorio `INTEX-Alertas-Publicas`, reemplace `app.py`, `alert_job.py`, `requirements.txt`, `.env.example` y `README.md`.
3. Haga commit de los cambios.
4. Streamlit Community Cloud normalmente detectará el cambio y reiniciará la aplicación.
5. Abra la aplicación y confirme que aparece “INTEX Alertas Públicas V2”.

## Configurar Gmail de forma segura
1. Active la verificación en dos pasos en la cuenta emisora de Google.
2. Genere una contraseña de aplicación desde la configuración de seguridad de Google.
3. En Streamlit Cloud, abra la configuración de la aplicación y agregue en **Secrets**:
```toml
SMTP_USER = "intexventas@gmail.com"
SMTP_PASSWORD = "SU_CONTRASENA_DE_APLICACION"
```
4. No publique ni comparta la contraseña en GitHub o en el chat.
5. En la app, escriba el destinatario y presione “Enviar oportunidades nuevas por correo”.

## Envío automático diario
Streamlit Community Cloud no garantiza ejecutar un script todos los días por sí solo. Para alertas automáticas, configure un programador externo como GitHub Actions y añada los secretos SMTP requeridos. El envío automático usa una base SQLite local para evitar repetir alertas; en entornos efímeros conviene cambiarla por una base de datos persistente.

## Importante
La fuente de datos por defecto es un archivo público de contrataciones en formato JSONL/GZIP. Si la dirección deja de funcionar o el año cambia, actualice la URL desde la barra lateral. Siempre confirme la licitación y sus documentos en el portal oficial antes de presentar una oferta.
