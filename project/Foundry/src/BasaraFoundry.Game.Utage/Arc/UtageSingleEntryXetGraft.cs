using System.Security.Cryptography;
using System.Text.Json;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.Game.Utage.Arc;

public sealed record SingleEntryXetGraftAudit(
    int Schema,
    DateTimeOffset CreatedAtUtc,
    string SourceArcSha256,
    string OutputArcSha256,
    int MemberIndex,
    string MemberName,
    uint TypeHash,
    int SourceRawSize,
    int OutputRawSize,
    int BlocksTotal,
    int BlocksReplaced,
    int MaskPixels,
    int OutsideMaskPixelDelta,
    bool GraftOk,
    bool ArcRoundTripVerified,
    bool ApprovedEligible,
    IReadOnlyList<string> Notes);

public sealed record SingleEntryXetGraftResult(
    byte[] SiblingArcBytes,
    string AuditJson,
    SingleEntryXetGraftAudit Audit,
    Bc3GraftResult Graft,
    ArcBuildResult ArcBuild,
    AssetApprovalEvidence ApprovalEvidence);

/// <summary>
/// Certified production transaction for one XET member inside one Utage ARC.
///
/// The source ARC is never mutated. The returned bytes are a sibling archive.
/// The transaction fails closed unless the BC3 block graft succeeds, exactly one
/// ARC member is replaced, the rebuilt member round-trips to the grafted XET,
/// and all writer safety checks pass.
/// </summary>
public static class UtageSingleEntryXetGraft
{
    private const int AuditSchema = 1;

    public static SingleEntryXetGraftResult BuildSibling(
        ReadOnlySpan<byte> sourceArc,
        int memberIndex,
        ReadOnlySpan<byte> candidateRgba,
        ReadOnlySpan<byte> editMask01,
        DateTimeOffset? createdAtUtc = null)
    {
        var sourceBytes = sourceArc.ToArray();
        using var sourceStream = new MemoryStream(sourceBytes, writable: false);
        var archive = UtageArcReader.Read(sourceStream, "<single-entry-graft-source>");

        if ((uint)memberIndex >= (uint)archive.Entries.Count)
            throw new ArgumentOutOfRangeException(nameof(memberIndex));

        var entry = archive.Entries[memberIndex];
        if (entry.TypeHash != UtageTypeHashes.Texture)
        {
            throw new InvalidDataException(
                $"ARC member {memberIndex} ('{entry.Name}') is {UtageTypeHashes.Label(entry.TypeHash)}, not a certified texture member.");
        }

        sourceStream.Position = 0;
        var pristineXet = UtageArcReader.ReadDecompressedPayload(sourceStream, entry);
        var graft = UtageBc3BlockGraft.GraftTopLevel(pristineXet, candidateRgba, editMask01);
        if (!graft.Report.Ok)
        {
            throw new InvalidOperationException(
                "BC3 production graft failed: " + string.Join(" | ", graft.Report.Notes));
        }

        var replacements = new Dictionary<int, byte[]> { [memberIndex] = graft.XetBytes };
        var build = UtageArcWriter.Rebuild(sourceBytes, replacements);

        if (build.ReplacedMemberCount != 1)
            throw new InvalidDataException($"Expected one replaced ARC member, got {build.ReplacedMemberCount}.");

        using var verifyStream = new MemoryStream(build.Bytes, writable: false);
        var rebuilt = UtageArcReader.Read(verifyStream, "<single-entry-graft-output>");
        var rebuiltEntry = rebuilt.Entries[memberIndex];
        verifyStream.Position = 0;
        var rebuiltRaw = UtageArcReader.ReadDecompressedPayload(verifyStream, rebuiltEntry);
        var roundTripVerified = rebuiltRaw.AsSpan().SequenceEqual(graft.XetBytes);
        if (!roundTripVerified)
            throw new InvalidDataException("Sibling ARC target member does not round-trip to the grafted XET bytes.");

        var notes = new List<string>(graft.Report.Notes)
        {
            "single ARC member replacement verified",
            "source ARC retained as immutable input; output is sibling bytes",
        };

        var approvalEvidence = new AssetApprovalEvidence(
            ProductionWriteVerified: graft.Report.Ok && roundTripVerified,
            ProofKind: "utage-bc3-block-graft+single-entry-arc-roundtrip",
            Notes: notes);

        var audit = new SingleEntryXetGraftAudit(
            Schema: AuditSchema,
            CreatedAtUtc: createdAtUtc ?? DateTimeOffset.UtcNow,
            SourceArcSha256: Sha256(sourceBytes),
            OutputArcSha256: Sha256(build.Bytes),
            MemberIndex: memberIndex,
            MemberName: entry.Name,
            TypeHash: entry.TypeHash,
            SourceRawSize: entry.RawSize,
            OutputRawSize: rebuiltEntry.RawSize,
            BlocksTotal: graft.Report.BlocksTotal,
            BlocksReplaced: graft.Report.BlocksReplaced,
            MaskPixels: graft.Report.MaskPixels,
            OutsideMaskPixelDelta: graft.Report.OutsideMaskPixelDelta,
            GraftOk: graft.Report.Ok,
            ArcRoundTripVerified: roundTripVerified,
            ApprovedEligible: approvalEvidence.ProductionWriteVerified,
            Notes: notes);

        var auditJson = JsonSerializer.Serialize(
            audit,
            new JsonSerializerOptions { WriteIndented = true });

        return new SingleEntryXetGraftResult(
            build.Bytes,
            auditJson,
            audit,
            graft,
            build,
            approvalEvidence);
    }

    private static string Sha256(ReadOnlySpan<byte> bytes) =>
        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}
