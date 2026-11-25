# Wanderlist: Travel Itinerary Organizer, Implementation Plan

Project #52 · StudentLife Hack · Domain: Travel & Transport

## 1. Decisions

| Decision | Choice | Why |
|---|---|---|
| UI framework | **Streamlit** | Fastest path to a polished demo: forms, tables, charts, downloads and file upload are built in. FastHTML needs hand-written HTML/HTMX; NiceGUI is great for event-driven apps but has more boilerplate for tables and charts. |
| Core logic | Pure Python **standard library** | Matches the brief's zero-dependency core. The UI is a thin layer, so the core is testable without Streamlit. |
| Storage | One JSON file (`data/itinerary.json`), atomic writes | Survives restarts, human-readable, schema-checked on load. |
| Interchange | CSV import (with row-level error log) and CSV / Markdown / TXT / JSON export | Covers the bulk-import and multi-format export stretch features. |

The brief lists a terminal menu as a must-have. Here it is replaced by a Streamlit sidebar menu, as requested. The `itinerary/` package has no UI code, so a CLI could be added later.

## 2. Architecture

```
app.py                    Streamlit UI (pages, forms, charts, downloads)
itinerary/
  models.py               Record, State, Warn dataclasses; CATEGORIES, STATUSES
  validation.py           Parsing + range checks; every failure becomes a readable message
  storage.py              Load/save JSON; recovers from missing/corrupt files
  logic.py                Filter, sort, paginate, summarize, warnings
  importer.py             Bulk CSV import with row-by-row error log
  exporter.py             Markdown, plain-text audit log, CSV, JSON
seed_data.py              Generates sample_data/ (41 rows + a deliberately bad CSV)
tests/test_core.py        unittest suite (no third-party deps)
```

Data flow: UI → `validation.make_record` → `State.records` → `Store.save`. Reads: `Store.load` → `logic.*` → UI.

## 3. Data model

`Record`: `id`, `destination`, `category`, `start_date`, `end_date` (ISO strings), `est_cost` (float), `status`, `notes`.
`State`: `budget`, `currency`, `records`.

- Categories: Flight, Stay, Activity, Food, Transport, Shopping, Other
- Statuses: Planned, Booked, Done, Cancelled (cancelled items are excluded from totals)

## 4. Validation rules

| Field | Rule |
|---|---|
| Destination | 2–80 chars, must contain a letter, limited punctuation `. , ' & ( ) / -` |
| Dates | `YYYY-MM-DD`, `DD/MM/YYYY` or `DD-MM-YYYY`; real calendar dates; year 2000–2100 |
| Date order | End date must not be before start date |
| Cost | Number (commas and ₹ $ € £ allowed), 0 ≤ cost ≤ 10,000,000, rounded to 2 decimals; NaN/inf rejected |
| Category / Status | Must be one of the allowed values (case-insensitive) |
| Notes | Max 500 chars; control characters and newlines collapsed |

## 4a. Warning rules

| Level | Trigger |
|---|---|
| Critical | Total exceeds budget; two stays in different places overlap |
| Warning | Spend ≥ 90% of budget; end date passed but still Planned/Booked; starts within 7 days and not Booked; cost > 3× its category median (categories with ≥ 4 items) |
| Info | Zero-cost flight or stay; span longer than 90 days; possible duplicate entry |

## 5. UI pages

1. **Dashboard**: metrics, budget bar, alerts, cost by category and month, status table, next-up item
2. **Add entry**: validated form (cost is free text so validation can be demonstrated)
3. **Browse & Search**: keyword, category, status, date range, cost range, sort, pagination
4. **Edit / Delete**: prefilled form, delete needs confirmation
5. **Import / Export**: CSV import with error log, four export formats, sample-data loader, reset
6. Sidebar: trip budget and currency

## 6. Milestones

| # | Milestone | Done when |
|---|---|---|
| 1 | Core package | Validation, storage, logic importable and unit-tested |
| 2 | Sample data | 41-row CSV + JSON and bad-import CSV generated |
| 3 | Streamlit UI | All five pages work against the core |
| 4 | Import/export + warnings | Round-trip export → import works |
| 5 | Demo polish | README, demo script rehearsed |

## 7. Demo script (about 4 minutes)

1. `streamlit run app.py`. Show the empty dashboard and welcome screen.
2. Import / Export → Sample data → load the 41-entry dataset. Dashboard fills with metrics, charts and alerts.
3. Add entry: enter destination `X`, dates reversed, cost `abc`. Show every error at once. Fix and save.
4. Browse & Search: search `goa`, filter Category = Stay, sort by cost.
5. Import the `bad_import.csv`. Show valid rows accepted and the row-by-row error log.
6. Stop the app, relaunch, and show the data is still there (persistence).
7. Export the Markdown report and show the alerts.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Corrupt or hand-edited data file | Quarantined as `.corrupt-<timestamp>`, fresh file created, invalid rows reported |
| Crash mid-write | Write to temp file, `fsync`, then `os.replace` |
| Streamlit version drift | Pin `streamlit>=1.40`; avoid deprecated arguments |
| Demo-day date sensitivity | Warnings use today's date; sample data is dated around Nov 2026–Jun 2027 |
