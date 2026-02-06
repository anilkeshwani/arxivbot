from arxivbot.find_arxiv_links import find_arxiv_links


class TestFindArxivLinks:
    def test_abs_url(self):
        assert find_arxiv_links("https://arxiv.org/abs/2301.12345") == ["2301.12345"]

    def test_pdf_url(self):
        assert find_arxiv_links("https://arxiv.org/pdf/2301.12345") == ["2301.12345"]

    def test_versioned_url(self):
        assert find_arxiv_links("https://arxiv.org/abs/2301.12345v3") == ["2301.12345v3"]

    def test_4_digit_id(self):
        assert find_arxiv_links("https://arxiv.org/abs/0704.0001") == ["0704.0001"]

    def test_multiple_links(self):
        text = "See https://arxiv.org/abs/2301.12345 and https://arxiv.org/pdf/2302.00001v2"
        assert find_arxiv_links(text) == ["2301.12345", "2302.00001v2"]

    def test_no_links(self):
        assert find_arxiv_links("No arxiv links here") == []

    def test_non_arxiv_url_ignored(self):
        assert find_arxiv_links("https://example.org/abs/2301.12345") == []
