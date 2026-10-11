"""Sky-DI: a small Document Intelligence Studio. Pick a model, give it a document, see what Azure reads."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

from skydi import analyzer, render, ui

load_dotenv()
ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
SAMPLES = {"Invoice (PDF)": "invoice.pdf", "Receipt (PNG)": "receipt.png", "Layout form (PDF)": "layout.pdf"}
MAX_BYTES = 20 * 1024 * 1024

st.set_page_config(page_title="Sky-DI", page_icon=str(ASSETS / "favicon.png"), layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("<style>" + "".join((ASSETS / f).read_text(encoding="utf-8")
                                for f in ("style.css", "motion.css", "studio.css")) + "</style>",
            unsafe_allow_html=True)


def fetch_url(url: str) -> bytes:
    """Download a public http(s) document, refusing private addresses and anything over 20 MB."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise analyzer.AnalyzeError("Enter a full http(s) link.")
    try:
        ips = {ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(u.hostname, None)}
    except (socket.gaierror, ValueError) as e:
        raise analyzer.AnalyzeError("Could not resolve that address.") from e
    if any(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved for ip in ips):
        raise analyzer.AnalyzeError("That address is not a public website.")
    try:
        with requests.get(url, timeout=15, stream=True, allow_redirects=False) as r:
            r.raise_for_status()
            data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    except requests.RequestException as e:
        raise analyzer.AnalyzeError("Could not download that link.") from e
    if len(data) > MAX_BYTES:
        raise analyzer.AnalyzeError("That file is over 20 MB.")
    return data


@st.cache_data(show_spinner=False)
def pages_of(data: bytes):
    return render.page_images(data)


def to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows).drop(columns=["polygon"], errors="ignore").rename(columns={"page": "Page"})
    if "Confidence" in df:
        df["Confidence"] = df["Confidence"].astype(float) * 100
    return df


def table(rows: list[dict], key: str) -> int | None:
    """Show rows as a selectable table and return the selected row index, if any."""
    if not rows:
        st.markdown('<div class="hint">Nothing found for this model.</div>', unsafe_allow_html=True)
        return None
    cfg = {"Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%.0f%%")}
    ev = st.dataframe(to_df(rows), key=key, hide_index=True, width="stretch", height=480, column_config=cfg,
                      on_select="rerun", selection_mode="single-row")
    sel = ev.selection.rows
    return sel[0] if sel else None


# ---------------------------------------------------------------- controls
st.markdown(ui.hero(), unsafe_allow_html=True)
left, right = st.columns([1, 1])
with left:
    label = st.selectbox("Model", [m.label for m in analyzer.MODELS])
    model = analyzer.BY_LABEL[label]
    st.markdown(ui.model_card(model.label, model.model_id, model.blurb), unsafe_allow_html=True)
with right:
    source = st.segmented_control("Document", ["Sample", "Upload", "URL"], default="Sample") or "Sample"
    upload, url, sample = None, "", ""
    if source == "Sample":
        sample = st.selectbox("Sample document", list(SAMPLES), label_visibility="collapsed")
    elif source == "Upload":
        upload = st.file_uploader("Upload a document", type=["pdf", "jpg", "jpeg", "png", "tiff", "tif", "bmp"],
                                  label_visibility="collapsed")
    else:
        url = st.text_input("Document link", placeholder="https://…/invoice.pdf", label_visibility="collapsed")
    go = st.button("Analyze", type="primary", width="stretch")

