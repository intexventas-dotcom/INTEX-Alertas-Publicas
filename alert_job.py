"""Envío programado opcional de oportunidades nuevas.
Ejecute este archivo desde un programador externo (por ejemplo, GitHub Actions).
Configure los secretos SMTP_USER, SMTP_PASSWORD y ALERT_RECIPIENT.
"""
import os
import sys
import pandas as pd
from app import DEFAULT_DATA_URL, load_records, prepare_dataframe, send_email

url = os.getenv("INTEX_DATA_URL", DEFAULT_DATA_URL)
recipient = os.getenv("ALERT_RECIPIENT", "intexventas@gmail.com")
smtp_user = os.getenv("SMTP_USER", "")
smtp_password = os.getenv("SMTP_PASSWORD", "")

try:
    df = prepare_dataframe(load_records(url))
    count, message = send_email(df, recipient, smtp_user, smtp_password)
    print(message)
    print(f"Oportunidades nuevas enviadas: {count}")
    sys.exit(0 if "No se pudo" not in message else 1)
except Exception as exc:
    print(f"Error en el trabajo programado: {exc}")
    sys.exit(1)
