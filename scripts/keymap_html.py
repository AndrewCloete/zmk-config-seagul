#!/usr/bin/env python3
"""Render the ZMK keymap as a single HTML page, one grid per layer.

Usage: scripts/keymap_html.py [keymap] [output.html]

Each line inside a layer's `bindings = < ... >` becomes one row of keys, so
lay out the keymap file the way the keys sit on the board.
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYMAP = ROOT / "config/boards/shields/seagull/seagull.keymap"
OUT = ROOT / "keymap.html"

MODS = {"LG": "⌘", "RG": "⌘", "LS": "⇧", "RS": "⇧", "LC": "⌃", "RC": "⌃", "LA": "⌥", "RA": "⌥"}
KEYS = {
    "BSPC": "⌫", "DEL": "⌦", "SPACE": "Space", "RET": "↵", "ENTER": "↵", "ESC": "Esc", "TAB": "⇥",
    "LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓",
    "EQUAL": "=", "MINUS": "-", "COMMA": ",", "DOT": ".", "SLASH": "/", "SEMI": ";",
    "PSCRN": "PrtSc", "C_PLAY_PAUSE": "⏯", "C_VOL_UP": "Vol+", "C_VOL_DN": "Vol−",
}
# What each key code does in DaVinci Resolve (macOS defaults), keyed by ZMK code.
RESOLVE = {
    "A": "Select", "B": "Blade", "T": "Trim", "N": "Snap", "E": "Edge",
    "LG(B)": "Split", "LS(BSPC)": "Ripple", "LG(Z)": "Undo", "LG(LS(Z))": "Redo",
    "SPACE": "Play", "LS(Z)": "Fit",
    "RIGHT": "+1 frame", "LEFT": "−1 frame", "LS(RIGHT)": "+1 sec", "LS(LEFT)": "−1 sec",
    "LG(EQUAL)": "Zoom in", "LG(MINUS)": "Zoom out",
    "DOT": "Nudge +1", "COMMA": "Nudge −1", "LS(DOT)": "Nudge +n", "LS(COMMA)": "Nudge −n",
    "DOWN": "Next edit", "UP": "Prev edit",
}
# Layer-tap style behaviours: first argument is the layer held, second the key tapped.
LAYER_TAPS = {"lt", "lt_now"}


def key(code):
    m = re.fullmatch(r"(\w+)\((.*)\)", code)
    if m:
        return MODS.get(m[1], m[1] + "+") + key(m[2])
    return KEYS.get(code, code)


def dual(code):
    """HTML showing the key, or its Resolve action when the toggle is on."""
    k, r = html.escape(key(code)), html.escape(RESOLVE.get(code, key(code)))
    return k if k == r else f'<i class="k">{k}</i><i class="r">{r}</i>'


def parse(text):
    text = re.sub(r"//.*", "", text)
    defines = {name: int(n) for name, n in re.findall(r"#define\s+(\w+)\s+(\d+)", text)}
    layers = []
    for m in re.finditer(
        r'display-name\s*=\s*"([^"]*)";\s*bindings\s*=\s*<(.*?)>;(?:\s*sensor-bindings\s*=\s*<(.*?)>;)?',
        text, re.S,
    ):
        rows = [["&" + b.strip() for b in line.split("&") if b.strip()]
                for line in m[2].strip().splitlines() if line.strip()]
        layers.append({"name": m[1], "rows": rows, "sensor": (m[3] or "").strip()})
    conditions = {}
    for ifs, then in re.findall(r"if-layers\s*=\s*<([^>]*)>;\s*then-layer\s*=\s*<([^>]*)>;", text):
        conditions[layer_index(then.strip(), defines)] = [layer_index(i, defines) for i in ifs.split()]
    return defines, layers, conditions


def layer_index(arg, defines):
    return defines[arg] if arg in defines else int(arg)


def label(binding, defines, layers):
    """Return (main label as HTML, small hint, css class) for one binding."""
    behavior, *args = binding[1:].split()
    name = lambda arg: html.escape(layers[layer_index(arg, defines)]["name"])
    if behavior == "kp":
        return dual(args[0]), "", ""
    if behavior == "mo":
        return name(args[0]), "hold", "layer"
    if behavior == "tog":
        return name(args[0]), "toggle", "layer"
    if behavior in LAYER_TAPS:
        return dual(args[1]), "hold: " + name(args[0]), "layer"
    if behavior == "trans":
        return "", "", "trans"
    if behavior == "none":
        return "", "", "none"
    if behavior == "bt":
        return ("BT " + args[1]) if args[0] == "BT_SEL" else args[0].replace("BT_", "BT "), "", ""
    if behavior == "bootloader":
        return "Boot", "", ""
    return html.escape(" ".join([behavior, *args])), "", ""


def activators(layers, defines, conditions):
    """Map layer index -> flat key positions on the base layer that activate it."""
    found = {}
    for pos, binding in enumerate(b for row in layers[0]["rows"] for b in row):
        behavior, *args = binding[1:].split()
        if behavior in {"mo", "tog"} | LAYER_TAPS:
            found.setdefault(layer_index(args[0], defines), []).append(pos)
    for then, ifs in conditions.items():
        found[then] = [p for i in ifs for p in found.get(i, [])]
    return found


def render(defines, layers, conditions):
    held = activators(layers, defines, conditions)
    base = [label(b, defines, layers)[0] for row in layers[0]["rows"] for b in row]
    cards = []
    for i, layer in enumerate(layers):
        note = ""
        if i in conditions:
            note = "active while " + " + ".join(layers[j]["name"] for j in conditions[i]) + " are held"
        rows, pos = [], 0
        for row in layer["rows"]:
            cells = []
            for binding in row:
                main, hint, cls = label(binding, defines, layers)
                if i and pos in held.get(i, []):
                    cls, hint = cls + " held", hint or "held"
                    main = main or base[pos]
                cells.append(
                    f'<div class="key {cls}" title="{html.escape(binding)}">'
                    f"<span>{main}</span><small>{hint}</small></div>"
                )
                pos += 1
            rows.append('<div class="row">' + "".join(cells) + "</div>")
        encoder = ""
        if layer["sensor"]:
            _, cw, ccw = layer["sensor"].lstrip("&").split()
            encoder = f'<p class="enc">Encoder: ↻ {dual(cw)} &nbsp; ↺ {dual(ccw)}</p>'
        cards.append(
            f'<section><h2>{i} · {html.escape(layer["name"])}</h2>'
            f'<p class="note">{html.escape(note)}</p>{"".join(rows)}{encoder}</section>'
        )
    return PAGE.replace("{cards}", "\n".join(cards))


PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seagull Keymap</title>
<style>
  :root { --bg: #fafafa; --fg: #222; --key: #fff; --line: #ccc; --muted: #888; --accent: #2a6fdb; --hold: #fde68a; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #1b1b1d; --fg: #eee; --key: #2a2a2e; --line: #444; --muted: #888; --accent: #7aa7ff; --hold: #6b5a1e; }
  }
  body { background: var(--bg); color: var(--fg); font: 14px system-ui, sans-serif; margin: 0; padding: 16px; }
  main { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr)); gap: 24px; }
  h2 { font-size: 15px; margin: 0 0 2px; }
  .note, .enc { color: var(--muted); margin: 0 0 8px; min-height: 1em; }
  .enc { margin-top: 8px; color: var(--fg); }
  .row { display: flex; gap: 4px; margin-bottom: 4px; }
  .key { width: 68px; height: 52px; border: 1px solid var(--line); border-radius: 6px; background: var(--key);
         display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
  .key span { font-weight: 600; }
  .key small { font-size: 10px; color: var(--muted); }
  .layer span { color: var(--accent); }
  .trans, .none { background: transparent; border-style: dashed; }
  .toggle { display: block; margin-bottom: 16px; }
  i { font-style: normal; }
  .r { display: none; }
  body:has(#resolve:checked) .k { display: none; }
  body:has(#resolve:checked) .r { display: inline; }
  .held { background: var(--hold); border-style: solid; }
  @media print {
    @page { size: A4 portrait; margin: 10mm; }
    :root { --bg: #fff; --fg: #000; --key: #fff; --line: #999; --muted: #555; --accent: #1d4ed8; --hold: #fde68a; }
    * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
    body { padding: 0; font-size: 9pt; }
    .toggle { display: none; }
    main { grid-template-columns: 1fr 1fr; gap: 6mm; }
    section { break-inside: avoid; }
    h2 { font-size: 10pt; }
    .row { gap: 1mm; margin-bottom: 1mm; }
    .key { width: 13mm; height: 10mm; border-radius: 1.5mm; }
    .key small { font-size: 6pt; }
  }
</style>
<label class="toggle"><input type="checkbox" id="resolve"> Show what the keys do in Resolve</label>
<main>
{cards}
</main>
"""

if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else KEYMAP
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    out.write_text(render(*parse(src.read_text())))
    print(out)
