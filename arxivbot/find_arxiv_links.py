#!/usr/bin/env python

import argparse
from pathlib import Path

from arxivbot.identifiers import ARXIV_URL_RE


def find_arxiv_links(text):
    """Return the arXiv IDs (with any version suffix) of every arXiv link in `text`."""
    return ARXIV_URL_RE.findall(text)


def clargs():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir", help="path to parent directory to search", type=Path)
    parser.add_argument("ext", help="file extension to search for", type=str)
    parser.add_argument("--verbose", "-v", action="store_true", help="print file paths alongside arXiv IDs")
    return parser.parse_args()


if __name__ == "__main__":
    args = clargs()
    verbose = args.verbose
    n_hits = 0
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
