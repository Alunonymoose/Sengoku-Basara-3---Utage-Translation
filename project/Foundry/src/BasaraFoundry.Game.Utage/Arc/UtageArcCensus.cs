using System.Security.Cryptography;
using BasaraFoundry.Game.Utage.Resources;

namespace BasaraFoundry.Game.Utage.Arc;

public sealed record UtageArcCensusRow(
    int Index,
    string Name,
    uint TypeHash,
    int Flags,
    int CompressedSize,
    int RawSize,
    string StoredSha256,
    string RawSha256,
    UtageResourceDescriptor Resource);

public sealed record UtageArcCensusReport(
    string SourceName,
    ushort Version,
    long Length,
    string ArcSha256,
    IReadOnlyList<UtageArcCensusRow> Resources,
    IReadOnlyDictionary<string, int> KindCounts,
    IReadOnlyDictionary<uint, int> TypeHashCounts);

/// <summary>
/// Produces the canonical per-member inventory used by the future ARC Explorer.
/// Every resource is represented, including unknown/special entries.
/// </summary>
public static class UtageArcCensus
{
    public static UtageArcCensusReport Scan(string path)
    {
        using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        var archive = UtageArcReader.Read(stream, path);
        stream.Position = 0;
        var archiveHash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();

        var rows = new List<UtageArcCensusRow>(archive.Entries.Count);
        foreach (var entry in archive.Entries)
        {
            var stored = UtageArcReader.ReadStoredPayload(stream, entry);
            var raw = UtageArcReader.ReadDecompressedPayload(stream, entry);
            var descriptor = UtageResourceInspector.Describe(raw, entry.TypeHash);
            rows.Add(new UtageArcCensusRow(
                entry.Index,
                entry.Name,
                entry.TypeHash,
                entry.Flags,
                entry.CompressedSize,
                entry.RawSize,
                Hash(stored),
                Hash(raw),
                descriptor));
        }

        var kinds = rows
            .GroupBy(row => row.Resource.Kind, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.OrdinalIgnoreCase);
        var hashes = rows.GroupBy(row => row.TypeHash).ToDictionary(group => group.Key, group => group.Count());

        return new UtageArcCensusReport(path, archive.Version, archive.Length, archiveHash, rows, kinds, hashes);
    }

    private static string Hash(ReadOnlySpan<byte> bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}