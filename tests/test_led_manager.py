from unittest.mock import MagicMock, patch

import pytest

from mopidy_rfid.led_manager import LEDManager


@pytest.fixture
def mock_gpio():
    """Mock RPi.GPIO."""
    with patch("mopidy_rfid.led_manager.GPIO") as mock:
        yield mock


@pytest.fixture
def mock_ws281x():
    """Mock rpi_ws281x."""
    with patch("mopidy_rfid.led_manager.PixelStrip") as mock_strip, patch(
        "mopidy_rfid.led_manager.Color"
    ) as mock_color:
        mock_color.return_value = 0xFF0000
        yield mock_strip, mock_color


def test_led_manager_init_gpio_only(mock_gpio):
    """Test LED manager initialization with GPIO only (no LED ring)."""
    manager = LEDManager(led_enabled=False, button_pin=13)
    mock_gpio.setmode.assert_called_once()
    mock_gpio.setup.assert_called_once_with(13, mock_gpio.OUT)


def test_led_manager_init_with_ring(mock_gpio, mock_ws281x):
    """Test LED manager initialization with LED ring."""
    mock_strip, mock_color = mock_ws281x
    mock_strip_instance = MagicMock()
    mock_strip.return_value = mock_strip_instance

    manager = LEDManager(led_enabled=True, led_pin=12, led_count=16, brightness=60)
    mock_strip.assert_called_once_with(16, 12, 800000, 10, False, 60, 0)
    mock_strip_instance.begin.assert_called_once()


def test_set_button_led_on(mock_gpio):
    """Test turning button LED on."""
    manager = LEDManager(led_enabled=False, button_pin=13)
    manager.set_button_led(True)
    mock_gpio.output.assert_called_with(13, mock_gpio.HIGH)


def test_set_button_led_off(mock_gpio):
    """Test turning button LED off."""
    manager = LEDManager(led_enabled=False, button_pin=13)
    manager.set_button_led(False)
    mock_gpio.output.assert_called_with(13, mock_gpio.LOW)


def test_show_ready(mock_gpio, mock_ws281x):
    """Test show_ready with LED ring."""
    mock_strip, mock_color = mock_ws281x
    mock_strip_instance = MagicMock()
    mock_strip_instance.numPixels.return_value = 16
    mock_strip.return_value = mock_strip_instance

    manager = LEDManager(led_enabled=True, led_count=16)
    manager.show_ready((0, 50, 0))

    mock_color.assert_called_with(0, 50, 0)
    assert mock_strip_instance.setPixelColor.call_count == 16
    mock_strip_instance.show.assert_called_once()


def test_flash_confirm(mock_gpio, mock_ws281x):
    """Test flash_confirm creates background thread."""
    mock_strip, mock_color = mock_ws281x
    mock_strip_instance = MagicMock()
    mock_strip_instance.numPixels.return_value = 16
    mock_strip_instance.getPixelColor.return_value = 0x000000
    mock_strip.return_value = mock_strip_instance

    manager = LEDManager(led_enabled=True, led_count=16)
    manager.flash_confirm((0, 255, 0), duration=0.01)

    # Flash runs in background thread, just check it doesn't crash


def test_shutdown(mock_gpio, mock_ws281x):
    """Test shutdown clears LEDs and cleans up GPIO."""
    mock_strip, mock_color = mock_ws281x
    mock_strip_instance = MagicMock()
    mock_strip_instance.numPixels.return_value = 16
    mock_strip.return_value = mock_strip_instance

    manager = LEDManager(led_enabled=True, button_pin=13)
    manager.shutdown()

    mock_gpio.output.assert_called()  # button LED off
    assert mock_strip_instance.setPixelColor.call_count == 16
    mock_strip_instance.show.assert_called()
    mock_gpio.cleanup.assert_called_with(13)


def test_led_disabled_no_crash(mock_gpio):
    """Test that disabled LED ring doesn't cause crashes."""
    manager = LEDManager(led_enabled=False)
    manager.show_ready()
    manager.flash_confirm()
    manager.shutdown()
    # Should not raise any exceptions
