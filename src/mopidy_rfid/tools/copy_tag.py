"""Interactive helper to copy an RFID tag's stored data.

Uses the same configuration section (`rfid`) from `ext.conf` as
`rfid_manager.py` (notably `pin_rst`) and attempts a hardware reset
before accessing the reader. If the RFID libraries aren't available,
falls back to a simulated mode where the user can paste data.

Usage: run this module directly. It will prompt to read a source tag
and then to write the captured data to a destination tag.
"""
from __future__ import annotations

import configparser
import logging
import sys
import time
from typing import Optional

try:
    # Python 3.9+: importlib.resources.read_text
    from importlib import resources
except Exception:  # pragma: no cover - fallback
    resources = None  # type: ignore

logger = logging.getLogger("mopidy_rfid.copy_tag")


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_dict({"rfid": {}})
    try:
        if resources is not None:
            try:
                txt = resources.read_text("mopidy_rfid", "ext.conf")
                cfg.read_string(txt)
                return cfg
            except Exception:
                pass
        # Fallback to package-relative file path
        import os

        here = os.path.dirname(__file__)
        pkg_root = os.path.abspath(os.path.join(here, ".."))
        path = os.path.join(pkg_root, "ext.conf")
        cfg.read(path)
    except Exception:
        logger.exception("Could not read ext.conf; using defaults")
    return cfg


