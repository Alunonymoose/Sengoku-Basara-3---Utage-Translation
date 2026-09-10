"""Remember how the window was arranged, so the layout survives a restart.

A workshop tool is used for hours at a time and everyone wants the panes a
different width.  Dragging them back every launch is the kind of small friction
that makes a tool feel disposable, so window geometry, every sash position,
the zoom mode and the last folders are written to a small JSON beside the app.

Nothing here is load-bearing: if the file is missing or corrupt the app starts
with sensible defaults and simply writes a fresh one on exit.
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_NAME = "alrummi3_settings.json"

DEFAULTS = {
    "geometry": "1720x1000",
    "zoomed": False,
    "body_sashes": [],
    "preview_sashes": [],
    "review_sashes": [],
    "zoom_mode": "fit",
    "zoom": 1.0,
    "last_arc_dir": "",
    "last_folder_dir": "",
    "last_output_dir": "",
    "font_scale": 1.0,
    "log_lines": 400,
}


def settings_path(app_root: Path) -> Path:
    return Path(app_root) / SETTINGS_NAME


def load(app_root: Path) -> dict:
    data = dict(DEFAULTS)
    path = settings_path(app_root)
    if not path.is_file():
        return data
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if isinstance(stored, dict):
        for key, value in stored.items():
            if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
                data[key] = value
            elif key in DEFAULTS and isinstance(DEFAULTS[key], float):
                try:
                    data[key] = float(value)
                except (TypeError, ValueError):
                    pass
    return data


def save(app_root: Path, data: dict) -> None:
    try:
        settings_path(app_root).write_text(
            json.dumps(data, indent=1), encoding="utf-8"
        )
    except OSError:
        # Losing the layout is never worth interrupting the user for.
        pass
