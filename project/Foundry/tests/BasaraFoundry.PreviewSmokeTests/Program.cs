using System.Buffers.Binary;
using System.Text;
using BasaraFoundry.Game.Utage.Preview;

namespace BasaraFoundry.PreviewSmokeTests;

internal static class Program
{
    private static int Main()
    {
        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-preview-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            var arcPath = Path.Combine(root, "cockpit1P.arc");
            File.WriteAllBytes(arcPath, BuildTextureArc());

            var preview = UtageXetPreviewService.Create(
                root,
                "cockpit1P.arc",
                0,
                "id\\texture\\jpn\\roulette\\roulette_000_ID_HQ");

            Equal(1, preview.Schema, "preview schema");
            Equal(8, preview.Width, "preview width");
            Equal(8, preview.Height, "preview height");
            Equal(0x97, preview.Version, "preview XET version");
            Equal(0x2A, preview.FormatCode, "preview XET format");
            Equal("DXT5", preview.BlockFormat, "preview BCn format");
            True(preview.CanEncode, "certified BC3 preview reports writable capability");
            Equal(8 * 8 * 4, preview.Rgba.Length, "preview RGBA byte count");

            Throws<InvalidDataException>(() => UtageXetPreviewService.Create(
                root,
                "..\\escape.arc",
                0,
                preview.ResourceName), "preview blocks source-root path traversal");

            Throws<InvalidDataException>(() => UtageXetPreviewService.Create(
                root,
                "cockpit1P.arc",
                0,
                "id\\texture\\jpn\\roulette\\different_ID_HQ"), "preview blocks stale indexed member name");

            Console.WriteLine("Preview smoke tests passed.");
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
        var payload = BuildXet(8, 8, 0x2A);
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

    private static byte[] BuildXet(int width, int height, int formatCode)
    {
        const int textureOffset = 20;
        const int blockSize = 16;
        var payloadSize = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * blockSize;
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
