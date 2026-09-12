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
    int OutsideEffectiveBlockPixelDelta,
    int CompressionCollateralPixels,
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
/// The selected target owns output container identity; pristine JPN supplies
/// trusted image payload bytes; only approved touched BC3 blocks come from the
/// localized candidate.
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
            throw new InvalidDataException($"ARC member {memberIndex} ('{entry.Name}') is {UtageTypeHashes.Label(entry.TypeHash)}, not a certified texture member.");

        sourceStream.Position = 0;
        var targetXet = UtageArcReader.ReadDecompressedPayload(sourceStream, entry);
        var compatibility = EnsureCompatibleTarget(targetXet, pristineBytes);

        var graft = UtageBc3BlockGraft.GraftTopLevel(pristineBytes, candidateBytes, maskBytes);
        if (!graft.Report.Ok)
            throw new InvalidOperationException("BC3 production graft failed: " + string.Join(" | ", graft.Report.Notes));

        var finalXet = targetXet.ToArray();
        var targetInfo = compatibility.Target;
        var pristineInfo = compatibility.Pristine;
        var payloadLength = compatibility.TopLevelPayloadLength;

        graft.GraftedPayload.AsSpan().CopyTo(finalXet.AsSpan(targetInfo.TextureOffset, payloadLength));

        if (!finalXet.AsSpan(0, targetInfo.TextureOffset).SequenceEqual(targetXet.AsSpan(0, targetInfo.TextureOffset)))
            throw new InvalidDataException("Target XET shell/header changed during production graft.");
        if (!finalXet.AsSpan(targetInfo.TextureOffset + payloadLength).SequenceEqual(targetXet.AsSpan(targetInfo.TextureOffset + payloadLength)))
            throw new InvalidDataException("Target XET bytes after the certified payload range changed during production graft.");

        var finalDecode = UtageXetCodec.DecodeTopLevel(finalXet);
        if (graft.VerificationDecode is null || !finalDecode.Rgba.AsSpan().SequenceEqual(graft.VerificationDecode.Rgba))
            throw new InvalidDataException("Target-shell final XET decode differs from the verified pristine-shell graft decode.");
        if (graft.Report.OutsideEffectiveBlockPixelDelta != 0)
            throw new InvalidDataException($"Final decoded output changed {graft.Report.OutsideEffectiveBlockPixelDelta} pixels outside the effective BC3 block mask.");

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
            "selected target XET owns output shell/header/container identity",
            $"certified top-level payload bytes copied = {payloadLength}",
            "target XET shell and non-payload bytes preserved exactly",
            "target-shell final decode equals verified pristine-shell graft decode",
            "single ARC member replacement verified",
            "all non-target ARC stored payloads verified unchanged by UtageArcWriter",
            "source ARC retained as immutable input; output is build bytes",
        };

        var approvalEvidence = new AssetApprovalEvidence(
            productionWriteVerified: graft.Report.Ok && roundTripVerified && graft.Report.OutsideEffectiveBlockPixelDelta == 0,
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

        AssetApprovalGuard.EnsureCanTransition(AssetApprovalState.Review, AssetApprovalState.Approved, approvalEvidence);
        notes.Add("domain approval guard accepted opaque proof bound to target/pristine/candidate/mask/final hashes");

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
            OutsideEffectiveBlockPixelDelta: graft.Report.OutsideEffectiveBlockPixelDelta,
            CompressionCollateralPixels: graft.Report.CompressionCollateralPixels,
            TargetShellPreserved: true,
            UsedPristineOverride: true,
            GraftOk: graft.Report.Ok,
            ArcRoundTripVerified: roundTripVerified,
            ApprovedEligible: true,
            Notes: notes);

        var auditJson = JsonSerializer.Serialize(audit, new JsonSerializerOptions { WriteIndented = true });
        return new SingleEntryXetGraftResult(build.Bytes, auditJson, audit, graft, build, approvalEvidence);
    }

    private static XetCompatibility EnsureCompatibleTarget(ReadOnlySpan<byte> targetXet, ReadOnlySpan<byte> pristineXet)
    {
        var target = UtageXetReader.ReadInfo(targetXet);
        var pristine = UtageXetReader.ReadInfo(pristineXet);

        if (target.Version != pristine.Version || target.Swizzle != pristine.Swizzle ||
            target.Reserved != pristine.Reserved || target.AlphaFlags != pristine.AlphaFlags ||
            target.MipCount != pristine.MipCount || target.Width != pristine.Width || target.Height != pristine.Height ||
            target.ImageCount != pristine.ImageCount || target.FormatCode != pristine.FormatCode ||
            target.Unknown3 != pristine.Unknown3 || target.TextureOffset != pristine.TextureOffset ||
            target.BlockFormat != pristine.BlockFormat || target.BlockSizeBytes != pristine.BlockSizeBytes ||
            target.TopLevelSizeBytes != pristine.TopLevelSizeBytes)
        {
            throw new InvalidDataException(
                "Pristine counterpart XET is not structurally compatible with the selected target texture. " +
                $"Target={Describe(target)}; pristine={Describe(pristine)}.");
        }

        UtageXetCodec.RequireEncodingCapability(pristine);
        UtageXetCodec.RequireEncodingCapability(target);

        var payloadLength = pristine.TopLevelSizeBytes
            ?? throw new NotSupportedException("XET encoded top-level byte size is unknown.");
        var targetEnd = checked(target.TextureOffset + payloadLength);
        var pristineEnd = checked(pristine.TextureOffset + payloadLength);

        if (target.MipCount > 1 || pristine.MipCount > 1 || targetXet.Length != targetEnd || pristineXet.Length != pristineEnd)
            throw new NotSupportedException("Target-shell graft v0.1 is single-level only and refuses trailing or multi-mip XET data.");

        return new XetCompatibility(target, pristine, payloadLength);
    }

    private static string Describe(UtageXetInfo info) =>
        $"v=0x{info.Version:X2} {info.Width}x{info.Height} fmt=0x{info.FormatCode:X2} mip={info.MipCount} swizzle={info.Swizzle} " +
        $"reserved={info.Reserved} alpha={info.AlphaFlags} images={info.ImageCount} unk3=0x{info.Unknown3:X4} offset={info.TextureOffset}";

    private static string Sha256(ReadOnlySpan<byte> bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private sealed record XetCompatibility(UtageXetInfo Target, UtageXetInfo Pristine, int TopLevelPayloadLength);
}
