using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Layout;

namespace BasaraFoundry.Game.Utage.Index;

public sealed record IndexedUtageResource(
    string ArchivePath,
    int EntryIndex,
    string ResourceName,
    uint TypeHash,
    string TypeLabel,
    int RawSize,
    int StoredSize);

public sealed record IndexedUtageArchive(
    string RelativePath,
    ushort Version,
    IReadOnlyList<IndexedUtageResource> Resources);

public sealed record UtageIndexIssue(string RelativePath, string ErrorType, string Message);

public sealed record UtageIndexSnapshot(
    int Schema,
    string Root,
    DateTimeOffset CreatedAtUtc,
    IReadOnlyList<IndexedUtageArchive> Archives,
    IReadOnlyList<IndexedUtageResource> Resources,
    IReadOnlyList<UtageIndexIssue> Issues);

public sealed record LayoutTextureReference(
    string ArchivePath,
    string LayoutResource,
    string NodeName,
    string Role,
    string TextureResource);

public sealed record AssetSearchHit(IndexedUtageResource Resource, int Score, string Why);

public sealed class UtageAssetIndex
{
    public UtageAssetIndex(
        string root,
        IReadOnlyList<IndexedUtageArchive> archives,
        IReadOnlyList<UtageIndexIssue> issues)
    {
        Root = root;
        Archives = archives;
        Issues = issues;
        Resources = archives.SelectMany(archive => archive.Resources).ToArray();
    }

    public string Root { get; }
    public IReadOnlyList<IndexedUtageArchive> Archives { get; }
    public IReadOnlyList<IndexedUtageResource> Resources { get; }
    public IReadOnlyList<UtageIndexIssue> Issues { get; }

    public UtageIndexSnapshot ToSnapshot(DateTimeOffset createdAtUtc) => new(
        Schema: 1,
        Root: Root,
        CreatedAtUtc: createdAtUtc,
        Archives: Archives,
        Resources: Resources,
        Issues: Issues);

    public IReadOnlyList<AssetSearchHit> Search(string query, int limit = 50)
    {
        if (string.IsNullOrWhiteSpace(query) || limit <= 0)
            return [];

        var q = Normalize(query.Trim());
        var results = new List<AssetSearchHit>();
        foreach (var resource in Resources)
        {
            var normalizedName = Normalize(resource.ResourceName);
            var tail = normalizedName.Split('\\').Last();
            var archive = Normalize(resource.ArchivePath);
            var score = 0;
            var why = "";

            if (tail.Equals(q, StringComparison.OrdinalIgnoreCase))
            {
                score = 100;
                why = "exact resource name";
            }
            else if (tail.StartsWith(q, StringComparison.OrdinalIgnoreCase))
            {
                score = 85;
                why = "resource name prefix";
            }
            else if (normalizedName.Contains(q, StringComparison.OrdinalIgnoreCase))
            {
                score = 65;
                why = "resource path contains query";
            }
            else if (archive.Contains(q, StringComparison.OrdinalIgnoreCase))
            {
                score = 35;
                why = "archive path contains query";
            }

            if (score > 0)
                results.Add(new AssetSearchHit(resource, score, why));
        }

        return results
            .OrderByDescending(hit => hit.Score)
            .ThenBy(hit => hit.Resource.ArchivePath, StringComparer.OrdinalIgnoreCase)
            .ThenBy(hit => hit.Resource.ResourceName, StringComparer.OrdinalIgnoreCase)
            .Take(limit)
            .ToArray();
    }

    private static string Normalize(string value) => value.Replace('/', '\\').ToLowerInvariant();
}

/// <summary>
/// Read-only metadata indexer. A bad/special ARC becomes an issue row rather
/// than aborting the entire project scan. Parent game folders are resolved to
/// one concrete ENG/JPN route before scanning, while archive paths remain
/// relative to the selected root so subsequent preview containment is stable.
/// </summary>
public static class UtageAssetIndexer
{
    public static UtageAssetIndex IndexRoot(string root, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(root);
        var fullRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        if (!Directory.Exists(fullRoot))
            throw new DirectoryNotFoundException(fullRoot);
        return IndexTree(fullRoot, fullRoot, cancellationToken);
    }

    public static UtageAssetIndex IndexSelectedRoot(
        string selectedRoot,
        UtageContentRoute route,
        CancellationToken cancellationToken = default)
    {
        var resolved = UtageRouteResolver.Resolve(selectedRoot, route);
        return IndexTree(resolved.SelectedRoot, resolved.RouteRoot, cancellationToken);
    }

    private static UtageAssetIndex IndexTree(
        string identityRoot,
        string scanRoot,
        CancellationToken cancellationToken)
    {
        var archives = new List<IndexedUtageArchive>();
        var issues = new List<UtageIndexIssue>();
        foreach (var path in Directory.EnumerateFiles(scanRoot, "*.arc", SearchOption.AllDirectories)
                                      .OrderBy(path => path, StringComparer.OrdinalIgnoreCase))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var relative = Path.GetRelativePath(identityRoot, path);
            try
            {
                var arc = UtageArcReader.Read(path);
                var resources = arc.Entries.Select(entry => new IndexedUtageResource(
                    relative,
                    entry.Index,
                    entry.Name,
                    entry.TypeHash,
                    UtageTypeHashes.Label(entry.TypeHash),
                    entry.RawSize,
                    entry.CompressedSize)).ToArray();
                archives.Add(new IndexedUtageArchive(relative, arc.Version, resources));
            }
            catch (Exception ex) when (ex is InvalidDataException or NotSupportedException or IOException)
            {
                issues.Add(new UtageIndexIssue(relative, ex.GetType().Name, ex.Message));
            }
        }

        return new UtageAssetIndex(identityRoot, archives, issues);
    }

    public static IReadOnlyList<LayoutTextureReference> InspectLayoutReferences(string archivePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(archivePath);
        using var stream = File.Open(archivePath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var archive = UtageArcReader.Read(stream, archivePath);
        var references = new List<LayoutTextureReference>();

        foreach (var entry in archive.Entries.Where(entry => entry.TypeHash == UtageTypeHashes.Layout))
        {
            stream.Position = 0;
            var raw = UtageArcReader.ReadDecompressedPayload(stream, entry);
            if (!UtageLayoutReader.IsLayout(raw))
                continue;

            UtageLayoutInfo layout;
            try
            {
                layout = UtageLayoutReader.ReadInventory(raw, entry.Name);
            }
            catch (InvalidDataException)
            {
                continue;
            }

            foreach (var node in layout.Nodes.Where(node => !string.IsNullOrEmpty(node.Texture)))
            {
                references.Add(new LayoutTextureReference(
                    archivePath,
                    entry.Name,
                    node.Name,
                    node.Role,
                    node.Texture));
            }
        }

        return references;
    }
}
