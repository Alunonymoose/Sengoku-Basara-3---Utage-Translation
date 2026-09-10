from __future__ import annotations

"""Run a local vision-model review over generated texture contact sheets."""

import argparse
import base64
import json
import urllib.request
from pathlib import Path

from model_cockpit import MODELS


def ask(model: str, image: Path, prompt: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(image.read_bytes()).decode("ascii")],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    request = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.load(response)
    return str(result.get("response", "")).strip()


def parse_json(response: str) -> dict:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_response": response}
    return value if isinstance(value, dict) else {"raw_response": response}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODELS["texture_review"])
    parser.add_argument(
        "--cockpit",
        type=Path,
        default=Path(r"E:\Utage Patching New\_codex_tenka_v6\texture_cockpit"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    prompt = (
        "You are reviewing a game texture translation audit sheet. "
        "Inspect every artwork tile, ignoring the tiny filename labels and "
        "any captions beneath tiles. The artwork itself should be English; "
        "do not treat filenames or model guesses as Japanese text. "
        "Return strict JSON with keys: overall_score (0-10), japanese_visible "
        "(true/false), style_consistency (0-10), clipping_or_layout_issues "
        "(true/false), suspicious_tiles (array of tile labels), and concise_notes. "
        "Judge whether the English lettering looks like finished hand-painted "
        "console game artwork rather than a generic system font. Do not invent "
        "text that is unreadable."
    )
    report = {"model": args.model, "sheets": []}
    for sheet in sorted(args.cockpit.glob("contact_entry_*.png")):
        try:
            response = ask(args.model, sheet, prompt)
            try:
                assessment = parse_json(response)
            except Exception:
                assessment = {"raw_response": response}
            report["sheets"].append({"sheet": sheet.name, "assessment": assessment})
        except Exception as exc:
            report["sheets"].append({"sheet": sheet.name, "error": str(exc)})
    output = args.output or args.cockpit / "VISION_REVIEW.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "pass", "sheets": len(report["sheets"]), "output": str(output)}))


if __name__ == "__main__":
    main()
