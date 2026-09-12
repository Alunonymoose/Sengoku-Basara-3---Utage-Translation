namespace BasaraFoundry.Game.Utage;

public static class UtageTypeHashes
{
    public const uint Texture = 0x241F5DEB;
    public const uint Message = 0x10C460E6;
    public const uint Mif = 0x2EA515BF;
    public const uint Asc = 0x5E0EF076;
    public const uint Font = 0x1D609FFB;
    public const uint Layout = 0x60DD1B16;

    public static string Label(uint hash) => hash switch
    {
        Texture => "texture",
        Message => "message",
        Mif => "mif",
        Asc => "asc",
        Font => "font",
        Layout => "layout",
        _ => $"0x{hash:X8}",
    };
}
