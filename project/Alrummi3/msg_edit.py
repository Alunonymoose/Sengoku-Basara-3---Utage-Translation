"""In-game dialogue editing, ported from the project's proven build pipeline.

This is a faithful port of the project's `rebuild_msg.py`, `pipeline.py` and
`build_final2.py` onto Alrummi 3's own ARC layer.  Nothing here was invented:
the control grammar, the Latin glyph encoding, the blank-run rule and the
reveal budget all come from the master handover document and the scripts that
built 1,380 working archives.

The rules that matter, in the order the project ranks them:

* Utage's `\\0FIM` event and voice links are never touched.  `primary.col4`
  and `secondary.col8` stay byte-identical; touching either is what desynced
  dialogue from voice the first time round.  **Only secondary column 0**, the
  reveal budget, is rewritten.
* The GSM record count and order never change - only each record's glyph
  sequence, and within a record only the text runs between the controls.
* **A run that encodes to nothing must not vanish.**  An empty speech makes
  the record hold one speech fewer than the engine expects, every reveal
  budget after it shifts by one, and the last line waits forever for
  characters that never arrive, repeating its voice clip.  Empty runs are
  written as a single space, exactly as Capcom's own English does.
* The Japanese font and its kanji atlas pages are replaced with Samurai
  Heroes' 184-glyph Latin font and its pages.
"""

from __future__ import annotations

import gzip
import json
import struct
import textwrap
from pathlib import Path
from typing import Callable, Sequence

from alrummi3_core import parse_arc, rebuild_arc, unpack_entry

# Control-word argument counts.
#
# 0xFF92 takes ONE argument.  The master handover document says two; that is
# wrong, and following it silently ate the first character of every speech
# that follows a colour tag - "Student of the Honest Satake School" decoded
# as "tudent of...".  Decoding the installed English both ways settles it:
# with one argument the mid-word speeches drop from 116 to 60, and the 60 that
# remain are lines that legitimately begin with a space for a runtime name.
# `probe_argc` re-runs that comparison on demand.
ARGC = {
    0xFC0F: 1, 0xFC12: 0, 0xFC16: 1, 0xFC17: 1, 0xFED2: 2, 0xFF91: 1,
    0xFF92: 1, 0xFFFA: 1, 0xFFFB: 1, 0xFFFD: 0, 0xFFFE: 0, 0xFFFF: 0,
}
NEWLINE = 0xFFFE

# Capcom's maximum line in this font, and the dialogue plate's line ceiling.
LINE_WIDTH = 41
PLATE_LINES = 3
BRIEFING_LINES = 6


# ---------------------------------------------------------------- encoding

def enc(ch: str) -> int | None:
    """ASCII to Latin glyph id.  The font has no '&', so everything above shifts."""

    o = ord(ch)
    if o < 0x20 or o > 0x7E:
        return None
    return o - 32 if o < 0x26 else o - 33


def encode_text(s: str) -> list[int]:
    out: list[int] = []
    for ch in s:
        if ch == "\n":
            out.append(NEWLINE)
            continue
        glyph = enc(ch)
        out.append(glyph if glyph is not None else enc("?"))
    return out


def dec_en(ids: Sequence[int]) -> str:
    """Latin glyph ids back to ASCII, the inverse of enc()."""

    out = []
    for g in ids:
        if g > 0x8000:
            continue
        c = g + 32 if g < 0x06 else g + 33
        out.append(chr(c) if 32 <= c <= 126 else "?")
    return "".join(out)


ENCODABLE = {chr(c) for c in range(0x20, 0x7F)} - {"&"}


def unencodable(text: str) -> set[str]:
    """Characters that cannot be drawn by the Latin font."""

    return {ch for ch in text if ch != "\n" and ch not in ENCODABLE}


# ------------------------------------------------------------------- GSM

