using System.Security.Cryptography;

namespace BasaraFoundry.Domain;

public sealed record RuntimeVerificationEvidence(
    int Schema,
    string Runtime,
    string BuildId,
    string OutputArcSha256,
    string ScreenshotSha256,
    string ScreenshotPath,
    DateTimeOffset CapturedAtUtc,
    string? Notes = null);

/// <summary>
/// Guards the final Built -> RuntimeVerified transition. Runtime evidence is
/// meaningful only when it is bound to the exact production ARC hash/build ID
/// and to a content-hashed screenshot captured from the intended runtime.
/// </summary>
public static class RuntimeVerificationGuard
{
    public const int EvidenceSchema = 1;

    public static string BuildIdForArc(string outputArcSha256)
    {
        RequireSha256(outputArcSha256, nameof(outputArcSha256));
        return $"sb3u-arc-{outputArcSha256[..16].ToLowerInvariant()}";
    }

    public static RuntimeVerificationEvidence CreateEvidence(
        string runtime,
        string outputArcSha256,
        ReadOnlySpan<byte> screenshotBytes,
        string screenshotPath,
        DateTimeOffset capturedAtUtc,
        string? notes = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(runtime);
        ArgumentException.ThrowIfNullOrWhiteSpace(screenshotPath);
        RequireSha256(outputArcSha256, nameof(outputArcSha256));
        if (screenshotBytes.IsEmpty)
            throw new ArgumentException("Runtime screenshot bytes are empty.", nameof(screenshotBytes));
        if (capturedAtUtc == default)
            throw new ArgumentException("Runtime capture timestamp is required.", nameof(capturedAtUtc));

        var screenshotSha256 = Convert.ToHexString(SHA256.HashData(screenshotBytes)).ToLowerInvariant();
        return new RuntimeVerificationEvidence(
            Schema: EvidenceSchema,
            Runtime: runtime.Trim(),
            BuildId: BuildIdForArc(outputArcSha256),
            OutputArcSha256: outputArcSha256.ToLowerInvariant(),
            ScreenshotSha256: screenshotSha256,
            ScreenshotPath: screenshotPath,
            CapturedAtUtc: capturedAtUtc,
            Notes: notes);
    }

    public static void EnsureValidForBuild(
        string expectedRuntime,
        string expectedOutputArcSha256,
        RuntimeVerificationEvidence? evidence)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedRuntime);
        RequireSha256(expectedOutputArcSha256, nameof(expectedOutputArcSha256));

        if (evidence is null)
            throw new InvalidOperationException("Runtime Verified requires build-bound runtime evidence.");
        if (evidence.Schema != EvidenceSchema)
            throw new InvalidOperationException($"Unsupported runtime evidence schema {evidence.Schema}.");
        if (!string.Equals(evidence.Runtime, expectedRuntime, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(
                $"Runtime evidence is for '{evidence.Runtime}', expected '{expectedRuntime}'.");
        if (!string.Equals(evidence.OutputArcSha256, expectedOutputArcSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Runtime evidence belongs to a different output ARC hash.");

        var expectedBuildId = BuildIdForArc(expectedOutputArcSha256);
        if (!string.Equals(evidence.BuildId, expectedBuildId, StringComparison.Ordinal))
            throw new InvalidOperationException("Runtime evidence build ID does not match the exact output ARC hash.");
        RequireSha256(evidence.ScreenshotSha256, nameof(evidence.ScreenshotSha256));
        if (string.IsNullOrWhiteSpace(evidence.ScreenshotPath))
            throw new InvalidOperationException("Runtime evidence screenshot path is missing.");
        if (evidence.CapturedAtUtc == default)
            throw new InvalidOperationException("Runtime evidence capture timestamp is missing.");
    }

    public static AssetApprovalState PromoteToRuntimeVerified(
        AssetApprovalState current,
        string expectedRuntime,
        string expectedOutputArcSha256,
        RuntimeVerificationEvidence? evidence)
    {
        if (current != AssetApprovalState.Built)
        {
            throw new InvalidOperationException(
                $"Runtime verification requires Built state; current state is {current}.");
        }

        EnsureValidForBuild(expectedRuntime, expectedOutputArcSha256, evidence);
        return AssetApprovalState.RuntimeVerified;
    }

    public static void VerifyScreenshotBytes(
        RuntimeVerificationEvidence evidence,
        ReadOnlySpan<byte> screenshotBytes)
    {
        ArgumentNullException.ThrowIfNull(evidence);
        if (screenshotBytes.IsEmpty)
            throw new InvalidOperationException("Runtime evidence screenshot bytes are empty.");
        var actual = Convert.ToHexString(SHA256.HashData(screenshotBytes)).ToLowerInvariant();
        if (!string.Equals(actual, evidence.ScreenshotSha256, StringComparison.Ordinal))
            throw new InvalidOperationException("Runtime screenshot bytes no longer match their evidence hash.");
    }

    private static void RequireSha256(string value, string paramName)
    {
        if (value is null || value.Length != 64 || value.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Expected a 64-character SHA-256 hex string.", paramName);
    }
}
