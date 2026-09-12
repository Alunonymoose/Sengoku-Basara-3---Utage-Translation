using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using BasaraFoundry.Game.Utage.Index;
using BasaraFoundry.Game.Utage.Preview;
using Microsoft.UI.Xaml;
using Windows.Graphics.Imaging;
using Windows.Storage;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private sealed record CandidateReview(
        string RgbaPath,
        byte[] Rgba,
        string Sha256,
        string DisplayName,
        long Generation);

    private IndexedUtageResource? _activeResource;
    private int _activeWidth;
    private int _activeHeight;
    private string? _activeSourceResourceSha256;
    private CandidateReview? _candidateReview;
    private long _reviewGeneration;

    private long BeginAssetReview()
    {
        var generation = Interlocked.Increment(ref _reviewGeneration);
        _activeResource = null;
        _activeWidth = 0;
        _activeHeight = 0;
        _activeSourceResourceSha256 = null;
        _candidateReview = null;

        CurrentEngImage.Source = null;
        CurrentEngPlaceholder.Visibility = Visibility.Visible;
        CurrentEngMeta.Text = "Loading selected asset…";
        OriginalJpImage.Source = null;
        OriginalJpPlaceholder.Visibility = Visibility.Visible;
        OriginalJpMeta.Text = "Reference pending";
        SamuraiHeroesImage.Source = null;
        SamuraiHeroesPlaceholder.Visibility = Visibility.Visible;
        SamuraiHeroesMeta.Text = "Reference pending";
        DimensionsText.Text = "Dimensions: —";
        DependencyAuditText.Text = "Dependency audit: —";

        ResetWorkingAndEncodedPanes();
        LoadCandidateButton.IsEnabled = false;
        EncodeRoundTripButton.IsEnabled = false;
        SendForApprovalButton.IsEnabled = false;
        return generation;
    }

    private bool IsReviewCurrent(long generation) =>
        Volatile.Read(ref _reviewGeneration) == generation;

    private void SetActiveTexture(
        IndexedUtageResource resource,
        UtageXetPreviewSnapshot preview,
        long generation)
    {
        if (!IsReviewCurrent(generation))
            return;
        _activeResource = resource;
        _activeWidth = preview.Width;
        _activeHeight = preview.Height;
        _activeSourceResourceSha256 = preview.SourceResourceSha256;
        _candidateReview = null;
        ResetWorkingAndEncodedPanes();
        LoadCandidateButton.IsEnabled = preview.CanEncode;
        EncodeRoundTripButton.IsEnabled = false;
        ProtectedPixelsText.Text = "Protected pixels: UNVERIFIED — no edit mask";
        SendForApprovalButton.IsEnabled = false;
    }

    private void ResetWorkingAndEncodedPanes()
    {
        WorkingImage.Source = null;
        WorkingPlaceholder.Visibility = Visibility.Visible;
        WorkingMeta.Text = "No candidate loaded";
        EncodedResultImage.Source = null;
        EncodedResultPlaceholder.Visibility = Visibility.Visible;
        EncodedResultMeta.Text = "No round-trip preview";
        ProtectedPixelsText.Text = "Protected pixels: —";
    }

    private async void LoadCandidate_Click(object sender, RoutedEventArgs e)
    {
        var resource = _activeResource;
        var sourceHash = _activeSourceResourceSha256;
        var width = _activeWidth;
        var height = _activeHeight;
        var startingGeneration = Volatile.Read(ref _reviewGeneration);
        if (resource is null || string.IsNullOrWhiteSpace(sourceHash) || width <= 0 || height <= 0)
        {
            SearchStatusText.Text = "Preview a certified texture before loading a candidate PNG.";
            return;
        }

        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.PicturesLibrary,
        };
        picker.FileTypeFilter.Add(".png");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(this));
        var file = await picker.PickSingleFileAsync();
        if (file is null)
            return;
        if (!IsReviewCurrent(startingGeneration) || !SameResource(_activeResource, resource))
        {
            SearchStatusText.Text = "Candidate selection was discarded because the active asset changed while the file picker was open.";
            return;
        }

        try
        {
            using var stream = await file.OpenAsync(FileAccessMode.Read);
            var decoder = await BitmapDecoder.CreateAsync(stream);
            if ((int)decoder.PixelWidth != width || (int)decoder.PixelHeight != height)
            {
                throw new InvalidDataException(
                    $"Candidate is {decoder.PixelWidth}×{decoder.PixelHeight}; selected texture is {width}×{height}. Foundry will not resize texture atlases implicitly.");
            }

            var provider = await decoder.GetPixelDataAsync(
                BitmapPixelFormat.Rgba8,
                BitmapAlphaMode.Straight,
                new BitmapTransform(),
                ExifOrientationMode.IgnoreExifOrientation,
                ColorManagementMode.DoNotColorManage);
            var rgba = provider.DetachPixelData();
            var expected = checked(width * height * 4);
            if (rgba.Length != expected)
                throw new InvalidDataException($"PNG decoder returned {rgba.Length} bytes; expected {expected}.");
            if (!IsReviewCurrent(startingGeneration) || !SameResource(_activeResource, resource))
            {
                SearchStatusText.Text = "Decoded candidate was discarded because the active asset changed.";
                return;
            }

            var hash = Sha256(rgba);
            var cacheDir = Path.Combine(Path.GetDirectoryName(_projectPath)!, "cache", "candidates");
            Directory.CreateDirectory(cacheDir);
            var candidatePath = Path.Combine(cacheDir, $"candidate-{hash}.rgba");
            await PersistContentAddressedAsync(candidatePath, rgba, hash);

            if (!IsReviewCurrent(startingGeneration) || !SameResource(_activeResource, resource))
            {
                SearchStatusText.Text = "Candidate cache completed, but the active asset changed; the stale candidate was not attached to the review.";
                return;
            }

            var candidateGeneration = Interlocked.Increment(ref _reviewGeneration);
            _candidateReview = new CandidateReview(candidatePath, rgba, hash, file.Name, candidateGeneration);
            WorkingImage.Source = PreviewBitmapFactory.FromRgba(width, height, rgba);
            WorkingPlaceholder.Visibility = Visibility.Collapsed;
            WorkingMeta.Text = $"{file.Name} · RGBA {hash[..12]}… · {width}×{height}";
            EncodedResultImage.Source = null;
            EncodedResultPlaceholder.Visibility = Visibility.Visible;
            EncodedResultMeta.Text = "Round-trip required";
            EncodeRoundTripButton.IsEnabled = true;
            ProtectedPixelsText.Text = "Protected pixels: UNVERIFIED — no edit mask";
            SendForApprovalButton.IsEnabled = false;
            SearchStatusText.Text = "Candidate loaded into an immutable content-addressed review slot. No game file was modified.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or ArgumentException)
        {
            SearchStatusText.Text = $"Candidate load stopped safely: {ex.Message}";
        }
    }

    private async void EncodeRoundTrip_Click(object sender, RoutedEventArgs e)
    {
        var resource = _activeResource;
        var sourceHash = _activeSourceResourceSha256;
        var candidate = _candidateReview;
        var generation = Volatile.Read(ref _reviewGeneration);
        var root = _project?.Sources.UtageEnglish;
        if (resource is null || candidate is null || string.IsNullOrWhiteSpace(sourceHash) || string.IsNullOrWhiteSpace(root))
            return;
        if (candidate.Generation != generation)
        {
            SearchStatusText.Text = "Candidate review state is stale; reload the candidate before encoding.";
            return;
        }

        var operationId = Guid.NewGuid().ToString("N");
        var output = Path.Combine(
            Path.GetDirectoryName(_projectPath)!,
            "cache", "previews", "roundtrip",
            $"{candidate.Sha256[..16]}-{operationId}.json");

        try
        {
            EncodeRoundTripButton.IsEnabled = false;
            SearchStatusText.Text = "Encoding the frozen candidate to certified BC3 and decoding the exact result in the isolated worker…";
            await RunRoundTripWorkerAsync(
                Path.GetFullPath(root),
                resource,
                candidate.RgbaPath,
                output);

            if (!IsRoundTripOperationCurrent(generation, resource, candidate, sourceHash))
            {
                SearchStatusText.Text = "A completed round-trip was discarded because the active asset or candidate changed while it was running.";
                return;
            }

            var result = LoadRoundTripSnapshot(
                output,
                root,
                resource,
                sourceHash,
                candidate.Sha256,
                candidate.Rgba.Length);
            if (!IsRoundTripOperationCurrent(generation, resource, candidate, sourceHash))
            {
                SearchStatusText.Text = "Round-trip validation completed after the review changed; stale output was not displayed.";
                return;
            }

            EncodedResultImage.Source = PreviewBitmapFactory.FromRgba(result.Width, result.Height, result.VerificationRgba);
            EncodedResultPlaceholder.Visibility = Visibility.Collapsed;
            EncodedResultMeta.Text = $"Actual BC3 decode · MAE {result.MeanAbsoluteChannelError:F2} · max {result.MaxChannelError} · XET {result.EncodedXetSha256[..12]}…";
            ProtectedPixelsText.Text = "Protected pixels: UNVERIFIED — no edit mask";
            SendForApprovalButton.IsEnabled = false;
            SearchStatusText.Text = "Encoded Result is bound to this exact source hash and candidate hash. Approval/build remains blocked until protected pixels are verified.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or JsonException or TimeoutException or ArgumentException)
        {
            if (IsReviewCurrent(generation))
            {
                EncodedResultImage.Source = null;
                EncodedResultPlaceholder.Visibility = Visibility.Visible;
                EncodedResultMeta.Text = "Round-trip blocked";
                SearchStatusText.Text = $"Round-trip stopped safely: {ex.Message}";
            }
        }
        finally
        {
            if (IsReviewCurrent(generation) && _candidateReview?.Sha256 == candidate.Sha256)
                EncodeRoundTripButton.IsEnabled = true;
        }
    }

    private bool IsRoundTripOperationCurrent(
        long generation,
        IndexedUtageResource resource,
        CandidateReview candidate,
        string sourceHash) =>
        IsReviewCurrent(generation) &&
        SameResource(_activeResource, resource) &&
        string.Equals(_activeSourceResourceSha256, sourceHash, StringComparison.Ordinal) &&
        _candidateReview is not null &&
        _candidateReview.Generation == generation &&
        string.Equals(_candidateReview.Sha256, candidate.Sha256, StringComparison.Ordinal);

    private static bool SameResource(IndexedUtageResource? left, IndexedUtageResource? right) =>
        left is not null && right is not null &&
        left.EntryIndex == right.EntryIndex &&
        left.ArchivePath.Equals(right.ArchivePath, StringComparison.OrdinalIgnoreCase) &&
        left.ResourceName.Equals(right.ResourceName, StringComparison.Ordinal);

    private static async Task PersistContentAddressedAsync(string path, byte[] bytes, string expectedHash)
    {
        if (File.Exists(path))
        {
            var existing = await File.ReadAllBytesAsync(path);
            if (!Sha256(existing).Equals(expectedHash, StringComparison.Ordinal))
                throw new InvalidDataException("Content-addressed candidate cache entry is corrupted and will not be reused.");
            return;
        }

        var temp = path + ".tmp." + Guid.NewGuid().ToString("N");
        try
        {
            await File.WriteAllBytesAsync(temp, bytes);
            if (!Sha256(await File.ReadAllBytesAsync(temp)).Equals(expectedHash, StringComparison.Ordinal))
                throw new InvalidDataException("Candidate cache write failed verification.");
            try
            {
                File.Move(temp, path, overwrite: false);
            }
            catch (IOException) when (File.Exists(path))
            {
                var existing = await File.ReadAllBytesAsync(path);
                if (!Sha256(existing).Equals(expectedHash, StringComparison.Ordinal))
                    throw new InvalidDataException("Concurrent candidate cache creation produced unexpected content.");
            }
        }
        finally
        {
            if (File.Exists(temp))
                File.Delete(temp);
        }
    }

    private static async Task RunRoundTripWorkerAsync(
        string root,
        IndexedUtageResource resource,
        string candidateRgbaPath,
        string output)
    {
        var workerPath = Path.Combine(AppContext.BaseDirectory, "worker", "BasaraFoundry.Worker.exe");
        if (!File.Exists(workerPath))
            throw new FileNotFoundException("The isolated Foundry round-trip worker is missing from this build.", workerPath);

        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
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
            "roundtrip-xet", "--root", root, "--archive", resource.ArchivePath,
            "--entry", resource.EntryIndex.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--name", resource.ResourceName, "--rgba", candidateRgbaPath, "--output", output,
        })
        {
            start.ArgumentList.Add(argument);
        }

        using var process = Process.Start(start)
            ?? throw new IOException("Could not start the isolated Foundry round-trip worker.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(45));
        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Round-trip worker exceeded the 45-second safety limit and was terminated.");
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        if (process.ExitCode != 0)
        {
            var detail = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
            throw new InvalidDataException($"Round-trip worker failed with exit code {process.ExitCode}: {detail.Trim()}");
        }
        if (!File.Exists(output))
            throw new InvalidDataException("Round-trip worker reported success but did not produce a snapshot.");
    }

    private static UtageXetRoundTripSnapshot LoadRoundTripSnapshot(
        string path,
        string expectedRoot,
        IndexedUtageResource resource,
        string expectedSourceHash,
        string expectedCandidateHash,
        int expectedRgbaLength)
    {
        using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        var result = JsonSerializer.Deserialize<UtageXetRoundTripSnapshot>(stream, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        }) ?? throw new InvalidDataException("Round-trip snapshot was empty.");

        if (result.Schema != 1 ||
            !PathsEqual(result.Root, expectedRoot) ||
            !result.ArchivePath.Equals(resource.ArchivePath, StringComparison.OrdinalIgnoreCase) ||
            result.EntryIndex != resource.EntryIndex ||
            !result.ResourceName.Equals(resource.ResourceName, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Round-trip snapshot identity does not match the frozen review asset.");
        }
        if (!result.SourceResourceSha256.Equals(expectedSourceHash, StringComparison.Ordinal))
            throw new InvalidDataException("Source texture changed after the Current ENG preview; re-preview before reviewing this candidate.");
        if (!result.CandidateRgbaSha256.Equals(expectedCandidateHash, StringComparison.Ordinal))
            throw new InvalidDataException("Round-trip snapshot does not belong to the frozen candidate RGBA.");
        if (result.VerificationRgba.Length != expectedRgbaLength ||
            result.VerificationRgba.Length != checked(result.Width * result.Height * 4))
        {
            throw new InvalidDataException("Round-trip snapshot RGBA length is invalid.");
        }
        if (result.EncodedXetSha256.Length != 64)
            throw new InvalidDataException("Round-trip snapshot encoded XET hash is invalid.");
        return result;
    }

    private static string Sha256(ReadOnlySpan<byte> bytes) =>
        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}
