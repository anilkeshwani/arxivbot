import threading

import pytest
import requests

from arxivbot import arxiv_api, obsidian_importer, s2_api
from arxivbot.arxiv_api import fetch_arxiv_papers
from arxivbot.database import init_db, paper_exists
from arxivbot.obsidian_importer import _normalize_paper, _process_paper
from arxivbot.s2_api import fetch_s2_batch


S2_PAPER = {
    "paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
    "title": "Attention is All you Need",
    "abstract": "The dominant sequence transduction models...",
    "authors": [{"authorId": "1", "name": "Ashish Vaswani"}, {"authorId": None, "name": None}],
    "year": 2017,
    "publicationDate": "2017-06-12",
    "venue": "NeurIPS",
    "externalIds": {"ArXiv": "1706.03762", "DOI": "10.48550/arXiv.1706.03762", "CorpusId": 13756489},
    "url": "https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776",
    "openAccessPdf": None,
    "tldr": {"model": "tldr@v2.0.0", "text": "A new architecture."},
    "fieldsOfStudy": None,
    "citationCount": 100,
    "influentialCitationCount": 10,
}


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(s2_api.time, "sleep", lambda _: None)


def test_fetch_s2_batch_splits_found_and_not_found():
    session = _Session(_Response(200, [S2_PAPER, None]))
    papers, not_found = fetch_s2_batch(["ARXIV:1706.03762", "ARXIV:0000.00000"], ["title"], "key", session=session)
    assert papers == [S2_PAPER]
    assert not_found == ["ARXIV:0000.00000"]
    assert session.calls[0]["json"] == {"ids": ["ARXIV:1706.03762", "ARXIV:0000.00000"]}
    assert session.calls[0]["headers"] == {"x-api-key": "key"}


def test_fetch_s2_batch_retries_rate_limits():
    session = _Session(_Response(429), _Response(503), _Response(200, [S2_PAPER]))
    assert fetch_s2_batch(["ARXIV:1706.03762"], ["title"], session=session) == ([S2_PAPER], [])
    assert len(session.calls) == 3


def test_fetch_s2_batch_raises_after_last_attempt():
    session = _Session(*[_Response(429)] * s2_api.S2_MAX_ATTEMPTS)
    with pytest.raises(requests.HTTPError):
        fetch_s2_batch(["ARXIV:1706.03762"], ["title"], session=session)


def test_fetch_s2_batch_does_not_retry_client_errors():
    session = _Session(_Response(400))
    with pytest.raises(requests.HTTPError):
        fetch_s2_batch(["bad"], ["title"], session=session)
    assert len(session.calls) == 1


def test_normalize_paper_from_s2_json():
    paper = _normalize_paper(S2_PAPER)
    assert paper["authors"] == ["Ashish Vaswani"]
    assert paper["publication_date"] == "2017-06-12"
    assert paper["tldr"] == "A new architecture."
    assert paper["fields_of_study"] == []
    assert paper["link"] == "https://arxiv.org/abs/1706.03762"
    assert paper["pdf_url"] == "https://arxiv.org/pdf/1706.03762"
    assert paper["open_access_pdf_url"] is None


def test_failed_note_write_leaves_no_db_row(tmp_path, monkeypatch):
    db_path = tmp_path / "papers.db"
    init_db(db_path)
    monkeypatch.setattr(obsidian_importer, "DB_PATH", db_path)

    def fail_write(**_):
        raise OSError("disk full")

    monkeypatch.setattr(obsidian_importer, "write_obsidian_paper", fail_write)
    with pytest.raises(OSError):
        _process_paper(_normalize_paper(S2_PAPER), download_pdf=False)
    assert not paper_exists(db_path, arxiv_id="1706.03762")


def test_main_exits_when_vault_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(obsidian_importer, "PAPERS_DIR", tmp_path / "missing_vault" / "Papers")
    monkeypatch.setattr(obsidian_importer, "DB_PATH", tmp_path / "missing_vault" / ".papers.db")
    monkeypatch.setattr("sys.argv", ["obsidian-import", "1706.03762", "--no_pdf"])
    with pytest.raises(SystemExit) as exit_info:
        obsidian_importer.main()
    assert exit_info.value.code == 1
    assert not (tmp_path / "missing_vault").exists()


ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All
      You Need</title>
    <summary>The dominant sequence transduction models.</summary>
    <author><name>Ashish Vaswani</name></author>
    <category term="cs.CL"/>
  </entry>
</feed>"""


class _ArxivResponse(_Response):
    def __init__(self, status_code, text):
        super().__init__(status_code)
        self.text = text


def test_fetch_arxiv_papers_parses_atom(monkeypatch):
    monkeypatch.setattr(arxiv_api.requests, "get", lambda *a, **k: _ArxivResponse(200, ARXIV_ATOM))
    [paper] = fetch_arxiv_papers(["1706.03762"])
    assert paper["paper_id"] == "arxiv:1706.03762"
    assert paper["title"] == "Attention Is All You Need"
    assert paper["publication_date"] == "2017-06-12"
    assert paper["link"] == "https://arxiv.org/abs/1706.03762"
    assert paper["fields_of_study"] == ["cs.CL"]


@pytest.mark.parametrize(
    ("response", "error"),
    [(_ArxivResponse(503, ""), requests.HTTPError), (_ArxivResponse(200, "<html>maintenance"), ValueError)],
)
def test_fetch_arxiv_papers_raises_on_failure(monkeypatch, response, error):
    monkeypatch.setattr(arxiv_api.requests, "get", lambda *a, **k: response)
    with pytest.raises(error):
        fetch_arxiv_papers(["1706.03762"])


def test_fetch_s2_batch_retries_connection_errors():
    class _FlakySession(_Session):
        def post(self, url, **kwargs):
            if not self.calls:
                self.calls.append(kwargs)
                raise requests.ConnectionError("reset")
            return super().post(url, **kwargs)

    session = _FlakySession(_Response(200, [S2_PAPER]))
    assert fetch_s2_batch(["ARXIV:1706.03762"], ["title"], session=session) == ([S2_PAPER], [])


def test_fetch_s2_batch_worst_case_fits_telegram_timeout(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(s2_api.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(s2_api.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    class _HangingSession:
        def post(self, url, timeout, **kwargs):
            clock[0] += sum(timeout)
            raise requests.Timeout("read timed out")

    with pytest.raises(requests.Timeout):
        fetch_s2_batch(["ARXIV:1706.03762"], ["title"], session=_HangingSession())
    # The bot kills obsidian-import at 120s, and the arXiv fallback (5s connect + 20s read) runs after S2 gives up
    assert clock[0] <= 120 - 25



def test_fetch_s2_batch_abandons_a_request_that_outlasts_its_attempt(monkeypatch):
    # Stands in for a server that keeps every socket wait under the read timeout but never finishes
    monkeypatch.setattr(s2_api, "S2_TIMEOUT", (0.05, 0.05))
    monkeypatch.setattr(s2_api, "S2_MAX_ATTEMPTS", 1)
    never = threading.Event()

    class _StalledSession:
        def post(self, url, **kwargs):
            never.wait()

    try:
        with pytest.raises(requests.Timeout):
            fetch_s2_batch(["ARXIV:1706.03762"], ["title"], session=_StalledSession())
    finally:
        never.set()
