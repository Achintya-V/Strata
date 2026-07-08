"""SQLite FTS5 index — the DERIVED cache (never the source of truth).

Invariant: delete .strata/index.db and `reindex()` rebuilds everything from
wiki/*.md and raw/. Three FTS tables:

- pages_fts  — compiled pages (title/tags/summary/body)
- claims_fts — individual ledger claims (enables temporal + provenance search)
- raw_fts    — raw entries; the stopgap that makes writes searchable *before*
               async compilation lands (§5.2)

Connections are per-operation (cheap, WAL) so worker threads never share one.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from ..db import ConnectionPool
from ..models import Claim, Page, RawEntry
from ..obs import log
from ..storage.repo import Repo

_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY, type TEXT, user_id TEXT, agent_id TEXT, run_id TEXT,
    title TEXT, tags TEXT, status TEXT, confidence REAL,
    created TEXT, updated TEXT, summary TEXT, pinned INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}'
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    id UNINDEXED, title, tags, summary, body, tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY, page_id TEXT, subject TEXT, text TEXT,
    provenance TEXT, confidence REAL,
    valid_from TEXT, valid_until TEXT, recorded_at TEXT, supersedes TEXT
);
CREATE INDEX IF NOT EXISTS idx_claims_page ON claims(page_id);
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
    claim_id UNINDEXED, text, tokenize='porter unicode61'
);
CREATE VIRTUAL TABLE IF NOT EXISTS raw_fts USING fts5(
    path UNINDEXED, user_id UNINDEXED, text, tokenize='porter unicode61'
);
"""

_TOKEN = re.compile(r"\w+", re.UNICODE)


def fts_query(query: str) -> Optional[str]:
    """Build a safe OR-joined FTS5 match expression (partial-overlap queries
    still surface results; special characters can't break the parser)."""
    tokens = _TOKEN.findall(query.lower())
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in tokens[:32])


