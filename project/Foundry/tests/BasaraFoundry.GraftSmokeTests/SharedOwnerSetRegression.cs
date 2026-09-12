using System.Buffers.Binary;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

/// <summary>
/// End-to-end Worker regression for the historical cockpit dependency class.
/// Proves that three byte-identical target owners are emitted as one staged
/// build set, while divergent same-named owners fail before an output directory
/// exists. This intentionally uses the real cockpit_020 internal resource name.
/// </summary>
internal static class SharedOwnerSetRegression
{
    [ModuleInitializer]
    internal static void Run()
    {
        const string resourceName = "id\\texture\\jpn\\cockpit\\cockpit_020_ID_HQ";
        const int width = 16;
        const int height = 8;
        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-owner-set-{Guid.NewGuid():N}");
        var engDir = Path.Combine(root, "canonical-eng");
        var jpnDir = Path.Combine(root, "canonical-jpn");
        var workDir = Path.Combine(root, "work");
        var buildParent = Path.Combine(root, "builds");
        Directory.CreateDirectory(engDir);
        Directory.CreateDirectory(jpnDir);
        Directory.CreateDirectory(workDir);
        Directory.CreateDirectory(buildParent);

        try
        {
            var pristineRgba = BuildBaseRgba(width, height);
            var pristineXet = BuildXetFromRgba(pristineRgba, width, height);
            var pristineDecoded = UtageXetCodec.DecodeTopLevel(pristineXet).Rgba;

            // The current ENG duplicate may already contain damage outside the
            // intended edit. All owners use the same current target bytes so the
            // shared-owner transaction is allowed to synchronize them; pristine
            // JPN remains the untouched-art authority.
            var currentEngRgba = pristineDecoded.ToArray();
            currentEngRgba[(0 * width + 8) * 4] ^= 0x55;
            var commonTargetXet = BuildXetFromRgba(currentEngRgba, width, height);
            var commonTargetArc = BuildSingleEntryArc(resourceName, commonTargetXet);

            var ownerNames = new[] { "cockpit1P.arc", "cockpit2P.arc", "vs_cockpit.arc" };
            var sourceSnapshots = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
            foreach (var ownerName in ownerNames)
            {
                var path = Path.Combine(engDir, ownerName);
                File.WriteAllBytes(path, commonTargetArc);
                sourceSnapshots[path] = commonTargetArc.ToArray();
            }
            File.WriteAllBytes(Path.Combine(jpnDir, "cockpit1P.arc"), BuildSingleEntryArc(resourceName, pristineXet));

            var candidate = pristineDecoded.ToArray();
            var mask = new byte[width * height];
            for (var y = 1; y < 3; y++)
            {
                for (var x = 1; x < 3; x++)
                {
                    var pixel = y * width + x;
                    var i = pixel * 4;
                    candidate[i] = 255;
                    candidate[i + 1] = 240;
                    candidate[i + 2] = 80;
                    candidate[i + 3] = 255;
                    mask[pixel] = 1;
                }
            }
            var candidatePath = Path.Combine(workDir, "candidate.rgba");
            var maskPath = Path.Combine(workDir, "mask.bin");
            File.WriteAllBytes(candidatePath, candidate);
            File.WriteAllBytes(maskPath, mask);

            var workerDll = FindWorkerDll();
            var outputDir = Path.Combine(buildParent, "cockpit-020-owner-set");
            var exit = RunWorker(
                workerDll,
                [
                    "graft-xet-set",
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
                    "--output-dir", outputDir,
                ],
                out var stdout,
                out var stderr);

            Equal(0, exit, $"shared-owner Worker succeeds ({stderr})");
            True(Directory.Exists(outputDir), "shared-owner output promoted as one directory");
            True(!Directory.EnumerateDirectories(buildParent, "*.stage.*", SearchOption.TopDirectoryOnly).Any(), "no staging directory leaked after promotion");

            var groupAuditPath = Path.Combine(outputDir, "owner-set.foundry.audit.json");
            True(File.Exists(groupAuditPath), "group audit written");
            using (var groupDocument = JsonDocument.Parse(File.ReadAllBytes(groupAuditPath)))
            {
                var group = groupDocument.RootElement;
                Equal(3, group.GetProperty("ownerCount").GetInt32(), "group audit owner count");
                True(group.GetProperty("allOwnersVerified").GetBoolean(), "group audit verifies all owners");
                Equal(64, group.GetProperty("buildSetSha256").GetString()!.Length, "group build-set hash present");
                Equal(resourceName, group.GetProperty("resourceName").GetString()!, "group audit resource identity");
            }

            var finalResourceHashes = new HashSet<string>(StringComparer.Ordinal);
            foreach (var ownerName in ownerNames)
            {
                var stem = Path.GetFileNameWithoutExtension(ownerName);
                var outputArc = Path.Combine(outputDir, stem + ".foundry.arc");
                var outputAudit = outputArc + ".audit.json";
                True(File.Exists(outputArc), $"{ownerName} synchronized output exists");
                True(File.Exists(outputAudit), $"{ownerName} per-owner audit exists");
                finalResourceHashes.Add(ReadMemberSha256(outputArc, resourceName));
            }
            Equal(1, finalResourceHashes.Count, "all owners contain byte-identical final XET");
            True(stdout.Contains("\"owners\":3", StringComparison.OrdinalIgnoreCase), "Worker reports complete owner count");

            foreach (var pair in sourceSnapshots)
                True(File.ReadAllBytes(pair.Key).AsSpan().SequenceEqual(pair.Value), $"canonical source unchanged: {Path.GetFileName(pair.Key)}");

            // Now prove a same-named but divergent duplicate is not synchronized
            // on assumption. Rebuild only vs_cockpit with a structurally valid but
            // byte-different target XET and require zero output directory.
            var divergentEngDir = Path.Combine(root, "divergent-eng");
            Directory.CreateDirectory(divergentEngDir);
            File.WriteAllBytes(Path.Combine(divergentEngDir, "cockpit1P.arc"), commonTargetArc);
            File.WriteAllBytes(Path.Combine(divergentEngDir, "cockpit2P.arc"), commonTargetArc);
            var divergentRgba = currentEngRgba.ToArray();
            divergentRgba[(4 * width + 12) * 4 + 1] ^= 0x66;
            var divergentXet = BuildXetFromRgba(divergentRgba, width, height);
            File.WriteAllBytes(Path.Combine(divergentEngDir, "vs_cockpit.arc"), BuildSingleEntryArc(resourceName, divergentXet));

            var rejectedDir = Path.Combine(buildParent, "divergent-owner-set");
            var rejectedExit = RunWorker(
                workerDll,
                [
                    "graft-xet-set",
                    "--root", divergentEngDir,
                    "--archive", "cockpit1P.arc",
                    "--entry", "0",
                    "--name", resourceName,
                    "--pristine-root", jpnDir,
                    "--pristine-archive", "cockpit1P.arc",
                    "--pristine-entry", "0",
                    "--pristine-name", resourceName,
                    "--rgba", candidatePath,
                    "--mask", maskPath,
                    "--output-dir", rejectedDir,
                ],
                out _,
                out var rejectedError);

            Equal(2, rejectedExit, "divergent shared owners fail closed");
            True(rejectedError.Contains("divergent raw target XET", StringComparison.OrdinalIgnoreCase), "divergence failure is explicit");
            True(!Directory.Exists(rejectedDir), "divergent transaction creates no promoted output directory");
            True(!Directory.EnumerateDirectories(buildParent, "divergent-owner-set.stage.*", SearchOption.TopDirectoryOnly).Any(), "divergent transaction creates no staging residue");

            Console.WriteLine("PASS shared-owner set Worker transaction regression");
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    private static byte[] BuildBaseRgba(int width, int height)
    {
        var rgba = new byte[width * height * 4];
        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var i = (y * width + x) * 4;
                rgba[i] = (byte)(20 + (x / 4) * 25);
                rgba[i + 1] = (byte)(60 + (y / 4) * 20);
                rgba[i + 2] = 30;
                rgba[i + 3] = 255;
            }
        }
        return rgba;
    }

