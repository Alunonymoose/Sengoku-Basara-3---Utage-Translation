"""High-quality art-preserving image edit for Alrummi 3 V4.

Optional cloud path: only used when no official Samurai Heroes donor exists.
The source ARC is never touched here; this module only returns a preview image.
"""
from __future__ import annotations

import base64
import io
import json
import secrets
import urllib.error
import urllib.request

import numpy as np
from PIL import Image

MODEL = "gpt-image-2.5-sunburst"
ENDPOINT = "https://api.openai.com/v1/images/edits"
WORK = 1024
MARGIN = 48

class ImageEditError(RuntimeError):
    pass

def _multipart(fields: dict[str, str], png: bytes):
    boundary = "----AlrummiV4" + secrets.token_hex(16)
    out = io.BytesIO()
    def line(blob=b""):
        out.write(blob); out.write(b"\r\n")
    for key, value in fields.items():
        line(f"--{boundary}".encode())
        line(f'Content-Disposition: form-data; name="{key}"'.encode())
        line()
        line(str(value).encode("utf-8"))
    line(f"--{boundary}".encode())
    line(b'Content-Disposition: form-data; name="image"; filename="texture.png"')
    line(b"Content-Type: image/png")
    line()
    out.write(png); out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), boundary

def _fit_canvas(image: Image.Image):
    image = image.convert("RGBA")
    usable = WORK - MARGIN*2
    scale = min(usable/max(1,image.width), usable/max(1,image.height))
    size = (max(1,round(image.width*scale)), max(1,round(image.height*scale)))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    x = (WORK-size[0])//2
    y = (WORK-size[1])//2
    canvas = Image.new("RGBA",(WORK,WORK),(0,0,0,0))
    canvas.alpha_composite(resized,(x,y))
    return canvas,(x,y,x+size[0],y+size[1])

def _request(canvas: Image.Image, prompt: str, api_key: str) -> Image.Image:
    buf = io.BytesIO(); canvas.save(buf,"PNG")
    body,boundary = _multipart({
        "model": MODEL,
        "prompt": prompt,
        "size": "1024x1024",
        "quality": "high",
        "output_format": "png",
    }, buf.getvalue())
    req = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "User-Agent": "Alrummi3-V4/1.0",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8",errors="replace")
        try:
            detail = json.loads(detail).get("error",{}).get("message",detail)
        except Exception:
            pass
        raise ImageEditError(f"image edit failed ({exc.code}): {detail}") from exc
    except Exception as exc:
        raise ImageEditError(f"image edit request failed: {exc}") from exc

    rows = payload.get("data") or []
    if not rows:
        raise ImageEditError("image API returned no image")
    row = rows[0]
    if row.get("b64_json"):
        raw = base64.b64decode(row["b64_json"])
    elif row.get("url"):
        with urllib.request.urlopen(row["url"], timeout=120) as response:
            raw = response.read()
    else:
        raise ImageEditError("image response contained neither b64_json nor url")
    with Image.open(io.BytesIO(raw)) as opened:
        out = opened.convert("RGBA"); out.load()
    return out

def edit_texture(art_source: Image.Image, resource_name: str, api_key: str,
                 wording_hint: str = ""):
    """Rebuild lettering while preserving the original sprite-sheet artwork."""
    if not api_key.strip():
        raise ImageEditError("No OpenAI API key supplied")

    art = art_source.convert("RGBA")
    canvas, placement = _fit_canvas(art)
    hint = " ".join(wording_hint.split()).strip()
    special = ""
    lowered = resource_name.lower()
    if "roulette" in lowered or "fortune" in lowered:
        special = (
            " Fortune/roulette terminology must use these exact translations where those "
            "Japanese labels occur: 大吉 = GREAT LUCK, 吉 = GOOD LUCK, 凶 = BAD LUCK."
        )
    exact = (
        f" If the operator supplied wording, use it exactly where appropriate: {hint!r}."
        if hint else
        " Translate the visible Japanese UI wording faithfully into concise natural English."
    )
    prompt = (
        "You are editing an original PlayStation 3 Sengoku BASARA 3 Utage UI sprite sheet. "
        "This is a localization repair, not a redesign. Preserve every sprite's exact position, "
        "size, silhouette, border, material, ornament, lighting, texture, perspective and visual "
        "hierarchy. Keep the native Japanese game's high-quality stylized art. Replace only text "
        "that is Japanese, broken, ugly, or visibly fan-made with professionally integrated English "
        "lettering that looks as if Capcom shipped it. Do not add panels, glow, icons, extra words, "
        "new decorations, or generic gold/jade styling. Do not move or resize any sprite. "
        "Keep transparent areas transparent and do not paint into unused atlas space."
        + exact + special +
        f" Resource identity: {resource_name!r}. Return the complete edited sprite sheet."
    )
    generated = _request(canvas,prompt,api_key)
    if generated.size != (WORK,WORK):
        generated = generated.resize((WORK,WORK),Image.Resampling.LANCZOS)
    x0,y0,x1,y1 = placement
    crop = generated.crop((x0,y0,x1,y1)).resize(art.size,Image.Resampling.LANCZOS)

    # Critical game-format preservation: alpha/silhouette comes from the real asset,
    # and fully transparent RGB is restored too because those hidden RGB values can
    # matter to the game's shader/material path.
    orig = np.asarray(art,dtype=np.uint8)
    gen = np.asarray(crop,dtype=np.uint8).copy()
    gen[...,3] = orig[...,3]
    transparent = orig[...,3] <= 3
    gen[transparent,:3] = orig[transparent,:3]
    out = Image.fromarray(gen,"RGBA")
    return out, {
        "mode":"high_quality_ai_rebuild",
        "model":MODEL,
        "quality":"high",
        "resource":resource_name,
        "art_source_dimensions":list(art.size),
        "alpha_preserved":True,
        "transparent_rgb_preserved":True,
        "wording_hint":hint or None,
    }
