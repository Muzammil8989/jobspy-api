"""
JobSpy API Service
==================

A lightweight Flask wrapper around the JobSpy library, exposing job
search (LinkedIn, Indeed, and others) as a simple HTTP JSON API for
use from n8n or any other automation tool.

Setup
-----
    pip install python-jobspy flask

Run (development)
------------------
    python jobspy_api.py

Run (production, via Docker/gunicorn)
--------------------------------------
    gunicorn --bind 0.0.0.0:5000 --timeout 120 --workers 2 jobspy_api:app

Endpoints
---------
    GET  /health   -> service health check
    POST /scrape   -> run a job search

n8n calls this at: http://host.docker.internal:5000/scrape
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from flask import Flask, jsonify, request
from jobspy import scrape_jobs

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULT_SITE_NAMES = ["linkedin", "indeed"]
DEFAULT_RESULTS_WANTED = 20
DEFAULT_HOURS_OLD = 96
DEFAULT_COUNTRY_INDEED = "USA"
MAX_RESULTS_WANTED = 200  # hard ceiling to avoid runaway scrape jobs

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jobspy_api")

app = Flask(__name__)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

class ValidationError(ValueError):
    """Raised when the incoming request body fails validation."""


def _validate_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the incoming JSON payload.

    Raises ValidationError with a human-readable message on bad input.
    Returns a clean dict of parameters ready to pass to scrape_jobs().
    """
    search_term = str(data.get("search_term", "")).strip()
    if not search_term:
        raise ValidationError("'search_term' is required and cannot be empty.")

    location = str(data.get("location", "")).strip()

    site_names = data.get("site_names", DEFAULT_SITE_NAMES)
    if not isinstance(site_names, list) or not site_names:
        raise ValidationError("'site_names' must be a non-empty list of strings.")

    results_wanted = data.get("results_wanted", DEFAULT_RESULTS_WANTED)
    try:
        results_wanted = int(results_wanted)
    except (TypeError, ValueError):
        raise ValidationError("'results_wanted' must be an integer.")
    if results_wanted <= 0:
        raise ValidationError("'results_wanted' must be greater than 0.")
    if results_wanted > MAX_RESULTS_WANTED:
        logger.warning(
            "results_wanted=%s exceeds cap; clamping to %s",
            results_wanted,
            MAX_RESULTS_WANTED,
        )
        results_wanted = MAX_RESULTS_WANTED

    hours_old = data.get("hours_old", DEFAULT_HOURS_OLD)
    try:
        hours_old = int(hours_old)
    except (TypeError, ValueError):
        raise ValidationError("'hours_old' must be an integer.")

    is_remote: Optional[bool] = data.get("is_remote", None)
    if is_remote is not None and not isinstance(is_remote, bool):
        raise ValidationError("'is_remote' must be a boolean or omitted.")

    country_indeed = str(data.get("country_indeed", DEFAULT_COUNTRY_INDEED)).strip()

    return {
        "search_term": search_term,
        "location": location,
        "site_name": site_names,
        "results_wanted": results_wanted,
        "hours_old": hours_old,
        "is_remote": is_remote,
        "country_indeed": country_indeed,
    }


def _normalize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Force any date/datetime-like column to a plain ISO string.

    pandas' to_json() can silently emit raw epoch-millisecond integers
    for date columns depending on the underlying dtype, even when
    date_format="iso" is passed. Converting explicitly here sidesteps
    that entirely and guarantees a human-readable value downstream.
    """
    for col in df.columns:
        if "date" in col.lower():
            df[col] = (
                df[col]
                .astype(str)
                .replace({"NaT": "", "None": "", "nan": ""})
            )
    return df


def _dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a jobs DataFrame into a list of plain JSON-safe dicts."""
    if df is None or df.empty:
        return []
    df = _normalize_date_columns(df.copy())
    # where_records avoids NaN leaking into the JSON as literal `NaN`
    return df.where(pd.notnull(df), None).to_dict(orient="records")


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health() -> Any:
    """Basic liveness check."""
    return jsonify(
        {
            "status": "ok",
            "service": "jobspy-api",
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.route("/scrape", methods=["POST"])
def scrape() -> Any:
    """Run a job search and return normalized results.

    Expected JSON body:
        {
          "search_term": "Full Stack Developer",   // required
          "location": "Karachi, Pakistan",          // optional
          "site_names": ["linkedin", "indeed"],     // optional
          "results_wanted": 20,                     // optional
          "hours_old": 96,                          // optional
          "is_remote": true,                        // optional
          "country_indeed": "Pakistan"               // optional
        }
    """
    raw_body = request.get_json(silent=True)
    if raw_body is None:
        return (
            jsonify({"success": False, "error": "Request body must be valid JSON.", "jobs": []}),
            400,
        )

    try:
        params = _validate_payload(raw_body)
    except ValidationError as exc:
        logger.info("Rejected request: %s", exc)
        return jsonify({"success": False, "error": str(exc), "jobs": []}), 400

    logger.info(
        "Scraping '%s' in '%s' (sites=%s, remote=%s, results_wanted=%s)",
        params["search_term"],
        params["location"] or "any",
        params["site_name"],
        params["is_remote"],
        params["results_wanted"],
    )

    try:
        jobs_df = scrape_jobs(**params)
    except Exception:
        logger.exception("scrape_jobs() failed")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Job search failed. See service logs for details.",
                    "jobs": [],
                }
            ),
            502,
        )

    try:
        records = _dataframe_to_records(jobs_df)
    except Exception:
        logger.exception("Failed to serialize results")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Failed to serialize job results.",
                    "jobs": [],
                }
            ),
            500,
        )

    logger.info("Found %d job(s) for '%s'", len(records), params["search_term"])
    return jsonify({"success": True, "count": len(records), "jobs": records})


@app.errorhandler(404)
def not_found(_err: Any) -> Any:
    return jsonify({"success": False, "error": "Not found. Available routes: /health, /scrape"}), 404


@app.errorhandler(405)
def method_not_allowed(_err: Any) -> Any:
    return jsonify({"success": False, "error": "Method not allowed."}), 405


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)