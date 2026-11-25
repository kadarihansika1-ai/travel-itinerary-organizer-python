"""JSON persistence with recovery from missing or corrupted files."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .models import Record, State
from .validation import clean_currency, parse_cost, validate_fields

SCHEMA_VERSION = 1


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.notices: list[str] = []

    # ---------- loading ----------
    def load(self) -> State:
        self.notices = []
        if not self.path.exists():
            state = State()
            self.save(state)
            self.notices.append("No data file found, so a fresh itinerary was created.")
            return state
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self._quarantine(f"not valid JSON: {exc.__class__.__name__}")
        except OSError as exc:
            self.notices.append(f"Could not read the data file ({exc.__class__.__name__}); starting empty without overwriting it.")
            return State()
        if not isinstance(raw, dict) or not isinstance(raw.get("records", []), list):
            return self._quarantine("unexpected structure")
        return self._parse(raw)

    def _parse(self, raw: dict) -> State:
        state = State()
        try:
            budget = parse_cost(raw.get("budget", 0))
        except ValueError:
            budget = 0.0
            self.notices.append("Saved budget was invalid and was reset to 0.")
        state.budget = budget
        currency, error = clean_currency(raw.get("currency", "INR"))
        state.currency = currency if currency else "INR"
        if error:
            self.notices.append("Saved currency was invalid and was reset to INR.")

        used_ids: set[int] = set()
        pending: list[Record] = []
        rejected: list[str] = []
        for index, item in enumerate(raw.get("records", []), start=1):
            if not isinstance(item, dict):
                rejected.append(f"item {index}: not an object")
                continue
            clean, errors = validate_fields(
                item.get("destination"), item.get("category"), item.get("start_date"),
                item.get("end_date"), item.get("est_cost"), item.get("status", "Planned"), item.get("notes", ""),
            )
            if errors:
                rejected.append(f"item {index}: {errors[0]}")
                continue
            rid = item.get("id")
            valid_id = isinstance(rid, int) and not isinstance(rid, bool) and rid > 0 and rid not in used_ids
            if valid_id:
                used_ids.add(rid)
            pending.append(Record(id=rid if valid_id else 0, **clean))
        next_free = max(used_ids, default=0) + 1
        for rec in pending:
            if rec.id == 0:
                rec.id = next_free
                next_free += 1
        state.records = pending
        if rejected:
            preview = "; ".join(rejected[:3]) + (" ..." if len(rejected) > 3 else "")
            self.notices.append(f"Skipped {len(rejected)} invalid record(s) in the data file ({preview}).")
        return state

    def _quarantine(self, reason: str) -> State:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        try:
            os.replace(self.path, backup)
            saved = f" The original was kept as {backup.name}."
        except OSError:
            saved = ""
        state = State()
        self.save(state)
        self.notices.append(f"The data file was unreadable ({reason}), so a clean file was created.{saved}")
        return state

    # ---------- saving ----------
    def save(self, state: State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "budget": state.budget,
            "currency": state.currency,
            "records": [r.to_dict() for r in state.records],
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
