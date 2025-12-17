from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import tornado.web
import tornado.websocket

logger = logging.getLogger("mopidy_rfid")

# Store the HTTP server's IOLoop so we can safely broadcast from other threads
_io_loop = None  # type: ignore

LAST_SCAN: dict[str, Any] | None = None


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
                    logger.info(f"http: browsing for type: {item_type}")
                    
                    if item_type == "playlist":
                        # Get playlists - most reliable
                        playlists_result = self.core.playlists.as_list().get()
                        for pl in playlists_result:
                            # Extract source from URI (e.g., spotify:playlist:xxx -> spotify)
                            source = pl.uri.split(':')[0] if ':' in pl.uri else 'unknown'
                            items.append({
                                "uri": pl.uri,
                                "name": pl.name or "Unknown Playlist",
                                "type": "playlist",
                                "source": source
                            })
                        logger.info(f"http: found {len(items)} playlists")
                        
                    elif item_type == "album":
                        # Get albums by browsing all sources
                        browse_result = self.core.library.browse(uri=None).get()
                        for ref in browse_result:
                            try:
                                # Browse each source
                                sub_result = self.core.library.browse(uri=ref.uri).get()
                                for item in sub_result:
                                    if item.type == "album":
                                        source = item.uri.split(':')[0] if ':' in item.uri else 'unknown'
                                        items.append({
                                            "uri": item.uri,
                                            "name": item.name or "Unknown Album",
                                            "type": "album",
                                            "source": source
                                        })
                                    # Also check directories for albums
                                    elif item.type == "directory":
                                        try:
                                            deep_result = self.core.library.browse(uri=item.uri).get()
                                            for deep_item in deep_result[:100]:
                                                if deep_item.type == "album":
                                                    source = deep_item.uri.split(':')[0] if ':' in deep_item.uri else 'unknown'
                                                    items.append({
                                                        "uri": deep_item.uri,
                                                        "name": deep_item.name or "Unknown Album",
                                                        "type": "album",
                                                        "source": source
                                                    })
                                        except Exception:
                                            pass
                                    if len(items) >= 200:  # Limit to prevent timeout
                                        break
                            except Exception:
                                continue
                        logger.info(f"http: found {len(items)} albums")
                        
                    elif item_type == "track":
                        # Get tracks by browsing
                        browse_result = self.core.library.browse(uri=None).get()
                        for ref in browse_result:
                            try:
                                sub_result = self.core.library.browse(uri=ref.uri).get()
                                for item in sub_result:
                                    if item.type == "track":
                                        source = item.uri.split(':')[0] if ':' in item.uri else 'unknown'
                                        items.append({
                                            "uri": item.uri,
                                            "name": item.name or "Unknown Track",
                                            "type": "track",
                                            "source": source
                                        })
                                    # Browse deeper for tracks
                                    elif item.type in ("directory", "album"):
                                        try:
                                            deep_result = self.core.library.browse(uri=item.uri).get()
                                            for deep_item in deep_result[:100]:
                                                if deep_item.type == "track":
                                                    source = deep_item.uri.split(':')[0] if ':' in deep_item.uri else 'unknown'
                                                    items.append({
                                                        "uri": deep_item.uri,
                                                        "name": deep_item.name or "Unknown Track",
                                                        "type": "track",
                                                        "source": source
                                                    })
                                        except Exception:
                                            pass
                                    if len(items) >= 200:
                                        break
                            except Exception:
                                continue
                        logger.info(f"http: found {len(items)} tracks")
                        
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


class LastScanHandler(tornado.web.RequestHandler):
    async def get(self):
        global LAST_SCAN
        self.write(LAST_SCAN or {})


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

    # Capture the current IOLoop for thread-safe broadcasts
    try:
        from tornado.ioloop import IOLoop
        global _io_loop
        _io_loop = IOLoop.current()
        logger.info("http: Captured HTTP server IOLoop for broadcasts")
    except Exception:
        logger.exception("http: Failed to capture IOLoop")

    web_path = os.path.join(os.path.dirname(__file__), "web")
    static_path = os.path.join(web_path, "static")

    return [
        (r"/api/mappings", MappingsHandler, {"frontend": frontend}),
        (r"/api/mappings/(.*)", MappingDeleteHandler, {"frontend": frontend}),
        (r"/api/search", SearchHandler, {"core": core}),
        (r"/api/browse", BrowseHandler, {"core": core}),
        (r"/api/last-scan", LastScanHandler, {}),
        (r"/ws", WSHandler, {}),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/(favicon\.ico)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/(.*)", tornado.web.StaticFileHandler, {"path": web_path, "default_filename": "index.html"}),
    ]


def broadcast_event(obj: Any) -> None:
    """Helper to broadcast WebSocket events from frontend (thread-safe)."""
    try:
        global _io_loop, LAST_SCAN
        # Store last scan if applicable
        if isinstance(obj, dict) and obj.get("event") == "tag_scanned":
            LAST_SCAN = {"tag_id": obj.get("tag_id"), "ts": time.time(), "uri": obj.get("uri", "")}
        if _io_loop is not None:
            _io_loop.add_callback(WSHandler.broadcast, obj)
        else:
            WSHandler.broadcast(obj)
    except Exception:
        logger.exception("http: broadcast failed")
