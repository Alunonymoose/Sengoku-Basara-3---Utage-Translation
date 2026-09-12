using BCnEncoder.Encoder;
using BCnEncoder.Shared;

namespace BasaraFoundry.Game.Utage.Xet;

public sealed record Bc3GraftReport(
    int BlocksTotal,
    int BlocksReplaced,
    int MaskPixels,
    int OutsideMaskPixelDelta,
    int OutsideEffectiveBlockPixelDelta,
    int CompressionCollateralPixels,
    IReadOnlyList<(int Bx, int By)> BlockCoords,
    bool Ok,
    IReadOnlyList<string> Notes);

public sealed record Bc3GraftResult(
    byte[] XetBytes,
    byte[] GraftedPayload,
    Bc3GraftReport Report,
    XetDecodedImage? VerificationDecode);

/// <summary>
/// Production BC3 writer for Utage XET.
/// Starts from pristine compressed artwork, requires candidate equality outside
/// the exact edit mask, expands only to intersecting 4x4 BC3 blocks, preserves
/// all untouched compressed blocks byte-for-byte, then verifies the final decode.
/// </summary>
public static class UtageBc3BlockGraft
{
    public const int BlockBytes = 16;

    public static IReadOnlyList<(int Bx, int By)> MaskToBlockSet(ReadOnlySpan<byte> mask01, int width, int height)
    {
        if (mask01.Length != checked(width * height))
            throw new ArgumentException("Mask length must equal width*height (one byte per pixel).", nameof(mask01));

        var set = new SortedSet<(int, int)>();
        for (var y = 0; y < height; y++)
            for (var x = 0; x < width; x++)
                if (mask01[y * width + x] != 0)
                    set.Add((x / 4, y / 4));

        var bw = Math.Max(1, (width + 3) / 4);
        var bh = Math.Max(1, (height + 3) / 4);
        return set.Where(p => p.Item1 >= 0 && p.Item2 >= 0 && p.Item1 < bw && p.Item2 < bh).ToArray();
    }

    public static int CountOutsideMaskDeltas(ReadOnlySpan<byte> baseRgba, ReadOnlySpan<byte> candidateRgba, ReadOnlySpan<byte> mask01, int width, int height)
    {
        var pixels = checked(width * height);
        if (baseRgba.Length != pixels * 4 || candidateRgba.Length != pixels * 4 || mask01.Length != pixels)
            throw new ArgumentException("RGBA/mask dimensions disagree.");

        var delta = 0;
        for (var i = 0; i < pixels; i++)
        {
            if (mask01[i] != 0) continue;
            if (PixelDiffers(baseRgba, candidateRgba, i)) delta++;
        }
        return delta;
    }

