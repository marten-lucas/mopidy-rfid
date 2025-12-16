from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Make static type checker aware of these names without requiring the packages
    import RPi.GPIO as GPIO  # type: ignore
    import spidev  # type: ignore
    from mfrc522 import SimpleMFRC522  # type: ignore

if not TYPE_CHECKING:
    try:
        import RPi.GPIO as GPIO
    except Exception:
        GPIO = None  # type: ignore

    try:
        import spidev  # noqa: F401 - optionally used by SimpleMFRC522
    except Exception:
        spidev = None  # type: ignore

    try:
        from mfrc522 import SimpleMFRC522
    except Exception:
        SimpleMFRC522 = None  # type: ignore
else:
    # For static type checkers, declare names
    GPIO: Any = None  # type: ignore
    spidev: Any = None  # type: ignore
    SimpleMFRC522: Any = None  # type: ignore

logger = logging.getLogger("mopidy_rfid")


class RFIDManager:
    """Manage RC522 RFID reader with a self-healing background read loop.

    Uses pin 25 (BCM) as RST to hardware-reset the reader when SPI errors
    or timeouts occur. Calls a provided callback with the tag id (int).
    """

    def __init__(self, on_tag: Callable[[int], None], pin_rst: int = 25, poll_interval: float = 0.1) -> None:
        self._on_tag = on_tag
        self._pin_rst = pin_rst
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._reader: Optional[Any] = None

        if GPIO is not None:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self._pin_rst, GPIO.OUT)
                # Ensure reader is awake
                self._hw_reset()
            except Exception:
                logger.exception("RFID: GPIO setup failed")
        else:
            logger.warning("RFID: RPi.GPIO not available; RFID hardware disabled until runtime")

        self._init_reader()

    def _hw_reset(self) -> None:
        if GPIO is None:
            return
        try:
            logger.debug("RFID: performing hardware reset on pin %s", self._pin_rst)
            GPIO.output(self._pin_rst, GPIO.LOW)
            time.sleep(0.1)
            GPIO.output(self._pin_rst, GPIO.HIGH)
            time.sleep(0.1)
        except Exception:
            logger.exception("RFID: failed during hardware reset")

    def _init_reader(self) -> None:
        with self._lock:
            if SimpleMFRC522 is None:
                logger.debug("RFID: SimpleMFRC522 class not available in this environment")
                self._reader = None
                return
            try:
                logger.debug("RFID: initializing SimpleMFRC522 reader")
                self._reader = SimpleMFRC522()
            except Exception:
                logger.exception("RFID: failed to initialize reader, will attempt hardware reset")
                self._hw_reset()
                try:
                    self._reader = SimpleMFRC522()
                except Exception:
                    logger.exception("RFID: re-initialization failed")
                    self._reader = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.debug("RFID: read thread already running")
            return
        if SimpleMFRC522 is None:
            logger.warning("RFID: cannot start read loop; SimpleMFRC522 not available")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop, name="rfid-read-loop", daemon=True)
        self._thread.start()
        logger.info("RFID: read thread started")

    def stop(self) -> None:
        logger.info("RFID: stopping read thread")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if GPIO is not None:
            try:
                GPIO.cleanup(self._pin_rst)
            except Exception:
                logger.exception("RFID: GPIO cleanup failed")

    def _read_loop(self) -> None:
        """Background loop: use read_id_no_block to avoid blocking forever.

        On SPI errors or repeated failures, attempt hardware reset and re-init.
        """
        last_success = time.time()
        consecutive_errors = 0

        while not self._stop_event.is_set():
            try:
                if self._reader is None:
                    self._init_reader()

                if self._reader is None:
                    logger.debug("RFID: reader not available, sleeping before retry")
                    time.sleep(1.0)
                    continue

                # Prefer non-blocking read if available
                read_fn = getattr(self._reader, "read_id_no_block", None)
                if callable(read_fn):
                    tag_id = read_fn()
                else:
                    # Fall back to blocking read with short timeout handling
                    try:
                        tag_id, _ = self._reader.read()
                    except Exception:
                        tag_id = None

                if tag_id is not None:
                    # Safely convert tag_id to int
                    tid: Optional[int]
                    try:
                        tid = int(str(tag_id))
                    except Exception:
                        try:
                            # if bytes, attempt conversion
                            if isinstance(tag_id, (bytes, bytearray)):
                                tid = int.from_bytes(tag_id, "big")
                            else:
                                tid = None
                        except Exception:
                            tid = None
                    if tid is None:
                        logger.warning("RFID: could not convert tag id %r to int", tag_id)
                    else:
                        logger.info("RFID: tag detected: %s", tid)
                        try:
                            self._on_tag(tid)
                        except Exception:
                            logger.exception("RFID: on_tag callback raised an exception")
                        last_success = time.time()
                        consecutive_errors = 0
                        # Small debounce: avoid reading same tag repeatedly
                        time.sleep(1.0)
                else:
                    # No tag present
                    time.sleep(self._poll_interval)

            except Exception:
                consecutive_errors += 1
                logger.exception("RFID: exception in read loop (count=%s)", consecutive_errors)
                # If many consecutive errors, attempt hardware reset and re-init
                if consecutive_errors >= 3 or (time.time() - last_success) > 10:
                    logger.warning("RFID: attempting hardware reset due to errors/timeout")
                    try:
                        self._hw_reset()
                        with self._lock:
                            self._reader = None
                        self._init_reader()
                    except Exception:
                        logger.exception("RFID: reset/re-init attempt failed")
                    consecutive_errors = 0
                time.sleep(0.5)

        logger.info("RFID: read loop exited")
