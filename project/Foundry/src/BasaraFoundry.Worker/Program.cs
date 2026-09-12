using System.Text.Json;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Index;
using BasaraFoundry.Game.Utage.Preview;

static string? Option(string[] args, string name)
{
    for (var i = 0; i < args.Length - 1; i++)
    {
        if (args[i].Equals(name, StringComparison.OrdinalIgnoreCase))
            return args[i + 1];
    }
    return null;
}

static int Usage()
{
    Console.Error.WriteLine("Usage:");
    Console.Error.WriteLine("  BasaraFoundry.Worker index --root <source-root> [--route eng|jpn|direct] --output <snapshot.json>");
    Console.Error.WriteLine("  BasaraFoundry.Worker preview-xet --root <source-root> --archive <relative.arc> --entry <index> --name <resource> --output <preview.json>");
    Console.Error.WriteLine("  BasaraFoundry.Worker roundtrip-xet --root <source-root> --archive <relative.arc> --entry <index> --name <resource> --rgba <candidate.rgba> --output <preview.json>");
    Console.Error.WriteLine("  BasaraFoundry.Worker graft-xet --root <source-root> --archive <relative.arc> --entry <index> --name <resource> --rgba <candidate.rgba> --mask <mask.bin> --output-arc <sibling.arc> --audit <audit.json>");
    return 64;
}

static async Task WriteAtomicJsonAsync<T>(string output, T value)
{
    output = Path.GetFullPath(output);
    var directory = Path.GetDirectoryName(output);
    if (string.IsNullOrWhiteSpace(directory))
        throw new InvalidOperationException("Worker output must have a parent directory.");
    Directory.CreateDirectory(directory);

    var temp = output + ".tmp." + Guid.NewGuid().ToString("N");
    try
    {
        await using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            await JsonSerializer.SerializeAsync(stream, value, new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            });
            await stream.FlushAsync();
        }
        File.Move(temp, output, overwrite: true);
    }
    finally
    {
        if (File.Exists(temp))
            File.Delete(temp);
    }
}

static async Task WriteAtomicBytesAsync(string output, ReadOnlyMemory<byte> bytes)
{
    output = Path.GetFullPath(output);
    var directory = Path.GetDirectoryName(output);
    if (string.IsNullOrWhiteSpace(directory))
        throw new InvalidOperationException("Worker output must have a parent directory.");
    Directory.CreateDirectory(directory);

    var temp = output + ".tmp." + Guid.NewGuid().ToString("N");
    try
    {
        await File.WriteAllBytesAsync(temp, bytes.ToArray());
        File.Move(temp, output, overwrite: true);
    }
    finally
    {
        if (File.Exists(temp))
            File.Delete(temp);
    }
}

static string ResolveArchivePath(string root, string archiveRelativePath)
{
    ArgumentException.ThrowIfNullOrWhiteSpace(root);
    ArgumentException.ThrowIfNullOrWhiteSpace(archiveRelativePath);

    var fullRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
    if (!Directory.Exists(fullRoot))
        throw new DirectoryNotFoundException(fullRoot);
    if (Path.IsPathRooted(archiveRelativePath))
        throw new InvalidDataException("Texture archive path must be relative to the configured source root.");

    var normalizedRelative = archiveRelativePath
        .Replace('\\', Path.DirectorySeparatorChar)
        .Replace('/', Path.DirectorySeparatorChar);
    var archivePath = Path.GetFullPath(Path.Combine(fullRoot, normalizedRelative));
    var comparison = OperatingSystem.IsWindows()
        ? StringComparison.OrdinalIgnoreCase
        : StringComparison.Ordinal;
    var prefix = fullRoot + Path.DirectorySeparatorChar;
    if (!archivePath.StartsWith(prefix, comparison))
        throw new InvalidDataException("Texture archive path escapes the configured source root.");
    if (!File.Exists(archivePath))
        throw new FileNotFoundException("Indexed texture archive no longer exists.", archivePath);
    return archivePath;
}

