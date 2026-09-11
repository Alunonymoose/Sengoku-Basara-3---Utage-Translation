"""Attach an Alrummi3 handoff pack to ChatGPT using a real browser file input.

This is deliberately a transport helper only.  It does not call the OpenAI API,
does not submit the prompt, does not download a result, and never writes an ARC.

Why this exists
---------------
Google Drive connector reads are useful context, but images fetched from Drive
are not guaranteed to become image-edit attachments.  For texture editing the
PNG files must enter the ChatGPT conversation through the browser's actual file
upload control.  This helper uses Selenium with a dedicated persistent browser
profile so the operator can log in once and keep using the free ChatGPT web UI.

The automation fails closed: if it cannot find the composer/file input it leaves
the handoff pack untouched and returns a clear error so Alrummi can fall back to
opening the folder manually.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Iterable


CHATGPT_URL = "https://chatgpt.com/"
PROFILE_DIRNAME = "Alrummi3 ChatGPT Browser"


class ChatGPTHandoffError(RuntimeError):
    pass


@dataclass
class HandoffResult:
    browser: str
    attached: tuple[Path, ...]
    prompt_inserted: bool


def _import_selenium():
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
    except Exception as exc:  # pragma: no cover - depends on optional runtime
        raise ChatGPTHandoffError(
            "Selenium is not available. Install it with: python -m pip install selenium"
        ) from exc
    return webdriver, WebDriverException, By, WebDriverWait


def _profile_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    path = base / "Alrummi3" / PROFILE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalise_files(paths: Iterable[Path | str]) -> tuple[Path, ...]:
    result: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise ChatGPTHandoffError(f"Attachment does not exist: {path}")
        if path.suffix.casefold() != ".png":
            raise ChatGPTHandoffError(f"Only PNG texture attachments are allowed: {path.name}")
        result.append(path)
    if not result:
        raise ChatGPTHandoffError("No PNG attachments were supplied")
    return tuple(result)


def _new_driver():
    webdriver, WebDriverException, _By, _Wait = _import_selenium()
    profile = _profile_root()
    errors: list[str] = []

    # Chrome first, then Edge.  Selenium Manager resolves the installed driver
    # automatically.  A dedicated profile avoids touching the operator's normal
    # browser profile and preserves the ChatGPT login between Alrummi sessions.
    try:
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile / 'chrome'}")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-features=Translate")
        return "Chrome", webdriver.Chrome(options=options)
    except Exception as exc:
        errors.append(f"Chrome: {exc}")

    try:
        options = webdriver.EdgeOptions()
        options.add_argument(f"--user-data-dir={profile / 'edge'}")
        return "Edge", webdriver.Edge(options=options)
    except Exception as exc:
        errors.append(f"Edge: {exc}")

    raise ChatGPTHandoffError(
        "Could not start Chrome or Edge for the ChatGPT handoff. " + " | ".join(errors)
    )


def attach_handoff(
    *,
    files: Iterable[Path | str],
    prompt: str,
    timeout: float = 90.0,
) -> HandoffResult:
    """Open ChatGPT, upload ``files``, and insert ``prompt`` without submitting.

    On first use the operator may need to sign in in the opened browser window.
    The wait is intentionally generous for that first-login case.
    """
    attachments = _normalise_files(files)
    if not prompt.strip():
        raise ChatGPTHandoffError("Prompt is empty")

    browser_name, driver = _new_driver()
    _webdriver, _WebDriverException, By, WebDriverWait = _import_selenium()

    try:
        driver.get(CHATGPT_URL)
        wait = WebDriverWait(driver, timeout)

        # ChatGPT currently exposes a hidden file input when attachment upload
        # is available.  Prefer inputs accepting images/files; otherwise use the
        # first enabled file input.  send_keys() uploads through the browser's
        # real control, which is the key difference from a Drive-only handoff.
        def find_file_input(drv):
            candidates = drv.find_elements(By.CSS_SELECTOR, "input[type='file']")
            for element in candidates:
                try:
                    if element.is_enabled():
                        return element
                except Exception:
                    continue
            return False

        file_input = wait.until(find_file_input)
        file_input.send_keys("\n".join(str(path) for path in attachments))

        # Wait until uploads have had a chance to register before filling the
        # composer.  We do not click Send: the user sees the real attachments
        # and prompt and remains the final gate before the request is submitted.
        time.sleep(1.0)

        composer = None
        selectors = (
            "#prompt-textarea",
            "textarea[data-id='root']",
            "div[contenteditable='true'][data-virtualkeyboard='true']",
            "div[contenteditable='true']",
        )
        deadline = time.time() + timeout
        while time.time() < deadline and composer is None:
            for selector in selectors:
                for element in driver.find_elements(By.CSS_SELECTOR, selector):
                    try:
                        if element.is_displayed() and element.is_enabled():
                            composer = element
                            break
                    except Exception:
                        continue
                if composer is not None:
                    break
            if composer is None:
                time.sleep(0.25)

        if composer is None:
            raise ChatGPTHandoffError(
                "PNG files were attached, but the ChatGPT composer could not be found. "
                "The browser has been left open so the handoff can be completed manually."
            )

        composer.click()
        # JS text insertion is avoided because React/contenteditable state can
        # ignore it. Selenium key input produces normal browser input events.
        composer.send_keys(prompt)
        return HandoffResult(browser_name, attachments, True)
    except ChatGPTHandoffError:
        raise
    except Exception as exc:
        # Intentionally do not close the browser on failure: the user may already
        # be signed in with the correct files visible and can finish manually.
        raise ChatGPTHandoffError(f"ChatGPT browser handoff failed: {exc}") from exc


def pick_handoff_pngs(pack: Path | str) -> tuple[Path, ...]:
    """Return source + pristine reference PNGs in deterministic order."""
    root = Path(pack)
    if not root.is_dir():
        raise ChatGPTHandoffError(f"Handoff folder does not exist: {root}")

    pngs = sorted(root.glob("*.png"))
    if not pngs:
        pngs = sorted(root.rglob("*.png"))
    if not pngs:
        raise ChatGPTHandoffError("Handoff pack contains no PNG files")

    def rank_source(path: Path) -> tuple[int, int]:
        name = path.name.casefold()
        score = 0
        if "selected" in name or "source" in name:
            score += 100
        if "jpn" in name or "reference" in name or "pristine" in name:
            score -= 100
        return score, path.stat().st_size

    source = max(pngs, key=rank_source)
    references = [
        p for p in pngs
        if p != source and any(t in p.name.casefold() for t in ("jpn", "reference", "pristine"))
    ]
    chosen = [source]
    if references:
        chosen.append(max(references, key=lambda p: p.stat().st_size))
    else:
        others = [p for p in pngs if p != source]
        if others:
            chosen.append(max(others, key=lambda p: p.stat().st_size))
    return tuple(chosen)


def read_handoff_prompt(pack: Path | str) -> str:
    root = Path(pack)
    preferred = (
        "CHATGPT_PROMPT.txt",
        "prompt.txt",
        "prompt.md",
    )
    for name in preferred:
        path = root / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    candidates = sorted(root.glob("*prompt*.txt")) + sorted(root.glob("*prompt*.md"))
    if candidates:
        return candidates[0].read_text(encoding="utf-8", errors="replace")
    raise ChatGPTHandoffError("Handoff pack contains no ChatGPT prompt file")
