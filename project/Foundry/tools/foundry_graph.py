from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_LIVE_ROOT = Path(r"E:\Utage Patching New")
DEFAULT_ENG_ROOT = DEFAULT_LIVE_ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\eng"
DEFAULT_JPN_ROOT = DEFAULT_LIVE_ROOT / r"PS3_GAME\USRDIR\nativePS3\rom\jpn"
DEFAULT_SH_ROOT = Path(r"E:\SAMURAI HEROES\PS3_GAME\USRDIR\nativePS3\rom\eng")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAFE_ARC = PROJECT_ROOT / r"tools\donor_matcher_v5_1_2026-09-23\safe_arc.py"
XET = PROJECT_ROOT / r"texture_tools\xet_ps3_2026-09-25\xet_ps3.py"

SCHEMA_VERSION = 1
CERT_SCHEMA = "BASARA_FOUNDRY_SIGNOFF_V1"


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def detect_kind(type_hash: int, raw: bytes) -> tuple[str, str]:
    magic = raw[:4]
    if magic == b"\x00XET":
        return "texture", "XET"
    if magic == b"\x00PSL":
        return "layout", "PSL"
    if magic == b"\x00TNF":
        return "font-map", "TNF"
    if magic == b"\x00GSM":
        return "message", "GSM"
    if magic == b"\x00FIM":
        return "message-map", "FIM"
    if magic == b"\x00CSA":
        return "charset", "CSA"
    if magic == b"SCRA":
        return "child-manifest", "SCRA"
    if type_hash == 0x241F5DEB:
        return "texture", magic.hex()
    return "binary", magic.hex()


@dataclass(frozen=True)
class RootSpec:
    role: str
    root: Path


