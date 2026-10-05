import os
import re
import json
import gzip
import sqlite3
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import requests
import streamlit as st

APP_NAME = "INTEX Alertas Públicas"
DEFAULT_EMAIL = "intexventas@gmail.com"
DEFAULT_DATA_URL = os.getenv(
    "DATA_URL",
    "https://fastly.data.open-contracting.org/downloads/honduras_oncae/4176/2026.jsonl.gz"
)
DB_PATH = os.getenv("DB_PATH", "intex_alertas.db")

KEYWORDS = {
    "uniforme": 12, "uniformes": 12, "textil": 12, "textiles": 12,
    "confeccion": 11, "confección": 11, "vestuario": 10, "ropa": 9,
    "camisa": 9, "camisas": 9, "pantalon": 9, "pantalón": 9,
    "pantalones": 9, "polo": 8, "camiseta": 8, "chaqueta": 8,
    "gabacha": 9, "bata": 8, "overol": 9, "overoles": 9,
    "chaleco": 8, "delantal": 8, "mandil": 8, "gorro": 6, "gorra": 8,
    "gorras": 8, "bordado": 7, "bordados": 7, "serigrafia": 7,
    "serigrafía": 7, "dryfit": 8, "dry fit": 8, "reflectivo": 7,
    "reflectiva": 7, "tela": 6, "bandera": 5, "banderas": 5,
    "pañuelo": 5, "bufanda": 5
}

NEGATIVE = {
    "medicamento": -8, "medicamentos": -8, "software": -6, "licencia de software": -8,
    "obra civil": -8, "combustible": -8, "vehiculo": -7, "vehículo": -7
}

def normalize(s):
    s = str(s or "").lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_alerts (
            ocid TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def get_sent(conn):
    return {r[0] for r in conn.execute("SELECT ocid FROM sent_alerts").fetchall()}

def mark_sent(conn, ocids):
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR IGNORE INTO sent_alerts(ocid, sent_at) VALUES (?, ?)",
        [(x, now) for x in ocids]
    )
    conn.commit()

def money(v):
    try:
        return f"L {float(v):,.2f}"
    except Exception:
        return "No indicado"

def extract_text(rec):
    parts = [
        rec.get("ocid"), rec.get("id"), rec.get("date"),
        rec.get("tender", {}).get("title"),
        rec.get("tender", {}).get("description"),
        rec.get("tender", {}).get("procurementMethod"),
        rec.get("tender", {}).get("procurementMethodDetails"),
        rec.get("planning", {}).get("rationale"),
    ]
    buyer = rec.get("buyer", {})
    parts += [buyer.get("name"), buyer.get("id")]

    for item in rec.get("tender", {}).get("items", []) or []:
        parts += [
            item.get("description"),
            item.get("classification", {}).get("description"),
            item.get("classification", {}).get("id"),
        ]
    for p in rec.get("parties", []) or []:
        parts += [p.get("name"), p.get("roles")]
    return normalize(" ".join(map(str, parts)))

def score_record(rec):
    text = extract_text(rec)
    score = 0
    hits = []
    for kw, weight in KEYWORDS.items():
        if normalize(kw) in text:
            score += weight
            hits.append(kw)
    for kw, weight in NEGATIVE.items():
        if normalize(kw) in text:
            score += weight

    if score >= 24:
        level = "ALTA"
    elif score >= 12:
        level = "MEDIA"
    else:
        level = "BAJA"
    return max(score, 0), level, hits

def get_deadline(rec):
    tp = rec.get("tender", {}).get("tenderPeriod", {}) or {}
    return tp.get("endDate") or rec.get("tender", {}).get("submissionMethodDetails")

def get_amount(rec):
    tender_value = rec.get("tender", {}).get("value", {}) or {}
    if tender_value.get("amount") is not None:
        return tender_value.get("amount")
    budget = rec.get("planning", {}).get("budget", {}) or {}
    amount = budget.get("amount", {}) or {}
    return amount.get("amount")

def record_to_row(rec):
    score, level, hits = score_record(rec)
    title = rec.get("tender", {}).get("title") or rec.get("tender", {}).get("description") or "Sin título"
    buyer = (rec.get("buyer") or {}).get("name") or "No indicado"
    method = rec.get("tender", {}).get("procurementMethodDetails") or rec.get("tender", {}).get("procurementMethod") or "No indicado"
    ocid = rec.get("ocid") or rec.get("id") or ""
    date = rec.get("date") or ""
    deadline = get_deadline(rec)
    amount = get_amount(rec)
    return {
        "ocid": ocid,
        "fecha_publicacion": date[:10] if date else "",
        "entidad": buyer,
        "titulo": title,
        "modalidad": method,
        "fecha_limite": deadline[:10] if isinstance(deadline, str) else "",
        "monto": amount,
        "relevancia": level,
        "puntaje": score,
        "coincidencias": ", ".join(hits[:10]),
        "url": f"https://contratacionesabiertas.gob.hn/proceso/{ocid}/" if ocid else "https://contratacionesabiertas.gob.hn/"
    }

@st.cache_data(ttl=3600, show_spinner=False)
def load_records(data_url):
    r = requests.get(data_url, timeout=90, headers={"User-Agent": "INTEX-Alertas-Publicas/1.0"})
    r.raise_for_status()
    rows = []
    raw = gzip.decompress(r.content).decode("utf-8") if data_url.endswith(".gz") else r.text
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            row = record_to_row(rec)
            if row["puntaje"] > 0:
                rows.append(row)
        except Exception:
            continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha_publicacion"] = pd.to_datetime(df["fecha_publicacion"], errors="coerce")
    df["fecha_limite_dt"] = pd.to_datetime(df["fecha_limite"], errors="coerce")
    return df.sort_values(["puntaje", "fecha_publicacion"], ascending=[False, False]).reset_index(drop=True)

