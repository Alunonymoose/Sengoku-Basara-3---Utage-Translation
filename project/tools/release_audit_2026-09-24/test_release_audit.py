#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("foundry_release_audit", HERE / "foundry_release_audit.py")
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

class ReleaseAuditBootstrapTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(audit.classify_file(Path("rom/eng/title.arc")), "ARC")
        self.assertEqual(audit.classify_file(Path("PS3_GAME/USRDIR/EBOOT.BIN")), "EXECUTABLE")
        self.assertEqual(audit.classify_file(Path("nativePS3/movie/op029_00.pam")), "MOVIE_PAM")
        self.assertEqual(audit.classify_file(Path("PS3_GAME/PARAM.SFO")), "CONFIG_METADATA")
        self.assertEqual(audit.classify_file(Path("PS3_GAME/TROPDIR/NPWR02325_00/TROP.SFM")), "TROPHY")

    def test_sha256_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.bin"
            p.write_bytes(b"abc")
            self.assertEqual(
                audit.sha256_file(p),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )

    def test_dependency_record_detects_expected_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tool.py"
            p.write_bytes(b"abc")
            rec = audit.dependency_record(
                p,
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )
            self.assertTrue(rec["exists"])
            self.assertTrue(rec["hash_ok"])

    def test_dependency_record_accepts_newline_only_text_equivalence(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tool.py"
            p.write_bytes(b"print('x')\nprint('y')\n")
            crlf = b"print('x')\r\nprint('y')\r\n"
            expected = audit.sha256_bytes(crlf)
            rec = audit.dependency_record(p, expected)
            self.assertTrue(rec["hash_ok"])
            self.assertEqual(rec["hash_match_form"], "utf8_crlf")

    def test_scan_files_emits_errors_instead_of_silent_skip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "x.arc").write_bytes(b"not-an-arc")
            rows = audit.scan_files(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["relative_path"], "x.arc")
            self.assertEqual(rows[0]["status"], "OK")
            self.assertEqual(rows[0]["class"], "ARC")

if __name__ == "__main__":
    unittest.main()
