"""Index of the papers already in the vault, read from the frontmatter of the notes in Papers/.

The notes are the only record of which papers the vault holds, so the index is rebuilt from them on every run
instead of being stored. Nothing is written, which leaves no shared file for two machines to conflict over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re

import yaml

from arxivbot.identifiers import extract_arxiv_id, normalize_doi, strip_arxiv_version


LOGGER = logging.getLogger(__name__)

# A frontmatter delimiter line: exactly '---', optionally followed by trailing
# whitespace, matched as a whole line (never a '---' substring embedded in a
# value or in the body — e.g. an em-dash rendered as '---' in an S2 tldr).
_FRONTMATTER_DELIMITER_RE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)

# Every scalar loads as a string, so an unquoted arxiv_id such as 2406.12990 keeps its trailing zero
_STRING_LOADER = getattr(yaml, "CBaseLoader", yaml.BaseLoader)
_NULLS = {"", "null", "Null", "NULL", "~"}


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split note text into (frontmatter_text, body) on line-anchored '---' delimiters.

    Requires the text to begin with a line that is exactly '---'. The
    frontmatter ends at the next line that is exactly '---' (trailing
    whitespace allowed). Returns None if the text does not start with such a
    delimiter line, or if no closing delimiter line follows it.
    """
    open_match = _FRONTMATTER_DELIMITER_RE.match(text)
    if open_match is None:
        return None
    close_match = _FRONTMATTER_DELIMITER_RE.search(text, open_match.end())
    if close_match is None:
        return None
    return text[open_match.end() : close_match.start()], text[close_match.end() :]


def _read_frontmatter(note: Path) -> dict | None:
    try:
        split = split_frontmatter(note.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        LOGGER.warning(f"Skipping {note.name}: could not read file: {exc}")
        return None
    if split is None:
        return None
    try:
        frontmatter = yaml.load(split[0], Loader=_STRING_LOADER)
    except yaml.YAMLError as exc:
        LOGGER.warning(f"Skipping {note.name}: invalid YAML frontmatter: {exc}")
        return None
    return frontmatter if isinstance(frontmatter, dict) else None


def _scalar(frontmatter: dict, key: str) -> str | None:
    value = frontmatter.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return None if value in _NULLS else value


@dataclass(frozen=True)
class IndexedPaper:
    path: Path
    title: str


@dataclass
class PaperIndex:
    """Paper notes by Semantic Scholar paper ID, versionless arXiv ID and lowercased DOI. The first note found wins."""

    by_s2_id: dict[str, IndexedPaper] = field(default_factory=dict)
    by_arxiv_id: dict[str, IndexedPaper] = field(default_factory=dict)
    by_doi: dict[str, IndexedPaper] = field(default_factory=dict)

    @classmethod
    def build(cls, papers_dir: Path) -> PaperIndex:
        index = cls()
        for note in sorted(papers_dir.glob("*.md")):
            frontmatter = _read_frontmatter(note)
            if frontmatter is None:
                continue
            paper = IndexedPaper(note, _scalar(frontmatter, "title") or note.stem)
            if s2_id := _scalar(frontmatter, "s2_paper_id"):
                index.by_s2_id.setdefault(s2_id.lower(), paper)
            arxiv_id = _scalar(frontmatter, "arxiv_id") or extract_arxiv_id(_scalar(frontmatter, "link") or "")
            if arxiv_id:
                index.by_arxiv_id.setdefault(strip_arxiv_version(arxiv_id), paper)
            if doi := _scalar(frontmatter, "doi"):
                index.by_doi.setdefault(normalize_doi(doi), paper)
        LOGGER.info(
            f"Indexed {papers_dir}: {len(index.by_s2_id)} S2 IDs, "
            f"{len(index.by_arxiv_id)} arXiv IDs, {len(index.by_doi)} DOIs"
        )
        return index

    def find(
        self, *, paper_id: str | None = None, arxiv_id: str | None = None, doi: str | None = None
    ) -> IndexedPaper | None:
        """The note for a paper known by any of the given IDs, or None."""
        if paper_id and (paper := self.by_s2_id.get(paper_id.lower())):
            return paper
        if arxiv_id and (paper := self.by_arxiv_id.get(strip_arxiv_version(arxiv_id))):
            return paper
        if doi and (paper := self.by_doi.get(normalize_doi(doi))):
            return paper
        return None

    def arxiv_paths(self) -> dict[str, Path]:
        """Note path by versionless arXiv ID, which write_obsidian_paper uses to find a note under another name."""
        return {arxiv_id: paper.path for arxiv_id, paper in self.by_arxiv_id.items()}
