using System.Buffers.Binary;
using System.Text;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Arc;

namespace BasaraFoundry.SmokeTests;

internal static class Program
{
    private static int Main()
    {
        Console.WriteLine("BASARA Foundry v0.1 smoke tests");
        Console.WriteLine("--------------------------------");

        var project = new FoundryProject(
            Schema: 1,
            ProjectName: "Sengoku BASARA 3 Utage English",
            Target: "SB3U_PS3",
            Sources: new SourceRoots(null, null, null, null),
            Rules: new ProjectRules());
        Smoke.True(project.Rules.CanonicalSourcesReadOnly, "project defaults to read-only canonical sources");
        Smoke.True(project.Rules.ArtRequiresApproval, "art approval gate defaults on");

        var bytes = BuildSyntheticArc();
        using (var stream = new MemoryStream(bytes, writable: false))
        {
            var arc = UtageArcReader.Read(stream, "synthetic.arc");
            Smoke.Equal((ushort)8, arc.Version, "ARC v8 header");
            Smoke.Equal(2, arc.Entries.Count, "ARC entry count");
            Smoke.Equal("id\\texture\\roulette_000_ID_HQ", arc.Entries[0].Name, "resource name");
            Smoke.Equal(0x241F5DEBu, arc.Entries[0].TypeHash, "texture type hash");
            Smoke.Equal(
                "TEST_TEXTURE_0001",
                Encoding.ASCII.GetString(UtageArcReader.ReadDecompressedPayload(stream, arc.Entries[0])),
                "stored payload round-trip");
        }

        Smoke.Throws<InvalidDataException>(() =>
        {
            using var bad = new MemoryStream(BuildSyntheticArc(corruptSecondOffset: true), writable: false);
            _ = UtageArcReader.Read(bad, "corrupt.arc");
        }, "out-of-range member is rejected");

        Smoke.Throws<NotSupportedException>(() =>
        {
            var little = BuildSyntheticArc();
            little[0] = (byte)'A';
            little[1] = (byte)'R';
            little[2] = (byte)'C';
            little[3] = 0;
            using var stream = new MemoryStream(little, writable: false);
            _ = UtageArcReader.Read(stream, "wrong-platform.arc");
        }, "uncertified ARC platform is rejected");

        Console.WriteLine($"\nSmoke tests passed: {Smoke.Passed}");
        return 0;
    }

    private static byte[] BuildSyntheticArc(bool corruptSecondOffset = false)
    {
        const int entrySize = 80;
        const int tableStart = 8;
        const int payload1Offset = 0x800;
        const int payload2Offset = 0x820;

        var first = Encoding.ASCII.GetBytes("id\\texture\\roulette_000_ID_HQ");
        var second = Encoding.ASCII.GetBytes("id\\lsp\\roulette\\roulette_000");
        var payload1 = Encoding.ASCII.GetBytes("TEST_TEXTURE_0001");
        var payload2 = Encoding.ASCII.GetBytes("LAYOUT_NODE_TEST");
        var length = payload2Offset + payload2.Length;
        var arc = new byte[length];

        arc[0] = 0x00;
        arc[1] = 0x43;
        arc[2] = 0x52;
        arc[3] = 0x41;
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(4, 2), 8);
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(6, 2), 2);

        void Entry(int index, byte[] name, uint typeHash, byte[] payload, int payloadOffset)
        {
            var record = arc.AsSpan(tableStart + index * entrySize, entrySize);
            name.CopyTo(record);
            BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), typeHash);
            BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), (uint)payload.Length);
            BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), (uint)(payload.Length << 3));
            BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), (uint)payloadOffset);
            if (payloadOffset + payload.Length <= arc.Length)
                payload.CopyTo(arc.AsSpan(payloadOffset));
        }

        Entry(0, first, 0x241F5DEB, payload1, payload1Offset);
        Entry(1, second, 0x60DD1B16, payload2, corruptSecondOffset ? 0x100000 : payload2Offset);
        return arc;
    }

    private static class Smoke
    {
        private static int _passed;

        public static void Equal<T>(T expected, T actual, string name) where T : notnull
        {
            if (!EqualityComparer<T>.Default.Equals(expected, actual))
                throw new Exception($"FAIL {name}: expected {expected}, got {actual}");
            Console.WriteLine($"PASS {name}");
            _passed++;
        }

        public static void True(bool value, string name)
        {
            if (!value)
                throw new Exception($"FAIL {name}");
            Console.WriteLine($"PASS {name}");
            _passed++;
        }

        public static void Throws<T>(Action action, string name) where T : Exception
        {
            try
            {
                action();
            }
            catch (T)
            {
                Console.WriteLine($"PASS {name}");
                _passed++;
                return;
            }

            throw new Exception($"FAIL {name}: expected {typeof(T).Name}");
        }

        public static int Passed => _passed;
    }
}
