using System.Buffers.Binary;
using System.Text;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Art;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.StyleKitSmokeTests;

/// <summary>
/// Synthetic proof that UtageStyleKitAssembler emits mask-safe candidates
/// that pass through UtageSingleEntryXetGraft.BuildSibling.
/// </summary>
internal static class Program
{
    private static int Main()
    {
        TestOutsideMaskIdentityShTier();
        TestOutsideMaskIdentityStyleKit();
        TestProductionWithoutKitThrows();
        TestMultiLineFillsBoxHeight();
        TestBuildSiblingSynthetic();

        Console.WriteLine("Style-kit smoke tests passed.");
        return 0;
    }

    private static void TestOutsideMaskIdentityShTier()
    {
        var pristine = Solid(16, 8, 0x10, 0x20, 0x30, 0xFF);
        var donor = Solid(4, 4, 0xFF, 0x00, 0x00, 0xFF);

        var edit = new UtageStyleKitAssembler.StyleKitTextEdit
        {
            X = 4,
            Y = 2,
            BoxWidth = 4,
            BoxHeight = 4,
            Text = "A",
            ShDonorRgba = donor,
            ShDonorWidth = 4,
            ShDonorHeight = 4,
            ShDonorMatcherConfidence = 1.0f,
        };

        var r = UtageStyleKitAssembler.Assemble(
            pristine, 16, 8, [edit], styleKit: null, production: true);

        Equal(UtageStyleKitAssembler.Tier.ShPixelCrop, r.TierUsed, "tier is ShPixelCrop");
        Equal(0, UtageBc3BlockGraft.CountOutsideMaskDeltas(
            pristine, r.CandidateRgba, r.Mask01, 16, 8), "outside-mask delta is zero (SH)");
        True(UtageBc3BlockGraft.MaskToBlockSet(r.Mask01, 16, 8).Count > 0, "MaskToBlockSet non-empty (SH)");
    }

    private static void TestOutsideMaskIdentityStyleKit()
    {
        var pristine = Solid(32, 16, 0x05, 0x05, 0x05, 0xFF);
        var kit = new SyntheticStyleKitV0();
        var edit = new UtageStyleKitAssembler.StyleKitTextEdit
        {
            X = 8,
            Y = 4,
            BoxWidth = 16,
            BoxHeight = 8,
            Text = "AB",
        };

        var r = UtageStyleKitAssembler.Assemble(
            pristine, 32, 16, [edit], kit, production: true);

        Equal(UtageStyleKitAssembler.Tier.StyleKitV0, r.TierUsed, "tier is StyleKitV0");
        Equal(0, UtageBc3BlockGraft.CountOutsideMaskDeltas(
            pristine, r.CandidateRgba, r.Mask01, 32, 16), "outside-mask delta is zero (StyleKit)");
    }

    private static void TestProductionWithoutKitThrows()
    {
        var pristine = Solid(16, 16, 0, 0, 0, 0xFF);
        var edit = new UtageStyleKitAssembler.StyleKitTextEdit
        {
            X = 0,
            Y = 0,
            BoxWidth = 16,
            BoxHeight = 16,
            Text = "X",
        };

        Throws<InvalidOperationException>(
            () => UtageStyleKitAssembler.Assemble(
                pristine, 16, 16, [edit], styleKit: null, production: true),
            "production with no kit throws");

        var r = UtageStyleKitAssembler.Assemble(
            pristine, 16, 16, [edit], styleKit: null, production: false);
        Equal(UtageStyleKitAssembler.Tier.MockupBlocked, r.TierUsed, "non-production returns MockupBlocked");
    }

