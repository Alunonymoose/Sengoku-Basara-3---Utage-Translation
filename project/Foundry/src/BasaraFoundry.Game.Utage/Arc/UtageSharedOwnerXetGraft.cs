using System.Security.Cryptography;
using System.Text;
using BasaraFoundry.Game.Utage.Xet;

namespace BasaraFoundry.Game.Utage.Arc;

public sealed record SharedOwnerXetSource(
    string ArchivePath,
    int MemberIndex,
    byte[] SourceArcBytes);

public sealed record SharedOwnerXetGraftOutput(
    string ArchivePath,
    int MemberIndex,
    SingleEntryXetGraftResult Transaction);

public sealed record SharedOwnerXetGraftOwnerAudit(
    string ArchivePath,
    int MemberIndex,
    string SourceArcSha256,
    string OutputArcSha256,
    string TargetResourceSha256,
    string FinalResourceSha256,
    bool TargetShellPreserved,
    bool ArcRoundTripVerified,
    bool ApprovedEligible);

public sealed record SharedOwnerXetGraftGroupAudit(
    int Schema,
    DateTimeOffset CreatedAtUtc,
    string ResourceName,
    uint TypeHash,
    int OwnerCount,
    string CommonTargetResourceSha256,
    string PristineBaseSha256,
    string CandidateRgbaSha256,
    string EditMaskSha256,
    string FinalResourceSha256,
    string BuildSetSha256,
    bool SourceOwnersByteIdentical,
    bool AllOwnersVerified,
    IReadOnlyList<SharedOwnerXetGraftOwnerAudit> Owners,
    IReadOnlyList<string> Notes);

public sealed record SharedOwnerXetGraftSetResult(
    IReadOnlyList<SharedOwnerXetGraftOutput> Outputs,
    SharedOwnerXetGraftGroupAudit Audit);

/// <summary>
/// Certified v0.1 transaction for an internal XET identity owned by more than
/// one ARC. All target owners are validated before any caller writes output.
/// Automatic synchronization is intentionally limited to duplicate owners whose
/// current raw target XET bytes are identical; divergent duplicates require an
/// explicit dependency investigation rather than guessing that they should be
/// made the same.
/// </summary>
public static class UtageSharedOwnerXetGraft
{
    private const int AuditSchema = 1;

    public static SharedOwnerXetGraftSetResult BuildSet(
        IReadOnlyList<SharedOwnerXetSource> owners,
        string expectedResourceName,
        ReadOnlySpan<byte> pristineXet,
        ReadOnlySpan<byte> candidateRgba,
        ReadOnlySpan<byte> editMask01,
        DateTimeOffset? createdAtUtc = null)
    {
        ArgumentNullException.ThrowIfNull(owners);
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedResourceName);
        if (owners.Count < 2)
            throw new ArgumentException("Shared-owner transaction requires at least two target owners.", nameof(owners));
        if (pristineXet.IsEmpty)
            throw new ArgumentException("A pristine counterpart XET is mandatory for shared-owner production grafts.", nameof(pristineXet));

        var timestamp = createdAtUtc ?? DateTimeOffset.UtcNow;
        var ordered = owners
            .OrderBy(owner => NormalizeArchivePath(owner.ArchivePath), StringComparer.OrdinalIgnoreCase)
            .ThenBy(owner => owner.MemberIndex)
            .ToArray();

        if (ordered.Select(owner => $"{NormalizeArchivePath(owner.ArchivePath)}#{owner.MemberIndex}")
                   .Distinct(StringComparer.OrdinalIgnoreCase)
                   .Count() != ordered.Length)
        {
            throw new InvalidDataException("Shared-owner transaction contains duplicate ARC/member identities.");
        }

