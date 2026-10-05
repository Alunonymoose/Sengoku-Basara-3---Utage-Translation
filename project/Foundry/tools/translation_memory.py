from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(r"E:\Utage Patching New\.foundry\cache\translation_memory.sqlite")
PROVENANCE_PRIORITY = {
    "project-approved": 100,
    "official-SH": 90,
    "official-reference": 85,
    "human-reference": 70,
    "Xaldin-reference": 65,
    "literal-JPN": 50,
    "machine-draft": 20,
    "other": 10,
}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip().casefold()


def source_key(source_text: str, source_lang: str = "ja") -> str:
    payload = f"{source_lang}\0{normalize(source_text)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class TranslationMemory:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self._init_schema()

    def close(self):
        self.db.close()

    def _init_schema(self):
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries(
              id INTEGER PRIMARY KEY,
              source_text TEXT NOT NULL,
              source_norm TEXT NOT NULL,
              source_lang TEXT NOT NULL DEFAULT 'ja',
              source_key TEXT NOT NULL,
              target_text TEXT NOT NULL,
              target_norm TEXT NOT NULL,
              target_lang TEXT NOT NULL DEFAULT 'en',
              provenance TEXT NOT NULL,
              priority INTEGER NOT NULL,
              approved INTEGER NOT NULL DEFAULT 0,
              scope TEXT NOT NULL DEFAULT '',
              speaker TEXT NOT NULL DEFAULT '',
              resource_name TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              UNIQUE(source_key,target_norm,provenance,scope,speaker,resource_name)
            );
            CREATE INDEX IF NOT EXISTS idx_tm_source_key ON entries(source_key);
            CREATE INDEX IF NOT EXISTS idx_tm_source_norm ON entries(source_norm);
            CREATE INDEX IF NOT EXISTS idx_tm_target_norm ON entries(target_norm);
            CREATE INDEX IF NOT EXISTS idx_tm_scope ON entries(scope);
            CREATE INDEX IF NOT EXISTS idx_tm_provenance ON entries(provenance);
            """
        )
        try:
            self.db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                  source_text,target_text,speaker,resource_name,scope,
                  content='entries',content_rowid='id'
                )
                """
            )
            self.db.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                  INSERT INTO entries_fts(rowid,source_text,target_text,speaker,resource_name,scope)
                  VALUES(new.id,new.source_text,new.target_text,new.speaker,new.resource_name,new.scope);
                END;
                CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                  INSERT INTO entries_fts(entries_fts,rowid,source_text,target_text,speaker,resource_name,scope)
                  VALUES('delete',old.id,old.source_text,old.target_text,old.speaker,old.resource_name,old.scope);
                END;
                CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                  INSERT INTO entries_fts(entries_fts,rowid,source_text,target_text,speaker,resource_name,scope)
                  VALUES('delete',old.id,old.source_text,old.target_text,old.speaker,old.resource_name,old.scope);
                  INSERT INTO entries_fts(rowid,source_text,target_text,speaker,resource_name,scope)
                  VALUES(new.id,new.source_text,new.target_text,new.speaker,new.resource_name,new.scope);
                END;
                """
            )
            self.db.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            pass
        self.db.commit()

    def add(
        self,
        source_text: str,
        target_text: str,
        *,
        source_lang: str = "ja",
        target_lang: str = "en",
        provenance: str = "other",
        approved: bool = False,
        scope: str = "",
        speaker: str = "",
        resource_name: str = "",
        note: str = "",
    ) -> int:
        source_norm = normalize(source_text)
        target_norm = normalize(target_text)
        if not source_norm or not target_norm:
            raise ValueError("source and target text must be non-empty")
        key = source_key(source_text, source_lang)
        priority = PROVENANCE_PRIORITY.get(provenance, PROVENANCE_PRIORITY["other"])
        now = utcnow()
        self.db.execute(
            """
            INSERT INTO entries(
              source_text,source_norm,source_lang,source_key,
              target_text,target_norm,target_lang,provenance,priority,approved,
              scope,speaker,resource_name,note,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source_key,target_norm,provenance,scope,speaker,resource_name)
            DO UPDATE SET
              target_text=excluded.target_text,
              priority=excluded.priority,
              approved=MAX(entries.approved,excluded.approved),
              note=CASE WHEN excluded.note<>'' THEN excluded.note ELSE entries.note END
            """,
            (
                source_text, source_norm, source_lang, key,
                target_text, target_norm, target_lang, provenance, priority,
                1 if approved else 0, scope, speaker, resource_name, note, now
            )
        )
        self.db.commit()
        row = self.db.execute(
            """
            SELECT id FROM entries
            WHERE source_key=? AND target_norm=? AND provenance=?
              AND scope=? AND speaker=? AND resource_name=?
            """,
            (key, target_norm, provenance, scope, speaker, resource_name)
        ).fetchone()
        return int(row[0])

    def find(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        qnorm = normalize(query)
        exact = self.db.execute(
            """
            SELECT * FROM entries
            WHERE source_norm=? OR target_norm=?
            ORDER BY approved DESC,priority DESC,id DESC
            LIMIT ?
            """,
            (qnorm, qnorm, limit)
        ).fetchall()
        if exact:
            return [dict(r) for r in exact]

        rows = []
        try:
            escaped = " ".join(re.findall(r"\w+", query, flags=re.UNICODE))
            if escaped:
                rows = self.db.execute(
                    """
                    SELECT e.* FROM entries_fts f
                    JOIN entries e ON e.id=f.rowid
                    WHERE entries_fts MATCH ?
                    ORDER BY e.approved DESC,e.priority DESC,e.id DESC
                    LIMIT ?
                    """,
                    (escaped, limit)
                ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            like = f"%{qnorm}%"
            rows = self.db.execute(
                """
                SELECT * FROM entries
                WHERE source_norm LIKE ? OR target_norm LIKE ?
                   OR lower(speaker) LIKE ? OR lower(resource_name) LIKE ?
                ORDER BY approved DESC,priority DESC,id DESC
                LIMIT ?
                """,
                (like, like, like, like, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def audit(self) -> dict[str, Any]:
        total = self.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        approved = self.db.execute("SELECT COUNT(*) FROM entries WHERE approved=1").fetchone()[0]

        conflicts = self.db.execute(
            """
            SELECT source_key,MIN(source_text) source_text,COUNT(DISTINCT target_norm) target_count
            FROM entries
            WHERE approved=1
            GROUP BY source_key
            HAVING COUNT(DISTINCT target_norm)>1
            ORDER BY target_count DESC,source_text
            """
        ).fetchall()
        conflict_rows = []
        for c in conflicts:
            variants = self.db.execute(
                """
                SELECT target_text,provenance,scope,speaker,resource_name,priority
                FROM entries
                WHERE source_key=? AND approved=1
                ORDER BY priority DESC,target_text
                """,
                (c["source_key"],)
            ).fetchall()
            conflict_rows.append({
                "source_key": c["source_key"],
                "source_text": c["source_text"],
                "target_count": c["target_count"],
                "variants": [dict(v) for v in variants],
            })

        provenance = {
            row["provenance"]: row["count"]
            for row in self.db.execute(
                "SELECT provenance,COUNT(*) count FROM entries GROUP BY provenance ORDER BY count DESC"
            )
        }
        scopes = [
            dict(row) for row in self.db.execute(
                """
                SELECT scope,COUNT(*) entries,SUM(approved) approved
                FROM entries GROUP BY scope ORDER BY entries DESC LIMIT 100
                """
            )
        ]
        return {
            "schema": "BASARA_TRANSLATION_MEMORY_AUDIT_V1",
            "db": str(self.db_path),
            "entries": total,
            "approved_entries": approved,
            "approved_source_conflicts": len(conflict_rows),
            "conflicts": conflict_rows,
            "provenance": provenance,
            "top_scopes": scopes,
        }

    def export_csv(self, path: Path):
        rows = self.db.execute(
            """
            SELECT source_text,target_text,source_lang,target_lang,provenance,approved,
                   scope,speaker,resource_name,note,created_at
            FROM entries
            ORDER BY source_norm,approved DESC,priority DESC,id
            """
        ).fetchall()
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "source_text","target_text","source_lang","target_lang","provenance",
            "approved","scope","speaker","resource_name","note","created_at"
        ]
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in rows:
                w.writerow(dict(row))

    def import_jsonl(self, path: Path) -> dict[str, int]:
        added = 0
        failed = 0
        with path.open("r", encoding="utf-8-sig") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    self.add(
                        row["source_text"], row["target_text"],
                        source_lang=row.get("source_lang", "ja"),
                        target_lang=row.get("target_lang", "en"),
                        provenance=row.get("provenance", "other"),
                        approved=bool(row.get("approved", False)),
                        scope=row.get("scope", ""),
                        speaker=row.get("speaker", ""),
                        resource_name=row.get("resource_name", ""),
                        note=row.get("note", ""),
                    )
                    added += 1
                except Exception:
                    failed += 1
        return {"added": added, "failed": failed}


def main() -> int:
    ap = argparse.ArgumentParser(description="Provenance-aware BASARA translation memory")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    sub = ap.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add")
    add.add_argument("source")
    add.add_argument("target")
    add.add_argument("--source-lang", default="ja")
    add.add_argument("--target-lang", default="en")
    add.add_argument("--provenance", default="other")
    add.add_argument("--approved", action="store_true")
    add.add_argument("--scope", default="")
    add.add_argument("--speaker", default="")
    add.add_argument("--resource", default="")
    add.add_argument("--note", default="")

    find = sub.add_parser("find")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=50)

    sub.add_parser("audit")

    imp = sub.add_parser("import-jsonl")
    imp.add_argument("path")

    exp = sub.add_parser("export")
    exp.add_argument("path")

    args = ap.parse_args()
    tm = TranslationMemory(Path(args.db))
    try:
        if args.cmd == "add":
            row_id = tm.add(
                args.source, args.target,
                source_lang=args.source_lang,
                target_lang=args.target_lang,
                provenance=args.provenance,
                approved=args.approved,
                scope=args.scope,
                speaker=args.speaker,
                resource_name=args.resource,
                note=args.note,
            )
            print(json.dumps({"id": row_id, "db": str(tm.db_path)}, indent=2))
        elif args.cmd == "find":
            print(json.dumps(tm.find(args.query, args.limit), indent=2, ensure_ascii=False))
        elif args.cmd == "audit":
            print(json.dumps(tm.audit(), indent=2, ensure_ascii=False))
        elif args.cmd == "import-jsonl":
            print(json.dumps(tm.import_jsonl(Path(args.path)), indent=2))
        elif args.cmd == "export":
            out = Path(args.path)
            tm.export_csv(out)
            print(json.dumps({"output": str(out)}, indent=2))
    finally:
        tm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
