"""Small HTML builders for the Sky-DI look. All dynamic text is escaped."""

from __future__ import annotations

from html import escape


def hero() -> str:
    return (
        '<div class="hero">'
        '<div class="brand"><span class="logo">&#9729;</span>Sky-DI</div>'
        '<h1>Document Intelligence <span class="grad">Studio.</span></h1>'
        '<p>Pick a model, drop in a document, and see exactly what Azure reads from it.</p>'
        '</div>'
    )


def model_card(label: str, model_id: str, blurb: str) -> str:
    return (f'<div class="card mcard"><div class="cvname">{escape(label)}</div>'
            f'<div class="cvmeta">{escape(blurb)}</div>'
            f'<span class="pill sync">{escape(model_id)}</span></div>')


def stat_chips(stats: dict) -> str:
    return '<div class="stats">' + "".join(
        f'<div class="stat"><b>{escape(str(v))}</b><span>{escape(k)}</span></div>' for k, v in stats.items()) + '</div>'


def progress(text: str) -> str:
    return f'<div class="card"><div class="cvname">{escape(text)}</div><div class="bar"></div></div>'


def side_tag(side: str, label: str) -> str:
    return f'<div class="sidetag s{side.lower()}"><i>{escape(side)}</i>{escape(label)}</div>'


def inspector(label: str | None = None, page: int | None = None, confidence: str = "") -> str:
    if not label:
        return '<div class="insp"><div class="cvmeta">Hover a box to read it. Click to select it.</div></div>'
    meta = " · ".join(x for x in (f"Page {page}" if page else "", confidence) if x)
    return (f'<div class="insp"><div class="cvname">{escape(label)}</div>'
            f'<div class="cvmeta">{escape(meta)}</div></div>')


def compare_table(a: tuple[str, dict], b: tuple[str, dict]) -> str:
    """Stats of two results side by side; a row whose numbers differ is marked."""
    head = (f'<tr><th></th><th>{side_tag("A", a[0])}</th><th>{side_tag("B", b[0])}</th></tr>')
    body = "".join(
        f'<tr class="{"diff" if a[1][k] != b[1][k] else ""}"><th>{escape(k)}</th><td>{a[1][k]}</td><td>{b[1][k]}</td></tr>'
        for k in a[1])
    return f'<table class="grid cmp">{head}{body}</table>'
