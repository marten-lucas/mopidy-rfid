from __future__ import annotations

import logging
import threading
import time
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
        strip = self._get_strip()
        count = self._get_count()
        if not strip:
            return
        self._apply_brightness()
        try:
            remain_ratio = max(0.0, min(1.0, remain_ratio))
            remain_leds = int(round(count * remain_ratio))
            for i in range(count):
                strip.setPixelColor(i, self._color(color) if i < remain_leds else self._color((0, 0, 0)))
            strip.show()
        except Exception:
            pass

    # helpers
    def _set_upto(self, idx: int, color):
        for j in range(self.led_count):
            if j <= idx:
                self.strip.setPixelColor(j, self._color_tuple(color))
            else:
                self.strip.setPixelColor(j, self._color_tuple((0,0,0)))
        self.strip.show()

    def _color_tuple(self, rgb):
        # Convert (r,g,b) to library color; assume strip.Color exists
        try:
            from rpi_ws281x import Color
            r,g,b = rgb
            return Color(r, g, b)
        except Exception:
            return 0
