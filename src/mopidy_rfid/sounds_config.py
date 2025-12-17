from __future__ import annotations

import json
import os
from typing import Dict, Optional

DEFAULT_PATH = os.path.expanduser("~/.config/mopidy-rfid/sounds.json")

class SoundsConfig:
    def __init__(self, path: Optional[str] = None) -> None:
        self._path = os.path.expanduser(path or DEFAULT_PATH)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data: Dict[str, str] = {"welcome": "", "farewell": "", "detected": ""}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                    if isinstance(obj, dict):
                        self._data.update({k: str(v) for k, v in obj.items() if k in self._data})
        except Exception:
            pass

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get_all(self) -> Dict[str, str]:
        return dict(self._data)

    def set(self, key: str, uri: str) -> None:
        if key in self._data:
            self._data[key] = uri
            self.save()

    def get(self, key: str) -> str:
        return self._data.get(key, "")
