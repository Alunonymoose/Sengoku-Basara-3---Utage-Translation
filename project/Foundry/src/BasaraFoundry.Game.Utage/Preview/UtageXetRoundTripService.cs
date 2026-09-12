using System.Security.Cryptography;
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
/// The selected texture is loaded once so validation and encoding cannot bind
/// to different source bytes.
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
        var selected = UtageSelectedTextureLoader.Load(
            root,
            archiveRelativePath,
            entryIndex,
            expectedResourceName);
        var info = selected.Decoded.Info;

        var expectedRgbaLength = checked(selected.Decoded.Width * selected.Decoded.Height * 4);
        if (candidateRgba.Length != expectedRgbaLength)
        {
            throw new ArgumentException(
                $"Candidate contains {candidateRgba.Length} RGBA bytes; selected {selected.Decoded.Width}x{selected.Decoded.Height} texture requires {expectedRgbaLength}.",
                nameof(candidateRgba));
        }

        var candidateBytes = candidateRgba.ToArray();
        var candidateHash = Hex(SHA256.HashData(candidateBytes));
        var build = UtageXetCodec.ReplaceSingleLevel(selected.RawXet, candidateBytes);
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
            SourceResourceSha256: selected.SourceResourceSha256,
            CandidateRgbaSha256: candidateHash,
            EncodedXetSha256: encodedHash,
            MeanAbsoluteChannelError: totalError / (double)candidateBytes.Length,
            MaxChannelError: maxError,
            VerificationRgba: verification);
    }

    private static string Hex(ReadOnlySpan<byte> value) => Convert.ToHexString(value).ToLowerInvariant();
}
