from __future__ import annotations

import json
import logging
import os
from typing import Any

import tornado.web
import tornado.websocket

logger = logging.getLogger("mopidy_rfid")


class MappingsHandler(tornado.web.RequestHandler):
    def initialize(self, frontend: Any):
        self.frontend = frontend

    async def get(self):
        try:
            if self.frontend is None:
                logger.error("http: frontend not available")
                self.set_status(503)
                self.write({"error": "frontend not available"})
                return
            mappings = self.frontend.proxy().list_mappings().get()
            self.write(mappings)
        except Exception:
            logger.exception("http: list mappings failed")
            self.set_status(500)
            self.write({})

    async def post(self):
        try:
            if self.frontend is None:
                logger.error("http: frontend not available")
                self.set_status(503)
                self.write({"ok": False, "error": "frontend not available"})
                return
            data = json.loads(self.request.body.decode("utf-8"))
            tag = str(data.get("tag", ""))
            uri = str(data.get("uri", ""))
            if not tag or not uri:
                raise ValueError("missing tag or uri")
            self.frontend.proxy().set_mapping(tag, uri).get()
            self.write({"ok": True})
        except Exception:
            logger.exception("http: set mapping failed")
            self.set_status(400)
            self.write({"ok": False})


class MappingDeleteHandler(tornado.web.RequestHandler):
    def initialize(self, frontend: Any):
        self.frontend = frontend

    async def delete(self, tag: str):
        try:
            if self.frontend is None:
                logger.error("http: frontend not available")
                self.set_status(503)
                self.write({"ok": False, "error": "frontend not available"})
                return
            ok = self.frontend.proxy().delete_mapping(tag).get()
            self.write({"ok": ok})
        except Exception:
            logger.exception("http: delete mapping failed")
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
            results = []
            if self.core is not None:
                try:
                    search_result = self.core.library.search({"any": [q]}).get()
                    if search_result:
                        for result in search_result:
                            tracks = getattr(result, "tracks", [])
                            for t in tracks:
                                results.append({"uri": getattr(t, "uri", ""), "name": getattr(t, "name", "")})
                except Exception:
                    logger.exception("http: Mopidy library search failed")
            self.write({"results": results})
        except Exception:
            logger.exception("http: search handler failed")
            self.set_status(500)
            self.write({"results": []})


class WSHandler(tornado.websocket.WebSocketHandler):
    clients: set[WSHandler] = set()

    def open(self):
        logger.debug("websocket: client connected")
        self.clients.add(self)

    def on_close(self):
        logger.debug("websocket: client disconnected")
        self.clients.discard(self)

    def check_origin(self, origin: str) -> bool:
        return True

    @classmethod
    def broadcast(cls, obj: Any) -> None:
        msg = json.dumps(obj)
        for c in list(cls.clients):
            try:
                c.write_message(msg)
            except Exception:
                logger.exception("websocket: failed to write message")


def factory(config: Any, core: Any) -> list[tuple[str, Any, dict]]:
    """Factory function called by Mopidy to register HTTP handlers."""
    # Get the running frontend actor (Mopidy will have started it)
    frontend = None
    try:
        import pykka
        for actor_ref in pykka.ActorRegistry.get_all():
            # Check actor class name instead of isinstance
            if actor_ref.actor_class.__name__ == 'RFIDFrontend':
                frontend = actor_ref
                logger.info("http: Found RFIDFrontend actor")
                break
        if not frontend:
            logger.warning("http: RFIDFrontend actor not found in registry")
    except Exception:
        logger.exception("http: Could not locate RFIDFrontend actor")

    web_path = os.path.join(os.path.dirname(__file__), "web")

    return [
        (r"/api/mappings", MappingsHandler, {"frontend": frontend}),
        (r"/api/mappings/(.*)", MappingDeleteHandler, {"frontend": frontend}),
        (r"/api/search", SearchHandler, {"core": core}),
        (r"/ws", WSHandler, {}),
        (r"/(.*)", tornado.web.StaticFileHandler, {"path": web_path, "default_filename": "index.html"}),
    ]


def broadcast_event(obj: Any) -> None:
    """Helper to broadcast WebSocket events from frontend."""
    try:
        WSHandler.broadcast(obj)
    except Exception:
        logger.exception("http: broadcast failed")
