#!/usr/bin/env python

from __future__ import annotations

import arxiv
from arxiv import SortCriterion, SortOrder
from typer import Option, run


def main(
    query: str = "",
    id_list: list[str] = Option([], help="Comma-separated list of arXiv IDs"),
    max_results: int = 10,
    sort_by: SortCriterion = "submittedDate",
    sort_order: SortOrder = "descending",
    coerce_to_list: bool = True,
    verbose: bool = True,
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
    if verbose:
        for result in results:
            print(f"{result.title} - {result.published}", end="\n\n")
    return results


if __name__ == "__main__":
    run(main)
