using System.Security.Cryptography;
using System.Text;

namespace BasaraFoundry.Game.Utage.Arc;

/// <summary>
/// Recomputes the schema-1 owner-set binding from a persisted group audit.
/// Consumers must not trust BuildSetSha256 merely because it is 64 hex chars;
/// it must be derived again from the complete sorted owner/output set.
/// </summary>
public static class UtageSharedOwnerAuditVerifier
{
    public static void EnsureValid(SharedOwnerXetGraftGroupAudit audit)
    {
        ArgumentNullException.ThrowIfNull(audit);
        if (audit.Schema != 1)
            throw new NotSupportedException($"Unsupported shared-owner audit schema {audit.Schema}.");
        if (string.IsNullOrWhiteSpace(audit.ResourceName) || audit.TypeHash != UtageTypeHashes.Texture)
            throw new InvalidDataException("Shared-owner audit resource identity is invalid.");
        if (audit.OwnerCount < 2 || audit.Owners.Count != audit.OwnerCount)
            throw new InvalidDataException("Shared-owner audit owner count is invalid.");
        if (!audit.SourceOwnersByteIdentical || !audit.AllOwnersVerified)
            throw new InvalidDataException("Shared-owner audit does not certify an identical-source, fully verified owner set.");

        foreach (var hash in new[]
        {
            audit.CommonTargetResourceSha256,
            audit.PristineBaseSha256,
            audit.CandidateRgbaSha256,
            audit.EditMaskSha256,
            audit.FinalResourceSha256,
            audit.BuildSetSha256,
        })
        {
            RequireSha256(hash);
        }

        var identities = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var owner in audit.Owners)
        {
            if (string.IsNullOrWhiteSpace(owner.ArchivePath) || owner.MemberIndex < 0)
                throw new InvalidDataException("Shared-owner audit contains an invalid owner identity.");
            if (!identities.Add($"{Normalize(owner.ArchivePath)}#{owner.MemberIndex}"))
                throw new InvalidDataException("Shared-owner audit contains duplicate owner identities.");
            foreach (var hash in new[]
            {
                owner.SourceArcSha256,
                owner.OutputArcSha256,
                owner.TargetResourceSha256,
                owner.FinalResourceSha256,
            })
            {
                RequireSha256(hash);
            }
            if (!owner.TargetResourceSha256.Equals(audit.CommonTargetResourceSha256, StringComparison.Ordinal) ||
                !owner.FinalResourceSha256.Equals(audit.FinalResourceSha256, StringComparison.Ordinal) ||
                !owner.TargetShellPreserved || !owner.ArcRoundTripVerified || !owner.ApprovedEligible)
            {
                throw new InvalidDataException($"Shared-owner audit owner '{owner.ArchivePath}' is not bound to the certified common target/final resource state.");
            }
        }

        var expected = ComputeBuildSetSha256(audit);
        if (!expected.Equals(audit.BuildSetSha256, StringComparison.Ordinal))
            throw new InvalidDataException("Shared-owner BuildSetSha256 does not match the recomputed complete owner/output binding.");
    }

    public static string ComputeBuildSetSha256(SharedOwnerXetGraftGroupAudit audit)
    {
        ArgumentNullException.ThrowIfNull(audit);
        var builder = new StringBuilder();
        builder.Append("shared-owner-xet-v1\n")
            .Append(audit.ResourceName).Append('\n')
            .Append(audit.PristineBaseSha256).Append('\n')
            .Append(audit.CandidateRgbaSha256).Append('\n')
            .Append(audit.EditMaskSha256).Append('\n');
        foreach (var owner in audit.Owners
                     .OrderBy(owner => Normalize(owner.ArchivePath), StringComparer.OrdinalIgnoreCase)
                     .ThenBy(owner => owner.MemberIndex))
        {
            builder.Append(Normalize(owner.ArchivePath)).Append('#').Append(owner.MemberIndex).Append('|')
                .Append(owner.SourceArcSha256).Append('|')
                .Append(owner.OutputArcSha256).Append('|')
                .Append(owner.FinalResourceSha256).Append('\n');
        }
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(builder.ToString()))).ToLowerInvariant();
    }

    private static string Normalize(string path) => path.Replace('\\', '/');

    private static void RequireSha256(string value)
    {
        if (value is null || value.Length != 64 || value.Any(c => !Uri.IsHexDigit(c)))
            throw new InvalidDataException("Shared-owner audit contains an invalid SHA-256 binding.");
    }
}
