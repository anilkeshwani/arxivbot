from datetime import date

from arxivbot.clip_queue import ClipQueue


DAY = date(2026, 11, 4)


def _queue(tmp_path):
    return ClipQueue(tmp_path / ".clip-queue.json", tmp_path / "Clip Queue.md")


def test_a_page_is_queued_once_and_matched_by_its_link_or_where_it_redirects(tmp_path):
    queue = _queue(tmp_path)
    resolved = "https://www.ft.com/content/abc?accessToken=x"
    assert queue.add("https://giftarticle.ft.com/redeem/abc", "403 Forbidden", DAY, resolved)
    assert not queue.add("https://giftarticle.ft.com/redeem/abc/", "403 Forbidden", DAY)
    assert queue.find("https://ft.com/content/abc")  # the redirect's token is ignored
    assert not queue.find("https://www.ft.com/content/abd")

    queue.add("https://twitter.com/a/status/1?s=20", "403 Forbidden", DAY)
    assert queue.remove("https://x.com/a/status/1")
    assert len(queue) == 1


def test_query_strings_tell_pages_apart_for_posted_links(tmp_path):
    queue = _queue(tmp_path)
    queue.add("https://www.youtube.com/watch?v=A", "429", DAY)
    assert not queue.find("https://www.youtube.com/watch?v=B")


def test_save_writes_the_queue_and_its_note_and_reloads(tmp_path):
    queue = _queue(tmp_path)
    queue.save()
    assert (tmp_path / "Clip Queue.md").read_text().endswith("Nothing to clip.\n")
    queue.add("https://e.com/a", "403 Forbidden", DAY)
    queue.save()
    assert "- <https://e.com/a> (posted 2026-11-04: 403 Forbidden)\n" in (tmp_path / "Clip Queue.md").read_text()
    assert _queue(tmp_path).pages == [{"url": "https://e.com/a", "posted": "2026-11-04", "reason": "403 Forbidden"}]


def test_remove_clipped_takes_off_pages_with_a_clipping(tmp_path):
    clippings = tmp_path / "Clippings"
    clippings.mkdir()
    (clippings / "A.md").write_text('---\ntitle: "A"\nsource: "https://e.com/a"\n---\nBody\n')
    queue = _queue(tmp_path)
    queue.add("https://www.e.com/a/", "403 Forbidden", DAY)
    queue.add("https://e.com/b", "403 Forbidden", DAY)
    assert [page["url"] for page in queue.remove_clipped(clippings)] == ["https://www.e.com/a/"]
    assert [page["url"] for page in queue.pages] == ["https://e.com/b"]
