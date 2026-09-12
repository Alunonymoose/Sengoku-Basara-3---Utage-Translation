using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.Game.Utage.Preview;

public sealed record UtageXetPreviewSnapshot(
    int Schema,
    string Root,
    string ArchivePath,
    int EntryIndex,
    string ResourceName,
    DateTimeOffset CreatedAtUtc,
    int Width,
    int Height,
    int Version,
    int FormatCode,
    string BlockFormat,
    int MipCount,
    int Swizzle,
    bool CanEncode,
    byte[] Rgba);

/// <summary>
/// Read-only selected-resource preview boundary. The caller supplies the exact
/// archive-relative path, entry index, and indexed resource name. All three are
/// revalidated against the current source before any decode occurs.
/// </summary>
public static class UtageXetPreviewService
{
    public static UtageXetPreviewSnapshot Create(
        string root,
        string archiveRelativePath,
        int entryIndex,
        string expectedResourceName)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(root);
        ArgumentException.ThrowIfNullOrWhiteSpace(archiveRelativePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedResourceName);
        if (entryIndex < 0)
            throw new ArgumentOutOfRangeException(nameof(entryIndex));

        var fullRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        if (!Directory.Exists(fullRoot))
            throw new DirectoryNotFoundException(fullRoot);
        if (Path.IsPathRooted(archiveRelativePath))
            throw new InvalidDataException("Preview archive path must be relative to the configured source root.");

        var normalizedRelative = archiveRelativePath
            .Replace('\\', Path.DirectorySeparatorChar)
            .Replace('/', Path.DirectorySeparatorChar);
        var archivePath = Path.GetFullPath(Path.Combine(fullRoot, normalizedRelative));
        if (!IsWithinRoot(fullRoot, archivePath))
            throw new InvalidDataException("Preview archive path escapes the configured source root.");
        if (!File.Exists(archivePath))
            throw new FileNotFoundException("Indexed preview archive no longer exists.", archivePath);

        using var stream = File.Open(archivePath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var archive = UtageArcReader.Read(stream, archivePath);
        if ((uint)entryIndex >= (uint)archive.Entries.Count)
            throw new InvalidDataException("Indexed ARC member no longer exists at the recorded entry index.");

        var entry = archive.Entries[entryIndex];
        if (entry.Index != entryIndex || !entry.Name.Equals(expectedResourceName, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Indexed ARC member identity changed; reindex before previewing or building this asset.");
        }
        if (entry.TypeHash != UtageTypeHashes.Texture)
            throw new NotSupportedException("Selected ARC member is not a certified Utage texture resource.");

        var raw = UtageArcReader.ReadDecompressedPayload(stream, entry);
        var decoded = UtageXetCodec.DecodeTopLevel(raw);
        var info = decoded.Info;

        return new UtageXetPreviewSnapshot(
            Schema: 1,
            Root: fullRoot,
            ArchivePath: archiveRelativePath,
            EntryIndex: entryIndex,
            ResourceName: entry.Name,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            Width: decoded.Width,
            Height: decoded.Height,
            Version: info.Version,
            FormatCode: info.FormatCode,
            BlockFormat: info.BlockFormat ?? "unknown",
            MipCount: info.MipCount,
            Swizzle: info.Swizzle,
            CanEncode: UtageXetCodec.CanEncode(info),
            Rgba: decoded.Rgba);
    }

    private static bool IsWithinRoot(string root, string candidate)
    {
        var comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (string.Equals(root, candidate, comparison))
            return false;
        var prefix = root + Path.DirectorySeparatorChar;
        return candidate.StartsWith(prefix, comparison);
    }
}
