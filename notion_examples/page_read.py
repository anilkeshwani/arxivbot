import json
from pprint import pprint

from notion_client import Client


notion_token = ""
notion_page_id = ""


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


def main():
    client = Client(auth=notion_token)

    content = read_text(client, notion_page_id)

    write_dict_to_file_as_json(content, "content.json")

    simple_blocks = create_simple_blocks_from_content(client, content)

    write_dict_to_file_as_json(simple_blocks, "simple_blocks.json")


if __name__ == "__main__":
    main()
