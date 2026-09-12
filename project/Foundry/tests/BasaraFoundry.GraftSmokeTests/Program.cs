using System.Buffers.Binary;
using System.Text;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

/// <summary>
/// Synthetic proof of the Research Ledger BC3 block-graft production rule and
/// the production transaction that carries one verified XET into one sibling ARC.
/// </summary>
internal static class Program
{
    private static int Main()
    {
        const int width = 16;
        const int height = 8;
        var sourceRgba = new byte[width * height * 4];
        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var i = (y * width + x) * 4;
                sourceRgba[i] = (byte)(10 + (x / 4) * 30);
                sourceRgba[i + 1] = 80;
                sourceRgba[i + 2] = 20;
                sourceRgba[i + 3] = 255;
            }
        }

        var pristineXet = BuildXetFromRgba(sourceRgba, width, height);
        var pristineDecoded = UtageXetCodec.DecodeTopLevel(pristineXet).Rgba;
        var candidate = pristineDecoded.ToArray();

        for (var y = 1; y < 3; y++)
        {
            for (var x = 1; x < 3; x++)
            {
                var i = (y * width + x) * 4;
                candidate[i] = 255;
                candidate[i + 1] = 255;
                candidate[i + 2] = 120;
                candidate[i + 3] = 255;
            }
        }

        var mask = new byte[width * height];
        for (var y = 1; y < 3; y++)
        {
            for (var x = 1; x < 3; x++)
                mask[y * width + x] = 1;
        }

        // Domain rect mask converts to the same flat mask.
        var fromRects = EditMaskCodec.ToMask01(
            new EditMask([new PixelRect(1, 1, 3, 3)]),
            width,
            height);
        True(mask.AsSpan().SequenceEqual(fromRects), "EditMaskCodec matches hand-built mask01");

        var result = UtageBc3BlockGraft.GraftTopLevel(pristineXet, candidate, mask);
        True(result.Report.Ok, "graft reports ok");
        Equal(1, result.Report.BlocksReplaced, "exactly one block replaced");
        Equal(0, result.Report.OutsideMaskPixelDelta, "outside-mask delta is zero");

        var bad = candidate.ToArray();
        bad[(0 * width + 8) * 4] ^= 0x7F;
        var rejected = UtageBc3BlockGraft.GraftTopLevel(pristineXet, bad, mask);
        True(!rejected.Report.Ok, "rejects outside-mask changes");

        // ENG-like member bytes that differ outside the mask must not be the art base
        // when a JPN override is supplied — override is the pristine decode base.
        var engMemberRgba = pristineDecoded.ToArray();
        engMemberRgba[0] ^= 0x11; // outside mask corruption on ENG member art
        var engMemberXet = BuildXetFromRgba(engMemberRgba, width, height);
        var sourceArc = BuildSingleEntryArc("roulette_000_ID_HQ", engMemberXet);
        var sourceArcSnapshot = sourceArc.ToArray();

        var tx = UtageSingleEntryXetGraft.BuildSibling(
            sourceArc,
            memberIndex: 0,
            candidate,
            mask,
            pristineXetOverride: pristineXet,
            createdAtUtc: new DateTimeOffset(2026, 9, 12, 0, 0, 0, TimeSpan.Zero));

        True(sourceArc.AsSpan().SequenceEqual(sourceArcSnapshot), "source ARC remains byte-identical");
        True(tx.Audit.UsedPristineOverride, "audit records pristine override");
        True(tx.Audit.GraftOk && tx.Audit.ArcRoundTripVerified && tx.Audit.ApprovedEligible, "transaction fully verified");
        True(!string.IsNullOrWhiteSpace(tx.ApprovalEvidence.SourceArcSha256), "evidence bound to source hash");
        True(!string.IsNullOrWhiteSpace(tx.ApprovalEvidence.OutputArcSha256), "evidence bound to output hash");

        var review = AssetApprovalGuard.Promote(
            AssetApprovalState.Draft,
            AssetApprovalState.Review,
            evidence: null);
        Equal(AssetApprovalState.Review, review, "review allowed without production proof");

        Throws<InvalidOperationException>(
            () => AssetApprovalGuard.Promote(
                AssetApprovalState.Review,
                AssetApprovalState.Approved,
                new AssetApprovalEvidence(true, "forged-proof")),
            "approval rejected for unknown proof kind");

        Throws<InvalidOperationException>(
            () => AssetApprovalGuard.Promote(
                AssetApprovalState.Review,
                AssetApprovalState.Approved,
                new AssetApprovalEvidence(
                    true,
                    AssetApprovalEvidence.UtageBc3GraftArcProofKind)),
            "approval rejected when proof kind is known but hashes are missing");

        var approved = AssetApprovalGuard.Promote(
            AssetApprovalState.Review,
            AssetApprovalState.Approved,
            tx.ApprovalEvidence);
        Equal(AssetApprovalState.Approved, approved, "approval accepted with bound graft+ARC proof");

        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-sibling-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            var sourcePath = Path.Combine(root, "cockpit1P.arc");
            File.WriteAllBytes(sourcePath, sourceArc);
            var written = UtageSiblingArcStore.Write(sourcePath, tx);
            True(File.Exists(written.OutputArcPath), "sibling ARC written");
            True(File.Exists(written.AuditJsonPath), "audit JSON written");
            True(!PathsEqual(written.SourceArcPath, written.OutputArcPath), "sibling path differs from source");
            Throws<InvalidOperationException>(
                () => UtageSiblingArcStore.Write(sourcePath, tx, sourcePath),
                "disk writer refuses source overwrite");
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }

        Console.WriteLine("Graft smoke tests passed.");
        Console.WriteLine($"  blocks_replaced={result.Report.BlocksReplaced}/{result.Report.BlocksTotal}");
        Console.WriteLine($"  sibling_arc_sha256={tx.Audit.OutputArcSha256}");
        return 0;
    }

    private static byte[] BuildXetFromRgba(byte[] rgba, int width, int height)
    {
        const int textureOffset = 20;
        var topLevel = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 16;
        var shell = new byte[textureOffset + topLevel];
        shell[0] = 0;
        shell[1] = (byte)'X';
        shell[2] = (byte)'E';
        shell[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(4, 4), (uint)(0x97 | (2 << 28)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(12, 4), (uint)(1 | (0x2A << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(16, 4), textureOffset);
        var built = UtageXetCodec.ReplaceSingleLevel(shell, rgba);
        return built.XetBytes;
    }

    private static byte[] BuildSingleEntryArc(string name, byte[] rawPayload)
    {
        const int headerSize = 8;
        const int entrySize = 80;
        const int payloadOffset = 128;
        var arc = new byte[payloadOffset + rawPayload.Length];
        arc[0] = 0;
        arc[1] = (byte)'C';
        arc[2] = (byte)'R';
        arc[3] = (byte)'A';
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(4, 2), 8);
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(6, 2), 1);
        var record = arc.AsSpan(headerSize, entrySize);
        var nameBytes = Encoding.UTF8.GetBytes(name);
        if (nameBytes.Length >= 64)
            throw new ArgumentException("Synthetic ARC name must fit the 64-byte field.", nameof(name));
        nameBytes.CopyTo(record);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), UtageTypeHashes.Texture);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), checked((uint)rawPayload.Length));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), checked((uint)rawPayload.Length << 3));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), payloadOffset);
        rawPayload.CopyTo(arc.AsSpan(payloadOffset));
        return arc;
    }

    private static bool PathsEqual(string a, string b) =>
        string.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase);

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

    private static void Throws<TException>(Action action, string label) where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            Console.WriteLine($"PASS {label}");
            return;
        }

        throw new Exception($"FAIL {label}: expected {typeof(TException).Name}");
    }
}
