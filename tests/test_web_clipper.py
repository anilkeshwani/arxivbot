from datetime import date
from pathlib import Path
import subprocess

import pytest
import yaml

from arxivbot import web_clipper
from arxivbot.web_clipper import ClipError, build_clipping, clip_file, clip_html, clip_url, sanitize_clip_filename


URL = "https://www.speechmatics.com/company/articles-and-news/meet-oak"
PAGE = {
    "title": "Meet Oak: medical transcription",
    "author": "Ada Lovelace, Alan Turing",
    "published": "2026-10-14T10:14:53.528Z, 2026-10-14T00:00:00.000Z",
    "description": 'Oak is "first" for recall',
    "content": "Intro\n\n![fig](https://www.speechmatics.com/a.png)",
}


def test_build_clipping_matches_web_clipper_template():
    title, note = build_clipping(URL, PAGE, date(2026, 10, 21))
    assert title == "Meet Oak: medical transcription"
    assert note == (
        "---\n"
        'title: "Meet Oak: medical transcription"\n'
        f'source: "{URL}"\n'
        "author:\n"
        '  - "[[Ada Lovelace]]"\n'
        '  - "[[Alan Turing]]"\n'
        "published: 2026-10-14\n"
        "created: 2026-10-21\n"
        'description: "Oak is \\"first\\" for recall"\n'
        "tags:\n"
        '  - "clippings"\n'
        "---\n"
        "Intro\n\n![fig](https://www.speechmatics.com/a.png)\n"
    )


def test_build_clipping_leaves_missing_fields_empty():
    _, note = build_clipping(URL, {"content": "Body"}, date(2026, 10, 21))
    assert f'title: "{URL}"' in note
    assert "author:\npublished:\ncreated: 2026-10-21\ndescription:\ntags:" in note


def test_build_clipping_frontmatter_is_valid_yaml_with_control_characters():
    _, note = build_clipping(URL, {"title": "Bad\x7f title", "content": "Body"}, date(2026, 10, 21))
    assert yaml.safe_load(note.split("---\n")[1])["title"] == "Badtitle"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Meet Oak: medical transcription", "Meet Oak medical transcription"),
        ("A/B testing? [Part #1] | Blog", "AB testing Part 1  Blog"),
        ("  Trailing dots...  ", "Trailing dots"),
        (":::", "Untitled"),
        ("語" * 100, "語" * 80),
    ],
)
def test_sanitize_clip_filename(title, expected):
    assert sanitize_clip_filename(title) == expected


def test_clip_url_writes_note_and_skips_reclip(tmp_path, monkeypatch):
    monkeypatch.setattr(web_clipper, "run_defuddle", lambda url: PAGE)
    path, created = clip_url(URL, tmp_path, today=date(2026, 10, 21))
    assert created and path == tmp_path / "Meet Oak medical transcription.md"

    renamed = path.rename(tmp_path / "Oak.md")
    again, created = clip_url(URL, tmp_path)
    assert not created and again == renamed

    other, created = clip_url("https://other.example/meet-oak", tmp_path)
    assert created and other == tmp_path / "Meet Oak medical transcription.md"
    clip_url("https://third.example/meet-oak", tmp_path)
    assert (tmp_path / "Meet Oak medical transcription 2.md").exists()


def test_clip_url_rejects_empty_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(web_clipper, "run_defuddle", lambda url: {"title": "Login", "content": "  "})
    with pytest.raises(ClipError):
        clip_url(URL, tmp_path)
    assert not list(tmp_path.iterdir())


def test_run_defuddle_sends_a_browser_user_agent(monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "Error: Failed to fetch: 403 Forbidden")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ClipError, match="403 Forbidden"):
        web_clipper.run_defuddle(URL)
    assert calls[0][calls[0].index("--user-agent") + 1].startswith("Mozilla/5.0")


