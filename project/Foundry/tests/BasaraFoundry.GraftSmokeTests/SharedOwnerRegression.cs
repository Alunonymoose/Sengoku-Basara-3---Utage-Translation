using System.Buffers.Binary;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text;
using BasaraFoundry.Game.Utage;

namespace BasaraFoundry.GraftSmokeTests;

/// <summary>
/// Regression for the cockpit V1 class of defect: the same internal texture
/// resource can be owned by multiple ARCs. The legacy single-owner production
/// command must refuse to emit any output when that condition is discovered.
/// This runs before the normal graft smoke Main so CI cannot accidentally skip
/// the owner-safety proof while still reporting the graft suite green.
/// </summary>
internal static class SharedOwnerRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        const string resourceName = "id\\texture\\jpn\\cockpit\\cockpit_020_ID_HQ";
        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-shared-owner-{Guid.NewGuid():N}");
        var engDir = Path.Combine(root, "canonical-eng");
        var jpnDir = Path.Combine(root, "canonical-jpn");
        var buildDir = Path.Combine(root, "build");
        var workDir = Path.Combine(root, "work");
        Directory.CreateDirectory(engDir);
        Directory.CreateDirectory(jpnDir);
        Directory.CreateDirectory(buildDir);
        Directory.CreateDirectory(workDir);

        try
        {
            var dummyPayload = new byte[] { 0, (byte)'X', (byte)'E', (byte)'T' };
            File.WriteAllBytes(Path.Combine(engDir, "cockpit1P.arc"), BuildSingleEntryArc(resourceName, dummyPayload));
            File.WriteAllBytes(Path.Combine(engDir, "vs_cockpit.arc"), BuildSingleEntryArc(resourceName, dummyPayload));
            File.WriteAllBytes(Path.Combine(jpnDir, "cockpit1P.arc"), BuildSingleEntryArc(resourceName, dummyPayload));

            var candidatePath = Path.Combine(workDir, "candidate.rgba");
            var maskPath = Path.Combine(workDir, "mask.bin");
            File.WriteAllBytes(candidatePath, [0, 0, 0, 0]);
            File.WriteAllBytes(maskPath, [1]);

            var outputPath = Path.Combine(buildDir, "cockpit1P.foundry.arc");
            var auditPath = outputPath + ".audit.json";
            var workerDll = FindWorkerDll();
            var exit = RunWorker(
                workerDll,
                [
                    "graft-xet",
                    "--root", engDir,
                    "--archive", "cockpit1P.arc",
                    "--entry", "0",
                    "--name", resourceName,
                    "--pristine-root", jpnDir,
                    "--pristine-archive", "cockpit1P.arc",
                    "--pristine-entry", "0",
                    "--pristine-name", resourceName,
                    "--rgba", candidatePath,
                    "--mask", maskPath,
                    "--output-arc", outputPath,
                    "--audit", auditPath,
                ],
                out var stdout,
                out var stderr);

            if (exit != 2)
                throw new Exception($"FAIL shared-owner Worker gate: expected exit 2, got {exit}. stdout={stdout} stderr={stderr}");
            if (!stderr.Contains("has 2 exact ENG owners", StringComparison.OrdinalIgnoreCase) ||
                !stderr.Contains("Refusing unsafe single-owner graft", StringComparison.OrdinalIgnoreCase) ||
                !stderr.Contains("cockpit1P.arc#0", StringComparison.OrdinalIgnoreCase) ||
                !stderr.Contains("vs_cockpit.arc#0", StringComparison.OrdinalIgnoreCase))
            {
                throw new Exception($"FAIL shared-owner Worker gate explanation: {stderr}");
            }
            if (File.Exists(outputPath) || File.Exists(auditPath))
                throw new Exception("FAIL shared-owner Worker gate emitted production output before refusing the unsafe transaction.");

            Console.WriteLine("PASS shared-owner Worker gate refuses one-ARC output for a two-owner texture");
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    private static string FindWorkerDll()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            var candidate = Path.Combine(
                dir.FullName,
                "src",
                "BasaraFoundry.Worker",
                "bin",
                "Release",
                "net10.0",
                "BasaraFoundry.Worker.dll");
            if (File.Exists(candidate))
                return candidate;
        }
        throw new FileNotFoundException("Could not locate BasaraFoundry.Worker.dll for shared-owner regression.");
    }

    private static int RunWorker(
        string workerDll,
        IReadOnlyList<string> arguments,
        out string stdout,
        out string stderr)
    {
        var start = new ProcessStartInfo
        {
            FileName = "dotnet",
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        start.ArgumentList.Add(workerDll);
        foreach (var argument in arguments)
            start.ArgumentList.Add(argument);

        using var process = Process.Start(start)
            ?? throw new IOException("Could not start Worker shared-owner regression process.");
        stdout = process.StandardOutput.ReadToEnd();
        stderr = process.StandardError.ReadToEnd();
        if (!process.WaitForExit(60_000))
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Worker shared-owner regression exceeded 60 seconds.");
        }
        return process.ExitCode;
    }

    private static byte[] BuildSingleEntryArc(string name, byte[] rawPayload)
    {
        const int headerSize = 8;
        const int entrySize = 80;
        const int payloadOffset = 128;
        var arc = new byte[payloadOffset + rawPayload.Length];
        arc[0] = 0;
        arc[1] = (byte)'C';
        arc[2] = (byte)'R';
        arc[3] = (byte)'A';
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(4, 2), 8);
        BinaryPrimitives.WriteUInt16BigEndian(arc.AsSpan(6, 2), 1);
        var record = arc.AsSpan(headerSize, entrySize);
        var nameBytes = Encoding.UTF8.GetBytes(name);
        if (nameBytes.Length >= 64)
            throw new ArgumentException("Synthetic ARC name must fit the 64-byte field.", nameof(name));
        nameBytes.CopyTo(record);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), UtageTypeHashes.Texture);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), checked((uint)rawPayload.Length));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), checked((uint)rawPayload.Length << 3));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), payloadOffset);
        rawPayload.CopyTo(arc.AsSpan(payloadOffset));
        return arc;
    }
}
