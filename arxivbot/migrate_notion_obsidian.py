#!/usr/bin/env python

"""
Fields required from Notion db export: Tags, Code, Demo, Page
"""


from __future__ import annotations

import csv
import logging
from pathlib import Path
from pprint import pprint
from urllib.parse import urlparse

import arxiv

from arxivbot.constants import OBSIDIAN_VAULT_DIR, PAPERS_DIR
from arxivbot.constants import PDFS_DIR
from arxivbot.obsidian_importer import write_obsidian_paper
from arxivbot.utils import canonicalise_arxiv


LOGGER = logging.getLogger(__name__)

# constants
ARXIV_MIGRATION_COMPLETE = False  # lets me move on to non-arXiv migration
VERBOSE = False

# migration
REQUIRED_EXPORTED_FIELDS: tuple = ("Name", "Tags", "Link", "Code", "Demo", "Page")  # retain name for debugging
BATCH_SIZE: int = 50  # batch size when making calls to arXiv API
EXPORTED_NOTION_DB_PATH = OBSIDIAN_VAULT_DIR / "data/papers_db_notion.csv"


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
        client = arxiv.Client()

        for idx_batch in range(n_batches):
            if (idx_batch + 1) == n_batches:
                print(f"Retrieving entries {(BATCH_SIZE * idx_batch, n_arxiv)}")
                search = arxiv.Search(id_list=arxiv_id_list[BATCH_SIZE * idx_batch : n_arxiv])
                entries_slice = entries[BATCH_SIZE * idx_batch : n_arxiv]
                for arxiv_paper, notion_entry in zip(client.results(search), entries_slice):
                    write_obsidian_paper(arxiv_paper, notion_entry, PAPERS_DIR, PDFS_DIR, download_pdf=False)
            else:
                print(f"Retrieving entries {(BATCH_SIZE * idx_batch, BATCH_SIZE * (idx_batch + 1))}")
                search = arxiv.Search(
                    id_list=arxiv_id_list[BATCH_SIZE * idx_batch : BATCH_SIZE * (idx_batch + 1)]
                )
                entries_slice = entries[BATCH_SIZE * idx_batch : BATCH_SIZE * (idx_batch + 1)]
                for arxiv_paper, notion_entry in zip(client.results(search), entries_slice):
                    write_obsidian_paper(arxiv_paper, notion_entry, PAPERS_DIR, PDFS_DIR, download_pdf=False)

    pprint([_["Name"] for _ in non_arxiv_entries])  # show the papers that we haven't saved via arXiv links
