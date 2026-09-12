namespace BasaraFoundry.Game.Utage.Arc;

public sealed record SiblingArcWriteResult(
    string SourceArcPath,
    string OutputArcPath,
    string AuditJsonPath,
    string SourceArcSha256,
    string OutputArcSha256);

/// <summary>
/// Filesystem promotion for a certified single-entry graft transaction.
/// Never overwrites the source ARC path.
/// </summary>
public static class UtageSiblingArcStore
{
    public static SiblingArcWriteResult Write(
        string sourceArcPath,
        SingleEntryXetGraftResult transaction,
        string? outputArcPath = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceArcPath);
        ArgumentNullException.ThrowIfNull(transaction);

        var sourceFull = Path.GetFullPath(sourceArcPath);
        if (!File.Exists(sourceFull))
            throw new FileNotFoundException("Source ARC does not exist.", sourceFull);

        var outputFull = Path.GetFullPath(outputArcPath ?? DefaultSiblingPath(sourceFull));
        if (PathsEqual(sourceFull, outputFull))
            throw new InvalidOperationException("Refusing to overwrite the source ARC path.");

        var auditFull = outputFull + ".audit.json";
        Directory.CreateDirectory(Path.GetDirectoryName(outputFull)!);

        // Write to temp then move for slightly safer promotion on the same volume.
        var tmpArc = outputFull + ".tmp";
        var tmpAudit = auditFull + ".tmp";
        File.WriteAllBytes(tmpArc, transaction.SiblingArcBytes);
        File.WriteAllText(tmpAudit, transaction.AuditJson);
        File.Move(tmpArc, outputFull, overwrite: true);
        File.Move(tmpAudit, auditFull, overwrite: true);

        return new SiblingArcWriteResult(
            sourceFull,
            outputFull,
            auditFull,
            transaction.Audit.SourceArcSha256,
            transaction.Audit.OutputArcSha256);
    }

    public static string DefaultSiblingPath(string sourceArcPath)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(sourceArcPath)) ?? Environment.CurrentDirectory;
        var stem = Path.GetFileNameWithoutExtension(sourceArcPath);
        var ext = Path.GetExtension(sourceArcPath);
        if (string.IsNullOrEmpty(ext))
            ext = ".arc";
        return Path.Combine(dir, stem + ".foundry" + ext);
    }

    private static bool PathsEqual(string a, string b) =>
        string.Equals(
            Path.GetFullPath(a).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
            Path.GetFullPath(b).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);
}
