using System.Buffers.Binary;

namespace BasaraFoundry.Game.Utage.Xet;

public sealed record UtageXetInfo(
    int Version,
    int Swizzle,
    int Reserved,
    int AlphaFlags,
    int MipCount,
    int Width,
    int Height,
    int ImageCount,
    int FormatCode,
    int Unknown3,
    int TextureOffset,
    string? BlockFormat,
    int? BlockSizeBytes,
    int? TopLevelSizeBytes)
{
    public bool HasKnownBlockFormat => BlockFormat is not null && BlockSizeBytes is not null;
    public bool CanDecodeTopLevel => Swizzle == 0 && HasKnownBlockFormat;
}

/// <summary>
/// Metadata parser for the PS3 big-endian XET form used by Utage.
/// This deliberately does not treat unknown format codes as DXT5.
/// </summary>
public static class UtageXetReader
{
    private static ReadOnlySpan<byte> Magic => [0x00, 0x58, 0x45, 0x54]; // \0XET

    private static readonly IReadOnlyDictionary<int, string> KnownFormats =
        new Dictionary<int, string>
        {
            [0x13] = "DXT1",
            [0x14] = "DXT1",
            [0x15] = "DXT5", // Utage samples are BC2/BC3-ambiguous; donor swap is byte-compatible.
            [0x17] = "DXT5",
            [0x18] = "DXT5",
            [0x19] = "DXT1", // Verified against real Utage PS3 samples; generic MT tables say BC4.
            [0x2A] = "DXT5",
            [0x2B] = "DXT5",
        };

    public static UtageXetInfo ReadInfo(ReadOnlySpan<byte> raw)
    {
        if (raw.Length < 20)
            throw new InvalidDataException("XET header is truncated; expected at least 20 bytes.");
        if (!raw[..4].SequenceEqual(Magic))
            throw new InvalidDataException("Resource is not a PS3 XET texture.");

        var block4 = BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(4, 4));
        var block8 = BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(8, 4));
        var block12 = BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(12, 4));

        var version = (int)(block4 & 0xFFF);
        var swizzle = (int)((block4 >> 12) & 0xFFF);
        var reserved = (int)((block4 >> 24) & 0xF);
        var alphaFlags = (int)((block4 >> 28) & 0xF);

        var mipCount = (int)(block8 & 0x3F);
        var width = (int)((block8 >> 6) & 0x1FFF);
        var height = (int)((block8 >> 19) & 0x1FFF);

        var imageCount = (int)(block12 & 0xFF);
        var formatCode = (int)((block12 >> 8) & 0xFF);
        var unknown3 = (int)((block12 >> 16) & 0xFFFF);
        var textureOffsetU = BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(16, 4));
        if (textureOffsetU > int.MaxValue)
            throw new InvalidDataException("XET texture offset exceeds Foundry's safe integer range.");
        var textureOffset = (int)textureOffsetU;

        if (width <= 0 || height <= 0)
            throw new InvalidDataException($"XET has invalid dimensions {width}x{height}.");
        if (textureOffset < 20 || textureOffset > raw.Length)
            throw new InvalidDataException($"XET texture offset 0x{textureOffset:X} is outside the resource.");

        KnownFormats.TryGetValue(formatCode, out var blockFormat);
        int? blockSize = blockFormat switch
        {
            "DXT1" => 8,
            "DXT5" => 16,
            _ => null,
        };

        int? topLevelSize = null;
        if (blockSize is int bytesPerBlock)
        {
            topLevelSize = checked(
                Math.Max(1, (width + 3) / 4) *
                Math.Max(1, (height + 3) / 4) *
                bytesPerBlock);

            if ((long)textureOffset + topLevelSize.Value > raw.Length)
            {
                throw new InvalidDataException(
                    $"XET top-level payload overruns the resource: {width}x{height}, " +
                    $"format 0x{formatCode:X2}, offset 0x{textureOffset:X}.");
            }
        }

        return new UtageXetInfo(
            version,
            swizzle,
            reserved,
            alphaFlags,
            mipCount,
            width,
            height,
            imageCount,
            formatCode,
            unknown3,
            textureOffset,
            blockFormat,
            blockSize,
            topLevelSize);
    }

    public static void RequireTopLevelDecodeCapability(UtageXetInfo info)
    {
        ArgumentNullException.ThrowIfNull(info);
        if (info.Swizzle != 0)
            throw new NotSupportedException(
                $"XET declares swizzle {info.Swizzle}; Foundry will not guess a de-swizzle path.");
        if (!info.HasKnownBlockFormat)
            throw new NotSupportedException(
                $"XET format 0x{info.FormatCode:X2} has no certified Utage decoder yet.");
    }
}
