using System.Buffers.Binary;

namespace BasaraFoundry.Game.Utage.Message;

public sealed record UtageTnfGlyph(int Code, ushort PackedGlyph, int AtlasPage, int GlyphId, ushort X, ushort Y, ushort Advance);
public sealed record UtageTnfInfo(uint Count, uint CellWidth, uint CellHeight, IReadOnlyList<UtageTnfGlyph> Glyphs);

public sealed record UtageGsmRow(int Index, uint OffsetUnits, uint LengthUnits, int VisibleUnits, bool Terminated, IReadOnlyList<ushort> Codes);
public sealed record UtageGsmInfo(uint TotalUnits, uint Count, IReadOnlyList<UtageGsmRow> Rows);

public sealed record UtageFimMap(int MessageIndex, IReadOnlyList<uint> Words, uint FormatIndex);
public sealed record UtageFimFormat(int FormatIndex, uint LineCount, uint DisplayGlyphCount, IReadOnlyList<uint> Words, int Offset);
public sealed record UtageFimInfo(uint MessageCount, uint FormatCount, IReadOnlyList<UtageFimMap> Maps, IReadOnlyList<UtageFimFormat> Formats);

public sealed record UtageCsaInfo(uint CountOrSize, IReadOnlyList<uint> Words);

/// <summary>
/// Bounds-checked, read-only parsers ported from the proven mt_arc_explorer fixture logic.
/// Writers are deliberately absent: message/font mutation remains gated until structural invariants are certified.
/// </summary>
public static class UtageMessageResourceReader
{
    private const int FimHeaderSize = 32;
    private const int FimMapSize = 20;
    private const int FimFormatSize = 44;

    public static UtageTnfInfo ReadTnf(ReadOnlySpan<byte> raw)
    {
        RequireMagic(raw, "TNF", 32);
        var count = U32(raw, 8);
        var cellWidth = U32(raw, 12);
        var cellHeight = U32(raw, 16);
        var required = checked(32L + count * 8L);
        if (required > raw.Length)
            throw new InvalidDataException("TNF glyph records overrun resource.");

        var glyphs = new List<UtageTnfGlyph>(checked((int)count));
        for (var code = 0; code < count; code++)
        {
            var offset = checked(32 + (int)code * 8);
            var packedGlyph = U16(raw, offset);
            glyphs.Add(new UtageTnfGlyph(
                checked((int)code),
                packedGlyph,
                packedGlyph >> 8,
                packedGlyph & 0xFF,
                U16(raw, offset + 2),
                U16(raw, offset + 4),
                U16(raw, offset + 6)));
        }
        return new UtageTnfInfo(count, cellWidth, cellHeight, glyphs);
    }

    public static UtageGsmInfo ReadGsm(ReadOnlySpan<byte> raw)
    {
        RequireMagic(raw, "GSM", 16);
        var totalUnits = U32(raw, 8);
        var count = U32(raw, 12);
        var tableBytes = checked((long)count * 8L);
        var payloadStart = checked(16L + tableBytes);
        var payloadEnd = checked(payloadStart + totalUnits * 2L);
        if (payloadEnd > raw.Length)
            throw new InvalidDataException("GSM payload overruns resource.");

        var rows = new List<UtageGsmRow>(checked((int)count));
        for (var index = 0; index < count; index++)
        {
            var table = checked(16 + (int)index * 8);
            var offsetUnits = U32(raw, table);
            var lengthUnits = U32(raw, table + 4);
            var start = checked(payloadStart + offsetUnits * 2L);
            var end = checked(start + lengthUnits * 2L);
            if (start < payloadStart || end > raw.Length)
                throw new InvalidDataException($"GSM row {index} overruns payload.");

            var codes = new ushort[checked((int)lengthUnits)];
            var visible = codes.Length;
            var terminated = false;
            for (var i = 0; i < codes.Length; i++)
            {
                codes[i] = U16(raw, checked((int)start + i * 2));
                if (!terminated && codes[i] == 0xFFFF)
                {
                    visible = i;
                    terminated = true;
                }
            }
            rows.Add(new UtageGsmRow(checked((int)index), offsetUnits, lengthUnits, visible, terminated, codes));
        }
        return new UtageGsmInfo(totalUnits, count, rows);
    }

    public static UtageFimInfo ReadFim(ReadOnlySpan<byte> raw)
    {
        RequireMagic(raw, "FIM", FimHeaderSize);
        var messageCount = U32(raw, 8);
        var formatCount = U32(raw, 12);
        var mapsStart = FimHeaderSize;
        var formatsStart = checked(mapsStart + (long)messageCount * FimMapSize);
        var required = checked(formatsStart + (long)formatCount * FimFormatSize);
        if (required > raw.Length)
            throw new InvalidDataException("FIM records overrun resource.");

        var maps = new List<UtageFimMap>(checked((int)messageCount));
        for (var index = 0; index < messageCount; index++)
        {
            var offset = checked(mapsStart + (int)index * FimMapSize);
            var words = ReadWords(raw, offset, 5);
            maps.Add(new UtageFimMap(checked((int)index), words, words[4]));
        }

        var formats = new List<UtageFimFormat>(checked((int)formatCount));
        for (var index = 0; index < formatCount; index++)
        {
            var offset = checked((int)formatsStart + (int)index * FimFormatSize);
            var words = ReadWords(raw, offset, 11);
            formats.Add(new UtageFimFormat(
                checked((int)index),
                words[0] >> 16,
                words[0] & 0xFFFF,
                words,
                offset));
        }
        return new UtageFimInfo(messageCount, formatCount, maps, formats);
    }

    public static UtageCsaInfo ReadCsa(ReadOnlySpan<byte> raw)
    {
        RequireMagic(raw, "CSA", 8);
        var words = new List<uint>();
        for (var offset = 8; offset + 4 <= raw.Length; offset += 4)
            words.Add(U32(raw, offset));
        return new UtageCsaInfo(U32(raw, 4), words);
    }

    private static IReadOnlyList<uint> ReadWords(ReadOnlySpan<byte> raw, int offset, int count)
    {
        var result = new uint[count];
        for (var i = 0; i < count; i++)
            result[i] = U32(raw, checked(offset + i * 4));
        return result;
    }

    private static void RequireMagic(ReadOnlySpan<byte> raw, string ascii, int minimumLength)
    {
        if (raw.Length < minimumLength || raw[0] != 0 || raw[1] != ascii[0] || raw[2] != ascii[1] || raw[3] != ascii[2])
            throw new InvalidDataException($"Resource is not a valid {ascii} payload.");
    }

    private static ushort U16(ReadOnlySpan<byte> raw, int offset) => BinaryPrimitives.ReadUInt16BigEndian(raw.Slice(offset, 2));
    private static uint U32(ReadOnlySpan<byte> raw, int offset) => BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(offset, 4));
}