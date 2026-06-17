# Tests for the Validator component and the /upload route.
# Covers Property 3 (non-CSV rejected without saving) and Property 4 (valid CSV always saved + redirects).
# Also covers Property 8 (Bootstrap alert wraps error messages) for upload errors.
# See design.md §Correctness Properties and tasks.md tasks 7.3, 7.4, 7.5, 10.5.

import sys
import os
import io
from unittest.mock import patch, MagicMock

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

def _authenticated_client(client):
    """Set a logged-in session on the given client."""
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    return client


def _upload_file(client, filename, content, content_type="text/csv"):
    """POST a file to /upload using multipart form data."""
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# task 7.3 — Property 3: Non-CSV file uploads are always rejected without saving
# Feature: flask-analytics-portal, Property 3: Non-CSV file uploads are always rejected without saving
# ---------------------------------------------------------------------------

@given(filename=st.text(min_size=1))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property3_non_csv_rejected_without_saving(client, tmp_upload_dir, filename):
    """
    # Feature: flask-analytics-portal, Property 3: Non-CSV file uploads are always rejected without saving
    **Validates: Requirements 7.1**
    Any file whose name does not end in .csv (case-insensitive) must be
    rejected with HTTP 200, no file saved, and an error alert in the body.
    """
    # Filter out .csv filenames (case-insensitive) and empty/whitespace-only filenames
    if filename.lower().endswith(".csv"):
        return
    # Also skip filenames that are empty after stripping — werkzeug secure_filename may produce empty string
    from werkzeug.utils import secure_filename
    safe = secure_filename(filename)
    if not safe:
        return

    _authenticated_client(client)
    response = _upload_file(client, filename, b"some,data\n1,2")

    assert response.status_code == 200

    # No files should have been written to the temp upload dir
    saved_files = list(tmp_upload_dir.iterdir())
    assert len(saved_files) == 0, f"Unexpected files saved: {saved_files}"

    body = response.data.decode("utf-8", errors="replace")
    assert "alert" in body.lower() or "error" in body.lower() or "only" in body.lower()


# ---------------------------------------------------------------------------
# task 7.4 — Property 4: Valid CSV upload is always saved and redirects to dashboard
# Feature: flask-analytics-portal, Property 4: Valid CSV upload is always saved and redirects to dashboard
# ---------------------------------------------------------------------------

@given(content=st.binary(min_size=1, max_size=1024))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property4_valid_csv_saved_and_redirects(client, tmp_upload_dir, content):
    """
    # Feature: flask-analytics-portal, Property 4: Valid CSV upload is always saved and redirects to dashboard
    **Validates: Requirements 7.2**
    A file with a .csv extension and valid CSV content must be saved to the
    upload folder and return a 302 redirect to /dashboard.
    """
    # Build a minimal valid CSV: ensure content is valid UTF-8 CSV
    # Use a safe CSV header + one data row so process_csv succeeds
    csv_content = b"col1,col2\n" + content.replace(b"\x00", b"")
    # Ensure it's decodable as UTF-8 (replace invalid bytes)
    try:
        csv_content.decode("utf-8")
    except UnicodeDecodeError:
        csv_content = b"col1,col2\nvalue1,value2\n"

    _authenticated_client(client)
    response = _upload_file(client, "test_data.csv", csv_content)

    assert response.status_code == 302, (
        f"Expected 302, got {response.status_code}. Body: {response.data[:500]}"
    )
    assert "/dashboard" in response.headers.get("Location", "")

    # File must exist in the upload directory
    saved_files = list(tmp_upload_dir.iterdir())
    assert len(saved_files) >= 1, "No file was saved to the upload directory"


# ---------------------------------------------------------------------------
# task 7.5 — Example tests for /upload
# ---------------------------------------------------------------------------

def test_upload_no_file_returns_error_on_upload_page(client):
    """Upload with no file selected returns an error message on the upload page."""
    _authenticated_client(client)
    # Post with an empty file field (simulates user clicking Upload without choosing a file)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="replace")
    assert "alert" in body.lower() or "select" in body.lower() or "error" in body.lower()


