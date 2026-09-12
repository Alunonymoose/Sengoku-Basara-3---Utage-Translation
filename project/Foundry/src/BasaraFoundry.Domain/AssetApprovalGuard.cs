namespace BasaraFoundry.Domain;

/// <summary>
/// Safety evidence that must exist before artwork can cross the approval boundary.
/// Domain code deliberately does not depend on a game-format implementation; the
/// caller supplies the result of the certified production writer/verification path.
/// </summary>
public sealed record AssetApprovalEvidence(
    bool ProductionWriteVerified,
    string ProofKind,
    IReadOnlyList<string>? Notes = null);

public static class AssetApprovalGuard
{
    /// <summary>
    /// Refuse promotion to Approved (or any later state) unless a certified
    /// production-write proof succeeded. For Utage BC3 texture work this value
    /// must come directly from Bc3GraftReport.Ok after the sibling ARC verifies.
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

        if (string.IsNullOrWhiteSpace(evidence.ProofKind))
            throw new InvalidOperationException("Approval proof must identify its production verification kind.");
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
