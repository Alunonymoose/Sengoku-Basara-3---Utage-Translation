namespace BasaraFoundry.Game.Utage.Arc;

public sealed record SiblingArcWriteResult(
    string SourceArcPath,
    string OutputArcPath,
    string AuditJsonPath,
    string SourceArcSha256,
    string OutputArcSha256);

/// <summary>
/// Filesystem promotion for a certified single-entry graft transaction.
/// Canonical source directories are input-only: callers must provide an explicit
/// output path in a different directory. Foundry project builds satisfy this by
/// writing under the project build tree.
/// </summary>
public static class UtageSiblingArcStore
{
    public static SiblingArcWriteResult Write(
        string sourceArcPath,
        SingleEntryXetGraftResult transaction,
        string outputArcPath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceArcPath);
        ArgumentNullException.ThrowIfNull(transaction);
        ArgumentException.ThrowIfNullOrWhiteSpace(outputArcPath);

        var sourceFull = Path.GetFullPath(sourceArcPath);
        if (!File.Exists(sourceFull))
            throw new FileNotFoundException("Source ARC does not exist.", sourceFull);

        var outputFull = Path.GetFullPath(outputArcPath);
        if (PathsEqual(sourceFull, outputFull))
            throw new InvalidOperationException("Refusing to overwrite the source ARC path.");

        var sourceDir = Path.GetDirectoryName(sourceFull)
            ?? throw new InvalidOperationException("Source ARC has no parent directory.");
        var outputDir = Path.GetDirectoryName(outputFull)
            ?? throw new InvalidOperationException("Output ARC has no parent directory.");
        if (PathsEqual(sourceDir, outputDir))
        {
            throw new InvalidOperationException(
                "Refusing to write production output beside the canonical source ARC. Choose a Foundry project build directory.");
        }

        var auditFull = outputFull + ".audit.json";
        Directory.CreateDirectory(outputDir);

        var tmpArc = outputFull + ".tmp." + Guid.NewGuid().ToString("N");
        var tmpAudit = auditFull + ".tmp." + Guid.NewGuid().ToString("N");
        try
        {
            File.WriteAllBytes(tmpArc, transaction.SiblingArcBytes);
            File.WriteAllText(tmpAudit, transaction.AuditJson);
            File.Move(tmpArc, outputFull, overwrite: true);
            File.Move(tmpAudit, auditFull, overwrite: true);
        }
        finally
        {
            if (File.Exists(tmpArc)) File.Delete(tmpArc);
            if (File.Exists(tmpAudit)) File.Delete(tmpAudit);
        }

        return new SiblingArcWriteResult(
            sourceFull,
            outputFull,
            auditFull,
            transaction.Audit.SourceArcSha256,
            transaction.Audit.OutputArcSha256);
    }

    private static bool PathsEqual(string a, string b) =>
        string.Equals(
            Path.GetFullPath(a).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
            Path.GetFullPath(b).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);
}
