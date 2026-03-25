#!/usr/bin/env python

from __future__ import annotations

import logging
import os
import re
from argparse import ArgumentParser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from dotenv import load_dotenv
from pathvalidate import sanitize_filename
from rich.logging import RichHandler
from semanticscholar import SemanticScholar

from arxivbot.constants import DB_PATH, DEFAULT_PAPER_TAGS, PAPERS_DIR, PDFS_DIR, S2_BATCH_SIZE, S2_FIELDS
from arxivbot.database import get_paper_title, init_db, paper_exists, upsert_paper
from arxivbot.utils import inflect_day, parse_paper_id


LOGGER = logging.getLogger(__name__)


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
    arxiv_id: str,
    s2_paper_id: str,
    s2_url: str,
    pdf_url: str,
    citation_count: int,
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
        "arxiv_id": arxiv_id,
        "s2_paper_id": s2_paper_id,
        "s2_url": s2_url,
        "pdf_url": pdf_url,
        "citation_count": citation_count,
        "code": notion_entry["Code"] if notion_entry is not None else "",
        "page": notion_entry["Page"] if notion_entry is not None else "",
        "demo": notion_entry["Demo"] if notion_entry is not None else "",
        "tags": notion_entry["Tags"] if notion_entry is not None else DEFAULT_PAPER_TAGS,
    }
    frontmatter = yaml.dump(frontmatter_fields, sort_keys=False, allow_unicode=True)
    return "---" + "\n" + frontmatter + "---" + "\n"


# Target frontmatter key order for consistent notes
_FRONTMATTER_KEY_ORDER = [
    "title", "authors", "published", "link", "doi", "venue", "tldr",
    "arxiv_id", "s2_paper_id", "s2_url", "pdf_url", "citation_count",
    "code", "page", "demo", "tags",
]


def _update_existing_note(note_path: Path, new_fields: dict) -> None:
    """Additively merge new frontmatter fields into an existing Obsidian note.

    Only missing keys are added — existing values are NEVER overwritten.
    Fields are inserted in the canonical order defined by _FRONTMATTER_KEY_ORDER.
    """
    text = note_path.read_text(encoding="utf-8")

    # Split on the YAML front-matter delimiters (first two '---' lines)
    parts = text.split("---", 2)
    if len(parts) < 3:
        LOGGER.warning(f"Could not parse frontmatter in {note_path} — skipping update")
        return

    existing_fm = yaml.safe_load(parts[1])
    if not isinstance(existing_fm, dict):
        LOGGER.warning(f"Frontmatter is not a dict in {note_path} — skipping update")
        return

    body = parts[2]  # everything after the closing '---'

    # Determine which keys are actually new
    keys_to_add = {k: v for k, v in new_fields.items() if k not in existing_fm}
    if not keys_to_add:
        LOGGER.info(f"No new frontmatter keys to add for {note_path.name}")
        return

    # Build merged dict in canonical order
    merged: dict = {}
    for key in _FRONTMATTER_KEY_ORDER:
        if key in existing_fm:
            merged[key] = existing_fm[key]
        elif key in keys_to_add:
            merged[key] = keys_to_add[key]
    # Preserve any keys not in the canonical order (shouldn't happen, but be safe)
    for key in existing_fm:
        if key not in merged:
            merged[key] = existing_fm[key]

    new_frontmatter = yaml.dump(merged, sort_keys=False, allow_unicode=True)
    note_path.write_text("---\n" + new_frontmatter + "---" + body, encoding="utf-8")
    LOGGER.info(f"Updated frontmatter ({len(keys_to_add)} new keys) for {note_path.name}")


