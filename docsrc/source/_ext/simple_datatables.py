# simple_datatable.py
import json
from sphinx.application import Sphinx

CDN_JS  = "https://cdn.jsdelivr.net/npm/simple-datatables@9.0.0/dist/umd/simple-datatables.js"
CDN_CSS = "https://cdn.jsdelivr.net/npm/simple-datatables@9.0.0/dist/style.css"

def _add_init_js(app: Sphinx):
    selector = app.config.simple_datatable_selector or "table.sdtable"
    options = app.config.simple_datatable_options or {}

    init_code = f"""
document.addEventListener('DOMContentLoaded', function() {{
  if (!window.simpleDatatables) {{
    console.warn('simpleDatatables not loaded yet');
    return;
  }}
  document.querySelectorAll('{selector}').forEach(function(el) {{
    if (!el.dataset.sdInit) {{
      el.dataset.sdInit = '1';
      try {{
        new window.simpleDatatables.DataTable(el, {json.dumps(options)});
      }} catch (e) {{
        console.error('Simple-DataTables init failed:', e);
      }}
    }}
  }});
}});
"""
    app.add_js_file(None, body=init_code)

def setup(app: Sphinx):
    app.add_config_value("simple_datatable_selector", "table.sdtable", "html")
    app.add_config_value("simple_datatable_options", {}, "html")

    app.add_css_file(CDN_CSS)
    app.add_js_file(CDN_JS, defer="defer")  # ← changed

    app.connect("builder-inited", _add_init_js)

    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
