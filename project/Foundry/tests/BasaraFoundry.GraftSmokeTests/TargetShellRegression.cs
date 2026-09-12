using System.Buffers.Binary;
using System.Runtime.CompilerServices;
using System.Text;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

/// <summary>
/// Regression for the 2026-09-12 donor-whole-XET defect.
/// Runs as part of the existing GraftSmokeTests executable before Program.Main.
/// </summary>
internal static class TargetShellRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        const int width = 8;
        const int height = 4;
        const int textureOffset = 24;

        var sourceRgba = new byte[width * height * 4];
        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var p = (y * width + x) * 4;
                sourceRgba[p] = (byte)(30 + x * 8);
                sourceRgba[p + 1] = (byte)(50 + y * 10);
                sourceRgba[p + 2] = 90;
                sourceRgba[p + 3] = 255;
            }
        }

        var pristineXet = BuildXet(sourceRgba, width, height, textureOffset, "JPN!");
        var pristineDecoded = UtageXetCodec.DecodeTopLevel(pristineXet).Rgba;

        // Candidate changes one exact pixel in block 0.
        var candidate = pristineDecoded.ToArray();
        var changedPixel = 1 * width + 1;
        var changedOffset = changedPixel * 4;
        candidate[changedOffset] = 240;
        candidate[changedOffset + 1] = 220;
        candidate[changedOffset + 2] = 40;
        candidate[changedOffset + 3] = 255;
        var mask = new byte[width * height];
        mask[changedPixel] = 1;

        // Current ENG target contains unrelated damage in block 1 and a distinct
        // target-only extension shell. Neither may be taken as pristine art;
        // the shell, however, is the live container identity and must survive.
        var damagedTargetRgba = pristineDecoded.ToArray();
        var damagedPixel = 1 * width + 6;
        damagedTargetRgba[damagedPixel * 4] ^= 0x7f;
        var targetXet = BuildXet(damagedTargetRgba, width, height, textureOffset, "ENG!");
        var sourceArc = BuildSingleEntryArc("roulette_000_ID_HQ", targetXet);

        var tx = UtageSingleEntryXetGraft.BuildSibling(
            sourceArc,
            0,
            pristineXet,
            candidate,
            mask,
            new DateTimeOffset(2026, 9, 12, 12, 0, 0, TimeSpan.Zero));

        var finalXet = ReadOnlyMember(tx.SiblingArcBytes, 0);
        Assert(finalXet.AsSpan(0, textureOffset).SequenceEqual(targetXet.AsSpan(0, textureOffset)),
            "target XET shell/header preserved byte-for-byte");
        Assert(Encoding.ASCII.GetString(finalXet, 20, 4) == "ENG!",
            "target-only XET extension survives; pristine donor shell not transplanted");
        Assert(!Encoding.ASCII.GetString(finalXet, 20, 4).Equals("JPN!", StringComparison.Ordinal),
            "output shell is not the pristine donor shell");

        var finalDecoded = UtageXetCodec.DecodeTopLevel(finalXet).Rgba;
        Assert(PixelEqual(finalDecoded, pristineDecoded, damagedPixel),
            "unrelated damaged ENG block restored from pristine compressed artwork");
        Assert(tx.Audit.TargetShellPreserved, "audit records target-shell preservation");
        Assert(tx.Audit.OutsideEffectiveBlockPixelDelta == 0,
            "audit proves zero final decoded delta outside effective BC3 footprint");
        Assert(tx.Audit.CandidateRgbaSha256 == tx.ApprovalEvidence.CandidateSha256,
            "approval proof bound to candidate hash");
        Assert(tx.Audit.EditMaskSha256 == tx.ApprovalEvidence.EditMaskSha256,
            "approval proof bound to edit-mask hash");
        Assert(tx.Audit.TargetResourceSha256 == tx.ApprovalEvidence.TargetResourceSha256,
            "approval proof bound to target resource hash");
        Assert(tx.Audit.PristineBaseSha256 == tx.ApprovalEvidence.PristineResourceSha256,
            "approval proof bound to pristine resource hash");
        Assert(tx.Audit.FinalResourceSha256 == tx.ApprovalEvidence.FinalResourceSha256,
            "approval proof bound to final resource hash");

        // Fail closed when parsed interpretation metadata differs even though the
        // dimensions/format would otherwise look superficially compatible.
        var incompatible = pristineXet.ToArray();
        var block4 = BinaryPrimitives.ReadUInt32BigEndian(incompatible.AsSpan(4, 4));
        block4 ^= 1u << 28; // alter alphaFlags only
        BinaryPrimitives.WriteUInt32BigEndian(incompatible.AsSpan(4, 4), block4);
        ExpectThrows<InvalidDataException>(() =>
            UtageSingleEntryXetGraft.BuildSibling(sourceArc, 0, incompatible, candidate, mask),
            "interpretation-affecting XET header mismatch rejected");

        Console.WriteLine("PASS target-shell regression transaction");
    }

    private static byte[] BuildXet(byte[] rgba, int width, int height, int textureOffset, string shellTag)
    {
        var topLevel = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 16;
        var shell = new byte[textureOffset + topLevel];
        shell[0] = 0;
        shell[1] = (byte)'X';
        shell[2] = (byte)'E';
        shell[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(4, 4), (uint)(0x97 | (2 << 28)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(12, 4), (uint)(1 | (0x2A << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(16, 4), checked((uint)textureOffset));
        Encoding.ASCII.GetBytes(shellTag).CopyTo(shell.AsSpan(20, 4));
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
        Encoding.UTF8.GetBytes(name).CopyTo(record);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), UtageTypeHashes.Texture);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), checked((uint)rawPayload.Length));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), checked((uint)rawPayload.Length << 3));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), payloadOffset);
        rawPayload.CopyTo(arc.AsSpan(payloadOffset));
        return arc;
    }

    private static byte[] ReadOnlyMember(byte[] arcBytes, int index)
    {
        using var stream = new MemoryStream(arcBytes, writable: false);
        var arc = UtageArcReader.Read(stream, "<target-shell-regression>");
        stream.Position = 0;
        return UtageArcReader.ReadDecompressedPayload(stream, arc.Entries[index]);
    }

    private static bool PixelEqual(ReadOnlySpan<byte> a, ReadOnlySpan<byte> b, int pixel)
    {
        var o = pixel * 4;
        return a.Slice(o, 4).SequenceEqual(b.Slice(o, 4));
    }

    private static void Assert(bool condition, string label)
    {
        if (!condition) throw new Exception("FAIL target-shell regression: " + label);
        Console.WriteLine("PASS " + label);
    }

    private static void ExpectThrows<T>(Action action, string label) where T : Exception
    {
        try { action(); }
        catch (T) { Console.WriteLine("PASS " + label); return; }
        throw new Exception($"FAIL target-shell regression: {label}; expected {typeof(T).Name}");
    }
}
