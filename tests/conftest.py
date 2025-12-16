import sys
from unittest.mock import MagicMock

import pytest


# Mock hardware modules for testing environments without RPi hardware
@pytest.fixture(autouse=True)
def mock_hardware_modules():
    """Auto-mock hardware modules that may not be available."""
    # Only mock if not already imported
    if "RPi.GPIO" not in sys.modules:
        sys.modules["RPi.GPIO"] = MagicMock()
    if "spidev" not in sys.modules:
        sys.modules["spidev"] = MagicMock()
    if "mfrc522" not in sys.modules:
        sys.modules["mfrc522"] = MagicMock()
    if "rpi_ws281x" not in sys.modules:
        sys.modules["rpi_ws281x"] = MagicMock()

    yield

    # Cleanup after tests (optional)
