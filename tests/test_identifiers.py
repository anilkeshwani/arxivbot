import pytest

from arxivbot.find_arxiv_links import find_arxiv_links
from arxivbot.identifiers import (
    clean_doi,
    dedup_keys,
    extract_arxiv_id,
    extract_doi,
    normalize_doi,
    normalize_title,
    parse_paper_id,
    same_paper,
    strip_arxiv_version,
)


S2_SHA = "ebdbded60f48131ed7ba73807c3c086993a96f89"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2408.16532", "ARXIV:2408.16532"),
        ("2408.16532v3", "ARXIV:2408.16532"),
        ("arXiv:2408.16532", "ARXIV:2408.16532"),
        ("https://arxiv.org/abs/2408.16532v2", "ARXIV:2408.16532"),
        ("https://arxiv.org/pdf/2408.16532", "ARXIV:2408.16532"),
        ("https://arxiv.org/html/2408.16532v1", "ARXIV:2408.16532"),
        ("10.48550/arXiv.2408.16532", "ARXIV:2408.16532"),
        ("DOI:10.48550/arXiv.2408.16532v2", "ARXIV:2408.16532"),
        ("https://doi.org/10.48550/arXiv.2408.16532", "ARXIV:2408.16532"),
        ("10.1109/ICASSP49357.2023.10095827", "DOI:10.1109/ICASSP49357.2023.10095827"),
        ("DOI:10.1145/3776574.3831131", "DOI:10.1145/3776574.3831131"),
        ("https://doi.org/10.1007/S00500-026-11448-Y", "DOI:10.1007/S00500-026-11448-Y"),
        ("CorpusId:215416146", "CorpusId:215416146"),
        (S2_SHA, S2_SHA),
        (S2_SHA.upper(), S2_SHA),
        (f"https://www.semanticscholar.org/paper/Some-Title/{S2_SHA}", S2_SHA),
        (f"https://www.semanticscholar.org/paper/{S2_SHA}", S2_SHA),
        ("  2408.16532  ", "ARXIV:2408.16532"),
        ("https://www.doi.org/10.1109/TASLP.2019.29151", "DOI:10.1109/TASLP.2019.29151"),
        ("doi.org/10.1109/TASLP.2019.29151", "DOI:10.1109/TASLP.2019.29151"),
        ("DOI: 10.1145/abc", "DOI:10.1145/abc"),
    ],
)
def test_parse_paper_id(raw, expected):
    assert parse_paper_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "not a paper", "https://ieeexplore.ieee.org/document/11722574"])
def test_parse_paper_id_rejects_unparseable(raw):
    with pytest.raises(ValueError):
        parse_paper_id(raw)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see https://arxiv.org/pdf/2609.14743v2 for details", "2609.14743"),
        ("arXiv preprint arXiv:2610.04651, 2026", "2610.04651"),
        ("https://ieeexplore.ieee.org/document/11720295/", None),
        ("10.1109/ICASSP49357.2023.10095827", None),
        ("version 1234.567 only has three digits", None),
    ],
)
def test_extract_arxiv_id(text, expected):
    assert extract_arxiv_id(text) == expected


def test_strip_arxiv_version():
    assert strip_arxiv_version("2109.00301v3") == "2109.00301"
    assert strip_arxiv_version("2109.00301") == "2109.00301"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1145/3776574.3831131", "10.1145/3776574.3831131"),
        ("DOI:10.1145/ABC", "10.1145/abc"),
        ("https://dx.doi.org/10.1145/ABC", "10.1145/abc"),
        ("10.1145/abc.", "10.1145/abc"),
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


def test_clean_doi_keeps_case():
    assert clean_doi("https://doi.org/10.1109/TASLP.2019.2915167.") == "10.1109/TASLP.2019.2915167"


def test_normalize_title_folds_case_accents_and_punctuation():
    assert normalize_title("  Café: A Study of Codecs!  ") == "cafe a study of codecs"
    assert normalize_title("GS-Codec: A Gaussian-Splatting Bottleneck") == normalize_title(
        "GS Codec - A Gaussian Splatting  bottleneck"
    )


def test_dedup_keys_order_and_normalization():
    keys = dedup_keys(s2_id=S2_SHA.upper(), arxiv_id="2408.16532v2", doi="10.1145/ABC", title="A Title.")
    assert keys == [f"s2:{S2_SHA}", "arxiv:2408.16532", "doi:10.1145/abc", "title:a title"]


def test_dedup_keys_skips_missing_and_empty_values():
    assert dedup_keys() == []
    assert dedup_keys(doi="", title="!!!") == []


def test_find_arxiv_links_keeps_versions():
    text = "arxiv.org/abs/2408.16532v2 and https://arxiv.org/pdf/2609.14743"
    assert find_arxiv_links(text) == ["2408.16532v2", "2609.14743"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://dl.acm.org/doi/abs/10.1145/3842436.3843815", "10.1145/3842436.3843815"),
        ("https://link.springer.com/article/10.1007/s10772-026-10296-3?af=R#sec1", "10.1007/s10772-026-10296-3"),
        ('<a href="https://doi.org/10.1145/abc">x</a>', "10.1145/abc"),
        ("https://ieeexplore.ieee.org/document/11735054", None),
    ],
)
def test_extract_doi(text, expected):
    assert extract_doi(text) == expected


def test_sici_dois_are_cut_at_angle_brackets():
    # Documented limitation: DOI_RE stops at "<" so DOIs come out of HTML cleanly
    assert extract_doi("10.1002/(SICI)1097-4636(199706)35:4<500::AID-JBM8>3.0.CO;2-P") != (
        "10.1002/(SICI)1097-4636(199706)35:4<500::AID-JBM8>3.0.CO;2-P"
    )


def test_dedup_keys_maps_arxiv_dois_to_arxiv_key():
    assert dedup_keys(doi="10.48550/arXiv.2408.16532") == ["arxiv:2408.16532", "doi:10.48550/arxiv.2408.16532"]


def test_same_paper_prefers_strong_keys_over_titles():
    preprint = dedup_keys(arxiv_id="2408.16532", title="Codec Paper")
    published = dedup_keys(doi="10.1109/X.1", title="Codec paper.")
    assert same_paper(preprint, published)  # only the title can decide
    assert same_paper(preprint, dedup_keys(arxiv_id="2408.16532v2", title="Renamed"))
    assert not same_paper(
        dedup_keys(s2_id="a" * 40, title="Introduction"), dedup_keys(s2_id="b" * 40, title="Introduction")
    )
    assert not same_paper(dedup_keys(title="One"), dedup_keys(title="Two"))
