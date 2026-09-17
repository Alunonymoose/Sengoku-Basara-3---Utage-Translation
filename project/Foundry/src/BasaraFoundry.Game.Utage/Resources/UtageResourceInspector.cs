using System.Buffers.Binary;
using System.Text;

namespace BasaraFoundry.Game.Utage.Resources;

public enum UtageResourceCapability
{
    Unknown = 0,
    IdentifyOnly,
    Read,
    ReadAndPreview,
    ReadAndWriteGuarded,
}

public sealed record UtageResourceDescriptor(
    string Kind,
    string SuggestedExtension,
    uint DeclaredTypeHash,
    string Magic,
    UtageResourceCapability Capability,
    string Notes);

/// <summary>
/// Central, fail-closed classifier for decompressed ARC members.
/// Type hashes are evidence, but content magic wins for format identification.
/// Unknown resources remain visible and hash-addressable instead of disappearing.
/// </summary>
public static class UtageResourceInspector
{
    private static readonly IReadOnlyDictionary<uint, (string Kind, string Ext, UtageResourceCapability Capability, string Notes)> TypeMap =
        new Dictionary<uint, (string, string, UtageResourceCapability, string)>
        {
            [UtageTypeHashes.Texture] = ("XET texture", ".xet", UtageResourceCapability.ReadAndWriteGuarded, "Guarded writer exists only for certified XET shapes."),
            [UtageTypeHashes.Message] = ("GSM message strings", ".gsm", UtageResourceCapability.Read, "Preserve row/control structure against pristine Utage."),
            [UtageTypeHashes.Mif] = ("FIM/MIF message format", ".fim", UtageResourceCapability.Read, "Format/control metadata; writer remains gated."),
            [UtageTypeHashes.Asc] = ("CSA/ASC character set", ".csa", UtageResourceCapability.Read, "Character-set sidecar; semantics remain partially decoded."),
            [UtageTypeHashes.Font] = ("TNF font map", ".tnf", UtageResourceCapability.Read, "Glyph map/metrics; writing remains gated by atlas mapping proof."),
            [UtageTypeHashes.Layout] = ("PSL/LSP layout", ".lsp", UtageResourceCapability.Read, "Generic geometry writer is not certified; fixture-specific writes only."),
        };

    public static UtageResourceDescriptor Describe(ReadOnlySpan<byte> raw, uint declaredTypeHash)
    {
        var magic = Magic(raw);
        var byMagic = magic switch
        {
            "\0XET" => new UtageResourceDescriptor("XET texture", ".xet", declaredTypeHash, magic, UtageResourceCapability.ReadAndWriteGuarded, "Texture container. Preserve target shell and unsupported mip/swizzle forms fail closed."),
            "\0PSL" => new UtageResourceDescriptor("PSL/LSP layout", ".lsp", declaredTypeHash, magic, UtageResourceCapability.Read, "Layout/controller resource. Known fixtures may have stronger evidence than the generic reader."),
            "\0TNF" => new UtageResourceDescriptor("TNF font map", ".tnf", declaredTypeHash, magic, UtageResourceCapability.Read, "Font glyph map/metrics."),
            "\0GSM" => new UtageResourceDescriptor("GSM message strings", ".gsm", declaredTypeHash, magic, UtageResourceCapability.Read, "Message row table and encoded glyph/control units."),
            "\0FIM" => new UtageResourceDescriptor("FIM message formats", ".fim", declaredTypeHash, magic, UtageResourceCapability.Read, "Per-message mapping and display-format records."),
            "\0CSA" => new UtageResourceDescriptor("CSA character set", ".csa", declaredTypeHash, magic, UtageResourceCapability.Read, "Character-set sidecar."),
            _ => null,
        };
        if (byMagic is not null)
            return byMagic;

        if (TypeMap.TryGetValue(declaredTypeHash, out var typed))
            return new UtageResourceDescriptor(typed.Kind, typed.Ext, declaredTypeHash, magic, typed.Capability, typed.Notes + " Content magic was not recognized; do not write automatically.");

        return new UtageResourceDescriptor(
            $"Unknown 0x{declaredTypeHash:X8}",
            ".bin",
            declaredTypeHash,
            magic,
            UtageResourceCapability.IdentifyOnly,
            "Unclassified resource. Preserve byte-for-byte, expose hex/string views, and promote only after fixture-backed reverse engineering.");
    }

    public static string Magic(ReadOnlySpan<byte> raw)
    {
        if (raw.Length < 4)
            return raw.Length == 0 ? "<empty>" : Convert.ToHexString(raw);
        if (raw[0] == 0 && raw[1] is >= 0x20 and <= 0x7E && raw[2] is >= 0x20 and <= 0x7E && raw[3] is >= 0x20 and <= 0x7E)
            return "\\0" + Encoding.ASCII.GetString(raw[1..4]);
        return "0x" + BinaryPrimitives.ReadUInt32BigEndian(raw[..4]).ToString("X8");
    }
}