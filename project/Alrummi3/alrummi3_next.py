"""Alrummi 3 Next - simplified, codec-first Utage localization workbench.

The old GUI grew around experiments.  This frontend reverses that order:
1. decode exactly like Kuriimu2 first;
2. show the real game artwork;
3. offer only safe actions relevant to the selected resource;
4. review the full candidate;
5. write a new ARC and verify exactly one resource changed.

The legacy GUI remains in the repository for specialist dialogue/batch tools.
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import queue
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else HERE

# Keep the Tcl/Tk staging fix used by the existing build.
if getattr(sys, "frozen", False):
    runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    tcl_dir = runtime_root / "_tcl_data"
    tk_dir = runtime_root / "_tk_data"
else:
    runtime_root = HERE / ".tk-runtime"
    tcl_dir = runtime_root / "tcl8.6"
    tk_dir = runtime_root / "tk8.6"
if (tcl_dir / "init.tcl").is_file():
    os.environ["TCL_LIBRARY"] = str(tcl_dir)
if (tk_dir / "tk.tcl").is_file():
    os.environ["TK_LIBRARY"] = str(tk_dir)

if sys.platform == "win32":
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageTk

from alrummi3_core import (
    ArcArchive,
    ArcEntry,
    Region,
    decode_resource as legacy_decode_resource,
    find_jpn_reference,
    format_gsm_document,
    parse_arc,
    rebuild_arc,
    sha256,
    type_label,
    unpack_entry,
    verify_single_replacement,
    write_audit,
)
import mttex_codec
import native_texture_tools
from donor_index import (
    donor_index_path,
    find_donor_candidates,
    load_donor_index,
    load_donor_raw,
)


BG = "#111418"
PANEL = "#1a1f25"
PANEL2 = "#20262d"
TEXT = "#eef2f4"
MUTED = "#9da8b2"
ACCENT = "#35a666"
WARNING = "#d29a3a"


def _lossless_donor_swap(source_raw: bytes, donor_raw: bytes) -> tuple[bytes, dict]:
    source = mttex_codec.parse_xet(source_raw)
    donor = mttex_codec.parse_xet(donor_raw)
    if (source.width, source.height, source.fourcc, source.mip_count) != (
        donor.width, donor.height, donor.fourcc, donor.mip_count
    ):
        raise ValueError(
            "Lossless donor requires the same dimensions, compression and mip count."
        )
    output = bytearray(source_raw)
    copied = 0
    for level in range(source.mip_count):
        sw, sh, ssize = source.mip_size(level)
        dw, dh, dsize = donor.mip_size(level)
        if (sw, sh, ssize) != (dw, dh, dsize):
            raise ValueError(f"donor mip {level} geometry differs")
        so = source.mip_offsets[level]
        do = donor.mip_offsets[level]
        output[so:so + ssize] = donor_raw[do:do + dsize]
        copied += ssize
    return bytes(output), {
        "mode": "lossless_donor_payload",
        "bytes_copied": copied,
        "mip_count": source.mip_count,
    }


class PreviewPane(ttk.Frame):
    def __init__(self, master, title: str, on_box=None):
        super().__init__(master, style="Panel.TFrame")
        self.on_box = on_box
        self.image: Image.Image | None = None
        self.photo = None
        self.render = None
        self.drag_start = None
        self.region: Region | None = None
        self.title_var = tk.StringVar(value=title)
        head = ttk.Frame(self, style="Panel.TFrame")
        head.pack(fill="x", padx=8, pady=(7, 4))
        ttk.Label(head, textvariable=self.title_var, style="Subhead.TLabel").pack(side="left")
        self.meta = ttk.Label(head, text="", style="Muted.TLabel")
        self.meta.pack(side="right")
        self.canvas = tk.Canvas(self, bg="#0b0d10", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        if on_box:
            self.canvas.bind("<ButtonPress-1>", self._press)
            self.canvas.bind("<B1-Motion>", self._motion)
            self.canvas.bind("<ButtonRelease-1>", self._release)

    def set_image(self, image: Image.Image | None, meta=""):
        self.image = image.copy() if image is not None else None
        self.meta.configure(text=meta)
        self.redraw()

    @staticmethod
    def _checker(image: Image.Image, tile=10):
        rgba = image.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (54, 58, 63, 255))
        draw = ImageDraw.Draw(bg)
        for y in range(0, rgba.height, tile):
            for x in range(0, rgba.width, tile):
                if ((x // tile) + (y // tile)) & 1:
                    draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(76, 81, 87, 255))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")

    def redraw(self):
        self.canvas.delete("all")
        if self.image is None:
            self.canvas.create_text(
                max(10, self.canvas.winfo_width() // 2),
                max(10, self.canvas.winfo_height() // 2),
                text="No texture selected", fill=MUTED, font=("Segoe UI", 12)
            )
            self.render = None
            return
        cw = max(40, self.canvas.winfo_width() - 20)
        ch = max(40, self.canvas.winfo_height() - 20)
        scale = min(cw / self.image.width, ch / self.image.height)
        scale = max(0.05, min(8.0, scale))
        size = (max(1, round(self.image.width * scale)), max(1, round(self.image.height * scale)))
        display = self._checker(self.image).resize(size, Image.Resampling.NEAREST if scale >= 2 else Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(display)
        x = max(10, (self.canvas.winfo_width() - size[0]) // 2)
        y = max(10, (self.canvas.winfo_height() - size[1]) // 2)
        self.canvas.create_image(x, y, image=self.photo, anchor="nw", tags="image")
        self.render = (scale, x, y, size[0], size[1])
        if self.region:
            self._draw_region(self.region)

    def _to_image_xy(self, event):
        if not self.render or self.image is None:
            return None
        scale, ox, oy, rw, rh = self.render
        x = int((event.x - ox) / scale)
        y = int((event.y - oy) / scale)
        return (
            max(0, min(self.image.width - 1, x)),
            max(0, min(self.image.height - 1, y)),
        )

    def _press(self, event):
        point = self._to_image_xy(event)
        if point is not None:
            self.drag_start = point

    def _motion(self, event):
        if self.drag_start is None:
            return
        point = self._to_image_xy(event)
        if point is None:
            return
        x0, y0 = self.drag_start
        x1, y1 = point
        self.region = Region(min(x0, x1), min(y0, y1), max(x0, x1) + 1, max(y0, y1) + 1)
        self.redraw()

    def _release(self, event):
        if self.drag_start is None:
            return
        point = self._to_image_xy(event)
        self.drag_start = None
        if point is None or self.region is None:
            return
        if self.region.width < 2 or self.region.height < 2:
            self.region = None
            self.redraw()
            return
        if self.on_box:
            self.on_box(self.region)

    def _draw_region(self, region):
        if not self.render:
            return
        scale, ox, oy, _rw, _rh = self.render
        self.canvas.create_rectangle(
            ox + region.left * scale,
            oy + region.top * scale,
            ox + region.right * scale,
            oy + region.bottom * scale,
            outline="#62ff9a", width=2, tags="region"
        )


class AlrummiNext(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Alrummi 3 Next — Utage ARC Localizer")
        self.geometry("1540x900")
        self.minsize(1180, 720)
        self.configure(bg=BG)

        self.loaded_archives: list[ArcArchive] = []
        self.archive: ArcArchive | None = None
        self.entry: ArcEntry | None = None
        self.source_raw: bytes | None = None
        self.source_image: Image.Image | None = None
        self.candidate_image: Image.Image | None = None
        self.candidate_raw_override: bytes | None = None
        self.codec_info: dict = {}
        self.selection_region: Region | None = None
        self.donor_index = load_donor_index(donor_index_path(APP_ROOT))
        self.donor_rows: list[dict] = []
        self.last_output: Path | None = None
        self.worker_queue = queue.Queue()
        self.busy = False

        self._style()
        self._ui()
        self.after(100, self._poll)
        self._status("Open an ARC. Texture preview now follows Kuriimu2's PS3 colour rules.")

    def _style(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Subhead.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background=BG, foreground="#70ee9a", font=("Segoe UI", 21, "bold"))
        style.configure("TButton", padding=(10, 7), font=("Segoe UI", 9))
        style.configure("Accent.TButton", background=ACCENT, foreground="white", font=("Segoe UI", 10, "bold"), padding=(10, 8))
        style.map("Accent.TButton", background=[("active", "#43bd77")])
        style.configure("Treeview", background="#101317", fieldbackground="#101317", foreground=TEXT, rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background="#2b323a", foreground=TEXT, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#236544")], foreground=[("selected", "white")])
        style.configure("TNotebook", background=PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 7))

    def _ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=14, pady=(12, 8))
        ttk.Label(header, text="Alrummi 3 Next", style="Title.TLabel").pack(side="left")
        tk.Label(header, text="Kuriimu2-parity codec • native-art editing", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(14, 0), pady=(8, 0))
        ttk.Button(header, text="Open ARC…", command=self.open_arc).pack(side="right")
        ttk.Button(header, text="Open folder…", command=self.open_folder).pack(side="right", padx=(0, 6))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        left = ttk.Frame(body, style="Panel.TFrame", padding=10)
        body.add(left, weight=2)
        self._left(left)

        middle = ttk.Frame(body, style="Panel.TFrame", padding=6)
        body.add(middle, weight=6)
        self._middle(middle)

        right = ttk.Frame(body, style="Panel.TFrame", padding=10)
        body.add(right, weight=3)
        self._right(right)

        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=14, pady=(0, 9))
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(footer, textvariable=self.status_var, bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=150)
        self.progress.pack(side="right")

    def _left(self, panel):
        ttk.Label(panel, text="Files", style="Subhead.TLabel").pack(anchor="w")
        self.archive_var = tk.StringVar()
        self.archive_combo = ttk.Combobox(panel, textvariable=self.archive_var, state="readonly")
        self.archive_combo.pack(fill="x", pady=(7, 6))
        self.archive_combo.bind("<<ComboboxSelected>>", self._archive_selected)
        self.search_var = tk.StringVar()
        search = ttk.Entry(panel, textvariable=self.search_var)
        search.pack(fill="x", pady=(0, 6))
        self.search_var.trace_add("write", lambda *_: self._refresh_tree())

        tree_wrap = ttk.Frame(panel, style="Panel.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        tree_wrap.rowconfigure(0, weight=1); tree_wrap.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_wrap, columns=("idx","type","name"), show="headings")
        self.tree.heading("idx", text="#"); self.tree.heading("type", text="Type"); self.tree.heading("name", text="Resource")
        self.tree.column("idx", width=46, anchor="e", stretch=False)
        self.tree.column("type", width=58, anchor="center", stretch=False)
        self.tree.column("name", width=330, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns"); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._entry_selected)

        self.only_useful = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text="textures + messages only", variable=self.only_useful, command=self._refresh_tree).pack(anchor="w", pady=(6, 0))
        self.archive_meta = ttk.Label(panel, text="No ARC loaded", style="Muted.TLabel", wraplength=360)
        self.archive_meta.pack(fill="x", pady=(9, 0))

    def _middle(self, panel):
        self.tabs = ttk.Notebook(panel)
        self.tabs.pack(fill="both", expand=True)
        work = ttk.Frame(self.tabs, style="Panel.TFrame")
        msg = ttk.Frame(self.tabs, style="Panel.TFrame")
        diag = ttk.Frame(self.tabs, style="Panel.TFrame")
        self.tabs.add(work, text="Texture workshop")
        self.tabs.add(msg, text="Messages")
        self.tabs.add(diag, text="Diagnostics")

        pair = ttk.PanedWindow(work, orient="horizontal")
        pair.pack(fill="both", expand=True)
        self.source_pane = PreviewPane(pair, "Native source — drag to select text", self._box_selected)
        self.candidate_pane = PreviewPane(pair, "Candidate")
        pair.add(self.source_pane, weight=1); pair.add(self.candidate_pane, weight=1)

        self.msg_text = tk.Text(msg, bg="#0f1216", fg=TEXT, insertbackground="white", relief="flat", wrap="word", font=("Consolas", 10))
        self.msg_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.msg_text.configure(state="disabled")

        diag_top = ttk.Frame(diag, style="Panel.TFrame")
        diag_top.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(diag_top, text="Compare Kuriimu2-exported PNG…", command=self.compare_kuriimu_png).pack(side="left")
        self.diag_text = tk.Text(diag, bg="#0f1216", fg="#c9e6d3", relief="flat", wrap="word", font=("Consolas", 10))
        self.diag_text.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.diag_text.configure(state="disabled")

    def _right(self, panel):
        ttk.Label(panel, text="Safe actions", style="Subhead.TLabel").pack(anchor="w")
        ttk.Label(panel, text="The tool now preserves the game's own material artwork. No automatic gold/jade repainting.", style="Muted.TLabel", wraplength=350).pack(anchor="w", pady=(3, 10))

        donor_box = ttk.LabelFrame(panel, text=" Official Samurai Heroes donor ")
        donor_box.pack(fill="x", pady=(0, 10))
        ttk.Button(donor_box, text="Find matching donor", command=self.find_donors).pack(fill="x", padx=7, pady=(7, 5))
        self.donor_list = tk.Listbox(donor_box, bg="#101317", fg=TEXT, selectbackground="#236544", relief="flat", height=5, font=("Consolas", 8), exportselection=False)
        self.donor_list.pack(fill="x", padx=7)
        ttk.Button(donor_box, text="Use selected donor — lossless", style="Accent.TButton", command=self.use_donor).pack(fill="x", padx=7, pady=7)

        edit_box = ttk.LabelFrame(panel, text=" Native artwork editing ")
        edit_box.pack(fill="x", pady=(0, 10))
        ttk.Label(edit_box, text="English wording", style="Muted.TLabel").pack(anchor="w", padx=7, pady=(6, 2))
        self.wording = ttk.Entry(edit_box)
        self.wording.pack(fill="x", padx=7)
        self.region_label = ttk.Label(edit_box, text="Drag a box over source text first.", style="Muted.TLabel", wraplength=330)
        self.region_label.pack(anchor="w", padx=7, pady=(5, 5))
        ttk.Button(edit_box, text="Replace lettering only", command=self.replace_lettering).pack(fill="x", padx=7, pady=(0, 4))
        ttk.Button(edit_box, text="Erase lettering only", command=lambda: self.replace_lettering(erase=True)).pack(fill="x", padx=7, pady=(0, 4))
        ttk.Button(edit_box, text="Fortune cards: relabel, preserve art", command=self.relabel_fortune).pack(fill="x", padx=7, pady=(0, 7))

        candidate_box = ttk.LabelFrame(panel, text=" Candidate ")
        candidate_box.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(candidate_box, style="Panel.TFrame")
        row.pack(fill="x", padx=7, pady=7)
        ttk.Button(row, text="Import PNG…", command=self.import_png).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Reset", command=self.reset_candidate).pack(side="left", fill="x", expand=True, padx=(5, 0))

        out_box = ttk.LabelFrame(panel, text=" Verified ARC output ")
        out_box.pack(fill="x")
        self.reviewed = tk.BooleanVar(value=False)
        ttk.Checkbutton(out_box, text="I reviewed the complete candidate", variable=self.reviewed, command=self._update_write).pack(anchor="w", padx=7, pady=(7, 4))
        self.write_button = ttk.Button(out_box, text="Write NEW verified ARC", style="Accent.TButton", command=self.write_arc, state="disabled")
        self.write_button.pack(fill="x", padx=7, pady=(0, 5))
        self.output_label = ttk.Label(out_box, text="Source ARC is never overwritten.", style="Muted.TLabel", wraplength=330)
        self.output_label.pack(anchor="w", padx=7, pady=(0, 7))

    def _status(self, text):
        self.status_var.set(text)

    def _set_busy(self, value):
        self.busy = value
        if value: self.progress.start(12)
        else: self.progress.stop()

    def _worker(self, name, function):
        if self.busy:
            return
        self._set_busy(True)
        def run():
            try: self.worker_queue.put((name, True, function()))
            except Exception as exc: self.worker_queue.put((name, False, exc))
        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            while True:
                name, ok, value = self.worker_queue.get_nowait()
                self._set_busy(False)
                if not ok:
                    self._status(f"Error: {value}")
                    messagebox.showerror("Alrummi 3 Next", str(value))
                    continue
                getattr(self, f"_done_{name}")(value)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def open_arc(self):
        path = filedialog.askopenfilename(filetypes=[("ARC archive", "*.arc"), ("All files", "*.*")])
        if path:
            self._status("Opening ARC…")
            self._worker("open_arc", lambda: parse_arc(Path(path)))

    def _done_open_arc(self, archive):
        self.loaded_archives = [archive]
        self.archive_combo.configure(values=[str(archive.path)])
        self.archive_combo.current(0)
        self._set_archive(archive)

    def open_folder(self):
        folder = filedialog.askdirectory(title="Open folder containing ARC files")
        if not folder: return
        root = Path(folder)
        def scan():
            archives = []
            errors = []
            for path in sorted(root.rglob("*.arc"), key=lambda p: str(p).lower()):
                try: archives.append(parse_arc(path, metadata_only=True))
                except Exception as exc: errors.append((path, str(exc)))
            return archives, errors
        self._status("Scanning ARC files…")
        self._worker("open_folder", scan)

    def _done_open_folder(self, result):
        archives, errors = result
        if not archives:
            messagebox.showinfo("Alrummi 3 Next", "No readable ARC files found.")
            return
        self.loaded_archives = archives
        self.archive_combo.configure(values=[str(a.path) for a in archives])
        self.archive_combo.current(0)
        self._load_archive_index(0)
        self._status(f"Loaded {len(archives)} ARC headers" + (f"; {len(errors)} skipped" if errors else ""))

    def _archive_selected(self, _event=None):
        index = self.archive_combo.current()
        if index >= 0: self._load_archive_index(index)

    def _load_archive_index(self, index):
        archive = self.loaded_archives[index]
        if not archive.data:
            try:
                archive = parse_arc(archive.path)
                self.loaded_archives[index] = archive
            except Exception as exc:
                messagebox.showerror("Alrummi 3 Next", str(exc)); return
        self._set_archive(archive)

    def _set_archive(self, archive):
        self.archive = archive
        self.entry = None; self.source_raw = None; self.source_image = None
        self.candidate_image = None; self.candidate_raw_override = None
        self.archive_meta.configure(text=f"{archive.path}\n{len(archive.entries)} entries • ARC v{archive.version} • {archive.platform}")
        self._refresh_tree()
        self.source_pane.set_image(None); self.candidate_pane.set_image(None)
        self._show_diag({"archive": str(archive.path), "entries": len(archive.entries)})
        self._update_write()

    def _refresh_tree(self):
        if not hasattr(self, "tree"): return
        self.tree.delete(*self.tree.get_children())
        if not self.archive: return
        query = self.search_var.get().strip().lower()
        for entry in self.archive.entries:
            kind = type_label(entry.type_hash, entry.name)
            if self.only_useful.get() and kind not in ("tex", "texture", "msg"):
                continue
            if query and query not in entry.name.lower() and query not in str(entry.index):
                continue
            self.tree.insert("", "end", iid=str(entry.index), values=(entry.index, kind, entry.name))

    def _entry_selected(self, _event=None):
        if not self.archive: return
        selected = self.tree.selection()
        if not selected: return
        index = int(selected[0])
        self.entry = self.archive.entries[index]
        try:
            self.source_raw = unpack_entry(self.entry)
            if self.source_raw[:4] == b"\0XET":
                image, info = mttex_codec.decode_xet(self.source_raw)
                self.source_image = image
                self.codec_info = info.as_dict()
                self.candidate_image = None; self.candidate_raw_override = None
                shader = info.shader
                self.source_pane.set_image(image, f"{info.width}×{info.height} • {info.fourcc} • {shader}")
                self.candidate_pane.set_image(None)
                self.tabs.select(0)
                self._show_diag({"resource": self.entry.name, **self.codec_info})
                if info.format_code == 0x2A:
                    self._status("Decoded with Kuriimu2 MT YCbCr shader — this is the intended display colour.")
                else:
                    self._status(f"Decoded {self.entry.name}")
            elif type_label(self.entry.type_hash, self.entry.name) == "msg":
                document = format_gsm_document(self.source_raw, name=self.entry.name)
                self._set_msg(document); self.tabs.select(1)
                self._status(f"Opened message resource {self.entry.name}")
            else:
                image, info = legacy_decode_resource(self.source_raw, self.entry.name)
                self.source_image = image; self.codec_info = info
                self.source_pane.set_image(image, f"{image.width}×{image.height}")
                self.tabs.select(0)
        except Exception as exc:
            self.source_image = None
            self.source_pane.set_image(None)
            self._show_diag({"resource": self.entry.name, "error": str(exc)})
            messagebox.showerror("Decode failed", str(exc))
        self.reviewed.set(False); self.selection_region = None; self.source_pane.region = None
        self._update_write()

    def _set_msg(self, text):
        self.msg_text.configure(state="normal"); self.msg_text.delete("1.0", "end")
        self.msg_text.insert("1.0", text); self.msg_text.configure(state="disabled")

    def _show_diag(self, payload):
        self.diag_text.configure(state="normal"); self.diag_text.delete("1.0", "end")
        self.diag_text.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False))
        self.diag_text.configure(state="disabled")

    def _box_selected(self, region):
        self.selection_region = region
        self.source_pane.region = region
        self.region_label.configure(text=f"Selected: X {region.left}, Y {region.top}, {region.width}×{region.height}")

    def reset_candidate(self):
        self.candidate_image = None; self.candidate_raw_override = None
        self.candidate_pane.set_image(None); self.reviewed.set(False); self._update_write()
        self._status("Candidate reset; source untouched.")

    def replace_lettering(self, erase=False):
        if self.source_image is None or self.selection_region is None:
            messagebox.showinfo("Alrummi 3 Next", "Drag a tight box around the lettering in the source preview first.")
            return
        text = "" if erase else self.wording.get().strip()
        if not erase and not text:
            messagebox.showinfo("Alrummi 3 Next", "Enter the English wording first."); return
        base = self.candidate_image or self.source_image
        try:
            image, meta = native_texture_tools.replace_lettering(base, self.selection_region, text)
        except Exception as exc:
            messagebox.showerror("Lettering replacement", str(exc)); return
        self._set_candidate(image, meta)

    def relabel_fortune(self):
        if self.source_image is None:
            messagebox.showinfo("Alrummi 3 Next", "Select the roulette texture first."); return
        raw = self.wording.get().strip()
        labels = [v.strip() for v in raw.replace("|", "\n").splitlines() if v.strip()]
        if len(labels) != 3:
            labels = ["GREAT LUCK", "GOOD LUCK", "BAD LUCK"]
        try:
            image, meta = native_texture_tools.relabel_fortune_cards(self.source_image, labels)
        except Exception as exc:
            messagebox.showerror("Fortune cards", str(exc)); return
        self._set_candidate(image, meta)

    def _set_candidate(self, image, meta):
        self.candidate_image = image
        self.candidate_raw_override = None
        self.candidate_pane.set_image(image, "review before writing")
        self.reviewed.set(False); self._update_write(); self.tabs.select(0)
        self._show_diag({"resource": self.entry.name if self.entry else "", **self.codec_info, "candidate": meta})
        self._status("Candidate ready. Compare the whole texture before writing.")

    def import_png(self):
        if self.source_image is None: return
        path = filedialog.askopenfilename(filetypes=[("PNG", "*.png"), ("Images", "*.png *.bmp *.tga")])
        if not path: return
        try:
            image = Image.open(path).convert("RGBA"); image.load()
            if image.size != self.source_image.size:
                raise ValueError(f"PNG is {image.size}; source is {self.source_image.size}. Dimensions must match.")
        except Exception as exc:
            messagebox.showerror("Import candidate", str(exc)); return
        self._set_candidate(image, {"mode": "imported_png", "path": path})

    def find_donors(self):
        self.donor_list.delete(0, "end"); self.donor_rows = []
        if not self.entry:
            return
        if not self.donor_index:
            messagebox.showinfo("Donor index", "No donor_index.json is available beside the app. Use the legacy donor-index builder once, then Alrummi Next will reuse it.")
            return
        rows = find_donor_candidates(self.donor_index, self.entry.name, source_archive=self.archive.path, limit=20)
        self.donor_rows = rows
        for row in rows:
            self.donor_list.insert("end", f"{Path(row['archive']).name}  #{row['entry_index']}  {row['reason']}")
        self._status(f"Found {len(rows)} donor candidate(s).")

    def use_donor(self):
        if not self.donor_rows or self.source_raw is None:
            return
        sel = self.donor_list.curselection()
        if not sel: messagebox.showinfo("Donor", "Select a donor first."); return
        row = self.donor_rows[sel[0]]
        try:
            donor_raw = load_donor_raw(row["archive"], row["entry_index"])
            image, donor_info = mttex_codec.decode_xet(donor_raw)
            swapped, meta = _lossless_donor_swap(self.source_raw, donor_raw)
            if self.source_image and image.size != self.source_image.size:
                raise ValueError("Donor dimensions differ from source.")
        except Exception as exc:
            messagebox.showerror("Donor", str(exc)); return
        self.candidate_image = image
        self.candidate_raw_override = swapped
        self.candidate_pane.set_image(image, "official donor • lossless payload")
        self.reviewed.set(False); self._update_write(); self.tabs.select(0)
        self._show_diag({"resource": self.entry.name, **self.codec_info, "candidate": meta, "donor": row})
        self._status("Official donor loaded losslessly. Review the entire texture.")

    def compare_kuriimu_png(self):
        if self.source_image is None:
            messagebox.showinfo("Compare", "Select a texture first."); return
        path = filedialog.askopenfilename(title="Select PNG exported by Kuriimu2", filetypes=[("PNG", "*.png")])
        if not path: return
        try:
            other = Image.open(path).convert("RGBA"); other.load()
            result = mttex_codec.compare_images(self.source_image, other)
        except Exception as exc:
            messagebox.showerror("Compare", str(exc)); return
        self._show_diag({"resource": self.entry.name if self.entry else "", **self.codec_info, "kuriimu_png_comparison": result})
        self.tabs.select(2)
        self._status("Kuriimu2 PNG comparison complete.")

    def _update_write(self):
        ready = bool(self.archive and self.entry and self.source_raw and self.candidate_image and self.reviewed.get())
        self.write_button.configure(state="normal" if ready else "disabled")

    def write_arc(self):
        if not (self.archive and self.entry and self.source_raw and self.candidate_image and self.reviewed.get()):
            return
        try:
            if self.candidate_raw_override is not None:
                replacement = self.candidate_raw_override
                encode_meta = {"mode": "lossless donor payload"}
            else:
                replacement, encode_meta = mttex_codec.encode_candidate(self.source_raw, self.candidate_image)

            rebuilt = rebuild_arc(self.archive, {self.entry.index: replacement})
            output = self.archive.path.with_name(self.archive.path.stem + "_ALRUMMI_NEXT.arc")
            output.write_bytes(rebuilt)
            after = parse_arc(output)
            verify = verify_single_replacement(self.archive, after, self.entry.index)
            audit = {
                "tool": "Alrummi 3 Next",
                "source": str(self.archive.path),
                "output": str(output),
                "resource": self.entry.name,
                "entry_index": self.entry.index,
                "codec": self.codec_info,
                "encoding": encode_meta,
                "verification": verify,
                "source_resource_sha256": sha256(self.source_raw),
                "replacement_resource_sha256": sha256(replacement),
            }
            audit_path = output.with_suffix(output.suffix + ".audit.json")
            write_audit(audit_path, audit)
            self.last_output = output
            self.output_label.configure(text=f"Verified output:\n{output.name}\nAudit: {audit_path.name}")
            self._status(f"PASS — wrote {output.name}; exactly entry {self.entry.index} changed.")
            messagebox.showinfo("Verified ARC written", f"Created:\n{output}\n\nVerification passed: exactly one resource changed.")
        except Exception as exc:
            messagebox.showerror("Write failed safely", str(exc))
            self._status(f"Write refused: {exc}")


def main():
    app = AlrummiNext()
    app.mainloop()


if __name__ == "__main__":
    main()
