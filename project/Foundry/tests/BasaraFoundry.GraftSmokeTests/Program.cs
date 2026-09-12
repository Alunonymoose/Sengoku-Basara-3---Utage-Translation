using System.Buffers.Binary;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

/// <summary>
/// Synthetic proof of the Research Ledger BC3 block-graft production rule.
/// Does not require private game fixtures. Candidate artwork deliberately
/// begins from the pristine XET's decoded RGBA, because protected-pixel
/// identity is defined against the actual compressed source, not a hypothetical
/// pre-compression image that may differ after BC3 quantisation.
/// </summary>
internal static class Program
{
    private static int Main()
    {
        // 16x8 = 8 BC3 blocks. Edit only the top-left 4x4 block.
        const int width = 16;
        const int height = 8;
        var sourceRgba = new byte[width * height * 4];
        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var i = (y * width + x) * 4;
                sourceRgba[i] = (byte)(10 + (x / 4) * 30);
                sourceRgba[i + 1] = 80;
                sourceRgba[i + 2] = 20;
                sourceRgba[i + 3] = 255;
            }
        }

        var pristineXet = BuildXetFromRgba(sourceRgba, width, height);
        var pristineDecoded = UtageXetCodec.DecodeTopLevel(pristineXet).Rgba;
        var candidate = pristineDecoded.ToArray();

        // Lettering-style edit inside block (0,0).
        for (var y = 1; y < 3; y++)
        {
            for (var x = 1; x < 3; x++)
            {
                var i = (y * width + x) * 4;
                candidate[i] = 255;
                candidate[i + 1] = 255;
                candidate[i + 2] = 120;
                candidate[i + 3] = 255;
            }
        }

        var mask = new byte[width * height];
        for (var y = 1; y < 3; y++)
        {
            for (var x = 1; x < 3; x++)
                mask[y * width + x] = 1;
        }

        var result = UtageBc3BlockGraft.GraftTopLevel(pristineXet, candidate, mask);
        True(result.Report.Ok, "graft reports ok");
        Equal(1, result.Report.BlocksReplaced, "exactly one block replaced");
        Equal(0, result.Report.OutsideMaskPixelDelta, "outside-mask delta is zero");
        True(result.XetBytes.Length == pristineXet.Length, "XET length preserved");

        // Header must be unchanged.
        True(pristineXet.AsSpan(0, 20).SequenceEqual(result.XetBytes.AsSpan(0, 20)), "XET header preserved");

        // Reject path: mutate one guaranteed-different pixel outside the mask.
        var bad = candidate.ToArray();
        var badOffset = (0 * width + 8) * 4;
        bad[badOffset] ^= 0x7F;
        var rejected = UtageBc3BlockGraft.GraftTopLevel(pristineXet, bad, mask);
        True(!rejected.Report.Ok, "rejects outside-mask changes");
        True(rejected.Report.OutsideMaskPixelDelta > 0, "reports outside-mask delta");

        Console.WriteLine("Graft smoke tests passed.");
        Console.WriteLine($"  blocks_replaced={result.Report.BlocksReplaced}/{result.Report.BlocksTotal}");
        foreach (var note in result.Report.Notes)
            Console.WriteLine($"  note: {note}");
        return 0;
    }

    private static byte[] BuildXetFromRgba(byte[] rgba, int width, int height)
    {
        // Build a minimal valid single-level 0x2A XET, then fill payload via codec.
        const int textureOffset = 20;
        var topLevel = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 16;
        var shell = new byte[textureOffset + topLevel];
        shell[0] = 0;
        shell[1] = (byte)'X';
        shell[2] = (byte)'E';
        shell[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(4, 4), (uint)(0x97 | (2 << 28)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(12, 4), (uint)(1 | (0x2A << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(16, 4), textureOffset);

        // ReplaceSingleLevel is used only to manufacture a synthetic compressed
        // pristine fixture. The graft test itself never production-reencodes the
        // untouched blocks.
        var built = UtageXetCodec.ReplaceSingleLevel(shell, rgba);
        return built.XetBytes;
    }

    private static void Equal<T>(T expected, T actual, string label) where T : notnull
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new Exception($"FAIL {label}: expected {expected}, got {actual}");
        Console.WriteLine($"PASS {label}");
    }

    private static void True(bool value, string label)
    {
        if (!value)
            throw new Exception($"FAIL {label}");
        Console.WriteLine($"PASS {label}");
    }
}
