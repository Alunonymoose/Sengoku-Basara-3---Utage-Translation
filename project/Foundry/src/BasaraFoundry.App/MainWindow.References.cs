using BasaraFoundry.Game.Utage.Index;
using BasaraFoundry.Game.Utage.Preview;
using Microsoft.UI.Xaml;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private UtageAssetIndex? _japaneseIndex;
    private UtageAssetIndex? _samuraiHeroesIndex;

    private async Task LoadReferencePreviewsAsync(IndexedUtageResource currentResource, long reviewGeneration)
    {
        ClearJapaneseProductionReference(reviewGeneration);

        await LoadOneReferenceAsync(
            label: "Original JP",
            root: _project?.Sources.UtageJapanese,
            route: UtageContentRoute.Japanese,
            cacheFileName: "utage-jpn.index.json",
            currentResource,
            reviewGeneration,
            setIndex: index => _japaneseIndex = index,
            getIndex: () => _japaneseIndex,
            setImage: bitmap => OriginalJpImage.Source = bitmap,
            setPlaceholder: visible => OriginalJpPlaceholder.Visibility = visible ? Visibility.Visible : Visibility.Collapsed,
            setMeta: text => OriginalJpMeta.Text = text,
            onResolved: (resource, preview) => SetJapaneseProductionReference(resource, preview, reviewGeneration));

        if (!IsReviewCurrent(reviewGeneration))
            return;

        await LoadOneReferenceAsync(
            label: "Samurai Heroes",
            root: _project?.Sources.SamuraiHeroes,
            route: UtageContentRoute.English,
            cacheFileName: "samurai-heroes.index.json",
            currentResource,
            reviewGeneration,
            setIndex: index => _samuraiHeroesIndex = index,
            getIndex: () => _samuraiHeroesIndex,
            setImage: bitmap => SamuraiHeroesImage.Source = bitmap,
            setPlaceholder: visible => SamuraiHeroesPlaceholder.Visibility = visible ? Visibility.Visible : Visibility.Collapsed,
            setMeta: text => SamuraiHeroesMeta.Text = text);
    }

    private async Task LoadOneReferenceAsync(
        string label,
        string? root,
        UtageContentRoute route,
        string cacheFileName,
        IndexedUtageResource currentResource,
        long reviewGeneration,
        Action<UtageAssetIndex> setIndex,
        Func<UtageAssetIndex?> getIndex,
        Action<Microsoft.UI.Xaml.Media.ImageSource?> setImage,
        Action<bool> setPlaceholder,
        Action<string> setMeta,
        Action<IndexedUtageResource, UtageXetPreviewSnapshot>? onResolved = null)
    {
        if (!IsReviewCurrent(reviewGeneration))
            return;

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
            RequireDistinctReferenceRoute(root, route, label);

            var index = getIndex();
            if (index is null || !PathsEqual(index.Root, root))
            {
                var snapshotPath = Path.Combine(
                    Path.GetDirectoryName(_projectPath)!,
                    "cache",
                    cacheFileName);
                await RunRoutedIndexWorkerAsync(root, snapshotPath, route);
                if (!IsReviewCurrent(reviewGeneration))
                    return;
                index = LoadIndexSnapshot(snapshotPath, root);
                setIndex(index);
            }

            var match = ReferenceMatcher.TryResolveUniqueStrong(currentResource, index);
            if (match is null)
            {
                if (!IsReviewCurrent(reviewGeneration))
                    return;
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
                "cache", "previews", "reference",
                $"{cacheFileName.Replace(".index.json", "", StringComparison.OrdinalIgnoreCase)}-{reviewGeneration}-{Guid.NewGuid():N}.json");
            await RunPreviewWorkerAsync(
                root,
                match.Resource.ArchivePath,
                match.Resource.EntryIndex,
                match.Resource.ResourceName,
                previewPath);
            if (!IsReviewCurrent(reviewGeneration))
                return;

            var preview = LoadPreviewSnapshot(previewPath, root, match.Resource);
            if (!IsReviewCurrent(reviewGeneration))
                return;

            setImage(PreviewBitmapFactory.FromRgba(preview.Width, preview.Height, preview.Rgba));
            setPlaceholder(false);
            setMeta($"{match.Confidence} · {match.Why} · {preview.Width}×{preview.Height} {preview.BlockFormat} · source {preview.SourceResourceSha256[..12]}…");
            onResolved?.Invoke(match.Resource, preview);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or System.Text.Json.JsonException or TimeoutException or ArgumentException)
        {
            if (!IsReviewCurrent(reviewGeneration))
                return;
            setImage(null);
            setPlaceholder(true);
            setMeta($"Reference blocked safely: {ex.Message}");
        }
    }
}
