using System.Buffers.Binary;
using System.Text;

namespace BasaraFoundry.Game.Utage.Layout;

public sealed record UtagePslNodeRecord(
    int Index,
    int Offset,
    float X,
    float Y,
    int? ParentRecordIndex,
    uint NodeBindingId,
    IReadOnlyList<uint> Words70To90,
    IReadOnlyList<uint> Words94ToA0,
    byte[] RawRecord);

public sealed record UtagePslString(
    int LengthPrefixOffset,
    int PayloadOffset,
    string Value);

public sealed record UtagePslInfo(
    uint Version,
    uint HeaderWord08,
    ushort RecordCount,
    ushort SecondaryHeaderCount,
    int RecordsEnd,
    int? StringTableOffset,
    uint? StringTableEntryCount,
    IReadOnlyList<UtagePslNodeRecord> Records,
    IReadOnlyList<UtagePslString> StringInventory);

/// <summary>
/// Conservative, read-only parser for BASARA PSL v0x21 layouts.
///
/// Fixture work across Utage and Samurai Heroes proves:
/// - header size = 0x10;
/// - the big-endian u16 at +0x0C is the number of 0xB0/176-byte records;
/// - the u16 at +0x0E is a separate secondary header count and must NOT be
///   added to the record count;
/// - record +0x38 is the parent record index, with 0xFFFFFFFF marking the
///   single scene-graph root;
/// - a variable middle section may follow the record array;
/// - many, but not all, fixtures carry a trailing hierarchy/string table
///   beginning with a u32 entry count and a u32 length-prefixed "SysRoot\0"
///   sentinel.
///
/// The hierarchy after SysRoot is variable and is not yet generically decoded.
/// In particular, node names/textures are NOT assumed to map one-for-one to
/// record indices. Raw records and a conservative length-prefixed ASCII string
/// inventory are exposed so callers can gather evidence without inventing
/// unsupported geometry or hierarchy semantics.
/// </summary>
public static class UtagePslReader
{
    private const int HeaderSize = 0x10;
    private const int RecordSize = 0xB0;
    private static ReadOnlySpan<byte> Magic => [0x00, 0x50, 0x53, 0x4C]; // \0PSL
    private static ReadOnlySpan<byte> SysRoot => "SysRoot\0"u8;

    public static UtagePslInfo Read(ReadOnlySpan<byte> raw)
    {
        if (raw.Length < HeaderSize || !raw[..4].SequenceEqual(Magic))
            throw new InvalidDataException("Resource is not a PSL layout.");

        var version = U32(raw, 4);
        var headerWord08 = U32(raw, 8);
        var recordCount = U16(raw, 12);
        var secondaryHeaderCount = U16(raw, 14);

        var recordsEnd = checked(HeaderSize + recordCount * RecordSize);
        if (recordsEnd > raw.Length)
            throw new InvalidDataException(
                $"PSL record array overruns resource: {recordCount} * 0x{RecordSize:X} + 0x{HeaderSize:X} > 0x{raw.Length:X}.");

        var records = new List<UtagePslNodeRecord>(recordCount);
        for (var index = 0; index < recordCount; index++)
        {
            var offset = checked(HeaderSize + index * RecordSize);
            var record = raw.Slice(offset, RecordSize);

            var words70To90 = new uint[9];
            for (var i = 0; i < words70To90.Length; i++)
                words70To90[i] = U32(record, 0x70 + i * 4);

            var words94ToA0 = new uint[4];
            for (var i = 0; i < words94ToA0.Length; i++)
                words94ToA0[i] = U32(record, 0x94 + i * 4);

            records.Add(new UtagePslNodeRecord(
                index,
                offset,
                F32(record, 0x00),
                F32(record, 0x04),
                ParentIndex(record, recordCount),
                U32(record, 0x50),
                words70To90,
                words94ToA0,
                record.ToArray()));
        }

        var stringTableOffset = TryLocateStringTable(raw, recordsEnd);
        uint? stringTableEntryCount = stringTableOffset.HasValue ? U32(raw, stringTableOffset.Value) : null;
        var strings = stringTableOffset.HasValue
            ? ExtractLengthPrefixedAsciiStrings(raw, stringTableOffset.Value + 4)
            : Array.Empty<UtagePslString>();

        return new UtagePslInfo(
            version,
            headerWord08,
            recordCount,
            secondaryHeaderCount,
            recordsEnd,
            stringTableOffset,
            stringTableEntryCount,
            records,
            strings);
    }

