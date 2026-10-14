"""The page viewer: the page image with every detected item as a hoverable, clickable shape on top."""

from __future__ import annotations

import streamlit as st

from skydi import hover, render

# Draw order: big containers first so smaller items sit on top and win the hover.
KIND_ORDER = ("table", "para", "line", "field", "kv", "mark", "barcode")

CSS = """
.pv{border-radius:16px;overflow:hidden;border:1px solid rgba(37,99,235,.14);position:relative;
  box-shadow:0 10px 30px rgba(37,99,235,.12);background:#fff;font-family:'Plus Jakarta Sans',system-ui,sans-serif}
.pv-bar{display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;padding:.5rem .6rem;border-bottom:1px solid rgba(37,99,235,.12);
  background:#F7FAFF;font-size:12px;line-height:1.2;color:#0F2547}
.pv-bar button{font:inherit;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:.4rem;color:inherit;
  background:#fff;border:1px solid rgba(37,99,235,.18);border-radius:999px;padding:.3rem .65rem;transition:background .15s,opacity .15s}
.pv-bar button:hover{background:#E8F1FF}
.pv-bar button:focus-visible{outline:2px solid #0F2547;outline-offset:1px}
.pv-bar .lyr i{width:.6rem;height:.6rem;border-radius:50%;background:rgb(var(--c));flex:none}
.pv-bar .lyr b{font-weight:600;color:#5B7396;font-variant-numeric:tabular-nums}
.pv-bar .lyr[aria-pressed=false]{opacity:.5;background:transparent}
.pv-bar .lyr[aria-pressed=false] i{background:transparent;box-shadow:inset 0 0 0 1.5px rgb(var(--c))}
.pv-bar .sp{flex:1}
.pv-bar .zv{min-width:3.2em;text-align:center;font-weight:600;color:#5B7396;font-variant-numeric:tabular-nums}
.pv-bar .z{padding:.3rem .6rem;min-width:2rem;justify-content:center}
.pv-scroll{overflow:auto;line-height:0}
.pv.zoomed .pv-scroll{max-height:78vh}
.pv-stage{position:relative;transform-origin:0 0}
.pv img{display:block;width:100%;height:auto;user-select:none;-webkit-user-drag:none}
.pv svg{position:absolute;inset:0;width:100%;height:100%}
.pv polygon{vector-effect:non-scaling-stroke;stroke-width:1.5;cursor:pointer;outline:none;
  transition:fill .15s ease,stroke .15s ease,stroke-opacity .15s ease,fill-opacity .15s ease}
.k-para{--c:14,165,233}.k-line{--c:56,189,248}.k-field{--c:5,150,105}.k-kv{--c:99,102,241}
.k-table{--c:245,158,11}.k-mark{--c:13,148,136}.k-barcode{--c:219,39,119}
.pv polygon{fill:rgba(var(--c),.16);stroke:rgba(var(--c),.85)}
.pv polygon:hover,.pv polygon.hov{fill:rgba(var(--c),.34);stroke:rgb(var(--c));stroke-width:2.5}
.pv polygon:focus-visible{stroke:#0F2547;stroke-width:3;stroke-dasharray:6 3;fill:rgba(var(--c),.34)}
.pv polygon.dim{fill-opacity:0;stroke-opacity:.28;stroke-width:1}
.pv polygon.dim:hover,.pv polygon.dim.hov{fill-opacity:1;stroke-opacity:1;stroke-width:2}
.pv polygon.sel{fill:rgba(37,99,235,.26);stroke:#2563EB;stroke-width:3.5}
.pv polygon.off:not(.sel){display:none}
.pv-tip{position:absolute;left:0;top:0;max-width:min(320px,80%);pointer-events:none;opacity:0;transform:translateY(4px);
  transition:opacity .12s ease,transform .12s ease;z-index:3;background:#0F2547;color:#fff;border-radius:10px;
  padding:.4rem .6rem;font-size:12.5px;line-height:1.35;box-shadow:0 8px 20px rgba(15,37,71,.28)}
.pv-tip.on{opacity:1;transform:none}
.pv-tip b{display:block;font-weight:700;word-break:break-word}
.pv-tip span{color:#A9C4EC;font-size:11.5px}
@media (prefers-reduced-motion:reduce){.pv polygon,.pv-tip,.pv-bar button{transition:none}}
"""

