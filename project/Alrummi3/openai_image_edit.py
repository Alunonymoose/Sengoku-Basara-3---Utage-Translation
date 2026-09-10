"""Optional OpenAI image-edit bridge for Alrummi 3 Hybrid.

This module is deliberately dependency-free and does not store API keys.  It
uses the Image Edit endpoint only when the operator explicitly chooses the
cloud edit action.  The local ARC/codec workflow remains fully offline.

The image model is never allowed to replace the whole game texture directly.
We send a context crop and composite the returned pixels only into the selected
rectangle; the original alpha silhouette is restored before returning.
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass

from PIL import Image

from alrummi3_core import Region


DEFAULT_MODEL = "gpt-image-2.5-sunburst"
ENDPOINT = "https://api.openai.com/v1/images/edits"
WORK_SIZE = 1024
MARGIN = 64


class OpenAIImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedEdit:
    canvas: Image.Image
    crop_box: Region
    placement: tuple[int, int, int, int]


def _expand(box: Region, image_size: tuple[int, int], amount: float = 0.28) -> Region:
    width, height = image_size
    pad_x = max(8, round(box.width * amount))
    pad_y = max(8, round(box.height * amount))
    return Region(
        max(0, box.left - pad_x),
        max(0, box.top - pad_y),
        min(width, box.right + pad_x),
        min(height, box.bottom + pad_y),
    )


def prepare_edit(source: Image.Image, region: Region) -> PreparedEdit:
    source = source.convert("RGBA")
    crop_box = _expand(region.clipped(source.size), source.size)
    crop = source.crop((crop_box.left, crop_box.top, crop_box.right, crop_box.bottom))

    usable = WORK_SIZE - MARGIN * 2
    scale = min(usable / max(1, crop.width), usable / max(1, crop.height))
    size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
    resized = crop.resize(size, Image.Resampling.LANCZOS)
    x = (WORK_SIZE - size[0]) // 2
    y = (WORK_SIZE - size[1]) // 2

    canvas = Image.new("RGBA", (WORK_SIZE, WORK_SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(resized, (x, y))
    return PreparedEdit(canvas, crop_box, (x, y, x + size[0], y + size[1]))


def _multipart(fields: dict[str, str], filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----Alrummi" + secrets.token_hex(16)
    out = io.BytesIO()

    def write(value: bytes) -> None:
        out.write(value)
        out.write(b"\r\n")

    for key, value in fields.items():
        write(f"--{boundary}".encode("ascii"))
        write(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"))
        write(b"")
        write(str(value).encode("utf-8"))

    write(f"--{boundary}".encode("ascii"))
    write(
        f'Content-Disposition: form-data; name="image"; filename="{filename}"'.encode("utf-8")
    )
    write(b"Content-Type: image/png")
    write(b"")
    out.write(data)
    out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode("ascii"))
    return out.getvalue(), boundary


def _request_image(canvas: Image.Image, prompt: str, api_key: str, *, model: str, quality: str) -> Image.Image:
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    body, boundary = _multipart(
        {
            "model": model,
            "prompt": prompt,
            "size": "1024x1024",
            "quality": quality,
            "output_format": "png",
        },
        "alrummi_texture.png",
        buffer.getvalue(),
    )
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "User-Agent": "Alrummi3-Hybrid/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(detail).get("error", {}).get("message", detail)
        except Exception:
            message = detail
        raise OpenAIImageError(f"OpenAI image edit failed ({exc.code}): {message}") from exc
    except urllib.error.URLError as exc:
        raise OpenAIImageError(f"Could not reach the OpenAI API: {exc.reason}") from exc
    except Exception as exc:
        raise OpenAIImageError(str(exc)) from exc

    rows = payload.get("data") or []
    if not rows:
        raise OpenAIImageError("Image API returned no image data")
    row = rows[0]
    if row.get("b64_json"):
        raw = base64.b64decode(row["b64_json"])
    elif row.get("url"):
        try:
            with urllib.request.urlopen(row["url"], timeout=120) as response:
                raw = response.read()
        except Exception as exc:
            raise OpenAIImageError(f"Could not download generated image: {exc}") from exc
    else:
        raise OpenAIImageError("Image API response did not contain b64_json or url")

    try:
        with Image.open(io.BytesIO(raw)) as opened:
            image = opened.convert("RGBA")
            image.load()
            return image
    except Exception as exc:
        raise OpenAIImageError(f"Generated image could not be decoded: {exc}") from exc


def edit_region(
    art_source: Image.Image,
    region: Region,
    wording: str,
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
    quality: str = "high",
) -> tuple[Image.Image, Region, dict]:
    """Return an AI-edited context crop in original texture coordinates.

    The caller decides which full candidate receives it.  Alpha is restored
    from the art source so generated pixels cannot expand or shrink the UI
    sprite silhouette.
    """
    wording = " ".join(str(wording).split())
    if not wording:
        raise OpenAIImageError("Enter the exact English wording first")
    if not api_key.strip():
        raise OpenAIImageError("No API key was supplied")

    prepared = prepare_edit(art_source, region)
    prompt = (
        "Edit this cropped PlayStation 3 game UI texture, preserving the existing Sengoku BASARA "
        "artwork exactly. Do not redesign the object, change its silhouette, recolor the material, "
        "move borders, add panels, add glow, or invent decoration. Preserve the original lighting, "
        "engraving, wear, texture, and period-styled typography treatment. Replace only the visible "
        f"Japanese/incorrect lettering on the central UI object with exactly: {wording!r}. "
        "The English text should look professionally integrated into the existing artwork, with the "
        "same hierarchy, perspective, bevel/emboss treatment and ink/metal response as the source. "
        "No other words. Keep all non-lettering artwork unchanged."
    )
    generated = _request_image(prepared.canvas, prompt, api_key, model=model, quality=quality)
    if generated.size != (WORK_SIZE, WORK_SIZE):
        generated = generated.resize((WORK_SIZE, WORK_SIZE), Image.Resampling.LANCZOS)

    x0, y0, x1, y1 = prepared.placement
    generated_crop = generated.crop((x0, y0, x1, y1)).resize(
        (prepared.crop_box.width, prepared.crop_box.height), Image.Resampling.LANCZOS
    )
    original_crop = art_source.convert("RGBA").crop(
        (prepared.crop_box.left, prepared.crop_box.top, prepared.crop_box.right, prepared.crop_box.bottom)
    )
    # Keep the game's exact alpha/silhouette.  The generated RGB can improve
    # lettering and material detail, but it may not invent coverage.
    generated_crop.putalpha(original_crop.getchannel("A"))
    return generated_crop, prepared.crop_box, {
        "mode": "openai_image_edit",
        "model": model,
        "quality": quality,
        "wording": wording,
        "context_box": prepared.crop_box.as_list(),
        "alpha_preserved": True,
        "whole_texture_replaced": False,
    }
