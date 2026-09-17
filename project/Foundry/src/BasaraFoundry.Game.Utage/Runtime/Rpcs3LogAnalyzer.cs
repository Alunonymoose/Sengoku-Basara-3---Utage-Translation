using System.Text.RegularExpressions;

namespace BasaraFoundry.Game.Utage.Runtime;

public sealed record Rpcs3FileOpen(string Path, bool Completed, int LineNumber, string RawLine);
public sealed record Rpcs3VfsMount(string VirtualPath, string HostPath, int LineNumber);
public sealed record Rpcs3RuntimeTrace(
    IReadOnlyList<Rpcs3FileOpen> FileOpens,
    IReadOnlyList<Rpcs3VfsMount> Mounts,
    IReadOnlyDictionary<string, int> OpenCounts)
{
    public IReadOnlyList<Rpcs3FileOpen> OpensContaining(string fragment) => FileOpens
        .Where(item => item.Path.Contains(fragment, StringComparison.OrdinalIgnoreCase))
        .ToArray();
}

/// <summary>
/// Parses an RPCS3.log into asset-loading evidence. This is deliberately an
/// offline log reader: it does not modify RPCS3 settings or claim a resource is
/// runtime-owned merely because it exists on disk.
/// </summary>
public static partial class Rpcs3LogAnalyzer
{
    [GeneratedRegex("VFS: Mounted path \\\"(?<virtual>[^\\\"]+)\\\" to \\\"(?<host>[^\\\"]+)\\\"")]
    private static partial Regex MountRegex();

    // RPCS3 has emitted both typographic and ASCII quotes in logs over time.
    [GeneratedRegex("sys_fs_open\\(path=[“\\\"](?<path>[^”\\\"]+)[”\\\"]", RegexOptions.CultureInvariant)]
    private static partial Regex OpenAttemptRegex();

    [GeneratedRegex("sys_fs_open\\(\\): fd=\\d+.*?'(?<path>/[^']+)'", RegexOptions.CultureInvariant)]
    private static partial Regex OpenCompleteRegex();

    public static Rpcs3RuntimeTrace Parse(IEnumerable<string> lines)
    {
        var opens = new List<Rpcs3FileOpen>();
        var mounts = new List<Rpcs3VfsMount>();
        var lineNumber = 0;

        foreach (var line in lines)
        {
            lineNumber++;
            var mount = MountRegex().Match(line);
            if (mount.Success)
                mounts.Add(new Rpcs3VfsMount(mount.Groups["virtual"].Value, mount.Groups["host"].Value, lineNumber));

            var complete = OpenCompleteRegex().Match(line);
            if (complete.Success)
            {
                opens.Add(new Rpcs3FileOpen(Normalize(complete.Groups["path"].Value), true, lineNumber, line));
                continue;
            }

            var attempt = OpenAttemptRegex().Match(line);
            if (attempt.Success)
                opens.Add(new Rpcs3FileOpen(Normalize(attempt.Groups["path"].Value), false, lineNumber, line));
        }

        var counts = opens
            .Where(item => item.Completed)
            .GroupBy(item => item.Path, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.OrdinalIgnoreCase);

        return new Rpcs3RuntimeTrace(opens, mounts, counts);
    }

    public static Rpcs3RuntimeTrace ParseFile(string path) => Parse(File.ReadLines(path));

    public static string? ToUtageRelativePath(string rpcs3Path)
    {
        const string marker = "/PS3_GAME/USRDIR/nativePS3/";
        var normalized = Normalize(rpcs3Path);
        var index = normalized.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
        return index < 0 ? null : normalized[(index + marker.Length)..];
    }

    private static string Normalize(string value) => value.Replace('\\', '/');
}