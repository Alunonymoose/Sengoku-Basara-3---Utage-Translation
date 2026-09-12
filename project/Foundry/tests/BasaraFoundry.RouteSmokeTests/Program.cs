using BasaraFoundry.Game.Utage.Index;

namespace BasaraFoundry.RouteSmokeTests;

internal static class Program
{
    private static int Main()
    {
        var root = Path.Combine(Path.GetTempPath(), $"basara-foundry-routes-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            TestStandardGameRoot(root);
            TestExactRoute(root);
            TestDirectArcFallback(root);
            TestAmbiguousParent(root);
            TestMissingRoute(root);
            TestSelectedRootIndexIsolation(root);
            Console.WriteLine("Route resolution smoke tests passed.");
            return 0;
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    private static void TestStandardGameRoot(string sandbox)
    {
        var game = Path.Combine(sandbox, "game");
        var eng = Path.Combine(game, "PS3_GAME", "USRDIR", "nativePS3", "rom", "eng");
        var jpn = Path.Combine(game, "PS3_GAME", "USRDIR", "nativePS3", "rom", "jpn");
        MakeRoute(eng);
        MakeRoute(jpn);

        var resolvedEng = UtageRouteResolver.Resolve(game, UtageContentRoute.English);
        var resolvedJpn = UtageRouteResolver.Resolve(game, UtageContentRoute.Japanese);
        Equal(Path.GetFullPath(eng), resolvedEng.RouteRoot, "parent game root resolves English route only");
        Equal(Path.GetFullPath(jpn), resolvedJpn.RouteRoot, "parent game root resolves Japanese route only");
        True(!PathsEqual(resolvedEng.RouteRoot, resolvedJpn.RouteRoot), "English and Japanese routes remain distinct");
    }

    private static void TestExactRoute(string sandbox)
    {
        var route = Path.Combine(sandbox, "exact", "rom", "eng");
        MakeRoute(route);
        var resolved = UtageRouteResolver.Resolve(route, UtageContentRoute.English);
        Equal(Path.GetFullPath(route), resolved.RouteRoot, "exact rom/eng folder resolves to itself");
    }

    private static void TestDirectArcFallback(string sandbox)
    {
        var route = Path.Combine(sandbox, "custom-export");
        MakeRoute(route);
        var resolved = UtageRouteResolver.Resolve(route, UtageContentRoute.English);
        Equal(Path.GetFullPath(route), resolved.RouteRoot, "custom direct ARC export remains supported");
    }

    private static void TestAmbiguousParent(string sandbox)
    {
        var parent = Path.Combine(sandbox, "ambiguous");
        MakeRoute(Path.Combine(parent, "rom", "eng"));
        MakeRoute(Path.Combine(parent, "nativePS3", "rom", "eng"));
        Throws<InvalidDataException>(
            () => UtageRouteResolver.Resolve(parent, UtageContentRoute.English),
            "ambiguous parent with two plausible English routes is rejected");
    }

    private static void TestMissingRoute(string sandbox)
    {
        var empty = Path.Combine(sandbox, "empty");
        Directory.CreateDirectory(empty);
        Throws<InvalidDataException>(
            () => UtageRouteResolver.Resolve(empty, UtageContentRoute.English),
            "folder without a concrete ARC route is rejected");
    }

    private static void TestSelectedRootIndexIsolation(string sandbox)
    {
        var game = Path.Combine(sandbox, "indexed-game");
        var eng = Path.Combine(game, "PS3_GAME", "USRDIR", "nativePS3", "rom", "eng");
        var jpn = Path.Combine(game, "PS3_GAME", "USRDIR", "nativePS3", "rom", "jpn");
        Directory.CreateDirectory(eng);
        Directory.CreateDirectory(jpn);
        File.WriteAllBytes(Path.Combine(eng, "eng-only.arc"), [1, 2, 3]);
        File.WriteAllBytes(Path.Combine(jpn, "jpn-only.arc"), [4, 5, 6]);

        var engIndex = UtageAssetIndexer.IndexSelectedRoot(game, UtageContentRoute.English);
        var jpnIndex = UtageAssetIndexer.IndexSelectedRoot(game, UtageContentRoute.Japanese);
        Equal(Path.GetFullPath(game), engIndex.Root, "selected parent remains index identity root");
        Equal(1, engIndex.Issues.Count, "English route scan sees only one English ARC issue");
        True(engIndex.Issues[0].RelativePath.Contains($"{Path.DirectorySeparatorChar}eng{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase),
            "English route scan path stays under eng");
        True(!engIndex.Issues[0].RelativePath.Contains($"{Path.DirectorySeparatorChar}jpn{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase),
            "English route scan does not leak Japanese ARC tree");
        Equal(1, jpnIndex.Issues.Count, "Japanese route scan sees only one Japanese ARC issue");
        True(jpnIndex.Issues[0].RelativePath.Contains($"{Path.DirectorySeparatorChar}jpn{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase),
            "Japanese route scan path stays under jpn");
    }

    private static void MakeRoute(string path)
    {
        Directory.CreateDirectory(path);
        File.WriteAllBytes(Path.Combine(path, "basara.arc"), [0]);
    }

    private static bool PathsEqual(string left, string right) =>
        string.Equals(
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(left)),
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(right)),
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);

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

    private static void Throws<T>(Action action, string label) where T : Exception
    {
        try
        {
            action();
        }
        catch (T)
        {
            Console.WriteLine($"PASS {label}");
            return;
        }
        throw new Exception($"FAIL {label}: expected {typeof(T).Name}");
    }
}
