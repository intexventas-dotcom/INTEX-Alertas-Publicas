"""Diagnóstico de acceso y estructura pública de HonduCompras SICC.

No envía correos ni modifica datos. Imprime únicamente metadatos de la página
para diseñar un extractor compatible con la estructura real del portal.
"""
import re
import requests
from html.parser import HTMLParser

URL = "https://sicc.honducompras.gob.hn/HC/procesos/busquedahistorico.aspx"

class PageInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = False
        self.title_text = []
        self.forms = []
        self.current_form = None
        self.tables = []
        self.current_table = None
        self.current_row = None
        self.current_cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.title = True
        elif tag == "form":
            self.current_form = {"id": attrs.get("id"), "action": attrs.get("action"), "method": attrs.get("method")}
            self.forms.append(self.current_form)
        elif tag == "input" and self.current_form is not None:
            self.current_form.setdefault("inputs", []).append({
                "name": attrs.get("name"), "type": attrs.get("type"), "value": attrs.get("value", "")[:80]
            })
        elif tag == "table":
            self.current_table = {"id": attrs.get("id"), "rows": []}
            self.tables.append(self.current_table)
        elif tag == "tr" and self.current_table is not None:
            self.current_row = []
        elif tag in ("td", "th") and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data):
        value = re.sub(r"\\s+", " ", data).strip()
        if not value:
            return
        if self.title:
            self.title_text.append(value)
        if self.current_cell is not None:
            self.current_cell.append(value)

    def handle_endtag(self, tag):
        if tag == "title":
            self.title = False
        elif tag == "form":
            self.current_form = None
        elif tag in ("td", "th") and self.current_cell is not None:
            self.current_row.append(" ".join(self.current_cell))
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row:
                self.current_table["rows"].append(self.current_row)
            self.current_row = None
        elif tag == "table":
            self.current_table = None

def main():
    print("HONDUCOMPRAS_SICC_PROBE_BEGIN")
    try:
        response = requests.get(URL, timeout=35, headers={
            "User-Agent": "INTEX-Alertas-Publicas/2.1 (+public procurement monitoring)"
        })
        print(f"HTTP_STATUS={response.status_code}")
        print(f"FINAL_URL={response.url}")
        print(f"CONTENT_TYPE={response.headers.get('Content-Type', '')}")
        response.raise_for_status()
        parser = PageInspector()
        parser.feed(response.text)
        print("PAGE_TITLE=" + " ".join(parser.title_text)[:250])
        print(f"FORM_COUNT={len(parser.forms)}")
        for form in parser.forms[:5]:
            print("FORM=" + repr(form)[:1200])
        print(f"TABLE_COUNT={len(parser.tables)}")
        for index, table in enumerate(parser.tables[:10]):
            print(f"TABLE_{index}_ID={table['id']}")
            print(f"TABLE_{index}_ROW_COUNT={len(table['rows'])}")
            for row in table["rows"][:4]:
                print(f"TABLE_{index}_SAMPLE_ROW={repr(row)[:800]}")
        print("HONDUCOMPRAS_SICC_PROBE_END")
    except Exception as exc:
        print(f"PROBE_ERROR={type(exc).__name__}: {exc}")
        print("HONDUCOMPRAS_SICC_PROBE_END")
        # El diagnóstico no debe bloquear el envío basado en la fuente existente.

if __name__ == "__main__":
    main()
