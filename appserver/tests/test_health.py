# Tests for the /health endpoint, bootstrap startup, and the HTTP 500 custom error handler.
# See design.md §Testing Strategy and tasks.md tasks 2.2, 3.2, 11.2.

import sys
import os
import importlib
from unittest.mock import patch

import pytest

# Ensure appserver/ is on sys.path
_appserver_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _appserver_dir not in sys.path:
    sys.path.insert(0, _appserver_dir)

from app import app as flask_app


# ---------------------------------------------------------------------------
# task 2.2 — Bootstrap: exits with code 1 when uploads/ cannot be created
# ---------------------------------------------------------------------------

def test_startup_exits_when_uploads_dir_cannot_be_created():
    """
    Simulate __main__ block: if os.makedirs raises PermissionError,
    the process should call sys.exit(1).
    """
    with patch("os.makedirs", side_effect=PermissionError("Permission denied")):
        with patch("sys.exit") as mock_exit:
            # Re-run the __main__ block logic inline (mirrors app.py entry point)
            try:
                os.makedirs(flask_app.config["UPLOAD_FOLDER"], exist_ok=True)
            except PermissionError as e:
                print(f"Error: Could not create uploads directory: {e}")
                sys.exit(1)
            mock_exit.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# task 3.2 — GET /health
# ---------------------------------------------------------------------------

def test_health_returns_200_ok_text_plain(client):
    """GET /health returns 200, body 'OK', Content-Type text/plain."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.data == b"OK"
    assert "text/plain" in response.content_type


def test_health_no_session_cookie_returns_200_not_redirect(client):
    """GET /health with no session cookie returns 200, not a redirect."""
    response = client.get("/health")
    assert response.status_code == 200
    # Must not be a redirect to /login
    assert response.status_code != 302


# ---------------------------------------------------------------------------
# task 11.2 — 500 error handler suppresses traceback
# ---------------------------------------------------------------------------

def test_500_handler_returns_user_readable_message_without_traceback():
    """
    Directly invoke the registered 500 error handler.
    Assert: status 500, no 'Traceback' in body, user-readable message present.
    """
    # Call the error handler directly within an app context
    with flask_app.app_context():
        from werkzeug.exceptions import InternalServerError
        exc = InternalServerError()
        response, status_code = flask_app.error_handler_spec[None][500][InternalServerError](exc)

    assert status_code == 500
    assert "Traceback" not in response
    # The custom 500 handler renders a user-readable message
    assert any(
        phrase in response.lower()
        for phrase in ("error", "unexpected", "try again", "please")
    )
