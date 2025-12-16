from __future__ import annotations

import logging
import os
import sqlite3
import threading
from typing import Dict, Optional

logger = logging.getLogger("mopidy_rfid")


class MappingsDB:
    """Simple SQLite-backed storage for tag -> URI mappings.

    Default DB path: ~/.config/mopidy-rfid/mappings.db
    """

    def __init__(self, path: Optional[str] = None) -> None:
        if path:
            self._path = os.path.expanduser(path)
        else:
            cfg_dir = os.path.expanduser("~/.config/mopidy-rfid")
            os.makedirs(cfg_dir, exist_ok=True)
            self._path = os.path.join(cfg_dir, "mappings.db")

        self._lock = threading.Lock()
        try:
            self._ensure_table()
        except Exception:
            logger.exception("MappingsDB: failed to ensure table")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            logger.debug("MappingsDB: PRAGMA configuration failed, continuing")
        return conn

    def _ensure_table(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mappings(
                        tag TEXT PRIMARY KEY,
                        uri TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, tag: str) -> Optional[str]:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    cur = conn.execute("SELECT uri FROM mappings WHERE tag = ?", (tag,))
                    row = cur.fetchone()
                    return row[0] if row else None
                finally:
                    conn.close()
        except Exception:
            logger.exception("MappingsDB: failed to get mapping for %s", tag)
            return None

    def set(self, tag: str, uri: str) -> None:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute("INSERT OR REPLACE INTO mappings(tag, uri) VALUES(?, ?)", (tag, uri))
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            logger.exception("MappingsDB: failed to set mapping %s -> %s", tag, uri)

    def delete(self, tag: str) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    cur = conn.execute("DELETE FROM mappings WHERE tag = ?", (tag,))
                    conn.commit()
                    return cur.rowcount > 0
                finally:
                    conn.close()
        except Exception:
            logger.exception("MappingsDB: failed to delete mapping for %s", tag)
            return False

    def list_all(self) -> Dict[str, str]:
        try:
            with self._lock:
                conn = self._get_conn()
                try:
                    cur = conn.execute("SELECT tag, uri FROM mappings")
                    return {row[0]: row[1] for row in cur.fetchall()}
                finally:
                    conn.close()
        except Exception:
            logger.exception("MappingsDB: failed to list mappings")
            return {}