def hw_reset(pin_rst: int) -> None:
    try:
        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin_rst, GPIO.OUT)
        logger.debug("Performing hardware reset on pin %s", pin_rst)
        GPIO.output(pin_rst, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(pin_rst, GPIO.HIGH)
        time.sleep(0.1)
    except Exception:
        logger.exception("Hardware reset failed or RPi.GPIO not available")


def init_reader() -> Optional[object]:
    try:
        from mfrc522 import SimpleMFRC522  # type: ignore

        try:
            return SimpleMFRC522()
        except Exception:
            logger.exception("Failed to initialize SimpleMFRC522")
            return None
    except Exception:
        logger.debug("mfrc522 library not available; entering simulated mode")
        return None


def detect_tag_type_from_lowlevel(reader: object) -> Optional[str]:
    """Best-effort detection of tag type from low-level reader methods.

    Returns a short string describing the tag (e.g. 'uidlen:4') or None.
    This is intentionally conservative and will not attempt invasive operations.
    """
    try:
        low = getattr(reader, "MFRC522", None) or getattr(reader, "reader", None) or getattr(reader, "_reader", None)
        if low is None:
            return None

        # Try common anticollision API which often returns (status, uid)
        anticoll = getattr(low, "anticoll", None) or getattr(low, "anticollision", None)
        if callable(anticoll):
            try:
                res = anticoll()
                # res may be (status, uid) or uid directly
                if isinstance(res, tuple) and len(res) >= 2:
                    uid = res[1]
                else:
                    uid = res
                if isinstance(uid, (list, tuple, bytes, bytearray)):
                    return f"uidlen:{len(uid)}"
            except Exception:
                pass

        # Try request API which may return (status, tag_type)
        req = getattr(low, "request", None) or getattr(low, "MFRC522_Request", None)
        if callable(req):
            try:
                # Some implementations expect a mode constant; try without and with common constant
                res = None
                try:
                    res = req()
                except Exception:
                    # try with typical flag value for idle
                    const = getattr(low, "PICC_REQIDL", None) or getattr(low, "REQIDL", None)
                    if const is not None:
                        res = req(const)
                if isinstance(res, tuple) and len(res) >= 2:
                    tag_type = res[1]
                    return f"tagtype:{tag_type}"
            except Exception:
                pass
    except Exception:
        pass
    return None


def read_tag(reader: object) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """Return (tag_id, text, type) where one or more may be None in simulated mode."""
    if reader is None:
        # Simulated: ask user to paste source content
        print("Simulated mode: enter source tag data (or leave empty for no data):")
        txt = input("Source data: ")
        print("Simulated source id (optional):")
        sid = input("Source id (number): ")
        ttype = input("Simulated tag type (optional): ")
        try:
            sid_i = int(sid) if sid.strip() else None
        except Exception:
            sid_i = None
        return sid_i, txt or None, (ttype or None)

    # Real reader: call read() and try to interpret values
    try:
        print("Waiting for tag... place it on the reader.")
        result = reader.read()
    except Exception:
        logger.exception("Reader.read() failed")
        return None, None, None

    # result often is (id, text) but some libs differ; detect
    try:
        if isinstance(result, tuple) and len(result) == 2:
            a, b = result
            raw_id = None
            raw_text = None
            if isinstance(a, int):
                raw_id = a
                raw_text = b
            elif isinstance(b, int):
                raw_id = b
                raw_text = a
            else:
                # Try to coerce
                try:
                    raw_id = int(a)
                    raw_text = str(b)
                except Exception:
                    raw_id = None
                    raw_text = str(a) if a is not None else None
            ttype = detect_tag_type_from_lowlevel(reader)
            return raw_id, raw_text, ttype
        # Unexpected single value
        if isinstance(result, int):
            ttype = detect_tag_type_from_lowlevel(reader)
            return result, None, ttype
        ttype = detect_tag_type_from_lowlevel(reader)
        return None, str(result), ttype
    except Exception:
        logger.exception("Could not parse read() result")
        return None, None, None


def write_tag(reader: object, text: Optional[str]) -> bool:
    if reader is None:
        print("Simulated mode: writing data to target (no hardware).")
        print("Written data:", repr(text))
        return True

    try:
        if text is None:
            text = ""
        # Common SimpleMFRC522 API: write(text)
        try:
            reader.write(text)
            return True
        except TypeError:
            # Some variants expect (text, uid) — try the simpler call first
            reader.write(str(text))
            return True
    except Exception:
        logger.exception("Failed to write to tag")
        return False


def main() -> int:
    cfg = load_config()
    pin_rst = 25
    try:
        pin_rst = cfg.getint("rfid", "pin_rst", fallback=25)
    except Exception:
        pass

    print("Using reset pin (BCM):", pin_rst)
    print("Attempting hardware reset (if supported)...")
    hw_reset(pin_rst)

    reader = init_reader()
    if reader is None:
        print("RFID reader not available; running in simulated mode.")

    # Inform the user about tag type detection limitations
    print("Hinweis: Die Tag‑Typ‑Erkennung ist Best‑Effort.")
    print("Verschiedene Chiptypen (z.B. MIFARE Classic, Ultralight, NTAG) unterscheiden sich in UID‑Länge, Speicherstruktur und Schreibverhalten.")
    print("Bei inkompatiblen Tag‑Typen kann das Schreiben oder die Verifikation fehlschlagen.")
    print("Das Skript behandelt 'magic' und 'writable' als Wildcards und ignoriert diese beim Typ‑Vergleich.")

    input("Step 1: place the SOURCE tag on the reader, then press Enter...")
    sid, stext, stype = read_tag(reader)
    print("Source tag read:")
    print("  id:", sid)
    print("  data:", repr(stext))
    print("  type:", stype)

    # Write to target
    input("Remove the source tag. Then place the TARGET tag on the reader and press Enter to write...")
    ok = write_tag(reader, stext)
    if not ok:
        print("Write failed. See logs for details.")
        return 2

    # Verify by read-back: let the user present the target tag for verification
    max_retries = 2
    for attempt in range(1, max_retries + 2):
        input("Place the TARGET tag on the reader for verification, then press Enter...")
        vid, vtext, vtype = read_tag(reader)

        match_id = sid is None or vid is None or sid == vid
        match_data = (stext == vtext)
        # Treat 'magic' and 'writable' as wildcards to ignore
        def types_match(a: Optional[str], b: Optional[str]) -> bool:
            if a is None or b is None:
                return True
            if a in ("magic", "writable") or b in ("magic", "writable"):
                return True
            return a == b

        def aggressive_incompatible(a: Optional[str], b: Optional[str]) -> Optional[str]:
            """Return a short reason string if types would be incompatible under
            an aggressive check (strict equality / uid length), otherwise None.
            """
            if a is None or b is None:
                return None
            if a == b:
                return None
            # uidlen:N format
            if a.startswith("uidlen:") and b.startswith("uidlen:"):
                try:
                    na = int(a.split(":", 1)[1])
                    nb = int(b.split(":", 1)[1])
                    if na != nb:
                        return f"uid length differs ({na} vs {nb})"
                except Exception:
                    return f"different uid descriptors: {a} vs {b}"
            # tagtype:... format or other differences
            return f"different types: {a} vs {b}"

        match_type = types_match(stype, vtype)

        # If types differ in a way a strict/aggressive check wouldn't accept,
        # inform the user even if the loose verification succeeded/failed.
        aggr_reason = aggressive_incompatible(stype, vtype)
        if aggr_reason:
            print("Hinweis: Bei einer aggressiveren Typprüfung würde dies als inkompatibel gelten:", aggr_reason)

        if match_id and match_data and match_type:
            print("Verification successful: target matches source.")
            return 0

        print("Verification failed.")
        print("  expected id:", sid, "got:", vid)
        print("  expected type:", stype, "got:", vtype)
        print("  expected data:", repr(stext))
        print("  read data:", repr(vtext))

        if attempt > max_retries:
            print("Maximum verification attempts reached. Aborting.")
            return 3

        ans = input("Retry writing to the target and verify again? [y/N]: ").strip().lower()
        if not ans.startswith("y"):
            print("Aborted by user.")
            return 4

        # Retry write
        input("Place the TARGET tag on the reader to write and press Enter...")
        ok = write_tag(reader, stext)
        if not ok:
            print("Write failed during retry. See logs.")
            return 5
        # small pause before verifying again
        time.sleep(0.5)

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
