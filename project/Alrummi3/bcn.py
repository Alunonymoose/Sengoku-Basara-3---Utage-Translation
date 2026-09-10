"""Block compression for BC1 (DXT1) and BC3 (DXT5), done properly.

The first encoder in this project picked its two endpoint colours as the
brightest and darkest pixel in the block by luma.  That is quick and it is
wrong: the best pair of endpoints is the pair that spans the block's dominant
axis in colour space, which is rarely the brightest and darkest.  On lettering
with a coloured outline the difference is visible as muddied edges.

This module does what a real encoder does:

1. fit a line through the block's colours along their principal axis;
2. quantise its ends to RGB565 and assign each pixel the nearest of the four
   palette entries;
3. re-solve the endpoints by least squares for the indices just chosen, and
   repeat - each pass lowers the error;
4. for BC1, also try the three-colour punch-through mode when the block has
   transparent pixels, because BC1 has only one bit of alpha.

Everything is vectorised over all blocks at once with numpy, which matters:
the pure-Python version took about four seconds on a 1024x1024 texture.

Correctness is not asserted here - `_bcn_validate.py` round-trips real game
textures through this encoder and measures the error against the originals.
"""

from __future__ import annotations

import numpy as np

# A pixel this transparent is treated as a hole in BC1's one-bit alpha.
BC1_ALPHA_CUTOFF = 128
REFINE_PASSES = 3


# ---------------------------------------------------------------- helpers

def _to_565(color: np.ndarray) -> np.ndarray:
    """Quantise float RGB in 0..255 to a packed RGB565 integer."""

    c = np.clip(np.rint(color), 0, 255).astype(np.int32)
    r = (c[..., 0] * 31 + 127) // 255
    g = (c[..., 1] * 63 + 127) // 255
    b = (c[..., 2] * 31 + 127) // 255
    return (r << 11) | (g << 5) | b


def _from_565(packed: np.ndarray) -> np.ndarray:
    """Expand RGB565 back to the 0..255 values the hardware actually uses."""

    r = (packed >> 11) & 0x1F
    g = (packed >> 5) & 0x3F
    b = packed & 0x1F
    out = np.empty(packed.shape + (3,), dtype=np.float32)
    out[..., 0] = (r << 3) | (r >> 2)
    out[..., 1] = (g << 2) | (g >> 4)
    out[..., 2] = (b << 3) | (b >> 2)
    return out


