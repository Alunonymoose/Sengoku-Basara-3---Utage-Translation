"""Reading Japanese off a texture, with more than one engine.

Two engines are available and they fail differently, so the tool uses both:

* **RapidOCR** (ONNX, offline, no GPU) is fast and confident — it reads 大吉
  and 吉 at 0.99 on this game's cards in under two seconds, and its detector
  finds the text boxes on a whole sheet in well under one. Its recognition
  model is trained on Chinese, which covers kanji but not kana, and it
  confuses visually close characters: it reads 凶 as 区.
* **The local vision model** (qwen2.5vl through Ollama) reads more of the
  small elements but takes ten times as long and is far less reliable about
  what it invents.

So: RapidOCR first, the vision model for whatever it could not read, and the
project dictionary as the arbiter of what the English should be. Where an OCR
result is not in the dictionary, a small set of **known confusions** is tried
before giving up — that is what turns 区 back into 凶.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

# Below this confidence a read is shown for review rather than applied: a
# dictionary hit built on a shaky OCR result is still a shaky result, and
# wrong English on a texture is worse than leaving the Japanese alone.
TRUST_THRESHOLD = 0.60

# Characters this kind of model reliably mixes up in game lettering.  Each
# entry is tried as a substitution when a read is not in the dictionary.
CONFUSABLES = {
    "区": "凶", "凶": "区",
    "口": "回", "回": "口",
    "土": "士", "士": "土",
    "未": "末", "末": "未",
    "大": "犬", "犬": "大",
    "日": "曰", "曰": "日",
    "ロ": "口",
    "X": "凶", "x": "凶", "lix": "凶",
}


@dataclass
class Read:
    text: str
    confidence: float
    engine: str
    box: tuple | None = None


def _prepare(crop: Image.Image, target: int = 512, backdrop=(0, 0, 0, 255)) -> Image.Image:
    """Upscale and flatten. A 33x14 badge is unreadable to any engine."""

    scale = min(10, max(1, int(round(target / max(1, min(crop.width, crop.height))))))
    big = crop.convert("RGBA")
    if scale > 1:
        big = big.resize((big.width * scale, big.height * scale), Image.Resampling.LANCZOS)
    flat = Image.new("RGBA", big.size, backdrop)
    flat.alpha_composite(big)
    return flat.convert("RGB")


class RapidEngine:
    """The ONNX detector plus recogniser, if it is installed."""

    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def read_regions(self, image: Image.Image, scale: int = 2) -> list[Read]:
        """Find and read every text box on a whole sheet in one pass."""

        big = image.convert("RGBA")
        if scale > 1:
            big = big.resize((big.width * scale, big.height * scale), Image.Resampling.LANCZOS)
        flat = Image.new("RGBA", big.size, (0, 0, 0, 255))
        flat.alpha_composite(big)
        result, _elapse = self._engine(np.asarray(flat.convert("RGB")))
        reads: list[Read] = []
        for box, text, confidence in (result or []):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            reads.append(Read(
                text=str(text).strip(),
                confidence=float(confidence),
                engine=self.name,
                box=(int(min(xs)) // scale, int(min(ys)) // scale,
                     int(max(xs)) // scale, int(max(ys)) // scale),
            ))
        return reads

    def read_crop(self, crop: Image.Image) -> Read | None:
        result, _elapse = self._engine(np.asarray(_prepare(crop)))
        if not result:
            return None
        text = "".join(str(r[1]).strip() for r in result).replace(" ", "")
        confidence = max(float(r[2]) for r in result)
        return Read(text=text, confidence=confidence, engine=self.name)


class VisionEngine:
    """The local Ollama vision model, used only as OCR."""

    name = "vision model"

    PROMPT = (
        "Transcribe every Japanese character you can see in this image.\n"
        "Reply with ONLY the characters, nothing else. No explanation, no "
        "English, no romaji.\n"
        "If there is no Japanese text at all, reply with exactly NONE."
    )

    def __init__(self, client) -> None:
        self._client = client

    def read_crop(self, crop: Image.Image) -> Read | None:
        buffer = io.BytesIO()
        _prepare(crop, backdrop=(18, 18, 22, 255)).save(buffer, format="PNG")
        try:
            result = self._client._post({
                "model": self._client.vision_model,
                "prompt": self.PROMPT,
                "images": [base64.b64encode(buffer.getvalue()).decode("ascii")],
                "stream": False,
                "options": {"temperature": 0.0},
            }, 300)
        except Exception:
            return None
        text = str(result.get("response", "")).strip().replace("NONE", "").strip()
        if not text:
            return None
        # Confidence is unknown for a free-form model, so it is scored below
        # anything RapidOCR reports and treated accordingly.
        return Read(text=text, confidence=0.35, engine=self.name)


def build_engines(ai_client=None) -> list:
    """Whatever is available, fastest and most reliable first."""

    engines = []
    try:
        engines.append(RapidEngine())
    except Exception:
        pass
    if ai_client is not None:
        engines.append(VisionEngine(ai_client))
    return engines


def resolve_text(dictionary: dict, text: str):
    """Look a read up, trying known character confusions before giving up."""

    from project_dict import lookup as dict_lookup

    if not text:
        return None
    hit = dict_lookup(dictionary, text)
    if hit:
        return hit[0], text, "dictionary"
    cleaned = text.replace(" ", "").strip()
    if cleaned != text:
        hit = dict_lookup(dictionary, cleaned)
        if hit:
            return hit[0], cleaned, "dictionary"
    # One substitution at a time, which is enough for the confusions that
    # actually occur and keeps this from inventing words.
    for index, character in enumerate(cleaned):
        replacement = CONFUSABLES.get(character)
        if not replacement:
            continue
        candidate = cleaned[:index] + replacement + cleaned[index + 1:]
        hit = dict_lookup(dictionary, candidate)
        if hit:
            return hit[0], candidate, "dictionary (corrected a known OCR confusion)"
    for whole, replacement in CONFUSABLES.items():
        if cleaned == whole:
            hit = dict_lookup(dictionary, replacement)
            if hit:
                return hit[0], replacement, "dictionary (corrected a known OCR confusion)"
    return None


def read_element(crop: Image.Image, engines: list) -> Read | None:
    """Best available read of one element, trying each engine in turn."""

    best: Read | None = None
    for engine in engines:
        try:
            read = engine.read_crop(crop)
        except Exception:
            continue
        if read and read.text:
            if best is None or read.confidence > best.confidence:
                best = read
            # A confident dedicated OCR result is not worth second-guessing.
            if read.confidence >= 0.8:
                break
    return best
