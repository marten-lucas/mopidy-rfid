import os
import tempfile
from pathlib import Path

import pytest

from mopidy_rfid.mappings_db import MappingsDB


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_mappings.db")
        yield db_path


def test_db_creation(temp_db):
    """Test that database file is created."""
    db = MappingsDB(temp_db)
    assert Path(temp_db).exists()


def test_set_and_get_mapping(temp_db):
    """Test setting and retrieving a mapping."""
    db = MappingsDB(temp_db)
    db.set("123456", "spotify:track:test")
    result = db.get("123456")
    assert result == "spotify:track:test"


def test_get_nonexistent_mapping(temp_db):
    """Test retrieving a non-existent mapping returns None."""
    db = MappingsDB(temp_db)
    result = db.get("999999")
    assert result is None


def test_update_existing_mapping(temp_db):
    """Test updating an existing mapping."""
    db = MappingsDB(temp_db)
    db.set("123456", "spotify:track:old")
    db.set("123456", "spotify:track:new")
    result = db.get("123456")
    assert result == "spotify:track:new"


def test_delete_mapping(temp_db):
    """Test deleting a mapping."""
    db = MappingsDB(temp_db)
    db.set("123456", "spotify:track:test")
    deleted = db.delete("123456")
    assert deleted is True
    result = db.get("123456")
    assert result is None


def test_delete_nonexistent_mapping(temp_db):
    """Test deleting a non-existent mapping."""
    db = MappingsDB(temp_db)
    deleted = db.delete("999999")
    assert deleted is False


def test_list_all_mappings(temp_db):
    """Test listing all mappings."""
    db = MappingsDB(temp_db)
    db.set("111", "uri1")
    db.set("222", "uri2")
    db.set("333", "uri3")
    all_mappings = db.list_all()
    assert len(all_mappings) == 3
    assert all_mappings["111"] == "uri1"
    assert all_mappings["222"] == "uri2"
    assert all_mappings["333"] == "uri3"


def test_list_all_empty(temp_db):
    """Test listing all mappings when database is empty."""
    db = MappingsDB(temp_db)
    all_mappings = db.list_all()
    assert all_mappings == {}


def test_special_characters_in_tag(temp_db):
    """Test handling special characters in tag IDs."""
    db = MappingsDB(temp_db)
    db.set("tag-with-dashes", "uri:test")
    db.set("tag_with_underscores", "uri:test2")
    assert db.get("tag-with-dashes") == "uri:test"
    assert db.get("tag_with_underscores") == "uri:test2"


def test_long_uri(temp_db):
    """Test handling very long URIs."""
    db = MappingsDB(temp_db)
    long_uri = "spotify:track:" + "a" * 1000
    db.set("123", long_uri)
    assert db.get("123") == long_uri


def test_default_db_path():
    """Test that default path uses ~/.config/mopidy-rfid/mappings.db."""
    db = MappingsDB()
    expected_path = os.path.expanduser("~/.config/mopidy-rfid/mappings.db")
    assert db._path == expected_path
