#!/usr/bin/env python

import argparse
import re
from pathlib import Path


def find_arxiv_links(text):
    """Find arXiv IDs in URLs like arxiv.org/abs/YYMM.NNNNN or arxiv.org/pdf/YYMM.NNNNN."""
    pattern = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)")
    return pattern.findall(text)


def clargs():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir", help="path to parent directory to search", type=Path)
    parser.add_argument("ext", help="file extension to search for", type=str)
    return parser.parse_args()


if __name__ == "__main__":
    verbose = False
    n_hits = 0
    args = clargs()
    filepaths = args.dir.rglob(f"*.{args.ext}")
    for filepath in filepaths:
        with open(filepath, "r") as f:
            text = f.read()
        hits = find_arxiv_links(text)
        if hits:
            for hit in hits:
                if verbose:
                    print(f"Found arXiv link in {filepath}: {hit}")
                else:
                    print(hit)
                n_hits += 1
    if verbose:
        print(f"Found {n_hits} hits.")
