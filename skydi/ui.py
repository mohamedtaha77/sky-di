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
