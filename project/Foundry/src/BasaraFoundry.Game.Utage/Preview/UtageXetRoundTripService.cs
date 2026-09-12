using System.Security.Cryptography;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.Game.Utage.Preview;

public sealed record UtageXetRoundTripSnapshot(
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
    string SourceResourceSha256,
    string CandidateRgbaSha256,
    string EncodedXetSha256,
    double MeanAbsoluteChannelError,
    int MaxChannelError,
    byte[] VerificationRgba);

/// <summary>
/// Non-production visual round-trip. It proves what a candidate would look
/// like after Foundry's certified BCn encode/decode path but emits no ARC and
/// grants no approval. Production build remains a separate gated operation.
/// </summary>
public static class UtageXetRoundTripService
{
    public static UtageXetRoundTripSnapshot Create(
        string root,
        string archiveRelativePath,
        int entryIndex,
        string expectedResourceName,
        ReadOnlySpan<byte> candidateRgba)
    {
        // Reuse the read-only preview gate first: this validates root escape,
        // member identity, texture type, XET metadata and decode capability.
        var preview = UtageXetPreviewService.Create(
            root,
            archiveRelativePath,
            entryIndex,
            expectedResourceName);

        var expectedRgbaLength = checked(preview.Width * preview.Height * 4);
        if (candidateRgba.Length != expectedRgbaLength)
        {
            throw new ArgumentException(
                $"Candidate contains {candidateRgba.Length} RGBA bytes; selected {preview.Width}x{preview.Height} texture requires {expectedRgbaLength}.",
                nameof(candidateRgba));
        }

        var archivePath = ResolveValidatedArchivePath(preview.Root, preview.ArchivePath);
        using var stream = File.Open(archivePath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var archive = UtageArcReader.Read(stream, archivePath);
        if ((uint)entryIndex >= (uint)archive.Entries.Count)
            throw new InvalidDataException("Selected ARC member changed after preview validation.");

        var entry = archive.Entries[entryIndex];
        if (!entry.Name.Equals(expectedResourceName, StringComparison.Ordinal) ||
            entry.TypeHash != UtageTypeHashes.Texture)
        {
            throw new InvalidDataException("Selected ARC member identity changed after preview validation.");
        }

        var originalXet = UtageArcReader.ReadDecompressedPayload(stream, entry);
        var sourceHash = Hex(SHA256.HashData(originalXet));
        var candidateBytes = candidateRgba.ToArray();
        var candidateHash = Hex(SHA256.HashData(candidateBytes));

        var build = UtageXetCodec.ReplaceSingleLevel(originalXet, candidateBytes);
        var encodedHash = Hex(SHA256.HashData(build.XetBytes));
        var verification = build.VerificationDecode.Rgba;
        if (verification.Length != candidateBytes.Length)
            throw new InvalidDataException("Verification decode returned an unexpected RGBA length.");

        long totalError = 0;
        var maxError = 0;
        for (var i = 0; i < candidateBytes.Length; i++)
        {
            var error = Math.Abs(candidateBytes[i] - verification[i]);
            totalError += error;
            if (error > maxError)
                maxError = error;
        }

        return new UtageXetRoundTripSnapshot(
            Schema: 1,
            Root: preview.Root,
            ArchivePath: preview.ArchivePath,
            EntryIndex: preview.EntryIndex,
            ResourceName: preview.ResourceName,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            Width: preview.Width,
            Height: preview.Height,
            Version: preview.Version,
            FormatCode: preview.FormatCode,
            BlockFormat: preview.BlockFormat,
            SourceResourceSha256: sourceHash,
            CandidateRgbaSha256: candidateHash,
            EncodedXetSha256: encodedHash,
            MeanAbsoluteChannelError: totalError / (double)candidateBytes.Length,
            MaxChannelError: maxError,
            VerificationRgba: verification);
    }

    private static string ResolveValidatedArchivePath(string root, string relative)
    {
        var fullRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var normalizedRelative = relative
            .Replace('\\', Path.DirectorySeparatorChar)
            .Replace('/', Path.DirectorySeparatorChar);
        var candidate = Path.GetFullPath(Path.Combine(fullRoot, normalizedRelative));
        var comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        var prefix = fullRoot + Path.DirectorySeparatorChar;
        if (!candidate.StartsWith(prefix, comparison))
            throw new InvalidDataException("Round-trip archive path escapes the configured source root.");
        return candidate;
    }

    private static string Hex(ReadOnlySpan<byte> value) => Convert.ToHexString(value).ToLowerInvariant();
}
