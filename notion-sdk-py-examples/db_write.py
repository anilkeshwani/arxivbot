import json
import os
import uuid
from pprint import pprint

from notion_client import Client


notion_token = os.environ["NOTION_TOKEN"]
notion_page_id = ""
notion_database_id = ""


def write_text(client, page_id, text, type="paragraph"):
    client.blocks.children.append(
        block_id=page_id,
        children=[
            {"object": "block", "type": type, type: {"rich_text": [{"type": "text", "text": {"content": text}}]}}
        ],
    )


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


def create_simple_blocks_from_content(client, content):

    page_simple_blocks = []

    for block in content:

        block_id = block["id"]
        block_type = block["type"]
        has_children = block["has_children"]
        rich_text = block[block_type].get("rich_text")

        if not rich_text:
            return

        simple_block = {"id": block_id, "type": block_type, "text": rich_text[0]["plain_text"]}

        if has_children:
            nested_children = read_text(client, block_id)
            simple_block["children"] = create_simple_blocks_from_content(client, nested_children)

        page_simple_blocks.append(simple_block)

    return page_simple_blocks


def write_row(client, database_id, user_id, event, date):

    client.pages.create(
        **{
            "parent": {"database_id": database_id},
            "properties": {
                "UserId": {"title": [{"text": {"content": user_id}}]},
                "Event": {"select": {"name": event}},
                "Date": {"date": {"start": date}},
            },
        }
    )


def main():
    client = Client(auth=notion_token)

    user_id = str(uuid.uuid4())
    event = "Visitor"
    date = "2022-12-25"

    write_row(client, notion_database_id, user_id, event, date)


if __name__ == "__main__":
    main()
