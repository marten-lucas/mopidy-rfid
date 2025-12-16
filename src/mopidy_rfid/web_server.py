from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket

logger = logging.getLogger("mopidy_rfid")


class MappingsHandler(tornado.web.RequestHandler):
    def initialize(self, db: Any):
        self.db = db

    async def get(self, tag: str | None = None):
        try:
            out = self.db.list_all()
            self.write(out)
        except Exception:
            logger.exception("web: list mappings failed")
            self.set_status(500)
            self.write({})

    async def post(self):
        try:
            data = json.loads(self.request.body.decode("utf-8"))
            tag = str(data.get("tag"))
            uri = str(data.get("uri"))
            if not tag or not uri:
                raise ValueError("missing")
            self.db.set(tag, uri)
            self.write({"ok": True})
        except Exception:
            logger.exception("web: set mapping failed")
            self.set_status(400)
            self.write({"ok": False})

    async def delete(self, tag: str):
        try:
            ok = self.db.delete(tag)
            self.write({"ok": ok})
        except Exception:
            logger.exception("web: delete mapping failed")
            self.set_status(500)
            self.write({"ok": False})


class SearchHandler(tornado.web.RequestHandler):
    def initialize(self, core: Any):
        self.core = core

    async def get(self):
        q = self.get_query_argument("q", default="")
        if not q:
            self.write({"results": []})
            return
        try:
            # Use Mopidy core.library.search with a simple any query
            results = []
            if self.core is not None:
                try:
                    res = self.core.library.search({"any": [q]}).get()
                    tracks = res.get("tracks", [])
                    for t in tracks:
                        results.append({"uri": getattr(t, "uri", ""), "name": getattr(t, "name", "")})
                except Exception:
                    logger.exception("web: search via Mopidy failed")
            self.write({"results": results})
        except Exception:
            logger.exception("web: search failed")
            self.set_status(500)
            self.write({"results": []})


class WSHandler(tornado.websocket.WebSocketHandler):
    clients: set["WSHandler"] = set()

    def open(self):
        logger.debug("websocket: client connected")
        self.clients.add(self)

    def on_close(self):
        logger.debug("websocket: client disconnected")
        self.clients.discard(self)

    def check_origin(self, origin: str) -> bool:  # allow cross-origin for local network
        return True

    @classmethod
    def broadcast(cls, obj: Any) -> None:
        msg = json.dumps(obj)
        for c in list(cls.clients):
            try:
                c.write_message(msg)
            except Exception:
                logger.exception("websocket: failed to write message")


_server_state: dict[str, Any] = {}


def start_server(host: str, port: int, db: Any, core: Any) -> dict:
    """Start Tornado in a background thread. Returns a handle dict for stop_server."""
    static_path = os.path.join(os.path.dirname(__file__), "web", "static")

    app = tornado.web.Application(
        [
            (r"/api/mappings", MappingsHandler, dict(db=db)),
            (r"/api/mappings/(.*)", MappingsHandler, dict(db=db)),
            (r"/api/search", SearchHandler, dict(core=core)),
            (r"/ws", WSHandler),
            (r"/(.*)", tornado.web.StaticFileHandler, {"path": static_path, "default_filename": "index.html"}),
        ],
        debug=False,
    )

    http_server = tornado.httpserver.HTTPServer(app)
    loop = tornado.ioloop.IOLoop()

    def _run():
        try:
            loop.make_current()
            http_server.listen(port, address=host)
            logger.info("web: tornado listening on %s:%s", host, port)
            loop.start()
        except Exception:
            logger.exception("web: tornado loop failed")

    t = threading.Thread(target=_run, name="mopidy-rfid-tornado", daemon=True)
    t.start()

    handle = {"loop": loop, "thread": t, "http_server": http_server}
    _server_state["handle"] = handle
    return handle


def stop_server(handle: dict) -> None:
    try:
        loop = handle.get("loop")
        if loop is None:
            return
        loop.add_callback(loop.stop)
        # wait for thread to exit
        thread = handle.get("thread")
        if thread is not None:
            thread.join(timeout=2.0)
        logger.info("web: tornado stopped")
    except Exception:
        logger.exception("web: failed to stop tornado")


def broadcast_event(obj: Any) -> None:
    try:
        WSHandler.broadcast(obj)
    except Exception:
        logger.exception("web: broadcast failed")
