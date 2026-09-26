"""Shared corpus loader for agent1 analyses (reads MANIFEST.json of pack_text_corpus; no game text stored here)."""
import json, os, re, collections
from pathlib import Path
CORPUS = Path(os.environ.get("CORPUS", "."))
SKIP = re.compile(r"BACKUP|backup|Copy|PRE_", re.I)
M = json.load(open(CORPUS / "MANIFEST.json"))
FILES = collections.defaultdict(dict)   # tree -> (arc, name, kind) -> entry
for f in M["files"]:
    FILES[f["tree"]][(f["arc"], f["name"], f["kind"])] = f
def read(f): return (CORPUS / f["path"]).read_bytes()
def live_tables(tree="utage_eng"):
    for (arc, name, kind), f in sorted(FILES[tree].items()):
        if kind != "gsm" or SKIP.search(arc): continue
        yield arc, name, f, FILES[tree].get((arc, name, "fim"))
def csa_for(tree, arc):
    from basara.font import Csa
    c = [f for (a, n, k), f in FILES[tree].items() if a == arc and k == "csa"]
    return [Csa.parse(read(f)) for f in c]
def sh_key(arc, name):
    """Map a Utage (arc, name) to the SH eng (arc, name). SH swaps msg_mNNN_plNNN -> msg_plNNN_mNNN and uses \\eng\\."""
    m = re.match(r"id/msg_m(\d+)_pl(\d+)\.arc$", arc)
    a = f"id/msg_pl{m.group(2)}_m{m.group(1)}.arc" if m else arc
    return "PS3_GAME/USRDIR/nativePS3/rom/eng/" + a, name.replace("\\jpn\\", "\\eng\\")
