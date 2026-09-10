#!/usr/bin/env python3
"""V15 - restore the mission-local ASCII font route for every English battle
message set in Sengoku BASARA 3 Utage.

V10/V11 removed each mission set's local font (TNF 0x1D609FFB, CSA 0x5E0EF076
and the glyph atlas pages 0x241F5DEB) on the assumption that the engine would
fall back to the global msg\\ascii route the way Samurai Heroes does.  Utage's
engine does not: with no local .fnt the set never resolves and no dialogue is
drawn at all.  Every English text set that *does* work in Utage today
(id_pause, id_result, id_tenka, id_brief) carries its own copy of the global
ASCII font under its own resource names, so that is what each mission set gets
here.

Output shape, per mission set, starting from the pristine Japanese archive:

    TNF  msg\\<set>\\jpn\\<set>            <- global ASCII TNF (184 glyphs, 2 pages)
    GSM  msg\\<set>\\jpn\\<set>            <- Samurai Heroes English text
    FIM  msg\\<set>\\jpn\\<set>            <- Samurai Heroes English metrics
    XET  msg\\<set>\\jpn\\<set>_00_ID_HQ   <- global ASCII atlas page 0
    XET  msg\\<set>\\jpn\\<set>_01_ID_HQ   <- global ASCII atlas page 1
    CSA  msg\\<set>\\jpn\\<set>            <- global ASCII char->glyph table
    GSM  msg\\<set>\\jpn\\<set>_r          <- Samurai Heroes English text
    FIM  msg\\<set>\\jpn\\<set>_r          <- Samurai Heroes English metrics
    ... every non-message entry byte-identical (stage script, name plates)

Atlas pages 02+ are dropped: the ASCII TNF encodes its page in the high byte of
each glyph id and never references a page above 1, so they are dead weight.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"E:\Utage Patching New\_codex_tenka_v6")
import arc_tools as A
import arcbuild

UTAGE = Path(r"E:\Utage Patching New")
SH = Path(r"E:\SAMURAI HEROES")
UTAGE_ID_JPN = UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\jpn\id"
UTAGE_ID_ENG = UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id"
SH_ID_ENG = SH / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id"
FONT_ARC = UTAGE / r"PS3_GAME\USRDIR\nativePS3\rom\eng\basara.arc"

TNF, GSM, FIM, XET, CSA = 0x1D609FFB, 0x10C460E6, 0x2EA515BF, 0x241F5DEB, 0x5E0EF076

FONT_SHA = {
    "tnf": "df843e0b42390e89adcbf16ef02ce8d4d91cb984790b9f3211ac1ec0b7c5efbe",
    "csa": "9d5b493204cae29be28a24bf28ec1b46ba00d9a8c35d2a48618900a6108e988b",
    "page_00": "bd9325a975d6b963c7b8a21151c5fbe4866ae36a89d8f632cc58cb3c868b244f",
    "page_01": "2563fb5f4c3d54bcdaacecdad231bf8e1709877f878b00caf3bfc9cffc34f783",
}

STAGING = Path(__file__).parent / "V15_STAGING"
REPORT = Path(__file__).parent / "V15_REPORT.json"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_font():
    arc = A.parse_arc(FONT_ARC)
    want = {
        "tnf": (TNF, r"msg\ascii\jpn\ascii"),
        "csa": (CSA, r"msg\ascii\jpn\ascii"),
        "page_00": (XET, r"msg\ascii\jpn\ascii_00_ID_HQ"),
        "page_01": (XET, r"msg\ascii\jpn\ascii_01_ID_HQ"),
    }
    out = {}
    for name, key in want.items():
        hits = [e for e in arc.entries if (e.type_hash, e.name) == key]
        if len(hits) != 1:
            raise AssertionError("%s: %d matches for %s" % (name, len(hits), key))
        out[name] = A.unpack(hits[0])
    got = {k: sha(v) for k, v in out.items()}
    if got != FONT_SHA:
        raise AssertionError({"font hash mismatch": got})
    return out


def set_key(arc):
    """The set's internal resource name, e.g. msg\\m019_15\\jpn\\m019_15."""
    hits = {e.name for e in arc.entries
            if e.type_hash == GSM and not e.name.endswith("_r")}
    if len(hits) != 1:
        raise AssertionError("expected 1 main GSM, found %s" % sorted(hits))
    return hits.pop()


def text_payloads(arc, key):
    want = {(GSM, key), (FIM, key), (GSM, key + "_r"), (FIM, key + "_r")}
    out = {}
    for e in arc.entries:
        k = (e.type_hash, e.name)
        if k in want:
            if k in out:
                raise AssertionError("duplicate %s" % (k,))
            out[k] = A.unpack(e)
    if set(out) != want:
        raise AssertionError("missing text resources: %s" % (want - set(out),))
    return out


