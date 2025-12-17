from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mopidy.core import Core  # type: ignore
    import pykka

# Defensive imports for pykka and mopidy
try:
    import pykka
except Exception:  # pragma: no cover - runtime only
    pykka = None  # type: ignore

try:
    from mopidy.core import Core  # type: ignore
except Exception:  # pragma: no cover - runtime only
    Core = object  # type: ignore

from .rfid_manager import RFIDManager
from .led_manager import LEDManager
from .mappings_db import MappingsDB
from .sounds_config import SoundsConfig

logger = logging.getLogger("mopidy_rfid")


# Choose base class: pykka.ThreadingActor if available, else plain object
if pykka is not None:
    _BaseClass = pykka.ThreadingActor
else:
    _BaseClass = object  # type: ignore


class RFIDFrontend(_BaseClass):
    """Pykka ThreadingActor frontend bridging Mopidy core and hardware managers."""

    def __init__(self, config: Dict[str, Any], core: Any) -> None:
        if pykka is not None:
            super().__init__()
        self._config = config.get("rfid", {}) if isinstance(config, dict) else {}
        self.core = core
        self._rfid: Optional[RFIDManager] = None
        self._led: Optional[LEDManager] = None
        self._db = MappingsDB(self._config.get("mappings_db_path"))
        self._sounds = SoundsConfig(self._config.get("sounds_config_path"))
        # Load config mappings as fallback/defaults
        self._config_mappings: Dict[str, str] = self._config.get("mappings", {}) or {}

    def on_start(self) -> None:
        """Called by Mopidy when actor starts. Must return quickly."""
        logger.info("RFIDFrontend starting")
        # Start hardware initialization in background thread to avoid blocking
        t = threading.Thread(target=self._init_hardware, name="rfid-hw-init", daemon=True)
        t.start()
        # Play welcome sound if configured
        try:
            uri = self._sounds.get("welcome")
            if uri and self.core is not None:
                logger.info("RFIDFrontend: playing welcome sound: %s", uri)
                self.core.tracklist.clear().get()
                self.core.tracklist.add(uris=[uri]).get()
                self.core.playback.play().get()
        except Exception:
            logger.exception("RFIDFrontend: failed to play welcome sound")

    def _init_hardware(self) -> None:
        """Initialize hardware in background thread."""
        pin_rst = int(self._config.get("pin_rst", 25))
        pin_button_led = int(self._config.get("pin_button_led", 13))
        led_enabled = bool(self._config.get("led_enabled", True))
        led_pin = int(self._config.get("led_pin", 12))
        led_count = int(self._config.get("led_count", 16))
        led_brightness = int(self._config.get("led_brightness", 60))

        # Initialize LED manager
        try:
            self._led = LEDManager(
                led_enabled=led_enabled,
                led_pin=led_pin,
                led_count=led_count,
                brightness=led_brightness,
                button_pin=pin_button_led,
            )
            if self._led:
                self._led.set_button_led(True)
                if led_enabled:
                    self._led.show_ready()
        except Exception:
            logger.exception("Failed to initialize LED manager")
            self._led = None

        # Initialize RFID manager
        try:
            self._rfid = RFIDManager(on_tag=self._on_tag_detected, pin_rst=pin_rst)
            if self._rfid:
                self._rfid.start()
        except Exception:
            logger.exception("Failed to initialize RFID manager")
            self._rfid = None

        logger.info("RFIDFrontend hardware initialization complete")

    def on_stop(self) -> None:
        """Called by Mopidy when actor stops."""
        logger.info("RFIDFrontend stopping")
        # Play farewell sound
        try:
            uri = self._sounds.get("farewell")
            if uri and self.core is not None:
                logger.info("RFIDFrontend: playing farewell sound: %s", uri)
                self.core.tracklist.clear().get()
                self.core.tracklist.add(uris=[uri]).get()
                self.core.playback.play().get()
        except Exception:
            logger.exception("RFIDFrontend: failed to play farewell sound")
        if self._rfid:
            try:
                self._rfid.stop()
            except Exception:
                logger.exception("Error stopping RFID manager")
        if self._led:
            try:
                self._led.shutdown()
            except Exception:
                logger.exception("Error shutting down LED manager")

    # --- Mapping helper methods (callable via actor proxy) ---
    def get_mapping(self, tag: str) -> Optional[str]:
        mapping = self._db.get(tag)
        if mapping:
            return mapping.get("uri")
        return self._config_mappings.get(tag)

    def set_mapping(self, tag: str, uri: str, description: str = "") -> None:
        self._db.set(tag, uri, description)

    def delete_mapping(self, tag: str) -> bool:
        return self._db.delete(tag)

    def list_mappings(self) -> Dict[str, Dict[str, str]]:
        out = self._db.list_all()
        # Merge config mappings where DB doesn't have them
        for k, v in self._config_mappings.items():
            if k not in out:
                out[k] = {"uri": v, "description": ""}
        return out

    # --- Tag handling ---
    def _on_tag_detected(self, tag_id: int) -> None:
        """Handle tag detection: map tag -> URI or special commands.

        Supported mapping values:
        - A Mopidy URI: will be added to the tracklist and played.
        - The special string "TOGGLE_PLAY": toggles play/pause.
        - The special string "STOP": stops playback.
        """
        tag_str = str(tag_id)
        logger.info("RFIDFrontend: tag detected: %s", tag_str)
        # Flash LED as confirmation
        if self._led:
            try:
                self._led.flash_confirm()
            except Exception:
                logger.exception("LED flash failed")
        # Play detected sound (confirmation)
        try:
            uri_det = self._sounds.get("detected")
            if uri_det and self.core is not None:
                logger.info("RFIDFrontend: playing detected sound: %s", uri_det)
                # Play detected confirmation quickly without clearing user's tracklist persistently
                self.core.tracklist.clear().get()
                self.core.tracklist.add(uris=[uri_det]).get()
                self.core.playback.play().get()
        except Exception:
            logger.exception("RFIDFrontend: failed to play detected sound")

        # ALWAYS broadcast tag event to Web UI (even if no mapping exists)
        # Use a separate thread to avoid event loop issues
        def _broadcast():
            try:
                from . import http
                uri = self.get_mapping(tag_str)
                http.broadcast_event({"event": "tag_scanned", "tag_id": tag_str, "uri": uri or ""})
                logger.info("RFIDFrontend: broadcasted tag_scanned event for tag %s", tag_str)
            except Exception:
                logger.exception("Failed to broadcast tag event")
        
        threading.Thread(target=_broadcast, daemon=True).start()

        uri = self.get_mapping(tag_str)
        if not uri:
            logger.warning("No mapping found for tag %s", tag_str)
            return

        if self.core is None:
            logger.warning("Core not available; cannot execute mapping for %s", tag_str)
            return

        try:
            if uri == "TOGGLE_PLAY":
                if self.core.playback.get_state().get() == "playing":
                    self.core.playback.pause().get()
                else:
                    self.core.playback.play().get()
            elif uri == "STOP":
                self.core.playback.stop().get()
            else:
                logger.info("RFIDFrontend: adding URI to tracklist: %s", uri)
                # Clear tracklist then add and play
                self.core.tracklist.clear().get()
                
                # Handle different URI types
                if uri.startswith('spotify:album:') or ':album:' in uri:
                    # For albums, lookup tracks and add them
                    lookup_result = self.core.library.lookup(uris=[uri]).get()
                    if lookup_result and uri in lookup_result:
                        tracks = lookup_result[uri]
                        if tracks:
                            for track in tracks:
                                self.core.tracklist.add(uris=[track.uri]).get()
                        else:
                            logger.warning("Album has no tracks: %s", uri)
                    else:
                        # Fallback: try to add directly
                        self.core.tracklist.add(uris=[uri]).get()
                elif uri.startswith('spotify:playlist:') or ':playlist:' in uri:
                    # For playlists, lookup tracks and add them
                    lookup_result = self.core.library.lookup(uris=[uri]).get()
                    if lookup_result and uri in lookup_result:
                        tracks = lookup_result[uri]
                        if tracks:
                            for track in tracks:
                                self.core.tracklist.add(uris=[track.uri]).get()
                        else:
                            logger.warning("Playlist has no tracks: %s", uri)
                    else:
                        # Fallback: try to add directly
                        self.core.tracklist.add(uris=[uri]).get()
                else:
                    # For tracks or other URIs, add directly
                    self.core.tracklist.add(uris=[uri]).get()
                
                self.core.playback.play().get()

        except Exception:
            logger.exception("Failed to execute action for tag %s", tag_str)
