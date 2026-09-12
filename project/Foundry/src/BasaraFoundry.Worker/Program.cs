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
    Console.Error.WriteLine("  BasaraFoundry.Worker graft-xet --root <eng-root> --archive <relative.arc> --entry <index> --name <resource> --pristine-root <jpn-root> --pristine-archive <relative.arc> --pristine-entry <index> --pristine-name <resource> --rgba <candidate.rgba> --mask <mask.bin> --output-arc <build.arc> --audit <audit.json>");
    Console.Error.WriteLine(SharedOwnerWorkerCommand.UsageLine);
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
    if (!IsWithinRoot(fullRoot, archivePath, allowEqual: false))
        throw new InvalidDataException("Texture archive path escapes the configured source root.");
    if (!File.Exists(archivePath))
        throw new FileNotFoundException("Indexed texture archive no longer exists.", archivePath);
    return archivePath;
}

static byte[] ReadCertifiedTextureRaw(
    string root,
    string archiveRelativePath,
    int entryIndex,
    string expectedName,
    out string archivePath)
{
    archivePath = ResolveArchivePath(root, archiveRelativePath);
    using var stream = File.Open(archivePath, FileMode.Open, FileAccess.Read, FileShare.Read);
    var parsed = UtageArcReader.Read(stream, archivePath);
    if ((uint)entryIndex >= (uint)parsed.Entries.Count)
        throw new InvalidDataException("Indexed ARC member no longer exists at the recorded entry index.");
    var entry = parsed.Entries[entryIndex];
    if (entry.Index != entryIndex || !entry.Name.Equals(expectedName, StringComparison.Ordinal))
        throw new InvalidDataException("Indexed ARC member identity changed; reindex before building this asset.");
    if (entry.TypeHash != UtageTypeHashes.Texture)
        throw new NotSupportedException("Selected ARC member is not a certified Utage texture resource.");
    stream.Position = 0;
    return UtageArcReader.ReadDecompressedPayload(stream, entry);
}

static bool IsWithinRoot(string root, string candidate, bool allowEqual)
{
    var fullRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
    var fullCandidate = Path.TrimEndingDirectorySeparator(Path.GetFullPath(candidate));
    var comparison = OperatingSystem.IsWindows()
        ? StringComparison.OrdinalIgnoreCase
        : StringComparison.Ordinal;
    if (string.Equals(fullRoot, fullCandidate, comparison))
        return allowEqual;
    return fullCandidate.StartsWith(fullRoot + Path.DirectorySeparatorChar, comparison);
}

static bool PathsEqual(string left, string right)
{
    var comparison = OperatingSystem.IsWindows()
        ? StringComparison.OrdinalIgnoreCase
        : StringComparison.Ordinal;
    return string.Equals(Path.GetFullPath(left), Path.GetFullPath(right), comparison);
}

