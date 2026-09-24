from __future__ import annotations
import sqlite3
from pathlib import Path


def connect_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE files(id INTEGER PRIMARY KEY,path TEXT NOT NULL UNIQUE,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,sha256 TEXT NOT NULL,kind TEXT NOT NULL);
    CREATE TABLE arcs(id INTEGER PRIMARY KEY,file_id INTEGER NOT NULL UNIQUE REFERENCES files(id) ON DELETE CASCADE,parse_status TEXT NOT NULL,version INTEGER,member_count INTEGER,alignment INTEGER,error TEXT);
    CREATE TABLE resources(
      id INTEGER PRIMARY KEY,arc_id INTEGER NOT NULL REFERENCES arcs(id) ON DELETE CASCADE,
      member_index INTEGER NOT NULL,internal_path TEXT NOT NULL,canonical_path TEXT NOT NULL,
      type_hash INTEGER NOT NULL,type_hex TEXT NOT NULL,flags INTEGER NOT NULL,codec TEXT NOT NULL,
      compressed_size INTEGER NOT NULL,declared_raw_size INTEGER NOT NULL,actual_raw_size INTEGER NOT NULL,
      stored_sha256 TEXT NOT NULL,raw_sha256 TEXT NOT NULL,warning TEXT,UNIQUE(arc_id,member_index));
    CREATE INDEX ix_resources_identity ON resources(type_hash,canonical_path);
    CREATE INDEX ix_resources_path ON resources(canonical_path);
    CREATE TABLE arc_runtime_order(arc_id INTEGER PRIMARY KEY REFERENCES arcs(id) ON DELETE CASCADE,runtime_rank INTEGER NOT NULL,evidence_source TEXT NOT NULL);
    CREATE VIEW provider_groups AS SELECT type_hash,type_hex,canonical_path,COUNT(*) provider_count,COUNT(DISTINCT raw_sha256) payload_variants FROM resources GROUP BY type_hash,type_hex,canonical_path;
    """)
