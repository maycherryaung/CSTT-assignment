"""
Shared pytest fixtures for the Flask Analytics Portal test suite.

The test runner should be invoked from the `appserver/` directory so that
`from app import app` resolves correctly, e.g.:
    cd appserver && pytest tests/

Alternatively, pytest can be run from the repo root with:
    pytest appserver/tests/
provided `appserver/` is on sys.path (see sys.path manipulation below).
"""

import sys
import os

# Ensure `appserver/` is on sys.path so `from app import app` always resolves,
# regardless of the directory from which pytest is invoked.
_appserver_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _appserver_dir not in sys.path:
    sys.path.insert(0, _appserver_dir)

import pytest
from app import app as flask_app


@pytest.fixture()
def client(tmp_path):
    """
    Flask test client fixture.

    Sets TESTING=True, points UPLOAD_FOLDER at a temporary directory so tests
    never write to the real uploads/ directory, and yields the test client.
    """
    flask_app.config["TESTING"] = True
    flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
    # Use a fixed secret key so sessions work predictably in tests.
    flask_app.config["SECRET_KEY"] = "test-secret-key"

    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def tmp_upload_dir(tmp_path, monkeypatch):
    """
    Fixture that patches app.config["UPLOAD_FOLDER"] to a pytest-managed
    temporary directory for the duration of a single test.

    Yields the tmp_path Path object so tests can inspect directory contents.
    """
    monkeypatch.setitem(flask_app.config, "UPLOAD_FOLDER", str(tmp_path))
    yield tmp_path
