"""Canonical paper identifiers and the keys used to deduplicate papers.

Importing this module loads only the standard library. Installing arxivbot
still installs all of its dependencies.
"""

from __future__ import annotations

import re
import unicodedata


__all__ = [
    "clean_doi",
    "dedup_keys",
    "extract_arxiv_id",
    "extract_doi",
    "normalize_doi",
    "normalize_title",
    "parse_paper_id",
    "same_paper",
    "strip_arxiv_version",
]

# Modern arXiv IDs (YYMM.NNNNN, since 2007), with optional version suffix.
# The lookarounds stop matches inside longer digit runs, such as the
# "2023.10095" inside the DOI 10.1109/ICASSP49357.2023.10095827.
ARXIV_ID_RE = re.compile(r"(?<!\d)(?<!\d\.)(\d{4}\.\d{4,5})(v\d+)?(?!\d)")
ARXIV_URL_RE = re.compile(r"(?:https?://)?(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5}(?:v\d+)?)")
S2_URL_RE = re.compile(r"semanticscholar\.org/paper/(?:[^/\s]+/)?([0-9a-f]{40})", re.IGNORECASE)
# Stops at quotes and angle brackets so DOIs come out of HTML cleanly. Legacy
# SICI DOIs, which contain "<" and ">", are therefore not supported.
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)")

_DOI_PREFIX_RE = re.compile(r"^(?:doi:\s*|(?:https?://)?(?:www\.|dx\.)?doi\.org/)", re.IGNORECASE)
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(\d{4}\.\d{4,5})(?:v\d+)?$", re.IGNORECASE)
_DOI_TRAILING_PUNCT = ".,;:)]}>'\""
_STRONG_KEY_NAMESPACES = ("s2", "arxiv", "doi")


def strip_arxiv_version(arxiv_id: str) -> str:
    """'2109.00301v3' -> '2109.00301'."""
    return re.sub(r"v\d+$", "", arxiv_id)


def extract_arxiv_id(text: str) -> str | None:
    """Return the first modern arXiv ID in `text`, without its version, or None."""
    match = ARXIV_ID_RE.search(text)
    return match.group(1) if match else None


def clean_doi(doi: str) -> str:
    """Strip a 'doi:' or doi.org prefix and trailing punctuation, keeping the original case."""
    return _DOI_PREFIX_RE.sub("", doi.strip()).strip().rstrip(_DOI_TRAILING_PUNCT)


def normalize_doi(doi: str) -> str:
    """Comparison key for a DOI. DOIs are case-insensitive, so this is clean_doi lowercased."""
    return clean_doi(doi).lower()


def extract_doi(text: str) -> str | None:
    """Return the first DOI in `text` (e.g. a publisher URL), cleaned, without any URL query or fragment."""
    match = DOI_RE.search(text)
    return clean_doi(re.split(r"[?#]", match.group(1))[0]) if match else None


def normalize_title(title: str) -> str:
    """Title key: accents folded, case folded, punctuation dropped. Empty for titles with no Latin letters or digits."""
    decomposed = unicodedata.normalize("NFKD", title)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    words = re.sub(r"[^0-9a-z]+", " ", ascii_only.casefold())
    return " ".join(words.split())


def parse_paper_id(input_str: str) -> str:
    """Convert user input (arXiv ID or URL, S2 URL or SHA, DOI or doi.org URL) to an S2 API paper_id.

    Returns a string suitable for the S2 API paper lookup endpoint, e.g.:
    - "ARXIV:2408.16532" for arXiv inputs, including arXiv's own DOIs (10.48550/arXiv.*)
    - "ebdbded60f48131ed7ba73807c3c086993a96f89" for S2 SHA inputs
    - "DOI:10.1109/ICASSP.2023.10095827" for DOI inputs (see clean_doi)
    """
    input_str = input_str.strip()
    if not input_str:
        raise ValueError("Got empty string for paper identifier.")

    s2_url_match = S2_URL_RE.search(input_str)
    if s2_url_match:
        return s2_url_match.group(1).lower()

    if input_str.upper().startswith("CORPUSID:"):
        return input_str

    # DOIs before arXiv: a DOI can contain an arXiv-like substring
    if _DOI_PREFIX_RE.match(input_str) or input_str.startswith("10."):
        doi = clean_doi(input_str)
        arxiv_doi_match = _ARXIV_DOI_RE.match(doi)
        if arxiv_doi_match:
            return f"ARXIV:{arxiv_doi_match.group(1)}"
        return f"DOI:{doi}"

    arxiv_id = extract_arxiv_id(input_str)
    if arxiv_id:
        return f"ARXIV:{arxiv_id}"

    if re.fullmatch(r"[0-9a-f]{40}", input_str, re.IGNORECASE):
        return input_str.lower()

    raise ValueError(f"Could not parse paper identifier: {input_str!r}")


def dedup_keys(
    *,
    s2_id: str | None = None,
    arxiv_id: str | None = None,
    doi: str | None = None,
    title: str | None = None,
) -> list[str]:
    """Namespaced keys a paper is known by, strongest first: s2, arxiv, doi, title.

    Compare keys with same_paper. They are in-memory comparison keys, not a
    storage format: normalization may change between versions, so persist the
    raw fields and rebuild keys when loading.
    """
    keys = []
    if s2_id:
        keys.append(f"s2:{s2_id.lower()}")
    if doi and (arxiv_doi_match := _ARXIV_DOI_RE.match(clean_doi(doi))):
        arxiv_id = arxiv_id or arxiv_doi_match.group(1)
    if arxiv_id:
        keys.append(f"arxiv:{strip_arxiv_version(arxiv_id)}")
    if doi:
        keys.append(f"doi:{normalize_doi(doi)}")
    if title and (title_key := normalize_title(title)):
        keys.append(f"title:{title_key}")
    return keys


def same_paper(a_keys: list[str], b_keys: list[str]) -> bool:
    """Whether two dedup_keys lists describe the same paper.

    A shared s2, arxiv or doi key means the same paper. Different values in the
    same strong namespace mean different papers, whatever the titles say. A
    shared title counts only when neither of those decides.
    """
    shared = set(a_keys) & set(b_keys)
    if any(k.split(":", 1)[0] in _STRONG_KEY_NAMESPACES for k in shared):
        return True
    for namespace in _STRONG_KEY_NAMESPACES:
        prefix = f"{namespace}:"
        if any(k.startswith(prefix) for k in a_keys) and any(k.startswith(prefix) for k in b_keys):
            return False
    return any(k.startswith("title:") for k in shared)