def _principal_axis(colors: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean and dominant direction of each block's colour cloud.

    ``colors`` is (N, 16, 3); ``weights`` is (N, 16) and is zero for pixels
    that must not influence the fit, such as fully transparent ones.
    """

    total = np.maximum(weights.sum(axis=1, keepdims=True), 1e-6)
    mean = (colors * weights[..., None]).sum(axis=1) / total
    centered = (colors - mean[:, None, :]) * weights[..., None]
    # Batched covariance: (N, 3, 3)
    cov = np.einsum("nij,nik->njk", centered, centered)
    # Power iteration finds the dominant eigenvector without a full solve.
    axis = np.array([0.9, 1.0, 0.7], dtype=np.float32)
    axis = np.broadcast_to(axis, (colors.shape[0], 3)).copy()
    for _ in range(8):
        axis = np.einsum("nij,nj->ni", cov, axis)
        norm = np.linalg.norm(axis, axis=1, keepdims=True)
        flat = norm[:, 0] < 1e-9
        axis = np.where(flat[:, None], np.array([1.0, 1.0, 1.0], np.float32), axis / np.maximum(norm, 1e-9))
    return mean.astype(np.float32), axis.astype(np.float32)


def _least_squares_endpoints(
    colors: np.ndarray,
    weights: np.ndarray,
    alpha_of_c0: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Re-solve both endpoints for the indices already chosen.

    Each pixel is reconstructed as ``a*c0 + (1-a)*c1``, so with the ``a`` for
    every pixel known this is an ordinary two-unknown least-squares problem.
    """

    a = alpha_of_c0 * weights
    b = (1.0 - alpha_of_c0) * weights
    aa = (a * alpha_of_c0).sum(axis=1)
    ab = (a * (1.0 - alpha_of_c0)).sum(axis=1)
    bb = (b * (1.0 - alpha_of_c0)).sum(axis=1)
    ax = np.einsum("ni,nic->nc", a, colors)
    bx = np.einsum("ni,nic->nc", b, colors)
    det = aa * bb - ab * ab
    safe = np.abs(det) > 1e-6
    inv = np.where(safe, 1.0 / np.where(safe, det, 1.0), 0.0)
    c0 = (bb[:, None] * ax - ab[:, None] * bx) * inv[:, None]
    c1 = (aa[:, None] * bx - ab[:, None] * ax) * inv[:, None]
    return c0, c1, safe


def _blocks_from_image(rgba: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Cut an RGBA image into 4x4 blocks, padding by edge replication."""

    height, width = rgba.shape[:2]
    bw, bh = (width + 3) // 4, (height + 3) // 4
    padded = np.zeros((bh * 4, bw * 4, 4), dtype=rgba.dtype)
    padded[:height, :width] = rgba
    if bh * 4 > height:
        padded[height:, :width] = rgba[height - 1:height]
    if bw * 4 > width:
        padded[:, width:] = padded[:, width - 1:width]
    blocks = (
        padded.reshape(bh, 4, bw, 4, 4)
        .transpose(0, 2, 1, 3, 4)
        .reshape(bh * bw, 16, 4)
    )
    return blocks, bw, bh


# ------------------------------------------------------------------ colour

def _block_error(colors, weights, q0, q1, three_color) -> np.ndarray:
    """Sum of squared error a candidate endpoint pair would actually cost."""

    p0, p1 = _from_565(q0), _from_565(q1)
    pal = _palette(p0, p1, three_color)
    distance = ((colors[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(axis=3)
    if three_color.any():
        # Index 3 is transparent black in three-colour mode; it must not be
        # offered to opaque pixels when scoring.
        distance[:, :, 3] = np.where(three_color[:, None], np.inf, distance[:, :, 3])
    best = distance.min(axis=2)
    return (best * weights).sum(axis=1)


def _refine(colors, weights, c0, c1, three_color, passes=REFINE_PASSES):
    for _ in range(passes):
        q0, q1 = _to_565(c0), _to_565(c1)
        p0, p1 = _from_565(q0), _from_565(q1)
        alpha = _assign_alpha(colors, weights, p0, p1, three_color)
        n0, n1, ok = _least_squares_endpoints(colors, weights, alpha)
        c0 = np.where(ok[:, None], n0, c0)
        c1 = np.where(ok[:, None], n1, c1)
    return c0, c1


def _fit_color_pair(
    colors: np.ndarray,
    weights: np.ndarray,
    three_color: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Endpoint pair per block, chosen from several candidates by real error.

    Insetting the ends of the fitted line helps most blocks and hurts a few
    high-contrast ones, so rather than guess, every candidate is scored by the
    error it would actually produce and the winner is kept per block.
    """

    mean, axis = _principal_axis(colors, weights)
    projection = np.einsum("nic,nc->ni", colors - mean[:, None, :], axis)
    masked = np.where(weights > 0, projection, np.nan)
    with np.errstate(invalid="ignore"):
        lo = np.nan_to_num(np.nanmin(masked, axis=1))
        hi = np.nan_to_num(np.nanmax(masked, axis=1))

    span = (hi - lo) * (1.0 / 16.0)
    raw0 = mean + axis * hi[:, None]
    raw1 = mean + axis * lo[:, None]
    inset0 = mean + axis * (hi - span)[:, None]
    inset1 = mean + axis * (lo + span)[:, None]

    candidates = [
        (raw0, raw1),
        (inset0, inset1),
        _refine(colors, weights, raw0.copy(), raw1.copy(), three_color),
        _refine(colors, weights, inset0.copy(), inset1.copy(), three_color),
    ]

    best0 = best1 = None
    best_error = None
    for c0, c1 in candidates:
        q0, q1 = _to_565(c0), _to_565(c1)
        error = _block_error(colors, weights, q0, q1, three_color)
        if best_error is None:
            best0, best1, best_error = c0, c1, error
            continue
        better = error < best_error
        best0 = np.where(better[:, None], c0, best0)
        best1 = np.where(better[:, None], c1, best1)
        best_error = np.where(better, error, best_error)
    return best0, best1


def _palette(p0: np.ndarray, p1: np.ndarray, three_color: np.ndarray) -> np.ndarray:
    """The four (or three) colours the hardware will interpolate."""

    out = np.empty((p0.shape[0], 4, 3), dtype=np.float32)
    out[:, 0] = p0
    out[:, 1] = p1
    four = (2.0 * p0 + p1) / 3.0
    fourb = (p0 + 2.0 * p1) / 3.0
    half = (p0 + p1) / 2.0
    out[:, 2] = np.where(three_color[:, None], half, four)
    out[:, 3] = np.where(three_color[:, None], 0.0, fourb)
    return out


def _assign_alpha(colors, weights, p0, p1, three_color) -> np.ndarray:
    """The c0 weight implied by the nearest palette entry, for refinement."""

    pal = _palette(p0, p1, three_color)
    distance = ((colors[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(axis=3)
    distance = np.where(weights[..., None] > 0, distance, 0.0)
    choice = distance.argmin(axis=2)
    four_weights = np.array([1.0, 0.0, 2.0 / 3.0, 1.0 / 3.0], dtype=np.float32)
    three_weights = np.array([1.0, 0.0, 0.5, 0.0], dtype=np.float32)
    table = np.where(three_color[:, None], three_weights, four_weights)
    return np.take_along_axis(table, choice, axis=1).astype(np.float32)


def _color_indices(colors, alphas, q0, q1, three_color) -> np.ndarray:
    p0, p1 = _from_565(q0), _from_565(q1)
    pal = _palette(p0, p1, three_color)
    distance = ((colors[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(axis=3)
    if three_color.any():
        # In three-colour mode index 3 is transparent black, so it must only be
        # chosen for pixels that really are transparent.  In four-colour mode
        # index 3 is an ordinary interpolated colour and must stay available -
        # masking it there silently collapsed a quarter of the palette.
        transparent = alphas < BC1_ALPHA_CUTOFF
        three = three_color[:, None]
        distance[:, :, 3] = np.where(
            three,
            np.where(transparent, -1.0, np.inf),
            distance[:, :, 3],
        )
    return distance.argmin(axis=2).astype(np.uint32)


# -------------------------------------------------------------------- BC1

def encode_bc1(rgba: np.ndarray) -> bytes:
    """Encode an RGBA image to BC1/DXT1 blocks."""

    blocks, bw, bh = _blocks_from_image(rgba)
    colors = blocks[:, :, :3].astype(np.float32)
    alphas = blocks[:, :, 3].astype(np.float32)
    opaque = alphas >= BC1_ALPHA_CUTOFF
    # A block with any transparent pixel must use the punch-through mode.
    three_color = ~opaque.all(axis=1)
    weights = opaque.astype(np.float32)
    # A block that is entirely transparent still needs a colour fit; fall back
    # to weighting every pixel so the endpoints are defined.
    empty = weights.sum(axis=1) < 1.0
    weights = np.where(empty[:, None], 1.0, weights)

    c0, c1 = _fit_color_pair(colors, weights, three_color)
    q0, q1 = _to_565(c0), _to_565(c1)

    # Mode is chosen by the ordering of the two endpoints: c0 > c1 means the
    # four-colour mode, c0 <= c1 the three-colour punch-through mode.
    need_swap = np.where(three_color, q0 > q1, q0 < q1)
    q0n = np.where(need_swap, q1, q0)
    q1n = np.where(need_swap, q0, q1)
    q0, q1 = q0n, q1n
    equal = q0 == q1
    # Equal endpoints read as three-colour mode; nudge when we wanted four.
    fix = equal & ~three_color
    q0 = np.where(fix & (q0 < 0xFFFF), q0 + 1, q0)
    q1 = np.where(fix & (q0 == 0xFFFF) & (q1 > 0), q1 - 1, q1)

    indices = _color_indices(colors, alphas, q0, q1, three_color)
    packed = np.zeros(blocks.shape[0], dtype=np.uint32)
    for i in range(16):
        packed |= (indices[:, i] & 0x3) << (2 * i)

    out = np.empty((blocks.shape[0], 8), dtype=np.uint8)
    out[:, 0] = q0 & 0xFF
    out[:, 1] = (q0 >> 8) & 0xFF
    out[:, 2] = q1 & 0xFF
    out[:, 3] = (q1 >> 8) & 0xFF
    out[:, 4] = packed & 0xFF
    out[:, 5] = (packed >> 8) & 0xFF
    out[:, 6] = (packed >> 16) & 0xFF
    out[:, 7] = (packed >> 24) & 0xFF
    return out.tobytes()


# -------------------------------------------------------------------- BC3

def _alpha_palette(a0: np.ndarray, a1: np.ndarray) -> np.ndarray:
    pal = np.empty((a0.shape[0], 8), dtype=np.float32)
    pal[:, 0] = a0
    pal[:, 1] = a1
    for k in range(2, 8):
        pal[:, k] = ((8 - k) * a0 + (k - 1) * a1) / 7.0
    return pal


# Weight of endpoint a0 for each of the eight indices, used when re-solving.
_ALPHA_WEIGHTS = np.array(
    [1.0, 0.0] + [(8 - k) / 7.0 for k in range(2, 8)], dtype=np.float32
)


def _encode_alpha_block(alphas: np.ndarray) -> np.ndarray:
    """The eight-byte interpolated-alpha half of a BC3 block.

    The endpoints are not simply the block's minimum and maximum.  If the
    original block never used its own endpoint indices, min and max are
    interpolated values and re-deriving from them narrows the range every
    round trip.  So the endpoints are re-solved by least squares against the
    indices they produce, exactly as the colour endpoints are.
    """

    a0 = alphas.max(axis=1).astype(np.float32)
    a1 = alphas.min(axis=1).astype(np.float32)

    def indices_for(x0, x1):
        pal = _alpha_palette(x0, x1)
        return np.abs(alphas[:, :, None] - pal[:, None, :]).argmin(axis=2)

    for _ in range(3):
        choice = indices_for(a0, a1)
        w0 = _ALPHA_WEIGHTS[choice]
        w1 = 1.0 - w0
        aa = (w0 * w0).sum(axis=1)
        ab = (w0 * w1).sum(axis=1)
        bb = (w1 * w1).sum(axis=1)
        ax = (w0 * alphas).sum(axis=1)
        bx = (w1 * alphas).sum(axis=1)
        det = aa * bb - ab * ab
        ok = np.abs(det) > 1e-6
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        n0 = (bb * ax - ab * bx) * inv
        n1 = (aa * bx - ab * ax) * inv
        a0 = np.where(ok, np.clip(n0, 0, 255), a0)
        a1 = np.where(ok, np.clip(n1, 0, 255), a1)

    # Least squares helps a fresh image but hurts a round trip, where the
    # original endpoints usually ARE the block's max and min.  Score both and
    # keep whichever reproduces the alpha more closely, per block.
    raw0 = alphas.max(axis=1).astype(np.float32)
    raw1 = alphas.min(axis=1).astype(np.float32)

    def alpha_error(x0, x1):
        pal = _alpha_palette(x0, x1)
        return np.abs(alphas[:, :, None] - pal[:, None, :]).min(axis=2).sum(axis=1)

    def alpha_worst(x0, x1):
        pal = _alpha_palette(x0, x1)
        return np.abs(alphas[:, :, None] - pal[:, None, :]).min(axis=2).max(axis=1)

    # Preserving alpha exactly matters more than the average: an alpha of 0
    # drifting to 18 turns an invisible pixel visible and drags its meaningless
    # RGB on screen.  So a candidate only wins if it is better on the worst
    # pixel as well as on the total.
    raw_total, fit_total = alpha_error(raw0, raw1), alpha_error(a0, a1)
    raw_worst, fit_worst = alpha_worst(raw0, raw1), alpha_worst(a0, a1)
    keep_raw = (raw_total <= fit_total) | (raw_worst < fit_worst)
    a0 = np.where(keep_raw, raw0, a0)
    a1 = np.where(keep_raw, raw1, a1)

    a0i = np.clip(np.rint(a0), 0, 255).astype(np.int32)
    a1i = np.clip(np.rint(a1), 0, 255).astype(np.int32)
    # The eight-value interpolated mode requires a0 > a1; equal endpoints would
    # select the six-value mode, whose indices 6 and 7 mean 0 and 255.
    swap = a0i < a1i
    a0i, a1i = np.where(swap, a1i, a0i), np.where(swap, a0i, a1i)
    equal = a0i == a1i
    a1i = np.where(equal & (a0i > 0), a0i - 1, a1i)
    a0i = np.where(equal & (a0i == 0), 1, a0i)

    choice = indices_for(a0i.astype(np.float32), a1i.astype(np.float32)).astype(np.uint64)
    bits = np.zeros(alphas.shape[0], dtype=np.uint64)
    for i in range(16):
        bits |= (choice[:, i] & np.uint64(7)) << np.uint64(3 * i)
    out = np.empty((alphas.shape[0], 8), dtype=np.uint8)
    out[:, 0] = a0i
    out[:, 1] = a1i
    for byte in range(6):
        out[:, 2 + byte] = (bits >> np.uint64(8 * byte)) & np.uint64(0xFF)
    return out


def encode_bc3(rgba: np.ndarray) -> bytes:
    """Encode an RGBA image to BC3/DXT5 blocks."""

    blocks, bw, bh = _blocks_from_image(rgba)
    colors = blocks[:, :, :3].astype(np.float32)
    alphas = blocks[:, :, 3].astype(np.float32)
    # BC3 carries full alpha separately, so every pixel informs the colour fit
    # except ones that are invisible anyway.
    weights = (alphas >= 8).astype(np.float32)
    empty = weights.sum(axis=1) < 1.0
    weights = np.where(empty[:, None], 1.0, weights)
    three_color = np.zeros(blocks.shape[0], dtype=bool)

    c0, c1 = _fit_color_pair(colors, weights, three_color)
    q0, q1 = _to_565(c0), _to_565(c1)
    swap = q0 < q1
    q0n = np.where(swap, q1, q0)
    q1n = np.where(swap, q0, q1)
    q0, q1 = q0n, q1n
    equal = q0 == q1
    q0 = np.where(equal & (q0 < 0xFFFF), q0 + 1, q0)
    q1 = np.where(equal & (q0 == 0xFFFF) & (q1 > 0), q1 - 1, q1)

    indices = _color_indices(colors, alphas, q0, q1, three_color)
    packed = np.zeros(blocks.shape[0], dtype=np.uint32)
    for i in range(16):
        packed |= (indices[:, i] & 0x3) << (2 * i)

    alpha_half = _encode_alpha_block(alphas)
    out = np.empty((blocks.shape[0], 16), dtype=np.uint8)
    out[:, :8] = alpha_half
    out[:, 8] = q0 & 0xFF
    out[:, 9] = (q0 >> 8) & 0xFF
    out[:, 10] = q1 & 0xFF
    out[:, 11] = (q1 >> 8) & 0xFF
    out[:, 12] = packed & 0xFF
    out[:, 13] = (packed >> 8) & 0xFF
    out[:, 14] = (packed >> 16) & 0xFF
    out[:, 15] = (packed >> 24) & 0xFF
    return out.tobytes()


def encode(rgba: np.ndarray, fourcc: str) -> bytes:
    if fourcc == "DXT1":
        return encode_bc1(rgba)
    if fourcc == "DXT5":
        return encode_bc3(rgba)
    raise ValueError(f"no encoder for {fourcc}")
