"""Alrummi 3 V4 — simple texture-fix front end.

Normal workflow:
    Open ARC -> select texture -> Fix Texture -> preview -> Apply to ARC

The mature Alrummi 3 implementation remains underneath for ARC parsing,
donors, messages, dialogue tools, batch operations and diagnostics.  V4 hides
that complexity until Advanced Tools is opened.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from PIL import Image

import alrummi3_core as core
import alrummi3_gui as legacy
import donor_index as donor_module
import v4_mttex_codec as codec
import v4_image_edit


# ---------------------------------------------------------------------------
# Correct texture codec everywhere, not just in the visible preview.
# ---------------------------------------------------------------------------
_LEGACY_DECODE = legacy.decode_resource
_LEGACY_ENCODE = legacy.encode_replacement

def v4_decode_resource(raw: bytes, name: str = ""):
    if raw[:4] == b"\0XET":
        return codec.decode_resource(raw, name)
    return _LEGACY_DECODE(raw, name)

def v4_encode_replacement(raw: bytes, name: str, candidate: Image.Image, region: core.Region):
    if raw[:4] == b"\0XET":
        encoded, _ = codec.encode_candidate(raw, candidate, region=region)
        return encoded
    return _LEGACY_ENCODE(raw, name, candidate, region)

def v4_swap_xet_payload(source_raw: bytes, donor_raw: bytes):
    return codec.swap_xet_payload(source_raw, donor_raw)

def v4_load_donor_image(archive_path, entry_index):
    archive = core.parse_arc(Path(archive_path))
    index = int(entry_index)
    if not 0 <= index < len(archive.entries):
        raise ValueError(f"donor entry {index} outside {archive_path}")
    entry = archive.entries[index]
    raw = core.unpack_entry(entry)
    image, info = v4_decode_resource(raw, entry.name)
    return image, info, entry.name

legacy.decode_resource = v4_decode_resource
legacy.encode_replacement = v4_encode_replacement
legacy.swap_xet_payload = v4_swap_xet_payload
legacy.load_donor_image = v4_load_donor_image
core.decode_resource = v4_decode_resource
core.encode_replacement = v4_encode_replacement
core.swap_xet_payload = v4_swap_xet_payload
donor_module.load_donor_image = v4_load_donor_image

for module in (
    getattr(legacy, "sheet", None),
    getattr(legacy, "autofix", None),
    getattr(legacy, "layout_mod", None),
    sys.modules.get("batch"),
    sys.modules.get("character_map"),
):
    if module is None:
        continue
    if hasattr(module, "decode_resource"):
        setattr(module, "decode_resource", v4_decode_resource)
    if hasattr(module, "encode_replacement"):
        setattr(module, "encode_replacement", v4_encode_replacement)
    if hasattr(module, "swap_xet_payload"):
        setattr(module, "swap_xet_payload", v4_swap_xet_payload)


class AlrummiV4App(legacy.Alrummi3App):
    def __init__(self):
        self._v4_api_key = ""
        self._v4_fix_running = False
        self._last_codec_info = {}
        super().__init__()
        self.title("Alrummi 3 V4 — Utage Texture Fixer")

    # ------------------------------------------------------------------
    # Minimal main window. The old action panel is built in a hidden
    # advanced window so every mature backend attribute still exists.
    # ------------------------------------------------------------------
    def _build_ui(self):
        header = tk.Frame(self, bg="#17191c")
        header.pack(fill="x", padx=14, pady=(10, 6))
        ttk.Label(header, text="Alrummi 3 V4", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="Open ARC  →  select texture  →  Fix Texture  →  Apply",
            style="Muted.TLabel",
        ).pack(side="left", padx=(14, 0), pady=(5, 0))

        ttk.Button(header, text="Open ARC…", command=self.open_arc).pack(side="right")
        ttk.Button(header, text="Advanced tools…", command=self.show_advanced).pack(
            side="right", padx=(0, 7)
        )
        self.data_status = ttk.Label(header, text="Dictionary…", style="Muted.TLabel")
        self.data_status.pack(side="right", padx=(0, 10))
        self.ai_status = ttk.Label(header, text="AI: automatic", style="Muted.TLabel")
        self.ai_status.pack(side="right", padx=(0, 10))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=3)
        self.body_paned = body
        self._build_browser_panel(body)
        self._build_preview_panel(body)
        self._build_simple_panel(body)

        # Preserve the entire old feature set without putting it in the main
        # workflow. Closing this window only hides it.
        self._advanced_window = tk.Toplevel(self)
        self._advanced_window.title("Alrummi 3 V4 — Advanced Tools")
        self._advanced_window.geometry("430x820")
        self._advanced_window.protocol("WM_DELETE_WINDOW", self._advanced_window.withdraw)
        advanced_body = ttk.PanedWindow(self._advanced_window, orient="horizontal")
        advanced_body.pack(fill="both", expand=True)
        legacy.Alrummi3App._build_action_panel(self, advanced_body)
        self._advanced_window.withdraw()

        footer = tk.Frame(self, bg="#17191c")
        footer.pack(fill="x", padx=14, pady=(3, 8))
        self.status = ttk.Label(footer, text="", style="Muted.TLabel")
        self.status.pack(side="left", fill="x", expand=True)
        self.loading_label = ttk.Label(footer, text="Ready", style="Muted.TLabel")
        self.loading_label.pack(side="right", padx=(10, 6))
        self.loading_bar = ttk.Progressbar(footer, mode="indeterminate", length=120)
        self.loading_bar.pack(side="right")

    def _build_simple_panel(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        parent.add(panel, weight=2)
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="Texture fix", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            panel,
            text=(
                "Select the bad texture on the left. V4 tries an official Samurai "
                "Heroes donor first. If none exists, it rebuilds from the pristine "
                "/jpn artwork using high-quality image editing when available."
            ),
            style="Muted.TLabel", wraplength=310,
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        self.fix_button = ttk.Button(
            panel, text="★  FIX TEXTURE", style="Accent.TButton", command=self.fix_texture
        )
        self.fix_button.grid(row=2, column=0, sticky="ew", ipady=8)

        ttk.Label(panel, text="English wording override (optional)", style="Muted.TLabel").grid(
            row=3, column=0, sticky="w", pady=(12, 3)
        )
        self.v4_wording = tk.StringVar()
        ttk.Entry(panel, textvariable=self.v4_wording).grid(row=4, column=0, sticky="ew")

        self.fix_route = ttk.Label(
            panel,
            text="No candidate yet.",
            style="Muted.TLabel", wraplength=310,
        )
        self.fix_route.grid(row=5, column=0, sticky="w", pady=(10, 12))

        ttk.Separator(panel).grid(row=6, column=0, sticky="ew", pady=(0, 12))

        self.apply_button = ttk.Button(
            panel, text="APPLY TO ARC", style="Danger.TButton",
            command=self.apply_to_arc, state="disabled",
        )
        self.apply_button.grid(row=7, column=0, sticky="ew", ipady=8)

        ttk.Label(
            panel,
            text=(
                "Apply is the confirmation. V4 verifies the rebuilt ARC first, "
                "backs up the current ARC, then overwrites it."
            ),
            style="Muted.TLabel", wraplength=310,
        ).grid(row=8, column=0, sticky="w", pady=(5, 10))

        ttk.Button(panel, text="Restore previous ARC", command=self.restore_previous).grid(
            row=9, column=0, sticky="ew"
        )
        ttk.Button(panel, text="Advanced tools…", command=self.show_advanced).grid(
            row=10, column=0, sticky="ew", pady=(6, 0)
        )

        self.backup_status = ttk.Label(
            panel, text="Automatic backup: on", style="Muted.TLabel", wraplength=310
        )
        self.backup_status.grid(row=11, column=0, sticky="w", pady=(9, 0))

    def _build_menu(self):
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="Open ARC…\tCtrl+O", command=self.open_arc)
        file_menu.add_command(label="Open folder…", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        bar.add_cascade(label="File", menu=file_menu)

        tools = tk.Menu(bar, tearoff=0)
        tools.add_command(label="Fix Texture\tCtrl+G", command=self.fix_texture)
        tools.add_command(label="Apply to ARC\tCtrl+Enter", command=self.apply_to_arc)
        tools.add_command(label="Restore previous ARC", command=self.restore_previous)
        tools.add_separator()
        tools.add_command(label="Advanced tools…", command=self.show_advanced)
        bar.add_cascade(label="Tools", menu=tools)
        self.configure(menu=bar)

    def _install_shortcuts(self):
        self.bind_all("<Control-o>", lambda _e: self.open_arc())
        self.bind_all("<Control-g>", lambda _e: self.fix_texture())
        self.bind_all("<Control-Return>", lambda _e: self.apply_to_arc())

    def show_advanced(self):
        self._advanced_window.deiconify()
        self._advanced_window.lift()
        self._advanced_window.focus_force()

    # ------------------------------------------------------------------
    # Resource selection / candidate state.
    # ------------------------------------------------------------------
    def _resource_decoded(self, result):
        archive, raw, image, info, readable = result
        self._last_codec_info = dict(info or {})
        super()._resource_decoded(result)
        self.apply_button.configure(state="disabled")
        self.fix_button.configure(state="normal")
        self.fix_route.configure(text="Ready. Press FIX TEXTURE.")
        if readable is None and image is not None:
            shader = info.get("display_shader", "none")
            self.preview_meta.configure(
                text=(
                    f"{self.source_name}\n{info['container']} {info['format']} · "
                    f"{info['width']}×{info['height']} · {shader} · "
                    f"{info.get('codec','legacy')}"
                )
            )

    def _set_v4_candidate(self, image: Image.Image, meta: dict, lossless: bytes | None = None):
        if self.source_image is None:
            raise ValueError("source image disappeared")
        if image.size != self.source_image.size:
            raise ValueError(
                f"candidate dimensions {image.size} do not match source {self.source_image.size}"
            )
        self.candidate_image = image.convert("RGBA")
        self.candidate_meta = dict(meta)
        self.candidate_meta["source_dimensions"] = list(self.source_image.size)
        self.candidate_meta["candidate_dimensions"] = list(image.size)
        self.donor_replacement = lossless
        self.confirm_var.set(False)
        try:
            self.save_candidate_button.configure(state="normal")
        except Exception:
            pass
        self._draw_preview("candidate")
        self.preview_notebook.select(self.review_tab)
        self.apply_button.configure(state="normal")

    # ------------------------------------------------------------------
    # One button.
    # ------------------------------------------------------------------
    def fix_texture(self):
        if self.source_image is None or self.source_raw is None or self.selected_entry is None:
            messagebox.showinfo("Alrummi 3 V4", "Open an ARC and select a texture first.")
            return
        if self._v4_fix_running:
            return
        self._v4_fix_running = True
        self._v4_wording_snapshot = self.v4_wording.get().strip()
        self.fix_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.fix_route.configure(text="Checking official donor and pristine /jpn artwork…")
        self._set_progress("Fixing texture")
        self._set_status("Fix Texture: donor first, then native-art rebuild.")
        self._run_worker("autofix", self._v4_prepare_fix_guarded)

    def _v4_prepare_fix_guarded(self):
        try:
            return self._v4_prepare_fix()
        except Exception as exc:
            return {"route": "v4_error", "error": str(exc)}

    def _v4_prepare_fix(self):
        source = self.source_image.copy()
        raw = bytes(self.source_raw)
        entry = self.selected_entry
        archive = self.archive
        if entry is None or archive is None:
            raise ValueError("selection changed while preparing the fix")

        # Always recover the pristine Japanese counterpart when it exists.
        reference = None
        reference_meta = None
        match = core.find_jpn_reference(archive.path, entry.name)
        if match is not None:
            ref_archive, ref_entry = match
            ref_raw = core.unpack_entry(ref_entry)
            try:
                reference, reference_meta = v4_decode_resource(ref_raw, ref_entry.name)
            except Exception:
                reference = None
                reference_meta = None

        # A one-button workflow must not require the user to manually build
        # the donor index. Load it if cached, otherwise build it once.
        donor_index = self.donor_index
        if donor_index is None:
            donor_index = legacy.load_donor_index(legacy.donor_index_path(legacy.APP_ROOT))
        if donor_index is None:
            roots = [Path(r) for r in legacy.DEFAULT_DONOR_ROOTS if Path(r).is_dir()]
            if roots:
                donor_index = legacy.build_donor_index(roots)
                legacy.save_donor_index(donor_index, legacy.donor_index_path(legacy.APP_ROOT))

        charmap = self.character_map
        if charmap is None:
            charmap = legacy.load_character_map(legacy.character_map_path(legacy.APP_ROOT))

        if donor_index is not None:
            preferred = []
            translated = legacy.translate_resource(charmap, entry.name)
            if translated is not None:
                key, info = translated
                preferred.append((key, f"same character, matched on {info['matched_on']}"))
            candidates = legacy.find_donor_candidates(
                donor_index,
                entry.name,
                source_archive=str(archive.path),
                limit=12,
                preferred_keys=preferred,
            )
            for candidate in candidates:
                try:
                    image, info, resource = v4_load_donor_image(
                        candidate["archive"], candidate["entry_index"]
                    )
                except Exception:
                    continue
                if image.size != source.size:
                    continue
                lossless = None
                if raw[:4] == b"\0XET":
                    try:
                        donor_raw = legacy.load_donor_raw(
                            candidate["archive"], candidate["entry_index"]
                        )
                        lossless = v4_swap_xet_payload(raw, donor_raw)
                    except Exception:
                        lossless = None
                return {
                    "route": "donor",
                    "image": image,
                    "lossless": lossless,
                    "donor_index": donor_index,
                    "meta": {
                        "mode": "v4_official_donor",
                        "donor_archive": candidate["archive"],
                        "donor_entry_index": candidate["entry_index"],
                        "donor_resource": resource,
                        "match_reason": candidate.get("reason", ""),
                        "lossless_block_copy": lossless is not None,
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
        }

    def _get_v4_api_key(self):
        if self._v4_api_key:
            return self._v4_api_key
        env = os.environ.get("OPENAI_API_KEY", "").strip()
        if env:
            self._v4_api_key = env
            return env
        key = simpledialog.askstring(
            "High-quality texture rebuild",
            "No official Samurai Heroes texture exists for this asset.\n\n"
            "For the high-quality art-preserving rebuild, paste an OpenAI API key.\n"
            "It is kept in memory only.\n\n"
            "Cancel uses Alrummi's offline text-replacement fallback.",
            show="•",
            parent=self,
        )
        if key:
            self._v4_api_key = key.strip()
        return self._v4_api_key

    def _autofix_done(self, report):
        # Only consume our V4 reports. Advanced tools can still call the old
        # implementation when not inside a V4 Fix Texture run.
        if not self._v4_fix_running and not (
            isinstance(report, dict) and str(report.get("route","")).startswith("v4_")
        ):
            return super()._autofix_done(report)

        if report.get("donor_index") is not None:
            self.donor_index = report["donor_index"]

        route = report.get("route")
        if route == "donor":
            self._v4_fix_running = False
            self.fix_button.configure(state="normal")
            self._set_v4_candidate(report["image"], report["meta"], report.get("lossless"))
            quality = "lossless" if report.get("lossless") is not None else "re-encoded"
            self.fix_route.configure(
                text=f"Official Samurai Heroes donor found ({quality}). Preview it, then Apply."
            )
            self._set_status("Fix Texture complete: official Samurai Heroes donor.")
            return

        if route == "v4_error":
            self._v4_fix_running = False
            self.fix_button.configure(state="normal")
            self.apply_button.configure(state="disabled")
            self.fix_route.configure(text=f"Fix failed: {report.get('error','unknown error')}")
            self._set_status(self.fix_route.cget("text"))
            return

        if route == "needs_rebuild":
            key = self._get_v4_api_key()
            self.fix_route.configure(
                text="No official donor. Rebuilding from pristine game artwork…"
            )
            if key:
                self._run_worker("autofix", lambda: self._v4_ai_rebuild(report, key))
            else:
                self._run_worker("autofix", lambda: self._v4_offline_rebuild(report))
            return

        if route in ("v4_ai", "v4_offline"):
            self._v4_fix_running = False
            self.fix_button.configure(state="normal")
            image = report.get("image")
            if image is None:
                self.fix_route.configure(
                    text="No safe automatic replacement was found. Open Advanced tools for manual repair."
                )
                self._set_status("Fix Texture could not produce a safe candidate.")
                return
            self._set_v4_candidate(image, report.get("meta") or {}, None)
            if route == "v4_ai":
                note = "High-quality native-art rebuild ready. Preview it, then Apply."
            else:
                note = "Offline lettering fallback ready. Preview it carefully, then Apply."
            if report.get("ai_error"):
                note += f" Cloud edit failed, so offline fallback was used: {report['ai_error']}"
            self.fix_route.configure(text=note)
            self._set_status(note)
            return

        self._v4_fix_running = False
        self.fix_button.configure(state="normal")
        self.fix_route.configure(text="Fix failed to produce a candidate.")

    def _v4_ai_rebuild(self, report, key):
        art = report.get("reference")
        if art is None or art.size != report["source"].size:
            art = report["source"]
        hint = str(report.get("wording_hint", "")).strip()
        try:
            image, meta = v4_image_edit.edit_texture(
                art, report["name"], key, wording_hint=hint
            )
            return {
                "route": "v4_ai",
                "image": image,
                "meta": meta | {
                    "art_reference": "jpn" if report.get("reference") is not None else "source"
                },
                "donor_index": report.get("donor_index"),
            }
        except Exception as exc:
            fallback = self._v4_offline_rebuild(report)
            fallback["ai_error"] = str(exc)
            return fallback

    def _v4_offline_rebuild(self, report):
        source = report["source"]
        art = report.get("reference")
        if art is None or art.size != source.size:
            art = source
        name = report["name"]

        # If the user supplied exact wording and marked a repair box in
        # Advanced tools, honour it before trying OCR.
        wording = str(report.get("wording_hint", "")).strip()
        if wording and getattr(self, "repair_regions", None):
            box = self.repair_regions[-1]
            image, meta = core.render_text_in_region(
                art.copy(), wording, box, clear_first=True
            )
            return {
                "route": "v4_offline",
                "image": image,
                "meta": meta | {"mode": "v4_offline_exact_wording"},
                "donor_index": report.get("donor_index"),
            }

        try:
            layout, _inventory = self._layout_for(name)
            assets = legacy.sheet.find_assets(
                art, self._ocr_engine(), layout=layout, texture_name=name
            )
            legacy.sheet.translate_assets(assets, self.project_dictionary)
            image, notes = legacy.sheet.rebuild_sheet(art, assets)
            applied = sum(1 for asset in assets if asset.ready)
            if applied:
                return {
                    "route": "v4_offline",
                    "image": image,
                    "meta": {
                        "mode": "v4_offline_sheet",
                        "elements": len(assets),
                        "applied": applied,
                        "notes": notes,
                        "art_reference": "jpn" if report.get("reference") is not None else "source",
                    },
                    "donor_index": report.get("donor_index"),
                }
        except Exception as exc:
            return {
                "route": "v4_offline",
                "image": None,
                "meta": {"mode": "v4_offline_failed", "error": str(exc)},
                "donor_index": report.get("donor_index"),
            }

        return {
            "route": "v4_offline",
            "image": None,
            "meta": {"mode": "v4_offline_no_match"},
            "donor_index": report.get("donor_index"),
        }

    # ------------------------------------------------------------------
    # Preview -> Apply. No extra confirmation maze.
    # ------------------------------------------------------------------
    def apply_to_arc(self):
        if (
            self.archive is None or self.selected_entry is None
            or self.source_raw is None or self.candidate_image is None
        ):
            messagebox.showinfo("Alrummi 3 V4", "Create and preview a candidate first.")
            return
        self.apply_button.configure(state="disabled")
        self.fix_button.configure(state="disabled")
        self._set_status("Verifying replacement and backing up ARC…")
        self._run_worker("write", self._v4_apply_worker_guarded)

    def _v4_apply_worker_guarded(self):
        try:
            return self._v4_apply_worker()
        except Exception as exc:
            return {"mode": "v4_write_error", "error": str(exc)}

    def _v4_apply_worker(self):
        before = self.archive
        entry = self.selected_entry
        if before is None or entry is None:
            raise ValueError("ARC selection changed")
        # Reload from disk so the overwrite is always based on the latest ARC,
        # not a stale copy that was opened before another tool changed it.
        before = core.parse_arc(before.path)
        if entry.index >= len(before.entries):
            raise ValueError("selected entry no longer exists in the current ARC")
        disk_entry = before.entries[entry.index]
        if disk_entry.name != entry.name:
            raise ValueError(
                "ARC entry order changed on disk; refusing to overwrite the wrong resource"
            )
        disk_raw = core.unpack_entry(disk_entry)
        if core.sha256(disk_raw) != core.sha256(self.source_raw):
            raise ValueError(
                "The selected texture changed on disk since it was previewed. "
                "Reopen it before applying."
            )

        if self.donor_replacement is not None:
            replacement = self.donor_replacement
        elif disk_raw[:4] == b"\0XET":
            replacement, encode_meta = codec.encode_candidate(
                disk_raw, self.candidate_image
            )
            if self.candidate_meta is not None:
                self.candidate_meta["encode"] = encode_meta
        else:
            full = core.Region(0, 0, self.candidate_image.width, self.candidate_image.height)
            replacement = v4_encode_replacement(
                disk_raw, disk_entry.name, self.candidate_image, full
            )

        built = core.rebuild_arc(before, {entry.index: replacement})
        arc_path = before.path
        tmp = arc_path.with_name(arc_path.name + ".alrummi-v4.tmp")
        tmp.write_bytes(built)
        try:
            after = core.parse_arc(tmp)
            verification = core.verify_single_replacement(before, after, entry.index)

            original_backup = arc_path.with_name(arc_path.name + ".alrummi-original.bak")
            previous_backup = arc_path.with_name(arc_path.name + ".alrummi-previous.bak")
            if not original_backup.exists():
                shutil.copy2(arc_path, original_backup)
            shutil.copy2(arc_path, previous_backup)

            audit_path = arc_path.with_name(arc_path.name + ".alrummi-v4.audit.json")
            audit = {
                "tool": "Alrummi 3 V4",
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "archive": str(arc_path),
                "resource": disk_entry.name,
                "entry_index": disk_entry.index,
                "candidate": self.candidate_meta,
                "verification": verification,
                "backups": {
                    "original": str(original_backup),
                    "previous": str(previous_backup),
                },
            }
            core.write_audit(audit_path, audit)

            os.replace(tmp, arc_path)
            new_archive = core.parse_arc(arc_path)
            return {
                "mode": "v4_overwrite",
                "archive": new_archive,
                "entry_index": entry.index,
                "audit": audit_path,
                "verification": verification,
                "previous_backup": previous_backup,
                "original_backup": original_backup,
            }
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    def _write_finished(self, result):
        if isinstance(result, dict) and result.get("mode") == "v4_write_error":
            self.apply_button.configure(state="normal" if self.candidate_image is not None else "disabled")
            self.fix_button.configure(state="normal")
            self.fix_route.configure(text=f"Apply failed: {result.get('error','unknown error')}")
            self._set_status(self.fix_route.cget("text"))
            messagebox.showerror("Apply failed", str(result.get("error", "unknown error")))
            return
        if not isinstance(result, dict) or result.get("mode") != "v4_overwrite":
            return super()._write_finished(result)

        new_archive = result["archive"]
        index = int(result["entry_index"])
        self.archive = new_archive
        if 0 <= self.current_archive_index < len(self.loaded_archives):
            self.loaded_archives[self.current_archive_index] = new_archive

        self.candidate_image = None
        self.candidate_meta = None
        self.donor_replacement = None
        self.apply_button.configure(state="disabled")
        self.fix_button.configure(state="normal")
        self.fix_route.configure(
            text=f"Applied. Backup: {Path(result['previous_backup']).name}"
        )
        self.backup_status.configure(
            text=f"Previous ARC saved as {Path(result['previous_backup']).name}"
        )
        self._refresh_entries()
        if str(index) in self.entry_tree.get_children():
            self.entry_tree.selection_set(str(index))
            self.entry_tree.see(str(index))
            self._entry_selected()

        self._set_status(
            f"Applied to {new_archive.path.name}. "
            f"Verified {result['verification']['changed_entries']} changed entry."
        )
        messagebox.showinfo(
            "Applied to ARC",
            f"Updated:\n{new_archive.path}\n\n"
            f"Backup:\n{result['previous_backup']}\n\n"
            f"Audit:\n{result['audit']}",
        )

    def restore_previous(self):
        if self.archive is None:
            messagebox.showinfo("Alrummi 3 V4", "Open an ARC first.")
            return
        arc_path = self.archive.path
        previous = arc_path.with_name(arc_path.name + ".alrummi-previous.bak")
        original = arc_path.with_name(arc_path.name + ".alrummi-original.bak")
        backup = previous if previous.exists() else original
        if not backup.exists():
            messagebox.showinfo("Alrummi 3 V4", "No Alrummi backup exists for this ARC yet.")
            return
        tmp = arc_path.with_name(arc_path.name + ".alrummi-restore.tmp")
        shutil.copy2(backup, tmp)
        os.replace(tmp, arc_path)
        restored = core.parse_arc(arc_path)
        self.archive = restored
        if 0 <= self.current_archive_index < len(self.loaded_archives):
            self.loaded_archives[self.current_archive_index] = restored
        self._set_current_archive(self.current_archive_index)
        self.fix_route.configure(text=f"Restored {backup.name}.")
        self._set_status(f"Restored ARC from {backup}.")


if __name__ == "__main__":
    AlrummiV4App().mainloop()
