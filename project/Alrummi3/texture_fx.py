"""Material and lighting effects for game textures.

The "polish" the tool used to offer was a contrast and sharpness nudge, which
is nowhere near what a replacement texture needs.  What is actually wanted is
what an artist would do in a layer-style panel: take a flat shape and give it
a bevelled edge, a metal or jade gradient, an inner shadow, a gloss sweep and
a rim light, so it reads as an object rather than a coloured rectangle.

All of it is deterministic numpy and PIL - no model, no download, no network.
That matters here: the results are repeatable, they preserve the exact source
dimensions, and they run in milliseconds rather than minutes.

The method throughout is the standard one:

* the **alpha channel is a height field** once it is blurred, so the gradient
  of that blur gives a surface normal per pixel;
* lighting is Blinn-Phong against that normal - a diffuse term for the body of
  the bevel and a specular term for the highlight along the lit edge;
* colour comes from a **gradient map**: the luminance of each pixel indexes a
  256-entry ramp, which is how a green card becomes gold without touching its
  shape.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


# --------------------------------------------------------------- utilities

def _as_float(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Return (rgb 0..1, alpha 0..1) as float32 arrays."""

    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    return rgba[..., :3], rgba[..., 3]


def _to_image(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    out = np.empty(rgb.shape[:2] + (4,), dtype=np.float32)
    out[..., :3] = np.clip(rgb, 0.0, 1.0)
    out[..., 3] = np.clip(alpha, 0.0, 1.0)
    return Image.fromarray((out * 255.0 + 0.5).astype(np.uint8), "RGBA")


def _blur(array: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return array
    image = Image.fromarray((np.clip(array, 0, 1) * 255).astype(np.uint8), "L")
    blurred = image.filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(blurred, dtype=np.float32) / 255.0


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def ramp(stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    """Build a 256x3 colour lookup table from (position, rgb) stops."""

    stops = sorted(stops, key=lambda s: s[0])
    table = np.zeros((256, 3), dtype=np.float32)
    positions = [int(round(p * 255)) for p, _c in stops]
    colours = [np.array(c, dtype=np.float32) / 255.0 for _p, c in stops]
    for index in range(len(stops) - 1):
        a, b = positions[index], positions[index + 1]
        if b <= a:
            continue
        span = np.linspace(0.0, 1.0, b - a + 1, dtype=np.float32)[:, None]
        table[a : b + 1] = colours[index] * (1 - span) + colours[index + 1] * span
    table[: positions[0]] = colours[0]
    table[positions[-1] :] = colours[-1]
    return table


def gradient_map(rgb: np.ndarray, table: np.ndarray, amount: float = 1.0) -> np.ndarray:
    """Recolour by luminance through a ramp — a green card becomes gold."""

    index = np.clip(luminance(rgb) * 255.0, 0, 255).astype(np.uint8)
    mapped = table[index]
    return rgb * (1.0 - amount) + mapped * amount


# ------------------------------------------------------------------ shading

def surface_normals(alpha: np.ndarray, radius: float, depth: float) -> np.ndarray:
    """Treat a blurred alpha channel as a height field and differentiate it."""

    height = _blur(alpha, radius)
    gy, gx = np.gradient(height.astype(np.float32))
    normals = np.stack([-gx * depth, -gy * depth, np.ones_like(height)], axis=-1)
    length = np.linalg.norm(normals, axis=-1, keepdims=True)
    return normals / np.maximum(length, 1e-6)


def shade(
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    radius: float = 3.0,
    depth: float = 22.0,
    light=(-0.55, -0.65, 0.52),
    ambient: float = 0.62,
    diffuse: float = 0.55,
    specular: float = 0.85,
    shininess: float = 34.0,
    spec_tint=(1.0, 0.98, 0.9),
) -> np.ndarray:
    """Bevel and emboss: light the surface implied by the alpha channel."""

    normals = surface_normals(alpha, radius, depth)
    light_vector = np.array(light, dtype=np.float32)
    light_vector /= np.linalg.norm(light_vector)
    view = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    half = light_vector + view
    half /= np.linalg.norm(half)

    ndotl = np.clip((normals * light_vector).sum(axis=-1), 0.0, 1.0)
    ndoth = np.clip((normals * half).sum(axis=-1), 0.0, 1.0)
    lit = ambient + diffuse * ndotl
    highlight = specular * np.power(ndoth, shininess)

    tint = np.array(spec_tint, dtype=np.float32)
    return rgb * lit[..., None] + highlight[..., None] * tint


def inner_shadow(rgb: np.ndarray, alpha: np.ndarray, radius: float = 6.0,
                 strength: float = 0.55) -> np.ndarray:
    """Darken just inside the silhouette, which reads as thickness."""

    inside = np.clip(_blur(alpha, radius) - (1.0 - alpha), 0.0, 1.0)
    shade_mask = np.clip(1.0 - inside, 0.0, 1.0) * alpha
    return rgb * (1.0 - strength * shade_mask[..., None])


def inner_glow(rgb: np.ndarray, alpha: np.ndarray, colour, radius: float = 5.0,
               strength: float = 0.6) -> np.ndarray:
    edge = np.clip(alpha - _blur(alpha, radius), 0.0, 1.0) * alpha
    tint = np.array(colour, dtype=np.float32) / 255.0
    return rgb + edge[..., None] * tint * strength


def outer_glow(rgb: np.ndarray, alpha: np.ndarray, colour, radius: float = 9.0,
               strength: float = 0.9) -> tuple[np.ndarray, np.ndarray]:
    """A halo outside the silhouette. Returns new (rgb, alpha)."""

    halo = np.clip(_blur(alpha, radius) - alpha, 0.0, 1.0)
    tint = np.array(colour, dtype=np.float32) / 255.0
    glow_alpha = np.clip(alpha + halo * strength, 0.0, 1.0)
    blended = rgb * alpha[..., None] + tint * halo[..., None] * strength
    safe = np.maximum(glow_alpha, 1e-6)[..., None]
    return blended / safe, glow_alpha


def gloss(rgb: np.ndarray, alpha: np.ndarray, strength: float = 0.35,
          tilt: float = 0.55, position: float = 0.34, width: float = 0.20) -> np.ndarray:
    """A soft diagonal sheen across the upper part of the shape."""

    height, width_px = alpha.shape
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    xs = np.linspace(0.0, 1.0, width_px, dtype=np.float32)[None, :]
    band = ys + tilt * xs
    band = band / (1.0 + tilt)
    sweep = np.exp(-((band - position) ** 2) / max(width * width, 1e-6))
    return rgb + (sweep * alpha * strength)[..., None]


def detail_noise(rgb: np.ndarray, alpha: np.ndarray, strength: float = 0.04,
                 seed: int = 7) -> np.ndarray:
    """A little high-frequency grain so a flat fill does not look plastic."""

    rng = np.random.default_rng(seed)
    grain = rng.normal(0.0, 1.0, size=alpha.shape).astype(np.float32)
    grain = _blur(np.clip(grain * 0.5 + 0.5, 0, 1), 0.6) * 2.0 - 1.0
    return rgb + (grain * alpha * strength)[..., None]


def asanoha_pattern(shape: tuple[int, int], scale: float = 26.0,
                    strength: float = 0.10) -> np.ndarray:
    """A geometric lattice in the spirit of the hemp-leaf pattern.

    Built from interfering sine waves at three orientations, which gives a
    repeating triangular lattice without needing an asset file.
    """

    height, width = shape
    ys = np.arange(height, dtype=np.float32)[:, None]
    xs = np.arange(width, dtype=np.float32)[None, :]
    field = np.zeros(shape, dtype=np.float32)
    for angle in (0.0, np.pi / 3.0, 2.0 * np.pi / 3.0):
        projected = xs * np.cos(angle) + ys * np.sin(angle)
        field += np.cos(2.0 * np.pi * projected / scale)
    field = field / 3.0
    return np.abs(field) * strength


# ------------------------------------------------------------------ presets

RAMPS = {
    "gold": ramp([
        (0.00, (58, 34, 6)), (0.22, (132, 88, 22)), (0.45, (214, 168, 62)),
        (0.60, (255, 233, 158)), (0.74, (208, 156, 48)), (0.88, (150, 100, 26)),
        (1.00, (255, 248, 214)),
    ]),
    "jade": ramp([
        (0.00, (4, 32, 20)), (0.28, (14, 82, 52)), (0.52, (38, 148, 96)),
        (0.72, (120, 214, 158)), (1.00, (226, 255, 240)),
    ]),
    "silver": ramp([
        (0.00, (28, 32, 38)), (0.30, (96, 104, 116)), (0.55, (176, 186, 198)),
        (0.70, (240, 246, 252)), (0.85, (150, 160, 172)), (1.00, (255, 255, 255)),
    ]),
    "bronze": ramp([
        (0.00, (40, 18, 8)), (0.30, (104, 54, 24)), (0.58, (176, 106, 52)),
        (0.76, (226, 168, 106)), (1.00, (255, 226, 186)),
    ]),
    "emerald_glass": ramp([
        (0.00, (2, 26, 18)), (0.35, (10, 96, 66)), (0.62, (46, 178, 126)),
        (0.82, (150, 240, 200)), (1.00, (255, 255, 255)),
    ]),
}


PRESETS = {
    "Gold medallion": {
        "ramp": "gold", "ramp_amount": 0.92,
        "bevel_radius": 2.4, "bevel_depth": 30.0,
        "specular": 1.05, "shininess": 42.0,
        "inner_shadow": 0.42, "gloss": 0.30,
        "outer_glow": None, "pattern": 0.0, "noise": 0.03,
    },
    "Jade card": {
        "ramp": "jade", "ramp_amount": 0.85,
        "bevel_radius": 3.2, "bevel_depth": 20.0,
        "specular": 0.7, "shininess": 26.0,
        "inner_shadow": 0.40, "gloss": 0.26,
        "outer_glow": (120, 255, 170), "pattern": 0.09, "noise": 0.03,
    },
    "Polished silver": {
        "ramp": "silver", "ramp_amount": 0.95,
        "bevel_radius": 2.0, "bevel_depth": 34.0,
        "specular": 1.2, "shininess": 60.0,
        "inner_shadow": 0.35, "gloss": 0.34,
        "outer_glow": None, "pattern": 0.0, "noise": 0.02,
    },
    "Bronze relief": {
        "ramp": "bronze", "ramp_amount": 0.9,
        "bevel_radius": 3.0, "bevel_depth": 26.0,
        "specular": 0.8, "shininess": 30.0,
        "inner_shadow": 0.5, "gloss": 0.2,
        "outer_glow": None, "pattern": 0.06, "noise": 0.045,
    },
    "Emerald glass": {
        "ramp": "emerald_glass", "ramp_amount": 0.8,
        "bevel_radius": 4.0, "bevel_depth": 18.0,
        "specular": 1.15, "shininess": 70.0,
        "inner_shadow": 0.28, "gloss": 0.42,
        "outer_glow": (150, 255, 210), "pattern": 0.0, "noise": 0.015,
    },
    "Depth only (keep colour)": {
        "ramp": None, "ramp_amount": 0.0,
        "bevel_radius": 2.6, "bevel_depth": 24.0,
        "specular": 0.8, "shininess": 34.0,
        "inner_shadow": 0.40, "gloss": 0.24,
        "outer_glow": None, "pattern": 0.0, "noise": 0.02,
    },
}


def style_image(image: Image.Image, preset: str = "Gold medallion",
                strength: float = 1.0, **overrides) -> tuple[Image.Image, dict]:
    """Apply a material preset to a whole image, preserving its dimensions."""

    settings = dict(PRESETS.get(preset, PRESETS["Gold medallion"]))
    settings.update(overrides)
    rgb, alpha = _as_float(image)
    original_alpha = alpha.copy()

    table_name = settings.get("ramp")
    if table_name and settings.get("ramp_amount", 0) > 0:
        rgb = gradient_map(rgb, RAMPS[table_name], settings["ramp_amount"] * strength)

    pattern = settings.get("pattern", 0.0)
    if pattern > 0:
        rgb = rgb + (asanoha_pattern(alpha.shape, strength=pattern * strength) * alpha)[..., None]

    rgb = shade(
        rgb, alpha,
        radius=settings["bevel_radius"],
        depth=settings["bevel_depth"] * strength,
        specular=settings["specular"] * strength,
        shininess=settings["shininess"],
    )
    if settings.get("inner_shadow", 0) > 0:
        rgb = inner_shadow(rgb, alpha, strength=settings["inner_shadow"] * strength)
    if settings.get("gloss", 0) > 0:
        rgb = gloss(rgb, alpha, strength=settings["gloss"] * strength)
    if settings.get("noise", 0) > 0:
        rgb = detail_noise(rgb, alpha, strength=settings["noise"])

    glow_colour = settings.get("outer_glow")
    if glow_colour:
        rgb, alpha = outer_glow(rgb, alpha, glow_colour, strength=0.75 * strength)

    result = _to_image(rgb, alpha)
    return result, {
        "mode": "material_style",
        "preset": preset,
        "strength": round(strength, 3),
        "ramp": table_name,
        "dimensions": list(result.size),
        "alpha_grew": bool((alpha > original_alpha + 0.01).any()),
    }


def style_region(image: Image.Image, region, preset: str = "Gold medallion",
                 strength: float = 1.0, **overrides) -> tuple[Image.Image, dict]:
    """Apply a preset to one rectangle, leaving every other pixel untouched."""

    base = image.convert("RGBA")
    box = region.clipped(base.size)
    crop = base.crop((box.left, box.top, box.right, box.bottom))
    styled, meta = style_image(crop, preset, strength, **overrides)
    out = base.copy()
    out.paste(styled, (box.left, box.top))
    meta["region"] = box.as_list()
    meta["dimensions"] = list(out.size)
    return out, meta
