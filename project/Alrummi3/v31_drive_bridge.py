"""Compatibility bridge for the existing Alrummi3 v31 ChatGPT buttons.

This module is intentionally invasive in *zero* archive-writing code.  It wraps
v31's existing visible buttons at runtime:

    SEND TO CHATGPT
    IMPORT CHATGPT RESULT...

The original v31 callbacks remain the authority for producing the handoff pack
and for validating/loading the returned candidate.  The bridge only adds a
Drive-backed transport layer between them.

Flow
----
1. User presses SEND TO CHATGPT.
2. v31 creates its normal local handoff folder.
3. This bridge suppresses only the unwanted chatgpt.com browser tab.
4. The newest handoff pack is mirrored into
   ALRUMMI3_FACTORY_ROOT/INBOX/JOB_... and normalized to source.png/reference.
5. The bridge polls the matching OUTBOX job for replacement.png.
6. When it appears, the bridge calls v31's existing IMPORT CHATGPT RESULT...
   callback while temporarily injecting the returned PNG into its file picker.
7. v31 performs its own dimension/format checks and loads the candidate.

Nothing here patches an ARC, installs game data, or bypasses v31's approval
step.  If the bridge cannot confidently identify the handoff folder, it fails
closed and leaves v31's local handoff untouched.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import time
import webbrowser
from typing import Any, Callable, Iterable

from PIL import Image
from tkinter import filedialog


RESULT_NAME = "replacement.png"
DEFAULT_HANDOFF_DIRNAME = "Alrummi3 ChatGPT"
SEND_LABELS = {"send to chatgpt", "send to chatgpt...", "send to chatgpt…"}
IMPORT_LABELS = {
    "import chatgpt result",
    "import chatgpt result...",
    "import chatgpt result…",
}


class BridgeError(RuntimeError):
    pass


@dataclass
class BridgeJob:
    job_id: str
    inbox_dir: Path
    outbox_dir: Path
    local_pack: Path
    created_at: float

    @property
    def result_path(self) -> Path:
        return self.outbox_dir / RESULT_NAME


@dataclass
class V31DriveBridge:
    app: Any
    factory_root: Path
    handoff_root: Path
    poll_ms: int = 1500

    def __post_init__(self) -> None:
        self.factory_root = Path(self.factory_root)
        self.handoff_root = Path(self.handoff_root)
        self.send_button: Any | None = None
        self.import_button: Any | None = None
        self._send_tcl_command: str | None = None
        self._import_tcl_command: str | None = None
        self.current_job: BridgeJob | None = None
        self._poll_token: Any | None = None
        self._last_result_signature: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # Installation / widget discovery
    # ------------------------------------------------------------------
    def install(self) -> "V31DriveBridge":
        self._ensure_factory_dirs()
        self.send_button = self._find_button(SEND_LABELS)
        self.import_button = self._find_button(IMPORT_LABELS)
        if self.send_button is None:
            raise BridgeError("Could not find v31 'SEND TO CHATGPT' button")
        if self.import_button is None:
            raise BridgeError("Could not find v31 'IMPORT CHATGPT RESULT' button")

        self._send_tcl_command = str(self.send_button.cget("command"))
        self._import_tcl_command = str(self.import_button.cget("command"))
        if not self._send_tcl_command or not self._import_tcl_command:
            raise BridgeError("v31 ChatGPT buttons have no callable Tk command")

        self.send_button.configure(command=self.send_to_factory)
        # Keep the Import button usable manually.  We do not replace it.
        self._status("Drive factory bridge ready")
        return self

    def uninstall(self) -> None:
        self.stop_watching()
        if self.send_button is not None and self._send_tcl_command:
            self.send_button.configure(command=self._send_tcl_command)
        self._status("Drive factory bridge disabled")

    def _walk_widgets(self, root: Any) -> Iterable[Any]:
        stack = [root]
        seen: set[str] = set()
        while stack:
            widget = stack.pop()
            key = str(widget)
            if key in seen:
                continue
            seen.add(key)
            yield widget
            try:
                stack.extend(reversed(widget.winfo_children()))
            except Exception:
                continue

    @staticmethod
    def _normalise_label(value: str) -> str:
        return " ".join(value.strip().casefold().replace("…", "...").split())

    def _find_button(self, accepted: set[str]) -> Any | None:
        wanted = {self._normalise_label(v) for v in accepted}
        for widget in self._walk_widgets(self.app):
            try:
                text = str(widget.cget("text"))
                command = str(widget.cget("command"))
            except Exception:
                continue
            if command and self._normalise_label(text) in wanted:
                return widget
        return None

    # ------------------------------------------------------------------
    # SEND wrapper
    # ------------------------------------------------------------------
    def send_to_factory(self) -> None:
        if not self._send_tcl_command:
            raise BridgeError("Bridge is not installed")

        before = self._snapshot_handoff_dirs()
        started = time.time()
        self._status("Creating ChatGPT handoff pack...")

        try:
            with _suppress_chatgpt_browser_tabs():
                self.app.tk.call(self._send_tcl_command)
        except Exception as exc:
            self._status(f"v31 handoff failed: {exc}")
            raise

        pack = self._find_new_handoff(before, started)
        if pack is None:
            self._status(
                "v31 created no identifiable handoff folder; Drive upload was not attempted"
            )
            return

        try:
            job = self._mirror_pack(pack)
        except Exception as exc:
            self._status(f"Drive factory handoff failed: {exc}")
            raise

        self.current_job = job
        self._last_result_signature = None
        self._status(
            f"Factory job {job.job_id} ready in Drive; waiting for {RESULT_NAME}"
        )
        self.start_watching()

    def _snapshot_handoff_dirs(self) -> dict[Path, int]:
        root = self.handoff_root
        if not root.exists():
            return {}
        result: dict[Path, int] = {}
        try:
            for path in root.iterdir():
                if not path.is_dir():
                    continue
                try:
                    result[path.resolve()] = path.stat().st_mtime_ns
                except OSError:
                    continue
        except OSError:
            return {}
        return result

    def _find_new_handoff(self, before: dict[Path, int], started: float) -> Path | None:
        # v31 currently writes one folder per send operation.  Prefer a newly
        # created directory; otherwise accept an existing directory whose mtime
        # changed during this callback.  Never guess from an old untouched pack.
        deadline = time.time() + 3.0
        best: tuple[int, Path] | None = None
        while time.time() <= deadline:
            after = self._snapshot_handoff_dirs()
            for path, mtime in after.items():
                old = before.get(path)
                changed = old is None or mtime != old
                if not changed:
                    continue
                try:
                    if path.stat().st_mtime >= started - 2.0:
                        if best is None or mtime > best[0]:
                            best = (mtime, path)
                except OSError:
                    continue
            if best is not None:
                return best[1]
            # Tk callback normally writes synchronously, but tolerate a tiny
            # delayed filesystem flush without blocking for long.
            try:
                self.app.update_idletasks()
            except Exception:
                pass
            time.sleep(0.05)
        return None

    def _ensure_factory_dirs(self) -> None:
        for name in ("INBOX", "OUTBOX", "DONE", "REJECTED"):
            (self.factory_root / name).mkdir(parents=True, exist_ok=True)

    def _mirror_pack(self, pack: Path) -> BridgeJob:
        job_id = _job_id(pack.name)
        inbox = self.factory_root / "INBOX" / job_id
        outbox = self.factory_root / "OUTBOX" / job_id
        if inbox.exists() or outbox.exists():
            raise BridgeError(f"Factory job already exists: {job_id}")

        inbox.mkdir(parents=True)
        outbox.mkdir(parents=True)
        original_dir = inbox / "v31_pack"
        shutil.copytree(pack, original_dir)

        pngs = _readable_pngs(original_dir)
        if not pngs:
            shutil.rmtree(inbox, ignore_errors=True)
            shutil.rmtree(outbox, ignore_errors=True)
            raise BridgeError("v31 handoff pack contains no readable PNG")

        source = _pick_source_png(pngs)
        reference = _pick_reference_png(pngs, exclude=source)
        source_target = inbox / "source.png"
        shutil.copy2(source, source_target)
        width, height = _image_size(source_target)

        files = {
            "source": "source.png",
            "original_pack": "v31_pack/",
        }
        if reference is not None:
            ref_target = inbox / "pristine_jpn.png"
            shutil.copy2(reference, ref_target)
            rw, rh = _image_size(ref_target)
            if (rw, rh) == (width, height):
                files["pristine_jpn"] = "pristine_jpn.png"
            else:
                # Keep the source pack untouched, but do not mislabel a crop or
                # mockup as a full-sheet reference.
                ref_target.unlink(missing_ok=True)

        original_prompt = _pick_prompt_file(original_dir)
        if original_prompt is not None:
            try:
                original_text = original_prompt.read_text(encoding="utf-8", errors="replace")
            except OSError:
                original_text = ""
        else:
            original_text = ""

        prompt = _bridge_prompt(
            job_id=job_id,
            width=width,
            height=height,
            original_prompt=original_text,
        )
        (inbox / "prompt.md").write_text(prompt, encoding="utf-8")
        manifest = {
            "schema": "alrummi3.v31_drive_bridge",
            "schema_version": 1,
            "job_id": job_id,
            "created_local": datetime.now().astimezone().isoformat(),
            "source_handoff_folder": str(pack),
            "source": {
                "file": "source.png",
                "width": width,
                "height": height,
            },
            "files": files,
            "return": {
                "folder": f"OUTBOX/{job_id}",
                "file": RESULT_NAME,
            },
            "rules": {
                "no_arc_write": True,
                "approval_required": True,
                "v31_import_validation_required": True,
            },
        }
        (inbox / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (outbox / "README_RETURN_HERE.txt").write_text(
            f"Return the full-sheet PNG here as {RESULT_NAME}.\n"
            f"Required size: {width}x{height}.\n"
            "Alrummi v31 will perform its own import validation before the image becomes a candidate.\n",
            encoding="utf-8",
        )
        # readiness marker written last
        (inbox / ".ready").write_text("ready\n", encoding="ascii")
        return BridgeJob(job_id, inbox, outbox, pack, time.time())

    # ------------------------------------------------------------------
    # OUTBOX watcher / v31 import injection
    # ------------------------------------------------------------------
    def start_watching(self) -> None:
        self.stop_watching()
        self._poll_token = self.app.after(self.poll_ms, self._poll)

    def stop_watching(self) -> None:
        if self._poll_token is not None:
            try:
                self.app.after_cancel(self._poll_token)
            except Exception:
                pass
            self._poll_token = None

    def _poll(self) -> None:
        self._poll_token = None
        job = self.current_job
        if job is None:
            return
        path = job.result_path
        if path.is_file():
            try:
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                signature = None
            if signature is not None and signature != self._last_result_signature:
                self._last_result_signature = signature
                try:
                    self._import_result_through_v31(path)
                except Exception as exc:
                    self._status(f"Returned PNG could not be imported by v31: {exc}")
                else:
                    self._status(
                        f"Factory result for {job.job_id} loaded through v31 validation; review before Apply"
                    )
                    return
        self._poll_token = self.app.after(self.poll_ms, self._poll)

    def _import_result_through_v31(self, result: Path) -> None:
        if not self._import_tcl_command:
            raise BridgeError("v31 Import callback is unavailable")
        # v31 already owns the import validation and candidate state.  Inject
        # only the chosen path into its existing file-dialog call.
        original = filedialog.askopenfilename

        def injected(*_args: Any, **_kwargs: Any) -> str:
            return str(result)

        filedialog.askopenfilename = injected
        try:
            self.app.tk.call(self._import_tcl_command)
        finally:
            filedialog.askopenfilename = original

    def _status(self, message: str) -> None:
        for name in ("_set_status", "set_status", "status_message"):
            callback = getattr(self.app, name, None)
            if callable(callback):
                try:
                    callback(message)
                    return
                except Exception:
                    pass
        label = getattr(self.app, "status", None)
        if label is not None:
            try:
                label.configure(text=message)
                return
            except Exception:
                pass
        print(f"[Alrummi3 Drive Bridge] {message}")


def install_v31_drive_bridge(
    app: Any,
    *,
    factory_root: Path | str | None = None,
    handoff_root: Path | str | None = None,
    poll_ms: int = 1500,
) -> V31DriveBridge:
    """Install the bridge after v31 has finished constructing its widgets.

    ``factory_root`` should be the *locally synced* Google Drive directory named
    ``Alrummi3_AI_Factory``.  Set ALRUMMI3_FACTORY_ROOT to avoid hard-coding it.
    """
    factory = Path(
        factory_root
        or os.environ.get("ALRUMMI3_FACTORY_ROOT", "")
        or _discover_factory_root()
    )
    if not str(factory):
        raise BridgeError(
            "No Drive factory root configured. Set ALRUMMI3_FACTORY_ROOT to the locally synced "
            "Alrummi3_AI_Factory directory."
        )
    if handoff_root is None:
        pictures = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Pictures"
        handoff = pictures / DEFAULT_HANDOFF_DIRNAME
    else:
        handoff = Path(handoff_root)
    bridge = V31DriveBridge(app, factory, handoff, poll_ms=poll_ms)
    return bridge.install()


@contextmanager
def _suppress_chatgpt_browser_tabs() -> Iterable[None]:
    """Suppress only ChatGPT URLs while v31 builds its existing handoff pack."""
    original_open = webbrowser.open
    original_new = webbrowser.open_new
    original_tab = webbrowser.open_new_tab

    def wrapped(url: str, *args: Any, **kwargs: Any) -> bool:
        lower = str(url).casefold()
        if "chatgpt.com" in lower or "chat.openai.com" in lower:
            return True
        return bool(original_open(url, *args, **kwargs))

    def wrapped_new(url: str, *args: Any, **kwargs: Any) -> bool:
        lower = str(url).casefold()
        if "chatgpt.com" in lower or "chat.openai.com" in lower:
            return True
        return bool(original_new(url, *args, **kwargs))

    def wrapped_tab(url: str, *args: Any, **kwargs: Any) -> bool:
        lower = str(url).casefold()
        if "chatgpt.com" in lower or "chat.openai.com" in lower:
            return True
        return bool(original_tab(url, *args, **kwargs))

    webbrowser.open = wrapped
    webbrowser.open_new = wrapped_new
    webbrowser.open_new_tab = wrapped_tab
    try:
        yield
    finally:
        webbrowser.open = original_open
        webbrowser.open_new = original_new
        webbrowser.open_new_tab = original_tab


def _discover_factory_root() -> str:
    # This is deliberately conservative.  A wrong Drive root means uploading
    # the asset to the wrong place, so return an empty string unless the exact
    # Alrummi3_AI_Factory directory already exists.
    home = Path.home()
    candidates = [
        home / "Google Drive" / "My Drive" / "Alrummi3_AI_Factory",
        home / "Google Drive" / "Alrummi3_AI_Factory",
        home / "My Drive" / "Alrummi3_AI_Factory",
    ]
    if os.name == "nt":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            candidates.append(Path(f"{letter}:\\My Drive\\Alrummi3_AI_Factory"))
    for path in candidates:
        try:
            if path.is_dir():
                return str(path)
        except OSError:
            continue
    return ""


def _job_id(pack_name: str) -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in pack_name)
    safe = safe.strip("._")[:48] or "texture"
    return f"JOB_{stamp}_{safe}"


def _readable_pngs(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*.png"):
        try:
            with Image.open(path) as image:
                image.verify()
            found.append(path)
        except Exception:
            continue
    return found


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _pick_source_png(paths: list[Path]) -> Path:
    def rank(path: Path) -> tuple[int, int, int]:
        name = path.name.casefold()
        reference_penalty = any(token in name for token in ("jpn", "japanese", "reference", "pristine"))
        source_bonus = any(token in name for token in ("selected", "source", "sheet", "texture", "atlas"))
        try:
            w, h = _image_size(path)
            area = w * h
        except Exception:
            area = 0
        return (0 if reference_penalty else 1, 1 if source_bonus else 0, area)

    return max(paths, key=rank)


def _pick_reference_png(paths: list[Path], *, exclude: Path) -> Path | None:
    candidates = [p for p in paths if p != exclude]
    if not candidates:
        return None

    def rank(path: Path) -> tuple[int, int]:
        name = path.name.casefold()
        reference_bonus = any(token in name for token in ("jpn", "japanese", "reference", "pristine"))
        try:
            w, h = _image_size(path)
            area = w * h
        except Exception:
            area = 0
        return (1 if reference_bonus else 0, area)

    return max(candidates, key=rank)


def _pick_prompt_file(root: Path) -> Path | None:
    preferred: list[Path] = []
    for pattern in ("*prompt*.md", "*prompt*.txt", "*.md", "*.txt"):
        preferred.extend(root.rglob(pattern))
    return preferred[0] if preferred else None


def _bridge_prompt(*, job_id: str, width: int, height: int, original_prompt: str) -> str:
    original = original_prompt.strip()
    if original:
        original = "\n\nV31 ORIGINAL INSTRUCTIONS\n-------------------------\n" + original
    return f"""ALRUMMI3 DRIVE FACTORY JOB: {job_id}

Use source.png as the exact atlas/geometry authority.  The complete untouched
v31 handoff pack is also in v31_pack/ for context and references.

Produce ONE finished full-sheet PNG named {RESULT_NAME} at exactly {width}x{height}.
Do not crop, pad, resize, rearrange sprites, or redesign unrelated artwork.
Preserve transparency and all non-target UI art.  Improve only the Japanese,
broken, ugly, or explicitly requested localized UI elements, matching Capcom's
Samurai Heroes style where the references support it.

Return the finished file to:
OUTBOX/{job_id}/{RESULT_NAME}

Do not patch an ARC.  Alrummi v31 will import and validate the returned PNG as
a candidate and the user must still approve it before any archive rebuild.
{original}
"""
