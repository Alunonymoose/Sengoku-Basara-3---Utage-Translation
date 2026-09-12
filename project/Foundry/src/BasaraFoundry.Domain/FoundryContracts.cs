namespace BasaraFoundry.Domain;

public enum CapabilityLevel
{
    Unsupported = 0,
    Experimental = 1,
    Verified = 2,
    RuntimeVerified = 3,
}

public enum AssetApprovalState
{
    Draft = 0,
    Review = 1,
    Approved = 2,
    Built = 3,
    RuntimeVerified = 4,
}

public sealed record FormatCapabilities(
    string Id,
    CapabilityLevel Read,
    CapabilityLevel Write,
    CapabilityLevel RoundTrip,
    CapabilityLevel Runtime);

public sealed record SourceFingerprint(
    string Path,
    string Sha256,
    long Length);

public sealed record AssetKey(
    string Game,
    string Archive,
    string Resource,
    string ResourceType);

public sealed record PixelRect(int Left, int Top, int Right, int Bottom)
{
    public int Width => Math.Max(0, Right - Left);
    public int Height => Math.Max(0, Bottom - Top);

    public bool Contains(int x, int y) =>
        x >= Left && x < Right && y >= Top && y < Bottom;
}

public sealed record EditMask(
    IReadOnlyList<PixelRect> Regions,
    bool RejectChangesOutsideRegions = true);

public sealed record DependencyEvidence(
    string Kind,
    AssetKey Target,
    string Evidence,
    double Confidence);

public sealed record RuntimeEvidence(
    string ScreenshotPath,
    string BuildId,
    DateTimeOffset CapturedAtUtc,
    string? Notes = null);

public sealed record AssetRecord(
    AssetKey Key,
    SourceFingerprint Source,
    AssetApprovalState Approval,
    FormatCapabilities Capabilities,
    IReadOnlyList<DependencyEvidence> Dependencies,
    IReadOnlyList<RuntimeEvidence> RuntimeEvidence);

public sealed record SourceRoots(
    string? UtageEnglish,
    string? UtageJapanese,
    string? SamuraiHeroes,
    string? SumeragiReference);

public sealed record ProjectRules(
    bool CanonicalSourcesReadOnly = true,
    bool ArtRequiresApproval = true,
    bool DependencyAuditRequired = true,
    bool RuntimeEvidenceRequiredForRuntimeVerified = true,
    bool RejectUnexpectedPixelsOutsideEditMask = true);

public sealed record FoundryProject(
    int Schema,
    string ProjectName,
    string Target,
    SourceRoots Sources,
    ProjectRules Rules);
