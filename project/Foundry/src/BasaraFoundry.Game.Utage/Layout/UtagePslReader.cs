using System.Buffers.Binary;
using System.Text;

namespace BasaraFoundry.Game.Utage.Layout;

public sealed record UtagePslNode(
    int Index,
    string Group,
    int Offset,
    string Name,
    string Texture,
    int? NameStringOffset,
    int? TextureStringOffset,
    float X,
    float Y,
    IReadOnlyList<uint> UvWords,
    IReadOnlyList<uint> ColourWords,
    byte[] RawRecord);

public sealed record UtagePslInfo(
    uint Version,
    ushort RenderNodeCount,
    ushort AuxiliaryNodeCount,
    int RecordCount,
    int StringTableOffset,
    IReadOnlyList<UtagePslNode> Nodes);

/// <summary>
/// Structured, read-only parser for the real Utage PSL v0x21 family proven by
/// title.arc and the legacy mt_arc_explorer fixtures. Record size is 0xB0/176.
/// Unknown record fields are deliberately retained in RawRecord; this parser
/// does not imply a generic layout writer is safe.
/// </summary>
public static class UtagePslReader
{
    private const int HeaderSize = 16;
    private const int RecordSize = 176;

    public static UtagePslInfo Read(ReadOnlySpan<byte> raw)
    {
        if (raw.Length < HeaderSize || raw[0] != 0 || raw[1] != (byte)'P' || raw[2] != (byte)'S' || raw[3] != (byte)'L')
            throw new InvalidDataException("Resource is not a PSL layout.");

        var version = U32(raw, 4);
        var groupA = U16(raw, 12);
        var groupB = U16(raw, 14);
        var count = checked(groupA + groupB);
        var recordsEnd = checked(HeaderSize + count * RecordSize);
        if (recordsEnd > raw.Length)
            throw new InvalidDataException("PSL node records overrun resource.");

        var stringTableOffset = LocateStringTable(raw, count);
        var cursor = checked(stringTableOffset + 7);
        var names = new (string Name, string Texture, int NameOffset, int TextureOffset)[groupA];
        for (var i = 0; i < groupA; i++)
        {
            var name = ReadPaddedString(raw, cursor);
            cursor = name.NextOffset;
            var texture = ReadPaddedString(raw, cursor);
            cursor = texture.NextOffset;
            names[i] = (name.Value, texture.Value, name.PayloadOffset, texture.PayloadOffset);
        }

        var nodes = new List<UtagePslNode>(count);
        for (var index = 0; index < count; index++)
        {
            var offset = checked(HeaderSize + index * RecordSize);
            var record = raw.Slice(offset, RecordSize);
            var isRender = index < groupA;
            var uvWords = new[] { U32(record, 0x84), U32(record, 0x88), U32(record, 0x8C), U32(record, 0x90) };
            var colourWords = new[] { U32(record, 0x94), U32(record, 0x98), U32(record, 0x9C), U32(record, 0xA0) };

            nodes.Add(new UtagePslNode(
                index,
                isRender ? "A/render" : "B/aux",
                offset,
                isRender ? names[index].Name : $"group_b_{index - groupA:000}",
                isRender ? names[index].Texture : string.Empty,
                isRender ? names[index].NameOffset : null,
                isRender ? names[index].TextureOffset : null,
                F32(record, 0),
                F32(record, 4),
                uvWords,
                colourWords,
                record.ToArray()));
        }

        return new UtagePslInfo(version, groupA, groupB, count, stringTableOffset, nodes);
    }

    private static int LocateStringTable(ReadOnlySpan<byte> raw, int recordCount)
    {
        var start = checked(HeaderSize + recordCount * RecordSize);
        for (var offset = start; offset <= raw.Length - 12; offset += 4)
        {
            if (!raw.Slice(offset, 4).SequenceEqual(new byte[] { 0xFF, 0xFF, 0xFF, 0xFF }))
                continue;

            var length = raw[offset + 7];
            if (length is < 1 or > 128 || offset + 8 + length > raw.Length)
                continue;

            var value = raw.Slice(offset + 8, length);
            if (value[^1] == 0 && value[..^1].SequenceEqual("SysRoot"u8))
                return offset;
        }
        throw new InvalidDataException("PSL string table could not be located with the proven SysRoot sentinel.");
    }

    private static (string Value, int NextOffset, int PayloadOffset) ReadPaddedString(ReadOnlySpan<byte> raw, int offset)
    {
        if ((uint)offset >= (uint)raw.Length)
            throw new InvalidDataException("PSL string offset is outside the resource.");
        var length = raw[offset];
        offset++;
        var payloadOffset = offset;
        var end = checked(offset + length);
        if (length == 0 || end > raw.Length)
            throw new InvalidDataException("PSL packed string is invalid.");

        var payload = raw.Slice(offset, length);
        var actualLength = payload.Length > 0 && payload[^1] == 0 ? payload.Length - 1 : payload.Length;
        var value = Encoding.ASCII.GetString(payload[..actualLength]);
        offset = end;
        while (offset < raw.Length && raw[offset] == 0)
            offset++;
        return (value, offset, payloadOffset);
    }

    private static ushort U16(ReadOnlySpan<byte> raw, int offset) => BinaryPrimitives.ReadUInt16BigEndian(raw.Slice(offset, 2));
    private static uint U32(ReadOnlySpan<byte> raw, int offset) => BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(offset, 4));
    private static float F32(ReadOnlySpan<byte> raw, int offset) => BitConverter.Int32BitsToSingle(BinaryPrimitives.ReadInt32BigEndian(raw.Slice(offset, 4)));
}