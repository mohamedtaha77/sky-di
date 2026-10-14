"""The reading view: the document's text in reading order, with headings, tables and checkboxes rendered as such."""

from __future__ import annotations

import streamlit as st

from skydi import analyzer, hover

HEAD_KINDS = {"columnHeader", "rowHeader", "stubHead"}


def _offset(item: dict) -> int:
    spans = item.get("spans") or [{}]
    return spans[0].get("offset", 0)


def build_blocks(result: dict, ids: dict[str, str]) -> list[dict]:
    """Paragraphs and tables in reading order. Each block carries the id of the row it came from, so a click or
    hover maps to the same shape on the page. `ids` maps a kind to its tab name. Without paragraphs (older API
    results) the lines stand in for them."""
    pages = {p.get("pageNumber"): p for p in result.get("pages") or []}
    tables = result.get("tables") or []
    spans = [(s.get("offset", 0), s.get("offset", 0) + s.get("length", 0)) for t in tables for s in t.get("spans") or []]
    entries: list[tuple[int, int, dict]] = []

    cell_id = 0
    for t in tables:
        cells = []
        for c in t.get("cells") or []:
            cells.append({"id": f'{ids["table"]}|{cell_id}', "r": c.get("rowIndex", 0), "c": c.get("columnIndex", 0),
                          "rs": c.get("rowSpan", 1), "cs": c.get("columnSpan", 1), "text": c.get("content", ""),
                          "head": c.get("kind") in HEAD_KINDS})
            cell_id += 1
        page = ((t.get("boundingRegions") or [{}])[0]).get("pageNumber")
        entries.append((page or 0, _offset(t), {"t": "table", "rows": t.get("rowCount", 0),
                                                "cols": t.get("columnCount", 0), "cells": cells}))

    if result.get("paragraphs"):
        for i, para in enumerate(result["paragraphs"]):
            off = _offset(para)
            if any(a <= off < b for a, b in spans):  # text inside a table is shown by the table
                continue
            page = ((para.get("boundingRegions") or [{}])[0]).get("pageNumber") or 0
            role = para.get("role")
            entries.append((page, off, {"t": "p", "id": f'{ids["para"]}|{i}', "role": role,
                                        "label": analyzer.ROLES.get(role, ""), "text": para.get("content", "")}))
    else:
        for i, row in enumerate(analyzer.line_rows(result)):
            entries.append((row["page"] or 0, i, {"t": "p", "id": f'{ids["line"]}|{i}', "role": None, "label": "",
                                                  "text": row["Line"]}))

    blocks, last = [], None
    for page, _, block in sorted(entries, key=lambda e: (e[0], e[1])):
        if page != last and len(pages) > 1:
            blocks.append({"t": "page", "n": page})
        last = page
        blocks.append(block)
    return blocks


CSS = """
.rd{max-height:640px;overflow:auto;background:#fff;border:1px solid rgba(37,99,235,.14);border-radius:16px;
  padding:1.2rem 1.4rem 1.6rem;box-shadow:0 10px 30px rgba(37,99,235,.08);color:#0F2547;
  font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:.92rem;line-height:1.6;position:relative}
.rd .b{position:relative;margin:0 0 .55rem;padding:.15rem .5rem;border-radius:8px;cursor:pointer;
  transition:background .15s ease,box-shadow .15s ease;outline:none;overflow-wrap:anywhere}
.rd .b:hover,.rd .b.hov{background:rgba(56,189,248,.16)}
.rd .b:focus-visible{box-shadow:0 0 0 2px #0F2547}
.rd .b.sel{background:rgba(37,99,235,.14);box-shadow:inset 0 0 0 2px #2563EB}
.rd .title{font-size:1.5rem;font-weight:800;line-height:1.2;letter-spacing:-.02em;margin-top:.4rem}
.rd .sectionHeading{font-size:1.1rem;font-weight:700;margin-top:1rem}
.rd .pageHeader,.rd .pageFooter,.rd .pageNumber,.rd .footnote{font-size:.78rem;color:#5B7396}
.rd .pageHeader,.rd .pageFooter{border-top:1px dashed rgba(37,99,235,.25);border-bottom:1px dashed rgba(37,99,235,.25)}
.rd .pageNumber{text-align:center}
.rd .formulaBlock{font-family:ui-monospace,Menlo,monospace;background:#F4F8FF}
.rd .tag{display:block;font-size:.66rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#5B7396;line-height:1.3}
.rd .pg{display:flex;align-items:center;gap:.6rem;margin:1.2rem 0 .8rem;font-size:.72rem;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase;color:#5B7396}
.rd .pg::before,.rd .pg::after{content:"";flex:1;height:1px;background:rgba(37,99,235,.18)}
.rd .tw{overflow-x:auto;margin:.3rem 0 .9rem}
.rd table{border-collapse:collapse;width:100%;font-size:.84rem;font-variant-numeric:tabular-nums}
.rd td,.rd th{border:1px solid rgba(37,99,235,.2);padding:.3rem .55rem;text-align:left;vertical-align:top;cursor:pointer;
  transition:background .15s ease;outline:none}
.rd th{background:#E8F1FF;font-weight:700}
.rd td:hover,.rd th:hover,.rd td.hov,.rd th.hov{background:rgba(56,189,248,.2)}
.rd td:focus-visible,.rd th:focus-visible{box-shadow:inset 0 0 0 2px #0F2547}
.rd td.sel,.rd th.sel{background:rgba(37,99,235,.18);box-shadow:inset 0 0 0 2px #2563EB}
.rd .chk{display:inline-block;width:.95em;height:.95em;border:1.5px solid #5B7396;border-radius:3px;vertical-align:-.12em;
  margin:0 .15em;position:relative;background:#fff}
.rd .chk.on{background:#2563EB;border-color:#2563EB}
.rd .chk.on::after{content:"";position:absolute;left:.26em;top:.06em;width:.26em;height:.5em;border:solid #fff;
  border-width:0 2px 2px 0;transform:rotate(45deg)}
.rd .empty{color:#5B7396}
@media (prefers-reduced-motion:reduce){.rd .b,.rd td,.rd th{transition:none}}
"""

