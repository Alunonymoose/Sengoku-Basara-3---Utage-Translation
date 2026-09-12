using System.Security.Cryptography;
using BasaraFoundry.Domain;

namespace BasaraFoundry.Game.Utage.Xet;

public sealed record UtageEditMaskProposal(
    int Width,
    int Height,
    byte[] Mask01,
    int ChangedPixels,
    int AffectedBlocks,
    int EffectiveBlockPixels,
    int PotentialCollateralPixels,
    PixelRect? ChangedBounds,
    IReadOnlyList<(int Bx, int By)> BlockCoords,
    string PristineRgbaSha256,
    string CandidateRgbaSha256,
    string MaskSha256)
{
    public bool HasChanges => ChangedPixels > 0;
}

/// <summary>
/// Builds a review proposal from the exact decoded pristine counterpart and the
/// frozen candidate. This is deliberately NOT approval: the operator still has
/// to inspect the exact changed-pixel mask and the larger BC3 block footprint.
/// </summary>
public static class UtageEditMaskProposalService
{
    public static UtageEditMaskProposal Create(
        ReadOnlySpan<byte> pristineRgba,
        ReadOnlySpan<byte> candidateRgba,
        int width,
        int height)
    {
        if (width <= 0 || height <= 0)
            throw new ArgumentOutOfRangeException(nameof(width), "Texture dimensions must be positive.");

        var pixels = checked(width * height);
        var rgbaBytes = checked(pixels * 4);
        if (pristineRgba.Length != rgbaBytes || candidateRgba.Length != rgbaBytes)
            throw new ArgumentException("Pristine/candidate RGBA lengths must equal width*height*4.");

        var mask = new byte[pixels];
        var changed = 0;
        var minX = width;
        var minY = height;
        var maxX = -1;
        var maxY = -1;

        for (var y = 0; y < height; y++)
        {
            for (var x = 0; x < width; x++)
            {
                var pixel = y * width + x;
                var o = pixel * 4;
                if (pristineRgba[o] == candidateRgba[o] &&
                    pristineRgba[o + 1] == candidateRgba[o + 1] &&
                    pristineRgba[o + 2] == candidateRgba[o + 2] &&
                    pristineRgba[o + 3] == candidateRgba[o + 3])
                {
                    continue;
                }

                mask[pixel] = 1;
                changed++;
                minX = Math.Min(minX, x);
                minY = Math.Min(minY, y);
                maxX = Math.Max(maxX, x);
                maxY = Math.Max(maxY, y);
            }
        }

        var blocks = UtageBc3BlockGraft.MaskToBlockSet(mask, width, height);
        var effectivePixels = 0;
        foreach (var (bx, by) in blocks)
        {
            var left = bx * 4;
            var top = by * 4;
            var right = Math.Min(width, left + 4);
            var bottom = Math.Min(height, top + 4);
            effectivePixels += Math.Max(0, right - left) * Math.Max(0, bottom - top);
        }

        PixelRect? bounds = changed == 0
            ? null
            : new PixelRect(minX, minY, maxX + 1, maxY + 1);

        return new UtageEditMaskProposal(
            Width: width,
            Height: height,
            Mask01: mask,
            ChangedPixels: changed,
            AffectedBlocks: blocks.Count,
            EffectiveBlockPixels: effectivePixels,
            PotentialCollateralPixels: Math.Max(0, effectivePixels - changed),
            ChangedBounds: bounds,
            BlockCoords: blocks,
            PristineRgbaSha256: Sha256(pristineRgba),
            CandidateRgbaSha256: Sha256(candidateRgba),
            MaskSha256: Sha256(mask));
    }

    /// <summary>
    /// Creates a human-review image. Exact edited pixels are highlighted strongly;
    /// pixels in the same 4x4 BC3 blocks but outside the exact mask are highlighted
    /// separately so compression collateral is visible before approval.
    /// </summary>
    public static byte[] CreateReviewRgba(
        ReadOnlySpan<byte> candidateRgba,
        UtageEditMaskProposal proposal)
    {
        ArgumentNullException.ThrowIfNull(proposal);
        var pixels = checked(proposal.Width * proposal.Height);
        if (candidateRgba.Length != pixels * 4 || proposal.Mask01.Length != pixels)
            throw new ArgumentException("Candidate/proposal dimensions disagree.");

        var blockPixels = new byte[pixels];
        foreach (var (bx, by) in proposal.BlockCoords)
        {
            var left = bx * 4;
            var top = by * 4;
            var right = Math.Min(proposal.Width, left + 4);
            var bottom = Math.Min(proposal.Height, top + 4);
            for (var y = top; y < bottom; y++)
            {
                for (var x = left; x < right; x++)
                    blockPixels[y * proposal.Width + x] = 1;
            }
        }

        var output = candidateRgba.ToArray();
        for (var i = 0; i < pixels; i++)
        {
            var o = i * 4;
            if (proposal.Mask01[i] != 0)
            {
                // Exact changed pixel: vivid magenta over the candidate.
                output[o] = 255;
                output[o + 1] = (byte)(output[o + 1] / 4);
                output[o + 2] = 220;
                output[o + 3] = 255;
            }
            else if (blockPixels[i] != 0)
            {
                // Same compressed block, not explicitly editable: amber warning.
                output[o] = (byte)((output[o] + 255) / 2);
                output[o + 1] = (byte)((output[o + 1] + 165) / 2);
                output[o + 2] = (byte)(output[o + 2] / 2);
                output[o + 3] = 255;
            }
            else
            {
                // Outside production footprint: dim but still recognizable.
                output[o] = (byte)(output[o] / 3);
                output[o + 1] = (byte)(output[o + 1] / 3);
                output[o + 2] = (byte)(output[o + 2] / 3);
                output[o + 3] = 255;
            }
        }

        return output;
    }

    private static string Sha256(ReadOnlySpan<byte> bytes) =>
        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}
