namespace BasaraFoundry.Game.Utage.Xet;

public sealed record UtageRbxgPlanes(byte[] BaseRgba, byte[] MaskRgba);

/// <summary>
/// Artist-facing adapter for PS3 MT Framework format 0x2B (RBxG).
/// Stored BC3 RGBA is not a normal artist RGBA image:
///   visible/base = (stored.A, stored.A, stored.A, stored.G)
///   hidden/mask  = (stored.R, stored.B, 0, 255)
/// Repacking reverses exactly:
///   stored = (mask.R, base.A, mask.G, base.G)
/// </summary>
public static class UtageRbxgCodec
{
    public static UtageRbxgPlanes UnpackStoredRgba(ReadOnlySpan<byte> storedRgba)
    {
        ValidateRgbaLength(storedRgba.Length, nameof(storedRgba));
        var baseRgba = new byte[storedRgba.Length];
        var maskRgba = new byte[storedRgba.Length];

        for (var o = 0; o < storedRgba.Length; o += 4)
        {
            var r = storedRgba[o];
            var g = storedRgba[o + 1];
            var b = storedRgba[o + 2];
            var a = storedRgba[o + 3];

            baseRgba[o] = a;
            baseRgba[o + 1] = a;
            baseRgba[o + 2] = a;
            baseRgba[o + 3] = g;

            maskRgba[o] = r;
            maskRgba[o + 1] = b;
            maskRgba[o + 2] = 0;
            maskRgba[o + 3] = 255;
        }

        return new UtageRbxgPlanes(baseRgba, maskRgba);
    }

    public static byte[] PackStoredRgba(ReadOnlySpan<byte> baseRgba, ReadOnlySpan<byte> maskRgba)
    {
        if (baseRgba.Length != maskRgba.Length)
            throw new ArgumentException("RBxG base/mask plane lengths disagree.");
        ValidateRgbaLength(baseRgba.Length, nameof(baseRgba));

        var stored = new byte[baseRgba.Length];
        for (var o = 0; o < stored.Length; o += 4)
        {
            if (baseRgba[o] != baseRgba[o + 1] || baseRgba[o + 1] != baseRgba[o + 2])
                throw new InvalidDataException($"RBxG base pixel {o / 4} is not canonical greyscale RGB.");
            if (maskRgba[o + 2] != 0 || maskRgba[o + 3] != 255)
                throw new InvalidDataException($"RBxG mask pixel {o / 4} does not preserve canonical B=0/A=255 metadata.");

            stored[o] = maskRgba[o];
            stored[o + 1] = baseRgba[o + 3];
            stored[o + 2] = maskRgba[o + 1];
            stored[o + 3] = baseRgba[o + 1];
        }
        return stored;
    }

    private static void ValidateRgbaLength(int length, string parameter)
    {
        if (length == 0 || length % 4 != 0)
            throw new ArgumentException("RGBA buffer must be non-empty and divisible by four bytes.", parameter);
    }
}
