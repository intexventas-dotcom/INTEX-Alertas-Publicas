import gzip
import json
import os
import re
import sqlite3
import smtplib
import hashlib
from datetime import datetime, date
from email.message import EmailMessage
from io import BytesIO

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "INTEX Alertas Públicas V2"
DEFAULT_DATA_URL = "https://fastly.data.open-contracting.org/downloads/honduras_oncae/4176/2026.jsonl.gz"
DB_PATH = os.getenv("INTEX_DB_PATH", "intex_alerts.sqlite3")

DIRECT = {
    "uniforme": 30, "uniformes": 30, "confeccion": 26, "confección": 26,
    "textil": 25, "textiles": 25, "vestuario": 24, "ropa de trabajo": 25,
    "ropa institucional": 25, "camisa": 22, "camisas": 22, "pantalon": 20,
    "pantalón": 20, "pantalones": 20, "camiseta": 18, "camisetas": 18,
    "polo": 18, "polos": 18, "chaqueta": 18, "chaquetas": 18,
    "gabacha": 22, "gabachas": 22, "bata": 18, "batas": 18,
    "overol": 22, "overoles": 22, "chaleco": 18, "chalecos": 18,
    "delantal": 18, "delantales": 18, "mandil": 18, "gorra": 16,
    "gorras": 16, "ropa industrial": 22, "uniforme escolar": 30,
    "uniformes escolares": 30, "uniforme empresarial": 30,
    "uniformes empresariales": 30
}
RELATED = {
    "bordado": 12, "bordados": 12, "serigrafia": 12, "serigrafía": 12,
    "dryfit": 14, "dry fit": 14, "reflectivo": 12, "reflectiva": 12,
    "tela": 10, "telas": 10, "bandera": 8, "banderas": 8,
    "pañuelo": 8, "bufanda": 8, "calzado": 3
}
EXCLUDE = {
    "medicamento": 40, "medicamentos": 40, "farmaceutico": 40,
    "farmacéutico": 40, "software": 35, "licencia de software": 40,
    "combustible": 35, "gasolina": 35, "diesel": 35, "diésel": 35,
    "vehiculo": 35, "vehículo": 35, "obra civil": 40, "construccion": 40,
    "construcción": 40, "cemento": 35, "asfalto": 35,
    "equipo medico": 40, "equipo médico": 40, "reactivos": 40
}
STRONG_TITLE = (
    "uniforme", "uniformes", "confeccion", "confección", "textil", "textiles",
    "camisa", "camisas", "ropa de trabajo", "vestuario", "gabacha", "overol",
    "pantalon", "pantalón", "polo", "camiseta"
)

