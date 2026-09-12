using System.Text.Json;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Arc;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private const int VerifiedOwnerSetResumeSchema = 1;

    private string VerifiedOwnerSetResumeStatePath =>
        Path.Combine(Path.GetDirectoryName(_projectPath)!, "state", "last-verified-owner-set.json");

    private void WriteVerifiedOwnerSetResumeState(string? runtimeEvidenceJsonPath)
    {
        var build = _verifiedOwnerSetBuild
            ?? throw new InvalidOperationException("Verified synchronized build is missing.");
        var buildSetHash = _verifiedOwnerSetBuildSetSha256
            ?? throw new InvalidOperationException("Verified synchronized build-set hash is missing.");
        var anchorHash = _verifiedOwnerSetAnchorOutputSha256
            ?? throw new InvalidOperationException("Verified synchronized anchor ARC hash is missing.");
        var finalHash = _verifiedOwnerSetFinalResourceSha256
            ?? throw new InvalidOperationException("Verified synchronized final XET hash is missing.");
        var buildId = _verifiedOwnerSetBuildId
            ?? throw new InvalidOperationException("Verified synchronized build ID is missing.");
        var approvedAt = _ownerSetEncodedResultApprovedAtUtc
            ?? throw new InvalidOperationException("Synchronized encoded-result approval timestamp is missing.");

        var state = new VerifiedOwnerSetResumeState(
            Schema: VerifiedOwnerSetResumeSchema,
            BuildDirectoryRelativePath: ToProjectRelativePath(build.BuildDirectory),
            GroupAuditRelativePath: ToProjectRelativePath(build.GroupAuditPath),
            BuildSetSha256: buildSetHash,
            AnchorArchivePath: build.ActiveOwnerAudit.MemberName is null ? "" :
                build.GroupAudit.Owners.Single(owner =>
                    owner.MemberIndex == build.ActiveOwnerAudit.MemberIndex &&
                    owner.OutputArcSha256.Equals(anchorHash, StringComparison.Ordinal)).ArchivePath,
            AnchorMemberIndex: build.ActiveOwnerAudit.MemberIndex,
            AnchorOutputArcRelativePath: ToProjectRelativePath(build.ActiveOwnerOutputArcPath),
            AnchorAuditRelativePath: ToProjectRelativePath(build.ActiveOwnerAuditPath),
            AnchorOutputArcSha256: anchorHash,
            FinalResourceSha256: finalHash,
            BuildId: buildId,
            EncodedResultApprovedAtUtc: approvedAt,
            RuntimeEvidenceRelativePath: string.IsNullOrWhiteSpace(runtimeEvidenceJsonPath)
                ? null
                : ToProjectRelativePath(runtimeEvidenceJsonPath),
            UpdatedAtUtc: DateTimeOffset.UtcNow);

        var full = Path.GetFullPath(VerifiedOwnerSetResumeStatePath);
        Directory.CreateDirectory(Path.GetDirectoryName(full)!);
        var temp = full + ".tmp." + Guid.NewGuid().ToString("N");
        try
        {
            File.WriteAllText(temp, JsonSerializer.Serialize(state, new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            }));
            File.Move(temp, full, overwrite: true);
        }
        finally
        {
            if (File.Exists(temp))
                File.Delete(temp);
        }
    }

    private void TryRestoreVerifiedOwnerSetState()
    {
        if (!File.Exists(VerifiedOwnerSetResumeStatePath))
            return;

        try
        {
            var saved = JsonSerializer.Deserialize<VerifiedOwnerSetResumeState>(
                File.ReadAllText(VerifiedOwnerSetResumeStatePath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new InvalidDataException("Saved synchronized-build state was empty.");
            if (saved.Schema != VerifiedOwnerSetResumeSchema)
                throw new NotSupportedException($"Unsupported synchronized-build resume schema {saved.Schema}.");
            if (saved.EncodedResultApprovedAtUtc == default)
                throw new InvalidDataException("Saved synchronized build has no encoded-result approval binding.");

            var buildDirectory = ResolveProjectRelativePath(saved.BuildDirectoryRelativePath);
            var groupAuditPath = ResolveProjectRelativePath(saved.GroupAuditRelativePath);
            var anchorOutputPath = ResolveProjectRelativePath(saved.AnchorOutputArcRelativePath);
            var anchorAuditPath = ResolveProjectRelativePath(saved.AnchorAuditRelativePath);
            if (!Directory.Exists(buildDirectory) || !File.Exists(groupAuditPath) ||
                !File.Exists(anchorOutputPath) || !File.Exists(anchorAuditPath))
            {
                throw new InvalidDataException("Saved synchronized build directory or anchor audit/output no longer exists.");
            }

            var group = JsonSerializer.Deserialize<SharedOwnerXetGraftGroupAudit>(
                File.ReadAllText(groupAuditPath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new InvalidDataException("Saved synchronized group audit was empty.");
            UtageSharedOwnerAuditVerifier.EnsureValid(group);
            if (!group.BuildSetSha256.Equals(saved.BuildSetSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Saved synchronized build-set hash no longer matches the group audit.");

            var anchorOwner = group.Owners.SingleOrDefault(owner =>
                owner.MemberIndex == saved.AnchorMemberIndex &&
                owner.ArchivePath.Replace('\\', '/').Equals(saved.AnchorArchivePath.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase))
                ?? throw new InvalidDataException("Saved synchronized anchor owner is no longer present in the group audit.");
            if (!anchorOwner.OutputArcSha256.Equals(saved.AnchorOutputArcSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Saved synchronized anchor ARC hash no longer matches the group audit.");

            var physicalAnchorHash = Sha256(File.ReadAllBytes(anchorOutputPath));
            if (!physicalAnchorHash.Equals(saved.AnchorOutputArcSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Saved synchronized anchor ARC changed on disk.");

            var activeAudit = JsonSerializer.Deserialize<SingleEntryXetGraftAudit>(
                File.ReadAllText(anchorAuditPath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new InvalidDataException("Saved synchronized anchor audit was empty.");
            ValidateProductionAuditForResume(activeAudit, physicalAnchorHash);
            if (activeAudit.MemberIndex != saved.AnchorMemberIndex ||
                !activeAudit.OutputArcSha256.Equals(anchorOwner.OutputArcSha256, StringComparison.Ordinal) ||
                !activeAudit.FinalResourceSha256.Equals(saved.FinalResourceSha256, StringComparison.Ordinal) ||
                !activeAudit.FinalResourceSha256.Equals(group.FinalResourceSha256, StringComparison.Ordinal))
            {
                throw new InvalidDataException("Saved synchronized anchor audit no longer matches the group binding.");
            }

            var build = new VerifiedOwnerSetBuild(
                group,
                groupAuditPath,
                buildDirectory,
                activeAudit,
                anchorAuditPath,
                anchorOutputPath);
            var revalidated = RevalidateOwnerSetOnDisk(build);
            if (!revalidated.BuildSetSha256.Equals(saved.BuildSetSha256, StringComparison.Ordinal) ||
                !revalidated.FinalResourceSha256.Equals(saved.FinalResourceSha256, StringComparison.Ordinal))
            {
                throw new InvalidDataException("Saved synchronized owner set changed after its encoded-result approval.");
            }

            var expectedBuildId = OwnerSetRuntimeVerificationGuard.BuildIdForSet(saved.BuildSetSha256);
            if (!expectedBuildId.Equals(saved.BuildId, StringComparison.Ordinal))
                throw new InvalidDataException("Saved synchronized build ID does not match the complete build-set hash.");

            // Only displace a valid restored single-owner state after every owner-set
            // binding above has passed. A corrupt owner-set state must not destroy a
            // separately valid single-owner resume checkpoint.
            ResetRuntimeEvidenceState();
            ResetOwnerSetRuntimeEvidenceState();
            _verifiedOwnerSetBuild = build;
            _verifiedOwnerSetBuildSetSha256 = saved.BuildSetSha256;
            _verifiedOwnerSetAnchorOutputSha256 = saved.AnchorOutputArcSha256;
            _verifiedOwnerSetFinalResourceSha256 = saved.FinalResourceSha256;
            _verifiedOwnerSetBuildId = saved.BuildId;
            _ownerSetEncodedResultApprovedAtUtc = saved.EncodedResultApprovedAtUtc;
            _ownerSetRuntimeVerificationEvidence = null;

            SendForApprovalButton.Content = "Attach RPCS3 owner-set verification";
            SendForApprovalButton.IsEnabled = true;
            SearchStatusText.Text =
                $"Restored encoded-result-approved synchronized build {saved.BuildId} ({group.OwnerCount} ARCs). RPCS3 runtime evidence is still required.";

            if (string.IsNullOrWhiteSpace(saved.RuntimeEvidenceRelativePath))
                return;

            var evidencePath = ResolveProjectRelativePath(saved.RuntimeEvidenceRelativePath);
            if (!File.Exists(evidencePath))
                return;
            var evidence = JsonSerializer.Deserialize<OwnerSetRuntimeVerificationEvidence>(
                File.ReadAllText(evidencePath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new InvalidDataException("Saved synchronized runtime evidence was empty.");
            OwnerSetRuntimeVerificationGuard.EnsureValidForBuild(
                "RPCS3",
                saved.BuildSetSha256,
                saved.AnchorOutputArcSha256,
                evidence);
            var screenshotPath = ResolveProjectRelativePath(evidence.ScreenshotPath);
            if (!File.Exists(screenshotPath))
                throw new InvalidDataException("Saved synchronized RPCS3 screenshot no longer exists.");
            OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(evidence, File.ReadAllBytes(screenshotPath));
            var state = OwnerSetRuntimeVerificationGuard.PromoteToRuntimeVerified(
                AssetApprovalState.Built,
                "RPCS3",
                saved.BuildSetSha256,
                saved.AnchorOutputArcSha256,
                evidence);
            if (state != AssetApprovalState.RuntimeVerified)
                throw new InvalidDataException("Saved synchronized runtime evidence did not pass the RuntimeVerified transition guard.");

            // Re-check every ARC after loading evidence too: a valid old screenshot
            // cannot keep RuntimeVerified status if any synchronized output changed.
            RevalidateOwnerSetOnDisk(build);
            _ownerSetRuntimeVerificationEvidence = evidence;
            SendForApprovalButton.Content = "Owner set Runtime Verified";
            SendForApprovalButton.IsEnabled = false;
            SearchStatusText.Text =
                $"RUNTIME VERIFIED · restored synchronized {group.OwnerCount}-ARC build {saved.BuildId} · RPCS3 screenshot {evidence.ScreenshotSha256[..12]}…";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or JsonException or ArgumentException or InvalidOperationException)
        {
            ResetOwnerSetRuntimeEvidenceState();
            SearchStatusText.Text =
                $"Previous synchronized-build state was not restored because it failed validation: {ex.Message}";
        }
    }

    private sealed record VerifiedOwnerSetResumeState(
        int Schema,
        string BuildDirectoryRelativePath,
        string GroupAuditRelativePath,
        string BuildSetSha256,
        string AnchorArchivePath,
        int AnchorMemberIndex,
        string AnchorOutputArcRelativePath,
        string AnchorAuditRelativePath,
        string AnchorOutputArcSha256,
        string FinalResourceSha256,
        string BuildId,
        DateTimeOffset EncodedResultApprovedAtUtc,
        string? RuntimeEvidenceRelativePath,
        DateTimeOffset UpdatedAtUtc);
}
