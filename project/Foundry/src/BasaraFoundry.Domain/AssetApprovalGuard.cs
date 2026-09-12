namespace BasaraFoundry.Domain;

/// <summary>
/// Opaque safety evidence created only by a certified production writer.
/// The constructor is internal; the Domain assembly grants friendship only to
/// the certified Utage format assembly. UI/worker callers can inspect evidence
/// but cannot construct a successful token through the normal API surface.
/// </summary>
public sealed class AssetApprovalEvidence
{
    public const string UtageBc3GraftArcProofKind =
        "utage-bc3-block-graft+single-entry-arc-roundtrip:v1";

    internal AssetApprovalEvidence(
        bool productionWriteVerified,
        string proofKind,
        string sourceArcSha256,
        string outputArcSha256,
        int memberIndex,
        string memberName,
        IReadOnlyList<string>? notes = null)
    {
        ProductionWriteVerified = productionWriteVerified;
        ProofKind = proofKind;
        SourceArcSha256 = sourceArcSha256;
        OutputArcSha256 = outputArcSha256;
        MemberIndex = memberIndex;
        MemberName = memberName;
        Notes = notes ?? Array.Empty<string>();
    }

    public bool ProductionWriteVerified { get; }
    public string ProofKind { get; }
    public string SourceArcSha256 { get; }
    public string OutputArcSha256 { get; }
    public int MemberIndex { get; }
    public string MemberName { get; }
    public IReadOnlyList<string> Notes { get; }
}

public static class AssetApprovalGuard
{
    /// <summary>
    /// Refuse promotion to Approved (or any later state) unless a recognized,
    /// structurally valid certified production-write proof succeeded.
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

        if (!string.Equals(
                evidence.ProofKind,
                AssetApprovalEvidence.UtageBc3GraftArcProofKind,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"Cannot promote asset to {requested}: proof kind '{evidence.ProofKind}' is not a certified Foundry production proof.");
        }

        if (!IsSha256(evidence.SourceArcSha256) || !IsSha256(evidence.OutputArcSha256))
        {
            throw new InvalidOperationException(
                $"Cannot promote asset to {requested}: production proof is not bound to valid source/output ARC SHA-256 fingerprints.");
        }

        if (evidence.MemberIndex < 0 || string.IsNullOrWhiteSpace(evidence.MemberName))
        {
            throw new InvalidOperationException(
                $"Cannot promote asset to {requested}: production proof is not bound to a valid ARC member identity.");
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

    private static bool IsSha256(string value)
    {
        if (value.Length != 64)
            return false;
        foreach (var c in value)
        {
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')))
                return false;
        }
        return true;
    }
}
