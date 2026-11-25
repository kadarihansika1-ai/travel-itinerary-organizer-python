# 🧭 Wanderlist: Travel Itinerary Organizer

A Streamlit app to organize destinations, dates, notes and estimated costs. The core logic uses only the Python standard library. Streamlit is needed only for the UI.

## Run it

```bash
ents.txt
streamlit runpython -m venv .venv                 # Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirem app.py
```

Needs Python 3.10+. Data is saved to `data/itinerary.json` and survives restarts.

Quick start: open **Import / Export → Sample data & reset → Load sample dataset** to fill the app with 41 demo entries.

## Features

| Brief requirement | Where |
|---|---|
| Menu-driven interface | Streamlit sidebar (5 pages) |
| Defensive input validation | `itinerary/validation.py`: all errors are reported together |
| Core logic: organize destinations, dates, notes, costs | `itinerary/logic.py` |
| Local persistence (JSON), recovery from bad files | `itinerary/storage.py`: atomic writes, corrupt files quarantined |
| Keyword and category search | **Browse & Search**: keyword, category, status, date range, cost range, sort, pagination |
| Executive summary | **Dashboard**: totals, average, budget, category/month/status breakdowns, next up |
| Multi-format export | Markdown, plain-text audit log, CSV, JSON |
| Threshold warnings | Over budget, overdue, starting soon but unbooked, cost anomalies, overlapping stays |
| Bulk CSV import with error log | **Import CSV**: valid rows imported, bad rows listed with reasons |

## Project layout

```
app.py              Streamlit UI
itinerary/          UI-independent core (models, validation, storage, logic, importer, exporter)
seed_data.py        Regenerates sample_data/
sample_data/        41-row CSV + JSON, and bad_import.csv for the import demo
tests/test_core.py  32 unit tests
PLAN.md             Implementation plan and demo script
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- Cancelled entries are excluded from totals, averages and charts, and shown separately.
- Dates can be entered as `YYYY-MM-DD`, `DD/MM/YYYY` or `DD-MM-YYYY` in CSV imports.
- Corrupted data files are renamed to `itinerary.json.corrupt-<timestamp>` and a clean file is created.
- Alerts use today's date. The sample data is dated Oct 2026 to Sep 2027.
