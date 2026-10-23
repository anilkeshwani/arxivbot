from datetime import date

import pytest

from arxivbot import web_clipper
from arxivbot.web_clipper import ClipError, build_clipping, clip_url, resolve_relative_links, sanitize_clip_filename


URL = "https://www.speechmatics.com/company/articles-and-news/meet-oak"
PAGE = {
    "title": "Meet Oak: medical transcription",
    "author": "Sebastian Raschka, PhD",
    "published": "2026-10-14T10:14:53.528Z, 2026-10-14T00:00:00.000Z",
    "description": 'Oak is "first" for recall',
    "content": "Intro\n\n![fig](/_next/image?url=a.png)",
}


def test_build_clipping_matches_web_clipper_template():
    title, note = build_clipping(URL, PAGE, date(2026, 10, 21))
    assert title == "Meet Oak: medical transcription"
    assert note == (
        "---\n"
        'title: "Meet Oak: medical transcription"\n'
        f'source: "{URL}"\n'
        "author:\n"
        '  - "[[Sebastian Raschka]]"\n'
        '  - "[[PhD]]"\n'
        "published: 2026-10-14\n"
        "created: 2026-10-21\n"
        'description: "Oak is \\"first\\" for recall"\n'
        "tags:\n"
        '  - "clippings"\n'
        "---\n"
        "Intro\n\n![fig](https://www.speechmatics.com/_next/image?url=a.png)\n"
    )


def test_build_clipping_leaves_missing_fields_empty():
    _, note = build_clipping(URL, {"content": "Body"}, date(2026, 10, 21))
    assert f'title: "{URL}"' in note
    assert "author:\npublished:\ncreated: 2026-10-21\ndescription:\ntags:" in note


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Meet Oak: medical transcription", "Meet Oak medical transcription"),
        ("A/B testing? [Part #1] | Blog", "AB testing Part 1 Blog"),
        ("  Trailing dots...  ", "Trailing dots"),
        (":::", "Untitled"),
    ],
)
def test_sanitize_clip_filename(title, expected):
    assert sanitize_clip_filename(title) == expected


def test_resolve_relative_links_keeps_absolute_and_anchor_links():
    md = "[a](/x) [b](../y.png) [c](https://e.com/z) [d](#sec) [e](mailto:a@b.c) [f](//cdn.e.com/i.png)"
    assert resolve_relative_links(md, "https://site.org/blog/post") == (
        "[a](https://site.org/x) [b](https://site.org/y.png) [c](https://e.com/z) [d](#sec) "
        "[e](mailto:a@b.c) [f](https://cdn.e.com/i.png)"
    )


def test_clip_url_writes_note_and_skips_reclip(tmp_path, monkeypatch):
    monkeypatch.setattr(web_clipper, "run_defuddle", lambda url: PAGE)
    path, created = clip_url(URL, tmp_path, created=date(2026, 10, 21))
    assert created and path == tmp_path / "Meet Oak medical transcription.md"

    again, created = clip_url(URL, tmp_path)
    assert not created and again == path

    other, created = clip_url("https://other.example/meet-oak", tmp_path)
    assert created and other == tmp_path / "Meet Oak medical transcription 2.md"


def test_clip_url_rejects_empty_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(web_clipper, "run_defuddle", lambda url: {"title": "Login", "content": "  "})
    with pytest.raises(ClipError):
        clip_url(URL, tmp_path)
    assert not list(tmp_path.iterdir())
