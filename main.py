from __future__ import annotations

import os
from argparse import ArgumentParser
from datetime import datetime

import arxiv
from dotenv import load_dotenv
from notion_client import Client


def search_arxiv(
    id_list: list[str],
    max_results: int,
    query: str | None = None,
    sort_by=arxiv.SortCriterion.SubmittedDate,
    sort_order=arxiv.SortOrder.Descending,
):
    kwargs = {"id_list": id_list, "max_results": max_results, "sort_by": sort_by, "sort_order": sort_order}
    if query is not None:
        kwargs["query"] = query  # type: ignore
    search = arxiv.Search(**kwargs)
    return search.results()


def main(arxiv_id_list: list[str], max_results: int, add_topic_tag: bool = True, add_arxiv_type: bool = True):
    load_dotenv()  # load READING_LIST_DATABASE_ID from .env file
    notion = Client(auth=os.environ["NOTION_TOKEN"])  # must be exported as environment variable
    for arxiv_paper in search_arxiv(id_list=arxiv_id_list, max_results=max_results):
        new_arxiv_entry = {
            "Name": {"title": [{"text": {"content": arxiv_paper.title}}]},
            "Published": {"date": {"start": arxiv_paper.published.isoformat()}},
            "Authors": {
                "multi_select": [{"color": "default", "name": author.name} for author in arxiv_paper.authors],
                "type": "multi_select",
            },
            "Link": {"type": "url", "url": arxiv_paper.entry_id},
            "Added": {"date": {"start": datetime.now().isoformat()}},
        }
        if add_topic_tag:
            new_arxiv_entry.update(
                {"Topics": {"multi_select": [{"name": arxiv_paper.primary_category}], "type": "multi_select"}}
            )
        if add_arxiv_type:
            new_arxiv_entry.update({"Type": {"select": {"name": "arXiv"}, "type": "select"}})
        notion.pages.create(parent={"database_id": os.getenv("READING_LIST_DATABASE_ID")}, properties=new_arxiv_entry)


def clargs():
    parser = ArgumentParser()
    parser.add_argument("arxiv_id_list", type=str, nargs="+")
    parser.add_argument("--max_results", type=int, default=10**10)
    parser.add_argument("--add_topic_tag", type=bool, default=False)
    parser.add_argument("--add_arxiv_type", type=bool, default=False)
    """
    # arguments retained for posterity in case of future expansion of functionality. Not currently supported.
    parser.add_argument("--query", type=str, default=None)
    parser.add_argument("--sort_by", type=str, default=arxiv.SortCriterion.SubmittedDate)
    parser.add_argument("--sort_order", type=str, default=arxiv.SortOrder.Descending)
    """
    return parser.parse_args()


if __name__ == "__main__":
    args = clargs()
    main(args.arxiv_id_list, args.max_results, add_topic_tag=args.add_topic_tag, add_arxiv_type=args.add_arxiv_type)
