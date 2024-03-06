import os
from pprint import pprint

from notion_client import Client


notion_token = os.environ["NOTION_TOKEN"]
notion_page_id = ""


def write_text(client, page_id, text, type):
    client.blocks.children.append(
        block_id=page_id,
        children=[
            {"object": "block", "type": type, type: {"rich_text": [{"type": "text", "text": {"content": text}}]}}
        ],
    )


def main():
    client = Client(auth=notion_token)

    write_text(client, notion_page_id, "Hello World!", "to_do")


if __name__ == "__main__":
    main()
