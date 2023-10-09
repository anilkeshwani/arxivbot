from __future__ import annotations

import logging
from urllib.parse import urlparse


# TODO is this best practice?
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(logging.StreamHandler())


def inflect_day(day: int):
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    return str(day) + suffix


def canonicalise_arxiv(arxiv_like: str) -> str:
    """
    Convert arXiv IDs and URLs to canonical-ish form usable by search_arxiv.

    Handles cases like:
    - arXiv:1905.00001
    - https://arxiv.org/abs/1905.00001
    - https://arxiv.org/pdf/1905.00001.pdf
    - https://arxiv.org/abs/1905.00001v1
    - https://arxiv.org/pdf/1905.00001v1.pdf
    - moz-extension://cf2764a6-e6bc-4c15-93f7-ff7531c62f1c/pdfviewer.html?target=https://arxiv.org/pdf/2204.03067.pdf
    """
    if arxiv_like == "":
        raise ValueError("Got empty string for arxiv_like.")
    if arxiv_like.startswith("moz-extension"):
        arxiv_like = urlparse(arxiv_like).query.split("=")[-1]
    if arxiv_like.startswith("arXiv:"):
        arxiv_like = arxiv_like[6:]
    if arxiv_like.startswith("http"):
        urlparse_result = urlparse(arxiv_like)
        if not urlparse_result.netloc == "arxiv.org":
            raise ValueError("URL does not point to arXiv")
        return urlparse_result.path.strip("/").split("/")[-1].strip(".pdf")
    else:
        return arxiv_like.strip()
