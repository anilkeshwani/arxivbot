from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    abstract TEXT,
    publication_date TEXT,
    year INTEGER,
    arxiv_id TEXT,
    doi TEXT,
    venue TEXT,
    tldr TEXT,
    s2_url TEXT NOT NULL,
    fields_of_study TEXT,
    citation_count INTEGER DEFAULT 0,
    influential_citation_count INTEGER DEFAULT 0,
    open_access_pdf_url TEXT,
    added_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
"""


def _strip_arxiv_version(arxiv_id: str | None) -> str | None:
    """Normalize arXiv ID by stripping the version suffix (e.g., '2109.00301v3' -> '2109.00301')."""
    if not arxiv_id:
        return arxiv_id
    return re.sub(r"v\d+$", "", arxiv_id)


def _get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    """Create the papers table and indexes if they don't exist."""
    with _get_connection(db_path) as conn:
        conn.executescript(_SCHEMA)
        # Normalize any versioned arXiv IDs (e.g., "2109.00301v3" -> "2109.00301")
        rows = conn.execute(
            "SELECT paper_id, arxiv_id FROM papers WHERE arxiv_id IS NOT NULL AND arxiv_id LIKE '%v%'"
        ).fetchall()
        for row in rows:
            clean = _strip_arxiv_version(row["arxiv_id"])
            if clean != row["arxiv_id"]:
                conn.execute(
                    "UPDATE papers SET arxiv_id = ? WHERE paper_id = ?",
                    (clean, row["paper_id"]),
                )


def paper_exists(
    db_path: Path,
    *,
    paper_id: str | None = None,
    arxiv_id: str | None = None,
    doi: str | None = None,
) -> bool:
    """Check if a paper exists in the database by S2 paper_id, arXiv ID, or DOI."""
    with _get_connection(db_path) as conn:
        if paper_id:
            row = conn.execute("SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
            if row:
                return True
        if arxiv_id:
            clean_id = _strip_arxiv_version(arxiv_id)
            row = conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (clean_id,)).fetchone()
            if row:
                return True
        if doi:
            row = conn.execute("SELECT 1 FROM papers WHERE doi = ?", (doi,)).fetchone()
            if row:
                return True
    return False


def get_paper_title(
    db_path: Path,
    *,
    paper_id: str | None = None,
    arxiv_id: str | None = None,
    doi: str | None = None,
) -> str | None:
    """Look up a paper's title by S2 paper_id, arXiv ID, or DOI. Returns None if not found."""
    with _get_connection(db_path) as conn:
        if paper_id:
            row = conn.execute("SELECT title FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
            if row:
                return row["title"]
        if arxiv_id:
            clean_id = _strip_arxiv_version(arxiv_id)
            row = conn.execute("SELECT title FROM papers WHERE arxiv_id = ?", (clean_id,)).fetchone()
            if row:
                return row["title"]
        if doi:
            row = conn.execute("SELECT title FROM papers WHERE doi = ?", (doi,)).fetchone()
            if row:
                return row["title"]
    return None


def upsert_paper(
    db_path: Path,
    *,
    paper_id: str,
    title: str,
    authors: list[str],
    abstract: str | None,
    publication_date: str | None,
    year: int | None,
    arxiv_id: str | None,
    doi: str | None,
    venue: str | None,
    tldr: str | None,
    s2_url: str,
    fields_of_study: list[str],
    citation_count: int,
    influential_citation_count: int,
    open_access_pdf_url: str | None,
) -> None:
    """Insert or update a paper record, preserving the original added_at timestamp."""
    arxiv_id = _strip_arxiv_version(arxiv_id)
    now = datetime.now(timezone.utc).isoformat()
    with _get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO papers (
                paper_id, title, authors, abstract, publication_date, year,
                arxiv_id, doi, venue, tldr, s2_url, fields_of_study,
                citation_count, influential_citation_count, open_access_pdf_url, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                abstract = excluded.abstract,
                publication_date = excluded.publication_date,
                year = excluded.year,
                arxiv_id = excluded.arxiv_id,
                doi = excluded.doi,
                venue = excluded.venue,
                tldr = excluded.tldr,
                s2_url = excluded.s2_url,
                fields_of_study = excluded.fields_of_study,
                citation_count = excluded.citation_count,
                influential_citation_count = excluded.influential_citation_count,
                open_access_pdf_url = excluded.open_access_pdf_url
            """,
            (
                paper_id,
                title,
                json.dumps(authors),
                abstract,
                publication_date,
                year,
                arxiv_id,
                doi,
                venue,
                tldr,
                s2_url,
                json.dumps(fields_of_study),
                citation_count,
                influential_citation_count,
                open_access_pdf_url,
                now,
            ),
        )
