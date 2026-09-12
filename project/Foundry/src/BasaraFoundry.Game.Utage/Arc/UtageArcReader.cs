using System.Buffers.Binary;
using System.IO.Compression;
using System.Text;

namespace BasaraFoundry.Game.Utage.Arc;

public sealed record UtageArcEntry(
    int Index,
    string Name,
    uint TypeHash,
    int CompressedSize,
    int RawSize,
    int Flags,
    int PayloadOffset,
    byte[] OriginalRecord);

public sealed record UtageArcArchive(
    string SourceName,
    ushort Version,
    IReadOnlyList<UtageArcEntry> Entries,
    long Length);

/// <summary>
/// Conservative reader for the PS3 big-endian MT Framework ARC v8 form used by Utage.
/// It deliberately refuses formats it has not been certified against.
/// </summary>
public static class UtageArcReader
{
    private static ReadOnlySpan<byte> Magic => [0x00, 0x43, 0x52, 0x41]; // \0CRA
    private const int HeaderSize = 8;
    private const int EntrySize = 80;
    private const int NameSize = 64;

    public static UtageArcArchive Read(string path)
    {
        using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Read(stream, path);
    }

    public static UtageArcArchive Read(Stream stream, string sourceName = "<stream>")
    {
        ArgumentNullException.ThrowIfNull(stream);
        if (!stream.CanRead || !stream.CanSeek)
            throw new ArgumentException("ARC input must be a readable, seekable stream.", nameof(stream));

        if (stream.Length < HeaderSize)
            throw new InvalidDataException("ARC is shorter than its 8-byte header.");

        Span<byte> header = stackalloc byte[HeaderSize];
        stream.Position = 0;
        stream.ReadExactly(header);

        if (!header[..4].SequenceEqual(Magic))
            throw new NotSupportedException("Foundry v0.1 only certifies the PS3 big-endian \\0CRA ARC form.");

        var version = BinaryPrimitives.ReadUInt16BigEndian(header[4..6]);
        var count = BinaryPrimitives.ReadUInt16BigEndian(header[6..8]);
        if (version != 8)
            throw new NotSupportedException($"ARC version {version} is readable only after a dedicated capability test; v0.1 certifies v8.");

        var tableLength = checked((long)count * EntrySize);
        var tableEnd = HeaderSize + tableLength;
        if (tableEnd > stream.Length)
            throw new InvalidDataException("ARC entry table extends beyond end of file.");

        var entries = new List<UtageArcEntry>(count);
        var record = new byte[EntrySize];

        for (var index = 0; index < count; index++)
        {
            stream.Position = HeaderSize + (long)index * EntrySize;
            stream.ReadExactly(record);

            var nameEnd = Array.IndexOf(record, (byte)0, 0, NameSize);
            if (nameEnd < 0)
                nameEnd = NameSize;
            var name = Encoding.UTF8.GetString(record, 0, nameEnd);

            var typeHash = BinaryPrimitives.ReadUInt32BigEndian(record.AsSpan(64, 4));
            var compressedSizeU = BinaryPrimitives.ReadUInt32BigEndian(record.AsSpan(68, 4));
            var packedSize = BinaryPrimitives.ReadUInt32BigEndian(record.AsSpan(72, 4));
            var payloadOffsetU = BinaryPrimitives.ReadUInt32BigEndian(record.AsSpan(76, 4));

            if (compressedSizeU > int.MaxValue || payloadOffsetU > int.MaxValue)
                throw new InvalidDataException($"ARC entry {index} exceeds Foundry's current safe integer range.");

            var compressedSize = (int)compressedSizeU;
            var payloadOffset = (int)payloadOffsetU;
            var rawSize = checked((int)(packedSize >> 3));
            var flags = (int)(packedSize & 0x7);
            var payloadEnd = (long)payloadOffset + compressedSize;

            if (payloadOffset < tableEnd || payloadEnd > stream.Length)
                throw new InvalidDataException($"ARC entry {index} ('{name}') has an invalid payload range.");

            entries.Add(new UtageArcEntry(
                index,
                name,
                typeHash,
                compressedSize,
                rawSize,
                flags,
                payloadOffset,
                record.ToArray()));
        }

        return new UtageArcArchive(sourceName, version, entries, stream.Length);
    }

    public static byte[] ReadStoredPayload(Stream stream, UtageArcEntry entry)
    {
        ArgumentNullException.ThrowIfNull(stream);
        ArgumentNullException.ThrowIfNull(entry);
        var output = new byte[entry.CompressedSize];
        stream.Position = entry.PayloadOffset;
        stream.ReadExactly(output);
        return output;
    }

    public static byte[] ReadDecompressedPayload(Stream stream, UtageArcEntry entry)
    {
        var stored = ReadStoredPayload(stream, entry);
        if (entry.CompressedSize == entry.RawSize)
            return stored;

        using var source = new MemoryStream(stored, writable: false);
        using var zlib = new ZLibStream(source, CompressionMode.Decompress, leaveOpen: false);
        using var target = new MemoryStream(entry.RawSize > 0 ? entry.RawSize : 0);
        zlib.CopyTo(target);
        var result = target.ToArray();
        if (result.Length != entry.RawSize)
            throw new InvalidDataException(
                $"Decompressed ARC member '{entry.Name}' to {result.Length} bytes; expected {entry.RawSize}.");
        return result;
    }
}
