from __future__ import annotations

import json
import re
from pprint import pprint

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent


def extract_metadata(url: str) -> dict:
    ua = UserAgent()
    headers = {"User-Agent": ua.random}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Error: Unable to access the URL. Status code: {response.status_code}")
    soup = BeautifulSoup(response.content, "html.parser")
    script_tags = soup.find_all("script")
    metadata_content = None
    for script_tag in script_tags:
        if script_tag.string and "xplGlobal.document.metadata" in script_tag.string:
            metadata_content = script_tag.string.strip()
            break
    if metadata_content is None:
        raise RuntimeError("Error: xplGlobal.document.metadata not found in the page.")
    json_match = re.search(r"xplGlobal\.document\.metadata=(\{.*\});", metadata_content)
    if not json_match:
        raise RuntimeError("Error: JSON object not found in xplGlobal.document.metadata.")
    metadata_json = json_match.group(1)
    metadata = json.loads(metadata_json)
    return metadata


def extract_salient_fields_from_metadata(metadata: dict) -> dict:
    salient = {}
    fields = [
        "publicationDate",
        "displayPublicationTitle",
        "displayPublicationDate",
        "articleNumber",
        "abstract",
        "displayDocTitle",
    ]
    for field in fields:
        salient.update({field: metadata[field]})
    authors = [author["name"] for author in metadata["authors"]]
    salient.update({"authors": authors})
    return salient


# Example usage:
url = "https://ieeexplore.ieee.org/document/9381663"
metadata = extract_metadata(url)
salient = extract_salient_fields_from_metadata(metadata)
pprint(salient, width=180)
