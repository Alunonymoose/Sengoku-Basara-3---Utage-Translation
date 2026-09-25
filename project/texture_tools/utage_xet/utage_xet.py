"""Compatibility shim: the canonical XET codec now lives in the ``basara``
core package (``project/basara/src/basara/xet.py``). ``import utage_xet``
returns that exact module so existing tools and tests keep working."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "basara" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from basara import xet as _impl  # noqa: E402

sys.modules[__name__] = _impl