static bool ArchivePathsEqual(string left, string right)
{
    var normalizedLeft = left.Replace('\\', '/');
    var normalizedRight = right.Replace('\\', '/');
    var comparison = OperatingSystem.IsWindows()
        ? StringComparison.OrdinalIgnoreCase
        : StringComparison.Ordinal;
    return normalizedLeft.Equals(normalizedRight, comparison);
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
    var sharedOwnerResult = await SharedOwnerWorkerCommand.TryRunAsync(args);
    if (sharedOwnerResult.HasValue)
        return sharedOwnerResult.Value;

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
        var pristineRoot = Option(args, "--pristine-root") ?? "";
        var pristineArchive = Option(args, "--pristine-archive") ?? "";
        var pristineName = Option(args, "--pristine-name") ?? "";
        var rgbaPath = Option(args, "--rgba") ?? "";
        var maskPath = Option(args, "--mask") ?? "";
        var outputArc = Option(args, "--output-arc") ?? "";
        var auditPath = Option(args, "--audit") ?? "";
        var entryText = Option(args, "--entry");
        var pristineEntryText = Option(args, "--pristine-entry");
        if (string.IsNullOrWhiteSpace(root) ||
            string.IsNullOrWhiteSpace(archive) ||
            string.IsNullOrWhiteSpace(name) ||
            string.IsNullOrWhiteSpace(pristineRoot) ||
            string.IsNullOrWhiteSpace(pristineArchive) ||
            string.IsNullOrWhiteSpace(pristineName) ||
            string.IsNullOrWhiteSpace(rgbaPath) ||
            string.IsNullOrWhiteSpace(maskPath) ||
            string.IsNullOrWhiteSpace(outputArc) ||
            string.IsNullOrWhiteSpace(auditPath) ||
            !int.TryParse(entryText, out var entryIndex) || entryIndex < 0 ||
            !int.TryParse(pristineEntryText, out var pristineEntryIndex) || pristineEntryIndex < 0)
        {
            return Usage();
        }

        root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        pristineRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(pristineRoot));
        if (PathsEqual(root, pristineRoot))
            throw new InvalidOperationException("Production graft requires a distinct pristine counterpart root; ENG cannot certify itself as JPN artwork authority.");

        // Production edits are not allowed to pretend a duplicated internal
        // resource is owned by only the selected ARC. This is the exact class
        // of failure that previously left cockpit1P/cockpit2P/vs_cockpit out
        // of sync. Until the synchronized owner-set transaction is invoked,
        // the legacy single-owner command fails closed.
        var engIndex = UtageAssetIndexer.IndexRoot(root);
        var owners = engIndex.FindOwners(name, UtageTypeHashes.Texture);
        if (owners.Count == 0)
            throw new InvalidDataException("Production owner audit could not rediscover the selected texture in the ENG source root.");
        if (!owners.Any(owner =>
                owner.EntryIndex == entryIndex &&
                ArchivePathsEqual(owner.ArchivePath, archive) &&
                owner.ResourceName.Equals(name, StringComparison.Ordinal)))
        {
            throw new InvalidDataException("Production owner audit does not contain the selected ARC/member identity; reindex before building.");
        }
        if (owners.Count > 1)
        {
            var ownerList = string.Join(", ", owners.Select(owner => $"{owner.ArchivePath}#{owner.EntryIndex}"));
            throw new InvalidOperationException(
                $"Resource '{name}' has {owners.Count} exact ENG owners. Refusing unsafe single-owner graft; " +
                $"use a synchronized multi-owner build. Owners: {ownerList}");
        }

        _ = ReadCertifiedTextureRaw(root, archive, entryIndex, name, out var sourceArcPath);
        var pristineXet = ReadCertifiedTextureRaw(
            pristineRoot,
            pristineArchive,
            pristineEntryIndex,
            pristineName,
            out var pristineArcPath);
        if (PathsEqual(sourceArcPath, pristineArcPath))
            throw new InvalidOperationException("Target ARC and pristine counterpart ARC must be distinct source files.");

        rgbaPath = Path.GetFullPath(rgbaPath);
        maskPath = Path.GetFullPath(maskPath);
        outputArc = Path.GetFullPath(outputArc);
        auditPath = Path.GetFullPath(auditPath);

        if (PathsEqual(sourceArcPath, outputArc) || PathsEqual(pristineArcPath, outputArc))
            throw new InvalidOperationException("Production output must never overwrite a canonical source ARC.");
        if (PathsEqual(sourceArcPath, auditPath) || PathsEqual(pristineArcPath, auditPath) || PathsEqual(outputArc, auditPath))
            throw new InvalidOperationException("Source ARC, pristine ARC, output ARC, and audit paths must be distinct.");
        if (IsWithinRoot(root, outputArc, allowEqual: true) || IsWithinRoot(pristineRoot, outputArc, allowEqual: true))
            throw new InvalidOperationException("Production output must be written outside canonical ENG/JPN source roots.");
        if (IsWithinRoot(root, auditPath, allowEqual: true) || IsWithinRoot(pristineRoot, auditPath, allowEqual: true))
            throw new InvalidOperationException("Production audit must be written outside canonical ENG/JPN source roots.");

        var sourceArc = await File.ReadAllBytesAsync(sourceArcPath);
        var candidate = await File.ReadAllBytesAsync(rgbaPath);
        var mask = await File.ReadAllBytesAsync(maskPath);
        var transaction = UtageSingleEntryXetGraft.BuildSibling(
            sourceArc,
            entryIndex,
            pristineXet,
            candidate,
            mask);

        await WriteAtomicBytesAsync(outputArc, transaction.SiblingArcBytes);
        await WriteAtomicJsonAsync(auditPath, transaction.Audit);

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            command = "graft-xet",
            sourceArc = sourceArcPath,
            pristineArc = pristineArcPath,
            siblingArc = outputArc,
            audit = auditPath,
            resource = transaction.Audit.MemberName,
            pristineResource = pristineName,
            owners = owners.Count,
            blocksReplaced = transaction.Audit.BlocksReplaced,
            blocksTotal = transaction.Audit.BlocksTotal,
            outsideMaskPixelDelta = transaction.Audit.OutsideMaskPixelDelta,
            approvedEligible = transaction.Audit.ApprovedEligible,
            sourceArcSha256 = transaction.Audit.SourceArcSha256,
            outputArcSha256 = transaction.Audit.OutputArcSha256,
            pristineBaseSha256 = transaction.Audit.PristineBaseSha256,
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
