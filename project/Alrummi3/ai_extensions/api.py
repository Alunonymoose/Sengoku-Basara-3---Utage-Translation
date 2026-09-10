"""Stable, local extension contract for Alrummi 3.

Other AIs can add a provider without changing the GUI.  Providers should
return proposals only; the GUI remains responsible for preview, verification,
and the user's explicit confirmation before any ARC is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


API_VERSION = "1.0"


@dataclass(frozen=True)
class TextureAnalysis:
    translation: str = ""
    confidence: float | None = None
    regions: list[dict[str, int]] = field(default_factory=list)
    notes: str = ""
    provider: str = "unknown"


class AlrummiAIProvider(Protocol):
    """Interface an external local AI adapter may implement."""

    provider_id: str
    display_name: str
    api_version: str

    def analyze_texture(self, image_png: bytes, texture_name: str) -> TextureAnalysis:
        ...

