#!/usr/bin/env python

from __future__ import annotations

import logging
import os
from argparse import ArgumentParser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from dotenv import load_dotenv
from pathvalidate import sanitize_filename
from semanticscholar import SemanticScholar

from arxivbot.constants import DB_PATH, DEFAULT_PAPER_TAGS, PAPERS_DIR, PDFS_DIR, S2_BATCH_SIZE, S2_FIELDS
from arxivbot.database import init_db, paper_exists, upsert_paper
from arxivbot.utils import inflect_day, parse_paper_id


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(logging.StreamHandler())


def _load_s2_api_key() -> str | None:
    """Load S2 API key from environment."""
    load_dotenv()
    load_dotenv("credentials.env")
    return os.environ.get("S2_API_KEY")


def _get_arxiv_link(arxiv_id: str | None) -> str | None:
    """Construct arXiv abstract URL from arXiv ID."""
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    return None


def _get_pdf_url(arxiv_id: str | None, open_access_pdf: dict | None) -> str | None:
    """Best-effort PDF URL: prefer arXiv, then openAccessPdf."""
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}"
    if open_access_pdf and open_access_pdf.get("url"):
        return open_access_pdf["url"]
    return None


def _parse_publication_date(pub_date_str: str | None) -> date | None:
    """Parse S2 publicationDate (YYYY-MM-DD) to a date object."""
    if pub_date_str:
        try:
            return date.fromisoformat(pub_date_str)
        except (ValueError, TypeError):
            return None
    return None


def get_author_wiki(author_name: str, people_dir: Path | str = "People") -> str:
    _author_page = Path(people_dir, sanitize_filename(author_name))
    return f"[[{str(_author_page)}|{author_name}]]"


def collect_paper_yaml(
    title: str,
    authors: list[str],
    published_str: str,
    link: str,
    doi: str,
    venue: str,
    tldr: str,
    notion_entry: dict | None,
) -> str:
    """Build YAML frontmatter string.

    CRITICAL: The field ordering and field names must match the original format exactly
    for existing fields. New fields (doi, venue, tldr) are added after 'link'.
    """
    frontmatter_fields = {
        "title": title,
        "authors": authors,
        "published": published_str,
        "link": link,
        "doi": doi,
        "venue": venue,
        "tldr": tldr,
        "code": notion_entry["Code"] if notion_entry is not None else "",
        "page": notion_entry["Page"] if notion_entry is not None else "",
        "demo": notion_entry["Demo"] if notion_entry is not None else "",
        "tags": notion_entry["Tags"] if notion_entry is not None else DEFAULT_PAPER_TAGS,
    }
    frontmatter = yaml.dump(frontmatter_fields, sort_keys=False, allow_unicode=True)
    return "---" + "\n" + frontmatter + "---" + "\n"


def write_obsidian_paper(
    title: str,
    authors: list[str],
    abstract: str,
    published_date: date | None,
    year: int | None,
    link: str,
    doi: str,
    venue: str,
    tldr: str,
    notion_entry: dict | None,
    obsidian_papers_dir: Path,
    obsidian_pdfs_dir: Path,
    download_pdf: bool,
    pdf_url: str | None,
    log_fileexistserror: bool = False,
) -> str:
    MD_LINE_ENDING = "  \n"

    # Build published string for YAML frontmatter
    if published_date:
        published_str = published_date.isoformat()  # YYYY-MM-DD
    elif year:
        published_str = str(year)
    else:
        published_str = ""

    frontmatter = collect_paper_yaml(title, authors, published_str, link, doi, venue, tldr, notion_entry)

    # Wikified authors
    _authors_wikified = ", ".join([get_author_wiki(name) for name in authors])

    # Clean abstract
    paper_abstract = abstract.replace("-\n", "-").replace("\n", " ") if abstract else ""

    # Pretty-printed date
    if published_date:
        pretty_date = inflect_day(published_date.day) + published_date.strftime(" %B %Y (%A)")
    elif year:
        pretty_date = str(year)
    else:
        pretty_date = "Unknown"

    metadata_fields = (
        f"Title: {title}",
        f"Authors: {_authors_wikified}",
        f"Published: {pretty_date}",
        f"Link: {link}",
    )

    inline_metadata = MD_LINE_ENDING.join(metadata_fields)
    abstract_callout = MD_LINE_ENDING.join(("> [!abstract]", f"> {paper_abstract}"))
    obsidian_paper = frontmatter + "\n" + inline_metadata + "\n\n" + abstract_callout + "\n\n" "---" + "\n\n"

    filename = sanitize_filename(title.replace(".", " "))
    obsidian_paper_path = (obsidian_papers_dir / filename).with_suffix(".md")
    try:
        with open(obsidian_paper_path, "x") as f:
            f.write(obsidian_paper)
            LOGGER.info(str(obsidian_paper_path))
    except FileExistsError as fee:
        LOGGER.info("Skipping. Paper already present in vault:")
        LOGGER.info(str(obsidian_paper_path))
        if log_fileexistserror:
            LOGGER.exception(fee)

    if download_pdf and pdf_url:
        parsed_url = urlparse(pdf_url)
        if parsed_url.scheme not in ("http", "https"):
            LOGGER.warning("Skipping PDF download: unexpected URL scheme %r", pdf_url)
        else:
            pdf_filename = f"{filename}.pdf"
            pdf_path = obsidian_pdfs_dir / pdf_filename
            if pdf_path.exists():
                LOGGER.info("Skipping. PDF already present in vault:")
                LOGGER.info(str(pdf_path))
            else:
                try:
                    response = requests.get(pdf_url, timeout=60)
                    response.raise_for_status()
                    pdf_path.write_bytes(response.content)
                    LOGGER.info(str(pdf_path))
                except requests.RequestException as e:
                    LOGGER.warning("PDF download failed for %r: %s", pdf_url, e)

    return obsidian_paper


