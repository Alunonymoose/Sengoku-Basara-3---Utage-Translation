"""Alrummi 3 V4.1 — hardened one-button texture fixer.

This is a thin correction layer over V4.  It keeps the simple UI and mature
Alrummi backends, but changes the decision that matters:

    Open ARC -> select texture -> FIX TEXTURE -> preview -> APPLY TO ARC

FIX TEXTURE no longer trusts the first same-size Samurai Heroes candidate.
Every donor must pass provenance, binary/image, geometry and OCR checks.  Bad
or still-Japanese donors are skipped automatically and the pipeline continues
to the native-art rebuild.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from PIL import Image

import alrummi3_v4 as v4
import v41_donor_validate as donor_gate
import v41_image_edit


class AlrummiV41App(v4.AlrummiV4App):
    def __init__(self):
        self._v41_rejected_donors: list[dict] = []
        super().__init__()
        self.title("Alrummi 3 2.0 — Utage Texture Workshop")
        try:
            self.fix_route.configure(text="Ready. FIX TEXTURE now validates donors before using them.")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Source text: read it once, use OCR only as evidence / geometry and the
    # project dictionary as the authoritative translation source.
    # ------------------------------------------------------------------
    def _v41_detect_text_edits(self, image: Image.Image, engine, wording_hint: str):
        reads = []
        if engine is not None:
            try:
                reads = engine.read_regions(image, scale=3) or []
            except Exception:
                try:
                    reads = engine.read_regions(image, scale=2) or []
                except Exception:
                    reads = []

        source_ocr = " ".join(
            str(getattr(row, "text", "")).strip()
            for row in reads if str(getattr(row, "text", "")).strip()
        )
        edits: list[v41_image_edit.TextEdit] = []
        for row in reads:
            text = str(getattr(row, "text", "")).strip()
            box = getattr(row, "box", None)
            if not text or not box or not donor_gate.japanese_chars(text):
                continue
            try:
                region = v4.core.Region(int(box[0]), int(box[1]), int(box[2]), int(box[3])).clipped(image.size)
            except Exception:
                continue
            english = ""
            try:
                resolved = v4.legacy.ocr.resolve_text(self.project_dictionary, text)
                if resolved:
                    english = str(resolved[0]).strip()
            except Exception:
                try:
                    hit = v4.legacy.dict_lookup(self.project_dictionary, text)
                    if hit:
                        english = str(hit[0]).strip()
                except Exception:
                    pass

            # These are confirmed game terms and also protect the roulette
            # sheet when OCR sees a single character rather than a phrase.
            known = {"大吉": "GREAT LUCK", "吉": "GOOD LUCK", "凶": "BAD LUCK", "区": "BAD LUCK"}
            english = known.get(text.replace(" ", ""), english)
            edits.append(v41_image_edit.TextEdit(region, text, english))

        edits.sort(key=lambda item: (item.box.top, item.box.left))

        hint = " ".join(str(wording_hint).split()).strip()
        if hint and edits:
            # Pipe-separated overrides map in reading order. A single detected
            # label receives the entire override verbatim.
            pieces = [piece.strip() for piece in hint.split("|") if piece.strip()]
            if len(edits) == 1:
                edits[0] = replace(edits[0], english=hint)
            elif len(pieces) == len(edits):
                edits = [replace(edit, english=piece) for edit, piece in zip(edits, pieces)]

        # OCR can miss a highly stylised text-only texture entirely. If the
        # operator supplied wording, use the visible-alpha bounds as the one
        # edit region rather than handing the image model the entire atlas.
        if hint and not edits:
            alpha = image.convert("RGBA").getchannel("A")
            bbox = alpha.getbbox()
            if bbox:
                edits.append(v41_image_edit.TextEdit(
                    v4.core.Region(*bbox).clipped(image.size), "", hint
                ))

        return source_ocr, edits

    # ------------------------------------------------------------------
    # Donor-first, but donor must prove it is actually an improvement.
    # ------------------------------------------------------------------
    def _v4_prepare_fix(self):
        source = self.source_image.copy()
        raw = bytes(self.source_raw)
        entry = self.selected_entry
        archive = self.archive
        if entry is None or archive is None:
            raise ValueError("selection changed while preparing the fix")

        reference = None
        reference_meta = None
        match = v4.core.find_jpn_reference(archive.path, entry.name)
        if match is not None:
            ref_archive, ref_entry = match
            ref_raw = v4.core.unpack_entry(ref_entry)
            try:
                reference, reference_meta = v4.v4_decode_resource(ref_raw, ref_entry.name)
            except Exception:
                reference = None
                reference_meta = None

        donor_index = self.donor_index
        if donor_index is None:
            donor_index = v4.legacy.load_donor_index(v4.legacy.donor_index_path(v4.legacy.APP_ROOT))
        if donor_index is None:
            roots = [Path(root) for root in v4.legacy.DEFAULT_DONOR_ROOTS if Path(root).is_dir()]
            if roots:
                donor_index = v4.legacy.build_donor_index(roots)
                v4.legacy.save_donor_index(donor_index, v4.legacy.donor_index_path(v4.legacy.APP_ROOT))

        charmap = self.character_map
        if charmap is None:
            charmap = v4.legacy.load_character_map(v4.legacy.character_map_path(v4.legacy.APP_ROOT))

        try:
            engine = self._ocr_engine()
        except Exception:
            engine = None
        source_ocr, text_edits = self._v41_detect_text_edits(
            reference if reference is not None and reference.size == source.size else source,
            engine,
            getattr(self, "_v4_wording_snapshot", ""),
        )

        rejected: list[dict] = []
        if donor_index is not None:
            preferred = []
            translated = v4.legacy.translate_resource(charmap, entry.name)
            if translated is not None:
                key, info = translated
                preferred.append((key, f"same character, matched on {info['matched_on']}"))
            candidates = v4.legacy.find_donor_candidates(
                donor_index,
                entry.name,
                source_archive=str(archive.path),
                limit=16,
                preferred_keys=preferred,
            )

            for candidate in candidates:
                try:
                    donor_raw = v4.legacy.load_donor_raw(
                        candidate["archive"], candidate["entry_index"]
                    )
                    image, info, resource = v4.v4_load_donor_image(
                        candidate["archive"], candidate["entry_index"]
                    )
                except Exception as exc:
                    rejected.append({
                        "archive": candidate.get("archive", ""),
                        "entry_index": candidate.get("entry_index"),
                        "reason": f"could not load/decode donor: {exc}",
                    })
                    continue

                verdict = donor_gate.validate_donor(
                    source, raw, image, donor_raw, candidate["archive"],
                    ocr_engine=engine, source_ocr=source_ocr,
                )

                # Fail closed: if OCR could not positively see Latin lettering,
                # this candidate is not allowed to end Fix Texture. A missed
                # good donor costs one rebuild; a false-positive donor leaves
                # the Japanese in the game.
                if not verdict.donor_latin:
                    verdict.accepted = False
                    if "donor OCR did not prove English lettering" not in verdict.reasons:
                        verdict.reasons.append("donor OCR did not prove English lettering")

                if not verdict.accepted:
                    rejected.append({
                        "archive": candidate.get("archive", ""),
                        "entry_index": candidate.get("entry_index"),
                        "resource": resource,
                        "match_reason": candidate.get("reason", ""),
                        "validation": verdict.as_dict(),
                    })
                    continue

                lossless = None
                if raw[:4] == b"\0XET" and verdict.exact_xet_layout:
                    try:
                        lossless = v4.v4_swap_xet_payload(raw, donor_raw)
                    except Exception:
                        lossless = None
                return {
                    "route": "donor",
                    "image": image,
                    "lossless": lossless,
                    "donor_index": donor_index,
                    "meta": {
                        "mode": "v41_validated_official_donor",
                        "donor_archive": candidate["archive"],
                        "donor_entry_index": candidate["entry_index"],
                        "donor_resource": resource,
                        "match_reason": candidate.get("reason", ""),
                        "lossless_block_copy": lossless is not None,
                        "validation": verdict.as_dict(),
                        "rejected_before_accept": rejected,
                    },
                }

        return {
            "route": "needs_rebuild",
            "source": source,
            "reference": reference,
            "reference_meta": reference_meta,
            "donor_index": donor_index,
            "name": entry.name,
            "wording_hint": getattr(self, "_v4_wording_snapshot", ""),
            "source_ocr": source_ocr,
            "text_edits": text_edits,
            "donor_rejections": rejected,
        }

    # ------------------------------------------------------------------
    # High-quality path: full native sheet is context, but only detected text
    # regions are copied back. No global repainting.
    # ------------------------------------------------------------------
    def _v4_ai_rebuild(self, report, key):
        art = report.get("reference")
        if art is None or art.size != report["source"].size:
            art = report["source"]
        hint = str(report.get("wording_hint", "")).strip()
        edits = list(report.get("text_edits") or [])
        try:
            image, meta = v41_image_edit.edit_texture(
                art,
                report["name"],
                key,
                edits=edits,
                wording_hint=hint,
            )
            try:
                engine = self._ocr_engine()
            except Exception:
                engine = None
            quality = donor_gate.candidate_quality(
                report["source"], image,
                ocr_engine=engine,
                source_ocr=str(report.get("source_ocr", "")),
            )
            if not quality["accepted"]:
                rejected = self._v4_no_image_provider(
                    report,
                    "AI candidate rejected: " + "; ".join(quality["reasons"]),
                )
                rejected["candidate_quality"] = quality
                return rejected
            return {
                "route": "v4_ai",
                "image": image,
                "meta": meta | {
                    "art_reference": "jpn" if report.get("reference") is not None else "source",
                    "candidate_quality": quality,
                    "donor_rejections": report.get("donor_rejections", []),
                },
                "donor_index": report.get("donor_index"),
                "donor_rejections": report.get("donor_rejections", []),
            }
        except Exception as exc:
            rejected = self._v4_no_image_provider(report, f"Image provider failed: {exc}")
            rejected["donor_rejections"] = report.get("donor_rejections", [])
            return rejected

    def _v4_offline_rebuild(self, report):
        source = report["source"]
        art = report.get("reference")
        if art is None or art.size != source.size:
            art = source

        # Free mode uses the native-art sheet rebuild first.  It measures the
        # existing stroke, repairs only the detected glyph hole, and redraws
        # the wording with the sheet's own colour/outline/glow.  This is much
        # safer than painting a generic font over the whole atlas and costs no
        # API credits.
        wording = " ".join(str(report.get("wording_hint", "")).split()).strip()
        source_ocr = str(report.get("source_ocr", ""))
        edits = [edit for edit in report.get("text_edits", []) if str(edit.english).strip()]
        try:
            engine = self._ocr_engine()
        except Exception:
            engine = None

        try:
            layout, _inventory = self._layout_for(report["name"])
            assets = v4.legacy.sheet.find_assets(
                art, engine, layout=layout, texture_name=report["name"]
            )

            # OCR in the hardened path already knows the approved English for
            # Japanese labels (including the small roulette vocabulary). Feed
            # that result back into the higher-quality sheet renderer when its
            # own dictionary lookup is less certain.
            for asset in assets:
                overlaps = []
                for edit in edits:
                    left = max(asset.box.left, edit.box.left)
                    top = max(asset.box.top, edit.box.top)
                    right = min(asset.box.right, edit.box.right)
                    bottom = min(asset.box.bottom, edit.box.bottom)
                    area = max(0, right - left) * max(0, bottom - top)
                    if area:
                        overlaps.append((area, edit))
                if overlaps:
                    _area, edit = max(overlaps, key=lambda pair: pair[0])
                    asset.english = str(edit.english).strip()
                    asset.done = False

            # If OCR sees Latin text, this is a repair/re-letter pass rather
            # than a translation pass. It removes the old pasted lettering and
            # rebuilds it in-place instead of declaring it "already English".
            reletter = not donor_gate.japanese_chars(source_ocr)
            v4.legacy.sheet.translate_assets(
                assets, self.project_dictionary, reletter=reletter
            )

            ready = [asset for asset in assets if asset.ready]
            if wording and ready:
                pieces = [piece.strip() for piece in wording.split("|") if piece.strip()]
                if len(ready) == 1:
                    ready[0].english = wording
                elif len(pieces) == len(ready):
                    for asset, piece in zip(ready, pieces):
                        asset.english = piece

            image, notes = v4.legacy.sheet.rebuild_sheet(art, assets)
            applied = sum(1 for asset in assets if asset.ready)
            if applied:
                quality = donor_gate.candidate_quality(
                    source, image, ocr_engine=engine, source_ocr=source_ocr
                )
                if quality["accepted"]:
                    return {
                        "route": "v4_offline",
                        "image": image,
                        "meta": {
                            "mode": "v41_native_sheet_free",
                            "elements": len(assets),
                            "applied": applied,
                            "notes": notes,
                            "quality": quality,
                            "art_reference": "jpn" if report.get("reference") is not None else "source",
                            "network_used": False,
                        },
                        "donor_index": report.get("donor_index"),
                        "donor_rejections": report.get("donor_rejections", []),
                    }
                rejected_quality = quality
            else:
                rejected_quality = None
        except Exception as exc:
            rejected_quality = {"error": str(exc)}

        # Last-resort local path: honour an explicitly supplied repair region
        # even when OCR cannot segment this particular stylised asset.
        if not edits and wording and getattr(self, "repair_regions", None):
            edits = [v41_image_edit.TextEdit(self.repair_regions[-1], "", wording)]
        if not edits:
            return {
                "route": "v4_offline", "image": None,
                "meta": {
                    "mode": "v41_no_safe_local_edit",
                    "quality": rejected_quality,
                    "network_used": False,
                },
                "donor_index": report.get("donor_index"),
                "donor_rejections": report.get("donor_rejections", []),
            }

        image = art.copy()
        records = []
        for edit in edits:
            image, meta = v4.core.render_text_in_region(
                image, edit.english, edit.box, clear_first=True
            )
            records.append({"box": edit.box.as_list(), "english": edit.english})
        quality = donor_gate.candidate_quality(
            source, image, ocr_engine=engine, source_ocr=source_ocr
        )
        if not quality["accepted"]:
            return {
                "route": "v4_offline", "image": None,
                "meta": {"mode": "v41_local_quality_rejected", "quality": quality},
                "donor_index": report.get("donor_index"),
                "donor_rejections": report.get("donor_rejections", []),
            }
        return {
            "route": "v4_offline", "image": image,
            "meta": {
                "mode": "v41_surgical_local_edit",
                "art_reference": "jpn" if report.get("reference") is not None else "source",
                "edits": records,
                "outside_detected_text_regions_preserved": True,
                "quality": quality,
                "network_used": False,
            },
            "donor_index": report.get("donor_index"),
            "donor_rejections": report.get("donor_rejections", []),
        }

    def _autofix_done(self, report):
        route = report.get("route") if isinstance(report, dict) else ""
        if route == "needs_rebuild":
            self._v41_rejected_donors = list(report.get("donor_rejections") or [])
        elif route == "donor":
            self._v41_rejected_donors = list((report.get("meta") or {}).get("rejected_before_accept") or [])
        elif route in ("v4_ai", "v4_offline"):
            self._v41_rejected_donors = list(report.get("donor_rejections") or self._v41_rejected_donors)

        super()._autofix_done(report)

        # For final states, explain that donor candidates were deliberately
        # rejected instead of silently pretending the first match was English.
        if route in ("donor", "v4_ai", "v4_offline") and self._v41_rejected_donors:
            count = len(self._v41_rejected_donors)
            current = str(self.fix_route.cget("text"))
            self.fix_route.configure(
                text=current + f"  Skipped {count} invalid/still-Japanese donor candidate(s)."
            )


if __name__ == "__main__":
    AlrummiV41App().mainloop()
