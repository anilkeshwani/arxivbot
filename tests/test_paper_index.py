from arxivbot.paper_index import PaperIndex


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
