"""Local-only Ollama client used by Alrummi 3.

No cloud endpoint is used.  If Ollama is unavailable, the GUI remains useful
as a manual translation and texture-layout tool.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request


class LocalAIError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        vision_model: str = "qwen2.5vl:7b",
        text_model: str = "qwen2.5:3b",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.vision_model = vision_model
        self.text_model = text_model

    def _post(self, payload: dict, timeout: int = 180) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LocalAIError(str(exc)) from exc

    def ping(self) -> str:
        result = self._post({"model": self.text_model, "prompt": "Reply with exactly READY.", "stream": False}, 15)
        return str(result.get("response", "")).strip()

    def analyze_texture(
        self,
        image_bytes: bytes,
        texture_name: str,
        width: int = 0,
        height: int = 0,
    ) -> dict:
        """Read the Japanese on a texture and propose English wording.

        Vision models routinely answer this kind of request by transcribing the
        Japanese rather than translating it, and by inventing coordinates in a
        space that has nothing to do with the real texture.  The prompt names
        the true pixel size and separates transcription from translation so
        both failures are visible in the result instead of silent.
        """

        size_hint = (
            f"The texture is exactly {width} pixels wide and {height} pixels tall. "
            f"Every coordinate you return must satisfy 0 <= left < right <= {width} "
            f"and 0 <= top < bottom <= {height}. "
            if width and height
            else ""
        )
        prompt = (
            "You are Alrummi 3, an offline game-texture localization assistant. "
            "The image is a game texture that contains Japanese text.\n\n"
            "Do both of these:\n"
            "1. Transcribe the Japanese you can actually see, exactly, into the "
            "japanese field.\n"
            "2. Translate that into natural English for a game UI, into the "
            "translation field.\n\n"
            "Rules:\n"
            "- The translation field MUST be English. Never put kanji, kana or "
            "Japanese of any kind in the translation field.\n"
            "- If the Japanese is a personal name, give the standard romanized "
            "name, not a literal gloss of the characters.\n"
            "- Keep the English short enough to fit the texture.\n"
            "- If you cannot read the text, set both japanese and translation to "
            'an empty string. Do not guess.\n'
            f"- {size_hint}"
            "\n"
            "Return strict JSON only, with keys: japanese (string), translation "
            "(string), confidence (number from 0 to 1), regions (array of objects "
            "with integer left, top, right, bottom), notes (string). "
            f"The texture resource name is: {texture_name}"
        )
        result = self._post(
            {
                "model": self.vision_model,
                "prompt": prompt,
                "images": [base64.b64encode(image_bytes).decode("ascii")],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            300,
        )
        return self._parse_json(str(result.get("response", "")).strip())

    @staticmethod
    def has_japanese(text: str) -> bool:
        """True when the text contains kana or CJK ideographs."""

        return any(
            "\u3040" <= ch <= "\u30ff"  # hiragana + katakana
            or "\u3400" <= ch <= "\u4dbf"  # CJK extension A
            or "\u4e00" <= ch <= "\u9fff"  # CJK unified ideographs
            or "\uff66" <= ch <= "\uff9d"  # halfwidth katakana
            for ch in text
        )

    def translate_japanese(self, japanese: str) -> str:
        """Second-pass translation when the vision model returns Japanese."""

        prompt = (
            "Translate this Japanese game text into natural, concise English.\n"
            "It is from a Sengoku-era Japanese game, so personal names should use "
            "their standard romanization.\n"
            "Reply with ONLY the English text. No quotes, no explanation, no "
            "Japanese, no romaji in brackets.\n\n"
            f"{japanese.strip()}"
        )
        result = self._post(
            {
                "model": self.text_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1},
            },
            180,
        )
        return str(result.get("response", "")).strip().strip('"').strip()

    def suggest_english(
        self,
        image_bytes: bytes,
        texture_name: str,
        width: int = 0,
        height: int = 0,
    ) -> dict:
        """Read a texture, and guarantee the translation field is English."""

        parsed = self.analyze_texture(image_bytes, texture_name, width, height)
        japanese = str(parsed.get("japanese", "")).strip()
        translation = str(parsed.get("translation", "")).strip()
        parsed["source_size"] = [width, height]
        parsed["retranslated"] = False

        # The vision model very often transcribes instead of translating.  When
        # that happens the text model gets a second, narrower job.
        if translation and self.has_japanese(translation):
            if not japanese:
                japanese = translation
                parsed["japanese"] = japanese
            try:
                retranslated = self.translate_japanese(japanese)
            except LocalAIError:
                retranslated = ""
            if retranslated and not self.has_japanese(retranslated):
                parsed["translation"] = retranslated
                parsed["retranslated"] = True
            else:
                parsed["translation"] = ""
                parsed["notes"] = (
                    "The local models returned Japanese rather than English. "
                    + str(parsed.get("notes", ""))
                ).strip()
        return parsed

    def chat(self, message: str, *, context: str = "", history: list[dict] | None = None) -> str:
        """Ask the local text model for an Alrummi 3 workflow suggestion."""

        transcript = []
        for item in (history or [])[-8:]:
            role = "User" if item.get("role") == "user" else "Alrummi 3"
            transcript.append(f"{role}: {str(item.get('content', '')).strip()}")
        prompt = (
            "You are Alrummi 3, a local-only assistant inside a game texture "
            "localization editor. Help with translation wording, texture layout, "
            "ARC workflow, and safe review steps. Be concise and practical. "
            "Do not claim to have edited or written files. If asked for English "
            "wording, put the suggested wording first and keep explanations short.\n\n"
            f"Current context:\n{context.strip() or 'No texture is selected.'}\n\n"
            f"Recent conversation:\n{chr(10).join(transcript) or '(none)'}\n\n"
            f"User request:\n{message.strip()}"
        )
        result = self._post(
            {
                "model": self.text_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.25},
            },
            180,
        )
        response = str(result.get("response", "")).strip()
        if not response:
            raise LocalAIError("local model returned an empty chat response")
        return response

    @staticmethod
    def _parse_json(response: str) -> dict:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LocalAIError(f"local model did not return JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LocalAIError("local model returned a non-object response")
        return parsed
