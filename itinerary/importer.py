"""Bulk CSV import with row-by-row error reporting."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from .logic import next_id
from .models import Record
from .validation import make_record

REQUIRED_COLUMNS = ("destination", "start_date", "end_date", "est_cost")
OPTIONAL_COLUMNS = ("category", "status", "notes")
ALIASES = {
    "cost": "est_cost", "estimated_cost": "est_cost", "start": "start_date", "end": "end_date",
    "from": "start_date", "to": "end_date", "place": "destination", "type": "category",
}
MAX_ROWS = 5000


@dataclass
class RowError:
    row: int
    message: str
    raw: str


@dataclass
class ImportResult:
    records: list[Record] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    duplicates: int = 0
    total_rows: int = 0
    header_error: str | None = None


def _normalize(name: str) -> str:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(key, key)


def _dup_key(r: Record) -> tuple:
    return (r.destination.lower(), r.category, r.start_date, r.end_date, r.est_cost)


def import_csv_text(text: str, existing: list[Record], max_rows: int = MAX_ROWS) -> ImportResult:
    result = ImportResult()
    reader = csv.reader(io.StringIO(text))
    try:
        header_row = next(reader)
    except (StopIteration, csv.Error):
        result.header_error = "The file is empty or not a readable CSV."
        return result

    header = [_normalize(h) for h in header_row]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        result.header_error = f"Missing required column(s): {', '.join(missing)}. Found: {', '.join(h for h in header_row if h.strip()) or 'none'}."
        return result

    known = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS)
    seen_keys = {_dup_key(r) for r in existing}
    new_id = next_id(existing)

    try:
        for row in reader:
            line = reader.line_num
            if not any(cell.strip() for cell in row):
                continue
            result.total_rows += 1
            raw = " | ".join(row)
            if result.total_rows > max_rows:
                result.errors.append(RowError(line, f"Row limit of {max_rows} reached; remaining rows were not read.", raw))
                break
            if len(row) != len(header):
                result.errors.append(RowError(line, f"Expected {len(header)} columns but found {len(row)}.", raw))
                continue
            values = {h: v for h, v in zip(header, row) if h in known}
            rec, errors = make_record(
                new_id,
                destination=values.get("destination"),
                category=values.get("category") or "Other",
                start_date=values.get("start_date"),
                end_date=values.get("end_date"),
                est_cost=values.get("est_cost"),
                status=values.get("status") or "Planned",
                notes=values.get("notes", ""),
            )
            if errors:
                result.errors.append(RowError(line, " ".join(errors), raw))
                continue
            key = _dup_key(rec)
            if key in seen_keys:
                result.duplicates += 1
                continue
            seen_keys.add(key)
            result.records.append(rec)
            new_id += 1
    except csv.Error as exc:
        result.errors.append(RowError(reader.line_num, f"CSV could not be parsed past this point: {exc}", ""))
    return result


def error_log_csv(result: ImportResult) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["row", "error", "original_row"])
    for e in result.errors:
        writer.writerow([e.row, e.message, e.raw])
    return buffer.getvalue()
