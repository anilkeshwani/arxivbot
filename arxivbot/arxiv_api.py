"""Paper metadata from the arXiv Atom API, for papers Semantic Scholar does not have."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from arxivbot.identifiers import extract_arxiv_id


LOGGER = logging.getLogger(__name__)

_ARXIV_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def fetch_arxiv_papers(arxiv_ids: list[str]) -> list[dict]:
    """Fetch paper metadata directly from the arXiv Atom API.

    Fallback for papers not found on Semantic Scholar. Returns normalized
    paper dicts compatible with _process_paper(). Uses a synthetic
    paper_id of the form "arxiv:{id}" since no S2 SHA is available.
    """
    if not arxiv_ids:
        return []

    id_list = ",".join(arxiv_ids)
    url = f"https://export.arxiv.org/api/query?id_list={id_list}&max_results={len(arxiv_ids)}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        LOGGER.error(f"arXiv API request failed: {e}")
        return []

    root = ET.fromstring(response.text)
    ns = _ARXIV_ATOM_NS
    papers: list[dict] = []

    for entry in root.findall("atom:entry", ns):
        title = " ".join(entry.findtext("atom:title", "", ns).split())
        if not title or title.lower() == "error":
            continue

        authors = [
            name.strip()
            for author in entry.findall("atom:author", ns)
            if (name := author.findtext("atom:name", "", ns).strip())
        ]

        abstract = " ".join(entry.findtext("atom:summary", "", ns).split())

        # Extract bare arXiv ID from entry <id> (e.g. "http://arxiv.org/abs/1904.05862v4")
        arxiv_id = extract_arxiv_id(entry.findtext("atom:id", "", ns)) or ""

        # Publication date
        pub_str = entry.findtext("atom:published", "", ns)
        pub_date = pub_str[:10] if pub_str and len(pub_str) >= 10 else None
        year = int(pub_date[:4]) if pub_date else None

        # Optional DOI from arXiv metadata
        doi = entry.findtext("arxiv:doi", None, ns)

        # arXiv categories
        categories = [cat.get("term", "") for cat in entry.findall("atom:category", ns) if cat.get("term")]

        papers.append(
            {
                "paper_id": f"arxiv:{arxiv_id}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "publication_date": pub_date,
                "year": year,
                "arxiv_id": arxiv_id,
                "doi": doi,
                "venue": "",
                "tldr": "",
                "s2_url": "",
                "fields_of_study": categories,
                "citation_count": 0,
                "influential_citation_count": 0,
                "link": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "open_access_pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            }
        )

    return papers
