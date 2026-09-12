using System.Text.Json;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Preview;
using BasaraFoundry.Game.Utage.Xet;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private const int VerifiedBuildResumeSchema = 2;
    private string? _verifiedBuildArcPath;
    private string? _verifiedBuildAuditPath;
    private string? _verifiedBuildOutputSha256;
    private string? _verifiedBuildFinalResourceSha256;
    private string? _verifiedBuildId;
    private DateTimeOffset? _encodedResultApprovedAtUtc;
    private RuntimeVerificationEvidence? _runtimeVerificationEvidence;

    private bool HasVerifiedBuildAwaitingRuntimeEvidence =>
        _runtimeVerificationEvidence is null &&
        _encodedResultApprovedAtUtc is not null &&
        !string.IsNullOrWhiteSpace(_verifiedBuildArcPath) &&
        !string.IsNullOrWhiteSpace(_verifiedBuildOutputSha256) &&
        !string.IsNullOrWhiteSpace(_verifiedBuildFinalResourceSha256) &&
        !string.IsNullOrWhiteSpace(_verifiedBuildId);

    private string ProjectDirectory => Path.GetDirectoryName(_projectPath)!;

    private string VerifiedBuildResumeStatePath =>
        Path.Combine(ProjectDirectory, "state", "last-verified-build.json");

    private void ResetRuntimeEvidenceState()
    {
        _verifiedBuildArcPath = null;
        _verifiedBuildAuditPath = null;
        _verifiedBuildOutputSha256 = null;
        _verifiedBuildFinalResourceSha256 = null;
        _verifiedBuildId = null;
        _encodedResultApprovedAtUtc = null;
        _runtimeVerificationEvidence = null;
    }

    /// <summary>
    /// A structurally verified worker build is NOT yet an operator-approved build.
    /// This method deliberately starts a second review of the actual decoded BC3
    /// output. Only explicit approval of those final bytes unlocks runtime evidence.
    /// </summary>
    private void SetVerifiedBuildForRuntimeEvidence(
        SingleEntryXetGraftAudit audit,
        string outputArcPath,
        string auditPath)
    {
        ArgumentNullException.ThrowIfNull(audit);
        outputArcPath = Path.GetFullPath(outputArcPath);
        auditPath = Path.GetFullPath(auditPath);
        if (!File.Exists(outputArcPath) || !File.Exists(auditPath))
            throw new InvalidDataException("Verified production ARC/audit pair is missing before encoded-result review.");

        var physicalHash = Sha256(File.ReadAllBytes(outputArcPath));
        ValidateProductionAuditForResume(audit, physicalHash);

        // Fail closed until the human has reviewed the actual encoded bytes.
        ResetRuntimeEvidenceState();
        SendForApprovalButton.Content = "Review encoded result";
        SendForApprovalButton.IsEnabled = false;
        SearchStatusText.Text =
            "Worker build passed structural verification. Final BC3 output still requires explicit visual approval before runtime evidence can be attached.";

        BeginEncodedResultReview(audit, outputArcPath, auditPath);
    }

    private async void BeginEncodedResultReview(
        SingleEntryXetGraftAudit audit,
        string outputArcPath,
        string auditPath)
    {
        try
        {
            var expectedOutputHash = audit.OutputArcSha256;
            var candidate = _candidateReview;
            var proposal = _editMaskProposal;
            if (candidate is null || proposal is null)
                throw new InvalidOperationException("Candidate/mask review state disappeared before encoded-result approval.");
            if (!audit.CandidateRgbaSha256.Equals(candidate.Sha256, StringComparison.Ordinal) ||
                !audit.EditMaskSha256.Equals(proposal.MaskSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Encoded result is not bound to the currently reviewed candidate and edit mask.");

            var finalResource = ReadAuditedFinalResource(outputArcPath, audit);
            var finalHash = Sha256(finalResource);
            if (!finalHash.Equals(audit.FinalResourceSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Decoded-review resource does not match the production audit final-resource hash.");

            var decoded = UtageXetCodec.DecodeTopLevel(finalResource);
            var stack = new StackPanel { Spacing = 10, MaxWidth = 940 };
            stack.Children.Add(new TextBlock
            {
                Text =
                    $"This is the ACTUAL BC3-decoded texture inside the built sibling ARC.\n\n" +
                    $"Touched BC3 blocks: {audit.BlocksReplaced:N0}/{audit.BlocksTotal:N0}\n" +
                    $"Exact edit-mask pixels: {audit.MaskPixels:N0}\n" +
                    $"Compression collateral inside touched blocks: {audit.CompressionCollateralPixels:N0} px\n" +
                    $"Protected-pixel delta outside touched blocks: {audit.OutsideEffectiveBlockPixelDelta:N0} px\n\n" +
                    $"Output ARC: {audit.OutputArcSha256[..16]}…\n" +
                    $"Final XET: {audit.FinalResourceSha256[..16]}…\n" +
                    $"Candidate: {audit.CandidateRgbaSha256[..16]}…\n" +
                    $"Mask: {audit.EditMaskSha256[..16]}…\n\n" +
                    "Approve only if the complete encoded sheet still looks correct. This approval is separate from approving the intended edit mask.",
                TextWrapping = TextWrapping.Wrap,
            });
            stack.Children.Add(new Border
            {
                Height = 560,
                Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 18, 18, 18)),
                Child = new Image
                {
                    Source = PreviewBitmapFactory.FromRgba(decoded.Width, decoded.Height, decoded.Rgba),
                    Stretch = Microsoft.UI.Xaml.Media.Stretch.Uniform,
                },
            });

            var dialog = new ContentDialog
            {
                XamlRoot = WorkspacePanel.XamlRoot,
                Title = "Review final encoded production result",
                PrimaryButtonText = "Approve encoded result",
                CloseButtonText = "Reject",
                DefaultButton = ContentDialogButton.Close,
                Content = stack,
            };

            var result = await dialog.ShowAsync();
            if (result != ContentDialogResult.Primary)
            {
                _editMaskApproved = false;
                SearchStatusText.Text =
                    "Encoded result was rejected. The sibling ARC remains an unapproved build artifact; canonical sources are unchanged. Adjust the candidate before rebuilding.";
                ProtectedPixelsText.Text = "ENCODED RESULT REJECTED · source files unchanged";
                SendForApprovalButton.Content = "Review edit mask";
                SendForApprovalButton.IsEnabled = false;
                return;
            }

            // Anti-stale checks after the operator spent time looking at the image.
            var physicalHashAfterReview = Sha256(File.ReadAllBytes(outputArcPath));
            if (!physicalHashAfterReview.Equals(expectedOutputHash, StringComparison.Ordinal))
                throw new InvalidDataException("Production ARC changed during encoded-result review; approval was discarded.");
            if (_candidateReview?.Sha256 != candidate.Sha256 ||
                _editMaskProposal?.MaskSha256 != proposal.MaskSha256)
                throw new InvalidOperationException("Candidate or edit mask changed during encoded-result review; approval was discarded.");

            var finalResourceAfterReview = ReadAuditedFinalResource(outputArcPath, audit);
            if (!Sha256(finalResourceAfterReview).Equals(finalHash, StringComparison.Ordinal))
                throw new InvalidDataException("Final XET changed during encoded-result review; approval was discarded.");

            _verifiedBuildArcPath = outputArcPath;
            _verifiedBuildAuditPath = auditPath;
            _verifiedBuildOutputSha256 = expectedOutputHash;
            _verifiedBuildFinalResourceSha256 = finalHash;
            _verifiedBuildId = RuntimeVerificationGuard.BuildIdForArc(expectedOutputHash);
            _encodedResultApprovedAtUtc = DateTimeOffset.UtcNow;
            _runtimeVerificationEvidence = null;
            WriteVerifiedBuildResumeState(runtimeEvidenceJsonPath: null);

            ProtectedPixelsText.Text =
                $"ENCODED RESULT APPROVED · {audit.BlocksReplaced}/{audit.BlocksTotal} BC3 blocks · protected pixels unchanged";
            SendForApprovalButton.Content = "Attach RPCS3 verification screenshot";
            SendForApprovalButton.IsEnabled = true;
            SearchStatusText.Text =
                $"Encoded output approved for {_verifiedBuildId}. Runtime Verified remains blocked until RPCS3 evidence is bound to this exact ARC hash.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or ArgumentException or InvalidOperationException)
        {
            ResetRuntimeEvidenceState();
            SendForApprovalButton.Content = "Review edit mask";
            SendForApprovalButton.IsEnabled = false;
            SearchStatusText.Text = $"Encoded-result approval stopped safely: {ex.Message}";
        }
    }

    private static byte[] ReadAuditedFinalResource(string outputArcPath, SingleEntryXetGraftAudit audit)
    {
        using var outputStream = File.Open(outputArcPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var rebuilt = UtageArcReader.Read(outputStream, outputArcPath);
        if ((uint)audit.MemberIndex >= (uint)rebuilt.Entries.Count)
            throw new InvalidDataException("Built ARC no longer contains the audited target member.");
        var rebuiltEntry = rebuilt.Entries[audit.MemberIndex];
        if (!rebuiltEntry.Name.Equals(audit.MemberName, StringComparison.Ordinal))
            throw new InvalidDataException("Built ARC member identity no longer matches the audit.");
        outputStream.Position = 0;
        return UtageArcReader.ReadDecompressedPayload(outputStream, rebuiltEntry);
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
            if (saved.EncodedResultApprovedAtUtc == default || string.IsNullOrWhiteSpace(saved.FinalResourceSha256))
                throw new InvalidDataException("Saved build has no encoded-result approval binding.");

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
            if (!audit.FinalResourceSha256.Equals(saved.FinalResourceSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Saved encoded-result approval belongs to a different final XET hash.");
            var finalResource = ReadAuditedFinalResource(outputArcPath, audit);
            if (!Sha256(finalResource).Equals(saved.FinalResourceSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Saved approved final XET changed on disk.");

            var buildId = RuntimeVerificationGuard.BuildIdForArc(physicalHash);
            if (!buildId.Equals(saved.BuildId, StringComparison.Ordinal))
                throw new InvalidDataException("Saved build ID does not match the verified ARC hash.");

            _verifiedBuildArcPath = outputArcPath;
            _verifiedBuildAuditPath = auditPath;
            _verifiedBuildOutputSha256 = physicalHash;
            _verifiedBuildFinalResourceSha256 = saved.FinalResourceSha256;
            _verifiedBuildId = buildId;
            _encodedResultApprovedAtUtc = saved.EncodedResultApprovedAtUtc;
            _runtimeVerificationEvidence = null;

            SendForApprovalButton.Content = "Attach RPCS3 verification screenshot";
            SendForApprovalButton.IsEnabled = true;
            SearchStatusText.Text = $"Restored encoded-result-approved build {buildId}. RPCS3 runtime evidence is still required.";

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
                WriteVerifiedBuildResumeState(runtimeEvidenceJsonPath: null);
                SearchStatusText.Text =
                    $"Restored encoded-result-approved build {buildId}, but previous RPCS3 evidence was rejected: {ex.Message} " +
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
        if (audit.Schema != 4)
            throw new NotSupportedException($"Unsupported production graft audit schema {audit.Schema}; target-shell production requires schema 4.");
        if (!audit.GraftOk || !audit.ArcRoundTripVerified || !audit.ApprovedEligible ||
            !audit.UsedPristineOverride || !audit.TargetShellPreserved)
            throw new InvalidDataException("Production audit is not eligible to restore a target-shell-preserving verified build.");
        if (audit.OutsideMaskPixelDelta != 0 || audit.OutsideEffectiveBlockPixelDelta != 0)
            throw new InvalidDataException("Production audit reports changed pixels outside the certified edit footprint.");
        if (!audit.OutputArcSha256.Equals(physicalOutputHash, StringComparison.Ordinal))
            throw new InvalidDataException("Production audit output hash does not match the physical ARC.");
        if (audit.MemberIndex < 0 || string.IsNullOrWhiteSpace(audit.MemberName))
            throw new InvalidDataException("Production audit member identity is invalid.");
        foreach (var hash in new[]
        {
            audit.SourceArcSha256,
            audit.OutputArcSha256,
            audit.TargetResourceSha256,
            audit.PristineBaseSha256,
            audit.CandidateRgbaSha256,
            audit.EditMaskSha256,
            audit.FinalResourceSha256,
        })
        {
            if (hash.Length != 64 || hash.Any(c => !Uri.IsHexDigit(c)))
                throw new InvalidDataException("Production audit contains an invalid SHA-256 binding.");
        }
    }

    private void WriteVerifiedBuildResumeState(string? runtimeEvidenceJsonPath)
    {
        var outputArc = _verifiedBuildArcPath
            ?? throw new InvalidOperationException("Verified build ARC path is missing.");
        var auditPath = _verifiedBuildAuditPath
            ?? throw new InvalidOperationException("Verified build audit path is missing.");
        var outputHash = _verifiedBuildOutputSha256
            ?? throw new InvalidOperationException("Verified build hash is missing.");
        var finalResourceHash = _verifiedBuildFinalResourceSha256
            ?? throw new InvalidOperationException("Approved final resource hash is missing.");
        var buildId = _verifiedBuildId
            ?? throw new InvalidOperationException("Verified build ID is missing.");
        var approvedAt = _encodedResultApprovedAtUtc
            ?? throw new InvalidOperationException("Encoded-result approval timestamp is missing.");

        var saved = new VerifiedBuildResumeState(
            Schema: VerifiedBuildResumeSchema,
            OutputArcRelativePath: ToProjectRelativePath(outputArc),
            AuditRelativePath: ToProjectRelativePath(auditPath),
            OutputArcSha256: outputHash,
            FinalResourceSha256: finalResourceHash,
            BuildId: buildId,
            EncodedResultApprovedAtUtc: approvedAt,
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
        var finalResourceHash = _verifiedBuildFinalResourceSha256;
        var buildId = _verifiedBuildId;
        var auditPath = _verifiedBuildAuditPath;
        if (string.IsNullOrWhiteSpace(outputArcPath) ||
            string.IsNullOrWhiteSpace(outputHash) ||
            string.IsNullOrWhiteSpace(finalResourceHash) ||
            string.IsNullOrWhiteSpace(buildId) ||
            string.IsNullOrWhiteSpace(auditPath) ||
            _encodedResultApprovedAtUtc is null)
        {
            throw new InvalidOperationException("No encoded-result-approved production build is awaiting runtime evidence.");
        }
        if (!File.Exists(outputArcPath) || !File.Exists(auditPath))
            throw new InvalidDataException("Verified build/audit pair no longer exists.");
        if (!Sha256(File.ReadAllBytes(outputArcPath)).Equals(outputHash, StringComparison.Ordinal))
            throw new InvalidDataException("Production ARC changed after encoded-result approval; runtime evidence cannot be attached to a stale build.");

        var currentAudit = JsonSerializer.Deserialize<SingleEntryXetGraftAudit>(
            File.ReadAllText(auditPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidDataException("Production audit was empty before runtime-evidence handoff.");
        ValidateProductionAuditForResume(currentAudit, outputHash);
        if (!Sha256(ReadAuditedFinalResource(outputArcPath, currentAudit)).Equals(finalResourceHash, StringComparison.Ordinal))
            throw new InvalidDataException("Final XET changed after encoded-result approval; runtime evidence cannot be attached.");

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
            notes: $"Operator-attested RPCS3 evidence for {buildId}; source file {file.Name}; production audit {Path.GetFileName(auditPath)}; encoded result approved {_encodedResultApprovedAtUtc:O}.");
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
                $"Approved final XET SHA-256: {finalResourceHash}\n" +
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

        if (!Sha256(File.ReadAllBytes(outputArcPath)).Equals(outputHash, StringComparison.Ordinal))
            throw new InvalidDataException("Production ARC changed during runtime-evidence review; attestation was discarded.");
        if (!Sha256(ReadAuditedFinalResource(outputArcPath, currentAudit)).Equals(finalResourceHash, StringComparison.Ordinal))
            throw new InvalidDataException("Final XET changed during runtime-evidence review; attestation was discarded.");

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
        string FinalResourceSha256,
        string BuildId,
        DateTimeOffset EncodedResultApprovedAtUtc,
        string? RuntimeEvidenceRelativePath,
        DateTimeOffset UpdatedAtUtc);
}
