from __future__ import annotations

import json
import os
from typing import Dict, Optional

DEFAULT_PATH = os.path.expanduser("~/.config/mopidy-rfid/led.json")

class LedConfig:
    def __init__(self, path: Optional[str] = None) -> None:
        self._path = os.path.expanduser(path or DEFAULT_PATH)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        # Store booleans and brightness values together
        self._data: Dict[str, object] = {
            "welcome": True,
            "farewell": True,
            "remaining": True,
            "brightness": 60,
            "idle_brightness": 10,
        }
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                    if isinstance(obj, dict):
                        # Booleans
                        for k in ("welcome", "farewell", "remaining"):
                            if k in obj:
                                self._data[k] = bool(obj[k])
                        # Brightness values
                        if "brightness" in obj:
                            try:
                                b = int(obj["brightness"])  # type: ignore[arg-type]
                                self._data["brightness"] = max(0, min(255, b))
                            except Exception:
                                pass
                        if "idle_brightness" in obj:
                            try:
                                ib = int(obj["idle_brightness"])  # type: ignore[arg-type]
                                self._data["idle_brightness"] = max(0, min(255, ib))
                            except Exception:
                                pass
        except Exception:
            pass

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get_all(self) -> Dict[str, object]:
        return dict(self._data)

    def set(self, key: str, value: bool) -> None:
        if key in ("welcome", "farewell", "remaining"):
            self._data[key] = bool(value)
            self.save()

    def get(self, key: str) -> bool:
        if key in ("welcome", "farewell", "remaining"):
            return bool(self._data.get(key, False))
        return False

    # Brightness helpers
    def get_brightness(self) -> int:
        try:
            return int(self._data.get("brightness", 60))
        except Exception:
            return 60

    def set_brightness(self, value: int) -> None:
        try:
            v = max(0, min(255, int(value)))
            self._data["brightness"] = v
            self.save()
        except Exception:
            pass

    def get_idle_brightness(self) -> int:
        try:
            return int(self._data.get("idle_brightness", 10))
        except Exception:
            return 10

    def set_idle_brightness(self, value: int) -> None:
        try:
            v = max(0, min(255, int(value)))
            self._data["idle_brightness"] = v
            self.save()
        except Exception:
            pass
