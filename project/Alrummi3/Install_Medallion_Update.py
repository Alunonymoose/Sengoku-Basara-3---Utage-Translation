from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parent
GUI = ROOT / 'alrummi3_gui.py'
text = GUI.read_text(encoding='utf-8')
original = text

if 'import medallion_fx' not in text:
    text = text.replace('import texture_fx\n', 'import texture_fx\nimport medallion_fx\n', 1)

old = '''        ttk.Button(style_buttons, text="Style selected box",\n                   command=self.apply_style_box).grid(row=0, column=1, sticky="ew", padx=(3, 0))\n        self.style_status = ttk.Label(create_tab, text="", style="Muted.TLabel", wraplength=330)\n'''
new = '''        ttk.Button(style_buttons, text="Style selected box",\n                   command=self.apply_style_box).grid(row=0, column=1, sticky="ew", padx=(3, 0))\n        ttk.Button(style_buttons, text="Rebuild fortune medallions", style="Accent.TButton",\n                   command=self.rebuild_fortune_medallions).grid(\n                       row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))\n        self.style_status = ttk.Label(create_tab, text="", style="Muted.TLabel", wraplength=330)\n'''
if 'text="Rebuild fortune medallions"' not in text:
    if old not in text:
        raise SystemExit('Could not locate the Material and depth button block. GUI left unchanged.')
    text = text.replace(old, new, 1)

marker = '    def apply_style_all(self) -> None:\n'
method = '''    def rebuild_fortune_medallions(self) -> None:\n        \"\"\"Build the three main roulette fortune medallions as one candidate.\"\"\"\n        base = self._style_base()\n        if base is None:\n            messagebox.showinfo(\"Alrummi 3\", \"Select a decodable texture first.\")\n            return\n\n        raw = self.translation.get(\"1.0\", \"end-1c\").strip()\n        labels = [\"GREAT LUCK\", \"GOOD LUCK\", \"BAD LUCK\"]\n        if raw and raw != \"English translation / replacement text\":\n            if \"|\" in raw:\n                supplied = [p.strip() for p in raw.split(\"|\") if p.strip()]\n            else:\n                supplied = [p.strip() for p in raw.splitlines() if p.strip()]\n            for index, value in enumerate(supplied[:3]):\n                labels[index] = value.upper()\n\n        try:\n            candidate, meta = medallion_fx.rebuild_fortune_sheet(base, labels)\n        except Exception as exc:\n            messagebox.showerror(\"Alrummi 3\", str(exc))\n            self._set_status(f\"Fortune medallion rebuild failed: {exc}\")\n            return\n\n        self.donor_replacement = None\n        self.candidate_image = candidate\n        self.candidate_meta = meta\n        self.confirm_var.set(False)\n        self.save_candidate_button.configure(state=\"normal\")\n        self._update_confirm_state()\n        self._draw_preview(\"candidate\")\n        try:\n            self.preview_notebook.select(self.review_tab)\n        except Exception:\n            pass\n        self.style_status.configure(text=\"Rebuilt GREAT / GOOD / BAD LUCK medallions. Review the candidate.\")\n        self.output_label.configure(text=\"Medallions rebuilt. Review, tick confirmation, then write the new ARC.\")\n        self._set_status(\"Fortune medallion candidate generated. Source ARC remains untouched.\")\n\n'''
if 'def rebuild_fortune_medallions(self)' not in text:
    if marker not in text:
        raise SystemExit('Could not locate apply_style_all(). GUI left unchanged.')
    text = text.replace(marker, method + marker, 1)

if text != original:
    backup = GUI.with_suffix('.py.before_medallion_update')
    if not backup.exists():
        backup.write_text(original, encoding='utf-8')
    GUI.write_text(text, encoding='utf-8')

py_compile.compile(str(ROOT / 'medallion_fx.py'), doraise=True)
py_compile.compile(str(GUI), doraise=True)
print('Alrummi 3 medallion update installed and syntax-checked successfully.')
