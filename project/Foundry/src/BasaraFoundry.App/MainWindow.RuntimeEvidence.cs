using System.Text.Json;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Arc;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private const int VerifiedBuildResumeSchema = 1;
    private string? _verifiedBuildArcPath;
    private string? _verifiedBuildAuditPath;
    private string? _verifiedBuildOutputSha256;
    private string? _verifiedBuildId;
    private RuntimeVerificationEvidence? _runtimeVerificationEvidence;

    private bool HasVerifiedBuildAwaitingRuntimeEvidence =>
        _runtimeVerificationEvidence is null &&
        !string.IsNullOrWhiteSpace(_verifiedBuildArcPath) &&
        !string.IsNullOrWhiteSpace(_verifiedBuildOutputSha256) &&
        !string.IsNullOrWhiteSpace(_verifiedBuildId);

    private string ProjectDirectory => Path.GetDirectoryName(_projectPath)!;

    private string VerifiedBuildResumeStatePath =>
        Path.Combine(ProjectDirectory, "state", "last-verified-build.json");

    private void ResetRuntimeEvidenceState()
    {
        _verifiedBuildArcPath = null;
        _verifiedBuildAuditPath = null;
        _verifiedBuildOutputSha256 = null;
        _verifiedBuildId = null;
        _runtimeVerificationEvidence = null;
    }

    private void SetVerifiedBuildForRuntimeEvidence(
        SingleEntryXetGraftAudit audit,
        string outputArcPath,
        string auditPath)
    {
        ArgumentNullException.ThrowIfNull(audit);
        outputArcPath = Path.GetFullPath(outputArcPath);
        auditPath = Path.GetFullPath(auditPath);
        if (!File.Exists(outputArcPath) || !File.Exists(auditPath))
            throw new InvalidDataException("Verified production ARC/audit pair is missing before runtime-evidence handoff.");

        var physicalHash = Sha256(File.ReadAllBytes(outputArcPath));
        ValidateProductionAuditForResume(audit, physicalHash);

        _verifiedBuildArcPath = outputArcPath;
        _verifiedBuildAuditPath = auditPath;
        _verifiedBuildOutputSha256 = audit.OutputArcSha256;
        _verifiedBuildId = RuntimeVerificationGuard.BuildIdForArc(audit.OutputArcSha256);
        _runtimeVerificationEvidence = null;
        WriteVerifiedBuildResumeState(runtimeEvidenceJsonPath: null);

        SendForApprovalButton.Content = "Attach RPCS3 verification screenshot";
        SendForApprovalButton.IsEnabled = true;
        SearchStatusText.Text =
            $"Verified build {_verifiedBuildId} is ready for runtime evidence. " +
            "Runtime Verified remains blocked until a screenshot is explicitly bound to this exact ARC hash.";
    }

    private void TryRestoreVerifiedBuildState()
    {
        ResetRuntimeEvidenceState();
        if (!File.Exists(VerifiedBuildResumeStatePath))
            return;

        try
        {
            var saved = JsonSerializer.Deserialize<VerifiedBuildResumeState>(
                File.ReadAllText(VerifiedBuildResumeStatePath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new InvalidDataException("Saved verified-build state was empty.");
            if (saved.Schema != VerifiedBuildResumeSchema)
                throw new NotSupportedException($"Unsupported verified-build resume schema {saved.Schema}.");

            var outputArcPath = ResolveProjectRelativePath(saved.OutputArcRelativePath);
            var auditPath = ResolveProjectRelativePath(saved.AuditRelativePath);
            if (!File.Exists(outputArcPath) || !File.Exists(auditPath))
                throw new InvalidDataException("Saved verified build or production audit no longer exists.");

            var physicalHash = Sha256(File.ReadAllBytes(outputArcPath));
            if (!physicalHash.Equals(saved.OutputArcSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Saved verified ARC changed on disk; its previous verified state was not restored.");

            var audit = JsonSerializer.Deserialize<SingleEntryXetGraftAudit>(
                File.ReadAllText(auditPath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new InvalidDataException("Saved production audit was empty.");
            ValidateProductionAuditForResume(audit, physicalHash);

            var buildId = RuntimeVerificationGuard.BuildIdForArc(physicalHash);
            if (!buildId.Equals(saved.BuildId, StringComparison.Ordinal))
                throw new InvalidDataException("Saved build ID does not match the verified ARC hash.");

            _verifiedBuildArcPath = outputArcPath;
            _verifiedBuildAuditPath = auditPath;
            _verifiedBuildOutputSha256 = physicalHash;
            _verifiedBuildId = buildId;
            _runtimeVerificationEvidence = null;

            SendForApprovalButton.Content = "Attach RPCS3 verification screenshot";
            SendForApprovalButton.IsEnabled = true;
            SearchStatusText.Text = $"Restored verified build {buildId}. RPCS3 runtime evidence is still required.";

            if (string.IsNullOrWhiteSpace(saved.RuntimeEvidenceRelativePath))
                return;

            var runtimeEvidencePath = ResolveProjectRelativePath(saved.RuntimeEvidenceRelativePath);
            if (!File.Exists(runtimeEvidencePath))
                return;

            RuntimeVerificationEvidence evidence;
            try
            {
                evidence = JsonSerializer.Deserialize<RuntimeVerificationEvidence>(
                    File.ReadAllText(runtimeEvidencePath),
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                    ?? throw new InvalidDataException("Saved runtime evidence was empty.");
                RuntimeVerificationGuard.EnsureValidForBuild("RPCS3", physicalHash, evidence);

                var screenshotPath = ResolveProjectRelativePath(evidence.ScreenshotPath);
                if (!File.Exists(screenshotPath))
                    throw new InvalidDataException("Saved RPCS3 evidence screenshot no longer exists.");
                RuntimeVerificationGuard.VerifyScreenshotBytes(evidence, File.ReadAllBytes(screenshotPath));
                var state = RuntimeVerificationGuard.PromoteToRuntimeVerified(
                    AssetApprovalState.Built,
                    "RPCS3",
                    physicalHash,
                    evidence);
                if (state != AssetApprovalState.RuntimeVerified)
                    throw new InvalidDataException("Saved runtime evidence did not pass the RuntimeVerified transition guard.");
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or JsonException)
            {
                // Keep the verified build, but forget rejected runtime evidence so the
                // next launch does not repeatedly resurrect a stale screenshot claim.
                WriteVerifiedBuildResumeState(runtimeEvidenceJsonPath: null);
                SearchStatusText.Text =
                    $"Restored verified build {buildId}, but previous RPCS3 evidence was rejected: {ex.Message} " +
                    "Attach a new screenshot to verify this build again.";
                return;
            }

            _runtimeVerificationEvidence = evidence;
            SendForApprovalButton.Content = "Runtime Verified";
            SendForApprovalButton.IsEnabled = false;
            SearchStatusText.Text =
                $"RUNTIME VERIFIED · restored {buildId} · RPCS3 screenshot {evidence.ScreenshotSha256[..12]}…";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or JsonException or ArgumentException)
        {
            ResetRuntimeEvidenceState();
            SendForApprovalButton.IsEnabled = false;
            SearchStatusText.Text =
                $"Previous verified-build state was not restored because it failed validation: {ex.Message}";
        }
    }

    private void ValidateProductionAuditForResume(SingleEntryXetGraftAudit audit, string physicalOutputHash)
    {
        if (audit.Schema != 3)
            throw new NotSupportedException($"Unsupported production graft audit schema {audit.Schema}.");
        if (!audit.GraftOk || !audit.ArcRoundTripVerified || !audit.ApprovedEligible || !audit.UsedPristineOverride)
            throw new InvalidDataException("Production audit is not eligible to restore a verified build.");
        if (audit.OutsideMaskPixelDelta != 0)
            throw new InvalidDataException("Production audit reports changed pixels outside the approved mask.");
        if (!audit.OutputArcSha256.Equals(physicalOutputHash, StringComparison.Ordinal))
            throw new InvalidDataException("Production audit output hash does not match the physical ARC.");
        if (audit.MemberIndex < 0 || string.IsNullOrWhiteSpace(audit.MemberName))
            throw new InvalidDataException("Production audit member identity is invalid.");
    }

    private void WriteVerifiedBuildResumeState(string? runtimeEvidenceJsonPath)
    {
        var outputArc = _verifiedBuildArcPath
            ?? throw new InvalidOperationException("Verified build ARC path is missing.");
        var auditPath = _verifiedBuildAuditPath
            ?? throw new InvalidOperationException("Verified build audit path is missing.");
        var outputHash = _verifiedBuildOutputSha256
            ?? throw new InvalidOperationException("Verified build hash is missing.");
        var buildId = _verifiedBuildId
            ?? throw new InvalidOperationException("Verified build ID is missing.");

        var saved = new VerifiedBuildResumeState(
            Schema: VerifiedBuildResumeSchema,
            OutputArcRelativePath: ToProjectRelativePath(outputArc),
            AuditRelativePath: ToProjectRelativePath(auditPath),
            OutputArcSha256: outputHash,
            BuildId: buildId,
            RuntimeEvidenceRelativePath: string.IsNullOrWhiteSpace(runtimeEvidenceJsonPath)
                ? null
                : ToProjectRelativePath(runtimeEvidenceJsonPath),
            UpdatedAtUtc: DateTimeOffset.UtcNow);

        var full = Path.GetFullPath(VerifiedBuildResumeStatePath);
        Directory.CreateDirectory(Path.GetDirectoryName(full)!);
        var temp = full + ".tmp." + Guid.NewGuid().ToString("N");
        try
        {
            File.WriteAllText(temp, JsonSerializer.Serialize(saved, new JsonSerializerOptions
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

    private string ToProjectRelativePath(string path)
    {
        var projectRoot = Path.GetFullPath(ProjectDirectory);
        var full = Path.GetFullPath(path);
        if (!IsPathInsideRoot(projectRoot, full))
            throw new InvalidDataException("Verified-build state may only reference files inside the Foundry project directory.");
        return Path.GetRelativePath(projectRoot, full);
    }

    private string ResolveProjectRelativePath(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathRooted(relativePath))
            throw new InvalidDataException("Saved verified-build state contains an invalid relative path.");

        var projectRoot = Path.GetFullPath(ProjectDirectory);
        var full = Path.GetFullPath(Path.Combine(projectRoot, relativePath));
        if (!IsPathInsideRoot(projectRoot, full))
            throw new InvalidDataException("Saved verified-build state attempted to escape the Foundry project directory.");
        return full;
    }

    private static bool IsPathInsideRoot(string root, string candidate)
    {
        var normalizedRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root)) + Path.DirectorySeparatorChar;
        var normalizedCandidate = Path.GetFullPath(candidate);
        return normalizedCandidate.StartsWith(normalizedRoot, StringComparison.OrdinalIgnoreCase);
    }

    private async Task AttachRuntimeEvidenceAsync()
    {
        var outputArcPath = _verifiedBuildArcPath;
        var outputHash = _verifiedBuildOutputSha256;
        var buildId = _verifiedBuildId;
        var auditPath = _verifiedBuildAuditPath;
        if (string.IsNullOrWhiteSpace(outputArcPath) ||
            string.IsNullOrWhiteSpace(outputHash) ||
            string.IsNullOrWhiteSpace(buildId) ||
            string.IsNullOrWhiteSpace(auditPath))
        {
            throw new InvalidOperationException("No verified production build is awaiting runtime evidence.");
        }
        if (!File.Exists(outputArcPath) || !File.Exists(auditPath))
            throw new InvalidDataException("Verified build/audit pair no longer exists.");
        if (!Sha256(File.ReadAllBytes(outputArcPath)).Equals(outputHash, StringComparison.Ordinal))
            throw new InvalidDataException("Production ARC changed after verification; runtime evidence cannot be attached to a stale build.");

        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.PicturesLibrary,
        };
        picker.FileTypeFilter.Add(".png");
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(this));
        var file = await picker.PickSingleFileAsync();
        if (file is null)
            return;

        byte[] screenshotBytes;
        await using (var input = await file.OpenStreamForReadAsync())
        await using (var memory = new MemoryStream())
        {
            await input.CopyToAsync(memory);
            screenshotBytes = memory.ToArray();
        }
        if (screenshotBytes.Length == 0)
            throw new InvalidDataException("Selected runtime screenshot is empty.");

        // Re-check the build after the picker was open: evidence must never bind
        // to an ARC that changed while the operator was selecting a screenshot.
        if (!Sha256(File.ReadAllBytes(outputArcPath)).Equals(outputHash, StringComparison.Ordinal))
            throw new InvalidDataException("Production ARC changed while selecting runtime evidence.");

        var projectDir = ProjectDirectory;
        var evidenceDir = Path.Combine(projectDir, "runtime-evidence", buildId);
        Directory.CreateDirectory(evidenceDir);
        var extension = Path.GetExtension(file.Name).ToLowerInvariant();
        if (extension is not (".png" or ".jpg" or ".jpeg"))
            throw new InvalidDataException("Runtime evidence must be a PNG or JPEG screenshot.");

        var capturedAt = file.DateCreated == default ? DateTimeOffset.UtcNow : file.DateCreated;
        var screenshotSha = Sha256(screenshotBytes);
        var screenshotPath = Path.Combine(evidenceDir, $"screenshot-{screenshotSha}{extension}");
        var relativeScreenshotPath = Path.GetRelativePath(projectDir, screenshotPath);
        var evidence = RuntimeVerificationGuard.CreateEvidence(
            runtime: "RPCS3",
            outputArcSha256: outputHash,
            screenshotBytes: screenshotBytes,
            screenshotPath: relativeScreenshotPath,
            capturedAtUtc: capturedAt.ToUniversalTime(),
            notes: $"Operator-attested RPCS3 evidence for {buildId}; source file {file.Name}; production audit {Path.GetFileName(auditPath)}.");
        RuntimeVerificationGuard.EnsureValidForBuild("RPCS3", outputHash, evidence);
        RuntimeVerificationGuard.VerifyScreenshotBytes(evidence, screenshotBytes);

        var bitmap = new BitmapImage();
        using (var imageStream = await file.OpenAsync(FileAccessMode.Read))
            await bitmap.SetSourceAsync(imageStream);

        var stack = new StackPanel { Spacing = 10, MaxWidth = 900 };
        stack.Children.Add(new TextBlock
        {
            Text =
                $"Build ID: {buildId}\n" +
                $"Output ARC SHA-256: {outputHash}\n" +
                $"Screenshot SHA-256: {evidence.ScreenshotSha256}\n\n" +
                "Confirm only if this screenshot shows this exact Foundry build running correctly in RPCS3. " +
                "Foundry cannot infer that from the image alone; this is an explicit operator attestation.",
            TextWrapping = TextWrapping.Wrap,
        });
        stack.Children.Add(new Border
        {
            Height = 520,
            Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 18, 18, 18)),
            Child = new Image
            {
                Source = bitmap,
                Stretch = Microsoft.UI.Xaml.Media.Stretch.Uniform,
            },
        });

        var dialog = new ContentDialog
        {
            XamlRoot = WorkspacePanel.XamlRoot,
            Title = "Bind RPCS3 runtime evidence to this exact build",
            PrimaryButtonText = "Mark this build Runtime Verified",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            Content = stack,
        };
        var result = await dialog.ShowAsync();
        if (result != ContentDialogResult.Primary)
        {
            SearchStatusText.Text = "Runtime evidence was not accepted. Build remains Built, not Runtime Verified.";
            return;
        }

        // Final anti-stale gate after the human reviewed the screenshot.
        if (!Sha256(File.ReadAllBytes(outputArcPath)).Equals(outputHash, StringComparison.Ordinal))
            throw new InvalidDataException("Production ARC changed during runtime-evidence review; attestation was discarded.");

        await PersistContentAddressedAsync(screenshotPath, screenshotBytes, evidence.ScreenshotSha256);
        RuntimeVerificationGuard.VerifyScreenshotBytes(evidence, await File.ReadAllBytesAsync(screenshotPath));
        RuntimeVerificationGuard.EnsureValidForBuild("RPCS3", outputHash, evidence);
        var state = RuntimeVerificationGuard.PromoteToRuntimeVerified(
            AssetApprovalState.Built,
            "RPCS3",
            outputHash,
            evidence);
        if (state != AssetApprovalState.RuntimeVerified)
            throw new InvalidOperationException("Runtime verification guard did not return RuntimeVerified state.");

        var evidenceJsonPath = Path.Combine(evidenceDir, "runtime-evidence.json");
        await WriteAtomicRuntimeEvidenceJsonAsync(evidenceJsonPath, evidence);
        var loaded = await LoadRuntimeEvidenceAsync(evidenceJsonPath);
        RuntimeVerificationGuard.EnsureValidForBuild("RPCS3", outputHash, loaded);
        RuntimeVerificationGuard.VerifyScreenshotBytes(loaded, await File.ReadAllBytesAsync(screenshotPath));

        _runtimeVerificationEvidence = loaded;
        WriteVerifiedBuildResumeState(evidenceJsonPath);
        SendForApprovalButton.Content = "Runtime Verified";
        SendForApprovalButton.IsEnabled = false;
        SearchStatusText.Text =
            $"RUNTIME VERIFIED · {buildId} · RPCS3 screenshot {loaded.ScreenshotSha256[..12]}… · evidence {evidenceJsonPath}";
    }

    private static async Task WriteAtomicRuntimeEvidenceJsonAsync(
        string path,
        RuntimeVerificationEvidence evidence)
    {
        var full = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(full)!);
        var temp = full + ".tmp." + Guid.NewGuid().ToString("N");
        try
        {
            await using var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            await JsonSerializer.SerializeAsync(stream, evidence, new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            });
            await stream.FlushAsync();
            File.Move(temp, full, overwrite: true);
        }
        finally
        {
            if (File.Exists(temp))
                File.Delete(temp);
        }
    }

    private static async Task<RuntimeVerificationEvidence> LoadRuntimeEvidenceAsync(string path)
    {
        await using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return await JsonSerializer.DeserializeAsync<RuntimeVerificationEvidence>(stream, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        }) ?? throw new InvalidDataException("Runtime evidence JSON was empty.");
    }

    private sealed record VerifiedBuildResumeState(
        int Schema,
        string OutputArcRelativePath,
        string AuditRelativePath,
        string OutputArcSha256,
        string BuildId,
        string? RuntimeEvidenceRelativePath,
        DateTimeOffset UpdatedAtUtc);
}
