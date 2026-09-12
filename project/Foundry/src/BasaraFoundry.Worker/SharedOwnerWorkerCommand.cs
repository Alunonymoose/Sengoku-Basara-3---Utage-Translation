using System.Security.Cryptography;
using System.Text.Json;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Index;

internal static class SharedOwnerWorkerCommand
{
    public const string CommandName = "graft-xet-set";

    public static string UsageLine =>
        "  BasaraFoundry.Worker graft-xet-set --root <eng-root> --archive <anchor.arc> --entry <index> --name <resource> " +
        "--pristine-root <jpn-root> --pristine-archive <relative.arc> --pristine-entry <index> --pristine-name <resource> " +
        "--rgba <candidate.rgba> --mask <mask.bin> --output-dir <owner-set-build-dir>";

    public static async Task<int?> TryRunAsync(string[] args)
    {
        if (args.Length == 0 || !args[0].Equals(CommandName, StringComparison.OrdinalIgnoreCase))
            return null;

        var root = Option(args, "--root") ?? "";
        var archive = Option(args, "--archive") ?? "";
        var name = Option(args, "--name") ?? "";
        var pristineRoot = Option(args, "--pristine-root") ?? "";
        var pristineArchive = Option(args, "--pristine-archive") ?? "";
        var pristineName = Option(args, "--pristine-name") ?? "";
        var rgbaPath = Option(args, "--rgba") ?? "";
        var maskPath = Option(args, "--mask") ?? "";
        var outputDir = Option(args, "--output-dir") ?? "";
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
            string.IsNullOrWhiteSpace(outputDir) ||
            !int.TryParse(entryText, out var entryIndex) || entryIndex < 0 ||
            !int.TryParse(pristineEntryText, out var pristineEntryIndex) || pristineEntryIndex < 0)
        {
            throw new ArgumentException("Invalid graft-xet-set arguments. " + UsageLine);
        }

