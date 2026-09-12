using System.Buffers.Binary;
using System.IO.Compression;

namespace BasaraFoundry.Game.Utage.Arc;

public sealed record ArcMemberBuildResult(
    int Index,
    string Name,
    bool Replaced,
    int OriginalOffset,
    int NewOffset,
    int OriginalStoredSize,
    int NewStoredSize,
    int OriginalRawSize,
    int NewRawSize);

public sealed record ArcBuildResult(
    byte[] Bytes,
    int Alignment,
    int ReplacedMemberCount,
    IReadOnlyList<ArcMemberBuildResult> Members)
{
    public bool IsNoOp => ReplacedMemberCount == 0;
}

/// <summary>
/// Surgical writer for the certified PS3 Utage ARC v8 form.
///
/// Safety contract:
/// - the source archive is reparsed from the exact bytes being rebuilt;
/// - a no-op build returns those source bytes exactly;
/// - untouched stored member payloads are copied byte-for-byte;
/// - entry names, type hashes and flag bits are preserved;
/// - only size/offset fields required by relocation are rewritten;
/// - output is reparsed before it is returned.
/// </summary>
public static class UtageArcWriter
{
    private static readonly int[] CandidateAlignments =
        [2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4];

    public static ArcBuildResult Rebuild(
        ReadOnlySpan<byte> original,
        IReadOnlyDictionary<int, byte[]> rawReplacements)
    {
        ArgumentNullException.ThrowIfNull(rawReplacements);

        if (original.Length < 8)
            throw new InvalidDataException("ARC source is shorter than its header.");

        var sourceBytes = original.ToArray();
        using var sourceStream = new MemoryStream(sourceBytes, writable: false);
        var archive = UtageArcReader.Read(sourceStream, "<rebuild-source>");

        if (rawReplacements.Count == 0)
        {
            return new ArcBuildResult(
                sourceBytes,
                DetectAlignment(archive.Entries),
                0,
                archive.Entries
                    .Select(entry => new ArcMemberBuildResult(
                        entry.Index,
                        entry.Name,
                        false,
                        entry.PayloadOffset,
                        entry.PayloadOffset,
                        entry.CompressedSize,
                        entry.CompressedSize,
                        entry.RawSize,
                        entry.RawSize))
                    .ToArray());
        }

        ValidateReplacementKeys(archive, rawReplacements);
        ValidatePayloadRanges(archive, sourceBytes.Length);

        var alignment = DetectAlignment(archive.Entries);
        var physicalEntries = archive.Entries.OrderBy(entry => entry.PayloadOffset).ToArray();
        var firstPayload = physicalEntries[0].PayloadOffset;
        var output = new List<byte>(Math.Max(sourceBytes.Length, firstPayload));
        output.AddRange(sourceBytes.AsSpan(0, firstPayload).ToArray());

        var newOffsets = new Dictionary<int, int>(archive.Entries.Count);
        var storedPayloads = new Dictionary<int, byte[]>(archive.Entries.Count);
        var rawSizes = new Dictionary<int, int>(archive.Entries.Count);

        foreach (var entry in physicalEntries)
        {
            var targetOffset = Align(output.Count, alignment);
            if (targetOffset > output.Count)
                output.AddRange(new byte[targetOffset - output.Count]);

            byte[] stored;
            int rawSize;
            if (rawReplacements.TryGetValue(entry.Index, out var replacement))
            {
                ArgumentNullException.ThrowIfNull(replacement);
                rawSize = replacement.Length;
                EnsurePackedSizeFits(rawSize, entry.Index);
                stored = entry.CompressedSize == entry.RawSize
                    ? replacement.ToArray()
                    : CompressZlib(replacement);
            }
            else
            {
                rawSize = entry.RawSize;
                stored = sourceBytes.AsSpan(entry.PayloadOffset, entry.CompressedSize).ToArray();
            }

            newOffsets[entry.Index] = targetOffset;
            storedPayloads[entry.Index] = stored;
            rawSizes[entry.Index] = rawSize;
            output.AddRange(stored);
        }

        var rebuilt = output.ToArray();
        foreach (var entry in archive.Entries)
        {
            var recordOffset = 8 + entry.Index * 80;
            var stored = storedPayloads[entry.Index];
            var rawSize = rawSizes[entry.Index];
            var packedSize = checked(((uint)rawSize << 3) | (uint)(entry.Flags & 0x7));

            // Preserve name + type hash exactly. Rewrite only compressed size,
            // packed raw size/flags, and payload offset.
            BinaryPrimitives.WriteUInt32BigEndian(
                rebuilt.AsSpan(recordOffset + 68, 4),
                checked((uint)stored.Length));
            BinaryPrimitives.WriteUInt32BigEndian(
                rebuilt.AsSpan(recordOffset + 72, 4),
                packedSize);
            BinaryPrimitives.WriteUInt32BigEndian(
                rebuilt.AsSpan(recordOffset + 76, 4),
                checked((uint)newOffsets[entry.Index]));
        }

        VerifyRebuiltArchive(sourceBytes, archive, rebuilt, rawReplacements);

        var members = archive.Entries.Select(entry => new ArcMemberBuildResult(
            entry.Index,
            entry.Name,
            rawReplacements.ContainsKey(entry.Index),
            entry.PayloadOffset,
            newOffsets[entry.Index],
            entry.CompressedSize,
            storedPayloads[entry.Index].Length,
            entry.RawSize,
            rawSizes[entry.Index])).ToArray();

        return new ArcBuildResult(rebuilt, alignment, rawReplacements.Count, members);
    }

