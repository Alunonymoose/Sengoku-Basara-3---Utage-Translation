using BCnEncoder.Decoder;
using BCnEncoder.Encoder;
using BCnEncoder.Shared;

namespace BasaraFoundry.Game.Utage.Xet;

public sealed record XetDecodedImage(
    int Width,
    int Height,
    byte[] Rgba,
    UtageXetInfo Info);

public sealed record XetSingleLevelBuildResult(
    byte[] XetBytes,
    byte[] EncodedPayload,
    XetDecodedImage VerificationDecode);

/// <summary>
/// Certified top-level BCn codec boundary for Utage PS3 XET resources.
///
/// Read support follows the XET metadata capability table. XET header/table
/// fields are big-endian on PS3, but verified Utage BC payloads use the normal
/// BCn byte layout expected by BCnEncoder.Net. Do not infer or apply a colour
/// endpoint byte swap from container endianness. The 2026-09-24 title_004
/// runtime failure explicitly disproved that synthetic assumption.
///
/// Write support is intentionally narrower: v0.1 only re-encodes the DXT5
/// codes already proven in the Utage project. DXT1 and fixture-proven 0x15
/// DXT3/BC2 remain read-only until real-game write/runtime fixtures certify
/// those paths.
/// </summary>
public static class UtageXetCodec
{
    private static readonly HashSet<int> WritableDxt5Codes = [0x17, 0x18, 0x2A];

    public static XetDecodedImage DecodeTopLevel(ReadOnlySpan<byte> raw)
    {
        var info = UtageXetReader.ReadInfo(raw);
        UtageXetReader.RequireTopLevelDecodeCapability(info);
        var format = ToCompressionFormat(info);
        var payloadLength = info.TopLevelSizeBytes
            ?? throw new NotSupportedException("XET top-level byte size is unknown for this format.");
        var payload = raw.Slice(info.TextureOffset, payloadLength).ToArray();

        // Verified Utage 0x2A/title_004 uses standard BCn payload byte order.
        // XET container fields are big-endian, but the BC payload is not
        // endpoint-byte-swapped.

        var decoder = new BcDecoder();
        var pixels = decoder.DecodeRaw(payload, info.Width, info.Height, format);
        if (pixels.Length != checked(info.Width * info.Height))
            throw new InvalidDataException("BCn decoder returned an unexpected pixel count.");

        var rgba = new byte[checked(pixels.Length * 4)];
        for (var i = 0; i < pixels.Length; i++)
        {
            var p = pixels[i];
            var offset = i * 4;
            rgba[offset] = p.r;
            rgba[offset + 1] = p.g;
            rgba[offset + 2] = p.b;
            rgba[offset + 3] = p.a;
        }

        var displayRgba = StorageToDisplayRgba(info, rgba);
        return new XetDecodedImage(info.Width, info.Height, displayRgba, info);
    }

    public static bool CanEncode(UtageXetInfo info) =>
        info.Swizzle == 0 &&
        info.BlockFormat == "DXT5" &&
        WritableDxt5Codes.Contains(info.FormatCode);

    public static XetSingleLevelBuildResult ReplaceSingleLevel(
        ReadOnlySpan<byte> originalXet,
        ReadOnlySpan<byte> rgba)
    {
        var info = UtageXetReader.ReadInfo(originalXet);
        RequireEncodingCapability(info);

        var expectedRgba = checked(info.Width * info.Height * 4);
        if (rgba.Length != expectedRgba)
        {
            throw new ArgumentException(
                $"RGBA candidate contains {rgba.Length} bytes; {info.Width}x{info.Height} requires {expectedRgba}.",
                nameof(rgba));
        }

        var topLevelBytes = info.TopLevelSizeBytes
            ?? throw new NotSupportedException("XET encoded byte size is unknown.");
        var expectedEnd = checked(info.TextureOffset + topLevelBytes);

        // This entry point is deliberately single-level. Refuse to leave old
        // Japanese mip data behind or to reinterpret unknown trailing data.
        if (info.MipCount > 1 || originalXet.Length != expectedEnd)
        {
            throw new NotSupportedException(
                "This XET contains mip/trailing texture data. Use a certified mip-chain writer; " +
                "Foundry will not replace only the top level.");
        }

        var encoded = EncodeTopLevelPayloadForPs3(info, rgba);
        if (encoded.Length != topLevelBytes)
        {
            throw new InvalidDataException(
                $"BC3 encoder returned {encoded.Length} bytes; XET requires {topLevelBytes}.");
        }

        var output = originalXet.ToArray();
        encoded.CopyTo(output.AsSpan(info.TextureOffset, topLevelBytes));

        // Verify the exact bytes that would be inserted, not the source RGBA.
        var verification = DecodeTopLevel(output);
        return new XetSingleLevelBuildResult(output, encoded, verification);
    }

