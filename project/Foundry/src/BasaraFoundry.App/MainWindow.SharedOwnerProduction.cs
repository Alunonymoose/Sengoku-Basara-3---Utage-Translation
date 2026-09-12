using System.Diagnostics;
using System.Text.Json;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Index;
using BasaraFoundry.Game.Utage.Preview;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private sealed record VerifiedOwnerSetBuild(
        SharedOwnerXetGraftGroupAudit GroupAudit,
        string GroupAuditPath,
        string BuildDirectory,
        SingleEntryXetGraftAudit ActiveOwnerAudit,
        string ActiveOwnerAuditPath,
        string ActiveOwnerOutputArcPath);

    private async Task<VerifiedOwnerSetBuild> BuildAndVerifySharedOwnerSetAsync(
        string engRoot,
        IReadOnlyList<IndexedUtageResource> owners,
        IndexedUtageResource activeTarget,
        string jpnRoot,
        IndexedUtageResource pristineResource,
        CandidateReview candidate,
        UtageXetPreviewSnapshot pristine,
        UtageEditMaskProposal proposal,
        string candidateRgbaPath,
        string maskPath)
    {
        if (owners.Count < 2)
            throw new InvalidOperationException("Shared-owner production path requires at least two exact owners.");
        if (!owners.Any(owner =>
                owner.EntryIndex == activeTarget.EntryIndex &&
                ArchivePathsEqual(owner.ArchivePath, activeTarget.ArchivePath) &&
                owner.ResourceName.Equals(activeTarget.ResourceName, StringComparison.Ordinal)))
        {
            throw new InvalidDataException("Active target is not present in the exact shared-owner set.");
        }

        var projectDir = Path.GetDirectoryName(_projectPath)!;
        var resourceTail = activeTarget.ResourceName.Replace('/', '\\').Split('\\').Last();
        var safeTail = string.Concat(resourceTail.Select(ch => Path.GetInvalidFileNameChars().Contains(ch) ? '_' : ch));
        var buildDirectory = Path.Combine(
            projectDir,
            "builds",
            "texture-grafts",
            "owner-sets",
            $"{safeTail}-{candidate.Sha256[..12]}-{Guid.NewGuid():N}");

        SearchStatusText.Text =
            $"Building one synchronized transaction for all {owners.Count} exact owners; canonical ENG/JPN sources remain read only…";
        await RunGraftSetWorkerAsync(
            engRoot,
            activeTarget,
            jpnRoot,
            pristineResource,
            candidateRgbaPath,
            maskPath,
            buildDirectory);

        var groupAuditPath = Path.Combine(buildDirectory, "owner-set.foundry.audit.json");
        if (!File.Exists(groupAuditPath))
            throw new InvalidDataException("Shared-owner worker reported success but group audit is missing.");
        var groupAudit = JsonSerializer.Deserialize<SharedOwnerXetGraftGroupAudit>(
            File.ReadAllText(groupAuditPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidDataException("Shared-owner group audit was empty.");
        UtageSharedOwnerAuditVerifier.EnsureValid(groupAudit);

        if (!groupAudit.ResourceName.Equals(activeTarget.ResourceName, StringComparison.Ordinal) ||
            groupAudit.TypeHash != activeTarget.TypeHash ||
            groupAudit.OwnerCount != owners.Count)
        {
            throw new InvalidDataException("Shared-owner group audit does not match the active resource/owner count.");
        }
        if (string.IsNullOrWhiteSpace(_activeSourceResourceSha256) ||
            !groupAudit.CommonTargetResourceSha256.Equals(_activeSourceResourceSha256, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Shared-owner group audit belongs to a different Current ENG target XET.");
        }
        if (!groupAudit.PristineBaseSha256.Equals(pristine.SourceResourceSha256, StringComparison.Ordinal) ||
            !groupAudit.CandidateRgbaSha256.Equals(candidate.Sha256, StringComparison.Ordinal) ||
            !groupAudit.CandidateRgbaSha256.Equals(proposal.CandidateRgbaSha256, StringComparison.Ordinal) ||
            !groupAudit.EditMaskSha256.Equals(proposal.MaskSha256, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Shared-owner group audit is not bound to the reviewed pristine/candidate/mask transaction.");
        }

        var expectedOwnerKeys = owners
            .Select(OwnerKey)
            .OrderBy(value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        var auditedOwnerKeys = groupAudit.Owners
            .Select(owner => OwnerKey(owner.ArchivePath, owner.MemberIndex))
            .OrderBy(value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (!expectedOwnerKeys.SequenceEqual(auditedOwnerKeys, StringComparer.OrdinalIgnoreCase))
            throw new InvalidDataException("Shared-owner group audit owner identities differ from the indexed exact-owner set.");

        SingleEntryXetGraftAudit? activeAudit = null;
        string? activeAuditPath = null;
        string? activeOutputPath = null;
        foreach (var owner in owners)
        {
            var groupOwner = groupAudit.Owners.Single(auditOwner =>
                auditOwner.MemberIndex == owner.EntryIndex &&
                ArchivePathsEqual(auditOwner.ArchivePath, owner.ArchivePath));
            var outputArc = SharedOwnerOutputPath(buildDirectory, owner.ArchivePath);
            var auditPath = outputArc + ".audit.json";
            if (!File.Exists(outputArc) || !File.Exists(auditPath))
                throw new InvalidDataException($"Shared-owner output/audit pair is missing for '{owner.ArchivePath}'.");

            var audit = LoadAndVerifyProductionAudit(
                auditPath,
                outputArc,
                owner,
                candidate,
                pristine,
                proposal);
            if (!audit.SourceArcSha256.Equals(groupOwner.SourceArcSha256, StringComparison.Ordinal) ||
                !audit.OutputArcSha256.Equals(groupOwner.OutputArcSha256, StringComparison.Ordinal) ||
                !audit.TargetResourceSha256.Equals(groupOwner.TargetResourceSha256, StringComparison.Ordinal) ||
                !audit.FinalResourceSha256.Equals(groupOwner.FinalResourceSha256, StringComparison.Ordinal) ||
                !audit.FinalResourceSha256.Equals(groupAudit.FinalResourceSha256, StringComparison.Ordinal))
            {
                throw new InvalidDataException($"Shared-owner per-ARC audit disagrees with the group binding for '{owner.ArchivePath}'.");
            }

            if (owner.EntryIndex == activeTarget.EntryIndex && ArchivePathsEqual(owner.ArchivePath, activeTarget.ArchivePath))
            {
                activeAudit = audit;
                activeAuditPath = auditPath;
                activeOutputPath = outputArc;
            }
        }

        if (activeAudit is null || activeAuditPath is null || activeOutputPath is null)
            throw new InvalidDataException("Shared-owner build did not produce the active target owner output.");

        return new VerifiedOwnerSetBuild(
            groupAudit,
            groupAuditPath,
            buildDirectory,
            activeAudit,
            activeAuditPath,
            activeOutputPath);
    }

    private static async Task RunGraftSetWorkerAsync(
        string engRoot,
        IndexedUtageResource target,
        string jpnRoot,
        IndexedUtageResource pristine,
        string candidateRgbaPath,
        string maskPath,
        string outputDirectory)
    {
        var workerPath = Path.Combine(AppContext.BaseDirectory, "worker", "BasaraFoundry.Worker.exe");
        if (!File.Exists(workerPath))
            throw new FileNotFoundException("The isolated Foundry production worker is missing from this build.", workerPath);
        if (Directory.Exists(outputDirectory) || File.Exists(outputDirectory))
            throw new InvalidOperationException("Shared-owner output directory already exists; refusing to merge builds.");

        var start = new ProcessStartInfo
        {
            FileName = workerPath,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in new[]
        {
            "graft-xet-set",
            "--root", engRoot,
            "--archive", target.ArchivePath,
            "--entry", target.EntryIndex.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--name", target.ResourceName,
            "--pristine-root", jpnRoot,
            "--pristine-archive", pristine.ArchivePath,
            "--pristine-entry", pristine.EntryIndex.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--pristine-name", pristine.ResourceName,
            "--rgba", candidateRgbaPath,
            "--mask", maskPath,
            "--output-dir", outputDirectory,
        })
        {
            start.ArgumentList.Add(argument);
        }

        using var process = Process.Start(start)
            ?? throw new IOException("Could not start the isolated shared-owner production worker.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Shared-owner production worker exceeded the 3-minute safety limit and was terminated.");
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        if (process.ExitCode != 0)
        {
            var detail = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
            throw new InvalidDataException($"Shared-owner production worker failed with exit code {process.ExitCode}: {detail.Trim()}");
        }
        if (!Directory.Exists(outputDirectory))
            throw new InvalidDataException("Shared-owner worker reported success but did not promote its output directory.");
    }

    private static string SharedOwnerOutputPath(string buildDirectory, string archiveRelativePath)
    {
        if (Path.IsPathRooted(archiveRelativePath))
            throw new InvalidDataException("Shared-owner archive identity must be relative.");
        var normalized = archiveRelativePath.Replace('\\', Path.DirectorySeparatorChar).Replace('/', Path.DirectorySeparatorChar);
        var directory = Path.GetDirectoryName(normalized);
        var fileName = Path.GetFileNameWithoutExtension(normalized) + ".foundry.arc";
        var relative = string.IsNullOrEmpty(directory) ? fileName : Path.Combine(directory, fileName);
        var root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(buildDirectory));
        var full = Path.GetFullPath(Path.Combine(root, relative));
        if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Shared-owner output path escaped the owner-set build directory.");
        return full;
    }

    private static string OwnerKey(IndexedUtageResource owner) => OwnerKey(owner.ArchivePath, owner.EntryIndex);

    private static string OwnerKey(string archivePath, int memberIndex) =>
        $"{archivePath.Replace('\\', '/')}#{memberIndex}";

    private static bool ArchivePathsEqual(string left, string right) =>
        left.Replace('\\', '/').Equals(right.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase);
}
