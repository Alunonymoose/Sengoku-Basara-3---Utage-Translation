using System.Text.Json;
using BasaraFoundry.Game.Utage.Index;

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
    Console.Error.WriteLine("Usage: BasaraFoundry.Worker index --root <utage-root> --output <snapshot.json>");
    return 64;
}

if (args.Length == 0 || !args[0].Equals("index", StringComparison.OrdinalIgnoreCase))
    return Usage();

var root = Option(args, "--root");
var output = Option(args, "--output");
if (string.IsNullOrWhiteSpace(root) || string.IsNullOrWhiteSpace(output))
    return Usage();

try
{
    root = Path.GetFullPath(root);
    output = Path.GetFullPath(output);

    var index = UtageAssetIndexer.IndexRoot(root);
    var snapshot = index.ToSnapshot(DateTimeOffset.UtcNow);

    var directory = Path.GetDirectoryName(output);
    if (string.IsNullOrWhiteSpace(directory))
        throw new InvalidOperationException("Snapshot output must have a parent directory.");
    Directory.CreateDirectory(directory);

    var temp = output + ".tmp." + Guid.NewGuid().ToString("N");
    try
    {
        await using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            await JsonSerializer.SerializeAsync(stream, snapshot, new JsonSerializerOptions
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

    Console.WriteLine(JsonSerializer.Serialize(new
    {
        ok = true,
        snapshot = output,
        archives = snapshot.Archives.Count,
        resources = snapshot.Resources.Count,
        issues = snapshot.Issues.Count,
    }));
    return 0;
}
catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or ArgumentException)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(new
    {
        ok = false,
        errorType = ex.GetType().Name,
        message = ex.Message,
    }));
    return 2;
}
