from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

logger = logging.getLogger("mopidy_rfid")


class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        b = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            # serve Materialize-based admin page
            html = (
                '<!doctype html>'
                '<html>'
                '<head>'
                '  <meta charset="utf-8">'
                '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />'
                '  <title>mopidy-rfid admin</title>'
                '  <link href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css" rel="stylesheet">'
                '  <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">'
                '  <style>td.pointer{cursor:pointer} pre{white-space:pre-wrap}</style>'
                '</head>'
                '<body>'
                '  <nav><div class="nav-wrapper teal"><a href="#" class="brand-logo center">mopidy-rfid</a></div></nav>'
                '  <div class="container" style="padding-top:20px">'
                '    <div class="row">'
                '      <div class="col s12">'
                '        <h5>Mappings</h5>'
                '        <table class="striped highlight">'
                '          <thead><tr><th>Tag</th><th>Action / URI</th><th></th></tr></thead>'
                '          <tbody id="mappings-tbody"></tbody>'
                '        </table>'
                '      </div>'
                '    </div>'
                '  </div>'
                '  <!-- FAB -->'
                '  <div class="fixed-action-btn"><a id="open-add" class="btn-floating btn-large red"><i class="large material-icons">add</i></a></div>'
                '  <!-- Modal Structure -->'
                '  <div id="mapping-modal" class="modal">'
                '    <div class="modal-content">'
                '      <h4 id="modal-title">Add Mapping</h4>'
                '      <div class="row">'
                '        <div class="input-field col s12">'
                '          <input id="tag-input" type="text">'
                '          <label for="tag-input">Tag ID</label>'
                '        </div>'
                '        <div class="input-field col s12">'
                '          <select id="type-select">'
                '            <option value="URI" selected>URI</option>'
                '            <option value="TOGGLE_PLAY">TOGGLE_PLAY</option>'
                '            <option value="STOP">STOP</option>'
                '          </select>'
                '          <label>Action Type</label>'
                '        </div>'
                '        <div class="input-field col s12" id="uri-field">'
                '          <input id="uri-input" type="text">'
                '          <label for="uri-input">URI</label>'
                '        </div>'
                '      </div>'
                '    </div>'
                '    <div class="modal-footer">'
                '      <a href="#!" id="save-mapping" class="modal-close waves-effect waves-green btn">Save</a>'
                '      <a href="#!" class="modal-close waves-effect btn-flat">Cancel</a>'
                '    </div>'
                '  </div>'
                '  <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"></script>'
                '  <script>'
                '    document.addEventListener("DOMContentLoaded", function(){'
                '      var elems = document.querySelectorAll(".modal"); M.Modal.init(elems);'
                '      var selects = document.querySelectorAll("select"); M.FormSelect.init(selects);'
                '      const modal = M.Modal.getInstance(document.getElementById("mapping-modal"));'
                '      document.getElementById("open-add").addEventListener("click", ()=>{'
                '        document.getElementById("modal-title").innerText = "Add Mapping";'
                '        document.getElementById("tag-input").value = "";'
                '        document.getElementById("uri-input").value = "";'
                '        M.updateTextFields();'
                '        M.FormSelect.init(document.querySelectorAll("select"));'
                '        modal.open();'
                '      });'
                '      function fetchMappings(){'
                '        fetch("/api/mappings").then(r=>r.json()).then(j=>renderMappings(j)).catch(e=>console.error(e));'
                '      }'
                '      function renderMappings(map){'
                '        const tbody = document.getElementById("mappings-tbody"); tbody.innerHTML = "";'
                '        Object.keys(map).forEach(tag=>{'
                '          const tr = document.createElement("tr");'
                '          const tdTag = document.createElement("td"); tdTag.textContent = tag; tdTag.className = "pointer";'
                '          const tdUri = document.createElement("td"); tdUri.innerHTML = "<pre>"+map[tag]+"</pre>";'
                '          const tdDel = document.createElement("td");'
                '          const delBtn = document.createElement("a"); delBtn.className = "waves-effect waves-light btn-small red"; delBtn.textContent = "Delete";'
                '          delBtn.addEventListener("click", (ev)=>{ ev.stopPropagation(); if(confirm("Delete mapping for " + tag + "?")){ fetch("/api/mappings/"+encodeURIComponent(tag), {method: "DELETE"}).then(()=>fetchMappings()); } });'
                '          tdDel.appendChild(delBtn);'
                '          tr.appendChild(tdTag); tr.appendChild(tdUri); tr.appendChild(tdDel);'
                '          tr.addEventListener("click", ()=>{'
                '            document.getElementById("modal-title").innerText = "Edit Mapping";'
                '            document.getElementById("tag-input").value = tag;'
                '            document.getElementById("uri-input").value = map[tag];'
                '            M.updateTextFields();'
                '            modal.open();'
                '          });'
                '          tbody.appendChild(tr);'
                '        });'
                '      }'
                '      document.getElementById("save-mapping").addEventListener("click", ()=>{'
                '        const tag = document.getElementById("tag-input").value.trim();'
                '        const type = document.getElementById("type-select").value;'
                '        let uri = document.getElementById("uri-input").value.trim();'
                '        if(type !== "URI") uri = type;'
                '        if(!tag || !uri){ alert("Tag and action required"); return; }'
                '        fetch("/api/mappings", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({tag: tag, uri: uri})}).then(r=>{ if(r.ok) fetchMappings(); else r.json().then(()=>alert("Failed to save")); });'
                '      });'
                '      // hide/show URI input depending on type'
                '      document.getElementById("type-select").addEventListener("change", function(e){'
                '        const v = this.value;'
                '        document.getElementById("uri-field").style.display = v === "URI" ? "block" : "none";'
                '      });'
                '      // init display'
                '      document.getElementById("uri-field").style.display = "block";'
                '      fetchMappings();'
                '    });'
                '  </script>'
                '</body></html>'
            )
            b = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return

        if self.path == "/api/mappings":
            out = getattr(self.server, "admin_list_mappings", lambda: {})()
            self._send_json(out)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/mappings":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                tag = str(data.get("tag"))
                uri = str(data.get("uri"))
                if not tag or not uri:
                    raise ValueError("missing")
                getattr(self.server, "admin_set_mapping", lambda t, u: None)(tag, uri)
                self._send_json({"ok": True})
            except Exception:
                self._send_json({"ok": False}, status=400)
            return

        if self.path.startswith("/api/mappings/"):
            # treat as delete
            tag = self.path[len("/api/mappings/"):]
            ok = getattr(self.server, "admin_delete_mapping", lambda t: False)(tag)
            self._send_json({"ok": ok})
            return

        self.send_response(404)
        self.end_headers()


class AdminHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, list_fn: Callable[[], dict], set_fn: Callable[[str, str], None], del_fn: Callable[[str], bool]):
        super().__init__(server_address, RequestHandlerClass)
        self._list_fn = list_fn
        self._set_fn = set_fn
        self._del_fn = del_fn

    def admin_list_mappings(self):
        try:
            return self._list_fn()
        except Exception:
            logger.exception("web_ui: list mappings failed")
            return {}

    def admin_set_mapping(self, tag: str, uri: str) -> None:
        try:
            self._set_fn(tag, uri)
        except Exception:
            logger.exception("web_ui: set mapping failed")

    def admin_delete_mapping(self, tag: str) -> bool:
        try:
            return self._del_fn(tag)
        except Exception:
            logger.exception("web_ui: delete mapping failed")
            return False


class WebUI:
    def __init__(self, host: str, port: int, list_fn, set_fn, del_fn) -> None:
        self._host = host
        self._port = port
        self._list_fn = list_fn
        self._set_fn = set_fn
        self._del_fn = del_fn
        self._server: AdminHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        try:
            self._server = AdminHTTPServer((self._host, self._port), _Handler, self._list_fn, self._set_fn, self._del_fn)
            t = threading.Thread(target=self._server.serve_forever, name="mopidy-rfid-webui", daemon=True)
            t.start()
            self._thread = t
            logger.info("web_ui: started on %s:%s", self._host, self._port)
        except Exception:
            logger.exception("web_ui: failed to start")
            self._server = None

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
                logger.info("web_ui: stopped")
            except Exception:
                logger.exception("web_ui: failed to stop")
            finally:
                self._server = None
                self._thread = None
