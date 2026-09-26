"""tools/propagate_translated_textures.py on a synthetic eng/jpn pair: only
byte-proven missed providers are copied, everything ambiguous goes to review,
and the patchset it writes builds through the normal basara pipeline."""
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

import numpy as np

from basara import arc, patch, xet

TOOL = Path(__file__).resolve().parents[1] / "tools" / "propagate_translated_textures.py"
spec = importlib.util.spec_from_file_location("propagate", TOOL)
prop = importlib.util.module_from_spec(spec)
sys.modules["propagate"] = prop          # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(prop)

sha = lambda b: hashlib.sha256(b).hexdigest()
TH = 0x241F5DEB
PSL_TH = 0x2C4D1F0A


def _xet(fill, w=32, h=32):
    hdr = b"\x00XET" + struct.pack(">III", 0x97 | (2 << 28), 1 | (w << 6) | (h << 19), 1 | (0x2A << 8)) + struct.pack(">I", 20)
    shell = hdr + bytes([0, 0] + [0] * 6 + [0xEF, 0x7B, 0xEF, 0x7B] + [0] * 4) * ((w // 4) * (h // 4))
    img = np.zeros((h, w, 4), np.uint8)
    img[4:28, 4:28] = (*fill, 255)
    return xet.graft(shell, img, allow_inconclusive_byte_order=True)[0]


def _english(jp, text_rows=(8, 16)):
    img = xet.decode_display(jp).copy()
    img[text_rows[0]:text_rows[1], 8:24] = (255, 255, 255, 255)
    return xet.graft(jp, img, allow_inconclusive_byte_order=True)[0]


def _swapped(x):
    """What the quarantined xetenc path wrote: RGB565 endpoint bytes swapped in every block."""
    b = bytearray(x)
    off = xet.xet_info(x).mip_offsets[0]
    for o in range(off, len(b) - 15, 16):
        b[o + 8], b[o + 9], b[o + 10], b[o + 11] = b[o + 9], b[o + 8], b[o + 11], b[o + 10]
    return bytes(b)


def _tree(tmp_path):
    J, K, L = _xet((90, 90, 90)), _xet((40, 40, 40)), _xet((150, 150, 150))
    EJ, EK1, EK2, EL = _english(J), _english(K), _english(K, (18, 24)), _english(L)
    psl = b"\x00PSL" + bytes(60)
    psl2 = b"\x00PSL" + bytes(59) + b"\x01"
    name = r"id\texture\jpn\stage\stage_001_ID_HQ"
    kname = r"id\texture\jpn\waza\waza_004_ID_HQ"
    lname = r"id\texture\jpn\army\army_018_ID_HQ"
    M = _xet((200, 200, 200))
    mname = r"id\texture\jpn\waza2\waza2_001_ID_HQ"
    layout = {
        # path: (jpn members, eng members)
        "tenka/tenka_stage_m001.arc": ([(name, TH, J), ("lay", PSL_TH, psl)], [(name, TH, EJ), ("lay", PSL_TH, psl)]),
        "common/mission/m001.arc": ([(name, TH, J), ("x", TH, K)], [(name, TH, J), ("x", TH, K)]),
        "versus/menu.arc": ([(name, TH, J)], [(name, TH, J)]),
        "tenka/waza_a.arc": ([(kname, TH, K)], [(kname, TH, EK1)]),
        "tenka/waza_b.arc": ([(kname, TH, K)], [(kname, TH, EK2)]),
        "pause/waza_pl004.arc": ([(kname, TH, K)], [(kname, TH, K)]),
        "tenka/attack.arc": ([(lname, TH, L), ("lay", PSL_TH, psl)], [(lname, TH, EL), ("lay", PSL_TH, psl2)]),
        "tenka/dream.arc": ([(lname, TH, L)], [(lname, TH, L)]),
        "select/c_common.arc": ([(mname, TH, M)], [(mname, TH, _swapped(_english(M)))]),
        "select/c_story.arc": ([(mname, TH, M)], [(mname, TH, M)]),
    }
    eng, jpn = tmp_path / "rom" / "eng", tmp_path / "rom" / "jpn"
    for rel, (jm, em) in layout.items():
        for root, members in ((jpn, jm), (eng, em)):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(arc.build(members))
    return eng, jpn, dict(J=J, K=K, L=L, EJ=EJ)


def test_only_byte_proven_missed_providers_are_copied(tmp_path):
    eng, jpn, t = _tree(tmp_path)
    providers, psl = prop.scan(eng, jpn, log=lambda m: None)
    groups = prop.decide(providers, psl, eng, jpn)
    verdicts = {g.name.rsplit("\\", 1)[-1]: g.verdict for g in groups}
    assert verdicts == {"stage_001_ID_HQ": "SAFE",
                        "waza_004_ID_HQ": "REVIEW_CONFLICTING_ENGLISH_VERSIONS",
                        "army_018_ID_HQ": "REVIEW_LAYOUT_CHANGED_IN_DONOR",
                        "waza2_001_ID_HQ": "REPAIR_DONOR_FIRST"}         # damage is never spread
    stage = next(g for g in groups if g.verdict == "SAFE")
    assert sorted(x["arc"] for x in stage.targets) == ["common/mission/m001.arc", "versus/menu.arc"]
    assert stage.english_sha == sha(t["EJ"])

    out = tmp_path / "work"
    summary = prop.write_outputs(groups, eng, out)
    assert summary["safe_targets"] == 2 and summary["safe_archives"] == 2
    assert "waza_004" in (out / "review.tsv").read_text(encoding="utf-8")

    rec = patch.build(out / "safe" / "patchset.toml", eng, tmp_path / "build")
    for a in rec["archives"]:
        built = arc.read((tmp_path / "build" / a["path"]).read_bytes())
        live = arc.read((eng / a["path"]).read_bytes())
        for e in built:
            if e.name.endswith("stage_001_ID_HQ"):
                assert e.raw == t["EJ"]                       # the shipped English art, byte for byte
            else:
                assert e.raw == live[e.index].raw             # nothing else touched
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    assert {g["verdict"] for g in plan} == set(verdicts.values())