        root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        pristineRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(pristineRoot));
        rgbaPath = Path.GetFullPath(rgbaPath);
        maskPath = Path.GetFullPath(maskPath);
        outputDir = Path.TrimEndingDirectorySeparator(Path.GetFullPath(outputDir));

        if (PathsEqual(root, pristineRoot))
            throw new InvalidOperationException("Shared-owner production requires distinct ENG and pristine JPN roots.");
        if (!Directory.Exists(root))
            throw new DirectoryNotFoundException(root);
        if (!Directory.Exists(pristineRoot))
            throw new DirectoryNotFoundException(pristineRoot);
        if (IsWithinRoot(root, outputDir, allowEqual: true) || IsWithinRoot(pristineRoot, outputDir, allowEqual: true))
            throw new InvalidOperationException("Shared-owner production output must be outside canonical ENG/JPN roots.");
        if (Directory.Exists(outputDir) || File.Exists(outputDir))
            throw new InvalidOperationException("Shared-owner output directory must not already exist; refusing to merge with a prior build.");

        var index = UtageAssetIndexer.IndexRoot(root);
        var owners = index.FindOwners(name, UtageTypeHashes.Texture);
        if (owners.Count < 2)
            throw new InvalidOperationException($"Resource '{name}' has {owners.Count} exact ENG owner(s); graft-xet-set requires at least two.");
        if (!owners.Any(owner =>
                owner.EntryIndex == entryIndex &&
                ArchivePathsEqual(owner.ArchivePath, archive) &&
                owner.ResourceName.Equals(name, StringComparison.Ordinal)))
        {
            throw new InvalidDataException("Shared-owner audit does not contain the selected anchor ARC/member identity; reindex before building.");
        }

        var pristineXet = ReadCertifiedTextureRaw(
            pristineRoot,
            pristineArchive,
            pristineEntryIndex,
            pristineName,
            out var pristineArcPath);

        var sources = new List<SharedOwnerXetSource>(owners.Count);
        foreach (var owner in owners)
        {
            _ = ReadCertifiedTextureRaw(root, owner.ArchivePath, owner.EntryIndex, name, out var ownerArcPath);
            if (PathsEqual(ownerArcPath, pristineArcPath))
                throw new InvalidOperationException("A target owner ARC resolves to the pristine counterpart ARC; source roots are not safely distinct.");
            sources.Add(new SharedOwnerXetSource(
                owner.ArchivePath,
                owner.EntryIndex,
                await File.ReadAllBytesAsync(ownerArcPath)));
        }

        var candidate = await File.ReadAllBytesAsync(rgbaPath);
        var mask = await File.ReadAllBytesAsync(maskPath);

        // Critical transaction boundary: validate/build every owner completely in
        // memory before creating any staging directory or output file.
        var set = UtageSharedOwnerXetGraft.BuildSet(
            sources,
            name,
            pristineXet,
            candidate,
            mask);

        var outputParent = Path.GetDirectoryName(outputDir)
            ?? throw new InvalidOperationException("Shared-owner output directory has no parent.");
        Directory.CreateDirectory(outputParent);
        var stageDir = outputDir + ".stage." + Guid.NewGuid().ToString("N");
        if (Directory.Exists(stageDir) || File.Exists(stageDir))
            throw new IOException("Generated staging path already exists.");

        var stagedOutputs = new List<object>(set.Outputs.Count);
        try
        {
            Directory.CreateDirectory(stageDir);
            foreach (var output in set.Outputs)
            {
                var relativeOutput = MakeSiblingRelativePath(output.ArchivePath);
                var stagedArc = ResolveContainedOutput(stageDir, relativeOutput);
                Directory.CreateDirectory(Path.GetDirectoryName(stagedArc)!);
                await File.WriteAllBytesAsync(stagedArc, output.Transaction.SiblingArcBytes);
                var stagedAudit = stagedArc + ".audit.json";
                await WriteJsonAsync(stagedAudit, output.Transaction.Audit);

                var persistedHash = Sha256(await File.ReadAllBytesAsync(stagedArc));
                if (!persistedHash.Equals(output.Transaction.Audit.OutputArcSha256, StringComparison.Ordinal))
                    throw new InvalidDataException($"Staged owner output hash mismatch for '{output.ArchivePath}'.");

                stagedOutputs.Add(new
                {
                    sourceArchive = output.ArchivePath,
                    memberIndex = output.MemberIndex,
                    outputRelativePath = relativeOutput.Replace('\\', '/'),
                    outputArcSha256 = output.Transaction.Audit.OutputArcSha256,
                    finalResourceSha256 = output.Transaction.Audit.FinalResourceSha256,
                });
            }

            var groupAuditPath = Path.Combine(stageDir, "owner-set.foundry.audit.json");
            await WriteJsonAsync(groupAuditPath, set.Audit);

            // Directory.Move is the promotion boundary. Stage and destination
            // share a parent, so normal local filesystems perform a same-volume
            // directory rename rather than exposing a half-written owner set.
            Directory.Move(stageDir, outputDir);
        }
        catch
        {
            if (Directory.Exists(stageDir))
                Directory.Delete(stageDir, recursive: true);
            throw;
        }

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            ok = true,
            command = CommandName,
            resource = set.Audit.ResourceName,
            owners = set.Audit.OwnerCount,
            outputDirectory = outputDir,
            groupAudit = Path.Combine(outputDir, "owner-set.foundry.audit.json"),
            buildSetSha256 = set.Audit.BuildSetSha256,
            pristineArc = pristineArcPath,
            pristineBaseSha256 = set.Audit.PristineBaseSha256,
            finalResourceSha256 = set.Audit.FinalResourceSha256,
            outputs = stagedOutputs,
        }));
        return 0;
    }

    private static string? Option(string[] args, string name)
    {
        for (var i = 0; i < args.Length - 1; i++)
        {
            if (args[i].Equals(name, StringComparison.OrdinalIgnoreCase))
                return args[i + 1];
        }
        return null;
    }

    private static byte[] ReadCertifiedTextureRaw(
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

    private static string ResolveArchivePath(string root, string relative)
    {
        if (Path.IsPathRooted(relative))
            throw new InvalidDataException("Archive path must be relative to its configured root.");
        var fullRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var normalized = relative.Replace('\\', Path.DirectorySeparatorChar).Replace('/', Path.DirectorySeparatorChar);
        var candidate = Path.GetFullPath(Path.Combine(fullRoot, normalized));
        if (!IsWithinRoot(fullRoot, candidate, allowEqual: false))
            throw new InvalidDataException("Archive path escapes its configured root.");
        if (!File.Exists(candidate))
            throw new FileNotFoundException("Indexed texture archive no longer exists.", candidate);
        return candidate;
    }

    private static string MakeSiblingRelativePath(string archiveRelativePath)
    {
        if (Path.IsPathRooted(archiveRelativePath))
            throw new InvalidDataException("Shared-owner archive path must remain relative.");
        var normalized = archiveRelativePath.Replace('\\', Path.DirectorySeparatorChar).Replace('/', Path.DirectorySeparatorChar);
        var directory = Path.GetDirectoryName(normalized);
        var fileName = Path.GetFileNameWithoutExtension(normalized) + ".foundry.arc";
        return string.IsNullOrEmpty(directory) ? fileName : Path.Combine(directory, fileName);
    }

    private static string ResolveContainedOutput(string stageRoot, string relative)
    {
        var root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(stageRoot));
        var candidate = Path.GetFullPath(Path.Combine(root, relative));
        if (!IsWithinRoot(root, candidate, allowEqual: false))
            throw new InvalidDataException("Generated owner output path escapes the staging root.");
        return candidate;
    }

    private static async Task WriteJsonAsync<T>(string path, T value)
    {
        await using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        await JsonSerializer.SerializeAsync(stream, value, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        });
        await stream.FlushAsync();
    }

    private static bool ArchivePathsEqual(string left, string right)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        return left.Replace('\\', '/').Equals(right.Replace('\\', '/'), comparison);
    }

    private static bool PathsEqual(string left, string right)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        return Path.TrimEndingDirectorySeparator(Path.GetFullPath(left))
            .Equals(Path.TrimEndingDirectorySeparator(Path.GetFullPath(right)), comparison);
    }

    private static bool IsWithinRoot(string root, string candidate, bool allowEqual)
    {
        var fullRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var fullCandidate = Path.TrimEndingDirectorySeparator(Path.GetFullPath(candidate));
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (fullRoot.Equals(fullCandidate, comparison))
            return allowEqual;
        return fullCandidate.StartsWith(fullRoot + Path.DirectorySeparatorChar, comparison);
    }

    private static string Sha256(ReadOnlySpan<byte> bytes) =>
        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}
