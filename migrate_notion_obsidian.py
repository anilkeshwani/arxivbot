#!/usr/bin/env python

"""
Fields required from Notion db export: Tags, Code, Demo, Page
"""


from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from pprint import pprint
from urllib.parse import urlparse

import arxiv
import yaml
from pathvalidate import sanitize_filename

from main import canonicalise_arxiv
from utils import inflect_day


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(logging.StreamHandler())

# constants
ARXIV_MIGRATION_COMPLETE = True  # lets me move on to non-arXiv migration
VERBOSE = False

# Obsidian-related
OBSIDIAN_VAULT_DIR = Path("/Users/anilkeshwani/Desktop/journal/")
PAPERS_DIR = OBSIDIAN_VAULT_DIR / "Papers"

# migration
REQUIRED_EXPORTED_FIELDS: tuple = ("Name", "Tags", "Link", "Code", "Demo", "Page")  # retain name for debugging
BATCH_SIZE: int = 50  # batch size when making calls to arXiv API
EXPORTED_NOTION_DB_PATH = OBSIDIAN_VAULT_DIR / "data/papers_db_notion.csv"


def get_author_wiki(author_name, people_dir: Path | str = "People"):
    _author_page = Path(people_dir, sanitize_filename(author_name))
    return f"[[{str(_author_page)} | {author_name}]]"


def collect_paper_yaml(arxiv_paper: arxiv.arxiv.Result, notion_entry: dict) -> str:
    frontmatter_fields = {
        "title": arxiv_paper.title,
        "authors": [author.name for author in arxiv_paper.authors],
        "published": arxiv_paper.published.isoformat(),
        "link": arxiv_paper.entry_id,
        "code": notion_entry["Code"],
        "page": notion_entry["Page"],
        "demo": notion_entry["Demo"],
        "tags": notion_entry["Tags"],
    }
    frontmatter = yaml.dump(frontmatter_fields, sort_keys=False, allow_unicode=True)
    return "---" + "\n" + frontmatter + "---" + "\n"


def write_obsidian_paper(
    arxiv_paper: arxiv.arxiv.Result, notion_entry: dict, obsidian_papers_dir: Path, log_fileexistserror: bool = False
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


if __name__ == "__main__":
    # read the database of papers exported from Notion
    with open(EXPORTED_NOTION_DB_PATH, "r") as f:
        papers_db = list(csv.reader(f))
    headers = papers_db.pop(0)
    # rename headers
    headers[0] = "Name"
    headers[headers.index("Website or Post")] = "Page"

    # sanitize + prepare the database entries
    entries: list[dict] = []
    non_arxiv_entries: list[dict] = []

    for i, entry in enumerate(papers_db):
        entry_dict = {k: v for k, v in zip(headers, entry) if k in REQUIRED_EXPORTED_FIELDS}
        entry_dict["Tags"] = [t.replace(" ", "-") for t in entry_dict["Tags"].split(", ")]  # type: ignore
        entry_dict["Tags"] = [t.replace("content-length", "context-length") for t in entry_dict["Tags"]]  # type: ignore
        # find the non-arxiv "links"
        if urlparse(entry_dict["Link"]).netloc != "arxiv.org":
            non_arxiv_entries.append(entry_dict)
        else:
            entry_dict["arxiv_id"] = canonicalise_arxiv(entry_dict["Link"])
            entries.append(entry_dict)

    if not ARXIV_MIGRATION_COMPLETE:
        n_arxiv = len(entries)
        arxiv_id_list: list[str] = [entry["arxiv_id"] for entry in entries]
        n_batches = -(n_arxiv // -BATCH_SIZE)  # ceil

        for idx_batch in range(n_batches):
            if (idx_batch + 1) == n_batches:
                print(f"Retrieving entries {(BATCH_SIZE * idx_batch, n_arxiv)}")
                results = arxiv.Search(id_list=arxiv_id_list[BATCH_SIZE * idx_batch : n_arxiv]).results()
                entries_slice = entries[BATCH_SIZE * idx_batch : n_arxiv]
                for arxiv_paper, notion_entry in zip(results, entries_slice):
                    write_obsidian_paper(arxiv_paper, notion_entry, PAPERS_DIR)
            else:
                print(f"Retrieving entries {(BATCH_SIZE * idx_batch, BATCH_SIZE * (idx_batch + 1))}")
                results = arxiv.Search(
                    id_list=arxiv_id_list[BATCH_SIZE * idx_batch : BATCH_SIZE * (idx_batch + 1)]
                ).results()
                entries_slice = entries[BATCH_SIZE * idx_batch : BATCH_SIZE * (idx_batch + 1)]
                for arxiv_paper, notion_entry in zip(results, entries_slice):
                    write_obsidian_paper(arxiv_paper, notion_entry, PAPERS_DIR)

    pprint([_["Name"] for _ in non_arxiv_entries])  # show the papers that we haven't saved via arXiv links
