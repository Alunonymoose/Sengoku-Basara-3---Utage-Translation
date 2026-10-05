import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "foundry_graph.py"
spec = importlib.util.spec_from_file_location("foundry_graph_tested", MODULE)
fg = importlib.util.module_from_spec(spec)
sys.modules["foundry_graph_tested"] = fg
spec.loader.exec_module(fg)


class FoundryGraphTests(unittest.TestCase):
    def test_incremental_file_index(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            live = tmp / "live"
            eng = live / "PS3_GAME" / "USRDIR" / "nativePS3" / "rom" / "eng"
            eng.mkdir(parents=True)
            target = eng / "hello.bin"
            target.write_bytes(b"abc")
            graph = fg.FoundryGraph(tmp / "graph.sqlite", live)
            try:
                first = graph.scan_root(fg.RootSpec("ENG", eng), None, None)
                self.assertEqual(first["changed_files"], 1)
                second = graph.scan_root(fg.RootSpec("ENG", eng), None, None)
                self.assertEqual(second["reused_files"], 1)
                target.write_bytes(b"abcd")
                third = graph.scan_root(fg.RootSpec("ENG", eng), None, None)
                self.assertEqual(third["changed_files"], 1)
                row = graph.db.execute("SELECT sha256,size FROM files WHERE role='ENG'").fetchone()
                self.assertEqual(row["size"], 4)
                self.assertEqual(row["sha256"], fg.sha256_bytes(b"abcd"))
            finally:
                graph.close()

    def test_signoff_invalidates_when_live_bytes_change(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            live = tmp / "live"
            scope = live / "PS3_GAME" / "USRDIR" / "nativePS3" / "rom" / "eng" / "demo"
            scope.mkdir(parents=True)
            (scope / "a.arc").write_bytes(b"A")
            b = scope / "b.arc"
            b.write_bytes(b"B")
            graph = fg.FoundryGraph(tmp / "graph.sqlite", live)
            try:
                cert = graph.create_signoff(
                    "PS3_GAME/USRDIR/nativePS3/rom/eng/demo",
                    "ROM_ENG_DEMO_TEST", "test-v1"
                )
                data = json.loads(cert.read_text(encoding="utf-8"))
                self.assertEqual(data["file_count"], 2)
                self.assertEqual(graph.evaluate_signoffs()[0]["status"], "VALID")
                b.write_bytes(b"B changed")
                state = graph.evaluate_signoffs()[0]
                self.assertEqual(state["status"], "STALE")
                self.assertIn("changed", state["reason"])
            finally:
                graph.close()

    def test_fingerprint_is_stable_for_same_index(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            live = tmp / "live"
            eng = live / "PS3_GAME" / "USRDIR" / "nativePS3" / "rom" / "eng"
            eng.mkdir(parents=True)
            (eng / "x.bin").write_bytes(b"x")
            (eng / "y.bin").write_bytes(b"y")
            graph = fg.FoundryGraph(tmp / "graph.sqlite", live)
            try:
                graph.scan_root(fg.RootSpec("ENG", eng), None, None)
                one = graph.fingerprint()
                graph.scan_root(fg.RootSpec("ENG", eng), None, None)
                two = graph.fingerprint()
                self.assertEqual(one, two)
            finally:
                graph.close()


if __name__ == "__main__":
    unittest.main()
