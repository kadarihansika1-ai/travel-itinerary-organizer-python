"""Wanderlist: Travel Itinerary Organizer (Streamlit UI).

Run with:  streamlit run app.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from itinerary import exporter, importer, logic
from itinerary.models import CATEGORIES, STATUSES, State
from itinerary.storage import Store
from itinerary.validation import clean_currency, make_record

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "itinerary.json"
SAMPLE_JSON = ROOT / "sample_data" / "sample_itinerary.json"
SAMPLE_CSV = ROOT / "sample_data" / "sample_itinerary.csv"
BAD_CSV = ROOT / "sample_data" / "bad_import.csv"

PAGES = ["📊 Dashboard", "➕ Add entry", "🔎 Browse & Search", "✏️ Edit / Delete", "📥 Import / Export"]
LEVEL_ICON = {"critical": "🔴", "warning": "🟠", "info": "🔵"}
PAGE_SIZE = 10

st.set_page_config(page_title="Wanderlist · Itinerary Organizer", page_icon="🧭", layout="wide")


# ---------- small helpers ----------
def flash(kind: str, message: str) -> None:
    st.session_state.setdefault("flash", []).append((kind, message))


def show_flash() -> None:
    for kind, message in st.session_state.pop("flash", []):
        getattr(st, kind)(message)


def records_df(records, currency: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"ID": r.id, "Destination": r.destination, "Category": r.category, "Start": r.start_date,
         "End": r.end_date, f"Cost ({currency})": r.est_cost, "Status": r.status, "Notes": r.notes}
        for r in records
    ])


def show_errors(errors: list[str]) -> None:
    st.error(f"Please fix {len(errors)} problem(s):\n\n" + "\n".join(f"- {e}" for e in errors))


# ---------- pages ----------
def page_dashboard(state: State, today: date) -> None:
    st.title("🧭 Wanderlist")
    st.caption("Organize destinations, dates, notes and estimated costs in one place.")
    if not state.records:
        st.info("Your itinerary is empty. Add an entry from the sidebar, or open **Import / Export → Sample data** to load 41 demo entries.")
        return

    cur = state.currency
    summary = logic.summarize(state.records, state.budget, today)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total estimated cost", logic.money(summary["total"], cur))
    c2.metric("Entries", summary["count"], help="Cancelled entries are not counted.")
    c3.metric("Average per entry", logic.money(summary["average"], cur))
    c4.metric("Destinations", summary["destination_count"])

    if summary["budget_used_pct"] is not None:
        pct = summary["budget_used_pct"]
        st.progress(min(pct / 100, 1.0), text=f"Budget used: {pct:.1f}% ({logic.money(summary['total'], cur)} of {logic.money(summary['budget'], cur)})")
    else:
        st.caption("No budget set. Add one in the sidebar to enable budget alerts.")

    warnings = logic.find_warnings(state.records, state.budget, today, cur)
    with st.expander(f"⚠️ Alerts ({len(warnings)})", expanded=bool(warnings)):
        if not warnings:
            st.success("Nothing needs attention.")
        for w in warnings:
            st.markdown(f"{LEVEL_ICON[w.level]} **{w.level.title()}**: {w.message}")

    left, right = st.columns(2)
    with left:
        st.subheader("Cost by category")
        st.bar_chart(pd.Series({k: v["total"] for k, v in summary["by_category"].items()}, name="Cost"))
    with right:
        st.subheader("Cost by month")
        st.bar_chart(pd.Series(summary["by_month"], name="Cost"))

    left, right = st.columns(2)
    with left:
        st.subheader("Status")
        st.dataframe(pd.DataFrame(
            [{"Status": s, "Entries": v["count"], f"Total ({cur})": v["total"]} for s, v in summary["by_status"].items()]
        ), hide_index=True)
    with right:
        st.subheader("Top destinations by cost")
        st.dataframe(pd.DataFrame(
            [{"Destination": d, f"Cost ({cur})": v} for d, v in summary["by_destination"][:5]]
        ), hide_index=True)

    nxt = summary["next_item"]
    if nxt:
        st.info(f"**Next up:** {nxt.destination} · {nxt.category} · {nxt.start_date} (in {(nxt.start - today).days} days) · status {nxt.status}")
    if summary["highest"]:
        h = summary["highest"]
        st.caption(f"Most expensive entry: {h.destination} ({h.category}) at {logic.money(h.est_cost, cur)}. "
                   f"Trip window: {summary['trip_start']} to {summary['trip_end']}.")


ADD_KEYS = ["add_dest", "add_cat", "add_start", "add_end", "add_cost", "add_status", "add_notes"]


def page_add(state: State, store: Store, today: date) -> None:
    st.title("➕ Add entry")
    if st.session_state.pop("add_reset", False):
        for key in ADD_KEYS:
            st.session_state.pop(key, None)
    st.caption("Every field is checked before saving. All problems are listed together.")
    with st.form("add_form", clear_on_submit=False):
        dest = st.text_input("Destination", key="add_dest", placeholder="e.g. Goa")
        c1, c2 = st.columns(2)
        category = c1.selectbox("Category", CATEGORIES, key="add_cat")
        status = c2.selectbox("Status", STATUSES, key="add_status")
        d1, d2 = st.columns(2)
        start = d1.date_input("Start date", value=today, key="add_start")
        end = d2.date_input("End date", value=today, key="add_end")
        cost = st.text_input(f"Estimated cost ({state.currency})", key="add_cost", placeholder="e.g. 12500 or 12,500.50")
        notes = st.text_area("Notes", key="add_notes", placeholder="Booking refs, ideas, reminders (max 500 characters)")
        submitted = st.form_submit_button("Save entry", type="primary")

    if submitted:
        record, errors = make_record(
            logic.next_id(state.records), destination=dest, category=category, start_date=start,
            end_date=end, est_cost=cost, status=status, notes=notes,
        )
        if errors:
            show_errors(errors)
            return
        state.records.append(record)
        store.save(state)
        flash("success", f"Saved #{record.id}: {record.destination} ({record.category}, {logic.money(record.est_cost, state.currency)}).")
        st.session_state["add_reset"] = True
        st.rerun()


def page_browse(state: State, today: date) -> None:
    st.title("🔎 Browse & Search")
    if not state.records:
        st.info("Nothing to search yet.")
        return
    cur = state.currency

    keyword = st.text_input("Keyword", placeholder="Searches destination, category, status and notes, e.g. 'goa scuba'")
    f1, f2 = st.columns(2)
    cats = f1.multiselect("Category", CATEGORIES)
    stats = f2.multiselect("Status", STATUSES)
    f3, f4, f5 = st.columns(3)
    use_dates = f3.checkbox("Filter by date range")
    date_from = f3.date_input("From", value=today, disabled=not use_dates)
    date_to = f4.date_input("To", value=today, disabled=not use_dates)
    max_value = max(r.est_cost for r in state.records)
    cost_range = f5.slider("Cost range", 0.0, float(max_value), (0.0, float(max_value)))
    s1, s2 = st.columns(2)
    sort_key = s1.selectbox("Sort by", list(logic.SORT_KEYS))
    descending = s2.toggle("Descending")

    matches = logic.filter_records(
        state.records, keyword, cats, stats,
        date_from if use_dates else None, date_to if use_dates else None,
        cost_range[0] if cost_range[0] > 0 else None,
        cost_range[1] if cost_range[1] < max_value else None,
    )
    matches = logic.sort_records(matches, sort_key, descending)
    subtotal = sum(r.est_cost for r in logic.active(matches))
    st.markdown(f"**{len(matches)}** of {len(state.records)} entries match · subtotal (excluding cancelled): **{logic.money(subtotal, cur)}**")
    if use_dates and date_to < date_from:
        st.warning("The 'To' date is before the 'From' date, so nothing can match.")
    if not matches:
        st.info("No entries match these filters.")
        return

    pages = logic.paginate(matches, 1, PAGE_SIZE)[1]
    page = st.number_input(f"Page (1-{pages})", min_value=1, max_value=pages, value=1, step=1) if pages > 1 else 1
    chunk, _ = logic.paginate(matches, int(page), PAGE_SIZE)
    st.dataframe(records_df(chunk, cur), hide_index=True)
    st.caption(f"Showing {len(chunk)} entries on page {int(page)} of {pages}.")


def page_edit(state: State, store: Store, today: date) -> None:
    st.title("✏️ Edit / Delete")
    if not state.records:
        st.info("Nothing to edit yet.")
        return
    ordered = logic.sort_records(state.records, "Start date")
    labels = {r.id: f"#{r.id} · {r.destination} · {r.category} · {r.start_date}" for r in ordered}
    rid = st.selectbox("Choose an entry", list(labels), format_func=labels.get)
    index = next(i for i, r in enumerate(state.records) if r.id == rid)
    rec = state.records[index]

    with st.form(f"edit_form_{rid}"):
        dest = st.text_input("Destination", value=rec.destination)
        c1, c2 = st.columns(2)
        category = c1.selectbox("Category", CATEGORIES, index=CATEGORIES.index(rec.category))
        status = c2.selectbox("Status", STATUSES, index=STATUSES.index(rec.status))
        d1, d2 = st.columns(2)
        start = d1.date_input("Start date", value=rec.start)
        end = d2.date_input("End date", value=rec.end)
        cost = st.text_input(f"Estimated cost ({state.currency})", value=f"{rec.est_cost:.2f}")
        notes = st.text_area("Notes", value=rec.notes)
        save = st.form_submit_button("Save changes", type="primary")
        confirm = st.checkbox("Yes, delete this entry")
        delete = st.form_submit_button("Delete entry")

    if save:
        updated, errors = make_record(rid, destination=dest, category=category, start_date=start,
                                      end_date=end, est_cost=cost, status=status, notes=notes)
        if errors:
            show_errors(errors)
            return
        state.records[index] = updated
        store.save(state)
        flash("success", f"Updated #{rid}.")
        st.rerun()
    if delete:
        if not confirm:
            st.warning("Tick 'Yes, delete this entry' first.")
            return
        del state.records[index]
        store.save(state)
        flash("success", f"Deleted #{rid}.")
        st.rerun()


def page_import_export(state: State, store: Store, today: date) -> None:
    st.title("📥 Import / Export")
    tab_import, tab_export, tab_data = st.tabs(["Import CSV", "Export reports", "Sample data & reset"])
    cur = state.currency

    with tab_import:
        st.caption("Required columns: destination, start_date, end_date, est_cost. Optional: category, status, notes. "
                   "Dates may be YYYY-MM-DD or DD/MM/YYYY. Bad rows are skipped and listed with the reason.")
        upload = st.file_uploader("Choose a CSV file", type=["csv"], key=f"upload_{st.session_state.get('upload_n', 0)}")
        if upload is not None:
            try:
                text = upload.getvalue().decode("utf-8-sig")
            except UnicodeDecodeError:
                st.error("This file is not UTF-8 text. Re-save it as CSV (UTF-8) and try again.")
                text = None
            if text is not None:
                result = importer.import_csv_text(text, state.records)
                if result.header_error:
                    st.error(result.header_error)
                else:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Rows read", result.total_rows)
                    m2.metric("Ready to import", len(result.records))
                    m3.metric("Duplicates skipped", result.duplicates)
                    m4.metric("Rejected", len(result.errors))
                    if result.errors:
                        st.subheader("Row-by-row error log")
                        st.dataframe(pd.DataFrame([{"Row": e.row, "Problem": e.message, "Original": e.raw} for e in result.errors]), hide_index=True)
                        st.download_button("Download error log (CSV)", importer.error_log_csv(result), "import_errors.csv", "text/csv")
                    if result.records:
                        with st.expander("Preview of valid rows", expanded=not result.errors):
                            st.dataframe(records_df(result.records, cur), hide_index=True)
                        if st.button(f"Import {len(result.records)} valid row(s)", type="primary"):
                            state.records.extend(result.records)
                            store.save(state)
                            flash("success", f"Imported {len(result.records)} row(s); {len(result.errors)} rejected, {result.duplicates} duplicate(s) skipped.")
                            st.session_state["upload_n"] = st.session_state.get("upload_n", 0) + 1
                            st.rerun()
                    else:
                        st.warning("No valid new rows to import from this file.")
        sample_cols = st.columns(2)
        if SAMPLE_CSV.exists():
            sample_cols[0].download_button("Download sample CSV (41 rows)", SAMPLE_CSV.read_bytes(), "sample_itinerary.csv", "text/csv")
        if BAD_CSV.exists():
            sample_cols[1].download_button("Download CSV with errors (for testing)", BAD_CSV.read_bytes(), "bad_import.csv", "text/csv")

    with tab_export:
        if not state.records:
            st.info("Add some entries first.")
        else:
            summary = logic.summarize(state.records, state.budget, today)
            warnings = logic.find_warnings(state.records, state.budget, today, cur)
            markdown = exporter.to_markdown(state.records, summary, warnings, cur, today)
            e1, e2, e3, e4 = st.columns(4)
            e1.download_button("Markdown report", markdown, "itinerary_report.md", "text/markdown")
            e2.download_button("Text audit log", exporter.to_audit_text(state.records, summary, warnings, cur, today), "itinerary_audit.txt", "text/plain")
            e3.download_button("CSV", exporter.to_csv_text(state.records), "itinerary.csv", "text/csv")
            e4.download_button("JSON", exporter.to_json_text(state), "itinerary.json", "application/json")
            with st.expander("Preview Markdown report"):
                st.markdown(markdown)

    with tab_data:
        st.subheader("Sample data")
        if SAMPLE_JSON.exists():
            replace_ok = st.checkbox("Replace my current data with the sample dataset", disabled=not state.records)
            if st.button("Load sample dataset (41 entries)"):
                if state.records and not replace_ok:
                    st.warning("Tick the box above to confirm replacing your current entries.")
                else:
                    sample = Store(SAMPLE_JSON).load()
                    state.records, state.budget, state.currency = sample.records, sample.budget, sample.currency
                    store.save(state)
                    flash("success", f"Loaded {len(sample.records)} sample entries.")
                    st.rerun()
        else:
            st.warning("sample_data/ was not found. Run `python seed_data.py` to create it.")
        st.subheader("Reset")
        confirm = st.checkbox("I understand this deletes every entry")
        if st.button("Delete all entries"):
            if not confirm:
                st.warning("Tick the confirmation box first.")
            else:
                state.records = []
                store.save(state)
                flash("success", "All entries deleted.")
                st.rerun()


# ---------- main ----------
def main() -> None:
    store = Store(DATA_FILE)
    state = store.load()
    today = date.today()

    st.sidebar.title("🧭 Wanderlist")
    page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
    with st.sidebar.expander("💰 Trip budget"):
        with st.form("budget_form"):
            budget = st.number_input("Total budget", min_value=0.0, max_value=1e9, value=float(state.budget), step=1000.0)
            currency = st.text_input("Currency", value=state.currency)
            if st.form_submit_button("Save budget"):
                clean, error = clean_currency(currency)
                if error:
                    st.error(error)
                else:
                    state.budget, state.currency = float(budget), clean
                    store.save(state)
                    flash("success", "Budget saved.")
                    st.rerun()
    st.sidebar.caption(f"{len(state.records)} entries · data saved to data/itinerary.json")

    for notice in store.notices:
        st.warning(notice)
    show_flash()

    if page == PAGES[0]:
        page_dashboard(state, today)
    elif page == PAGES[1]:
        page_add(state, store, today)
    elif page == PAGES[2]:
        page_browse(state, today)
    elif page == PAGES[3]:
        page_edit(state, store, today)
    else:
        page_import_export(state, store, today)


main()