def gsm_records(blob: bytes) -> list[list[int]]:
    pool_chars, count = struct.unpack(">2I", blob[8:16])
    table, pool = 16, 16 + count * 8
    if pool + pool_chars * 2 != len(blob):
        raise ValueError("unexpected GSM layout")
    out = []
    for i in range(count):
        off, length = struct.unpack(">2I", blob[table + i * 8: table + i * 8 + 8])
        out.append(
            list(struct.unpack(">%dH" % length, blob[pool + off * 2: pool + off * 2 + length * 2]))
            if length else []
        )
    return out


def build_gsm(template: bytes, records: Sequence[Sequence[int]]) -> bytes:
    pool: list[int] = []
    table = bytearray()
    for record in records:
        table += struct.pack(">2I", len(pool), len(record))
        pool.extend(record)
    head = bytearray(template[:16])
    struct.pack_into(">2I", head, 8, len(pool), len(records))
    body = struct.pack(">%dH" % len(pool), *pool) if pool else b""
    return bytes(head) + bytes(table) + body


def segs_of(seq: Sequence[int], argc: dict[int, int] | None = None) -> list[tuple]:
    argc = ARGC if argc is None else argc
    out = []
    j, n = 0, len(seq)
    while j < n:
        x = seq[j]
        if x >= 0xF000:
            k = 1 + argc.get(x, 1)
            out.append(("c", list(seq[j:j + k]), x))
            j += k
        elif x >= 0x8000:
            out.append(("c", [x], None))
            j += 1
        else:
            run = []
            while j < n and seq[j] < 0x8000:
                run.append(seq[j])
                j += 1
            out.append(("t", run, None))
    return out


def groups_of(segs: Sequence[tuple]) -> list[tuple[int, int]]:
    """Index ranges covering one speech: text segments glued by newlines."""

    groups = []
    i, n = 0, len(segs)
    while i < n:
        if segs[i][0] == "t":
            j = i
            while True:
                k = j + 1
                if k + 1 < n and segs[k][0] == "c" and segs[k][2] == NEWLINE and segs[k + 1][0] == "t":
                    j = k + 1
                    continue
                break
            groups.append((i, j))
            i = j + 1
        else:
            i += 1
    return groups


def speech_text(segs: Sequence[tuple], rng: tuple[int, int], decode: Callable) -> str:
    a, b = rng
    parts = []
    for k in range(a, b + 1):
        kind, words, _ctrl = segs[k]
        parts.append("\n" if kind == "c" else decode(words))
    return "".join(parts)


def rebuild_record(seq: Sequence[int], english: Sequence[str | None]) -> list[int]:
    segs = segs_of(seq)
    groups = groups_of(segs)
    starts = {a: (a, b) for a, b in groups}
    order = {a: i for i, (a, b) in enumerate(groups)}
    out: list[int] = []
    i, n = 0, len(segs)
    while i < n:
        if i in starts:
            a, b = starts[i]
            value = english[order[a]] if order[a] < len(english) else None
            if value is None:
                for k in range(a, b + 1):
                    out.extend(segs[k][1])
            else:
                out.extend(encode_text(value))
            i = b + 1
            continue
        out.extend(segs[i][1])
        i += 1
    return out


def probe_argc(records: Sequence[Sequence[int]], argc: dict[int, int]) -> dict:
    """Score an argument-count table: a good table leaves no impossible glyphs.

    A wrong count makes the parser treat a control's argument as a glyph, so
    text runs pick up values far outside the font.  Counting those is how the
    two candidate tables are told apart on real data.
    """

    impossible = 0
    text_words = 0
    for seq in records:
        for kind, words, _ctrl in segs_of(seq, argc):
            if kind != "t":
                continue
            for w in words:
                text_words += 1
                if w >= 0x4000:
                    impossible += 1
    return {"text_words": text_words, "impossible": impossible}


# -------------------------------------------------------------- wrapping

