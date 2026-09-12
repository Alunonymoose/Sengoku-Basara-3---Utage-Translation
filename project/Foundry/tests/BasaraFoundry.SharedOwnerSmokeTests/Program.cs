using System.Buffers.Binary;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.SharedOwnerSmokeTests;

internal static class Program
{
    private const string SharedName = "id\\texture\\jpn\\cockpit\\cockpit_020_ID_HQ";

    private static int Main()
    {
        const int width = 16;
        const int height = 8;
        var rgba = new byte[width * height * 4];
        for (var y = 0; y < height; y++)
        for (var x = 0; x < width; x++)
        {
            var i = (y * width + x) * 4;
            rgba[i] = (byte)(25 + x * 3);
            rgba[i + 1] = (byte)(60 + y * 8);
            rgba[i + 2] = 110;
            rgba[i + 3] = 255;
        }

        var pristineXet = BuildXetFromRgba(rgba, width, height);
        var pristineDecoded = UtageXetCodec.DecodeTopLevel(pristineXet).Rgba;
        var candidate = pristineDecoded.ToArray();
        var mask = new byte[width * height];
        for (var y = 1; y < 3; y++)
        for (var x = 1; x < 3; x++)
        {
            var i = (y * width + x) * 4;
            candidate[i] = 235;
            candidate[i + 1] = 210;
            candidate[i + 2] = 90;
            mask[y * width + x] = 1;
        }

        var ownerArc = BuildSingleEntryArc(SharedName, pristineXet);
        var direct = UtageSharedOwnerXetGraft.BuildSet(
            [
                new SharedOwnerXetSource("id/cockpit1P.arc", 0, ownerArc.ToArray()),
                new SharedOwnerXetSource("id/cockpit2P.arc", 0, ownerArc.ToArray()),
                new SharedOwnerXetSource("id/vs_cockpit.arc", 0, ownerArc.ToArray()),
            ],
            SharedName,
            pristineXet,
            candidate,
            mask,
            new DateTimeOffset(2026, 9, 12, 12, 0, 0, TimeSpan.Zero));

        Equal(3, direct.Outputs.Count, "direct shared-owner transaction produces all three owners");
        Equal(3, direct.Audit.OwnerCount, "group audit records complete owner count");
        True(direct.Audit.AllOwnersVerified, "group audit certifies every owner");
        True(direct.Audit.SourceOwnersByteIdentical, "group audit records identical target-XET prerequisite");
        True(direct.Outputs.All(output => output.Transaction.Audit.FinalResourceSha256 == direct.Audit.FinalResourceSha256),
            "all owners contain the same final XET hash");
        UtageSharedOwnerAuditVerifier.EnsureValid(direct.Audit);

        var forgedAudit = direct.Audit with { BuildSetSha256 = new string('0', 64) };
        Throws<InvalidDataException>(
            () => UtageSharedOwnerAuditVerifier.EnsureValid(forgedAudit),
            "group verifier rejects forged BuildSetSha256");

        var divergentRgba = pristineDecoded.ToArray();
        divergentRgba[(0 * width + 12) * 4] ^= 0x3F;
        var divergentXet = BuildXetFromRgba(divergentRgba, width, height);
        var divergentArc = BuildSingleEntryArc(SharedName, divergentXet);
        Throws<InvalidOperationException>(
            () => UtageSharedOwnerXetGraft.BuildSet(
                [
                    new SharedOwnerXetSource("id/cockpit1P.arc", 0, ownerArc.ToArray()),
                    new SharedOwnerXetSource("id/cockpit2P.arc", 0, divergentArc),
                    new SharedOwnerXetSource("id/vs_cockpit.arc", 0, ownerArc.ToArray()),
                ],
                SharedName,
                pristineXet,
                candidate,
                mask),
            "divergent same-name target XET owners fail closed");

        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-owner-set-{Guid.NewGuid():N}");
        var engRoot = Path.Combine(root, "eng");
        var jpnRoot = Path.Combine(root, "jpn");
        var work = Path.Combine(root, "work");
        Directory.CreateDirectory(Path.Combine(engRoot, "id"));
        Directory.CreateDirectory(Path.Combine(jpnRoot, "id"));
        Directory.CreateDirectory(work);
        try
        {
            foreach (var name in new[] { "cockpit1P.arc", "cockpit2P.arc", "vs_cockpit.arc" })
                File.WriteAllBytes(Path.Combine(engRoot, "id", name), ownerArc);
            File.WriteAllBytes(Path.Combine(jpnRoot, "id", "cockpit1P.arc"), BuildSingleEntryArc(SharedName, pristineXet));
            var candidatePath = Path.Combine(work, "candidate.rgba");
            var maskPath = Path.Combine(work, "mask.bin");
            File.WriteAllBytes(candidatePath, candidate);
            File.WriteAllBytes(maskPath, mask);

            var workerDll = FindWorkerDll();
            var unsafeSingle = Path.Combine(work, "unsafe-single.arc");
            var singleExit = RunWorker(workerDll,
                [
                    "graft-xet",
                    "--root", engRoot,
                    "--archive", "id/cockpit1P.arc",
                    "--entry", "0",
                    "--name", SharedName,
                    "--pristine-root", jpnRoot,
                    "--pristine-archive", "id/cockpit1P.arc",
                    "--pristine-entry", "0",
                    "--pristine-name", SharedName,
                    "--rgba", candidatePath,
                    "--mask", maskPath,
                    "--output-arc", unsafeSingle,
                    "--audit", unsafeSingle + ".audit.json",
                ], out _, out var singleError);
            Equal(2, singleExit, "legacy single-owner Worker path refuses a shared texture");
            True(!File.Exists(unsafeSingle), "unsafe single-owner output is never created");
            True(singleError.Contains("synchronized multi-owner build", StringComparison.OrdinalIgnoreCase),
                "single-owner refusal explains synchronized-owner requirement");

            var setOutput = Path.Combine(work, "owner-set-build");
            var setExit = RunWorker(workerDll,
                [
                    "graft-xet-set",
                    "--root", engRoot,
                    "--archive", "id/cockpit1P.arc",
                    "--entry", "0",
                    "--name", SharedName,
                    "--pristine-root", jpnRoot,
                    "--pristine-archive", "id/cockpit1P.arc",
                    "--pristine-entry", "0",
                    "--pristine-name", SharedName,
                    "--rgba", candidatePath,
                    "--mask", maskPath,
                    "--output-dir", setOutput,
                ], out var setStdout, out var setError);
            Equal(0, setExit, $"shared-owner Worker transaction succeeds ({setError})");
            True(Directory.Exists(setOutput), "owner-set build is promoted as one directory");
            var groupAuditPath = Path.Combine(setOutput, "owner-set.foundry.audit.json");
            True(File.Exists(groupAuditPath), "owner-set group audit is persisted");
            var persisted = JsonSerializer.Deserialize<SharedOwnerXetGraftGroupAudit>(
                File.ReadAllText(groupAuditPath),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                ?? throw new Exception("Persisted owner-set audit was empty.");
            UtageSharedOwnerAuditVerifier.EnsureValid(persisted);
            Equal(3, persisted.OwnerCount, "Worker group audit retains all three owners");
            True(setStdout.Contains(persisted.BuildSetSha256, StringComparison.OrdinalIgnoreCase),
                "Worker reports deterministic complete build-set hash");
            foreach (var name in new[] { "cockpit1P.foundry.arc", "cockpit2P.foundry.arc", "vs_cockpit.foundry.arc" })
                True(File.Exists(Path.Combine(setOutput, "id", name)), $"Worker emitted synchronized {name}");

            // Prove failure is atomic: a divergent duplicate is rejected before an
            // output directory appears, so no partially synchronized build can escape.
            File.WriteAllBytes(Path.Combine(engRoot, "id", "cockpit2P.arc"), divergentArc);
            var divergentOutput = Path.Combine(work, "divergent-owner-set");
            var divergentExit = RunWorker(workerDll,
                [
                    "graft-xet-set",
                    "--root", engRoot,
                    "--archive", "id/cockpit1P.arc",
                    "--entry", "0",
                    "--name", SharedName,
                    "--pristine-root", jpnRoot,
                    "--pristine-archive", "id/cockpit1P.arc",
                    "--pristine-entry", "0",
                    "--pristine-name", SharedName,
                    "--rgba", candidatePath,
                    "--mask", maskPath,
                    "--output-dir", divergentOutput,
                ], out _, out var divergentError);
            Equal(2, divergentExit, "Worker rejects divergent duplicate owner XETs");
            True(!Directory.Exists(divergentOutput), "divergent failure exposes no partial owner-set directory");
            True(divergentError.Contains("divergent raw target XET", StringComparison.OrdinalIgnoreCase),
                "divergent rejection explains why automatic synchronization stopped");
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }

        Console.WriteLine("Shared-owner smoke tests passed.");
        Console.WriteLine($"  build_set_sha256={direct.Audit.BuildSetSha256}");
        return 0;
    }

    private static string FindWorkerDll()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            var candidate = Path.Combine(dir.FullName, "src", "BasaraFoundry.Worker", "bin", "Release", "net10.0", "BasaraFoundry.Worker.dll");
            if (File.Exists(candidate))
                return candidate;
        }
        throw new FileNotFoundException("Could not locate the already-built BasaraFoundry.Worker.dll for shared-owner CLI smoke.");
    }

    private static int RunWorker(string workerDll, IReadOnlyList<string> args, out string stdout, out string stderr)
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
        foreach (var arg in args)
            start.ArgumentList.Add(arg);
        using var process = Process.Start(start) ?? throw new IOException("Could not start Worker shared-owner smoke process.");
        stdout = process.StandardOutput.ReadToEnd();
        stderr = process.StandardError.ReadToEnd();
        if (!process.WaitForExit(60_000))
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Worker shared-owner smoke exceeded 60 seconds.");
        }
        return process.ExitCode;
    }

    private static byte[] BuildXetFromRgba(byte[] rgba, int width, int height)
    {
        const int textureOffset = 20;
        var payloadLength = Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 16;
        var shell = new byte[textureOffset + payloadLength];
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

    private static byte[] BuildSingleEntryArc(string resourceName, byte[] rawPayload)
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
        var nameBytes = Encoding.UTF8.GetBytes(resourceName);
        if (nameBytes.Length >= 64)
            throw new ArgumentException("Synthetic ARC resource name must fit the 64-byte field.", nameof(resourceName));
        nameBytes.CopyTo(record);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(64, 4), UtageTypeHashes.Texture);
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(68, 4), checked((uint)rawPayload.Length));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(72, 4), checked((uint)rawPayload.Length << 3));
        BinaryPrimitives.WriteUInt32BigEndian(record.Slice(76, 4), payloadOffset);
        rawPayload.CopyTo(arc.AsSpan(payloadOffset));
        return arc;
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

    private static void Throws<TException>(Action action, string label) where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            Console.WriteLine($"PASS {label}");
            return;
        }
        throw new Exception($"FAIL {label}: expected {typeof(TException).Name}");
    }
}
