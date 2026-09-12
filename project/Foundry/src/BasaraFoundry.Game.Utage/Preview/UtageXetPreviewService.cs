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
    string SourceResourceSha256,
    byte[] Rgba);

/// <summary>
/// Read-only selected-resource preview boundary. The caller supplies the exact
/// archive-relative path, entry index, and indexed resource name. Selection,
/// type validation, decompression, XET capability checks, hashing and decode
/// all come from one file handle via UtageSelectedTextureLoader.
/// </summary>
public static class UtageXetPreviewService
{
    public static UtageXetPreviewSnapshot Create(
        string root,
        string archiveRelativePath,
        int entryIndex,
        string expectedResourceName)
    {
        var selected = UtageSelectedTextureLoader.Load(
            root,
            archiveRelativePath,
            entryIndex,
            expectedResourceName);
        var info = selected.Decoded.Info;

        return new UtageXetPreviewSnapshot(
            Schema: 1,
            Root: selected.Root,
            ArchivePath: selected.ArchiveRelativePath,
            EntryIndex: selected.EntryIndex,
            ResourceName: selected.ResourceName,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            Width: selected.Decoded.Width,
            Height: selected.Decoded.Height,
            Version: info.Version,
            FormatCode: info.FormatCode,
            BlockFormat: info.BlockFormat ?? "unknown",
            MipCount: info.MipCount,
            Swizzle: info.Swizzle,
            CanEncode: UtageXetCodec.CanEncode(info),
            SourceResourceSha256: selected.SourceResourceSha256,
            Rgba: selected.Decoded.Rgba);
    }
}
