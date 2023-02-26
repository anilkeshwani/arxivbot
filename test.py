from __future__ import annotations

import os
from argparse import ArgumentParser
from datetime import datetime

import arxiv
from dotenv import load_dotenv
from notion_client import Client


def search_arxiv(
    query: str | None = None,
    id_list: list[str] = [],
    max_results: int = 10,
    sort_by=arxiv.SortCriterion.SubmittedDate,
    sort_order=arxiv.SortOrder.Descending,
):
    kwargs = {"id_list": id_list, "max_results": max_results, "sort_by": sort_by}
    if query is not None:
        kwargs["query"] = query  # type: ignore
    search = arxiv.Search(**kwargs)
    return search.results()


def main(arxiv_id_list: list[str]):
    load_dotenv()  # load READING_LIST_DATABASE_ID from .env file
    notion = Client(auth=os.environ["NOTION_TOKEN"])  # must be exported as environment variable
    arxiv_paper = next(search_arxiv(id_list=[arxiv_id]))
    new_arxiv_entry = {
        "Name": {"title": [{"text": {"content": arxiv_paper.title}}]},
        "Published": {"date": {"start": arxiv_paper.published.isoformat()}},
        "Authors": {
            "multi_select": [{"color": "default", "name": author.name} for author in arxiv_paper.authors],
            "type": "multi_select",
        },
        "Topics": {"multi_select": [{"name": arxiv_paper.primary_category}], "type": "multi_select"},
        "Type": {
            "select": {"name": "arXiv"},
            "type": "select",
        },
        "Link": {"type": "url", "url": arxiv_paper.entry_id},
        "Added": {"date": {"start": datetime.now().isoformat()}},
    }
    notion.pages.create(parent={"database_id": os.getenv("READING_LIST_DATABASE_ID")}, properties=new_arxiv_entry)


def clargs():
    parser = ArgumentParser()
    parser.add_argument("arxiv_id_list", type=str, nargs="+")
    """
    # arguments retained for posterity in case of future expansion of functionality. Not currently supported.
    parser.add_argument("--query", type=str, default=None)
    parser.add_argument("--max_results", type=int, default=1)
    parser.add_argument("--sort_by", type=str, default=arxiv.SortCriterion.SubmittedDate)
    parser.add_argument("--sort_order", type=str, default=arxiv.SortOrder.Descending)
    """
    return parser.parse_args()


if __name__ == "__main__":
    args = clargs()
    main(args.arxiv_id)
