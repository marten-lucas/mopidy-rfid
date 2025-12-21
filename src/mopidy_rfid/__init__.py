from __future__ import annotations

import logging
import pathlib
from typing import Any

from mopidy import config as mopidy_config
from mopidy import ext

logger = logging.getLogger(__name__)

class Extension(ext.Extension):
    dist_name = "mopidy-rfid"
    ext_name = "rfid"
    version = "0.1.0"

    def get_default_config(self) -> str:
        # Sicherer Pfad zur ext.conf
        conf_file = pathlib.Path(__file__).parent / "ext.conf"
        try:
            return conf_file.read_text()
        except FileNotFoundError:
            logger.error(f"RFID extension: ext.conf not found at {conf_file}")
            return ""

    def get_config_schema(self) -> mopidy_config.ConfigSchema:
        schema = mopidy_config.ConfigSchema(self.ext_name)
        
        # Standard Mopidy-Option
        schema["enabled"] = mopidy_config.Boolean()
        
        # Hardware-Pins
        schema["pin_rst"] = mopidy_config.Integer(minimum=0, maximum=40)
        schema["pin_button_led"] = mopidy_config.Integer(minimum=0, maximum=40)
        
        # LED Einstellungen
        schema["led_enabled"] = mopidy_config.Boolean()
        schema["led_pin"] = mopidy_config.Integer(minimum=0, maximum=40)
        schema["led_count"] = mopidy_config.Integer(minimum=1)
        schema["led_brightness"] = mopidy_config.Integer(minimum=0, maximum=255)
        schema["led_idle_brightness"] = mopidy_config.Integer(minimum=0, maximum=255)
        
        # Datenbank Pfad
        schema["mappings_db_path"] = mopidy_config.Path(optional=True)
        
        return schema

    def setup(self, registry: Any) -> None:
        # 1. Registrierung des Frontends (Hintergrund-Logik)
        from .frontend import RFIDFrontend
        registry.add("frontend", RFIDFrontend)

        # 2. Registrierung der Web-API (Tornado App)
        try:
            from .http import factory
            registry.add("http:app", {
                "name": self.ext_name,
                "factory": factory
            })
            logger.info("RFID extension: HTTP API factory registered")
        except (ImportError, AttributeError):
            logger.warning("RFID extension: HTTP factory not found, API disabled")

        logger.info("RFID extension: Setup complete")

    def get_bundle_dir(self) -> str:
        # Das hier macht die Extension unter :6680/rfid/ sichtbar
        bundle_dir = pathlib.Path(__file__).parent / "web"
        if not bundle_dir.exists():
            logger.warning(f"RFID extension: Web bundle directory not found at {bundle_dir}")
        return str(bundle_dir)