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
    string CandidateRgbaSha256,
    string EditMaskSha256,
    string FinalResourceSha256,
    int MemberIndex,
    string MemberName,
    uint TypeHash,
    int SourceRawSize,
    int OutputRawSize,
    int BlocksTotal,
    int BlocksReplaced,
    int MaskPixels,
    int OutsideMaskPixelDelta,
    bool TargetShellPreserved,
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
/// The selected ARC/member owns the output container identity. Production
/// artwork MUST be based on an explicitly supplied pristine counterpart XET
/// (normally Japanese), but the pristine XET must never replace the target
/// shell wholesale. The final XET is constructed from the target shell plus
/// the certified pristine/grafted top-level image payload.
/// </summary>
public static class UtageSingleEntryXetGraft
{
    private const int AuditSchema = 4;

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
        var candidateBytes = candidateRgba.ToArray();
        var maskBytes = editMask01.ToArray();
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
        var compatibility = EnsureCompatibleTarget(targetXet, pristineBytes);

        var graft = UtageBc3BlockGraft.GraftTopLevel(pristineBytes, candidateBytes, maskBytes);
        if (!graft.Report.Ok)
        {
            throw new InvalidOperationException(
                "BC3 production graft failed: " + string.Join(" | ", graft.Report.Notes));
        }

        // Critical ownership rule: preserve the exact target XET shell/header and
        // only replace the certified top-level image payload range with the
        // pristine-derived block graft. Never transplant the pristine donor XET
        // wholesale into the live target ARC.
        var finalXet = targetXet.ToArray();
        var targetInfo = compatibility.Target;
        var pristineInfo = compatibility.Pristine;
        var payloadLength = compatibility.TopLevelPayloadLength;
        graft.XetBytes.AsSpan(pristineInfo.TextureOffset, payloadLength)
            .CopyTo(finalXet.AsSpan(targetInfo.TextureOffset, payloadLength));

        if (!finalXet.AsSpan(0, targetInfo.TextureOffset).SequenceEqual(targetXet.AsSpan(0, targetInfo.TextureOffset)))
            throw new InvalidDataException("Target XET shell/header changed during production graft.");
        if (!finalXet.AsSpan(targetInfo.TextureOffset + payloadLength)
                .SequenceEqual(targetXet.AsSpan(targetInfo.TextureOffset + payloadLength)))
            throw new InvalidDataException("Target XET bytes after the certified payload range changed during production graft.");

        var replacements = new Dictionary<int, byte[]> { [memberIndex] = finalXet };
        var build = UtageArcWriter.Rebuild(sourceBytes, replacements);

        if (build.ReplacedMemberCount != 1)
            throw new InvalidDataException($"Expected one replaced ARC member, got {build.ReplacedMemberCount}.");

        var untouched = build.Members.Count(m => !m.Replaced);
        if (untouched != archive.Entries.Count - 1 || build.Members.Count(m => m.Replaced) != 1)
            throw new InvalidDataException("Unexpected replaced-member set after ARC rebuild.");

        using var verifyStream = new MemoryStream(build.Bytes, writable: false);
        var rebuilt = UtageArcReader.Read(verifyStream, "<single-entry-graft-output>");
        var rebuiltEntry = rebuilt.Entries[memberIndex];
        verifyStream.Position = 0;
        var rebuiltRaw = UtageArcReader.ReadDecompressedPayload(verifyStream, rebuiltEntry);
        var roundTripVerified = rebuiltRaw.AsSpan().SequenceEqual(finalXet);
        if (!roundTripVerified)
            throw new InvalidDataException("Sibling ARC target member does not round-trip to the final target-shell-preserving XET bytes.");

