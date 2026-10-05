# INTEX Alertas Públicas 🇭🇳🧵

Aplicación para detectar oportunidades de contratación pública de Honduras relacionadas con:

- Uniformes empresariales y escolares
- Camisas, pantalones y polos
- Ropa de trabajo
- Confección y textiles
- Bordado y serigrafía
- Gabachas, batas, overoles y chalecos
- Gorras, delantales, mandiles
- Tela y productos textiles
- Elementos relacionados como banderas/bufandas

## 1. Instalar

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Probar el tablero

```bash
streamlit run app.py
```

Abra la dirección que muestra Streamlit.

## 3. Configurar las alertas por Gmail

La cuenta destinataria está preparada como:

`intexventas@gmail.com`

Para enviar correo desde Gmail, cree una contraseña de aplicación de Google y configure:

```text
SMTP_USER=intexventas@gmail.com
SMTP_PASSWORD=SU_APP_PASSWORD
ALERT_EMAIL=intexventas@gmail.com
```

No use la contraseña normal de Gmail.

## 4. Ejecutar alertas automáticamente

En Windows puede programar:

```bash
python alert_job.py
```

una vez al día mediante el Programador de tareas.

En Linux/servidor, por ejemplo:

```cron
0 7 * * * cd /ruta/INTEX_Alertas_Publicas && /ruta/.venv/bin/python alert_job.py
```

## 5. Fuente de datos

La aplicación utiliza datos abiertos de contratación pública de Honduras publicados por ONCAE/OCDS. El archivo 2026 se configura por defecto en `DATA_URL`.

Al comenzar un nuevo año, actualice `DATA_URL` con el archivo anual vigente.

## 6. Cómo funciona el filtro INTEX

Cada proceso recibe un puntaje según las palabras encontradas en título, descripción, artículos, comprador y modalidad.

- ALTA: 24 puntos o más
- MEDIA: 12 a 23
- BAJA: menos de 12

El sistema guarda en SQLite los procesos ya enviados para evitar correos duplicados.

## 7. Recomendación de uso

La alerta sirve para detectar oportunidades; antes de presentar una oferta, INTEX debe revisar el pliego, requisitos, fecha límite, garantías, condiciones de entrega, impuestos y requisitos de proveedor en la plataforma oficial.

## Próxima versión recomendada

Agregar:
1. búsqueda de PACC para detectar compras planificadas antes de la licitación;
2. clasificación por institución;
3. estimación de volumen (unidades/tela cuando los datos lo permitan);
4. semáforo de días restantes;
5. botón “Me interesa” y seguimiento comercial;
6. alerta inmediata para procesos de relevancia ALTA.
