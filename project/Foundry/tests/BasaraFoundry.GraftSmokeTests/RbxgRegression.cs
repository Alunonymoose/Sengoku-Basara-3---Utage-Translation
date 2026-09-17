using System.Buffers.Binary;
using System.Runtime.CompilerServices;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

internal static class RbxgRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        var stored = new byte[]
        {
            10, 20, 30, 40,
            50, 60, 70, 80,
            90, 100, 110, 120,
            130, 140, 150, 160,
        };
        var planes = UtageRbxgCodec.UnpackStoredRgba(stored);
        var repacked = UtageRbxgCodec.PackStoredRgba(planes.BaseRgba, planes.MaskRgba);
        Assert(stored.AsSpan().SequenceEqual(repacked), "RBxG stored-channel split/join is exact");
        Assert(planes.BaseRgba.AsSpan(0, 4).SequenceEqual(new byte[] { 40, 40, 40, 20 }), "RBxG base mapping is A,A,A,G");
        Assert(planes.MaskRgba.AsSpan(0, 4).SequenceEqual(new byte[] { 10, 30, 0, 255 }), "RBxG mask mapping is R,B,0,255");

        const int width = 4;
        const int height = 4;
        const int textureOffset = 20;
        var shell = new byte[textureOffset + 16];
        shell[0] = 0;
        shell[1] = (byte)'X';
        shell[2] = (byte)'E';
        shell[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(4, 4), 0x97u);
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(12, 4), (uint)(1 | (0x2B << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(16, 4), textureOffset);

        var baseRgba = new byte[width * height * 4];
        var maskRgba = new byte[width * height * 4];
        for (var i = 0; i < width * height; i++)
        {
            var o = i * 4;
            baseRgba[o] = baseRgba[o + 1] = baseRgba[o + 2] = (byte)(80 + i);
            baseRgba[o + 3] = (byte)(180 + (i % 16));
            maskRgba[o] = (byte)(20 + i);
            maskRgba[o + 1] = (byte)(40 + i);
            maskRgba[o + 2] = 0;
            maskRgba[o + 3] = 255;
        }

        ExpectThrows<NotSupportedException>(() => UtageXetCodec.ReplaceSingleLevel(shell, baseRgba),
            "plain RGBA writer refuses format 0x2B");
        var built = UtageXetCodec.ReplaceRbxgSingleLevel(shell, baseRgba, maskRgba);
        Assert(UtageXetReader.ReadInfo(built.XetBytes).FormatCode == 0x2B, "dedicated RBxG writer preserves format id");
        Assert(built.VerificationPlanes.BaseRgba.Length == baseRgba.Length, "RBxG verification base plane dimensions preserved");
        Assert(built.VerificationPlanes.MaskRgba.Length == maskRgba.Length, "RBxG verification mask plane dimensions preserved");

        var badBase = planes.BaseRgba.ToArray();
        badBase[0] ^= 1;
        ExpectThrows<InvalidDataException>(() => UtageRbxgCodec.PackStoredRgba(badBase, planes.MaskRgba),
            "non-canonical RBxG base plane fails closed");

        Console.WriteLine("PASS RBxG regression");
    }

    private static void Assert(bool condition, string label)
    {
        if (!condition) throw new Exception("FAIL RBxG regression: " + label);
        Console.WriteLine("PASS " + label);
    }

    private static void ExpectThrows<T>(Action action, string label) where T : Exception
    {
        try { action(); }
        catch (T) { Console.WriteLine("PASS " + label); return; }
        throw new Exception($"FAIL RBxG regression: {label}; expected {typeof(T).Name}");
    }
}