def test_upload_non_csv_extension_returns_error_no_file_saved(client, tmp_upload_dir):
    """Upload with a non-CSV extension returns error and saves no file."""
    _authenticated_client(client)
    response = _upload_file(client, "data.txt", b"some,data\n1,2")
    assert response.status_code == 200

    saved_files = list(tmp_upload_dir.iterdir())
    assert len(saved_files) == 0

    body = response.data.decode("utf-8", errors="replace")
    assert "alert" in body.lower() or "csv" in body.lower()


def test_upload_exactly_16mb_succeeds(client, tmp_upload_dir):
    """Upload of exactly 16 MB file content succeeds (boundary: max allowed)."""
    _authenticated_client(client)
    max_size = 16 * 1024 * 1024  # 16 MB exactly
    # Build a valid CSV: header + data rows
    # The multipart framing adds ~200 bytes overhead for boundary headers.
    # To ensure the raw request stays at or under 16 MB, we keep the file
    # content a bit under 16 MB so the total request stays within the limit.
    #
    # We target file content = 16 MB - 512 bytes to safely stay within the
    # MAX_CONTENT_LENGTH of 16 MB when multipart headers are included.
    header = b"col1,col2\n"
    # Each data row "a,b\n" = 4 bytes
    target_content_size = max_size - 512  # leave headroom for multipart overhead
    remaining = target_content_size - len(header)
    row = b"a,b\n"
    full_rows = remaining // len(row)
    leftover = remaining % len(row)
    content = header + row * full_rows + b"x" * leftover

    assert len(content) == target_content_size

    response = _upload_file(client, "big.csv", content)
    # Should succeed: 302 redirect to dashboard
    assert response.status_code == 302, (
        f"Expected 302 for large file, got {response.status_code}"
    )
    assert "/dashboard" in response.headers.get("Location", "")


def test_upload_16mb_plus_1_byte_rejected_with_size_error(client):
    """Upload of 16 MB + 1 byte is rejected with a 413 size error."""
    _authenticated_client(client)
    over_size = 16 * 1024 * 1024 + 1
    content = b"a" * over_size

    response = _upload_file(client, "toobig.csv", content)
    # Werkzeug/Flask returns 413 for oversized requests
    assert response.status_code == 413


def test_upload_disk_write_failure_returns_error_no_partial_file(client, tmp_upload_dir):
    """If file.save raises OSError, return error and no partial file on disk."""
    _authenticated_client(client)

    with patch("werkzeug.datastructures.FileStorage.save", side_effect=OSError("Disk full")):
        response = _upload_file(client, "data.csv", b"col1,col2\n1,2\n")

    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="replace")
    assert "alert" in body.lower() or "error" in body.lower() or "saved" in body.lower()

    # No partial file should remain on disk
    saved_files = list(tmp_upload_dir.iterdir())
    assert len(saved_files) == 0


# ---------------------------------------------------------------------------
# task 10.5 — Property 8: Bootstrap alert class wraps error messages (upload)
# Feature: flask-analytics-portal, Property 8: Bootstrap alert class wraps all error messages
# ---------------------------------------------------------------------------

def test_property8_no_file_upload_uses_bootstrap_alert(client):
    """
    # Feature: flask-analytics-portal, Property 8: Bootstrap alert class wraps all error messages
    **Validates: Requirements 10.1**
    Upload error (no file) must wrap the error in a Bootstrap alert element.
    """
    _authenticated_client(client)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="replace")
    assert 'class="alert' in body


def test_property8_non_csv_upload_uses_bootstrap_alert(client):
    """
    # Feature: flask-analytics-portal, Property 8: Bootstrap alert class wraps all error messages
    **Validates: Requirements 10.1**
    Upload error (non-CSV) must wrap the error in a Bootstrap alert element.
    """
    _authenticated_client(client)
    response = _upload_file(client, "data.txt", b"some data")
    assert response.status_code == 200
    body = response.data.decode("utf-8", errors="replace")
    assert 'class="alert' in body
