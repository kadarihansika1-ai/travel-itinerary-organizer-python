"""Business logic: search, sort, summaries and warning rules."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date

from .models import Record, Warn

ANOMALY_FACTOR = 3.0
UPCOMING_DAYS = 7
LONG_SPAN_DAYS = 90
BUDGET_WARN_RATIO = 0.9

SORT_KEYS = {
    "Start date": lambda r: (r.start_date, r.id),
    "Destination": lambda r: (r.destination.lower(), r.start_date),
    "Category": lambda r: (r.category, r.start_date),
    "Status": lambda r: (r.status, r.start_date),
    "Cost": lambda r: (r.est_cost, r.id),
}


def money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def next_id(records: list[Record]) -> int:
    return max((r.id for r in records), default=0) + 1


def active(records: list[Record]) -> list[Record]:
    """Records that count toward totals (everything except Cancelled)."""
    return [r for r in records if r.status != "Cancelled"]


# ---------- search / sort / paginate ----------
def filter_records(records, keyword="", categories=None, statuses=None,
                   date_from: date | None = None, date_to: date | None = None,
                   min_cost: float | None = None, max_cost: float | None = None):
    words = keyword.lower().split()
    out = []
    for r in records:
        haystack = f"{r.destination} {r.category} {r.status} {r.notes}".lower()
        if words and not all(w in haystack for w in words):
            continue
        if categories and r.category not in categories:
            continue
        if statuses and r.status not in statuses:
            continue
        if date_from and r.end < date_from:
            continue
        if date_to and r.start > date_to:
            continue
        if min_cost is not None and r.est_cost < min_cost:
            continue
        if max_cost is not None and r.est_cost > max_cost:
            continue
        out.append(r)
    return out


def sort_records(records, key: str = "Start date", descending: bool = False):
    return sorted(records, key=SORT_KEYS[key], reverse=descending)


def paginate(items: list, page: int, size: int) -> tuple[list, int]:
    pages = max(1, math.ceil(len(items) / size))
    page = min(max(1, page), pages)
    return items[(page - 1) * size: page * size], pages


# ---------- summary ----------
def summarize(records: list[Record], budget: float, today: date) -> dict:
    act = active(records)
    total = round(sum(r.est_cost for r in act), 2)
    count = len(act)

    by_category: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0})
    by_month: dict[str, float] = defaultdict(float)
    by_destination: dict[str, float] = defaultdict(float)
    for r in act:
        by_category[r.category]["count"] += 1
        by_category[r.category]["total"] += r.est_cost
        by_month[r.start_date[:7]] += r.est_cost
        by_destination[r.destination] += r.est_cost
    for value in by_category.values():
        value["total"] = round(value["total"], 2)
        value["share"] = round(value["total"] / total * 100, 1) if total else 0.0

    by_status: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0})
    for r in records:
        by_status[r.status]["count"] += 1
        by_status[r.status]["total"] = round(by_status[r.status]["total"] + r.est_cost, 2)

    cancelled = [r for r in records if r.status == "Cancelled"]
    upcoming = [r for r in act if r.status in ("Planned", "Booked") and r.start >= today]
    destinations = sorted(by_destination.items(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "total": total,
        "count": count,
        "average": round(total / count, 2) if count else 0.0,
        "highest": max(act, key=lambda r: r.est_cost, default=None),
        "lowest": min(act, key=lambda r: r.est_cost, default=None),
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1]["total"])),
        "by_status": dict(by_status),
        "by_month": {k: round(v, 2) for k, v in sorted(by_month.items())},
        "by_destination": [(d, round(v, 2)) for d, v in destinations],
        "top_destination": destinations[0][0] if destinations else None,
        "destination_count": len(by_destination),
        "trip_start": min((r.start for r in act), default=None),
        "trip_end": max((r.end for r in act), default=None),
        "budget": budget,
        "budget_used_pct": round(total / budget * 100, 1) if budget > 0 else None,
        "remaining": round(budget - total, 2) if budget > 0 else None,
        "cancelled_count": len(cancelled),
        "cancelled_value": round(sum(r.est_cost for r in cancelled), 2),
        "next_item": min(upcoming, key=lambda r: (r.start, r.id), default=None),
    }


# ---------- warnings ----------
def _label(r: Record) -> str:
    return f"#{r.id} {r.destination} ({r.category}, {r.start_date})"


def find_warnings(records: list[Record], budget: float, today: date, currency: str = "INR") -> list[Warn]:
    act = active(records)
    found: list[Warn] = []

    # Budget
    total = sum(r.est_cost for r in act)
    if budget > 0:
        if total > budget:
            found.append(Warn("critical", "over_budget",
                              f"Over budget by {money(total - budget, currency)} ({money(total, currency)} planned vs {money(budget, currency)})."))
        elif total >= budget * BUDGET_WARN_RATIO:
            found.append(Warn("warning", "near_budget",
                              f"{total / budget * 100:.0f}% of the budget is already planned ({money(budget - total, currency)} left)."))

    # Overdue / starting soon
    for r in act:
        if r.status in ("Planned", "Booked") and r.end < today:
            found.append(Warn("warning", "overdue",
                              f"Overdue: {_label(r)} ended {r.end_date} but is still {r.status}.", r.id))
        elif r.status == "Planned" and 0 <= (r.start - today).days <= UPCOMING_DAYS:
            days = (r.start - today).days
            when = "today" if days == 0 else f"in {days} day(s)"
            found.append(Warn("warning", "unbooked_soon",
                              f"Starts {when} but not booked yet: {_label(r)}.", r.id))

    # Cost anomalies (per category, needs enough data to be meaningful)
    groups: dict[str, list[Record]] = defaultdict(list)
    for r in act:
        groups[r.category].append(r)
    for category, items in groups.items():
        if len(items) >= 4:
            median = statistics.median(r.est_cost for r in items)
            if median > 0:
                for r in items:
                    if r.est_cost > ANOMALY_FACTOR * median:
                        found.append(Warn("warning", "cost_anomaly",
                                          f"Unusual cost: {_label(r)} is {money(r.est_cost, currency)}, over {ANOMALY_FACTOR:.0f}x the {category} median ({money(median, currency)}).", r.id))

    # Overlapping stays in different places (same-day checkout/check-in is fine)
    stays = sorted((r for r in act if r.category == "Stay"), key=lambda r: (r.start_date, r.id))
    for i, a in enumerate(stays):
        for b in stays[i + 1:]:
            if b.start >= a.end:
                break
            if a.start < b.end and b.start < a.end and a.destination.lower() != b.destination.lower():
                found.append(Warn("critical", "stay_overlap",
                                  f"Overlapping stays: {_label(a)} and {_label(b)}.", b.id))

    # Zero-cost flights/stays, very long spans, duplicates
    seen: dict[tuple, int] = {}
    for r in act:
        if r.est_cost == 0 and r.category in ("Flight", "Stay"):
            found.append(Warn("info", "zero_cost", f"Zero cost on a {r.category.lower()}: {_label(r)}.", r.id))
        if (r.end - r.start).days > LONG_SPAN_DAYS:
            found.append(Warn("info", "long_span", f"Very long span ({r.days} days): {_label(r)}.", r.id))
        key = (r.destination.lower(), r.category, r.start_date, r.end_date, r.est_cost)
        if key in seen:
            found.append(Warn("info", "duplicate", f"Possible duplicate: {_label(r)} matches #{seen[key]}.", r.id))
        else:
            seen[key] = r.id

    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(found, key=lambda w: (order[w.level], w.record_id or 0))
