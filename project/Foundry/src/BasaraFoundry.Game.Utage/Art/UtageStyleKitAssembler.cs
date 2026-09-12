using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.Game.Utage.Art;

/// <summary>
/// Emits (candidateRgba, editMask01). Does not write ARC bytes.
/// Caller wires the result into <see cref="Arc.UtageSingleEntryXetGraft.BuildSibling"/>.
/// </summary>
public static class UtageStyleKitAssembler
{
    /// <summary>
    /// App boundary maps unique Strong / ExactLanguageVariant matches to 1.0f.
    /// Assembler never calls ReferenceMatcher.
    /// </summary>
    public const float ShDonorMinConfidence = 0.80f;

    public enum Tier
    {
        MockupBlocked = 0,
        StyleKitV0 = 1,
        ShPixelCrop = 2,
    }

    public sealed class StyleKitTextEdit
    {
        public int X { get; set; }
        public int Y { get; set; }
        public int BoxWidth { get; set; }
        public int BoxHeight { get; set; }
        public string Text { get; set; } = string.Empty;
        public byte[]? ShDonorRgba { get; set; }
        public int ShDonorWidth { get; set; }
        public int ShDonorHeight { get; set; }
        public float ShDonorMatcherConfidence { get; set; }
    }

    public sealed class Result
    {
        public required byte[] CandidateRgba { get; init; }
        public required byte[] Mask01 { get; init; }
        public int Width { get; init; }
        public int Height { get; init; }
        public Tier TierUsed { get; init; }
    }

    public static Result Assemble(
        ReadOnlySpan<byte> pristineRgba,
        int width,
        int height,
        IReadOnlyList<StyleKitTextEdit> edits,
        IStyleKitV0? styleKit,
        bool production = true)
    {
        if (width <= 0 || height <= 0)
            throw new ArgumentOutOfRangeException(nameof(width));
        if (pristineRgba.Length != checked(width * height * 4))
            throw new ArgumentException("pristineRgba length != width*height*4", nameof(pristineRgba));
        ArgumentNullException.ThrowIfNull(edits);

        var candidate = new byte[pristineRgba.Length];
        pristineRgba.CopyTo(candidate);
        var mask01 = new byte[width * height];
        var tier = Tier.MockupBlocked;

        foreach (var edit in edits)
        {
            if (edit.ShDonorRgba is { } donor
                && donor.Length == checked(edit.ShDonorWidth * edit.ShDonorHeight * 4)
                && edit.ShDonorMatcherConfidence >= ShDonorMinConfidence)
            {
                BlitScaled(
                    donor,
                    edit.ShDonorWidth,
                    edit.ShDonorHeight,
                    candidate,
                    width,
                    height,
                    mask01,
                    edit.X,
                    edit.Y,
                    edit.BoxWidth,
                    edit.BoxHeight);
                tier = Higher(tier, Tier.ShPixelCrop);
                continue;
            }

            if (styleKit is not null)
            {
                RenderTextLines(edit, styleKit, candidate, width, height, mask01);
                tier = Higher(tier, Tier.StyleKitV0);
                continue;
            }

            if (production)
            {
                throw new InvalidOperationException(
                    "Production requires an SH donor (gated by the App via ReferenceMatcher) or IStyleKitV0. " +
                    "Desktop mockup is blocked.");
            }

            tier = Higher(tier, Tier.MockupBlocked);
        }

        // Exact-delta mask: 1 wherever candidate differs from pristine.
        // Satisfies outside-mask identity; graft expands to 4x4 via MaskToBlockSet.
        for (var i = 0; i < mask01.Length; i++)
        {
            var p = i * 4;
            var same =
                candidate[p] == pristineRgba[p]
                && candidate[p + 1] == pristineRgba[p + 1]
                && candidate[p + 2] == pristineRgba[p + 2]
                && candidate[p + 3] == pristineRgba[p + 3];
            mask01[i] = same ? (byte)0 : (byte)1;
        }

        var delta = UtageBc3BlockGraft.CountOutsideMaskDeltas(
            pristineRgba, candidate, mask01, width, height);
        if (delta != 0)
            throw new InvalidOperationException($"Assembler produced {delta} outside-mask deltas.");

        return new Result
        {
            CandidateRgba = candidate,
            Mask01 = mask01,
            Width = width,
            Height = height,
            TierUsed = tier,
        };
    }

