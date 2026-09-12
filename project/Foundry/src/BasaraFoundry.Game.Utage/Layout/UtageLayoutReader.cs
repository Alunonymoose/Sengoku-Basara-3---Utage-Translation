using System.Buffers.Binary;
using System.Text;
using System.Text.RegularExpressions;

namespace BasaraFoundry.Game.Utage.Layout;

public sealed record UtageLayoutNode(string Name, string Texture, string Role);

public sealed record UtageLayoutInfo(
    string Name,
    uint Version,
    int DeclaredNodeCount,
    int DeclaredTextureCount,
    IReadOnlyList<UtageLayoutNode> Nodes,
    IReadOnlyList<string> Textures)
{
    public bool InventoryComplete => Nodes.Count >= DeclaredNodeCount;

    public IReadOnlyList<UtageLayoutNode> NodesUsing(string textureName)
    {
        var tail = Normalize(textureName).Split('\\').Last();
        return Nodes
            .Where(node => !string.IsNullOrEmpty(node.Texture) &&
                           Normalize(node.Texture).EndsWith(tail, StringComparison.OrdinalIgnoreCase))
            .ToArray();
    }

    private static string Normalize(string value) => value.Replace('/', '\\');
}

/// <summary>
/// Conservative read-only inventory parser for Utage PSL/LSP resources.
///
/// This intentionally does NOT decode node rectangles, placement, animation,
/// or geometry. It only recovers the names and texture references already
/// proven reliable in Alrummi, so Foundry can establish dependency evidence
/// without claiming a layout preview it cannot yet reproduce.
/// </summary>
public static partial class UtageLayoutReader
{
    private static ReadOnlySpan<byte> Magic => [0x00, 0x50, 0x53, 0x4C]; // \0PSL

    [GeneratedRegex(@"^(?:[A-Za-z][A-Za-z0-9_]*|[0-9]+_[0-9]+)$", RegexOptions.CultureInvariant)]
    private static partial Regex IdentifierRegex();

    public static bool IsLayout(ReadOnlySpan<byte> raw) => raw.Length >= 4 && raw[..4].SequenceEqual(Magic);

    public static UtageLayoutInfo ReadInventory(ReadOnlySpan<byte> raw, string name = "")
    {
        if (raw.Length < 16)
            throw new InvalidDataException("PSL resource is shorter than its 16-byte header.");
        if (!IsLayout(raw))
            throw new InvalidDataException("Resource is not a PSL layout.");

        var version = BinaryPrimitives.ReadUInt32BigEndian(raw.Slice(4, 4));
        var nodeCount = BinaryPrimitives.ReadUInt16BigEndian(raw.Slice(12, 2));
        var textureCount = BinaryPrimitives.ReadUInt16BigEndian(raw.Slice(14, 2));

        var nodes = new List<UtageLayoutNode>();
        var textures = new List<string>();
        var seenNodes = new HashSet<(string Name, string Texture)>();
        string? pending = null;

        void Flush(string texture = "")
        {
            if (pending is null)
                return;
            var key = (pending, texture);
            if (seenNodes.Add(key))
                nodes.Add(new UtageLayoutNode(pending, texture, DescribeRole(pending)));
            pending = null;
        }

        foreach (var text in PrintableRuns(raw[16..]))
        {
            var reference = text.TrimStart('+');
            if (ContainsTexturePath(reference))
            {
                if (!textures.Contains(reference, StringComparer.OrdinalIgnoreCase))
                    textures.Add(reference);
                Flush(reference);
                continue;
            }

            if (text.Length <= 40 && IdentifierRegex().IsMatch(text))
            {
                Flush();
                pending = text;
            }
        }
        Flush();

        // A name may appear once in the hierarchy and again as an animation
        // target immediately associated with a texture. Keep the richer row.
        var namesWithTexture = nodes
            .Where(node => !string.IsNullOrEmpty(node.Texture))
            .Select(node => node.Name)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        nodes = nodes
            .Where(node => !string.IsNullOrEmpty(node.Texture) || !namesWithTexture.Contains(node.Name))
            .ToList();

        return new UtageLayoutInfo(name, version, nodeCount, textureCount, nodes, textures);
    }

    private static IEnumerable<string> PrintableRuns(ReadOnlySpan<byte> raw)
    {
        var bytes = raw.ToArray();
        var start = -1;
        for (var i = 0; i <= bytes.Length; i++)
        {
            var printable = i < bytes.Length && bytes[i] is >= 0x20 and <= 0x7E;
            if (printable)
            {
                if (start < 0)
                    start = i;
                continue;
            }

            if (start >= 0)
            {
                var length = i - start;
                if (length >= 3)
                    yield return Encoding.ASCII.GetString(bytes, start, length);
                start = -1;
            }
        }
    }

    private static bool ContainsTexturePath(string value)
    {
        var normalized = value.Replace('/', '\\');
        return normalized.Contains("\\texture\\", StringComparison.OrdinalIgnoreCase);
    }

    private static string DescribeRole(string name)
    {
        var lowered = name.ToLowerInvariant();
        var roles = new (string Prefix, string Role)[]
        {
            ("sysroot", "layout root"),
            ("waku", "frame"),
            ("sitaji", "backing plate"),
            ("moji", "lettering"),
            ("kage", "shadow"),
            ("hanko", "stamp"),
            ("ring", "ring"),
            ("icon", "icon"),
            ("base", "base"),
            ("bg", "background"),
            ("btn", "button"),
            ("cursor", "cursor"),
            ("line", "rule"),
            ("num", "number"),
            ("point", "pointer"),
        };
        foreach (var (prefix, role) in roles)
        {
            if (lowered.StartsWith(prefix, StringComparison.Ordinal))
                return role;
        }

        if (Regex.IsMatch(name, @"^\d+_\d+$", RegexOptions.CultureInvariant))
            return "group";
        return "";
    }
}
