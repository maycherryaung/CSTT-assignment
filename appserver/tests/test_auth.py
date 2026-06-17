# Tests for Auth_Guard decorator, login route, and logout route.
# Covers Property 1 (invalid credentials rejected) and Property 2 (Auth_Guard blocks unauthenticated requests).
# Also covers Property 8 (Bootstrap alert wraps error messages) for auth errors.
# See design.md §Correctness Properties and tasks.md tasks 4.2, 5.3, 5.4, 10.5.

import sys
import os

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure appserver/ is on sys.path
_appserver_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _appserver_dir not in sys.path:
    sys.path.insert(0, _appserver_dir)

from app import app as flask_app


# ---------------------------------------------------------------------------
# task 4.2 — Property 2: Auth_Guard blocks all unauthenticated requests
# Feature: flask-analytics-portal, Property 2: Auth_Guard blocks all unauthenticated requests to protected routes
# ---------------------------------------------------------------------------

PROTECTED_ROUTES = ["/upload", "/dashboard"]
# Route-to-methods mapping: only test methods that each route actually registers.
# The auth guard fires before dispatch; for disallowed methods Flask returns 405
# before the guard even runs, so we only test valid methods per route.
_ROUTE_METHOD_PAIRS = [
    ("/upload", "GET"),
    ("/upload", "POST"),
    ("/dashboard", "GET"),
]


@given(
    route_method=st.sampled_from(_ROUTE_METHOD_PAIRS),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property2_auth_guard_blocks_unauthenticated_requests(client, route_method):
    """
    # Feature: flask-analytics-portal, Property 2: Auth_Guard blocks all unauthenticated requests to protected routes
    **Validates: Requirements 4.1**
    For every valid HTTP method on each protected route, an unauthenticated
    request must receive a 302 redirect to /login.
    """
    route, method = route_method
    # No session set — purely unauthenticated
    response = client.open(route, method=method)
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


# ---------------------------------------------------------------------------
# task 5.3 — Property 1: Invalid credentials are always rejected
# Feature: flask-analytics-portal, Property 1: Invalid credentials are always rejected
# ---------------------------------------------------------------------------

@given(
    username=st.text(),
    password=st.text(),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property1_invalid_credentials_rejected(client, username, password):
    """
    # Feature: flask-analytics-portal, Property 1: Invalid credentials are always rejected
    **Validates: Requirements 5.1**
    For any (username, password) pair that is NOT ("admin", "password123"),
    POST /login must return 200, not set session["logged_in"]=True,
    and the response body must contain an error message.
    """
    # Filter out the one valid credential pair
    if username == "admin" and password == "password123":
        return

    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )

    assert response.status_code == 200

    # Session must not be marked as logged_in
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True

    # Body must contain an error indication
    body = response.data.decode("utf-8", errors="replace")
    assert "invalid" in body.lower() or "error" in body.lower() or "alert" in body.lower()


# ---------------------------------------------------------------------------
# task 5.4 — Example tests: login / logout
# ---------------------------------------------------------------------------

def test_login_valid_credentials_sets_session_and_redirects_to_upload(client):
    """POST /login with correct credentials sets session and returns 302 to /upload."""
    response = client.post(
        "/login",
        data={"username": "admin", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/upload" in response.headers.get("Location", "")

    with client.session_transaction() as sess:
        assert sess.get("logged_in") is True


def test_logout_clears_session_and_redirects_to_login(client):
    """GET /logout clears session and returns 302 to /login."""
    # First log in
    with client.session_transaction() as sess:
        sess["logged_in"] = True

    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")

    with client.session_transaction() as sess:
        assert not sess.get("logged_in")


def test_logout_with_no_active_session_redirects_without_error(client):
    """GET /logout with no active session returns 302 to /login without error."""
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


# ---------------------------------------------------------------------------
# task 10.5 — Property 8: Bootstrap alert class wraps error messages (auth)
# Feature: flask-analytics-portal, Property 8: Bootstrap alert class wraps all error messages
# ---------------------------------------------------------------------------

def test_property8_invalid_login_uses_bootstrap_alert(client):
    """
    # Feature: flask-analytics-portal, Property 8: Bootstrap alert class wraps all error messages
    **Validates: Requirements 10.1**
    Invalid credentials response body must contain class="alert (Bootstrap alert).
    """
    response = client.post(
        "/login",
        data={"username": "wrong", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="replace")
    assert 'class="alert' in body
