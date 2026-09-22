namespace BasaraFoundry.Game.Utage.Xet;

/// <summary>
/// Exact PS3 MT Framework YCbCr colour shader used by Kuriimu2 for 0x2A/0x2B.
/// Converts between artist/display RGBA and the RGBA channels physically stored
/// in the BC3 payload. Threshold 123 and truncating clamp intentionally match
/// Kuriimu2's MtTex_YCbCrColorShader.
/// </summary>
public static class UtageYcbcrColorShader
{
    public const int CbCrThreshold = 123;

    public static byte[] StoredToDisplay(ReadOnlySpan<byte> storedRgba)
    {
        Validate(storedRgba, nameof(storedRgba));
        var output = new byte[storedRgba.Length];
        for (var o = 0; o < storedRgba.Length; o += 4)
        {
            var alpha = storedRgba[o + 1];
            var y = storedRgba[o + 3];
            var cb = storedRgba[o + 2] - CbCrThreshold;
            var cr = storedRgba[o] - CbCrThreshold;

            output[o] = Clamp(y + 1.402 * cr);
            output[o + 1] = Clamp(y - 0.344136 * cb - 0.714136 * cr);
            output[o + 2] = Clamp(y + 1.772 * cb);
            output[o + 3] = alpha;
        }
        return output;
    }

    public static byte[] DisplayToStored(ReadOnlySpan<byte> displayRgba)
    {
        Validate(displayRgba, nameof(displayRgba));
        var output = new byte[displayRgba.Length];
        for (var o = 0; o < displayRgba.Length; o += 4)
        {
            var r = displayRgba[o];
            var g = displayRgba[o + 1];
            var b = displayRgba[o + 2];
            var a = displayRgba[o + 3];

            var y = 0.299 * r + 0.587 * g + 0.114 * b;
            var cb = CbCrThreshold - 0.168736 * r - 0.331264 * g + 0.5 * b;
            var cr = CbCrThreshold + 0.5 * r - 0.418688 * g - 0.081312 * b;

            output[o] = Clamp(cr);
            output[o + 1] = a;
            output[o + 2] = Clamp(cb);
            output[o + 3] = Clamp(y);
        }
        return output;
    }

    private static byte Clamp(double value) => (byte)Math.Max(0, Math.Min(value, 255));

    private static void Validate(ReadOnlySpan<byte> rgba, string parameter)
    {
        if (rgba.Length == 0 || rgba.Length % 4 != 0)
            throw new ArgumentException("RGBA buffer must be non-empty and divisible by four bytes.", parameter);
    }
}
