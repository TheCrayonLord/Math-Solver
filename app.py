"""Local web app.  Start with:  streamlit run app.py"""
from __future__ import annotations

import hashlib
import os
import tempfile

import pymupdf
import streamlit as st

from verifier.ingest import parse_page_ranges, read_document, read_pdf
from verifier.models import (
    VERDICT_CORRECT, VERDICT_ICONS, VERDICT_INCOMPLETE, VERDICT_NO_KEY, VERDICT_REVIEW,
    VERDICT_UNREADABLE, VERDICT_WRONG,
)
from verifier.pipeline import run, summarize_errors
from verifier.report import to_csv
from verifier.structure import find_key_pages

@st.cache_resource(show_spinner="Reading the document…")
def load(file_bytes: bytes, name: str):
    if name.lower().endswith(".docx"):
        tmp = tempfile.mkdtemp(prefix="mathverify_")
        path = os.path.join(tmp, name)
        with open(path, "wb") as f:
            f.write(file_bytes)
        doc = read_document(path, name)
        pdf_path = os.path.join(tmp, os.path.splitext(name)[0] + ".pdf")
        pdf_bytes = open(pdf_path, "rb").read() if os.path.exists(pdf_path) else None
        return doc, pdf_bytes
    return read_pdf(file_bytes, name), file_bytes


@st.cache_data(show_spinner=False)
def render_page(pdf_bytes: bytes, index: int, zoom: float = 1.3) -> bytes:
    pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return pdf[index].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")


def ranges_text(indices, doc, printed: bool) -> str:
    if not indices:
        return ""
    nums = [doc.pages[i].printed if printed else i + 1 for i in indices]
    nums = [n for n in nums if n is not None]
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if prev != start else str(start))
            start = prev = n
    out.append(f"{start}-{prev}" if prev != start else str(start))
    return ", ".join(out)


