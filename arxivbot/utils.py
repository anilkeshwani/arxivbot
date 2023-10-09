from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import arxiv
import yaml
from pathvalidate import sanitize_filename


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


# arXiv


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


# Obsidian


def get_author_wiki(author_name, people_dir: Path | str = "People"):
    _author_page = Path(people_dir, sanitize_filename(author_name))
    return f"[[{str(_author_page)} | {author_name}]]"


def collect_paper_yaml(arxiv_paper: arxiv.arxiv.Result, notion_entry: dict | None) -> str:
    frontmatter_fields = {
        "title": arxiv_paper.title,
        "authors": [author.name for author in arxiv_paper.authors],
        "published": arxiv_paper.published.isoformat(),
        "link": arxiv_paper.entry_id,
        "code": notion_entry["Code"] if notion_entry is not None else "",
        "page": notion_entry["Page"] if notion_entry is not None else "",
        "demo": notion_entry["Demo"] if notion_entry is not None else "",
        "tags": notion_entry["Tags"] if notion_entry is not None else "",
    }
    frontmatter = yaml.dump(frontmatter_fields, sort_keys=False, allow_unicode=True)
    return "---" + "\n" + frontmatter + "---" + "\n"


def write_obsidian_paper(
    arxiv_paper: arxiv.arxiv.Result,
    notion_entry: dict | None,
    obsidian_papers_dir: Path,
    log_fileexistserror: bool = False,
) -> str:
    MD_LINE_ENDING = "  \n"
    frontmatter = collect_paper_yaml(arxiv_paper, notion_entry)
    _authors_wikified = ", ".join([get_author_wiki(author.name) for author in arxiv_paper.authors])
    arxiv_paper_summary = arxiv_paper.summary.replace("-\n", "-").replace("\n", " ")
    published: datetime = arxiv_paper.published  # type: ignore
    published_pretty = inflect_day(published.day) + published.strftime(" %B %Y (%A) @ %H:%M:%S")
    metadata_fields = (
        f"Title: {arxiv_paper.title}",
        f"Authors: {_authors_wikified}",
        f"Published: {published_pretty}",
        f"Link: {arxiv_paper.entry_id}",
    )

    inline_metadata = MD_LINE_ENDING.join(metadata_fields)
    abstract_callout = MD_LINE_ENDING.join(("> [!abstract]", f"> {arxiv_paper_summary}"))
    obsidian_paper = frontmatter + "\n" + inline_metadata + "\n\n" + abstract_callout + "\n\n" "---" + "\n\n"

    filename = sanitize_filename(arxiv_paper.title.replace(".", " "))
    obsidian_paper_path = (obsidian_papers_dir / filename).with_suffix(".md")
    try:
        with open(obsidian_paper_path, "x") as f:
            f.write(obsidian_paper)
    except FileExistsError as fee:
        LOGGER.info("Skipping. Paper already present in database:")
        LOGGER.info(str(obsidian_paper_path))
        if log_fileexistserror:
            LOGGER.exception(fee)
    return obsidian_paper
