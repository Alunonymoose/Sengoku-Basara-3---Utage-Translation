"""Alrummi 3 Hybrid.

This keeps the mature Alrummi 3 feature set (ARC browser, JPN reference,
Samurai Heroes donors, MSG reader/editor, dialogue batch, texture batch, local
Ollama chat, installs/revert and audit writes) but replaces the PS3 XET path
with the Kuriimu2-parity codec proven in Alrummi Next.

The UI is intentionally an overlay/subclass rather than a second rewrite.  The
legacy implementation remains the feature provider; this file changes the
front door, defaults and unsafe texture-generation choices.
"""
from __future__ import annotations

import io
import json
import os
import queue
import re
import sys
import threading
import time
import zipfile
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image

import alrummi3_core as core
import alrummi3_gui as legacy
import donor_index as donor_module
import mttex_codec
import openai_image_edit


# ---------------------------------------------------------------------------
# Codec compatibility layer
# ---------------------------------------------------------------------------
_LEGACY_DECODE = legacy.decode_resource
_LEGACY_ENCODE = legacy.encode_replacement
_LEGACY_DONOR_LOAD = legacy.load_donor_image


def hybrid_decode_resource(raw: bytes, name: str = ""):
    if raw[:4] == b"\0XET":
        return mttex_codec.decode_resource(raw, name)
    return _LEGACY_DECODE(raw, name)


def hybrid_encode_replacement(raw: bytes, name: str, candidate: Image.Image, region: core.Region):
    if raw[:4] == b"\0XET":
        encoded, _meta = mttex_codec.encode_candidate(raw, candidate, region=region)
        return encoded
    return _LEGACY_ENCODE(raw, name, candidate, region)


def hybrid_swap_xet_payload(source_raw: bytes, donor_raw: bytes) -> bytes:
    """Lossless donor swap using the same header interpretation as previews."""
    source = mttex_codec.parse_xet(source_raw)
    donor = mttex_codec.parse_xet(donor_raw)
    signature_source = (source.width, source.height, source.format_code, source.mip_count)
    signature_donor = (donor.width, donor.height, donor.format_code, donor.mip_count)
    if signature_source != signature_donor:
        raise ValueError(
            "donor texture is not byte-layout compatible with the source: "
            f"{signature_donor} != {signature_source}"
        )
    output = bytearray(source_raw)
    for level in range(source.mip_count):
        sw, sh, ssize = source.mip_size(level)
        dw, dh, dsize = donor.mip_size(level)
        if (sw, sh, ssize) != (dw, dh, dsize):
            raise ValueError(f"donor mip {level} geometry differs")
        so = source.mip_offsets[level]
        do = donor.mip_offsets[level]
        output[so:so + ssize] = donor_raw[do:do + dsize]
    return bytes(output)


def hybrid_load_donor_image(archive_path, entry_index):
    archive = core.parse_arc(Path(archive_path))
    if not 0 <= int(entry_index) < len(archive.entries):
        raise ValueError(f"donor entry {entry_index} is outside {archive_path}")
    entry = archive.entries[int(entry_index)]
    raw = core.unpack_entry(entry)
    image, info = hybrid_decode_resource(raw, entry.name)
    return image, info, entry.name


# Inherited methods resolve these names in alrummi3_gui's module globals.
legacy.decode_resource = hybrid_decode_resource
legacy.encode_replacement = hybrid_encode_replacement
legacy.swap_xet_payload = hybrid_swap_xet_payload
legacy.load_donor_image = hybrid_load_donor_image

# Make later imports and the modules already imported by the legacy UI see the
# same codec.  This closes the old failure where the main preview was correct
# but a donor/reference/batch helper decoded the same resource differently.
core.decode_resource = hybrid_decode_resource
core.encode_replacement = hybrid_encode_replacement
core.swap_xet_payload = hybrid_swap_xet_payload
donor_module.load_donor_image = hybrid_load_donor_image
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
        setattr(module, "decode_resource", hybrid_decode_resource)
    if hasattr(module, "encode_replacement"):
        setattr(module, "encode_replacement", hybrid_encode_replacement)
    if hasattr(module, "swap_xet_payload"):
        setattr(module, "swap_xet_payload", hybrid_swap_xet_payload)


