namespace BasaraFoundry.Domain;

/// <summary>
/// Safety evidence required before artwork can cross the approval boundary.
/// Domain stays format-agnostic; the production transaction must populate the
/// bound hashes. Guard rejects verified proofs that omit them or use an
/// unknown proof kind (closes the trivial forge path).
/// </summary>
public sealed record AssetApprovalEvidence(
    bool ProductionWriteVerified,
    string ProofKind,
    string? SourceArcSha256 = null,
    string? OutputArcSha256 = null,
    int? MemberIndex = null,
    IReadOnlyList<string>? Notes = null)
{
    public const string UtageBc3GraftArcProofKind =
        "utage-bc3-block-graft+single-entry-arc-roundtrip";

    /// <summary>
    /// Preferred factory for successful production transactions.
    /// </summary>
    public static AssetApprovalEvidence ForUtageBc3GraftArc(
        string sourceArcSha256,
        string outputArcSha256,
        int memberIndex,
        IReadOnlyList<string>? notes = null)
    {
        if (string.IsNullOrWhiteSpace(sourceArcSha256))
            throw new ArgumentException("Source ARC SHA-256 is required.", nameof(sourceArcSha256));
        if (string.IsNullOrWhiteSpace(outputArcSha256))
            throw new ArgumentException("Output ARC SHA-256 is required.", nameof(outputArcSha256));
        if (memberIndex < 0)
            throw new ArgumentOutOfRangeException(nameof(memberIndex));

        return new AssetApprovalEvidence(
            ProductionWriteVerified: true,
            ProofKind: UtageBc3GraftArcProofKind,
            SourceArcSha256: sourceArcSha256.Trim().ToLowerInvariant(),
            OutputArcSha256: outputArcSha256.Trim().ToLowerInvariant(),
            MemberIndex: memberIndex,
            Notes: notes);
    }
}

public static class AssetApprovalGuard
{
    private static readonly HashSet<string> AllowedProofKinds =
        new(StringComparer.Ordinal)
        {
            AssetApprovalEvidence.UtageBc3GraftArcProofKind,
        };

    /// <summary>
    /// Refuse promotion to Approved (or any later state) unless a certified,
    /// hash-bound production-write proof is present.
    /// </summary>
    public static void EnsureCanTransition(
        AssetApprovalState current,
        AssetApprovalState requested,
        AssetApprovalEvidence? evidence)
    {
        if (requested < current)
            throw new InvalidOperationException($"Approval state cannot move backwards from {current} to {requested}.");

        if (requested < AssetApprovalState.Approved)
            return;

        if (evidence is null || !evidence.ProductionWriteVerified)
        {
            throw new InvalidOperationException(
                $"Cannot promote asset to {requested}: certified production-write verification is missing or failed.");
        }

        if (string.IsNullOrWhiteSpace(evidence.ProofKind) || !AllowedProofKinds.Contains(evidence.ProofKind))
        {
            throw new InvalidOperationException(
                $"Cannot promote asset to {requested}: proof kind '{evidence.ProofKind}' is not a certified Foundry production proof.");
        }

        if (string.IsNullOrWhiteSpace(evidence.SourceArcSha256) ||
            string.IsNullOrWhiteSpace(evidence.OutputArcSha256) ||
            evidence.MemberIndex is null ||
            evidence.MemberIndex < 0)
        {
            throw new InvalidOperationException(
                $"Cannot promote asset to {requested}: production proof is not bound to source/output ARC hashes and member index.");
        }
    }

    public static AssetApprovalState Promote(
        AssetApprovalState current,
        AssetApprovalState requested,
        AssetApprovalEvidence? evidence)
    {
        EnsureCanTransition(current, requested, evidence);
        return requested;
    }
}
