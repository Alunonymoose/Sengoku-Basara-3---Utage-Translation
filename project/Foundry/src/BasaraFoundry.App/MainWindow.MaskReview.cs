using System.Diagnostics;
using System.Text.Json;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Index;
using BasaraFoundry.Game.Utage.Preview;
using BasaraFoundry.Game.Utage.Xet;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private IndexedUtageResource? _productionJapaneseResource;
    private UtageXetPreviewSnapshot? _productionJapanesePreview;
    private UtageEditMaskProposal? _editMaskProposal;
    private string? _editMaskPath;
    private bool _editMaskApproved;
    private string? _approvedMaskSha256;
    private string? _approvedCandidateSha256;
    private string? _approvedPristineSha256;
    private bool _approvalClickHooked;

    private void ClearJapaneseProductionReference(long generation)
    {
        if (!IsReviewCurrent(generation))
            return;
        _productionJapaneseResource = null;
        _productionJapanesePreview = null;
        ResetMaskReviewState();
    }

    private void SetJapaneseProductionReference(
        IndexedUtageResource resource,
        UtageXetPreviewSnapshot preview,
        long generation)
    {
        if (!IsReviewCurrent(generation))
            return;
        _productionJapaneseResource = resource;
        _productionJapanesePreview = preview;
    }

    private void ResetMaskReviewState()
    {
        _editMaskProposal = null;
        _editMaskPath = null;
        _editMaskApproved = false;
        _approvedMaskSha256 = null;
        _approvedCandidateSha256 = null;
        _approvedPristineSha256 = null;

        if (!_approvalClickHooked)
        {
            SendForApprovalButton.Click += SendForApproval_Click;
            _approvalClickHooked = true;
        }

        SendForApprovalButton.Content = "Review edit mask";
        SendForApprovalButton.IsEnabled = false;
    }

    private async Task RefreshMaskProposalAsync()
    {
        var generation = Volatile.Read(ref _reviewGeneration);
        var candidate = _candidateReview;
        var pristine = _productionJapanesePreview;
        var pristineResource = _productionJapaneseResource;
        var active = _activeResource;

        _editMaskProposal = null;
        _editMaskPath = null;
        _editMaskApproved = false;
        _approvedMaskSha256 = null;
        _approvedCandidateSha256 = null;
        _approvedPristineSha256 = null;
        SendForApprovalButton.Content = "Review edit mask";
        SendForApprovalButton.IsEnabled = false;

        if (candidate is null || pristine is null || pristineResource is null || active is null)
        {
            ProtectedPixelsText.Text = "Protected pixels: waiting for candidate + unique pristine JP reference";
            return;
        }
        if (candidate.Generation != generation || !IsReviewCurrent(generation))
            return;
        if (pristine.Width != _activeWidth || pristine.Height != _activeHeight)
        {
            ProtectedPixelsText.Text = "Protected pixels: BLOCKED — JP counterpart dimensions differ";
            return;
        }

        var proposal = UtageEditMaskProposalService.Create(
            pristine.Rgba,
            candidate.Rgba,
            _activeWidth,
            _activeHeight);
        if (!IsReviewCurrent(generation) || _candidateReview?.Sha256 != candidate.Sha256)
            return;

        if (!proposal.HasChanges)
        {
            ProtectedPixelsText.Text = "Protected pixels: no candidate changes versus pristine JP";
            return;
        }

        var cacheDir = Path.Combine(Path.GetDirectoryName(_projectPath)!, "cache", "masks");
        Directory.CreateDirectory(cacheDir);
        var maskPath = Path.Combine(cacheDir, $"mask-{proposal.MaskSha256}.bin");
        await PersistContentAddressedAsync(maskPath, proposal.Mask01, proposal.MaskSha256);
        if (!IsReviewCurrent(generation) || _candidateReview?.Sha256 != candidate.Sha256)
            return;

        _editMaskProposal = proposal;
        _editMaskPath = maskPath;
        ProtectedPixelsText.Text =
            $"Mask proposal: {proposal.ChangedPixels:N0} exact px · {proposal.AffectedBlocks:N0} BC3 blocks · " +
            $"{proposal.PotentialCollateralPixels:N0} block-neighbour px — REVIEW REQUIRED";
        SendForApprovalButton.Content = "Review edit mask";
        SendForApprovalButton.IsEnabled = true;
    }

    private async void SendForApproval_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            if (!_editMaskApproved)
            {
                await ReviewEditMaskAsync();
                return;
            }

            await BuildApprovedSiblingAsync();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or JsonException or TimeoutException or ArgumentException or InvalidOperationException)
        {
            SearchStatusText.Text = $"Production action stopped safely: {ex.Message}";
        }
    }

    private async Task ReviewEditMaskAsync()
    {
        var proposal = _editMaskProposal;
        var candidate = _candidateReview;
        var pristine = _productionJapanesePreview;
        if (proposal is null || candidate is null || pristine is null)
            throw new InvalidOperationException("A frozen candidate and unique pristine JP reference are required before mask review.");
        if (!MaskBindingsCurrent(proposal, candidate, pristine))
            throw new InvalidOperationException("Mask proposal is stale; regenerate it from the current candidate/reference pair.");

        var overlay = UtageEditMaskProposalService.CreateReviewRgba(candidate.Rgba, proposal);
        var stack = new StackPanel { Spacing = 10, MaxWidth = 820 };
        stack.Children.Add(new TextBlock
        {
            Text = $"Exact changed pixels: {proposal.ChangedPixels:N0}\n" +
                   $"BC3 blocks that will be replaced: {proposal.AffectedBlocks:N0}\n" +
                   $"Pixels inside those blocks but outside the exact mask: {proposal.PotentialCollateralPixels:N0}\n\n" +
                   "Magenta = explicitly edited pixels. Amber = same 4×4 BC3 block, so compression may affect them. Dim = protected/untouched.",
            TextWrapping = TextWrapping.Wrap,
        });
        stack.Children.Add(new Border
        {
            Height = 500,
            Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 18, 18, 18)),
            Child = new Image
            {
                Source = PreviewBitmapFactory.FromRgba(proposal.Width, proposal.Height, overlay),
                Stretch = Microsoft.UI.Xaml.Media.Stretch.Uniform,
            },
        });
        stack.Children.Add(new TextBlock
        {
            Text = $"Candidate {candidate.Sha256[..12]}… · pristine JP {pristine.SourceResourceSha256[..12]}… · mask {proposal.MaskSha256[..12]}…",
            Opacity = 0.65,
            TextWrapping = TextWrapping.Wrap,
        });

        var dialog = new ContentDialog
        {
            XamlRoot = WorkspacePanel.XamlRoot,
            Title = "Review production edit mask",
            PrimaryButtonText = "Approve this mask",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            Content = stack,
        };
        var result = await dialog.ShowAsync();
        if (result != ContentDialogResult.Primary)
        {
            SearchStatusText.Text = "Mask was not approved. No production ARC was built.";
            return;
        }

        if (!MaskBindingsCurrent(proposal, candidate, pristine))
            throw new InvalidOperationException("Review changed while the mask dialog was open; approval was discarded.");

        _editMaskApproved = true;
        _approvedMaskSha256 = proposal.MaskSha256;
        _approvedCandidateSha256 = candidate.Sha256;
        _approvedPristineSha256 = pristine.SourceResourceSha256;
        ProtectedPixelsText.Text =
            $"Mask APPROVED · {proposal.ChangedPixels:N0} px · {proposal.AffectedBlocks:N0} BC3 blocks";
        SendForApprovalButton.Content = "Build verified sibling ARC";
        SendForApprovalButton.IsEnabled = true;
        SearchStatusText.Text = "Edit mask approved. Source files are still untouched; production build is now unlocked.";
    }

    private async Task BuildApprovedSiblingAsync()
    {
        var proposal = _editMaskProposal;
        var candidate = _candidateReview;
        var pristine = _productionJapanesePreview;
        var pristineResource = _productionJapaneseResource;
        var target = _activeResource;
        var engRoot = _project?.Sources.UtageEnglish;
        var jpnRoot = _project?.Sources.UtageJapanese;
        var maskPath = _editMaskPath;

        if (!_editMaskApproved || proposal is null || candidate is null || pristine is null ||
            pristineResource is null || target is null || string.IsNullOrWhiteSpace(engRoot) ||
            string.IsNullOrWhiteSpace(jpnRoot) || string.IsNullOrWhiteSpace(maskPath))
        {
            throw new InvalidOperationException("Production build prerequisites are incomplete.");
        }
        if (!MaskBindingsCurrent(proposal, candidate, pristine) ||
            !string.Equals(_approvedMaskSha256, proposal.MaskSha256, StringComparison.Ordinal) ||
            !string.Equals(_approvedCandidateSha256, candidate.Sha256, StringComparison.Ordinal) ||
            !string.Equals(_approvedPristineSha256, pristine.SourceResourceSha256, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Approved mask binding is stale; review the mask again before building.");
        }

        var projectDir = Path.GetDirectoryName(_projectPath)!;
        var archiveStem = Path.GetFileNameWithoutExtension(target.ArchivePath);
        var buildDir = Path.Combine(projectDir, "builds", "texture-grafts", $"{archiveStem}-{candidate.Sha256[..12]}");
        Directory.CreateDirectory(buildDir);
        var outputArc = Path.Combine(buildDir, $"{archiveStem}.foundry.arc");
        var auditPath = outputArc + ".audit.json";

        SendForApprovalButton.IsEnabled = false;
        SearchStatusText.Text = "Building from pristine JP compressed blocks in the isolated worker; canonical sources remain read only…";

        await RunGraftWorkerAsync(
            Path.GetFullPath(engRoot),
            target,
            Path.GetFullPath(jpnRoot),
            pristineResource,
            candidate.RgbaPath,
            maskPath,
            outputArc,
            auditPath);

        var audit = LoadAndVerifyProductionAudit(
            auditPath,
            outputArc,
            target,
            candidate,
            pristine,
            proposal);

        ProtectedPixelsText.Text =
            $"VERIFIED BUILD · {audit.BlocksReplaced}/{audit.BlocksTotal} BC3 blocks · outside-mask delta {audit.OutsideMaskPixelDelta}";
        SendForApprovalButton.Content = "Verified build created";
        SendForApprovalButton.IsEnabled = false;
        SearchStatusText.Text =
            $"Verified sibling ARC created: {outputArc} · audit {auditPath} · output {audit.OutputArcSha256[..12]}…";
    }

    private bool MaskBindingsCurrent(
        UtageEditMaskProposal proposal,
        CandidateReview candidate,
        UtageXetPreviewSnapshot pristine) =>
        IsReviewCurrent(candidate.Generation) &&
        _candidateReview?.Sha256 == candidate.Sha256 &&
        proposal.CandidateRgbaSha256 == candidate.Sha256 &&
        proposal.PristineRgbaSha256 == Sha256(pristine.Rgba) &&
        pristine.SourceResourceSha256 == _productionJapanesePreview?.SourceResourceSha256;

    private static async Task RunGraftWorkerAsync(
        string engRoot,
        IndexedUtageResource target,
        string jpnRoot,
        IndexedUtageResource pristine,
        string candidateRgbaPath,
        string maskPath,
        string outputArc,
        string auditPath)
    {
        var workerPath = Path.Combine(AppContext.BaseDirectory, "worker", "BasaraFoundry.Worker.exe");
        if (!File.Exists(workerPath))
            throw new FileNotFoundException("The isolated Foundry production worker is missing from this build.", workerPath);

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
            "graft-xet",
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
            "--output-arc", outputArc,
            "--audit", auditPath,
        })
        {
            start.ArgumentList.Add(argument);
        }

        using var process = Process.Start(start)
            ?? throw new IOException("Could not start the isolated Foundry production worker.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Production worker exceeded the 60-second safety limit and was terminated.");
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        if (process.ExitCode != 0)
        {
            var detail = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
            throw new InvalidDataException($"Production worker failed with exit code {process.ExitCode}: {detail.Trim()}");
        }
        if (!File.Exists(outputArc) || !File.Exists(auditPath))
            throw new InvalidDataException("Production worker reported success but did not create both ARC and audit outputs.");
    }

    private static SingleEntryXetGraftAudit LoadAndVerifyProductionAudit(
        string auditPath,
        string outputArc,
        IndexedUtageResource target,
        CandidateReview candidate,
        UtageXetPreviewSnapshot pristine,
        UtageEditMaskProposal proposal)
    {
        using var stream = File.Open(auditPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var audit = JsonSerializer.Deserialize<SingleEntryXetGraftAudit>(stream, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        }) ?? throw new InvalidDataException("Production audit JSON was empty.");

        if (audit.Schema != 3 || !audit.GraftOk || !audit.ArcRoundTripVerified || !audit.ApprovedEligible || !audit.UsedPristineOverride)
            throw new InvalidDataException("Production audit does not represent a fully verified mandatory-pristine transaction.");
        if (audit.MemberIndex != target.EntryIndex || !audit.MemberName.Equals(target.ResourceName, StringComparison.Ordinal))
            throw new InvalidDataException("Production audit member identity does not match the active target.");
        if (!audit.TargetResourceSha256.Equals(_activeSourceResourceSha256, StringComparison.Ordinal))
            throw new InvalidDataException("Current ENG texture changed after review; production output is stale.");
        if (!audit.PristineBaseSha256.Equals(pristine.SourceResourceSha256, StringComparison.Ordinal))
            throw new InvalidDataException("Production audit used a different pristine JP XET than the reviewed reference.");
        if (audit.MaskPixels != proposal.ChangedPixels || audit.BlocksReplaced != proposal.AffectedBlocks)
            throw new InvalidDataException("Production audit mask/block counts do not match the approved mask proposal.");
        if (!Sha256(File.ReadAllBytes(outputArc)).Equals(audit.OutputArcSha256, StringComparison.Ordinal))
            throw new InvalidDataException("Production ARC hash does not match its audit.");
        if (!candidate.Sha256.Equals(proposal.CandidateRgbaSha256, StringComparison.Ordinal))
            throw new InvalidDataException("Production proposal no longer matches the frozen candidate.");

        return audit;
    }
}
