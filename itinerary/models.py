"""Data structures shared by every module."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

CATEGORIES = ("Flight", "Stay", "Activity", "Food", "Transport", "Shopping", "Other")
STATUSES = ("Planned", "Booked", "Done", "Cancelled")
CSV_COLUMNS = ("id", "destination", "category", "start_date", "end_date", "est_cost", "status", "notes")


@dataclass
class Record:
    id: int
    destination: str
    category: str
    start_date: str  # ISO yyyy-mm-dd
    end_date: str  # ISO yyyy-mm-dd
    est_cost: float
    status: str = "Planned"
    notes: str = ""

    @property
    def start(self) -> date:
        return date.fromisoformat(self.start_date)

    @property
    def end(self) -> date:
        return date.fromisoformat(self.end_date)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class State:
    budget: float = 0.0
    currency: str = "INR"
    records: list[Record] = field(default_factory=list)


@dataclass(frozen=True)
class Warn:
    level: str  # "critical" | "warning" | "info"
    code: str
    message: str
    record_id: int | None = None