        var inspected = new List<(SharedOwnerXetSource Owner, byte[] TargetXet, string TargetHash)>();
        foreach (var owner in ordered)
        {
            if (string.IsNullOrWhiteSpace(owner.ArchivePath))
                throw new InvalidDataException("Shared-owner archive path is empty.");
            if (owner.MemberIndex < 0)
                throw new InvalidDataException("Shared-owner member index is negative.");
            if (owner.SourceArcBytes is null || owner.SourceArcBytes.Length == 0)
                throw new InvalidDataException($"Shared-owner source ARC '{owner.ArchivePath}' is empty.");

            using var stream = new MemoryStream(owner.SourceArcBytes, writable: false);
            var arc = UtageArcReader.Read(stream, owner.ArchivePath);
            if ((uint)owner.MemberIndex >= (uint)arc.Entries.Count)
                throw new InvalidDataException($"Shared owner '{owner.ArchivePath}' no longer contains member index {owner.MemberIndex}.");

            var entry = arc.Entries[owner.MemberIndex];
            if (!entry.Name.Equals(expectedResourceName, StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"Shared owner '{owner.ArchivePath}' member {owner.MemberIndex} is '{entry.Name}', expected '{expectedResourceName}'.");
            }
            if (entry.TypeHash != UtageTypeHashes.Texture)
                throw new InvalidDataException($"Shared owner '{owner.ArchivePath}' member is not a texture resource.");

            stream.Position = 0;
            var targetXet = UtageArcReader.ReadDecompressedPayload(stream, entry);
            // Parse now so malformed target bytes fail before any owner transaction is built.
            _ = UtageXetReader.ReadInfo(targetXet);
            inspected.Add((owner, targetXet, Sha256(targetXet)));
        }

        var commonTargetHash = inspected[0].TargetHash;
        var divergent = inspected
            .Where(item => !item.TargetHash.Equals(commonTargetHash, StringComparison.Ordinal))
            .Select(item => $"{item.Owner.ArchivePath}#{item.Owner.MemberIndex}={item.TargetHash}")
            .ToArray();
        if (divergent.Length > 0)
        {
            var baseline = $"{inspected[0].Owner.ArchivePath}#{inspected[0].Owner.MemberIndex}={commonTargetHash}";
            throw new InvalidOperationException(
                "Shared resource owners have divergent raw target XET payloads. Foundry will not synchronize divergent duplicates automatically. " +
                $"Baseline {baseline}; divergent {string.Join(", ", divergent)}");
        }

        var outputs = new List<SharedOwnerXetGraftOutput>(inspected.Count);
        foreach (var item in inspected)
        {
            var transaction = UtageSingleEntryXetGraft.BuildSibling(
                item.Owner.SourceArcBytes,
                item.Owner.MemberIndex,
                pristineXet,
                candidateRgba,
                editMask01,
                timestamp);
            if (!transaction.Audit.MemberName.Equals(expectedResourceName, StringComparison.Ordinal) ||
                !transaction.Audit.TargetResourceSha256.Equals(commonTargetHash, StringComparison.Ordinal) ||
                !transaction.Audit.TargetShellPreserved ||
                !transaction.Audit.ArcRoundTripVerified ||
                !transaction.Audit.ApprovedEligible ||
                transaction.Audit.OutsideEffectiveBlockPixelDelta != 0)
            {
                throw new InvalidDataException($"Shared-owner output for '{item.Owner.ArchivePath}' did not satisfy the certified production invariants.");
            }
            outputs.Add(new SharedOwnerXetGraftOutput(item.Owner.ArchivePath, item.Owner.MemberIndex, transaction));
        }

        var first = outputs[0].Transaction.Audit;
        if (outputs.Any(output =>
                !output.Transaction.Audit.PristineBaseSha256.Equals(first.PristineBaseSha256, StringComparison.Ordinal) ||
                !output.Transaction.Audit.CandidateRgbaSha256.Equals(first.CandidateRgbaSha256, StringComparison.Ordinal) ||
                !output.Transaction.Audit.EditMaskSha256.Equals(first.EditMaskSha256, StringComparison.Ordinal) ||
                !output.Transaction.Audit.FinalResourceSha256.Equals(first.FinalResourceSha256, StringComparison.Ordinal)))
        {
            throw new InvalidDataException("Shared-owner outputs do not agree on pristine/candidate/mask/final-resource hashes.");
        }

