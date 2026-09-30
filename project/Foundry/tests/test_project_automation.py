import importlib.util
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


doctor = load("doctor_tested", "doctor.py")
det = load("determinism_guard_tested", "determinism_guard.py")


class ProjectAutomationTests(unittest.TestCase):
    def test_doctor_overall_precedence(self):
        self.assertEqual(doctor.derive_overall([
            {"status": "PASS"}, {"status": "PASS"}
        ]), "PASS")
        self.assertEqual(doctor.derive_overall([
            {"status": "PASS"}, {"status": "WARN"}
        ]), "WARN")
        self.assertEqual(doctor.derive_overall([
            {"status": "WARN"}, {"status": "FAIL"}
        ]), "FAIL")

    def test_oracle_lock_validation(self):
        names = ["RPCS3", "REvilLib", "Kuriimu2", "DirectXTex", "Compressonator", "bcdec", "vgmstream"]
        data = {"oracles": [{"name": n, "commit": "a" * 40} for n in names]}
        state, _, details = doctor.validate_oracle_lock(data)
        self.assertEqual(state, "PASS")
        self.assertEqual(details["count"], len(names))

        bad = {"oracles": [{"name": "RPCS3", "commit": "not-a-sha"}]}
        state, _, details = doctor.validate_oracle_lock(bad)
        self.assertEqual(state, "FAIL")
        self.assertTrue(details["bad"])
        self.assertTrue(details["missing"])

    def test_determinism_guard_detects_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "a.bin").write_bytes(b"same")
            (right / "a.bin").write_bytes(b"same")
            one = det.compare_trees(left, right)
            self.assertTrue(one["reproducible"])

            (right / "a.bin").write_bytes(b"different")
            two = det.compare_trees(left, right)
            self.assertFalse(two["reproducible"])
            self.assertEqual(two["changed_files"][0]["path"], "a.bin")

    def test_determinism_guard_detects_missing_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "a.bin").write_bytes(b"a")
            result = det.compare_trees(left, right)
            self.assertFalse(result["reproducible"])
            self.assertEqual(result["only_left"], ["a.bin"])

    def test_doctor_detects_live_graph_staleness(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live = root / "live"
            eng = live / "PS3_GAME" / "USRDIR" / "nativePS3" / "rom" / "eng"
            eng.mkdir(parents=True)
            target = eng / "a.bin"
            target.write_bytes(b"a")
            fg = doctor.fg.FoundryGraph(root / "graph.sqlite", live)
            try:
                fg.scan_root(doctor.fg.RootSpec("ENG", eng), None, None)
                fresh = doctor.live_role_freshness(fg, "ENG", eng)
                self.assertTrue(fresh["fresh"])
                target.write_bytes(b"changed")
                stale = doctor.live_role_freshness(fg, "ENG", eng)
                self.assertFalse(stale["fresh"])
                self.assertEqual(stale["changed_count"], 1)
            finally:
                fg.close()


if __name__ == "__main__":
    unittest.main()
