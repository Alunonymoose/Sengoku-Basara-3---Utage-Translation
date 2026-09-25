"""GSM/FIM, grammar detection and the FIM contract -- including the two
regressions that cost this project the most: dialogue runaway (stale FIM
budgets/offsets) and the eaten first letter of highlighted words."""

import pytest
from hypothesis import given, settings, strategies as st

from basara import arc
from basara.font import Csa
from basara.markup import decode, encode
from basara.msg import (LEGACY, WESTERN, Fim, Gsm, MsgError, apply, check, detect_grammar,
                        speech_spans, tokenize)
from basara.table import MessageTable
from fixtures import TEXTS, csa_blob, msg_archive, table_blobs

CSA = Csa.parse(csa_blob())


def _pair(texts=TEXTS, grammar="western"):
    g, f = table_blobs(texts, CSA, grammar)
    return Gsm.parse(g), Fim.parse(f), g, f


def test_exact_round_trip_including_padding_and_header_word():
    g, f = table_blobs(TEXTS, CSA, header_word=0x12345678, padding=5)
    assert Gsm.parse(g).to_bytes() == g
    assert Fim.parse(f).to_bytes() == f


def test_size_checks_fail_closed():
    g, f = table_blobs(TEXTS, CSA)
    with pytest.raises(MsgError):
        Gsm.parse(g + b"\0\0")
    with pytest.raises(MsgError):
        Fim.parse(f[:-4])


def test_fixture_satisfies_contract_and_apply_is_identity():
    gsm, fim, _, f = _pair()
    assert check(gsm, fim).ok
    assert apply(gsm, fim).to_bytes() == f


def test_same_length_edit_is_in_place_and_byte_minimal():
    gsm, _, g, _ = _pair()
    w = list(gsm.words(0))
    w[0] = w[1]
    new = gsm.with_records({0: w}).to_bytes()
    diff = [i for i in range(len(g)) if g[i] != new[i]]
    assert len(new) == len(g) and diff and max(diff) - min(diff) < 2


def test_length_change_repacks_and_keeps_padding():
    gsm, _, _, _ = _pair()
    longer = list(gsm.words(0)[:-1]) + [1, 2, 3, 0xFFFF]
    new = gsm.with_records({0: longer})
    assert new.words(0) == tuple(longer)
    assert all(new.words(i) == gsm.words(i) for i in range(1, len(gsm)))
    assert new.pool[-3:] == gsm.pool[-3:] == (0xFFFF,) * 3


def test_edit_rederives_budget_and_speech_offsets_of_following_speeches():
    """The 2026-09-14 runaway bug: text grew, FIM col0/col1 were stale."""
    gsm, fim, _, _ = _pair()
    old = decode(gsm.words(2), CSA)
    grown = old.replace("Masamune!", "Masamune, my lord!")
    new_gsm = gsm.with_records({2: encode(grown, CSA)})
    assert not check(new_gsm, fim).ok               # untouched FIM is now wrong
    new_fim = apply(new_gsm, fim)
    assert check(new_gsm, new_fim).ok
    first = fim.first_row(2)
    before, after = fim.secondary[first + 1], new_fim.secondary[first + 1]
    assert after[1] >> 16 == (before[1] >> 16) + len("Masamune, my lord!") - len("Masamune!")
    for j in range(len(fim.secondary)):              # only col0 + col1-high may move
        assert fim.secondary[j][2:] == new_fim.secondary[j][2:]
        assert fim.secondary[j][1] & 0xFFFF == new_fim.secondary[j][1] & 0xFFFF
    assert fim.primary == new_fim.primary and fim.header == new_fim.header


def test_changing_the_number_of_speeches_is_refused():
    gsm, fim, _, _ = _pair()
    split = encode("Sacred Tree Bow:{p}First Frost{end}", CSA)
    with pytest.raises(MsgError, match="speech count"):
        apply(gsm.with_records({0: split}), fim)


def test_final_ffffd_before_terminator_is_not_a_new_speech():
    w = encode("Hi{p}{end}", CSA)
    assert speech_spans(w, 1) == [(0, len(w))]


def test_zero_speech_record_with_text_is_rejected():
    with pytest.raises(MsgError, match="zero-speech"):
        speech_spans(encode("Hi{end}", CSA), 0)


def test_unknown_control_word_fails_closed():
    with pytest.raises(MsgError, match="unknown control word F123"):
        tokenize([0x41, 0xF123, 0xFFFF])


