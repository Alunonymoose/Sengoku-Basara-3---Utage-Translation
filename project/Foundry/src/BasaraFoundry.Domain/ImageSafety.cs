namespace BasaraFoundry.Domain;

public sealed record PixelDiffReport(
    int TotalPixels,
    int ChangedPixels,
    int ChangedInsideMask,
    int ChangedOutsideMask,
    bool IsSafe);

public static class PixelDiffValidator
{
    public static PixelDiffReport CompareRgba(
        ReadOnlySpan<byte> before,
        ReadOnlySpan<byte> after,
        int width,
        int height,
        EditMask mask)
    {
        ArgumentNullException.ThrowIfNull(mask);
        if (width <= 0 || height <= 0)
            throw new ArgumentOutOfRangeException(nameof(width), "Image dimensions must be positive.");

        var expectedLength = checked(width * height * 4);
        if (before.Length != expectedLength || after.Length != expectedLength)
        {
            throw new ArgumentException(
                $"RGBA buffers must both contain exactly {expectedLength} bytes for {width}x{height}.");
        }

        var changed = 0;
        var inside = 0;
        var outside = 0;

        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var offset = (y * width + x) * 4;
                if (before.Slice(offset, 4).SequenceEqual(after.Slice(offset, 4)))
                    continue;

                changed++;
                var allowed = mask.Regions.Any(region => region.Contains(x, y));
                if (allowed)
                    inside++;
                else
                    outside++;
            }
        }

        var safe = !mask.RejectChangesOutsideRegions || outside == 0;
        return new PixelDiffReport(width * height, changed, inside, outside, safe);
    }
}