def send_email(df, recipient):
    if df.empty:
        return False, "No hay oportunidades para enviar."

    sender = os.getenv("SMTP_USER", recipient)
    password = os.getenv("SMTP_PASSWORD", "")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))

    if not password:
        return False, "Falta SMTP_PASSWORD. Para Gmail use una contraseña de aplicación."

    subject = f"INTEX | {len(df)} nuevas oportunidades públicas de textiles/uniformes"
    html = f"""
    <html><body>
    <h2>INTEX – Alertas Públicas de Honduras</h2>
    <p>Se detectaron <b>{len(df)}</b> oportunidades con posible relación con confección, textiles y uniformes.</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Relevancia</th><th>Entidad</th><th>Oportunidad</th><th>Límite</th><th>Monto</th><th>Ver</th></tr>
    """
    for _, r in df.iterrows():
        html += f"""
        <tr>
          <td><b>{r['relevancia']}</b> ({r['puntaje']})</td>
          <td>{r['entidad']}</td>
          <td>{r['titulo']}</td>
          <td>{r['fecha_limite'] or 'No indicado'}</td>
          <td>{money(r['monto'])}</td>
          <td><a href="{r['url']}">Abrir proceso</a></td>
        </tr>
        """
    html += "</table><p>Fuente: ONCAE / HonduCompras / Portal de Contrataciones Abiertas de Honduras.</p></body></html>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())
    return True, "Correo enviado correctamente."

def send_new_alerts(df, recipient):
    conn = init_db()
    sent = get_sent(conn)
    new_df = df[~df["ocid"].isin(sent)].copy()
    new_df = new_df[new_df["relevancia"].isin(["ALTA", "MEDIA"])].head(25)
    if new_df.empty:
        return 0, "No hay alertas nuevas."
    ok, message = send_email(new_df, recipient)
    if ok:
        mark_sent(conn, new_df["ocid"].tolist())
        return len(new_df), message
    return 0, message

st.set_page_config(page_title=APP_NAME, page_icon="🧵", layout="wide")
st.title("🧵 INTEX Alertas Públicas")
st.caption("Monitor de oportunidades de contratación pública de Honduras para confección, textiles, uniformes y productos relacionados.")

with st.sidebar:
    st.header("Configuración")
    email = st.text_input("Correo de alertas", value=DEFAULT_EMAIL)
    data_url = st.text_input("Fuente de datos 2026", value=DEFAULT_DATA_URL)
    min_score = st.slider("Puntaje mínimo", 1, 30, 12)
    if st.button("🔄 Actualizar datos", use_container_width=True):
        load_records.clear()
        st.rerun()
    st.info("La fuente utilizada corresponde a datos abiertos de contratación pública. Revise siempre el pliego oficial antes de ofertar.")

try:
    df = load_records(data_url)
except Exception as e:
    st.error(f"No fue posible cargar los datos: {e}")
    st.stop()

if df.empty:
    st.warning("No se encontraron registros relevantes en la fuente.")
    st.stop()

# Filtros
c1, c2, c3 = st.columns(3)
with c1:
    search = st.text_input("🔎 Buscar", placeholder="Ej.: camisas, uniformes, tela...")
with c2:
    level = st.multiselect("Relevancia", ["ALTA", "MEDIA", "BAJA"], default=["ALTA", "MEDIA"])
with c3:
    entity = st.text_input("Entidad", placeholder="Ej.: Secretaría de Educación")

view = df[df["puntaje"] >= min_score].copy()
if level:
    view = view[view["relevancia"].isin(level)]
if search:
    q = normalize(search)
    view = view[view.apply(lambda r: q in normalize(" ".join(map(str, r.values))), axis=1)]
if entity:
    view = view[view["entidad"].str.contains(entity, case=False, na=False)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Oportunidades", len(view))
m2.metric("Alta relevancia", int((view["relevancia"] == "ALTA").sum()))
m3.metric("Media relevancia", int((view["relevancia"] == "MEDIA").sum()))
m4.metric("Entidades", view["entidad"].nunique())

st.divider()
st.subheader("Oportunidades detectadas")
display = view[[
    "relevancia", "puntaje", "entidad", "titulo",
    "modalidad", "fecha_limite", "monto", "coincidencias", "url"
]].copy()
display.columns = [
    "Relevancia", "Puntaje", "Entidad", "Oportunidad",
    "Modalidad", "Fecha límite", "Monto", "Palabras detectadas", "Enlace"
]
st.dataframe(display, use_container_width=True, hide_index=True, column_config={
    "Enlace": st.column_config.LinkColumn("Proceso oficial")
})

st.divider()
st.subheader("📧 Alertas por correo")
st.write(f"Las alertas se enviarán a **{email}** cuando se configure SMTP.")
if st.button("📨 Enviar ahora las oportunidades nuevas", type="primary"):
    count, msg = send_new_alerts(view, email)
    if count:
        st.success(f"{msg} Se enviaron {count} oportunidades.")
    else:
        st.warning(msg)

with st.expander("Palabras que busca el sistema"):
    st.write(", ".join(KEYWORDS.keys()))