static bool TryCommonPreviewArgs(
    string[] args,
    out string root,
    out string archive,
    out int entryIndex,
    out string name,
    out string output)
{
    root = Option(args, "--root") ?? "";
    archive = Option(args, "--archive") ?? "";
    name = Option(args, "--name") ?? "";
    output = Option(args, "--output") ?? "";
    entryIndex = -1;
    var entryText = Option(args, "--entry");
    return !string.IsNullOrWhiteSpace(root) &&
           !string.IsNullOrWhiteSpace(archive) &&
           !string.IsNullOrWhiteSpace(name) &&
           !string.IsNullOrWhiteSpace(output) &&
           int.TryParse(entryText, out entryIndex) &&
           entryIndex >= 0;
}

if (args.Length == 0)
    return Usage();

try
{
    if (args[0].Equals("index", StringComparison.OrdinalIgnoreCase))
    {
        var root = Option(args, "--root");
        var output = Option(args, "--output");
        if (string.IsNullOrWhiteSpace(root) || string.IsNullOrWhiteSpace(output))
            return Usage();

        root = Path.GetFullPath(root);
        output = Path.GetFullPath(output);
        var route = (Option(args, "--route") ?? "eng").Trim().ToLowerInvariant();
        var index = route switch
        {
            "eng" or "english" => UtageAssetIndexer.IndexSelectedRoot(root, UtageContentRoute.English),
            "jpn" or "jp" or "japanese" => UtageAssetIndexer.IndexSelectedRoot(root, UtageContentRoute.Japanese),
            "direct" => UtageAssetIndexer.IndexRoot(root),
            _ => throw new ArgumentException($"Unsupported index route '{route}'. Expected eng, jpn, or direct."),
        };
        var snapshot = index.ToSnapshot(DateTimeOffset.UtcNow);
        await WriteAtomicJsonAsync(output, snapshot);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            command = "index",
            route,
            snapshot = output,
            archives = snapshot.Archives.Count,
            resources = snapshot.Resources.Count,
            issues = snapshot.Issues.Count,
        }));
        return 0;
    }

    if (args[0].Equals("preview-xet", StringComparison.OrdinalIgnoreCase))
    {
        if (!TryCommonPreviewArgs(args, out var root, out var archive, out var entryIndex, out var name, out var output))
            return Usage();

        root = Path.GetFullPath(root);
        output = Path.GetFullPath(output);
        var preview = UtageXetPreviewService.Create(root, archive, entryIndex, name);
        await WriteAtomicJsonAsync(output, preview);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            command = "preview-xet",
            preview = output,
            resource = preview.ResourceName,
            width = preview.Width,
            height = preview.Height,
            format = preview.BlockFormat,
            canEncode = preview.CanEncode,
        }));
        return 0;
    }

    if (args[0].Equals("roundtrip-xet", StringComparison.OrdinalIgnoreCase))
    {
        if (!TryCommonPreviewArgs(args, out var root, out var archive, out var entryIndex, out var name, out var output))
            return Usage();
        var rgbaPath = Option(args, "--rgba");
        if (string.IsNullOrWhiteSpace(rgbaPath))
            return Usage();

        root = Path.GetFullPath(root);
        output = Path.GetFullPath(output);
        rgbaPath = Path.GetFullPath(rgbaPath);
        var candidate = await File.ReadAllBytesAsync(rgbaPath);
        var roundTrip = UtageXetRoundTripService.Create(root, archive, entryIndex, name, candidate);
        await WriteAtomicJsonAsync(output, roundTrip);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            command = "roundtrip-xet",
            preview = output,
            resource = roundTrip.ResourceName,
            meanAbsoluteChannelError = roundTrip.MeanAbsoluteChannelError,
            maxChannelError = roundTrip.MaxChannelError,
        }));
        return 0;
    }

    if (args[0].Equals("graft-xet", StringComparison.OrdinalIgnoreCase))
    {
        var root = Option(args, "--root") ?? "";
        var archive = Option(args, "--archive") ?? "";
        var name = Option(args, "--name") ?? "";
        var rgbaPath = Option(args, "--rgba") ?? "";
        var maskPath = Option(args, "--mask") ?? "";
        var outputArc = Option(args, "--output-arc") ?? "";
        var auditPath = Option(args, "--audit") ?? "";
        var entryText = Option(args, "--entry");
        if (string.IsNullOrWhiteSpace(root) ||
            string.IsNullOrWhiteSpace(archive) ||
            string.IsNullOrWhiteSpace(name) ||
            string.IsNullOrWhiteSpace(rgbaPath) ||
            string.IsNullOrWhiteSpace(maskPath) ||
            string.IsNullOrWhiteSpace(outputArc) ||
            string.IsNullOrWhiteSpace(auditPath) ||
            !int.TryParse(entryText, out var entryIndex) || entryIndex < 0)
        {
            return Usage();
        }

        var sourceArcPath = ResolveArchivePath(root, archive);
        rgbaPath = Path.GetFullPath(rgbaPath);
        maskPath = Path.GetFullPath(maskPath);
        outputArc = Path.GetFullPath(outputArc);
        auditPath = Path.GetFullPath(auditPath);

        var pathComparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (string.Equals(sourceArcPath, outputArc, pathComparison))
            throw new InvalidOperationException("Production graft output must be a sibling ARC; overwriting the source ARC is forbidden.");
        if (string.Equals(sourceArcPath, auditPath, pathComparison) ||
            string.Equals(outputArc, auditPath, pathComparison))
            throw new InvalidOperationException("Source ARC, sibling ARC, and audit paths must all be distinct.");

        var sourceArc = await File.ReadAllBytesAsync(sourceArcPath);
        using (var sourceStream = new MemoryStream(sourceArc, writable: false))
        {
            var parsed = UtageArcReader.Read(sourceStream, sourceArcPath);
            if ((uint)entryIndex >= (uint)parsed.Entries.Count)
                throw new InvalidDataException("Indexed ARC member no longer exists at the recorded entry index.");
            var entry = parsed.Entries[entryIndex];
            if (!entry.Name.Equals(name, StringComparison.Ordinal))
                throw new InvalidDataException("Indexed ARC member identity changed; reindex before building this asset.");
            if (entry.TypeHash != UtageTypeHashes.Texture)
                throw new NotSupportedException("Selected ARC member is not a certified Utage texture resource.");
        }

        var candidate = await File.ReadAllBytesAsync(rgbaPath);
        var mask = await File.ReadAllBytesAsync(maskPath);
        var transaction = UtageSingleEntryXetGraft.BuildSibling(sourceArc, entryIndex, candidate, mask);

        await WriteAtomicBytesAsync(outputArc, transaction.SiblingArcBytes);
        await WriteAtomicJsonAsync(auditPath, transaction.Audit);

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            command = "graft-xet",
            sourceArc = sourceArcPath,
            siblingArc = outputArc,
            audit = auditPath,
            resource = transaction.Audit.MemberName,
            blocksReplaced = transaction.Audit.BlocksReplaced,
            blocksTotal = transaction.Audit.BlocksTotal,
            outsideMaskPixelDelta = transaction.Audit.OutsideMaskPixelDelta,
            approvedEligible = transaction.Audit.ApprovedEligible,
            sourceArcSha256 = transaction.Audit.SourceArcSha256,
            outputArcSha256 = transaction.Audit.OutputArcSha256,
        }));
        return 0;
    }

    return Usage();
}
catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or ArgumentException or InvalidOperationException)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(new
    {
        ok = false,
        errorType = ex.GetType().Name,
        message = ex.Message,
    }));
    return 2;
}