    internal static byte[] EncodeTopLevelPayloadForPs3(
        UtageXetInfo info,
        ReadOnlySpan<byte> displayRgba)
    {
        ArgumentNullException.ThrowIfNull(info);
        RequireEncodingCapability(info);

        var storageRgba = DisplayToStorageRgba(info, displayRgba);
        return EncodeBc3StoragePayloadForPs3(storageRgba, info.Width, info.Height);
    }

    private static byte[] EncodeBc3StoragePayloadForPs3(ReadOnlySpan<byte> storageRgba, int width, int height)
    {
        var expectedRgba = checked(width * height * 4);
        if (storageRgba.Length != expectedRgba)
            throw new ArgumentException($"RGBA contains {storageRgba.Length} bytes; {width}x{height} requires {expectedRgba}.", nameof(storageRgba));

        var encoder = new BcEncoder();
        encoder.OutputOptions.Format = CompressionFormat.Bc3;
        // Kuriimu2/Kanvas parity: BCnEncoder.Net 2.2.1 Balanced, no mipmaps.
        encoder.OutputOptions.Quality = CompressionQuality.Balanced;
        encoder.OutputOptions.GenerateMipMaps = false;

        var levels = encoder.EncodeToRawBytes(storageRgba.ToArray(), width, height, PixelFormat.Rgba32);
        if (levels.Length != 1)
            throw new InvalidDataException($"BCn encoder returned {levels.Length} levels for a single-level request.");

        return levels[0];
    }

    private static byte[] StorageToDisplayRgba(UtageXetInfo info, ReadOnlySpan<byte> storageRgba)
    {
        if (info.FormatCode != 0x2A)
            return storageRgba.ToArray();

        var output = new byte[storageRgba.Length];
        for (var i = 0; i < storageRgba.Length; i += 4)
        {
            var storedR = storageRgba[i];
            var storedG = storageRgba[i + 1];
            var storedB = storageRgba[i + 2];
            var storedA = storageRgba[i + 3];

            var y = storedA;
            var cb = storedB - 123;
            var cr = storedR - 123;

            output[i] = ClampByte(y + 1.402 * cr);
            output[i + 1] = ClampByte(y - 0.344136 * cb - 0.714136 * cr);
            output[i + 2] = ClampByte(y + 1.772 * cb);
            output[i + 3] = storedG;
        }
        return output;
    }

    private static byte[] DisplayToStorageRgba(UtageXetInfo info, ReadOnlySpan<byte> displayRgba)
    {
        var expected = checked(info.Width * info.Height * 4);
        if (displayRgba.Length != expected)
            throw new ArgumentException($"RGBA contains {displayRgba.Length} bytes; {info.Width}x{info.Height} requires {expected}.", nameof(displayRgba));

        if (info.FormatCode != 0x2A)
            return displayRgba.ToArray();

        var output = new byte[displayRgba.Length];
        for (var i = 0; i < displayRgba.Length; i += 4)
        {
            var r = displayRgba[i];
            var g = displayRgba[i + 1];
            var b = displayRgba[i + 2];
            var a = displayRgba[i + 3];

            var y = 0.299 * r + 0.587 * g + 0.114 * b;
            var cb = 123 - 0.168736 * r - 0.331264 * g + 0.5 * b;
            var cr = 123 + 0.5 * r - 0.418688 * g - 0.081312 * b;

            // Kuriimu2 PS3 0x2A Write() stores RGBA = (Cr, input alpha, Cb, Y).
            output[i] = ClampByte(cr);
            output[i + 1] = a;
            output[i + 2] = ClampByte(cb);
            output[i + 3] = ClampByte(y);
        }
        return output;
    }

    private static byte ClampByte(double value) =>
        (byte)Math.Clamp((int)value, 0, 255);

    public static void RequireEncodingCapability(UtageXetInfo info)
    {
        ArgumentNullException.ThrowIfNull(info);
        UtageXetReader.RequireTopLevelDecodeCapability(info);
        if (!CanEncode(info))
        {
            throw new NotSupportedException(
                $"Foundry v0.1 has not certified writing XET format 0x{info.FormatCode:X2} ({info.BlockFormat ?? "unknown"}).");
        }
    }

    private static CompressionFormat ToCompressionFormat(UtageXetInfo info) => info.BlockFormat switch
    {
        "DXT1" => CompressionFormat.Bc1,
        "DXT3" => CompressionFormat.Bc2,
        "DXT5" => CompressionFormat.Bc3,
        _ => throw new NotSupportedException(
            $"No BCn decoder mapping exists for XET format 0x{info.FormatCode:X2}.")
    };
}
