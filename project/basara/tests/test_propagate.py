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
    F = _xet((10, 10, 10))
    fname = r"msg\\m000_03\\jpn\\m000_03_13_ID_HQ"
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
        "id/msg_a.arc": ([(fname, TH, F)], [(fname, TH, _english(F))]),
        "id/msg_b.arc": ([(fname, TH, F)], [(fname, TH, F)]),
    }
    eng, jpn = tmp_path / "rom" / "eng", tmp_path / "rom" / "jpn"
    for rel, (jm, em) in layout.items():
        for root, members in ((jpn, jm), (eng, em)):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(arc.build(members))
    return eng, jpn, dict(J=J, K=K, L=L, EJ=EJ, EK1=EK1, name=name, kname=kname, mname=mname)


def test_only_byte_proven_missed_providers_are_copied(tmp_path):
    eng, jpn, t = _tree(tmp_path)
    providers, psl = prop.scan(eng, jpn, log=lambda m: None)
    groups = prop.decide(providers, psl, eng, jpn)
    verdicts = {g.name.rsplit("\\", 1)[-1]: g.verdict for g in groups}
    assert verdicts == {"stage_001_ID_HQ": "SAFE",
                        "waza_004_ID_HQ": "REVIEW_CONFLICTING_ENGLISH_VERSIONS",
                        "army_018_ID_HQ": "REVIEW_LAYOUT_CHANGED_IN_DONOR",
                        "waza2_001_ID_HQ": "REPAIR_DONOR_FIRST",         # damage is never spread
                        "m000_03_13_ID_HQ": "REVIEW_FONT_PAGE"}          # glyph atlases stay with their TNF/CSA
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


