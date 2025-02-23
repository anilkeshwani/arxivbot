#!/usr/bin/env python

from __future__ import annotations

import os
from argparse import ArgumentParser
from datetime import datetime

import arxiv
from dotenv import load_dotenv
from notion_client import Client

from arxivbot.utils import canonicalise_arxiv


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


def check_row_exists(arxiv_like: str) -> bool:
    """Check whether a row with the given arXiv ID already exists in the database.

    Args:
        arxiv_like (str): An arXiv ID or URL.

    Returns:
        tuple[bool, str]: Boolean indicating whether the row exists, and the normalized arXiv ID.
    """
    load_dotenv()  # load READING_LIST_DATABASE_ID from .env file
    notion = Client(auth=os.environ["NOTION_TOKEN"])  # must be exported as environment variable
    database_id = os.environ["READING_LIST_DATABASE_ID"]
    arxiv_id = canonicalise_arxiv(arxiv_like)
    rows = notion.databases.query(database_id=database_id, filter={"property": "Link", "url": {"equals": arxiv_like}})
    return len(rows["results"]) != 0


def main(
    arxiv_list: list[str],
    max_results: int,
    add_abstract: bool = True,
    add_topic_tag: bool = True,
    add_arxiv_type: bool = True,
):
    load_dotenv()  # load READING_LIST_DATABASE_ID from .env file
    load_dotenv("credentials.env")
    notion = Client(auth=os.environ["NOTION_TOKEN"])  # must be exported as environment variable
    database_id = os.environ["READING_LIST_DATABASE_ID"]
    arxiv_list = [canonicalise_arxiv(arxiv_like) for arxiv_like in arxiv_list]
    for arxiv_paper in search_arxiv(id_list=arxiv_list, max_results=max_results):
        row_present = check_row_exists(arxiv_paper.entry_id)
        if row_present:
            print(f"Skipping {arxiv_paper.title} (URL: {arxiv_paper.entry_id}) as it already exists in the database.")
            continue
        else:
            new_arxiv_entry = {
                "Name": {"title": [{"text": {"content": arxiv_paper.title}}]},
                "Published": {"date": {"start": arxiv_paper.published.isoformat()}},  # type: ignore
                "Authors": {
                    "multi_select": [{"color": "default", "name": author.name} for author in arxiv_paper.authors],
                    "type": "multi_select",
                },
                "Link": {"type": "url", "url": arxiv_paper.entry_id},
                "Added": {"date": {"start": datetime.now().isoformat()}},
            }
            if add_topic_tag:
                new_arxiv_entry.update(
                    {"Tags": {"multi_select": [{"name": arxiv_paper.primary_category}], "type": "multi_select"}}
                )
            if add_arxiv_type:
                new_arxiv_entry.update({"Type": {"select": {"name": "arXiv"}, "type": "select"}})
            if add_abstract:
                children = [
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Abstract"}}]},
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": arxiv_paper.summary.replace("\n", " ")}}]
                        },
                    },
                    {"object": "block", "type": "divider", "divider": {}},  # add a page divider below the abstract
                ]
            else:  # if we're not adding the abstract, we still need to pass an empty list to the children argument
                children = []

            # create the new row in the database
            notion.pages.create(parent={"database_id": database_id}, properties=new_arxiv_entry, children=children)


def clargs():
    parser = ArgumentParser()
    parser.add_argument("arxiv_list", type=str, nargs="+")
    parser.add_argument("--max_results", type=int, default=10**10)
    parser.add_argument("--add_abstract", type=bool, default=True)
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
    main(
        args.arxiv_list,
        args.max_results,
        args.add_abstract,
        add_topic_tag=args.add_topic_tag,
        add_arxiv_type=args.add_arxiv_type,
    )
