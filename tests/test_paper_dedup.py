import pytest

from arxivbot.obsidian_importer import _drop_duplicate_papers
from arxivbot.telegram_bot import extract_paper_ids


def _paper(paper_id, arxiv_id=None, doi=None, title="T"):
    return {"paper_id": paper_id, "arxiv_id": arxiv_id, "doi": doi, "title": title}


def test_drop_duplicate_papers_keeps_first_of_shared_keys():
    first = _paper("a" * 40, arxiv_id="2408.16532", title="first")
    same_arxiv = _paper("b" * 40, arxiv_id="2408.16532v2", title="second")
    fallback = _paper("arxiv:2408.16532", arxiv_id="2408.16532", title="arxiv fallback")
    other = _paper("c" * 40, doi="10.1145/ABC", title="other")
    same_doi = _paper("d" * 40, doi="10.1145/abc", title="other again")
    assert _drop_duplicate_papers([first, same_arxiv, fallback, other, same_doi]) == [first, other]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("check https://arxiv.org/abs/2408.16532v2", ["2408.16532v2"]),
        ("arxiv.org/abs/2408.16532 and https://doi.org/10.48550/arXiv.2408.16532", ["2408.16532"]),
        ("2408.16532 and 2501.00001v1", ["2408.16532", "2501.00001v1"]),
        ("arXiv:2408.16532", ["2408.16532"]),
        ('<a href="https://doi.org/10.1145/abc">paper</a>', ["10.1145/abc"]),
        ("no ids here", []),
    ],
)
def test_extract_paper_ids(text, expected):
    assert extract_paper_ids(text) == expected
