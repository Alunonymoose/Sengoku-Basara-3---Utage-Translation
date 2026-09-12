using BasaraFoundry.Domain;

namespace BasaraFoundry.RuntimeEvidenceSmokeTests;

internal static class Program
{
    private static int Main()
    {
        var outputArcHash = new string('a', 64);
        var otherArcHash = new string('b', 64);
        var screenshot = new byte[] { 0x89, 0x50, 0x4E, 0x47, 1, 2, 3, 4, 5 };
        var captured = new DateTimeOffset(2026, 9, 12, 2, 30, 0, TimeSpan.Zero);

        var evidence = RuntimeVerificationGuard.CreateEvidence(
            runtime: "RPCS3",
            outputArcSha256: outputArcHash,
            screenshotBytes: screenshot,
            screenshotPath: "runtime-evidence/a/screenshot.png",
            capturedAtUtc: captured,
            notes: "roulette_000_ID_HQ visible in game");

        Equal(RuntimeVerificationGuard.EvidenceSchema, evidence.Schema, "runtime evidence schema");
        Equal("sb3u-arc-aaaaaaaaaaaaaaaa", evidence.BuildId, "build ID derives from ARC hash");
        Equal(outputArcHash, evidence.OutputArcSha256, "evidence binds exact ARC hash");
        True(evidence.ScreenshotSha256.Length == 64, "screenshot gets content hash");

        RuntimeVerificationGuard.EnsureValidForBuild("RPCS3", outputArcHash, evidence);
        RuntimeVerificationGuard.VerifyScreenshotBytes(evidence, screenshot);
        Equal(
            AssetApprovalState.RuntimeVerified,
            RuntimeVerificationGuard.PromoteToRuntimeVerified(
                AssetApprovalState.Built,
                "RPCS3",
                outputArcHash,
                evidence),
            "Built state promotes with matching runtime evidence");

        Throws<InvalidOperationException>(
            () => RuntimeVerificationGuard.EnsureValidForBuild("RPCS3", otherArcHash, evidence),
            "evidence from another ARC hash is rejected");
        Throws<InvalidOperationException>(
            () => RuntimeVerificationGuard.EnsureValidForBuild("Real PS3", outputArcHash, evidence),
            "evidence from another runtime is rejected");
        Throws<InvalidOperationException>(
            () => RuntimeVerificationGuard.PromoteToRuntimeVerified(
                AssetApprovalState.Approved,
                "RPCS3",
                outputArcHash,
                evidence),
            "RuntimeVerified cannot skip Built state");

        var tamperedScreenshot = screenshot.ToArray();
        tamperedScreenshot[^1] ^= 0xFF;
        Throws<InvalidOperationException>(
            () => RuntimeVerificationGuard.VerifyScreenshotBytes(evidence, tamperedScreenshot),
            "tampered screenshot bytes are rejected");

        var forgedBuildId = evidence with { BuildId = "sb3u-arc-deadbeefdeadbeef" };
        Throws<InvalidOperationException>(
            () => RuntimeVerificationGuard.EnsureValidForBuild("RPCS3", outputArcHash, forgedBuildId),
            "forged build ID is rejected");

        // Shared-resource builds must be certified as a complete synchronized set.
        // Binding only the active ARC would reintroduce the cockpit1P/cockpit2P/
        // vs_cockpit failure class, so the runtime evidence has a separate contract.
        var buildSetHash = new string('c', 64);
        var otherBuildSetHash = new string('d', 64);
        var anchorArcHash = new string('e', 64);
        var otherAnchorArcHash = new string('f', 64);
        var setEvidence = OwnerSetRuntimeVerificationGuard.CreateEvidence(
            runtime: "RPCS3",
            buildSetSha256: buildSetHash,
            anchorOutputArcSha256: anchorArcHash,
            screenshotBytes: screenshot,
            screenshotPath: "runtime-evidence/set/screenshot.png",
            capturedAtUtc: captured,
            notes: "all synchronized cockpit owners installed together");

        Equal(OwnerSetRuntimeVerificationGuard.EvidenceSchema, setEvidence.Schema, "owner-set runtime evidence schema");
        Equal("sb3u-set-cccccccccccccccc", setEvidence.BuildId, "owner-set build ID derives from complete set hash");
        Equal(buildSetHash, setEvidence.BuildSetSha256, "owner-set evidence binds exact BuildSetSha256");
        Equal(anchorArcHash, setEvidence.AnchorOutputArcSha256, "owner-set evidence also binds reviewed anchor ARC");
        OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", buildSetHash, anchorArcHash, setEvidence);
        OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(setEvidence, screenshot);
        Equal(
            AssetApprovalState.RuntimeVerified,
            OwnerSetRuntimeVerificationGuard.PromoteToRuntimeVerified(
                AssetApprovalState.Built,
                "RPCS3",
                buildSetHash,
                anchorArcHash,
                setEvidence),
            "Built owner set promotes with matching set-bound evidence");

        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", otherBuildSetHash, anchorArcHash, setEvidence),
            "owner-set evidence from another complete build set is rejected");
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", buildSetHash, otherAnchorArcHash, setEvidence),
            "owner-set evidence from another anchor ARC is rejected");
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("Real PS3", buildSetHash, anchorArcHash, setEvidence),
            "owner-set evidence from another runtime is rejected");
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.PromoteToRuntimeVerified(
                AssetApprovalState.Approved,
                "RPCS3",
                buildSetHash,
                anchorArcHash,
                setEvidence),
            "owner-set RuntimeVerified cannot skip Built state");
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.VerifyScreenshotBytes(setEvidence, tamperedScreenshot),
            "owner-set evidence rejects tampered screenshot bytes");
        var forgedSetBuildId = setEvidence with { BuildId = "sb3u-set-deadbeefdeadbeef" };
        Throws<InvalidOperationException>(
            () => OwnerSetRuntimeVerificationGuard.EnsureValidForBuild("RPCS3", buildSetHash, anchorArcHash, forgedSetBuildId),
            "forged owner-set build ID is rejected");

        Console.WriteLine("Runtime evidence smoke tests passed.");
        return 0;
    }

    private static void Equal<T>(T expected, T actual, string label) where T : notnull
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new Exception($"FAIL {label}: expected {expected}, got {actual}");
        Console.WriteLine($"PASS {label}");
    }

    private static void True(bool value, string label)
    {
        if (!value)
            throw new Exception($"FAIL {label}");
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
