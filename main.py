#!/usr/bin/env python

from __future__ import annotations

import arxiv
import notion
from arxiv import SortCriterion, SortOrder
from typer import run


"""
def main(
    query: str,
    id_list: list[str] = [],
    max_results: int = 10,
    sort_by: SortCriterion = "submittedDate",
    sort_order: SortOrder = "descending",
    coerce_to_list: bool = True,
):
    search = arxiv.Search(
        query=query,
        id_list=id_list,
        max_results=max_results,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    results = search.results()
    if coerce_to_list:
        results = list(results)
    for result in results:
        print(f"{result.title} - {result.published}", end="\n\n")
    return results

if __name__ == "__main__":
    run(main)
"""

from notion.client import NotionClient


# Obtain the `token_v2` value by inspecting your browser cookies on a logged-in (non-guest) session on Notion.so
client = NotionClient(token_v2="secret_in3t0eYVXryTuLb1kcz3CDYIehu6gTuhvaP13coQpNZ")

# Replace this URL with the URL of the page you want to edit
page = client.get_block("https://www.notion.so/Test-da3cb9863df944efa9c5aaf753cccfce")

print("The old title is:", page.title)

# Note: You can use Markdown! We convert on-the-fly to Notion's internal formatted text data structure.
page.title = "The title has now changed, and has *live-updated* in the browser!"
