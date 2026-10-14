"""JS shared by the page viewer and the reading view: hovering an item in one lights it up in the other."""

# `me` names the sender ('page' or 'reader'); `onOther(id)` runs when the other side reports the item under its pointer.
JS = """
const hoverLink = (side, me, onOther) => {
  const handler = (ev) => { const d = ev.detail; if (d.side === side && d.from !== me) onOther(d.id); };
  window.addEventListener('skydi:hover', handler);
  return {
    say: (id) => window.dispatchEvent(new CustomEvent('skydi:hover', { detail: { side, id, from: me } })),
    stop: () => window.removeEventListener('skydi:hover', handler),
  };
};
"""
