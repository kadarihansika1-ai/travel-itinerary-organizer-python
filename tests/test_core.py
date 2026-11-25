"""Core tests (standard library only).  Run:  python -m unittest discover -s tests -v"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from itinerary import exporter, importer, logic  # noqa: E402
from itinerary.models import Record, State  # noqa: E402
from itinerary.storage import Store  # noqa: E402
from itinerary.validation import (  # noqa: E402
    clean_currency, make_record, parse_cost, parse_date, validate_fields,
)

TODAY = date(2026, 11, 25)
ROOT = Path(__file__).resolve().parent.parent


def rec(i, dest="Goa", cat="Stay", s="2026-12-01", e="2026-12-03", cost=1000.0, status="Planned", notes=""):
    return Record(i, dest, cat, s, e, cost, status, notes)


class ValidationTests(unittest.TestCase):
    def test_cost_formats(self):
        self.assertEqual(parse_cost("1,250.504"), 1250.5)
        self.assertEqual(parse_cost("₹ 12,500"), 12500.0)
        self.assertEqual(parse_cost(0), 0.0)
        self.assertEqual(parse_cost("10000000"), 10_000_000.0)

    def test_cost_rejections(self):
        for bad in ["", "   ", "abc", "-1", "10000001", "1e5", "1_000", "nan", "inf", None, True, float("nan"), float("inf"), "1" * 400]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_cost(bad)

    def test_dates(self):
        self.assertEqual(parse_date("2027-03-05"), date(2027, 3, 5))
        self.assertEqual(parse_date("05/03/2027"), date(2027, 3, 5))
        self.assertEqual(parse_date(date(2027, 1, 1)), date(2027, 1, 1))
        for bad in ["", "31/02/2027", "2027-13-01", "tomorrow", "1999-12-31", "2101-01-01"]:
            with self.assertRaises(ValueError, msg=bad):
                parse_date(bad)

    def test_all_errors_reported_together(self):
        clean, errors = validate_fields("X", "Spa", "2027-02-10", "2027-02-01", "abc", "Maybe", "n" * 501)
        self.assertIsNone(clean)
        self.assertGreaterEqual(len(errors), 6)

    def test_valid_record_is_normalised(self):
        r, errors = make_record(5, destination="  Goa  ", category="stay", start_date="2026-12-01",
                                end_date="01/12/2026", est_cost="1,000", status="BOOKED", notes="a\nb\t c")
        self.assertEqual(errors, [])
        self.assertEqual((r.destination, r.category, r.status, r.notes), ("Goa", "Stay", "Booked", "a b c"))

    def test_destination_rules(self):
        for bad in ["", "A", "1234", "<script>", "x" * 81]:
            _, errors = validate_fields(bad, "Stay", "2026-12-01", "2026-12-01", "1", "Planned", "")
            self.assertTrue(errors, bad)
        for good in ["São Paulo", "St. John's", "Rio (Brazil)", "東京 Tokyo"]:
            _, errors = validate_fields(good, "Stay", "2026-12-01", "2026-12-01", "1", "Planned", "")
            self.assertEqual(errors, [], good)

    def test_currency(self):
        self.assertEqual(clean_currency(" inr "), ("INR", None))
        self.assertEqual(clean_currency("₹"), ("₹", None))
        self.assertIsNotNone(clean_currency("12")[1])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data" / "it.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_creates_template(self):
        store = Store(self.path)
        state = store.load()
        self.assertEqual(state.records, [])
        self.assertTrue(self.path.exists())

    def test_round_trip(self):
        store = Store(self.path)
        state = State(budget=5000, currency="USD", records=[rec(1, notes="café, \"quoted\"")])
        store.save(state)
        loaded = Store(self.path).load()
        self.assertEqual(loaded.records, state.records)
        self.assertEqual((loaded.budget, loaded.currency), (5000.0, "USD"))

    def test_corrupt_json_is_quarantined(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        store = Store(self.path)
        state = store.load()
        self.assertEqual(state.records, [])
        self.assertEqual(len(list(self.path.parent.glob("it.json.corrupt-*"))), 1)
        self.assertTrue(store.notices)
        json.loads(self.path.read_text(encoding="utf-8"))  # fresh file is valid

    def test_binary_garbage_is_quarantined(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"\xff\xfe\x00\x80garbage")
        Store(self.path).load()
        self.assertEqual(len(list(self.path.parent.glob("it.json.corrupt-*"))), 1)

    def test_wrong_structure_is_quarantined(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        Store(self.path).load()
        self.assertEqual(len(list(self.path.parent.glob("it.json.corrupt-*"))), 1)

    def test_invalid_records_skipped_and_ids_repaired(self):
        self.path.parent.mkdir(parents=True)
        good = rec(1).to_dict()
        dup_id = rec(1, dest="Hampi").to_dict()
        bad = {"id": 3, "destination": "", "category": "Stay"}
        self.path.write_text(json.dumps({"budget": "oops", "records": [good, dup_id, bad, "junk"]}), encoding="utf-8")
        store = Store(self.path)
        state = store.load()
        self.assertEqual(len(state.records), 2)
        self.assertEqual(len({r.id for r in state.records}), 2)
        self.assertEqual(state.budget, 0.0)
        self.assertTrue(any("Skipped 2" in n for n in store.notices))


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            rec(1, "Goa", "Stay", cost=1000), rec(2, "Goa", "Food", "2026-12-02", "2026-12-02", 500, notes="Seafood dinner"),
            rec(3, "Hampi", "Stay", "2026-12-03", "2026-12-05", 2000, "Booked"),
            rec(4, "Ooty", "Stay", "2027-01-01", "2027-01-02", 9999, "Cancelled"),
        ]

    def test_cancelled_excluded_from_totals(self):
        s = logic.summarize(self.records, 0, TODAY)
        self.assertEqual(s["total"], 3500.0)
        self.assertEqual(s["count"], 3)
        self.assertEqual(s["average"], 1166.67)
        self.assertEqual(s["cancelled_count"], 1)
        self.assertEqual(s["cancelled_value"], 9999.0)
        self.assertEqual(s["top_destination"], "Hampi")
        self.assertEqual(s["by_category"]["Stay"]["total"], 3000.0)
        self.assertIsNone(s["budget_used_pct"])

    def test_empty_summary(self):
        s = logic.summarize([], 1000, TODAY)
        self.assertEqual((s["total"], s["count"], s["average"]), (0.0, 0, 0.0))
        self.assertIsNone(s["next_item"])

    def test_search(self):
        r = self.records
        self.assertEqual([x.id for x in logic.filter_records(r, "goa")], [1, 2])
        self.assertEqual([x.id for x in logic.filter_records(r, "GOA seafood")], [2])
        self.assertEqual([x.id for x in logic.filter_records(r, categories=["Stay"], statuses=["Booked"])], [3])
        self.assertEqual([x.id for x in logic.filter_records(r, min_cost=1000, max_cost=2000)], [1, 3])
        self.assertEqual([x.id for x in logic.filter_records(r, date_from=date(2026, 12, 4), date_to=date(2026, 12, 4))], [3])
        self.assertEqual(logic.filter_records(r, "zzz"), [])

    def test_sort_and_paginate(self):
        self.assertEqual([x.id for x in logic.sort_records(self.records, "Cost", True)], [4, 3, 1, 2])
        items, pages = logic.paginate(list(range(25)), 3, 10)
        self.assertEqual((len(items), pages), (5, 3))
        self.assertEqual(logic.paginate([], 1, 10), ([], 1))
        self.assertEqual(logic.paginate(list(range(25)), 99, 10)[0], list(range(20, 25)))

    def test_next_id(self):
        self.assertEqual(logic.next_id([]), 1)
        self.assertEqual(logic.next_id(self.records), 5)

    def codes(self, records, budget=0.0):
        return [w.code for w in logic.find_warnings(records, budget, TODAY)]

    def test_budget_warnings(self):
        r = [rec(1, cost=1000, s="2027-03-01", e="2027-03-02")]
        self.assertNotIn("over_budget", self.codes(r, 5000))
        self.assertIn("near_budget", self.codes(r, 1050))
        self.assertIn("over_budget", self.codes(r, 999))
        self.assertEqual(self.codes(r, 0), [])

    def test_overdue_and_upcoming(self):
        past = rec(1, s="2026-11-01", e="2026-11-02", status="Booked")
        done = rec(2, s="2026-11-01", e="2026-11-02", status="Done")
        soon = rec(3, s="2026-11-28", e="2026-11-28")
        soon_booked = rec(4, s="2026-11-28", e="2026-11-28", status="Booked")
        later = rec(5, s="2026-12-10", e="2026-12-10")
        codes = self.codes([past, done, soon, soon_booked, later])
        self.assertEqual(codes.count("overdue"), 1)
        self.assertEqual(codes.count("unbooked_soon"), 1)

    def test_stay_overlap_boundaries(self):
        same_day = [rec(1, "Goa", s="2026-12-01", e="2026-12-03"), rec(2, "Hampi", s="2026-12-03", e="2026-12-05")]
        overlap = [rec(1, "Goa", s="2026-12-01", e="2026-12-04"), rec(2, "Hampi", s="2026-12-03", e="2026-12-05")]
        same_place = [rec(1, "Goa", s="2026-12-01", e="2026-12-04"), rec(2, "goa", s="2026-12-03", e="2026-12-05")]
        self.assertNotIn("stay_overlap", self.codes(same_day))
        self.assertIn("stay_overlap", self.codes(overlap))
        self.assertNotIn("stay_overlap", self.codes(same_place))

    def test_anomaly_needs_enough_data_and_uses_median(self):
        few = [rec(i, cat="Food", cost=c) for i, c in enumerate([100, 100, 5000], 1)]
        many = [rec(i, cat="Food", cost=c) for i, c in enumerate([100, 120, 110, 5000], 1)]
        self.assertNotIn("cost_anomaly", self.codes(few))
        self.assertEqual(self.codes(many).count("cost_anomaly"), 1)

    def test_info_rules(self):
        codes = self.codes([rec(1, cat="Flight", cost=0), rec(2, s="2027-01-01", e="2027-06-01"), rec(3), rec(4)])
        for code in ("zero_cost", "long_span", "duplicate"):
            self.assertIn(code, codes)

    def test_warning_order(self):
        warnings = logic.find_warnings([rec(1, cost=500, cat="Flight"), rec(2, cost=0, cat="Flight")], 100, TODAY)
        self.assertEqual(warnings[0].level, "critical")
        self.assertEqual(warnings[-1].level, "info")


class ImportExportTests(unittest.TestCase):
    def test_bad_import_file(self):
        text = (ROOT / "sample_data" / "bad_import.csv").read_text(encoding="utf-8")
        existing = Store(ROOT / "sample_data" / "sample_itinerary.json").load().records
        result = importer.import_csv_text(text, existing)
        self.assertIsNone(result.header_error)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(result.errors), 9)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(result.total_rows, 12)
        self.assertEqual(result.records[1].start_date, "2027-03-15")
        self.assertEqual(result.records[1].est_cost, 1250.5)
        self.assertEqual(result.records[0].id, len(existing) + 1)
        log = importer.error_log_csv(result)
        self.assertEqual(log.splitlines()[0], "row,error,original_row")
        self.assertEqual(len(list(__import__("csv").reader(log.splitlines()))), 10)

    def test_header_problems(self):
        self.assertIsNotNone(importer.import_csv_text("", []).header_error)
        self.assertIn("est_cost", importer.import_csv_text("destination,start_date,end_date\nA,1,2\n", []).header_error)

    def test_aliases_blank_rows_and_defaults(self):
        text = "Place,Start,End,Cost\nGoa,2026-12-01,2026-12-02,100\n,,,\n"
        result = importer.import_csv_text(text, [])
        self.assertEqual(len(result.records), 1)
        self.assertEqual((result.records[0].category, result.records[0].status), ("Other", "Planned"))
        self.assertEqual(result.errors, [])

    def test_in_file_duplicates(self):
        text = "destination,start_date,end_date,est_cost\nGoa,2026-12-01,2026-12-02,100\nGOA,2026-12-01,2026-12-02,100\n"
        result = importer.import_csv_text(text, [])
        self.assertEqual((len(result.records), result.duplicates), (1, 1))

    def test_row_limit(self):
        text = "destination,start_date,end_date,est_cost\n" + "".join(f"P{i}x,2026-12-01,2026-12-02,{i}\n" for i in range(5))
        result = importer.import_csv_text(text, [], max_rows=3)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(len(result.errors), 1)

    def test_csv_export_round_trips_through_import(self):
        state = Store(ROOT / "sample_data" / "sample_itinerary.json").load()
        text = exporter.to_csv_text(state.records)
        result = importer.import_csv_text(text, [])
        self.assertEqual(result.errors, [])
        # the sample intentionally contains one duplicate row, which import skips
        self.assertEqual(len(result.records) + result.duplicates, len(state.records))
        self.assertEqual(result.duplicates, 1)

    def test_reports(self):
        state = Store(ROOT / "sample_data" / "sample_itinerary.json").load()
        summary = logic.summarize(state.records, state.budget, TODAY)
        warnings = logic.find_warnings(state.records, state.budget, TODAY, state.currency)
        md = exporter.to_markdown(state.records, summary, warnings, "INR", TODAY)
        txt = exporter.to_audit_text(state.records, summary, warnings, "INR", TODAY)
        self.assertIn("# Travel Itinerary Report", md)
        self.assertIn("## Alerts", md)
        self.assertIn("TRAVEL ITINERARY AUDIT LOG", txt)
        self.assertIn("Overlapping stays", md)
        self.assertEqual(json.loads(exporter.to_json_text(state))["records"][0]["id"], 1)
        pipe = exporter.to_markdown([rec(1, notes="a|b")], logic.summarize([rec(1)], 0, TODAY), [], "INR", TODAY)
        self.assertIn("a\\|b", pipe)


class SampleDataTests(unittest.TestCase):
    def test_sample_dataset_shape(self):
        state = Store(ROOT / "sample_data" / "sample_itinerary.json").load()
        self.assertTrue(30 <= len(state.records) <= 50)
        self.assertEqual(len({r.id for r in state.records}), len(state.records))
        summary = logic.summarize(state.records, state.budget, TODAY)
        self.assertEqual(summary["total"], 276400.01)
        self.assertEqual(summary["budget_used_pct"], 92.1)


if __name__ == "__main__":
    unittest.main()
