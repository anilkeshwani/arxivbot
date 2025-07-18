from __future__ import annotations

import logging
import re


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
    """Extracts and returns the first arXiv identifier-like string (inc. optional version) from a string."""
    if not arxiv_like:
        raise ValueError("Got empty string for arxiv_like.")

    # Regex for modern arXiv IDs, with optional version
    match = re.search(r"(\d{4}\.\d{4,5}(v\d+)?)", arxiv_like)
    if match:
        return match.group(1)
    else:
        raise ValueError("Could not find a valid arXiv identifier.")