def normalize(s):
    s = str(s or "").lower()
    replacements = {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u"}
    for a, b in replacements.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()

def first(d, keys, default=""):
    for k in keys:
        value = d.get(k)
        if value not in (None, "", [], {}):
            return value
    return default

def parse_date(value):
    if not value:
        return None
    try:
        return pd.to_datetime(value, errors="coerce", utc=True).date()
    except Exception:
        return None

def extract_records(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("releases"), list):
            return obj["releases"]
        if isinstance(obj.get("records"), list):
            return obj["records"]
        if isinstance(obj.get("data"), list):
            return obj["data"]
        return [obj]
    return []

def load_records(url, uploaded_file=None):
    raw = None
    if uploaded_file is not None:
        raw = uploaded_file.getvalue()
    else:
        response = requests.get(url, timeout=45, headers={"User-Agent": "INTEX-Alertas-Publicas/2.0"})
        response.raise_for_status()
        raw = response.content

    if raw[:2] == b"\x1f\x8b" or (url.lower().endswith(".gz") if uploaded_file is None else False):
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass

    text = raw.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return []
    # JSON Lines is the common format for Open Contracting bulk files.
    if "\n" in text and not text.lstrip().startswith(("[", "{")):
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.extend(extract_records(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return rows
    try:
        return extract_records(json.loads(text))
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            try:
                rows.extend(extract_records(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return rows

def flatten_record(r):
    if not isinstance(r, dict):
        return None
    tender = r.get("tender") or {}
    buyer = r.get("buyer") or {}
    procuring = r.get("procuringEntity") or {}
    parties = r.get("parties") or []
    entity = first(buyer, ["name"]) or first(procuring, ["name"])
    if not entity and isinstance(parties, list):
        for p in parties:
            if isinstance(p, dict) and p.get("roles") and any(x in p.get("roles", []) for x in ["buyer", "procuringEntity"]):
                entity = (p.get("name") or "")
                if entity:
                    break
    title = first(tender, ["title", "description"]) or first(r, ["title", "ocid", "id"], "Oportunidad sin título")
    description = first(tender, ["description"])
    items = tender.get("items") or []
    item_text = " ".join(str(first(i, ["description", "classification"], "")) for i in items if isinstance(i, dict))
    docs = tender.get("documents") or []
    doc_text = " ".join(str(d.get("title", "")) for d in docs if isinstance(d, dict))
    body = " ".join([str(description), item_text, doc_text])
    tender_period = tender.get("tenderPeriod") or {}
    closing = parse_date(first(tender_period, ["endDate"]))
    published = parse_date(first(r, ["date"]) or first(tender, ["datePublished"]))
    url = ""
    for d in docs:
        if isinstance(d, dict) and d.get("url"):
            url = d["url"]
            break
    if not url:
        url = first(tender, ["url"])
    return {
        "id": str(first(r, ["ocid", "id"], "")),
        "titulo": str(title),
        "institucion": str(entity or "Institución no identificada"),
        "descripcion": str(body),
        "publicacion": published,
        "fecha_limite": closing,
        "url": str(url or ""),
        "raw": r
    }

def score_opportunity(title, body):
    nt, nb = normalize(title), normalize(body)
    score, found_direct, found_related, found_exclude = 0, [], [], []
    for term, weight in DIRECT.items():
        t = normalize(term)
        if t in nt:
            score += weight
            found_direct.append(term)
        elif t in nb:
            score += max(5, round(weight * 0.48))
            found_direct.append(term)
    for term, weight in RELATED.items():
        t = normalize(term)
        if t in nt:
            score += weight
            found_related.append(term)
        elif t in nb:
            score += max(2, round(weight * 0.45))
            found_related.append(term)
    for term, weight in EXCLUDE.items():
        if normalize(term) in nt or normalize(term) in nb:
            score -= weight
            found_exclude.append(term)

    strong = any(normalize(term) in nt for term in STRONG_TITLE)
    if found_related and not found_direct:
        score = min(score, 35)
    if found_exclude and not strong and not found_direct:
        return 0, "DESCARTAR", "Coincide con términos de otro sector: " + ", ".join(found_exclude[:3])
    score = max(0, min(100, score))
    if strong or score >= 60:
        priority = "MUY ALTA"
    elif score >= 35:
        priority = "ALTA"
    elif score >= 18:
        priority = "MEDIA"
    else:
        priority = "BAJA"

    reasons = []
    if found_direct:
        reasons.append("Coincide con: " + ", ".join(dict.fromkeys(found_direct[:5])))
    if found_related:
        reasons.append("Relacionado con: " + ", ".join(dict.fromkeys(found_related[:3])))
    if found_exclude:
        reasons.append("Revisar posible rubro ajeno: " + ", ".join(found_exclude[:2]))
    return score, priority, " | ".join(reasons) if reasons else "Coincidencia débil; revisar manualmente"

def prepare_dataframe(records):
    rows = []
    seen = set()
    for r in records:
        flat = flatten_record(r)
        if not flat:
            continue
        key = flat["id"] or hashlib.sha1((flat["titulo"] + flat["institucion"]).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        score, priority, reason = score_opportunity(flat["titulo"], flat["descripcion"])
        if score < 12 or priority == "DESCARTAR":
            continue
        today = date.today()
        deadline = flat["fecha_limite"]
        days = (deadline - today).days if deadline else None
        if deadline:
            status = "VENCIDA" if days < 0 else ("URGENTE" if days <= 7 else ("PRÓXIMA" if days <= 15 else "VIGENTE"))
        else:
            status = "Sin fecha publicada"
        rows.append({
            "Prioridad": priority, "Puntaje": score, "Título": flat["titulo"],
            "Institución": flat["institucion"], "Fecha límite": deadline,
            "Días restantes": days, "Estado": status, "¿Por qué INTEX?": reason,
            "Publicado": flat["publicacion"], "Enlace": flat["url"], "_id": key,
            "_texto": normalize(flat["titulo"] + " " + flat["institucion"] + " " + flat["descripcion"])
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        order = {"MUY ALTA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3}
        df["_orden"] = df["Prioridad"].map(order)
        df = df.sort_values(["_orden", "Puntaje", "Días restantes"], ascending=[True, False, True], na_position="last").drop(columns=["_orden"])
    return df

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sent_alerts (id TEXT PRIMARY KEY, sent_at TEXT)")
        conn.commit()

def send_email(df, recipient, smtp_user, smtp_password):
    if df.empty:
        return 0, "No hay oportunidades para enviar."
    if not smtp_user or not smtp_password:
        return 0, "Falta configurar SMTP_USER y SMTP_PASSWORD en los secretos."
    init_db()
    new_rows = []
    with sqlite3.connect(DB_PATH) as conn:
        sent = {row[0] for row in conn.execute("SELECT id FROM sent_alerts").fetchall()}
        for _, row in df.iterrows():
            if str(row["_id"]) not in sent:
                new_rows.append(row)
        if not new_rows:
            return 0, "No se encontraron oportunidades nuevas para enviar."
        msg = EmailMessage()
        msg["Subject"] = f"INTEX | {len(new_rows)} oportunidades públicas de textiles/uniformes"
        msg["From"] = smtp_user
        msg["To"] = recipient
        lines = ["Oportunidades detectadas por INTEX Alertas Públicas V2", ""]
        for row in new_rows[:40]:
            lines += [
                f"[{row['Prioridad']}] {row['Título']}",
                f"Institución: {row['Institución']}",
                f"Puntaje: {row['Puntaje']}/100",
                f"Fecha límite: {row['Fecha límite'] or 'No publicada'}",
                f"Días restantes: {row['Días restantes'] if pd.notna(row['Días restantes']) else 'No disponible'}",
                f"¿Por qué INTEX?: {row['¿Por qué INTEX?']}",
                f"Enlace: {row['Enlace'] or 'No disponible'}",
                ""
            ]
        msg.set_content("\n".join(lines))
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            for row in new_rows:
                conn.execute("INSERT OR IGNORE INTO sent_alerts (id, sent_at) VALUES (?, ?)",
                             (str(row["_id"]), datetime.utcnow().isoformat()))
            conn.commit()
            return len(new_rows), "Correo enviado correctamente."
        except Exception as e:
            return 0, f"No se pudo enviar el correo: {e}"

st.set_page_config(page_title=APP_TITLE, page_icon="🧵", layout="wide")
st.title("🧵 INTEX Alertas Públicas V2")
st.caption("Monitor de oportunidades de contratación pública en Honduras relacionadas con textiles, confección y uniformes.")

with st.sidebar:
    st.header("Fuente de datos")
    data_url = st.text_input("URL de datos JSON/JSONL/GZIP", value=os.getenv("INTEX_DATA_URL", DEFAULT_DATA_URL))
    uploaded = st.file_uploader("O cargar archivo de contrataciones", type=["json", "jsonl", "gz", "txt"])
    st.divider()
    st.header("Filtros")
    min_score = st.slider("Puntaje mínimo", min_value=0, max_value=100, value=12, step=1)
    urgent_only = st.checkbox("Solo oportunidades con 15 días o menos", value=False)
    priorities = st.multiselect("Prioridad", ["MUY ALTA", "ALTA", "MEDIA", "BAJA"],
                                default=["MUY ALTA", "ALTA", "MEDIA", "BAJA"])
    st.divider()
    st.header("Alertas por correo")
    recipient = st.text_input("Correo destinatario", value="intexventas@gmail.com")
    smtp_user = st.text_input("Cuenta Gmail emisora", value=os.getenv("SMTP_USER", ""))
    smtp_password = st.text_input("Contraseña de aplicación de Google", type="password", value=os.getenv("SMTP_PASSWORD", ""))
    send_button = st.button("Enviar oportunidades nuevas por correo", use_container_width=True)

@st.cache_data(ttl=900, show_spinner=False)
def get_data(url):
    records = load_records(url)
    return prepare_dataframe(records)

try:
    with st.spinner("Consultando oportunidades de contratación..."):
        if uploaded is not None:
            df_all = prepare_dataframe(load_records(data_url, uploaded))
        else:
            df_all = get_data(data_url)
    st.success(f"Consulta completada. Oportunidades relacionadas detectadas: {len(df_all)}")
except Exception as e:
    df_all = pd.DataFrame()
    st.error("No se pudo consultar la fuente automáticamente.")
    st.caption(f"Detalle técnico: {e}")
    st.info("Puede cargar un archivo JSON/JSONL descargado de la fuente oficial para continuar.")

if not df_all.empty:
    total = len(df_all)
    very_high = int((df_all["Prioridad"] == "MUY ALTA").sum())
    high = int((df_all["Prioridad"] == "ALTA").sum())
    urgent = int(df_all["Días restantes"].apply(lambda x: pd.notna(x) and 0 <= x <= 15).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Oportunidades detectadas", total)
    c2.metric("Muy alta prioridad", very_high)
    c3.metric("Alta prioridad", high)
    c4.metric("Vencen en ≤15 días", urgent)

    query = st.text_input("Buscar por título, institución o coincidencia", placeholder="Ej. camisas, uniformes, hospital...")
    entities = sorted(df_all["Institución"].dropna().astype(str).unique().tolist())
    selected_entities = st.multiselect("Filtrar por institución", entities)
    df = df_all[df_all["Puntaje"] >= min_score].copy()
    df = df[df["Prioridad"].isin(priorities)]
    if selected_entities:
        df = df[df["Institución"].isin(selected_entities)]
    if urgent_only:
        df = df[df["Días restantes"].apply(lambda x: pd.notna(x) and 0 <= x <= 15)]
    if query.strip():
        q = normalize(query)
        df = df[df["_texto"].str.contains(re.escape(q), na=False)]

    st.subheader(f"Resultados: {len(df)} oportunidades")
    display_cols = ["Prioridad", "Puntaje", "Título", "Institución", "Fecha límite", "Días restantes", "Estado", "¿Por qué INTEX?", "Enlace"]
    show = df[display_cols].copy()
    show["Enlace"] = show["Enlace"].apply(lambda x: x if isinstance(x, str) and x.startswith(("http://", "https://")) else "")
    st.dataframe(show, use_container_width=True, hide_index=True,
                 column_config={"Enlace": st.column_config.LinkColumn("Enlace", display_text="Abrir oportunidad"),
                                "Puntaje": st.column_config.ProgressColumn("Puntaje", min_value=0, max_value=100, format="%d/100"),
                                "Fecha límite": st.column_config.DateColumn("Fecha límite", format="DD/MM/YYYY"),
                                "Publicado": st.column_config.DateColumn("Publicado", format="DD/MM/YYYY") if "Publicado" in show.columns else None})
    csv = df[display_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("Descargar resultados en Excel/CSV", data=csv, file_name="INTEX_oportunidades_V2.csv", mime="text/csv")
    if send_button:
        count, message = send_email(df, recipient, smtp_user, smtp_password)
        if count:
            st.success(f"{message} Oportunidades enviadas: {count}.")
        else:
            st.warning(message)
else:
    st.warning("No hay resultados disponibles para mostrar. Revise la fuente de datos o cargue un archivo de contrataciones.")

st.divider()
st.caption("Aviso: esta herramienta sirve como filtro de apoyo. Verifique siempre los pliegos, requisitos, fechas y enlaces en la fuente oficial antes de preparar una oferta.")