JS = hover.JS + """
const NAMES = { para: 'Paragraphs', line: 'Lines', field: 'Fields', kv: 'Pairs', table: 'Tables', mark: 'Marks', barcode: 'Barcodes' };
const STEPS = [0.5, 0.75, 1, 1.5, 2, 3];

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  // the page image is sent once per session and kept here; ask for it again if this tab has lost it
  const store = (window.__skydiImgs = window.__skydiImgs || new Map());
  if (data.src) {
    store.set(data.imgKey, data.src);
    if (store.size > 12) store.delete(store.keys().next().value);
  }
  const src = store.get(data.imgKey);
  if (!src) { setTriggerValue('resend', data.imgKey); return; }

  let root = parentElement.querySelector('.pv');
  if (!root) {
    root = document.createElement('div');
    root.className = 'pv';
    root.innerHTML = '<div class="pv-bar"></div><div class="pv-scroll"><div class="pv-stage"><img alt="">' +
                     '<svg viewBox="0 0 1 1" preserveAspectRatio="none"></svg></div></div><div class="pv-tip" role="status"></div>';
    parentElement.appendChild(root);
  }
  const bar = root.querySelector('.pv-bar'), stage = root.querySelector('.pv-stage'), img = root.querySelector('img');
  const svg = root.querySelector('svg'), tip = root.querySelector('.pv-tip');
  if (img.dataset.src !== data.imgKey) { img.src = src; img.dataset.src = data.imgKey; }
  img.alt = data.alt;
  svg.replaceChildren();
  tip.classList.remove('on');

  // view state lives on the element, so it survives the reruns a click causes
  const hidden = new Set((root.dataset.hidden || '').split(',').filter(Boolean));
  let zoom = +root.dataset.zoom || 1;
  const applyZoom = () => {
    stage.style.width = zoom * 100 + '%';
    root.classList.toggle('zoomed', zoom > 1);
    root.dataset.zoom = zoom;
    const zv = bar.querySelector('.zv'); if (zv) zv.textContent = Math.round(zoom * 100) + '%';
  };
  const applyLayers = () => {
    svg.querySelectorAll('polygon').forEach((p) => p.classList.toggle('off', hidden.has(p.dataset.kind)));
    bar.querySelectorAll('.lyr').forEach((b) => b.setAttribute('aria-pressed', String(!hidden.has(b.dataset.kind))));
    root.dataset.hidden = [...hidden].join(',');
  };

  // toolbar: one toggle per kind on this page, then the zoom controls
  bar.replaceChildren();
  const counts = {};
  data.items.forEach((it) => { counts[it.kind] = (counts[it.kind] || 0) + 1; });
  Object.keys(NAMES).filter((k) => counts[k]).forEach((k) => {
    const b = document.createElement('button');
    b.className = 'lyr k-' + k; b.dataset.kind = k; b.type = 'button';
    b.innerHTML = '<i></i>' + NAMES[k] + ' <b>' + counts[k] + '</b>';
    b.onclick = (e) => { e.stopPropagation(); hidden.has(k) ? hidden.delete(k) : hidden.add(k); applyLayers(); };
    bar.appendChild(b);
  });
  const sp = document.createElement('span'); sp.className = 'sp'; bar.appendChild(sp);
  const zbtn = (txt, label, fn) => {
    const b = document.createElement('button');
    b.className = 'z'; b.type = 'button'; b.textContent = txt; b.setAttribute('aria-label', label);
    b.onclick = (e) => { e.stopPropagation(); fn(); applyZoom(); }; bar.appendChild(b); return b;
  };
  const step = (d) => () => {
    const i = STEPS.indexOf(zoom), j = Math.min(STEPS.length - 1, Math.max(0, (i < 0 ? 2 : i) + d)); zoom = STEPS[j];
  };
  zbtn('\u2212', 'Zoom out', step(-1));
  const zv = document.createElement('span'); zv.className = 'zv'; bar.appendChild(zv);
  zbtn('+', 'Zoom in', step(1));
  zbtn('Fit', 'Fit page to width', () => { zoom = 1; });
  applyZoom();

  // the reading view reports the item under the pointer; show it on the page too
  const link = hoverLink(data.side, 'page', (id) => {
    svg.querySelectorAll('polygon.hov').forEach((n) => n.classList.remove('hov'));
    if (id) svg.querySelectorAll('polygon').forEach((n) => { if (n.dataset.id === id) n.classList.add('hov'); });
  });

  const NS = 'http://www.w3.org/2000/svg';
  const hasSel = !!data.selected;
  const items = data.items.slice().sort((a, b) => (a.id === data.selected) - (b.id === data.selected));

  const showTip = (it, e) => {
    tip.replaceChildren();
    const b = document.createElement('b'); b.textContent = it.label; tip.appendChild(b);
    if (it.sub) { const s = document.createElement('span'); s.textContent = it.sub; tip.appendChild(s); }
    tip.classList.add('on');
    const r = root.getBoundingClientRect();
    let x = e.clientX - r.left + 14, y = e.clientY - r.top + 16;
    if (x + tip.offsetWidth > r.width - 6) x = Math.max(6, e.clientX - r.left - tip.offsetWidth - 14);
    if (y + tip.offsetHeight > r.height - 6) y = Math.max(6, e.clientY - r.top - tip.offsetHeight - 14);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  };

  for (const it of items) {
    const p = document.createElementNS(NS, 'polygon');
    p.setAttribute('points', it.pts);
    p.setAttribute('class', 'k-' + it.kind + (it.id === data.selected ? ' sel' : hasSel ? ' dim' : ''));
    p.setAttribute('tabindex', '0');
    p.setAttribute('role', 'button');
    p.setAttribute('aria-label', it.label + (it.sub ? ', ' + it.sub : ''));
    p.dataset.id = it.id; p.dataset.kind = it.kind;
    p.addEventListener('pointerenter', (e) => { showTip(it, e); link.say(it.id); });
    p.addEventListener('pointermove', (e) => showTip(it, e));
    p.addEventListener('pointerleave', () => { tip.classList.remove('on'); link.say(null); });
    p.addEventListener('click', (e) => { e.stopPropagation(); setTriggerValue('pick', it.id); });
    p.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTriggerValue('pick', it.id); }
    });
    svg.appendChild(p);
  }
  applyLayers();
  stage.onclick = () => { if (hasSel) setTriggerValue('pick', ''); };

  return link.stop;
}
"""