    private static Tier Higher(Tier a, Tier b) =>
        (int)a >= (int)b ? a : b;

    private static void RenderTextLines(
        StyleKitTextEdit edit,
        IStyleKitV0 kit,
        byte[] dstRgba,
        int dstW,
        int dstH,
        byte[] dstMask)
    {
        var lines = edit.Text.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n');
        var lineCount = Math.Max(1, lines.Length);
        var lineH = Math.Max(1, edit.BoxHeight / lineCount);

        for (var li = 0; li < lines.Length; li++)
        {
            var line = lines[li];
            if (line.Length == 0)
                continue;

            var glyphs = new List<(int W, int H, byte[] Cov)>(line.Length);
            foreach (var c in line)
                glyphs.Add(kit.RasterizeGlyph(c));

            var maxH = 1;
            var totalNaturalW = 0;
            foreach (var g in glyphs)
            {
                if (g.H > maxH)
                    maxH = g.H;
                totalNaturalW += g.W + 1;
            }

            if (totalNaturalW <= 0)
                continue;

            // Fit line height first, then shrink if width overflows.
            var scale = (float)lineH / maxH;
            var scaledTotalW = (int)(totalNaturalW * scale);
            if (scaledTotalW > edit.BoxWidth)
                scale = (float)edit.BoxWidth / totalNaturalW;

            var finalW = Math.Max(1, (int)(totalNaturalW * scale));
            var cursorX = edit.X;
            if (finalW < edit.BoxWidth)
                cursorX += (edit.BoxWidth - finalW) / 2;
            var lineY = edit.Y + li * lineH;

            foreach (var g in glyphs)
            {
                var gw = Math.Max(1, (int)(g.W * scale));
                var gh = Math.Max(1, (int)(g.H * scale));
                var scaled = ScaleCoverage(g.Cov, g.W, g.H, gw, gh);
                var gy = lineY + Math.Max(0, (lineH - gh) / 2);

                StyleKitV0Compositor.Composite(
                    scaled, gw, gh,
                    dstRgba, dstW, dstH, dstMask,
                    cursorX, gy, kit);

                cursorX += gw + Math.Max(1, (int)scale);
            }
        }
    }

    private static void BlitScaled(
        ReadOnlySpan<byte> srcRgba,
        int srcW,
        int srcH,
        byte[] dstRgba,
        int dstW,
        int dstH,
        byte[] dstMask,
        int dstX,
        int dstY,
        int boxW,
        int boxH)
    {
        if (srcW <= 0 || srcH <= 0 || boxW <= 0 || boxH <= 0)
            return;

        var scale = Math.Min((float)boxW / srcW, (float)boxH / srcH);
        var w = Math.Max(1, (int)(srcW * scale));
        var h = Math.Max(1, (int)(srcH * scale));
        var offX = dstX + Math.Max(0, (boxW - w) / 2);
        var offY = dstY + Math.Max(0, (boxH - h) / 2);

        for (var y = 0; y < h; y++)
        {
            for (var x = 0; x < w; x++)
            {
                var sx = Math.Min((int)(x / scale), srcW - 1);
                var sy = Math.Min((int)(y / scale), srcH - 1);
                var sp = (sy * srcW + sx) * 4;
                if (srcRgba[sp + 3] == 0)
                    continue;

                var dx = offX + x;
                var dy = offY + y;
                if ((uint)dx >= (uint)dstW || (uint)dy >= (uint)dstH)
                    continue;

                var dp = (dy * dstW + dx) * 4;
                dstRgba[dp] = srcRgba[sp];
                dstRgba[dp + 1] = srcRgba[sp + 1];
                dstRgba[dp + 2] = srcRgba[sp + 2];
                dstRgba[dp + 3] = srcRgba[sp + 3];
                dstMask[dy * dstW + dx] = 1;
            }
        }
    }

    private static byte[] ScaleCoverage(ReadOnlySpan<byte> src, int sw, int sh, int dw, int dh)
    {
        var dst = new byte[dw * dh];
        for (var y = 0; y < dh; y++)
        {
            for (var x = 0; x < dw; x++)
            {
                var sx = Math.Min((int)((float)x / dw * sw), sw - 1);
                var sy = Math.Min((int)((float)y / dh * sh), sh - 1);
                dst[y * dw + x] = src[sy * sw + sx];
            }
        }

        return dst;
    }
}
