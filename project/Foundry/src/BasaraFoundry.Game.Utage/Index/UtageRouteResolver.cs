namespace BasaraFoundry.Game.Utage.Index;

public enum UtageContentRoute
{
    English = 0,
    Japanese = 1,
}

public sealed record ResolvedUtageRoute(
    string SelectedRoot,
    string RouteRoot,
    UtageContentRoute Route,
    string Resolution);

/// <summary>
/// Resolves a user-selected Utage/SH folder to one concrete rom/eng or rom/jpn
/// asset route. A parent game folder is accepted, but ambiguous layouts are
/// rejected instead of recursively mixing unrelated ARC trees.
/// </summary>
public static class UtageRouteResolver
{
    public static ResolvedUtageRoute Resolve(string selectedRoot, UtageContentRoute route)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(selectedRoot);
        var selected = Path.TrimEndingDirectorySeparator(Path.GetFullPath(selectedRoot));
        if (!Directory.Exists(selected))
            throw new DirectoryNotFoundException(selected);

        var leaf = route == UtageContentRoute.English ? "eng" : "jpn";
        var relativeCandidates = new[]
        {
            leaf,
            Path.Combine("rom", leaf),
            Path.Combine("nativePS3", "rom", leaf),
            Path.Combine("USRDIR", "nativePS3", "rom", leaf),
            Path.Combine("PS3_GAME", "USRDIR", "nativePS3", "rom", leaf),
        };

        var comparer = OperatingSystem.IsWindows()
            ? StringComparer.OrdinalIgnoreCase
            : StringComparer.Ordinal;
        var known = relativeCandidates
            .Select(relative => Path.TrimEndingDirectorySeparator(Path.GetFullPath(Path.Combine(selected, relative))))
            .Where(LooksLikeArcRoute)
            .Distinct(comparer)
            .ToArray();

        if (known.Length > 1)
        {
            throw new InvalidDataException(
                $"Selected folder contains multiple plausible {leaf} ARC routes. Choose the exact intended rom/{leaf} folder instead: " +
                string.Join(" | ", known));
        }

        if (known.Length == 1)
        {
            return new ResolvedUtageRoute(
                SelectedRoot: selected,
                RouteRoot: known[0],
                Route: route,
                Resolution: $"resolved descendant rom/{leaf}");
        }

        if (LooksLikeArcRoute(selected))
        {
            return new ResolvedUtageRoute(
                SelectedRoot: selected,
                RouteRoot: selected,
                Route: route,
                Resolution: "selected folder is the ARC route");
        }

        throw new InvalidDataException(
            $"Could not resolve one {leaf} ARC route below '{selected}'. Choose the exact rom/{leaf} folder or a parent containing one standard nativePS3 route.");
    }

    private static bool LooksLikeArcRoute(string path)
    {
        if (!Directory.Exists(path))
            return false;
        try
        {
            return Directory.EnumerateFiles(path, "*.arc", SearchOption.TopDirectoryOnly).Any();
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
        catch (IOException)
        {
            return false;
        }
    }
}
