using BasaraFoundry.Game.Utage.Preview;
using Microsoft.UI.Xaml;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private async void GenerateReplacement_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var active = _activeResource;
            var donor = _samuraiHeroesProductionResource;
            var donorPreview = _samuraiHeroesProductionPreview;
            var pristine = _productionJapanesePreview;
            if (active is null || pristine is null)
                throw new InvalidOperationException("Preview a texture with a certified pristine Japanese counterpart first.");

            GenerateReplacementButton.IsEnabled = false;

            if (donor is not null && donorPreview is { CanEncode: true } &&
                donorPreview.Width == _activeWidth && donorPreview.Height == _activeHeight)
            {
                if (donorPreview.Rgba.Length != pristine.Rgba.Length)
                    throw new InvalidDataException("Official donor and pristine Japanese atlas sizes differ.");

                SearchStatusText.Text = "Creating one-click replacement from Capcom's official Samurai Heroes artwork…";
                await AttachGeneratedCandidateAsync(
                    donorPreview.Rgba,
                    $"Official Samurai Heroes · {donor.ResourceName}",
                    "OFFICIAL DONOR");
                SearchStatusText.Text =
                    "Replacement ready from official Samurai Heroes artwork. " +
                    "The preview is now the working candidate; pristine Japanese pixels remain the production authority outside approved changes.";
                return;
            }

            await GenerateAiRepairCandidateAsync();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or ArgumentException or InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            SearchStatusText.Text = $"One-click replacement stopped safely: {ex.Message}";
        }
        finally
        {
            RefreshGenerateReplacementAvailability();
        }
    }

    private async Task AttachGeneratedCandidateAsync(byte[] rgba, string displayName, string origin)
    {
        var resource = _activeResource ?? throw new InvalidOperationException("No active texture is selected.");
        var expectedLength = checked(_activeWidth * _activeHeight * 4);
        if (rgba.Length != expectedLength)
            throw new InvalidDataException($"Generated candidate returned {rgba.Length} RGBA bytes; expected {expectedLength}.");

        var hash = Sha256(rgba);
        var cacheDir = Path.Combine(Path.GetDirectoryName(_projectPath)!, "cache", "candidates");
        Directory.CreateDirectory(cacheDir);
        var candidatePath = Path.Combine(cacheDir, $"candidate-{hash}.rgba");
        await PersistContentAddressedAsync(candidatePath, rgba, hash);

        if (!SameResource(_activeResource, resource))
            throw new InvalidOperationException("The active texture changed while the replacement candidate was being created.");

        var generation = Interlocked.Increment(ref _reviewGeneration);
        _candidateReview = new CandidateReview(candidatePath, rgba, hash, displayName, generation);
        WorkingImage.Source = PreviewBitmapFactory.FromRgba(_activeWidth, _activeHeight, rgba);
        WorkingPlaceholder.Visibility = Visibility.Collapsed;
        WorkingMeta.Text = $"{origin} · {displayName} · RGBA {hash[..12]}… · {_activeWidth}×{_activeHeight}";
        EncodedResultImage.Source = null;
        EncodedResultPlaceholder.Visibility = Visibility.Visible;
        EncodedResultMeta.Text = "Round-trip required";
        EncodeRoundTripButton.IsEnabled = true;
        ProtectedPixelsText.Text = "Comparing replacement against pristine Japanese artwork…";
        SendForApprovalButton.IsEnabled = false;

        await RefreshMaskProposalSafeAsync();
    }
}
