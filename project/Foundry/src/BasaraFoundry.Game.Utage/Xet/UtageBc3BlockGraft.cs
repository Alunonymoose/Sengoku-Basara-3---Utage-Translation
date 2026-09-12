using BCnEncoder.Encoder;
using BCnEncoder.Shared;

namespace BasaraFoundry.Game.Utage.Xet;

public sealed record Bc3GraftReport(
    int BlocksTotal,
    int BlocksReplaced,
    int MaskPixels,
    int OutsideMaskPixelDelta,
    IReadOnlyList<(int Bx, int By)> BlockCoords,
    bool Ok,
    IReadOnlyList<string> Notes);

public sealed record Bc3GraftResult(
    byte[] XetBytes,
    byte[] GraftedPayload,
    Bc3GraftReport Report,
    XetDecodedImage? VerificationDecode);

/// <summary>
/// Production BC3 writer for Utage XET (Research Ledger 2026-09-12).
///
/// Never production-reencode an entire BC3 atlas merely because lettering
/// changed. Start from the pristine compressed payload (typically Japanese),
/// require the candidate RGBA to be pixel-identical outside the edit mask,
/// expand the mask to intersecting 4x4 blocks, and replace only those 16-byte
/// BC3 blocks. Full-sheet encode is preview evidence only.
/// </summary>
public static class UtageBc3BlockGraft
{
    public const int BlockBytes = 16;

