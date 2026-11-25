"""Defensive parsing and range checks.

Every function either returns a clean value or raises ValueError with a
message that is safe to show directly to the user.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime

from .models import CATEGORIES, STATUSES, Record

MAX_COST = 10_000_000.0
MIN_YEAR, MAX_YEAR = 2000, 2100
MIN_DESTINATION, MAX_DESTINATION = 2, 80
MAX_NOTES = 500

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_DEST_PATTERN = re.compile(r"^[\w .,'&()/\-]+$")
_HAS_LETTER = re.compile(r"[^\W\d_]")
_COST_PATTERN = re.compile(r"^-?\d+(\.\d+)?$")
_CURRENCY_PATTERN = re.compile(r"^[A-Za-z₹$€£]{1,5}$")


def clean_text(value) -> str:
    """Strip control characters and collapse whitespace."""
    if value is None:
        return ""
    return " ".join(_CONTROL_CHARS.sub(" ", str(value)).split())


def parse_date(value, label: str = "Date") -> date:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = clean_text(value)
        if not text:
            raise ValueError(f"{label} is required.")
        parsed = None
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"{label} '{text}' is not a valid date (use YYYY-MM-DD or DD/MM/YYYY).")
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise ValueError(f"{label} year must be between {MIN_YEAR} and {MAX_YEAR}.")
    return parsed


def parse_cost(value) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError("Estimated cost is required.")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        original = clean_text(value)
        text = re.sub(r"[₹$€£,\s]", "", original)
        if not text:
            raise ValueError("Estimated cost is required.")
        if not _COST_PATTERN.match(text):
            raise ValueError(f"Estimated cost '{original}' is not a number.")
        number = float(text)
    if not math.isfinite(number):
        raise ValueError("Estimated cost must be a finite number.")
    if number < 0:
        raise ValueError("Estimated cost cannot be negative.")
    if number > MAX_COST:
        raise ValueError(f"Estimated cost cannot exceed {MAX_COST:,.0f}.")
    return round(number, 2)


def parse_destination(value) -> str:
    text = clean_text(value)
    if not text:
        raise ValueError("Destination is required.")
    if len(text) < MIN_DESTINATION:
        raise ValueError(f"Destination must be at least {MIN_DESTINATION} characters.")
    if len(text) > MAX_DESTINATION:
        raise ValueError(f"Destination must be at most {MAX_DESTINATION} characters (got {len(text)}).")
    if not _HAS_LETTER.search(text):
        raise ValueError("Destination must contain at least one letter.")
    if not _DEST_PATTERN.match(text):
        raise ValueError("Destination contains unsupported characters (allowed: letters, digits, spaces, . , ' & ( ) / -).")
    return text


def parse_choice(value, options: tuple[str, ...], label: str) -> str:
    text = clean_text(value)
    for option in options:
        if option.lower() == text.lower():
            return option
    shown = ", ".join(options)
    raise ValueError(f"{label} '{text}' is not valid. Choose one of: {shown}." if text else f"{label} is required.")


def parse_notes(value) -> str:
    text = clean_text(value)
    if len(text) > MAX_NOTES:
        raise ValueError(f"Notes must be at most {MAX_NOTES} characters (got {len(text)}).")
    return text


def clean_currency(value) -> tuple[str | None, str | None]:
    text = clean_text(value)
    if not _CURRENCY_PATTERN.match(text):
        return None, "Currency must be 1-5 letters or a symbol such as ₹, $, €, £."
    return text.upper() if text.isalpha() else text, None


def validate_fields(destination, category, start_date, end_date, est_cost, status="Planned", notes=""):
    """Validate every field and report *all* problems at once.

    Returns (clean_fields_dict, errors). clean_fields_dict is None when errors exist.
    """
    errors: list[str] = []
    clean: dict = {}

    def run(key, func, *args):
        try:
            clean[key] = func(*args)
        except ValueError as exc:
            errors.append(str(exc))

    run("destination", parse_destination, destination)
    run("category", parse_choice, category, CATEGORIES, "Category")
    run("start_date", parse_date, start_date, "Start date")
    run("end_date", parse_date, end_date, "End date")
    run("est_cost", parse_cost, est_cost)
    run("status", parse_choice, status, STATUSES, "Status")
    run("notes", parse_notes, notes)

    if "start_date" in clean and "end_date" in clean and clean["end_date"] < clean["start_date"]:
        errors.append("End date cannot be before the start date.")

    if errors:
        return None, errors
    clean["start_date"] = clean["start_date"].isoformat()
    clean["end_date"] = clean["end_date"].isoformat()
    return clean, []


def make_record(rec_id: int, **fields) -> tuple[Record | None, list[str]]:
    clean, errors = validate_fields(**fields)
    if errors:
        return None, errors
    return Record(id=rec_id, **clean), []