def main():
    st.set_page_config(page_title="Answer Key Checker", page_icon="✔️", layout="wide")
    st.title("✔️ Answer Key Checker")
    st.caption("Drop in a math book or worksheet. Every problem is solved exactly and compared with "
               "the answer key. Runs entirely on your computer.")

    up = st.file_uploader("PDF or Word file", type=["pdf", "docx"])
    if not up:
        st.info("Upload a digital PDF (with selectable text) or a .docx file to begin.")
        st.stop()

    data = up.getvalue()
    try:
        doc, pdf_bytes = load(data, up.name)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Couldn't read this file: {exc}")
        st.stop()

    n_pages = len(doc.pages)
    has_printed = doc.page_offset is not None
    if sum(len(p.lines) for p in doc.pages) == 0:
        st.error("This PDF has no selectable text (it looks scanned). Only digital PDFs are supported for now.")
        st.stop()

    file_id = hashlib.sha1(data).hexdigest()
    detected_key = find_key_pages(doc)

    with st.sidebar:
        st.header("What to check")
        info = f"**{n_pages} pages.**"
        if has_printed:
            first = next(p for p in doc.pages if p.printed is not None)
            info += f" Printed page numbers found (PDF page {first.index + 1} = page {first.printed})."
        st.markdown(info)

        numbering = "Printed page numbers"
        if has_printed:
            numbering = st.radio("Page numbers I'll type are…",
                                 ["Printed page numbers", "PDF page numbers"], horizontal=False)
        use_printed = has_printed and numbering == "Printed page numbers"

        scope = st.radio("Pages to check", ["All pages", "Choose pages"], horizontal=True)
        page_spec = ""
        if scope == "Choose pages":
            page_spec = st.text_input("Pages (e.g. 12-30, 45, 51-60)", key=f"pages_{file_id}")

        st.divider()
        st.subheader("Answer key")
        if detected_key:
            st.markdown(f"Found on page{'s' if len(detected_key) > 1 else ''} "
                            f"**{ranges_text(detected_key, doc, use_printed)}**"
                        f"{'' if use_printed else ' (PDF numbering)'}.")
        else:
            st.warning("No answer key section was found automatically.")
        manual_key = st.checkbox("Set answer key pages myself", value=not detected_key)
        key_spec = ""
        if manual_key:
            key_spec = st.text_input("Answer key pages", key=f"key_{file_id}")

        st.divider()
        go = st.button("Check answers", type="primary", use_container_width=True)

    # page preview
    with st.expander("Preview a page"):
        if pdf_bytes:
            pi = st.number_input("PDF page", 1, n_pages, 1) - 1
            st.caption(doc.pages[pi].label)
            st.image(render_page(pdf_bytes, pi), width=650)

    if go:
        try:
            if scope == "All pages":
                pages = list(range(n_pages))
            else:
                pages = parse_page_ranges(page_spec, doc, use_printed)
                if not pages:
                    raise ValueError("Type the pages to check, e.g. 12-30.")
            key_pages = parse_page_ranges(key_spec, doc, use_printed) if manual_key else detected_key
            if manual_key and not key_pages:
                raise ValueError("Type the answer key pages, or untick 'Set answer key pages myself'.")
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        bar = st.progress(0.0, text="Finding problems…")

        def prog(i, n):
            bar.progress(i / max(n, 1), text=f"Checking problem {i} of {n}")

        st.session_state["report"] = (file_id, run(doc, pages, key_pages, progress=prog))
        bar.empty()

    if "report" not in st.session_state or st.session_state["report"][0] != file_id:
        st.write("Choose the pages in the sidebar, then press **Check answers**.")
        st.stop()

    rep = st.session_state["report"][1]
    if not rep.results:
        st.warning("No numbered problems were found on the selected pages.")
        st.stop()

    # ------------------------------------------------------------------ summary
    cols = st.columns(5)
    for col, v in zip(cols, [VERDICT_WRONG, VERDICT_INCOMPLETE, VERDICT_CORRECT, VERDICT_REVIEW, VERDICT_NO_KEY]):
        col.metric(f"{VERDICT_ICONS[v]} {v}", rep.count(v))
    st.caption(f"{len(rep.results)} problems checked on {len(rep.problem_pages)} page(s); "
               f"{rep.key_entries} answers read from the key.")
    for note in rep.notes:
        st.warning(note)

    st.download_button("Download results (CSV)", to_csv(rep), file_name=f"{os.path.splitext(up.name)[0]}_check.csv",
                       mime="text/csv")


    def show_result(r, open_=False):
        p = r.problem
        title = f"{VERDICT_ICONS[r.verdict]} {p.page[0].upper() + p.page[1:]} — {p.label}"
        if r.error_type:
            title += f" · {r.error_type}"
        with st.expander(title, expanded=open_):
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown(f"**Problem:** `{p.text}`")
                if p.instruction:
                    st.caption(f"Directions: {p.instruction}")
                if r.key:
                    st.markdown(f"**Key says** · {r.key.page}: `{r.key.answer}`")
                if r.computed:
                    st.markdown(f"**Correct answer:** `{r.computed}`")
                if r.message:
                    box = st.error if r.verdict == VERDICT_WRONG else st.warning if r.verdict != VERDICT_CORRECT else st.success
                    box(r.message)
                for c in r.checks:
                    st.markdown(f"- {c}")
                if r.steps:
                    st.markdown("**Steps:**  \n" + "  \n".join(r.steps))
            with c2:
                if pdf_bytes and st.toggle("Show page", key=f"pg_{id(r)}"):
                    st.image(render_page(pdf_bytes, p.page_index, 1.0))
                    if r.key and r.key.page_index != p.page_index:
                        st.caption(f"Answer key — {r.key.page}")
                        st.image(render_page(pdf_bytes, r.key.page_index, 1.0))


    tab_err, tab_rev, tab_all = st.tabs([
        f"Errors in the key ({rep.count(VERDICT_WRONG) + rep.count(VERDICT_INCOMPLETE)})",
        f"Needs review ({rep.count(VERDICT_REVIEW) + rep.count(VERDICT_UNREADABLE)})",
        "All problems",
    ])
    with tab_err:
        errs = summarize_errors(rep)
        if not errs:
            st.success("No errors found in the answer key for the problems that could be checked.")
        for r in errs:
            show_result(r, open_=len(errs) <= 10)
    with tab_rev:
        revs = [r for r in rep.results if r.verdict in (VERDICT_REVIEW, VERDICT_UNREADABLE)]
        if not revs:
            st.success("Nothing needs manual review.")
        else:
            st.caption("These couldn't be verified automatically, so check them by hand.")
        for r in sorted(revs, key=lambda r: (r.problem.page_index, r.problem.number)):
            show_result(r)
    with tab_all:
        rows = [{
            "": VERDICT_ICONS[r.verdict], "Page": r.problem.page, "Problem": r.problem.label,
            "Text": r.problem.text, "Key": r.key.answer if r.key else "", "Computed": r.computed,
            "Result": r.verdict,
        } for r in sorted(rep.results, key=lambda r: (r.problem.page_index, r.problem.section or "",
                                                       r.problem.number, r.problem.part or ""))]
        st.dataframe(rows, use_container_width=True, hide_index=True)


# Worker processes (used to solve problems in parallel with a time limit) re-import this file
# under the name "__mp_main__"; they must not run the page.
if __name__ != "__mp_main__":
    main()
