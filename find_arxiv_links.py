#!/usr/bin/env python

import argparse
import re
from pathlib import Path


# return string matches for the regex pattern: arxiv.org\/...\/[0-9]{4}\.[0-9]{5}
def find_arxiv_links(text):
    pattern = re.compile(r"arxiv.org\/...\/([0-9]{4}\.[0-9]{5}v?[0-9]*)")
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
