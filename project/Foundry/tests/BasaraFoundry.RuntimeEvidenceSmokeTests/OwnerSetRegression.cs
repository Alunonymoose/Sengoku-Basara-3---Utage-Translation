using System.Runtime.CompilerServices;
using BasaraFoundry.Domain;

namespace BasaraFoundry.RuntimeEvidenceSmokeTests;

internal static class OwnerSetRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        var buildSetHash = new string('c', 64);
        var otherSetHash = new string('d', 64);
        var anchorArcHash = new string('e', 64);
        var otherArcHash = new string('f', 64);
        var screenshot = new byte[] { 0x89, 0x50, 0x4E, 0x47, 9, 8, 7, 6 };
        var captured = new DateTimeOffset(2026, 9, 12, 20, 30, 0, TimeSpan.Zero);

        var evidence = OwnerSetRuntimeVerificationGuard.CreateEvidence(
            runtime: "RPCS3",
            buildSetSha256: buildSetHash,
            anchorOutputArcSha256: anchorArcHash,
            screenshotBytes: screenshot,
            screenshotPath: "runtime-evidence/set/screenshot.png",
            capturedAtUtc: captured,
            notes: "cockpit_020 shared owner set visible in game");

        Equal("sb3u-set-cccccccccccccccc", evidence.BuildId, "owner-set build ID derives from set hash");
        Equal(buildSetHash, evidence.BuildSetSha256, "owner-set evidence binds complete set hash");
        Equal(anchorArcHash, evidence.AnchorOutputArcSha256, "owner-set evidence binds reviewed anchor ARC hash");
        OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", buildSetHash, anchorArcHash, evidence);
        OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(evidence, screenshot);
        Equal(
            AssetApprovalState.RuntimeVerified,
            OwnerSetRuntimeVerificationGuard.PromoteToRuntimeVerified(
                AssetApprovalState.Built,
                "RPCS3",
                buildSetHash,
                anchorArcHash,
                evidence),
            "owner-set Built state promotes only with matching group evidence");

        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", otherSetHash, anchorArcHash, evidence),
            "owner-set evidence from another group hash is rejected");
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", buildSetHash, otherArcHash, evidence),
            "owner-set evidence from another anchor ARC is rejected");
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("Real PS3", buildSetHash, anchorArcHash, evidence),
            "owner-set evidence from another runtime is rejected");

        var tampered = screenshot.ToArray();
        tampered[^1] ^= 0xFF;
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(evidence, tampered),
            "owner-set tampered screenshot is rejected");

        Console.WriteLine("PASS owner-set runtime evidence regression");
    }

    private static void Equal<T>(T expected, T actual, string label) where T : notnull
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new Exception($"FAIL {label}: expected {expected}, got {actual}");
        Console.WriteLine($"PASS {label}");
    }

    private static void Throws<TException>(Action action, string label) where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            Console.WriteLine($"PASS {label}");
            return;
        }
        throw new Exception($"FAIL {label}: expected {typeof(TException).Name}");
    }
}
