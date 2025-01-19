# arxivbot

## Feature Requests

- [ ] provide cleaner abstracts
  - [ ] parse URLs and hyperlink them
  - [ ] parse latex and render it as an equation
- [ ] provide integration via Telegram so that users can send their link to an authenticated channel and GitHub actions will trigger uploads nightly or, better, in response to a trigger triggered by Telegram
- [x] write abstract to entries as text
- [x] add check for duplicate entries before adding to database (i.e. if arXiv ID is already in database)
- [ ] I would love to read arXiv papers as epubs on my Kindle
    - https://tex.stackexchange.com/questions/1551/use-latex-to-produce-epub
    - https://www.reddit.com/r/MachineLearning/comments/5xtnl4/d_reading_arxiv_preprints_on_an_ereader/

## Credentials

_credentials_template.env_ is a copy of (template for) a file, _credentials.env_, which should be placed in the same (top-level) directory with your Notion Integration token for authenticating. This is more convenient that exporting it each time you use the tool.

## Semantic Scholar Resources

Move the arxivbot onto the [Semantic Scholar (S2) Academic Graph API](https://api.semanticscholar.org/api-docs/graph). 

Motivations:
- this is more general
- aggregates data from a wide array of sources - in addition to arXiv, we can directly collect from e.g. ACL, Nature etc. more easily
- easily queryable by extracting S2 paper SHA from URL (terminal)

Suggested usage: Exactly as arxivbot but with S2 URL. 

- Ideally would accept arXiv or S2 URL
    - can we extract the same metadata from both; 
    - maybe just a fallback to arXiv arxivbot if arXiv ID/URL passed?
- What does S2 give us (response) that we might want to add to the paper (meta)data?

Example S2 paper page URL:

```
https://www.semanticscholar.org/paper/WavTokenizer%3A-an-Efficient-Acoustic-Discrete-Codec-Ji-Jiang/ebdbded60f48131ed7ba73807c3c086993a96f89
```

Example Academic Graph API query:

```
https://api.semanticscholar.org/graph/v1/paper/ebdbded60f48131ed7ba73807c3c086993a96f89?fields=url,year,authors,externalIds,abstract,venue,references,influentialCitationCount,fieldsOfStudy
```

Example based on: [CLI_cURL_Papers_with_Key example](https://github.com/allenai/s2-folks/blob/3c786b3f0727cca5049afd5654494acd99b80efb/examples/Webinar%20Code%20Examples/CLI_cURL_Papers_with_Key). 

[Example response](/example_s2_academic_api_response.json)

[S2 API Tutorial](https://www.semanticscholar.org/product/api/tutorial)

- [Get Open Access PDFs](https://github.com/allenai/s2-folks/tree/3c786b3f0727cca5049afd5654494acd99b80efb/examples/python/get_open_access_pdf)
    - this is via [Open Access](https://www.openaccess.nl/en/what-is-open-access)
- [Get details about a paper - Academic Graph API](https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_get_paper)
    - See the contents of Response Schema (200 OK) in that same section for a list of all available fields that can be returned and **image below**
- See API [usage examples](https://github.com/allenai/s2-folks/tree/3c786b3f0727cca5049afd5654494acd99b80efb/examples) and [Python examples](https://github.com/allenai/s2-folks/tree/3c786b3f0727cca5049afd5654494acd99b80efb/examples/python)

![S2 Academic Graph - Details about a paper - Sample Response - 200 OK](/S2%20Academic%20Graph%20-%20Details%20about%20a%20paper%20-%20Sample%20Response%20-%20200%20OK.png)

I filled out the [S2 API key request form](https://www.semanticscholar.org/product/api#api-key-form) on 2024-12-21. 

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