# ---------------------------------------------------------------------------
# UI overlay
# ---------------------------------------------------------------------------
class AlrummiHybridApp(legacy.Alrummi3App):
    def __init__(self) -> None:
        self._hybrid_queue: queue.Queue = queue.Queue()
        self._openai_key: str = ""
        self._last_codec_info: dict = {}
        super().__init__()
        self.title("Alrummi 3 — Utage Localization Workshop")
        self.after(120, self._poll_hybrid_queue)

    def _build_style(self) -> None:
        super()._build_style()
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Compact.TButton", padding=(8, 5))
        style.configure("Quick.TLabelframe", background="#24282d")
        style.configure("Quick.TLabelframe.Label", background="#24282d", foreground="#e8eaed", font=("Segoe UI", 9, "bold"))

    def _build_ui(self) -> None:
        """A cleaner shell around the original feature panels."""
        header = tk.Frame(self, bg="#17191c")
        header.pack(fill="x", padx=14, pady=(10, 6))
        ttk.Label(header, text="Alrummi 3", style="Title.TLabel").pack(side="left")
        tk.Label(
            header,
            text="Kuriimu2-correct textures  •  SH donors  •  MSG/dialogue tools",
            bg="#17191c", fg="#9aa3ad", font=("Segoe UI", 9),
        ).pack(side="left", padx=(12, 0), pady=(5, 0))

        ttk.Button(header, text="Open ARC…", command=self.open_arc, style="Compact.TButton").pack(side="right")
        ttk.Button(header, text="Open folder…", command=self.open_folder, style="Compact.TButton").pack(side="right", padx=(0, 6))
        self.autofix_button = ttk.Button(
            header, text="★ Suggested fix", style="Accent.TButton", command=self.suggested_fix
        )
        self.autofix_button.pack(side="right", padx=(0, 8))

        # These attributes are used by the mature backend.  Keep them compact
        # instead of dedicating half of the title bar to status badges.
        self.data_status = ttk.Label(header, text="Dictionary…", style="Muted.TLabel")
        self.data_status.pack(side="right", padx=(0, 8))
        self.ai_status = ttk.Label(header, text="AI: offline", style="Muted.TLabel")
        self.ai_status.pack(side="right", padx=(0, 8))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=3)
        self.body_paned = body
        self._build_browser_panel(body)
        self._build_preview_panel(body)
        super()._build_action_panel(body)
        self._hybrid_rework_action_panel()

        footer = tk.Frame(self, bg="#17191c")
        footer.pack(fill="x", padx=14, pady=(3, 8))
        self.status = ttk.Label(footer, text="", style="Muted.TLabel")
        self.status.pack(side="left", fill="x", expand=True)
        self.loading_label = ttk.Label(footer, text="Ready", style="Muted.TLabel")
        self.loading_label.pack(side="right", padx=(10, 6))
        self.loading_bar = ttk.Progressbar(footer, mode="indeterminate", length=120)
        self.loading_bar.pack(side="right")

    @staticmethod
    def _walk_widgets(widget):
        for child in widget.winfo_children():
            yield child
            yield from AlrummiHybridApp._walk_widgets(child)

    @staticmethod
    def _text_of(widget) -> str:
        try:
            return str(widget.cget("text"))
        except Exception:
            return ""

    def _hybrid_rework_action_panel(self) -> None:
        """Keep every old tool, but make the normal workflow one short tab."""
        self.generation_mode_var.set("Lettering replacement")
        try:
            self.generation_mode.configure(values=("Lettering replacement",))
        except Exception:
            pass
        self.polish_var.set(False)
        self.clear_var.set(True)

        # Remove the generic gold/jade/bronze repainting controls from sight.
        # The functions remain callable from old projects, but they are no
        # longer presented as a recommended localization workflow.
        for widget in list(self._walk_widgets(self.action_notebook)):
            text = self._text_of(widget).strip()
            low = text.lower()
            hide = False
            if text == "Material and depth":
                hide = True
            elif low.startswith("give flat artwork a bevelled edge"):
                hide = True
            elif low.startswith("polish colour and sharpness"):
                hide = True
            elif text in ("Style whole texture", "Style selected box"):
                # Hide the whole button row so it leaves no dead controls.
                try:
                    widget.master.grid_remove()
                except Exception:
                    pass
                hide = True
            elif low.startswith("the recommended mode keeps the full source artwork"):
                hide = True
            elif isinstance(widget, ttk.Combobox):
                try:
                    if str(widget.cget("textvariable")) == str(self.style_var):
                        hide = True
                    elif widget is self.generation_mode:
                        hide = True
                except Exception:
                    pass
            if hide:
                try:
                    widget.grid_remove()
                except Exception:
                    try:
                        widget.pack_forget()
                    except Exception:
                        pass

        # Strength row is an anonymous frame; identify it by its child label.
        for widget in list(self._walk_widgets(self.action_notebook)):
            if isinstance(widget, ttk.Label) and self._text_of(widget) == "Strength":
                try:
                    widget.master.grid_remove()
                except Exception:
                    pass
        try:
            self.style_status.grid_remove()
        except Exception:
            pass

        # Shorten legacy labels which previously described the experimental
        # repainting path.
        for widget in self._walk_widgets(self.action_notebook):
            text = self._text_of(widget)
            if text == "1  Choose how to create the candidate":
                widget.configure(text="Advanced texture repair")
            elif text == "3  Generate visual texture copy":
                widget.configure(text="Create lettering candidate")

        # Rename advanced tabs, then insert the everyday workflow first.
        for tab_id in self.action_notebook.tabs():
            text = self.action_notebook.tab(tab_id, "text")
            rename = {
                "Create texture": "Texture tools",
                "SH donors": "SH donors",
                "Batch": "Texture batch",
                "Dialogue batch": "Dialogue batch",
                "Local chat": "Offline chat",
            }.get(text)
            if rename:
                self.action_notebook.tab(tab_id, text=rename)

        quick = ttk.Frame(self.action_notebook, style="Panel.TFrame", padding=8)
        quick.columnconfigure(0, weight=1)
        self.action_notebook.insert(0, quick, text="Quick fix")
        self._build_quick_tab(quick)
        self.action_notebook.select(0)

    def _build_quick_tab(self, tab) -> None:
        ttk.Label(tab, text="Fix the selected texture", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            tab,
            text=(
                "The source preview uses the Kuriimu2 colour rules. Shift+drag the source around "
                "the lettering/object you want to change. Official SH art is preferred; AI edits "
                "are clipped back to that selected area."
            ),
            style="Muted.TLabel", wraplength=330,
        ).grid(row=1, column=0, sticky="w", pady=(3, 8))

        donor_box = ttk.LabelFrame(tab, text="Best quality first", style="Quick.TLabelframe", padding=7)
        donor_box.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        donor_box.columnconfigure(0, weight=1)
        ttk.Button(
            donor_box, text="Find official Samurai Heroes donor", style="Accent.TButton",
            command=self.quick_find_donor,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            donor_box, text="Uses official localized artwork with no AI repainting when a counterpart exists.",
            style="Muted.TLabel", wraplength=310,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        edit_box = ttk.LabelFrame(tab, text="Selected-area repair", style="Quick.TLabelframe", padding=7)
        edit_box.grid(row=3, column=0, sticky="ew", pady=(0, 7))
        edit_box.columnconfigure(0, weight=1)
        self.quick_wording_var = tk.StringVar()
        ttk.Entry(edit_box, textvariable=self.quick_wording_var).grid(row=0, column=0, sticky="ew")
        self.quick_region_label = ttk.Label(
            edit_box, text="No area selected — Shift+drag on the source preview.",
            style="Muted.TLabel", wraplength=310,
        )
        self.quick_region_label.grid(row=1, column=0, sticky="w", pady=(4, 6))
        ttk.Button(
            edit_box, text="Replace wording locally", command=self.quick_local_lettering
        ).grid(row=2, column=0, sticky="ew")
        ttk.Button(
            edit_box, text="AI image edit — preserve original art", style="Accent.TButton",
            command=self.quick_cloud_edit,
        ).grid(row=3, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(
            edit_box,
            text=(
                "AI image edit is optional. It uses the original /jpn crop as visual reference when "
                "available and pastes only the selected pixels back. API key is kept in memory only."
            ),
            style="Muted.TLabel", wraplength=310,
        ).grid(row=4, column=0, sticky="w", pady=(4, 0))

        handoff = ttk.LabelFrame(tab, text="Work with ChatGPT", style="Quick.TLabelframe", padding=7)
        handoff.grid(row=4, column=0, sticky="ew", pady=(0, 7))
        handoff.columnconfigure(0, weight=1)
        ttk.Button(
            handoff, text="Export one-file ChatGPT repair bundle", command=self.export_chatgpt_bundle
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            handoff,
            text="Bundles the decoded source, /jpn reference, raw XET, selection, candidate and diagnostics.",
            style="Muted.TLabel", wraplength=310,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        candidate_box = ttk.LabelFrame(tab, text="Candidate", style="Quick.TLabelframe", padding=7)
        candidate_box.grid(row=5, column=0, sticky="ew")
        candidate_box.columnconfigure(0, weight=1)
        candidate_box.columnconfigure(1, weight=1)
        ttk.Button(candidate_box, text="Import edited PNG…", command=self.import_candidate_png).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(candidate_box, text="Reset candidate", command=self.reset_hybrid_candidate).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ttk.Button(candidate_box, text="Save candidate PNG…", command=self.save_candidate_image).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

    def _action_tab(self, wanted: str):
        for tab_id in self.action_notebook.tabs():
            if self.action_notebook.tab(tab_id, "text") == wanted:
                return tab_id
        return None

    def quick_find_donor(self) -> None:
        tab = self._action_tab("SH donors")
        if tab:
            self.action_notebook.select(tab)
        self.find_donors()

    def _active_repair_region(self) -> core.Region | None:
        if not getattr(self, "repair_regions", None):
            return None
        try:
            selected = self.repair_list.curselection()
            if selected:
                return self.repair_regions[int(selected[0])]
        except Exception:
            pass
        return self.repair_regions[-1]

    def _sync_quick_wording(self) -> str:
        wording = " ".join(self.quick_wording_var.get().split()).strip()
        if not wording:
            try:
                old = self.translation.get("1.0", "end-1c").strip()
                if old != "English translation / replacement text":
                    wording = " ".join(old.split())
            except Exception:
                pass
        if wording:
            self.translation.delete("1.0", "end")
            self.translation.insert("1.0", wording)
        return wording

    def _select_last_repair(self) -> bool:
        if not self.repair_regions:
            messagebox.showinfo(
                "Alrummi 3",
                "Shift+drag a box over the source texture first. For stylized art, include the whole label/object rather than only a couple of letters.",
            )
            return False
        try:
            self.repair_list.selection_clear(0, "end")
            self.repair_list.selection_set(len(self.repair_regions) - 1)
            self.repair_list.see(len(self.repair_regions) - 1)
        except Exception:
            pass
        return True

    def quick_local_lettering(self) -> None:
        wording = self._sync_quick_wording()
        if not wording:
            messagebox.showinfo("Alrummi 3", "Enter the exact English wording first.")
            return
        if not self._select_last_repair():
            return
        self.letter_box()

    def _get_cloud_key(self) -> str:
        if self._openai_key:
            return self._openai_key
        env_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if env_key:
            self._openai_key = env_key
            return env_key
        key = simpledialog.askstring(
            "Optional OpenAI image edit",
            "Paste an OpenAI API key for this session.\n\nIt is kept in memory only and is not written to Alrummi settings. API usage is billed separately from a ChatGPT subscription.",
            show="•",
            parent=self,
        )
        if key:
            self._openai_key = key.strip()
        return self._openai_key

    def quick_cloud_edit(self) -> None:
        if self.source_image is None:
            messagebox.showinfo("Alrummi 3", "Select a texture first.")
            return
        region = self._active_repair_region()
        if region is None:
            messagebox.showinfo(
                "Alrummi 3",
                "Shift+drag around the whole stylized label/object on the source preview first.",
            )
            return
        wording = self._sync_quick_wording()
        if not wording:
            messagebox.showinfo("Alrummi 3", "Enter the exact English wording first.")
            return
        key = self._get_cloud_key()
        if not key:
            return

        # Give the model the untouched Japanese artwork when possible, but do
        # not replace the whole candidate with Japanese.  Only the selected
        # rectangle is pasted into the current English/source candidate.
        art_source = self.source_image
        if self.reference_image is not None and self.reference_image.size == self.source_image.size:
            art_source = self.reference_image
        base_candidate = (
            self.candidate_image.copy() if self.candidate_image is not None else self.source_image.copy()
        )
        self._set_status("AI image edit running on the selected area…")
        self._busy_jobs += 1
        self._set_busy(True)

        def runner():
            try:
                result = openai_image_edit.edit_region(art_source, region, wording, key)
                self._hybrid_queue.put((True, (result, base_candidate, region)))
            except Exception as exc:
                self._hybrid_queue.put((False, exc))

        threading.Thread(target=runner, daemon=True).start()

    def _poll_hybrid_queue(self) -> None:
        try:
            while True:
                ok, payload = self._hybrid_queue.get_nowait()
                self._busy_jobs = max(0, self._busy_jobs - 1)
                if self._busy_jobs == 0:
                    self._set_busy(False)
                if not ok:
                    self._set_status(f"AI image edit failed: {payload}")
                    messagebox.showerror("Alrummi 3", str(payload))
                    continue
                (generated_crop, context_box, meta), base_candidate, region = payload
                inner = core.Region(
                    region.left - context_box.left,
                    region.top - context_box.top,
                    region.right - context_box.left,
                    region.bottom - context_box.top,
                ).clipped(generated_crop.size)
                piece = generated_crop.crop((inner.left, inner.top, inner.right, inner.bottom))
                if piece.size != (region.width, region.height):
                    piece = piece.resize((region.width, region.height), Image.Resampling.LANCZOS)
                base_candidate.paste(piece, (region.left, region.top))
                self.candidate_image = base_candidate
                self.candidate_meta = meta | {
                    "pasted_region": region.as_list(),
                    "art_reference": "jpn" if self.reference_image is not None else "source",
                }
                self.donor_replacement = None
                self.confirm_var.set(False)
                self.save_candidate_button.configure(state="normal")
                self._update_confirm_state()
                self._draw_preview("candidate")
                self.preview_notebook.select(self.review_tab)
                self._set_status("AI edit returned. Only the selected area was pasted into the candidate; review at 1:1 before writing.")
        except queue.Empty:
            pass
        self.after(120, self._poll_hybrid_queue)

    def import_candidate_png(self) -> None:
        if self.source_image is None:
            messagebox.showinfo("Alrummi 3", "Select a texture first.")
            return
        selected = filedialog.askopenfilename(
            title="Import edited candidate PNG",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            with Image.open(selected) as opened:
                candidate = opened.convert("RGBA")
                candidate.load()
        except Exception as exc:
            messagebox.showerror("Alrummi 3", f"Could not open PNG: {exc}")
            return
        if candidate.size != self.source_image.size:
            messagebox.showerror(
                "Alrummi 3",
                f"Candidate is {candidate.width}×{candidate.height}; source is {self.source_image.width}×{self.source_image.height}. Dimensions must match exactly.",
            )
            return
        self.candidate_image = candidate
        self.candidate_meta = {
            "mode": "imported_png",
            "path": str(selected),
            "dimensions_match": True,
        }
        self.donor_replacement = None
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="normal")
        self._update_confirm_state()
        self._draw_preview("candidate")
        self.preview_notebook.select(self.review_tab)
        self._set_status("Edited PNG imported as candidate. Review the whole texture before writing.")

    def reset_hybrid_candidate(self) -> None:
        self.candidate_image = None
        self.candidate_meta = None
        self.donor_replacement = None
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="disabled")
        self._update_confirm_state()
        self._draw_preview("candidate")
        self._set_status("Candidate cleared; source remains untouched.")

    def _region_release(self, event) -> None:
        super()._region_release(event)
        region = self._active_repair_region()
        if hasattr(self, "quick_region_label"):
            if region:
                self.quick_region_label.configure(
                    text=f"Selected: x={region.left}, y={region.top}, {region.width}×{region.height}px"
                )
            else:
                self.quick_region_label.configure(text="No area selected — Shift+drag on the source preview.")

    def _resource_decoded(self, result) -> None:
        archive, raw, image, info, readable = result
        self._last_codec_info = dict(info or {})
        super()._resource_decoded(result)
        if readable is None and image is not None:
            shader = info.get("display_shader", "none")
            codec = info.get("codec", "legacy")
            self.preview_meta.configure(
                text=(
                    f"{self.source_name}\n{info['container']} {info['format']} · "
                    f"{info['width']}×{info['height']} · shader {shader} · {codec} · "
                    f"{'writable' if info.get('writable') else 'preview only'}"
                )
            )
            self._set_status(
                "Source decoded with the corrected MT Framework colour path. Use Quick fix for normal work; advanced tabs retain the old tools."
            )

    def export_chatgpt_bundle(self) -> None:
        if self.source_image is None or self.source_raw is None or self.selected_entry is None:
            messagebox.showinfo("Alrummi 3", "Select a texture first.")
            return
        region = self._active_repair_region()
        wording = self._sync_quick_wording()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(self.selected_entry.name).name)[:70]
        jobs = legacy.APP_ROOT / "chatgpt_jobs"
        jobs.mkdir(parents=True, exist_ok=True)
        output = jobs / f"{stamp}_{safe_name}.zip"

        metadata = {
            "tool": "Alrummi 3 Hybrid",
            "archive": str(self.archive.path) if self.archive else None,
            "archive_version": self.archive.version if self.archive else None,
            "entry_index": self.selected_entry.index,
            "resource_name": self.selected_entry.name,
            "resource_type_hash": f"0x{self.selected_entry.type_hash:08X}",
            "source_sha256": core.sha256(self.source_raw),
            "source_dimensions": list(self.source_image.size),
            "codec": self._last_codec_info,
            "selection": region.as_list() if region else None,
            "wording": wording or None,
            "candidate_meta": self.candidate_meta,
        }
        request = (
            "ALRUMMI 3 / UTAGE TEXTURE REPAIR\n\n"
            f"Resource: {self.selected_entry.name}\n"
            f"Requested English wording: {wording or '[not supplied]'}\n"
            f"Selected pixel box: {region.as_list() if region else '[none]'}\n\n"
            "Goal: inspect the source texture, original /jpn reference when included, candidate and codec metadata. "
            "Preserve the native Sengoku BASARA artwork, atlas geometry, transparency and dimensions. Prefer an official "
            "Samurai Heroes transplant when one exists. For Utage-exclusive art, change only the Japanese/broken lettering "
            "and keep the original material, borders, lighting and decoration. Do not generically repaint the whole texture. "
            "If returning artwork, return a PNG with exactly the source dimensions and explain which region changed.\n"
        )

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            buf = io.BytesIO(); self.source_image.save(buf, "PNG")
            zf.writestr("source_display.png", buf.getvalue())
            if self.reference_image is not None:
                buf = io.BytesIO(); self.reference_image.save(buf, "PNG")
                zf.writestr("jpn_reference.png", buf.getvalue())
            if self.candidate_image is not None:
                buf = io.BytesIO(); self.candidate_image.save(buf, "PNG")
                zf.writestr("candidate.png", buf.getvalue())
            zf.writestr("resource_raw.xet", self.source_raw)
            zf.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))
            zf.writestr("REQUEST.txt", request)

        try:
            self.clipboard_clear()
            self.clipboard_append(request + f"\nBundle path: {output}")
            self.update_idletasks()
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                os.startfile(jobs)
            except Exception:
                pass
        self._set_status(f"ChatGPT repair bundle created: {output}. Request text copied to clipboard.")
        messagebox.showinfo(
            "ChatGPT bundle ready",
            f"Created:\n{output}\n\nThe request is on your clipboard. Upload this ZIP in the ChatGPT conversation and I can inspect the exact texture/resource.",
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            "About Alrummi 3 Hybrid",
            "Alrummi 3 Hybrid\n\nFeature-complete Alrummi 3 UI with the Kuriimu2-parity PS3 XET decoder/encoder backported from the Next experiment.\n\nGeneric gold/jade repainting is hidden by default; official SH donors and native-art-preserving edits are preferred.",
        )


if __name__ == "__main__":
    app = AlrummiHybridApp()
    app.mainloop()