def wrap(text: str, width: int = LINE_WIDTH) -> str:
    lines = text.split("\n")
    if all(len(line) <= width for line in lines):
        return text
    out: list[str] = []
    for part in lines:
        out += textwrap.wrap(part, width) or [""]
    if len(out) > PLATE_LINES:
        out = textwrap.wrap(" ".join(text.split()), width)
    return "\n".join(out)


def line_ceiling(japanese: str) -> int:
    """Three lines on the dialogue plate, six in the mission-briefing box.

    The project's rule: a Japanese key carrying its own hard line breaks is a
    briefing, and that widget holds six lines.
    """

    return BRIEFING_LINES if "\n" in japanese else PLATE_LINES


# --------------------------------------------------------------- decoding

def load_glyph_maps(app_root: Path) -> dict[str, dict[int, str]]:
    path = Path(app_root) / "project_data" / "glyph_maps.json.gz"
    if not path.is_file():
        return {}
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return {}
    return {name: {int(k): v for k, v in mapping.items()} for name, mapping in raw.items()}


def decode_archive(
    archive_path: str | Path,
    glyph_map: dict[int, str] | None = None,
) -> list[dict]:
    """Read every speech out of a msg archive, as editable rows."""

    archive = parse_arc(Path(archive_path))
    mapping = glyph_map or {}

    def decode_jp(words):
        return "".join(mapping.get(g, "") for g in words)

    rows: list[dict] = []
    for entry in archive.entries:
        raw = unpack_entry(entry)
        if raw[:4] != b"\0GSM":
            continue
        name = entry.name.replace("\\", "/")
        for index, seq in enumerate(gsm_records(raw)):
            segs = segs_of(seq)
            groups = groups_of(segs)
            if not groups:
                continue
            for speech, rng in enumerate(groups):
                japanese = speech_text(segs, rng, decode_jp)
                english_now = speech_text(segs, rng, dec_en)
                rows.append({
                    "gsm": name,
                    "record": index,
                    "speech": speech,
                    "japanese": japanese,
                    "current": english_now,
                    "has_japanese": any(ord(c) > 0x2000 for c in japanese),
                    "english": "",
                    "signed_off": False,
                })
    return rows


def validate_row(row: dict) -> list[str]:
    """Problems that would show up in game, per the project's conventions."""

    problems: list[str] = []
    text = row.get("english") or ""
    if not text.strip():
        return problems
    bad = unencodable(text)
    if bad:
        problems.append("cannot be drawn: " + " ".join(sorted(bad)))
    wrapped = wrap(text)
    ceiling = line_ceiling(row.get("japanese", ""))
    lines = wrapped.count("\n") + 1
    if lines > ceiling:
        problems.append(f"{lines} lines, the widget shows {ceiling}")
    longest = max((len(line) for line in wrapped.split("\n")), default=0)
    if longest > LINE_WIDTH:
        problems.append(f"line of {longest} characters, maximum {LINE_WIDTH}")
    return problems


# ------------------------------------------------------- English assembly

# Full-width punctuation the message tables use, mapped to what the Latin font
# can draw.  Taken from the project's build_final2.py.
PUNCT = {
    "\u3000": " ", "\u3001": ", ", "\u3002": ". ", "\uff01": "!", "\uff07": "!",
    "\uff1f": "?", "\uff1a": ":", "\uff1b": ";", "\uff0c": ", ", "\uff0e": ". ",
    "\u300c": '"', "\u300d": '"', "\u300e": '"', "\u300f": '"',
    "\u3010": "[", "\u3011": "]", "\uff08": "(", "\uff09": ")",
    "\u30fb": " - ", "\u30fc": "-", "\u2026": "...", "\uff5e": "~", "\u301c": "~",
    "\u3005": "", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
    "\uff05": "%", "\uff03": "#", "\uff0f": "/", "\uff0b": "+", "\uff0d": "-",
}
for _i in range(10):
    PUNCT[chr(0xFF10 + _i)] = str(_i)
