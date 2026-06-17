"""
DataBox.ai Flask Analytics Portal
CSTT AWS Cloud Security Assignment — Task 1
App Server: private subnet 10.0.3.0/24, accessible via Bastion Host only.
"""

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
import csv
import os
import sys
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
app.config["SECRET_KEY"] = "dev-secret-key-change-in-production"  # PRODUCTION: replace SECRET_KEY with a secrets-manager value
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=60)
app.config["PROPAGATE_EXCEPTIONS"] = False  # PRODUCTION: Flask debug mode MUST be disabled on the App Server to suppress tracebacks


# ---------------------------------------------------------------------------
# Auth_Guard
# ---------------------------------------------------------------------------
# login_required decorator — reads session['logged_in'];
# redirects unauthenticated requests to /login.

def login_required(f):
    """
    Auth_Guard decorator.

    Wraps any route that requires an authenticated session.
    Reads session['logged_in'] and, if falsy or absent, immediately returns
    a 302 redirect to /login — implementing the default-deny posture described
    in Requirement 4.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# GET  /health  — unauthenticated health probe
@app.route("/health", methods=["GET"])
def health():
    return Response("OK", status=200, mimetype="text/plain")

# GET  /login   — render login form
# POST /login   — validate credentials, set session
# GET  /logout  — clear session, redirect to /login
# GET  /upload  — render upload form          [Auth_Guard]
# POST /upload  — validate + save + process   [Auth_Guard]
# GET  /dashboard — render analytics page    [Auth_Guard]


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)

    # POST — validate submitted credentials
    username = request.form.get("username")
    password = request.form.get("password")

    # PRODUCTION: replace hardcoded credentials with a proper identity provider, IAM roles, HTTPS, and S3 encryption
    if username == "admin" and password == "password123":
        session.clear()
        session["logged_in"] = True
        session["username"] = "admin"
        session.permanent = True
        return redirect(url_for("upload"))

    return render_template("login.html", error="Invalid username or password. Please try again.")


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("upload.html", error=None)

    # POST — validate, save, and process the uploaded file
    file = request.files.get("file", FileStorage())
    is_valid, error_message = validate_file(file)

    if not is_valid:
        return render_template("upload.html", error=error_message)

    # Validation passed — save the file
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    try:
        file.save(filepath)
    except OSError:
        if os.path.exists(filepath):
            os.remove(filepath)
        return render_template("upload.html", error="The file could not be saved. Please try again.")

    # Process the saved CSV
    try:
        result = process_csv(filepath)
    except Exception:
        return render_template("upload.html", error="The file could not be read. Please check the file is a valid CSV and try again.")

    session["csv_result"] = result
    return redirect(url_for("dashboard"))


@app.errorhandler(413)
def request_entity_too_large(e):
    return render_template("upload.html", error="File exceeds the maximum allowed size of 16 MB."), 413


@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    csv_result = session.get("csv_result")
    return render_template("dashboard.html", csv_result=csv_result)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
# validate_file(file) -> (bool, str | None)
# Pure function — no filesystem access.

def validate_file(file):
    """
    Validate an uploaded file object before any disk I/O.

    Checks (in order):
      1. No file selected (empty or absent filename).
      2. Filename does not end with .csv (case-insensitive).

    Returns:
        (True, None)               — all checks passed
        (False, error_message)     — first failing check, with message
    """
    if not file.filename:
        return (False, "Please select a file to upload.")

    if not secure_filename(file.filename).lower().endswith(".csv"):
        return (False, "Only .csv files are accepted.")

    return (True, None)


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------
# process_csv(filepath: str) -> dict  (CSVResult)
# Reads saved CSV; returns row/column/header/preview stats.
# On error: deletes saved file, raises ProcessorError.


class ProcessorError(Exception):
    """Raised by process_csv when the CSV file cannot be read or parsed."""


def process_csv(filepath):
    """
    Read a saved CSV file and return a CSVResult dict.

    Keys returned:
        rows       (int)        — data rows excluding the header
        columns    (int)        — number of columns
        headers    (list[str])  — column names from the header row
        preview    (list[list]) — up to the first 5 data rows
        filename   (str)        — os.path.basename(filepath)
        timestamp  (str)        — datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_count (int)        — .csv files currently in UPLOAD_FOLDER

    Raises:
        ProcessorError — on UnicodeDecodeError, csv.Error, or OSError;
                         the saved file is deleted before the error is raised.
    """
    try:
        with open(filepath, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            all_rows = list(reader)
    except (UnicodeDecodeError, csv.Error, OSError):
        # Delete the saved file; ignore if it is already gone.
        try:
            os.remove(filepath)
        except OSError:
            pass
        raise ProcessorError("The file could not be read.")

    # Separate header from data rows.
    headers = all_rows[0] if all_rows else []
    data_rows = all_rows[1:] if len(all_rows) > 1 else []

    upload_folder = app.config["UPLOAD_FOLDER"]
    try:
        file_count = len([f for f in os.listdir(upload_folder) if f.endswith(".csv")])
    except OSError:
        file_count = 0

    return {
        "rows": len(data_rows),
        "columns": len(headers),
        "headers": headers,
        "preview": data_rows[:5],
        "filename": os.path.basename(filepath),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_count": file_count,
    }


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------
# @app.errorhandler(500) — returns user-readable message, suppresses traceback.

@app.errorhandler(500)
def internal_server_error(e):
    return (
        "<html><body>"
        "<h1>Internal Server Error</h1>"
        "<p>An unexpected error occurred. Please try again later.</p>"
        "</body></html>"
    ), 500


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    except PermissionError as e:
        print(f"Error: Could not create uploads directory: {e}")
        sys.exit(1)
    app.run(host="0.0.0.0", port=5000)
