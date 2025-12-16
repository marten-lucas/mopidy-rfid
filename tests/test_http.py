import json
from unittest.mock import MagicMock, patch

import pytest
import tornado.testing

from mopidy_rfid import http


class TestHTTPHandlers(tornado.testing.AsyncHTTPTestCase):
    """Test HTTP/WebSocket handlers."""

    def get_app(self):
        """Create test application."""
        # Mock frontend actor with proper actor_ref structure
        mock_proxy = MagicMock()
        mock_proxy.list_mappings().get.return_value = {
            "123": "spotify:track:test",
            "456": "TOGGLE_PLAY",
        }
        mock_proxy.set_mapping().get.return_value = None
        mock_proxy.delete_mapping().get.return_value = True

        mock_actor_ref = MagicMock()
        mock_actor_ref.proxy.return_value = mock_proxy

        self.mock_frontend = MagicMock()
        self.mock_frontend.actor_ref = mock_actor_ref

        # Mock core with proper search structure
        mock_track = MagicMock()
        mock_track.uri = "spotify:track:found"
        mock_track.name = "Test Track"
        mock_result = MagicMock()
        mock_result.tracks = [mock_track]
        
        self.mock_core = MagicMock()
        self.mock_core.library.search().get.return_value = [mock_result]

        routes = http.factory({}, self.mock_core)
        # Inject our mock frontend into handlers
        # Routes can be tuples of length 2 or 3 depending on handler
        updated_routes = []
        for route in routes:
            if len(route) == 3:
                pattern, handler_class, init_dict = route
                if "frontend" in init_dict:
                    init_dict["frontend"] = self.mock_frontend
                updated_routes.append((pattern, handler_class, init_dict))
            else:
                updated_routes.append(route)

        return tornado.web.Application(updated_routes)

    def test_get_mappings(self):
        """Test GET /rfid/api/mappings."""
        response = self.fetch("/rfid/api/mappings")
        assert response.code == 200
        data = json.loads(response.body)
        assert "123" in data
        assert data["123"] == "spotify:track:test"

    def test_post_mapping(self):
        """Test POST /rfid/api/mappings."""
        body = json.dumps({"tag": "789", "uri": "local:track:test.mp3"})
        response = self.fetch(
            "/rfid/api/mappings",
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["ok"] is True

    def test_post_mapping_missing_fields(self):
        """Test POST with missing fields returns 400."""
        body = json.dumps({"tag": "789"})  # missing uri
        response = self.fetch(
            "/rfid/api/mappings",
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        assert response.code == 400

    def test_delete_mapping(self):
        """Test DELETE /rfid/api/mappings/<tag>."""
        self.mock_frontend.actor_ref.proxy().delete_mapping().get.return_value = True
        response = self.fetch("/rfid/api/mappings/123", method="DELETE")
        assert response.code == 200
        data = json.loads(response.body)
        assert data["ok"] is True

    def test_search_endpoint(self):
        """Test GET /rfid/api/search."""
        response = self.fetch("/rfid/api/search?q=test")
        assert response.code == 200
        data = json.loads(response.body)
        # Should have results from mocked core
        assert "results" in data
        assert isinstance(data["results"], list)


def test_websocket_broadcast():
    """Test WebSocket broadcast to connected clients."""
    mock_client1 = MagicMock()
    mock_client2 = MagicMock()

    http.WSHandler.clients.add(mock_client1)
    http.WSHandler.clients.add(mock_client2)

    http.broadcast_event({"event": "test", "data": "value"})

    mock_client1.write_message.assert_called_once()
    mock_client2.write_message.assert_called_once()

    # Cleanup
    http.WSHandler.clients.clear()


def test_broadcast_event_helper():
    """Test broadcast_event helper function."""
    with patch.object(http.WSHandler, "broadcast") as mock_broadcast:
        http.broadcast_event({"test": "data"})
        mock_broadcast.assert_called_once_with({"test": "data"})