def _build_arxiv_index(papers_dir: Path) -> dict[str, Path]:
    """Build a mapping from normalized (versionless) arXiv ID to existing note path.

    Scans all .md files once, extracting arXiv IDs from frontmatter (arxiv_id field
    or link field). First match wins — if two files share the same arXiv ID, the
    first one found is kept.
    """
    index: dict[str, Path] = {}
    for md in papers_dir.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            LOGGER.warning(f"Skipping {md.name}: could not read file: {exc}")
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1])
        except yaml.YAMLError as exc:
            LOGGER.warning(f"Skipping {md.name}: invalid YAML frontmatter: {exc}")
            continue
        if not isinstance(fm, dict):
            continue
        # Check arxiv_id field
        aid = str(fm.get("arxiv_id", "") or "")
        if aid:
            clean = re.sub(r"v\d+$", "", aid)
            index.setdefault(clean, md)
            continue
        # Fall back to extracting from link
        link = str(fm.get("link", "") or "")
        m = re.search(r"(\d{4}\.\d{4,5})", link)
        if m:
            index.setdefault(m.group(1), md)
    LOGGER.info(f"Built arXiv index: {len(index)} papers with arXiv IDs")
    return index


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
    arxiv_id: str = "",
    s2_paper_id: str = "",
    s2_url: str = "",
    pdf_url: str | None = None,
    citation_count: int = 0,
    notion_entry: dict | None = None,
    obsidian_papers_dir: Path = PAPERS_DIR,
    obsidian_pdfs_dir: Path = PDFS_DIR,
    download_pdf: bool = True,
    log_fileexistserror: bool = False,
    arxiv_index: dict[str, Path] | None = None,
) -> str:
    MD_LINE_ENDING = "  \n"

    # Build published string for YAML frontmatter
    if published_date:
        published_str = published_date.isoformat()  # YYYY-MM-DD
    elif year:
        published_str = str(year)
    else:
        published_str = ""

    frontmatter = collect_paper_yaml(
        title, authors, published_str, link, doi, venue, tldr,
        arxiv_id, s2_paper_id, s2_url, pdf_url or "", citation_count,
        notion_entry,
    )

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

    s2_fields = {
        "doi": doi,
        "venue": venue,
        "tldr": tldr,
        "arxiv_id": arxiv_id,
        "s2_paper_id": s2_paper_id,
        "s2_url": s2_url,
        "pdf_url": pdf_url or "",
        "citation_count": citation_count,
    }

    # Check if a note with the same arXiv ID already exists under a different filename
    existing_path = None
    if arxiv_id and arxiv_index:
        clean_id = re.sub(r"v\d+$", "", arxiv_id)
        existing_path = arxiv_index.get(clean_id)

    if existing_path and existing_path != obsidian_paper_path:
        LOGGER.info("Paper exists under different name, updating frontmatter:")
        LOGGER.info(f"  existing: {existing_path.name}")
        LOGGER.info(f"  S2 title: {filename}")
        _update_existing_note(existing_path, s2_fields)
    else:
        try:
            with open(obsidian_paper_path, "x") as f:
                f.write(obsidian_paper)
                LOGGER.info(str(obsidian_paper_path))
        except FileExistsError as fee:
            LOGGER.info("Paper already present in vault, updating frontmatter:")
            LOGGER.info(str(obsidian_paper_path))
            _update_existing_note(obsidian_paper_path, s2_fields)
            if log_fileexistserror:
                LOGGER.exception(fee)

    if download_pdf and pdf_url:
        parsed_url = urlparse(pdf_url)
        if parsed_url.scheme not in ("http", "https"):
            LOGGER.warning(f"Skipping PDF download: unexpected URL scheme {pdf_url!r}")
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
                    LOGGER.warning(f"PDF download failed for {pdf_url!r}: {e}")

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
        all_not_found.extend(nf.paperId if hasattr(nf, "paperId") else nf for nf in not_found)

    return all_papers, all_not_found, all_failed


def _process_paper(paper: dict, download_pdf: bool, arxiv_index: dict[str, Path] | None = None) -> None:
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
        arxiv_id=paper["arxiv_id"] or "",
        s2_paper_id=paper["paper_id"] or "",
        s2_url=paper["s2_url"],
        pdf_url=paper["pdf_url"],
        citation_count=paper["citation_count"],
        download_pdf=download_pdf,
        arxiv_index=arxiv_index,
    )


