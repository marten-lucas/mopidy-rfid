from __future__ import annotations

import json
import os
from typing import Dict, Optional

DEFAULT_PATH = os.path.expanduser("~/.config/mopidy-rfid/led.json")

class LedConfig:
    def __init__(self, path: Optional[str] = None) -> None:
        self._path = os.path.expanduser(path or DEFAULT_PATH)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data: Dict[str, bool] = {
            "welcome": True,
            "farewell": True,
            "remaining": False,
        }
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                    if isinstance(obj, dict):
                        for k in list(self._data.keys()):
                            if k in obj:
                                self._data[k] = bool(obj[k])
        except Exception:
            pass

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get_all(self) -> Dict[str, bool]:
        return dict(self._data)

    def set(self, key: str, value: bool) -> None:
        if key in self._data:
            self._data[key] = bool(value)
            self.save()

    def get(self, key: str) -> bool:
        return bool(self._data.get(key, False))
