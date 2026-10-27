"""Clip web pages into the vault's Clippings/ folder, mimicking the Obsidian Web Clipper's default template."""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import date
import html as html_lib
import json
import logging
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

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
_X_HOSTS = {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
_X_POST_PATH_RE = re.compile(r"^/(\w{1,15})/status/(\d+)")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TWEET_TITLE_CHARS = 80
# A saved page's own URL, from its canonical link or og:url tag
_PAGE_URL_TAG_RE = re.compile(
    r"<link[^>]+rel=[\"']canonical[\"'][^>]*>|<meta[^>]+property=[\"']og:url[\"'][^>]*>", re.I
)
_URL_ATTR_RE = re.compile(r"(?:href|content)=[\"'](https?://[^\"']+)[\"']", re.I)
_SOURCE_RE = re.compile(r'^source: ("(?:[^"\\]|\\.)*")$', re.M)
CLIP_FILE_SUFFIXES = {".md": "markdown", ".markdown": "markdown", ".html": "html", ".htm": "html"}
# Characters YAML forbids even in double-quoted scalars, which json.dumps leaves unescaped
_YAML_UNSAFE_RE = re.compile("[\x7f-\x9f\u2028\u2029]")


class ClipError(RuntimeError):
    pass


def run_defuddle(source: str) -> dict:
    """Extract a page, from a URL or a saved HTML file, with the Defuddle CLI (the Web Clipper's extractor)."""
    # Output goes via a file: the CLI exits before flushing a piped stdout, truncating long pages at 64 KiB
    with tempfile.TemporaryDirectory(prefix="arxivbot_clip_") as tmp_dir:
        out_path = Path(tmp_dir) / "page.json"
        try:
            result = subprocess.run(
                ["defuddle", "parse", source, "--json", "--markdown", "--output", str(out_path)]
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


def canonical_url(url: str) -> str:
    """The URL a page is clipped and matched under: an X post loses twitter.com hosts and share suffixes like ?s=20."""
    parts = urlsplit(url)
    if parts.hostname in _X_HOSTS and (m := _X_POST_PATH_RE.match(parts.path)):
        return f"https://x.com/{m.group(1)}/status/{m.group(2)}"
    return url


def _x_post_title(url: str, content: str) -> str | None:
    """Title an X post "@handle on X: <opening words>", since Defuddle calls every post "Post by @handle on X"."""
    m = _X_POST_PATH_RE.match(urlsplit(url).path)
    words = " ".join(_MD_LINK_RE.sub(r"\1", _MD_IMAGE_RE.sub("", content)).split())
    if not url.startswith("https://x.com/") or not m or not words:
        return None
    if len(words) > _TWEET_TITLE_CHARS:
        words = words[:_TWEET_TITLE_CHARS].rsplit(" ", 1)[0] + "…"
    return f"@{m.group(1)} on X: {words}"


def build_clipping(url: str, page: dict, created: date) -> tuple[str, str]:
    """Build (title, note text) from Defuddle output, matching the Web Clipper's default frontmatter."""
    title = _x_post_title(url, page.get("content") or "") or (page.get("title") or "").strip() or url
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


def _new_note_path(clippings_dir: Path, stem: str) -> Path:
    note_path = clippings_dir / f"{stem}.md"
    n = 1
    while note_path.exists():
        n += 1
        note_path = clippings_dir / f"{stem} {n}.md"
    return note_path


def _save(note_path: Path, note: str) -> tuple[Path, bool]:
    note_path.parent.mkdir(exist_ok=True)
    note_path.write_text(note, encoding="utf-8")
    LOGGER.info(f"Clipped: {note_path}")
    return note_path, True


def _save_page(url: str, page: dict, clippings_dir: Path, today: date | None) -> tuple[Path, bool]:
    if not (page.get("content") or "").strip():
        raise ClipError("Defuddle extracted no content (page may need JavaScript or a login)")
    title, note = build_clipping(url, page, today or date.today())
    return _save(_new_note_path(clippings_dir, sanitize_clip_filename(title)), note)


def _already_clipped(url: str, clippings_dir: Path) -> Path | None:
    if existing := find_clipping(url, clippings_dir):
        LOGGER.info(f"Already clipped: {existing}")
    return existing


def clip_url(url: str, clippings_dir: Path = CLIPPINGS_DIR, today: date | None = None) -> tuple[Path, bool]:
    """Clip url into clippings_dir. Returns (note path, created) where created is False if already clipped."""
    url = canonical_url(url)
    if existing := _already_clipped(url, clippings_dir):
        return existing, False
    return _save_page(url, run_defuddle(url), clippings_dir, today)


def _page_url(html: str) -> str | None:
    for tag in _PAGE_URL_TAG_RE.findall(html):
        if m := _URL_ATTR_RE.search(tag):
            return html_lib.unescape(m.group(1))
    return None


def clip_html(
    html_path: Path, url: str | None = None, clippings_dir: Path = CLIPPINGS_DIR, today: date | None = None
) -> tuple[Path, bool]:
    """Clip a page saved from a browser, for pages only a logged-in browser can load.

    The source is the page's canonical URL, falling back to url when the page names none.
    """
    html = html_path.read_text(encoding="utf-8", errors="replace")
    if not (url := _page_url(html) or url):
        raise ClipError("The saved page does not name its URL. Send its link along with the file.")
    url = canonical_url(url)
    if existing := _already_clipped(url, clippings_dir):
        return existing, False

    # Defuddle resolves a saved page's relative links and images against its <base>
    base = f'<base href="{html_lib.escape(url)}">'
    based, n = re.subn(r"<head\b[^>]*>", lambda m: m.group(0) + base, html, count=1, flags=re.I)
    with tempfile.TemporaryDirectory(prefix="arxivbot_page_") as tmp_dir:
        page_path = Path(tmp_dir) / "page.html"
        page_path.write_text(based if n else base + html, encoding="utf-8")
        return _save_page(url, run_defuddle(str(page_path)), clippings_dir, today)


def clip_markdown(md_path: Path, clippings_dir: Path = CLIPPINGS_DIR) -> tuple[Path, bool]:
    """Save a note the Web Clipper exported as a file, unchanged, unless a note with its source exists."""
    note = md_path.read_text(encoding="utf-8")
    if (m := _SOURCE_RE.search(note[:4096])) and (existing := _already_clipped(json.loads(m.group(1)), clippings_dir)):
        return existing, False
    return _save(_new_note_path(clippings_dir, sanitize_clip_filename(md_path.stem)), note)


def clip_file(path: Path, url: str | None = None, clippings_dir: Path = CLIPPINGS_DIR) -> tuple[Path, bool]:
    """Clip a saved .html page or a Web Clipper .md note."""
    kind = CLIP_FILE_SUFFIXES.get(path.suffix.lower())
    if kind == "markdown":
        return clip_markdown(path, clippings_dir)
    if kind == "html":
        return clip_html(path, url, clippings_dir)
    raise ClipError(f"Cannot clip {path.name}: send a .html page or a .md note from the Web Clipper")


def main() -> None:
    parser = ArgumentParser(description="Clip web pages into the Obsidian vault's Clippings/ folder")
    parser.add_argument("sources", nargs="+", help="Page URLs, pages saved as .html, or Web Clipper .md notes")
    parser.add_argument("--url", help="Source URL for a saved .html page that does not name its own")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    failed = False
    for source in args.sources:
        try:
            if Path(source).is_file():
                clip_file(Path(source), args.url)
            else:
                clip_url(source)
        except (ClipError, OSError) as e:
            LOGGER.error(f"Failed to clip {source}: {e}")
            failed = True
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
