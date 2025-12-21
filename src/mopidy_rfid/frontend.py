from __future__ import annotations

import logging
import time
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
from .led_config import LedConfig

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
        self._led_cfg = LedConfig(self._config.get("led_config_path"))
        # Load config mappings as fallback/defaults
        self._config_mappings: Dict[str, str] = self._config.get("mappings", {}) or {}
        self._progress_thread: Optional[threading.Thread] = None
        self._progress_stop = threading.Event()

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
        # LED welcome animation if enabled (may run after hardware init)
        try:
            if self._led and getattr(self._led, '_enabled', False) and self._led_cfg.get("welcome"):
                # Prefer animated welcome
                try:
                    self._led.welcome_scan(color=(0,255,0), delay=0.05)
                except Exception:
                    self._led.show_ready()
        except Exception:
            logger.exception("RFIDFrontend: LED welcome animation failed")
        # Start remaining progress updater
        self._start_progress_updater()

    def _init_hardware(self) -> None:
        """Initialize hardware in background thread."""
        pin_rst = int(self._config.get("pin_rst", 25))
        pin_button_led = int(self._config.get("pin_button_led", 13))
        led_enabled = bool(self._config.get("led_enabled", True))
        led_pin = int(self._config.get("led_pin", 12))
        led_count = int(self._config.get("led_count", 16))
        led_brightness = int(self._config.get("led_brightness", 60))
        led_idle_brightness = int(self._config.get("led_idle_brightness", 10))

        # Initialize LED manager
        try:
            self._led = LEDManager(
                led_enabled=led_enabled,
                led_pin=led_pin,
                led_count=led_count,
                brightness=led_brightness,
                idle_brightness=led_idle_brightness,
                button_pin=pin_button_led,
            )
            if self._led and getattr(self._led, '_enabled', False):
                try:
                    self._led.stop_standby_comet()
                except Exception:
                    pass
                if led_enabled:
                    self._led.show_ready()
                    # Start standby comet (very low brightness, slow)
                    try:
                        self._led.start_standby_comet(color=(0, 8, 0), delay=5.0, trail=2)
                    except Exception:
                        pass
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
        # LED farewell animation if enabled
        try:
            if self._led and self._led_cfg.get("farewell"):
                try:
                    self._led.farewell_scan(color=(0,255,0), delay=0.05)
                except Exception:
                    self._led.flash_confirm()
        except Exception:
            logger.exception("RFIDFrontend: LED farewell animation failed")
        # Stop remaining progress updater
        self._stop_progress_updater()
        # Stop standby comet
        try:
            if self._led and getattr(self._led, '_enabled', False):
                self._led.stop_standby_comet()
        except Exception:
            pass
        # Allow farewell sound to play before shutdown to avoid SEGV in teardown
        try:
            time.sleep(3)
        except Exception:
            pass
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

    def _start_progress_updater(self) -> None:
        if self._progress_thread and self._progress_thread.is_alive():
            return
        self._progress_stop.clear()
        def _run():
            last_state = None
            while not self._progress_stop.is_set():
                try:
                    if self._led and getattr(self._led, '_enabled', False) and self._led_cfg.get("remaining") and self.core is not None:
                        state = self.core.playback.get_state().get()

                        # Act only on state changes to avoid repeated start/stop calls
                        if state != last_state:
                            try:
                                if state == "playing":
                                    # Stop idle comet and paused animation when playback starts
                                    try:
                                        self._led.stop_standby_comet()
                                    except Exception:
                                        logger.exception("Failed to stop standby comet on play")
                                    try:
                                        self._led.stop_paused_sweep()
                                    except Exception:
                                        logger.exception("Failed to stop paused sweep on play")
                                    # Immediately update LEDs to show correct remaining progress
                                    try:
                                        cp = self.core.playback.get_current_tl_track().get()
                                        pos_ms = self.core.playback.get_time_position().get()
                                        length_ms = None
                                        if cp and cp.track and cp.track.length:
                                            length_ms = int(cp.track.length)
                                        if length_ms and length_ms > 0:
                                            remain_ratio = max(0.0, min(1.0, 1.0 - (pos_ms/float(length_ms))))
                                            self._led.remaining_progress(remain_ratio, color=(255,255,255))
                                    except Exception:
                                        logger.exception("Failed to update remaining progress on resume")
                                elif state == "paused":
                                    # Stop standby comet and remaining progress, start paused animation
                                    try:
                                        self._led.stop_standby_comet()
                                    except Exception:
                                        pass
                                    # Calculate current remain LEDs for paused animation
                                    try:
                                        cp = self.core.playback.get_current_tl_track().get()
                                        pos_ms = self.core.playback.get_time_position().get()
                                        length_ms = None
                                        if cp and cp.track and cp.track.length:
                                            length_ms = int(cp.track.length)
                                        if length_ms and length_ms > 0:
                                            remain_ratio = max(0.0, min(1.0, 1.0 - (pos_ms/float(length_ms))))
                                            remain_leds = int(round(self._led._led_count * remain_ratio))
                                            self._led.start_paused_sweep(remain_leds)
                                    except Exception:
                                        logger.exception("Failed to start paused sweep")
                                else:
                                    # Stopped: stop paused animation, restart idle comet
                                    try:
                                        self._led.stop_paused_sweep()
                                    except Exception:
                                        pass
                                    try:
                                        self._led.start_standby_comet(color=(0,8,0), delay=5.0, trail=2)
                                    except Exception:
                                        logger.exception("Failed to start standby comet on stop")
                            except Exception:
                                logger.exception("Error handling LED animations on state change")
                            last_state = state

                        # Track remaining time when playing or paused
                        if state in ("playing", "paused"):
                            cp = self.core.playback.get_current_tl_track().get()
                            pos_ms = self.core.playback.get_time_position().get()
                            length_ms = None
                            try:
                                if cp and cp.track and cp.track.length:
                                    length_ms = int(cp.track.length)
                            except Exception:
                                length_ms = None
                            if length_ms and length_ms > 0:
                                remain_ratio = max(0.0, min(1.0, 1.0 - (pos_ms/float(length_ms))))
                                remain_leds = int(round(self._led._led_count * remain_ratio))
                                logger.debug(
                                    "Progress updater: pos=%dms len=%dms ratio=%.3f remain_leds=%d",
                                    pos_ms, length_ms, remain_ratio, remain_leds
                                )
                                try:
                                    if state == "playing":
                                        self._led.remaining_progress(remain_ratio, color=(255,255,255))
                                    elif state == "paused":
                                        # Update paused animation remain count
                                        self._led.update_paused_remain(remain_leds)
                                except Exception:
                                    logger.exception("Progress updater: LED update failed")
                        else:
                            # Reset cache when stopped
                            if hasattr(self._led, '_last_remain_count'):
                                logger.debug("Progress updater: clearing cache (state=%s)", state)
                                delattr(self._led, '_last_remain_count')
                    time.sleep(0.2)
                except Exception:
                    time.sleep(0.5)
        self._progress_thread = threading.Thread(target=_run, name="led-progress", daemon=True)
        self._progress_thread.start()

    def _stop_progress_updater(self) -> None:
        try:
            self._progress_stop.set()
        except Exception:
            pass
        # thread will end shortly

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

    def get_led_manager(self) -> Optional[LEDManager]:
        """Return the LED manager instance."""
        return self._led

    # --- Tag handling ---
    def _play_detect_then_execute(self, mapped_uri: str) -> None:
        """Queue detected sound first, then mapped content, and start playback once."""
        if self.core is None:
            logger.warning("Core not available; cannot execute mapping")
            return
        try:
            uri_det = self._sounds.get("detected")
        except Exception:
            uri_det = ""
        try:
            # Handle special commands first BEFORE clearing tracklist
            if mapped_uri == "TOGGLE_PLAY":
                # Toggle current playback state without adding detected sound or clearing tracklist
                state = self.core.playback.get_state().get()
                logger.info("RFIDFrontend: TOGGLE_PLAY - current state: %s", state)
                if state == "playing":
                    self.core.playback.pause().get()
                    logger.info("RFIDFrontend: paused playback")
                elif state == "paused":
                    self.core.playback.resume().get()
                    logger.info("RFIDFrontend: resumed playback")
                else:
                    # If stopped, start playing current tracklist
                    self.core.playback.play().get()
                    logger.info("RFIDFrontend: started playback from stopped")
                return
            
            # For all other actions, clear tracklist
            self.core.tracklist.clear().get()
            if mapped_uri == "STOP":
                # Stop playback immediately; don't queue detected sound
                self.core.playback.stop().get()
                return
            # Add detected sound first if configured
            if uri_det:
                logger.info("RFIDFrontend: queue detected sound: %s", uri_det)
                self.core.tracklist.add(uris=[uri_det]).get()
            # Add mapped content
            logger.info("RFIDFrontend: queue mapped content: %s", mapped_uri)
            # Expand albums/playlists
            if mapped_uri.startswith('spotify:album:') or ':album:' in mapped_uri:
                lookup_result = self.core.library.lookup(uris=[mapped_uri]).get()
                tracks = lookup_result.get(mapped_uri) if lookup_result else None
                if tracks:
                    for track in tracks:
                        self.core.tracklist.add(uris=[track.uri]).get()
                else:
                    self.core.tracklist.add(uris=[mapped_uri]).get()
            elif mapped_uri.startswith('spotify:playlist:') or ':playlist:' in mapped_uri:
                lookup_result = self.core.library.lookup(uris=[mapped_uri]).get()
                tracks = lookup_result.get(mapped_uri) if lookup_result else None
                if tracks:
                    for track in tracks:
                        self.core.tracklist.add(uris=[track.uri]).get()
                else:
                    self.core.tracklist.add(uris=[mapped_uri]).get()
            else:
                self.core.tracklist.add(uris=[mapped_uri]).get()
            # Start playback once; Mopidy will play detected then continue to mapped
            self.core.playback.play().get()
        except Exception:
            logger.exception("RFIDFrontend: queue detected+mapped failed")

    def _execute_mapping(self, uri: str) -> None:
        """Execute a mapping URI: handle special commands and URI types."""
        if self.core is None:
            logger.warning("Core not available; cannot execute mapping")
            return
        if uri == "TOGGLE_PLAY":
            if self.core.playback.get_state().get() == "playing":
                self.core.playback.pause().get()
            else:
                self.core.playback.play().get()
            return
        if uri == "STOP":
            self.core.playback.stop().get()
            return
        logger.info("RFIDFrontend: adding URI to tracklist: %s", uri)
        self.core.tracklist.clear().get()
        # Handle albums/playlists vs tracks
        if uri.startswith('spotify:album:') or ':album:' in uri:
            lookup_result = self.core.library.lookup(uris=[uri]).get()
            if lookup_result and uri in lookup_result:
                tracks = lookup_result[uri]
                if tracks:
                    for track in tracks:
                        self.core.tracklist.add(uris=[track.uri]).get()
                else:
                    logger.warning("Album has no tracks: %s", uri)
            else:
                self.core.tracklist.add(uris=[uri]).get()
        elif uri.startswith('spotify:playlist:') or ':playlist:' in uri:
            lookup_result = self.core.library.lookup(uris=[uri]).get()
            if lookup_result and uri in lookup_result:
                tracks = lookup_result[uri]
                if tracks:
                    for track in tracks:
                        self.core.tracklist.add(uris=[track.uri]).get()
                else:
                    logger.warning("Playlist has no tracks: %s", uri)
            else:
                self.core.tracklist.add(uris=[uri]).get()
        else:
            self.core.tracklist.add(uris=[uri]).get()
        self.core.playback.play().get()

    def _on_tag_detected(self, tag_id: int) -> None:
        """Handle tag detection: map tag -> URI or special commands.

        Supported mapping values:
        - A Mopidy URI: will be added to the tracklist and played.
        - The special string "TOGGLE_PLAY": toggles play/pause.
        - The special string "STOP": stops playback.
        """
        tag_str = str(tag_id)
        logger.info("RFIDFrontend: tag detected: %s", tag_str)
        
        # Determine mapping first to decide confirmation behavior
        mapped_uri = self.get_mapping(tag_str)
        
        # LED detected confirm
        try:
            if self._led and getattr(self._led, '_enabled', False):
                self._led.flash_confirm()
        except Exception:
            logger.exception("LED flash failed")
        
        # Remaining track animation hook (optional)
        try:
            if self._led and self._led_cfg.get("remaining"):
                state = self.core.playback.get_state().get() if self.core else None
                if state == "playing":
                    pass
        except Exception:
            logger.exception("LED remaining animation hook failed")
        
        # Play detected sound (confirmation) only when no mapping exists to avoid playback race
        try:
            if not mapped_uri:
                uri_det = self._sounds.get("detected")
                if uri_det and self.core is not None:
                    logger.info("RFIDFrontend: playing detected sound: %s", uri_det)
                    self.core.tracklist.clear().get()
                    self.core.tracklist.add(uris=[uri_det]).get()
                    self.core.playback.play().get()
        except Exception:
            logger.exception("RFIDFrontend: failed to play detected sound")

        # Broadcast tag event to Web UI
        def _broadcast():
            try:
                from . import http
                # determine action for UI
                if mapped_uri:
                    if mapped_uri == "TOGGLE_PLAY":
                        action = "toggle"
                    elif mapped_uri == "STOP":
                        action = "stop"
                    else:
                        action = "play"
                else:
                    action = "none"
                http.broadcast_event({
                    "event": "tag_scanned",
                    "tag_id": tag_str,
                    "uri": mapped_uri or "",
                    "action": action,
                })
                logger.info("RFIDFrontend: broadcasted tag_scanned event for tag %s (action=%s)", tag_str, action)
            except Exception:
                logger.exception("Failed to broadcast tag event")
        threading.Thread(target=_broadcast, daemon=True).start()

        # Execute mapping if present
        uri = mapped_uri
        if not uri:
            logger.warning("No mapping found for tag %s", tag_str)
            return
        
        if self.core is None:
            logger.warning("Core not available; cannot execute mapping for %s", tag_str)
            return
        
        # Play detected sound together with blink, then continue to mapped track
        try:
            self._play_detect_then_execute(uri)
        except Exception:
            logger.exception("RFIDFrontend: failed detected-then-execute flow")