status = st.empty()
if go:
    try:
        if source == "Sample":
            name, data = SAMPLES[sample], (ROOT / "samples" / SAMPLES[sample]).read_bytes()
        elif source == "Upload":
            if upload is None:
                raise analyzer.AnalyzeError("Choose a file first.")
            name, data = upload.name, upload.getvalue()
            if len(data) > MAX_BYTES:
                raise analyzer.AnalyzeError("That file is over 20 MB.")
        else:
            name, data = url.rsplit("/", 1)[-1] or "document", fetch_url(url.strip())
        sha = hashlib.sha1(data).hexdigest()
        cache = st.session_state.setdefault("results", {})
        if (sha, label) not in cache:
            status.markdown(ui.progress(f"Analyzing {name} with {label}…"), unsafe_allow_html=True)
            cache[(sha, label)] = analyzer.analyze(data, model)
        st.session_state["doc"] = {"name": name, "data": data, "sha": sha, "label": label}
        st.session_state.pop("prev_sel", None)
        status.empty()
    except analyzer.AnalyzeError as e:
        status.error(str(e))

# ---------------------------------------------------------------- studio view
doc = st.session_state.get("doc")
if not doc:
    st.markdown('<div class="hint" style="text-align:center;margin-top:1.5rem">Choose a model and a document, '
                'then press Analyze.</div>', unsafe_allow_html=True)
    st.stop()

dmodel = analyzer.BY_LABEL[doc["label"]]
result = st.session_state["results"][(doc["sha"], doc["label"])]
imgs = pages_of(doc["data"])
page_info = {p["pageNumber"]: p for p in result.get("pages") or []}

if dmodel.label in ("Invoices", "Receipts"):
    primary, prows = "field", analyzer.field_rows(result)
elif dmodel.label == "General documents":
    primary, prows = "kv", analyzer.kv_rows(result)
else:
    primary, prows = "line", analyzer.line_rows(result)
trows = analyzer.table_rows(result)
tab_rows = {"Fields": ("field", prows), "Key-value pairs": ("kv", prows), "Content": ("line", analyzer.line_rows(result)),
            "Tables": ("table", trows)}

st.markdown(f'<div class="section">{html.escape(doc["name"])} · {dmodel.label}</div>',
            unsafe_allow_html=True)
st.markdown(ui.stat_chips(analyzer.stats(result)), unsafe_allow_html=True)

# the table click from the previous run decides what is highlighted now
sels = {t: st.session_state.get(f"tbl_{t}", {}).get("selection", {}).get("rows", []) for t in tab_rows}
sels = {t: r[0] for t, r in sels.items() if r and t in dmodel.tabs}
prev = st.session_state.get("prev_sel", {})
changed = [t for t, i in sels.items() if prev.get(t) != i]
st.session_state["prev_sel"] = sels
active = changed[-1] if changed else st.session_state.get("active_tab")
st.session_state["active_tab"] = active if active in sels else None
active = st.session_state["active_tab"]

page_key = f"page_{doc['sha']}"
if changed and active:  # jump to the page of the clicked item
    pg = tab_rows[active][1][sels[active]].get("page")
    if pg and 1 <= pg <= len(imgs):
        st.session_state[page_key] = pg

view, panel = st.columns([1.1, 1])
with view:
    if len(imgs) > 1:
        if len(imgs) <= 8:
            page = st.segmented_control("Page", list(range(1, len(imgs) + 1)), default=1, key=page_key) or 1
        else:
            page = st.number_input("Page", 1, len(imgs), 1, key=page_key)
    else:
        page = 1
    img = imgs[page - 1]
    scale = render.scale_for(img, page_info.get(page, {}))
    if active:
        kind, rows = tab_rows[active]
        img = render.draw_overlay(img, rows, page, scale, kind, sels[active])
    else:
        img = render.draw_overlay(img, prows, page, scale, primary)
        if "Tables" in dmodel.tabs and primary != "table":
            img = render.draw_overlay(img, trows, page, scale, "table")
    st.image(img, width="stretch")

with panel:
    for tab, t in zip(st.tabs(list(dmodel.tabs)), dmodel.tabs):
        with tab:
            if t == "JSON":
                st.download_button("Download JSON", json.dumps(result, indent=2), f"{Path(doc['name']).stem}.json",
                                   "application/json")
                st.json(result, expanded=1)
            else:
                table(tab_rows[t][1], f"tbl_{t}")
