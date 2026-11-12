import json
import os
from pathlib import Path

import pytest

from arxivbot import paper_index
from arxivbot.paper_index import PaperIndex, default_cache_path


def _note(papers_dir, name, frontmatter):
    path = papers_dir / f"{name}.md"
    path.write_text(f"---\n{frontmatter}\n---\n\nBody with a line of its own:\n---\n")
    return path


def test_finds_a_note_by_any_of_its_ids(tmp_path):
    path = _note(
        tmp_path,
        "Coding Speech",
        "title: Coding Speech Through Vocal Tract Kinematics\n"
        "doi: 10.1109/JSTSP.2024.3497655\n"
        "arxiv_id: '2406.12998v2'\n"
        "s2_paper_id: 5D659C7F2B08A4F3E0C5DEDF89D5B015581193AC",
    )
    index = PaperIndex.build(tmp_path)
    for ids in (
        {"paper_id": "5d659c7f2b08a4f3e0c5dedf89d5b015581193ac"},
        {"arxiv_id": "2406.12998"},
        {"arxiv_id": "2406.12998v5"},
        {"doi": "10.1109/jstsp.2024.3497655"},
        {"doi": "https://doi.org/10.1109/JSTSP.2024.3497655"},
    ):
        found = index.find(**ids)
        assert found is not None and found.path == path, ids
        assert found.title == "Coding Speech Through Vocal Tract Kinematics"
    assert index.find(doi="10.1109/other") is None
    assert index.find() is None


def test_takes_the_arxiv_id_from_the_link_when_the_field_is_missing(tmp_path):
    _note(tmp_path, "Old", "link: https://arxiv.org/abs/1706.03762v7")
    index = PaperIndex.build(tmp_path)
    assert index.find(arxiv_id="1706.03762").title == "Old"
    assert index.arxiv_paths() == {"1706.03762": tmp_path / "Old.md"}


def test_unquoted_arxiv_id_keeps_its_trailing_zero(tmp_path):
    _note(tmp_path, "Unquoted", "arxiv_id: 2406.12990")
    assert PaperIndex.build(tmp_path).find(arxiv_id="2406.12990") is not None


def test_empty_and_null_ids_are_not_indexed(tmp_path):
    _note(tmp_path, "Blank", "doi: ''\narxiv_id: null\ns2_paper_id: ~")
    index = PaperIndex.build(tmp_path)
    assert not (index.by_doi or index.by_arxiv_id or index.by_s2_id)


def test_skips_notes_without_readable_frontmatter(tmp_path):
    (tmp_path / "Plain.md").write_text("no frontmatter, doi: 10.1/x")
    (tmp_path / "Broken.md").write_text("---\ndoi: [unclosed\n---\n")
    (tmp_path / "List.md").write_text("---\n- a\n- b\n---\n")
    _note(tmp_path, "Good", "doi: 10.1/x")
    assert PaperIndex.build(tmp_path).find(doi="10.1/x").title == "Good"


def test_first_note_in_name_order_wins_a_shared_id(tmp_path):
    _note(tmp_path, "B", "doi: 10.1/x")
    _note(tmp_path, "A", "doi: 10.1/x")
    assert PaperIndex.build(tmp_path).find(doi="10.1/x").title == "A"


def _build_without_reading(papers_dir):
    """Build the index, failing if any note is read from disk."""
    def fail(note):
        raise AssertionError(f"read {note.name} again")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(paper_index, "_read_fields", fail)
        return PaperIndex.build(papers_dir)


def test_cache_spares_rereading_unchanged_notes(tmp_path):
    _note(tmp_path, "A", "doi: 10.1/a\narxiv_id: '2406.12990'")
    first = PaperIndex.build(tmp_path)
    assert default_cache_path(tmp_path).exists()
    second = _build_without_reading(tmp_path)
    assert second == first
    assert second.find(arxiv_id="2406.12990").title == "A"


def test_cache_follows_added_changed_and_deleted_notes(tmp_path):
    a = _note(tmp_path, "A", "doi: 10.1/a")
    b = _note(tmp_path, "B", "doi: 10.1/b")
    PaperIndex.build(tmp_path)
    a.write_text("---\ndoi: 10.1/a-changed\n---\n")
    os.utime(a, ns=(a.stat().st_atime_ns, a.stat().st_mtime_ns + 1_000_000))
    b.unlink()
    _note(tmp_path, "C", "doi: 10.1/c")
    index = PaperIndex.build(tmp_path)
    assert index.find(doi="10.1/a") is None
    assert index.find(doi="10.1/a-changed").title == "A"
    assert index.find(doi="10.1/b") is None
    assert index.find(doi="10.1/c").title == "C"
    assert set(json.loads(default_cache_path(tmp_path).read_text())["notes"]) == {"A.md", "C.md"}


def test_cache_is_rebuilt_when_unusable(tmp_path):
    _note(tmp_path, "A", "doi: 10.1/a")
    cache = default_cache_path(tmp_path)
    for content in ("not json", json.dumps({"version": -1, "notes": {}}), json.dumps([1, 2])):
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(content)
        assert PaperIndex.build(tmp_path).find(doi="10.1/a").title == "A"
        assert json.loads(cache.read_text())["version"] == paper_index._CACHE_VERSION


def test_cache_of_another_papers_folder_is_not_used(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    for folder, doi in ((first, "10.1/one"), (second, "10.1/two")):
        folder.mkdir()
        _note(folder, "Same", f"doi: {doi}")
    shared = tmp_path / "shared.json"
    PaperIndex.build(first, shared)
    assert PaperIndex.build(second, shared).find(doi="10.1/two") is not None


def test_works_when_the_cache_cannot_be_written(tmp_path, caplog):
    _note(tmp_path, "A", "doi: 10.1/a")
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert PaperIndex.build(tmp_path, blocker / "sub" / "index.json").find(doi="10.1/a").title == "A"
    assert "Could not save the paper index" in caplog.text


def test_a_note_that_cannot_be_read_is_tried_again_next_time(tmp_path):
    _note(tmp_path, "A", "doi: 10.1/a")
    real_read_text = Path.read_text

    def flaky(self, *args, **kwargs):
        if self.name == "A.md":
            raise PermissionError("busy")
        return real_read_text(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "read_text", flaky)
        assert PaperIndex.build(tmp_path).find(doi="10.1/a") is None
    assert PaperIndex.build(tmp_path).find(doi="10.1/a").title == "A"


def test_a_note_rewritten_with_its_old_mtime_and_size_is_read_again(tmp_path):
    note = _note(tmp_path, "A", "doi: 10.1/aaaa")
    PaperIndex.build(tmp_path)
    before = note.stat()
    note.write_text(note.read_text().replace("aaaa", "bbbb"))
    os.utime(note, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert note.stat().st_size == before.st_size
    index = PaperIndex.build(tmp_path)
    assert index.find(doi="10.1/bbbb") is not None
    assert index.find(doi="10.1/aaaa") is None


def test_an_interrupted_save_leaves_no_temporary_file(tmp_path):
    _note(tmp_path, "A", "doi: 10.1/a")
    cache = tmp_path / "cache" / "index.json"

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(paper_index.json, "dump", interrupt)
        with pytest.raises(KeyboardInterrupt):
            PaperIndex.build(tmp_path, cache)
    assert list(cache.parent.iterdir()) == []
