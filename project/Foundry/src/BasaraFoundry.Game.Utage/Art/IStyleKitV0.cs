namespace BasaraFoundry.Game.Utage.Art;

/// <summary>
/// v0 style kit. NOT Capcom-certified. Supplies per-glyph coverage plus a fixed
/// material palette. The compositor (not the kit) applies stroke / fill / bevel.
/// SH pixel crop outranks this tier when the caller supplies a gated donor.
/// </summary>
public interface IStyleKitV0
{
    /// <summary>
    /// Natural-size coverage in [0..255], row-major, length == W*H.
    /// Caller scales. 0 = outside glyph, 255 = inside body.
    /// </summary>
    (int W, int H, byte[] Coverage) RasterizeGlyph(char c);

    (byte R, byte G, byte B) FillTop { get; }
    (byte R, byte G, byte B) FillBottom { get; }
    (byte R, byte G, byte B) Stroke { get; }
    (byte R, byte G, byte B) BevelHi { get; }
    (byte R, byte G, byte B) BevelLo { get; }
    int StrokeWidth { get; }
}