JS = hover.JS + """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  let root = parentElement.querySelector('.rd');
  if (!root) { root = document.createElement('div'); root.className = 'rd'; parentElement.appendChild(root); }
  root.replaceChildren();
  const prevScroll = root.dataset.scroll ? +root.dataset.scroll : 0;
  const els = new Map();
  const reveal = (el) => {  // scroll a block into view when it is off-screen
    const r = root.getBoundingClientRect(), e = el.getBoundingClientRect();
    if (e.top < r.top || e.bottom > r.bottom) root.scrollTop += e.top - r.top - r.height / 3;
  };
  const link = hoverLink(data.side, 'reader', (id) => {
    els.forEach((el) => el.classList.remove('hov'));
    const el = id && els.get(id);
    if (el) { el.classList.add('hov'); reveal(el); }
  });

  const addText = (el, text) => {
    // ':selected:' / ':unselected:' are Azure's inline checkbox tokens; draw them as checkboxes
    text.split(/(:selected:|:unselected:)/).forEach((part) => {
      if (part === ':selected:' || part === ':unselected:') {
        const c = document.createElement('span');
        c.className = 'chk' + (part === ':selected:' ? ' on' : '');
        c.setAttribute('role', 'img');
        c.setAttribute('aria-label', part === ':selected:' ? 'selected' : 'not selected');
        el.appendChild(c);
      } else if (part) el.appendChild(document.createTextNode(part));
    });
  };
  const wire = (el, id, label) => {
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    if (label) el.setAttribute('aria-label', label);
    if (id === data.selected) el.classList.add('sel');
    el.addEventListener('pointerenter', () => link.say(id));
    el.addEventListener('pointerleave', () => link.say(null));
    el.addEventListener('click', (e) => { e.stopPropagation(); setTriggerValue('pick', id); });
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTriggerValue('pick', id); } });
    els.set(id, el);
  };

  if (!data.blocks.length) {
    const e = document.createElement('div'); e.className = 'empty'; e.textContent = 'No text was found in this document.';
    root.appendChild(e);
  }
  for (const b of data.blocks) {
    if (b.t === 'page') {
      const d = document.createElement('div'); d.className = 'pg'; d.textContent = 'Page ' + b.n; root.appendChild(d);
    } else if (b.t === 'p') {
      const d = document.createElement('div'); d.className = 'b ' + (b.role || 'body');
      if (b.label && b.role !== 'title' && b.role !== 'sectionHeading') {
        const t = document.createElement('span'); t.className = 'tag'; t.textContent = b.label; d.appendChild(t);
      }
      addText(d, b.text); wire(d, b.id, (b.label ? b.label + ': ' : '') + b.text); root.appendChild(d);
    } else if (b.t === 'table') {
      const w = document.createElement('div'); w.className = 'tw';
      const tb = document.createElement('table'); const rows = [];
      for (const c of b.cells) {
        (rows[c.r] = rows[c.r] || []).push(c);
      }
      for (const r of rows) {
        if (!r) continue;
        const tr = document.createElement('tr');
        r.sort((x, y) => x.c - y.c).forEach((c) => {
          const td = document.createElement(c.head ? 'th' : 'td');
          if (c.rs > 1) td.rowSpan = c.rs;
          if (c.cs > 1) td.colSpan = c.cs;
          addText(td, c.text); wire(td, c.id, c.text); tr.appendChild(td);
        });
        tb.appendChild(tr);
      }
      w.appendChild(tb); root.appendChild(w);
    }
  }

  root.scrollTop = prevScroll;
  root.addEventListener('scroll', () => { root.dataset.scroll = root.scrollTop; }, { passive: true });
  if (data.selected && els.has(data.selected)) reveal(els.get(data.selected));
  root.onclick = () => { if (data.selected) setTriggerValue('pick', ''); };
  return link.stop;
}
"""

_component = st.components.v2.component("skydi_reader", css=CSS, js=JS)


def reading_view(key: str, side: str, blocks: list[dict], selected: str | None, on_pick) -> None:
    _component(key=key, data={"side": side, "blocks": blocks, "selected": selected}, on_pick_change=on_pick)