for _i in range(26):
    PUNCT[chr(0xFF21 + _i)] = chr(65 + _i)
    PUNCT[chr(0xFF41 + _i)] = chr(97 + _i)


_CJK_RANGES = (
    ("぀", "ヿ"),
    ("㐀", "䶿"),
    ("一", "鿿"),
    ("ｦ", "ﾝ"),
)


def _has_cjk(text: str) -> bool:
    return any(lo <= ch <= hi for ch in text for lo, hi in _CJK_RANGES)


def translit(text: str) -> str:
    """Last resort for a run with no translation: keep what maps to ASCII.

    A run must never keep its original glyph ids - in the Latin font those
    land on stray marks at the end of the atlas, which is where the
    "Harumasa Nanbu# Take them down!" corruption came from.
    """

    out = []
    for ch in text:
        if ch in PUNCT:
            out.append(PUNCT[ch])
        elif ch == "\n" or 32 <= ord(ch) <= 126:
            out.append(ch)
    return "".join(out).strip(" ")


def _latin_parts(donor_path: Path) -> tuple[bytes, bytes, list[bytes]]:
    donor = parse_arc(Path(donor_path))
    by_magic: dict[bytes, list[tuple[str, bytes]]] = {}
    for entry in donor.entries:
        raw = unpack_entry(entry)
        by_magic.setdefault(raw[:4], []).append((entry.name.replace("\\", "/"), raw))
    tnf = by_magic[b"\0TNF"][0][1]
    csa = by_magic[b"\0CSA"][0][1]
    pages = [raw for name, raw in by_magic.get(b"\0XET", []) if name.startswith("msg/")]
    return tnf, csa, pages


