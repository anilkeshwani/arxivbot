#!/usr/bin/env python

from argparse import ArgumentParser

import arxiv

from constants import PAPERS_DIR
from utils import canonicalise_arxiv, write_obsidian_paper


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("id_list", type=str, nargs="+")
    parser.add_argument("--max_results", type=int, default=10**10)
    args = parser.parse_args()
    args.id_list = [canonicalise_arxiv(arxiv_id) for arxiv_id in args.id_list]
    for arxiv_paper in arxiv.Search(**vars(args)).results():
        write_obsidian_paper(arxiv_paper, None, PAPERS_DIR)
