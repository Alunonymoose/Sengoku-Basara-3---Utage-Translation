"""What a resource inside an ARC actually is, and what it is tied to.

Everything here comes from the project's master handover document.  The point
is that you should never have to remember which file pairs with which: select
a resource and the tool tells you what it is, what it depends on, what depends
on it, and where other copies of it live.
"""

from __future__ import annotations

from pathlib import Path

# magic -> (short name, what it is, what it is tied to)
TYPE_NOTES = {
    b"\0XET": (
        "XET texture",
        "A DXT5 (or DXT1) texture atlas page. Dimensions are packed into bytes "
        "8..10; the block payload starts at the offset in bytes 16..19.",
        "Sprite positions come from a separate LSP layout in the same archive. "
        "Replacing a texture with one of DIFFERENT dimensions means the layout "
        "must be swapped too, or the UVs point at the wrong region.",
    ),
    b"\0GSM": (
        "GSM message table",
        "The dialogue itself: a table of records, each a sequence of glyph "
        "ordinals and control words. There is no Unicode here - text is "
        "indices into the font's glyph table.",
        "Pairs by name with a FIM (event and voice links, and the reveal "
        "budget) and needs the TNF font plus its CSA charmap to be readable.",
    ),
    b"\0FIM": (
        "FIM index map",
        "Links each message to its event and its voice clip, and carries the "
        "reveal budget in secondary column 0 as (lines << 16) | characters.",
        "THE DANGEROUS ONE. primary col4 and secondary col8 must never change "
        "- that is what marries dialogue to the right voice line. Only column "
        "0 may be rewritten.",
    ),
    b"\0CSA": (
        "CSA charmap",
        "Maps a character code to a glyph id in the font. For the English "
        "font 95 of 116 entries map - printable ASCII, with '&' absent.",
        "Meaningless without the TNF it belongs to. Swap them together.",
    ),
    b"\0TNF": (
        "TNF font definition",
        "The glyph table: cell position and advance per glyph. Text refers to "
        "glyphs by ORDINAL - the record's position here - not by the glyph_id "
        "key field.",
        "Its glyph cells live in the XET atlas pages beside it. A font swap "
        "means swapping the TNF, its CSA, and its atlas pages together.",
    ),
    b"\0PSL": (
        "PSL/LSP layout",
        "Sprite layout: which region of which atlas page is drawn where, and "
        "at what size. The node record format is not cracked.",
        "Sized for Japanese cells, which is why Latin text can draw about 1.7x "
        "too large. The fix used elsewhere was to shrink the glyph ink inside "
        "its cell rather than edit the layout.",
    ),
    b"QRTS": (
        "QRTS voice playlist",
        "NUL-terminated clip paths in play order. FIM secondary col8's low 16 "
        "bits index into this list.",
        "Utage and Samurai Heroes name these files differently and their lists "
        "are different lengths - which is exactly why transplanting SH's FIM "
        "desynced the dialogue.",
    ),
    b"\0SFX": ("SFX effects", "Sound effect definitions.", ""),
}

FAMILY_NOTES = {
    "cp_name_pl": "Officer name plate drawn in battle. Also copied into "
                  "rom/eng/id/friend_NNN.arc and rom/stage/stNNN/mNNN.arc - "
                  "changing one copy is not enough.",
    "cp_name_army": "Army name plate. Lives in mNNN_enemy.arc.",
    "cp_face_msg": "Character portrait for the dialogue plate. Byte-identical "
                   "between Utage and Samurai Heroes, which is what lets the "
                   "character map pair renumbered rosters.",
    "cp_face_army": "Army-screen portrait.",
    "kamon": "Family crest. Shared by everyone in a clan, so it identifies the "
             "clan but NOT the person - Masamune Date and Kojuro Katakura "
             "share the Date crest.",
    "waza": "Special-attack name art, still Japanese for the Utage-exclusive "
            "cast (pl016-pl029).",
}


def describe_entry(raw: bytes, name: str) -> list[str]:
    lines: list[str] = []
    magic = raw[:4]
    short, what, tied = TYPE_NOTES.get(magic, ("unknown", f"Magic {magic!r}.", ""))
    lines.append(f"TYPE   {short}")
    lines.append(f"       {what}")
    if tied:
        lines.append("")
        lines.append(f"TIED TO")
        lines.append(f"       {tied}")
    base = name.replace("/", "\\").split("\\")[-1].lower()
    for prefix, note in FAMILY_NOTES.items():
        if base.startswith(prefix):
            lines.append("")
            lines.append("FAMILY")
            lines.append(f"       {note}")
            break
    return lines


def siblings(entries, name: str) -> list[str]:
    """Entries in the same archive that share this resource's name."""

    target = name.replace("/", "\\")
    return [e.name for e in entries if e.name.replace("/", "\\") == target]
