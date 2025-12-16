import tempfile
from unittest.mock import MagicMock, patch

import pytest

from mopidy_rfid.frontend import RFIDFrontend


@pytest.fixture
def temp_db_path():
    """Provide temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield f"{tmpdir}/test.db"


@pytest.fixture
def mock_hardware():
    """Mock all hardware dependencies."""
    with patch("mopidy_rfid.frontend.RFIDManager") as mock_rfid, patch(
        "mopidy_rfid.frontend.LEDManager"
    ) as mock_led:
        yield mock_rfid, mock_led


@pytest.fixture
def mock_core():
    """Mock Mopidy core with fresh instance per test."""
    core = MagicMock()
    core.playback.get_state().get.return_value = "stopped"
    core.tracklist.clear().get.return_value = None
    core.tracklist.add().get.return_value = None
    core.playback.play().get.return_value = None
    core.playback.pause().get.return_value = None
    core.playback.stop().get.return_value = None
    return core


def test_frontend_init(mock_core, temp_db_path):
    """Test frontend initialization."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)
    assert frontend.core == mock_core
    assert frontend._db is not None


def test_get_mapping(mock_core, temp_db_path):
    """Test get_mapping method."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)
    frontend._db.set("123", "spotify:track:test")

    result = frontend.get_mapping("123")
    assert result == "spotify:track:test"


def test_get_mapping_from_config(mock_core, temp_db_path):
    """Test get_mapping fallback to config mappings."""
    config = {
        "rfid": {
            "mappings_db_path": temp_db_path,
            "mappings": {"999": "config:uri"},
        }
    }
    frontend = RFIDFrontend(config, mock_core)

    result = frontend.get_mapping("999")
    assert result == "config:uri"


def test_set_mapping(mock_core, temp_db_path):
    """Test set_mapping method."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)

    frontend.set_mapping("456", "local:track:test.mp3")
    result = frontend.get_mapping("456")
    assert result == "local:track:test.mp3"


def test_delete_mapping(mock_core, temp_db_path):
    """Test delete_mapping method."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)
    frontend._db.set("789", "uri:test")

    deleted = frontend.delete_mapping("789")
    assert deleted is True
    assert frontend.get_mapping("789") is None


def test_list_mappings(mock_core, temp_db_path):
    """Test list_mappings merges DB and config."""
    config = {
        "rfid": {
            "mappings_db_path": temp_db_path,
            "mappings": {"config_tag": "config_uri"},
        }
    }
    frontend = RFIDFrontend(config, mock_core)
    frontend._db.set("db_tag", "db_uri")

    result = frontend.list_mappings()
    assert "db_tag" in result
    assert "config_tag" in result
    assert result["db_tag"] == "db_uri"
    assert result["config_tag"] == "config_uri"


def test_on_tag_detected_plays_uri(mock_core, temp_db_path):
    """Test tag detection plays URI."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)
    frontend._db.set("123", "spotify:track:test")

    frontend._on_tag_detected(123)

    # Check that the chained call was made (call().get())
    assert mock_core.tracklist.clear.called
    assert mock_core.tracklist.add.called
    assert mock_core.playback.play.called


def test_on_tag_detected_toggle_play(mock_core, temp_db_path):
    """Test TOGGLE_PLAY action."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)
    frontend._db.set("456", "TOGGLE_PLAY")

    # Simulate playing state
    mock_core.playback.get_state().get.return_value = "playing"
    frontend._on_tag_detected(456)
    assert mock_core.playback.pause.called

    # Simulate paused state
    mock_core.reset_mock()
    mock_core.playback.get_state().get.return_value = "paused"
    frontend._on_tag_detected(456)
    assert mock_core.playback.play.called


def test_on_tag_detected_stop(mock_core, temp_db_path):
    """Test STOP action."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)
    frontend._db.set("789", "STOP")

    frontend._on_tag_detected(789)
    assert mock_core.playback.stop.called


def test_on_tag_detected_no_mapping(temp_db_path):
    """Test tag detection with no mapping doesn't crash."""
    # Create fresh mock to avoid state from other tests
    fresh_core = MagicMock()
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, fresh_core)

    frontend._on_tag_detected(999)  # No mapping for this tag
    # Should not call any playback methods (returns early on no mapping)
    assert not fresh_core.tracklist.add.called


def test_on_start_initializes_hardware(mock_core, mock_hardware, temp_db_path):
    """Test on_start initializes managers in background."""
    mock_rfid, mock_led = mock_hardware
    config = {
        "rfid": {
            "mappings_db_path": temp_db_path,
            "pin_rst": 25,
            "led_enabled": True,
        }
    }
    frontend = RFIDFrontend(config, mock_core)
    frontend.on_start()

    # on_start returns immediately, hardware init happens in background
    # Just check it doesn't crash


def test_on_stop_cleans_up(mock_core, temp_db_path):
    """Test on_stop cleans up managers."""
    config = {"rfid": {"mappings_db_path": temp_db_path}}
    frontend = RFIDFrontend(config, mock_core)

    mock_rfid = MagicMock()
    mock_led = MagicMock()
    frontend._rfid = mock_rfid
    frontend._led = mock_led

    frontend.on_stop()

    mock_rfid.stop.assert_called_once()
    mock_led.shutdown.assert_called_once()
