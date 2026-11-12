"""Pruebas independientes de disponibilidad de fuentes públicas INTEX.

Este diagnóstico es informativo: no extrae ni publica procesos, no envía correos
y nunca bloquea el trabajo de alertas si una fuente externa no responde.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

TIMEOUT = (8, 18)
HEADERS = {"User-Agent": "INTEX-Alertas-Publicas/2.2 (+public procurement monitoring)"}
SICC_PATH = "/HC/Procesos/BusquedaHistorico.aspx"
PORTAL = "https://honducompras.gob.hn/"
OCDS = "https://fastly.data.open-contracting.org/downloads/honduras_oncae/4368/2026.jsonl.gz"


class LinkFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            href = attrs.get("href", "").strip()
            if href:
                self.links.append((href, attrs.get("title", "")))


class FormInspector(HTMLParser):
    """Resume formularios ASP.NET sin imprimir valores de sesión o tokens."""
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current_form = None
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "form":
            self.current_form = {
                "action": attrs.get("action", ""),
                "method": attrs.get("method", "get").upper(),
                "fields": [],
            }
            self.forms.append(self.current_form)
        elif tag == "input" and self.current_form is not None:
            name = attrs.get("name") or attrs.get("id") or ""
            if name:
                value = attrs.get("value", "")
                field_type = attrs.get("type", "text").lower()
                detail = f"{name} (type={field_type}"
                if field_type == "hidden":
                    detail += f", value_length={len(value)}"
                elif value:
                    detail += f", value={value[:80]!r}"
                detail += ")"
                self.current_form["fields"].append(detail)
        elif tag == "select" and self.current_form is not None:
            name = attrs.get("name") or attrs.get("id") or ""
            if name:
                self.current_form["fields"].append(f"{name} (select)")
        elif tag == "textarea" and self.current_form is not None:
            name = attrs.get("name") or attrs.get("id") or ""
            if name:
                self.current_form["fields"].append(f"{name} (textarea)")
        elif tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])

    def handle_endtag(self, tag):
        if tag.lower() == "form":
            self.current_form = None

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            href = attrs.get("href", "").strip()
            if href:
                self.links.append((href, attrs.get("title", "")))


def probe(label, url, inspect_html=False):
    print(f"\nSOURCE={label}")
    print(f"REQUEST_URL={url}")
    try:
        response = requests.get(
            url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True,
            stream=True,
        )
        print(f"HTTP_STATUS={response.status_code}")
        print(f"FINAL_URL={response.url}")
        print(f"CONTENT_TYPE={response.headers.get('Content-Type', '')}")
        print(f"CONTENT_LENGTH={response.headers.get('Content-Length', 'unknown')}")
        if inspect_html:
            chunk = next(response.iter_content(chunk_size=262144), b"")
            text = chunk.decode("utf-8", errors="replace")
            title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            print("PAGE_TITLE=" + (re.sub(r"\\s+", " ", title.group(1)).strip()[:200] if title else "not found in first response chunk"))
            finder = LinkFinder()
            finder.feed(text)
            matches = []
            for href, title_attr in finder.links:
                combined = (href + " " + title_attr).lower()
                if any(word in combined for word in ("difusion", "difusión", "proceso", "contrato", "compras")):
                    absolute = urljoin(response.url, href)
                    if absolute not in matches:
                        matches.append(absolute)
            print(f"RELEVANT_LINK_COUNT={len(matches)}")
            for link in matches[:12]:
                print("RELEVANT_LINK=" + link[:500])

            inspector = FormInspector()
            inspector.feed(text)
            print(f"FORM_COUNT={len(inspector.forms)}")
            for index, form in enumerate(inspector.forms[:8], start=1):
                action = urljoin(response.url, form["action"] or response.url)
                print(f"FORM_{index}_METHOD={form['method']}")
                print(f"FORM_{index}_ACTION={action[:500]}")
                print(f"FORM_{index}_FIELD_COUNT={len(form['fields'])}")
                for field in form["fields"][:40]:
                    print(f"FORM_{index}_FIELD={field[:240]}")
            print(f"SCRIPT_SOURCE_COUNT={len(inspector.scripts)}")
            for src in inspector.scripts[:20]:
                print("SCRIPT_SOURCE=" + urljoin(response.url, src)[:500])
        else:
            chunk = next(response.iter_content(chunk_size=32), b"")
            if label == "OCDS":
                print(f"FIRST_BYTES_HEX={chunk[:16].hex()}")
                print(f"GZIP_SIGNATURE={'yes' if chunk.startswith(bytes([31, 139])) else 'not confirmed'}")
        response.close()
        return response.status_code
    except requests.exceptions.ConnectTimeout:
        print("RESULT=CONNECT_TIMEOUT")
    except requests.exceptions.ReadTimeout:
        print("RESULT=READ_TIMEOUT")
    except requests.exceptions.SSLError as exc:
        print(f"RESULT=SSL_ERROR: {type(exc).__name__}")
    except requests.exceptions.ConnectionError as exc:
        print(f"RESULT=CONNECTION_ERROR: {type(exc).__name__}")
    except Exception as exc:
        print(f"RESULT=ERROR: {type(exc).__name__}: {str(exc)[:300]}")
    return None


def main():
    print("INTEX_SOURCE_DIAGNOSTICS_BEGIN")
    print("NOTE=Each source is tested independently; failures do not stop alert delivery.")

    # SICC: both schemes are tested separately; HTTP may redirect to HTTPS.
    probe("SICC_HTTPS", "https://sicc.honducompras.gob.hn" + SICC_PATH, True)
    probe("SICC_HTTP", "http://sicc.honducompras.gob.hn" + SICC_PATH, True)

    # HonduCompras 2: inspect only links actually returned by the official portal.
    probe("HONDUCOMPRAS_2_PORTAL", PORTAL, True)

    # OCDS bulk file: check reachability and gzip signature without downloading
    # or parsing the complete dataset in this diagnostic step.
    probe("OCDS", OCDS, False)

    print("\nINTEX_SOURCE_DIAGNOSTICS_END")


if __name__ == "__main__":
    main()
