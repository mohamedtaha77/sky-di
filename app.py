"""Sky-DI: a small Document Intelligence Studio. Pick a model, give it a document, see what Azure reads."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import socket
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

from skydi import analyzer, reader, render, ui, viewer

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


@st.cache_data(show_spinner=False)
def page_urls(data: bytes) -> list[str]:
    return [render.page_data_url(i) for i in pages_of(data)]


def to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows).drop(columns=["polygon", "rowSpan", "colSpan"], errors="ignore").rename(columns={"page": "Page"})
    if "Confidence" in df:
        df["Confidence"] = df["Confidence"].astype(float) * 100
    return df


def csv_safe(df: pd.DataFrame) -> str:
    """CSV text for a download. Cells come from the document, so a leading = + - @ (or tab / CR) is escaped with a
    quote to stop Excel and Sheets from running it as a formula."""
    return df.map(lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
                  ).to_csv(index=False)


def table(rows: list[dict], key: str, name: str):
    """Show rows as a selectable table with a CSV download, and return the selected row index, if any."""
    if not rows:
        st.markdown('<div class="hint">Nothing found for this model.</div>', unsafe_allow_html=True)
        return
    df = to_df(rows)
    st.download_button("Download CSV", csv_safe(df), f"{name}.csv", "text/csv", key=f"csv_{key}")
    cfg = {"Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%.0f%%")}
    st.dataframe(df, key=key, hide_index=True, width="stretch", height=480, column_config=cfg,
                 on_select="rerun", selection_mode="single-row")


# Each row kind is shown in one tab; a click on the page maps a shape id "<tab>|<row>" back to that tab's row.
KIND_TAB = {"field": "Fields", "kv": "Key-value pairs", "line": "Lines", "table": "Tables", "mark": "Marks",
            "barcode": "Barcodes", "para": "Content"}
TAB_KIND = {t: k for k, t in KIND_TAB.items()}
PRIMARY = {"Invoices": "field", "Receipts": "field", "General documents": "kv", "Layout": "para",
           "OCR / Read": "para"}


def prepare(label: str, result: dict) -> dict:
    """Everything derived from one model's result, computed once when it arrives instead of on every rerun."""
    model = analyzer.BY_LABEL[label]
    rows = {k: fn(result) for k, fn in analyzer.ROWS.items()}
    tabs = list(model.tabs)
    for extra in ("Marks", "Barcodes"):  # only when the document has some
        if rows[TAB_KIND[extra]]:
            tabs.insert(tabs.index("JSON"), extra)
    primary = PRIMARY.get(label, "line")
    if primary == "para" and not rows["para"]:  # older results have no paragraphs; fall back to lines
        primary = "line"
    blocks = reader.build_blocks(result, KIND_TAB)
    return {"label": label, "model": model, "result": result, "rows": rows, "tabs": tabs, "stats": analyzer.stats(result),
            "shown": [primary] + [k for k in ("table", "mark", "barcode") if KIND_TAB[k] in tabs and k != primary],
            "page_info": {p["pageNumber"]: p for p in result.get("pages") or []}, "blocks": blocks,
            "text": "\n\n".join(b["text"] for b in blocks if b["t"] == "p"), "json": json.dumps(result, indent=2)}


@dataclass
class Sel:
    """One pane's selection. `seen` is the last selection read from each table, and `epoch` renames the tables'
    widgets to drop their own selection, which Streamlit can't clear from code."""
    row: tuple[str, int] | None = None   # (tab, row index)
    seen: dict = field(default_factory=dict)
    epoch: int = 0

    @property
    def id(self) -> str | None:  # the id the page and the reading view use
        return f"{self.row[0]}|{self.row[1]}" if self.row else None

    def clear(self):
        self.row, self.seen, self.epoch = None, {}, self.epoch + 1


def sel_of(side: str) -> Sel:
    return st.session_state.setdefault(f"sel_{side}", Sel())


def on_pick(side: str, key: str):
    """A shape on the page or a block in the reading view was clicked: select that row, or clear when it was already
    selected / the background was clicked."""
    pick = getattr(st.session_state.get(key), "pick", None)
    if pick is None:
        return
    sel, (tab, _, idx) = sel_of(side), pick.partition("|")
    if not pick or (tab, int(idx)) == sel.row:
        sel.clear()
    else:
        sel.row = (tab, int(idx))


def on_resend(key: str):
    """The browser lost a page image (a reload, say); send it again on this rerun."""
    st.session_state.get("sent_imgs", set()).discard(getattr(st.session_state.get(key), "resend", None))


def table_key(c: dict, tab: str) -> str:
    return f"tbl_{c['side']}_{c['sha'][:8]}_{sel_of(c['side']).epoch}_{tab}"


def sync_selection(c: dict) -> int | None:
    """Pick up a table click (a page click is already handled by on_pick). Returns the page to jump to, if any."""
    sel, sels = sel_of(c["side"]), {}
    for t in c["tabs"]:
        if t in TAB_KIND and t != "Content":  # the reading view has no table of its own
            rows = st.session_state.get(table_key(c, t), {}).get("selection", {}).get("rows", [])
            if rows:
                sels[t] = rows[0]
    prev, sel.seen = sel.seen, sels
    changed = [t for t, i in sels.items() if prev.get(t) != i]
    if changed:
        sel.row = (changed[-1], sels[changed[-1]])
        return c["rows"][TAB_KIND[sel.row[0]]][sel.row[1]].get("page")
    if sel.row and sel.row[0] in prev and sel.row[0] not in sels:  # the selected row was deselected in its table
        sel.clear()
    return None