def build_english_archive(
    jp_path: str | Path,
    donor_path: str | Path,
    rows: Sequence[dict],
    *,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[bytes, dict]:
    """Assemble the English archive, including the reveal budget.

    ``rows`` are the decoded rows from :func:`decode_archive`, with ``english``
    filled in.  A speech left blank is transliterated rather than left alone,
    because the Latin font cannot draw the original Japanese glyph ids - a run
    kept as-is renders as stray marks from the end of the atlas.
    """

    archive = parse_arc(Path(jp_path))
    lat_tnf, lat_csa, lat_pages = _latin_parts(Path(donor_path))
    if not lat_pages:
        raise ValueError("donor archive carries no msg/ Latin atlas pages")

    by_key = {(r["gsm"], r["record"], r["speech"]): r for r in rows}

    gsm_entries: dict[str, tuple] = {}
    fim_entries: dict[str, tuple] = {}
    for entry in archive.entries:
        raw = unpack_entry(entry)
        name = entry.name.replace("\\", "/")
        if raw[:4] == b"\0GSM":
            gsm_entries[name] = (entry, raw)
        elif raw[:4] == b"\0FIM":
            fim_entries[name] = (entry, raw)

    replacements: dict[int, bytes] = {}
    # "transliterated" covers two very different cases and reporting them
    # together is misleading: a speech that was already English passes through
    # unchanged, while one that still held Japanese genuinely loses meaning.
    stats = {
        "translated": 0,
        "transliterated": 0,
        "passthrough_english": 0,
        "japanese_lost": 0,
        "budget": 0,
        "blank_runs": 0,
        "speeches": 0,
    }
    total = max(1, len(gsm_entries))

    for position, (name, (gentry, graw)) in enumerate(gsm_entries.items(), start=1):
        records = gsm_records(graw)
        fentry, fraw = fim_entries.get(name, (None, None))
        newf = bytearray(fraw) if fraw else None
        secondary_start = 0
        n2 = 0
        if newf is not None:
            n1, n2, _nv = struct.unpack(">3I", fraw[8:20])
            secondary_start = 32 + n1 * 20

        for index, seq in enumerate(records):
            segs = segs_of(seq)
            groups = groups_of(segs)
            if not groups:
                continue

            japanese: list[str] = []
            texts: list[str] = []
            for speech in range(len(groups)):
                row = by_key.get((name, index, speech))
                source_jp = str(row.get("japanese", "")) if row else ""
                japanese.append(source_jp)
                value = str(row.get("english", "")) if row else ""
                if value.strip():
                    stats["translated"] += 1
                else:
                    # No translation: keep whatever maps to ASCII, drop the rest.
                    value = translit(source_jp)
                    stats["transliterated"] += 1
                    # Use the same CJK test the survey uses, or the two
                    # disagree: full-width punctuation such as ＇ is above
                    # U+2000 but is not Japanese that needs translating.
                    if _has_cjk(source_jp):
                        stats["japanese_lost"] += 1
                    elif source_jp.strip():
                        stats["passthrough_english"] += 1
                value = wrap(value)
                if not value:
                    # An empty run would vanish and shift every later budget.
                    value = " "
                    stats["blank_runs"] += 1
                texts.append(value)
                stats["speeches"] += 1
            records[index] = rebuild_record(seq, texts)

            if newf is None:
                continue
            primary = struct.unpack(">5I", fraw[32 + index * 20: 52 + index * 20])
            first_secondary = primary[4]
            k = 0
            for jp_text, en_text in zip(japanese, texts):
                # Blank speeches are skipped by the engine and consume no row.
                if not jp_text.strip():
                    continue
                row_index = first_secondary + k
                k += 1
                if row_index >= n2:
                    continue
                off = secondary_start + row_index * 44
                old = struct.unpack(">I", fraw[off:off + 4])[0]
                jp_chars = len(jp_text) - jp_text.count("\n")
                # Records with a runtime substitution store more characters
                # than the text needs; that slack is preserved, not discarded.
                slack = max(0, (old & 0xFFFF) - jp_chars)
                en_lines = en_text.count("\n") + 1
                en_chars = len(en_text) - en_text.count("\n")
                struct.pack_into(">I", newf, off, (en_lines << 16) | min(0xFFFF, en_chars + slack))
                stats["budget"] += 1

        replacements[gentry.index] = build_gsm(graw, records)
        if newf is not None and bytes(newf) != fraw:
            replacements[fentry.index] = bytes(newf)
        if progress:
            progress(position, total)

    slot = 0
    for entry in archive.entries:
        raw = unpack_entry(entry)
        name = entry.name.replace("\\", "/")
        magic = raw[:4]
        if magic == b"\0TNF":
            replacements[entry.index] = lat_tnf
        elif magic == b"\0CSA":
            replacements[entry.index] = lat_csa
        elif magic == b"\0XET" and name.startswith("msg/"):
            replacements[entry.index] = lat_pages[slot] if slot < len(lat_pages) else lat_pages[-1]
            slot += 1

    return rebuild_arc(archive, replacements), stats


def verify_english_build(jp_path: str | Path, built: bytes) -> dict:
    """The project's five build invariants, checked against the source.

    A route was only ever installed at 46 archives passing all five.  The
    third and fourth are the ones that matter most: they are what keeps the
    dialogue married to the right voice line.
    """

    import io

    before = parse_arc(Path(jp_path))
    scratch = Path(jp_path).with_suffix(".alrummi3-verify.tmp")
    scratch.write_bytes(built)
    try:
        after = parse_arc(scratch)
    finally:
        scratch.unlink(missing_ok=True)

    problems: list[str] = []
    checks: dict[str, bool] = {}

    before_gsm = {e.name: unpack_entry(e) for e in before.entries if unpack_entry(e)[:4] == b"\0GSM"}
    after_gsm = {e.name: unpack_entry(e) for e in after.entries if unpack_entry(e)[:4] == b"\0GSM"}
    before_fim = {e.name: unpack_entry(e) for e in before.entries if unpack_entry(e)[:4] == b"\0FIM"}
    after_fim = {e.name: unpack_entry(e) for e in after.entries if unpack_entry(e)[:4] == b"\0FIM"}

    # 1 + 2: glyph values inside the Latin range, and no new out-of-range value.
    in_range = True
    subset = True
    for name, raw in after_gsm.items():
        original = before_gsm.get(name)
        if original is None:
            continue
        before_out = set()
        for seq in gsm_records(original):
            for kind, words, _c in segs_of(seq):
                if kind == "t":
                    before_out.update(w for w in words if w >= 184)
        for seq in gsm_records(raw):
            for kind, words, _c in segs_of(seq):
                if kind != "t":
                    continue
                for w in words:
                    if w >= 184:
                        in_range = False
                        if w not in before_out:
                            subset = False
    checks["1 glyphs in the Latin 184 range"] = in_range
    checks["2 out-of-range values are a subset of the original"] = subset

    # 3 + 4: the event and voice links are byte-identical.
    col4_ok = True
    col8_ok = True
    for name, raw in after_fim.items():
        original = before_fim.get(name)
        if original is None or len(original) != len(raw):
            col4_ok = col8_ok = False
            continue
        n1, n2, _nv = struct.unpack(">3I", original[8:20])
        for i in range(n1):
            off = 32 + i * 20 + 16
            if original[off:off + 4] != raw[off:off + 4]:
                col4_ok = False
        so = 32 + n1 * 20
        for i in range(n2):
            off = so + i * 44 + 32
            if original[off:off + 4] != raw[off:off + 4]:
                col8_ok = False
    checks["3 FIM primary col4 (event link) unchanged"] = col4_ok
    checks["4 FIM secondary col8 (voice link) unchanged"] = col8_ok

    # 5: the speech skeleton is identical and no run came out empty.
    shape_ok = True
    empty_runs = 0
    for name, raw in after_gsm.items():
        original = before_gsm.get(name)
        if original is None:
            continue
        old_records = gsm_records(original)
        new_records = gsm_records(raw)
        if len(old_records) != len(new_records):
            shape_ok = False
            continue
        for old_seq, new_seq in zip(old_records, new_records):
            old_groups = groups_of(segs_of(old_seq))
            new_segs = segs_of(new_seq)
            new_groups = groups_of(new_segs)
            if len(old_groups) != len(new_groups):
                shape_ok = False
            for a, b in new_groups:
                # "Empty" means the run encoded to no words at all, which
                # makes the speech vanish from the record and shifts every
                # later reveal budget.  A deliberate blank run is a single
                # space - one word - and is correct.
                if sum(
                    len(new_segs[k][1])
                    for k in range(a, b + 1)
                    if new_segs[k][0] == "t"
                ) == 0:
                    empty_runs += 1
    checks["5 speech skeleton identical, no empty run"] = shape_ok and empty_runs == 0

    for label, ok in checks.items():
        if not ok:
            problems.append(label)
    return {
        "status": "pass" if not problems else "fail",
        "checks": checks,
        "failed": problems,
        "empty_runs": empty_runs,
        "gsm_entries": len(after_gsm),
        "fim_entries": len(after_fim),
    }


def find_latin_donor(jp_path: str | Path, rom_root: str | Path) -> Path | None:
    """The Samurai Heroes donor that supplies the Latin font.

    Utage-exclusive stages (m035-m045) have no counterpart of the same name,
    but the Latin TNF and CSA are byte-identical across every donor, so any
    one of them supplies the font.
    """

    rom = Path(rom_root)
    donor_dir = rom / "eng" / "id_msg_BACKUP_pre_desync_fix"
    if not donor_dir.is_dir():
        return None
    exact = donor_dir / Path(jp_path).name
    if exact.is_file():
        return exact
    fallback = donor_dir / "msg_m019_pl003.arc"
    if fallback.is_file():
        return fallback
    for candidate in sorted(donor_dir.glob("msg_*.arc")):
        return candidate
    return None
