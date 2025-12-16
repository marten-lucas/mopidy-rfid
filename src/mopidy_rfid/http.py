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
            description = str(data.get("description", ""))
            if not tag or not uri:
                raise ValueError("missing tag or uri")
            self.frontend.proxy().set_mapping(tag, uri, description).get()
            # Broadcast update to all connected clients
            broadcast_event({"event": "mappings_updated"})
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


class BrowseHandler(tornado.web.RequestHandler):
    def initialize(self, core: Any):
        self.core = core

    async def get(self):
        item_type = self.get_query_argument("type", default="track")
        try:
            items = []
            if self.core is not None:
                try:
                    # Browse Spotify library
                    browse_result = self.core.library.browse(uri=None).get()
                    
                    if item_type == "track":
                        # Get all tracks from all sources
                        for ref in browse_result:
                            if ref.type == "directory":
                                # Browse into directory
                                sub_result = self.core.library.browse(uri=ref.uri).get()
                                for sub_ref in sub_result[:50]:  # Limit to 50 items
                                    if sub_ref.type == "track":
                                        items.append({
                                            "uri": sub_ref.uri,
                                            "name": sub_ref.name or "Unknown Track",
                                            "type": "track"
                                        })
                    elif item_type == "album":
                        # Get albums
                        for ref in browse_result:
                            if ref.type == "directory":
                                sub_result = self.core.library.browse(uri=ref.uri).get()
                                for sub_ref in sub_result[:50]:
                                    if sub_ref.type == "album":
                                        items.append({
                                            "uri": sub_ref.uri,
                                            "name": sub_ref.name or "Unknown Album",
                                            "type": "album"
                                        })
                    elif item_type == "playlist":
                        # Get playlists
                        playlists_result = self.core.playlists.as_list().get()
                        for pl in playlists_result:
                            items.append({
                                "uri": pl.uri,
                                "name": pl.name or "Unknown Playlist",
                                "type": "playlist"
                            })
                except Exception:
                    logger.exception("http: Mopidy library browse failed")
            
            self.write({"items": items})
        except Exception:
            logger.exception("http: browse handler failed")
            self.set_status(500)
            self.write({"items": []})


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
                            # Add tracks
                            tracks = getattr(result, "tracks", None)
                            if tracks:
                                for t in tracks:
                                    name = getattr(t, "name", None) or "Unknown"
                                    artists = getattr(t, "artists", None)
                                    artist_str = ", ".join([getattr(a, "name", "") for a in artists]) if artists else ""
                                    results.append({
                                        "uri": getattr(t, "uri", ""), 
                                        "name": f"{name} - {artist_str}" if artist_str else name,
                                        "type": "track"
                                    })
                            
                            # Add albums
                            albums = getattr(result, "albums", None)
                            if albums:
                                for a in albums:
                                    name = getattr(a, "name", None) or "Unknown Album"
                                    artists = getattr(a, "artists", None)
                                    artist_str = ", ".join([getattr(ar, "name", "") for ar in artists]) if artists else ""
                                    results.append({
                                        "uri": getattr(a, "uri", ""),
                                        "name": f"{name} - {artist_str}" if artist_str else name,
                                        "type": "album"
                                    })
                            
                            # Add playlists
                            playlists = getattr(result, "playlists", None)
                            if playlists:
                                for p in playlists:
                                    results.append({
                                        "uri": getattr(p, "uri", ""),
                                        "name": getattr(p, "name", "Unknown Playlist"),
                                        "type": "playlist"
                                    })
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
    static_path = os.path.join(web_path, "static")

    return [
        (r"/api/mappings", MappingsHandler, {"frontend": frontend}),
        (r"/api/mappings/(.*)", MappingDeleteHandler, {"frontend": frontend}),
        (r"/api/search", SearchHandler, {"core": core}),
        (r"/api/browse", BrowseHandler, {"core": core}),
        (r"/ws", WSHandler, {}),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/(favicon\.ico)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/(.*)", tornado.web.StaticFileHandler, {"path": web_path, "default_filename": "index.html"}),
    ]


def broadcast_event(obj: Any) -> None:
    """Helper to broadcast WebSocket events from frontend."""
    try:
        WSHandler.broadcast(obj)
    except Exception:
        logger.exception("http: broadcast failed")
