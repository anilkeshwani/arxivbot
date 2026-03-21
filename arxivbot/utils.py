from __future__ import annotations

import logging
import re


LOGGER = logging.getLogger(__name__)


def inflect_day(day: int):
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    return str(day) + suffix


def canonicalise_arxiv(arxiv_like: str) -> str:
    """Extracts and returns the first arXiv identifier-like string (inc. optional version) from a string."""
    if not arxiv_like:
        raise ValueError("Got empty string for arxiv_like.")

    # Regex for modern arXiv IDs, with optional version
    match = re.search(r"(\d{4}\.\d{4,5}(v\d+)?)", arxiv_like)
    if match:
        return match.group(1)
    else:
        raise ValueError("Could not find a valid arXiv identifier.")


def parse_paper_id(input_str: str) -> str:
    """Convert user input (arXiv ID, arXiv URL, S2 URL, S2 SHA, DOI) to S2 API paper_id format.

    Returns a string suitable for the S2 API paper lookup endpoint, e.g.:
    - "ARXIV:2408.16532" for arXiv inputs
    - "ebdbded60f48131ed7ba73807c3c086993a96f89" for S2 SHA inputs
    - "DOI:10.1234/foo" for DOI inputs
    """
    input_str = input_str.strip()
    if not input_str:
        raise ValueError("Got empty string for paper identifier.")

    # S2 URL: https://www.semanticscholar.org/paper/<optional-slug>/<40-hex-sha>
    s2_url_match = re.search(r"semanticscholar\.org/paper/(?:.+/)?([0-9a-f]{40})", input_str, re.IGNORECASE)
    if s2_url_match:
        return s2_url_match.group(1)

    # Explicit prefix formats — check before arXiv regex to avoid false matches
    # (e.g. "DOI:10.48550/arXiv.2408.16532" contains an arXiv-like substring)
    if input_str.upper().startswith("DOI:"):
        doi = re.sub(r"(?i)^doi:", "", input_str)
        return f"DOI:{doi}"

    if input_str.upper().startswith("CORPUSID:"):
        return input_str

    # arXiv URL or bare arXiv ID: extract the numeric ID, strip version
    arxiv_match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", input_str)
    if arxiv_match:
        return f"ARXIV:{arxiv_match.group(1)}"

    # 40-character hex string: S2 paperId
    if re.fullmatch(r"[0-9a-f]{40}", input_str, re.IGNORECASE):
        return input_str

    # Bare DOI (starts with 10.)
    if input_str.startswith("10."):
        return f"DOI:{input_str}"

    raise ValueError(f"Could not parse paper identifier: {input_str!r}")
