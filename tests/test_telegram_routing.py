import pytest

from arxivbot.telegram_bot import changed_paths, extract_links, route_message


def _post(text, entities=None):
    return {"chat": {"id": -100123}, "message_id": 7, "text": text, "entities": entities or []}


@pytest.mark.parametrize(
    ("text", "papers", "clips"),
    [
        ("https://arxiv.org/abs/2408.16532v2", ["2408.16532v2"], []),
        ("2408.16532", ["2408.16532"], []),
        ("DOI:10.18653/v1/N18-3011", ["10.18653/v1/N18-3011"], []),
        ("https://dl.acm.org/doi/10.1145/3776574.3831131", ["10.1145/3776574.3831131"], []),
        ("https://huggingface.co/papers/2408.16532", ["2408.16532"], []),
        (
            "Nice post: https://blog.example.com/notes/2408.12345-review.",
            [],
            ["https://blog.example.com/notes/2408.12345-review"],
        ),
        (
            "https://arxiv.org/abs/1706.03762 and https://huggingface.co/papers/2408.16532 and https://e.com/a",
            ["1706.03762", "2408.16532"],
            ["https://e.com/a"],
        ),
        ("https://arxiv.org/abs/1706.03762 https://doi.org/10.48550/arXiv.1706.03762", ["1706.03762"], []),
        ("just chatting", [], []),
    ],
)
def test_route_message(text, papers, clips):
    assert route_message(_post(text)) == (papers, clips)


def test_extract_links_reads_hyperlinked_text_and_keeps_balanced_parens():
    post = _post(
        "See (https://en.wikipedia.org/wiki/Mercury_(planet)) and this",
        entities=[{"type": "text_link", "offset": 56, "length": 4, "url": "https://e.com/hidden"}],
    )
    assert extract_links(post) == ["https://en.wikipedia.org/wiki/Mercury_(planet)", "https://e.com/hidden"]


def test_route_message_reads_captions():
    post = {"chat": {"id": 1}, "caption": "https://e.com/page", "caption_entities": []}
    assert route_message(post) == ([], ["https://e.com/page"])


def test_changed_paths_ignores_entries_dirty_before():
    before = {" M Papers/Old.md"}
    after = {" M Papers/Old.md", "?? Papers/New.md", " M .papers.db"}
    assert changed_paths(before, after) == [".papers.db", "Papers/New.md"]
