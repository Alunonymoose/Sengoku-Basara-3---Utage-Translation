"""Alrummi 3 - an offline AI-assisted ARC texture localization workbench."""

from __future__ import annotations

import io
import json
import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# The local Python install has Tcl/Tk files under AppData, which Tcl can list
# but cannot stat on this machine.  The build script stages the runtime in the
# bundle, and these paths must be set before tkinter imports _tkinter.
HERE = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    _tk_runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    _tk_tcl_dir = _tk_runtime_root / "_tcl_data"
    _tk_tk_dir = _tk_runtime_root / "_tk_data"
else:
    _tk_runtime_root = HERE / ".tk-runtime"
    _tk_tcl_dir = _tk_runtime_root / "tcl8.6"
    _tk_tk_dir = _tk_runtime_root / "tk8.6"
if (_tk_tcl_dir / "init.tcl").is_file():
    os.environ["TCL_LIBRARY"] = str(_tk_tcl_dir)
if (_tk_tk_dir / "tk.tcl").is_file():
    os.environ["TK_LIBRARY"] = str(_tk_tk_dir)

# Windows stretches a DPI-unaware window as a bitmap, which is why the text
# looks soft on a scaled display.  Declaring awareness before Tk starts makes
# it render at native resolution instead.
if sys.platform == "win32":
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor v1
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

import file_notes
import install as installer
import ui_state
import msg_batch
import msg_edit
import autofix
import layout as layout_mod
import ocr
import sheet
import texture_fx
import medallion_fx
from batch import apply_batch, plan_batch
from project_dict import load_dictionary, load_roster, lookup as dict_lookup, search as dict_search
from character_map import (
    DEFAULT_LOCAL_ROOTS,
    build_character_map,
    character_map_path,
    load_character_map,
    local_index_path,
    save_character_map,
    translate_resource,
)
from donor_index import (
    DEFAULT_DONOR_ROOTS,
    build_donor_index,
    donor_index_path,
    find_donor_candidates,
    fit_donor_image,
    load_donor_image,
    load_donor_index,
    load_donor_raw,
    save_donor_index,
)

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else HERE
sys.path.insert(0, str(HERE))

from alrummi3_core import (  # noqa: E402
    ArcArchive,
    ArcEntry,
    CSA_HASH,
    FIM_HASH,
    MSG_HASH,
    Region,
    decode_resource,
    encode_replacement,
    entry_report,
    find_jpn_reference,
    format_gsm_document,
    generate_candidate,
    generate_visual_copy,
    is_message_name,
    is_texture_name,
    parse_arc,
    rebuild_arc,
    erase_region,
    patch_region_from,
    render_text_in_region,
    sha256,
    swap_xet_payload,
    type_label,
    unpack_entry,
    verify_single_replacement,
    write_audit,
)
from ollama_client import LocalAIError, OllamaClient  # noqa: E402
from ai_extensions import discover_extensions  # noqa: E402


def _sheet_audit(name, assets, notes, layout, inventory,
                 *, relettered: bool = False) -> list[str]:
    """What was found on this sheet, what was rebuilt, and what still needs a
    decision — written so it can be acted on rather than just read."""

    ready = [a for a in assets if a.ready]
    finished = [a for a in assets if a.done]
    stuck = [a for a in assets if not a.ready and not a.done]
    route = ("Route: re-letter — this sheet is already English, so its own "
             "wording was redrawn." if relettered
             else "Route: rebuild the sheet asset by asset.")
    lines = [f"SUGGESTED FIX — {name}", "", route, ""]
    if relettered:
        lines.append("Use this when an earlier patch pasted its text over the "
                     "artwork. If the sheet is already good, do not confirm.")
        lines.append("")

    if inventory:
        lines.extend(inventory)
        lines.append("")
    elif layout is None:
        lines.append("No layout in this archive names this texture, so the "
                     "sprites below were found by reading the sheet itself.")
        lines.append("")

    if finished and not stuck and not ready:
        lines.append(f"This sheet is already in English — all {len(finished)} "
                     "asset(s) read back as English text. Nothing to do.")
        lines.append("")
        lines.append("If you meant to work on the Japanese original, open the "
                     "same archive under the jpn tree.")
        for asset in finished:
            lines.append(f"  done    {asset.describe()}")
        return lines

    summary = f"{len(assets)} asset(s) recognised, {len(ready)} rebuilt in English"
    if finished:
        summary += f", {len(finished)} already English"
    lines.append(summary + ".")
    lines.append("")
    for asset in assets:
        mark = "rebuilt " if asset.ready else ("done    " if asset.done else "left    ")
        lines.append(f"  {mark}{asset.describe()}")

    if stuck:
        lines.extend(["", "Still to do:"])
        for asset in stuck:
            why = asset.note or "no English wording available"
            where = f"({asset.box.left},{asset.box.top}) " \
                    f"{asset.box.width}x{asset.box.height}"
            lines.append(f"  {where}  {asset.japanese or '(unread)'} — {why}")
        lines.append("")
        lines.append("Add the wording to the project dictionary, or letter the "
                     "box by hand in the Create texture tab.")

    if notes:
        lines.extend(["", "Detail:"])
        lines.extend(f"  {line}" for line in notes)
    return lines


