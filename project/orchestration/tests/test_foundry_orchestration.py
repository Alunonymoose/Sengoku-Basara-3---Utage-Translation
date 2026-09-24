from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve()
FOUNDRY = HERE.parent.parent / "foundry.py"
spec = importlib.util.spec_from_file_location("foundry_orchestration", FOUNDRY)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def make_arc(resource: str, raw: bytes, type_hash: int = 0x241F5DEB) -> bytes:
    name = resource.encode("utf-8")
    if len(name) >= 64:
        raise ValueError("test name too long")
    count = 1
    table_end = 8 + 80 * count
    payload_offset = (table_end + 15) & ~15
    out = bytearray(payload_offset + len(raw))
    out[:4] = b"\0CRA"
    struct.pack_into(">HH", out, 4, 8, count)
    rec = 8
    out[rec:rec + len(name)] = name
    struct.pack_into(">IIII", out, rec + 64, type_hash, len(raw), len(raw) << 3, payload_offset)
    out[payload_offset:] = raw
    return bytes(out)


class OrchestrationTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mod.main(list(args))
        return code, buf.getvalue()

    def test_snapshot_query_runtime_precedence_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live = root / "PS3_GAME" / "USRDIR" / "nativePS3" / "rom" / "eng"
            live.mkdir(parents=True)
            key = r"id\texture\jpn\fixture\fixture_000_ID_HQ"
            (live / "a.arc").write_bytes(make_arc(key, b"AAAA"))
            (live / "b.arc").write_bytes(make_arc(key, b"BBBB"))
            log = root / "RPCS3.log"
            log.write_text("Opening /dev_hdd0/game/UTAGE/USRDIR/nativePS3/rom/eng/b.arc\nOpening /dev_hdd0/game/UTAGE/USRDIR/nativePS3/rom/eng/a.arc\n", encoding="utf-8")

            code, text = self.run_cli("snapshot", str(root), "--rpcs3-log", str(log), "--git-commit", "fixture")
            self.assertEqual(0, code)
            snap = json.loads(text)
            self.assertEqual(2, snap["arc_file_count"])
            self.assertEqual(2, snap["resource_count"])
            self.assertEqual(1, snap["duplicate_provider_groups"])
            self.assertEqual(1, snap["divergent_provider_groups"])
            self.assertGreaterEqual(snap["runtime_ranked_arcs"], 2)

            code, text = self.run_cli("query", str(root), key, "--type-hash", "0x241F5DEB", "--exact", "--json")
            self.assertEqual(0, code)
            result = json.loads(text)
            self.assertEqual("DIVERGENT", result[0]["status"])
            self.assertTrue(result[0]["observed_effective_provider"].endswith("b.arc"))

            code, text = self.run_cli("verify", str(root))
            self.assertEqual(0, code)
            self.assertTrue(json.loads(text)["match"])

            exported = root / "ownership-export"
            code, text = self.run_cli("export-ownership", str(root), "--out", str(exported))
            self.assertEqual(0, code)
            report = json.loads((exported / "resource_ownership.json").read_text(encoding="utf-8"))
            self.assertEqual(1, report["summary"]["divergent_exact_duplicate_classes"])
            self.assertTrue((exported / "resources.csv").is_file())
            self.assertEqual("USRDIR/nativePS3/rom/eng/b.arc", report["exact_duplicate_classes"][0]["effective_provider"])

            (live / "a.arc").write_bytes(make_arc(key, b"CCCC"))
            code, text = self.run_cli("verify", str(root))
            self.assertEqual(3, code)
            self.assertFalse(json.loads(text)["match"])

    def test_recipe_is_snapshot_and_candidate_hash_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live = root / "PS3_GAME" / "USRDIR" / "nativePS3" / "rom" / "eng"
            live.mkdir(parents=True)
            key = r"id\texture\jpn\fixture\fixture_001_ID_HQ"
            (live / "owner.arc").write_bytes(make_arc(key, b"DATA"))
            self.assertEqual(0, self.run_cli("snapshot", str(root))[0])

            candidate = root / "candidate.png"
            candidate.write_bytes(b"candidate-v1")
            recipe = root / "recipe.json"
            code, _ = self.run_cli(
                "recipe-new", str(root), key, "--type-hash", "0x241F5DEB",
                "--recipe-id", "fixture-recipe", "--candidate", str(candidate),
                "--encoder", "fixture", "--out", str(recipe),
            )
            self.assertEqual(0, code)
            obj = json.loads(recipe.read_text(encoding="utf-8"))
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            obj["approval"] = {"status": "APPROVED", "approved_candidate_sha256": digest, "evidence": ["unit-test"]}
            recipe.write_text(json.dumps(obj, indent=2), encoding="utf-8")

            code, text = self.run_cli("recipe-validate", str(recipe), "--snapshot", str(root), "--require-candidate")
            self.assertEqual(0, code)
            self.assertTrue(json.loads(text)["valid"])

            candidate.write_bytes(b"candidate-v2")
            code, text = self.run_cli("recipe-validate", str(recipe), "--snapshot", str(root), "--require-candidate")
            self.assertEqual(4, code)
            self.assertFalse(json.loads(text)["valid"])

    def test_visual_regression_mask_and_hash_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            baseline=root/"baseline.png"; candidate=root/"candidate.png"; mask=root/"mask.png"
            Image.new("RGBA",(8,8),(10,20,30,255)).save(baseline)
            changed=Image.new("RGBA",(8,8),(10,20,30,255)); changed.putpixel((3,4),(255,20,30,255)); changed.save(candidate)
            code,text=self.run_cli("visual-compare",str(baseline),str(candidate),"--out-dir",str(root/"fail"))
            self.assertEqual(5,code); self.assertFalse(json.loads(text)["pass"])
            m=Image.new("L",(8,8),0); m.putpixel((3,4),255); m.save(mask)
            code,text=self.run_cli("visual-compare",str(baseline),str(candidate),"--mask",str(mask),"--out-dir",str(root/"pass"),"--snapshot-id","a"*64)
            result=json.loads(text)
            self.assertEqual(0,code); self.assertTrue(result["pass"]); self.assertEqual("a"*64,result["snapshot_id"])
            self.assertTrue((root/"pass"/"visual_diff.png").is_file())


if __name__ == "__main__":
    unittest.main()