def draw_view(c: dict, page: int, imgs: list, urls: list[str]):
    side = c["side"]
    sel = sel_of(side).row
    kinds = c["shown"] + ([TAB_KIND[sel[0]]] if sel and TAB_KIND[sel[0]] not in c["shown"] else [])
    items = viewer.build_items({k: c["rows"][k] for k in kinds}, KIND_TAB, page, c["page_info"].get(page, {}),
                               imgs[page - 1])
    # the browser keeps each page image it has been sent, so a click doesn't ship 150-300 KB again
    img_key, sent = f"{side}:{c['sha'][:12]}:{page}", st.session_state.setdefault("sent_imgs", set())
    src = None if img_key in sent else urls[page - 1]
    sent.add(img_key)
    viewer.page_view(f"pv_{side}", side, img_key, src, items, sel_of(side).id, f"{c['name']}, page {page}",
                     lambda: on_pick(side, f"pv_{side}"), lambda: on_resend(f"pv_{side}"))
    info, clear = st.columns([5, 1], vertical_alignment="center")
    if sel:
        kind, row = TAB_KIND[sel[0]], c["rows"][TAB_KIND[sel[0]]][sel[1]]
        info.markdown(ui.inspector(viewer.label_of(kind, row), row.get("page"), viewer.confidence_text(row)),
                      unsafe_allow_html=True)
        clear.button("Clear", key=f"clear_{side}", on_click=sel_of(side).clear)
    else:
        info.markdown(ui.inspector(), unsafe_allow_html=True)


def draw_panel(c: dict):
    side, stem = c["side"], Path(c["name"]).stem
    for tab, t in zip(st.tabs(c["tabs"]), c["tabs"]):
        with tab:
            if t == "Content":
                st.download_button("Download text", c["text"], f"{stem}.txt", "text/plain", key=f"txt_{side}")
                reader.reading_view(f"rd_{side}", side, c["blocks"], sel_of(side).id, lambda: on_pick(side, f"rd_{side}"))
            elif t == "JSON":
                st.download_button("Download JSON", c["json"], f"{stem}-{c['model'].model_id}.json",
                                   "application/json", key=f"dl_{side}")
                st.json(c["result"], expanded=1)
            else:
                table(c["rows"][TAB_KIND[t]], table_key(c, t), f"{stem}-{t.lower().replace(' ', '-')}")


# ---------------------------------------------------------------- controls
st.markdown(ui.hero(), unsafe_allow_html=True)
left, right = st.columns([1, 1])
with left:
    label = st.selectbox("Model", [m.label for m in analyzer.MODELS])
    model = analyzer.BY_LABEL[label]
    st.markdown(ui.model_card(model.label, model.model_id, model.blurb), unsafe_allow_html=True)
    compare = st.toggle("Compare with a second model")
    label_b = None
    if compare:
        label_b = st.selectbox("Second model", [m.label for m in analyzer.MODELS if m.label != label])
labels = [label] + ([label_b] if label_b else [])
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
        for lb in labels:
            if (sha, lb) not in cache:
                status.markdown(ui.progress(f"Analyzing {name} with {lb}…"), unsafe_allow_html=True)
                cache[(sha, lb)] = prepare(lb, analyzer.analyze(data, analyzer.BY_LABEL[lb]))
        st.session_state["doc"] = {"name": name, "data": data, "sha": sha, "labels": labels}
        for side in "AB":
            sel_of(side).clear()
        status.empty()
    except analyzer.AnalyzeError as e:
        status.error(str(e))

# ---------------------------------------------------------------- studio view
doc = st.session_state.get("doc")
if not doc:
    st.markdown('<div class="hint" style="text-align:center;margin-top:1.5rem">Choose a model and a document, '
                'then press Analyze.</div>', unsafe_allow_html=True)
    st.stop()

imgs, urls = pages_of(doc["data"]), page_urls(doc["data"])
sides = [st.session_state["results"][(doc["sha"], lb)] | {"side": s, "sha": doc["sha"], "name": doc["name"]}
         for s, lb in zip("AB", doc["labels"])]
title = " vs ".join(doc["labels"])
st.markdown(f'<div class="section">{html.escape(doc["name"])} · {html.escape(title)}</div>', unsafe_allow_html=True)
if len(sides) == 2:
    st.markdown(ui.compare_table(*((c["label"], c["stats"]) for c in sides)),
                unsafe_allow_html=True)
else:
    chips = {k: v for k, v in sides[0]["stats"].items() if v or k not in ("Marks", "Barcodes")}
    st.markdown(ui.stat_chips(chips), unsafe_allow_html=True)

page_key = f"page_{doc['sha']}"
for c in sides:  # a table click on any side jumps both viewers to that page
    pg = sync_selection(c)
    if pg and 1 <= pg <= len(imgs):
        st.session_state[page_key] = pg

page = 1
if len(imgs) > 1:
    if len(imgs) <= 8:
        page = st.segmented_control("Page", list(range(1, len(imgs) + 1)), default=1, key=page_key) or 1
    else:
        page = st.number_input("Page", 1, len(imgs), 1, key=page_key)

if len(sides) == 1:
    view, panel = st.columns([1.1, 1])
    with view:
        draw_view(sides[0], page, imgs, urls)
    with panel:
        draw_panel(sides[0])
else:
    for col, c in zip(st.columns(2), sides):
        with col:
            st.markdown(f'<div class="side-head">{ui.side_tag(c["side"], c["label"])}</div>', unsafe_allow_html=True)
            draw_view(c, page, imgs, urls)
            draw_panel(c)