        var sourceArcHash = Sha256(sourceBytes);
        var outputArcHash = Sha256(build.Bytes);
        var targetHash = Sha256(targetXet);
        var pristineHash = Sha256(pristineBytes);
        var candidateHash = Sha256(candidateBytes);
        var maskHash = Sha256(maskBytes);
        var finalHash = Sha256(finalXet);
        var notes = new List<string>(graft.Report.Notes)
        {
            "production artwork base = explicit pristine counterpart XET image payload",
            "selected target XET owns and preserves output shell/header/container identity",
            $"certified top-level payload bytes copied = {payloadLength}",
            "bytes before target textureOffset preserved exactly from target XET",
            "bytes after certified top-level payload preserved exactly from target XET",
            "single ARC member replacement verified",
            "all non-target ARC stored payloads verified unchanged by UtageArcWriter",
            "source ARC retained as immutable input; output is build bytes",
        };

        var approvalEvidence = new AssetApprovalEvidence(
            productionWriteVerified: graft.Report.Ok && roundTripVerified,
            proofKind: AssetApprovalEvidence.UtageBc3GraftArcProofKind,
            sourceArcSha256: sourceArcHash,
            outputArcSha256: outputArcHash,
            targetResourceSha256: targetHash,
            pristineResourceSha256: pristineHash,
            candidateSha256: candidateHash,
            editMaskSha256: maskHash,
            finalResourceSha256: finalHash,
            memberIndex: memberIndex,
            memberName: entry.Name,
            notes: notes);

        AssetApprovalGuard.EnsureCanTransition(
            AssetApprovalState.Review,
            AssetApprovalState.Approved,
            approvalEvidence);
        notes.Add("domain approval guard accepted the opaque, fully input-bound production proof");

        var audit = new SingleEntryXetGraftAudit(
            Schema: AuditSchema,
            CreatedAtUtc: createdAtUtc ?? DateTimeOffset.UtcNow,
            SourceArcSha256: sourceArcHash,
            OutputArcSha256: outputArcHash,
            TargetResourceSha256: targetHash,
            PristineBaseSha256: pristineHash,
            CandidateRgbaSha256: candidateHash,
            EditMaskSha256: maskHash,
            FinalResourceSha256: finalHash,
            MemberIndex: memberIndex,
            MemberName: entry.Name,
            TypeHash: entry.TypeHash,
            SourceRawSize: entry.RawSize,
            OutputRawSize: rebuiltEntry.RawSize,
            BlocksTotal: graft.Report.BlocksTotal,
            BlocksReplaced: graft.Report.BlocksReplaced,
            MaskPixels: graft.Report.MaskPixels,
            OutsideMaskPixelDelta: graft.Report.OutsideMaskPixelDelta,
            TargetShellPreserved: true,
            UsedPristineOverride: true,
            GraftOk: graft.Report.Ok,
            ArcRoundTripVerified: roundTripVerified,
            ApprovedEligible: true,
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

    private static XetCompatibility EnsureCompatibleTarget(ReadOnlySpan<byte> targetXet, ReadOnlySpan<byte> pristineXet)
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
        UtageXetCodec.RequireEncodingCapability(target);

        var payloadLength = UtageXetCodec.TopLevelEncodedSize(pristine);
        if (target.TextureOffset < 0 || pristine.TextureOffset < 0 ||
            target.TextureOffset + payloadLength > targetXet.Length ||
            pristine.TextureOffset + payloadLength > pristineXet.Length)
        {
            throw new InvalidDataException("Target/pristine XET does not contain the complete certified top-level image payload range.");
        }

        return new XetCompatibility(target, pristine, payloadLength);
    }

    private static string Describe(UtageXetInfo info) =>
        $"v=0x{info.Version:X2} {info.Width}x{info.Height} fmt=0x{info.FormatCode:X2} mip={info.MipCount} swizzle={info.Swizzle} offset={info.TextureOffset}";

    private static string Sha256(ReadOnlySpan<byte> bytes) =>
        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private sealed record XetCompatibility(
        UtageXetInfo Target,
        UtageXetInfo Pristine,
        int TopLevelPayloadLength);
}
