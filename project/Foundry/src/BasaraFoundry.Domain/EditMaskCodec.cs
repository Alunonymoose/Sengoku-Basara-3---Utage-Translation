namespace BasaraFoundry.Domain;

/// <summary>
/// Converts domain edit regions into the flat per-pixel mask expected by the
/// Utage BC3 graft writer (non-zero = editable).
/// </summary>
public static class EditMaskCodec
{
    public static byte[] ToMask01(EditMask mask, int width, int height)
    {
        ArgumentNullException.ThrowIfNull(mask);
        if (width <= 0 || height <= 0)
            throw new ArgumentOutOfRangeException("Texture dimensions must be positive.");

        var pixels = checked(width * height);
        var output = new byte[pixels];
        if (mask.Regions.Count == 0)
            return output;

        foreach (var region in mask.Regions)
        {
            var left = Math.Clamp(region.Left, 0, width);
            var top = Math.Clamp(region.Top, 0, height);
            var right = Math.Clamp(region.Right, 0, width);
            var bottom = Math.Clamp(region.Bottom, 0, height);
            for (var y = top; y < bottom; y++)
            {
                var row = y * width;
                for (var x = left; x < right; x++)
                    output[row + x] = 1;
            }
        }

        return output;
    }
}
