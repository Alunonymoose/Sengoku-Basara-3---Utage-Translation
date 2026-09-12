using BasaraFoundry.Game.Utage.Index;
using Microsoft.UI.Xaml;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private UtageAssetIndex? _japaneseIndex;
    private UtageAssetIndex? _samuraiHeroesIndex;

    private async Task LoadReferencePreviewsAsync(IndexedUtageResource currentResource)
    {
        await LoadOneReferenceAsync(
            label: "Original JP",
            root: _project?.Sources.UtageJapanese,
            cacheFileName: "utage-jpn.index.json",
            currentResource,
            setIndex: index => _japaneseIndex = index,
            getIndex: () => _japaneseIndex,
            setImage: bitmap => OriginalJpImage.Source = bitmap,
            setPlaceholder: visible => OriginalJpPlaceholder.Visibility = visible ? Visibility.Visible : Visibility.Collapsed,
            setMeta: text => OriginalJpMeta.Text = text);

        await LoadOneReferenceAsync(
            label: "Samurai Heroes",
            root: _project?.Sources.SamuraiHeroes,
            cacheFileName: "samurai-heroes.index.json",
            currentResource,
            setIndex: index => _samuraiHeroesIndex = index,
            getIndex: () => _samuraiHeroesIndex,
            setImage: bitmap => SamuraiHeroesImage.Source = bitmap,
            setPlaceholder: visible => SamuraiHeroesPlaceholder.Visibility = visible ? Visibility.Visible : Visibility.Collapsed,
            setMeta: text => SamuraiHeroesMeta.Text = text);
    }

    private async Task LoadOneReferenceAsync(
        string label,
        string? root,
        string cacheFileName,
        IndexedUtageResource currentResource,
        Action<UtageAssetIndex> setIndex,
        Func<UtageAssetIndex?> getIndex,
        Action<Microsoft.UI.Xaml.Media.ImageSource?> setImage,
        Action<bool> setPlaceholder,
        Action<string> setMeta)
    {
        if (string.IsNullOrWhiteSpace(root))
        {
            setImage(null);
            setPlaceholder(true);
            setMeta($"{label} source is not configured");
            return;
        }

        try
        {
            root = Path.GetFullPath(root);
            var index = getIndex();
            if (index is null || !PathsEqual(index.Root, root))
            {
                var snapshotPath = Path.Combine(
                    Path.GetDirectoryName(_projectPath)!,
                    "cache",
                    cacheFileName);
                await RunIndexWorkerAsync(root, snapshotPath);
                index = LoadIndexSnapshot(snapshotPath, root);
                setIndex(index);
            }

            var match = ReferenceMatcher.TryResolveUniqueStrong(currentResource, index);
            if (match is null)
            {
                setImage(null);
                setPlaceholder(true);
                var candidates = ReferenceMatcher.FindCandidates(currentResource, index, 3);
                setMeta(candidates.Count == 0
                    ? "No counterpart evidence found"
                    : $"{candidates.Count} candidate(s); no unique strong match — operator review required");
                return;
            }

            var previewPath = Path.Combine(
                Path.GetDirectoryName(_projectPath)!,
                "cache",
                "previews",
                cacheFileName.Replace(".index.json", ".preview.json", StringComparison.OrdinalIgnoreCase));
            await RunPreviewWorkerAsync(
                root,
                match.Resource.ArchivePath,
                match.Resource.EntryIndex,
                match.Resource.ResourceName,
                previewPath);
            var preview = LoadPreviewSnapshot(previewPath, root, match.Resource);
            setImage(PreviewBitmapFactory.FromRgba(preview.Width, preview.Height, preview.Rgba));
            setPlaceholder(false);
            setMeta($"{match.Confidence} · {match.Why} · {preview.Width}×{preview.Height} {preview.BlockFormat}");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or System.Text.Json.JsonException or TimeoutException or ArgumentException)
        {
            setImage(null);
            setPlaceholder(true);
            setMeta($"Reference blocked safely: {ex.Message}");
        }
    }
}