    private static byte[] BuildXetFromRgba(byte[] rgba, int width, int height)
    {
        const int textureOffset = 20;
        var topLevel = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 16;
        var shell = new byte[textureOffset + topLevel];
        shell[0] = 0;
        shell[1] = (byte)'X';
        shell[2] = (byte)'E';
        shell[3] = (byte)'T';
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(4, 4), (uint)(0x97 | (2 << 28)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(8, 4), (uint)(1 | (width << 6) | (height << 19)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(12, 4), (uint)(1 | (0x2A << 8)));
        BinaryPrimitives.WriteUInt32BigEndian(shell.AsSpan(16, 4), textureOffset);
        return UtageXetCodec.ReplaceSingleLevel(shell, rgba).XetBytes;
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

    private static string ReadMemberSha256(string archivePath, string expectedName)
    {
        using var stream = File.OpenRead(archivePath);
        var arc = UtageArcReader.Read(stream, archivePath);
        if (arc.Entries.Count != 1 || !arc.Entries[0].Name.Equals(expectedName, StringComparison.Ordinal))
            throw new InvalidDataException("Synthetic synchronized output member identity changed.");
        stream.Position = 0;
        var raw = UtageArcReader.ReadDecompressedPayload(stream, arc.Entries[0]);
        return Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();
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
        throw new FileNotFoundException("Could not locate BasaraFoundry.Worker.dll for shared-owner set regression.");
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
            ?? throw new IOException("Could not start Worker shared-owner set regression process.");
        stdout = process.StandardOutput.ReadToEnd();
        stderr = process.StandardError.ReadToEnd();
        if (!process.WaitForExit(60_000))
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Worker shared-owner set regression exceeded 60 seconds.");
        }
        return process.ExitCode;
    }

    private static void Equal<T>(T expected, T actual, string label) where T : notnull
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new Exception($"FAIL {label}: expected {expected}, got {actual}");
        Console.WriteLine($"PASS {label}");
    }

    private static void True(bool value, string label)
    {
        if (!value)
            throw new Exception($"FAIL {label}");
        Console.WriteLine($"PASS {label}");
    }
}
