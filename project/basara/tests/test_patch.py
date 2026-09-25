"""Patchset build -> install -> rollback on a synthetic rom/eng tree, plus
catalogs and the CLI. This is the workflow that replaces bespoke build
scripts and ROOT-READY ZIPs."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from basara import arc, catalog, cli, patch, xet
from basara.table import MessageTable
from fixtures import TEXTS, msg_archive

sha = lambda b: hashlib.sha256(b).hexdigest()


def _xet_0x2a(w=32, h=32) -> bytes:
    import struct
    hdr = b"\x00XET" + struct.pack(">III", 0x97 | (2 << 28), 1 | (w << 6) | (h << 19), 1 | (0x2A << 8)) + struct.pack(">I", 20)
    blk = bytes([0, 0] + [0] * 6 + [0xEF, 0x7B, 0xEF, 0x7B] + [0] * 4)
    shell = hdr + blk * ((w // 4) * (h // 4))
    img = np.zeros((h, w, 4), np.uint8)
    img[4:28, 4:28] = (90, 90, 90, 255)
    out, _ = xet.graft(shell, img, allow_inconclusive_byte_order=True)
    return out


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "rom" / "eng"
    (root / "tenka").mkdir(parents=True)
    tex = _xet_0x2a()
    equip = msg_archive(TEXTS, extra_members=[(r"id\texture\jpn\tenka\tenka_023_ID_HQ", 0x241F5DEB, tex)])
    smith = arc.build([(r"id\texture\jpn\tenka\tenka_023_ID_HQ", 0x241F5DEB, tex)])
    (root / "tenka" / "equip.arc").write_bytes(equip)
    (root / "tenka" / "smith.arc").write_bytes(smith)
    work = tmp_path / "work"
    work.mkdir()
    cand = xet.decode_display(tex).copy()
    cand[8:16, 8:24] = (255, 255, 255, 255)
    from PIL import Image
    Image.fromarray(cand, "RGBA").save(work / "lottery.png")
    return root, work, equip, smith


def _patchset(work: Path, equip: bytes, smith: bytes, **over) -> Path:
    cand_sha = sha((work / "lottery.png").read_bytes())
    text = over.get("text", "Sacred Tree Bow:{br}First Frost{end}")
    expect = over.get("expect", TEXTS[0])
    body = f'''schema = "basara.patchset/1"
id = "test-set"

[[archive]]
path = "tenka/equip.arc"
sha256 = "{over.get('equip_sha', sha(equip))}"

  [[archive.text]]
  table = "id_brief_r"
  record = 0
  expect = {json.dumps(expect)}
  text = {json.dumps(text)}
  budget = {over.get('budget', 700)}

  [[archive.texture]]
  member = "tenka_023_ID_HQ"
  candidate = "lottery.png"
  candidate_sha256 = "{over.get('cand_sha', cand_sha)}"

[[archive]]
path = "tenka/smith.arc"
sha256 = "{sha(smith)}"

  [[archive.texture]]
  member = "tenka_023_ID_HQ"
  candidate = "lottery.png"
  candidate_sha256 = "{cand_sha}"
'''
    p = work / "set.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_build_install_rollback_end_to_end(tree, tmp_path):
    root, work, equip, smith = tree
    out = tmp_path / "build"
    rec = patch.build(_patchset(work, equip, smith), root, out)
    a = {x["path"]: x for x in rec["archives"]}
    assert len(a["tenka/equip.arc"]["changed_members"]) == 3        # GSM + FIM + texture
    # lockstep providers got byte-identical textures
    t_equip = arc.read((out / "tenka/equip.arc").read_bytes()).find("tenka_023_ID_HQ").raw
    t_smith = arc.read((out / "tenka/smith.arc").read_bytes()).find("tenka_023_ID_HQ").raw
    assert t_equip == t_smith
    # finished archive re-reads as intended
    t = MessageTable.open(arc.read((out / "tenka/equip.arc").read_bytes()), "id_brief_r")
    assert t.text(0) == "Sacred Tree Bow:{br}First Frost{end}" and t.text(1) == TEXTS[1]
    # live tree untouched by build
    assert (root / "tenka/equip.arc").read_bytes() == equip

    backups = tmp_path / "backups"
    inst = patch.install(out, root, backups)
    assert all(x["action"] == "install" for x in inst["archives"])
    assert sha((root / "tenka/equip.arc").read_bytes()) == a["tenka/equip.arc"]["output_sha256"]
    bdir = Path(inst["backup_dir"])
    assert (bdir / "tenka/equip.arc").read_bytes() == equip
    assert "tenka/equip.arc" in (bdir / "SHA256SUMS.txt").read_text()

    again = patch.install(out, root, backups)                          # idempotent
    assert all(x["action"] == "already-installed" for x in again["archives"])

    rb = patch.rollback(bdir / "INSTALL_RECORD.json")
    assert {x["action"] for x in rb["archives"]} == {"restore"}
    assert (root / "tenka/equip.arc").read_bytes() == equip
    assert (root / "tenka/smith.arc").read_bytes() == smith


def test_install_refuses_when_live_changed_since_build(tree, tmp_path):
    root, work, equip, smith = tree
    out = tmp_path / "build"
    patch.build(_patchset(work, equip, smith), root, out)
    (root / "tenka/equip.arc").write_bytes(equip[:-1] + bytes([equip[-1] ^ 1]))
    with pytest.raises(patch.PatchError, match="neither the build input nor output"):
        patch.install(out, root, tmp_path / "b")
    assert not (tmp_path / "b").exists()                                # nothing touched


def test_rollback_never_erases_later_edits(tree, tmp_path):
    root, work, equip, smith = tree
    out = tmp_path / "build"
    patch.build(_patchset(work, equip, smith), root, out)
    inst = patch.install(out, root, tmp_path / "b")
    (root / "tenka/equip.arc").write_bytes(b"someone else's newer work")
    with pytest.raises(patch.PatchError, match="refusing to erase later edits"):
        patch.rollback(Path(inst["backup_dir"]) / "INSTALL_RECORD.json")


@pytest.mark.parametrize("over,msg", [
    ({"equip_sha": "0" * 64}, "re-author the patchset"),
    ({"expect": "something else{end}"}, "patchset is stale"),
    ({"cand_sha": "f" * 64}, "candidate changed since approval"),
    ({"budget": 20}, "exceed budget"),
    ({"text": "Café{end}"}, "not in this font"),
    ({"text": "Two{p}speeches{end}", "expect": TEXTS[0]}, "structure changed"),
    ({"text": "Sacred {c:3}Tree{/c} Bow{end}"}, "structure changed"),
])
def test_build_fails_closed(tree, tmp_path, over, msg):
    root, work, equip, smith = tree
    with pytest.raises(Exception, match=msg):
        patch.build(_patchset(work, equip, smith, **over), root, tmp_path / "build")
    assert not (tmp_path / "build" / "build.json").exists()


def test_catalog_export_lint_import_build(tree, tmp_path):
    root, work, equip, _ = tree
    t = MessageTable.open(arc.read(equip), "id_brief_r")
    tsv = catalog.export(t)
    p = tmp_path / "brief.tsv"
    p.write_text(tsv, encoding="utf-8")
    rows = catalog.read(p)
    assert [r["record"] for r in rows] == [0, 1, 2, 4]                  # {end}-only row skipped
    edit = {0: "Sacred Tree Bow:{br}First Frost{end}",
            1: "Press {c:3}Release{/c} to flee.{end}",
            4: "Attack  Up +10%{end}"}
    for r in rows:
        r["translation"] = edit.get(r["record"], "")
    findings = catalog.lint(rows, t, budget=700)
    assert [f.code for f in findings] == ["extra-lines", "whitespace"]   # both are review WARNs
    assert all(f.level == "WARN" for f in findings)
    bad = [dict(r) for r in rows]
    bad[1]["translation"] = "Press Release to flee.{end}"               # colour span dropped
    bad[0]["translation"] = "Sacred Tree Bow — First Frost{end}"  # em dash not in font
    codes = {f.code for f in catalog.lint(bad, t)}
    assert {"placeables", "font-coverage"} <= codes
    toml = catalog.to_patchset(rows, patch_id="cat", arc_path="tenka/equip.arc", arc_sha256=sha(equip),
                               table="id_brief_r", budget=700)
    ps = work / "cat.toml"
    ps.write_text(toml, encoding="utf-8")
    patch.build(ps, root, tmp_path / "b2")
    t2 = MessageTable.open(arc.read((tmp_path / "b2/tenka/equip.arc").read_bytes()), "id_brief_r")
    assert t2.text(1) == edit[1] and t2.text(2) == TEXTS[2]


def test_catalog_terminology_lint(tree, tmp_path):
    _, _, equip, _ = tree
    t = MessageTable.open(arc.read(equip), "id_brief_r")
    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps({"entries": [{"id": "x", "status": "OFFICIAL_SH_EXACT",
                                              "canonical_english": "Faizlie Muto",
                                              "forbidden_or_superseded_variants": ["Fairy Muto"]}]}))
    rows = [{"record": 0, "current": TEXTS[0], "reference": "", "translation": "Fairy Muto{end}", "note": ""}]
    assert [f.code for f in catalog.lint(rows, t, terms_path=terms)] == ["terminology"]


def test_cli_smoke(tree, capsys, tmp_path):
    root, _, _, _ = tree
    arcp = str(root / "tenka/equip.arc")
    assert cli.main(["arc", "ls", arcp]) == 0
    assert "GSM" in capsys.readouterr().out
    assert cli.main(["msg", "tables", arcp]) == 0
    assert "OK" in capsys.readouterr().out
    assert cli.main(["msg", "show", arcp, "id_brief_r", "-r", "1"]) == 0
    assert "{c:3}Release{/c}" in capsys.readouterr().out
    assert cli.main(["msg", "census", str(root), "--out", str(tmp_path / "c.json")]) == 0
    assert json.loads((tmp_path / "c.json").read_text())["summary"] == {"OK": 1}
    bad = tmp_path / "bad.toml"
    bad.write_text('schema = "nope"\nid = "x"\n')
    assert cli.main(["build", str(bad), "--root", str(root), "--out", str(tmp_path / "o")]) == 2
