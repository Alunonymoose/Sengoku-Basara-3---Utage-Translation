using System.Buffers.Binary;
using System.Runtime.CompilerServices;
using System.Text;
using BasaraFoundry.Game.Utage.Arc;

namespace BasaraFoundry.GraftSmokeTests;

internal static class ArcOpaqueRegionRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        var withOpaqueGap = BuildTwoEntryArc(nonZeroGap: true);
        ExpectThrows<NotSupportedException>(
            () => UtageArcWriter.Rebuild(withOpaqueGap, new Dictionary<int, byte[]> { [0] = new byte[] { 9, 9, 9, 9 } }),
            "non-zero inter-member ARC gap fails closed");

        var withOpaqueTrailer = BuildOneEntryArc(trailerLength: 16, nonZeroTrailer: true);
        ExpectThrows<NotSupportedException>(
            () => UtageArcWriter.Rebuild(withOpaqueTrailer, new Dictionary<int, byte[]> { [0] = new byte[] { 5, 6, 7, 8 } }),
            "non-zero ARC trailer fails closed");

        var zeroTrailer = BuildOneEntryArc(trailerLength: 16, nonZeroTrailer: false);
        var rebuilt = UtageArcWriter.Rebuild(zeroTrailer, new Dictionary<int, byte[]> { [0] = new byte[] { 5, 6, 7, 8 } });
        Assert(rebuilt.Bytes.Length == zeroTrailer.Length, "zero trailer length preserved");
        Assert(rebuilt.Bytes.AsSpan(rebuilt.Bytes.Length - 16).ToArray().All(b => b == 0), "zero trailer bytes preserved as zero");

        Console.WriteLine("PASS ARC opaque-region regression");
    }

    private static byte[] BuildOneEntryArc(int trailerLength, bool nonZeroTrailer)
    {
        const int payloadOffset = 128;
        var payload = new byte[] { 1, 2, 3, 4 };
        var arc = new byte[payloadOffset + payload.Length + trailerLength];
        WriteHeader(arc, 1);
        WriteEntry(arc.AsSpan(8, 80), "one", payload.Length, payloadOffset);
        payload.CopyTo(arc.AsSpan(payloadOffset));
        if (nonZeroTrailer && trailerLength > 0)
            arc[payloadOffset + payload.Length + trailerLength - 1] = 0x7A;
        return arc;
    }

    private static byte[] BuildTwoEntryArc(bool nonZeroGap)
    {
        const int firstOffset = 192;
        const int secondOffset = 256;
        var first = new byte[] { 1, 2, 3, 4 };
        var second = new byte[] { 5, 6, 7, 8 };
        var arc = new byte[secondOffset + second.Length];
        WriteHeader(arc, 2);
        WriteEntry(arc.AsSpan(8, 80), "first", first.Length, firstOffset);
        WriteEntry(arc.AsSpan(88, 80), "second", second.Length, secondOffset);
        first.CopyTo(arc.AsSpan(firstOffset));
        second.CopyTo(arc.AsSpan(secondOffset));
        if (nonZeroGap)
            arc[firstOffset + first.Length + 3] = 0x55;
        return arc;
    }

    private static void WriteHeader(Span<byte> arc, ushort count)
    {
        arc[0] = 0;
        arc[1] = (byte)'C';
        arc[2] = (byte)'R';
        arc[3] = (byte)'A';
        BinaryPrimitives.WriteUInt16BigEndian(arc.Slice(4, 2), 8);
        BinaryPrimitives.WriteUInt16BigEndian(arc.Slice(6, 2), count);
    }

    private static void WriteEntry(Span<byte> record, string name, int size, int offset)
    {
        Encoding.UTF8.GetBytes(name).CopyTo(record);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), 0x12345678);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), checked((uint)size));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), checked((uint)size << 3));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), checked((uint)offset));
    }

    private static void Assert(bool condition, string label)
    {
        if (!condition) throw new Exception("FAIL ARC opaque-region regression: " + label);
        Console.WriteLine("PASS " + label);
    }

    private static void ExpectThrows<T>(Action action, string label) where T : Exception
    {
        try { action(); }
        catch (T) { Console.WriteLine("PASS " + label); return; }
        throw new Exception($"FAIL ARC opaque-region regression: {label}; expected {typeof(T).Name}");
    }
}
