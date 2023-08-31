#!/usr/bin/env python

import csv
from pathlib import Path
from pprint import pprint

import arxiv
import dateutil.parser
import pathvalidate
import yaml
from dateutil.parser._parser import ParserError

from main import canonicalise_arxiv


VERBOSE = False

# Fields required from Notion db export: Tags, Link, Code, Demo, Page, Status

# fmt: off
REQUIRED_EXPORTED_FIELDS = ("Tags", "Link", "Code", "Demo", "Page", "Status")
# fmt: on

entries = []

with open("/Users/anilkeshwani/Desktop/journal/data/papers_db_notion.csv", "r") as f:
    papers_db = csv.reader(f)
    headers = next(papers_db)
    headers[0] = "Name"
    headers[headers.index("Website or Post")] = "Page"
    idx_published = headers.index("Published")
    if VERBOSE:
        print(headers)
    for i, entry in enumerate(papers_db):
        entry_dict = {k: v for k, v in zip(headers, entry)}
        entry_dict = {k: v for k, v in zip(headers, entry) if k in REQUIRED_EXPORTED_FIELDS}
        entry_dict["Tags"] = entry_dict["Tags"].split(", ")
        try:
            entry_dict["arxiv_id"] = canonicalise_arxiv(entry_dict["Link"])
        except ValueError as ve:
            entry_dict["arxiv_id"] = ""
            print("\nError canonicalizing arXiv ID for:")
            print(entry_dict["Link"])
            print(ve, end="\n\n")
        entries.append(entry_dict)

arxiv_id_list: list[str] = [entry["arxiv_id"] for entry in entries]

results = arxiv.Search(id_list=arxiv_id_list).results()
for arxiv_paper, ed in zip(results, entries):
    print(f"{arxiv_paper.title = }")
    print(f"{[author.name for author in arxiv_paper.authors] = }")
    print(f"{arxiv_paper.entry_id = }")
    print(f"{arxiv_paper.primary_category = }")
    print(f"{arxiv_paper.published.isoformat() = }")
    arxiv_paper_summary = arxiv_paper.summary.replace("\n", " ")
    print(f"{arxiv_paper_summary = }")
    print("-" * 120)
    print()

# print(yaml.dump(entry_dict, sort_keys=False, Dumper=yaml.SafeDumper))