def _normalize_paper(paper) -> dict:
    """Normalize an S2 Paper object into a flat dict for downstream consumption."""
    external_ids = paper.externalIds or {}
    arxiv_id = external_ids.get("ArXiv")
    doi = external_ids.get("DOI")

    tldr_text = ""
    if paper.tldr:
        tldr_text = paper.tldr.get("text", "") if isinstance(paper.tldr, dict) else getattr(paper.tldr, "text", "")

    open_access = None
    if paper.openAccessPdf:
        if isinstance(paper.openAccessPdf, dict):
            open_access = paper.openAccessPdf
        else:
            open_access = {"url": getattr(paper.openAccessPdf, "url", "")}

    authors = []
    for a in paper.authors or []:
        name = a.get("name", "") if isinstance(a, dict) else getattr(a, "name", "")
        if name:
            authors.append(name)

    fields_of_study = paper.fieldsOfStudy or []
    if not isinstance(fields_of_study, list):
        fields_of_study = list(fields_of_study)

    link = _get_arxiv_link(arxiv_id) or paper.url or ""
    pdf_url = _get_pdf_url(arxiv_id, open_access)

    return {
        "paper_id": paper.paperId,
        "title": paper.title or "Untitled",
        "authors": authors,
        "abstract": paper.abstract,
        "publication_date": paper.publicationDate.strftime("%Y-%m-%d") if paper.publicationDate else None,
        "year": paper.year,
        "arxiv_id": arxiv_id,
        "doi": doi,
        "venue": paper.venue or "",
        "tldr": tldr_text,
        "s2_url": paper.url or "",
        "fields_of_study": fields_of_study,
        "citation_count": paper.citationCount or 0,
        "influential_citation_count": paper.influentialCitationCount or 0,
        "link": link,
        "pdf_url": pdf_url,
        "open_access_pdf_url": (open_access or {}).get("url") or None,
    }


def fetch_paper(sch: SemanticScholar, paper_id: str) -> dict:
    """Fetch a single paper from S2 API and return a normalized dict."""
    paper = sch.get_paper(paper_id, fields=S2_FIELDS)
    return _normalize_paper(paper)


def fetch_papers_batch(
    sch: SemanticScholar, paper_ids: list[str]
) -> tuple[list[dict], list[str], list[str]]:
    """Fetch papers in batch via POST /paper/batch, chunking if needed.

    Returns (normalized_papers, not_found_ids, failed_ids).
    """
    all_papers: list[dict] = []
    all_not_found: list[str] = []
    all_failed: list[str] = []

    for i in range(0, len(paper_ids), S2_BATCH_SIZE):
        chunk = paper_ids[i : i + S2_BATCH_SIZE]
        try:
            papers, not_found = sch.get_papers(chunk, fields=S2_FIELDS, return_not_found=True)
        except Exception as e:
            LOGGER.error(f"Batch fetch failed for chunk {i // S2_BATCH_SIZE + 1}: {e}")
            all_failed.extend(chunk)
            continue
        for p in papers:
            try:
                all_papers.append(_normalize_paper(p))
            except Exception as e:
                paper_id = getattr(p, "paperId", "unknown")
                LOGGER.error(f"Failed to normalize paper {paper_id}: {e}")
        all_not_found.extend(not_found)

    return all_papers, all_not_found, all_failed


