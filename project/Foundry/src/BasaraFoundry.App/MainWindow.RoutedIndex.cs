using System.Diagnostics;
using BasaraFoundry.Game.Utage.Index;

namespace BasaraFoundry.App;

public sealed partial class MainWindow
{
    private static async Task RunRoutedIndexWorkerAsync(
        string root,
        string output,
        UtageContentRoute route)
    {
        var workerPath = Path.Combine(AppContext.BaseDirectory, "worker", "BasaraFoundry.Worker.exe");
        if (!File.Exists(workerPath))
            throw new FileNotFoundException("The isolated Foundry indexing worker is missing from this build.", workerPath);

        root = Path.GetFullPath(root);
        output = Path.GetFullPath(output);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var start = new ProcessStartInfo
        {
            FileName = workerPath,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in new[]
        {
            "index", "--root", root,
            "--route", route == UtageContentRoute.Japanese ? "jpn" : "eng",
            "--output", output,
        })
        {
            start.ArgumentList.Add(argument);
        }

        using var process = Process.Start(start)
            ?? throw new IOException("Could not start the isolated Foundry indexing worker.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(2));

        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Reference index worker exceeded the 2-minute safety limit and was terminated.");
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        if (process.ExitCode != 0)
        {
            var detail = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
            throw new InvalidDataException($"Reference index worker failed with exit code {process.ExitCode}: {detail.Trim()}");
        }
        if (!File.Exists(output))
            throw new InvalidDataException("Reference index worker reported success but did not produce a snapshot.");
    }

    private void RequireDistinctReferenceRoute(string referenceRoot, UtageContentRoute referenceRoute, string label)
    {
        var currentRoot = _project?.Sources.UtageEnglish;
        if (string.IsNullOrWhiteSpace(currentRoot))
            throw new InvalidDataException("Current Utage English source is not configured.");

        UtageRouteResolver.RequireDistinct(
            currentRoot,
            UtageContentRoute.English,
            referenceRoot,
            referenceRoute,
            label);
    }
}
