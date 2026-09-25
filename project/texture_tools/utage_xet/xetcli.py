#!/usr/bin/env python3
"""Compatibility shim: texture commands now live in ``basara.texcli``
(``basara tex ...``). ``python xetcli.py <cmd> ...`` keeps working."""
import hashlib
import importlib.util
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "basara" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from basara.texcli import *  # noqa: E402,F401,F403
from basara.texcli import main, read_png, write_png  # noqa: E402,F401

SAFE_ARC = Path(__file__).resolve().parents[2] / "tools" / "donor_matcher_v5_1_2026-09-23" / "safe_arc.py"
SAFE_ARC_SHA256 = "7beb24a5e11c0e154ca2517447389518c09386e32104392bff8e3328cfbff6f3"


def load_safe_arc():
    """The pinned legacy parser, kept as an independent test oracle."""
    data = SAFE_ARC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SAFE_ARC_SHA256:
        sys.exit(f"safe_arc.py hash mismatch; expected pinned {SAFE_ARC_SHA256}")
    spec = importlib.util.spec_from_file_location("safe_arc", SAFE_ARC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    main()
