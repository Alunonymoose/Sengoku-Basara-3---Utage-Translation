using System.Buffers.Binary;
using System.Runtime.CompilerServices;
using System.Text;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

/// <summary>
/// Regression for the 2026-09-17 pristine-base defect: an incremental edit must
/// never revert pre-existing live English artwork in another untouched BC3 block.
/// </summary>
internal static class IncrementalTargetPreservationRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        const int width = 8;
        const int height = 4;
        const int textureOffset = 20;

        var pristineRgba = new byte[width * height * 4];
        for (var i = 0; i < width * height; i++)
        {
            pristineRgba[i * 4] = 40;
            pristineRgba[i * 4 + 1] = 70;
            pristineRgba[i * 4 + 2] = 100;
            pristineRgba[i * 4 + 3] = 255;
        }

        var pristineXet = BuildXet(pristineRgba, width, height, textureOffset);
        var pristineDecoded = UtageXetCodec.DecodeTopLevel(pristineXet).Rgba;

        // Existing live English artwork occupies block (1,0).
        var liveTargetRgba = pristineDecoded.ToArray();
        for (var y = 0; y < 4; y++)
        for (var x = 4; x < 8; x++)
        {
            var o = (y * width + x) * 4;
            liveTargetRgba[o] = 220;
            liveTargetRgba[o + 1] = 40;
            liveTargetRgba[o + 2] = 30;
            liveTargetRgba[o + 3] = 255;
        }
        var liveTargetXet = BuildXet(liveTargetRgba, width, height, textureOffset);
        var liveTargetDecoded = UtageXetCodec.DecodeTopLevel(liveTargetXet).Rgba;

        // Candidate starts from pristine/older artwork, not the live target. Only
        // block (0,0) is approved. Differences in untouched block (1,0) must be ignored.
        var candidate = pristineDecoded.ToArray();
        var changedPixel = 1 * width + 1;
        var changedOffset = changedPixel * 4;
        candidate[changedOffset] = 250;
        candidate[changedOffset + 1] = 230;
        candidate[changedOffset + 2] = 20;
        candidate[changedOffset + 3] = 255;
        var mask = new byte[width * height];
        mask[changedPixel] = 1;

        var sourceArc = BuildSingleEntryArc("incremental_ID_HQ", liveTargetXet);
        var tx = UtageSingleEntryXetGraft.BuildSibling(sourceArc, 0, pristineXet, candidate, mask);
        Assert(!tx.Audit.UsedPristineOverride, "normal production transaction uses current target as graft base");

        var finalXet = ReadOnlyMember(tx.SiblingArcBytes, 0);
        var finalDecoded = UtageXetCodec.DecodeTopLevel(finalXet).Rgba;
        Assert(BlockEqual(finalDecoded, liveTargetDecoded, width, bx: 1, by: 0),
            "pre-existing live English block survives incremental edit");

        var info = UtageXetReader.ReadInfo(liveTargetXet);
        var payloadLength = info.TopLevelSizeBytes!.Value;
        var livePayload = liveTargetXet.AsSpan(info.TextureOffset, payloadLength);
        var finalPayload = finalXet.AsSpan(info.TextureOffset, payloadLength);
        Assert(livePayload.Slice(16, 16).SequenceEqual(finalPayload.Slice(16, 16)),
            "untouched live BC3 block is byte-identical");
        Assert(!livePayload.Slice(0, 16).SequenceEqual(finalPayload.Slice(0, 16)),
            "approved touched BC3 block changed");

        Console.WriteLine("PASS incremental target preservation regression");
    }

    private static byte[] BuildXet(byte[] rgba, int width, int height, int textureOffset)
    {
        var topLevel = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 16;
        var shell = new byte[textureOffset + topLevel];
        shell[0] = 0;
        shell[1] = (byte)'X';
        shell[2] = (byte)'E';
        shell[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(4, 4), (uint)(0x97 | (2 << 28)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(12, 4), (uint)(1 | (0x17 << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(16, 4), checked((uint)textureOffset));
        return UtageXetCodec.ReplaceSingleLevel(shell, rgba).XetBytes;
    }

    private static byte[] BuildSingleEntryArc(string name, byte[] rawPayload)
    {
        const int payloadOffset = 128;
        var arc = new byte[payloadOffset + rawPayload.Length];
        arc[0] = 0;
        arc[1] = (byte)'C';
        arc[2] = (byte)'R';
        arc[3] = (byte)'A';
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(4, 2), 8);
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(6, 2), 1);
        var record = arc.AsSpan(8, 80);
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
        var arc = UtageArcReader.Read(stream, "<incremental-regression>");
        stream.Position = 0;
        return UtageArcReader.ReadDecompressedPayload(stream, arc.Entries[index]);
    }

    private static bool BlockEqual(ReadOnlySpan<byte> a, ReadOnlySpan<byte> b, int width, int bx, int by)
    {
        for (var y = by * 4; y < by * 4 + 4; y++)
        for (var x = bx * 4; x < bx * 4 + 4; x++)
        {
            var o = (y * width + x) * 4;
            if (!a.Slice(o, 4).SequenceEqual(b.Slice(o, 4))) return false;
        }
        return true;
    }

    private static void Assert(bool condition, string label)
    {
        if (!condition) throw new Exception("FAIL incremental target preservation: " + label);
        Console.WriteLine("PASS " + label);
    }
}
