import re
import subprocess

import pytest

from arxivbot import telegram_bot
from arxivbot.telegram_bot import extract_links, git_commit, git_push, process_paper, route_message, run_item


def _utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


def _post(text, extra_entities=()):
    """A message with the url entities Telegram would attach (offsets in UTF-16 code units)."""
    url_re = r"(?:https?://|www\.)\S+?(?=[.,)]?(?:\s|$))|\b[a-z]+\.example\.com/\S+"
    entities = [
        {"type": "url", "offset": _utf16_len(text[: m.start()]), "length": _utf16_len(m.group(0))}
        for m in re.finditer(url_re, text)
    ]
    return {"text": text, "entities": entities + list(extra_entities)}


@pytest.mark.parametrize(
    ("text", "papers", "clips"),
    [
        ("https://arxiv.org/abs/2408.16532v2", [("2408.16532v2", "https://arxiv.org/abs/2408.16532v2")], []),
        ("2408.16532", [("2408.16532", None)], []),
        ("DOI:10.18653/v1/N18-3011", [("10.18653/v1/N18-3011", None)], []),
        ("2408.16532 and doi 10.1145/3776574.3831131", [("10.1145/3776574.3831131", None), ("2408.16532", None)], []),
        (
            "https://dl.acm.org/doi/10.1145/3776574.3831131",
            [("10.1145/3776574.3831131", "https://dl.acm.org/doi/10.1145/3776574.3831131")],
            [],
        ),
        ("https://huggingface.co/papers/2408.16532", [("2408.16532", "https://huggingface.co/papers/2408.16532")], []),
        (
            "Nice: https://blog.example.com/notes/2408.12345-review.",
            [],
            ["https://blog.example.com/notes/2408.12345-review"],
        ),
        ("see www.blog.example.com/2408.12345 now", [], ["https://www.blog.example.com/2408.12345"]),
        ("see blog.example.com/2408.12345", [], ["https://blog.example.com/2408.12345"]),
        (
            "https://arxiv.org/abs/1706.03762 https://doi.org/10.48550/arXiv.1706.03762 https://e.com/a",
            [("1706.03762", "https://arxiv.org/abs/1706.03762")],
            ["https://e.com/a"],
        ),
        ("🙂 https://e.com/after-emoji", [], ["https://e.com/after-emoji"]),
        ("just chatting", [], []),
    ],
)
def test_route_message(text, papers, clips):
    assert route_message(_post(text)) == (papers, clips)


def test_extract_links_reads_hyperlinked_text_and_drops_non_web_schemes():
    post = _post(
        "See this and him",
        extra_entities=[
            {"type": "text_link", "offset": 4, "length": 4, "url": "https://e.com/hidden"},
            {"type": "text_link", "offset": 13, "length": 3, "url": "tg://user?id=1"},
        ],
    )
    assert extract_links(post) == (["https://e.com/hidden"], "See this and him")


def test_route_message_reads_captions():
    post = {"caption": "https://e.com/page", "caption_entities": [{"type": "url", "offset": 0, "length": 18}]}
    assert route_message(post) == ([], ["https://e.com/page"])


# --- Git handling, against real repositories ---


def _run(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def vault(tmp_path, monkeypatch):
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "t")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "t@t")
    remote, vault = tmp_path / "remote.git", tmp_path / "vault"
    _run(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    _run(tmp_path, "clone", "-q", str(remote), str(vault))
    (vault / "Papers").mkdir()
    (vault / "Clippings").mkdir()
    (vault / ".papers.db").write_text("db")
    (vault / "Papers" / "Old.md").write_text("old")
    _run(vault, "add", "-A")
    _run(vault, "commit", "-qm", "init")
    _run(vault, "push", "-q", "origin", "HEAD:main")
    _run(vault, "branch", "-q", "-u", "origin/main")
    monkeypatch.setattr(telegram_bot, "OBSIDIAN_VAULT_DIR", vault)
    monkeypatch.setattr(telegram_bot, "PAPERS_DIR", vault / "Papers")
    monkeypatch.setattr(
        telegram_bot, "VAULT_WRITE_PATHS", (vault / "Papers", vault / ".papers.db", vault / "Clippings")
    )
    return vault


def _committed_files(vault):
    return set(_run(vault, "show", "--name-only", "--format=", "HEAD").splitlines())


def test_run_item_commits_only_what_the_item_wrote(vault):
    (vault / "Papers" / "Old.md").write_text("user edit")
    (vault / "Unrelated.md").write_text("staged by user")
    _run(vault, "add", "Unrelated.md")
    (vault / "Papers" / "[CLS] B.md").write_text("user's untracked note")
    (vault / ".papers.db").write_text("dirty before")

    def job():
        (vault / "Papers" / "[CLS] A.md").write_text("new")
        (vault / ".papers.db").write_text("dirty again")
        return "Imported", "Import A"

    assert run_item("A", job) == ("Imported", True)
    assert _committed_files(vault) == {"Papers/[CLS] A.md", ".papers.db"}
    assert "A  Unrelated.md" in _run(vault, "status", "--porcelain")


def test_run_item_commits_files_written_before_a_failure(vault):
    def job():
        (vault / "Clippings" / "Page.md").write_text("note")
        raise ConnectionError("Telegram unreachable")

    status, committed = run_item("https://e.com", job)
    assert committed and status == "Error processing https://e.com: Telegram unreachable"
    assert _committed_files(vault) == {"Clippings/Page.md"}


def test_git_push_rebases_and_aborts_on_conflict(vault, tmp_path):
    other = tmp_path / "other"
    _run(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    (other / ".papers.db").write_text("laptop")
    _run(other, "commit", "-qam", "laptop import")
    _run(other, "push", "-q")

    (vault / "Clippings" / "Page.md").write_text("note")
    assert git_commit([vault / "Clippings" / "Page.md"], "Clip page")
    assert git_push()  # rebased onto the laptop's commit

    _run(other, "pull", "-q")
    (other / ".papers.db").write_text("laptop again")
    _run(other, "commit", "-qam", "laptop import 2")
    _run(other, "push", "-q")
    (vault / ".papers.db").write_text("server")
    assert git_commit([vault / ".papers.db"], "server import")
    assert not git_push()
    assert not (vault / ".git" / "rebase-merge").exists()
    assert _run(vault, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


def test_process_paper_clips_the_link_when_the_paper_is_not_found(vault, monkeypatch):
    monkeypatch.setattr(telegram_bot, "get_paper_title", lambda db_path, **ids: None)
    monkeypatch.setattr(telegram_bot, "analysis_enabled", lambda: False)
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd[0] == "obsidian-import":  # finds nothing
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(telegram_bot, "clip_page", lambda url: (f"Clipped: {url}", "Clip"))
    url = "https://www.biorxiv.org/content/10.1101/2024.05.01.592000v1.full"
    assert process_paper("10.1101/2024.05.01.592000v1.full", url, "tok", 1, 2) == (f"Clipped: {url}", "Clip")
    assert process_paper("2408.16532", None, "tok", 1, 2) == ("Paper not found: 2408.16532", None)


def test_run_item_logs_clip_failures_without_a_traceback(vault, caplog):
    def job():
        raise telegram_bot.ClipError("Defuddle failed: 403 Forbidden")

    assert run_item("https://e.com", job) == ("Error processing https://e.com: Defuddle failed: 403 Forbidden", False)
    assert not caplog.records[-1].exc_info
