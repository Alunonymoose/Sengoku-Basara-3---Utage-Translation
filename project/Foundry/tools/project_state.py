from pathlib import Path
import json, datetime

def load_project_current(root):
    root = Path(root)
    p = root / ".foundry" / "PROJECT_CURRENT.json"
    if not p.exists():
        return {"available": False, "reason": "PROJECT_CURRENT.json missing"}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"available": True, "data": data}

def require_fresh_or_exact_target(root, exact_target_verified=False):
    state = load_project_current(root)
    if not state["available"]:
        return {"ok": bool(exact_target_verified), "reason": state["reason"]}
    snap = state["data"].get("snapshot", {})
    if snap.get("status") == "CLEAN":
        return {"ok": True, "reason": "snapshot clean"}
    if exact_target_verified:
        return {"ok": True, "reason": "snapshot dirty; exact live target verified"}
    return {"ok": False, "reason": "snapshot dirty; refresh or verify exact live target"}

if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else r"E:\Utage Patching New"
    state = load_project_current(root)
    print(json.dumps(state, indent=2))
