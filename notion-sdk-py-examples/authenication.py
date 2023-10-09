import os
from pprint import pprint

from notion_client import Client


notion_token = os.environ["NOTION_TOKEN"]
notion_page_id = ""


def main():
    client = Client(auth=notion_token)

    page_response = client.pages.retrieve(notion_page_id)

    pprint(page_response, indent=2)


if __name__ == "__main__":
    main()