    public static IReadOnlyList<(int Bx, int By)> MaskToBlockSet(
        ReadOnlySpan<byte> mask01,
        int width,
        int height)
    {
        if (mask01.Length != checked(width * height))
            throw new ArgumentException("Mask length must equal width*height (one byte per pixel).", nameof(mask01));

        var set = new SortedSet<(int, int)>();
        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                if (mask01[y * width + x] == 0)
                    continue;
                set.Add((x / 4, y / 4));
            }
        }

        var bw = Math.Max(1, (width + 3) / 4);
        var bh = Math.Max(1, (height + 3) / 4);
        var list = new List<(int, int)>(set.Count);
        foreach (var (bx, by) in set)
        {
            if (bx >= 0 && by >= 0 && bx < bw && by < bh)
                list.Add((bx, by));
        }

        return list;
    }

    public static int CountOutsideMaskDeltas(
        ReadOnlySpan<byte> baseRgba,
        ReadOnlySpan<byte> candidateRgba,
        ReadOnlySpan<byte> mask01,
        int width,
        int height)
    {
        var pixels = checked(width * height);
        if (baseRgba.Length != pixels * 4 || candidateRgba.Length != pixels * 4 || mask01.Length != pixels)
            throw new ArgumentException("RGBA/mask dimensions disagree.");

        var delta = 0;
        for (var i = 0; i < pixels; i++)
        {
            if (mask01[i] != 0)
                continue;
            var o = i * 4;
            if (baseRgba[o] != candidateRgba[o] ||
                baseRgba[o + 1] != candidateRgba[o + 1] ||
                baseRgba[o + 2] != candidateRgba[o + 2] ||
                baseRgba[o + 3] != candidateRgba[o + 3])
            {
                delta++;
            }
        }

        return delta;
    }

    /// <summary>
    /// Graft candidate lettering into a pristine XET using an explicit edit mask.
    /// <paramref name="pristineXet"/> is the production artwork base (usually JPN).
    /// </summary>
    public static Bc3GraftResult GraftTopLevel(
        ReadOnlySpan<byte> pristineXet,
        ReadOnlySpan<byte> candidateRgba,
        ReadOnlySpan<byte> editMask01)
    {
        var info = UtageXetReader.ReadInfo(pristineXet);
        UtageXetCodec.RequireEncodingCapability(info);

        var expectedRgba = checked(info.Width * info.Height * 4);
        if (candidateRgba.Length != expectedRgba)
        {
            throw new ArgumentException(
                $"RGBA candidate contains {candidateRgba.Length} bytes; {info.Width}x{info.Height} requires {expectedRgba}.",
                nameof(candidateRgba));
        }

        if (editMask01.Length != info.Width * info.Height)
        {
            throw new ArgumentException(
                $"Edit mask contains {editMask01.Length} pixels; expected {info.Width * info.Height}.",
                nameof(editMask01));
        }

        var topLevelBytes = info.TopLevelSizeBytes
            ?? throw new NotSupportedException("XET encoded byte size is unknown.");
        var expectedEnd = checked(info.TextureOffset + topLevelBytes);
        if (info.MipCount > 1 || pristineXet.Length != expectedEnd)
        {
            throw new NotSupportedException(
                "Block-graft v0.1 is single-level only. Refuse multi-mip or trailing payload XETs.");
        }

        var notes = new List<string>();
        var baseDecode = UtageXetCodec.DecodeTopLevel(pristineXet);
        var outsideDelta = CountOutsideMaskDeltas(
            baseDecode.Rgba, candidateRgba, editMask01, info.Width, info.Height);
        if (outsideDelta != 0)
        {
            notes.Add($"REJECT: {outsideDelta} pixels outside edit mask differ from pristine decode.");
            return new Bc3GraftResult(
                Array.Empty<byte>(),
                Array.Empty<byte>(),
                new Bc3GraftReport(
                    BlocksTotal: BlockCount(info.Width, info.Height),
                    BlocksReplaced: 0,
                    MaskPixels: CountMask(editMask01),
                    OutsideMaskPixelDelta: outsideDelta,
                    BlockCoords: Array.Empty<(int, int)>(),
                    Ok: false,
                    Notes: notes),
                VerificationDecode: null);
        }

        notes.Add("candidate pixel-identical to pristine decode outside edit mask");

        var blocks = MaskToBlockSet(editMask01, info.Width, info.Height);
        if (blocks.Count == 0)
        {
            notes.Add("edit mask is empty — nothing to graft");
            return new Bc3GraftResult(
                Array.Empty<byte>(),
                Array.Empty<byte>(),
                new Bc3GraftReport(
                    BlocksTotal: BlockCount(info.Width, info.Height),
                    BlocksReplaced: 0,
                    MaskPixels: 0,
                    OutsideMaskPixelDelta: 0,
                    BlockCoords: Array.Empty<(int, int)>(),
                    Ok: false,
                    Notes: notes),
                VerificationDecode: null);
        }

        var fullEncoded = EncodeFullBc3(candidateRgba, info.Width, info.Height);
        if (fullEncoded.Length != topLevelBytes)
        {
            throw new InvalidDataException(
                $"BC3 encoder returned {fullEncoded.Length} bytes; XET requires {topLevelBytes}.");
        }

        var pristinePayload = pristineXet.Slice(info.TextureOffset, topLevelBytes).ToArray();
        var grafted = (byte[])pristinePayload.Clone();
        var bw = Math.Max(1, (info.Width + 3) / 4);

        foreach (var (bx, by) in blocks)
        {
            var index = by * bw + bx;
            var start = index * BlockBytes;
            fullEncoded.AsSpan(start, BlockBytes).CopyTo(grafted.AsSpan(start, BlockBytes));
        }

        // Untouched blocks must remain byte-identical to the pristine payload.
        var touched = new HashSet<int>();
        foreach (var (bx, by) in blocks)
            touched.Add(by * bw + bx);

        var totalBlocks = BlockCount(info.Width, info.Height);
        for (var i = 0; i < totalBlocks; i++)
        {
            if (touched.Contains(i))
                continue;
            var start = i * BlockBytes;
            if (!pristinePayload.AsSpan(start, BlockBytes).SequenceEqual(grafted.AsSpan(start, BlockBytes)))
            {
                notes.Add($"untouched block {i} changed — graft bug");
                return new Bc3GraftResult(
                    Array.Empty<byte>(),
                    grafted,
                    new Bc3GraftReport(
                        BlocksTotal: totalBlocks,
                        BlocksReplaced: blocks.Count,
                        MaskPixels: CountMask(editMask01),
                        OutsideMaskPixelDelta: 0,
                        BlockCoords: blocks,
                        Ok: false,
                        Notes: notes),
                    VerificationDecode: null);
            }
        }

        notes.Add("all untouched BC3 blocks byte-identical to pristine payload");

        var output = pristineXet.ToArray();
        grafted.CopyTo(output.AsSpan(info.TextureOffset, topLevelBytes));
        var verification = UtageXetCodec.DecodeTopLevel(output);

        return new Bc3GraftResult(
            output,
            grafted,
            new Bc3GraftReport(
                BlocksTotal: totalBlocks,
                BlocksReplaced: blocks.Count,
                MaskPixels: CountMask(editMask01),
                OutsideMaskPixelDelta: 0,
                BlockCoords: blocks,
                Ok: true,
                Notes: notes),
            verification);
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

    private static int BlockCount(int width, int height) =>
        Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4);

    private static int CountMask(ReadOnlySpan<byte> mask01)
    {
        var n = 0;
        foreach (var b in mask01)
        {
            if (b != 0)
                n++;
        }

        return n;
    }
}