    private static int? TryLocateStringTable(ReadOnlySpan<byte> raw, int recordsEnd)
    {
        // Real fixtures are not necessarily 4-byte aligned here. Search byte by
        // byte for the length-prefixed SysRoot sentinel.
        for (var payloadOffset = checked(recordsEnd + 8);
             payloadOffset <= raw.Length - SysRoot.Length;
             payloadOffset++)
        {
            if (!raw.Slice(payloadOffset, SysRoot.Length).SequenceEqual(SysRoot))
                continue;

            var lengthPrefixOffset = payloadOffset - 4;
            if (lengthPrefixOffset < recordsEnd || U32(raw, lengthPrefixOffset) != (uint)SysRoot.Length)
                continue;

            var tableOffset = lengthPrefixOffset - 4;
            if (tableOffset < recordsEnd)
                continue;

            var entryCount = U32(raw, tableOffset);
            if (entryCount is 0 or > 0x10000)
                continue;

            return tableOffset;
        }

        // Some valid PSLs (for example loading/capcom/mode-select fixtures)
        // do not expose this SysRoot hierarchy form. Record parsing remains
        // valid; callers must treat hierarchy linkage as unavailable.
        return null;
    }

    private static IReadOnlyList<UtagePslString> ExtractLengthPrefixedAsciiStrings(
        ReadOnlySpan<byte> raw,
        int start)
    {
        var strings = new List<UtagePslString>();
        var seen = new HashSet<(int Offset, string Value)>();

        // Strings inside the hierarchy are u32-length-prefixed but are not
        // guaranteed to be 4-byte aligned, so scan every byte. This is an
        // inventory only; it deliberately does not claim hierarchy linkage.
        for (var offset = start; offset <= raw.Length - 5; offset++)
        {
            var length = U32(raw, offset);
            if (length is < 1 or > 0x400 || offset + 4L + length > raw.Length)
                continue;

            var payload = raw.Slice(offset + 4, checked((int)length));
            if (payload[^1] != 0)
                continue;

            var textBytes = payload[..^1];
            if (textBytes.Length == 0 || !IsPrintableAscii(textBytes))
                continue;

            var value = Encoding.ASCII.GetString(textBytes);
            if (seen.Add((offset, value)))
                strings.Add(new UtagePslString(offset, offset + 4, value));
        }

        return strings;
    }

    private static bool IsPrintableAscii(ReadOnlySpan<byte> value)
    {
        foreach (var b in value)
        {
            if (b is < 0x20 or > 0x7E)
                return false;
        }

        return true;
    }

    private static int? ParentIndex(ReadOnlySpan<byte> record, int recordCount)
    {
        var value = U32(record, 0x38);
        if (value == uint.MaxValue)
            return null;
        if (value >= recordCount)
            throw new InvalidDataException($"PSL parent record index {value} is outside record count {recordCount}.");
        return checked((int)value);
    }

    private static ushort U16(ReadOnlySpan<byte> raw, int offset) =>
        BinaryPrimitives.ReadUInt16BigEndian(raw.Slice(offset, 2));

    private static uint U32(ReadOnlySpan<byte> raw, int offset) =>
        BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(offset, 4));

    private static float F32(ReadOnlySpan<byte> raw, int offset) =>
        BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32BigEndian(raw.Slice(offset, 4)));
}
