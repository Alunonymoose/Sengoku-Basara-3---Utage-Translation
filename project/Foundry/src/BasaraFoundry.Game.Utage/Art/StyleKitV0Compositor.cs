namespace BasaraFoundry.Game.Utage.Art;

/// <summary>
/// Real pixel compositor for StyleKitV0. Not Capcom-certified metal-jade.
/// Stacks stroke dilation, vertical fill gradient, and simple edge bevels.
/// </summary>
public static class StyleKitV0Compositor
{
    /// <summary>
    /// Composite one glyph into dstRgba / dstMask01 at (dstX, dstY).
    /// Writes 1 into dstMask01 wherever any glyph pixel (body, stroke, bevel) lands.
    /// </summary>
    public static void Composite(
        ReadOnlySpan<byte> coverage,
        int cw,
        int ch,
        Span<byte> dstRgba,
        int dstW,
        int dstH,
        Span<byte> dstMask01,
        int dstX,
        int dstY,
        IStyleKitV0 kit)
    {
        if (coverage.Length != cw * ch)
            throw new ArgumentException("coverage length != cw*ch", nameof(coverage));

        var strokeWidth = Math.Max(0, kit.StrokeWidth);
        var dilated = new byte[cw * ch];
        for (var y = 0; y < ch; y++)
        {
            for (var x = 0; x < cw; x++)
            {
                byte hit = 0;
                for (var dy = -strokeWidth; dy <= strokeWidth && hit == 0; dy++)
                {
                    for (var dx = -strokeWidth; dx <= strokeWidth && hit == 0; dx++)
                    {
                        var nx = x + dx;
                        var ny = y + dy;
                        if ((uint)nx >= (uint)cw || (uint)ny >= (uint)ch)
                            continue;
                        if (coverage[ny * cw + nx] > 0)
                            hit = 1;
                    }
                }

                dilated[y * cw + x] = hit;
            }
        }

        for (var y = 0; y < ch; y++)
        {
            var t = ch <= 1 ? 0f : (float)y / (ch - 1);
            var fr = Lerp(kit.FillTop.R, kit.FillBottom.R, t);
            var fg = Lerp(kit.FillTop.G, kit.FillBottom.G, t);
            var fb = Lerp(kit.FillTop.B, kit.FillBottom.B, t);

            for (var x = 0; x < cw; x++)
            {
                var i = y * cw + x;
                if (dilated[i] == 0)
                    continue;

                byte r, g, b;
                if (coverage[i] > 0)
                {
                    if (IsInnerLowerRight(coverage, cw, ch, x, y))
                        (r, g, b) = kit.BevelLo;
                    else
                        (r, g, b) = (fr, fg, fb);
                }
                else if (IsUpperLeftOuter(dilated, coverage, cw, ch, x, y))
                {
                    (r, g, b) = kit.BevelHi;
                }
                else
                {
                    (r, g, b) = kit.Stroke;
                }

                var dx = dstX + x;
                var dy = dstY + y;
                if ((uint)dx >= (uint)dstW || (uint)dy >= (uint)dstH)
                    continue;

                var di = (dy * dstW + dx) * 4;
                dstRgba[di] = r;
                dstRgba[di + 1] = g;
                dstRgba[di + 2] = b;
                dstRgba[di + 3] = 255;
                dstMask01[dy * dstW + dx] = 1;
            }
        }
    }

    private static byte Lerp(byte a, byte b, float t) =>
        (byte)(a + (b - a) * t);

    private static bool IsUpperLeftOuter(
        ReadOnlySpan<byte> dilated,
        ReadOnlySpan<byte> coverage,
        int w,
        int h,
        int x,
        int y)
    {
        var i = y * w + x;
        if (dilated[i] == 0 || coverage[i] > 0)
            return false;

        var up = y == 0 || dilated[(y - 1) * w + x] == 0;
        var left = x == 0 || dilated[y * w + (x - 1)] == 0;
        var upLeft = x == 0 || y == 0 || dilated[(y - 1) * w + (x - 1)] == 0;
        return up || left || upLeft;
    }

    private static bool IsInnerLowerRight(ReadOnlySpan<byte> coverage, int w, int h, int x, int y)
    {
        if (coverage[y * w + x] == 0)
            return false;

        var down = y == h - 1 || coverage[(y + 1) * w + x] == 0;
        var right = x == w - 1 || coverage[y * w + (x + 1)] == 0;
        return down || right;
    }
}