def _process_paper(paper: dict, download_pdf: bool) -> None:
    """Upsert a normalized paper dict into the DB and write an Obsidian note."""
    upsert_paper(
        DB_PATH,
        paper_id=paper["paper_id"],
        title=paper["title"],
        authors=paper["authors"],
        abstract=paper["abstract"],
        publication_date=paper["publication_date"],
        year=paper["year"],
        arxiv_id=paper["arxiv_id"],
        doi=paper["doi"],
        venue=paper["venue"],
        tldr=paper["tldr"],
        s2_url=paper["s2_url"],
        fields_of_study=paper["fields_of_study"],
        citation_count=paper["citation_count"],
        influential_citation_count=paper["influential_citation_count"],
        open_access_pdf_url=paper["open_access_pdf_url"],
    )

    pub_date = _parse_publication_date(paper["publication_date"])

    write_obsidian_paper(
        title=paper["title"],
        authors=paper["authors"],
        abstract=paper["abstract"] or "",
        published_date=pub_date,
        year=paper["year"],
        link=paper["link"],
        doi=paper["doi"] or "",
        venue=paper["venue"],
        tldr=paper["tldr"],
        notion_entry=None,
        obsidian_papers_dir=PAPERS_DIR,
        obsidian_pdfs_dir=PDFS_DIR,
        download_pdf=download_pdf,
        pdf_url=paper["pdf_url"],
    )


def _paper_exists_locally(s2_id: str) -> bool:
    """Check whether a paper is already in the local DB, given its S2 query ID."""
    if s2_id.startswith("ARXIV:"):
        return paper_exists(DB_PATH, arxiv_id=s2_id.removeprefix("ARXIV:"))
    if s2_id.startswith("DOI:"):
        return paper_exists(DB_PATH, doi=s2_id.removeprefix("DOI:"))
    return paper_exists(DB_PATH, paper_id=s2_id)


def main():
    parser = ArgumentParser(description="Import papers to Obsidian vault via Semantic Scholar API")
    parser.add_argument("id_list", type=str, nargs="+", help="Paper identifiers (arXiv IDs/URLs, S2 IDs/URLs, DOIs)")
    parser.add_argument("--no_pdf", action="store_false", dest="download_pdf", help="Skip PDF download")
    parser.add_argument("--force", action="store_true", help="Re-fetch papers even if already in local database")
    args = parser.parse_args()

    # Initialize database
    init_db(DB_PATH)

    # Initialize S2 client
    api_key = _load_s2_api_key()
    sch = SemanticScholar(api_key=api_key) if api_key else SemanticScholar()

    # Phase 1: Parse all identifiers, collecting valid S2 IDs (deduplicated)
    s2_ids: list[str] = []
    raw_by_s2_id: dict[str, str] = {}  # s2_id -> first raw input (for error messages)
    skipped_local: list[str] = []
    for raw_id in args.id_list:
        try:
            s2_id = parse_paper_id(raw_id)
        except ValueError as e:
            LOGGER.error(f"Skipping {raw_id!r}: {e}")
            continue
        if s2_id in raw_by_s2_id:
            LOGGER.warning(f"Skipping {raw_id!r}: resolves to same ID as {raw_by_s2_id[s2_id]!r}")
            continue
        if not args.force and _paper_exists_locally(s2_id):
            skipped_local.append(raw_id)
            continue
        s2_ids.append(s2_id)
        raw_by_s2_id[s2_id] = raw_id

    for raw_id in skipped_local:
        LOGGER.info(f"Already in local database, skipping: {raw_id!r} (use --force to re-fetch)")

    if not s2_ids:
        if skipped_local:
            LOGGER.info("All papers already in local database. Nothing to fetch.")
        else:
            LOGGER.error("No valid paper identifiers provided.")
        return

    # Phase 2: Batch fetch from S2 API
    LOGGER.info(f"Fetching {len(s2_ids)} paper(s) from Semantic Scholar...")
    papers, not_found, failed = fetch_papers_batch(sch, s2_ids)

    for nf_id in not_found:
        raw = raw_by_s2_id.get(nf_id, nf_id)
        LOGGER.warning(f"Paper not found: {raw!r} (resolved to {nf_id!r})")

    for fail_id in failed:
        raw = raw_by_s2_id.get(fail_id, fail_id)
        LOGGER.error(f"Failed to fetch (API error): {raw!r} (resolved to {fail_id!r})")

    LOGGER.info(
        f"Retrieved {len(papers)} paper(s), {len(not_found)} not found, {len(failed)} failed."
    )

    # Phase 3: Process each fetched paper (DB upsert + Obsidian note)
    for paper in papers:
        try:
            _process_paper(paper, args.download_pdf)
        except Exception as e:
            LOGGER.error(f"Failed to process {paper['title']!r}: {e}")


if __name__ == "__main__":
    main()