def convert(base_path, donor_path, font):
    base = A.parse_arc(base_path)
    donor = A.parse_arc(donor_path)
    key = set_key(base)
    donor_key = set_key(donor)
    donor_text = text_payloads(donor, donor_key)

    keep, repl, dropped = [], {}, []
    seen = set()
    for e in base.entries:
        name, th = e.name, e.type_hash
        if name.startswith("msg\\"):
            if th == TNF and name == key:
                repl[e.index] = font["tnf"]
            elif th == CSA and name == key:
                repl[e.index] = font["csa"]
            elif th == XET and name.startswith(key + "_") and name.endswith("_ID_HQ"):
                page = name[len(key) + 1:-len("_ID_HQ")]
                if page == "00":
                    repl[e.index] = font["page_00"]
                elif page == "01":
                    repl[e.index] = font["page_01"]
                else:
                    dropped.append(name)
                    continue
            elif th in (GSM, FIM) and name in (key, key + "_r"):
                repl[e.index] = donor_text[(th, name.replace(key, donor_key))]
            else:
                raise AssertionError("unhandled msg resource 0x%08X %s" % (th, name))
        keep.append(e.index)
        seen.add((th, name))

    required = {(TNF, key), (CSA, key), (GSM, key), (FIM, key),
                (GSM, key + "_r"), (FIM, key + "_r"),
                (XET, key + "_00_ID_HQ"), (XET, key + "_01_ID_HQ")}
    if not required <= seen:
        raise AssertionError("%s: missing %s" % (base_path.name, sorted(required - seen)))

    raw = arcbuild.build(base, keep, repl)
    info = {
        "base": base_path.name, "base_sha256": sha(base.data),
        "donor": donor_path.name, "donor_sha256": sha(donor.data),
        "set_key": key, "donor_key": donor_key,
        "entries_in": len(base.entries), "entries_out": len(keep),
        "dropped_atlas_pages": len(dropped),
        "output_sha256": sha(raw), "output_bytes": len(raw),
    }
    return raw, info


def verify(raw, base_path, donor_path, font):
    tmp = STAGING / "_verify.arc"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(raw)
    arc = A.parse_arc(tmp)
    tmp.unlink()

    key = set_key(arc)
    got = {(e.type_hash, e.name): A.unpack(e) for e in arc.entries}
    if got[(TNF, key)] != font["tnf"]:
        raise AssertionError("TNF not installed")
    if got[(CSA, key)] != font["csa"]:
        raise AssertionError("CSA not installed")
    if got[(XET, key + "_00_ID_HQ")] != font["page_00"]:
        raise AssertionError("page 00 not installed")
    if got[(XET, key + "_01_ID_HQ")] != font["page_01"]:
        raise AssertionError("page 01 not installed")
    if any(e.type_hash == XET and e.name.startswith(key + "_") and
           e.name not in (key + "_00_ID_HQ", key + "_01_ID_HQ") for e in arc.entries):
        raise AssertionError("stale atlas page survived")

    donor = A.parse_arc(donor_path)
    dkey = set_key(donor)
    dtext = text_payloads(donor, dkey)
    for th in (GSM, FIM):
        for suffix in ("", "_r"):
            if got[(th, key + suffix)] != dtext[(th, dkey + suffix)]:
                raise AssertionError("text 0x%08X%s is not exact SH" % (th, suffix))

    base = A.parse_arc(base_path)
    for e in base.entries:
        if e.name.startswith("msg\\"):
            continue
        if got[(e.type_hash, e.name)] != A.unpack(e):
            raise AssertionError("non-message resource altered: %s" % e.name)


def collect_targets():
    targets = []
    for p in sorted(UTAGE_ID_ENG.glob("msg_m*_pl*.arc")):
        if any(x in p.name for x in ("backup", "PRE_", "_V1")):
            continue
        if any(e.type_hash == TNF for e in A.parse_arc(p).entries):
            continue  # still has a local font: untouched Japanese, or already fixed
        m = re.fullmatch(r"msg_(m\d+)_(pl\d+)\.arc", p.name)
        if not m:
            raise AssertionError("unexpected name %s" % p.name)
        mission, player = m.groups()
        base = UTAGE_ID_JPN / p.name
        donor = SH_ID_ENG / ("msg_%s_%s.arc" % (player, mission))
        if not base.exists():
            raise AssertionError("no pristine base for %s" % p.name)
        if not donor.exists():
            raise AssertionError("no SH donor for %s" % p.name)
        targets.append((p, base, donor))
    return targets


def main():
    font = load_font()
    targets = collect_targets()
    print("%d sets to convert" % len(targets))
    if STAGING.exists():
        shutil.rmtree(STAGING)
    outdir = STAGING / r"PS3_GAME\USRDIR\nativePS3\rom\eng\id"
    outdir.mkdir(parents=True)

    infos = []
    for i, (live, base, donor) in enumerate(targets, 1):
        raw, info = convert(base, donor, font)
        verify(raw, base, donor, font)
        (outdir / live.name).write_bytes(raw)
        infos.append(info)
        if i % 100 == 0 or i == len(targets):
            print("  %d/%d" % (i, len(targets)))

    report = {
        "patch": "Utage Battle Dialogue V15 - mission-local ASCII font",
        "font_source": str(FONT_ARC),
        "font_sha256": FONT_SHA,
        "sets_converted": len(infos),
        "total_output_bytes": sum(x["output_bytes"] for x in infos),
        "atlas_pages_dropped": sum(x["dropped_atlas_pages"] for x in infos),
        "sets": infos,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "sets"}, indent=2))


if __name__ == "__main__":
    main()
