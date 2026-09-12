using System.Buffers.Binary;
using System.Diagnostics;
using System.Text;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage;
using BasaraFoundry.Game.Utage.Arc;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.GraftSmokeTests;

/// <summary>
/// Synthetic proof of the Research Ledger BC3 block-graft production rule and
/// the production transaction that carries one verified XET into one external build ARC.
/// Also exercises the actual isolated Worker CLI used by the WinUI application.
/// </summary>
internal static class Program
{
    private static int Main()
    {
        const int width = 16;
        const int height = 8;
        var sourceRgba = new byte[width * height * 4];
        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var i = (y * width + x) * 4;
                sourceRgba[i] = (byte)(10 + (x / 4) * 30);
                sourceRgba[i + 1] = 80;
                sourceRgba[i + 2] = 20;
                sourceRgba[i + 3] = 255;
            }
        }

        var pristineXet = BuildXetFromRgba(sourceRgba, width, height);
        var pristineDecoded = UtageXetCodec.DecodeTopLevel(pristineXet).Rgba;
        var candidate = pristineDecoded.ToArray();

        for (var y = 1; y < 3; y++)
        {
            for (var x = 1; x < 3; x++)
            {
                var i = (y * width + x) * 4;
                candidate[i] = 255;
                candidate[i + 1] = 255;
                candidate[i + 2] = 120;
                candidate[i + 3] = 255;
            }
        }

        var mask = new byte[width * height];
        for (var y = 1; y < 3; y++)
        {
            for (var x = 1; x < 3; x++)
                mask[y * width + x] = 1;
        }

        var fromRects = EditMaskCodec.ToMask01(
            new EditMask([new PixelRect(1, 1, 3, 3)]),
            width,
            height);
        True(mask.AsSpan().SequenceEqual(fromRects), "EditMaskCodec matches hand-built mask01");

        var proposal = UtageEditMaskProposalService.Create(pristineDecoded, candidate, width, height);
        Equal(4, proposal.ChangedPixels, "mask proposal exact changed-pixel count");
        Equal(1, proposal.AffectedBlocks, "mask proposal affected BC3 block count");
        Equal(16, proposal.EffectiveBlockPixels, "mask proposal effective block footprint");
        Equal(12, proposal.PotentialCollateralPixels, "mask proposal exposes block-neighbour pixels");
        Equal(new PixelRect(1, 1, 3, 3), proposal.ChangedBounds!, "mask proposal changed bounds");
        True(mask.AsSpan().SequenceEqual(proposal.Mask01), "mask proposal equals exact candidate delta");
        Equal(candidate.Length, UtageEditMaskProposalService.CreateReviewRgba(candidate, proposal).Length, "mask review RGBA dimensions preserved");

        var result = UtageBc3BlockGraft.GraftTopLevel(pristineXet, candidate, mask);
        True(result.Report.Ok, "graft reports ok");
        Equal(1, result.Report.BlocksReplaced, "exactly one block replaced");
        Equal(0, result.Report.OutsideMaskPixelDelta, "outside-mask delta is zero");

        var bad = candidate.ToArray();
        bad[(0 * width + 8) * 4] ^= 0x7F;
        var rejected = UtageBc3BlockGraft.GraftTopLevel(pristineXet, bad, mask);
        True(!rejected.Report.Ok, "rejects outside-mask changes");

        // Simulate an already-damaged ENG texture. Corrupt block (2,0), which is
        // outside the candidate's edit block. Production must still take that
        // untouched block from the pristine Japanese XET, never from ENG.
        var engMemberRgba = pristineDecoded.ToArray();
        engMemberRgba[(0 * width + 8) * 4] ^= 0x55;
        var engMemberXet = BuildXetFromRgba(engMemberRgba, width, height);
        var sourceArc = BuildSingleEntryArc("roulette_000_ID_HQ", engMemberXet);
        var pristineArc = BuildSingleEntryArc("roulette_000_ID_HQ", pristineXet);
        var sourceArcSnapshot = sourceArc.ToArray();

        Throws<ArgumentException>(
            () => UtageSingleEntryXetGraft.BuildSibling(
                sourceArc,
                0,
                Array.Empty<byte>(),
                candidate,
                mask),
            "production transaction rejects missing pristine counterpart");

        var tx = UtageSingleEntryXetGraft.BuildSibling(
            sourceArc,
            memberIndex: 0,
            pristineXet,
            candidate,
            mask,
            new DateTimeOffset(2026, 9, 12, 0, 0, 0, TimeSpan.Zero));

        True(sourceArc.AsSpan().SequenceEqual(sourceArcSnapshot), "source ARC remains byte-identical");
        True(tx.Audit.UsedPristineOverride, "audit records mandatory pristine base");
        True(!tx.Audit.TargetResourceSha256.Equals(tx.Audit.PristineBaseSha256, StringComparison.Ordinal), "audit proves ENG target and JPN base differ");
        True(tx.Audit.GraftOk && tx.Audit.ArcRoundTripVerified && tx.Audit.ApprovedEligible, "transaction fully verified");
        Equal(tx.Audit.SourceArcSha256, tx.ApprovalEvidence.SourceArcSha256, "evidence bound to source ARC hash");
        Equal(tx.Audit.OutputArcSha256, tx.ApprovalEvidence.OutputArcSha256, "evidence bound to output ARC hash");
        Equal(tx.Audit.MemberName, tx.ApprovalEvidence.MemberName, "evidence bound to member identity");
        True(tx.Audit.Notes.Any(n => n.Contains("domain approval guard accepted", StringComparison.Ordinal)), "audit eligibility was exercised through domain guard");

        True(typeof(AssetApprovalEvidence).GetConstructors().Length == 0, "approval evidence has no public constructor");
        True(!typeof(AssetApprovalEvidence)
            .GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static)
            .Any(m => m.ReturnType == typeof(AssetApprovalEvidence)), "approval evidence has no public minting factory");

        var review = AssetApprovalGuard.Promote(
            AssetApprovalState.Draft,
            AssetApprovalState.Review,
            evidence: null);
        Equal(AssetApprovalState.Review, review, "review allowed without production proof");

        Throws<InvalidOperationException>(
            () => AssetApprovalGuard.Promote(
                AssetApprovalState.Review,
                AssetApprovalState.Approved,
                null),
            "approval rejected without certified evidence");

        var approved = AssetApprovalGuard.Promote(
            AssetApprovalState.Review,
            AssetApprovalState.Approved,
            tx.ApprovalEvidence);
        Equal(AssetApprovalState.Approved, approved, "approval accepted with opaque bound graft+ARC proof");

        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-sibling-{Guid.NewGuid():N}");
        var engDir = Path.Combine(root, "canonical-eng");
        var jpnDir = Path.Combine(root, "canonical-jpn");
        var buildDir = Path.Combine(root, "foundry-build");
        var workDir = Path.Combine(root, "work");
        Directory.CreateDirectory(engDir);
        Directory.CreateDirectory(jpnDir);
        Directory.CreateDirectory(buildDir);
        Directory.CreateDirectory(workDir);
        try
        {
            var sourcePath = Path.Combine(engDir, "cockpit1P.arc");
            var pristinePath = Path.Combine(jpnDir, "cockpit1P.arc");
            var outputPath = Path.Combine(buildDir, "cockpit1P.foundry.arc");
            File.WriteAllBytes(sourcePath, sourceArc);
            File.WriteAllBytes(pristinePath, pristineArc);

            var written = UtageSiblingArcStore.Write(sourcePath, tx, outputPath);
            True(File.Exists(written.OutputArcPath), "external build ARC written");
            True(File.Exists(written.AuditJsonPath), "audit JSON written");
            True(!PathsEqual(written.SourceArcPath, written.OutputArcPath), "build path differs from source");
            Throws<InvalidOperationException>(
                () => UtageSiblingArcStore.Write(sourcePath, tx, sourcePath),
                "disk writer refuses source overwrite");
            Throws<InvalidOperationException>(
                () => UtageSiblingArcStore.Write(sourcePath, tx, Path.Combine(engDir, "cockpit1P.foundry.arc")),
                "disk writer refuses output beside canonical source");

            var candidatePath = Path.Combine(workDir, "candidate.rgba");
            var maskPath = Path.Combine(workDir, "mask.bin");
            File.WriteAllBytes(candidatePath, candidate);
            File.WriteAllBytes(maskPath, mask);

            var workerDll = FindWorkerDll();
            var workerOutput = Path.Combine(buildDir, "cockpit1P.worker.arc");
            var workerAudit = workerOutput + ".audit.json";
            var workerExit = RunWorker(
                workerDll,
                [
                    "graft-xet",
                    "--root", engDir,
                    "--archive", "cockpit1P.arc",
                    "--entry", "0",
                    "--name", "roulette_000_ID_HQ",
                    "--pristine-root", jpnDir,
                    "--pristine-archive", "cockpit1P.arc",
                    "--pristine-entry", "0",
                    "--pristine-name", "roulette_000_ID_HQ",
                    "--rgba", candidatePath,
                    "--mask", maskPath,
                    "--output-arc", workerOutput,
                    "--audit", workerAudit,
                ],
                out var workerStdout,
                out var workerStderr);
            Equal(0, workerExit, $"Worker production CLI succeeds ({workerStderr})");
            True(File.Exists(workerOutput) && File.Exists(workerAudit), "Worker created ARC + audit pair");
            True(sourceArc.AsSpan().SequenceEqual(File.ReadAllBytes(sourcePath)), "Worker left canonical ENG ARC byte-identical");
            True(pristineArc.AsSpan().SequenceEqual(File.ReadAllBytes(pristinePath)), "Worker left canonical JPN ARC byte-identical");
            True(workerStdout.Contains("\"approvedEligible\":true", StringComparison.OrdinalIgnoreCase), "Worker reports verified approval eligibility");

            var forbiddenOutput = Path.Combine(engDir, "forbidden.arc");
            var forbiddenExit = RunWorker(
                workerDll,
                [
                    "graft-xet",
                    "--root", engDir,
                    "--archive", "cockpit1P.arc",
                    "--entry", "0",
                    "--name", "roulette_000_ID_HQ",
                    "--pristine-root", jpnDir,
                    "--pristine-archive", "cockpit1P.arc",
                    "--pristine-entry", "0",
                    "--pristine-name", "roulette_000_ID_HQ",
                    "--rgba", candidatePath,
                    "--mask", maskPath,
                    "--output-arc", forbiddenOutput,
                    "--audit", forbiddenOutput + ".audit.json",
                ],
                out _,
                out var forbiddenError);
            Equal(2, forbiddenExit, "Worker rejects production output inside canonical ENG root");
            True(!File.Exists(forbiddenOutput), "forbidden Worker output was not created");
            True(forbiddenError.Contains("outside canonical ENG/JPN source roots", StringComparison.OrdinalIgnoreCase), "Worker explains canonical-root rejection");
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }

        Console.WriteLine("Graft smoke tests passed.");
        Console.WriteLine($"  blocks_replaced={result.Report.BlocksReplaced}/{result.Report.BlocksTotal}");
        Console.WriteLine($"  sibling_arc_sha256={tx.Audit.OutputArcSha256}");
        return 0;
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

        throw new FileNotFoundException("Could not locate the already-built BasaraFoundry.Worker.dll for CLI integration smoke.");
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
            ?? throw new IOException("Could not start Worker integration smoke process.");
        stdout = process.StandardOutput.ReadToEnd();
        stderr = process.StandardError.ReadToEnd();
        if (!process.WaitForExit(60_000))
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Worker integration smoke exceeded 60 seconds.");
        }
        return process.ExitCode;
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
        var built = UtageXetCodec.ReplaceSingleLevel(shell, rgba);
        return built.XetBytes;
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

    private static bool PathsEqual(string a, string b) =>
        string.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase);

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
