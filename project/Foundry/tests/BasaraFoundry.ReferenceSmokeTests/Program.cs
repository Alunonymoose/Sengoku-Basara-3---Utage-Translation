using BasaraFoundry.Game.Utage.Index;

namespace BasaraFoundry.ReferenceSmokeTests;

internal static class Program
{
    private static int Main()
    {
        var source = Resource(
            @"nativePS3\rom\eng\id\cockpit1P.arc",
            @"id\texture\jpn\roulette\roulette_000_ID_HQ");

        var japanese = Resource(
            @"nativePS3\rom\jpn\id\cockpit1P.arc",
            @"id\texture\jpn\roulette\roulette_000_ID_HQ");
        var japaneseIndex = Index(japanese);
        var jpnMatch = ReferenceMatcher.TryResolveUniqueStrong(source, japaneseIndex)
            ?? throw new Exception("FAIL pristine JPN counterpart should resolve uniquely");
        Equal(ReferenceMatchConfidence.ExactLanguageVariant, jpnMatch.Confidence, "JPN language-variant confidence");
        Equal(japanese.ResourceName, jpnMatch.Resource.ResourceName, "JPN counterpart resource");

        var heroes = Resource(
            @"nativePS3\rom\eng\id\cockpit1P.arc",
            @"id\texture\eng\roulette\roulette_000_ID_HQ");
        var heroesIndex = Index(heroes);
        var shMatch = ReferenceMatcher.TryResolveUniqueStrong(source, heroesIndex)
            ?? throw new Exception("FAIL Samurai Heroes counterpart should resolve uniquely");
        True(shMatch.Confidence >= ReferenceMatchConfidence.Strong, "SH language-neutral resource evidence is strong");

        var unrelated = Resource(
            @"nativePS3\rom\eng\gallery\gallery.arc",
            @"id\texture\eng\roulette\roulette_000_ID_HQ");
        var unrelatedIndex = Index(unrelated);
        True(ReferenceMatcher.TryResolveUniqueStrong(source, unrelatedIndex) is null,
            "resource-tail match in unrelated archive is not auto-selected");

        var duplicateA = Resource(@"a\cockpit1P.arc", @"id\texture\eng\roulette\roulette_000_ID_HQ");
        var duplicateB = Resource(@"b\cockpit1P.arc", @"id\texture\eng\roulette\roulette_000_ID_HQ");
        var ambiguousIndex = Index(duplicateA, duplicateB);
        True(ReferenceMatcher.TryResolveUniqueStrong(source, ambiguousIndex) is null,
            "equal strong candidates remain ambiguous for operator review");

        Console.WriteLine("Reference matching smoke tests passed.");
        return 0;
    }

    private static IndexedUtageResource Resource(string archive, string resource) => new(
        ArchivePath: archive,
        EntryIndex: 0,
        ResourceName: resource,
        TypeHash: 0x241F5DEB,
        TypeLabel: "texture",
        RawSize: 1024,
        StoredSize: 512);

    private static UtageAssetIndex Index(params IndexedUtageResource[] resources)
    {
        var archives = resources
            .GroupBy(resource => resource.ArchivePath, StringComparer.OrdinalIgnoreCase)
            .Select(group => new IndexedUtageArchive(group.Key, 8, group.ToArray()))
            .ToArray();
        return new UtageAssetIndex(@"C:\reference", archives, []);
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