        var ownerAudits = outputs.Select(output => new SharedOwnerXetGraftOwnerAudit(
            ArchivePath: output.ArchivePath,
            MemberIndex: output.MemberIndex,
            SourceArcSha256: output.Transaction.Audit.SourceArcSha256,
            OutputArcSha256: output.Transaction.Audit.OutputArcSha256,
            TargetResourceSha256: output.Transaction.Audit.TargetResourceSha256,
            FinalResourceSha256: output.Transaction.Audit.FinalResourceSha256,
            TargetShellPreserved: output.Transaction.Audit.TargetShellPreserved,
            ArcRoundTripVerified: output.Transaction.Audit.ArcRoundTripVerified,
            ApprovedEligible: output.Transaction.Audit.ApprovedEligible)).ToArray();

        var buildSetHash = ComputeBuildSetHash(
            expectedResourceName,
            first.PristineBaseSha256,
            first.CandidateRgbaSha256,
            first.EditMaskSha256,
            ownerAudits);
        var notes = new[]
        {
            "all exact owners validated before filesystem promotion",
            "v0.1 shared-owner synchronization requires byte-identical raw target XET payloads across owners",
            "divergent duplicate payloads fail closed for dependency investigation",
            "each ARC is rebuilt from its own source container; only the certified texture member is replaced",
            "each final XET preserves the common target shell and uses the same pristine/candidate/mask transaction",
            "group build hash binds the complete sorted owner/output set",
        };
        var audit = new SharedOwnerXetGraftGroupAudit(
            Schema: AuditSchema,
            CreatedAtUtc: timestamp,
            ResourceName: expectedResourceName,
            TypeHash: UtageTypeHashes.Texture,
            OwnerCount: outputs.Count,
            CommonTargetResourceSha256: commonTargetHash,
            PristineBaseSha256: first.PristineBaseSha256,
            CandidateRgbaSha256: first.CandidateRgbaSha256,
            EditMaskSha256: first.EditMaskSha256,
            FinalResourceSha256: first.FinalResourceSha256,
            BuildSetSha256: buildSetHash,
            SourceOwnersByteIdentical: true,
            AllOwnersVerified: ownerAudits.All(owner => owner.TargetShellPreserved && owner.ArcRoundTripVerified && owner.ApprovedEligible),
            Owners: ownerAudits,
            Notes: notes);

        if (!audit.AllOwnersVerified)
            throw new InvalidDataException("Shared-owner group audit did not verify every owner.");
        return new SharedOwnerXetGraftSetResult(outputs, audit);
    }

    private static string ComputeBuildSetHash(
        string resourceName,
        string pristineHash,
        string candidateHash,
        string maskHash,
        IReadOnlyList<SharedOwnerXetGraftOwnerAudit> owners)
    {
        var builder = new StringBuilder();
        builder.Append("shared-owner-xet-v1\n")
            .Append(resourceName).Append('\n')
            .Append(pristineHash).Append('\n')
            .Append(candidateHash).Append('\n')
            .Append(maskHash).Append('\n');
        foreach (var owner in owners.OrderBy(owner => NormalizeArchivePath(owner.ArchivePath), StringComparer.OrdinalIgnoreCase)
                                    .ThenBy(owner => owner.MemberIndex))
        {
            builder.Append(NormalizeArchivePath(owner.ArchivePath)).Append('#').Append(owner.MemberIndex).Append('|')
                .Append(owner.SourceArcSha256).Append('|')
                .Append(owner.OutputArcSha256).Append('|')
                .Append(owner.FinalResourceSha256).Append('\n');
        }
        return Sha256(Encoding.UTF8.GetBytes(builder.ToString()));
    }

    private static string NormalizeArchivePath(string value) => value.Replace('\\', '/');
    private static string Sha256(ReadOnlySpan<byte> bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}
