"""Pages the Telegram bot could not get, queued for clipping by hand from a browser.

The queue is a JSON file in the vault. A note listing it is rewritten from that file on every change, so it is
never edited by hand.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit

from arxivbot.constants import CLIP_QUEUE_NOTE, CLIP_QUEUE_PATH
from arxivbot.web_clipper import canonical_url, clipping_source


NOTE_HEADER = """\
# Clip Queue

Pages the Telegram bot could not get from the server. Open each one in your browser and clip it with the Obsidian \
Web Clipper: the bot takes it off this list once its clipping is in `Clippings/`. Send `/done <number>` to the bot \
to drop a page you no longer want. The bot rewrites this note, so edits to it are lost.

"""


def _page_key(url: str, with_query: bool = True) -> str:
    parts = urlsplit(canonical_url(url))
    key = (parts.hostname or "").removeprefix("www.") + parts.path.rstrip("/")
    return f"{key}?{parts.query}" if with_query and parts.query else key


def page_matches(page: dict, url: str) -> bool:
    """Whether url is the queued page: the link posted, or the page it redirected to, whose query may hold a token."""
    if _page_key(url) == _page_key(page["url"]):
        return True
    return bool(page.get("resolved")) and _page_key(url, with_query=False) == _page_key(page["resolved"], False)


class ClipQueue:
    def __init__(self, path: Path | None = None, note_path: Path | None = None):
        self.path, self.note_path = path or CLIP_QUEUE_PATH, note_path or CLIP_QUEUE_NOTE
        self.pages: list[dict] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def __len__(self) -> int:
        return len(self.pages)

    def find(self, url: str) -> dict | None:
        return next((page for page in self.pages if page_matches(page, url)), None)

    def add(self, url: str, reason: str, posted: date, resolved: str | None = None) -> bool:
        """Queue url, unless it is queued already. Returns whether it was added."""
        if self.find(url):
            return False
        page = {"url": url, "posted": posted.isoformat(), "reason": reason}
        if resolved and resolved != url:
            page["resolved"] = resolved
        self.pages.append(page)
        return True

    def remove(self, url: str) -> list[dict]:
        removed = [page for page in self.pages if page_matches(page, url)]
        self.pages = [page for page in self.pages if page not in removed]
        return removed

    def remove_clipped(self, clippings_dir: Path) -> list[dict]:
        """Take off the pages that now have a clipping, such as one made in the browser."""
        sources = [source for note in clippings_dir.glob("*.md") if (source := clipping_source(note))]
        removed = [page for page in self.pages if any(page_matches(page, source) for source in sources)]
        self.pages = [page for page in self.pages if page not in removed]
        return removed

    def note(self) -> str:
        lines = [f"- <{page['url']}> (posted {page['posted']}: {page['reason']})" for page in self.pages]
        return NOTE_HEADER + ("\n".join(lines) if lines else "Nothing to clip.") + "\n"

    def save(self) -> None:
        self.path.write_text(json.dumps(self.pages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.note_path.write_text(self.note(), encoding="utf-8")
