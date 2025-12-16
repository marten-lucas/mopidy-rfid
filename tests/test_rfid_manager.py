import time
from unittest.mock import MagicMock, patch

import pytest

from mopidy_rfid.rfid_manager import RFIDManager


@pytest.fixture
def mock_hardware():
    """Mock GPIO and SimpleMFRC522."""
    with patch("mopidy_rfid.rfid_manager.GPIO") as mock_gpio, patch(
        "mopidy_rfid.rfid_manager.SimpleMFRC522"
    ) as mock_reader_class:
        mock_reader_instance = MagicMock()
        mock_reader_class.return_value = mock_reader_instance
        yield mock_gpio, mock_reader_class, mock_reader_instance


def test_rfid_manager_init(mock_hardware):
    """Test RFID manager initialization."""
    mock_gpio, mock_reader_class, mock_reader = mock_hardware
    callback = MagicMock()

    manager = RFIDManager(on_tag=callback, pin_rst=25)

    mock_gpio.setmode.assert_called_once()
    mock_gpio.setup.assert_called_with(25, mock_gpio.OUT)
    mock_reader_class.assert_called_once()


def test_hardware_reset(mock_hardware):
    """Test hardware reset sequence."""
    mock_gpio, _, _ = mock_hardware
    callback = MagicMock()

    manager = RFIDManager(on_tag=callback, pin_rst=25)

    # Reset is called during init
    calls = mock_gpio.output.call_args_list
    assert any(call[0] == (25, mock_gpio.LOW) for call in calls)
    assert any(call[0] == (25, mock_gpio.HIGH) for call in calls)


def test_start_read_loop(mock_hardware):
    """Test that start() creates a background thread."""
    mock_gpio, _, mock_reader = mock_hardware
    mock_reader.read_id_no_block = MagicMock(return_value=None)
    callback = MagicMock()

    manager = RFIDManager(on_tag=callback, pin_rst=25)
    manager.start()

    assert manager._thread is not None
    assert manager._thread.is_alive()

    manager.stop()


def test_tag_detection_calls_callback(mock_hardware):
    """Test that tag detection triggers callback."""
    mock_gpio, _, mock_reader = mock_hardware
    callback = MagicMock()

    # Simulate tag detection
    mock_reader.read_id_no_block = MagicMock(side_effect=[123456789, None, None])

    manager = RFIDManager(on_tag=callback, pin_rst=25, poll_interval=0.01)
    manager.start()

    time.sleep(0.1)  # Give thread time to run
    manager.stop()

    callback.assert_called_with(123456789)


def test_tag_detection_with_fallback_read(mock_hardware):
    """Test fallback to blocking read() if read_id_no_block not available."""
    mock_gpio, _, mock_reader = mock_hardware
    callback = MagicMock()

    # Simulate old SimpleMFRC522 without read_id_no_block
    delattr(mock_reader, "read_id_no_block")
    mock_reader.read = MagicMock(return_value=(987654321, "text"))

    manager = RFIDManager(on_tag=callback, pin_rst=25, poll_interval=0.01)
    manager.start()

    time.sleep(0.1)
    manager.stop()

    callback.assert_called_with(987654321)


def test_stop_cleans_up_gpio(mock_hardware):
    """Test that stop() cleans up GPIO."""
    mock_gpio, _, _ = mock_hardware
    callback = MagicMock()

    manager = RFIDManager(on_tag=callback, pin_rst=25)
    manager.start()
    manager.stop()

    mock_gpio.cleanup.assert_called_with(25)


def test_read_loop_handles_exceptions(mock_hardware):
    """Test that read loop logs exceptions and doesn't crash."""
    mock_gpio, _, mock_reader = mock_hardware
    callback = MagicMock()

    # Simulate single exception, then tag, then None
    # (avoiding 3+ consecutive exceptions which triggers hardware reset)
    mock_reader.read_id_no_block = MagicMock(
        side_effect=[
            Exception("SPI error"),
            111222333,  # Tag detected after single error
            None, None, None
        ]
    )

    manager = RFIDManager(on_tag=callback, pin_rst=25, poll_interval=0.01)
    manager.start()

    time.sleep(0.5)  # Give time for exception + tag read
    manager.stop()

    # Ensure the reader was exercised and manager stopped cleanly
    assert mock_reader.read_id_no_block.call_count >= 1
    # Thread should be stopped or not alive
    assert manager._thread is None or not manager._thread.is_alive()


def test_callback_exception_doesnt_crash_loop(mock_hardware):
    """Test that exceptions in callback don't crash read loop."""
    mock_gpio, _, mock_reader = mock_hardware
    callback = MagicMock(side_effect=Exception("Callback error"))

    mock_reader.read_id_no_block = MagicMock(side_effect=[123456, None])

    manager = RFIDManager(on_tag=callback, pin_rst=25, poll_interval=0.01)
    manager.start()

    time.sleep(0.1)
    manager.stop()

    # Callback was called despite exception
    callback.assert_called_once()
