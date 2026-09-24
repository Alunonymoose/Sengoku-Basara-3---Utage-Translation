using System.Buffers.Binary;
using System.Text;
using BasaraFoundry.Game.Utage.Preview;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.RoundTripSmokeTests;

internal static class Program
{
    private static int Main()
    {
        // Independent PS3 0x2A fixture: the BC3 payload stores YCbCr shader
        // channels, and RGB565 colour endpoints are big-endian. This block's
        // raw storage pixel is approximately (Cr=247, coverage=255, Cb=82, Y=76),
        // which must render as opaque red.
        var ps3RedFixture = BuildPs3Bc3StoredForDisplayRedXet();
        var ps3RedDecoded = UtageXetCodec.DecodeTopLevel(ps3RedFixture).Rgba;
        for (var i = 0; i < ps3RedDecoded.Length; i += 4)
        {
            True(ps3RedDecoded[i] >= 240, "0x2A stored YCbCr fixture renders red channel");
            True(ps3RedDecoded[i + 1] <= 16, "0x2A stored YCbCr fixture renders green channel");
            True(ps3RedDecoded[i + 2] <= 16, "0x2A stored YCbCr fixture renders blue channel");
            Equal((byte)255, ps3RedDecoded[i + 3], "0x2A stored G becomes display alpha");
        }

        // Writer proof independent of Foundry's display decoder: inspect the
        // first encoded BC3 storage pixel using a tiny local PS3 block decoder.
        var solidRed = new byte[4 * 4 * 4];
        for (var i = 0; i < solidRed.Length; i += 4)
        {
            solidRed[i] = 255;
            solidRed[i + 3] = 255;
        }
        var redShell = BuildEmptyXet(4, 4, 0x2A);
        var encodedRed = UtageXetCodec.ReplaceSingleLevel(redShell, solidRed).XetBytes;
        var first = DecodeFirstPs3Bc3Pixel(encodedRed.AsSpan(20, 16));
        True(first.R >= 235 && first.G >= 235 && first.B >= 55 && first.B <= 105 &&
             first.A >= 55 && first.A <= 95,
            "0x2A writer emits PS3-endian stored (Cr, alpha, Cb, Y) channels");
        var displayCheck = UtageXetCodec.DecodeTopLevel(encodedRed).Rgba;
        True(displayCheck[0] >= 235 && displayCheck[1] <= 20 && displayCheck[2] <= 20 && displayCheck[3] >= 235,
            "0x2A encoded storage round-trips to visible red");

        var generic2B = BuildEmptyXet(4, 4, 0x2B);
        Throws<NotSupportedException>(
            () => UtageXetCodec.DecodeTopLevel(generic2B),
            "0x2B generic one-plane RGBA preview remains fail-closed");

        var ps3Bc2Fixture = BuildPs3Bc2SolidRedXet(alphaNibble: 8);
        var ps3Bc2Decoded = UtageXetCodec.DecodeTopLevel(ps3Bc2Fixture).Rgba;
        for (var i = 0; i < ps3Bc2Decoded.Length; i += 4)
        {
            True(ps3Bc2Decoded[i] >= 248, "0x15 BC2 fixture decodes red channel");
            True(ps3Bc2Decoded[i + 1] <= 8, "0x15 BC2 fixture decodes green channel");
            True(ps3Bc2Decoded[i + 2] <= 8, "0x15 BC2 fixture decodes blue channel");
            Equal((byte)136, ps3Bc2Decoded[i + 3], "0x15 BC2 fixture decodes explicit 4-bit alpha");
        }
        var ps3Bc2Info = UtageXetReader.ReadInfo(ps3Bc2Fixture);
        Equal("DXT3", ps3Bc2Info.BlockFormat!, "0x15 maps to DXT3/BC2 for read");
        True(!UtageXetCodec.CanEncode(ps3Bc2Info), "0x15 BC2 remains non-writable");
        Throws<NotSupportedException>(
            () => UtageXetCodec.ReplaceSingleLevel(ps3Bc2Fixture, ps3Bc2Decoded),
            "0x15 BC2 production write remains fail-closed");

        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-roundtrip-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            var arcPath = Path.Combine(root, "cockpit1P.arc");
            File.WriteAllBytes(arcPath, BuildTextureArc());
            var candidate = new byte[8 * 8 * 4];
            for (var i = 0; i < candidate.Length; i += 4)
            {
                candidate[i] = 210;
                candidate[i + 1] = 70;
                candidate[i + 2] = 25;
                candidate[i + 3] = 200;
            }

            var result = UtageXetRoundTripService.Create(
                root,
                "cockpit1P.arc",
                0,
                "id\\texture\\jpn\\roulette\\roulette_000_ID_HQ",
                candidate);

            Equal(1, result.Schema, "round-trip schema");
            Equal(8, result.Width, "round-trip width");
            Equal(8, result.Height, "round-trip height");
            Equal("DXT5", result.BlockFormat, "round-trip format");
            Equal(64, result.SourceResourceSha256.Length, "source resource SHA-256 length");
            Equal(64, result.CandidateRgbaSha256.Length, "candidate SHA-256 length");
            Equal(64, result.EncodedXetSha256.Length, "encoded XET SHA-256 length");
            Equal(candidate.Length, result.VerificationRgba.Length, "verification RGBA length");
            True(result.MeanAbsoluteChannelError >= 0 && result.MeanAbsoluteChannelError < 20,
                "BC3 verification mean error is finite and within smoke threshold");
            True(result.MaxChannelError >= 0 && result.MaxChannelError <= 255,
                "BC3 verification max error is bounded");

            Throws<ArgumentException>(() => UtageXetRoundTripService.Create(
                root,
                "cockpit1P.arc",
                0,
                "id\\texture\\jpn\\roulette\\roulette_000_ID_HQ",
                candidate.AsSpan(0, candidate.Length - 4)),
                "round-trip rejects wrong candidate dimensions");

            Console.WriteLine("Round-trip smoke tests passed.");
            return 0;
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    private static byte[] BuildPs3Bc3StoredForDisplayRedXet()
    {
        var raw = BuildEmptyXet(4, 4, 0x2A);
        var block = raw.AsSpan(20, 16);

        // BC3 alpha channel is stored Y for the 0x2A colour shader.
        block[0] = 76;
        block[1] = 0;
        // alpha indices 0 -> Y=76

        // RGB565 endpoint 0 ~= (Cr=247, coverage=255, Cb=82), PS3 BE.
        block[8] = 0xF7;
        block[9] = 0xEA;
        block[10] = 0x07;
        block[11] = 0xE0;
        // colour indices 0 -> endpoint 0 for every pixel.
        return raw;
    }

    private static byte[] BuildPs3Bc2SolidRedXet(byte alphaNibble)
    {
        if (alphaNibble > 0x0F)
            throw new ArgumentOutOfRangeException(nameof(alphaNibble));

        var raw = BuildEmptyXet(4, 4, 0x15);
        var block = raw.AsSpan(20, 16);
        var packedAlpha = (byte)(alphaNibble | (alphaNibble << 4));
        for (var i = 0; i < 8; i++)
            block[i] = packedAlpha;
        block[8] = 0xF8; block[9] = 0x00; // RGB565 red, PS3 big-endian
        block[10] = 0x07; block[11] = 0xE0; // RGB565 green, PS3 big-endian
        // colour index 0 for every pixel -> red endpoint.
        return raw;
    }

    private static byte[] BuildEmptyXet(int width, int height, int format)
    {
        const int textureOffset = 20;
        var bytesPerBlock = format == 0x19 ? 8 : 16;
        var payloadSize = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * bytesPerBlock;
        var raw = new byte[textureOffset + payloadSize];
        raw[0] = 0;
        raw[1] = (byte)'X';
        raw[2] = (byte)'E';
        raw[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(4, 4), (uint)(0x97 | (2 << 28)));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(12, 4), (uint)(1 | (format << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(16, 4), textureOffset);
        return raw;
    }

    private static (byte R, byte G, byte B, byte A) DecodeFirstPs3Bc3Pixel(ReadOnlySpan<byte> block)
    {
        if (block.Length != 16)
            throw new ArgumentException("BC3 block must be 16 bytes.", nameof(block));

        var a0 = block[0];
        var a1 = block[1];
        Span<byte> alpha = stackalloc byte[8];
        alpha[0] = a0; alpha[1] = a1;
        if (a0 > a1)
        {
            alpha[2] = (byte)((6 * a0 + a1) / 7);
            alpha[3] = (byte)((5 * a0 + 2 * a1) / 7);
            alpha[4] = (byte)((4 * a0 + 3 * a1) / 7);
            alpha[5] = (byte)((3 * a0 + 4 * a1) / 7);
            alpha[6] = (byte)((2 * a0 + 5 * a1) / 7);
            alpha[7] = (byte)((a0 + 6 * a1) / 7);
        }
        else
        {
            alpha[2] = (byte)((4 * a0 + a1) / 5);
            alpha[3] = (byte)((3 * a0 + 2 * a1) / 5);
            alpha[4] = (byte)((2 * a0 + 3 * a1) / 5);
            alpha[5] = (byte)((a0 + 4 * a1) / 5);
            alpha[6] = 0;
            alpha[7] = 255;
        }
        ulong aidx = 0;
        for (var i = 0; i < 6; i++)
            aidx |= (ulong)block[2 + i] << (8 * i);
        var a = alpha[(int)(aidx & 7)];

        var c0 = BinaryPrimitives.ReadUInt16BigEndian(block.Slice(8, 2));
        var c1 = BinaryPrimitives.ReadUInt16BigEndian(block.Slice(10, 2));
        var p0 = Rgb565(c0);
        var p1 = Rgb565(c1);
        var palette = new (byte R, byte G, byte B)[4];
        palette[0] = p0; palette[1] = p1;
        palette[2] = ((byte)((2 * p0.R + p1.R) / 3), (byte)((2 * p0.G + p1.G) / 3), (byte)((2 * p0.B + p1.B) / 3));
        palette[3] = ((byte)((p0.R + 2 * p1.R) / 3), (byte)((p0.G + 2 * p1.G) / 3), (byte)((p0.B + 2 * p1.B) / 3));
        var cidx = BinaryPrimitives.ReadUInt32LittleEndian(block.Slice(12, 4));
        var c = palette[(int)(cidx & 3)];
        return (c.R, c.G, c.B, a);
    }

    private static (byte R, byte G, byte B) Rgb565(ushort v)
    {
        var r = (v >> 11) & 31;
        var g = (v >> 5) & 63;
        var b = v & 31;
        return (
            (byte)((r * 255 + 15) / 31),
            (byte)((g * 255 + 31) / 63),
            (byte)((b * 255 + 15) / 31));
    }

    private static byte[] BuildTextureArc()
    {
        const int tableStart = 8;
        const int entrySize = 80;
        const int payloadOffset = 0x800;
        var name = Encoding.ASCII.GetBytes("id\\texture\\jpn\\roulette\\roulette_000_ID_HQ");
        var payload = BuildXet();
        var arc = new byte[payloadOffset + payload.Length];
        arc[0] = 0;
        arc[1] = (byte)'C';
        arc[2] = (byte)'R';
        arc[3] = (byte)'A';
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(4, 2), 8);
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(6, 2), 1);
        var record = arc.AsSpan(tableStart, entrySize);
        name.CopyTo(record);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), 0x241F5DEB);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), (uint)payload.Length);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), (uint)(payload.Length << 3));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), payloadOffset);
        payload.CopyTo(arc.AsSpan(payloadOffset));
        return arc;
    }

    private static byte[] BuildXet() => BuildEmptyXet(8, 8, 0x2A);

    private static void Equal<T>(T expected, T actual, string label) where T : notnull
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new Exception($"FAIL {label}: expected {expected}, got {actual}");
        Console.WriteLine($"PASS {label}");
    }

    private static void True(bool value, string label)
    {
        if (!value)
            throw new Exception($"FAIL {label}");
        Console.WriteLine($"PASS {label}");
    }

    private static void Throws<T>(Action action, string label) where T : Exception
    {
        try
        {
            action();
        }
        catch (T)
        {
            Console.WriteLine($"PASS {label}");
            return;
        }
        throw new Exception($"FAIL {label}: expected {typeof(T).Name}");
    }
}
