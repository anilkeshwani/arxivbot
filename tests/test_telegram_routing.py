import re
import subprocess
from functools import partial

import pytest

from arxivbot import clip_queue, telegram_bot
from arxivbot.clip_queue import ClipQueue
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
    queue_path, queue_note = vault / ".clip-queue.json", vault / "Clip Queue.md"
    for module in (telegram_bot, clip_queue):
        monkeypatch.setattr(module, "CLIP_QUEUE_PATH", queue_path)
        monkeypatch.setattr(module, "CLIP_QUEUE_NOTE", queue_note)
    monkeypatch.setattr(telegram_bot, "CLIPPINGS_DIR", vault / "Clippings")
    monkeypatch.setattr(telegram_bot, "QUEUE_MESSAGES_PATH", tmp_path / "state" / "queue-messages.json")
    monkeypatch.setattr(
        telegram_bot,
        "VAULT_WRITE_PATHS",
        (vault / "Papers", vault / ".papers.db", vault / "Clippings", queue_path, queue_note),
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


def test_analysis_prompt_asks_for_the_vault_summary_header():
    prompt = telegram_bot.ANALYSIS_PROMPT.format(pdf_path="p.pdf", figure_instructions="", today="2026-10-24", br="  ")
    assert "## <Opinionated and Captivating Summary Title> <Model Name>" in prompt
    assert "> [!info] #llm-generated/<your model ID, e.g. claude-opus-4-6>  \n> Date: 2026-10-24  \n" in prompt
    assert "> Source: Claude Code CLI  \n" in prompt


def test_a_posted_file_is_downloaded_and_clipped_with_the_caption_link(vault, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **kw: sent.append(a[2]) or 9)
    monkeypatch.setattr(telegram_bot, "edit_message", lambda token, chat, msg, text: sent.append(text))
    monkeypatch.setattr(telegram_bot, "git_push", lambda: True)
    monkeypatch.setattr(telegram_bot, "telegram_api", lambda token, method, **kw: {"result": {"file_path": "d/1.html"}})
    monkeypatch.setattr(
        telegram_bot.requests,
        "get",
        lambda url, **kw: type("R", (), {"content": b"<p>x</p>", "raise_for_status": lambda s: None})(),
    )
    calls = []

    def clip_file(path, url):
        calls.append((path.name, path.read_bytes(), url))
        note = vault / "Clippings" / "Quant.md"
        note.write_text("note")
        return note, True

    monkeypatch.setattr(telegram_bot, "clip_file", clip_file)
    post = _post("https://giftarticle.ft.com/redeem/abc")
    post.update(chat={"id": 1}, message_id=5, caption=post.pop("text"), caption_entities=post.pop("entities"))
    post["document"] = {"file_id": "f1", "file_name": "The quant.html"}

    telegram_bot.handle_message("tok", {1}, post)

    assert calls == [("The quant.html", b"<p>x</p>", "https://giftarticle.ft.com/redeem/abc")]
    assert sent == ["Processing 1 item(s)...", "Clipped: Quant"]
    assert _committed_files(vault) == {"Clippings/Quant.md"}


def test_a_failed_file_download_does_not_reveal_the_token(monkeypatch):
    def api(token, method, **kw):
        raise telegram_bot.requests.HTTPError(f"400 for url: https://api.telegram.org/bot{token}/getFile")

    monkeypatch.setattr(telegram_bot, "telegram_api", api)
    with pytest.raises(telegram_bot.ClipError) as info:
        telegram_bot.clip_document("SECRET", {"file_id": "f", "file_name": "big.html"}, None)
    assert "SECRET" not in str(info.value)


def _blocked(url, wayback=False):
    raise telegram_bot.NeedsBrowserError("Defuddle failed: Error: Failed to fetch: 403 Forbidden", "403 Forbidden")


GIFT = "https://giftarticle.ft.com/redeem/abc"


def test_a_blocked_page_with_no_snapshot_from_today_is_queued(vault, monkeypatch):
    monkeypatch.setattr(telegram_bot, "clip_url", _blocked)
    monkeypatch.setattr(telegram_bot, "clip_wayback", lambda url, clippings_dir, today: None)
    monkeypatch.setattr(telegram_bot, "final_url", lambda url: "https://www.ft.com/content/abc?accessToken=x")

    status, committed = run_item(GIFT, partial(telegram_bot.clip_page, GIFT))
    assert committed and status.endswith("Added to the clip queue (1 waiting).")
    assert "403 Forbidden" in status
    assert _committed_files(vault) == {".clip-queue.json", "Clip Queue.md"}
    assert f"- <{GIFT}> (posted " in (vault / "Clip Queue.md").read_text()

    assert run_item(GIFT, partial(telegram_bot.clip_page, GIFT)) == (f"Already in the clip queue: {GIFT}", False)


def test_a_blocked_page_is_clipped_from_a_snapshot_taken_today(vault, monkeypatch):
    note = vault / "Clippings" / "Deepgram.md"

    def wayback(url, clippings_dir, today):
        note.write_text('---\nsource: "https://www.daily.co/blog/deepgram/"\n---\nBody\n')
        return note, True

    monkeypatch.setattr(telegram_bot, "clip_url", _blocked)
    monkeypatch.setattr(telegram_bot, "clip_wayback", wayback)
    status, committed = run_item("u", partial(telegram_bot.clip_page, "https://www.daily.co/blog/deepgram/"))
    assert (status, committed) == ("Clipped from a Wayback Machine snapshot: Deepgram", True)
    assert "Wayback Machine" in _run(vault, "log", "-1", "--format=%s")
    assert not ClipQueue()


def test_a_page_clipped_elsewhere_leaves_the_queue_after_a_pull(vault, tmp_path, monkeypatch):
    queue = ClipQueue()
    queue.add(GIFT, "403 Forbidden", telegram_bot.date(2026, 11, 4), "https://www.ft.com/content/abc?accessToken=x")
    queue.add("https://e.com/keep", "timed out", telegram_bot.date(2026, 11, 4))
    queue.save()
    assert git_commit([vault / ".clip-queue.json", vault / "Clip Queue.md"], "queue") and git_push()

    laptop = tmp_path / "laptop"
    _run(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(laptop))
    (laptop / "Clippings").mkdir()  # empty in the fixture, so not in the clone
    (laptop / "Clippings" / "Quant.md").write_text(
        '---\ntitle: "Quant"\nsource: "https://www.ft.com/content/abc"\n---\n'
    )
    _run(laptop, "add", "-A")
    _run(laptop, "commit", "-qm", "Web Clipper")
    _run(laptop, "push", "-q")

    shown = []
    monkeypatch.setattr(telegram_bot, "show_queue", lambda token, chats: shown.append(len(ClipQueue())))
    telegram_bot.refresh_queue("tok", {1})
    assert [page["url"] for page in ClipQueue().pages] == ["https://e.com/keep"]
    assert shown == [1]
    assert _run(vault, "status", "--porcelain", "-b").startswith("## main...origin/main\n")


def test_done_drops_a_page_by_number_and_the_pinned_list_follows(vault, monkeypatch):
    queue = ClipQueue()
    for url in ("https://e.com/a", "https://e.com/b"):
        queue.add(url, "403 Forbidden", telegram_bot.date(2026, 11, 4))
    queue.save()
    calls, sent = [], []
    monkeypatch.setattr(telegram_bot, "git_push", lambda: True)
    monkeypatch.setattr(telegram_bot, "send_message", lambda token, chat, text, reply_to=None: sent.append(text) or 7)
    monkeypatch.setattr(telegram_bot, "telegram_api", lambda token, method, **kw: calls.append((method, kw["json"])))

    telegram_bot.handle_message("tok", {1}, {"chat": {"id": 1}, "message_id": 5, "text": "/done@vault_bot 1"})

    assert sent[0] == "Dropped https://e.com/a from the clip queue."
    assert "1. https://e.com/b (403 Forbidden, posted 2026-11-04)" in sent[1]
    assert calls == [("pinChatMessage", {"chat_id": 1, "message_id": 7, "disable_notification": True})]
    assert _run(vault, "log", "-1", "--format=%s").strip() == 'Drop "https://e.com/a" from the clip queue'

    telegram_bot.show_queue("tok", {1})  # later changes edit the pinned message
    assert calls[-1][0] == "editMessageText" and calls[-1][1]["message_id"] == 7