_component = st.components.v2.component("skydi_page_view", css=CSS, js=JS)


def label_of(kind: str, row: dict) -> str:
    """Short text for the hover tooltip and the selected-item strip."""
    if kind == "line":
        return row.get("Line", "")
    if kind == "para":
        return f'{row.get("Role", "Paragraph")}: {row.get("Text", "")}'
    if kind == "field":
        return f'{row.get("Field", "")}: {row.get("Value", "")}'
    if kind == "kv":
        return f'{row.get("Key", "")}: {row.get("Value", "")}'
    if kind == "table":
        cell = f'Table {row.get("table", 1)}, row {row.get("row", 0) + 1}, column {row.get("col", 0) + 1}'
        return f'{cell}: {row["text"]}' if row.get("text") else cell
    if kind == "mark":
        return f'{row.get("State", "")} checkbox'
    if kind == "barcode":
        return f'{row.get("Type", "Barcode")}: {row.get("Value", "")}'
    return ""


def confidence_text(row: dict) -> str:
    c = row.get("Confidence")
    return f"{float(c) * 100:.0f}% confidence" if c is not None else ""


def build_items(rows_by_kind: dict[str, list[dict]], ids: dict[str, str], page: int, page_info: dict, img) -> list[dict]:
    """Shapes for one page. `ids` maps a kind to its tab name, so a click maps back to a table row."""
    items = []
    for kind in KIND_ORDER:
        for i, r in enumerate(rows_by_kind.get(kind, [])):
            poly = r.get("polygon") or []
            if r.get("page") != page or len(poly) < 6:
                continue
            pts = render.norm_polygon(poly, page_info, img)
            items.append({"id": f"{ids[kind]}|{i}", "kind": kind, "label": label_of(kind, r) or kind,
                          "sub": confidence_text(r),
                          "pts": " ".join(f"{pts[j]},{pts[j + 1]}" for j in range(0, len(pts) - 1, 2))})
    return items


def page_view(key: str, side: str, img_key: str, src: str | None, items: list[dict], selected: str | None,
              alt: str, on_pick, on_resend) -> None:
    """`src` is None once the browser already holds this page image (see `img_key`)."""
    _component(key=key, data={"side": side, "imgKey": img_key, "src": src, "items": items, "selected": selected,
                              "alt": alt}, on_pick_change=on_pick, on_resend_change=on_resend)
