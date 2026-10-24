"""Clip web pages into the vault's Clippings/ folder, mimicking the Obsidian Web Clipper's default template."""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import date
import json
import logging
from pathlib import Path
import re
import subprocess
import tempfile

from arxivbot.constants import CLIPPINGS_DIR


LOGGER = logging.getLogger(__name__)

DEFUDDLE_TIMEOUT = 120
# Sites such as Medium refuse Defuddle's default User-Agent but serve a browser's
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

# Characters the Web Clipper strips from note filenames
_FILENAME_UNSAFE_RE = re.compile(r'[<>:"/\\|?*#^\[\]\x00-\x1f]')
# In bytes, leaving room for a " N.md" suffix within the usual 255-byte filename limit
_MAX_FILENAME_BYTES = 240
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Characters YAML forbids even in double-quoted scalars, which json.dumps leaves unescaped
_YAML_UNSAFE_RE = re.compile("[\x7f-\x9f\u2028\u2029]")


class ClipError(RuntimeError):
    pass


def run_defuddle(url: str) -> dict:
    """Fetch and extract a page with the Defuddle CLI (the Web Clipper's extractor). Returns its JSON output."""
    # Output goes via a file: the CLI exits before flushing a piped stdout, truncating long pages at 64 KiB
    with tempfile.TemporaryDirectory(prefix="arxivbot_clip_") as tmp_dir:
        out_path = Path(tmp_dir) / "page.json"
        try:
            result = subprocess.run(
                ["defuddle", "parse", url, "--json", "--markdown", "--output", str(out_path)]
                + ["--user-agent", USER_AGENT],
                capture_output=True,
                text=True,
                timeout=DEFUDDLE_TIMEOUT,
            )
        except FileNotFoundError as e:
            raise ClipError("Defuddle CLI not found. Install with: npm install -g defuddle") from e
        except subprocess.TimeoutExpired as e:
            raise ClipError(f"Defuddle timed out after {DEFUDDLE_TIMEOUT}s") from e
        if result.returncode != 0 or not out_path.exists():
            raise ClipError(f"Defuddle failed: {(result.stderr or result.stdout).strip()[:300]}")
        try:
            return json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ClipError(f"Defuddle returned invalid JSON: {e}") from e


def sanitize_clip_filename(title: str) -> str:
    name = _FILENAME_UNSAFE_RE.sub("", title).strip().strip(".")
    name = name.encode()[:_MAX_FILENAME_BYTES].decode(errors="ignore").rstrip()
    return name or "Untitled"


def _yaml_str(value: str) -> str:
    # A JSON string is a valid YAML double-quoted scalar
    return json.dumps(_YAML_UNSAFE_RE.sub("", value), ensure_ascii=False)


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
    return title, "\n".join(lines) + "\n" + (page.get("content") or "").strip() + "\n"


def find_clipping(url: str, clippings_dir: Path) -> Path | None:
    """The note already clipped from url, found by its source field so renamed notes still match."""
    source_line = f"\nsource: {_yaml_str(url)}\n"
    for note_path in clippings_dir.glob("*.md"):
        with note_path.open(encoding="utf-8", errors="ignore") as f:
            if source_line in f.read(4096):
                return note_path
    return None


def clip_url(url: str, clippings_dir: Path = CLIPPINGS_DIR, today: date | None = None) -> tuple[Path, bool]:
    """Clip url into clippings_dir. Returns (note path, created) where created is False if already clipped."""
    if existing := find_clipping(url, clippings_dir):
        LOGGER.info(f"Already clipped: {existing}")
        return existing, False

    page = run_defuddle(url)
    if not (page.get("content") or "").strip():
        raise ClipError("Defuddle extracted no content (page may need JavaScript or a login)")
    title, note = build_clipping(url, page, today or date.today())

    stem = sanitize_clip_filename(title)
    note_path = clippings_dir / f"{stem}.md"
    n = 1
    while note_path.exists():
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
        except (ClipError, OSError) as e:
            LOGGER.error(f"Failed to clip {url}: {e}")
            failed = True
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
