# arxivbot

## Feature Requests 

- [ ] provide cleaner abstracts
  - [ ] parse URLs and hyperlink them
  - [ ] parse latex and render it as an equation
- [ ] provide integration via Telegram so that users can send their link to an authenticated channel and GitHub actions will trigger uploads nightly or, better, in response to a trigger triggered by Telegram
- [x] write abstract to entries as text
- [x] add check for duplicate entries before adding to database (i.e. if arXiv ID is already in database)

## Credentials

_credentials_template.env_ is a copy of (template for) a file, _credentials.env_, which should be placed in the same (top-level) directory with your Notion Integration token for authenticating. This is more convenient that exporting it each time you use the tool. 

## Resources

- arxiv
  - http://lukasschwab.me/arxiv.py/index.html
  - Result http://lukasschwab.me/arxiv.py/index.html#Result
  - Search http://lukasschwab.me/arxiv.py/index.html#Search
- arxiv API 
  - https://info.arxiv.org/help/api/basics.html#quickstart
  - https://info.arxiv.org/help/api/user-manual.html#sort
  - https://info.arxiv.org/help/api/user-manual.html#python_simple_example
  - 
- https://www.notion.so/my-integrations
- https://developers.notion.com/reference/update-a-database
- what you actually want - to update or add a row of a database
  - https://developers.notion.com/reference/patch-page
  - https://developers.notion.com/reference/post-page
  - info about property of page's parent db (must match) https://developers.notion.com/reference/property-object

similar projects:
- https://github.com/wangjksjtu/arxiv2notionplus


## Directory structure

```
.
├── LICENSE
├── README.md
├── arxivbot
│   ├── __init__.py
│   ├── constants.py
│   ├── credentials.env
│   ├── credentials_template.env
│   ├── find_arxiv_links.py
│   ├── ieee_api.py
│   ├── ieee_scrape.py
│   ├── migrate_notion_obsidian.py
│   ├── notion_importer.py
│   ├── obsidian_importer.py
│   └── utils.py
├── docs
├── notion-sdk-py-examples
│   ├── README.md
│   ├── assets
│   │   └── notion-api-client-docs-map.jpg
│   ├── authenication.py
│   ├── db_read.py
│   ├── db_write.py
│   ├── page_read.py
│   └── page_write.py
├── requirements.txt
└── tests
    └── example_inputs
        └── ieee
            └── 9381661.html

8 directories, 22 files
```