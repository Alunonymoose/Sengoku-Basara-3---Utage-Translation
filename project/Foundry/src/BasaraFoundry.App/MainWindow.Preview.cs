using System.Diagnostics;
using System.Text.Json;
using BasaraFoundry.Game.Utage.Preview;
using Microsoft.UI.Xaml;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private async void PreviewAsset_Click(object sender, RoutedEventArgs e)
    {
        if (AssetResultsList.SelectedItem is not AssetResultItem selected)
            return;

        var root = _project?.Sources.UtageEnglish;
        if (string.IsNullOrWhiteSpace(root))
        {
            SearchStatusText.Text = "Current Utage English source is not configured.";
            return;
        }

        var resource = selected.Hit.Resource;
        var reviewGeneration = BeginAssetReview();
        var output = Path.Combine(
            Path.GetDirectoryName(_projectPath)!,
            "cache", "previews", "asset",
            $"current-eng-{reviewGeneration}-{Guid.NewGuid():N}.json");

        try
        {
            OpenAssetButton.IsEnabled = false;
            SearchStatusText.Text = $"Decoding {resource.ResourceName} in isolated worker…";
            await RunPreviewWorkerAsync(
                Path.GetFullPath(root),
                resource.ArchivePath,
                resource.EntryIndex,
                resource.ResourceName,
                output);

            if (!IsReviewCurrent(reviewGeneration))
                return;

            var preview = LoadPreviewSnapshot(output, root, resource);
            if (!IsReviewCurrent(reviewGeneration))
                return;

            CurrentEngImage.Source = PreviewBitmapFactory.FromRgba(preview.Width, preview.Height, preview.Rgba);
            CurrentEngPlaceholder.Visibility = Visibility.Collapsed;
            CurrentEngMeta.Text = $"XET v0x{preview.Version:X2} · {preview.BlockFormat}/0x{preview.FormatCode:X2} · {preview.MipCount} mip · " +
                                  (preview.CanEncode ? "certified writable" : "preview only") +
                                  $" · source {preview.SourceResourceSha256[..12]}…";
            DimensionsText.Text = $"Dimensions: {preview.Width}×{preview.Height}";
            DependencyAuditText.Text = "Dependency audit: indexed · controller geometry pending";
            SetActiveTexture(resource, preview, reviewGeneration);
            SearchStatusText.Text = $"Loaded Current ENG preview from {resource.ArchivePath} [{resource.EntryIndex}]. Resolving reference evidence…";

            await LoadReferencePreviewsAsync(resource, reviewGeneration);
            if (IsReviewCurrent(reviewGeneration))
                SearchStatusText.Text = $"Loaded {resource.ResourceName}. Current source remains read only; reference matches are evidence-only.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or JsonException or TimeoutException or ArgumentException)
        {
            if (IsReviewCurrent(reviewGeneration))
            {
                CurrentEngImage.Source = null;
                CurrentEngPlaceholder.Visibility = Visibility.Visible;
                CurrentEngMeta.Text = "Preview blocked";
                SearchStatusText.Text = $"Preview stopped safely: {ex.Message}";
            }
        }
        finally
        {
            OpenAssetButton.IsEnabled = AssetResultsList.SelectedItem is AssetResultItem;
        }
    }

    private static UtageXetPreviewSnapshot LoadPreviewSnapshot(
        string path,
        string expectedRoot,
        BasaraFoundry.Game.Utage.Index.IndexedUtageResource expectedResource)
    {
        using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        var preview = JsonSerializer.Deserialize<UtageXetPreviewSnapshot>(stream, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        }) ?? throw new InvalidDataException("Worker preview snapshot was empty.");

        if (preview.Schema != 1)
            throw new NotSupportedException($"Unsupported preview snapshot schema {preview.Schema}.");
        if (!PathsEqual(preview.Root, expectedRoot))
            throw new InvalidDataException("Preview snapshot belongs to a different source root.");
        if (!preview.ArchivePath.Equals(expectedResource.ArchivePath, StringComparison.OrdinalIgnoreCase) ||
            preview.EntryIndex != expectedResource.EntryIndex ||
            !preview.ResourceName.Equals(expectedResource.ResourceName, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Preview snapshot does not match the selected indexed asset.");
        }
        if (preview.Width <= 0 || preview.Height <= 0 ||
            preview.Rgba.Length != checked(preview.Width * preview.Height * 4))
        {
            throw new InvalidDataException("Preview snapshot has invalid image dimensions or RGBA length.");
        }
        if (preview.SourceResourceSha256.Length != 64)
            throw new InvalidDataException("Preview snapshot source fingerprint is missing or invalid.");

        return preview;
    }

    private static async Task RunPreviewWorkerAsync(
        string root,
        string archiveRelativePath,
        int entryIndex,
        string resourceName,
        string output)
    {
        var workerPath = Path.Combine(AppContext.BaseDirectory, "worker", "BasaraFoundry.Worker.exe");
        if (!File.Exists(workerPath))
            throw new FileNotFoundException("The isolated Foundry preview worker is missing from this build.", workerPath);

        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var start = new ProcessStartInfo
        {
            FileName = workerPath,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        start.ArgumentList.Add("preview-xet");
        start.ArgumentList.Add("--root");
        start.ArgumentList.Add(root);
        start.ArgumentList.Add("--archive");
        start.ArgumentList.Add(archiveRelativePath);
        start.ArgumentList.Add("--entry");
        start.ArgumentList.Add(entryIndex.ToString(System.Globalization.CultureInfo.InvariantCulture));
        start.ArgumentList.Add("--name");
        start.ArgumentList.Add(resourceName);
        start.ArgumentList.Add("--output");
        start.ArgumentList.Add(output);

        using var process = Process.Start(start)
            ?? throw new IOException("Could not start the isolated Foundry preview worker.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));

        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Preview worker exceeded the 30-second safety limit and was terminated.");
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        if (process.ExitCode != 0)
        {
            var detail = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
            throw new InvalidDataException($"Preview worker failed with exit code {process.ExitCode}: {detail.Trim()}");
        }
        if (!File.Exists(output))
            throw new InvalidDataException("Preview worker reported success but did not produce a snapshot.");
    }
}
