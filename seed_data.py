"""Generate the sample datasets in sample_data/.

Run:  python seed_data.py

Writes sample_itinerary.csv, sample_itinerary.json (41 rows incl. boundary and
edge cases) and bad_import.csv (rows that are deliberately invalid).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from itinerary.models import CSV_COLUMNS

OUT = Path(__file__).parent / "sample_data"
BUDGET = 300000  # sample total is about 276k, so the "near budget" alert fires; lower it live to demo "over budget"
CURRENCY = "INR"

# (destination, category, start, end, cost, status, notes)
ROWS = [
    # Goa + Hampi, Dec 2026
    ("Goa", "Flight", "2026-12-20", "2026-12-20", 9800, "Booked", "Hyderabad to Goa, IndiGo morning flight"),
    ("Goa", "Stay", "2026-12-20", "2026-12-24", 22000, "Booked", "Beachside resort, 4 nights"),
    ("Goa", "Activity", "2026-12-21", "2026-12-21", 3500, "Planned", "Scuba at Grande Island"),
    ("Goa", "Food", "2026-12-22", "2026-12-22", 2400, "Planned", "Seafood dinner on the beach"),
    ("Goa", "Transport", "2026-12-20", "2026-12-24", 6000, "Planned", "Scooter rental, 4 days"),
    ("Goa", "Flight", "2026-12-24", "2026-12-24", 8700, "Booked", "Return leg"),
    ("Hampi", "Stay", "2026-12-24", "2026-12-26", 5600, "Planned", "Heritage homestay (same-day checkout/check-in with Goa is fine)"),
    ("Hampi", "Activity", "2026-12-25", "2026-12-25", 1200, "Planned", "Virupaksha temple and coracle ride"),
    ("Hampi", "Transport", "2026-12-24", "2026-12-24", 3200, "Planned", "Cab from Goa"),
    # Singapore, Feb 2027
    ("Singapore", "Flight", "2027-02-10", "2027-02-10", 24000, "Planned", "Outbound"),
    ("Singapore", "Stay", "2027-02-10", "2027-02-15", 30000, "Planned", "Hotel near Orchard Road"),
    ("Singapore", "Activity", "2027-02-12", "2027-02-12", 6500, "Planned", "Universal Studios"),
    ("Singapore", "Food", "2027-02-13", "2027-02-13", 4500, "Planned", "Hawker centre crawl"),
    ("Singapore", "Transport", "2027-02-10", "2027-02-15", 2000, "Planned", "Transit card top-up"),
    ("Singapore", "Shopping", "2027-02-14", "2027-02-14", 5000, "Planned", "Gifts"),
    ("Singapore", "Flight", "2027-02-15", "2027-02-15", 22000, "Planned", "Return"),
    # Manali, Jan 2027
    ("Manali", "Flight", "2027-01-08", "2027-01-08", 7200, "Planned", "Delhi to Bhuntar"),
    ("Manali", "Stay", "2027-01-08", "2027-01-12", 14000, "Planned", "Cottage with heater"),
    ("Manali", "Activity", "2027-01-10", "2027-01-10", 2800, "Planned", "Skiing at Solang Valley"),
    ("Manali", "Transport", "2027-01-08", "2027-01-08", 1800, "Booked", "Taxi from airport"),
    ("Manali", "Food", "2027-01-09", "2027-01-09", 1600, "Planned", "Local Himachali thali"),
    # Jaipur, already in the past (overdue / done examples)
    ("Jaipur", "Stay", "2026-10-18", "2026-10-20", 9000, "Done", "Haveli stay"),
    ("Jaipur", "Activity", "2026-10-19", "2026-10-19", 1500, "Planned", "Amber Fort (never marked done)"),
    ("Jaipur", "Food", "2026-10-19", "2026-10-19", 1800, "Done", "Rajasthani dinner"),
    ("Jaipur", "Transport", "2026-10-18", "2026-10-20", 4200, "Booked", "Driver for 3 days (never marked done)"),
    # Kerala, Mar 2027
    ("Kochi", "Flight", "2027-03-05", "2027-03-05", 6400, "Planned", "Arrival"),
    ("Munnar", "Stay", "2027-03-06", "2027-03-08", 11000, "Planned", "Tea estate bungalow"),
    ("Alleppey", "Stay", "2027-03-08", "2027-03-10", 16000, "Planned", "Houseboat"),
    ("Alleppey", "Activity", "2027-03-09", "2027-03-09", 3000, "Planned", "Backwater canoe tour"),
    ("Kochi", "Food", "2027-03-10", "2027-03-10", 1200, "Planned", "Farewell dinner"),
    # Edge cases
    ("Delhi", "Stay", "2027-01-10", "2027-01-11", 4500, "Planned", "Overlaps the Manali stay, should raise a critical alert"),
    ("Mumbai", "Food", "2026-11-26", "2026-11-26", 0, "Planned", "Free tasting event (zero-cost boundary)"),
    ("Pune", "Activity", "2026-11-28", "2026-11-28", 800, "Planned", "Starts within a week and still not booked"),
    ("Hyderabad", "Other", "2026-11-25", "2026-11-25", 500, "Planned", "Single-day entry (start equals end)"),
    ("Ooty", "Stay", "2027-04-01", "2027-04-05", 9500, "Cancelled", "Cancelled because of the rain forecast"),
    ("Ooty", "Transport", "2027-04-01", "2027-04-01", 2500, "Cancelled", "Cancelled together with the stay"),
    ("Lisbon", "Food", "2027-05-02", "2027-05-02", 24000, "Planned", "Tasting menu (cost anomaly vs other food entries)"),
    ("Chennai", "Other", "2027-06-01", "2027-06-01", 0.01, "Planned", "Smallest non-zero cost boundary"),
    ("Leh", "Stay", "2027-06-10", "2027-09-10", 3000, "Planned", "Very long span, check the dates"),
    ("Udaipur", "Activity", "2027-02-20", "2027-02-20", 2200, "Planned", 'Boat ride on Lake Pichola, "sunset slot", incl. tax, café stop'),
    ("Goa", "Activity", "2026-12-21", "2026-12-21", 3500, "Planned", "Scuba at Grande Island (accidental duplicate)"),
]

BAD_IMPORT = [
    ("destination", "category", "start_date", "end_date", "est_cost", "status", "notes"),
    ("Varanasi", "Stay", "2027-03-15", "2027-03-17", "7500", "Planned", "Valid row"),
    ("Agra", "Activity", "15/03/2027", "15/03/2027", "1,250.50", "Booked", "Valid: DD/MM/YYYY date and comma in cost"),
    ("", "Stay", "2027-03-15", "2027-03-17", "7500", "Planned", "Blank destination"),
    ("Shimla", "Stay", "31/02/2027", "02/03/2027", "5000", "Planned", "Impossible date (31 Feb)"),
    ("Rishikesh", "Activity", "2027-04-10", "2027-04-05", "2000", "Planned", "End before start"),
    ("Darjeeling", "Food", "2027-04-10", "2027-04-10", "-300", "Planned", "Negative cost"),
    ("Coorg", "Stay", "2027-04-12", "2027-04-14", "abc", "Planned", "Non-numeric cost"),
    ("Kovalam", "Stay", "2027-04-12", "2027-04-14", "10000001", "Planned", "Cost above the 10,000,000 limit"),
    ("Pondicherry", "Spa", "2027-04-20", "2027-04-20", "3000", "Planned", "Unknown category"),
    ("Mysore", "Activity", "2027-04-22", "2027-04-22", "900", "Maybe", "Unknown status"),
    ("Khajuraho", "Stay", "2027-04-25"),
    ("Hampi", "Stay", "2026-12-24", "2026-12-26", "5600", "Planned", "Duplicate of a sample row (skipped, not an error)"),
]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    records = [
        {"id": i, "destination": d, "category": c, "start_date": s, "end_date": e,
         "est_cost": float(cost), "status": st, "notes": n}
        for i, (d, c, s, e, cost, st, n) in enumerate(ROWS, start=1)
    ]
    with open(OUT / "sample_itinerary.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    with open(OUT / "sample_itinerary.json", "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 1, "budget": BUDGET, "currency": CURRENCY, "records": records},
                  fh, indent=2, ensure_ascii=False)
    with open(OUT / "bad_import.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(BAD_IMPORT)
    print(f"Wrote {len(records)} sample rows and {len(BAD_IMPORT) - 1} import-test rows to {OUT}")


if __name__ == "__main__":
    main()