def test_pairs_mode_re_proves_every_reviewed_copy(tmp_path):
    eng, jpn, t = _tree(tmp_path)
    member = lambda rel, i: arc.read((eng / rel).read_bytes())[i].raw
    rows = [
        (t["name"], "common/mission/m001.arc", 0, sha(t["J"]), "tenka/tenka_stage_m001.arc", 0, sha(t["EJ"])),   # ok
        (t["kname"], "pause/waza_pl004.arc", 0, sha(t["K"]), "tenka/waza_a.arc", 0, sha(t["EK1"])),            # reviewed conflict choice
        (t["name"], "versus/menu.arc", 0, "0" * 64, "tenka/tenka_stage_m001.arc", 0, sha(t["EJ"])),            # stale approval
        (t["mname"], "select/c_story.arc", 0, sha(member("select/c_story.arc", 0)),
         "select/c_common.arc", 0, sha(member("select/c_common.arc", 0))),                                    # damaged donor
    ]
    # the same Japanese image stored under another name (cockpit_005 == result_011 in the real game)
    alias = r"id\texture\jpn\result\result_011_ID_HQ"
    for root in (jpn, eng):
        (root / "tenka" / "finish.arc").write_bytes(arc.build([(alias, TH, t["J"])]))
    rows = [r + ("", "") for r in rows] + [
        (t["name"], "tenka/finish.arc", 0, sha(t["J"]), "tenka/tenka_stage_m001.arc", 0, sha(t["EJ"]), alias, "")]
    tsv = tmp_path / "approved.tsv"
    tsv.write_text("member\ttarget_arc\ttarget_index\ttarget_sha256\tdonor_arc\tdonor_index\tdonor_sha256"
                   "\ttarget_member\tdonor_member\n" +
                   "".join("\t".join(map(str, r)) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "p2"
    summary = prop.build_pairs(tsv, eng, jpn, out, log=lambda m: None)
    assert summary == {"approved_rows": 5, "copies": 3, "archives": 3, "left_out": 2}
    report = {r["target"]: r for r in json.loads((out / "pairs_report.json").read_text(encoding="utf-8"))}
    assert report["versus/menu.arc#0"]["problems"] == ["target changed since approval"]
    assert report["select/c_story.arc#0"]["problems"] == ["donor shows legacy-writer damage"]
    rec = patch.build(out / "patchset.toml", eng, tmp_path / "b2")
    assert sorted(a["path"] for a in rec["archives"]) == ["common/mission/m001.arc", "pause/waza_pl004.arc",
                                                          "tenka/finish.arc"]
    assert arc.read((tmp_path / "b2" / "tenka/finish.arc").read_bytes())[0].raw == t["EJ"]
    assert arc.read((tmp_path / "b2" / "pause/waza_pl004.arc").read_bytes())[0].raw == t["EK1"]


def test_pack_members_takes_eng_jpn_and_layouts(tmp_path):
    import zipfile
    spec2 = importlib.util.spec_from_file_location("pack_members", TOOL.parent / "pack_members.py")
    pm = importlib.util.module_from_spec(spec2)
    sys.modules["pack_members"] = pm
    spec2.loader.exec_module(pm)
    eng, jpn, t = _tree(tmp_path)
    members, layouts = pm.parse_list("# repair inputs\ntenka/tenka_stage_m001.arc#0  # stage_001\n"
                                     "common/mission/m001.arc#1\nlayout tenka/tenka_stage_m001.arc\n")
    assert members == [("tenka/tenka_stage_m001.arc", 0), ("common/mission/m001.arc", 1)]
    res = pm.pack(eng, jpn, members, layouts, tmp_path / "m.zip", log=lambda m: None)
    assert res["members"] == 3
    z = zipfile.ZipFile(tmp_path / "m.zip")
    assert z.read("eng/tenka/tenka_stage_m001.arc/0000.tex") == t["EJ"]
    assert z.read("jpn/tenka/tenka_stage_m001.arc/0000.tex") == t["J"]
    man = json.loads(z.read("MANIFEST.json"))
    assert [m["same_as_jpn"] for m in man["members"]] == [False, True, True]     # stage edited; K and the layout untouched


def test_replace_members_only_takes_approved_bytes_over_the_computed_base(tmp_path):
    spec3 = importlib.util.spec_from_file_location("replace_members", TOOL.parent / "replace_members.py")
    rm = importlib.util.module_from_spec(spec3)
    sys.modules["replace_members"] = rm
    spec3.loader.exec_module(rm)
    eng, jpn, t = _tree(tmp_path)
    live = arc.read((eng / "common/mission/m001.arc").read_bytes())
    fixed = _english(t["J"])                                  # stands in for an approved repair
    files = tmp_path / "files"
    files.mkdir()
    (files / "fix.tex").write_bytes(fixed)
    (files / "bad.tex").write_bytes(fixed + b"x")
    rows = [("common/mission/m001.arc", 0, t["name"], sha(live[0].raw), "fix.tex", sha(fixed)),          # ok
            ("common/mission/m001.arc", 1, "x", "0" * 64, "fix.tex", sha(fixed)),                       # base moved on
            ("versus/menu.arc", 0, t["name"], sha(t["J"]), "bad.tex", sha(fixed))]                      # not the approved bytes
    lst = tmp_path / "repair.tsv"
    lst.write_text("arc\tindex\tmember\tbefore_sha256\tfile\tafter_sha256\n" +
                   "".join("\t".join(map(str, r)) + "\n" for r in rows), encoding="utf-8")
    res = rm.build(lst, files, eng, tmp_path / "out", log=lambda m: None)
    assert res == {"rows": 3, "replacements": 1, "archives": 1, "left_out": 2}
    rec = patch.build(tmp_path / "out" / "patchset.toml", eng, tmp_path / "b")
    built = arc.read((tmp_path / "b" / "common/mission/m001.arc").read_bytes())
    assert built[0].raw == fixed and built[1].raw == live[1].raw
    assert [a["path"] for a in rec["archives"]] == ["common/mission/m001.arc"]


def test_pack_fonts_and_chroma_audit_on_a_synthetic_tree(tmp_path):
    import zipfile
    spec4 = importlib.util.spec_from_file_location("pack_members", TOOL.parent / "pack_members.py")
    pm = importlib.util.module_from_spec(spec4)
    sys.modules["pack_members"] = pm
    spec4.loader.exec_module(pm)
    eng, jpn, t = _tree(tmp_path)
    tnf = b"\x00TNF" + bytes(28)
    for root in (eng, jpn):
        (root / "id" / "msg_c.arc").write_bytes(arc.build([("msg\\a\\jpn\\a_tnf", 1, tnf), ("msg\\a\\jpn\\a_tnf2", 1, tnf)]))
    res = pm.pack_fonts(eng, tmp_path / "f", log=lambda m: None)
    man = json.loads(zipfile.ZipFile(tmp_path / "f" / "fonts_part01.zip").read("FONTS_MANIFEST.json"))
    tn = [r for r in man if r["kind"] == "tnf"]
    assert len(tn) == 1 and len(tn[0]["owners"]) == 2 and res["distinct"]["tex"] >= 1

    spec5 = importlib.util.spec_from_file_location("chroma_audit", TOOL.parent / "chroma_audit.py")
    ca = importlib.util.module_from_spec(spec5)
    sys.modules["chroma_audit"] = ca
    spec5.loader.exec_module(ca)
    # a waza2-style fault: achromatic text, transparent texels stored (0,0,0,0)
    good = _english(t["M"] if "M" in t else t["J"])
    res = ca.run(eng, jpn, tmp_path / "audit", log=lambda m: None)
    assert res["edited_0x2A"] >= 3 and (tmp_path / "audit" / "upload_part01.zip").exists()
    assert good[:4] == b"\x00XET"