class FoundryGraph:
    def __init__(self, db_path: Path, live_root: Path = DEFAULT_LIVE_ROOT):
        self.db_path = Path(db_path)
        self.live_root = Path(live_root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.init_schema()

    def close(self):
        self.db.close()

    def init_schema(self):
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files(
              id INTEGER PRIMARY KEY,
              role TEXT NOT NULL,
              rel_path TEXT NOT NULL,
              abs_path TEXT NOT NULL,
              size INTEGER NOT NULL,
              mtime_ns INTEGER NOT NULL,
              sha256 TEXT NOT NULL,
              extension TEXT,
              is_arc INTEGER NOT NULL DEFAULT 0,
              scanned_at TEXT NOT NULL,
              UNIQUE(role, rel_path)
            );
            CREATE INDEX IF NOT EXISTS idx_files_sha ON files(sha256);
            CREATE INDEX IF NOT EXISTS idx_files_role_path ON files(role, rel_path);

            CREATE TABLE IF NOT EXISTS archives(
              file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
              version INTEGER,
              entry_count INTEGER,
              parse_ok INTEGER NOT NULL,
              parse_error TEXT
            );

            CREATE TABLE IF NOT EXISTS resources(
              id INTEGER PRIMARY KEY,
              file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
              member_index INTEGER NOT NULL,
              name TEXT NOT NULL,
              name_lower TEXT NOT NULL,
              type_hash INTEGER NOT NULL,
              codec TEXT,
              compressed_size INTEGER,
              raw_size INTEGER,
              raw_sha256 TEXT NOT NULL,
              stored_sha256 TEXT,
              magic TEXT,
              kind TEXT NOT NULL,
              xet_width INTEGER,
              xet_height INTEGER,
              xet_format INTEGER,
              xet_mips INTEGER,
              UNIQUE(file_id, member_index)
            );
            CREATE INDEX IF NOT EXISTS idx_resources_name ON resources(name_lower);
            CREATE INDEX IF NOT EXISTS idx_resources_rawsha ON resources(raw_sha256);
            CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type_hash);
            CREATE INDEX IF NOT EXISTS idx_resources_kind ON resources(kind);

            CREATE TABLE IF NOT EXISTS comparisons(
              resource_id INTEGER PRIMARY KEY REFERENCES resources(id) ON DELETE CASCADE,
              jpn_resource_id INTEGER REFERENCES resources(id) ON DELETE SET NULL,
              jpn_exact INTEGER,
              sh_resource_id INTEGER REFERENCES resources(id) ON DELETE SET NULL,
              sh_exact INTEGER
            );

            CREATE TABLE IF NOT EXISTS runtime_opens(
              rel_path TEXT PRIMARY KEY,
              open_count INTEGER NOT NULL,
              source_log TEXT,
              source_log_sha256 TEXT,
              ingested_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signoffs(
              id INTEGER PRIMARY KEY,
              cert_path TEXT UNIQUE NOT NULL,
              name TEXT NOT NULL,
              scope TEXT NOT NULL,
              created_at TEXT NOT NULL,
              rule_version TEXT,
              status TEXT NOT NULL,
              reason TEXT NOT NULL,
              checked_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signoff_files(
              signoff_id INTEGER NOT NULL REFERENCES signoffs(id) ON DELETE CASCADE,
              live_rel_path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              size INTEGER NOT NULL,
              PRIMARY KEY(signoff_id, live_rel_path)
            );

            CREATE VIEW IF NOT EXISTS v_resources AS
            SELECT r.*, f.role, f.rel_path AS arc_path, f.sha256 AS arc_sha256
            FROM resources r JOIN files f ON f.id=r.file_id;
            """
        )
        self.db.execute(
            "INSERT INTO meta(key,value) VALUES('schema_version',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self.db.commit()

    def _current_file_row(self, role: str, rel_path: str):
        return self.db.execute(
            "SELECT * FROM files WHERE role=? AND rel_path=?", (role, rel_path)
        ).fetchone()

    def scan_root(self, spec: RootSpec, safe_arc, xet, verbose: bool = False) -> dict:
        root = spec.root
        if not root.exists():
            return {"role": spec.role, "root": str(root), "available": False}

        seen = set()
        stats = {
            "role": spec.role, "root": str(root), "available": True,
            "files": 0, "changed_files": 0, "reused_files": 0,
            "arcs": 0, "arc_parse_errors": 0, "resources": 0, "textures": 0
        }

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = norm_rel(path, root)
            seen.add(rel)
            st = path.stat()
            stats["files"] += 1
            old = self._current_file_row(spec.role, rel)
            if old and int(old["size"]) == st.st_size and int(old["mtime_ns"]) == st.st_mtime_ns:
                stats["reused_files"] += 1
                continue

            digest = sha256_file(path)
            is_arc = path.suffix.lower() == ".arc"
            now = utcnow()
            self.db.execute(
                """
                INSERT INTO files(role,rel_path,abs_path,size,mtime_ns,sha256,extension,is_arc,scanned_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(role,rel_path) DO UPDATE SET
                  abs_path=excluded.abs_path,size=excluded.size,mtime_ns=excluded.mtime_ns,
                  sha256=excluded.sha256,extension=excluded.extension,is_arc=excluded.is_arc,
                  scanned_at=excluded.scanned_at
                """,
                (spec.role, rel, str(path), st.st_size, st.st_mtime_ns, digest,
                 path.suffix.lower(), 1 if is_arc else 0, now)
            )
            file_id = self.db.execute(
                "SELECT id FROM files WHERE role=? AND rel_path=?", (spec.role, rel)
            ).fetchone()[0]
            self.db.execute("DELETE FROM archives WHERE file_id=?", (file_id,))
            self.db.execute("DELETE FROM resources WHERE file_id=?", (file_id,))
            stats["changed_files"] += 1

            if is_arc:
                stats["arcs"] += 1
                try:
                    data = path.read_bytes()
                    entries = safe_arc.parse_arc(data)
                    version = int.from_bytes(data[4:6], "big") if len(data) >= 6 else None
                    self.db.execute(
                        "INSERT INTO archives(file_id,version,entry_count,parse_ok,parse_error) VALUES(?,?,?,?,NULL)",
                        (file_id, version, len(entries), 1)
                    )
                    for e in entries:
                        raw = e["raw"]
                        kind, magic = detect_kind(int(e["type_hash"]), raw)
                        width = height = fmt = mips = None
                        if kind == "texture" and raw.startswith(b"\x00XET"):
                            try:
                                inf = xet.info(raw)
                                width = int(inf.get("width")) if inf.get("width") is not None else None
                                height = int(inf.get("height")) if inf.get("height") is not None else None
                                fmt = int(inf.get("format")) if inf.get("format") is not None else None
                                mips = int(inf.get("mips")) if inf.get("mips") is not None else None
                            except Exception:
                                pass
                        self.db.execute(
                            """
                            INSERT INTO resources(
                              file_id,member_index,name,name_lower,type_hash,codec,
                              compressed_size,raw_size,raw_sha256,stored_sha256,magic,kind,
                              xet_width,xet_height,xet_format,xet_mips
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                file_id, int(e["index"]), e["name"], e["name"].lower(),
                                int(e["type_hash"]), e.get("codec"),
                                int(e.get("compressed_size", 0)), len(raw),
                                sha256_bytes(raw), sha256_bytes(e.get("stored", b"")),
                                magic, kind, width, height, fmt, mips
                            )
                        )
                        stats["resources"] += 1
                        if kind == "texture":
                            stats["textures"] += 1
                except Exception as exc:
                    stats["arc_parse_errors"] += 1
                    self.db.execute(
                        "INSERT INTO archives(file_id,version,entry_count,parse_ok,parse_error) VALUES(?,?,?,?,?)",
                        (file_id, None, None, 0, repr(exc))
                    )

            if stats["changed_files"] % 100 == 0:
                self.db.commit()
                if verbose:
                    print(f"[{spec.role}] changed={stats['changed_files']} files={stats['files']}", flush=True)

        stale = self.db.execute(
            "SELECT id,rel_path FROM files WHERE role=?", (spec.role,)
        ).fetchall()
        for row in stale:
            if row["rel_path"] not in seen:
                self.db.execute("DELETE FROM files WHERE id=?", (row["id"],))
        self.db.commit()

        # Recompute counts for reused resources too.
        stats["arcs"] = self.db.execute(
            "SELECT COUNT(*) FROM files WHERE role=? AND is_arc=1", (spec.role,)
        ).fetchone()[0]
        stats["resources"] = self.db.execute(
            "SELECT COUNT(*) FROM v_resources WHERE role=?", (spec.role,)
        ).fetchone()[0]
        stats["textures"] = self.db.execute(
            "SELECT COUNT(*) FROM v_resources WHERE role=? AND kind='texture'", (spec.role,)
        ).fetchone()[0]
        stats["arc_parse_errors"] = self.db.execute(
            """SELECT COUNT(*) FROM archives a JOIN files f ON f.id=a.file_id
               WHERE f.role=? AND a.parse_ok=0""", (spec.role,)
        ).fetchone()[0]
        return stats

    def build_comparisons(self):
        """Compare live ENG resources to JPN same-route peers and SH donors.

        JPN matching is deliberately route-bound. Samurai Heroes matching first
        tries the same route, then falls back to any same-basename/type official
        donor, preferring an exact raw-payload match. This mirrors the project's
        donor-first workflow without assuming archive topology is identical.
        """
        self.db.execute("DELETE FROM comparisons")
        eng = self.db.execute(
            "SELECT id,arc_path AS rel_path,member_index,name_lower,type_hash,raw_sha256 "
            "FROM v_resources WHERE role='ENG'"
        ).fetchall()

        jrows = self.db.execute(
            "SELECT id,arc_path AS rel_path,member_index,name_lower,type_hash,raw_sha256 "
            "FROM v_resources WHERE role='JPN'"
        ).fetchall()
        j_by_key = {(r["rel_path"], r["name_lower"], r["type_hash"]): r for r in jrows}
        j_by_index = {(r["rel_path"], r["member_index"], r["type_hash"]): r for r in jrows}

        srows = self.db.execute(
            "SELECT id,arc_path AS rel_path,member_index,name_lower,type_hash,raw_sha256 "
            "FROM v_resources WHERE role='SH'"
        ).fetchall()
        s_by_key = {(r["rel_path"], r["name_lower"], r["type_hash"]): r for r in srows}
        s_by_index = {(r["rel_path"], r["member_index"], r["type_hash"]): r for r in srows}
        s_by_exact = {}
        s_by_base = {}
        for r in srows:
            base = r["name_lower"].rsplit("\\", 1)[-1]
            s_by_exact.setdefault((base, r["type_hash"], r["raw_sha256"]), r)
            s_by_base.setdefault((base, r["type_hash"]), r)

        for e in eng:
            j = j_by_key.get((e["rel_path"], e["name_lower"], e["type_hash"]))
            if j is None:
                j = j_by_index.get((e["rel_path"], e["member_index"], e["type_hash"]))

            s = s_by_key.get((e["rel_path"], e["name_lower"], e["type_hash"]))
            if s is None:
                s = s_by_index.get((e["rel_path"], e["member_index"], e["type_hash"]))
            base = e["name_lower"].rsplit("\\", 1)[-1]
            exact_donor = s_by_exact.get((base, e["type_hash"], e["raw_sha256"]))
            if exact_donor is not None:
                s = exact_donor
            elif s is None:
                s = s_by_base.get((base, e["type_hash"]))

            self.db.execute(
                "INSERT INTO comparisons(resource_id,jpn_resource_id,jpn_exact,sh_resource_id,sh_exact) "
                "VALUES(?,?,?,?,?)",
                (
                    e["id"],
                    j["id"] if j else None,
                    int(j["raw_sha256"] == e["raw_sha256"]) if j else None,
                    s["id"] if s else None,
                    int(s["raw_sha256"] == e["raw_sha256"]) if s else None,
                ),
            )
        self.db.commit()

    def ingest_runtime_log(self, path: Path | None):
        self.db.execute("DELETE FROM runtime_opens")
        if path is None or not path.exists():
            self.db.commit()
            return {"available": False}
        digest = sha256_file(path)
        counts = {}
        rx = re.compile(r"(/dev_bdvd/PS3_GAME/USRDIR/nativePS3/[^\s\"']+)", re.I)
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                for m in rx.finditer(line):
                    raw = m.group(1).replace("\\", "/")
                    marker = "/nativePS3/"
                    pos = raw.lower().find(marker.lower())
                    if pos >= 0:
                        rel = raw[pos + len(marker):].replace("/", "\\").lower()
                        counts[rel] = counts.get(rel, 0) + 1
        now = utcnow()
        self.db.executemany(
            "INSERT INTO runtime_opens(rel_path,open_count,source_log,source_log_sha256,ingested_at) VALUES(?,?,?,?,?)",
            [(k, v, str(path), digest, now) for k, v in counts.items()]
        )
        self.db.commit()
        return {"available": True, "path": str(path), "sha256": digest, "unique_paths": len(counts)}

    def fingerprint(self) -> str:
        h = hashlib.sha256()
        for row in self.db.execute("SELECT role,rel_path,sha256 FROM files ORDER BY role,rel_path"):
            h.update(row["role"].encode())
            h.update(b"\0")
            h.update(row["rel_path"].encode("utf-8"))
            h.update(b"\0")
            h.update(row["sha256"].encode())
            h.update(b"\n")
        return h.hexdigest()

    def summary(self) -> dict:
        roles = {}
        for row in self.db.execute(
            """SELECT role,COUNT(*) files,SUM(is_arc) arcs FROM files GROUP BY role ORDER BY role"""
        ):
            role = row["role"]
            resources = self.db.execute(
                "SELECT COUNT(*) FROM v_resources WHERE role=?", (role,)
            ).fetchone()[0]
            textures = self.db.execute(
                "SELECT COUNT(*) FROM v_resources WHERE role=? AND kind='texture'", (role,)
            ).fetchone()[0]
            parse_errors = self.db.execute(
                """SELECT COUNT(*) FROM archives a JOIN files f ON f.id=a.file_id
                   WHERE f.role=? AND a.parse_ok=0""", (role,)
            ).fetchone()[0]
            roles[role] = {
                "files": row["files"], "arcs": row["arcs"] or 0,
                "resources": resources, "textures": textures, "parse_errors": parse_errors
            }
        cmp = self.db.execute(
            """SELECT
                 SUM(CASE WHEN jpn_exact=1 THEN 1 ELSE 0 END) jpn_exact,
                 SUM(CASE WHEN jpn_exact=0 THEN 1 ELSE 0 END) jpn_different,
                 SUM(CASE WHEN sh_exact=1 THEN 1 ELSE 0 END) sh_exact
               FROM comparisons"""
        ).fetchone()
        return {
            "schema_version": SCHEMA_VERSION,
            "db_path": str(self.db_path),
            "fingerprint": self.fingerprint(),
            "roles": roles,
            "comparisons": dict(cmp) if cmp else {},
            "runtime_paths": self.db.execute("SELECT COUNT(*) FROM runtime_opens").fetchone()[0],
            "signoffs": self.evaluate_signoffs(update_db=True),
        }

    def query(self, pattern: str, limit: int = 100) -> list[dict]:
        like = f"%{pattern.lower()}%"
        rows = self.db.execute(
            """SELECT r.id,r.role,r.arc_path,r.member_index,r.name,r.kind,
                      printf('0x%08X',r.type_hash) type_hash,r.raw_size,r.raw_sha256,
                      r.xet_width,r.xet_height,r.xet_format,r.xet_mips,
                      c.jpn_exact,c.sh_exact,
                      COALESCE(ro.open_count,0) runtime_open_count
               FROM v_resources r
               LEFT JOIN comparisons c ON c.resource_id=r.id
               LEFT JOIN runtime_opens ro ON lower(replace('rom/eng/' || r.arc_path,'/','\\'))=ro.rel_path
               WHERE lower(r.name) LIKE ? OR lower(r.arc_path) LIKE ?
               ORDER BY r.role,r.arc_path,r.member_index LIMIT ?""",
            (like, like, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def owners(self, resource_name: str, limit: int = 200) -> list[dict]:
        name = resource_name.lower()
        rows = self.db.execute(
            """SELECT role,arc_path,member_index,name,printf('0x%08X',type_hash) type_hash,
                      raw_sha256,kind
               FROM v_resources WHERE name_lower LIKE ?
               ORDER BY role,arc_path,member_index LIMIT ?""",
            (f"%{name}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def texture_suspects(self, limit: int = 500) -> list[dict]:
        rows = self.db.execute(
            """SELECT r.id,r.arc_path,r.member_index,r.name,r.raw_sha256,
                      r.xet_width,r.xet_height,r.xet_format,
                      c.jpn_exact,c.sh_exact,
                      CASE
                        WHEN c.jpn_exact=1 AND COALESCE(c.sh_exact,0)=0 THEN 3
                        WHEN c.jpn_exact=0 AND COALESCE(c.sh_exact,0)=0 THEN 2
                        ELSE 0
                      END AS score
               FROM v_resources r
               LEFT JOIN comparisons c ON c.resource_id=r.id
               WHERE r.role='ENG' AND r.kind='texture'
                 AND (
                    (c.jpn_exact=1 AND COALESCE(c.sh_exact,0)=0)
                    OR (c.jpn_exact=0 AND COALESCE(c.sh_exact,0)=0)
                 )
               ORDER BY score DESC,r.arc_path,r.member_index LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def create_signoff(self, scope: str, name: str, rule_version: str = "texture-qa-v1") -> Path:
        scope_path = (self.live_root / Path(scope)).resolve()
        if not scope_path.exists():
            raise FileNotFoundError(scope_path)
        files = []
        if scope_path.is_file():
            targets = [scope_path]
        else:
            targets = sorted(p for p in scope_path.rglob("*") if p.is_file())
        for p in targets:
            rel = p.relative_to(self.live_root).as_posix()
            st = p.stat()
            files.append({"path": rel, "sha256": sha256_file(p), "size": st.st_size})
        cert = {
            "schema": CERT_SCHEMA,
            "name": name,
            "scope": scope_path.relative_to(self.live_root).as_posix(),
            "created_at": utcnow(),
            "rule_version": rule_version,
            "live_root": str(self.live_root),
            "file_count": len(files),
            "files": files,
        }
        cert["certificate_sha256"] = sha256_bytes(
            json.dumps(cert, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        outdir = self.live_root / ".foundry" / "signoffs"
        outdir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
        out = outdir / f"{slug}.signoff.json"
        out.write_text(json.dumps(cert, indent=2), encoding="utf-8")
        self.import_signoff(out)
        return out

    def import_signoff(self, cert_path: Path):
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
        if cert.get("schema") != CERT_SCHEMA:
            raise ValueError(f"unsupported signoff schema: {cert.get('schema')}")
        status, reason = self._check_cert(cert)
        now = utcnow()
        self.db.execute(
            """INSERT INTO signoffs(cert_path,name,scope,created_at,rule_version,status,reason,checked_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(cert_path) DO UPDATE SET
                 name=excluded.name,scope=excluded.scope,created_at=excluded.created_at,
                 rule_version=excluded.rule_version,status=excluded.status,
                 reason=excluded.reason,checked_at=excluded.checked_at""",
            (str(cert_path), cert["name"], cert["scope"], cert["created_at"],
             cert.get("rule_version"), status, reason, now)
        )
        sid = self.db.execute("SELECT id FROM signoffs WHERE cert_path=?", (str(cert_path),)).fetchone()[0]
        self.db.execute("DELETE FROM signoff_files WHERE signoff_id=?", (sid,))
        self.db.executemany(
            "INSERT INTO signoff_files(signoff_id,live_rel_path,sha256,size) VALUES(?,?,?,?)",
            [(sid, f["path"], f["sha256"], f["size"]) for f in cert.get("files", [])]
        )
        self.db.commit()

    def _check_cert(self, cert: dict) -> tuple[str, str]:
        missing = []
        changed = []
        for f in cert.get("files", []):
            p = self.live_root / Path(f["path"])
            if not p.exists():
                missing.append(f["path"])
                continue
            st = p.stat()
            if st.st_size != int(f["size"]):
                changed.append(f["path"])
                continue
            if sha256_file(p) != f["sha256"]:
                changed.append(f["path"])
        if missing:
            return "STALE", f"{len(missing)} certified file(s) missing"
        if changed:
            return "STALE", f"{len(changed)} certified file(s) changed"
        return "VALID", "all certified file hashes match current live bytes"

    def evaluate_signoffs(self, update_db: bool = True) -> list[dict]:
        signoff_dir = self.live_root / ".foundry" / "signoffs"
        if signoff_dir.exists():
            for p in signoff_dir.glob("*.signoff.json"):
                try:
                    self.import_signoff(p)
                except Exception:
                    pass
        rows = self.db.execute("SELECT * FROM signoffs ORDER BY name").fetchall()
        out = []
        for row in rows:
            p = Path(row["cert_path"])
            if p.exists():
                try:
                    cert = json.loads(p.read_text(encoding="utf-8"))
                    status, reason = self._check_cert(cert)
                except Exception as exc:
                    status, reason = "ERROR", repr(exc)
            else:
                status, reason = "STALE", "certificate file missing"
            if update_db:
                self.db.execute(
                    "UPDATE signoffs SET status=?,reason=?,checked_at=? WHERE id=?",
                    (status, reason, utcnow(), row["id"])
                )
            out.append({
                "name": row["name"], "scope": row["scope"],
                "status": status, "reason": reason, "cert_path": row["cert_path"]
            })
        if update_db:
            self.db.commit()
        return out


def default_db(live_root: Path) -> Path:
    return live_root / ".foundry" / "cache" / "foundry_graph.sqlite"


def find_runtime_log(live_root: Path) -> Path | None:
    current = live_root / ".foundry" / "PROJECT_CURRENT.json"
    if current.exists():
        try:
            data = json.loads(current.read_text(encoding="utf-8"))
            p = data.get("snapshot", {}).get("runtime_log")
            if p and Path(p).exists():
                return Path(p)
        except Exception:
            pass
    candidates = list(Path.home().glob(r"Downloads\rpcs3*\log\RPCS3.log"))
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


def build_graph(
    live_root: Path = DEFAULT_LIVE_ROOT,
    include_jpn: bool = True,
    include_sh: bool = True,
    verbose: bool = False,
) -> dict:
    safe_arc = load_module("foundry_graph_safe_arc", SAFE_ARC)
    xet = load_module("foundry_graph_xet", XET)
    graph = FoundryGraph(default_db(live_root), live_root)
    specs = [RootSpec("ENG", live_root / r"PS3_GAME\USRDIR\nativePS3\rom\eng")]
    if include_jpn:
        specs.append(RootSpec("JPN", live_root / r"PS3_GAME\USRDIR\nativePS3\rom\jpn"))
    if include_sh and DEFAULT_SH_ROOT.exists():
        specs.append(RootSpec("SH", DEFAULT_SH_ROOT))
    scans = [graph.scan_root(s, safe_arc, xet, verbose=verbose) for s in specs]
    graph.build_comparisons()
    runtime = graph.ingest_runtime_log(find_runtime_log(live_root))
    summary = graph.summary()
    summary["scans"] = scans
    summary["runtime"] = runtime
    summary["generated_at"] = utcnow()
    status_path = live_root / ".foundry" / "FOUNDRY_GRAPH_STATUS.json"
    status_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    graph.close()
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="BASARA Foundry rebuildable live-resource graph")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--live-root", default=str(DEFAULT_LIVE_ROOT))
    b.add_argument("--no-jpn", action="store_true")
    b.add_argument("--no-sh", action="store_true")
    b.add_argument("--verbose", action="store_true")

    st = sub.add_parser("status")
    st.add_argument("--live-root", default=str(DEFAULT_LIVE_ROOT))

    q = sub.add_parser("query")
    q.add_argument("pattern")
    q.add_argument("--live-root", default=str(DEFAULT_LIVE_ROOT))
    q.add_argument("--limit", type=int, default=100)

    o = sub.add_parser("owners")
    o.add_argument("name")
    o.add_argument("--live-root", default=str(DEFAULT_LIVE_ROOT))

    s = sub.add_parser("suspects")
    s.add_argument("--live-root", default=str(DEFAULT_LIVE_ROOT))
    s.add_argument("--limit", type=int, default=200)

    c = sub.add_parser("certify")
    c.add_argument("scope")
    c.add_argument("--name", required=True)
    c.add_argument("--rule-version", default="texture-qa-v1")
    c.add_argument("--live-root", default=str(DEFAULT_LIVE_ROOT))

    so = sub.add_parser("signoffs")
    so.add_argument("--live-root", default=str(DEFAULT_LIVE_ROOT))

    args = ap.parse_args()
    live_root = Path(getattr(args, "live_root", DEFAULT_LIVE_ROOT))
    db = default_db(live_root)

    if args.cmd == "build":
        result = build_graph(live_root, not args.no_jpn, not args.no_sh, args.verbose)
        print(json.dumps(result, indent=2))
        return 0

    graph = FoundryGraph(db, live_root)
    try:
        if args.cmd == "status":
            print(json.dumps(graph.summary(), indent=2))
        elif args.cmd == "query":
            print(json.dumps(graph.query(args.pattern, args.limit), indent=2))
        elif args.cmd == "owners":
            print(json.dumps(graph.owners(args.name), indent=2))
        elif args.cmd == "suspects":
            print(json.dumps(graph.texture_suspects(args.limit), indent=2))
        elif args.cmd == "certify":
            p = graph.create_signoff(args.scope, args.name, args.rule_version)
            print(json.dumps({"certificate": str(p), "signoffs": graph.evaluate_signoffs()}, indent=2))
        elif args.cmd == "signoffs":
            print(json.dumps(graph.evaluate_signoffs(), indent=2))
    finally:
        graph.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
