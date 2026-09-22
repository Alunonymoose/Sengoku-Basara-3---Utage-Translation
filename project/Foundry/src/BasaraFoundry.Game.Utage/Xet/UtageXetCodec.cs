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

public sealed record XetRbxgBuildResult(
    byte[] XetBytes,
    byte[] EncodedPayload,
    XetDecodedImage VerificationStoredDecode,
    UtageRbxgPlanes VerificationPlanes);

/// <summary>
/// Certified top-level BCn codec boundary for Utage PS3 XET resources.
/// DecodeTopLevel returns the STORED BCn RGBA channels. For format 0x2B those
/// channels are not artist-facing RGBA; use DecodeRbxgTopLevel instead.
/// Plain write support excludes 0x2B so a normal RGBA buffer can never be
/// accidentally written into an RBxG texture.
/// </summary>
public static class UtageXetCodec
{
    private static readonly HashSet<int> PlainWritableDxt5Codes = [0x17, 0x18, 0x2A];

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

    public static UtageRbxgPlanes DecodeRbxgTopLevel(ReadOnlySpan<byte> raw)
    {
        var stored = DecodeTopLevel(raw);
        if (stored.Info.FormatCode != 0x2B)
            throw new NotSupportedException($"XET format 0x{stored.Info.FormatCode:X2} is not RBxG (0x2B).");
        return UtageRbxgCodec.UnpackStoredRgba(stored.Rgba);
    }

    public static bool CanEncode(UtageXetInfo info) =>
        info.Swizzle == 0 &&
        info.BlockFormat == "DXT5" &&
        PlainWritableDxt5Codes.Contains(info.FormatCode);

    public static bool CanEncodeRbxg(UtageXetInfo info) =>
        info.Swizzle == 0 &&
        info.FormatCode == 0x2B &&
        info.BlockFormat == "DXT5";

    public static XetSingleLevelBuildResult ReplaceSingleLevel(
        ReadOnlySpan<byte> originalXet,
        ReadOnlySpan<byte> rgba)
    {
        var info = UtageXetReader.ReadInfo(originalXet);
        RequireEncodingCapability(info);
        ValidateSingleLevelWrite(originalXet, info, rgba.Length);

        var encoded = EncodeBc3(rgba, info.Width, info.Height, info.TopLevelSizeBytes!.Value);
        var output = originalXet.ToArray();
        encoded.CopyTo(output.AsSpan(info.TextureOffset, encoded.Length));
        var verification = DecodeTopLevel(output);
        return new XetSingleLevelBuildResult(output, encoded, verification);
    }

    public static XetRbxgBuildResult ReplaceRbxgSingleLevel(
        ReadOnlySpan<byte> originalXet,
        ReadOnlySpan<byte> baseRgba,
        ReadOnlySpan<byte> maskRgba)
    {
        var info = UtageXetReader.ReadInfo(originalXet);
        RequireRbxgEncodingCapability(info);
        ValidateSingleLevelWrite(originalXet, info, baseRgba.Length);
        if (maskRgba.Length != baseRgba.Length)
            throw new ArgumentException("RBxG base/mask plane lengths disagree.", nameof(maskRgba));

        var storedRgba = UtageRbxgCodec.PackStoredRgba(baseRgba, maskRgba);
        var encoded = EncodeBc3(storedRgba, info.Width, info.Height, info.TopLevelSizeBytes!.Value);
        var output = originalXet.ToArray();
        encoded.CopyTo(output.AsSpan(info.TextureOffset, encoded.Length));
        var verificationStored = DecodeTopLevel(output);
        var verificationPlanes = UtageRbxgCodec.UnpackStoredRgba(verificationStored.Rgba);
        return new XetRbxgBuildResult(output, encoded, verificationStored, verificationPlanes);
    }

    public static void RequireEncodingCapability(UtageXetInfo info)
    {
        ArgumentNullException.ThrowIfNull(info);
        UtageXetReader.RequireTopLevelDecodeCapability(info);
        if (info.FormatCode == 0x2B)
        {
            throw new NotSupportedException(
                "XET format 0x2B uses the Utage PS3 RBxG channel layout. Plain RGBA writing is refused; use the dedicated RBxG path.");
        }
        if (!CanEncode(info))
        {
            throw new NotSupportedException(
                $"Foundry v0.1 has not certified plain-RGBA writing XET format 0x{info.FormatCode:X2} ({info.BlockFormat ?? "unknown"}).");
        }
    }

    public static void RequireRbxgEncodingCapability(UtageXetInfo info)
    {
        ArgumentNullException.ThrowIfNull(info);
        UtageXetReader.RequireTopLevelDecodeCapability(info);
        if (!CanEncodeRbxg(info))
            throw new NotSupportedException($"XET format 0x{info.FormatCode:X2} is not a certified RBxG write target.");
    }

    private static void ValidateSingleLevelWrite(ReadOnlySpan<byte> originalXet, UtageXetInfo info, int rgbaLength)
    {
        var expectedRgba = checked(info.Width * info.Height * 4);
        if (rgbaLength != expectedRgba)
            throw new ArgumentException($"RGBA candidate contains {rgbaLength} bytes; {info.Width}x{info.Height} requires {expectedRgba}.");

        var topLevelBytes = info.TopLevelSizeBytes
            ?? throw new NotSupportedException("XET encoded byte size is unknown.");
        var expectedEnd = checked(info.TextureOffset + topLevelBytes);
        if (info.MipCount > 1 || originalXet.Length != expectedEnd)
        {
            throw new NotSupportedException(
                "This XET contains mip/trailing texture data. Use a certified mip-chain writer; Foundry will not replace only the top level.");
        }
    }

    private static byte[] EncodeBc3(ReadOnlySpan<byte> rgba, int width, int height, int expectedBytes)
    {
        var encoder = new BcEncoder();
        encoder.OutputOptions.Format = CompressionFormat.Bc3;
        encoder.OutputOptions.Quality = CompressionQuality.BestQuality;
        encoder.OutputOptions.GenerateMipMaps = false;
        var levels = encoder.EncodeToRawBytes(rgba.ToArray(), width, height, PixelFormat.Rgba32);
        if (levels.Length != 1)
            throw new InvalidDataException($"BCn encoder returned {levels.Length} levels for a single-level request.");
        var encoded = levels[0];
        if (encoded.Length != expectedBytes)
            throw new InvalidDataException($"BC3 encoder returned {encoded.Length} bytes; XET requires {expectedBytes}.");
        return encoded;
    }

    private static CompressionFormat ToCompressionFormat(UtageXetInfo info) => info.BlockFormat switch
    {
        "DXT1" => CompressionFormat.Bc1,
        "DXT5" => CompressionFormat.Bc3,
        _ => throw new NotSupportedException(
            $"No BCn decoder mapping exists for XET format 0x{info.FormatCode:X2}.")
    };
}
