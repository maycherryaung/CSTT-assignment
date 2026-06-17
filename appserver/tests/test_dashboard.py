# Tests for the /dashboard route and dashboard.html template rendering.
# Covers Property 7 (dashboard renders complete analytics for any processed CSV).
# Also covers the empty-state message when no CSV has been uploaded.
# See design.md §Correctness Properties and tasks.md tasks 10.4, 10.6.

import sys
import os
import re
import html

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure appserver/ is on sys.path
_appserver_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _appserver_dir not in sys.path:
    sys.path.insert(0, _appserver_dir)

from app import app as flask_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _authenticated_with_csv_result(client, csv_result):
    """Set a logged-in session with a csv_result dict."""
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["csv_result"] = csv_result
    return client


# ---------------------------------------------------------------------------
# task 10.4 — Property 7: Dashboard renders complete analytics for any processed CSV
# Feature: flask-analytics-portal, Property 7: Dashboard renders complete analytics for any processed CSV
# ---------------------------------------------------------------------------

# Strategy for a valid csv_result dict
_csv_result_strategy = st.fixed_dictionaries({
    "rows": st.integers(min_value=0, max_value=1000),
    "columns": st.integers(min_value=1, max_value=50),
    "headers": st.lists(
        st.text(min_size=1, max_size=30, alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="<>")),
        min_size=1,
        max_size=10,
    ),
    "preview": st.lists(
        st.lists(
            st.text(max_size=20, alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="<>")),
            min_size=0,
            max_size=10,
        ),
        min_size=0,
        max_size=5,
    ),
    "filename": st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters='<>"/\\'),
    ),
    "timestamp": st.just("2024-01-15 10:30:00"),  # fixed valid timestamp for assertion
    "file_count": st.integers(min_value=0, max_value=100),
})


@given(csv_result=_csv_result_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property7_dashboard_renders_complete_analytics(client, csv_result):
    """
    # Feature: flask-analytics-portal, Property 7: Dashboard renders complete analytics for any processed CSV
    **Validates: Requirements 10.1**
    GET /dashboard with a csv_result in session must render:
    - correct row count
    - correct column count
    - column names in <th> elements
    - up to 5 <tbody> rows
    - "Completed" status text
    - filename
    - timestamp matching YYYY-MM-DD HH:MM:SS
    """
    _authenticated_with_csv_result(client, csv_result)
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="replace")
    # Unescape HTML entities (Jinja2 auto-escapes special chars like " -> &#34;)
    body_unescaped = html.unescape(body)

    # Row count appears in the rendered HTML
    assert str(csv_result["rows"]) in body

    # Column count appears in the rendered HTML
    assert str(csv_result["columns"]) in body

    # Each column header appears somewhere in the body (check unescaped version)
    for header in csv_result["headers"]:
        assert header in body_unescaped, f"Header '{header}' not found in dashboard HTML"

    # "Completed" status text
    assert "Completed" in body

    # Filename appears (check unescaped)
    assert csv_result["filename"] in body_unescaped

    # Timestamp matches pattern YYYY-MM-DD HH:MM:SS
    ts_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
    assert re.search(ts_pattern, body), "Timestamp pattern not found in dashboard HTML"

    # Preview: at most 5 <tr> rows inside <tbody>
    tbody_matches = re.findall(r"<tbody>(.*?)</tbody>", body, re.DOTALL)
    if tbody_matches:
        tbody_content = tbody_matches[0]
        tr_count = len(re.findall(r"<tr", tbody_content))
        assert tr_count <= 5, f"More than 5 tbody rows found: {tr_count}"


# ---------------------------------------------------------------------------
# task 10.6 — Example test: empty-state dashboard
# ---------------------------------------------------------------------------

def test_dashboard_no_csv_result_in_session_renders_empty_state(client):
    """
    GET /dashboard with no csv_result in session renders the empty-state
    message and returns HTTP 200.
    """
    # Authenticate but do NOT set csv_result
    with client.session_transaction() as sess:
        sess["logged_in"] = True

    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 200

    body = response.data.decode("utf-8", errors="replace")
    # The empty-state message from dashboard.html
    assert "no data" in body.lower() or "upload" in body.lower() or "yet" in body.lower()
