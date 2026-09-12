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
/// Does not require private game fixtures.
/// </summary>
internal static class Program
{
    private static int Main()
    {
        // 16x8 = 8 BC3 blocks. Edit only the top-left 4x4 block.
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

        // Lettering-style edit inside block (0,0).
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

        var result = UtageBc3BlockGraft.GraftTopLevel(pristineXet, candidate, mask);
        True(result.Report.Ok, "graft reports ok");
        Equal(1, result.Report.BlocksReplaced, "exactly one block replaced");
        Equal(0, result.Report.OutsideMaskPixelDelta, "outside-mask delta is zero");
        True(result.XetBytes.Length == pristineXet.Length, "XET length preserved");
        True(pristineXet.AsSpan(0, 20).SequenceEqual(result.XetBytes.AsSpan(0, 20)), "XET header preserved");

        // Reject path: mutate one guaranteed-different pixel outside the mask.
        var bad = candidate.ToArray();
        var badOffset = (0 * width + 8) * 4;
        bad[badOffset] ^= 0x7F;
        var rejected = UtageBc3BlockGraft.GraftTopLevel(pristineXet, bad, mask);
        True(!rejected.Report.Ok, "rejects outside-mask changes");
        True(rejected.Report.OutsideMaskPixelDelta > 0, "reports outside-mask delta");

        // Production path: graft the XET into exactly one texture member in a
        // sibling ARC and emit an auditable proof. The original ARC remains input.
        var sourceArc = BuildSingleEntryArc("roulette_000_ID_HQ", pristineXet);
        var sourceArcSnapshot = sourceArc.ToArray();
        var tx = UtageSingleEntryXetGraft.BuildSibling(
            sourceArc,
            memberIndex: 0,
            candidate,
            mask,
            new DateTimeOffset(2026, 9, 12, 0, 0, 0, TimeSpan.Zero));

        True(sourceArc.AsSpan().SequenceEqual(sourceArcSnapshot), "source ARC remains byte-identical");
        Equal(1, tx.ArcBuild.ReplacedMemberCount, "single ARC member replaced");
        True(tx.Audit.GraftOk, "audit records successful graft");
        True(tx.Audit.ArcRoundTripVerified, "audit records ARC round-trip verification");
        True(tx.Audit.ApprovedEligible, "audit marks transaction approval-eligible");
        True(tx.AuditJson.Contains("\"approvedEligible\": true", StringComparison.OrdinalIgnoreCase), "audit JSON records approval eligibility");

        // Domain gate: draft/review can exist without production proof, but the
        // Approved boundary is impossible without a successful certified proof.
        var review = AssetApprovalGuard.Promote(
            AssetApprovalState.Draft,
            AssetApprovalState.Review,
            evidence: null);
        Equal(AssetApprovalState.Review, review, "review allowed without production proof");
        Throws<InvalidOperationException>(
            () => AssetApprovalGuard.Promote(AssetApprovalState.Review, AssetApprovalState.Approved, null),
            "approval rejected without production proof");
        var approved = AssetApprovalGuard.Promote(
            AssetApprovalState.Review,
            AssetApprovalState.Approved,
            tx.ApprovalEvidence);
        Equal(AssetApprovalState.Approved, approved, "approval accepted with verified graft+ARC proof");

        Console.WriteLine("Graft smoke tests passed.");
        Console.WriteLine($"  blocks_replaced={result.Report.BlocksReplaced}/{result.Report.BlocksTotal}");
        Console.WriteLine($"  sibling_arc_sha256={tx.Audit.OutputArcSha256}");
        foreach (var note in tx.Audit.Notes)
            Console.WriteLine($"  note: {note}");
        return 0;
    }

    private static byte[] BuildXetFromRgba(byte[] rgba, int width, int height)
    {
        // Build a minimal valid single-level 0x2A XET, then fill payload via codec.
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

        // ReplaceSingleLevel is used only to manufacture a synthetic compressed
        // pristine fixture. The graft test itself never production-reencodes the
        // untouched blocks.
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
