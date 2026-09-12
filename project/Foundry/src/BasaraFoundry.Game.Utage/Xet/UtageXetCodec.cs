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
/// Read support follows the XET metadata capability table. Write support is
/// intentionally narrower: v0.1 only re-encodes the DXT5 codes already proven
/// in the Utage project. DXT1 and the ambiguous 0x15 form remain read-only
/// until real-game fixtures certify Foundry's writer.
/// </summary>
public static class UtageXetCodec
{
    private static readonly HashSet<int> WritableDxt5Codes = [0x17, 0x18, 0x2A, 0x2B];

    public static XetDecodedImage DecodeTopLevel(ReadOnlySpan<byte> raw)
    {
        var info = UtageXetReader.ReadInfo(raw);
        UtageXetReader.RequireTopLevelDecodeCapability(info);
        var format = ToCompressionFormat(info);
        var payloadLength = info.TopLevelSizeBytes
            ?? throw new NotSupportedException("XET top-level byte size is unknown for this format.");
        var payload = raw.Slice(info.TextureOffset, payloadLength).ToArray();

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

        return new XetDecodedImage(info.Width, info.Height, rgba, info);
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

        var encoder = new BcEncoder();
        encoder.OutputOptions.Format = CompressionFormat.Bc3;
        encoder.OutputOptions.Quality = CompressionQuality.BestQuality;
        encoder.OutputOptions.GenerateMipMaps = false;

        var levels = encoder.EncodeToRawBytes(rgba, info.Width, info.Height, PixelFormat.Rgba32);
        if (levels.Length != 1)
            throw new InvalidDataException($"BCn encoder returned {levels.Length} levels for a single-level request.");
        var encoded = levels[0];
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
        "DXT5" => CompressionFormat.Bc3,
        _ => throw new NotSupportedException(
            $"No BCn decoder mapping exists for XET format 0x{info.FormatCode:X2}.")
    };
}
