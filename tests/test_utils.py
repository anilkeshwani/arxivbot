import pytest

from arxivbot.utils import canonicalise_arxiv, inflect_day


class TestInflectDay:
    def test_st_suffixes(self):
        assert inflect_day(1) == "1st"
        assert inflect_day(21) == "21st"
        assert inflect_day(31) == "31st"

    def test_nd_suffixes(self):
        assert inflect_day(2) == "2nd"
        assert inflect_day(22) == "22nd"

    def test_rd_suffixes(self):
        assert inflect_day(3) == "3rd"
        assert inflect_day(23) == "23rd"

    def test_th_suffixes(self):
        for day in [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 24, 25, 26, 27, 28, 29, 30]:
            assert inflect_day(day) == f"{day}th"


class TestCanonicaliseArxiv:
    def test_bare_id_5_digit(self):
        assert canonicalise_arxiv("2301.12345") == "2301.12345"

    def test_bare_id_4_digit(self):
        assert canonicalise_arxiv("0704.0001") == "0704.0001"

    def test_id_with_version(self):
        assert canonicalise_arxiv("2301.12345v2") == "2301.12345v2"

    def test_abs_url(self):
        assert canonicalise_arxiv("https://arxiv.org/abs/2301.12345") == "2301.12345"

    def test_pdf_url(self):
        assert canonicalise_arxiv("https://arxiv.org/pdf/2301.12345v1") == "2301.12345v1"

    def test_url_with_trailing_text(self):
        assert canonicalise_arxiv("https://arxiv.org/abs/2301.12345v2 some text") == "2301.12345v2"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty string"):
            canonicalise_arxiv("")

    def test_no_match_raises(self):
        with pytest.raises(ValueError, match="Could not find"):
            canonicalise_arxiv("not-an-arxiv-id")

    def test_old_format_4_digit(self):
        assert canonicalise_arxiv("1501.0001") == "1501.0001"
