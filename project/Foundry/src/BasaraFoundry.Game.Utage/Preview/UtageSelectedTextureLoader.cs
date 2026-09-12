using System.Security.Cryptography;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.Game.Utage.Preview;

internal sealed record UtageSelectedTexture(
    string Root,
    string ArchiveRelativePath,
    int EntryIndex,
    string ResourceName,
    byte[] RawXet,
    string SourceResourceSha256,
    XetDecodedImage Decoded);

/// <summary>
/// Single-open selection boundary for one indexed Utage texture.
/// Every consumer gets identity validation, decompression, XET validation,
/// source hashing and decode from the same file handle so a preview cannot be
/// silently rebound to a different archive between validation and use.
/// </summary>
internal static class UtageSelectedTextureLoader
{
    public static UtageSelectedTexture Load(
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
            throw new InvalidDataException("Texture archive path must be relative to the configured source root.");

        var normalizedRelative = archiveRelativePath
            .Replace('\\', Path.DirectorySeparatorChar)
            .Replace('/', Path.DirectorySeparatorChar);
        var archivePath = Path.GetFullPath(Path.Combine(fullRoot, normalizedRelative));
        if (!IsWithinRoot(fullRoot, archivePath))
            throw new InvalidDataException("Texture archive path escapes the configured source root.");
        if (!File.Exists(archivePath))
            throw new FileNotFoundException("Indexed texture archive no longer exists.", archivePath);

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
        var sourceHash = Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();

        return new UtageSelectedTexture(
            Root: fullRoot,
            ArchiveRelativePath: archiveRelativePath,
            EntryIndex: entryIndex,
            ResourceName: entry.Name,
            RawXet: raw,
            SourceResourceSha256: sourceHash,
            Decoded: decoded);
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
