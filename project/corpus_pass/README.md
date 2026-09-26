# Corpus pass — findings (2026-09-26)

Run over the user's text-only corpus upload (Utage eng/jpn + Samurai Heroes EU; `pack_text_corpus.py`).
Game text is NOT stored here; only the analysis scripts that were actually used.

1. **Parser fidelity:** all 14,240 real GSM/FIM tables round-trip byte-exact through `basara`.
2. **Grammar/contract census:** 14,421 / 14,630 tables satisfy the FIM contract under WESTERN
   (incl. 7,498 official SH). No table uses the legacy grammar. Words 0x8000–0xCFFF: none in the
   corpus (the gsm_tools vs FIM_CONTRACT_REPAIR disagreement is moot). New rules proven:
   FC11 = 0 args; spare unowned FIM rows exist (result_id) and are preserved.
3. **FC0E damage (fix ready):** 6,168 live ENG records / 44 archives have FC0E references
   overwritten with injected words; JPN and official SH never have text after FC0E (0 / 64,701).
   `fc0e_audit.py` measures, `fc0e_repair.py` proves + emits basara patchsets.
4. **Official English reuse:** only 22% of official SH English lines appear verbatim in live Utage
   (battle dialogue 18.6%). Names diverge from official (e.g. "Ichi" vs "Oichi",
   "Iansuke Akiyake" vs "Iorinosuke Akiage"). SH EU has no Japanese and FIM col8 is NOT a global
   voice-clip key (retracted), so line alignment needs the Japanese font decode (next step).
