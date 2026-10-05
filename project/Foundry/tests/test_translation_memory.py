import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "translation_memory.py"
spec = importlib.util.spec_from_file_location("translation_memory_tested", MODULE)
tm_mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tm_mod)


class TranslationMemoryTests(unittest.TestCase):
    def test_normalize_equivalent_spacing(self):
        self.assertEqual(tm_mod.normalize("  Hello   World  "), "hello world")
        self.assertEqual(tm_mod.normalize("ＡＢＣ"), "abc")

    def test_approved_conflict_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            tm = tm_mod.TranslationMemory(Path(td) / "tm.sqlite")
            try:
                tm.add("武田道場", "Takeda Dojo", provenance="project-approved", approved=True)
                tm.add("武田道場", "Takeda Training Hall", provenance="official-SH", approved=True)
                audit = tm.audit()
                self.assertEqual(audit["approved_source_conflicts"], 1)
                self.assertEqual(audit["conflicts"][0]["target_count"], 2)
            finally:
                tm.close()

    def test_priority_orders_approved_official_above_draft(self):
        with tempfile.TemporaryDirectory() as td:
            tm = tm_mod.TranslationMemory(Path(td) / "tm.sqlite")
            try:
                tm.add("独眼竜", "One-Eyed Dragon", provenance="machine-draft")
                tm.add("独眼竜", "One-Eyed Dragon", provenance="official-SH", approved=True)
                rows = tm.find("独眼竜")
                self.assertTrue(rows[0]["approved"])
                self.assertEqual(rows[0]["provenance"], "official-SH")
            finally:
                tm.close()


if __name__ == "__main__":
    unittest.main()
