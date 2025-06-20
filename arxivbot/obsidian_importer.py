#!/usr/bin/env python

from __future__ import annotations

import csv
import logging
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

import arxiv
import yaml
from pathvalidate import sanitize_filename

from arxivbot.constants import (
    DEFAULT_PAPER_TAGS,
    PAPERS_DIR,
    PDFS_DIR,
    PDFS_INDEX,
    PDFS_INDEX_FIELD_NAMES,
    PDFS_INDEX_ID,
)
from arxivbot.utils import canonicalise_arxiv, inflect_day


# TODO is this best practice?
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(logging.StreamHandler())


def get_author_wiki(author_name, people_dir: Path | str = "People"):
    _author_page = Path(people_dir, sanitize_filename(author_name))
    return f"[[{str(_author_page)}|{author_name}]]"


def collect_paper_yaml(arxiv_paper: arxiv.Result, notion_entry: dict | None) -> str:
    frontmatter_fields = {
        "title": arxiv_paper.title,
        "authors": [author.name for author in arxiv_paper.authors],
        "published": arxiv_paper.published.isoformat(),
        "link": arxiv_paper.entry_id,
        "code": notion_entry["Code"] if notion_entry is not None else "",
        "page": notion_entry["Page"] if notion_entry is not None else "",
        "demo": notion_entry["Demo"] if notion_entry is not None else "",
        "tags": notion_entry["Tags"] if notion_entry is not None else DEFAULT_PAPER_TAGS,
    }
    frontmatter = yaml.dump(frontmatter_fields, sort_keys=False, allow_unicode=True)
    return "---" + "\n" + frontmatter + "---" + "\n"


def write_obsidian_paper(
    arxiv_paper: arxiv.Result,
    notion_entry: dict | None,
    obsidian_papers_dir: Path,
    obsidian_pdfs_dir: Path,
    download_pdf: bool,
    log_fileexistserror: bool = False,
) -> str:
    MD_LINE_ENDING = "  \n"
    frontmatter = collect_paper_yaml(arxiv_paper, notion_entry)
    _authors_wikified = ", ".join([get_author_wiki(author.name) for author in arxiv_paper.authors])
    arxiv_paper_summary = arxiv_paper.summary.replace("-\n", "-").replace("\n", " ")
    published: datetime = arxiv_paper.published
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
            LOGGER.info(str(obsidian_paper_path))
    except FileExistsError as fee:
        LOGGER.info("Skipping. Paper already present in database:")
        LOGGER.info(str(obsidian_paper_path))
        if log_fileexistserror:
            LOGGER.exception(fee)

    if download_pdf:
        pdf_filename = f"{filename}.pdf"
        pdf_path = obsidian_pdfs_dir / pdf_filename  # co-opted from arxiv source code
        if pdf_path.exists():
            LOGGER.info("Skipping. PDF already present in database:")
            LOGGER.info(str(pdf_path))
        else:
            arxiv_paper.download_pdf(dirpath=str(obsidian_pdfs_dir), filename=pdf_filename)
            LOGGER.info(str(pdf_path))

        # add pdf to index as CSV row using csv module if not already present by checking entry_id
        pdfs_index = list(csv.reader(open(PDFS_INDEX, "r"), delimiter="\t"))
        assert pdfs_index[0] == PDFS_INDEX_FIELD_NAMES, "PDFs index header is incorrect. Check PDFS_INDEX_FIELD_NAMES."
        if arxiv_paper.entry_id in [PDFS_INDEX_FIELD_NAMES.index(PDFS_INDEX_ID) for row in pdfs_index]:
            LOGGER.info(f"Skipping addition of PDF to index ({PDFS_INDEX}). PDF already present in index.")
        else:
            current_time = datetime.now().isoformat()
            fields = (arxiv_paper.entry_id, published, current_time, pdf_filename.removesuffix(".pdf"))
            with open(PDFS_INDEX, "a") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(fields)
                f.write("\n")
    return obsidian_paper


def main():
    parser = ArgumentParser()
    parser.add_argument("id_list", type=str, nargs="+")
    parser.add_argument("--max_results", type=int, default=10**10)
    parser.add_argument("--no_pdf", action="store_false", dest="download_pdf")
    args = parser.parse_args()
    args.id_list = [canonicalise_arxiv(arxiv_id) for arxiv_id in args.id_list]
    for arxiv_paper in arxiv.Client().results((arxiv.Search(id_list=args.id_list, max_results=args.max_results))):
        write_obsidian_paper(arxiv_paper, None, PAPERS_DIR, PDFS_DIR, args.download_pdf, False)


if __name__ == "__main__":
    main()
