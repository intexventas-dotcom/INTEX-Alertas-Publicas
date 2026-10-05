"""
Ejecuta este archivo una vez al día para enviar las alertas nuevas.
Variables necesarias:
  SMTP_USER=intexventas@gmail.com
  SMTP_PASSWORD=contraseña_de_aplicación_de_Gmail
  ALERT_EMAIL=intexventas@gmail.com

Opcional:
  DATA_URL=URL del archivo JSONL.GZ de ONCAE/OCP
"""
import os
import pandas as pd
from app import load_records, send_new_alerts

recipient = os.getenv("ALERT_EMAIL", "intexventas@gmail.com")
data_url = os.getenv(
    "DATA_URL",
    "https://fastly.data.open-contracting.org/downloads/honduras_oncae/4176/2026.jsonl.gz"
)

df = load_records(data_url)
count, msg = send_new_alerts(df, recipient)
print(msg)
print(f"Alertas enviadas: {count}")
