using System.Security.Cryptography;

namespace BasaraFoundry.Domain;

public sealed record OwnerSetRuntimeVerificationEvidence(
    int Schema,
    string Runtime,
    string BuildId,
    string BuildSetSha256,
    string AnchorOutputArcSha256,
    string ScreenshotSha256,
    string ScreenshotPath,
    DateTimeOffset CapturedAtUtc,
    string? Notes = null);

/// <summary>
/// Runtime-evidence contract for a dependency-synchronized build containing
/// multiple output ARCs. The evidence binds the screenshot to the deterministic
/// owner-set hash and also records the active/anchor ARC hash used for the
/// operator's visual review. A single ARC hash is never sufficient to certify
/// a shared-resource build.
/// </summary>
public static class OwnerSetRuntimeVerificationGuard
{
    public const int EvidenceSchema = 1;

    public static string BuildIdForSet(string buildSetSha256)
    {
        RequireSha256(buildSetSha256, nameof(buildSetSha256));
        return $"sb3u-set-{buildSetSha256[..16].ToLowerInvariant()}";
    }

    public static OwnerSetRuntimeVerificationEvidence CreateEvidence(
        string runtime,
        string buildSetSha256,
        string anchorOutputArcSha256,
        ReadOnlySpan<byte> screenshotBytes,
        string screenshotPath,
        DateTimeOffset capturedAtUtc,
        string? notes = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(runtime);
        ArgumentException.ThrowIfNullOrWhiteSpace(screenshotPath);
        RequireSha256(buildSetSha256, nameof(buildSetSha256));
        RequireSha256(anchorOutputArcSha256, nameof(anchorOutputArcSha256));
        if (screenshotBytes.IsEmpty)
            throw new ArgumentException("Runtime screenshot bytes are empty.", nameof(screenshotBytes));
        if (capturedAtUtc == default)
            throw new ArgumentException("Runtime capture timestamp is required.", nameof(capturedAtUtc));

        return new OwnerSetRuntimeVerificationEvidence(
            Schema: EvidenceSchema,
            Runtime: runtime.Trim(),
            BuildId: BuildIdForSet(buildSetSha256),
            BuildSetSha256: buildSetSha256.ToLowerInvariant(),
            AnchorOutputArcSha256: anchorOutputArcSha256.ToLowerInvariant(),
            ScreenshotSha256: Convert.ToHexString(SHA256.HashData(screenshotBytes)).ToLowerInvariant(),
            ScreenshotPath: screenshotPath,
            CapturedAtUtc: capturedAtUtc,
            Notes: notes);
    }

    public static void EnsureValidForBuild(
        string expectedRuntime,
        string expectedBuildSetSha256,
        string expectedAnchorOutputArcSha256,
        OwnerSetRuntimeVerificationEvidence? evidence)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedRuntime);
        RequireSha256(expectedBuildSetSha256, nameof(expectedBuildSetSha256));
        RequireSha256(expectedAnchorOutputArcSha256, nameof(expectedAnchorOutputArcSha256));
        if (evidence is null)
            throw new InvalidOperationException("Runtime Verified owner-set build requires build-set-bound runtime evidence.");
        if (evidence.Schema != EvidenceSchema)
            throw new InvalidOperationException($"Unsupported owner-set runtime evidence schema {evidence.Schema}.");
        if (!evidence.Runtime.Equals(expectedRuntime, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException($"Runtime evidence is for '{evidence.Runtime}', expected '{expectedRuntime}'.");
        if (!evidence.BuildSetSha256.Equals(expectedBuildSetSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Runtime evidence belongs to a different owner-set build hash.");
        if (!evidence.AnchorOutputArcSha256.Equals(expectedAnchorOutputArcSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Runtime evidence belongs to a different anchor output ARC hash.");
        if (!evidence.BuildId.Equals(BuildIdForSet(expectedBuildSetSha256), StringComparison.Ordinal))
            throw new InvalidOperationException("Runtime evidence build ID does not match the exact owner-set hash.");
        RequireSha256(evidence.ScreenshotSha256, nameof(evidence.ScreenshotSha256));
        if (string.IsNullOrWhiteSpace(evidence.ScreenshotPath))
            throw new InvalidOperationException("Runtime evidence screenshot path is missing.");
        if (evidence.CapturedAtUtc == default)
            throw new InvalidOperationException("Runtime evidence capture timestamp is missing.");
    }

    public static AssetApprovalState PromoteToRuntimeVerified(
        AssetApprovalState current,
        string expectedRuntime,
        string expectedBuildSetSha256,
        string expectedAnchorOutputArcSha256,
        OwnerSetRuntimeVerificationEvidence? evidence)
    {
        if (current != AssetApprovalState.Built)
            throw new InvalidOperationException($"Runtime verification requires Built state; current state is {current}.");
        EnsureValidForBuild(expectedRuntime, expectedBuildSetSha256, expectedAnchorOutputArcSha256, evidence);
        return AssetApprovalState.RuntimeVerified;
    }

    public static void VerifyScreenshotBytes(
        OwnerSetRuntimeVerificationEvidence evidence,
        ReadOnlySpan<byte> screenshotBytes)
    {
        ArgumentNullException.ThrowIfNull(evidence);
        if (screenshotBytes.IsEmpty)
            throw new InvalidOperationException("Runtime evidence screenshot bytes are empty.");
        var actual = Convert.ToHexString(SHA256.HashData(screenshotBytes)).ToLowerInvariant();
        if (!actual.Equals(evidence.ScreenshotSha256, StringComparison.Ordinal))
            throw new InvalidOperationException("Runtime screenshot bytes no longer match their owner-set evidence hash.");
    }

    private static void RequireSha256(string value, string paramName)
    {
        if (value is null || value.Length != 64 || value.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Expected a 64-character SHA-256 hex string.", paramName);
    }
}
