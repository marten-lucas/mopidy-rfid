from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any, Optional

from typing import TYPE_CHECKING

logger = logging.getLogger("mopidy_rfid")

# Try importing Mopidy APIs, but provide safe fallbacks for static analysis / dev env
try:
    from mopidy import config as mopidy_config  # type: ignore
    from mopidy import ext  # type: ignore
except Exception:  # pragma: no cover - runtime environment may differ
    mopidy_config = None  # type: ignore

    class _ExtFallback:
        class Extension:  # type: ignore
            pass

    ext = _ExtFallback()  # type: ignore


class Extension(ext.Extension):  # type: ignore[name-defined]
    dist_name = "mopidy-rfid"
    ext_name = "rfid"
    version = "0.0.0"

    def get_default_config(self) -> str:
        """Return default configuration content for ext.conf.

        If Mopidy's config reader isn't available (e.g., during local linting),
        fall back to reading the packaged ext.conf manually.
        """
        if mopidy_config is not None:
            try:
                return mopidy_config.read(self.package)  # type: ignore[arg-type]
            except Exception:
                logger.exception("Failed to read default config via mopidy.config.read")
        # Fallback: attempt to load ext.conf from package data
        try:
            data = pkgutil.get_data(__name__, "ext.conf")
            if data:
                return data.decode("utf-8")
        except Exception:
            logger.exception("Failed to read packaged ext.conf")
        return ""

    def get_config_schema(self) -> Any:
        # Try to construct a Mopidy ConfigSchema if available, otherwise return a simple dict
        if mopidy_config is not None:
            schema = mopidy_config.ConfigSchema()
            schema["pin_rst"] = mopidy_config.Integer(minimum=0, maximum=40, default=25)
            schema["pin_button_led"] = mopidy_config.Integer(minimum=0, maximum=40, default=13)
            schema["led_enabled"] = mopidy_config.Boolean(default=True)
            schema["led_pin"] = mopidy_config.Integer(minimum=0, maximum=40, default=12)
            schema["led_count"] = mopidy_config.Integer(minimum=1, default=16)
            schema["led_brightness"] = mopidy_config.Integer(minimum=0, maximum=255, default=60)
            schema["mappings_db_path"] = mopidy_config.Path(optional=True)
            schema["mappings"] = mopidy_config.Dict()
            return schema
        # Fallback for environments without Mopidy:
        return {
            "pin_rst": 25,
            "pin_button_led": 13,
            "led_enabled": True,
            "led_pin": 12,
            "led_count": 16,
            "led_brightness": 60,
            "mappings": {},
        }

    def setup(self, registry: Any) -> None:  # pragma: no cover - runtime only
        try:
            from .frontend import RFIDFrontend
            from .http import factory
            registry.add("frontend", RFIDFrontend)
            registry.add("http:app", {"name": "rfid", "factory": factory})
            logger.info("mopidy-rfid extension setup complete")
        except Exception:
            logger.exception("Failed to register extension with Mopidy registry")
