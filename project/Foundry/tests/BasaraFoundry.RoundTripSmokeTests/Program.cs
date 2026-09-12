using System.Buffers.Binary;
using System.Text;
using BasaraFoundry.Game.Utage.Preview;

namespace BasaraFoundry.RoundTripSmokeTests;

internal static class Program
{
    private static int Main()
    {
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

    private static byte[] BuildXet()
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
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(12, 4), (uint)(1 | (0x2A << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(16, 4), textureOffset);
        return raw;
    }

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