    public static int DetectAlignment(IReadOnlyList<UtageArcEntry> entries)
    {
        if (entries.Count == 0)
            return 1;

        foreach (var alignment in CandidateAlignments)
        {
            if (entries.All(entry => entry.PayloadOffset % alignment == 0))
                return alignment;
        }

        return 1;
    }

    private static void ValidateReplacementKeys(
        UtageArcArchive archive,
        IReadOnlyDictionary<int, byte[]> replacements)
    {
        var valid = archive.Entries.Select(entry => entry.Index).ToHashSet();
        foreach (var index in replacements.Keys)
        {
            if (!valid.Contains(index))
                throw new ArgumentOutOfRangeException(
                    nameof(replacements),
                    $"Replacement targets ARC member {index}, but the archive contains {archive.Entries.Count} members.");
        }
    }

    private static void ValidatePayloadRanges(UtageArcArchive archive, int sourceLength)
    {
        var ordered = archive.Entries.OrderBy(entry => entry.PayloadOffset).ToArray();
        long previousEnd = 0;
        foreach (var entry in ordered)
        {
            var end = (long)entry.PayloadOffset + entry.CompressedSize;
            if (entry.PayloadOffset < previousEnd)
                throw new InvalidDataException($"ARC member {entry.Index} overlaps the previous payload.");
            if (end > sourceLength)
                throw new InvalidDataException($"ARC member {entry.Index} exceeds the source archive.");
            previousEnd = end;
        }
    }

    private static void EnsurePackedSizeFits(int rawSize, int index)
    {
        if (rawSize < 0 || rawSize > 0x1FFFFFFF)
        {
            throw new InvalidDataException(
                $"Replacement for ARC member {index} is too large for the PS3 packed-size field ({rawSize} bytes).");
        }
    }

    private static int Align(int value, int alignment)
    {
        if (alignment <= 1)
            return value;
        return checked(((value + alignment - 1) / alignment) * alignment);
    }

    private static byte[] CompressZlib(ReadOnlySpan<byte> raw)
    {
        using var output = new MemoryStream();
        using (var zlib = new ZLibStream(output, CompressionLevel.SmallestSize, leaveOpen: true))
        {
            zlib.Write(raw);
        }
        return output.ToArray();
    }

    private static void VerifyRebuiltArchive(
        byte[] original,
        UtageArcArchive before,
        byte[] rebuilt,
        IReadOnlyDictionary<int, byte[]> replacements)
    {
        using var rebuiltStream = new MemoryStream(rebuilt, writable: false);
        var after = UtageArcReader.Read(rebuiltStream, "<rebuilt>");

        if (after.Version != before.Version || after.Entries.Count != before.Entries.Count)
            throw new InvalidDataException("Rebuilt ARC changed its version or member count.");

        for (var i = 0; i < before.Entries.Count; i++)
        {
            var oldEntry = before.Entries[i];
            var newEntry = after.Entries[i];
            if (oldEntry.Index != newEntry.Index ||
                oldEntry.Name != newEntry.Name ||
                oldEntry.TypeHash != newEntry.TypeHash ||
                oldEntry.Flags != newEntry.Flags)
            {
                throw new InvalidDataException($"Rebuilt ARC changed protected metadata for member {i}.");
            }

            if (!replacements.ContainsKey(i))
            {
                var oldStored = original.AsSpan(oldEntry.PayloadOffset, oldEntry.CompressedSize);
                var newStored = rebuilt.AsSpan(newEntry.PayloadOffset, newEntry.CompressedSize);
                if (!oldStored.SequenceEqual(newStored))
                    throw new InvalidDataException($"Untouched ARC member {i} changed stored payload bytes.");
                if (oldEntry.RawSize != newEntry.RawSize || oldEntry.CompressedSize != newEntry.CompressedSize)
                    throw new InvalidDataException($"Untouched ARC member {i} changed size metadata.");
            }
            else
            {
                rebuiltStream.Position = 0;
                var decoded = UtageArcReader.ReadDecompressedPayload(rebuiltStream, newEntry);
                if (!decoded.AsSpan().SequenceEqual(replacements[i]))
                    throw new InvalidDataException($"Replacement ARC member {i} did not round-trip to the requested raw bytes.");
            }
        }
    }
}
