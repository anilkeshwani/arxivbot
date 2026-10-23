from datetime import date
import subprocess

import pytest
import yaml

from arxivbot import web_clipper
from arxivbot.web_clipper import ClipError, build_clipping, clip_url, sanitize_clip_filename


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