    private static void TestMultiLineFillsBoxHeight()
    {
        var pristine = Solid(64, 32, 0, 0, 0, 0xFF);
        var kit = new SyntheticStyleKitV0();
        var edit = new UtageStyleKitAssembler.StyleKitTextEdit
        {
            X = 0,
            Y = 0,
            BoxWidth = 64,
            BoxHeight = 32,
            Text = "GREAT\nLUCK",
        };

        var r = UtageStyleKitAssembler.Assemble(
            pristine, 64, 32, [edit], kit, production: true);

        var topHits = 0;
        var botHits = 0;
        var minY = int.MaxValue;
        var maxY = -1;
        for (var y = 0; y < 32; y++)
        {
            for (var x = 0; x < 64; x++)
            {
                if (r.Mask01[y * 64 + x] == 0)
                    continue;
                if (y < 16)
                    topHits++;
                else
                    botHits++;
                if (y < minY)
                    minY = y;
                if (y > maxY)
                    maxY = y;
            }
        }

        True(topHits > 0, "upper line rendered");
        True(botHits > 0, "lower line rendered");
        True(minY <= 8, $"mask reaches upper box region (minY={minY})");
        True(maxY >= 22, $"mask reaches lower box region (maxY={maxY})");
    }

    private static void TestBuildSiblingSynthetic()
    {
        var pristineRgba = Solid(16, 16, 0, 0, 0, 0xFF);
        var pristineXet = BuildXetFromRgba(pristineRgba, 16, 16);
        var sourceArc = BuildSingleEntryArc("roulette_000_ID_HQ", pristineXet);

        var kit = new SyntheticStyleKitV0();
        var edit = new UtageStyleKitAssembler.StyleKitTextEdit
        {
            X = 4,
            Y = 4,
            BoxWidth = 8,
            BoxHeight = 8,
            Text = "A",
        };

        var r = UtageStyleKitAssembler.Assemble(
            pristineRgba, 16, 16, [edit], kit, production: true);

        var tx = UtageSingleEntryXetGraft.BuildSibling(
            sourceArc,
            memberIndex: 0,
            pristineXet,
            r.CandidateRgba,
            r.Mask01);

        True(tx.Audit.GraftOk, "BuildSibling GraftOk");
        True(tx.SiblingArcBytes.Length > 0, "SiblingArcBytes non-empty");
        True(tx.Audit.OutsideMaskPixelDelta == 0, "audit outside-mask delta is zero");
        True(tx.Audit.BlocksReplaced > 0, "at least one BC3 block replaced");
    }

    // Fixtures copied from GraftSmokeTests patterns.

    private static byte[] Solid(int w, int h, byte r, byte g, byte b, byte a)
    {
        var buf = new byte[w * h * 4];
        for (var i = 0; i < w * h; i++)
        {
            buf[i * 4] = r;
            buf[i * 4 + 1] = g;
            buf[i * 4 + 2] = b;
            buf[i * 4 + 3] = a;
        }

        return buf;
    }

    private static byte[] BuildXetFromRgba(byte[] rgba, int width, int height)
    {
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
        return UtageXetCodec.ReplaceSingleLevel(shell, rgba).XetBytes;
    }

    private static byte[] BuildSingleEntryArc(string name, byte[] rawPayload)
    {
        const int headerSize = 8;
        const int entrySize = 80;
        const int payloadOffset = 128;
        var arc = new byte[payloadOffset + rawPayload.Length];
        arc[0] = 0;
        arc[1] = (byte)'C';
        arc[2] = (byte)'R';
        arc[3] = (byte)'A';
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(4, 2), 8);
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(6, 2), 1);
        var record = arc.AsSpan(headerSize, entrySize);
        var nameBytes = Encoding.UTF8.GetBytes(name);
        if (nameBytes.Length >= 64)
            throw new ArgumentException("Synthetic ARC name must fit the 64-byte field.", nameof(name));
        nameBytes.CopyTo(record);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), UtageTypeHashes.Texture);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), checked((uint)rawPayload.Length));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), checked((uint)rawPayload.Length << 3));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), payloadOffset);
        rawPayload.CopyTo(arc.AsSpan(payloadOffset));
        return arc;
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

    private static void Throws<TException>(Action action, string label) where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            Console.WriteLine($"PASS {label}");
            return;
        }

        throw new Exception($"FAIL {label}: expected {typeof(TException).Name}");
    }
}
