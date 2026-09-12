using System.Security.Cryptography;
using System.Text.Json;
using BasaraFoundry.Domain;

namespace BasaraFoundry.Project;

public static class FoundryProjectStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };

    public static FoundryProject Load(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        var json = File.ReadAllText(path);
        var project = JsonSerializer.Deserialize<FoundryProject>(json, JsonOptions)
            ?? throw new InvalidDataException("Foundry project JSON did not contain a project object.");
        ValidateSafetyContract(project);
        return project;
    }

    public static void SaveAtomic(string path, FoundryProject project)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentNullException.ThrowIfNull(project);
        ValidateSafetyContract(project);

        var fullPath = Path.GetFullPath(path);
        var directory = Path.GetDirectoryName(fullPath)
            ?? throw new InvalidOperationException("Project path has no parent directory.");
        Directory.CreateDirectory(directory);

        var tempPath = fullPath + $".tmp-{Guid.NewGuid():N}";
        try
        {
            var json = JsonSerializer.Serialize(project, JsonOptions) + Environment.NewLine;
            using (var stream = new FileStream(
                tempPath,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 4096,
                options: FileOptions.WriteThrough))
            using (var writer = new StreamWriter(stream))
            {
                writer.Write(json);
                writer.Flush();
                stream.Flush(flushToDisk: true);
            }

            if (File.Exists(fullPath))
                File.Replace(tempPath, fullPath, destinationBackupFileName: null, ignoreMetadataErrors: true);
            else
                File.Move(tempPath, fullPath);
        }
        finally
        {
            if (File.Exists(tempPath))
                File.Delete(tempPath);
        }
    }

    public static void ValidateSafetyContract(FoundryProject project)
    {
        if (project.Schema != 1)
            throw new NotSupportedException($"Foundry project schema {project.Schema} is not supported by v0.1.");
        if (!string.Equals(project.Target, "SB3U_PS3", StringComparison.Ordinal))
            throw new NotSupportedException($"Foundry v0.1 production target must be SB3U_PS3, not '{project.Target}'.");

        var rules = project.Rules ?? throw new InvalidDataException("Project safety rules are missing.");
        if (!rules.CanonicalSourcesReadOnly ||
            !rules.ArtRequiresApproval ||
            !rules.DependencyAuditRequired ||
            !rules.RuntimeEvidenceRequiredForRuntimeVerified ||
            !rules.RejectUnexpectedPixelsOutsideEditMask)
        {
            throw new InvalidDataException(
                "Foundry v0.1 refuses a project that weakens a mandatory production safety rule.");
        }
    }
}

public static class SourceFingerprintService
{
    public static SourceFingerprint Compute(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        var fullPath = Path.GetFullPath(path);
        var info = new FileInfo(fullPath);
        if (!info.Exists)
            throw new FileNotFoundException("Cannot fingerprint a missing source file.", fullPath);

        using var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        var hash = SHA256.HashData(stream);
        return new SourceFingerprint(fullPath, Convert.ToHexString(hash).ToLowerInvariant(), info.Length);
    }

    public static RecipeFreshness Assess(BuildRecipe recipe)
    {
        ArgumentNullException.ThrowIfNull(recipe);
        var path = recipe.BaseSource.Path;
        if (!File.Exists(path))
            return RecipeFreshness.MissingSource;

        var info = new FileInfo(path);
        if (info.Length != recipe.BaseSource.Length)
            return RecipeFreshness.LengthChanged;

        var current = Compute(path);
        return string.Equals(current.Sha256, recipe.BaseSource.Sha256, StringComparison.OrdinalIgnoreCase)
            ? RecipeFreshness.Current
            : RecipeFreshness.HashChanged;
    }

    public static void RequireCurrent(BuildRecipe recipe)
    {
        var freshness = Assess(recipe);
        if (freshness != RecipeFreshness.Current)
        {
            throw new InvalidOperationException(
                $"Build recipe '{recipe.Id}' is stale: source state is {freshness}. Rebase before building.");
        }
    }
}