def _paper_exists_locally(s2_id: str) -> bool:
    """Check whether a paper is already in the local DB, given its S2 query ID."""
    if s2_id.startswith("ARXIV:"):
        return paper_exists(DB_PATH, arxiv_id=s2_id.removeprefix("ARXIV:"))
    if s2_id.startswith("DOI:"):
        return paper_exists(DB_PATH, doi=s2_id.removeprefix("DOI:"))
    if s2_id.startswith("CORPUSID:"):
        LOGGER.debug(f"Cannot resolve CorpusID locally (DB does not store CorpusIDs): {s2_id}")
        return False
    return paper_exists(DB_PATH, paper_id=s2_id)


def _get_title_for_s2_id(s2_id: str) -> str | None:
    """Look up the title for a paper in the local DB given its S2 query ID."""
    if s2_id.startswith("ARXIV:"):
        return get_paper_title(DB_PATH, arxiv_id=s2_id.removeprefix("ARXIV:"))
    if s2_id.startswith("DOI:"):
        return get_paper_title(DB_PATH, doi=s2_id.removeprefix("DOI:"))
    if s2_id.startswith("CORPUSID:"):
        return None
    return get_paper_title(DB_PATH, paper_id=s2_id)


def _find_raw_input(paper: dict, raw_by_s2_id: dict[str, str]) -> str | None:
    """Find the raw user input that corresponds to a fetched paper."""
    if paper.get("arxiv_id"):
        raw = raw_by_s2_id.get(f"ARXIV:{paper['arxiv_id']}")
        if raw:
            return raw
    if paper.get("doi"):
        raw = raw_by_s2_id.get(f"DOI:{paper['doi']}")
        if raw:
            return raw
    return raw_by_s2_id.get(paper.get("paper_id", ""))


def main():
    parser = ArgumentParser(description="Import papers to Obsidian vault via Semantic Scholar API")
    parser.add_argument("id_list", type=str, nargs="+", help="Paper identifiers (arXiv IDs/URLs, S2 IDs/URLs, DOIs)")
    parser.add_argument("--no_pdf", action="store_false", dest="download_pdf", help="Skip PDF download")
    parser.add_argument("--force", action="store_true", help="Re-fetch papers even if already in local database")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("dotenv.main").setLevel(logging.ERROR)

    # Initialize database
    init_db(DB_PATH)

    # Initialize S2 client
    api_key = _load_s2_api_key()
    sch = SemanticScholar(api_key=api_key) if api_key else SemanticScholar()

    # Phase 1: Parse all identifiers, collecting valid S2 IDs (deduplicated)
    s2_ids: list[str] = []
    raw_by_s2_id: dict[str, str] = {}  # s2_id -> first raw input (for error messages)
    skipped_local: list[tuple[str, str]] = []  # (raw_id, s2_id)
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
            skipped_local.append((raw_id, s2_id))
            continue
        s2_ids.append(s2_id)
        raw_by_s2_id[s2_id] = raw_id

    for raw_id, s2_id in skipped_local:
        title = _get_title_for_s2_id(s2_id)
        title_suffix = f" — \"{title}\"" if title else ""
        LOGGER.info(f"Already in local database, skipping: {raw_id!r}{title_suffix} (use --force to re-fetch)")

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

    # Phase 3: Build arXiv index and process each fetched paper (DB upsert + Obsidian note)
    arxiv_index = _build_arxiv_index(PAPERS_DIR)
    for paper in papers:
        raw_input = _find_raw_input(paper, raw_by_s2_id)
        input_prefix = f"{raw_input!r} — " if raw_input else ""
        try:
            LOGGER.info(f"Importing: {input_prefix}\"{paper['title']}\"")
            _process_paper(paper, args.download_pdf, arxiv_index=arxiv_index)
        except Exception as e:
            LOGGER.error(f"Failed to process {input_prefix}\"{paper['title']}\": {e}")


if __name__ == "__main__":
    main()
