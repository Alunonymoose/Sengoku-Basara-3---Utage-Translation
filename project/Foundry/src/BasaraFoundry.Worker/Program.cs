using System.Text.Json;
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
