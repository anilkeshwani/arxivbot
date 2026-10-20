import sqlite3

from arxivbot.database import init_db, paper_exists, upsert_paper


def _upsert(db_path, **overrides):
    fields = dict(
        paper_id="abc123",
        title="A Paper",
        authors=["A. Author"],
        abstract=None,
        publication_date=None,
        year=2026,
        arxiv_id="2408.16532v2",
        doi="10.1145/ABC",
        venue="",
        tldr=None,
        s2_url="https://www.semanticscholar.org/paper/abc123",
        fields_of_study=[],
        citation_count=0,
        influential_citation_count=0,
        open_access_pdf_url=None,
    )
    fields.update(overrides)
    upsert_paper(db_path, **fields)


def test_lookups_ignore_arxiv_version_and_doi_case(tmp_path):
    db_path = tmp_path / "papers.db"
    init_db(db_path)
    _upsert(db_path)
    assert paper_exists(db_path, arxiv_id="2408.16532")
    assert paper_exists(db_path, arxiv_id="2408.16532v5")
    assert paper_exists(db_path, doi="10.1145/abc")
    assert paper_exists(db_path, doi="https://doi.org/10.1145/Abc")
    assert not paper_exists(db_path, doi="10.1145/other")


def test_init_db_normalizes_existing_dois(tmp_path):
    db_path = tmp_path / "papers.db"
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO papers (paper_id, title, authors, doi, s2_url, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("legacy", "Legacy", "[]", "10.1109/ICASSP.2023.1", "", "2025-01-01"),
        )
    init_db(db_path)
    assert paper_exists(db_path, doi="10.1109/icassp.2023.1")
