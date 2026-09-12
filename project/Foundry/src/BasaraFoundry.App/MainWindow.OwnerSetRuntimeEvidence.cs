using System.Text.Json;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Arc;
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
    private VerifiedOwnerSetBuild? _verifiedOwnerSetBuild;
    private string? _verifiedOwnerSetBuildSetSha256;
    private string? _verifiedOwnerSetAnchorOutputSha256;
    private string? _verifiedOwnerSetFinalResourceSha256;
    private string? _verifiedOwnerSetBuildId;
    private DateTimeOffset? _ownerSetEncodedResultApprovedAtUtc;
    private OwnerSetRuntimeVerificationEvidence? _ownerSetRuntimeVerificationEvidence;

    private bool HasVerifiedOwnerSetBuildAwaitingRuntimeEvidence =>
        _verifiedOwnerSetBuild is not null &&
        _ownerSetRuntimeVerificationEvidence is null &&
        _ownerSetEncodedResultApprovedAtUtc is not null &&
        !string.IsNullOrWhiteSpace(_verifiedOwnerSetBuildSetSha256) &&
        !string.IsNullOrWhiteSpace(_verifiedOwnerSetAnchorOutputSha256) &&
        !string.IsNullOrWhiteSpace(_verifiedOwnerSetFinalResourceSha256) &&
        !string.IsNullOrWhiteSpace(_verifiedOwnerSetBuildId);

    private void ResetOwnerSetRuntimeEvidenceState()
    {
        _verifiedOwnerSetBuild = null;
        _verifiedOwnerSetBuildSetSha256 = null;
        _verifiedOwnerSetAnchorOutputSha256 = null;
        _verifiedOwnerSetFinalResourceSha256 = null;
        _verifiedOwnerSetBuildId = null;
        _ownerSetEncodedResultApprovedAtUtc = null;
        _ownerSetRuntimeVerificationEvidence = null;
    }

    /// <summary>
    /// Starts the second human approval gate for a synchronized owner-set build.
    /// The active owner texture is shown because every certified owner is required
    /// to contain the same final XET hash, but approval/runtime evidence binds the
    /// complete deterministic BuildSetSha256 rather than only the active ARC.
    /// </summary>
    private void SetVerifiedOwnerSetBuildForRuntimeEvidence(VerifiedOwnerSetBuild build)
    {
        ArgumentNullException.ThrowIfNull(build);
        var group = RevalidateOwnerSetOnDisk(build);

        // A production review must represent exactly one build kind at a time.
        ResetRuntimeEvidenceState();
        ResetOwnerSetRuntimeEvidenceState();
        SendForApprovalButton.Content = "Review synchronized encoded result";
        SendForApprovalButton.IsEnabled = false;
        SearchStatusText.Text =
            $"All {group.OwnerCount} owner ARCs passed structural verification. The actual encoded texture still requires explicit visual approval before owner-set runtime evidence can be attached.";

        BeginOwnerSetEncodedResultReview(build);
    }

    private async void BeginOwnerSetEncodedResultReview(VerifiedOwnerSetBuild build)
    {
        try
        {
            var group = RevalidateOwnerSetOnDisk(build);
            var candidate = _candidateReview;
            var proposal = _editMaskProposal;
            if (candidate is null || proposal is null)
                throw new InvalidOperationException("Candidate/mask review state disappeared before synchronized encoded-result approval.");
            if (!group.CandidateRgbaSha256.Equals(candidate.Sha256, StringComparison.Ordinal) ||
                !group.EditMaskSha256.Equals(proposal.MaskSha256, StringComparison.Ordinal))
            {
                throw new InvalidDataException("Synchronized build is not bound to the currently reviewed candidate and edit mask.");
            }

            var finalResource = ReadAuditedFinalResource(build.ActiveOwnerOutputArcPath, build.ActiveOwnerAudit);
            var finalHash = Sha256(finalResource);
            if (!finalHash.Equals(group.FinalResourceSha256, StringComparison.Ordinal))
                throw new InvalidDataException("Active owner final XET does not match the synchronized build-set final-resource hash.");
            var decoded = UtageXetCodec.DecodeTopLevel(finalResource);

            var ownerList = string.Join("\n", group.Owners.Select(owner => $"• {owner.ArchivePath} [{owner.MemberIndex}] · {owner.OutputArcSha256[..12]}…"));
            var stack = new StackPanel { Spacing = 10, MaxWidth = 960 };
            stack.Children.Add(new TextBlock
            {
                Text =
                    $"This is the ACTUAL BC3-decoded texture from the active ARC inside a synchronized {group.OwnerCount}-owner build.\n" +
                    "Every owner has already been proven to contain this same final XET hash. Approval below binds the WHOLE owner set, not just this ARC.\n\n" +
                    $"Build-set SHA-256: {group.BuildSetSha256}\n" +
                    $"Final XET SHA-256: {group.FinalResourceSha256}\n" +
                    $"Candidate: {group.CandidateRgbaSha256[..16]}…\n" +
                    $"Mask: {group.EditMaskSha256[..16]}…\n\n" +
                    $"Synchronized owners:\n{ownerList}\n\n" +
                    "Approve only if the complete encoded sheet still looks correct. This is separate from approving the intended edit mask.",
                TextWrapping = TextWrapping.Wrap,
            });
            stack.Children.Add(new Border
            {
                Height = 540,
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
                Title = $"Review final synchronized production result ({group.OwnerCount} ARCs)",
                PrimaryButtonText = "Approve owner-set result",
                CloseButtonText = "Reject",
                DefaultButton = ContentDialogButton.Close,
                Content = stack,
            };
            var result = await dialog.ShowAsync();
            if (result != ContentDialogResult.Primary)
            {
                _editMaskApproved = false;
                ResetOwnerSetRuntimeEvidenceState();
                SearchStatusText.Text =
                    "Synchronized encoded result was rejected. Generated owner-set ARCs remain unapproved build artifacts; canonical sources are unchanged.";
                ProtectedPixelsText.Text = "OWNER-SET ENCODED RESULT REJECTED · source files unchanged";
                SendForApprovalButton.Content = "Review edit mask";
                SendForApprovalButton.IsEnabled = false;
                return;
            }

            if (_candidateReview?.Sha256 != candidate.Sha256 ||
                _editMaskProposal?.MaskSha256 != proposal.MaskSha256)
                throw new InvalidOperationException("Candidate or edit mask changed during synchronized encoded-result review; approval was discarded.");

            var afterReview = RevalidateOwnerSetOnDisk(build);
            if (!afterReview.BuildSetSha256.Equals(group.BuildSetSha256, StringComparison.Ordinal) ||
                !afterReview.FinalResourceSha256.Equals(finalHash, StringComparison.Ordinal))
            {
                throw new InvalidDataException("Synchronized owner set changed during encoded-result review; approval was discarded.");
            }

            _verifiedOwnerSetBuild = build;
            _verifiedOwnerSetBuildSetSha256 = group.BuildSetSha256;
            _verifiedOwnerSetAnchorOutputSha256 = build.ActiveOwnerAudit.OutputArcSha256;
            _verifiedOwnerSetFinalResourceSha256 = finalHash;
            _verifiedOwnerSetBuildId = OwnerSetRuntimeVerificationGuard.BuildIdForSet(group.BuildSetSha256);
            _ownerSetEncodedResultApprovedAtUtc = DateTimeOffset.UtcNow;
            _ownerSetRuntimeVerificationEvidence = null;

            ProtectedPixelsText.Text =
                $"OWNER SET APPROVED · {group.OwnerCount} synchronized ARCs · final XET {finalHash[..12]}…";
            SendForApprovalButton.Content = "Attach RPCS3 owner-set verification";
            SendForApprovalButton.IsEnabled = true;
            SearchStatusText.Text =
                $"Encoded owner set approved for {_verifiedOwnerSetBuildId}. Runtime Verified remains blocked until RPCS3 evidence is explicitly bound to this exact {group.OwnerCount}-ARC build set.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or ArgumentException or InvalidOperationException or JsonException)
        {
            ResetOwnerSetRuntimeEvidenceState();
            SendForApprovalButton.Content = "Review edit mask";
            SendForApprovalButton.IsEnabled = false;
            SearchStatusText.Text = $"Synchronized encoded-result approval stopped safely: {ex.Message}";
        }
    }

    private SharedOwnerXetGraftGroupAudit RevalidateOwnerSetOnDisk(VerifiedOwnerSetBuild build)
    {
        if (!Directory.Exists(build.BuildDirectory) || !File.Exists(build.GroupAuditPath))
            throw new InvalidDataException("Synchronized build directory/group audit no longer exists.");

        var group = JsonSerializer.Deserialize<SharedOwnerXetGraftGroupAudit>(
            File.ReadAllText(build.GroupAuditPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidDataException("Synchronized group audit was empty.");
        UtageSharedOwnerAuditVerifier.EnsureValid(group);
        if (!group.BuildSetSha256.Equals(build.GroupAudit.BuildSetSha256, StringComparison.Ordinal) ||
            group.OwnerCount != build.GroupAudit.OwnerCount ||
            !group.ResourceName.Equals(build.GroupAudit.ResourceName, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Synchronized group audit changed after build verification.");
        }

        foreach (var owner in group.Owners)
        {
            var outputArc = SharedOwnerOutputPath(build.BuildDirectory, owner.ArchivePath);
            var auditPath = outputArc + ".audit.json";
            if (!File.Exists(outputArc) || !File.Exists(auditPath))
                throw new InvalidDataException($"Synchronized owner output/audit is missing for '{owner.ArchivePath}'.");
            if (!Sha256(File.ReadAllBytes(outputArc)).Equals(owner.OutputArcSha256, StringComparison.Ordinal))
                throw new InvalidDataException($"Synchronized owner ARC changed on disk: '{owner.ArchivePath}'.");

            var audit = JsonSerializer.Deserialize<SingleEntryXetGraftAudit>(
                File.ReadAllText(auditPath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new InvalidDataException($"Synchronized per-owner audit is empty for '{owner.ArchivePath}'.");
            if (!audit.SourceArcSha256.Equals(owner.SourceArcSha256, StringComparison.Ordinal) ||
                !audit.OutputArcSha256.Equals(owner.OutputArcSha256, StringComparison.Ordinal) ||
                !audit.TargetResourceSha256.Equals(owner.TargetResourceSha256, StringComparison.Ordinal) ||
                !audit.FinalResourceSha256.Equals(owner.FinalResourceSha256, StringComparison.Ordinal) ||
                !audit.FinalResourceSha256.Equals(group.FinalResourceSha256, StringComparison.Ordinal) ||
                !audit.TargetShellPreserved || !audit.ArcRoundTripVerified || !audit.ApprovedEligible ||
                audit.OutsideEffectiveBlockPixelDelta != 0)
            {
                throw new InvalidDataException($"Synchronized per-owner audit no longer satisfies group invariants for '{owner.ArchivePath}'.");
            }
            var finalResource = ReadAuditedFinalResource(outputArc, audit);
            if (!Sha256(finalResource).Equals(group.FinalResourceSha256, StringComparison.Ordinal))
                throw new InvalidDataException($"Synchronized final XET changed on disk for '{owner.ArchivePath}'.");
        }

        return group;
    }

    private async Task AttachOwnerSetRuntimeEvidenceAsync()
    {
        var build = _verifiedOwnerSetBuild;
        var expectedSetHash = _verifiedOwnerSetBuildSetSha256;
        var expectedAnchorHash = _verifiedOwnerSetAnchorOutputSha256;
        var expectedFinalHash = _verifiedOwnerSetFinalResourceSha256;
        var buildId = _verifiedOwnerSetBuildId;
        if (build is null || string.IsNullOrWhiteSpace(expectedSetHash) || string.IsNullOrWhiteSpace(expectedAnchorHash) ||
            string.IsNullOrWhiteSpace(expectedFinalHash) || string.IsNullOrWhiteSpace(buildId) ||
            _ownerSetEncodedResultApprovedAtUtc is null)
        {
            throw new InvalidOperationException("No encoded-result-approved synchronized owner set is awaiting runtime evidence.");
        }

        var group = RevalidateOwnerSetOnDisk(build);
        if (!group.BuildSetSha256.Equals(expectedSetHash, StringComparison.Ordinal) ||
            !build.ActiveOwnerAudit.OutputArcSha256.Equals(expectedAnchorHash, StringComparison.Ordinal) ||
            !group.FinalResourceSha256.Equals(expectedFinalHash, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Approved synchronized build no longer matches its saved runtime-evidence binding.");
        }

        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.PicturesLibrary };
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

        group = RevalidateOwnerSetOnDisk(build);
        if (!group.BuildSetSha256.Equals(expectedSetHash, StringComparison.Ordinal))
            throw new InvalidDataException("Synchronized owner set changed while selecting runtime evidence.");

        var projectDir = Path.GetDirectoryName(_projectPath)!;
        var evidenceDir = Path.Combine(projectDir, "runtime-evidence", buildId);
        Directory.CreateDirectory(evidenceDir);
        var extension = Path.GetExtension(file.Name).ToLowerInvariant();
        if (extension is not (".png" or ".jpg" or ".jpeg"))
            throw new InvalidDataException("Runtime evidence must be a PNG or JPEG screenshot.");

        var capturedAt = file.DateCreated == default ? DateTimeOffset.UtcNow : file.DateCreated;
        var screenshotSha = Sha256(screenshotBytes);
        var screenshotPath = Path.Combine(evidenceDir, $"screenshot-{screenshotSha}{extension}");
        var relativeScreenshotPath = Path.GetRelativePath(projectDir, screenshotPath);
        var evidence = OwnerSetRuntimeVerificationGuard.CreateEvidence(
            runtime: "RPCS3",
            buildSetSha256: expectedSetHash,
            anchorOutputArcSha256: expectedAnchorHash,
            screenshotBytes: screenshotBytes,
            screenshotPath: relativeScreenshotPath,
            capturedAtUtc: capturedAt.ToUniversalTime(),
            notes: $"Operator-attested RPCS3 evidence for synchronized {group.OwnerCount}-ARC build {buildId}; source screenshot {file.Name}; encoded owner set approved {_ownerSetEncodedResultApprovedAtUtc:O}.");
        OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", expectedSetHash, expectedAnchorHash, evidence);
        OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(evidence, screenshotBytes);

        var bitmap = new BitmapImage();
        using (var imageStream = await file.OpenAsync(FileAccessMode.Read))
            await bitmap.SetSourceAsync(imageStream);

        var stack = new StackPanel { Spacing = 10, MaxWidth = 920 };
        stack.Children.Add(new TextBlock
        {
            Text =
                $"Build ID: {buildId}\n" +
                $"Synchronized owner count: {group.OwnerCount}\n" +
                $"Build-set SHA-256: {expectedSetHash}\n" +
                $"Anchor ARC SHA-256: {expectedAnchorHash}\n" +
                $"Final XET SHA-256: {expectedFinalHash}\n" +
                $"Screenshot SHA-256: {evidence.ScreenshotSha256}\n\n" +
                $"Confirm only if ALL {group.OwnerCount} .foundry.arc outputs from this exact owner-set build were installed together and this screenshot shows that build running correctly in RPCS3. " +
                "Foundry cannot infer installation provenance from the screenshot; this is an explicit operator attestation.",
            TextWrapping = TextWrapping.Wrap,
        });
        stack.Children.Add(new Border
        {
            Height = 520,
            Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 18, 18, 18)),
            Child = new Image { Source = bitmap, Stretch = Microsoft.UI.Xaml.Media.Stretch.Uniform },
        });

        var dialog = new ContentDialog
        {
            XamlRoot = WorkspacePanel.XamlRoot,
            Title = "Bind RPCS3 evidence to the complete synchronized owner set",
            PrimaryButtonText = "Mark owner set Runtime Verified",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            Content = stack,
        };
        var result = await dialog.ShowAsync();
        if (result != ContentDialogResult.Primary)
        {
            SearchStatusText.Text = "Owner-set runtime evidence was not accepted. Build remains Built, not Runtime Verified.";
            return;
        }

        group = RevalidateOwnerSetOnDisk(build);
        if (!group.BuildSetSha256.Equals(expectedSetHash, StringComparison.Ordinal))
            throw new InvalidDataException("Synchronized owner set changed during runtime-evidence review; attestation was discarded.");

        await PersistContentAddressedAsync(screenshotPath, screenshotBytes, evidence.ScreenshotSha256);
        OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(evidence, await File.ReadAllBytesAsync(screenshotPath));
        OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", expectedSetHash, expectedAnchorHash, evidence);
        var state = OwnerSetRuntimeVerificationGuard.PromoteToRuntimeVerified(
            AssetApprovalState.Built,
            "RPCS3",
            expectedSetHash,
            expectedAnchorHash,
            evidence);
        if (state != AssetApprovalState.RuntimeVerified)
            throw new InvalidOperationException("Owner-set runtime verification guard did not return RuntimeVerified state.");

        var evidenceJsonPath = Path.Combine(evidenceDir, "owner-set-runtime-evidence.json");
        await WriteAtomicOwnerSetRuntimeEvidenceJsonAsync(evidenceJsonPath, evidence);
        var loaded = JsonSerializer.Deserialize<OwnerSetRuntimeVerificationEvidence>(
            await File.ReadAllTextAsync(evidenceJsonPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidDataException("Persisted owner-set runtime evidence was empty.");
        OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", expectedSetHash, expectedAnchorHash, loaded);
        OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(loaded, await File.ReadAllBytesAsync(screenshotPath));

        _ownerSetRuntimeVerificationEvidence = loaded;
        SendForApprovalButton.Content = "Owner set Runtime Verified";
        SendForApprovalButton.IsEnabled = false;
        SearchStatusText.Text =
            $"RUNTIME VERIFIED · synchronized {group.OwnerCount}-ARC build {buildId} · RPCS3 screenshot {loaded.ScreenshotSha256[..12]}… · evidence {evidenceJsonPath}";
    }

    private static async Task WriteAtomicOwnerSetRuntimeEvidenceJsonAsync(
        string path,
        OwnerSetRuntimeVerificationEvidence evidence)
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
}
