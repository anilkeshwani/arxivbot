"""Clip web pages into the vault's Clippings/ folder, mimicking the Obsidian Web Clipper's default template."""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import date
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urljoin

from arxivbot.constants import CLIPPINGS_DIR


LOGGER = logging.getLogger(__name__)

# Defuddle is the extraction library behind the Obsidian Web Clipper; its CLI is an npm package (defuddle-cli)
DEFUDDLE_BIN = os.environ.get("DEFUDDLE_BIN", "defuddle")
DEFUDDLE_TIMEOUT = 120

# Characters the Web Clipper strips from note filenames
_FILENAME_UNSAFE_RE = re.compile(r'[<>:"/\\|?*#^\[\]\x00-\x1f]')
_MAX_FILENAME_LEN = 200
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Markdown link/image targets that are relative, e.g. ](/_next/image?url=...) or ](../img.png)
_RELATIVE_TARGET_RE = re.compile(r"\]\((?![a-zA-Z][a-zA-Z0-9+.-]*:|#)([^)\s]+)")
_SOURCE_RE = re.compile(r'^source:\s*"?(.*?)"?\s*$', re.MULTILINE)


class ClipError(RuntimeError):
    pass


def run_defuddle(url: str) -> dict:
    """Fetch and extract a page with the Defuddle CLI. Returns its JSON output (content is markdown)."""
    # Output goes via a file: the CLI exits before flushing a piped stdout, truncating long pages at 64 KiB
    with tempfile.TemporaryDirectory(prefix="arxivbot_clip_") as tmp_dir:
        out_path = Path(tmp_dir) / "page.json"
        try:
            result = subprocess.run(
                [DEFUDDLE_BIN, "parse", url, "--json", "--markdown", "--output", str(out_path)],
                capture_output=True,
                text=True,
                timeout=DEFUDDLE_TIMEOUT,
            )
        except FileNotFoundError as e:
            raise ClipError(f"Defuddle CLI not found ({DEFUDDLE_BIN!r}). Install with: npm install -g defuddle") from e
        except subprocess.TimeoutExpired as e:
            raise ClipError(f"Defuddle timed out after {DEFUDDLE_TIMEOUT}s") from e
        if result.returncode != 0 or not out_path.exists():
            raise ClipError(f"Defuddle failed: {(result.stderr or result.stdout).strip()[:500]}")
        try:
            return json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ClipError(f"Defuddle returned invalid JSON: {e}") from e


def sanitize_clip_filename(title: str) -> str:
    name = _FILENAME_UNSAFE_RE.sub("", title)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:_MAX_FILENAME_LEN].rstrip() or "Untitled"


def resolve_relative_links(markdown: str, base_url: str) -> str:
    return _RELATIVE_TARGET_RE.sub(lambda m: f"]({urljoin(base_url, m.group(1))}", markdown)


def _yaml_str(value: str) -> str:
    # A JSON string is a valid YAML double-quoted scalar
    return json.dumps(value, ensure_ascii=False)


def build_clipping(url: str, page: dict, created: date) -> tuple[str, str]:
    """Build (title, note text) from Defuddle output, matching the Web Clipper's default frontmatter."""
    title = (page.get("title") or "").strip() or url
    authors = [a.strip() for a in (page.get("author") or "").split(",") if a.strip()]
    published = _DATE_RE.search(page.get("published") or "")
    description = (page.get("description") or "").strip()

    lines = ["---", f"title: {_yaml_str(title)}", f"source: {_yaml_str(url)}"]
    lines += ["author:"] + [f"  - {_yaml_str(f'[[{a}]]')}" for a in authors]
    lines.append(f"published: {published.group(0)}" if published else "published:")
    lines.append(f"created: {created.isoformat()}")
    lines.append(f"description: {_yaml_str(description)}" if description else "description:")
    lines += ["tags:", '  - "clippings"', "---"]

    body = resolve_relative_links((page.get("content") or "").strip(), url)
    return title, "\n".join(lines) + "\n" + body + "\n"


def _existing_source(note_path: Path) -> str | None:
    match = _SOURCE_RE.search(note_path.read_text(encoding="utf-8")[:2000])
    return match.group(1) if match else None


def clip_url(url: str, clippings_dir: Path = CLIPPINGS_DIR, created: date | None = None) -> tuple[Path, bool]:
    """Clip url into clippings_dir. Returns (note path, created) where created is False if already clipped."""
    page = run_defuddle(url)
    if not (page.get("content") or "").strip():
        raise ClipError("Defuddle extracted no content (page may need JavaScript or a login)")
    title, note = build_clipping(url, page, created or date.today())

    stem = sanitize_clip_filename(title)
    note_path = clippings_dir / f"{stem}.md"
    n = 1
    while note_path.exists():
        if _existing_source(note_path) == url:
            LOGGER.info(f"Already clipped: {note_path}")
            return note_path, False
        n += 1
        note_path = clippings_dir / f"{stem} {n}.md"

    clippings_dir.mkdir(exist_ok=True)
    note_path.write_text(note, encoding="utf-8")
    LOGGER.info(f"Clipped: {note_path}")
    return note_path, True


def main() -> None:
    parser = ArgumentParser(description="Clip web pages into the Obsidian vault's Clippings/ folder")
    parser.add_argument("urls", nargs="+", help="Page URLs to clip")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    failed = False
    for url in args.urls:
        try:
            clip_url(url)
        except ClipError as e:
            LOGGER.error(f"Failed to clip {url}: {e}")
            failed = True
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
