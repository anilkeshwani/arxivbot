from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from pprint import pformat, pprint

from notion_client import Client
from typer import Argument, Option, run


notion_token = os.environ["NOTION_TOKEN"]


def write_dict_to_file_as_json(content: dict, file_name: Path | str):
    with open(file_name, "w") as f:
        f.write(json.dumps(content, ensure_ascii=False, indent=4, sort_keys=True))


def read_text(client, page_id):
    response = client.blocks.children.list(block_id=page_id)
    return response["results"]


def safe_get(data, dot_chained_keys):
    """
    {'a': {'b': [{'c': 1}]}}
    safe_get(data, 'a.b.0.c') -> 1
    """
    keys = dot_chained_keys.split(".")
    for key in keys:
        try:
            if isinstance(data, list):
                try:
                    data = data[int(key)]
                except ValueError as e:
                    raise ValueError(f"Key {key} is not an integer with list data: \n{pformat(data)}")
            else:
                data = data[key]
        except (KeyError, TypeError, IndexError):
            return None
    return data


def main(notion_database_id: str = Argument(..., help="Notion database ID")):
    client = Client(auth=notion_token)

    db_info = client.databases.retrieve(database_id=notion_database_id)
    write_dict_to_file_as_json(db_info, "db_info.json")  # type: ignore

    db_rows = client.databases.query(database_id=notion_database_id)
    write_dict_to_file_as_json(db_rows, "db_rows.json")  # type: ignore

    simple_rows = []
    for row in db_rows["results"]:  # type: ignore
        published = safe_get(row, "properties.Published.date.start")
        status = safe_get(row, "properties.Status.select.name")
        authors = safe_get(row, "properties.Authors.rich_text.0.plain_text")
        simple_rows.append(
            {
                "published": published,
                "status": status,
                "authors": authors,
            }
        )
    write_dict_to_file_as_json(simple_rows, "simple_rows.json")  # type: ignore


if __name__ == "__main__":
    run(main)
