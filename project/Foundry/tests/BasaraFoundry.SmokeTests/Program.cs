using System.Buffers.Binary;
using System.Text;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.SmokeTests;

internal static class Program
{
    private static int Main()
    {
        Console.WriteLine("BASARA Foundry v0.1 smoke tests");
        Console.WriteLine("--------------------------------");

        TestProjectSafetyDefaults();
        TestPixelMaskSafety();
        TestArcReader();
        TestArcWriter();
        TestXetMetadata();

        Console.WriteLine($"\nSmoke tests passed: {Smoke.Passed}");
        return 0;
    }

    private static void TestProjectSafetyDefaults()
    {
        var project = new FoundryProject(
            Schema: 1,
            ProjectName: "Sengoku BASARA 3 Utage English",
            Target: "SB3U_PS3",
            Sources: new SourceRoots(null, null, null, null),
            Rules: new ProjectRules());
        Smoke.True(project.Rules.CanonicalSourcesReadOnly, "project defaults to read-only canonical sources");
        Smoke.True(project.Rules.ArtRequiresApproval, "art approval gate defaults on");
    }

    private static void TestPixelMaskSafety()
    {
        const int width = 4;
        const int height = 2;
        var source = new byte[width * height * 4];
        var candidate = source.ToArray();
        var mask = new EditMask([new PixelRect(1, 0, 3, 1)]);

        candidate[(0 * width + 1) * 4] = 255;
        var good = PixelDiffValidator.CompareRgba(source, candidate, width, height, mask);
        Smoke.Equal(1, good.ChangedPixels, "pixel diff counts changed pixels");
        Smoke.Equal(0, good.ChangedOutsideMask, "mask accepts approved-region change");
        Smoke.True(good.IsSafe, "approved-region candidate is safe");

        candidate[(1 * width + 3) * 4 + 1] = 200;
        var bad = PixelDiffValidator.CompareRgba(source, candidate, width, height, mask);
        Smoke.Equal(1, bad.ChangedOutsideMask, "mask counts unexpected outside change");
        Smoke.True(!bad.IsSafe, "outside-mask change blocks production");
    }

    private static void TestArcReader()
    {
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
    }

    private static void TestArcWriter()
    {
        var original = BuildSyntheticArc();
        var noOp = UtageArcWriter.Rebuild(original, new Dictionary<int, byte[]>());
        Smoke.True(noOp.IsNoOp, "ARC no-op build is identified");
        Smoke.True(original.AsSpan().SequenceEqual(noOp.Bytes), "ARC no-op build is byte-identical");
        Smoke.Equal(32, noOp.Alignment, "ARC alignment inferred from real offsets");

        var replacement = Encoding.ASCII.GetBytes("ENGLISH_TEXTURE_REPLACEMENT_IS_LONGER");
        var built = UtageArcWriter.Rebuild(
            original,
            new Dictionary<int, byte[]> { [0] = replacement });
        Smoke.Equal(1, built.ReplacedMemberCount, "ARC build reports one replacement");

        using var oldStream = new MemoryStream(original, writable: false);
        using var newStream = new MemoryStream(built.Bytes, writable: false);
        var before = UtageArcReader.Read(oldStream, "before.arc");
        var after = UtageArcReader.Read(newStream, "after.arc");

        Smoke.Equal(before.Entries.Count, after.Entries.Count, "ARC writer preserves member count");
        Smoke.Equal(before.Entries[0].Name, after.Entries[0].Name, "ARC writer preserves replacement member name");
        Smoke.Equal(before.Entries[1].Name, after.Entries[1].Name, "ARC writer preserves untouched member name");
        Smoke.Equal(before.Entries[1].TypeHash, after.Entries[1].TypeHash, "ARC writer preserves untouched type hash");
        Smoke.Equal(before.Entries[1].Flags, after.Entries[1].Flags, "ARC writer preserves untouched flags");

        var decodedReplacement = UtageArcReader.ReadDecompressedPayload(newStream, after.Entries[0]);
        Smoke.True(replacement.AsSpan().SequenceEqual(decodedReplacement), "ARC replacement round-trips exact raw bytes");

        var oldUntouched = UtageArcReader.ReadStoredPayload(oldStream, before.Entries[1]);
        var newUntouched = UtageArcReader.ReadStoredPayload(newStream, after.Entries[1]);
        Smoke.True(oldUntouched.AsSpan().SequenceEqual(newUntouched), "ARC untouched stored payload remains byte-identical");
        Smoke.True(after.Entries[1].PayloadOffset > before.Entries[1].PayloadOffset, "ARC safely relocates later member when replacement grows");

        Smoke.Throws<ArgumentOutOfRangeException>(() =>
            UtageArcWriter.Rebuild(original, new Dictionary<int, byte[]> { [99] = [1, 2, 3] }),
            "ARC writer rejects nonexistent replacement member");
    }

    private static void TestXetMetadata()
    {
        var raw = BuildSyntheticXet(width: 512, height: 256, formatCode: 0x2A);
        var info = UtageXetReader.ReadInfo(raw);
        Smoke.Equal(0x97, info.Version, "XET v0x97 header");
        Smoke.Equal(512, info.Width, "XET width bitfield");
        Smoke.Equal(256, info.Height, "XET height bitfield");
        Smoke.Equal(0x2A, info.FormatCode, "XET format code");
        Smoke.Equal("DXT5", info.BlockFormat!, "XET Utage format mapping");
        Smoke.Equal(2, info.AlphaFlags, "XET alpha flags");
        Smoke.True(info.CanDecodeTopLevel, "linear known XET is decode-capable");
        Smoke.Equal(131072, info.TopLevelSizeBytes!.Value, "XET BC3 top-level byte size");
        UtageXetReader.RequireTopLevelDecodeCapability(info);

        var swizzled = UtageXetReader.ReadInfo(BuildSyntheticXet(128, 128, 0x2A, swizzle: 7));
        Smoke.True(!swizzled.CanDecodeTopLevel, "swizzled XET is not silently treated as linear");
        Smoke.Throws<NotSupportedException>(
            () => UtageXetReader.RequireTopLevelDecodeCapability(swizzled),
            "swizzled XET decode is blocked");

        var unknown = UtageXetReader.ReadInfo(BuildSyntheticXet(64, 64, 0x7E));
        Smoke.True(!unknown.HasKnownBlockFormat, "unknown XET format is not guessed as DXT5");
        Smoke.Throws<NotSupportedException>(
            () => UtageXetReader.RequireTopLevelDecodeCapability(unknown),
            "unknown XET format decode is blocked");
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

    private static byte[] BuildSyntheticXet(int width, int height, int formatCode, int swizzle = 0)
    {
        const int textureOffset = 20;
        var blockSize = formatCode switch
        {
            0x13 or 0x14 or 0x19 => 8,
            0x15 or 0x17 or 0x18 or 0x2A or 0x2B => 16,
            _ => 0,
        };
        var payloadSize = blockSize == 0
            ? 0
            : Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * blockSize;
        var raw = new byte[textureOffset + payloadSize];
        raw[0] = 0;
        raw[1] = (byte)'X';
        raw[2] = (byte)'E';
        raw[3] = (byte)'T';

        var block4 = (uint)(0x97 | (swizzle << 12) | (2 << 28));
        var block8 = (uint)(1 | (width << 6) | (height << 19));
        var block12 = (uint)(1 | (formatCode << 8));
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(4, 4), block4);
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(8, 4), block8);
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(12, 4), block12);
        BinaryPrimitives.WriteUInt32BigEndian(raw.AsSpan(16, 4), textureOffset);
        return raw;
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
