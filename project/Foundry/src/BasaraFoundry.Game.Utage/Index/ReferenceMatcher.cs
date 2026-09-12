namespace BasaraFoundry.Game.Utage.Index;

public enum ReferenceMatchConfidence
{
    Candidate = 1,
    Strong = 2,
    ExactLanguageVariant = 3,
}

public sealed record ReferenceMatch(
    IndexedUtageResource Resource,
    ReferenceMatchConfidence Confidence,
    int Score,
    string Why);

/// <summary>
/// Conservative cross-root resource matching for JPN/SH reference discovery.
/// It produces evidence-ranked candidates only. The caller may auto-select a
/// result only through TryResolveUniqueStrong; lower-confidence candidates are
/// deliberately left for operator review.
/// </summary>
public static class ReferenceMatcher
{
    public static IReadOnlyList<ReferenceMatch> FindCandidates(
        IndexedUtageResource source,
        UtageAssetIndex referenceIndex,
        int limit = 20)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(referenceIndex);
        if (limit <= 0)
            return [];

        var sourceResource = Normalize(source.ResourceName);
        var sourceResourceNeutral = LanguageNeutral(source.ResourceName);
        var sourceTail = Tail(source.ResourceName);
        var sourceArchive = Normalize(source.ArchivePath);
        var sourceArchiveNeutral = LanguageNeutral(source.ArchivePath);
        var sourceArchiveFile = Path.GetFileName(source.ArchivePath);

        var matches = new List<ReferenceMatch>();
        foreach (var candidate in referenceIndex.Resources)
        {
            if (candidate.TypeHash != source.TypeHash)
                continue;

            var candidateResource = Normalize(candidate.ResourceName);
            var candidateNeutral = LanguageNeutral(candidate.ResourceName);
            var candidateTail = Tail(candidate.ResourceName);
            var candidateArchive = Normalize(candidate.ArchivePath);
            var candidateArchiveNeutral = LanguageNeutral(candidate.ArchivePath);
            var candidateArchiveFile = Path.GetFileName(candidate.ArchivePath);

            ReferenceMatchConfidence? confidence = null;
            var score = 0;
            var reasons = new List<string>();

            if (sourceResourceNeutral == candidateNeutral &&
                sourceArchiveNeutral == candidateArchiveNeutral)
            {
                confidence = ReferenceMatchConfidence.ExactLanguageVariant;
                score += 1000;
                reasons.Add("language-neutral resource and archive paths match");
            }
            else
            {
                if (sourceResource == candidateResource)
                {
                    score += 450;
                    reasons.Add("exact resource path");
                }
                else if (sourceResourceNeutral == candidateNeutral)
                {
                    score += 400;
                    reasons.Add("language-neutral resource path");
                }
                else if (sourceTail == candidateTail)
                {
                    score += 250;
                    reasons.Add("exact resource tail");
                }
                else
                {
                    continue;
                }

                if (sourceArchive == candidateArchive)
                {
                    score += 400;
                    reasons.Add("exact archive path");
                }
                else if (sourceArchiveNeutral == candidateArchiveNeutral)
                {
                    score += 350;
                    reasons.Add("language-neutral archive path");
                }
                else if (sourceArchiveFile.Equals(candidateArchiveFile, StringComparison.OrdinalIgnoreCase))
                {
                    score += 250;
                    reasons.Add("same archive filename");
                }

                confidence = score >= 650
                    ? ReferenceMatchConfidence.Strong
                    : ReferenceMatchConfidence.Candidate;
            }

            matches.Add(new ReferenceMatch(candidate, confidence.Value, score, string.Join(" + ", reasons)));
        }

        return matches
            .OrderByDescending(match => match.Confidence)
            .ThenByDescending(match => match.Score)
            .ThenBy(match => match.Resource.ArchivePath, StringComparer.OrdinalIgnoreCase)
            .ThenBy(match => match.Resource.ResourceName, StringComparer.OrdinalIgnoreCase)
            .Take(limit)
            .ToArray();
    }

    public static ReferenceMatch? TryResolveUniqueStrong(
        IndexedUtageResource source,
        UtageAssetIndex referenceIndex)
    {
        var candidates = FindCandidates(source, referenceIndex, limit: 3);
        if (candidates.Count == 0 || candidates[0].Confidence < ReferenceMatchConfidence.Strong)
            return null;
        if (candidates.Count > 1 &&
            candidates[1].Confidence == candidates[0].Confidence &&
            candidates[1].Score == candidates[0].Score)
        {
            return null;
        }
        return candidates[0];
    }

    private static string Normalize(string value) =>
        value.Replace('/', '\\').Trim('\\').ToLowerInvariant();

    private static string Tail(string value)
    {
        var normalized = Normalize(value);
        var slash = normalized.LastIndexOf('\\');
        return slash < 0 ? normalized : normalized[(slash + 1)..];
    }

    private static string LanguageNeutral(string value)
    {
        var segments = Normalize(value).Split('\\', StringSplitOptions.RemoveEmptyEntries);
        for (var i = 0; i < segments.Length; i++)
        {
            if (segments[i] is "eng" or "jpn")
                segments[i] = "{lang}";
        }
        return string.Join('\\', segments);
    }
}
