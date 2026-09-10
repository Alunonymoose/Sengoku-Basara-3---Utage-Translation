from __future__ import annotations

"""Probe and route the local Ollama models used by the Utage pipeline."""

import argparse
import json
import time
import urllib.request
from pathlib import Path

MODELS = {
    "texture_review": "qwen2.5vl:7b",
    "texture_review_crosscheck": "gemma3:4b",
    "reasoning": "deepseek-r1:7b",
    "coding": "qwen2.5-coder:7b",
    "fast_text": "qwen2.5:3b",
}


def generate(model: str, prompt: str) -> tuple[str, float]:
    payload = {"model": model, "prompt": prompt, "stream": False}
    request = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    return str(result.get("response", "")).strip(), time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "MODEL_COCKPIT.json",
    )
    args = parser.parse_args()
    report = {"models": {}, "routing": MODELS}
    for role, model in MODELS.items():
        try:
            response, seconds = generate(model, "Reply with exactly READY.")
            report["models"][model] = {
                "role": role,
                "status": "ready" if "READY" in response.upper() else "responded",
                "seconds": round(seconds, 3),
            }
        except Exception as exc:
            report["models"][model] = {"role": role, "status": "error", "error": str(exc)}
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "pass", "models": len(report["models"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
