"""SQLite persistence (stdlib sqlite3). Datasets and analyses are stored as JSON payloads."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Optional

from . import config

DEFAULT_DB = config.resolve_path(os.environ.get("OFDE_DB_PATH") or "ofde.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_utc TEXT NOT NULL, name TEXT NOT NULL,
  origin TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analyses (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_utc TEXT NOT NULL, dataset_id INTEGER NOT NULL,
  title TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS priority_watch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL,
  analysis_id INTEGER,
  priority TEXT NOT NULL CHECK(priority IN ('critical','needs_attention')),
  reason TEXT NOT NULL,
  restricted_label TEXT NOT NULL DEFAULT 'none',
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','reviewed_resolved')),
  FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE SET NULL
);
"""


class Storage:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self):
        self._conn.close()

    def add_dataset(self, created_utc: str, dataset: dict) -> int:
        with self._lock:
            cur = self._conn.execute("INSERT INTO datasets(created_utc,name,origin,payload) VALUES (?,?,?,?)",
                                     (created_utc, dataset["name"], dataset["origin"], json.dumps(dataset)))
            self._conn.commit()
            return cur.lastrowid

    def get_dataset(self, ds_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT id, payload FROM datasets WHERE id=?", (ds_id,)).fetchone()
        if not row:
            return None
        d = json.loads(row["payload"])
        d["id"] = row["id"]
        return d

    def list_datasets(self) -> list:
        with self._lock:
            rows = self._conn.execute("SELECT id, created_utc, name, origin, payload FROM datasets ORDER BY id").fetchall()
        out = []
        for r in rows:
            d = json.loads(r["payload"])
            out.append({"id": r["id"], "name": r["name"], "origin": r["origin"], "imported_utc": d["imported_utc"],
                        "format": d["format"], "n_objects": len(d["objects"]), "n_cases": len(d.get("cases", [])),
                        "validation": d["validation"], "source_description": d["source_description"]})
        return out

    def add_analysis(self, created_utc: str, dataset_id: int, title: str, record: dict) -> int:
        with self._lock:
            cur = self._conn.execute("INSERT INTO analyses(created_utc,dataset_id,title,payload) VALUES (?,?,?,?)",
                                     (created_utc, dataset_id, title, json.dumps(record)))
            self._conn.commit()
            return cur.lastrowid

    def get_analysis(self, an_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT id, payload FROM analyses WHERE id=?", (an_id,)).fetchone()
        if not row:
            return None
        rec = json.loads(row["payload"])
        rec["id"] = row["id"]
        return rec

    def list_analyses(self, dataset_id: Optional[int] = None) -> list:
        q = "SELECT id, created_utc, dataset_id, title, payload FROM analyses"
        args: tuple = ()
        if dataset_id is not None:
            q += " WHERE dataset_id=?"
            args = (dataset_id,)
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY id DESC", args).fetchall()
        return [{"id": r["id"], "created_utc": r["created_utc"], "dataset_id": r["dataset_id"], "title": r["title"],
                 "record": json.loads(r["payload"])} for r in rows]

    def add_priority_alert(self, created_utc: str, analysis_id: Optional[int], priority: str,
                           reason: str, restricted_label: str = "none") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO priority_watch(created_utc,updated_utc,analysis_id,priority,reason,restricted_label,status) VALUES (?,?,?,?,?,?,?)",
                (created_utc, created_utc, analysis_id, priority, reason, restricted_label, "open"))
            self._conn.commit()
            return cur.lastrowid

    def list_priority_alerts(self) -> list:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM priority_watch ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END, id DESC").fetchall()
        return [dict(r) for r in rows]

    def get_priority_alert(self, alert_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM priority_watch WHERE id=?", (alert_id,)).fetchone()
        return dict(row) if row else None

    def update_priority_alert(self, alert_id: int, status: str, updated_utc: str) -> bool:
        with self._lock:
            cur = self._conn.execute("UPDATE priority_watch SET status=?, updated_utc=? WHERE id=?",
                                     (status, updated_utc, alert_id))
            self._conn.commit()
            return cur.rowcount > 0

    def reset(self):
        with self._lock:
            self._conn.executescript("DELETE FROM priority_watch; DELETE FROM analyses; DELETE FROM datasets; DELETE FROM sqlite_sequence;")
            self._conn.commit()
