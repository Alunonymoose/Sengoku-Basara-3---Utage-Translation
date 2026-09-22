using System.Buffers.Binary;
using System.Runtime.CompilerServices;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

internal static class YcbcrFormatRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        // Exact Kuriimu2 write transform: opaque red -> stored (Cr,A,Cb,Y).
        var red = new byte[] { 255, 0, 0, 255 };
        var storedRed = UtageYcbcrColorShader.DisplayToStored(red);
        Equal((byte)250, storedRed[0], "YCbCr red Cr");
        Equal((byte)255, storedRed[1], "YCbCr red alpha");
        Equal((byte)79, storedRed[2], "YCbCr red Cb");
        Equal((byte)76, storedRed[3], "YCbCr red Y");

        var displayRed = UtageYcbcrColorShader.StoredToDisplay(storedRed);
        Equal((byte)254, displayRed[0], "YCbCr red round-trip R");
        Equal((byte)0, displayRed[1], "YCbCr red round-trip G");
        Equal((byte)0, displayRed[2], "YCbCr red round-trip B");
        Equal((byte)255, displayRed[3], "YCbCr red round-trip A");

        var xet2A = BuildXet(0x2A);
        var candidate = new byte[8 * 8 * 4];
        for (var i = 0; i < candidate.Length; i += 4)
        {
            candidate[i] = 30;
            candidate[i + 1] = 120;
            candidate[i + 2] = 220;
            candidate[i + 3] = 200;
        }

        Throws<NotSupportedException>(
            () => UtageXetCodec.ReplaceSingleLevel(xet2A, candidate),
            "plain RGBA writer rejects 0x2A");

        var ycbcrBuild = UtageXetCodec.ReplaceYcbcrSingleLevel(xet2A, candidate);
        Equal(candidate.Length, ycbcrBuild.VerificationDisplayDecode.Rgba.Length,
            "0x2A YCbCr verification display length");
        True(UtageXetCodec.CanEncodeForEditing(ycbcrBuild.VerificationDisplayDecode.Info),
            "0x2A reports dedicated editing capability");

        var xet2B = BuildXet(0x2B);
        Throws<NotSupportedException>(
            () => UtageXetCodec.ReplaceSingleLevel(xet2B, candidate),
            "plain RGBA writer rejects 0x2B");
        Throws<NotSupportedException>(
            () => UtageXetCodec.ReplaceYcbcrSingleLevel(xet2B, candidate),
            "0x2B production writer remains fail-closed");

        var xet15 = BuildXet(0x15);
        var info15 = UtageXetReader.ReadInfo(xet15);
        True(!info15.HasKnownBlockFormat, "ambiguous 0x15 has no certified block decoder");
        Throws<NotSupportedException>(
            () => UtageXetReader.RequireTopLevelDecodeCapability(info15),
            "ambiguous 0x15 decode fails closed");

        Console.WriteLine("PASS YCbCr/format semantic regression");
    }

    private static byte[] BuildXet(int formatCode)
    {
        const int width = 8;
        const int height = 8;
        const int textureOffset = 20;
        const int payloadSize = 64;
        var raw = new byte[textureOffset + payloadSize];
        raw[0] = 0;
        raw[1] = (byte)'X';
        raw[2] = (byte)'E';
        raw[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(4, 4), (uint)(0x97 | (2 << 28)));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(12, 4), (uint)(1 | (formatCode << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(16, 4), textureOffset);
        return raw;
    }

    private static void Equal<T>(T expected, T actual, string label) where T : notnull
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new Exception($"FAIL {label}: expected {expected}, got {actual}");
        Console.WriteLine("PASS " + label);
    }

    private static void True(bool condition, string label)
    {
        if (!condition) throw new Exception("FAIL " + label);
        Console.WriteLine("PASS " + label);
    }

    private static void Throws<T>(Action action, string label) where T : Exception
    {
        try { action(); }
        catch (T) { Console.WriteLine("PASS " + label); return; }
        throw new Exception($"FAIL {label}: expected {typeof(T).Name}");
    }
}
