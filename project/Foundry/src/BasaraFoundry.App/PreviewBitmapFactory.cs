using System.Runtime.InteropServices.WindowsRuntime;
using Microsoft.UI.Xaml.Media.Imaging;

namespace BasaraFoundry.App;

internal static class PreviewBitmapFactory
{
    public static WriteableBitmap FromRgba(int width, int height, ReadOnlySpan<byte> rgba)
    {
        if (width <= 0 || height <= 0)
            throw new ArgumentOutOfRangeException(nameof(width));
        var expected = checked(width * height * 4);
        if (rgba.Length != expected)
            throw new ArgumentException($"RGBA preview contains {rgba.Length} bytes; {width}x{height} requires {expected}.", nameof(rgba));

        var bitmap = new WriteableBitmap(width, height);
        var bgraPremultiplied = new byte[expected];
        for (var offset = 0; offset < expected; offset += 4)
        {
            var r = rgba[offset];
            var g = rgba[offset + 1];
            var b = rgba[offset + 2];
            var a = rgba[offset + 3];
            bgraPremultiplied[offset] = Premultiply(b, a);
            bgraPremultiplied[offset + 1] = Premultiply(g, a);
            bgraPremultiplied[offset + 2] = Premultiply(r, a);
            bgraPremultiplied[offset + 3] = a;
        }

        using (var stream = bitmap.PixelBuffer.AsStream())
        {
            stream.Position = 0;
            stream.Write(bgraPremultiplied, 0, bgraPremultiplied.Length);
        }
        bitmap.Invalidate();
        return bitmap;
    }

    private static byte Premultiply(byte component, byte alpha) =>
        (byte)((component * alpha + 127) / 255);
}
