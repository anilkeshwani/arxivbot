"""Index of the papers already in the vault, read from the frontmatter of the notes in Papers/.

The notes are the only record of which papers the vault holds. What each note's frontmatter says is cached on this
machine, outside the vault, and a note is read again only when the file changes (its modification time, change time,
size or inode). The cache is derived from the notes and never committed, so there is nothing for two machines to
conflict over in git.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile

import yaml

from arxivbot.identifiers import extract_arxiv_id, normalize_doi, strip_arxiv_version


LOGGER = logging.getLogger(__name__)

# A frontmatter delimiter line: exactly '---', optionally followed by trailing
# whitespace, matched as a whole line (never a '---' substring embedded in a
# value or in the body — e.g. an em-dash rendered as '---' in an S2 tldr).
_FRONTMATTER_DELIMITER_RE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)

# Every scalar loads as a string, so an unquoted arxiv_id such as 2406.12990 keeps its trailing zero.
# The base loader builds only strings, lists and dicts, never Python objects.
_STRING_LOADER = getattr(yaml, "CBaseLoader", yaml.BaseLoader)
_NULLS = {"", "null", "Null", "NULL", "~"}

# The frontmatter fields the index reads. The cache stores them as written, and they are normalized when loaded, so
# a change to normalization needs no new cache. A change to which fields are read, or how, bumps _CACHE_VERSION.
_FIELDS = ("title", "s2_paper_id", "arxiv_id", "link", "doi")
_CACHE_VERSION = 1


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


def _read_fields(note: Path) -> dict[str, str] | None:
    """The _FIELDS a note's frontmatter sets, as strings.

    Empty for a note without valid frontmatter, None for a note that could not be read, which is not cached so the
    next run tries it again.
    """
    try:
        text = note.read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.warning(f"Skipping {note.name}: could not read file: {exc}")
        return None
    except UnicodeDecodeError as exc:
        LOGGER.warning(f"Skipping {note.name}: not UTF-8: {exc}")
        return {}
    split = split_frontmatter(text)
    if split is None:
        return {}
    try:
        frontmatter = yaml.load(split[0], Loader=_STRING_LOADER)
    except yaml.YAMLError as exc:
        LOGGER.warning(f"Skipping {note.name}: invalid YAML frontmatter: {exc}")
        return {}
    if not isinstance(frontmatter, dict):
        return {}
    fields = {}
    for key in _FIELDS:
        value = frontmatter.get(key)
        if isinstance(value, str) and (value := value.strip()) not in _NULLS:
            fields[key] = value
    return fields


def default_cache_path(papers_dir: Path) -> Path:
    """One cache file per papers folder, under $XDG_CACHE_HOME/arxivbot (default ~/.cache/arxivbot)."""
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser()
    digest = hashlib.sha256(str(papers_dir.resolve()).encode()).hexdigest()[:16]
    return cache_home / "arxivbot" / f"paper-index-{digest}.json"


def _load_cache(cache_path: Path, papers_dir: Path) -> dict[str, dict]:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        LOGGER.warning(f"Rebuilding the paper index: could not read {cache_path}: {exc}")
        return {}
    if not (
        isinstance(data, dict)
        and data.get("version") == _CACHE_VERSION
        and data.get("papers_dir") == str(papers_dir.resolve())
        and isinstance(data.get("notes"), dict)
    ):
        return {}
    return data["notes"]


def _save_cache(cache_path: Path, papers_dir: Path, notes: dict[str, dict]) -> None:
    """Write the cache atomically, so a concurrent reader sees the old file or the new one, never a partial one."""
    data = {"version": _CACHE_VERSION, "papers_dir": str(papers_dir.resolve()), "notes": notes}
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=cache_path.parent, prefix=f".{cache_path.name}.")
    except OSError as exc:
        LOGGER.warning(f"Could not save the paper index to {cache_path}: {exc}")
        return
    try:
        with open(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_name, cache_path)
    except OSError as exc:
        LOGGER.warning(f"Could not save the paper index to {cache_path}: {exc}")
        Path(tmp_name).unlink(missing_ok=True)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class IndexedPaper:
    path: Path
    title: str


@dataclass
class PaperIndex:
    """Paper notes by Semantic Scholar paper ID, versionless arXiv ID and lowercased DOI.

    When two notes share an ID, the first by file name wins.
    """

    by_s2_id: dict[str, IndexedPaper] = field(default_factory=dict)
    by_arxiv_id: dict[str, IndexedPaper] = field(default_factory=dict)
    by_doi: dict[str, IndexedPaper] = field(default_factory=dict)

    @classmethod
    def build(cls, papers_dir: Path, cache_path: Path | None = None) -> PaperIndex:
        """Index the notes in papers_dir, re-reading only those changed since the cache was saved.

        cache_path defaults to default_cache_path(papers_dir).
        """
        cache_path = cache_path or default_cache_path(papers_dir)
        cached = _load_cache(cache_path, papers_dir)
        notes: dict[str, dict] = {}
        reread = 0
        for note in sorted(papers_dir.glob("*.md")):
            try:
                stat = note.stat()
            except OSError:
                continue  # removed since the glob
            # Tools that restore a file's mtime cannot set its ctime, and a file replaced by another gets a new inode
            stamp = [stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino]
            entry = cached.get(note.name)
            if not (isinstance(entry, dict) and entry.get("stamp") == stamp and isinstance(entry.get("fields"), dict)):
                fields = _read_fields(note)
                if fields is None:
                    continue
                entry = {"stamp": stamp, "fields": fields}
                reread += 1
            notes[note.name] = entry

        if reread or notes.keys() != cached.keys():
            _save_cache(cache_path, papers_dir, notes)
        LOGGER.debug(f"Indexed {len(notes)} notes in {papers_dir}, {reread} read from disk")

        index = cls()
        for name, entry in notes.items():
            index._add(papers_dir / name, entry["fields"])
        return index

    def _add(self, path: Path, fields: dict) -> None:
        def text(key: str) -> str | None:
            value = fields.get(key)
            return value if isinstance(value, str) and value else None

        paper = IndexedPaper(path, text("title") or path.stem)
        if s2_id := text("s2_paper_id"):
            self.by_s2_id.setdefault(s2_id.lower(), paper)
        if arxiv_id := text("arxiv_id") or extract_arxiv_id(text("link") or ""):
            self.by_arxiv_id.setdefault(strip_arxiv_version(arxiv_id), paper)
        if doi := text("doi"):
            self.by_doi.setdefault(normalize_doi(doi), paper)

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
