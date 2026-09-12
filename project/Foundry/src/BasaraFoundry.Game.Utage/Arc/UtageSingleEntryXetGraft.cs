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
    string TargetResourceSha256,
    string PristineBaseSha256,
    int MemberIndex,
    string MemberName,
    uint TypeHash,
    int SourceRawSize,
    int OutputRawSize,
    int BlocksTotal,
    int BlocksReplaced,
    int MaskPixels,
    int OutsideMaskPixelDelta,
    bool UsedPristineOverride,
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
/// The selected ARC/member is the structural target only. Production artwork
/// MUST be based on an explicitly supplied pristine counterpart XET (normally
/// Japanese). A current ENG member may contain an old paste or lossy re-encode,
/// so silently falling back to it as pristine art is forbidden.
/// </summary>
public static class UtageSingleEntryXetGraft
{
    private const int AuditSchema = 3;

    public static SingleEntryXetGraftResult BuildSibling(
        ReadOnlySpan<byte> sourceArc,
        int memberIndex,
        ReadOnlySpan<byte> pristineXet,
        ReadOnlySpan<byte> candidateRgba,
        ReadOnlySpan<byte> editMask01,
        DateTimeOffset? createdAtUtc = null)
    {
        if (pristineXet.IsEmpty)
            throw new ArgumentException("A pristine counterpart XET is mandatory for production grafts.", nameof(pristineXet));

        var sourceBytes = sourceArc.ToArray();
        var pristineBytes = pristineXet.ToArray();
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
        var targetXet = UtageArcReader.ReadDecompressedPayload(sourceStream, entry);
        EnsureCompatibleTarget(targetXet, pristineBytes);

        var graft = UtageBc3BlockGraft.GraftTopLevel(pristineBytes, candidateRgba, editMask01);
        if (!graft.Report.Ok)
        {
            throw new InvalidOperationException(
                "BC3 production graft failed: " + string.Join(" | ", graft.Report.Notes));
        }

        var replacements = new Dictionary<int, byte[]> { [memberIndex] = graft.XetBytes };
        var build = UtageArcWriter.Rebuild(sourceBytes, replacements);

        if (build.ReplacedMemberCount != 1)
            throw new InvalidDataException($"Expected one replaced ARC member, got {build.ReplacedMemberCount}.");

        // UtageArcWriter already byte-verifies every untouched stored payload;
        // assert the replacement set again at this transaction boundary.
        var untouched = build.Members.Count(m => !m.Replaced);
        if (untouched != archive.Entries.Count - 1 || build.Members.Count(m => m.Replaced) != 1)
            throw new InvalidDataException("Unexpected replaced-member set after ARC rebuild.");

        using var verifyStream = new MemoryStream(build.Bytes, writable: false);
        var rebuilt = UtageArcReader.Read(verifyStream, "<single-entry-graft-output>");
        var rebuiltEntry = rebuilt.Entries[memberIndex];
        verifyStream.Position = 0;
        var rebuiltRaw = UtageArcReader.ReadDecompressedPayload(verifyStream, rebuiltEntry);
        var roundTripVerified = rebuiltRaw.AsSpan().SequenceEqual(graft.XetBytes);
        if (!roundTripVerified)
            throw new InvalidDataException("Sibling ARC target member does not round-trip to the grafted XET bytes.");

        var sourceArcHash = Sha256(sourceBytes);
        var outputArcHash = Sha256(build.Bytes);
        var targetHash = Sha256(targetXet);
        var pristineHash = Sha256(pristineBytes);
        var notes = new List<string>(graft.Report.Notes)
        {
            "production artwork base = explicit pristine counterpart XET",
            "selected target XET used only for compatibility/identity validation",
            "single ARC member replacement verified",
            "all non-target ARC stored payloads verified unchanged by UtageArcWriter",
            "source ARC retained as immutable input; output is sibling bytes",
        };

        var approvalEvidence = new AssetApprovalEvidence(
            productionWriteVerified: graft.Report.Ok && roundTripVerified,
            proofKind: AssetApprovalEvidence.UtageBc3GraftArcProofKind,
            sourceArcSha256: sourceArcHash,
            outputArcSha256: outputArcHash,
            memberIndex: memberIndex,
            memberName: entry.Name,
            notes: notes);

        var audit = new SingleEntryXetGraftAudit(
            Schema: AuditSchema,
            CreatedAtUtc: createdAtUtc ?? DateTimeOffset.UtcNow,
            SourceArcSha256: sourceArcHash,
            OutputArcSha256: outputArcHash,
            TargetResourceSha256: targetHash,
            PristineBaseSha256: pristineHash,
            MemberIndex: memberIndex,
            MemberName: entry.Name,
            TypeHash: entry.TypeHash,
            SourceRawSize: entry.RawSize,
            OutputRawSize: rebuiltEntry.RawSize,
            BlocksTotal: graft.Report.BlocksTotal,
            BlocksReplaced: graft.Report.BlocksReplaced,
            MaskPixels: graft.Report.MaskPixels,
            OutsideMaskPixelDelta: graft.Report.OutsideMaskPixelDelta,
            UsedPristineOverride: true,
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

    private static void EnsureCompatibleTarget(ReadOnlySpan<byte> targetXet, ReadOnlySpan<byte> pristineXet)
    {
        var target = UtageXetReader.ReadInfo(targetXet);
        var pristine = UtageXetReader.ReadInfo(pristineXet);

        if (target.Version != pristine.Version ||
            target.Width != pristine.Width ||
            target.Height != pristine.Height ||
            target.FormatCode != pristine.FormatCode ||
            target.MipCount != pristine.MipCount ||
            target.Swizzle != pristine.Swizzle ||
            target.TextureOffset != pristine.TextureOffset)
        {
            throw new InvalidDataException(
                "Pristine counterpart XET is not structurally compatible with the selected target texture. " +
                $"Target={Describe(target)}; pristine={Describe(pristine)}.");
        }

        UtageXetCodec.RequireEncodingCapability(pristine);
    }

    private static string Describe(XetInfo info) =>
        $"v=0x{info.Version:X2} {info.Width}x{info.Height} fmt=0x{info.FormatCode:X2} mip={info.MipCount} swizzle={info.Swizzle} offset={info.TextureOffset}";

    private static string Sha256(ReadOnlySpan<byte> bytes) =>
        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}