POST = "https://x.com/karpathy/status/1886192184808149383"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (POST, POST),
        ("https://twitter.com/karpathy/status/1886192184808149383?s=20&t=abc", POST),
        ("https://mobile.x.com/karpathy/status/1886192184808149383/photo/1", POST),
        ("https://x.com/AnthropicAI", "https://x.com/AnthropicAI"),
        ("https://example.com/a?s=20", "https://example.com/a?s=20"),
    ],
)
def test_canonical_url(url, expected):
    assert web_clipper.canonical_url(url) == expected


def test_x_post_clip_is_titled_with_its_opening_words_and_matched_across_hosts(tmp_path, monkeypatch):
    content = (
        '![photo](https://pbs.twimg.com/a.jpg) There\'s a new kind of coding I call "vibe coding", where you fully '
        "give in to the [vibes](https://e.com), embrace exponentials, and forget that the code even exists."
    )
    page = {"title": "Post by @karpathy on X", "author": "@karpathy", "content": content}
    monkeypatch.setattr(web_clipper, "run_defuddle", lambda url: page)

    path, created = clip_url("https://twitter.com/karpathy/status/1886192184808149383?s=20", tmp_path)
    title = '@karpathy on X: There\'s a new kind of coding I call "vibe coding", where you fully give in to…'
    assert created and path.name == sanitize_clip_filename(title) + ".md"
    assert f'source: "{POST}"' in path.read_text()

    again, created = clip_url(POST, tmp_path)
    assert not created and again == path


SAVED_PAGE = """<!doctype html><html><head><title>Quant | FT</title>
<link href="https://www.ft.com/content/bc6bba42" rel="canonical"></head><body>...</body></html>"""


def test_clip_html_uses_the_page_url_and_resolves_relative_links(tmp_path, monkeypatch):
    seen = {}

    def defuddle(source):
        seen["html"] = Path(source).read_text()
        return {"title": "The reclusive quant", "content": "Body"}

    monkeypatch.setattr(web_clipper, "run_defuddle", defuddle)
    page = tmp_path / "saved.html"
    page.write_text(SAVED_PAGE)
    clippings = tmp_path / "Clippings"

    path, created = clip_html(page, "https://giftarticle.ft.com/redeem/abc", clippings)
    assert created and path == clippings / "The reclusive quant.md"
    assert 'source: "https://www.ft.com/content/bc6bba42"' in path.read_text()
    assert '<head><base href="https://www.ft.com/content/bc6bba42"><title>' in seen["html"]
    assert clip_html(page, None, clippings) == (path, False)


def test_clip_html_falls_back_to_the_given_url_and_needs_one(tmp_path, monkeypatch):
    monkeypatch.setattr(web_clipper, "run_defuddle", lambda source: {"title": "T", "content": "Body"})
    page = tmp_path / "saved.html"
    page.write_text("<p>no head, no canonical</p>")
    with pytest.raises(ClipError, match="does not name its URL"):
        clip_html(page, None, tmp_path)
    path, _ = clip_html(page, "https://e.com/a", tmp_path)
    assert 'source: "https://e.com/a"' in path.read_text()


def test_clip_markdown_saves_web_clipper_notes_unchanged_and_once(tmp_path):
    note = '---\ntitle: "Quant"\nsource: "https://www.ft.com/content/bc6bba42?accessToken=x"\n---\nBody\n'
    upload = tmp_path / "upload" / "The reclusive quant: coming into the light.md"
    upload.parent.mkdir()
    upload.write_text(note)
    clippings = tmp_path / "Clippings"

    path, created = clip_file(upload, None, clippings)
    assert created and path == clippings / "The reclusive quant coming into the light.md"
    assert path.read_text() == note
    assert clip_file(upload, None, clippings) == (path, False)


def test_clip_file_rejects_other_files(tmp_path):
    with pytest.raises(ClipError, match="send a .html page or a .md note"):
        clip_file(tmp_path / "paper.pdf")
