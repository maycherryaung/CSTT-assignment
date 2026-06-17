# Tests for the Processor component (process_csv function).
# Covers Property 5 (accurate row/column/header extraction) and Property 6 (preview bounded and accurate).
# See design.md §Correctness Properties and tasks.md tasks 8.3, 8.4, 8.5.

import sys
import os
import csv
import tempfile
import io

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# Ensure appserver/ is on sys.path
_appserver_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _appserver_dir not in sys.path:
    sys.path.insert(0, _appserver_dir)

from app import app as flask_app, process_csv, ProcessorError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Safe text strategy: no surrogate characters, no null bytes
_safe_text = st.text(
    min_size=1,
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
)

_safe_cell = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
)


def _write_csv_to_temp(headers, rows, tmp_dir):
    """Write a CSV file to a temp dir and return its path."""
    path = os.path.join(tmp_dir, "test.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
    return path


# ---------------------------------------------------------------------------
# task 8.3 — Property 5: Processor accurately extracts row count, column count, headers
# Feature: flask-analytics-portal, Property 5: Processor accurately extracts row count, column count, and headers
# ---------------------------------------------------------------------------

@given(
    headers=st.lists(_safe_text, min_size=1, max_size=20),
    rows=st.lists(
        st.lists(_safe_cell, min_size=0, max_size=20),
        min_size=0,
        max_size=50,
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property5_processor_extracts_row_column_headers(tmp_path, headers, rows):
    """
    # Feature: flask-analytics-portal, Property 5: Processor accurately extracts row count, column count, and headers
    **Validates: Requirements 8.1**
    process_csv must report rows == N (data rows), columns == K (header count),
    and headers == header_list for any valid CSV.
    """
    path = _write_csv_to_temp(headers, rows, str(tmp_path))

    with flask_app.app_context():
        flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        result = process_csv(path)

    assert result["rows"] == len(rows), (
        f"Expected rows={len(rows)}, got {result['rows']}"
    )
    assert result["columns"] == len(headers), (
        f"Expected columns={len(headers)}, got {result['columns']}"
    )
    assert result["headers"] == headers, (
        f"Expected headers={headers!r}, got {result['headers']!r}"
    )


# ---------------------------------------------------------------------------
# task 8.4 — Property 6: Processor preview is bounded and matches actual data
# Feature: flask-analytics-portal, Property 6: Processor preview is bounded and matches actual data
# ---------------------------------------------------------------------------

@given(
    num_rows=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property6_preview_bounded_and_matches_data(tmp_path, num_rows):
    """
    # Feature: flask-analytics-portal, Property 6: Processor preview is bounded and matches actual data
    **Validates: Requirements 8.2**
    len(preview) == min(N, 5) and each preview row matches the corresponding
    source data row exactly.
    """
    headers = ["a", "b", "c"]
    rows = [[f"r{i}c0", f"r{i}c1", f"r{i}c2"] for i in range(num_rows)]
    path = _write_csv_to_temp(headers, rows, str(tmp_path))

    with flask_app.app_context():
        flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        result = process_csv(path)

    expected_preview_len = min(num_rows, 5)
    assert len(result["preview"]) == expected_preview_len, (
        f"Expected preview length {expected_preview_len}, got {len(result['preview'])}"
    )

    for i, preview_row in enumerate(result["preview"]):
        assert preview_row == rows[i], (
            f"Preview row {i} mismatch: expected {rows[i]!r}, got {preview_row!r}"
        )


# ---------------------------------------------------------------------------
# task 8.5 — Example tests for process_csv
# ---------------------------------------------------------------------------

def test_process_csv_header_only_no_data_rows(tmp_path):
    """CSV with header only (0 data rows): rows=0, empty preview, no error."""
    path = _write_csv_to_temp(["name", "age"], [], str(tmp_path))

    with flask_app.app_context():
        flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        result = process_csv(path)

    assert result["rows"] == 0
    assert result["preview"] == []
    assert result["headers"] == ["name", "age"]


def test_process_csv_bad_encoding_raises_processor_error_and_deletes_file(tmp_path):
    """
    A file with bad encoding raises ProcessorError and the file is deleted
    from the upload directory.
    """
    # Write a file with invalid UTF-8 bytes
    bad_path = os.path.join(str(tmp_path), "bad.csv")
    with open(bad_path, "wb") as f:
        f.write(b"\xff\xfe bad bytes \x80\x81\x82")

    assert os.path.exists(bad_path), "File should exist before processing"

    with flask_app.app_context():
        flask_app.config["UPLOAD_FOLDER"] = str(tmp_path)
        with pytest.raises(ProcessorError):
            process_csv(bad_path)

    assert not os.path.exists(bad_path), "File should be deleted after ProcessorError"
