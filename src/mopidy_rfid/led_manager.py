from __future__ import annotations

import logging
import threading
import time
import math
from typing import Tuple, Optional, Any

# Defensive import for GPIO and rpi_ws281x
try:
    import RPi.GPIO as GPIO
except Exception:  # pragma: no cover - hardware-specific
    GPIO = None  # type: ignore

try:
    from rpi_ws281x import PixelStrip, Color  # type: ignore
except Exception:  # pragma: no cover - hardware-specific
    PixelStrip = None  # type: ignore
    Color = None  # type: ignore

logger = logging.getLogger("mopidy_rfid")


class LEDManager:
    """Manage a WS2812B LED ring and a power-button LED.

    The ring is optional and only initialized when led_enabled is True and
    the rpi_ws281x library is available.
    """

    def __init__(
        self,
        led_enabled: bool = True,
        led_pin: int = 12,
        led_count: int = 16,
        brightness: int = 60,
        button_pin: int = 13,
    ) -> None:
        self._enabled = led_enabled and PixelStrip is not None
        self._led_pin = led_pin
        self._led_count = led_count
        self._brightness = brightness
        self._button_pin = button_pin
        self._lock = threading.Lock()
        self._strip: Optional[Any] = None

        if GPIO is not None:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self._button_pin, GPIO.OUT)
                GPIO.output(self._button_pin, GPIO.LOW)
            except Exception:
                logger.exception("LED: GPIO setup failed for button pin %s", self._button_pin)
        else:
            logger.warning("LED: RPi.GPIO not available; button LED disabled until runtime")

        if self._enabled:
            if PixelStrip is None or Color is None:
                logger.warning("LED: rpi_ws281x not available; disabling LED ring")
                self._enabled = False
                return
            try:
                logger.debug("LED: initializing PixelStrip on pin %s", led_pin)
                self._strip = PixelStrip(self._led_count, self._led_pin, 800000, 10, False, self._brightness, 0)
                self._strip.begin()
            except Exception:
                logger.exception("LED: failed to initialize PixelStrip; disabling LED ring")
                self._enabled = False
                self._strip = None

    def show_ready(self, color: Tuple[int, int, int] = (0, 50, 0)) -> None:
        """Light the entire ring with a steady color."""
        if not self._enabled or self._strip is None or Color is None:
            logger.debug("LED: show_ready called but LED ring disabled")
            return
        with self._lock:
            r, g, b = color
            col = Color(r, g, b)
            for i in range(self._strip.numPixels()):
                self._strip.setPixelColor(i, col)
            try:
                self._strip.show()
            except Exception:
                logger.exception("LED: failed to show ready color")

    def flash_confirm(self, color: Tuple[int, int, int] = (0, 255, 0), duration: float = 0.25) -> None:
        """Flash the ring briefly to confirm a tag detection."""
        if not self._enabled or self._strip is None or Color is None:
            logger.debug("LED: flash_confirm called but LED ring disabled")
            return

        def _flash() -> None:
            with self._lock:
                try:
                    # Save current state
                    saved = [self._strip.getPixelColor(i) for i in range(self._strip.numPixels())]
                    col = Color(*color)
                    for i in range(self._strip.numPixels()):
                        self._strip.setPixelColor(i, col)
                    self._strip.show()
                    time.sleep(duration)
                    for i, v in enumerate(saved):
                        self._strip.setPixelColor(i, v)
                    self._strip.show()
                except Exception:
                    logger.exception("LED: flash_confirm failed")

        t = threading.Thread(target=_flash, name="led-flash", daemon=True)
        t.start()

    def set_button_led(self, on: bool) -> None:
        """Set the small power button LED on GPIO pin."""
        if GPIO is None:
            logger.debug("LED: set_button_led called but RPi.GPIO not available")
            return
        try:
            GPIO.output(self._button_pin, GPIO.HIGH if on else GPIO.LOW)
        except Exception:
            logger.exception("LED: failed to set button LED state to %s", on)

    def shutdown(self) -> None:
        try:
            logger.info("LED: shutting down")
            self.set_button_led(False)
            if self._enabled and self._strip is not None and Color is not None:
                with self._lock:
                    for i in range(self._strip.numPixels()):
                        self._strip.setPixelColor(i, Color(0, 0, 0))
                    try:
                        self._strip.show()
                    except Exception:
                        logger.exception("LED: failed to clear strip on shutdown")
            if GPIO is not None:
                try:
                    GPIO.cleanup(self._button_pin)
                except Exception:
                    logger.exception("LED: GPIO cleanup failed")
        except Exception:
            logger.exception("LED: unexpected error during shutdown")

    def _get_strip(self):
        return getattr(self, '_strip', None) or getattr(self, 'strip', None)

    def _get_count(self):
        return getattr(self, 'led_count', None) or getattr(self, '_count', None) or 16

    def _color(self, rgb):
        try:
            from rpi_ws281x import Color
            r, g, b = rgb
            return Color(r, g, b)
        except Exception:
            return 0

    def _fill(self, strip, count, rgb):
        col = self._color(rgb)
        for i in range(count):
            strip.setPixelColor(i, col)
        strip.show()

    def _off(self, strip, count):
        col = self._color((0, 0, 0))
        for i in range(count):
            strip.setPixelColor(i, col)
        strip.show()

    def _apply_brightness(self):
        try:
            strip = self._get_strip()
            if not strip:
                return
            b = getattr(self, 'brightness', None) or getattr(self, '_brightness', None)
            if b is not None:
                try:
                    strip.setBrightness(int(b))
                except Exception:
                    pass
        except Exception:
            pass

    def welcome_scan(self, color=(0, 255, 0), delay=0.05):
        strip = self._get_strip()
        count = self._get_count()
        if not strip:
            return
        self._apply_brightness()
        try:
            with self._lock:
                self._off(strip, count)
                time.sleep(0.1)
                for i in range(count):
                    for j in range(count):
                        strip.setPixelColor(j, self._color(color) if j <= i else self._color((0, 0, 0)))
                    strip.show()
                    time.sleep(delay)
        except Exception:
            pass

    def farewell_scan(self, color=(0, 255, 0), delay=0.05):
        strip = self._get_strip()
        count = self._get_count()
        if not strip:
            return
        self._apply_brightness()
        try:
            with self._lock:
                self._fill(strip, count, color)
                time.sleep(0.1)
                for i in range(count - 1, -1, -1):
                    for j in range(count):
                        strip.setPixelColor(j, self._color(color) if j < i else self._color((0, 0, 0)))
                    strip.show()
                    time.sleep(delay)
                self._off(strip, count)
        except Exception:
            pass

    def remaining_progress(self, remain_ratio: float, color=(255, 255, 255)):
        """Update LED ring to show remaining track time. Only updates when LED count changes.

        Quick early-exit if nothing changed, then acquire lock and re-check before updating
        to avoid race with the standby comet and other animations.
        """
        remain_ratio = max(0.0, min(1.0, remain_ratio))
        count = self._led_count
        remain_leds = int(round(count * remain_ratio))

        # Quick early exit (cheap) before touching the strip
        last_count = getattr(self, '_last_remain_count', None)
        if last_count == remain_leds:
            return

        strip = self._get_strip()
        if not strip:
            return

        # Acquire lock (blocking) to serialize with other animations
        with self._lock:
            # Re-check under lock
            last_count = getattr(self, '_last_remain_count', None)
            if last_count == remain_leds:
                return

            try:
                self._last_remain_count = remain_leds

                # Set all LEDs at once
                for i in range(count):
                    if i < remain_leds:
                        strip.setPixelColor(i, self._color(color))
                    else:
                        strip.setPixelColor(i, self._color((0, 0, 0)))

                # Single show() call to update hardware
                strip.show()
            except Exception:
                logger.exception("LED: remaining_progress failed")

    # Remove obsolete helpers if present
    # (No-op placeholder to signal cleanup to tooling)

    # Standby comet animation (very low brightness, slow)
    _standby_lock = threading.Lock()
    _standby_stop = None
    _standby_thread = None

    def start_standby_comet(self, color=(0, 8, 0), delay=5.0, trail=2):
        """Start a slow-moving comet animation for standby mode."""
        strip = self._get_strip()
        count = self._get_count()
        if not strip:
            return

        # Use simple flag instead of lock to avoid complexity
        if getattr(self, '_standby_running', False):
            return  # Already running

        self._standby_stop = threading.Event()
        self._standby_running = True
        stop_ev = self._standby_stop

        def _run():
            idx = 0
            off = self._color((0, 0, 0))
            while not stop_ev.is_set():
                try:
                    # Build and show frame atomically under the lock
                    with self._lock:
                        # Clear all
                        for i in range(count):
                            strip.setPixelColor(i, off)
                        # Draw comet head and trail
                        for t in range(trail + 1):
                            pos = (idx - t) % count
                            intensity = max(1, color[1] - t * 2)
                            strip.setPixelColor(pos, self._color((color[0], intensity, color[2])))
                        strip.show()

                    # Move to next position
                    idx = (idx + 1) % count

                    # Wait for delay with responsiveness checks
                    for _ in range(int(delay * 2)):
                        if stop_ev.is_set():
                            break
                        time.sleep(0.5)
                except Exception:
                    time.sleep(0.5)

            # Clean up on exit
            self._standby_running = False

        self._standby_thread = threading.Thread(target=_run, name='led-standby', daemon=True)
        self._standby_thread.start()

    def stop_standby_comet(self):
        """Stop the standby comet animation and clear LEDs."""
        try:
            if hasattr(self, '_standby_stop') and self._standby_stop:
                self._standby_stop.set()
                self._standby_running = False
        except Exception:
            pass

        # Clear the ring
        try:
            strip = self._get_strip()
            count = self._get_count()
            if strip:
                off = self._color((0, 0, 0))
                for i in range(count):
                    strip.setPixelColor(i, off)
                strip.show()
        except Exception:
            pass

    # Fix helper syntax if present
    try:
        def _fix_helper_syntax():
            pass
    except Exception:
        pass

# Correct any lingering syntax in helper loops
# for j in range self.led_count: -> for j in range(self._get_count()):
# Patch any residual bad line literally
# for j in range self.led_count:  # bad
# should be:
# for j in range(self._get_count()):
