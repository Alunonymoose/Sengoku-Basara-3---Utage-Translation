namespace BasaraFoundry.Domain;

public enum BuildOperation
{
    ReplaceResource = 0,
}

public enum RecipeFreshness
{
    Current = 0,
    MissingSource = 1,
    LengthChanged = 2,
    HashChanged = 3,
}

public sealed record BuildRecipe(
    string Id,
    AssetKey Target,
    SourceFingerprint BaseSource,
    BuildOperation Operation,
    string ApprovedInputPath,
    DateTimeOffset CreatedAtUtc);

public sealed record BuildProvenance(
    string BuildId,
    string FoundryVersion,
    string GitCommit,
    int ProjectSchema,
    DateTimeOffset CreatedAtUtc,
    IReadOnlyList<SourceFingerprint> Sources,
    IReadOnlyList<string> RecipeIds);
