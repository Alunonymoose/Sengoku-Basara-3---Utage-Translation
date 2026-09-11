from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "alrummi3_v4.py"

IMPORT_OLD = "import drive_bridge\n"
IMPORT_NEW = '''import drive_bridge

try:
    from chatgpt_web_handoff import attach_handoff, ChatGPTHandoffError
except Exception:
    attach_handoff = None

    class ChatGPTHandoffError(RuntimeError):
        pass
'''

ANCHOR_OLD = '''        width, height = job["width"], job["height"]

        handoff_note = ""
'''

ANCHOR_NEW = '''        width, height = job["width"], job["height"]

        # Prefer a real browser upload so image_gen receives actual current-
        # conversation image attachments.  This deliberately does not submit
        # the prompt: the operator remains the final approval gate.
        browser_error = None
        png_attachments = [selected_path]
        if reference_path is not None:
            png_attachments.append(reference_path)
        if self.candidate_image is not None:
            candidate_path = export_root / "03_current_candidate.png"
            if candidate_path.is_file():
                png_attachments.append(candidate_path)

        if attach_handoff is not None:
            try:
                result = attach_handoff(files=png_attachments, prompt=prompt)
                names = ", ".join(path.name for path in result.attached)
                self._set_status(
                    f"ChatGPT ready in {result.browser}: {names}; review and press Send"
                )
                messagebox.showinfo(
                    "ChatGPT handoff ready",
                    f"ChatGPT opened in {result.browser} with the real PNG attachment(s):\\n"
                    f"{names}\\n\\nThe editing prompt is already in the composer. "
                    "Review the attachments and press Send when ready.\\n\\n"
                    f"Return one full {width}×{height} PNG, then use "
                    "IMPORT CHATGPT RESULT… in Alrummi 3.",
                )
                return
            except ChatGPTHandoffError as exc:
                browser_error = str(exc)
            except Exception as exc:
                browser_error = str(exc)

        handoff_note = ""
'''

FALLBACK_OLD = '''        self._set_status(handoff_note)
'''
FALLBACK_NEW = '''        if browser_error:
            handoff_note += f" Browser attachment fallback reason: {browser_error}"
        self._set_status(handoff_note)
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one source anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if "attach_handoff(files=png_attachments, prompt=prompt)" in text:
        compile(text, str(TARGET), "exec")
        print("v35 attachment handoff already applied")
        return

    text = replace_once(text, IMPORT_OLD, IMPORT_NEW, "import hook")
    text = replace_once(text, ANCHOR_OLD, ANCHOR_NEW, "send_to_chatgpt hook")
    text = replace_once(text, FALLBACK_OLD, FALLBACK_NEW, "fallback status hook")

    # Guard the two critical behavioral contracts: actual file attachment and
    # preservation of v35's manual fallback path.
    if "attach_handoff(files=png_attachments, prompt=prompt)" not in text:
        raise SystemExit("attachment call missing after patch")
    if "handoff_note" not in text or "Browser attachment fallback reason" not in text:
        raise SystemExit("clipboard/manual fallback was not preserved")
    if ".submit(" in text or "click_send" in text:
        raise SystemExit("unexpected automatic submission path detected")

    compile(text, str(TARGET), "exec")
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print("applied real ChatGPT PNG attachment handoff to v35")


if __name__ == "__main__":
    main()
