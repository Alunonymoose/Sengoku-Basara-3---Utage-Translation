"""Shared text normalisation for the polish pass."""
import re
TAG = re.compile(r"\{(?!\{)[^{}]*\}")
def speeches(t):
    """markup -> list of visible speeches, each a list of visual lines (controls stripped)."""
    out = []
    for sp in t.replace("{end}", "").split("{p}"):
        lines = [TAG.sub("", x).replace("{{", "{").replace("}}", "}") for x in sp.split("{br}")]
        if any(l.strip() for l in lines):
            out.append(lines)
    return out
def plain(t):
    return " / ".join(" ".join(l.strip() for l in sp) for sp in speeches(t))
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")