    public static Bc3GraftResult GraftTopLevel(ReadOnlySpan<byte> pristineXet, ReadOnlySpan<byte> candidateRgba, ReadOnlySpan<byte> editMask01)
    {
        var info = UtageXetReader.ReadInfo(pristineXet);
        UtageXetCodec.RequireEncodingCapability(info);

        var expectedRgba = checked(info.Width * info.Height * 4);
        if (candidateRgba.Length != expectedRgba)
            throw new ArgumentException($"RGBA candidate contains {candidateRgba.Length} bytes; {info.Width}x{info.Height} requires {expectedRgba}.", nameof(candidateRgba));
        if (editMask01.Length != info.Width * info.Height)
            throw new ArgumentException($"Edit mask contains {editMask01.Length} pixels; expected {info.Width * info.Height}.", nameof(editMask01));

        var topLevelBytes = info.TopLevelSizeBytes ?? throw new NotSupportedException("XET encoded byte size is unknown.");
        var expectedEnd = checked(info.TextureOffset + topLevelBytes);
        if (info.MipCount > 1 || pristineXet.Length != expectedEnd)
            throw new NotSupportedException("Block-graft v0.1 is single-level only. Refuse multi-mip or trailing payload XETs.");

        var notes = new List<string>();
        var baseDecode = UtageXetCodec.DecodeTopLevel(pristineXet);
        var outsideDelta = CountOutsideMaskDeltas(baseDecode.Rgba, candidateRgba, editMask01, info.Width, info.Height);
        if (outsideDelta != 0)
        {
            notes.Add($"REJECT: {outsideDelta} pixels outside edit mask differ from pristine decode.");
            return Failure(info, CountMask(editMask01), outsideDelta, Array.Empty<(int, int)>(), notes);
        }
        notes.Add("candidate pixel-identical to pristine decode outside exact edit mask");

        var blocks = MaskToBlockSet(editMask01, info.Width, info.Height);
        if (blocks.Count == 0)
        {
            notes.Add("edit mask is empty — nothing to graft");
            return Failure(info, 0, 0, blocks, notes);
        }

        var fullEncoded = EncodeFullBc3(candidateRgba, info.Width, info.Height);
        if (fullEncoded.Length != topLevelBytes)
            throw new InvalidDataException($"BC3 encoder returned {fullEncoded.Length} bytes; XET requires {topLevelBytes}.");

        var pristinePayload = pristineXet.Slice(info.TextureOffset, topLevelBytes).ToArray();
        var grafted = (byte[])pristinePayload.Clone();
        var bw = Math.Max(1, (info.Width + 3) / 4);

        foreach (var (bx, by) in blocks)
        {
            var start = (by * bw + bx) * BlockBytes;
            fullEncoded.AsSpan(start, BlockBytes).CopyTo(grafted.AsSpan(start, BlockBytes));
        }

        var touched = blocks.Select(p => p.By * bw + p.Bx).ToHashSet();
        var totalBlocks = BlockCount(info.Width, info.Height);
        for (var i = 0; i < totalBlocks; i++)
        {
            if (touched.Contains(i)) continue;
            var start = i * BlockBytes;
            if (!pristinePayload.AsSpan(start, BlockBytes).SequenceEqual(grafted.AsSpan(start, BlockBytes)))
            {
                notes.Add($"REJECT: untouched block {i} changed — graft bug");
                return new Bc3GraftResult(Array.Empty<byte>(), grafted,
                    new Bc3GraftReport(totalBlocks, blocks.Count, CountMask(editMask01), 0, 0, 0, blocks, false, notes), null);
            }
        }
        notes.Add("all untouched BC3 blocks byte-identical to pristine payload");

        var output = pristineXet.ToArray();
        grafted.CopyTo(output.AsSpan(info.TextureOffset, topLevelBytes));
        var verification = UtageXetCodec.DecodeTopLevel(output);

        var effectiveMask = BuildEffectiveBlockMask(blocks, info.Width, info.Height);
        var outsideEffective = 0;
        var collateral = 0;
        var pixels = checked(info.Width * info.Height);
        for (var i = 0; i < pixels; i++)
        {
            if (!PixelDiffers(baseDecode.Rgba, verification.Rgba, i)) continue;
            if (effectiveMask[i] == 0) outsideEffective++;
            else if (editMask01[i] == 0) collateral++;
        }

        if (outsideEffective != 0)
        {
            notes.Add($"REJECT: final decode changed {outsideEffective} pixels outside effective touched-block mask.");
            return new Bc3GraftResult(output, grafted,
                new Bc3GraftReport(totalBlocks, blocks.Count, CountMask(editMask01), 0, outsideEffective, collateral, blocks, false, notes), verification);
        }

        notes.Add("final decode has zero pixel delta outside effective touched-block mask");
        notes.Add($"BC3 compression collateral inside touched blocks but outside exact edit mask = {collateral} pixels");

        return new Bc3GraftResult(output, grafted,
            new Bc3GraftReport(totalBlocks, blocks.Count, CountMask(editMask01), 0, 0, collateral, blocks, true, notes), verification);
    }

    private static Bc3GraftResult Failure(UtageXetInfo info, int maskPixels, int outsideMaskDelta, IReadOnlyList<(int Bx, int By)> blocks, IReadOnlyList<string> notes) =>
        new(Array.Empty<byte>(), Array.Empty<byte>(),
            new Bc3GraftReport(BlockCount(info.Width, info.Height), 0, maskPixels, outsideMaskDelta, 0, 0, blocks, false, notes), null);

    private static byte[] BuildEffectiveBlockMask(IReadOnlyList<(int Bx, int By)> blocks, int width, int height)
    {
        var mask = new byte[checked(width * height)];
        foreach (var (bx, by) in blocks)
        {
            var x0 = bx * 4;
            var y0 = by * 4;
            for (var y = y0; y < Math.Min(height, y0 + 4); y++)
                for (var x = x0; x < Math.Min(width, x0 + 4); x++)
                    mask[y * width + x] = 1;
        }
        return mask;
    }

    private static bool PixelDiffers(ReadOnlySpan<byte> a, ReadOnlySpan<byte> b, int pixelIndex)
    {
        var o = pixelIndex * 4;
        return a[o] != b[o] || a[o + 1] != b[o + 1] || a[o + 2] != b[o + 2] || a[o + 3] != b[o + 3];
    }

    private static byte[] EncodeFullBc3(ReadOnlySpan<byte> rgba, int width, int height)
    {
        var encoder = new BcEncoder();
        encoder.OutputOptions.Format = CompressionFormat.Bc3;
        encoder.OutputOptions.Quality = CompressionQuality.BestQuality;
        encoder.OutputOptions.GenerateMipMaps = false;
        var levels = encoder.EncodeToRawBytes(rgba.ToArray(), width, height, PixelFormat.Rgba32);
        if (levels.Length != 1)
            throw new InvalidDataException($"BCn encoder returned {levels.Length} levels for a single-level request.");
        return levels[0];
    }

    private static int BlockCount(int width, int height) => Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4);
    private static int CountMask(ReadOnlySpan<byte> mask01) { var n = 0; foreach (var b in mask01) if (b != 0) n++; return n; }
}