class Alrummi3App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Alrummi 3 — Offline ARC Texture Localizer")
        self.geometry("1480x900")
        self.minsize(1180, 720)
        self.configure(bg="#17191c")

        self.archive: ArcArchive | None = None
        self.loaded_archives: list[ArcArchive] = []
        self.current_archive_index = 0
        self.selected_entry: ArcEntry | None = None
        self.source_raw: bytes | None = None
        self.source_image: Image.Image | None = None
        self.candidate_image: Image.Image | None = None
        self.reference_image: Image.Image | None = None
        self.reference_info: dict | None = None
        self.reference_archive: ArcArchive | None = None
        self.reference_entry: ArcEntry | None = None
        self.candidate_meta: dict | None = None
        self.source_photo: ImageTk.PhotoImage | None = None
        self.candidate_photo: ImageTk.PhotoImage | None = None
        self.reference_photo: ImageTk.PhotoImage | None = None
        self.zoom_var = tk.DoubleVar(value=1.0)
        self.preview_render: dict[str, tuple[float, int, int]] = {}
        self.msg_source: str = ""
        self.source_name: str = ""
        self.source_path: Path | None = None
        self.chat_history: list[dict] = []
        self._busy_jobs = 0
        self._scan_progress: tuple[int, int] = (0, 0)
        self._progress_label = 'Working'
        self.donor_index: dict | None = None
        self.donor_candidates: list[dict] = []
        self.donor_replacement: bytes | None = None
        self.character_map: dict | None = None
        self.project_dictionary: dict[str, str] = {}
        self.project_roster: dict[int, list[str]] = {}
        self.batch_rows: list[dict] = []
        self.batch_source_root: Path | None = None
        self.glyph_maps: dict[str, dict[int, str]] | None = None
        self.dialogue_rows: list[dict] = []
        self.dialogue_view: list[int] = []
        self.dialogue_path: Path | None = None
        self.dialogue_survey: list[dict] = []
        self.dialogue_view_rows: list[int] = []
        self._region_drag: tuple[float, float] | None = None
        self.repair_regions: list[Region] = []
        self.MAX_ARCHIVE_TABS = 16
        self._tab_frames: list = []
        self._suppress_tab_event = False
        self.settings = ui_state.load(APP_ROOT)
        self.zoom_mode = str(self.settings.get("zoom_mode", "fit"))
        # Not 0.0: that makes the first autosave fire on the very first poll,
        # 120ms after launch, which stores whatever half-built layout exists
        # at that instant and then treats it as the operator's choice.
        self._last_layout_save = time.time()
        self.popouts: dict[str, tk.Toplevel] = {}
        self._sash_touched: set[str] = set()
        self.last_written: Path | None = None
        self.last_written_target: Path | None = None
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.ai = OllamaClient()
        self.extensions = discover_extensions(APP_ROOT)
        self.texture_rows: list[ArcEntry] = []
        self._build_style()
        self._build_ui()
        self._build_menu()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._install_shortcuts()
        self.after(60, self._restore_layout)
        self._refresh_donor_index_label()
        self._refresh_character_map_label()
        self.project_dictionary = load_dictionary(APP_ROOT)
        self.project_roster = load_roster(APP_ROOT)
        if self.project_dictionary:
            self.data_status.configure(text=f"Dictionary: {len(self.project_dictionary)} entries")
            self._set_status(
                f"Loaded the project dictionary: {len(self.project_dictionary)} translations, "
                f"{len(self.project_roster)} roster names. Open an ARC to begin."
            )
        else:
            # Falling back to model guesses silently is how "Sakata Yoshitaka"
            # reached the screen, so say it loudly instead.
            self.data_status.configure(text="Dictionary: NOT LOADED")
            self._set_status(
                "WARNING: project_data/ was not found beside the app, so translations "
                "will be unverified model guesses. Copy project_data next to the "
                "executable, or run refresh_project_data.py."
            )
        self.after(120, self._poll_worker)
        self._set_status("Open an ARC to begin. Alrummi 3 is offline-first and never edits the source archive automatically.")

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#202327")
        style.configure("Panel.TFrame", background="#24282d")
        style.configure("TLabel", background="#24282d", foreground="#e8eaed")
        style.configure("Muted.TLabel", background="#24282d", foreground="#9aa3ad")
        style.configure("Title.TLabel", background="#17191c", foreground="#8cff8c", font=("Segoe UI", 19, "bold"))
        style.configure("TButton", padding=(10, 6))
        style.configure("Accent.TButton", background="#2d8b57", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#3ca96d")])
        style.configure("Danger.TButton", background="#a44848", foreground="white", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", background="#17191c", fieldbackground="#17191c", foreground="#e8eaed", rowheight=25)
        style.configure("Treeview.Heading", background="#30353b", foreground="#e8eaed")
        style.map("Treeview", background=[("selected", "#286448")], foreground=[("selected", "white")])

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg="#17191c")
        header.pack(fill="x", padx=16, pady=(14, 8))
        ttk.Label(header, text="Alrummi 3", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="offline AI-assisted texture workshop", style="Muted.TLabel").pack(side="left", padx=(14, 0), pady=(5, 0))
        ttk.Button(header, text="Open ARC…", command=self.open_arc).pack(side="right")
        ttk.Button(header, text="Open Folder…", command=self.open_folder).pack(side="right", padx=(0, 8))
        ttk.Button(header, text="Open Image…", command=self.open_image).pack(side="right", padx=(0, 8))
        ttk.Button(header, text="Open MSG…", command=self.open_msg).pack(side="right", padx=(0, 8))
        ttk.Button(header, text=f"Extensions ({len(self.extensions)})", command=self.show_extensions).pack(side="right", padx=(0, 8))
        ttk.Button(header, text="Reset layout", command=self.reset_layout).pack(side="right", padx=(0, 8))
        self.autofix_button = ttk.Button(header, text="★ Suggested fix", style="Accent.TButton", command=self.suggested_fix)
        self.autofix_button.pack(side="right", padx=(0, 10))
        self.data_status = ttk.Label(header, text="Dictionary: checking…", style="Muted.TLabel")
        self.data_status.pack(side="right", padx=(0, 12))
        self.ai_status = ttk.Label(header, text="AI: not checked", style="Muted.TLabel")
        self.ai_status.pack(side="right", padx=(0, 14), pady=(5, 0))

        # Three resizable panes rather than fixed columns: drag the dividers
        # to give the preview the room a 1024-wide texture actually needs.
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=4)
        self.body_paned = body

        self._build_browser_panel(body)
        self._build_preview_panel(body)
        self._build_action_panel(body)

        footer = tk.Frame(self, bg="#17191c")
        footer.pack(fill="x", padx=16, pady=(4, 10))
        self.status = ttk.Label(footer, text="", style="Muted.TLabel")
        self.status.pack(side="left", fill="x", expand=True)
        self.loading_label = ttk.Label(footer, text="Ready", style="Muted.TLabel")
        self.loading_label.pack(side="right", padx=(12, 8))
        self.loading_bar = ttk.Progressbar(footer, mode="indeterminate", length=150)
        self.loading_bar.pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Check Local AI", command=self.check_ai).pack(side="right")

    def _build_browser_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        parent.add(panel, weight=2)
        panel.rowconfigure(5, weight=1)
        panel.columnconfigure(0, weight=1)
        title_row = ttk.Frame(panel, style="Panel.TFrame")
        title_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(title_row, text="ARC contents", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(title_row, text="Close archive", command=self.close_current_archive).pack(side="right")
        self.archive_var = tk.StringVar()
        self.archive_combo = ttk.Combobox(panel, textvariable=self.archive_var, state="readonly")
        self.archive_combo.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        self.archive_combo.bind("<<ComboboxSelected>>", self._archive_changed)
        # One tab per open archive, as a file editor would do it.
        self.archive_tabs = ttk.Notebook(panel)
        self.archive_tabs.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.archive_tabs.bind("<<NotebookTabChanged>>", self._archive_tab_selected)
        self.archive_tabs.grid_remove()
        self.archive_tab_note = ttk.Label(panel, text="", style="Muted.TLabel", wraplength=360)
        self.archive_tab_note.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.archive_tab_note.grid_remove()
        self.search_var = tk.StringVar()
        search = ttk.Entry(panel, textvariable=self.search_var)
        self.search_entry = search
        search.grid(row=4, column=0, sticky="ew", pady=(7, 5))
        search.insert(0, "search names or indices…")
        search.bind("<FocusIn>", lambda _event: self._clear_placeholder(search))
        self.search_var.trace_add("write", lambda *_args: self._refresh_entries())

        tree_frame = ttk.Frame(panel, style="Panel.TFrame")
        tree_frame.grid(row=5, column=0, sticky="nsew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.entry_tree = ttk.Treeview(tree_frame, columns=("idx", "kind", "name"), show="headings", selectmode="browse")
        self.entry_tree.heading("idx", text="#")
        self.entry_tree.heading("kind", text="Type")
        self.entry_tree.heading("name", text="Resource")
        self.entry_tree.column("idx", width=45, anchor="e", stretch=False)
        self.entry_tree.column("kind", width=72, anchor="center", stretch=False)
        self.entry_tree.column("name", width=300, anchor="w")
        self.entry_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.entry_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.entry_tree.configure(yscrollcommand=scrollbar.set)
        self.entry_tree.bind("<<TreeviewSelect>>", self._entry_selected)

        self.filter_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text="textures + messages only", variable=self.filter_var, command=self._refresh_entries).grid(row=6, column=0, sticky="w", pady=(7, 0))
        self.archive_label = ttk.Label(panel, text="No archive loaded", style="Muted.TLabel", wraplength=360)
        self.archive_label.grid(row=7, column=0, sticky="w", pady=(10, 0))

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        parent.add(panel, weight=5)
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="Review", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        tools = ttk.Frame(panel, style="Panel.TFrame")
        tools.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        ttk.Button(tools, text="−", width=3, command=lambda: self._set_zoom(self.zoom_var.get() - 0.25)).pack(side="left")
        ttk.Button(tools, text="Fit", command=lambda: self.set_zoom_mode("fit")).pack(side="left", padx=(4, 0))
        ttk.Button(tools, text="1:1", command=lambda: self.set_zoom_mode("actual")).pack(side="left", padx=(4, 0))
        ttk.Button(tools, text="Fill", command=lambda: self.set_zoom_mode("fill")).pack(side="left", padx=(4, 0))
        self.zoom_scale = ttk.Scale(tools, from_=0.25, to=4.0, variable=self.zoom_var, command=self._zoom_changed, length=220)
        self.zoom_scale.pack(side="left", padx=8)
        ttk.Button(tools, text="+", width=3, command=lambda: self._set_zoom(self.zoom_var.get() + 0.25)).pack(side="left")
        self.zoom_label = ttk.Label(tools, text="Zoom 1.00×", style="Muted.TLabel")
        self.zoom_label.pack(side="left", padx=(8, 0))
        self.cursor_label = ttk.Label(tools, text="", style="Muted.TLabel")
        self.cursor_label.pack(side="right", padx=(8, 0))
        ttk.Label(tools, text="Ctrl+wheel zoom · drag pan · shift+drag box", style="Muted.TLabel").pack(side="right")

        self.preview_notebook = ttk.Notebook(panel)
        self.preview_notebook.grid(row=2, column=0, sticky="nsew", pady=(0, 4))
        self.review_tab = ttk.Frame(self.preview_notebook, style="Panel.TFrame")
        self.msg_tab = ttk.Frame(self.preview_notebook, style="Panel.TFrame")
        self.reference_tab = ttk.Frame(self.preview_notebook, style="Panel.TFrame")
        self.preview_notebook.add(self.review_tab, text="Texture review")
        self.preview_notebook.add(self.msg_tab, text="MSG reader")
        self.dialogue_tab = ttk.Frame(self.preview_notebook, style="Panel.TFrame")
        self.preview_notebook.add(self.reference_tab, text="JPN reference")
        self.notes_tab = ttk.Frame(self.preview_notebook, style="Panel.TFrame")
        self.preview_notebook.add(self.dialogue_tab, text="Dialogue editor")
        self.log_tab = ttk.Frame(self.preview_notebook, style="Panel.TFrame")
        self.preview_notebook.add(self.notes_tab, text="File notes")
        self.preview_notebook.add(self.log_tab, text="Log")
        log_frame = ttk.Frame(self.log_tab, style="Panel.TFrame")
        log_frame.pack(fill="both", expand=True, padx=8, pady=8)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame, bg="#101214", fg="#b7c7bd", relief="flat", wrap="word",
            font=("Consolas", 9), state="disabled",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_buttons = ttk.Frame(self.log_tab, style="Panel.TFrame")
        log_buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(log_buttons, text="Copy log", command=self.copy_log).pack(side="left")
        ttk.Button(log_buttons, text="Clear", command=self.clear_log).pack(side="left", padx=(6, 0))
        notes_frame = ttk.Frame(self.notes_tab, style="Panel.TFrame")
        notes_frame.pack(fill="both", expand=True, padx=8, pady=8)
        notes_frame.rowconfigure(0, weight=1)
        notes_frame.columnconfigure(0, weight=1)
        self.notes_text = tk.Text(
            notes_frame, bg="#17191c", fg="#e8eaed", relief="flat", wrap="word",
            font=("Segoe UI", 10), insertbackground="white",
        )
        self.notes_text.grid(row=0, column=0, sticky="nsew")
        notes_scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=self.notes_text.yview)
        notes_scroll.grid(row=0, column=1, sticky="ns")
        self.notes_text.configure(yscrollcommand=notes_scroll.set)
        ttk.Button(self.notes_tab, text="Find copies of this resource across both games", command=self.find_resource_copies).pack(fill="x", padx=8, pady=(0, 8))

        dialogue = self.dialogue_tab
        dialogue.columnconfigure(0, weight=1)
        dialogue.rowconfigure(2, weight=3)
        dialogue.rowconfigure(5, weight=2)

        dtools = ttk.Frame(dialogue, style="Panel.TFrame")
        dtools.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ttk.Button(dtools, text="Open dialogue archive…", command=self.open_dialogue).pack(side="left")
        ttk.Button(dtools, text="Fill from dictionary", command=self.fill_dialogue_from_dictionary).pack(side="left", padx=(6, 0))
        ttk.Label(dtools, text="Show", style="Muted.TLabel").pack(side="left", padx=(12, 4))
        self.dialogue_filter = tk.StringVar(value="Needs wording")
        filter_box = ttk.Combobox(
            dtools,
            textvariable=self.dialogue_filter,
            state="readonly",
            width=16,
            values=("All", "Needs wording", "Signed off", "Not signed off", "Problems"),
        )
        filter_box.pack(side="left")
        filter_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_dialogue_list())
        ttk.Button(dtools, text="Sign off all filled", command=self.sign_off_filled).pack(side="left", padx=(8, 0))
        self.dialogue_coverage = ttk.Label(dialogue, text="No dialogue archive open.", style="Muted.TLabel", wraplength=760)
        self.dialogue_coverage.grid(row=1, column=0, sticky="w", padx=8)

        dlist_frame = ttk.Frame(dialogue, style="Panel.TFrame")
        dlist_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 4))
        dlist_frame.rowconfigure(0, weight=1)
        dlist_frame.columnconfigure(0, weight=1)
        self.dialogue_list = tk.Listbox(
            dlist_frame, bg="#17191c", fg="#e8eaed", selectbackground="#1f6f3f",
            relief="flat", exportselection=False, font=("Consolas", 9),
        )
        self.dialogue_list.grid(row=0, column=0, sticky="nsew")
        dscroll = ttk.Scrollbar(dlist_frame, orient="vertical", command=self.dialogue_list.yview)
        dscroll.grid(row=0, column=1, sticky="ns")
        self.dialogue_list.configure(yscrollcommand=dscroll.set)
        self.dialogue_list.bind("<<ListboxSelect>>", self._dialogue_selected)

        ttk.Label(dialogue, text="Japanese", style="Muted.TLabel").grid(row=3, column=0, sticky="w", padx=8)
        self.dialogue_jp = tk.Text(dialogue, height=3, bg="#101214", fg="#c8ffd0", relief="flat", wrap="word", font=("Segoe UI", 10))
        self.dialogue_jp.grid(row=4, column=0, sticky="ew", padx=8)
        self.dialogue_jp.configure(state="disabled")
        english_head = ttk.Frame(dialogue, style="Panel.TFrame")
        english_head.grid(row=5, column=0, sticky="ew", padx=8, pady=(6, 0))
        ttk.Label(english_head, text="English (41 columns, 3 lines on the plate)", style="Muted.TLabel").pack(side="left")
        self.dialogue_problems = ttk.Label(english_head, text="", style="Muted.TLabel")
        self.dialogue_problems.pack(side="left", padx=(10, 0))
        self.dialogue_en = tk.Text(dialogue, height=4, bg="#17191c", fg="#e8eaed", insertbackground="white", relief="flat", wrap="none", font=("Consolas", 10))
        self.dialogue_en.grid(row=6, column=0, sticky="nsew", padx=8, pady=(2, 4))
        self.dialogue_en.bind("<KeyRelease>", lambda _e: self._dialogue_validate_live())
        dbuttons = ttk.Frame(dialogue, style="Panel.TFrame")
        dbuttons.grid(row=7, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(dbuttons, text="Apply + sign off  (Ctrl+Enter)", style="Accent.TButton", command=self.apply_dialogue_edit).pack(side="left")
        ttk.Button(dbuttons, text="Apply only", command=lambda: self.apply_dialogue_edit(sign_off=False)).pack(side="left", padx=(6, 0))
        ttk.Button(dbuttons, text="Build English archive…", style="Danger.TButton", command=self.build_dialogue_archive).pack(side="right")
        self.dialogue_en.bind("<Control-Return>", lambda _e: (self.apply_dialogue_edit(), "break")[1])

        review = self.review_tab
        review.columnconfigure(0, weight=1)
        review.rowconfigure(0, weight=1)
        # Source and candidate share a draggable divider, so either side can be
        # given the whole width when you want to study one of them.
        review_paned = ttk.PanedWindow(review, orient="horizontal")
        review_paned.grid(row=0, column=0, sticky="nsew")
        self.review_paned = review_paned
        source_wrap = ttk.Frame(review_paned, style="Panel.TFrame")
        candidate_wrap = ttk.Frame(review_paned, style="Panel.TFrame")
        review_paned.add(source_wrap, weight=1)
        review_paned.add(candidate_wrap, weight=1)
        for wrap, title, which in (
            (source_wrap, "Japanese source", "source"),
            (candidate_wrap, "English candidate", "candidate"),
        ):
            wrap.rowconfigure(1, weight=1)
            wrap.columnconfigure(0, weight=1)
            head = ttk.Frame(wrap, style="Panel.TFrame")
            head.grid(row=0, column=0, sticky="ew", pady=(4, 4))
            ttk.Label(head, text=title, style="Muted.TLabel").pack(side="left", padx=(4, 0))
            ttk.Button(head, text="⧉", width=3,
                       command=lambda w=which: self.popout_preview(w)).pack(side="right", padx=(0, 4))
        source_view = ttk.Frame(source_wrap, style="Panel.TFrame")
        source_view.grid(row=1, column=0, sticky="nsew", padx=(0, 3))
        source_view.rowconfigure(0, weight=1)
        source_view.columnconfigure(0, weight=1)
        candidate_view = ttk.Frame(candidate_wrap, style="Panel.TFrame")
        candidate_view.grid(row=1, column=0, sticky="nsew", padx=(3, 0))
        candidate_view.rowconfigure(0, weight=1)
        candidate_view.columnconfigure(0, weight=1)
        self.source_canvas = tk.Canvas(source_view, bg="#343a40", highlightthickness=0, xscrollincrement=20, yscrollincrement=20)
        self.source_canvas.grid(row=0, column=0, sticky="nsew")
        self.candidate_canvas = tk.Canvas(candidate_view, bg="#343a40", highlightthickness=0, xscrollincrement=20, yscrollincrement=20)
        self.candidate_canvas.grid(row=0, column=0, sticky="nsew")
        source_x = ttk.Scrollbar(source_view, orient="horizontal", command=self.source_canvas.xview)
        source_y = ttk.Scrollbar(source_view, orient="vertical", command=self.source_canvas.yview)
        source_x.grid(row=1, column=0, sticky="ew")
        source_y.grid(row=0, column=1, sticky="ns")
        candidate_x = ttk.Scrollbar(candidate_view, orient="horizontal", command=self.candidate_canvas.xview)
        candidate_y = ttk.Scrollbar(candidate_view, orient="vertical", command=self.candidate_canvas.yview)
        candidate_x.grid(row=1, column=0, sticky="ew")
        candidate_y.grid(row=0, column=1, sticky="ns")
        self.source_canvas.configure(xscrollcommand=source_x.set, yscrollcommand=source_y.set)
        self.candidate_canvas.configure(xscrollcommand=candidate_x.set, yscrollcommand=candidate_y.set)
        self.source_canvas.bind("<Configure>", lambda _event: self._draw_preview("source"))
        self.candidate_canvas.bind("<Configure>", lambda _event: self._draw_preview("candidate"))
        for canvas in (self.source_canvas, self.candidate_canvas):
            canvas.bind("<ButtonPress-1>", lambda event, target=canvas: target.scan_mark(event.x, event.y))
            canvas.bind("<B1-Motion>", lambda event, target=canvas: target.scan_dragto(event.x, event.y, gain=1))
            canvas.bind("<Control-MouseWheel>", self._preview_wheel)
        # Tk prefers the more specific binding, so shift+drag selects a region
        # on the source without disturbing plain drag-to-pan.
        for canvas, which in (
            (self.source_canvas, "source"),
            (self.candidate_canvas, "candidate"),
        ):
            canvas.bind("<Motion>", lambda e, w=which: self._preview_motion(e, w))
            canvas.bind("<Leave>", lambda _e: self.cursor_label.configure(text=""))
        self.source_canvas.bind("<Shift-ButtonPress-1>", self._region_press)
        self.source_canvas.bind("<Shift-B1-Motion>", self._region_motion)
        self.source_canvas.bind("<Shift-ButtonRelease-1>", self._region_release)

        msg_tools = ttk.Frame(self.msg_tab, style="Panel.TFrame")
        msg_tools.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(msg_tools, text="Open MSG…", command=self.open_msg).pack(side="left")
        ttk.Button(msg_tools, text="Save readable TXT…", command=self.save_msg_text).pack(side="left", padx=(6, 0))
        self.msg_source_label = ttk.Label(msg_tools, text="No MSG loaded", style="Muted.TLabel")
        self.msg_source_label.pack(side="left", padx=(12, 0))
        msg_frame = ttk.Frame(self.msg_tab, style="Panel.TFrame")
        msg_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        msg_frame.rowconfigure(0, weight=1)
        msg_frame.columnconfigure(0, weight=1)
        self.msg_text = tk.Text(msg_frame, bg="#17191c", fg="#e8eaed", insertbackground="white", relief="flat", wrap="none", font=("Consolas", 10), undo=False)
        self.msg_text.grid(row=0, column=0, sticky="nsew")
        msg_y = ttk.Scrollbar(msg_frame, orient="vertical", command=self.msg_text.yview)
        msg_y.grid(row=0, column=1, sticky="ns")
        msg_x = ttk.Scrollbar(msg_frame, orient="horizontal", command=self.msg_text.xview)
        msg_x.grid(row=1, column=0, sticky="ew")
        self.msg_text.configure(yscrollcommand=msg_y.set, xscrollcommand=msg_x.set)

        reference = self.reference_tab
        reference.rowconfigure(1, weight=1)
        reference.columnconfigure(0, weight=1)
        self.reference_label = ttk.Label(reference, text="No matching /jpn resource found yet.", style="Muted.TLabel", wraplength=760)
        self.reference_label.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        reference_view = ttk.Frame(reference, style="Panel.TFrame")
        reference_view.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        reference_view.rowconfigure(0, weight=1)
        reference_view.columnconfigure(0, weight=1)
        self.reference_canvas = tk.Canvas(reference_view, bg="#343a40", highlightthickness=0, xscrollincrement=20, yscrollincrement=20)
        self.reference_canvas.grid(row=0, column=0, sticky="nsew")
        reference_y = ttk.Scrollbar(reference_view, orient="vertical", command=self.reference_canvas.yview)
        reference_y.grid(row=0, column=1, sticky="ns")
        reference_x = ttk.Scrollbar(reference_view, orient="horizontal", command=self.reference_canvas.xview)
        reference_x.grid(row=1, column=0, sticky="ew")
        self.reference_canvas.configure(xscrollcommand=reference_x.set, yscrollcommand=reference_y.set)
        self.reference_canvas.bind("<Configure>", lambda _event: self._draw_preview("reference"))
        self.reference_canvas.bind("<ButtonPress-1>", lambda event: self.reference_canvas.scan_mark(event.x, event.y))
        self.reference_canvas.bind("<B1-Motion>", lambda event: self.reference_canvas.scan_dragto(event.x, event.y, gain=1))
        self.reference_canvas.bind("<Control-MouseWheel>", self._preview_wheel)

        self.preview_meta = ttk.Label(panel, text="Select a decodable XET/image resource.", style="Muted.TLabel", wraplength=760)
        self.preview_meta.grid(row=3, column=0, sticky="w", pady=(4, 0))

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        parent.add(panel, weight=3)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        ttk.Label(panel, text="Alrummi workspace", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text="Create a visual copy from the source, use its /jpn counterpart as a reference, or ask the local assistant for help.", style="Muted.TLabel", wraplength=340).grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.action_notebook = ttk.Notebook(panel)
        self.action_notebook.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

        confirm_frame = ttk.Frame(panel, style="Panel.TFrame")
        confirm_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        confirm_frame.columnconfigure(0, weight=1)
        ttk.Separator(confirm_frame).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(confirm_frame, text="Confirmation", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(
            confirm_frame,
            text=(
                "Applies to whatever candidate is loaded — a generated texture or a Samurai "
                "Heroes donor. Writes a new ARC and audit JSON beside the source; the source "
                "archive is never overwritten."
            ),
            style="Muted.TLabel",
            wraplength=340,
        ).grid(row=2, column=0, sticky="w", pady=(4, 6))
        self.confirm_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(confirm_frame, text="I reviewed the complete English candidate", variable=self.confirm_var, command=self._update_confirm_state).grid(row=3, column=0, sticky="w")
        self.confirm_button = ttk.Button(confirm_frame, text="Confirm + write new ARC", style="Danger.TButton", command=self.confirm_write, state="disabled")
        self.confirm_button.grid(row=4, column=0, sticky="ew", pady=(7, 0))
        self.output_label = ttk.Label(confirm_frame, text="Output: beside the source ARC", style="Muted.TLabel", wraplength=340)
        self.output_label.grid(row=5, column=0, sticky="w", pady=(7, 0))
        install_row = ttk.Frame(confirm_frame, style="Panel.TFrame")
        install_row.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        install_row.columnconfigure(0, weight=1)
        install_row.columnconfigure(1, weight=1)
        self.install_button = ttk.Button(install_row, text="Install into game tree…", command=self.install_last_build, state="disabled")
        self.install_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(install_row, text="Installs / revert…", command=self.show_installs).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ttk.Label(
            confirm_frame,
            text=(
                "Installing backs the original up first and refuses a build whose entry "
                "count does not match. Nothing is proven until RPCS3 is cold-booted."
            ),
            style="Muted.TLabel",
            wraplength=340,
        ).grid(row=7, column=0, sticky="w", pady=(5, 0))
        # This tab carries the most controls and the pane is narrow, so it
        # scrolls rather than clipping whatever falls off the bottom.
        create_outer = ttk.Frame(self.action_notebook, style="Panel.TFrame")
        create_canvas = tk.Canvas(create_outer, bg="#1e2125", highlightthickness=0)
        create_bar = ttk.Scrollbar(create_outer, orient="vertical", command=create_canvas.yview)
        create_canvas.configure(yscrollcommand=create_bar.set)
        create_canvas.pack(side="left", fill="both", expand=True)
        create_bar.pack(side="right", fill="y")
        create_tab = ttk.Frame(create_canvas, style="Panel.TFrame", padding=8)
        create_window = create_canvas.create_window((0, 0), window=create_tab, anchor="nw")

        def _create_resized(_event=None):
            create_canvas.configure(scrollregion=create_canvas.bbox("all"))
            create_canvas.itemconfigure(create_window, width=create_canvas.winfo_width())

        create_tab.bind("<Configure>", _create_resized)
        create_canvas.bind("<Configure>", _create_resized)
        create_canvas.bind(
            "<MouseWheel>",
            lambda e: create_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"),
        )
        self.create_canvas = create_canvas
        donor_tab = ttk.Frame(self.action_notebook, style="Panel.TFrame", padding=8)
        chat_tab = ttk.Frame(self.action_notebook, style="Panel.TFrame", padding=8)
        create_tab.columnconfigure(0, weight=1)
        create_tab.rowconfigure(30, weight=1)
        donor_tab.columnconfigure(0, weight=1)
        donor_tab.rowconfigure(8, weight=1)
        chat_tab.columnconfigure(0, weight=1)
        chat_tab.rowconfigure(0, weight=1)
        self.action_notebook.add(create_outer, text="Create texture")
        self.action_notebook.add(donor_tab, text="SH donors")
        batch_tab = ttk.Frame(self.action_notebook, style="Panel.TFrame", padding=8)
        batch_tab.columnconfigure(0, weight=1)
        batch_tab.rowconfigure(6, weight=1)
        self.action_notebook.add(batch_tab, text="Batch")
        msgbatch_tab = ttk.Frame(self.action_notebook, style="Panel.TFrame", padding=8)
        msgbatch_tab.columnconfigure(0, weight=1)
        msgbatch_tab.rowconfigure(5, weight=1)
        self.action_notebook.add(msgbatch_tab, text="Dialogue batch")
        self.action_notebook.add(chat_tab, text="Local chat")

        ttk.Label(msgbatch_tab, text="Build every dialogue archive", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            msgbatch_tab,
            text=(
                "Surveys rom/jpn/id and reports, per archive, what the project dictionary "
                "already covers and what still needs wording. Only archives that pass all "
                "five invariants are written, and only to a folder you choose."
            ),
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=1, column=0, sticky="w", pady=(3, 6))
        ttk.Button(msgbatch_tab, text="Survey dialogue archives…", style="Accent.TButton", command=self.survey_dialogue).grid(row=2, column=0, sticky="ew")
        self.msgbatch_summary = ttk.Label(msgbatch_tab, text="Not surveyed yet.", style="Muted.TLabel", wraplength=330)
        self.msgbatch_summary.grid(row=3, column=0, sticky="w", pady=(5, 4))
        filter_row = ttk.Frame(msgbatch_tab, style="Panel.TFrame")
        filter_row.grid(row=4, column=0, sticky="ew")
        ttk.Label(filter_row, text="Show", style="Muted.TLabel").pack(side="left", padx=(0, 5))
        self.msgbatch_filter = tk.StringVar(value="Ready")
        box = ttk.Combobox(filter_row, textvariable=self.msgbatch_filter, state="readonly", width=17,
                           values=("All", "Ready", "Needs wording", "Layout problems", "No glyph map"))
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _e: self._render_msgbatch())
        list_frame = ttk.Frame(msgbatch_tab, style="Panel.TFrame")
        list_frame.grid(row=5, column=0, sticky="nsew", pady=(6, 4))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.msgbatch_list = tk.Listbox(
            list_frame, bg="#17191c", fg="#e8eaed", selectbackground="#1f6f3f",
            relief="flat", exportselection=False, font=("Consolas", 9), height=10,
        )
        self.msgbatch_list.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(list_frame, orient="vertical", command=self.msgbatch_list.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.msgbatch_list.configure(yscrollcommand=bar.set)
        self.msgbatch_list.bind("<space>", self._msgbatch_toggle)
        self.msgbatch_list.bind("<Double-Button-1>", self._msgbatch_toggle)
        self.msgbatch_list.bind("<<ListboxSelect>>", self._msgbatch_selected)
        toggles = ttk.Frame(msgbatch_tab, style="Panel.TFrame")
        toggles.grid(row=6, column=0, sticky="ew")
        for col in range(3):
            toggles.columnconfigure(col, weight=1)
        ttk.Button(toggles, text="Toggle", command=self._msgbatch_toggle).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(toggles, text="Tick all ready", command=lambda: self._msgbatch_set_all(True)).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(toggles, text="Untick all", command=lambda: self._msgbatch_set_all(False)).grid(row=0, column=2, sticky="ew", padx=(3, 0))
        ttk.Button(msgbatch_tab, text="Build ticked archives…", style="Danger.TButton", command=self.build_dialogue_batch).grid(row=7, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(
            msgbatch_tab,
            text="Selecting a row opens that archive in the Dialogue editor so you can fill the gaps.",
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=8, column=0, sticky="w", pady=(4, 0))

        ttk.Label(batch_tab, text="Batch donor replacement", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            batch_tab,
            text=(
                "Proposes one donor per matched texture across many archives. Every row is a "
                "proposal you tick or untick; only ticked rows are written, and only ever to a "
                "separate output folder that mirrors the source tree."
            ),
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=1, column=0, sticky="w", pady=(3, 6))
        family_row = ttk.Frame(batch_tab, style="Panel.TFrame")
        family_row.grid(row=2, column=0, sticky="ew")
        family_row.columnconfigure(1, weight=1)
        ttk.Label(family_row, text="Families", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 6))
        self.batch_families = tk.StringVar(value="cp_name_pl,cp_name_army")
        ttk.Entry(family_row, textvariable=self.batch_families).grid(row=0, column=1, sticky="ew")
        ttk.Label(
            batch_tab,
            text="Leave families empty to consider every texture. Comma separated resource prefixes.",
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=3, column=0, sticky="w", pady=(3, 6))
        plan_row = ttk.Frame(batch_tab, style="Panel.TFrame")
        plan_row.grid(row=4, column=0, sticky="ew")
        plan_row.columnconfigure(0, weight=1)
        plan_row.columnconfigure(1, weight=1)
        ttk.Button(plan_row, text="Plan from loaded archives", command=self.plan_batch_loaded).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(plan_row, text="Plan from folder…", command=self.plan_batch_folder).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.batch_summary = ttk.Label(batch_tab, text="No plan yet.", style="Muted.TLabel", wraplength=330)
        self.batch_summary.grid(row=5, column=0, sticky="w", pady=(5, 4))
        batch_list_frame = ttk.Frame(batch_tab, style="Panel.TFrame")
        batch_list_frame.grid(row=6, column=0, sticky="nsew")
        batch_list_frame.rowconfigure(0, weight=1)
        batch_list_frame.columnconfigure(0, weight=1)
        self.batch_list = tk.Listbox(
            batch_list_frame,
            bg="#17191c",
            fg="#e8eaed",
            selectbackground="#1f6f3f",
            relief="flat",
            exportselection=False,
            font=("Consolas", 9),
            height=9,
        )
        self.batch_list.grid(row=0, column=0, sticky="nsew")
        batch_scroll = ttk.Scrollbar(batch_list_frame, orient="vertical", command=self.batch_list.yview)
        batch_scroll.grid(row=0, column=1, sticky="ns")
        self.batch_list.configure(yscrollcommand=batch_scroll.set)
        self.batch_list.bind("<<ListboxSelect>>", self._batch_selected)
        self.batch_list.bind("<space>", self._batch_toggle)
        self.batch_list.bind("<Double-Button-1>", self._batch_toggle)
        toggle_row = ttk.Frame(batch_tab, style="Panel.TFrame")
        toggle_row.grid(row=7, column=0, sticky="ew", pady=(5, 0))
        toggle_row.columnconfigure(0, weight=1)
        toggle_row.columnconfigure(1, weight=1)
        toggle_row.columnconfigure(2, weight=1)
        ttk.Button(toggle_row, text="Toggle", command=self._batch_toggle).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(toggle_row, text="Tick all", command=lambda: self._batch_set_all(True)).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(toggle_row, text="Untick all", command=lambda: self._batch_set_all(False)).grid(row=0, column=2, sticky="ew", padx=(3, 0))
        ttk.Label(
            batch_tab,
            text="Space or double-click toggles a row. Selecting a row previews its donor.",
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=8, column=0, sticky="w", pady=(4, 6))
        ttk.Button(batch_tab, text="Write ticked replacements…", style="Danger.TButton", command=self.apply_batch_plan).grid(row=9, column=0, sticky="ew")


        ttk.Label(donor_tab, text="Samurai Heroes donor textures", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            donor_tab,
            text=(
                "Samurai Heroes is an officially localized build of the same engine, so the "
                "correct English lettering often already exists as a real texture. Reusing one "
                "beats anything a font can render, and beats the local model on proper nouns."
            ),
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=1, column=0, sticky="w", pady=(3, 8))
        ttk.Button(donor_tab, text="Build / refresh donor index", command=self.build_donor_index).grid(row=2, column=0, sticky="ew")
        self.donor_index_label = ttk.Label(donor_tab, text="No donor index yet.", style="Muted.TLabel", wraplength=330)
        self.donor_index_label.grid(row=3, column=0, sticky="w", pady=(3, 6))
        ttk.Button(donor_tab, text="Match characters across games", command=self.build_character_map).grid(row=4, column=0, sticky="ew")
        self.character_map_label = ttk.Label(donor_tab, text="No character map yet.", style="Muted.TLabel", wraplength=330)
        self.character_map_label.grid(row=5, column=0, sticky="w", pady=(3, 8))
        ttk.Button(donor_tab, text="Find donors for the selected texture", style="Accent.TButton", command=self.find_donors).grid(row=6, column=0, sticky="ew")
        self.donor_status = ttk.Label(donor_tab, text="Select a texture in the ARC list, then search.", style="Muted.TLabel", wraplength=330)
        self.donor_status.grid(row=7, column=0, sticky="w", pady=(4, 4))
        donor_list_frame = ttk.Frame(donor_tab, style="Panel.TFrame")
        donor_list_frame.grid(row=8, column=0, sticky="nsew")
        donor_list_frame.rowconfigure(0, weight=1)
        donor_list_frame.columnconfigure(0, weight=1)
        self.donor_list = tk.Listbox(
            donor_list_frame,
            bg="#17191c",
            fg="#e8eaed",
            selectbackground="#1f6f3f",
            relief="flat",
            exportselection=False,
            font=("Consolas", 9),
            height=9,
        )
        self.donor_list.grid(row=0, column=0, sticky="nsew")
        donor_scroll = ttk.Scrollbar(donor_list_frame, orient="vertical", command=self.donor_list.yview)
        donor_scroll.grid(row=0, column=1, sticky="ns")
        self.donor_list.configure(yscrollcommand=donor_scroll.set)
        self.donor_list.bind("<<ListboxSelect>>", self._donor_selected)
        ttk.Label(donor_tab, text="Resize to the source dimensions", style="Muted.TLabel").grid(row=9, column=0, sticky="w", pady=(8, 0))
        self.donor_fit_var = tk.StringVar(value="Exact size only")
        ttk.Combobox(
            donor_tab,
            textvariable=self.donor_fit_var,
            state="readonly",
            values=("Exact size only", "Fit inside (keep aspect)", "Stretch to fill"),
        ).grid(row=10, column=0, sticky="ew", pady=(3, 6))
        ttk.Button(donor_tab, text="Use donor as the English candidate", style="Accent.TButton", command=self.use_donor).grid(row=11, column=0, sticky="ew")
        ttk.Button(donor_tab, text="Replace EVERY texture in this ARC…", style="Danger.TButton", command=self.replace_all_in_archive).grid(row=12, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(
            donor_tab,
            text=(
                "A donor replaces the whole texture, so the text region is set to the full "
                "canvas automatically. Confirmation is still required before anything is written."
            ),
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=13, column=0, sticky="w", pady=(5, 0))

        ttk.Label(create_tab, text="1  Choose how to create the candidate", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.generation_mode_var = tk.StringVar(value="Polished visual copy")
        self.generation_mode = ttk.Combobox(
            create_tab,
            textvariable=self.generation_mode_var,
            state="readonly",
            values=("Polished visual copy", "Lettering replacement"),
        )
        self.generation_mode.grid(row=1, column=0, sticky="ew", pady=(5, 2))
        ttk.Label(create_tab, text="The recommended mode keeps the full source artwork, improves its finish, wraps text cleanly, and preserves the exact texture dimensions.", style="Muted.TLabel", wraplength=330).grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Button(create_tab, text="Analyze Japanese + suggest English", command=self.analyze_selected).grid(row=3, column=0, sticky="ew")
        self.translation = tk.Text(create_tab, height=4, width=34, bg="#17191c", fg="#e8eaed", insertbackground="white", relief="flat", wrap="word")
        self.translation.grid(row=4, column=0, sticky="ew", pady=(7, 9))
        self.translation.insert("1.0", "English translation / replacement text")
        self.translation.bind("<FocusIn>", lambda _event: self._clear_text_placeholder(self.translation, "English translation / replacement text"))

        reference_frame = ttk.Frame(create_tab, style="Panel.TFrame")
        reference_frame.grid(row=5, column=0, sticky="ew", pady=(0, 9))
        reference_frame.columnconfigure(0, weight=1)
        ttk.Label(reference_frame, text="/jpn reference", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(reference_frame, text="Find matching /jpn", command=self.find_reference).grid(row=0, column=1, sticky="e")
        self.reference_status = ttk.Label(reference_frame, text="Not searched", style="Muted.TLabel", wraplength=330)
        self.reference_status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))

        ttk.Label(create_tab, text="2  Text region (pixels)", font=("Segoe UI", 10, "bold")).grid(row=6, column=0, sticky="w")
        region_frame = ttk.Frame(create_tab, style="Panel.TFrame")
        region_frame.grid(row=7, column=0, sticky="ew", pady=(5, 8))
        self.region_vars = [tk.StringVar(value=value) for value in ("0", "0", "0", "0")]
        for region_var in self.region_vars:
            region_var.trace_add("write", lambda *_: self._draw_region_overlay())
        for index, label in enumerate(("X", "Y", "W", "H")):
            ttk.Label(region_frame, text=label, style="Muted.TLabel").grid(row=0, column=index * 2, padx=(0, 3))
            ttk.Entry(region_frame, textvariable=self.region_vars[index], width=6).grid(row=0, column=index * 2 + 1, padx=(0, 7))
        ttk.Button(create_tab, text="Use full texture as canvas", command=self._use_full_region).grid(row=8, column=0, sticky="ew")

        ttk.Label(create_tab, text="Repair boxes  ·  shift+drag the source to add one", font=("Segoe UI", 9, "bold")).grid(row=13, column=0, sticky="w", pady=(10, 2))
        ttk.Label(
            create_tab,
            text=(
                "Fix part of a texture without touching the rest: mark a box, then patch "
                "just that rectangle from the Samurai Heroes donor, erase it, or letter it."
            ),
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=14, column=0, sticky="w", pady=(0, 4))
        repair_frame = ttk.Frame(create_tab, style="Panel.TFrame")
        repair_frame.grid(row=15, column=0, sticky="ew")
        repair_frame.columnconfigure(0, weight=1)
        self.repair_list = tk.Listbox(
            repair_frame, bg="#17191c", fg="#e8eaed", selectbackground="#1f6f3f",
            relief="flat", exportselection=False, font=("Consolas", 9), height=4,
        )
        self.repair_list.grid(row=0, column=0, sticky="ew")
        repair_scroll = ttk.Scrollbar(repair_frame, orient="vertical", command=self.repair_list.yview)
        repair_scroll.grid(row=0, column=1, sticky="ns")
        self.repair_list.configure(yscrollcommand=repair_scroll.set)
        self.repair_list.bind("<<ListboxSelect>>", lambda _e: self._draw_region_overlay())
        rbuttons = ttk.Frame(create_tab, style="Panel.TFrame")
        rbuttons.grid(row=16, column=0, sticky="ew", pady=(4, 0))
        for col in range(2):
            rbuttons.columnconfigure(col, weight=1)
        ttk.Button(rbuttons, text="Patch box from donor", style="Accent.TButton", command=self.patch_box_from_donor).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(rbuttons, text="Letter this box", command=self.letter_box).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ttk.Button(rbuttons, text="Erase box", command=self.erase_box).grid(row=1, column=0, sticky="ew", padx=(0, 3), pady=(4, 0))
        ttk.Button(rbuttons, text="Delete box", command=self.delete_box).grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=(4, 0))
        self.repair_status = ttk.Label(create_tab, text="No repair boxes yet.", style="Muted.TLabel", wraplength=330)
        self.repair_status.grid(row=17, column=0, sticky="w", pady=(4, 0))

        ttk.Label(create_tab, text="Material and depth", font=("Segoe UI", 9, "bold")).grid(row=18, column=0, sticky="w", pady=(12, 2))
        ttk.Label(
            create_tab,
            text=(
                "Give flat artwork a bevelled edge, a metal or jade gradient, an inner "
                "shadow and a gloss sweep — what a layer-style panel would do. Dimensions "
                "are preserved exactly."
            ),
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=19, column=0, sticky="w", pady=(0, 4))
        self.style_var = tk.StringVar(value="Gold medallion")
        ttk.Combobox(
            create_tab, textvariable=self.style_var, state="readonly",
            values=tuple(texture_fx.PRESETS),
        ).grid(row=20, column=0, sticky="ew")
        strength_row = ttk.Frame(create_tab, style="Panel.TFrame")
        strength_row.grid(row=21, column=0, sticky="ew", pady=(4, 4))
        strength_row.columnconfigure(1, weight=1)
        ttk.Label(strength_row, text="Strength", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 6))
        self.style_strength = tk.DoubleVar(value=1.0)
        ttk.Scale(strength_row, from_=0.2, to=1.6, variable=self.style_strength,
                  command=lambda _v: self.style_strength_label.configure(
                      text=f"{self.style_strength.get():.2f}×")).grid(row=0, column=1, sticky="ew")
        self.style_strength_label = ttk.Label(strength_row, text="1.00×", style="Muted.TLabel")
        self.style_strength_label.grid(row=0, column=2, padx=(6, 0))
        style_buttons = ttk.Frame(create_tab, style="Panel.TFrame")
        style_buttons.grid(row=22, column=0, sticky="ew")
        style_buttons.columnconfigure(0, weight=1)
        style_buttons.columnconfigure(1, weight=1)
        ttk.Button(style_buttons, text="Style whole texture", style="Accent.TButton",
                   command=self.apply_style_all).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(style_buttons, text="Style selected box",
                   command=self.apply_style_box).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ttk.Button(style_buttons, text="Rebuild fortune medallions", style="Accent.TButton",
                   command=self.rebuild_fortune_medallions).grid(
                       row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.style_status = ttk.Label(create_tab, text="", style="Muted.TLabel", wraplength=330)
        self.style_status.grid(row=23, column=0, sticky="w", pady=(4, 0))
        self.clear_var = tk.BooleanVar(value=False)
        self.polish_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(create_tab, text="clean old lettering inside the selected box", variable=self.clear_var).grid(row=9, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(create_tab, text="polish colour and sharpness while preserving dimensions", variable=self.polish_var).grid(row=10, column=0, sticky="w")
        ttk.Button(create_tab, text="3  Generate visual texture copy", style="Accent.TButton", command=self.generate).grid(row=11, column=0, sticky="ew", pady=(8, 0))
        self.save_candidate_button = ttk.Button(create_tab, text="Save candidate as PNG…", command=self.save_candidate_image, state="disabled")
        self.save_candidate_button.grid(row=12, column=0, sticky="ew", pady=(5, 0))

        # The confirmation lives on the panel rather than inside this tab, so
        # it is reachable from the donors and batch tabs too.  Having it here
        # was why a loaded donor looked impossible to write.

        self.chat_text = tk.Text(chat_tab, bg="#17191c", fg="#e8eaed", insertbackground="white", relief="flat", wrap="word", font=("Segoe UI", 10), state="disabled")
        self.chat_text.grid(row=0, column=0, sticky="nsew")
        chat_scroll = ttk.Scrollbar(chat_tab, orient="vertical", command=self.chat_text.yview)
        chat_scroll.grid(row=0, column=1, sticky="ns")
        self.chat_text.configure(yscrollcommand=chat_scroll.set)
        self.chat_input = tk.Text(chat_tab, height=4, bg="#17191c", fg="#e8eaed", insertbackground="white", relief="flat", wrap="word")
        self.chat_input.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 5))
        self.chat_input.bind("<Control-Return>", self._chat_submit_key)
        chat_buttons = ttk.Frame(chat_tab, style="Panel.TFrame")
        chat_buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(chat_buttons, text="Send to local AI", style="Accent.TButton", command=self.send_chat).pack(side="left", fill="x", expand=True)
        ttk.Button(chat_buttons, text="Use last reply", command=self.use_last_chat_reply).pack(side="left", padx=(5, 0))
        ttk.Button(chat_buttons, text="Clear", command=self.clear_chat).pack(side="left", padx=(5, 0))
        self._append_chat("Alrummi 3", "Local chat is ready. Ask for a shorter translation, a better fit for the box, or guidance on the matching /jpn reference.")

    def _clear_placeholder(self, widget: ttk.Entry) -> None:
        if widget.get() == "search names or indices…":
            widget.delete(0, "end")

    def _clear_text_placeholder(self, widget: tk.Text, value: str) -> None:
        if widget.get("1.0", "end-1c") == value:
            widget.delete("1.0", "end")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)
        self._log(text)

    def _log(self, text: str) -> None:
        """Keep a scrollback of what the tool has done this session."""

        if not hasattr(self, "log_text"):
            return
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {text}\n")
        limit = int(self.settings.get("log_lines", 400))
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > limit:
            self.log_text.delete("1.0", f"{lines - limit}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_progress(self, label: str) -> None:
        """Name what the progress bar is counting, so it is never a mystery."""

        self._progress_label = label

    def _set_busy(self, busy: bool) -> None:
        if busy:
            if str(self.loading_bar.cget("mode")) == "determinate":
                self.loading_bar.configure(mode="indeterminate")
            self.loading_label.configure(text="Working…")
            if self._busy_jobs == 1:
                self.loading_bar.start(12)
        else:
            self.loading_bar.stop()
            self.loading_label.configure(text="Ready")

    def open_arc(self) -> None:
        selected = filedialog.askopenfilename(title="Open MT Framework ARC", filetypes=[("ARC archives", "*.arc"), ("All files", "*.*")])
        if not selected:
            return
        self._set_status("Opening ARC…")
        self._run_worker("open", lambda: parse_arc(Path(selected)))

    def open_image(self) -> None:
        selected = filedialog.askopenfilename(
            title="Open source image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tga *.dds"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        self._set_status("Opening source image…")
        self._run_worker("image", lambda: self._load_image_file(path))

    @staticmethod
    def _load_image_file(path: Path) -> tuple[Path, bytes, Image.Image, dict]:
        raw = path.read_bytes()
        image, info = decode_resource(raw, path.name)
        return path, raw, image, info

    def open_folder(self) -> None:
        selected = filedialog.askdirectory(title="Open folder and scan all ARC archives")
        if not selected:
            return
        self._set_status("Scanning folder recursively for ARC archives…")
        self._run_worker("open_folder", lambda: self._scan_folder(Path(selected)))

    def _scan_folder(self, root: Path) -> tuple[list[ArcArchive], list[str]]:
        paths = sorted(
            (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".arc"),
            key=lambda path: str(path).lower(),
        )
        self._scan_progress = (0, len(paths))
        # Indexing an archive is header I/O rather than computation, so a small
        # thread pool turns a tree of thousands of ARCs from a long serial walk
        # into a short parallel one.  Results are stored by position so the
        # archive selector keeps sorted order regardless of completion order.
        indexed: list[ArcArchive | None] = [None] * len(paths)
        errors: list[str] = []
        completed = 0
        try:
            with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 2)) as pool:
                futures = {
                    pool.submit(parse_arc, path, metadata_only=True): index
                    for index, path in enumerate(paths)
                }
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        indexed[index] = future.result()
                    except Exception as exc:
                        errors.append(f"{paths[index]}: {exc}")
                    completed += 1
                    self._scan_progress = (completed, len(paths))
        finally:
            self._scan_progress = (0, 0)
        return [archive for archive in indexed if archive is not None], errors

    def _archives_opened(self, result: tuple[list[ArcArchive], list[str]]) -> None:
        archives, errors = result
        if not archives:
            message = "No readable ARC archives were found."
            if errors:
                message += f"\n\n{len(errors)} files were skipped."
            messagebox.showwarning("Alrummi 3", message)
            self._set_status(message)
            return
        self.loaded_archives = archives
        values = [f"{archive.path} · {len(archive.entries)} entries" for archive in archives]
        self._rebuild_archive_tabs()
        self.archive_combo.configure(values=values)
        self.archive_combo.current(0)
        self._set_current_archive(0)
        suffix = f" {len(errors)} skipped." if errors else ""
        self._set_status(f"Opened {len(archives)} ARC archives from the folder.{suffix}")
        if errors:
            self.after(50, lambda: messagebox.showwarning("Some ARCs were skipped", "\n".join(errors[:20]) + ("\n…" if len(errors) > 20 else "")))

    def _rebuild_archive_tabs(self) -> None:
        """One tab per open archive, the way a file editor does it.

        A folder scan can load thousands, and a tab strip that long is worse
        than useless, so past a couple of dozen the selector is left to do the
        job and the strip hides itself.
        """

        for tab in self.archive_tabs.tabs():
            self.archive_tabs.forget(tab)
        self._tab_frames = []
        archives = self.loaded_archives
        if not archives or len(archives) > self.MAX_ARCHIVE_TABS:
            self.archive_tabs.grid_remove()
            if len(archives) > self.MAX_ARCHIVE_TABS:
                self.archive_tab_note.configure(
                    text=f"{len(archives)} archives open — use the selector above."
                )
                self.archive_tab_note.grid()
            else:
                self.archive_tab_note.grid_remove()
            return
        self.archive_tab_note.grid_remove()
        self.archive_tabs.grid()
        for archive in archives:
            frame = ttk.Frame(self.archive_tabs, height=1)
            self._tab_frames.append(frame)
            self.archive_tabs.add(frame, text=f" {archive.path.name} ")
        if 0 <= self.current_archive_index < len(archives):
            self._suppress_tab_event = True
            try:
                self.archive_tabs.select(self.current_archive_index)
            finally:
                self._suppress_tab_event = False

    def _archive_tab_selected(self, _event=None) -> None:
        if self._suppress_tab_event:
            return
        try:
            index = self.archive_tabs.index(self.archive_tabs.select())
        except Exception:
            return
        if index != self.current_archive_index and index < len(self.loaded_archives):
            self._set_current_archive(index)

    def close_current_archive(self) -> None:
        if not self.loaded_archives:
            return
        index = self.current_archive_index
        if not 0 <= index < len(self.loaded_archives):
            return
        closed = self.loaded_archives.pop(index)
        if not self.loaded_archives:
            self.archive = None
            self.selected_entry = None
            self.source_raw = None
            self.source_image = None
            self.candidate_image = None
            self.texture_rows = []
            self.entry_tree.delete(*self.entry_tree.get_children())
            self._rebuild_archive_tabs()
            self.archive_combo.configure(values=[])
            self._draw_preview("source")
            self._draw_preview("candidate")
            self._set_status(f"Closed {closed.path.name}. No archives open.")
            return
        values = [f"{a.path} · {len(a.entries)} entries" for a in self.loaded_archives]
        self.archive_combo.configure(values=values)
        self._rebuild_archive_tabs()
        self._set_current_archive(min(index, len(self.loaded_archives) - 1))
        self._set_status(f"Closed {closed.path.name}.")

    def _archive_changed(self, _event=None) -> None:
        index = self.archive_combo.current()
        if index >= 0 and index < len(self.loaded_archives):
            self._set_current_archive(index)

    def _set_current_archive(self, index: int) -> None:
        if not self.loaded_archives:
            return
        self.archive = self.loaded_archives[index]
        self.current_archive_index = index
        self.source_path = self.archive.path
        self.source_name = str(self.archive.path)
        self.selected_entry = None
        self.source_raw = None
        self.source_image = None
        self.candidate_image = None
        self.reference_image = None
        self.reference_info = None
        self.reference_archive = None
        self.reference_entry = None
        self.candidate_meta = None
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="disabled")
        self._update_confirm_state()
        if self.archive_combo.current() != index:
            self.archive_combo.current(index)
        if getattr(self, "archive_tabs", None) is not None and self._tab_frames:
            self._suppress_tab_event = True
            try:
                if 0 <= index < len(self._tab_frames):
                    self.archive_tabs.select(index)
            except Exception:
                pass
            finally:
                self._suppress_tab_event = False
        self.archive_label.configure(
            text=(
                f"{self.archive.path}\n"
                f"{len(self.archive.entries)} entries · {self.archive.platform} v{self.archive.version} · "
                f"{self.archive.entry_size}-byte records\n"
                f"SHA-256 {self.archive.data_sha256[:16] + '…' if self.archive.data_sha256 else 'computed on selection'}"
            )
        )
        self._refresh_entries()
        self._draw_preview("source")
        self._draw_preview("candidate")
        self._draw_preview("reference")

    def _run_worker(self, label: str, function) -> None:
        self._busy_jobs += 1
        self._set_busy(True)

        def runner() -> None:
            try:
                self.worker_queue.put((label, (True, function())))
            except Exception as exc:  # worker errors are shown in the UI thread
                self.worker_queue.put((label, (False, exc)))
        threading.Thread(target=runner, daemon=True).start()

    def _poll_worker(self) -> None:
        try:
            while True:
                label, result = self.worker_queue.get_nowait()
                self._busy_jobs = max(0, self._busy_jobs - 1)
                if self._busy_jobs == 0:
                    self._set_busy(False)
                ok, value = result
                if not ok:
                    self._set_status(f"Error: {value}")
                    messagebox.showerror("Alrummi 3", str(value))
                    continue
                if label == "open":
                    self._archive_opened(value)
                elif label == "open_folder":
                    self._archives_opened(value)
                elif label == "image":
                    self._image_opened(value)
                elif label == "decode":
                    self._resource_decoded(value)
                elif label == "reference":
                    self._reference_opened(value)
                elif label == "generate":
                    self._candidate_generated(value)
                elif label == "msg_file":
                    self._msg_file_opened(value)
                elif label == "ai":
                    self._ai_finished(value)
                elif label == "chat":
                    self._chat_finished(value)
                elif label == "ping":
                    self._ai_ping_finished(value)
                elif label == "write":
                    self._write_finished(value)
                elif label == "donor_build":
                    self._donor_index_built(value)
                elif label == "donor_find":
                    self._donors_found(value)
                elif label == "donor_use":
                    self._donor_prepared(value)
                elif label == "charmap":
                    self._character_map_built(value)
                elif label == "batch_plan":
                    self._batch_planned(value)
                elif label == "batch_apply":
                    self._batch_applied(value)
                elif label == "dialogue_open":
                    self._dialogue_opened(value)
                elif label == "dialogue_build":
                    self._dialogue_built(value)
                elif label == "whole_arc":
                    self._whole_arc_done(value)
                elif label == "copies":
                    self._copies_found(value)
                elif label == "autofix":
                    self._autofix_done(value)
                elif label == "msg_survey":
                    self._dialogue_surveyed(value)
                elif label == "msg_batch":
                    self._dialogue_batch_done(value)
        except queue.Empty:
            pass
        # Persist the layout periodically as well as on close, so a crash or a
        # force-quit does not lose the panes you just arranged.
        now = time.time()
        if now - getattr(self, "_last_layout_save", 0.0) > 30.0:
            self._last_layout_save = now
            try:
                self._capture_layout()
                ui_state.save(APP_ROOT, self.settings)
            except Exception:
                pass

        scanned, total = self._scan_progress
        if total:
            percent = scanned / total * 100
            self.loading_label.configure(
                text=f"{self._progress_label} {scanned}/{total} ({percent:.0f}%)"
            )
            if str(self.loading_bar.cget("mode")) != "determinate":
                self.loading_bar.stop()
                self.loading_bar.configure(mode="determinate", maximum=100)
            self.loading_bar.configure(value=percent)
        elif str(self.loading_bar.cget("mode")) == "determinate" and self._busy_jobs:
            self.loading_bar.configure(mode="indeterminate")
            self.loading_bar.start(12)
        self.after(120, self._poll_worker)

    def _archive_opened(self, archive: ArcArchive) -> None:
        # Opening one archive adds it to the open set rather than replacing it,
        # so several can be worked on side by side.
        existing = [i for i, a in enumerate(self.loaded_archives)
                    if str(a.path) == str(archive.path)]
        if existing:
            self.loaded_archives[existing[0]] = archive
            index = existing[0]
        else:
            self.loaded_archives.append(archive)
            index = len(self.loaded_archives) - 1
        values = [f"{a.path} · {len(a.entries)} entries" for a in self.loaded_archives]
        self.archive_combo.configure(values=values)
        self._rebuild_archive_tabs()
        self._set_current_archive(index)
        self._set_status(
            f"Opened {archive.path.name}: {len(archive.entries)} entries. "
            f"{len(self.loaded_archives)} archive(s) open."
        )
        return

    def _archive_opened_legacy(self, archive: ArcArchive) -> None:
        self.loaded_archives = [archive]
        self.source_path = archive.path
        self.source_name = str(archive.path)
        self.archive_combo.configure(values=[f"{archive.path} · {len(archive.entries)} entries"])
        self.archive_combo.current(0)
        self._set_current_archive(0)
        self._set_status("ARC opened. Select a texture/resource to inspect it.")

    def _image_opened(self, result: tuple[Path, bytes, Image.Image, dict]) -> None:
        path, raw, image, info = result
        self.archive = None
        self.loaded_archives = []
        self.source_path = path
        self.source_name = path.name
        self.selected_entry = None
        self.source_raw = raw
        self.source_image = image
        self.candidate_image = None
        self.candidate_meta = None
        self.reference_image = None
        self.reference_info = None
        self.reference_archive = None
        self.reference_entry = None
        self.archive_combo.configure(values=[f"Loose image · {path.name}"])
        self.archive_var.set(f"Loose image · {path.name}")
        self.entry_tree.delete(*self.entry_tree.get_children())
        self.archive_label.configure(text=f"{path}\nLoose image · {info['width']}×{info['height']} · source bytes loaded")
        self.reference_status.configure(text="Loose images do not have an ARC /jpn counterpart.")
        self.reference_label.configure(text="No /jpn reference is available for a loose image.")
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="disabled")
        self._update_confirm_state()
        self._use_full_region()
        self.preview_notebook.select(self.review_tab)
        self.preview_meta.configure(text=f"{path}\n{info['container']} {info['format']} · {info['width']}×{info['height']} · loose image mode")
        self._draw_preview("source")
        self._draw_preview("candidate")
        self._draw_preview("reference")
        self._set_status("Source image opened. Add wording or use the local chat, then generate a visual copy.")

    def find_reference(self) -> None:
        if self.archive is None or self.selected_entry is None:
            messagebox.showinfo("Alrummi 3", "Select a texture inside an ARC first.")
            return
        self.reference_status.configure(text="Searching for the matching /jpn archive and resource…")
        self.reference_label.configure(text="Searching for a matching /jpn resource…")
        self._set_status("Looking for the /jpn equivalent as a visual reference…")
        self._run_worker("reference", self._find_reference)

    def _find_reference(self) -> tuple[ArcArchive, ArcEntry, bytes, Image.Image, dict] | None:
        if self.archive is None or self.selected_entry is None:
            return None
        match = find_jpn_reference(self.archive.path, self.selected_entry.name)
        if match is None:
            return None
        reference_archive, reference_entry = match
        raw = unpack_entry(reference_entry)
        image, info = decode_resource(raw, reference_entry.name)
        return reference_archive, reference_entry, raw, image, info

    def _reference_opened(self, result: tuple[ArcArchive, ArcEntry, bytes, Image.Image, dict] | None) -> None:
        if result is None:
            self.reference_image = None
            self.reference_info = None
            self.reference_archive = None
            self.reference_entry = None
            self.reference_status.configure(text="No matching /jpn archive/resource was found.")
            self.reference_label.configure(text="No matching /jpn resource found. The English source remains usable without it.")
            self._draw_preview("reference")
            self._set_status("No matching /jpn resource found.")
            return
        archive, entry, _raw, image, info = result
        self.reference_archive = archive
        self.reference_entry = entry
        self.reference_image = image
        self.reference_info = info
        self.reference_status.configure(text=f"Found {archive.path.name} · entry {entry.index} · click the JPN reference tab to view it.")
        self.reference_label.configure(text=f"{archive.path}\n{entry.name}\n{info['container']} {info['format']} · {info['width']}×{info['height']}")
        self._draw_preview("reference")
        self._set_status("Matching /jpn reference loaded. Review it from the JPN reference tab.")

    def _refresh_entries(self) -> None:
        if self.archive is None:
            return
        query = self.search_var.get().strip().lower()
        if query == "search names or indices…":
            query = ""
        self.entry_tree.delete(*self.entry_tree.get_children())
        self.texture_rows = []
        for entry in self.archive.entries:
            if self.filter_var.get() and not (is_texture_name(entry.name) or is_message_name(entry.name) or entry.type_hash in (MSG_HASH, FIM_HASH, CSA_HASH)):
                continue
            if query and query not in entry.name.lower() and query not in str(entry.index):
                continue
            kind = type_label(entry.type_hash, entry.name)
            self.texture_rows.append(entry)
            self.entry_tree.insert("", "end", iid=str(entry.index), values=(entry.index, kind, entry.name))

    def _entry_selected(self, _event=None) -> None:
        if self.archive is None:
            return
        selection = self.entry_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        self.selected_entry = self.archive.entries[index]
        self.source_name = self.selected_entry.name
        self.source_raw = None
        self.source_image = None
        self.candidate_image = None
        self.reference_image = None
        self.reference_info = None
        self.reference_archive = None
        self.reference_entry = None
        self.candidate_meta = None
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="disabled")
        self._update_confirm_state()
        self.reference_status.configure(text="Searching for matching /jpn resource…")
        self.reference_label.configure(text="Searching for a matching /jpn resource…")
        self.preview_meta.configure(text=f"Loading entry {index}: {self.selected_entry.name}")
        self._set_status("Decoding selected resource…")
        self._run_worker("decode", self._decode_selected)

    def _decode_selected(self) -> tuple[ArcArchive, bytes, Image.Image | None, dict, str | None]:
        if self.archive is None or self.selected_entry is None:
            raise ValueError("no resource selected")
        archive = self.archive if self.archive.data else parse_arc(self.archive.path)
        entry = archive.entries[self.selected_entry.index]
        raw = unpack_entry(entry)
        if raw[:4] == b"\0GSM" or entry.type_hash == MSG_HASH:
            matching_name = entry.name
            csa_raw = None
            fim_raw = None
            for sibling in archive.entries:
                if sibling.name != matching_name:
                    continue
                if sibling.type_hash == CSA_HASH:
                    csa_raw = unpack_entry(sibling)
                elif sibling.type_hash == FIM_HASH:
                    fim_raw = unpack_entry(sibling)
            readable = format_gsm_document(raw, name=matching_name, csa_raw=csa_raw, fim_raw=fim_raw)
            return archive, raw, None, {
                "container": "GSM",
                "format": ".msg",
                "width": 0,
                "height": 0,
                "writable": False,
            }, readable
        image, info = decode_resource(raw, entry.name)
        return archive, raw, image, info, None

    def _resource_decoded(self, result: tuple[ArcArchive, bytes, Image.Image | None, dict, str | None]) -> None:
        archive, self.source_raw, self.source_image, info, readable = result
        self.archive = archive
        if self.current_archive_index < len(self.loaded_archives):
            self.loaded_archives[self.current_archive_index] = archive
        self.candidate_image = None
        self.candidate_meta = None
        if readable is not None:
            msg_name = self.selected_entry.name if self.selected_entry else "MSG resource"
            self._show_msg_document(readable, msg_name)
            self.preview_meta.configure(text=f"{msg_name}\nGSM readable view · translation-safe control tags preserved")
            self._set_status("MSG loaded in the readable viewer. It is currently read-only; the source bytes remain unchanged.")
            return
        self._update_file_notes()
        self.preview_notebook.select(self.review_tab)
        self.source_name = self.selected_entry.name if self.selected_entry else self.source_name
        self.preview_meta.configure(text=f"{self.source_name}\n{info['container']} {info['format']} · {info['width']}×{info['height']} · {'writable' if info['writable'] else 'preview only'}")
        self._use_full_region()
        self._draw_preview("source")
        self._draw_preview("candidate")
        self._draw_preview("reference")
        if self.archive is not None and self.selected_entry is not None:
            self.reference_status.configure(text="Searching for matching /jpn resource…")
            self._run_worker("reference", self._find_reference)
        self._set_status("Source decoded. Add wording or use local AI, then generate a visual copy.")

    def open_msg(self) -> None:
        selected = filedialog.askopenfilename(
            title="Open loose MSG file",
            filetypes=[("MSG resources", "*.msg"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        self.source_image = None
        self.candidate_image = None
        self.candidate_meta = None
        self.save_candidate_button.configure(state="disabled")
        self.confirm_var.set(False)
        self._update_confirm_state()
        self._set_status("Reading MSG resource…")
        self._run_worker("msg_file", lambda: (path, format_gsm_document(path.read_bytes(), name=str(path))))

    def _msg_file_opened(self, result: tuple[Path, str]) -> None:
        path, readable = result
        self.source_path = path
        self.source_name = str(path)
        self._show_msg_document(readable, str(path))
        self.preview_meta.configure(text=f"{path}\nloose GSM/.msg resource · read-only readable view")
        self._set_status("Loose MSG loaded. Save a readable TXT copy if needed.")

    def _show_msg_document(self, readable: str, source: str) -> None:
        self.msg_text.configure(state="normal")
        self.msg_text.delete("1.0", "end")
        self.msg_text.insert("1.0", readable)
        self.msg_source = source
        self.msg_source_label.configure(text=source)
        self.preview_notebook.select(self.msg_tab)

    def save_msg_text(self) -> None:
        readable = self.msg_text.get("1.0", "end-1c")
        if not readable.strip():
            messagebox.showinfo("Alrummi 3", "Load an MSG resource first.")
            return
        output = filedialog.asksaveasfilename(
            title="Save readable MSG text",
            initialfile=Path(self.msg_source or "message").stem + ".txt",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
        )
        if output:
            Path(output).write_text(readable, encoding="utf-8")
            self._set_status(f"Readable MSG text saved to {output}")

    def save_candidate_image(self) -> None:
        if self.candidate_image is None:
            messagebox.showinfo("Alrummi 3", "Generate a visual candidate first.")
            return
        initial = (Path(self.source_name or "texture").stem + "_alrummi3.png")
        output = filedialog.asksaveasfilename(
            title="Save visual texture candidate",
            initialfile=initial,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
        )
        if not output:
            return
        self.candidate_image.save(output, format="PNG")
        self._set_status(f"Visual candidate saved to {output}")

    def _chat_submit_key(self, _event=None) -> str:
        self.send_chat()
        return "break"

    def _append_chat(self, speaker: str, message: str) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", f"{speaker}:\n{message.strip()}\n\n")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def clear_chat(self) -> None:
        self.chat_history.clear()
        self.chat_text.configure(state="normal")
        self.chat_text.delete("1.0", "end")
        self.chat_text.configure(state="disabled")
        self._append_chat("Alrummi 3", "Chat cleared. Ask me about wording, layout, /jpn references, or the current ARC workflow.")

    def _chat_context(self) -> str:
        source = self.source_name or "No source selected"
        size = f"{self.source_image.width}x{self.source_image.height}" if self.source_image else "unknown"
        reference = "available" if self.reference_image is not None else "not loaded"
        return f"Resource: {source}\nSource dimensions: {size}\nMatching /jpn reference: {reference}\nGeneration mode: {self.generation_mode_var.get()}"

    def send_chat(self) -> None:
        message = self.chat_input.get("1.0", "end-1c").strip()
        if not message:
            return
        self.chat_input.delete("1.0", "end")
        self.chat_history.append({"role": "user", "content": message})
        self._append_chat("You", message)
        history = list(self.chat_history)
        self._set_status("Asking the local Alrummi assistant…")
        self._run_worker("chat", lambda: self.ai.chat(message, context=self._chat_context(), history=history))

    def _chat_finished(self, response: str) -> None:
        response = str(response).strip()
        self.chat_history.append({"role": "assistant", "content": response})
        self._append_chat("Alrummi 3", response)
        self._set_status("Local chat replied. Use the response as wording if it contains a suitable translation.")

    def use_last_chat_reply(self) -> None:
        for item in reversed(self.chat_history):
            if item.get("role") == "assistant" and str(item.get("content", "")).strip():
                self.translation.delete("1.0", "end")
                self.translation.insert("1.0", str(item["content"]).strip())
                self.action_notebook.select(0)
                self._set_status("Last local-chat reply copied into the English wording box. Edit it before generating if needed.")
                return
        messagebox.showinfo("Alrummi 3", "There is no local-chat reply to use yet.")

    # ------------------------------------------------------------------
    # Layout, zoom and pop-out windows
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        """A menu bar, because this tool now has far more in it than fits on buttons."""

        bar = tk.Menu(self)

        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="Open ARC…\tCtrl+O", command=self.open_arc)
        file_menu.add_command(label="Open folder…\tCtrl+Shift+O", command=self.open_folder)
        file_menu.add_command(label="Open loose image…", command=self.open_image)
        file_menu.add_separator()
        file_menu.add_command(label="Open MSG file…", command=self.open_msg)
        file_menu.add_command(label="Open dialogue archive…", command=self.open_dialogue)
        file_menu.add_separator()
        file_menu.add_command(label="Save candidate as PNG…", command=self.save_candidate_image)
        file_menu.add_command(label="Save readable MSG text…", command=self.save_msg_text)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        bar.add_cascade(label="File", menu=file_menu)

        view = tk.Menu(bar, tearoff=0)
        view.add_command(label="Reset layout", command=self.reset_layout)
        view.add_separator()
        view.add_command(label="Fit\tCtrl+0", command=lambda: self.set_zoom_mode("fit"))
        view.add_command(label="Actual size 1:1\tCtrl+1", command=lambda: self.set_zoom_mode("actual"))
        view.add_command(label="Fill", command=lambda: self.set_zoom_mode("fill"))
        view.add_command(label="Zoom in\tCtrl++", command=lambda: self._set_zoom(self.zoom_var.get() + 0.25))
        view.add_command(label="Zoom out\tCtrl+-", command=lambda: self._set_zoom(self.zoom_var.get() - 0.25))
        view.add_separator()
        tabs = tk.Menu(view, tearoff=0)
        for label, attribute in (
            ("Texture review", "review_tab"),
            ("MSG reader", "msg_tab"),
            ("JPN reference", "reference_tab"),
            ("Dialogue editor", "dialogue_tab"),
            ("File notes", "notes_tab"),
            ("Log", "log_tab"),
        ):
            tabs.add_command(
                label=label,
                command=lambda a=attribute: self.preview_notebook.select(getattr(self, a)),
            )
        view.add_cascade(label="Go to tab", menu=tabs)
        view.add_separator()
        view.add_command(label="Pop out the source preview", command=lambda: self.popout_preview("source"))
        view.add_command(label="Pop out the candidate preview", command=lambda: self.popout_preview("candidate"))
        bar.add_cascade(label="View", menu=view)

        tools = tk.Menu(bar, tearoff=0)
        tools.add_command(label="Check local AI", command=self.check_ai)
        tools.add_command(label="Extensions…", command=self.show_extensions)
        tools.add_separator()
        tools.add_command(label="Build / refresh donor index", command=self.build_donor_index)
        tools.add_command(label="Match characters across games", command=self.build_character_map)
        tools.add_command(label="Find donors for this texture\tCtrl+D", command=self.find_donors)
        tools.add_command(label="Replace every texture in this ARC…", command=self.replace_all_in_archive)
        tools.add_separator()
        tools.add_command(label="Survey dialogue archives…", command=self.survey_dialogue)
        tools.add_command(label="Find copies of this resource", command=self.find_resource_copies)
        tools.add_separator()
        tools.add_command(label="Installs / revert…", command=self.show_installs)
        bar.add_cascade(label="Tools", menu=tools)

        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="Keyboard shortcuts\tF1", command=self.show_shortcuts)
        help_menu.add_command(label="What can this do?", command=self.show_capabilities)
        help_menu.add_command(label="About", command=self.show_about)
        bar.add_cascade(label="Help", menu=help_menu)

        self.configure(menu=bar)

    def show_capabilities(self) -> None:
        messagebox.showinfo(
            "Alrummi 3 — what it does",
            "TEXTURES\n"
            "  Open an ARC or a whole folder, preview XET textures, and replace them.\n"
            "  SH donors finds the official English texture for the same character,\n"
            "  matched by portrait rather than by filename, and copies it losslessly.\n"
            "  Shift+drag the source to add repair boxes and fix part of a texture.\n"
            "  Batch plans donor replacements across many archives at once.\n\n"
            "DIALOGUE\n"
            "  The Dialogue editor decodes a msg archive, fills it from the project's\n"
            "  14,948-entry dictionary, validates 41 columns and 3 lines, and builds\n"
            "  a new archive only if all five project invariants pass.\n"
            "  Dialogue batch does that for every archive at once.\n\n"
            "SAFETY\n"
            "  No source archive is ever modified. Every write produces an audit JSON.\n"
            "  Installing backs the original up first and can be reverted.\n"
            "  Nothing is proven until RPCS3 is cold-booted and you look at it.",
        )

    def show_about(self) -> None:
        donor = "built" if self.donor_index else "not built"
        charmap = f"{self.character_map.get('matched', 0)} characters" if self.character_map else "not built"
        messagebox.showinfo(
            "About Alrummi 3",
            "Alrummi 3 — offline ARC texture and dialogue workshop\n"
            "for the Sengoku BASARA 3 Utage English patch.\n\n"
            f"Project dictionary : {len(self.project_dictionary):,} entries\n"
            f"Roster             : {len(self.project_roster)} names\n"
            f"Donor index        : {donor}\n"
            f"Character map      : {charmap}\n\n"
            "Everything runs locally. No cloud service is contacted.",
        )

    def copy_log(self) -> None:
        text = self.log_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("Log copied to the clipboard.")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _install_shortcuts(self) -> None:
        """Keyboard for the things done hundreds of times a session."""

        bindings = {
            "<Control-o>": lambda _e: self.open_arc(),
            "<Control-Shift-O>": lambda _e: self.open_folder(),
            "<Control-g>": lambda _e: self.generate(),
            "<Control-d>": lambda _e: self.find_donors(),
            "<Control-Return>": lambda _e: self.confirm_write(),
            "<Control-f>": lambda _e: (self.search_entry.focus_set(), "break")[1],
            "<Control-l>": lambda _e: self.preview_notebook.select(self.log_tab),
            "<F1>": lambda _e: self.show_shortcuts(),
            "<Control-plus>": lambda _e: self._set_zoom(self.zoom_var.get() + 0.25),
            "<Control-minus>": lambda _e: self._set_zoom(self.zoom_var.get() - 0.25),
            "<Control-0>": lambda _e: self.set_zoom_mode("fit"),
            "<Control-1>": lambda _e: self.set_zoom_mode("actual"),
        }
        for sequence, handler in bindings.items():
            try:
                self.bind_all(sequence, handler)
            except Exception:
                pass

    def show_shortcuts(self) -> None:
        messagebox.showinfo(
            "Alrummi 3 — keyboard",
            "Ctrl+O        open an ARC\n"
            "Ctrl+Shift+O  open a folder\n"
            "Ctrl+F        jump to the search box\n"
            "Ctrl+G        generate a candidate\n"
            "Ctrl+D        find Samurai Heroes donors\n"
            "Ctrl+Enter    confirm and write\n"
            "Ctrl+L        show the log\n"
            "Ctrl+0 / 1    zoom to fit / 1:1\n"
            "Ctrl+ + / -   zoom in and out\n"
            "Shift+drag    add a repair box on the source\n"
            "F1            this list",
        )

    def set_zoom_mode(self, mode: str) -> None:
        """fit = whole texture visible, actual = 1 texel per pixel, fill = cover."""

        self.zoom_mode = mode
        self.zoom_var.set(1.0)
        self._zoom_changed()
        self._set_status({
            "fit": "Zoom: fit the whole texture in the pane.",
            "actual": "Zoom: 1:1, one texture pixel per screen pixel.",
            "fill": "Zoom: fill the pane, cropping the overflow.",
        }.get(mode, "Zoom changed."))

    def _preview_motion(self, event, which: str) -> None:
        """Show the texture pixel under the cursor - essential for boxing."""

        render = self.preview_render.get(which)
        image = {"source": self.source_image, "candidate": self.candidate_image,
                 "reference": self.reference_image}.get(which)
        if render is None or image is None:
            return
        scale, x0, y0 = render
        canvas = {"source": self.source_canvas, "candidate": self.candidate_canvas,
                  "reference": self.reference_canvas}[which]
        px = (canvas.canvasx(event.x) - x0) / max(scale, 1e-6)
        py = (canvas.canvasy(event.y) - y0) / max(scale, 1e-6)
        if 0 <= px < image.width and 0 <= py < image.height:
            try:
                rgba = image.convert("RGBA").getpixel((int(px), int(py)))
            except Exception:
                rgba = None
            colour = f"  rgba{rgba}" if rgba else ""
            self.cursor_label.configure(text=f"{int(px)}, {int(py)}{colour}")
        else:
            self.cursor_label.configure(text="")

    def popout_preview(self, which: str) -> None:
        """Open one preview in its own resizable window."""

        existing = self.popouts.get(which)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return
        window = tk.Toplevel(self)
        window.title(f"Alrummi 3 — {which} preview")
        window.geometry("1100x700")
        window.configure(bg="#17191c")
        canvas = tk.Canvas(window, bg="#343a40", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        window.canvas = canvas
        window.which = which
        window.photo = None
        canvas.bind("<Configure>", lambda _e, w=window: self._draw_popout(w))
        canvas.bind("<ButtonPress-1>", lambda e, c=canvas: c.scan_mark(e.x, e.y))
        canvas.bind("<B1-Motion>", lambda e, c=canvas: c.scan_dragto(e.x, e.y, gain=1))
        window.protocol("WM_DELETE_WINDOW", lambda w=window, k=which: self._close_popout(k, w))
        self.popouts[which] = window
        self._draw_popout(window)
        self._set_status(f"Opened the {which} preview in its own window.")

    def _close_popout(self, which: str, window) -> None:
        self.popouts.pop(which, None)
        window.destroy()

    def _draw_popout(self, window) -> None:
        if not window.winfo_exists():
            return
        which = window.which
        image = {"source": self.source_image, "candidate": self.candidate_image,
                 "reference": self.reference_image}.get(which)
        canvas = window.canvas
        canvas.delete("all")
        if image is None:
            canvas.create_text(200, 100, text="No image", fill="#9aa3ad", anchor="nw")
            return
        cw = max(1, canvas.winfo_width() - 12)
        ch = max(1, canvas.winfo_height() - 12)
        scale = min(cw / image.width, ch / image.height)
        if self.zoom_mode == "actual":
            scale = 1.0
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        preview = image.resize(size, Image.Resampling.NEAREST)
        backdrop = self._checkerboard(size)
        backdrop.alpha_composite(preview)
        window.photo = ImageTk.PhotoImage(backdrop)
        canvas.create_image(
            max(0, (canvas.winfo_width() - size[0]) // 2),
            max(0, (canvas.winfo_height() - size[1]) // 2),
            image=window.photo, anchor="nw",
        )

    def _refresh_popouts(self) -> None:
        for which, window in list(self.popouts.items()):
            if window.winfo_exists():
                self._draw_popout(window)
            else:
                self.popouts.pop(which, None)

    # A pane narrower than this is invisible in practice, and a layout that
    # produces one is treated as corrupt rather than restored.
    MIN_PANE = 240
    # The browser pane has to show a full resource path such as
    # id	exture\jpn\cockpit\cockpit_016_ID_HQ, so it gets real width.
    DEFAULT_BODY_FRACTIONS = (0.28, 0.68)
    DEFAULT_REVIEW_FRACTIONS = (0.5,)

    def _paned_widgets(self):
        return (
            (getattr(self, "body_paned", None), "body_sashes", self.DEFAULT_BODY_FRACTIONS),
            (getattr(self, "review_paned", None), "review_sashes", self.DEFAULT_REVIEW_FRACTIONS),
        )

    @staticmethod
    def _pane_widths(paned, positions) -> list[int]:
        total = paned.winfo_width()
        edges = [0] + list(positions) + [total]
        return [edges[i + 1] - edges[i] for i in range(len(edges) - 1)]

    def _positions_usable(self, paned, positions) -> bool:
        try:
            count = len(paned.panes())
        except Exception:
            return False
        if count < 2 or len(positions) != count - 1:
            return False
        if paned.winfo_width() < self.MIN_PANE * count:
            return False
        if any(w < self.MIN_PANE for w in self._pane_widths(paned, positions)):
            return False
        return all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))

    def _apply_fractions(self, paned, fractions) -> None:
        """Lay the sashes out proportionally, never below the minimum."""

        total = paned.winfo_width()
        try:
            count = len(paned.panes())
        except Exception:
            return
        if count < 2 or total < 50:
            return
        positions = []
        for index, fraction in enumerate(fractions[: count - 1]):
            wanted = int(total * fraction)
            lowest = self.MIN_PANE * (index + 1)
            highest = total - self.MIN_PANE * (count - 1 - index)
            positions.append(max(lowest, min(wanted, highest)))
        for index, value in enumerate(positions):
            try:
                paned.sashpos(index, value)
            except Exception:
                pass

    def _enforce_minimums(self, paned, fractions) -> bool:
        """Push any collapsed pane back to a usable width.

        Without this a divider can be dragged to the edge and the pane behind
        it simply disappears with no way back except a reset - which is exactly
        how the source preview and the whole workspace panel went missing.
        """

        try:
            count = len(paned.panes())
            positions = [paned.sashpos(i) for i in range(count - 1)]
        except Exception:
            return False
        if not positions:
            return False
        if all(w >= self.MIN_PANE for w in self._pane_widths(paned, positions)):
            return False
        self._apply_fractions(paned, fractions)
        return True

    def _watch_sashes(self) -> None:
        """Keep the panes honest: reopen anything a drag shut, and keep the
        proportional default correct while the window is still settling.

        A one-shot delayed re-apply was not enough - the frozen build takes
        longer to reach its final size than the delay, so the default landed
        against a stale width and the browser pane came out half as wide as
        intended.  Re-applying on <Configure> is self-correcting, and it stops
        as soon as the operator touches a divider.
        """

        for paned, key, fractions in self._paned_widgets():
            if paned is None:
                continue
            paned.bind(
                "<ButtonRelease-1>",
                lambda _e, p=paned, k=key, f=fractions: self._sash_released(p, f, k),
                add="+",
            )
            paned.bind(
                "<Configure>",
                lambda _e, p=paned, k=key, f=fractions: self._paned_resized(p, k, f),
                add="+",
            )

    def _paned_resized(self, paned, key, fractions) -> None:
        # Only a deliberate drag stops the proportional default being kept
        # correct.  Keying this off the saved settings instead let an early
        # autosave freeze a half-built layout in place.
        if key in self._sash_touched:
            self._enforce_minimums(paned, fractions)
            return
        self._apply_fractions(paned, fractions)

    def _sash_released(self, paned, fractions, key: str = "") -> None:
        if key:
            self._sash_touched.add(key)
        if self._enforce_minimums(paned, fractions):
            self._set_status(
                "A pane was dragged shut, so it has been reopened. "
                "Panes cannot be smaller than "
                f"{self.MIN_PANE} pixels."
            )

    def _restore_layout(self, attempt: int = 0) -> None:
        """Put the window and dividers back, ignoring an unusable saved layout."""

        if attempt == 0:
            geometry = str(self.settings.get("geometry", "")).strip()
            if geometry:
                try:
                    self.geometry(geometry)
                except Exception:
                    pass
            if self.settings.get("zoomed"):
                try:
                    self.state("zoomed")
                except Exception:
                    pass
        self.update_idletasks()

        body = getattr(self, "body_paned", None)
        if body is not None and body.winfo_width() < 100 and attempt < 12:
            # The window has not been laid out yet; sash positions set now
            # would be clamped to nonsense.
            self.after(80, lambda: self._restore_layout(attempt + 1))
            return

        used_defaults = False
        for paned, key, fractions in self._paned_widgets():
            if paned is None:
                continue
            saved = [int(v) for v in (self.settings.get(key) or []) if isinstance(v, (int, float))]
            if saved and self._positions_usable(paned, saved):
                for index, value in enumerate(saved):
                    try:
                        paned.sashpos(index, value)
                    except Exception:
                        pass
                # A restored layout is the operator's, so stop re-applying
                # the proportional default over the top of it.
                self._sash_touched.add(key)
            else:
                self._apply_fractions(paned, fractions)
                used_defaults = True
            self._enforce_minimums(paned, fractions)

        if used_defaults and attempt < 20:
            # The window is often still growing to its final size here, so a
            # proportional default lands against a stale width.  Lay it out
            # once more when everything has settled.
            self.after(350, self._relayout_defaults)

        self._watch_sashes()
        self.zoom_var.set(1.0)
        self._zoom_changed()

    def _relayout_defaults(self) -> None:
        """Re-apply proportional defaults once the window has its real size."""

        self.update_idletasks()
        for paned, key, fractions in self._paned_widgets():
            if paned is None or self.settings.get(key):
                continue
            self._apply_fractions(paned, fractions)

    def _capture_layout(self) -> None:
        try:
            self.settings["zoomed"] = self.state() == "zoomed"
            if not self.settings["zoomed"]:
                self.settings["geometry"] = self.geometry()
        except Exception:
            pass

        for paned, key, _fractions in self._paned_widgets():
            if paned is None:
                continue
            try:
                count = len(paned.panes())
                positions = [int(paned.sashpos(i)) for i in range(count - 1)]
            except Exception:
                continue
            # Never remember a layout with a pane missing from it.
            if positions and self._positions_usable(paned, positions):
                self.settings[key] = positions
            else:
                self.settings[key] = []

        self.settings["zoom_mode"] = self.zoom_mode
        self.settings["zoom"] = float(self.zoom_var.get())

    def reset_layout(self) -> None:
        self._sash_touched.clear()
        for paned, key, fractions in self._paned_widgets():
            self.settings[key] = []
            if paned is not None:
                self._apply_fractions(paned, fractions)
        self.settings["geometry"] = ui_state.DEFAULTS["geometry"]
        try:
            self.state("normal")
        except Exception:
            pass
        self.geometry(ui_state.DEFAULTS["geometry"])
        self.zoom_mode = "fit"
        self.zoom_var.set(1.0)
        self._zoom_changed()
        self._set_status("Layout reset: three panes restored, zoom back to fit.")

    def _on_close(self) -> None:
        self._capture_layout()
        ui_state.save(APP_ROOT, self.settings)
        self.destroy()

    def _set_zoom(self, value: float) -> None:
        self.zoom_var.set(max(0.25, min(4.0, float(value))))
        self._zoom_changed()

    def _zoom_changed(self, _value=None) -> None:
        self.zoom_label.configure(
            text=f"Zoom {self.zoom_var.get():.2f}× ({self.zoom_mode})"
        )
        self._draw_preview("source")
        self._draw_preview("candidate")
        self._draw_preview("reference")
        self._refresh_popouts()

    def _preview_wheel(self, event) -> str:
        self._set_zoom(self.zoom_var.get() + (0.25 if event.delta > 0 else -0.25))
        return "break"

    @staticmethod
    def _checkerboard(size: tuple[int, int]) -> Image.Image:
        image = Image.new("RGBA", size, (58, 63, 69, 255))
        draw = ImageDraw.Draw(image)
        cell = 16
        for y in range(0, size[1], cell):
            for x in range(0, size[0], cell):
                if (x // cell + y // cell) % 2:
                    draw.rectangle((x, y, min(size[0], x + cell), min(size[1], y + cell)), fill=(73, 79, 86, 255))
        return image

    def _draw_preview(self, which: str) -> None:
        if which == "source":
            canvas = self.source_canvas
            image = self.source_image
        elif which == "candidate":
            canvas = self.candidate_canvas
            image = self.candidate_image
        else:
            canvas = self.reference_canvas
            image = self.reference_image
        canvas.delete("all")
        canvas.configure(scrollregion=(0, 0, max(1, canvas.winfo_width()), max(1, canvas.winfo_height())))
        if image is None:
            width = max(canvas.winfo_width(), 200)
            height = max(canvas.winfo_height(), 120)
            hint = {
                "source": "Open an ARC, then pick a texture on the left.",
                "candidate": "Generate a candidate, or load a Samurai Heroes donor.",
                "reference": "Find a /jpn counterpart or a donor to show it here.",
            }.get(which, "Nothing to show yet.")
            canvas.create_text(
                width // 2, height // 2 - 14, text="No preview",
                fill="#6f7780", font=("Segoe UI", 15),
            )
            canvas.create_text(
                width // 2, height // 2 + 14, text=hint,
                fill="#9aa3ad", font=("Segoe UI", 10),
            )
            return
        width = max(1, canvas.winfo_width() - 20)
        height = max(1, canvas.winfo_height() - 20)
        if self.zoom_mode == "actual":
            base = 1.0
        elif self.zoom_mode == "fill":
            base = max(width / image.width, height / image.height)
        else:
            base = min(width / image.width, height / image.height)
        scale = max(0.01, base * self.zoom_var.get())
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        preview = image.resize(size, Image.Resampling.NEAREST)
        backdrop = self._checkerboard(size)
        backdrop.alpha_composite(preview)
        photo = ImageTk.PhotoImage(backdrop)
        if which == "source":
            self.source_photo = photo
        elif which == "candidate":
            self.candidate_photo = photo
        else:
            self.reference_photo = photo
        x0 = max(0, (canvas.winfo_width() - size[0]) // 2)
        y0 = max(0, (canvas.winfo_height() - size[1]) // 2)
        scroll_width = max(canvas.winfo_width(), size[0] + x0)
        scroll_height = max(canvas.winfo_height(), size[1] + y0)
        canvas.configure(scrollregion=(0, 0, scroll_width, scroll_height))
        canvas.create_image(x0, y0, image=photo, anchor="nw")
        self.preview_render[which] = (scale, x0, y0)
        if which == "source":
            self._draw_region_overlay()
        # A detached preview must follow whatever the docked one is showing.
        if self.popouts:
            self._refresh_popouts()

    def _draw_region_overlay(self) -> None:
        """Outline the current text region on the source preview."""

        render = self.preview_render.get("source")
        if render is None or self.source_image is None:
            return
        try:
            x, y, width, height = (int(var.get()) for var in self.region_vars)
        except ValueError:
            return
        scale, x0, y0 = render
        self.source_canvas.delete("region")
        active = self._selected_repair_index()
        for index, box in enumerate(self.repair_regions):
            selected = index == active
            self.source_canvas.create_rectangle(
                x0 + box.left * scale,
                y0 + box.top * scale,
                x0 + box.right * scale,
                y0 + box.bottom * scale,
                outline="#ffd24a" if selected else "#4aa3ff",
                width=3 if selected else 2,
                tags="region",
            )
            self.source_canvas.create_text(
                x0 + box.left * scale + 3,
                y0 + box.top * scale + 3,
                text=str(index + 1),
                anchor="nw",
                fill="#ffd24a" if selected else "#4aa3ff",
                font=("Segoe UI", 9, "bold"),
                tags="region",
            )
        if width <= 0 or height <= 0:
            return
        self.source_canvas.create_rectangle(
            x0 + x * scale,
            y0 + y * scale,
            x0 + (x + width) * scale,
            y0 + (y + height) * scale,
            outline="#7bff7b",
            width=2,
            dash=(5, 3),
            tags="region",
        )

    def _canvas_to_image(self, event) -> tuple[float, float] | None:
        """Map a source-canvas event to source-texture pixels."""

        render = self.preview_render.get("source")
        if render is None or self.source_image is None:
            return None
        scale, x0, y0 = render
        if scale <= 0:
            return None
        x = (self.source_canvas.canvasx(event.x) - x0) / scale
        y = (self.source_canvas.canvasy(event.y) - y0) / scale
        return (
            max(0.0, min(float(self.source_image.width), x)),
            max(0.0, min(float(self.source_image.height), y)),
        )

    def _apply_drag_region(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        left, right = sorted((start[0], end[0]))
        top, bottom = sorted((start[1], end[1]))
        self.region_vars[0].set(str(int(round(left))))
        self.region_vars[1].set(str(int(round(top))))
        self.region_vars[2].set(str(max(1, int(round(right - left)))))
        self.region_vars[3].set(str(max(1, int(round(bottom - top)))))

    def _region_press(self, event) -> str:
        self._region_drag = self._canvas_to_image(event)
        return "break"

    def _region_motion(self, event) -> str:
        point = self._canvas_to_image(event)
        if self._region_drag is not None and point is not None:
            self._apply_drag_region(self._region_drag, point)
        return "break"

    def _region_release(self, event) -> str:
        start, self._region_drag = self._region_drag, None
        point = self._canvas_to_image(event)
        if start is not None and point is not None:
            self._apply_drag_region(start, point)
            # Every drag also becomes a repair box, so several small fixes can
            # be queued on one texture instead of one region at a time.
            try:
                region = self._read_region()
            except Exception:
                return "break"
            if region.width >= 4 and region.height >= 4:
                self.repair_regions.append(region)
                self._refresh_repair_list(select=len(self.repair_regions) - 1)
                self._set_status(
                    f"Repair box {len(self.repair_regions)} added: "
                    f"{region.left},{region.top} {region.width}x{region.height}. "
                    "Patch it from the donor, letter it, or erase it."
                )
        return "break"

    # ------------------------------------------------------------------
    # Repair boxes: fix part of a texture without touching the rest
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # One-button audit and repair
    # ------------------------------------------------------------------

    def _layout_for(self, texture_name: str):
        """The layout that draws this texture, and what it says is on it.

        The game ships its own sprite inventory, so a sheet does not have to be
        treated as an anonymous picture: the layout names each node and the
        texture it draws from.
        """

        if self.archive is None:
            return None, []
        try:
            layouts = layout_mod.layouts_in_archive(self.archive)
        except Exception:
            return None, []
        for found in layouts:
            using = found.nodes_using(texture_name)
            if using:
                lines = [f"The layout {found.name} draws {len(using)} sprite(s) "
                         "from this texture:"]
                for node in using:
                    role = f"  — {node.role}" if node.role else ""
                    lines.append(f"    {node.name}{role}")
                if not found.complete:
                    lines.append(f"    (recovered {len(found.nodes)} of "
                                 f"{found.node_count} nodes; the node records "
                                 "themselves are not decoded)")
                return found, lines
        return None, []

    def _ocr_engine(self):
        """One OCR engine for the session — loading the models is slow."""

        if getattr(self, "_ocr", None) is None:
            self._ocr = ocr.RapidEngine()
        return self._ocr

    def suggested_fix(self) -> None:
        """Do the best available thing to this texture, and say what that was.

        Donor first, because an official Samurai Heroes texture is
        authoritative and lossless. Failing that, treat the texture as a sheet:
        find each element, read it, and letter the ones the dictionary can
        answer for.
        """

        if self.source_image is None or self.selected_entry is None:
            messagebox.showinfo("Alrummi 3", "Select a texture first.")
            return
        name = self.selected_entry.name
        source = self.source_image.copy()
        raw = self.source_raw
        donor_index = self.donor_index
        charmap = self.character_map
        dictionary = self.project_dictionary
        ai = self.ai if str(self.ai_status.cget("text")).endswith("ready") else self.ai
        archive_path = str(self.archive.path) if self.archive is not None else ""
        self._set_progress("Auditing sheet")
        self._set_status(f"Working out the best fix for {name.split(chr(92))[-1]}…")

        def run():
            report = {"name": name, "route": "", "lines": [], "image": None,
                      "meta": {}, "lossless": None}

            # 1. an exact-size donor replaces the whole thing losslessly
            if donor_index is not None:
                preferred = []
                translated = translate_resource(charmap, name)
                if translated is not None:
                    key, info = translated
                    preferred.append((key, f"same character, matched on {info['matched_on']}"))
                for candidate in find_donor_candidates(
                    donor_index, name, source_archive=archive_path,
                    limit=8, preferred_keys=preferred,
                ):
                    try:
                        image, _info, resource = load_donor_image(
                            candidate["archive"], candidate["entry_index"])
                    except Exception:
                        continue
                    if image.size != source.size:
                        continue
                    lossless = None
                    if raw and raw[:4] == b"\0XET":
                        try:
                            donor_raw = load_donor_raw(
                                candidate["archive"], candidate["entry_index"])
                            lossless = swap_xet_payload(raw, donor_raw)
                        except Exception:
                            lossless = None
                    report.update({
                        "route": "donor",
                        "image": image,
                        "lossless": lossless,
                        "meta": {
                            "mode": "suggested_fix_donor",
                            "donor_archive": candidate["archive"],
                            "donor_resource": resource,
                            "match_reason": candidate["reason"],
                            "lossless_block_copy": lossless is not None,
                        },
                        "lines": [
                            f"SUGGESTED FIX — {name}",
                            "",
                            "Route: official Samurai Heroes donor.",
                            f"  {resource}",
                            f"  from {candidate['archive']}",
                            f"  {candidate['reason']}",
                            f"  exact size {image.width}x{image.height}",
                            "  lossless block copy: "
                            + ("yes" if lossless is not None else "no, re-encoded"),
                        ],
                    })
                    return report

            # 2. no donor: take the sheet apart asset by asset and rebuild it.
            # Reading the layouts means decompressing the whole archive, so it
            # happens here on the worker rather than on the way in.
            layout, inventory = self._layout_for(name)
            assets = sheet.find_assets(source, self._ocr_engine(),
                                       layout=layout, texture_name=name)
            sheet.translate_assets(assets, dictionary)
            # Re-lettering an already-English sheet is deliberately *not* done
            # here. Measured on the roulette sheet: the English on a patched
            # sheet was pasted on rather than drawn into the artwork's opacity
            # layers, so the mask comes out poor and the rebuild leaves boxy
            # patches and ghosting — it makes finished work worse. The
            # `reletter` route exists for a sheet that is genuinely botched;
            # it has to be asked for, not guessed at.
            relettered = False
            rebuilt, notes = sheet.rebuild_sheet(source, assets)
            applied = sum(1 for a in assets if a.ready)
            meta = {
                "mode": "suggested_fix_sheet",
                "elements": len(assets),
                "applied": applied,
            }
            report.update({
                "route": "sheet",
                "image": rebuilt if applied else None,
                "meta": meta,
                "lines": _sheet_audit(name, assets, notes, layout, inventory,
                                      relettered=relettered),
            })
            return report

        self._run_worker("autofix", run)

    def _autofix_done(self, report: dict) -> None:
        lines = list(report.get("lines") or [])
        image = report.get("image")
        meta = report.get("meta") or {}

        if report.get("route") == "donor" and image is not None:
            self._donor_prepared((image, meta, report.get("lossless")))
            headline = "Replaced from the official donor."
        elif image is not None:
            self._repair_done(image, meta,
                              f"Sheet repaired: {meta.get('applied', 0)} of "
                              f"{meta.get('elements', 0)} elements lettered.")
            headline = (f"{meta.get('applied', 0)} of {meta.get('elements', 0)} "
                        "elements lettered from the dictionary.")
        else:
            headline = "Nothing could be applied automatically — see the audit."
            lines.append("")
            lines.append(
                "Nothing was changed. Every element was already English, or its "
                "wording is not in the project dictionary. Use the SH donors tab, "
                "or letter a repair box by hand."
            )

        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", "\n".join(lines))
        self.notes_text.configure(state="disabled")
        self.preview_notebook.select(self.notes_tab)
        self._set_status(headline + "  Full audit is in the File notes tab.")

    def _style_base(self) -> Image.Image | None:
        """Style whatever is on screen: the candidate if there is one."""

        if self.candidate_image is not None:
            return self.candidate_image
        if self.source_image is not None:
            return self.source_image.copy()
        return None

    def rebuild_fortune_medallions(self) -> None:
        """Build the three main roulette fortune medallions as one candidate."""
        base = self._style_base()
        if base is None:
            messagebox.showinfo("Alrummi 3", "Select a decodable texture first.")
            return

        raw = self.translation.get("1.0", "end-1c").strip()
        labels = ["GREAT LUCK", "GOOD LUCK", "BAD LUCK"]
        if raw and raw != "English translation / replacement text":
            if "|" in raw:
                supplied = [p.strip() for p in raw.split("|") if p.strip()]
            else:
                supplied = [p.strip() for p in raw.splitlines() if p.strip()]
            for index, value in enumerate(supplied[:3]):
                labels[index] = value.upper()

        try:
            candidate, meta = medallion_fx.rebuild_fortune_sheet(base, labels)
        except Exception as exc:
            messagebox.showerror("Alrummi 3", str(exc))
            self._set_status(f"Fortune medallion rebuild failed: {exc}")
            return

        self.donor_replacement = None
        self.candidate_image = candidate
        self.candidate_meta = meta
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="normal")
        self._update_confirm_state()
        self._draw_preview("candidate")
        try:
            self.preview_notebook.select(self.review_tab)
        except Exception:
            pass
        self.style_status.configure(text="Rebuilt GREAT / GOOD / BAD LUCK medallions. Review the candidate.")
        self.output_label.configure(text="Medallions rebuilt. Review, tick confirmation, then write the new ARC.")
        self._set_status("Fortune medallion candidate generated. Source ARC remains untouched.")

    def apply_style_all(self) -> None:
        base = self._style_base()
        if base is None:
            messagebox.showinfo("Alrummi 3", "Select a decodable texture first.")
            return
        preset = self.style_var.get()
        strength = float(self.style_strength.get())
        self._set_status(f"Applying {preset}…")
        try:
            styled, meta = texture_fx.style_image(base, preset, strength)
        except Exception as exc:
            messagebox.showerror("Could not apply that style", str(exc))
            return
        self._repair_done(
            styled, meta,
            f"{preset} applied at {strength:.2f}× across the whole texture, "
            f"{styled.width}×{styled.height} preserved.",
        )
        self.style_status.configure(text=f"{preset} · {strength:.2f}× · whole texture")

    def apply_style_box(self) -> None:
        target = self._repair_target()
        if target is None:
            return
        base, box = target
        preset = self.style_var.get()
        strength = float(self.style_strength.get())
        try:
            styled, meta = texture_fx.style_region(base, box, preset, strength)
        except Exception as exc:
            messagebox.showerror("Could not apply that style", str(exc))
            return
        self._repair_done(
            styled, meta,
            f"{preset} applied at {strength:.2f}× to the {box.width}×{box.height} box "
            f"at {box.left},{box.top}; every other pixel untouched.",
        )
        self.style_status.configure(
            text=f"{preset} · {strength:.2f}× · box {box.width}×{box.height}"
        )

    def _selected_repair_index(self) -> int:
        selection = self.repair_list.curselection() if hasattr(self, "repair_list") else ()
        if selection and selection[0] < len(self.repair_regions):
            return selection[0]
        return -1

    def _refresh_repair_list(self, select: int | None = None) -> None:
        self.repair_list.delete(0, "end")
        for index, box in enumerate(self.repair_regions):
            self.repair_list.insert(
                "end",
                f"{index + 1}.  x{box.left} y{box.top}  {box.width}x{box.height}",
            )
        if select is not None and 0 <= select < len(self.repair_regions):
            self.repair_list.selection_clear(0, "end")
            self.repair_list.selection_set(select)
            self.repair_list.see(select)
        self.repair_status.configure(
            text=(f"{len(self.repair_regions)} repair box(es)."
                  if self.repair_regions else "No repair boxes yet.")
        )
        self._draw_region_overlay()

    def _repair_base(self) -> Image.Image | None:
        """Work on the candidate if one exists, otherwise start from the source."""

        if self.candidate_image is not None:
            return self.candidate_image
        if self.source_image is not None:
            return self.source_image.copy()
        return None

    def _repair_target(self) -> tuple[Image.Image, Region] | None:
        index = self._selected_repair_index()
        if index < 0:
            messagebox.showinfo("Alrummi 3", "Shift+drag on the source to mark a box first.")
            return None
        base = self._repair_base()
        if base is None:
            messagebox.showinfo("Alrummi 3", "Select a decodable texture first.")
            return None
        return base, self.repair_regions[index]

    def _repair_done(self, image: Image.Image, meta: dict, note: str) -> None:
        # A hand repair is a candidate like any other, so the existing review
        # and confirmation path applies unchanged.
        self.donor_replacement = None
        self.candidate_image = image
        self.candidate_meta = dict(meta)
        if self.source_image is not None:
            self.candidate_meta["source_dimensions"] = list(self.source_image.size)
            self.candidate_meta["candidate_dimensions"] = list(image.size)
            self.candidate_meta["dimensions_match"] = image.size == self.source_image.size
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="normal")
        self._update_confirm_state()
        self._draw_preview("candidate")
        self.output_label.configure(text="Repaired. Tick the box below and press Confirm to write.")
        self._set_status(note)

    def patch_box_from_donor(self) -> None:
        """Copy just this rectangle from the donor - the surgical repair."""

        target = self._repair_target()
        if target is None:
            return
        base, box = target
        donor = self.reference_image
        if donor is None:
            messagebox.showinfo(
                "Alrummi 3",
                "No donor is loaded. Find one in the SH donors tab (selecting a "
                "donor previews it), or use Find matching /jpn.",
            )
            return
        if self.source_image is not None and donor.size != self.source_image.size:
            messagebox.showerror(
                "Donor is a different size",
                f"The donor is {donor.width}x{donor.height} but the texture is "
                f"{self.source_image.width}x{self.source_image.height}. A box patch "
                "needs matching dimensions so the rectangle lands where it came from.",
            )
            return
        try:
            image = patch_region_from(base, donor, box)
        except Exception as exc:
            messagebox.showerror("Cannot patch that box", str(exc))
            return
        self._repair_done(
            image,
            {"mode": "region_patch_from_donor", "region": box.as_list()},
            f"Patched {box.width}x{box.height} at {box.left},{box.top} from the donor. "
            "Every other pixel is untouched.",
        )

    def letter_box(self) -> None:
        target = self._repair_target()
        if target is None:
            return
        base, box = target
        text = self._translation_text()
        if not text:
            messagebox.showinfo("Alrummi 3", "Put the English wording in the box above first.")
            return
        image, meta = render_text_in_region(
            base, text, box, clear_first=self.clear_var.get()
        )
        self._repair_done(
            image, meta,
            f"Lettered {box.width}x{box.height} at {box.left},{box.top} "
            f"in the texture's own ink colour.",
        )

    def erase_box(self) -> None:
        target = self._repair_target()
        if target is None:
            return
        base, box = target
        image, method = erase_region(base, box)
        self._repair_done(
            image, {"mode": "region_erase", "region": box.as_list(), "clear_method": method},
            f"Erased {box.width}x{box.height} at {box.left},{box.top} ({method}).",
        )

    def delete_box(self) -> None:
        index = self._selected_repair_index()
        if index < 0:
            return
        self.repair_regions.pop(index)
        self._refresh_repair_list(select=min(index, len(self.repair_regions) - 1))

    def _use_full_region(self) -> None:
        if self.source_image is None:
            return
        self.region_vars[0].set("0")
        self.region_vars[1].set("0")
        self.region_vars[2].set(str(self.source_image.width))
        self.region_vars[3].set(str(self.source_image.height))

    def _read_region(self) -> Region:
        if self.source_image is None:
            raise ValueError("select a decodable texture first")
        x, y, width, height = (int(var.get()) for var in self.region_vars)
        if width <= 0 or height <= 0:
            raise ValueError("text region width and height must be positive")
        return Region(x, y, x + width, y + height).clipped(self.source_image.size)

    def _translation_text(self) -> str:
        value = self.translation.get("1.0", "end-1c").strip()
        if value == "English translation / replacement text":
            return ""
        return value

    def analyze_selected(self) -> None:
        if self.source_image is None:
            messagebox.showinfo("Alrummi 3", "Open an ARC texture or loose image first.")
            return
        preview = io.BytesIO()
        self.source_image.save(preview, format="PNG")
        self._set_status("Asking the local vision model to read and translate the texture…")
        payload = preview.getvalue()
        name = self.source_name or "texture"
        size = self.source_image.size
        dictionary = self.project_dictionary
        self._run_worker(
            "ai",
            lambda: self._suggest_with_dictionary(payload, name, size, dictionary),
        )

    def _suggest_with_dictionary(
        self,
        payload: bytes,
        name: str,
        size: tuple[int, int],
        dictionary: dict[str, str],
    ) -> dict:
        """Read the Japanese with the model, then translate it with the project.

        The vision model is good at reading the characters and bad at knowing
        what they mean - it renders 佐竹義重 as "Sakata Yoshitaka" where the
        project's own dictionary has "Yoshishige Satake". So the model is used
        for OCR and the dictionary decides the English whenever it knows.
        """

        result = self.ai.suggest_english(payload, name, size[0], size[1])
        japanese = str(result.get("japanese", "")).strip()
        hit = dict_lookup(dictionary, japanese) if japanese else None
        if hit is not None:
            english, how = hit
            result["translation"] = english
            result["translation_source"] = how
            result["confidence"] = 1.0
        elif result.get("translation"):
            result["translation_source"] = "local model (unverified guess)"
        else:
            result["translation_source"] = ""
        return result

    @staticmethod
    def _sane_region(region: dict, size: tuple[int, int]) -> Region | None:
        """Accept a model-suggested region only if it really describes this texture.

        A vision model will happily return coordinates from an imagined
        upscaled image.  Clipping those produces a one-pixel-wide box that
        looks like the button did nothing, so an implausible box is rejected
        outright and a 0-1000 normalized box is rescaled.
        """

        try:
            left = int(region["left"])
            top = int(region["top"])
            right = int(region["right"])
            bottom = int(region["bottom"])
        except (KeyError, TypeError, ValueError):
            return None
        if right <= left or bottom <= top:
            return None
        width, height = size
        if right > width or bottom > height:
            # Qwen-VL style 0-1000 normalized coordinates are worth rescaling;
            # anything else is not this texture and is discarded.
            if max(right, bottom) > 1000:
                return None
            left = round(left / 1000 * width)
            top = round(top / 1000 * height)
            right = round(right / 1000 * width)
            bottom = round(bottom / 1000 * height)
            if right <= left or bottom <= top:
                return None
        candidate = Region(left, top, right, bottom).clipped(size)
        # A box too small to letter is not a useful suggestion.
        if candidate.width < 8 or candidate.height < 8:
            return None
        return candidate

    def _ai_finished(self, result: dict) -> None:
        translation = str(result.get("translation", "")).strip()
        japanese = str(result.get("japanese", "")).strip()
        if translation:
            self.translation.delete("1.0", "end")
            self.translation.insert("1.0", translation)
        region_note = ""
        regions = result.get("regions") or []
        if regions and isinstance(regions[0], dict) and self.source_image is not None:
            suggested = self._sane_region(regions[0], self.source_image.size)
            if suggested is None:
                region_note = (
                    " The suggested text region did not fit this texture and was "
                    "ignored — shift+drag on the source to set it."
                )
            else:
                self.region_vars[0].set(str(suggested.left))
                self.region_vars[1].set(str(suggested.top))
                self.region_vars[2].set(str(suggested.width))
                self.region_vars[3].set(str(suggested.height))
                if suggested not in self.repair_regions:
                    self.repair_regions.append(suggested)
                    self._refresh_repair_list(select=len(self.repair_regions) - 1)
        confidence = result.get("confidence", "?")
        notes = str(result.get("notes", "")).strip()
        source = str(result.get("translation_source", "")).strip()
        if translation and source:
            notes = (f"Source: {source}. " + notes).strip()
        if not translation:
            summary = "No English could be produced for this texture."
            if japanese:
                summary += f" The Japanese reads {japanese}, which is not in the project dictionary."
            summary += " Type the wording yourself, or check the SH donors tab."
        else:
            if source.startswith("project dictionary"):
                summary = f"English from the {source} — authoritative."
            else:
                summary = (
                    f"English is a local-model guess (confidence {confidence}); "
                    "the model is unreliable on proper nouns, so check it."
                )
            if japanese:
                summary += f" Read as {japanese}."
        self._set_status(summary + region_note + (f" {notes}" if notes else ""))

    def _ai_ping_finished(self, response: str) -> None:
        if "READY" in str(response).upper():
            self.ai_status.configure(text="AI: local Ollama ready")
            self._set_status("Local Ollama is ready. No cloud connection is used.")
        else:
            self.ai_status.configure(text="AI: local model responded")
            self._set_status("Local Ollama responded, but not with the expected readiness phrase.")

    def _write_finished(self, result: tuple[Path, Path, dict]) -> None:
        try:
            self.last_written = Path(result[0])
            self.last_written_target = self.archive.path if self.archive is not None else None
            self.install_button.configure(state="normal")
        except Exception:
            pass
        output_path, audit_path, verification = result
        self.confirm_var.set(False)
        self._update_confirm_state()
        self.output_label.configure(text=f"Output: {output_path}")
        self._set_status(f"Confirmed replacement written. {verification['changed_entries']} changed entry; audit saved beside it.")
        messagebox.showinfo("Alrummi 3", f"Replacement written:\n{output_path}\n\nAudit report:\n{audit_path}")

    _DONOR_FIT_MODES = {
        "Exact size only": "exact",
        "Fit inside (keep aspect)": "contain",
        "Stretch to fill": "stretch",
    }

    @staticmethod
    def _describe_donor_index(index: dict | None) -> str:
        if index is None:
            return (
                "No donor index yet. Build it once — it takes about half a minute "
                "and is cached beside the app."
            )
        return (
            f"Index: {index.get('texture_count', 0)} textures across "
            f"{index.get('archive_count', 0)} archives, built {index.get('built', '?')}."
        )

    def _refresh_donor_index_label(self) -> None:
        if self.donor_index is None:
            self.donor_index = load_donor_index(donor_index_path(APP_ROOT))
        self.donor_index_label.configure(text=self._describe_donor_index(self.donor_index))

    def build_donor_index(self) -> None:
        roots = [root for root in DEFAULT_DONOR_ROOTS if Path(root).is_dir()]
        if not roots:
            messagebox.showwarning(
                "Alrummi 3",
                "No donor tree was found at:\n" + "\n".join(DEFAULT_DONOR_ROOTS),
            )
            return
        self._set_status("Indexing the Samurai Heroes donor textures…")

        def build() -> dict:
            try:
                index = build_donor_index(
                    roots, progress=lambda done, total: setattr(self, "_scan_progress", (done, total))
                )
                save_donor_index(index, donor_index_path(APP_ROOT))
            finally:
                self._scan_progress = (0, 0)
            return index

        self._run_worker("donor_build", build)

    def _donor_index_built(self, index: dict) -> None:
        self.donor_index = index
        self.donor_index_label.configure(text=self._describe_donor_index(index))
        self._set_status(
            f"Donor index ready: {index.get('texture_count', 0)} textures from "
            f"{index.get('archive_count', 0)} archives."
        )

    def _refresh_character_map_label(self) -> None:
        if self.character_map is None:
            self.character_map = load_character_map(character_map_path(APP_ROOT))
        self.character_map_label.configure(text=self._describe_character_map(self.character_map))

    @staticmethod
    def _describe_character_map(data: dict | None) -> str:
        if data is None:
            return (
                "No character map. Utage and Samurai Heroes number their rosters "
                "differently, so build this once to match them by portrait."
            )
        return f"Character map: {data.get('matched', 0)} characters matched, built {data.get('built', '?')}."

    def build_character_map(self) -> None:
        if self.donor_index is None:
            messagebox.showinfo("Alrummi 3", "Build the donor index first.")
            return
        roots = [root for root in DEFAULT_LOCAL_ROOTS if Path(root).is_dir()]
        if not roots:
            messagebox.showwarning(
                "Alrummi 3", "No local game tree was found at:\n" + "\n".join(DEFAULT_LOCAL_ROOTS)
            )
            return
        donor = self.donor_index
        self._set_status("Matching characters across both games by portrait…")

        def build() -> dict:
            try:
                local = load_donor_index(local_index_path(APP_ROOT))
                if local is None:
                    local = build_donor_index(
                        roots,
                        progress=lambda done, total: setattr(self, "_scan_progress", (done, total)),
                    )
                    save_donor_index(local, local_index_path(APP_ROOT))
                data = build_character_map(local, donor)
                save_character_map(data, character_map_path(APP_ROOT))
            finally:
                self._scan_progress = (0, 0)
            return data

        self._run_worker("charmap", build)

    def _character_map_built(self, data: dict) -> None:
        self.character_map = data
        self.character_map_label.configure(text=self._describe_character_map(data))
        self._set_status(
            f"Character map ready: {data.get('matched', 0)} characters matched by portrait. "
            "Donor search will now follow renumbered characters across games."
        )

    def find_donors(self) -> None:
        if self.donor_index is None:
            messagebox.showinfo("Alrummi 3", "Build the donor index first.")
            return
        if self.selected_entry is None:
            messagebox.showinfo("Alrummi 3", "Select a texture in the ARC contents list first.")
            return
        index = self.donor_index
        name = self.selected_entry.name
        source_archive = str(self.archive.path) if self.archive is not None else ""
        preferred: list[tuple[str, str]] = []
        translated = translate_resource(self.character_map, name)
        if translated is not None:
            donor_key, info = translated
            preferred.append((
                donor_key,
                f"same character, matched on {info['matched_on']} (distance {info['distance']})",
            ))
        self._set_status("Searching the Samurai Heroes tree for donor textures…")
        self._run_worker(
            "donor_find", lambda: self._collect_donors(index, name, source_archive, preferred)
        )

    @staticmethod
    def _collect_donors(
        index: dict,
        name: str,
        source_archive: str,
        preferred: list[tuple[str, str]] | None = None,
    ) -> list[dict]:
        resolved: list[dict] = []
        for candidate in find_donor_candidates(
            index, name, source_archive=source_archive, limit=12, preferred_keys=preferred
        ):
            try:
                image, _info, resource = load_donor_image(candidate["archive"], candidate["entry_index"])
            except Exception:
                # A donor that will not decode is not a donor.  Skipping here
                # keeps the list honest rather than failing at Use time.
                continue
            enriched = dict(candidate)
            enriched["size"] = list(image.size)
            enriched["resource"] = resource
            # Keep the decoded donor so selecting a row previews instantly
            # instead of re-parsing the archive.
            enriched["image"] = image
            resolved.append(enriched)
        return resolved

    def _donors_found(self, candidates: list[dict]) -> None:
        self.donor_candidates = candidates
        self.donor_list.delete(0, "end")
        if not candidates:
            message = (
                "No Samurai Heroes donor matches this resource. Utage-exclusive "
                "content has no counterpart in that release."
            )
            self.donor_status.configure(text=message)
            self._set_status(message)
            return
        target = self.source_image.size if self.source_image is not None else None
        for candidate in candidates:
            size = tuple(candidate["size"])
            label = "EXACT" if target is not None and size == target else f"{size[0]}x{size[1]}"
            self.donor_list.insert(
                "end",
                f"{label:>9s}  {Path(candidate['archive']).name} #{candidate['entry_index']}",
            )
        exact = sum(1 for c in candidates if target is not None and tuple(c["size"]) == target)
        self.donor_status.configure(
            text=f"{len(candidates)} donor(s) found, {exact} at the exact source size."
        )
        self.donor_list.selection_set(0)
        self._donor_selected()

    def _show_reference(self, image, caption: str) -> None:
        """Put an image in the reference pane and bring that tab forward."""

        self.reference_image = image
        self.reference_label.configure(text=caption)
        self._draw_preview("reference")
        try:
            self.preview_notebook.select(self.reference_tab)
        except Exception:
            pass

    def _donor_selected(self, _event=None) -> None:
        selection = self.donor_list.curselection()
        if not selection or selection[0] >= len(self.donor_candidates):
            return
        candidate = self.donor_candidates[selection[0]]
        size = tuple(candidate["size"])
        exact = self.source_image is not None and tuple(size) == self.source_image.size
        self.donor_status.configure(
            text=(
                f"{candidate['resource']}\n{size[0]}×{size[1]}"
                f"{' · exact match' if exact else ' · needs resizing'} · {candidate['reason']}\n"
                f"{candidate['archive']}"
            )
        )
        image = candidate.get("image")
        if image is not None:
            self._show_reference(
                image,
                f"DONOR PREVIEW — {candidate['resource']}  ({size[0]}×{size[1]})\n"
                f"{candidate['archive']}\n{candidate['reason']}",
            )

    def use_donor(self) -> None:
        if self.source_image is None:
            messagebox.showinfo("Alrummi 3", "Select the texture you want to replace first.")
            return
        selection = self.donor_list.curselection()
        if not selection or selection[0] >= len(self.donor_candidates):
            messagebox.showinfo("Alrummi 3", "Choose a donor from the list first.")
            return
        candidate = self.donor_candidates[selection[0]]
        mode = self._DONOR_FIT_MODES.get(self.donor_fit_var.get(), "exact")
        target = self.source_image.size
        source_raw = self.source_raw
        self._set_status("Loading the donor texture…")
        self._run_worker("donor_use", lambda: self._prepare_donor(candidate, target, mode, source_raw))

    @staticmethod
    def _prepare_donor(
        candidate: dict,
        target: tuple[int, int],
        mode: str,
        source_raw: bytes | None = None,
    ) -> tuple[Image.Image, dict, bytes | None]:
        image, _info, resource = load_donor_image(candidate["archive"], candidate["entry_index"])
        fitted, meta = fit_donor_image(image, target, mode)
        meta["donor_archive"] = candidate["archive"]
        meta["donor_entry_index"] = candidate["entry_index"]
        meta["donor_resource"] = resource
        meta["match_reason"] = candidate["reason"]
        # An unscaled donor of the same size and format can be copied block for
        # block, which avoids re-encoding lettering that is already compressed.
        lossless: bytes | None = None
        if mode == "exact" and source_raw and source_raw[:4] == b"\0XET":
            try:
                donor_raw = load_donor_raw(candidate["archive"], candidate["entry_index"])
                lossless = swap_xet_payload(source_raw, donor_raw)
            except Exception:
                lossless = None
        meta["lossless_block_copy"] = lossless is not None
        return fitted, meta, lossless

    def _donor_prepared(self, result: tuple[Image.Image, dict, bytes | None]) -> None:
        image, meta, lossless = result
        self._candidate_generated((image, meta))
        # A donor supplies the whole texture, so the patch rectangle must be the
        # whole canvas rather than whatever box was left over from lettering.
        self._use_full_region()
        self.donor_replacement = lossless
        # The confirmation sits below the tabs, so point at it explicitly.
        self.output_label.configure(
            text="Donor loaded. Tick the box below and press Confirm to write a new ARC."
        )
        meta = self.candidate_meta or {}
        quality = (
            "block-for-block copy, no quality loss"
            if lossless is not None
            else "re-encoded to BC3, slight softening"
        )
        self._set_status(
            f"Donor {Path(str(meta.get('donor_archive', ''))).name} "
            f"#{meta.get('donor_entry_index')} loaded as the candidate "
            f"({meta.get('mode', '')}, {quality}). Region set to the full texture. "
            "Review both panes, then confirm."
        )

    # ------------------------------------------------------------------
    # Batch donor replacement
    # ------------------------------------------------------------------

    def _batch_family_filter(self) -> tuple[str, ...] | None:
        raw = self.batch_families.get().strip()
        if not raw:
            return None
        return tuple(part.strip() for part in raw.split(",") if part.strip())

    def _start_batch_plan(self, paths: list[Path], source_root: Path) -> None:
        if self.donor_index is None:
            messagebox.showinfo("Alrummi 3", "Build the donor index first, in the SH donors tab.")
            return
        if not paths:
            messagebox.showinfo("Alrummi 3", "No ARC archives to plan over.")
            return
        self.batch_source_root = source_root
        donor = self.donor_index
        charmap = self.character_map
        families = self._batch_family_filter()
        self._set_status(f"Planning donor replacements across {len(paths)} archives…")

        def run():
            try:
                return plan_batch(
                    paths, donor, charmap,
                    families=families,
                    progress=lambda done, total: setattr(self, "_scan_progress", (done, total)),
                )
            finally:
                self._scan_progress = (0, 0)

        self._run_worker("batch_plan", run)

    def plan_batch_loaded(self) -> None:
        paths = [archive.path for archive in self.loaded_archives]
        if not paths and self.archive is not None:
            paths = [self.archive.path]
        if not paths:
            messagebox.showinfo("Alrummi 3", "Open an ARC or a folder first.")
            return
        root = Path(os.path.commonpath([str(p) for p in paths])) if len(paths) > 1 else paths[0].parent
        if root.is_file():
            root = root.parent
        self._start_batch_plan(paths, root)

    def plan_batch_folder(self) -> None:
        selected = filedialog.askdirectory(title="Plan donor replacements for every ARC under…")
        if not selected:
            return
        root = Path(selected)
        paths = sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".arc"
        )
        self._start_batch_plan(paths, root)

    def _batch_planned(self, result: tuple[list[dict], list[str]]) -> None:
        rows, errors = result
        self.batch_rows = rows
        self._render_batch_rows()
        done = sum(1 for r in rows if r.get("already_applied"))
        ticked = sum(1 for r in rows if r.get("use"))
        message = (
            f"{len(rows)} matched textures · {done} already carry this donor · "
            f"{ticked} ticked to write."
        )
        if errors:
            message += f" {len(errors)} archives skipped."
        self.batch_summary.configure(text=message)
        self._set_status("Batch plan ready. " + message + " Review rows before writing.")

    def _render_batch_rows(self) -> None:
        self.batch_list.delete(0, "end")
        for row in self.batch_rows:
            mark = "x" if row.get("use") else " "
            if row.get("already_applied"):
                state = "done"
            elif row.get("lossless"):
                state = "lossless"
            else:
                state = "re-encode"
            self.batch_list.insert(
                "end",
                f"[{mark}] {Path(row['archive']).name:<20s} #{row['entry_index']:<3d} "
                f"{row['size'][0]}x{row['size'][1]:<4d} t{row['tier']} {state}",
            )

    def _batch_selected(self, _event=None) -> None:
        selection = self.batch_list.curselection()
        if not selection or selection[0] >= len(self.batch_rows):
            return
        row = self.batch_rows[selection[0]]
        self.batch_summary.configure(
            text=(
                f"{row['resource']}\n{row['reason']}\n"
                f"donor: {Path(row['donor_archive']).name} #{row['donor_entry_index']}"
                + ("  · already applied" if row.get("already_applied") else "")
            )
        )
        try:
            image, _info, resource = load_donor_image(row["donor_archive"], row["donor_entry_index"])
        except Exception as exc:
            self._set_status(f"Could not preview that donor: {exc}")
            return
        self._show_reference(
            image,
            f"BATCH DONOR PREVIEW — {resource}\ninto {row['resource']}\n{row['reason']}",
        )

    def _batch_toggle(self, _event=None) -> str:
        selection = self.batch_list.curselection()
        if selection and selection[0] < len(self.batch_rows):
            index = selection[0]
            self.batch_rows[index]["use"] = not self.batch_rows[index].get("use")
            self._render_batch_rows()
            self.batch_list.selection_set(index)
            self.batch_list.see(index)
        return "break"

    def _batch_set_all(self, value: bool) -> None:
        for row in self.batch_rows:
            # Never bulk-tick a row that has nothing to change or cannot be
            # copied losslessly; those need a deliberate per-row decision.
            if value and (row.get("already_applied") or not row.get("lossless")):
                row["use"] = False
            else:
                row["use"] = value
        self._render_batch_rows()
        ticked = sum(1 for r in self.batch_rows if r.get("use"))
        self.batch_summary.configure(text=f"{ticked} of {len(self.batch_rows)} rows ticked.")

    def apply_batch_plan(self) -> None:
        ticked = [row for row in self.batch_rows if row.get("use")]
        if not ticked:
            messagebox.showinfo("Alrummi 3", "No rows are ticked.")
            return
        archives = len({row["archive"] for row in ticked})
        if not messagebox.askyesno(
            "Confirm batch write",
            f"Write {len(ticked)} replacements across {archives} archives?\n\n"
            "Every output goes to a folder you choose next. No source archive is "
            "modified, and each output gets its own audit JSON.",
        ):
            return
        selected = filedialog.askdirectory(title="Choose an output folder for the rebuilt archives")
        if not selected:
            return
        output_root = Path(selected)
        source_root = self.batch_source_root or Path(ticked[0]["archive"]).parent
        try:
            if output_root.resolve() == source_root.resolve() or source_root.resolve() in output_root.resolve().parents:
                messagebox.showerror(
                    "Safety stop",
                    "Choose an output folder outside the source tree. Alrummi 3 never "
                    "writes into the archives it read.",
                )
                return
        except OSError:
            pass
        rows = list(self.batch_rows)
        self._set_status(f"Writing {len(ticked)} replacements…")

        def run():
            try:
                return apply_batch(
                    rows, output_root, source_root,
                    progress=lambda done, total: setattr(self, "_scan_progress", (done, total)),
                )
            finally:
                self._scan_progress = (0, 0)

        self._run_worker("batch_apply", run)

    def _batch_applied(self, result: dict) -> None:
        message = (
            f"Wrote {result['archives_written']} archives "
            f"({result['replacements_written']} replacements) to {result['output_root']}."
        )
        if result.get("already_identical"):
            message += f" {result['already_identical']} were already identical and were skipped."
        if result["failures"]:
            message += f" {len(result['failures'])} failed."
        self.batch_summary.configure(text=message)
        self._set_status(message)
        if result["failures"]:
            messagebox.showwarning(
                "Some archives failed",
                "\n".join(result["failures"][:15])
                + ("\n…" if len(result["failures"]) > 15 else ""),
            )
        else:
            messagebox.showinfo("Alrummi 3", message)

    # ------------------------------------------------------------------
    # Dialogue editing
    # ------------------------------------------------------------------

    DIALOGUE_ROM = Path(r"E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom")

    def open_dialogue(self) -> None:
        start = self.DIALOGUE_ROM / "jpn" / "id"
        selected = filedialog.askopenfilename(
            title="Open a Japanese dialogue archive (rom/jpn/id/msg_m###_pl###.arc)",
            initialdir=str(start if start.is_dir() else Path.home()),
            filetypes=[("Message archives", "msg_*.arc"), ("ARC archives", "*.arc")],
        )
        if not selected:
            return
        path = Path(selected)
        self._set_status(f"Decoding {path.name}…")

        def run():
            if self.glyph_maps is None:
                self.glyph_maps = msg_edit.load_glyph_maps(APP_ROOT)
            rows = msg_edit.decode_archive(path, self.glyph_maps.get(path.name, {}))
            filled = 0
            for row in rows:
                if row["japanese"].strip():
                    hit = dict_lookup(self.project_dictionary, row["japanese"])
                    if hit:
                        row["english"] = hit[0]
                        row["source"] = hit[1]
                        filled += 1
            return path, rows, filled

        self._run_worker("dialogue_open", run)

    def _dialogue_opened(self, result: tuple[Path, list[dict], int]) -> None:
        path, rows, filled = result
        self.dialogue_path = path
        self.dialogue_rows = rows
        self._refresh_dialogue_list()
        self._update_dialogue_coverage()
        self.preview_notebook.select(self.dialogue_tab)
        self._set_status(
            f"{path.name}: {len(rows)} speeches, {filled} filled from the project dictionary. "
            "Review the rest, then build."
        )

    def _update_dialogue_coverage(self) -> None:
        rows = self.dialogue_rows
        if not rows:
            self.dialogue_coverage.configure(text="No dialogue archive open.")
            return
        filled = sum(1 for r in rows if r.get("english", "").strip())
        signed = sum(1 for r in rows if r.get("signed_off"))
        needs = sum(1 for r in rows if r["japanese"].strip() and not r.get("english", "").strip())
        problems = sum(1 for r in rows if msg_edit.validate_row(r))
        self.dialogue_coverage.configure(
            text=(
                f"{self.dialogue_path.name if self.dialogue_path else ''} · {len(rows)} speeches · "
                f"{filled} filled · {signed} signed off · {needs} still need wording · "
                f"{problems} with layout problems"
            )
        )

    def _dialogue_matches_filter(self, row: dict) -> bool:
        mode = self.dialogue_filter.get()
        if mode == "All":
            return True
        if mode == "Needs wording":
            return bool(row["japanese"].strip()) and not row.get("english", "").strip()
        if mode == "Signed off":
            return bool(row.get("signed_off"))
        if mode == "Not signed off":
            return not row.get("signed_off")
        if mode == "Problems":
            return bool(msg_edit.validate_row(row))
        return True

    def _refresh_dialogue_list(self) -> None:
        self.dialogue_list.delete(0, "end")
        self.dialogue_view = []
        for index, row in enumerate(self.dialogue_rows):
            if not self._dialogue_matches_filter(row):
                continue
            self.dialogue_view.append(index)
            mark = "x" if row.get("signed_off") else " "
            english = row.get("english", "").replace("\n", " / ")
            japanese = row["japanese"].replace("\n", " / ")
            self.dialogue_list.insert(
                "end",
                f"[{mark}] {row['record']:04d}.{row['speech']}  {japanese[:22]:<22s} > {english[:44]}",
            )
        self._update_dialogue_coverage()

    def _dialogue_selected(self, _event=None) -> None:
        selection = self.dialogue_list.curselection()
        if not selection or selection[0] >= len(self.dialogue_view):
            return
        row = self.dialogue_rows[self.dialogue_view[selection[0]]]
        self.dialogue_jp.configure(state="normal")
        self.dialogue_jp.delete("1.0", "end")
        self.dialogue_jp.insert("1.0", row["japanese"])
        self.dialogue_jp.configure(state="disabled")
        self.dialogue_en.delete("1.0", "end")
        self.dialogue_en.insert("1.0", row.get("english", ""))
        self._dialogue_validate_live()

    def _dialogue_validate_live(self) -> None:
        selection = self.dialogue_list.curselection()
        if not selection or selection[0] >= len(self.dialogue_view):
            return
        row = dict(self.dialogue_rows[self.dialogue_view[selection[0]]])
        row["english"] = self.dialogue_en.get("1.0", "end-1c")
        problems = msg_edit.validate_row(row)
        wrapped = msg_edit.wrap(row["english"])
        lines = wrapped.count("\n") + 1 if row["english"].strip() else 0
        longest = max((len(l) for l in wrapped.split("\n")), default=0)
        self.dialogue_problems.configure(
            text=("  ".join(problems) if problems else f"ok · {lines} line(s), longest {longest}")
        )

    def apply_dialogue_edit(self, sign_off: bool = True) -> None:
        selection = self.dialogue_list.curselection()
        if not selection or selection[0] >= len(self.dialogue_view):
            return
        index = self.dialogue_view[selection[0]]
        row = self.dialogue_rows[index]
        row["english"] = self.dialogue_en.get("1.0", "end-1c").strip("\n")
        row["source"] = "signed off by hand"
        if sign_off:
            row["signed_off"] = True
        position = selection[0]
        self._refresh_dialogue_list()
        if position < self.dialogue_list.size():
            self.dialogue_list.selection_set(position)
            self.dialogue_list.see(position)
            self._dialogue_selected()

    def fill_dialogue_from_dictionary(self) -> None:
        """Re-run the project dictionary over every speech that has no wording.

        Signed-off rows are left alone: a hand decision outranks a lookup.
        """

        if not self.dialogue_rows:
            messagebox.showinfo("Alrummi 3", "Open a dialogue archive first.")
            return
        if not self.project_dictionary:
            messagebox.showwarning(
                "Alrummi 3",
                "The project dictionary is not loaded, so there is nothing to fill from.",
            )
            return
        filled = 0
        for row in self.dialogue_rows:
            if row.get("signed_off") or row.get("english", "").strip():
                continue
            if not row["japanese"].strip():
                continue
            hit = dict_lookup(self.project_dictionary, row["japanese"])
            if hit:
                row["english"], row["source"] = hit
                filled += 1
        self._refresh_dialogue_list()
        self._set_status(f"Filled {filled} more speeches from the project dictionary.")

    def sign_off_filled(self) -> None:
        count = 0
        for row in self.dialogue_rows:
            if row.get("english", "").strip() and not msg_edit.validate_row(row):
                row["signed_off"] = True
                count += 1
        self._refresh_dialogue_list()
        self._set_status(f"Signed off {count} speeches that have wording and no layout problems.")

    def build_dialogue_archive(self) -> None:
        if not self.dialogue_rows or self.dialogue_path is None:
            messagebox.showinfo("Alrummi 3", "Open a dialogue archive first.")
            return
        rows = self.dialogue_rows
        needs = sum(1 for r in rows if r["japanese"].strip() and not r.get("english", "").strip())
        unsigned = sum(1 for r in rows if r.get("english", "").strip() and not r.get("signed_off"))
        problems = sum(1 for r in rows if msg_edit.validate_row(r))
        donor = msg_edit.find_latin_donor(self.dialogue_path, self.DIALOGUE_ROM)
        if donor is None:
            messagebox.showerror(
                "No Latin donor",
                "The Samurai Heroes donor directory was not found:\n"
                f"{self.DIALOGUE_ROM / 'eng' / 'id_msg_BACKUP_pre_desync_fix'}",
            )
            return
        message = (
            f"Build {self.dialogue_path.name} as English?\n\n"
            f"{len(rows)} speeches\n"
            f"{needs} still have no wording and will be transliterated\n"
            f"{unsigned} have wording you have not signed off\n"
            f"{problems} have layout problems\n\n"
            f"Latin font donor: {donor.name}\n\n"
            "The source archive is never modified. The build is verified against "
            "the project's five invariants before it is written."
        )
        if not messagebox.askyesno("Confirm dialogue build", message):
            return
        output = filedialog.asksaveasfilename(
            title="Save the English dialogue archive",
            initialfile=self.dialogue_path.name,
            defaultextension=".arc",
            filetypes=[("ARC archives", "*.arc")],
        )
        if not output:
            return
        out_path = Path(output)
        if out_path.resolve() == self.dialogue_path.resolve():
            messagebox.showerror("Safety stop", "Choose a different file. The source is never overwritten.")
            return
        source = self.dialogue_path
        self._set_status("Building the English dialogue archive…")

        def run():
            built, stats = msg_edit.build_english_archive(
                source, donor, rows,
                progress=lambda done, total: setattr(self, "_scan_progress", (done, total)),
            )
            report = msg_edit.verify_english_build(source, built)
            if report["status"] == "pass":
                out_path.write_bytes(built)
                audit = out_path.with_suffix(out_path.suffix + ".audit.json")
                audit.write_text(json.dumps({
                    "tool": "Alrummi 3 dialogue build",
                    "source": str(source),
                    "donor": str(donor),
                    "output": str(out_path),
                    "stats": stats,
                    "invariants": report["checks"],
                    "signed_off": sum(1 for r in rows if r.get("signed_off")),
                }, indent=1, ensure_ascii=False), encoding="utf-8")
            self._scan_progress = (0, 0)
            return out_path, stats, report

        self._run_worker("dialogue_build", run)

    def _dialogue_built(self, result: tuple[Path, dict, dict]) -> None:
        out_path, stats, report = result
        lines = [f"{label}: {'PASS' if ok else 'FAIL'}" for label, ok in report["checks"].items()]
        if report["status"] == "pass":
            self._set_status(f"Wrote {out_path}. All five invariants pass.")
            messagebox.showinfo(
                "Dialogue archive written",
                f"{out_path}\n\n"
                f"{stats['translated']} translated, {stats['transliterated']} transliterated, "
                f"{stats['budget']} reveal budgets rewritten, {stats['blank_runs']} blank runs preserved.\n\n"
                + "\n".join(lines),
            )
        else:
            self._set_status("Build refused: an invariant failed. Nothing was written.")
            messagebox.showerror(
                "Build refused",
                "The build failed the project's invariants and was NOT written:\n\n"
                + "\n".join(lines),
            )

    # ------------------------------------------------------------------
    # File notes, and whole-archive actions
    # ------------------------------------------------------------------

    def _update_file_notes(self) -> None:
        """Explain the selected resource: what it is, what it pairs with."""

        if not hasattr(self, "notes_text"):
            return
        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        if self.archive is None or self.selected_entry is None or self.source_raw is None:
            self.notes_text.insert("1.0", "Select a resource to see what it is.")
            self.notes_text.configure(state="disabled")
            return
        entry = self.selected_entry
        lines = [
            f"RESOURCE  {entry.name}",
            f"ARCHIVE   {self.archive.path}",
            f"          entry {entry.index} of {len(self.archive.entries)} · "
            f"{self.archive.platform} v{self.archive.version}",
            f"SIZE      {len(self.source_raw)} bytes raw, {entry.compressed_size} packed"
            f"{' (stored, not compressed)' if entry.compressed_size == entry.raw_size else ''}",
            f"TYPE HASH 0x{entry.type_hash:08X}  ({type_label(entry.type_hash, entry.name)})",
            "",
        ]
        lines += file_notes.describe_entry(self.source_raw, entry.name)

        # Everything else in this archive that shares the resource name is a
        # companion: a GSM's FIM and CSA, a texture's layout.
        same = [e for e in self.archive.entries
                if e.index != entry.index and e.name == entry.name]
        lines.append("")
        lines.append("IN THIS ARCHIVE, SAME NAME")
        if same:
            for e in same:
                raw = unpack_entry(e)
                magic = raw[:4]
                short = file_notes.TYPE_NOTES.get(magic, ("unknown",))[0]
                lines.append(f"       entry {e.index}: {short}")
        else:
            lines.append("       (none - this resource stands alone here)")

        # Cross-game counterpart, if the character map knows this one.
        translated = translate_resource(self.character_map, entry.name)
        lines.append("")
        lines.append("SAMURAI HEROES COUNTERPART")
        if translated is not None:
            key, info = translated
            lines.append(f"       {key}")
            lines.append(
                f"       matched on {info['matched_on']} at distance {info['distance']} "
                f"(margin {info['margin']})"
            )
        else:
            lines.append("       not matched - either not a per-character resource,")
            lines.append("       or the character map has not been built yet.")

        lines.append("")
        lines.append("COPIES ELSEWHERE")
        lines.append("       Press the button below to search both game trees.")
        self.notes_text.insert("1.0", "\n".join(lines))
        self.notes_text.configure(state="disabled")

    def find_resource_copies(self) -> None:
        if self.selected_entry is None:
            messagebox.showinfo("Alrummi 3", "Select a resource first.")
            return
        name = self.selected_entry.name
        donor = self.donor_index
        local = load_donor_index(local_index_path(APP_ROOT))
        if donor is None and local is None:
            messagebox.showinfo(
                "Alrummi 3",
                "Build the donor index (SH donors tab) so there is something to search.",
            )
            return
        self._set_status("Searching both trees for copies of this resource…")

        def run():
            base = name.replace("/", "\\").split("\\")[-1].lower()
            out = []
            for label, index in (("Utage", local), ("Samurai Heroes", donor)):
                if not index:
                    continue
                refs = index.get("by_key", {}).get(base, [])
                archives = index.get("archives", [])
                paths = sorted({archives[p] for p, _e in refs if p < len(archives)})
                out.append((label, paths))
            return name, out

        self._run_worker("copies", run)

    def _copies_found(self, result) -> None:
        name, groups = result
        lines = [f"COPIES OF {name.replace(chr(92), '/').split('/')[-1]}", ""]
        total = 0
        for label, paths in groups:
            lines.append(f"{label}: {len(paths)} archive(s)")
            total += len(paths)
            for path in paths[:40]:
                lines.append(f"    {path}")
            if len(paths) > 40:
                lines.append(f"    … and {len(paths) - 40} more")
            lines.append("")
        lines.append(
            "Changing one copy is not enough when the game reads another. The "
            "officer name plates in particular exist in three places."
        )
        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", "\n".join(lines))
        self.notes_text.configure(state="disabled")
        self.preview_notebook.select(self.notes_tab)
        self._set_status(f"{total} archives carry a resource of that name.")

    def replace_all_in_archive(self) -> None:
        """Plan and apply every available donor for the open archive at once."""

        if self.archive is None:
            messagebox.showinfo("Alrummi 3", "Open an ARC first.")
            return
        if self.donor_index is None:
            messagebox.showinfo("Alrummi 3", "Build the donor index first.")
            return
        path = self.archive.path
        donor = self.donor_index
        charmap = self.character_map
        self._set_progress("Checking textures")
        self._set_status(f"Looking for donors for every texture in {path.name}…")

        def run():
            try:
                rows, errors = plan_batch(
                    [path], donor, charmap, families=None,
                    progress=lambda done, total: setattr(self, "_scan_progress", (done, total)),
                )
            finally:
                self._scan_progress = (0, 0)
            return path, rows, errors

        self._run_worker("whole_arc", run)

    def _whole_arc_done(self, result) -> None:
        path, rows, errors = result
        textures = [e for e in (self.archive.entries if self.archive else [])
                    if type_label(e.type_hash, e.name) in ("tex", "texture")]
        ready = [r for r in rows if r.get("use")]
        done = [r for r in rows if r.get("already_applied")]
        weak = [r for r in rows if not r.get("use") and not r.get("already_applied")]
        matched = {r["entry_index"] for r in rows}
        nodonor = [e for e in textures if e.index not in matched]

        self.batch_rows = rows
        self.batch_source_root = path.parent
        self._render_batch_rows()

        summary = [
            f"{path.name}",
            f"{len(textures)} textures in this archive",
            f"{len(ready)} ready to replace (portrait-matched, exact size, lossless)",
            f"{len(done)} already carry the donor",
            f"{len(weak)} matched but weaker - review them in the Batch tab",
            f"{len(nodonor)} have no donor at all",
        ]
        self.batch_summary.configure(text=" · ".join(summary[1:]))
        if nodonor:
            summary.append("")
            summary.append("NO DONOR - these need lettering or re-rendering:")
            for e in nodonor[:25]:
                summary.append(f"    {e.name}")
            if len(nodonor) > 25:
                summary.append(f"    … and {len(nodonor) - 25} more")
        if errors:
            summary.append("")
            summary.append(f"{len(errors)} problems while reading the archive.")
        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", "\n".join(summary))
        self.notes_text.configure(state="disabled")
        self.preview_notebook.select(self.notes_tab)
        self._set_status(
            f"{len(ready)} of {len(textures)} textures are ready to replace. "
            "The plan is loaded in the Batch tab - review it, then write."
        )
        self.action_notebook.select(2)

    # ------------------------------------------------------------------
    # Installing into the game tree, and taking it back out
    # ------------------------------------------------------------------

    def install_last_build(self) -> None:
        if self.last_written is None or not self.last_written.is_file():
            messagebox.showinfo("Alrummi 3", "Write a build first.")
            return
        target = self.last_written_target
        if target is None:
            messagebox.showinfo("Alrummi 3", "No install target is known for that build.")
            return
        try:
            report = installer.check_compatible(self.last_written, target)
        except Exception as exc:
            messagebox.showerror("Refused", f"That build cannot replace the target:\n\n{exc}")
            return
        if not messagebox.askyesno(
            "Install into the game tree",
            f"Replace:\n{target}\n\nwith:\n{self.last_written}\n\n"
            f"{report['entries']} entries, {report['platform']} v{report['version']}.\n\n"
            "The current file is backed up first and can be reverted. "
            "Cold-boot RPCS3 afterwards and check the actual screen.",
        ):
            return
        try:
            entry = installer.install(self.last_written, target, APP_ROOT, note=self.source_name)
        except Exception as exc:
            messagebox.showerror("Install failed", str(exc))
            return
        self._set_status(f"Installed into {target}. Backup: {entry['backup']}")
        messagebox.showinfo(
            "Installed",
            f"{target}\n\nBacked up to:\n{entry['backup']}\n\n"
            "Cold-boot RPCS3 and look at the screen before installing more.",
        )

    def show_installs(self) -> None:
        entries = installer.load_manifest(APP_ROOT)
        if not entries:
            messagebox.showinfo("Alrummi 3", "Nothing has been installed through Alrummi 3 yet.")
            return
        window = tk.Toplevel(self)
        window.title("Alrummi 3 — installs")
        window.geometry("900x420")
        window.configure(bg="#17191c")
        frame = ttk.Frame(window, style="Panel.TFrame", padding=10)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Every archive Alrummi 3 has installed, newest last.",
                  style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        listbox = tk.Listbox(frame, bg="#17191c", fg="#e8eaed", selectbackground="#1f6f3f",
                             relief="flat", font=("Consolas", 9))
        listbox.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        for entry in entries:
            mark = "reverted" if entry.get("reverted") else "installed"
            listbox.insert("end", f"[{mark:9s}] {entry['installed']}  {Path(entry['target']).name}"
                                  f"   {entry['target']}")
        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.grid(row=2, column=0, sticky="ew")

        def revert_selected():
            selection = listbox.curselection()
            if not selection:
                return
            index = selection[0]
            if not messagebox.askyesno(
                "Revert", f"Restore the original of:\n{entries[index]['target']}?"
            ):
                return
            try:
                installer.revert(index, APP_ROOT)
            except Exception as exc:
                messagebox.showerror("Revert failed", str(exc))
                return
            listbox.delete(index)
            listbox.insert(index, f"[reverted ] {entries[index]['installed']}  "
                                  f"{Path(entries[index]['target']).name}   {entries[index]['target']}")
            self._set_status(f"Reverted {entries[index]['target']}")

        def revert_everything():
            if not messagebox.askyesno(
                "Revert everything",
                "Restore the original of every archive Alrummi 3 installed?",
            ):
                return
            result = installer.revert_all(APP_ROOT)
            messagebox.showinfo(
                "Revert", f"Reverted {result['reverted']} archive(s)."
                + (f"\n\n{len(result['failed'])} failed." if result["failed"] else ""))
            window.destroy()

        ttk.Button(buttons, text="Revert selected", command=revert_selected).pack(side="left")
        ttk.Button(buttons, text="Revert everything", style="Danger.TButton",
                   command=revert_everything).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")

    # ------------------------------------------------------------------
    # Dialogue batch: survey and build every archive
    # ------------------------------------------------------------------

    def survey_dialogue(self) -> None:
        start = self.DIALOGUE_ROM / "jpn" / "id"
        selected = filedialog.askdirectory(
            title="Survey every dialogue archive under…",
            initialdir=str(start if start.is_dir() else Path.home()),
        )
        if not selected:
            return
        root = Path(selected)
        paths = sorted(p for p in root.rglob("msg_m*.arc") if p.is_file())
        if not paths:
            messagebox.showinfo("Alrummi 3", "No msg_m*.arc archives under that folder.")
            return
        dictionary = self.project_dictionary
        if not dictionary:
            messagebox.showwarning(
                "Alrummi 3",
                "The project dictionary is not loaded, so a survey would report "
                "everything as untranslated.",
            )
            return
        self._set_progress("Surveying")
        self._set_status(f"Surveying {len(paths)} dialogue archives…")

        def run():
            try:
                if self.glyph_maps is None:
                    self.glyph_maps = msg_edit.load_glyph_maps(APP_ROOT)
                return msg_batch.survey(
                    paths, self.glyph_maps, dictionary,
                    progress=lambda done, total: setattr(self, "_scan_progress", (done, total)),
                )
            finally:
                self._scan_progress = (0, 0)

        self._run_worker("msg_survey", run)

    def _dialogue_surveyed(self, rows: list[dict]) -> None:
        self.dialogue_survey = rows
        self._render_msgbatch()
        total = msg_batch.summarise(rows)
        done = total["filled"] + total["already_english"]
        percent = done / max(1, total["japanese"]) * 100
        message = (
            f"{total['archives']} archives · {total['speeches']:,} speeches · "
            f"{done:,} of {total['japanese']:,} Japanese speeches already covered "
            f"({percent:.1f}%) · {total['missing']:,} need wording · "
            f"{total['problems']:,} layout problems · {total['ready']} ready to build"
        )
        self.msgbatch_summary.configure(text=message)
        self._set_status(message)

    def _msgbatch_matches(self, row: dict) -> bool:
        mode = self.msgbatch_filter.get()
        if mode == "All":
            return True
        if mode == "Ready":
            return bool(row.get("ready"))
        if mode == "Needs wording":
            return row.get("missing", 0) > 0
        if mode == "Layout problems":
            return row.get("problems", 0) > 0
        if mode == "No glyph map":
            return not row.get("has_glyph_map")
        return True

    def _render_msgbatch(self) -> None:
        self.msgbatch_list.delete(0, "end")
        self.dialogue_view_rows = []
        for index, row in enumerate(self.dialogue_survey):
            if not self._msgbatch_matches(row):
                continue
            self.dialogue_view_rows.append(index)
            mark = "x" if row.get("use") else " "
            state = "ready" if row.get("ready") else (
                "no map" if not row.get("has_glyph_map") else
                f"-{row.get('missing', 0)}/{row.get('problems', 0)}"
            )
            self.msgbatch_list.insert(
                "end",
                f"[{mark}] {row['name']:<22s} {row['japanese']:5d} jp  "
                f"{row['filled']:5d} filled  {state}",
            )
        ticked = sum(1 for r in self.dialogue_survey if r.get("use"))
        if self.dialogue_survey:
            self.msgbatch_summary.configure(
                text=f"{self.msgbatch_list.size()} shown · {ticked} ticked of "
                     f"{len(self.dialogue_survey)} archives"
            )

    def _msgbatch_selected(self, _event=None) -> None:
        """Open the highlighted archive in the editor to fill its gaps."""

        selection = self.msgbatch_list.curselection()
        if not selection or selection[0] >= len(self.dialogue_view_rows):
            return
        row = self.dialogue_survey[self.dialogue_view_rows[selection[0]]]
        self._set_status(
            f"{row['name']}: {row['filled']} filled, {row['missing']} need wording, "
            f"{row['problems']} layout problems."
        )

    def _msgbatch_toggle(self, _event=None) -> str:
        selection = self.msgbatch_list.curselection()
        if selection and selection[0] < len(self.dialogue_view_rows):
            index = self.dialogue_view_rows[selection[0]]
            row = self.dialogue_survey[index]
            row["use"] = not row.get("use")
            position = selection[0]
            self._render_msgbatch()
            self.msgbatch_list.selection_set(position)
            self.msgbatch_list.see(position)
        return "break"

    def _msgbatch_set_all(self, value: bool) -> None:
        for row in self.dialogue_survey:
            # Never bulk-tick an archive that is not ready: it would ship
            # transliterated junk where wording is still missing.
            row["use"] = bool(value and row.get("ready"))
        self._render_msgbatch()

    def build_dialogue_batch(self) -> None:
        ticked = [r for r in self.dialogue_survey if r.get("use")]
        if not ticked:
            messagebox.showinfo("Alrummi 3", "No archives are ticked.")
            return
        not_ready = [r for r in ticked if not r.get("ready")]
        message = (
            f"Build {len(ticked)} dialogue archives?\n\n"
            f"{sum(r['filled'] for r in ticked):,} speeches come from the project dictionary.\n"
            f"{sum(r['missing'] for r in ticked):,} have no wording and would be transliterated.\n"
            f"{sum(r['problems'] for r in ticked):,} have layout problems.\n\n"
        )
        if not_ready:
            message += f"{len(not_ready)} of them are NOT marked ready.\n\n"
        message += (
            "Each build is checked against the project's five invariants and is "
            "written only if all five pass. Sources are never modified."
        )
        if not messagebox.askyesno("Confirm dialogue batch", message):
            return
        selected = filedialog.askdirectory(title="Choose an output folder for the built archives")
        if not selected:
            return
        output_root = Path(selected)
        rom = self.DIALOGUE_ROM
        try:
            if rom.resolve() in output_root.resolve().parents or output_root.resolve() == rom.resolve():
                messagebox.showerror(
                    "Safety stop",
                    "Choose an output folder outside the game tree. Alrummi 3 never "
                    "writes into the archives it read.",
                )
                return
        except OSError:
            pass
        rows = list(self.dialogue_survey)
        dictionary = self.project_dictionary
        self._set_progress("Building dialogue")
        self._set_status(f"Building {len(ticked)} dialogue archives…")

        def run():
            try:
                return msg_batch.build_batch(
                    rows, rom, output_root, self.glyph_maps or {}, dictionary,
                    progress=lambda done, total: setattr(self, "_scan_progress", (done, total)),
                )
            finally:
                self._scan_progress = (0, 0)

        self._run_worker("msg_batch", run)

    def _dialogue_batch_done(self, result: dict) -> None:
        # Report the two kinds of untranslated speech separately: one is a
        # speech that was already English and passed through untouched, the
        # other is Japanese that genuinely lost its meaning.
        message = (
            f"Wrote {result['archives_written']} dialogue archives to "
            f"{result['output_root']}: {result['translated']:,} translated, "
            f"{result.get('passthrough_english', 0):,} already English and passed "
            f"through, {result.get('japanese_lost', 0):,} Japanese with no wording."
        )
        if result["archives_failed"]:
            message += f" {result['archives_failed']} were refused."
        self.msgbatch_summary.configure(text=message)
        self._set_status(message)
        if result["failed"]:
            detail = "\n".join(f"{f['name']}: {f['reason'][:90]}" for f in result["failed"][:15])
            messagebox.showwarning(
                "Some archives were refused",
                "These failed their invariants and were NOT written:\n\n" + detail
                + ("\n…" if len(result["failed"]) > 15 else ""),
            )
        else:
            messagebox.showinfo("Alrummi 3", message)

    def show_extensions(self) -> None:
        if not self.extensions:
            message = "No extension manifests found. Add reviewed updates under the Alrummi3\\updates folder."
        else:
            rows = []
            for extension in self.extensions:
                capabilities = ", ".join(extension.capabilities) or "none listed"
                rows.append(f"{extension.name} {extension.version} — {extension.status}\n  {capabilities}\n  {extension.description}")
            message = "\n\n".join(rows)
            message += "\n\nDrop-zone: " + str(APP_ROOT / "updates")
        messagebox.showinfo("Alrummi 3 extensions", message)

    def generate(self) -> None:
        if self.source_image is None:
            messagebox.showinfo("Alrummi 3", "Open an ARC texture or loose image first.")
            return
        try:
            region = self._read_region()
            text = self._translation_text()
            mode = self.generation_mode_var.get()
            if mode == "Lettering replacement" and not text:
                raise ValueError("enter English wording for lettering replacement")
            source = self.source_image.copy()
            clear_existing = self.clear_var.get()
            polish = self.polish_var.get()
            self.confirm_var.set(False)
            self._update_confirm_state()
            self._set_status("Generating a full visual texture copy…")
            self._run_worker("generate", lambda: self._generate_candidate(source, text, region, mode, clear_existing, polish))
        except Exception as exc:
            messagebox.showerror("Could not generate candidate", str(exc))

    @staticmethod
    def _generate_candidate(
        source: Image.Image,
        text: str,
        region: Region,
        mode: str,
        clear_existing: bool,
        polish: bool,
    ) -> tuple[Image.Image, dict]:
        if mode == "Lettering replacement":
            return generate_candidate(source, text, region, clear_existing=clear_existing)
        return generate_visual_copy(source, text, region, clear_existing=clear_existing, polish=polish)

    def _candidate_generated(self, result: tuple[Image.Image, dict]) -> None:
        # A newly rendered candidate is never a donor, so drop any stashed
        # lossless payload before the new one is reviewed.
        self.donor_replacement = None
        self.candidate_image, self.candidate_meta = result
        if self.source_image is None:
            return
        self.candidate_meta["source_dimensions"] = list(self.source_image.size)
        self.candidate_meta["candidate_dimensions"] = list(self.candidate_image.size)
        self.candidate_meta["dimensions_match"] = self.candidate_image.size == self.source_image.size
        self.confirm_var.set(False)
        self.save_candidate_button.configure(state="normal")
        self._update_confirm_state()
        # Put the result in front of the user rather than leaving it on a tab
        # they might not be looking at.
        try:
            self.preview_notebook.select(self.review_tab)
        except Exception:
            pass
        self._draw_preview("candidate")
        self._refresh_popouts()
        self.preview_meta.configure(
            text=(
                f"{self.source_name or 'source image'}\n"
                f"Source {self.source_image.width}×{self.source_image.height} · "
                f"candidate {self.candidate_image.width}×{self.candidate_image.height} · "
                "exact dimensions preserved"
            )
        )
        self._set_status("Complete visual candidate generated. Review the full texture, then confirm only when it looks right.")

    def _update_confirm_state(self) -> None:
        enabled = bool(self.confirm_var.get() and self.candidate_image is not None and self.selected_entry is not None and self.source_raw is not None)
        self.confirm_button.configure(state="normal" if enabled else "disabled")

    def confirm_write(self) -> None:
        if not self.confirm_var.get() or self.archive is None or self.selected_entry is None or self.source_raw is None or self.candidate_image is None or self.candidate_meta is None:
            return
        try:
            if self.source_image is None or self.candidate_image.size != self.source_image.size:
                raise ValueError("candidate dimensions do not match the source texture")
            region = self._read_region()
            if self.donor_replacement is not None:
                replacement = self.donor_replacement
            else:
                replacement = encode_replacement(
                    self.source_raw, self.selected_entry.name, self.candidate_image, region
                )
        except Exception as exc:
            messagebox.showerror("Cannot write replacement", str(exc))
            return
        default_name = self.archive.path.stem + "_alrummi3.arc"
        output = filedialog.asksaveasfilename(
            title="Save confirmed Alrummi 3 ARC",
            initialdir=str(self.archive.path.parent),
            initialfile=default_name,
            defaultextension=".arc",
            filetypes=[("ARC archives", "*.arc")],
        )
        if not output:
            return
        output_path = Path(output)
        if output_path.resolve() == self.archive.path.resolve():
            messagebox.showerror("Safety stop", "Choose a new output filename. The source ARC is never overwritten by Alrummi 3.")
            return
        self._set_status("Writing confirmed replacement and verifying archive invariants…")
        self._run_worker("write", lambda: self._write_output(output_path, replacement, region))

    def _write_output(self, output_path: Path, replacement: bytes, region: Region) -> tuple[Path, Path, dict]:
        if self.archive is None or self.selected_entry is None or self.candidate_meta is None:
            raise ValueError("nothing is ready to write")
        rebuilt = rebuild_arc(self.archive, {self.selected_entry.index: replacement})
        output_path.write_bytes(rebuilt)
        verified_archive = parse_arc(output_path)
        verification = verify_single_replacement(self.archive, verified_archive, self.selected_entry.index)
        audit_path = output_path.with_suffix(output_path.suffix + ".audit.json")
        payload = {
            "application": "Alrummi 3",
            "status": "pass",
            "source_arc": str(self.archive.path),
            "output_arc": str(output_path),
            "source_arc_sha256": sha256(self.archive.data),
            "output_arc_sha256": sha256(rebuilt),
            "selected_entry": entry_report(self.selected_entry, self.source_raw),
            "candidate": self.candidate_meta,
            "replacement_raw_size": len(replacement),
            "verification": verification,
            "runtime_note": "Offline structural validation passed. RPCS3 cold-boot smoke testing is still required.",
        }
        write_audit(audit_path, payload)
        return output_path, audit_path, verification

    def check_ai(self) -> None:
        self.ai_status.configure(text="AI: checking…")
        self._run_worker("ping", self.ai.ping)


def main() -> None:
    app = Alrummi3App()
    app.mainloop()


if __name__ == "__main__":
    main()