def test_grammar_detection_prevents_the_eaten_first_letter_bug():
    """On a WESTERN table the legacy FF92:2 grammar swallows the first glyph
    of every highlighted word ("Release" -> "elease"); detection must pick
    western and the legacy reading must visibly lose the letter."""
    gsm, fim, _, _ = _pair()
    assert detect_grammar(gsm, fim) == "western"
    assert not check(gsm, fim, "legacy").ok
    w = gsm.words(1)
    assert "Release" in decode(w, CSA, WESTERN)
    legacy_view = decode(w, CSA, LEGACY)
    assert "Release" not in legacy_view and "elease" in legacy_view


def test_grammar_detection_recognises_legacy_tables():
    texts = ["Hi {FF92:3,0}there{FF91:0} friend{end}", "Plain{end}"]
    g, f = table_blobs(texts, CSA, grammar="legacy")
    assert detect_grammar(Gsm.parse(g), Fim.parse(f)) == "legacy"


def test_uncharted_table_fails_closed():
    gsm, fim, _, _ = _pair()
    bad = list(fim.secondary)
    bad[0] = (bad[0][0] + 1,) + bad[0][1:]
    with pytest.raises(MsgError, match="no proven grammar"):
        detect_grammar(gsm, Fim(fim.header, fim.primary, tuple(bad)))


def test_ambiguous_word_range_is_reported():
    texts = ["A{w:9000}B{end}"]
    g, f = table_blobs(texts, CSA)
    assert check(Gsm.parse(g), Fim.parse(f)).ambiguous_words == 1


# ------------------------------------------------------------ property test
words_st = st.lists(st.sampled_from(list("ABCxyz ,.!") + ["{br}", "{c:3}", "{/c}"]), max_size=30)


@settings(max_examples=200, deadline=None)
@given(edits=st.dictionaries(st.sampled_from([0, 1, 2, 4]), words_st, max_size=3))
def test_any_text_edit_keeps_the_whole_table_contract_valid(edits):
    gsm, fim, _, _ = _pair()
    changes = {}
    for r, parts in edits.items():
        body = "".join(parts)
        if r == 2:  # keep its 3-speech structure, change the text around it
            body = f"{{spk:2}}{body}!{{p}}{{spk:5}}x{{p}}y{{end}}"
        else:
            body += "{end}"
        changes[r] = encode(body, CSA)
    new_gsm = gsm.with_records(changes)
    new_fim = apply(new_gsm, fim)
    assert check(new_gsm, new_fim).ok
    for r in range(len(gsm)):
        assert new_gsm.words(r) == tuple(changes.get(r, gsm.words(r)))


def test_message_table_builds_only_the_members_it_changed():
    src = msg_archive(TEXTS)
    a = arc.read(src)
    t = MessageTable.open(a, "id_brief_r")
    assert t.grammar_name == "western" and t.text(0) == TEXTS[0]
    t.set(0, "Sacred Tree Bow:{br}First Frost{end}")
    members = t.build()
    assert set(members) == {t.gsm_entry.index, t.fim_entry.index}
    out = arc.rebuild(src, members)
    t2 = MessageTable.open(arc.read(out), "id_brief_r")
    assert t2.text(0) == "Sacred Tree Bow:{br}First Frost{end}"
    assert all(t2.text(r) == TEXTS[r] for r in range(1, len(TEXTS)))
    assert check(t2.gsm, t2.fim).ok


def test_shipped_dangling_records_are_preserved_and_locked():
    """Real shape from official SH/Utage basara.arc + startup.arc: the last two
    records point at/past the pool end (offset=pool len=1, offset=pool+1 len=0)."""
    g, _ = table_blobs(["Hi{end}", "Yo{end}"], CSA, padding=0)
    gsm = Gsm.parse(g)
    pool = len(gsm.pool)
    shipped = Gsm(gsm.header_word, gsm.records + ((pool, 1), (pool + 1, 0)), gsm.pool)
    blob = shipped.to_bytes()
    back = Gsm.parse(blob)
    assert back.to_bytes() == blob and back.dangling == (2, 3)
    with pytest.raises(MsgError, match="past the pool"):
        back.with_records({2: [1]})
    grown = back.with_records({0: encode("Hello there{end}", CSA)})
    newpool = len(grown.pool)
    assert grown.records[2:] == ((newpool, 1), (newpool + 1, 0))
    assert grown.words(1) == back.words(1)
