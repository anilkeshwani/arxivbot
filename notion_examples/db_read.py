import json
import os
import uuid
from pprint import pprint

from notion_client import Client


notion_token = os.environ["NOTION_TOKEN"]
notion_page_id = ""
notion_database_id = ""


def write_dict_to_file_as_json(content, file_name):
    content_as_json_str = json.dumps(content)

    with open(file_name, "w") as f:
        f.write(content_as_json_str)


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
                data = data[int(key)]
            else:
                data = data[key]
        except (KeyError, TypeError, IndexError):
            return None
    return data


def main():
    client = Client(auth=notion_token)

    db_info = client.databases.retrieve(database_id=notion_database_id)

    write_dict_to_file_as_json(db_info, "db_info.json")

    db_rows = client.databases.query(database_id=notion_database_id)

    write_dict_to_file_as_json(db_rows, "db_rows.json")

    simple_rows = []

    for row in db_rows["results"]:
        user_id = safe_get(row, "properties.UserId.title.0.plain_text")
        date = safe_get(row, "properties.Date.date.start")
        event = safe_get(row, "properties.Event.select.name")

        simple_rows.append({"user_id": user_id, "date": date, "event": event})

    write_dict_to_file_as_json(simple_rows, "simple_rows.json")


if __name__ == "__main__":
    main()
