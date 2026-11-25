"""Report generation: Markdown, plain-text audit log, CSV and JSON."""
from __future__ import annotations

import csv
import io
import json
from datetime import date

from .logic import money, sort_records
from .models import CSV_COLUMNS, Record, State, Warn


def _md(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(records: list[Record], summary: dict, warnings: list[Warn], currency: str, generated_on: date) -> str:
    lines = [
        "# Travel Itinerary Report", "",
        f"_Generated {generated_on.isoformat()}_", "",
        "## Overview", "",
        "| Metric | Value |", "|---|---|",
        f"| Entries (excluding cancelled) | {summary['count']} |",
        f"| Total estimated cost | {money(summary['total'], currency)} |",
        f"| Average per entry | {money(summary['average'], currency)} |",
        f"| Destinations | {summary['destination_count']} |",
    ]
    if summary["trip_start"]:
        lines.append(f"| Date range | {summary['trip_start']} to {summary['trip_end']} |")
    if summary["budget_used_pct"] is not None:
        lines.append(f"| Budget | {money(summary['budget'], currency)} ({summary['budget_used_pct']}% used) |")
    if summary["cancelled_count"]:
        lines.append(f"| Cancelled | {summary['cancelled_count']} entries ({money(summary['cancelled_value'], currency)}) |")

    lines += ["", "## Cost by category", "", "| Category | Entries | Total | Share |", "|---|---:|---:|---:|"]
    for cat, v in summary["by_category"].items():
        lines.append(f"| {cat} | {v['count']} | {money(v['total'], currency)} | {v['share']}% |")

    lines += ["", "## Alerts", ""]
    lines += [f"- **{w.level.upper()}**: {_md(w.message)}" for w in warnings] or ["- None"]

    lines += ["", "## Itinerary", "", "| ID | Destination | Category | Start | End | Cost | Status | Notes |", "|---:|---|---|---|---|---:|---|---|"]
    for r in sort_records(records, "Start date"):
        lines.append(f"| {r.id} | {_md(r.destination)} | {r.category} | {r.start_date} | {r.end_date} | {r.est_cost:,.2f} | {r.status} | {_md(r.notes)} |")
    return "\n".join(lines) + "\n"


def to_audit_text(records: list[Record], summary: dict, warnings: list[Warn], currency: str, generated_on: date) -> str:
    width = 100
    lines = [
        "=" * width,
        f"TRAVEL ITINERARY AUDIT LOG  |  generated {generated_on.isoformat()}",
        "=" * width,
        f"Entries counted : {summary['count']}",
        f"Total estimate  : {money(summary['total'], currency)}",
        f"Average         : {money(summary['average'], currency)}",
        f"Cancelled       : {summary['cancelled_count']} ({money(summary['cancelled_value'], currency)})",
    ]
    if summary["budget_used_pct"] is not None:
        lines.append(f"Budget          : {money(summary['budget'], currency)} ({summary['budget_used_pct']}% used)")
    lines += ["", f"ALERTS ({len(warnings)})", "-" * width]
    lines += [f"[{w.level.upper():8}] {w.message}" for w in warnings] or ["None"]
    lines += ["", "RECORDS", "-" * width,
              f"{'ID':>4}  {'Destination':<22}{'Category':<10}{'Start':<11}{'End':<11}{'Cost':>12}  {'Status':<10}",
              "-" * width]
    for r in sort_records(records, "Start date"):
        lines.append(f"{r.id:>4}  {r.destination[:21]:<22}{r.category:<10}{r.start_date:<11}{r.end_date:<11}{r.est_cost:>12,.2f}  {r.status:<10}")
        if r.notes:
            lines.append(f"      note: {r.notes}")
    lines.append("=" * width)
    return "\n".join(lines) + "\n"


def to_csv_text(records: list[Record]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for r in sort_records(records, "Start date"):
        d = r.to_dict()
        writer.writerow([d[c] for c in CSV_COLUMNS])
    return buffer.getvalue()


def to_json_text(state: State) -> str:
    return json.dumps(
        {"schema_version": 1, "budget": state.budget, "currency": state.currency,
         "records": [r.to_dict() for r in state.records]},
        indent=2, ensure_ascii=False,
    )