class Indexer:
    def __init__(self, strata_dir: Path):
        self.db_path = strata_dir / "index.db"
        self._pool = ConnectionPool(self.db_path, row_factory=sqlite3.Row)
        self._init_db()

    def _db(self):
        return self._pool.tx()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_DDL)

    def close(self) -> None:
        """Release all index-db handles (Windows needs this before index.db
        can be deleted)."""
        self._pool.close_all()

    # ---------------- writes ----------------

    def index_page(self, page: Page, body: str) -> None:
        with self._db() as conn:
            self._index_page_conn(conn, page, body)

    def _index_page_conn(self, conn: sqlite3.Connection, page: Page, body: str) -> None:
        conn.execute("DELETE FROM pages WHERE id=?", (page.id,))
        conn.execute("DELETE FROM pages_fts WHERE id=?", (page.id,))
        conn.execute(
            "DELETE FROM claims_fts WHERE claim_id IN (SELECT id FROM claims WHERE page_id=?)",
            (page.id,))
        conn.execute("DELETE FROM claims WHERE page_id=?", (page.id,))
        conn.execute(
            "INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (page.id, page.type, page.user_id, page.agent_id, page.run_id, page.title,
             " ".join(page.tags), page.status.value, page.confidence, page.created,
             page.updated, page.summary, int(page.pinned), json.dumps(page.metadata)),
        )
        conn.execute(
            "INSERT INTO pages_fts (id, title, tags, summary, body) VALUES (?,?,?,?,?)",
            (page.id, page.title, " ".join(page.tags), page.summary, body),
        )
        for c in page.claims:
            conn.execute(
                "INSERT OR REPLACE INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
                (c.id, page.id, c.subject, c.text, c.provenance.value, c.confidence,
                 c.valid_from, c.valid_until, c.recorded_at, c.supersedes),
            )
            conn.execute("INSERT INTO claims_fts (claim_id, text) VALUES (?,?)", (c.id, c.text))

    def remove_page(self, page_id: str) -> None:
        with self._db() as conn:
            self._remove_page_conn(conn, page_id)

    def index_pages(self, page_ids: list[str], repo: Repo) -> None:
        """Incremental update after a write batch (§9.5)."""
        for pid in page_ids:
            parsed = repo.read_page(pid)
            if parsed is None:
                self.remove_page(pid)
            else:
                self.index_page(*parsed)

    def index_raw(self, entry: RawEntry) -> None:
        with self._db() as conn:
            conn.execute("INSERT INTO raw_fts (path, user_id, text) VALUES (?,?,?)",
                         (entry.path, entry.user_id, entry.text))

    def remove_user(self, user_id: str) -> None:
        with self._db() as conn:
            for (pid,) in conn.execute(
                    "SELECT id FROM pages WHERE user_id=?", (user_id,)).fetchall():
                self._remove_page_conn(conn, pid)
            conn.execute("DELETE FROM raw_fts WHERE user_id=?", (user_id,))

    def _remove_page_conn(self, conn: sqlite3.Connection, page_id: str) -> None:
        conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
        conn.execute("DELETE FROM pages_fts WHERE id=?", (page_id,))
        conn.execute(
            "DELETE FROM claims_fts WHERE claim_id IN (SELECT id FROM claims WHERE page_id=?)",
            (page_id,))
        conn.execute("DELETE FROM claims WHERE page_id=?", (page_id,))

    def reindex(self, repo: Repo) -> int:
        """Full rebuild from markdown — the recovery path proving the invariant."""
        n = 0
        with self._db() as conn:
            for table in ("pages", "pages_fts", "claims", "claims_fts", "raw_fts"):
                conn.execute(f"DELETE FROM {table}")
            for page, body in repo.iter_pages():
                self._index_page_conn(conn, page, body)
                n += 1
            if repo.raw_dir.exists():
                for path in sorted(repo.raw_dir.rglob("*.md")):
                    if "failed" in path.relative_to(repo.raw_dir).parts:
                        continue
                    entry = repo.read_raw(repo.rel(path))
                    if entry is not None:
                        conn.execute("INSERT INTO raw_fts (path, user_id, text) VALUES (?,?,?)",
                                     (entry.path, entry.user_id, entry.text))
        log.info("reindexed %d pages", n)
        return n

    # ---------------- queries ----------------

    def page_row(self, page_id: str) -> Optional[sqlite3.Row]:
        with self._db() as conn:
            return conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()

    def list_rows(self, type: Optional[str] = None, user_id: Optional[str] = None,
                  status: Optional[str] = None, pinned: Optional[bool] = None) -> list[sqlite3.Row]:
        clauses, params = [], []
        for col, val in (("type", type), ("user_id", user_id), ("status", status)):
            if val is not None:
                clauses.append(f"{col}=?")
                params.append(val)
        if pinned is not None:
            clauses.append("pinned=?")
            params.append(int(pinned))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._db() as conn:
            return conn.execute(
                f"SELECT * FROM pages {where} ORDER BY updated DESC", params).fetchall()

    def search_pages(self, query: str, type: Optional[str] = None,
                     user_id: Optional[str] = None, statuses: tuple[str, ...] = ("active",),
                     limit: int = 20) -> list[dict[str, Any]]:
        """BM25-ranked page hits (rank position is what matters downstream)."""
        match = fts_query(query)
        filters, params = ["p.status IN (%s)" % ",".join("?" * len(statuses))], list(statuses)
        if type:
            filters.append("p.type=?")
            params.append(type)
        if user_id:
            filters.append("(p.user_id=? OR p.user_id IS NULL)")   # user + shared knowledge
            params.append(user_id)
        where = " AND ".join(filters)
        with self._db() as conn:
            if match is None:
                return []
            rows = conn.execute(
                f"""SELECT p.*, snippet(pages_fts, 3, '[', ']', '…', 12) AS snip,
                           bm25(pages_fts) AS rank
                    FROM pages_fts JOIN pages p ON p.id = pages_fts.id
                    WHERE pages_fts MATCH ? AND {where}
                    ORDER BY rank LIMIT ?""",
                [match, *params, limit],
            ).fetchall()
        return [dict(r) for r in rows]

    def search_claims(self, query: str, user_id: Optional[str] = None,
                      as_of: Optional[str] = None, include_superseded: bool = False,
                      limit: int = 50) -> list[dict[str, Any]]:
        match = fts_query(query)
        if match is None:
            return []
        filters, params = [], []
        if user_id:
            filters.append("(p.user_id=? OR p.user_id IS NULL)")
            params.append(user_id)
        if as_of:
            # bi-temporal point-in-time: believed true on that date (§4.3)
            filters.append("(COALESCE(substr(c.valid_from,1,10), substr(c.recorded_at,1,10)) <= ?)")
            params.append(as_of[:10])
            filters.append("(c.valid_until IS NULL OR substr(c.valid_until,1,10) > ?)")
            params.append(as_of[:10])
        elif not include_superseded:
            filters.append("c.valid_until IS NULL")
        where = ("AND " + " AND ".join(filters)) if filters else ""
        with self._db() as conn:
            rows = conn.execute(
                f"""SELECT c.*, p.type AS page_type, p.title AS page_title,
                           p.user_id AS page_user_id, p.status AS page_status,
                           p.summary AS page_summary, p.updated AS page_updated,
                           bm25(claims_fts) AS rank
                    FROM claims_fts
                    JOIN claims c ON c.id = claims_fts.claim_id
                    JOIN pages p ON p.id = c.page_id
                    WHERE claims_fts MATCH ? {where}
                    ORDER BY rank LIMIT ?""",
                [match, *params, limit],
            ).fetchall()
        return [dict(r) for r in rows]

    def search_raw(self, query: str, user_id: Optional[str] = None,
                   limit: int = 10) -> list[dict[str, Any]]:
        match = fts_query(query)
        if match is None:
            return []
        where, params = "", []
        if user_id:
            where = "AND (user_id=? OR user_id IS NULL)"
            params.append(user_id)
        with self._db() as conn:
            rows = conn.execute(
                f"""SELECT path, user_id, snippet(raw_fts, 2, '[', ']', '…', 12) AS snip,
                           bm25(raw_fts) AS rank
                    FROM raw_fts WHERE raw_fts MATCH ? {where}
                    ORDER BY rank LIMIT ?""",
                [match, *params, limit],
            ).fetchall()
        return [dict(r) for r in rows]

    def index_entries(self) -> list[tuple]:
        """(type, id, title, summary, confidence, status) for index.md
        regeneration from the (already fresh) derived index — O(1) markdown parses."""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT type, id, title, summary, confidence, status FROM pages "
                "ORDER BY type, id").fetchall()
        return [tuple(r) for r in rows]

    def index_summary(self, max_chars: int = 4000) -> str:
        """SQLite-backed equivalent of Repo.index_summary (extractor routing)."""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT id, title, tags FROM pages WHERE status='active' ORDER BY id").fetchall()
        lines = [f"{r['id']} | {r['title']} | {','.join((r['tags'] or '').split()[:5])}"
                 for r in rows]
        return "\n".join(lines)[:max_chars]

    def counts(self) -> dict[str, Any]:
        with self._db() as conn:
            by_type = dict(conn.execute(
                "SELECT type, COUNT(*) FROM pages GROUP BY type").fetchall())
            by_status = dict(conn.execute(
                "SELECT status, COUNT(*) FROM pages GROUP BY status").fetchall())
            claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            active_claims = conn.execute(
                "SELECT COUNT(*) FROM claims WHERE valid_until IS NULL").fetchone()[0]
        return {"pages_by_type": by_type, "pages_by_status": by_status,
                "claims": claims, "active_claims": active_claims}
